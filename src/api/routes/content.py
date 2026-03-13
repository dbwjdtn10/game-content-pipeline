"""Content management API routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.api.main import get_db
from src.api.schemas import ContentListOut, ContentVersionOut, ReviewRequest
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
