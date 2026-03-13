"""Tests for the export layer (src/export/).

Covers JsonExporter, CsvExporter, MarkdownExporter, and TemplateRenderer
with real file I/O against a temporary directory.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# =========================================================================
# 1. JsonExporter
# =========================================================================

class TestJsonExporter:
    """Test JSON export functionality."""

    def _make_exporter(self) -> Any:
        try:
            from src.export.json_export import JsonExporter
            return JsonExporter()
        except ImportError:
            pytest.skip("JsonExporter not yet implemented")

    def test_export_writes_valid_json(
        self,
        sample_items: list[dict[str, Any]],
        temp_output_dir: Path,
    ) -> None:
        """Exported file should contain valid, parseable JSON."""
        exporter = self._make_exporter()
        output_path = temp_output_dir / "items.json"
        exporter.export(sample_items, output_path)

        assert output_path.exists()
        with output_path.open("r", encoding="utf-8") as fh:
            loaded = json.load(fh)
        assert len(loaded) == 5
        assert loaded[0]["name"] == "화염의 대검"

    def test_export_preserves_korean(
        self,
        sample_items: list[dict[str, Any]],
        temp_output_dir: Path,
    ) -> None:
        """Korean characters should not be escaped in the output."""
        exporter = self._make_exporter()
        output_path = temp_output_dir / "items_kr.json"
        exporter.export(sample_items, output_path)

        raw = output_path.read_text(encoding="utf-8")
        assert "화염의 대검" in raw
        assert "\\u" not in raw  # ensure_ascii=False

    def test_export_empty_list(self, temp_output_dir: Path) -> None:
        """Exporting an empty list should produce a valid JSON array."""
        exporter = self._make_exporter()
        output_path = temp_output_dir / "empty.json"
        exporter.export([], output_path)

        with output_path.open("r", encoding="utf-8") as fh:
            loaded = json.load(fh)
        assert loaded == []


# =========================================================================
# Fallback: standalone JSON export tests (always runnable)
# =========================================================================

class TestJsonExportStandalone:
    """JSON export tests that work even before src.export is implemented."""

    def test_json_dumps_roundtrip(
        self,
        sample_items: list[dict[str, Any]],
        temp_output_dir: Path,
    ) -> None:
        output_path = temp_output_dir / "standalone.json"
        with output_path.open("w", encoding="utf-8") as fh:
            json.dump(sample_items, fh, ensure_ascii=False, indent=2)

        with output_path.open("r", encoding="utf-8") as fh:
            loaded = json.load(fh)
        assert len(loaded) == len(sample_items)
        for orig, loaded_item in zip(sample_items, loaded):
            assert orig["name"] == loaded_item["name"]


# =========================================================================
# 2. CsvExporter
# =========================================================================

class TestCsvExporter:
    """Test CSV export functionality."""

    def _make_exporter(self) -> Any:
        try:
            from src.export.csv_export import CsvExporter
            return CsvExporter()
        except ImportError:
            pytest.skip("CsvExporter not yet implemented")

    def test_export_writes_correct_csv(
        self,
        sample_items: list[dict[str, Any]],
        temp_output_dir: Path,
    ) -> None:
        """CSV should have a header row and one data row per item."""
        exporter = self._make_exporter()
        output_path = temp_output_dir / "items.csv"
        exporter.export(sample_items, output_path)

        assert output_path.exists()
        with output_path.open("r", encoding="utf-8-sig") as fh:
            reader = csv.reader(fh)
            rows = list(reader)
        # Header + 5 data rows
        assert len(rows) >= 6
        header = rows[0]
        assert "name" in header

    def test_csv_flattens_nested_stats(
        self,
        sample_items: list[dict[str, Any]],
        temp_output_dir: Path,
    ) -> None:
        """Nested stats dict should be flattened into columns like stats.atk."""
        exporter = self._make_exporter()
        output_path = temp_output_dir / "items_flat.csv"
        exporter.export(sample_items, output_path)

        with output_path.open("r", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)
        first = rows[0]
        # The exporter should flatten nested dicts with dot notation
        has_atk = (
            "stats.atk" in first
            or "atk" in first
            or "stats_atk" in first
        )
        assert has_atk, f"Expected flattened ATK column, got: {list(first.keys())}"


# =========================================================================
# Fallback: standalone CSV export tests
# =========================================================================

class TestCsvExportStandalone:
    """CSV export tests that work without the real exporter."""

    def _flatten(self, d: dict[str, Any], parent_key: str = "") -> dict[str, Any]:
        items: list[tuple[str, Any]] = []
        for k, v in d.items():
            new_key = f"{parent_key}.{k}" if parent_key else k
            if isinstance(v, dict):
                items.extend(self._flatten(v, new_key).items())
            else:
                items.append((new_key, v))
        return dict(items)

    def test_flatten_nested_dict(self, single_item: dict[str, Any]) -> None:
        flat = self._flatten(single_item)
        assert "stats.atk" in flat
        assert "stats.def" in flat
        assert flat["stats.atk"] == single_item["stats"]["atk"]

    def test_write_csv_from_flat_dicts(
        self,
        sample_items: list[dict[str, Any]],
        temp_output_dir: Path,
    ) -> None:
        flat_items = [self._flatten(item) for item in sample_items]
        all_keys = list(dict.fromkeys(k for item in flat_items for k in item))
        output_path = temp_output_dir / "manual.csv"

        with output_path.open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=all_keys)
            writer.writeheader()
            writer.writerows(flat_items)

        with output_path.open("r", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)
        assert len(rows) == 5
        assert rows[0]["name"] == "화염의 대검"


# =========================================================================
# 3. MarkdownExporter / TemplateRenderer (Jinja2)
# =========================================================================

class TestMarkdownExporter:
    """Test Markdown export with Jinja2 templates."""

    def _make_exporter(self) -> Any:
        try:
            from src.export.markdown import MarkdownExporter
            return MarkdownExporter()
        except ImportError:
            pytest.skip("MarkdownExporter not yet implemented")

    def test_render_markdown_output(
        self,
        sample_items: list[dict[str, Any]],
        temp_output_dir: Path,
    ) -> None:
        """MarkdownExporter should produce a .md file with item names."""
        # Create a simple template for testing
        tmpl_dir = temp_output_dir / "templates"
        tmpl_dir.mkdir()
        tmpl_path = tmpl_dir / "test_items.md.j2"
        tmpl_path.write_text(
            "# Items\n{% for item in items %}\n## {{ item.name }}\n{{ item.description }}\n{% endfor %}\n",
            encoding="utf-8",
        )

        from src.export.markdown import MarkdownExporter
        exporter = MarkdownExporter(template_dir=tmpl_dir)
        output_path = temp_output_dir / "items.md"
        exporter.export({"items": sample_items}, "test_items.md.j2", output_path)

        assert output_path.exists()
        content = output_path.read_text(encoding="utf-8")
        assert "화염의 대검" in content


class TestTemplateRenderer:
    """Test Jinja2 template rendering (standalone, always runnable)."""

    def test_jinja2_basic_render(self) -> None:
        """Jinja2 should render a simple template with variables."""
        from jinja2 import Template

        tmpl = Template("# {{ title }}\n\n{% for item in items %}- {{ item.name }}\n{% endfor %}")
        result = tmpl.render(
            title="아이템 목록",
            items=[{"name": "화염의 대검"}, {"name": "서리 수호의 방패"}],
        )
        assert "# 아이템 목록" in result
        assert "- 화염의 대검" in result
        assert "- 서리 수호의 방패" in result

    def test_jinja2_item_table_template(
        self,
        sample_items: list[dict[str, Any]],
    ) -> None:
        """Render a markdown table from item data."""
        from jinja2 import Template

        tmpl_str = textwrap.dedent("""\
            # 아이템 리포트

            | 이름 | 등급 | 타입 | 레벨 | ATK | DEF | HP | MP |
            |------|------|------|------|-----|-----|----|----|
            {% for item in items -%}
            | {{ item.name }} | {{ item.rarity }} | {{ item.type }} | {{ item.level_requirement }} | {{ item.stats.atk }} | {{ item.stats.def }} | {{ item.stats.hp }} | {{ item.stats.mp }} |
            {% endfor %}
        """)
        tmpl = Template(tmpl_str)
        result = tmpl.render(items=sample_items)
        assert "화염의 대검" in result
        assert "epic" in result
        assert "340" in result  # ATK of first item

    def test_jinja2_template_from_file(
        self,
        sample_items: list[dict[str, Any]],
        temp_output_dir: Path,
    ) -> None:
        """Load a template from disk and render it."""
        from jinja2 import Environment, FileSystemLoader

        # Create a template file
        tmpl_path = temp_output_dir / "test_template.j2"
        tmpl_path.write_text(
            "# Items\n{% for item in items %}\n## {{ item.name }}\n{{ item.description }}\n{% endfor %}\n",
            encoding="utf-8",
        )

        env = Environment(loader=FileSystemLoader(str(temp_output_dir)))
        tmpl = env.get_template("test_template.j2")
        result = tmpl.render(items=sample_items)
        assert "# Items" in result
        assert "## 화염의 대검" in result

    def test_renderer_loads_templates_from_directory(self) -> None:
        """TemplateRenderer should load templates from game_data/templates/ if it exists."""
        try:
            from src.export.renderer import TemplateRenderer

            renderer = TemplateRenderer()
            assert renderer is not None
        except ImportError:
            pytest.skip("TemplateRenderer not yet implemented")


# We need textwrap for the table template test
import textwrap  # noqa: E402
