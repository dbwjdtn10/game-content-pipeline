"""Repository classes providing CRUD operations over SQLAlchemy models."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.storage.models import ContentVersion, PipelineRun


class ContentRepository:
    """CRUD operations for :class:`ContentVersion`."""

    def __init__(self, session: Session) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def get_by_id(self, version_id: str) -> ContentVersion | None:
        return self.session.get(ContentVersion, version_id)

    def get_latest_version(
        self, content_type: str, content_id: str
    ) -> ContentVersion | None:
        """Return the latest version of a piece of content."""
        stmt = (
            select(ContentVersion)
            .where(
                ContentVersion.content_type == content_type,
                ContentVersion.content_id == content_id,
            )
            .order_by(ContentVersion.version.desc())
            .limit(1)
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def get_by_status(
        self,
        status: str,
        content_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[ContentVersion]:
        stmt = (
            select(ContentVersion)
            .where(ContentVersion.status == status)
            .order_by(ContentVersion.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        if content_type is not None:
            stmt = stmt.where(ContentVersion.content_type == content_type)
        return self.session.execute(stmt).scalars().all()

    def get_history(
        self, content_type: str, content_id: str
    ) -> Sequence[ContentVersion]:
        """Return all versions of a content item, newest first."""
        stmt = (
            select(ContentVersion)
            .where(
                ContentVersion.content_type == content_type,
                ContentVersion.content_id == content_id,
            )
            .order_by(ContentVersion.version.desc())
        )
        return self.session.execute(stmt).scalars().all()

    def list_all(
        self,
        content_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[ContentVersion]:
        stmt = (
            select(ContentVersion)
            .order_by(ContentVersion.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        if content_type is not None:
            stmt = stmt.where(ContentVersion.content_type == content_type)
        return self.session.execute(stmt).scalars().all()

    def count_by_type_and_status(self) -> list[dict[str, Any]]:
        """Return aggregate counts grouped by content_type and status."""
        stmt = (
            select(
                ContentVersion.content_type,
                ContentVersion.status,
                func.count().label("count"),
            )
            .group_by(ContentVersion.content_type, ContentVersion.status)
        )
        rows = self.session.execute(stmt).all()
        return [
            {"content_type": r.content_type, "status": r.status, "count": r.count}
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def create_version(
        self,
        content_type: str,
        content_id: str,
        data: dict[str, Any],
        pipeline_id: str | None = None,
        validation_result: dict[str, Any] | None = None,
    ) -> ContentVersion:
        """Create a new content version, auto-incrementing the version number."""
        latest = self.get_latest_version(content_type, content_id)
        next_version = (latest.version + 1) if latest else 1

        cv = ContentVersion(
            content_type=content_type,
            content_id=content_id,
            version=next_version,
            data=data,
            pipeline_id=pipeline_id,
            validation_result=validation_result,
        )
        self.session.add(cv)
        self.session.flush()
        return cv

    def update_status(self, version_id: str, status: str) -> ContentVersion | None:
        cv = self.get_by_id(version_id)
        if cv is None:
            return None
        cv.status = status
        self.session.flush()
        return cv

    def approve(
        self,
        version_id: str,
        reviewed_by: str,
        comment: str | None = None,
    ) -> ContentVersion | None:
        cv = self.get_by_id(version_id)
        if cv is None:
            return None
        cv.status = "approved"
        cv.reviewed_by = reviewed_by
        cv.review_comment = comment
        self.session.flush()
        return cv

    def reject(
        self,
        version_id: str,
        reviewed_by: str,
        comment: str | None = None,
    ) -> ContentVersion | None:
        cv = self.get_by_id(version_id)
        if cv is None:
            return None
        cv.status = "rejected"
        cv.reviewed_by = reviewed_by
        cv.review_comment = comment
        self.session.flush()
        return cv


class PipelineRepository:
    """CRUD operations for :class:`PipelineRun`."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, run_id: str) -> PipelineRun | None:
        return self.session.get(PipelineRun, run_id)

    def create(
        self,
        name: str,
        config: dict[str, Any],
    ) -> PipelineRun:
        run = PipelineRun(
            name=name,
            config=config,
            status="pending",
            started_at=datetime.now(timezone.utc),
        )
        self.session.add(run)
        self.session.flush()
        return run

    def update_status(
        self,
        run_id: str,
        status: str,
        result: dict[str, Any] | None = None,
    ) -> PipelineRun | None:
        run = self.get_by_id(run_id)
        if run is None:
            return None
        run.status = status
        if result is not None:
            run.result = result
        if status in ("completed", "failed"):
            run.completed_at = datetime.now(timezone.utc)
        self.session.flush()
        return run

    def list_runs(
        self, limit: int = 50, offset: int = 0
    ) -> Sequence[PipelineRun]:
        stmt = (
            select(PipelineRun)
            .order_by(PipelineRun.started_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return self.session.execute(stmt).scalars().all()
