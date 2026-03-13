"""SQLAlchemy 2.0 ORM models for content versioning and pipeline runs."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    type_annotation_map = {
        dict[str, Any]: JSONB,
    }


class ContentVersion(Base):
    """Tracks every version of generated content, with review workflow."""

    __tablename__ = "content_versions"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: uuid.uuid4().hex,
    )
    content_type: Mapped[str] = mapped_column(
        Enum("item", "monster", "quest", "skill", name="content_type_enum"),
        nullable=False,
        index=True,
    )
    content_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(
        Enum(
            "draft",
            "reviewing",
            "approved",
            "rejected",
            name="content_status_enum",
        ),
        nullable=False,
        default="draft",
        index=True,
    )
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    validation_result: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    reviewed_by: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    pipeline_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )

    def __repr__(self) -> str:
        return (
            f"<ContentVersion(id={self.id!r}, type={self.content_type!r}, "
            f"content_id={self.content_id!r}, v={self.version}, "
            f"status={self.status!r})>"
        )


class PipelineRun(Base):
    """Records a pipeline execution with its config and results."""

    __tablename__ = "pipeline_runs"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: uuid.uuid4().hex,
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(
        Enum(
            "pending",
            "running",
            "completed",
            "failed",
            name="pipeline_status_enum",
        ),
        nullable=False,
        default="pending",
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<PipelineRun(id={self.id!r}, name={self.name!r}, "
            f"status={self.status!r})>"
        )
