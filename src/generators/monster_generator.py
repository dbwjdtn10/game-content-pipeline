"""Generator for game monsters and balance suggestions."""

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

class MonsterStats(BaseModel):
    hp: int = Field(ge=1, description="Hit points")
    atk: int = Field(ge=0, description="Attack power")
    def_: int = Field(ge=0, alias="def", description="Defense")
    speed: int = Field(ge=0, description="Speed stat")

    model_config = {"populate_by_name": True}


class MonsterSkill(BaseModel):
    name: str = Field(description="Skill name")
    type: Literal["active", "passive", "buff", "debuff"]
    damage_multiplier: float = Field(ge=0, description="Damage multiplier relative to base ATK")
    cooldown_seconds: float = Field(ge=0, description="Cooldown in seconds")
    description: str = Field(description="Skill effect description")


class DropItem(BaseModel):
    item_id: str = Field(description="Reference to item ID")
    item_name: str = Field(description="Item name for readability")
    drop_rate: float = Field(ge=0.0001, le=1.0, description="Drop probability")


class GeneratedMonster(BaseModel):
    name: str = Field(max_length=50, description="Monster name")
    type: Literal["normal", "elite", "boss"]
    level: int = Field(ge=1, le=99)
    region: str = Field(min_length=1, description="Region where the monster appears")
    stats: MonsterStats
    skills: list[MonsterSkill] = Field(min_length=1)
    drop_items: list[DropItem] = Field(default_factory=list)
    respawn_time_seconds: int = Field(ge=0)
    description: str = Field(max_length=500, description="Monster description")


class BalanceSuggestion(BaseModel):
    monster_name: str
    field: str
    current_value: Any
    suggested_value: Any
    reason: str


# ------------------------------------------------------------------
# Generator
# ------------------------------------------------------------------

class MonsterGenerator(BaseGenerator):
    """Generate monsters and provide balance suggestions via Gemini."""

    SEED_FILE = "monsters.json"

    def generate(
        self,
        *,
        region: str = "",
        count: int = 3,
        level_range: tuple[int, int] = (1, 99),
        difficulty: Literal["normal", "elite", "boss"] = "normal",
        _feedback: str = "",
    ) -> list[GeneratedMonster]:
        """Generate *count* monsters matching the given parameters."""
        self.log.info(
            "monster_generate_start",
            region=region,
            count=count,
            level_range=level_range,
            difficulty=difficulty,
            has_feedback=bool(_feedback),
        )
        prompt = self._build_prompt(
            region=region,
            count=count,
            level_range=level_range,
            difficulty=difficulty,
        )
        prompt = self._append_feedback(prompt, _feedback)
        raw = self._call_llm(prompt, response_schema=list[GeneratedMonster])
        monsters = self._parse_response(raw)
        self.log.info("monster_generate_done", generated=len(monsters))
        return monsters

    def balance(
        self,
        source_file: str,
        *,
        target_level: int = 10,
        difficulty: Literal["normal", "elite", "boss"] = "normal",
    ) -> list[BalanceSuggestion]:
        """Analyze a monster data file and return balance suggestions."""
        self.log.info(
            "monster_balance_start",
            source_file=source_file,
            target_level=target_level,
            difficulty=difficulty,
        )
        from pathlib import Path

        source = Path(source_file)
        if not source.exists():
            raise FileNotFoundError(f"Source file not found: {source}")

        monsters_data = json.loads(source.read_text(encoding="utf-8"))
        if isinstance(monsters_data, dict):
            monsters_data = [monsters_data]

        seed_monsters = self.load_seed(self.SEED_FILE)

        prompt = (
            "You are a game balance designer.\n\n"
            "Here are the monsters to review:\n"
            f"{self._to_json_block(monsters_data)}\n\n"
            "Here are reference monsters from the existing database:\n"
            f"{self._to_json_block(seed_monsters[:10])}\n\n"
            f"Target level: {target_level}\n"
            f"Difficulty tier: {difficulty}\n\n"
            "For each monster, analyze whether its stats, skills, and drop rates "
            "are balanced for the target level and difficulty tier. Return a JSON "
            "array of balance suggestions. Each suggestion should have: "
            "monster_name, field, current_value, suggested_value, reason.\n"
            "If a monster is well-balanced, still include an entry with "
            'field="overall" and reason explaining why it is balanced.\n'
        )

        raw = self._call_llm(prompt, response_schema=list[BalanceSuggestion])
        data = json.loads(raw)
        if isinstance(data, dict):
            data = [data]
        suggestions = [BalanceSuggestion.model_validate(s) for s in data]
        self.log.info("monster_balance_done", suggestions=len(suggestions))
        return suggestions

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _build_prompt(self, **kwargs: Any) -> str:
        region = kwargs.get("region", "")
        count = kwargs["count"]
        level_range: tuple[int, int] = kwargs["level_range"]
        difficulty = kwargs["difficulty"]

        seed_monsters = self.load_seed(self.SEED_FILE)
        filtered = self._filter_by_level_range(seed_monsters, level_range, level_key="level")
        examples_block = ""
        if filtered:
            examples_block = (
                "Existing monsters in this level range for reference:\n"
                f"{self._to_json_block(filtered[:5])}\n"
            )

        world_setting = self.load_world_setting()
        world_block = ""
        if world_setting:
            world_block = (
                "World setting and tone reference:\n"
                f"---\n{world_setting}\n---\n"
            )

        template = self.load_prompt_template("monster_system")
        if template:
            return template.format(
                region=region,
                count=count,
                level_range_low=level_range[0],
                level_range_high=level_range[1],
                difficulty=difficulty,
                world_block=world_block,
                examples_block=examples_block,
            )

        region_line = f"- Region: {region}\n" if region else ""

        return (
            "You are a game content designer for a fantasy RPG.\n\n"
            f"{world_block}"
            f"{examples_block}"
            f"Generate exactly {count} monsters with the following constraints:\n"
            f"- Difficulty type: {difficulty}\n"
            f"- Level between {level_range[0]} and {level_range[1]}\n"
            f"{region_line}"
            "Each monster must have: name, type (normal/elite/boss), level, region, "
            "stats (hp, atk, def, speed), skills (at least 1), drop_items, "
            "respawn_time_seconds, description.\n"
            "Return a JSON array.\n"
        )

    def _parse_response(self, raw: str) -> list[GeneratedMonster]:
        data = json.loads(raw)
        if isinstance(data, dict):
            data = [data]
        return [GeneratedMonster.model_validate(m) for m in data]
