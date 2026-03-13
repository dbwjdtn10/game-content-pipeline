"""Generator for game quests."""

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

class QuestStep(BaseModel):
    step_number: int = Field(ge=1, description="Order of this step")
    description: str = Field(description="What the player must do")
    objective_type: Literal["kill", "collect", "talk", "explore", "escort", "craft"]
    target: str = Field(description="Target entity or item name")
    target_count: int = Field(ge=1, default=1, description="How many needed")


class QuestReward(BaseModel):
    type: Literal["exp", "gold", "item"]
    amount: int | None = Field(default=None, description="Amount for exp/gold")
    item_name: str | None = Field(default=None, description="Item name if type=item")
    item_id: str | None = Field(default=None, description="Item id if type=item")


class GeneratedQuest(BaseModel):
    name: str = Field(max_length=80, description="Quest title")
    description: str = Field(max_length=500, description="Quest description")
    type: Literal["main", "side", "daily", "event"]
    region: str = Field(description="Region where quest takes place")
    npc: str = Field(description="Quest-giving NPC name")
    level_requirement: int = Field(ge=1, le=99)
    steps: list[QuestStep] = Field(min_length=1)
    rewards: list[QuestReward] = Field(min_length=1)
    prerequisite_quest: str | None = Field(
        default=None, description="Name of prerequisite quest, if any"
    )


# ------------------------------------------------------------------
# Generator
# ------------------------------------------------------------------

class QuestGenerator(BaseGenerator):
    """Generate quests via Gemini."""

    SEED_FILE = "quests.json"

    def generate(
        self,
        *,
        type: str = "side",
        region: str = "",
        npc: str = "",
        count: int = 1,
        min_steps: int = 2,
        max_steps: int = 5,
    ) -> list[GeneratedQuest]:
        """Generate *count* quests matching the given parameters."""
        self.log.info(
            "quest_generate_start",
            type=type,
            region=region,
            npc=npc,
            count=count,
            min_steps=min_steps,
            max_steps=max_steps,
        )
        prompt = self._build_prompt(
            type=type,
            region=region,
            npc=npc,
            count=count,
            min_steps=min_steps,
            max_steps=max_steps,
        )
        raw = self._call_llm(prompt, response_schema=list[GeneratedQuest])
        quests = self._parse_response(raw)
        self.log.info("quest_generate_done", generated=len(quests))
        return quests

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _build_prompt(self, **kwargs: Any) -> str:
        type_ = kwargs["type"]
        region = kwargs.get("region", "")
        npc = kwargs.get("npc", "")
        count = kwargs["count"]
        min_steps = kwargs["min_steps"]
        max_steps = kwargs["max_steps"]

        # Load seed quests and reference data
        seed_quests = self.load_seed(self.SEED_FILE)
        examples_block = ""
        if seed_quests:
            examples_block = (
                "Existing quests for reference style:\n"
                f"{self._to_json_block(seed_quests[:3])}\n"
            )

        # Load items and monsters for cross-referencing rewards/objectives
        seed_items = self.load_seed("items.json")
        seed_monsters = self.load_seed("monsters.json")

        reference_block = ""
        if seed_items or seed_monsters:
            ref_parts: list[str] = []
            if seed_items:
                item_names = [i.get("name", "") for i in seed_items[:15]]
                ref_parts.append(f"Available items (for rewards): {item_names}")
            if seed_monsters:
                monster_names = [m.get("name", "") for m in seed_monsters[:15]]
                ref_parts.append(f"Available monsters (for kill objectives): {monster_names}")
            reference_block = "\n".join(ref_parts) + "\n"

        world_setting = self.load_world_setting()
        world_block = ""
        if world_setting:
            world_block = (
                "World setting and tone reference:\n"
                f"---\n{world_setting}\n---\n"
            )

        template = self.load_prompt_template("quest_system")
        if template:
            return template.format(
                type=type_,
                region=region,
                npc=npc,
                count=count,
                min_steps=min_steps,
                max_steps=max_steps,
                world_block=world_block,
                examples_block=examples_block,
                reference_block=reference_block,
            )

        region_line = f"- Region: {region}\n" if region else ""
        npc_line = f"- Quest-giving NPC: {npc}\n" if npc else ""

        return (
            "You are a game quest designer for a fantasy RPG.\n\n"
            f"{world_block}"
            f"{examples_block}"
            f"{reference_block}"
            f"Generate exactly {count} quests with the following constraints:\n"
            f"- Quest type: {type_}\n"
            f"{region_line}"
            f"{npc_line}"
            f"- Each quest should have between {min_steps} and {max_steps} steps.\n"
            "- Steps must have: step_number, description, objective_type "
            "(kill/collect/talk/explore/escort/craft), target, target_count.\n"
            "- Rewards must have: type (exp/gold/item), amount (for exp/gold), "
            "item_name and item_id (for item rewards).\n"
            "- Each quest needs: name, description, type, region, npc, "
            "level_requirement, steps, rewards, prerequisite_quest (null if none).\n"
            "Return a JSON array.\n"
        )

    def _parse_response(self, raw: str) -> list[GeneratedQuest]:
        data = json.loads(raw)
        if isinstance(data, dict):
            data = [data]
        return [GeneratedQuest.model_validate(q) for q in data]
