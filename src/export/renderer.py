"""Jinja2 template renderer for game content exports."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

# Default template directory relative to project root
_DEFAULT_TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "game_data" / "templates"


class TemplateRenderer:
    """Loads and renders Jinja2 templates from a template directory.

    Parameters
    ----------
    template_dir:
        Path to the directory containing ``.j2`` / ``.jinja2`` templates.
        Defaults to ``game_data/templates/``.
    """

    def __init__(self, template_dir: str | Path | None = None) -> None:
        self.template_dir = Path(template_dir) if template_dir else _DEFAULT_TEMPLATE_DIR
        self.env = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            autoescape=select_autoescape(default=False),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render(self, template_name: str, data: dict[str, Any]) -> str:
        """Render a named template with the given data context.

        Parameters
        ----------
        template_name:
            File name of the template (e.g. ``item_card.md.j2``).
        data:
            Context dictionary passed to the template.

        Returns
        -------
        str
            Rendered output.
        """
        template = self.env.get_template(template_name)
        return template.render(**data)

    def list_templates(self) -> list[str]:
        """Return a list of available template names."""
        return self.env.list_templates()
