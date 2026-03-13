"""Generator for patch notes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

import structlog
from pydantic import BaseModel, Field

from src.generators.base import BaseGenerator

logger = structlog.get_logger(__name__)


# ------------------------------------------------------------------
# Pydantic models
# ------------------------------------------------------------------

class PatchSection(BaseModel):
    title: str = Field(description="Section title (e.g., 'New Content', 'Bug Fixes')")
    items: list[str] = Field(min_length=1, description="List of patch note entries")


class PatchNote(BaseModel):
    version: str = Field(description="Version string, e.g. '1.2.0'")
    date: str = Field(description="Release date, e.g. '2025-01-15'")
    title: str = Field(description="Patch title headline")
    summary: str = Field(description="Brief overall summary")
    sections: list[PatchSection] = Field(min_length=1)


# ------------------------------------------------------------------
# Generator
# ------------------------------------------------------------------

class PatchGenerator(BaseGenerator):
    """Generate patch notes from a changes manifest via Gemini."""

    def generate(
        self,
        *,
        changes_file: str,
        tone: Literal["formal", "casual", "hype"] = "casual",
    ) -> PatchNote:
        """Generate a patch note from a JSON changes file.

        The *changes_file* should be a path to a JSON document listing
        the raw changes (added items, balance tweaks, bug fixes, etc.).
        """
        self.log.info(
            "patch_generate_start",
            changes_file=changes_file,
            tone=tone,
        )
        prompt = self._build_prompt(changes_file=changes_file, tone=tone)
        raw = self._call_llm(prompt, response_schema=PatchNote)
        patch = self._parse_response(raw)
        self.log.info("patch_generate_done", version=patch.version)
        return patch

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _build_prompt(self, **kwargs: Any) -> str:
        changes_file = kwargs["changes_file"]
        tone = kwargs["tone"]

        changes_path = Path(changes_file)
        if not changes_path.exists():
            raise FileNotFoundError(f"Changes file not found: {changes_path}")

        changes_data = json.loads(changes_path.read_text(encoding="utf-8"))

        world_setting = self.load_world_setting()
        world_block = ""
        if world_setting:
            world_block = (
                "World setting and tone reference:\n"
                f"---\n{world_setting}\n---\n"
            )

        template = self.load_prompt_template("patch_system")
        if template:
            return template.format(
                tone=tone,
                changes=self._to_json_block(changes_data),
                world_block=world_block,
            )

        tone_descriptions = {
            "formal": "Write in a professional, concise tone suitable for official announcements.",
            "casual": "Write in a friendly, approachable tone that players will enjoy reading.",
            "hype": "Write in an excited, energetic tone to build hype and excitement!",
        }

        return (
            "You are a community manager writing patch notes for a fantasy RPG.\n\n"
            f"{world_block}"
            f"Tone: {tone_descriptions.get(tone, tone_descriptions['casual'])}\n\n"
            "Here are the raw changes for this patch:\n"
            f"{self._to_json_block(changes_data)}\n\n"
            "Generate a complete patch note document. Return a JSON object with:\n"
            '- version: version string (e.g., "1.2.0")\n'
            '- date: release date string (e.g., "2025-01-15")\n'
            "- title: catchy patch title\n"
            "- summary: brief overall summary (2-3 sentences)\n"
            "- sections: array of sections, each with a title and items array.\n"
            "  Group changes logically (e.g., New Content, Balance Changes, Bug Fixes, "
            "Quality of Life).\n"
        )

    def _parse_response(self, raw: str) -> PatchNote:
        data = json.loads(raw)
        return PatchNote.model_validate(data)
