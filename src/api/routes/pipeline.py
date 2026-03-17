"""Pipeline management API routes."""

from __future__ import annotations

from typing import Annotated

import yaml
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from src.api.main import get_db
from src.api.schemas import (
    PipelineRunCreatedOut,
    PipelineRunOut,
    PipelineRunRequest,
)
from src.pipeline.orchestrator import PipelineOrchestrator
from src.storage.repository import PipelineRepository

router = APIRouter()


def _get_repo(db: Annotated[Session, Depends(get_db)]) -> PipelineRepository:
    return PipelineRepository(db)


def _run_pipeline_background(
    yaml_config: str,
    retry_on_fail: int,
    run_id: str,
    database_url: str,
) -> None:
    """Execute the pipeline in a background thread and persist results.

    This function creates its own DB session so it is safe to call from
    a ``BackgroundTasks`` context.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session as SASession

    eng = create_engine(database_url, pool_pre_ping=True)
    with SASession(eng) as session:
        repo = PipelineRepository(session)
        repo.update_status(run_id, "running")
        session.commit()

        try:
            orchestrator = PipelineOrchestrator(retry_on_fail=retry_on_fail)
            result = orchestrator.run(yaml_config)

            repo.update_status(run_id, result.status, result=result.to_dict())
            session.commit()
        except Exception as exc:
            repo.update_status(run_id, "failed", result={"error": str(exc)})
            session.commit()


@router.post("/run", response_model=PipelineRunCreatedOut)
def run_pipeline(
    body: PipelineRunRequest,
    background_tasks: BackgroundTasks,
    repo: Annotated[PipelineRepository, Depends(_get_repo)],
) -> PipelineRunCreatedOut:
    """Trigger a new pipeline run.

    The pipeline is executed asynchronously in the background.  Use the
    ``GET /pipeline/{id}/status`` endpoint to poll for completion.
    """
    from src.config import get_settings

    # Parse config to extract the pipeline name
    try:
        cfg = yaml.safe_load(body.yaml_config)
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid YAML: {exc}")

    pipeline_name = cfg.get("name", "unnamed_pipeline")

    run = repo.create(name=pipeline_name, config=cfg)
    # Flush and commit so the background task can find the row
    repo.session.commit()

    background_tasks.add_task(
        _run_pipeline_background,
        body.yaml_config,
        body.retry_on_fail,
        run.id,
        get_settings().database_url,
    )

    return PipelineRunCreatedOut(pipeline_id=run.id, status="pending")


@router.get("/history", response_model=list[PipelineRunOut])
def list_pipeline_runs(
    repo: Annotated[PipelineRepository, Depends(_get_repo)],
    limit: int = 50,
    offset: int = 0,
) -> list[PipelineRunOut]:
    """List recent pipeline runs."""
    runs = repo.list_runs(limit=limit, offset=offset)
    return [PipelineRunOut.model_validate(r) for r in runs]


@router.get("/{run_id}/status", response_model=PipelineRunOut)
def get_pipeline_status(
    run_id: str,
    repo: Annotated[PipelineRepository, Depends(_get_repo)],
) -> PipelineRunOut:
    """Get the current status of a pipeline run."""
    run = repo.get_by_id(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    return PipelineRunOut.model_validate(run)
