"""Shared pytest fixtures for the Game Content Pipeline test suite."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Sample data fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def sample_items() -> list[dict[str, Any]]:
    """Load the five sample items from the fixtures directory."""
    path = FIXTURES_DIR / "sample_items.json"
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture()
def sample_monsters() -> list[dict[str, Any]]:
    """Load the three sample monsters from the fixtures directory."""
    path = FIXTURES_DIR / "sample_monsters.json"
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Temporary output directory
# ---------------------------------------------------------------------------

@pytest.fixture()
def temp_output_dir(tmp_path: Path) -> Path:
    """Provide a temporary directory for test output files.

    The directory is automatically cleaned up by pytest after each test.
    """
    output = tmp_path / "output"
    output.mkdir()
    return output


# ---------------------------------------------------------------------------
# Single-item convenience fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def single_item(sample_items: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the first sample item (epic weapon)."""
    return sample_items[0]


@pytest.fixture()
def single_monster(sample_monsters: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the first sample monster (elite)."""
    return sample_monsters[0]


# ---------------------------------------------------------------------------
# Environment variable helpers (avoid real API keys in tests)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure tests never rely on real environment variables."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-api-key-not-real")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///test.db")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/15")
