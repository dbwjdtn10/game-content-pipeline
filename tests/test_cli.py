"""Tests for the CLI interface (src/cli/).

Uses typer.testing.CliRunner to invoke commands without spawning a subprocess.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

try:
    from typer.testing import CliRunner
except ImportError:
    pytest.skip("typer not installed", allow_module_level=True)

from src.cli.main import app

runner = CliRunner()


# =========================================================================
# Helper: mock GeneratedItem-like objects
# =========================================================================

def _make_mock_items(count: int = 3) -> list[MagicMock]:
    """Create mock GeneratedItem Pydantic model instances."""
    items = []
    for i in range(count):
        m = MagicMock()
        m.model_dump.return_value = {
            "name": f"테스트 검 {i}",
            "description": "테스트 아이템 설명",
            "rarity": "epic",
            "type": "weapon",
            "level_requirement": 50 + i,
            "stats": {"atk": 300 + i * 10, "def": 20, "hp": 100, "mp": 0},
            "special_effect": None,
            "lore": "테스트 로어",
            "obtained_from": "테스트 던전",
        }
        items.append(m)
    return items


def _make_mock_monsters(count: int = 3) -> list[MagicMock]:
    items = []
    for i in range(count):
        m = MagicMock()
        m.model_dump.return_value = {
            "name": f"테스트 몬스터 {i}",
            "type": "normal",
            "level": 50 + i,
            "region": "화산 지대",
            "stats": {"hp": 1000, "atk": 200, "def": 100, "speed": 50},
            "skills": [],
            "drop_items": [],
            "respawn_time_seconds": 60,
            "description": "테스트",
        }
        items.append(m)
    return items


# =========================================================================
# 1. --help tests for all commands
# =========================================================================

class TestCLIHelp:
    """Verify that --help works for every command group."""

    def test_root_help(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0

    def test_item_help(self) -> None:
        result = runner.invoke(app, ["item", "--help"])
        assert result.exit_code == 0

    def test_item_generate_help(self) -> None:
        result = runner.invoke(app, ["item", "generate", "--help"])
        assert result.exit_code == 0

    def test_monster_help(self) -> None:
        result = runner.invoke(app, ["monster", "--help"])
        assert result.exit_code == 0

    def test_validate_help(self) -> None:
        result = runner.invoke(app, ["validate", "--help"])
        assert result.exit_code == 0

    def test_export_help(self) -> None:
        result = runner.invoke(app, ["export", "--help"])
        assert result.exit_code == 0

    def test_pipeline_help(self) -> None:
        result = runner.invoke(app, ["pipeline", "--help"])
        assert result.exit_code == 0


# =========================================================================
# 2. item generate with mocked generator
# =========================================================================

class TestItemGenerate:
    """Test the 'item generate' CLI command with mocked generator."""

    @patch("src.generators.ItemGenerator")
    def test_item_generate_basic(self, mock_gen_cls: MagicMock) -> None:
        mock_gen = mock_gen_cls.return_value
        mock_gen.generate.return_value = _make_mock_items(3)
        mock_gen.load_seed.return_value = []
        mock_gen.SEED_FILE = "items.json"

        result = runner.invoke(app, [
            "item", "generate",
            "--type", "weapon",
            "--rarity", "epic",
            "--count", "3",
        ])
        assert result.exit_code == 0
        mock_gen.generate.assert_called_once()

    @patch("src.generators.ItemGenerator")
    def test_item_generate_with_theme(self, mock_gen_cls: MagicMock) -> None:
        mock_gen = mock_gen_cls.return_value
        mock_gen.generate.return_value = _make_mock_items(1)
        mock_gen.load_seed.return_value = []
        mock_gen.SEED_FILE = "items.json"

        result = runner.invoke(app, [
            "item", "generate",
            "--type", "armor",
            "--rarity", "rare",
            "--count", "1",
            "--theme", "얼음",
        ])
        assert result.exit_code == 0

    @patch("src.generators.ItemGenerator")
    def test_item_generate_output_file(self, mock_gen_cls: MagicMock, tmp_path: Path) -> None:
        mock_gen = mock_gen_cls.return_value
        mock_gen.generate.return_value = _make_mock_items(2)
        mock_gen.load_seed.return_value = []
        mock_gen.SEED_FILE = "items.json"

        out = tmp_path / "items.json"
        result = runner.invoke(app, [
            "item", "generate",
            "--count", "2",
            "--output", str(out),
        ])
        assert result.exit_code == 0
        assert out.exists()
        data = json.loads(out.read_text(encoding="utf-8"))
        assert len(data) == 2


# =========================================================================
# 3. validate command
# =========================================================================

class TestValidateCommand:
    """Test the 'validate' CLI command."""

    def test_validate_nonexistent_file(self) -> None:
        """Validate on a non-existent file should fail gracefully."""
        result = runner.invoke(app, [
            "validate",
            "--target", "nonexistent_file_xyz.json",
        ])
        # Should exit with error (file not found)
        assert result.exit_code == 1


# =========================================================================
# 4. export command
# =========================================================================

class TestExportCommand:
    """Test the 'export' CLI command."""

    def test_export_nonexistent_source(self) -> None:
        """Export from non-existent source should fail gracefully."""
        result = runner.invoke(app, [
            "export",
            "--source", "nonexistent.json",
            "--format", "json",
        ])
        assert result.exit_code == 1

    def test_export_json(self, tmp_path: Path) -> None:
        """Export valid JSON data."""
        src = tmp_path / "items.json"
        src.write_text(json.dumps([{"name": "test"}], ensure_ascii=False), encoding="utf-8")
        out = tmp_path / "output.json"

        result = runner.invoke(app, [
            "export",
            "--source", str(src),
            "--format", "json",
            "--output", str(out),
        ])
        assert result.exit_code == 0
        assert out.exists()


# =========================================================================
# 5. pipeline
# =========================================================================

class TestPipelineCommand:
    """Test the 'pipeline' CLI command."""

    def test_pipeline_run_help(self) -> None:
        """Pipeline run help should show config option."""
        result = runner.invoke(app, ["pipeline", "run", "--help"])
        assert result.exit_code == 0
        assert "config" in result.output.lower()
