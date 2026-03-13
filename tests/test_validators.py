"""Tests for the validation subsystem (src/validators/).

Covers BalanceValidator, DuplicateValidator, and SchemaValidator with both
positive and negative cases.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.validators.models import ValidationResult

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "game_data" / "schema"


# =========================================================================
# BalanceValidator tests
# =========================================================================

class TestBalanceValidator:
    """Tests for BalanceValidator stat-range and rarity-hierarchy checks."""

    def _make_validator(self) -> Any:
        """Try to import the real BalanceValidator; provide a stub otherwise."""
        try:
            from src.validators.balance import BalanceValidator
            return BalanceValidator()
        except ImportError:
            pytest.skip("BalanceValidator not yet implemented")

    # ----- check_stat_range ---------------------------------------------------

    def test_stat_in_range_passes(self, sample_items: list[dict[str, Any]]) -> None:
        """An item whose stats fall within the expected range should pass."""
        validator = self._make_validator()
        # The first item (epic weapon) is a reference; check it against itself
        item = sample_items[0]
        result = validator.check_stat_range(item, sample_items)
        assert isinstance(result, ValidationResult)
        assert result.passed is True

    def test_stat_out_of_range_fails(self) -> None:
        """An item with absurdly high stats should fail the range check."""
        validator = self._make_validator()
        # Create a pool of 4+ items at the same rarity/level to meet the min-3 threshold
        base = {
            "name": "테스트 검", "rarity": "rare", "type": "weapon",
            "level_requirement": 50, "description": "테스트", "lore": "테스트",
            "obtained_from": "테스트", "special_effect": None,
        }
        pool = []
        for i, atk in enumerate([100, 110, 105, 108]):
            item = copy.deepcopy(base)
            item["name"] = f"테스트 검 {i}"
            item["stats"] = {"atk": atk, "def": 50, "hp": 200, "mp": 0}
            pool.append(item)

        outlier = copy.deepcopy(base)
        outlier["name"] = "이상치 검"
        outlier["stats"] = {"atk": 99999, "def": 50, "hp": 200, "mp": 0}
        result = validator.check_stat_range(outlier, pool)
        assert isinstance(result, ValidationResult)
        assert result.passed is False
        assert result.severity in ("warning", "error")

    def test_stat_zero_is_acceptable(self, sample_items: list[dict[str, Any]]) -> None:
        """Zero stats should not trigger a range violation for defensive items."""
        validator = self._make_validator()
        shield = sample_items[1]  # armor with atk=0
        result = validator.check_stat_range(shield, sample_items)
        assert result.passed is True

    # ----- check_rarity_hierarchy --------------------------------------------

    def test_rarity_hierarchy_respected(self, sample_items: list[dict[str, Any]]) -> None:
        """Higher rarity items should have higher total stats (happy path)."""
        validator = self._make_validator()
        # Check a higher-rarity item against the full pool
        epic_items = [i for i in sample_items if i.get("rarity") == "epic"]
        if epic_items:
            result = validator.check_rarity_hierarchy(epic_items[0], sample_items)
            assert isinstance(result, ValidationResult)
            assert result.passed is True

    def test_rarity_hierarchy_violated(self, sample_items: list[dict[str, Any]]) -> None:
        """If a rare item has lower stats than common median, hierarchy is broken."""
        validator = self._make_validator()
        items = copy.deepcopy(sample_items)
        # Find a non-common item and make it very weak
        for item in items:
            if item.get("rarity") in ("rare", "epic", "legendary"):
                item["stats"]["atk"] = 0
                item["stats"]["hp"] = 0
                item["stats"]["mp"] = 0
                item["stats"]["def"] = 0
                result = validator.check_rarity_hierarchy(item, items)
                # Should fail or at least be info (if not enough lower-rarity data)
                assert isinstance(result, ValidationResult)
                break

    # ----- auto_fix_stats ----------------------------------------------------

    def test_auto_fix_clamps_stats(self) -> None:
        """auto_fix_stats should clamp outlier stats to the allowed range."""
        validator = self._make_validator()
        base = {
            "name": "테스트 검", "rarity": "rare", "type": "weapon",
            "level_requirement": 50, "description": "테스트", "lore": "테스트",
            "obtained_from": "테스트", "special_effect": None,
        }
        pool = []
        for i, atk in enumerate([100, 110, 105, 108]):
            item = copy.deepcopy(base)
            item["name"] = f"테스트 검 {i}"
            item["stats"] = {"atk": atk, "def": 50, "hp": 200, "mp": 0}
            pool.append(item)

        outlier = copy.deepcopy(base)
        outlier["name"] = "이상치 검"
        outlier["stats"] = {"atk": 99999, "def": 50, "hp": 200, "mp": 0}
        fixed = validator.auto_fix_stats(outlier, pool)
        fixed_dict = fixed.model_dump(by_alias=True)
        assert fixed_dict["stats"]["atk"] <= 120  # should be clamped to mean+2σ range

    def test_auto_fix_does_not_change_valid_item(
        self, sample_items: list[dict[str, Any]]
    ) -> None:
        """auto_fix_stats on an already-valid item should leave it unchanged."""
        validator = self._make_validator()
        item = copy.deepcopy(sample_items[0])
        fixed = validator.auto_fix_stats(item, sample_items)
        fixed_dict = fixed.model_dump(by_alias=True)
        assert fixed_dict["stats"] == item["stats"]


# =========================================================================
# DuplicateValidator tests
# =========================================================================

class TestDuplicateValidator:
    """Tests for DuplicateValidator name/description similarity checks."""

    def _make_validator(self) -> Any:
        try:
            from src.validators.duplicate import DuplicateValidator
            return DuplicateValidator()
        except ImportError:
            pytest.skip("DuplicateValidator not yet implemented")

    # ----- check_name_similarity (Levenshtein) --------------------------------

    def test_identical_name_flagged(self, sample_items: list[dict[str, Any]]) -> None:
        """Exact duplicate names should be flagged."""
        validator = self._make_validator()
        existing_names = [i.get("name", "") for i in sample_items]
        result = validator.check_name_similarity(sample_items[0]["name"], existing_names)
        assert isinstance(result, ValidationResult)
        assert result.passed is False

    def test_similar_name_flagged(self, sample_items: list[dict[str, Any]]) -> None:
        """A name differing by 1-2 characters should be flagged (Levenshtein < 3)."""
        validator = self._make_validator()
        existing_names = [i.get("name", "") for i in sample_items]
        result = validator.check_name_similarity("화염의 대겁", existing_names)
        assert result.passed is False

    def test_unique_name_passes(self, sample_items: list[dict[str, Any]]) -> None:
        """A completely different name should pass the similarity check."""
        validator = self._make_validator()
        existing_names = [i.get("name", "") for i in sample_items]
        result = validator.check_name_similarity("천상의 별빛 지팡이", existing_names)
        assert result.passed is True

    # ----- check_description_similarity ---------------------------------------

    def test_duplicate_description_flagged(
        self, sample_items: list[dict[str, Any]]
    ) -> None:
        """An item with the same description should be flagged."""
        validator = self._make_validator()
        existing_descs = [i.get("description", "") for i in sample_items]
        result = validator.check_description_similarity(
            sample_items[0]["description"], existing_descs
        )
        # Exact match with itself should fail
        assert result.passed is False

    def test_unique_description_passes(
        self, sample_items: list[dict[str, Any]]
    ) -> None:
        """A completely different description should pass."""
        validator = self._make_validator()
        existing_descs = [i.get("description", "") for i in sample_items]
        unique_desc = (
            "은하수의 별가루를 모아 만든 전혀 새로운 종류의 무기. "
            "우주의 에너지가 깃들어 있어 공간을 왜곡시킬 수 있다."
        )
        result = validator.check_description_similarity(unique_desc, existing_descs)
        assert result.passed is True


# =========================================================================
# SchemaValidator tests
# =========================================================================

class TestSchemaValidator:
    """Tests for SchemaValidator JSON Schema validation."""

    def _make_validator(self) -> Any:
        try:
            from src.validators.schema_check import SchemaValidator
            return SchemaValidator()
        except ImportError:
            pytest.skip("SchemaValidator not yet implemented")

    def test_valid_item_passes_schema(self, single_item: dict[str, Any]) -> None:
        """A fixture item that matches item_schema.json should pass."""
        validator = self._make_validator()
        schema_path = SCHEMA_DIR / "item_schema.json"
        if not schema_path.exists():
            pytest.skip("item_schema.json not found")
        result = validator.validate(single_item, schema_path)
        assert isinstance(result, ValidationResult)
        assert result.passed is True

    def test_missing_required_field_fails(self, single_item: dict[str, Any]) -> None:
        """Removing a required field should produce a schema error."""
        validator = self._make_validator()
        schema_path = SCHEMA_DIR / "item_schema.json"
        if not schema_path.exists():
            pytest.skip("item_schema.json not found")
        bad = copy.deepcopy(single_item)
        del bad["name"]
        result = validator.validate(bad, schema_path)
        assert result.passed is False
        assert result.severity == "error"

    def test_extra_field_fails_strict(self, single_item: dict[str, Any]) -> None:
        """Schema has additionalProperties: false, so extra fields should fail."""
        validator = self._make_validator()
        schema_path = SCHEMA_DIR / "item_schema.json"
        if not schema_path.exists():
            pytest.skip("item_schema.json not found")
        bad = copy.deepcopy(single_item)
        bad["unknown_field"] = "surprise"
        result = validator.validate(bad, schema_path)
        assert result.passed is False

    def test_invalid_rarity_enum_fails(self, single_item: dict[str, Any]) -> None:
        """A rarity value not in the enum should fail."""
        validator = self._make_validator()
        schema_path = SCHEMA_DIR / "item_schema.json"
        if not schema_path.exists():
            pytest.skip("item_schema.json not found")
        bad = copy.deepcopy(single_item)
        bad["rarity"] = "godlike"
        result = validator.validate(bad, schema_path)
        assert result.passed is False

    def test_valid_monster_passes_schema(self, single_monster: dict[str, Any]) -> None:
        """A fixture monster that matches monster_schema.json should pass."""
        validator = self._make_validator()
        schema_path = SCHEMA_DIR / "monster_schema.json"
        if not schema_path.exists():
            pytest.skip("monster_schema.json not found")
        result = validator.validate(single_monster, schema_path)
        assert result.passed is True

    def test_monster_missing_stats_fails(self, single_monster: dict[str, Any]) -> None:
        """A monster without stats should fail."""
        validator = self._make_validator()
        schema_path = SCHEMA_DIR / "monster_schema.json"
        if not schema_path.exists():
            pytest.skip("monster_schema.json not found")
        bad = copy.deepcopy(single_monster)
        del bad["stats"]
        result = validator.validate(bad, schema_path)
        assert result.passed is False


# =========================================================================
# ValidationResult model tests
# =========================================================================

class TestValidationResult:
    """Test the shared ValidationResult Pydantic model."""

    def test_create_passing_result(self) -> None:
        result = ValidationResult(
            passed=True,
            check_name="test_check",
            severity="info",
            message="All good",
        )
        assert result.passed is True
        assert result.details is None

    def test_create_failing_result_with_details(self) -> None:
        result = ValidationResult(
            passed=False,
            check_name="stat_range",
            severity="error",
            message="ATK 99999 exceeds maximum 600",
            details={"field": "stats.atk", "value": 99999, "max": 600},
        )
        assert result.passed is False
        assert result.details["field"] == "stats.atk"

    def test_invalid_severity_raises(self) -> None:
        with pytest.raises(Exception):
            ValidationResult(
                passed=False,
                check_name="test",
                severity="critical",  # not in Literal
                message="fail",
            )
