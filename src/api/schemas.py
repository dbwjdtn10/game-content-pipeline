"""Pydantic v2 request/response schemas for the API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# ------------------------------------------------------------------
# Content schemas
# ------------------------------------------------------------------


class ContentVersionOut(BaseModel):
    """Response schema for a content version."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    content_type: str
    content_id: str
    version: int
    status: str
    data: dict[str, Any]
    validation_result: dict[str, Any] | None = None
    created_at: datetime
    reviewed_by: str | None = None
    review_comment: str | None = None
    pipeline_id: str | None = None


class ContentListOut(BaseModel):
    """Paginated list of content versions."""

    items: list[ContentVersionOut]
    total: int


class ReviewRequest(BaseModel):
    """Request body for approve/reject actions."""

    reviewed_by: str = Field(..., min_length=1, max_length=128)
    comment: str | None = None


class RegenerateRequest(BaseModel):
    """Request body to trigger content regeneration with feedback loop."""

    max_attempts: int = Field(default=3, ge=1, le=5, description="Max regeneration attempts")


# ------------------------------------------------------------------
# Pipeline schemas
# ------------------------------------------------------------------


class PipelineRunRequest(BaseModel):
    """Request body to trigger a pipeline run."""

    yaml_config: str = Field(..., description="YAML pipeline configuration")
    retry_on_fail: int = Field(
        default=0, ge=0, le=5, description="Number of retries for failed steps"
    )


class PipelineStepOut(BaseModel):
    status: str
    result: Any = None
    error: str | None = None


class PipelineRunOut(BaseModel):
    """Response for a pipeline run."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    config: dict[str, Any] | None = None
    result: dict[str, Any] | None = None


class PipelineRunCreatedOut(BaseModel):
    pipeline_id: str
    status: str
    steps: dict[str, PipelineStepOut] = {}


# ------------------------------------------------------------------
# Stats schemas
# ------------------------------------------------------------------


class TypeStatusCount(BaseModel):
    content_type: str
    status: str
    count: int


class StatsOverviewOut(BaseModel):
    total_content: int
    counts: list[TypeStatusCount]
    pipeline_runs: int
