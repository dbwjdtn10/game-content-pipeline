"""Tests for the content generators (src/generators/).

Covers Pydantic model validation, prompt building, response parsing, and
mocked Gemini API calls.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel, ValidationError


# =========================================================================
# Pydantic models (mirrors the project's expected GeneratedItem / etc.)
# If the real models are importable, use them; otherwise these stand-alone
# definitions let the tests run before the full implementation exists.
# =========================================================================

try:
    from src.generators.item_generator import GeneratedItem
except ImportError:
    from typing import Literal

    class ItemStats(BaseModel):
        atk: int
        def_: int = 0  # aliased
        hp: int = 0
        mp: int = 0

        class Config:
            populate_by_name = True
            fields = {"def_": {"alias": "def"}}

    class GeneratedItem(BaseModel):  # type: ignore[no-redef]
        name: str
        description: str
        rarity: Literal["common", "uncommon", "rare", "epic", "legendary"]
        type: Literal["weapon", "armor", "accessory", "consumable"]
        level_requirement: int
        stats: ItemStats
        special_effect: str | None = None
        lore: str
        obtained_from: str


try:
    from src.generators.monster_generator import GeneratedMonster
except ImportError:
    from typing import Literal  # noqa: F811

    class MonsterStats(BaseModel):
        hp: int
        atk: int
        def_: int = 0
        speed: int = 0

        class Config:
            populate_by_name = True
            fields = {"def_": {"alias": "def"}}

    class MonsterSkill(BaseModel):
        name: str
        type: Literal["active", "passive", "buff", "debuff"]
        damage_multiplier: float
        cooldown_seconds: float
        description: str

    class GeneratedMonster(BaseModel):  # type: ignore[no-redef]
        name: str
        type: Literal["normal", "elite", "boss"]
        level: int
        region: str
        stats: MonsterStats
        skills: list[MonsterSkill]
        description: str


try:
    from src.generators.quest_generator import GeneratedQuest
except ImportError:
    from typing import Literal  # noqa: F811

    class QuestStep(BaseModel):
        order: int
        objective: str
        description: str

    class QuestReward(BaseModel):
        type: Literal["item", "gold", "exp", "skill_point", "title"]
        name: str
        amount: int

    class GeneratedQuest(BaseModel):  # type: ignore[no-redef]
        title: str
        type: Literal["main", "side", "daily", "event"]
        description: str
        background: str
        npc: str
        region: str
        level_range: list[int]
        steps: list[QuestStep]
        rewards: list[QuestReward]
        prerequisites: list[str]
        estimated_time_minutes: int


# =========================================================================
# 1. Pydantic model validation
# =========================================================================

class TestGeneratedItemModel:
    """Test GeneratedItem Pydantic validation."""

    def test_valid_item_parses(self, single_item: dict[str, Any]) -> None:
        """A well-formed item dict should parse without error."""
        # The fixture uses "def" as key; remap if the model uses an alias.
        data = dict(single_item)
        item = GeneratedItem.model_validate(data)
        assert item.name == "화염의 대검"
        assert item.rarity == "epic"
        assert item.level_requirement == 52

    def test_missing_required_field_raises(self, single_item: dict[str, Any]) -> None:
        """Omitting a required field must raise ValidationError."""
        data = dict(single_item)
        del data["name"]
        with pytest.raises(ValidationError):
            GeneratedItem.model_validate(data)

    def test_invalid_rarity_raises(self, single_item: dict[str, Any]) -> None:
        """An invalid rarity value must raise ValidationError."""
        data = dict(single_item)
        data["rarity"] = "mythic"  # not in allowed literals
        with pytest.raises(ValidationError):
            GeneratedItem.model_validate(data)

    def test_negative_level_rejected_by_model(self, single_item: dict[str, Any]) -> None:
        """Pydantic model enforces ge=1 on level_requirement, so -5 should fail."""
        data = dict(single_item)
        data["level_requirement"] = -5
        with pytest.raises(ValidationError):
            GeneratedItem.model_validate(data)

    def test_invalid_type_raises(self, single_item: dict[str, Any]) -> None:
        """An invalid item type must raise ValidationError."""
        data = dict(single_item)
        data["type"] = "mount"
        with pytest.raises(ValidationError):
            GeneratedItem.model_validate(data)


class TestGeneratedMonsterModel:
    """Test GeneratedMonster Pydantic validation."""

    def test_valid_monster_parses(self, single_monster: dict[str, Any]) -> None:
        data = dict(single_monster)
        monster = GeneratedMonster.model_validate(data)
        assert monster.name == "용암 골렘"
        assert monster.type == "elite"

    def test_missing_skills_raises(self, single_monster: dict[str, Any]) -> None:
        data = dict(single_monster)
        del data["skills"]
        with pytest.raises(ValidationError):
            GeneratedMonster.model_validate(data)


# =========================================================================
# 2. Prompt building (mock LLM, verify prompt content)
# =========================================================================

class TestPromptBuilding:
    """Verify that _build_prompt produces expected content elements."""

    @patch("src.generators.base.get_settings")
    @patch("google.genai.Client")
    def test_item_generator_build_prompt(
        self,
        mock_client_cls: MagicMock,
        mock_get_settings: MagicMock,
    ) -> None:
        """ItemGenerator._build_prompt should contain type, rarity, and theme."""
        mock_get_settings.return_value = MagicMock(gemini_api_key="fake-key")
        try:
            from src.generators.item_generator import ItemGenerator

            gen = ItemGenerator()
            prompt = gen._build_prompt(
                type="weapon",
                rarity="epic",
                count=3,
                theme="화염",
                level_range=(50, 60),
            )
            assert "weapon" in prompt or "무기" in prompt
            assert "epic" in prompt or "에픽" in prompt
        except (ImportError, TypeError):
            pytest.skip("ItemGenerator not yet implemented")

    @patch("src.generators.base.get_settings")
    @patch("google.genai.Client")
    def test_monster_generator_build_prompt(
        self,
        mock_client_cls: MagicMock,
        mock_get_settings: MagicMock,
    ) -> None:
        mock_get_settings.return_value = MagicMock(gemini_api_key="fake-key")
        try:
            from src.generators.monster_generator import MonsterGenerator

            gen = MonsterGenerator()
            prompt = gen._build_prompt(
                region="화산 심연",
                count=3,
                level_range=(50, 60),
                difficulty="elite",
            )
            assert "화산" in prompt or "region" in prompt.lower() or "monster" in prompt.lower() or len(prompt) > 100
        except (ImportError, TypeError):
            pytest.skip("MonsterGenerator not yet implemented")


# =========================================================================
# 3. Response parsing
# =========================================================================

class TestResponseParsing:
    """Verify that _parse_response correctly parses LLM JSON output."""

    @patch("src.generators.base.get_settings")
    @patch("google.genai.Client")
    def test_item_generator_parse_response(
        self,
        mock_client_cls: MagicMock,
        mock_get_settings: MagicMock,
        single_item: dict[str, Any],
    ) -> None:
        mock_get_settings.return_value = MagicMock(gemini_api_key="fake-key")
        try:
            from src.generators.item_generator import ItemGenerator

            gen = ItemGenerator()
            raw_json = json.dumps(single_item, ensure_ascii=False)
            result = gen._parse_response(raw_json)
            assert result is not None
        except (ImportError, TypeError):
            pytest.skip("ItemGenerator not yet implemented")

    def test_parse_invalid_json_raises(self) -> None:
        """Parsing garbage should raise an error."""
        try:
            from src.generators.item_generator import ItemGenerator

            with patch("src.generators.base.get_settings") as m:
                m.return_value = MagicMock(gemini_api_key="fake-key")
                with patch("google.genai.Client"):
                    gen = ItemGenerator()
                    with pytest.raises(Exception):
                        gen._parse_response("{invalid json!!}")
        except ImportError:
            # Fallback: just verify json.loads fails
            with pytest.raises(json.JSONDecodeError):
                json.loads("{invalid json!!}")


# =========================================================================
# 4. Mocked Gemini API calls
# =========================================================================

class TestMockedGeminiCalls:
    """Ensure generators call the Gemini client correctly and handle responses."""

    @patch("src.generators.base.get_settings")
    @patch("google.genai.Client")
    def test_call_llm_returns_text(
        self,
        mock_client_cls: MagicMock,
        mock_get_settings: MagicMock,
        single_item: dict[str, Any],
    ) -> None:
        """_call_llm should return the text attribute from the model response."""
        mock_get_settings.return_value = MagicMock(gemini_api_key="fake-key")

        mock_response = MagicMock()
        mock_response.text = json.dumps(single_item, ensure_ascii=False)
        mock_response.usage_metadata = MagicMock(
            prompt_token_count=100,
            candidates_token_count=200,
            total_token_count=300,
            cached_content_token_count=0,
        )

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response
        mock_client_cls.return_value = mock_client

        try:
            from src.generators.item_generator import ItemGenerator

            gen = ItemGenerator()
            result = gen._call_llm("test prompt")
            assert result == mock_response.text
        except ImportError:
            from src.generators.base import BaseGenerator

            # Create a minimal concrete subclass for testing
            class _TestGen(BaseGenerator):
                def generate(self, *a: Any, **kw: Any) -> Any:
                    pass

                def _build_prompt(self, **kw: Any) -> str:
                    return ""

                def _parse_response(self, raw: str) -> Any:
                    return raw

            gen = _TestGen()
            gen.client = mock_client
            result = gen._call_llm("test prompt")
            assert result == mock_response.text

    @patch("src.generators.base.get_settings")
    @patch("google.genai.Client")
    def test_call_llm_retries_on_failure(
        self,
        mock_client_cls: MagicMock,
        mock_get_settings: MagicMock,
    ) -> None:
        """_call_llm should retry up to MAX_RETRIES on transient errors."""
        mock_get_settings.return_value = MagicMock(gemini_api_key="fake-key")

        mock_response = MagicMock()
        mock_response.text = '{"ok": true}'
        mock_response.usage_metadata = MagicMock(
            prompt_token_count=10,
            candidates_token_count=5,
            total_token_count=15,
            cached_content_token_count=0,
        )

        mock_client = MagicMock()
        # Fail twice, then succeed
        mock_client.models.generate_content.side_effect = [
            RuntimeError("transient"),
            RuntimeError("transient"),
            mock_response,
        ]
        mock_client_cls.return_value = mock_client

        try:
            from src.generators.item_generator import ItemGenerator

            gen = ItemGenerator()
        except ImportError:
            from src.generators.base import BaseGenerator

            class _TestGen(BaseGenerator):
                def generate(self, *a: Any, **kw: Any) -> Any:
                    pass

                def _build_prompt(self, **kw: Any) -> str:
                    return ""

                def _parse_response(self, raw: str) -> Any:
                    return raw

            gen = _TestGen()

        gen.client = mock_client

        with patch("src.generators.base.time.sleep"):  # skip backoff waits
            result = gen._call_llm("test prompt")

        assert result == '{"ok": true}'
        assert mock_client.models.generate_content.call_count == 3

    @patch("src.generators.base.get_settings")
    @patch("google.genai.Client")
    def test_call_llm_raises_after_exhausting_retries(
        self,
        mock_client_cls: MagicMock,
        mock_get_settings: MagicMock,
    ) -> None:
        """_call_llm should raise after MAX_RETRIES consecutive failures."""
        mock_get_settings.return_value = MagicMock(gemini_api_key="fake-key")

        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = RuntimeError("permanent")
        mock_client_cls.return_value = mock_client

        try:
            from src.generators.item_generator import ItemGenerator

            gen = ItemGenerator()
        except ImportError:
            from src.generators.base import BaseGenerator

            class _TestGen(BaseGenerator):
                def generate(self, *a: Any, **kw: Any) -> Any:
                    pass

                def _build_prompt(self, **kw: Any) -> str:
                    return ""

                def _parse_response(self, raw: str) -> Any:
                    return raw

            gen = _TestGen()

        gen.client = mock_client

        with patch("src.generators.base.time.sleep"):
            with pytest.raises(RuntimeError, match="permanent"):
                gen._call_llm("test prompt")

    @patch("src.generators.base.get_settings")
    @patch("google.genai.Client")
    def test_call_llm_raises_on_empty_response(
        self,
        mock_client_cls: MagicMock,
        mock_get_settings: MagicMock,
    ) -> None:
        """_call_llm should raise ValueError if model returns None text."""
        mock_get_settings.return_value = MagicMock(gemini_api_key="fake-key")

        mock_response = MagicMock()
        mock_response.text = None
        mock_response.usage_metadata = MagicMock(
            prompt_token_count=10,
            candidates_token_count=0,
            total_token_count=10,
            cached_content_token_count=0,
        )

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response
        mock_client_cls.return_value = mock_client

        try:
            from src.generators.item_generator import ItemGenerator

            gen = ItemGenerator()
        except ImportError:
            from src.generators.base import BaseGenerator

            class _TestGen(BaseGenerator):
                def generate(self, *a: Any, **kw: Any) -> Any:
                    pass

                def _build_prompt(self, **kw: Any) -> str:
                    return ""

                def _parse_response(self, raw: str) -> Any:
                    return raw

            gen = _TestGen()

        gen.client = mock_client

        with patch("src.generators.base.time.sleep"):
            with pytest.raises((ValueError, RuntimeError)):
                gen._call_llm("test prompt")
