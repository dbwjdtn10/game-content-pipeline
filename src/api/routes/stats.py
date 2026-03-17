"""Statistics and overview API routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.api.main import get_db
from src.api.schemas import StatsOverviewOut, TypeStatusCount
from src.storage.models import PipelineRun
from src.storage.repository import ContentRepository

router = APIRouter()


@router.get("/overview", response_model=StatsOverviewOut)
def stats_overview(
    db: Annotated[Session, Depends(get_db)],
) -> StatsOverviewOut:
    """Return aggregate counts by content type and status, plus pipeline run count."""
    repo = ContentRepository(db)
    raw_counts = repo.count_by_type_and_status()

    total_content = sum(c["count"] for c in raw_counts)

    pipeline_run_count: int = db.execute(
        select(func.count()).select_from(PipelineRun)
    ).scalar_one()

    return StatsOverviewOut(
        total_content=total_content,
        counts=[TypeStatusCount(**c) for c in raw_counts],
        pipeline_runs=pipeline_run_count,
    )
