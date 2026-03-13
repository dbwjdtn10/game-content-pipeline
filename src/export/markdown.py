"""Markdown exporter using Jinja2 templates."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from src.export.renderer import TemplateRenderer

logger = structlog.get_logger(__name__)


class MarkdownExporter:
    """Renders content through a Jinja2 template and writes Markdown output."""

    def __init__(self, template_dir: str | Path | None = None) -> None:
        self.renderer = TemplateRenderer(template_dir)

    def export(
        self,
        data: dict[str, Any],
        template_name: str,
        output_path: str | Path,
    ) -> Path:
        """Render *data* with the named template and write as ``.md``.

        Parameters
        ----------
        data:
            Context dictionary passed to the template.
        template_name:
            Jinja2 template file name (e.g. ``item_card.md.j2``).
        output_path:
            Destination file path.

        Returns
        -------
        Path
            Resolved path to the written file.
        """
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        rendered = self.renderer.render(template_name, data)
        path.write_text(rendered, encoding="utf-8")

        logger.info(
            "markdown_export.complete",
            output_path=str(path),
            template=template_name,
            size=path.stat().st_size,
        )
        return path
