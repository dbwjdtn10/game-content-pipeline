"""Generator for character/monster skills."""

from __future__ import annotations

import json
from typing import Any, Literal

import structlog
from pydantic import BaseModel, Field

from src.generators.base import BaseGenerator

logger = structlog.get_logger(__name__)


# ------------------------------------------------------------------
# Pydantic models
# ------------------------------------------------------------------

class GeneratedSkill(BaseModel):
    name: str = Field(max_length=50, description="Skill name")
    description: str = Field(max_length=300, description="Skill description")
    element: Literal["fire", "ice", "lightning", "earth", "wind", "water", "dark", "light", "none"]
    type: Literal["active", "passive", "buff", "debuff"]
    level_requirement: int = Field(ge=1, le=99)
    mp_cost: int = Field(ge=0, description="Mana cost")
    cooldown_seconds: float = Field(ge=0, description="Cooldown in seconds")
    damage_multiplier: float = Field(ge=0, description="Damage multiplier relative to base ATK")
    effect: str | None = Field(default=None, description="Additional effect description")
    duration_seconds: float | None = Field(
        default=None, description="Buff/debuff duration, null for instant skills"
    )


# ------------------------------------------------------------------
# Generator
# ------------------------------------------------------------------

class SkillGenerator(BaseGenerator):
    """Generate character/monster skills via Gemini."""

    SEED_FILE = "skills.json"

    def generate(
        self,
        *,
        element: str = "fire",
        count: int = 3,
        level_range: tuple[int, int] = (1, 99),
        _feedback: str = "",
    ) -> list[GeneratedSkill]:
        """Generate *count* skills matching the given parameters."""
        self.log.info(
            "skill_generate_start",
            element=element,
            count=count,
            level_range=level_range,
            has_feedback=bool(_feedback),
        )
        prompt = self._build_prompt(
            element=element,
            count=count,
            level_range=level_range,
        )
        prompt = self._append_feedback(prompt, _feedback)
        raw = self._call_llm(prompt, response_schema=list[GeneratedSkill])
        skills = self._parse_response(raw)
        self.log.info("skill_generate_done", generated=len(skills))
        return skills

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _build_prompt(self, **kwargs: Any) -> str:
        element = kwargs["element"]
        count = kwargs["count"]
        level_range: tuple[int, int] = kwargs["level_range"]

        seed_skills = self.load_seed(self.SEED_FILE)
        filtered = self._filter_by_level_range(seed_skills, level_range, level_key="level_requirement")
        examples_block = ""
        if filtered:
            examples_block = (
                "Existing skills for reference:\n"
                f"{self._to_json_block(filtered[:5])}\n"
            )

        world_setting = self.load_world_setting()
        world_block = ""
        if world_setting:
            world_block = (
                "World setting and tone reference:\n"
                f"---\n{world_setting}\n---\n"
            )

        template = self.load_prompt_template("skill_system")
        if template:
            return template.format(
                element=element,
                count=count,
                level_range_low=level_range[0],
                level_range_high=level_range[1],
                world_block=world_block,
                examples_block=examples_block,
            )

        return (
            "You are a game skill designer for a fantasy RPG.\n\n"
            f"{world_block}"
            f"{examples_block}"
            f"Generate exactly {count} skills with the following constraints:\n"
            f"- Element: {element}\n"
            f"- Level requirement between {level_range[0]} and {level_range[1]}\n"
            "Each skill must have: name, description, element, type "
            "(active/passive/buff/debuff), level_requirement, mp_cost, "
            "cooldown_seconds, damage_multiplier, effect (string or null), "
            "duration_seconds (number or null for instant skills).\n"
            "Return a JSON array.\n"
        )

    def _parse_response(self, raw: str) -> list[GeneratedSkill]:
        data = json.loads(raw)
        if isinstance(data, dict):
            data = [data]
        return [GeneratedSkill.model_validate(s) for s in data]
