"""Generator for game items (weapons, armor, accessories, consumables)."""

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

class ItemStats(BaseModel):
    atk: int = Field(ge=0, description="Attack power bonus")
    def_: int = Field(ge=0, alias="def", description="Defense bonus")
    hp: int = Field(ge=0, description="Hit points bonus")
    mp: int = Field(ge=0, description="Mana points bonus")

    model_config = {"populate_by_name": True}


class GeneratedItem(BaseModel):
    name: str = Field(max_length=50, description="Item name")
    description: str = Field(max_length=300, description="Item description")
    rarity: Literal["common", "uncommon", "rare", "epic", "legendary"]
    type: Literal["weapon", "armor", "accessory", "consumable"]
    level_requirement: int = Field(ge=1, le=99)
    stats: ItemStats
    special_effect: str | None = Field(
        default=None, max_length=200, description="Special effect, null if none"
    )
    lore: str = Field(max_length=500, description="Lore text")
    obtained_from: str = Field(min_length=1, description="How the item is obtained")


# ------------------------------------------------------------------
# Generator
# ------------------------------------------------------------------

class ItemGenerator(BaseGenerator):
    """Generate game items via Gemini."""

    SEED_FILE = "items.json"

    def generate(
        self,
        *,
        type: str = "weapon",
        rarity: str = "rare",
        count: int = 3,
        theme: str = "",
        level_range: tuple[int, int] = (1, 99),
    ) -> list[GeneratedItem]:
        """Generate *count* items matching the given parameters."""
        self.log.info(
            "item_generate_start",
            type=type,
            rarity=rarity,
            count=count,
            theme=theme,
            level_range=level_range,
        )
        prompt = self._build_prompt(
            type=type,
            rarity=rarity,
            count=count,
            theme=theme,
            level_range=level_range,
        )
        raw = self._call_llm(prompt, response_schema=list[GeneratedItem])
        items = self._parse_response(raw)
        self.log.info("item_generate_done", generated=len(items))
        return items

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _build_prompt(self, **kwargs: Any) -> str:
        type_ = kwargs["type"]
        rarity = kwargs["rarity"]
        count = kwargs["count"]
        theme = kwargs.get("theme", "")
        level_range: tuple[int, int] = kwargs["level_range"]

        # Load seed items for few-shot examples
        seed_items = self.load_seed(self.SEED_FILE)
        filtered = self._filter_by_level_range(seed_items, level_range)
        examples_block = ""
        if filtered:
            examples_block = (
                "Here are existing items in this level range for reference "
                "(follow similar stat ranges and style):\n"
                f"{self._to_json_block(filtered[:5])}\n"
            )

        # Compute stat ranges from seed for guidance
        stat_guidance = self._compute_stat_ranges(filtered or seed_items, rarity)

        # World setting for tone
        world_setting = self.load_world_setting()
        world_block = ""
        if world_setting:
            world_block = (
                "World setting and tone reference:\n"
                f"---\n{world_setting}\n---\n"
            )

        # Try loading a prompt template
        template = self.load_prompt_template("item_system")

        if template:
            return template.format(
                type=type_,
                rarity=rarity,
                count=count,
                theme=theme,
                level_range_low=level_range[0],
                level_range_high=level_range[1],
                world_block=world_block,
                examples_block=examples_block,
                stat_guidance=stat_guidance,
            )

        # Fallback inline prompt
        theme_line = f"Theme/concept: {theme}\n" if theme else ""

        return (
            "You are a game content designer for a fantasy RPG.\n\n"
            f"{world_block}"
            f"{examples_block}"
            f"{stat_guidance}"
            f"Generate exactly {count} items with the following constraints:\n"
            f"- Type: {type_}\n"
            f"- Rarity: {rarity}\n"
            f"- Level requirement between {level_range[0]} and {level_range[1]}\n"
            f"{theme_line}"
            "Return a JSON array of objects matching the GeneratedItem schema.\n"
            "Each item must have: name, description, rarity, type, level_requirement, "
            "stats (atk, def, hp, mp), special_effect (string or null), lore, obtained_from.\n"
        )

    def _parse_response(self, raw: str) -> list[GeneratedItem]:
        data = json.loads(raw)
        if isinstance(data, dict):
            data = [data]
        return [GeneratedItem.model_validate(item) for item in data]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_stat_ranges(
        items: list[dict[str, Any]], target_rarity: str
    ) -> str:
        """Return a human-readable stat-range guidance string."""
        if not items:
            return ""

        rarity_items = [i for i in items if i.get("rarity") == target_rarity]
        pool = rarity_items if rarity_items else items

        stats_keys = ["atk", "def", "hp", "mp"]
        ranges: dict[str, tuple[int, int]] = {}
        for key in stats_keys:
            values = [
                i.get("stats", {}).get(key, 0)
                for i in pool
                if isinstance(i.get("stats"), dict)
            ]
            if values:
                ranges[key] = (min(values), max(values))

        if not ranges:
            return ""

        lines = ["Recommended stat ranges (based on existing data):"]
        for key, (lo, hi) in ranges.items():
            lines.append(f"  {key}: {lo}–{hi}")
        return "\n".join(lines) + "\n"
