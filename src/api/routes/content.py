"""Content management API routes."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.api.main import get_db
from src.api.schemas import (
    ContentListOut,
    ContentVersionOut,
    RegenerateRequest,
    ReviewRequest,
)
from src.storage.repository import ContentRepository

router = APIRouter()


def _get_repo(db: Annotated[Session, Depends(get_db)]) -> ContentRepository:
    return ContentRepository(db)


@router.get("", response_model=ContentListOut)
def list_content(
    repo: Annotated[ContentRepository, Depends(_get_repo)],
    content_type: str | None = Query(None, description="Filter by content type"),
    status: str | None = Query(None, description="Filter by status"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> ContentListOut:
    """List content versions with optional filters."""
    if status:
        items = repo.get_by_status(status, content_type=content_type, limit=limit, offset=offset)
    else:
        items = repo.list_all(content_type=content_type, limit=limit, offset=offset)

    return ContentListOut(
        items=[ContentVersionOut.model_validate(i) for i in items],
        total=len(items),
    )


@router.get("/{version_id}", response_model=ContentVersionOut)
def get_content(
    version_id: str,
    repo: Annotated[ContentRepository, Depends(_get_repo)],
) -> ContentVersionOut:
    """Get a single content version by ID."""
    cv = repo.get_by_id(version_id)
    if cv is None:
        raise HTTPException(status_code=404, detail="Content version not found")
    return ContentVersionOut.model_validate(cv)


@router.post("/{version_id}/approve", response_model=ContentVersionOut)
def approve_content(
    version_id: str,
    body: ReviewRequest,
    repo: Annotated[ContentRepository, Depends(_get_repo)],
) -> ContentVersionOut:
    """Approve a content version."""
    cv = repo.approve(version_id, reviewed_by=body.reviewed_by, comment=body.comment)
    if cv is None:
        raise HTTPException(status_code=404, detail="Content version not found")
    return ContentVersionOut.model_validate(cv)


@router.post("/{version_id}/reject", response_model=ContentVersionOut)
def reject_content(
    version_id: str,
    body: ReviewRequest,
    repo: Annotated[ContentRepository, Depends(_get_repo)],
) -> ContentVersionOut:
    """Reject a content version."""
    cv = repo.reject(version_id, reviewed_by=body.reviewed_by, comment=body.comment)
    if cv is None:
        raise HTTPException(status_code=404, detail="Content version not found")
    return ContentVersionOut.model_validate(cv)


@router.get("/{content_type}/{content_id}/history", response_model=list[ContentVersionOut])
def get_version_history(
    content_type: str,
    content_id: str,
    repo: Annotated[ContentRepository, Depends(_get_repo)],
) -> list[ContentVersionOut]:
    """Get full version history for a content item."""
    versions = repo.get_history(content_type, content_id)
    if not versions:
        raise HTTPException(status_code=404, detail="No versions found")
    return [ContentVersionOut.model_validate(v) for v in versions]


def _regenerate_background(
    version_id: str,
    max_attempts: int,
    database_url: str,
) -> None:
    """Regenerate content in background with validation feedback loop."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session as SASession

    from src.generators import ItemGenerator, MonsterGenerator, QuestGenerator, SkillGenerator
    from src.pipeline.regenerator import ContentRegenerator
    from src.validators.balance import BalanceValidator

    eng = create_engine(database_url, pool_pre_ping=True)
    with SASession(eng) as session:
        repo = ContentRepository(session)
        cv = repo.get_by_id(version_id)
        if cv is None:
            return

        content_type = cv.content_type
        generator_map: dict[str, type] = {
            "item": ItemGenerator,
            "monster": MonsterGenerator,
            "quest": QuestGenerator,
            "skill": SkillGenerator,
        }
        generator_cls = generator_map.get(content_type)
        if generator_cls is None:
            return

        generator = generator_cls()

        # Build basic validators
        validator_fns: list[Any] = []
        bv = BalanceValidator()
        seed_items = generator.load_seed("items.json")

        if content_type == "item":
            def _balance_check(content: Any, _bv: Any = bv, _seed: Any = seed_items) -> list:
                items = content if isinstance(content, list) else [content]
                results = []
                for item in items:
                    d = item.model_dump(mode="json") if hasattr(item, "model_dump") else item
                    results.append(_bv.check_stat_range(d, _seed))
                return results
            validator_fns.append(_balance_check)

        regenerator = ContentRegenerator(
            generator, validator_fns, max_attempts=max_attempts,
        )

        # Extract generation params from existing data
        data = cv.data or {}
        gen_kwargs: dict[str, Any] = {}
        if content_type == "item":
            gen_kwargs = {
                "type": data.get("type", "weapon"),
                "rarity": data.get("rarity", "rare"),
                "count": 1,
            }

        regen_result = regenerator.run(**gen_kwargs)

        # Save as new version
        new_data = regen_result.content
        if hasattr(new_data, "model_dump"):
            new_data = new_data.model_dump(mode="json")
        elif isinstance(new_data, list) and new_data:
            new_data = new_data[0].model_dump(mode="json") if hasattr(new_data[0], "model_dump") else new_data[0]

        repo.create_version(
            content_type=content_type,
            content_id=cv.content_id,
            data=new_data,
            validation_result={"regeneration": regen_result.to_dict()},
        )
        session.commit()


@router.post("/{version_id}/regenerate")
def regenerate_content(
    version_id: str,
    body: RegenerateRequest,
    background_tasks: BackgroundTasks,
    repo: Annotated[ContentRepository, Depends(_get_repo)],
) -> dict[str, str]:
    """Trigger regeneration of a content version with validation feedback loop."""
    from src.config import get_settings

    cv = repo.get_by_id(version_id)
    if cv is None:
        raise HTTPException(status_code=404, detail="Content version not found")

    background_tasks.add_task(
        _regenerate_background,
        version_id,
        body.max_attempts,
        get_settings().database_url,
    )

    return {"status": "regenerating", "version_id": version_id}
