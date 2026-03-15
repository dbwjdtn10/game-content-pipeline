"""Self-improving content regeneration loop.

When validation fails, this module feeds the validation errors back into
the generator as corrective feedback, then re-validates the output.  The
loop repeats up to ``max_attempts`` times or until all checks pass.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import structlog

from src.generators.base import BaseGenerator
from src.validators.models import ValidationResult

logger = structlog.get_logger(__name__)


@dataclass
class RegenerationResult:
    """Outcome of a regeneration loop."""

    content: Any
    attempts: int
    succeeded: bool
    validation_history: list[list[dict[str, Any]]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempts": self.attempts,
            "succeeded": self.succeeded,
            "validation_history": self.validation_history,
        }


def _format_feedback(validation_results: list[ValidationResult]) -> str:
    """Convert failed validation results into a human-readable feedback block
    that can be appended to the generator prompt."""
    failures = [r for r in validation_results if not r.passed]
    if not failures:
        return ""

    lines = [
        "The previous generation had the following issues that MUST be fixed:\n"
    ]
    for i, fail in enumerate(failures, 1):
        lines.append(f"{i}. [{fail.check_name}] ({fail.severity}) {fail.message}")
        if fail.details:
            details_str = json.dumps(fail.details, ensure_ascii=False, indent=2)
            # Truncate very long details
            if len(details_str) > 500:
                details_str = details_str[:500] + "..."
            lines.append(f"   Details: {details_str}")
    lines.append(
        "\nPlease regenerate the content addressing ALL of the above issues. "
        "Ensure stats are within valid ranges, naming is consistent, and "
        "there are no duplicates."
    )
    return "\n".join(lines)


class ContentRegenerator:
    """Orchestrates the generate → validate → feedback → regenerate loop.

    Parameters
    ----------
    generator:
        The content generator instance (e.g. ItemGenerator).
    validators:
        A list of callables that accept the generated content and return
        a list of :class:`ValidationResult`.
    max_attempts:
        Maximum number of regeneration attempts (including the initial one).
    """

    def __init__(
        self,
        generator: BaseGenerator,
        validators: list[Any],
        *,
        max_attempts: int = 3,
    ) -> None:
        self.generator = generator
        self.validators = validators
        self.max_attempts = max_attempts
        self.log = logger.bind(
            regenerator=True,
            generator=generator.__class__.__name__,
        )

    def run(self, **generate_kwargs: Any) -> RegenerationResult:
        """Execute the regeneration loop.

        Parameters
        ----------
        **generate_kwargs:
            Keyword arguments forwarded to ``generator.generate()``.

        Returns
        -------
        RegenerationResult
            The final content and metadata about the regeneration loop.
        """
        validation_history: list[list[dict[str, Any]]] = []
        feedback = ""

        for attempt in range(1, self.max_attempts + 1):
            self.log.info("regeneration_attempt", attempt=attempt)

            # ---------- Generate ----------
            if feedback:
                # Inject feedback into the generation kwargs
                generate_kwargs["_feedback"] = feedback

            content = self.generator.generate(**generate_kwargs)

            # ---------- Validate ----------
            all_results: list[ValidationResult] = []
            for validator_fn in self.validators:
                results = validator_fn(content)
                if isinstance(results, ValidationResult):
                    all_results.append(results)
                elif isinstance(results, list):
                    all_results.extend(results)

            round_results = [
                r.model_dump() if hasattr(r, "model_dump") else r
                for r in all_results
            ]
            validation_history.append(round_results)

            all_passed = all(r.passed for r in all_results)

            if all_passed:
                self.log.info(
                    "regeneration_succeeded",
                    attempt=attempt,
                    total_checks=len(all_results),
                )
                return RegenerationResult(
                    content=content,
                    attempts=attempt,
                    succeeded=True,
                    validation_history=validation_history,
                )

            # ---------- Build feedback for next attempt ----------
            failures = [r for r in all_results if not r.passed]
            self.log.warning(
                "regeneration_validation_failed",
                attempt=attempt,
                failures=len(failures),
                total_checks=len(all_results),
            )
            feedback = _format_feedback(all_results)

        # Exhausted all attempts
        self.log.error(
            "regeneration_exhausted",
            max_attempts=self.max_attempts,
        )
        return RegenerationResult(
            content=content,  # type: ignore[possibly-undefined]
            attempts=self.max_attempts,
            succeeded=False,
            validation_history=validation_history,
        )
