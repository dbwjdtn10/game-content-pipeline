"""Shared validation result model."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ValidationResult(BaseModel):
    """Result of a single validation check."""

    passed: bool
    check_name: str
    severity: Literal["info", "warning", "error"]
    message: str
    details: dict | None = None
