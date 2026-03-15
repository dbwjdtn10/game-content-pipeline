"""Tests for the self-improving content regeneration loop (src/pipeline/regenerator.py).

Covers the feedback formatting, regeneration loop behaviour with mocked
generators and validators, and edge cases (immediate success, exhausted attempts).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.validators.models import ValidationResult


# =========================================================================
# 1. Feedback formatting
# =========================================================================

class TestFeedbackFormatting:
    """Verify that validation failures are correctly formatted into feedback."""

    def test_format_no_failures(self) -> None:
        from src.pipeline.regenerator import _format_feedback

        results = [
            ValidationResult(
                passed=True,
                check_name="stat_range",
                severity="info",
                message="All good.",
            )
        ]
        assert _format_feedback(results) == ""

    def test_format_single_failure(self) -> None:
        from src.pipeline.regenerator import _format_feedback

        results = [
            ValidationResult(
                passed=False,
                check_name="stat_range",
                severity="warning",
                message="ATK is too high.",
                details={"stat": "atk", "value": 999},
            )
        ]
        feedback = _format_feedback(results)
        assert "stat_range" in feedback
        assert "ATK is too high" in feedback
        assert "MUST be fixed" in feedback

    def test_format_multiple_failures(self) -> None:
        from src.pipeline.regenerator import _format_feedback

        results = [
            ValidationResult(
                passed=False,
                check_name="stat_range",
                severity="warning",
                message="ATK out of range.",
            ),
            ValidationResult(
                passed=True,
                check_name="schema",
                severity="info",
                message="Schema OK.",
            ),
            ValidationResult(
                passed=False,
                check_name="duplicate",
                severity="error",
                message="Duplicate name found.",
            ),
        ]
        feedback = _format_feedback(results)
        assert "1." in feedback
        assert "2." in feedback
        assert "stat_range" in feedback
        assert "duplicate" in feedback
        # The passing check should not be listed
        assert "schema" not in feedback or "Schema OK" not in feedback

    def test_format_truncates_long_details(self) -> None:
        from src.pipeline.regenerator import _format_feedback

        results = [
            ValidationResult(
                passed=False,
                check_name="big_check",
                severity="error",
                message="Something wrong.",
                details={"data": "x" * 1000},
            )
        ]
        feedback = _format_feedback(results)
        assert "..." in feedback


# =========================================================================
# 2. Regeneration loop
# =========================================================================

class TestContentRegenerator:
    """Test the regeneration loop with mocked generators and validators."""

    def _make_regenerator(
        self,
        generator: Any,
        validators: list[Any],
        max_attempts: int = 3,
    ) -> Any:
        from src.pipeline.regenerator import ContentRegenerator

        return ContentRegenerator(
            generator=generator,
            validators=validators,
            max_attempts=max_attempts,
        )

    def test_immediate_success(self) -> None:
        """If validation passes on first try, return immediately."""
        mock_gen = MagicMock()
        mock_gen.generate.return_value = [{"name": "Sword", "stats": {"atk": 10}}]

        passing_validator = lambda content: ValidationResult(
            passed=True,
            check_name="test_check",
            severity="info",
            message="OK",
        )

        regen = self._make_regenerator(mock_gen, [passing_validator])
        result = regen.run()

        assert result.succeeded is True
        assert result.attempts == 1
        assert len(result.validation_history) == 1
        mock_gen.generate.assert_called_once()

    def test_succeeds_on_second_attempt(self) -> None:
        """If first attempt fails but second passes, return after 2 attempts."""
        mock_gen = MagicMock()
        mock_gen.generate.side_effect = [
            [{"name": "BadSword"}],
            [{"name": "GoodSword"}],
        ]

        call_count = 0

        def validator(content: Any) -> ValidationResult:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return ValidationResult(
                    passed=False,
                    check_name="test_check",
                    severity="warning",
                    message="Bad!",
                )
            return ValidationResult(
                passed=True,
                check_name="test_check",
                severity="info",
                message="OK",
            )

        regen = self._make_regenerator(mock_gen, [validator])
        result = regen.run()

        assert result.succeeded is True
        assert result.attempts == 2
        assert len(result.validation_history) == 2
        # Second call should include feedback
        second_call_kwargs = mock_gen.generate.call_args_list[1][1]
        assert "_feedback" in second_call_kwargs
        assert second_call_kwargs["_feedback"] != ""

    def test_exhausted_attempts(self) -> None:
        """If all attempts fail, return with succeeded=False."""
        mock_gen = MagicMock()
        mock_gen.generate.return_value = [{"name": "AlwaysBad"}]

        failing_validator = lambda content: ValidationResult(
            passed=False,
            check_name="test_check",
            severity="error",
            message="Always fails.",
        )

        regen = self._make_regenerator(
            mock_gen, [failing_validator], max_attempts=2,
        )
        result = regen.run()

        assert result.succeeded is False
        assert result.attempts == 2
        assert len(result.validation_history) == 2
        assert mock_gen.generate.call_count == 2

    def test_multiple_validators(self) -> None:
        """All validators must pass for regeneration to succeed."""
        mock_gen = MagicMock()
        mock_gen.generate.return_value = [{"name": "TestItem"}]

        v1 = lambda c: ValidationResult(
            passed=True, check_name="v1", severity="info", message="OK",
        )
        v2 = lambda c: ValidationResult(
            passed=False, check_name="v2", severity="error", message="Fail",
        )

        regen = self._make_regenerator(mock_gen, [v1, v2], max_attempts=1)
        result = regen.run()

        assert result.succeeded is False

    def test_validator_returns_list(self) -> None:
        """Validators can return a list of ValidationResult."""
        mock_gen = MagicMock()
        mock_gen.generate.return_value = [{"name": "Item"}]

        def multi_validator(content: Any) -> list[ValidationResult]:
            return [
                ValidationResult(passed=True, check_name="a", severity="info", message="OK"),
                ValidationResult(passed=True, check_name="b", severity="info", message="OK"),
            ]

        regen = self._make_regenerator(mock_gen, [multi_validator])
        result = regen.run()

        assert result.succeeded is True
        assert len(result.validation_history[0]) == 2

    def test_generate_kwargs_forwarded(self) -> None:
        """Extra kwargs are forwarded to the generator."""
        mock_gen = MagicMock()
        mock_gen.generate.return_value = [{"name": "Item"}]

        v = lambda c: ValidationResult(
            passed=True, check_name="ok", severity="info", message="OK",
        )

        regen = self._make_regenerator(mock_gen, [v])
        result = regen.run(type="weapon", rarity="epic", count=5)

        call_kwargs = mock_gen.generate.call_args[1]
        assert call_kwargs["type"] == "weapon"
        assert call_kwargs["rarity"] == "epic"
        assert call_kwargs["count"] == 5

    def test_to_dict(self) -> None:
        """RegenerationResult.to_dict() produces correct format."""
        from src.pipeline.regenerator import RegenerationResult

        result = RegenerationResult(
            content=[{"name": "Item"}],
            attempts=2,
            succeeded=True,
            validation_history=[[{"check_name": "test", "passed": True}]],
        )
        d = result.to_dict()
        assert d["attempts"] == 2
        assert d["succeeded"] is True
        assert len(d["validation_history"]) == 1
