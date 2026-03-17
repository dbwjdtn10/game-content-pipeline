"""Consistency validation using LLM-based tone and naming checks."""

from __future__ import annotations

import json
import time

import structlog
from google import genai
from google.genai import types

from src.config import get_settings
from src.validators.models import ValidationResult

logger = structlog.get_logger(__name__)

DEFAULT_MODEL = "gemini-2.0-flash"
MAX_RETRIES = 3
INITIAL_BACKOFF = 1.0


class _ToneCheckResult:
    """Internal wrapper for LLM tone-check response parsing."""


class ConsistencyValidator:
    """Validates content consistency against the game world setting."""

    def __init__(self, *, model: str = DEFAULT_MODEL) -> None:
        settings = get_settings()
        self.client = genai.Client(api_key=settings.gemini_api_key)
        self.model = model
        self.log = logger.bind(validator="ConsistencyValidator")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_tone(self, content: str, world_setting: str) -> ValidationResult:
        """Use the LLM to evaluate whether *content* matches the world-setting tone.

        Returns a ValidationResult with severity based on the LLM assessment.
        """
        self.log.info("check_tone_start", content_length=len(content))

        prompt = (
            "You are a quality-assurance editor for a fantasy RPG.\n\n"
            "World setting and tone guide:\n"
            f"---\n{world_setting}\n---\n\n"
            "Content to evaluate:\n"
            f"---\n{content}\n---\n\n"
            "Evaluate whether the content's tone, vocabulary, and style are "
            "consistent with the world setting. Return a JSON object with:\n"
            '- "consistent": boolean (true if tone matches)\n'
            '- "score": float 0-1 (1 = perfect match)\n'
            '- "issues": list of strings describing any tone mismatches\n'
            '- "suggestions": list of strings with improvement suggestions\n'
        )

        raw = self._call_llm(prompt)
        data = json.loads(raw)

        consistent: bool = data.get("consistent", False)
        score: float = data.get("score", 0.0)
        issues: list[str] = data.get("issues", [])

        if consistent and score >= 0.8:
            severity = "info"
            message = "Content tone is consistent with the world setting."
        elif score >= 0.5:
            severity = "warning"
            message = f"Tone partially matches (score={score:.2f}). Issues: {'; '.join(issues)}"
        else:
            severity = "error"
            message = f"Tone mismatch (score={score:.2f}). Issues: {'; '.join(issues)}"

        result = ValidationResult(
            passed=consistent,
            check_name="tone_consistency",
            severity=severity,  # type: ignore[arg-type]
            message=message,
            details=data,
        )
        self.log.info("check_tone_done", passed=result.passed, severity=result.severity)
        return result

    def check_naming(self, name: str, existing_names: list[str]) -> ValidationResult:
        """Check whether *name* fits the naming conventions of *existing_names*.

        Uses the LLM to evaluate stylistic consistency.
        """
        self.log.info("check_naming_start", name=name, existing_count=len(existing_names))

        if not existing_names:
            return ValidationResult(
                passed=True,
                check_name="naming_consistency",
                severity="info",
                message="No existing names to compare against.",
            )

        sample = existing_names[:30]

        prompt = (
            "You are a naming convention reviewer for a fantasy RPG.\n\n"
            f"Existing names in the game:\n{json.dumps(sample, ensure_ascii=False)}\n\n"
            f"New proposed name: \"{name}\"\n\n"
            "Evaluate whether the new name fits the style, language, and "
            "conventions of the existing names. Return a JSON object with:\n"
            '- "fits": boolean (true if the name fits)\n'
            '- "score": float 0-1\n'
            '- "reasons": list of strings explaining the evaluation\n'
        )

        raw = self._call_llm(prompt)
        data = json.loads(raw)

        fits: bool = data.get("fits", False)
        score: float = data.get("score", 0.0)
        reasons: list[str] = data.get("reasons", [])

        if fits:
            severity = "info"
            message = f"Name '{name}' fits existing naming conventions (score={score:.2f})."
        elif score >= 0.5:
            severity = "warning"
            message = (
                f"Name '{name}' partially fits (score={score:.2f}). "
                f"Notes: {'; '.join(reasons)}"
            )
        else:
            severity = "error"
            message = (
                f"Name '{name}' does not fit naming conventions (score={score:.2f}). "
                f"Notes: {'; '.join(reasons)}"
            )

        result = ValidationResult(
            passed=fits,
            check_name="naming_consistency",
            severity=severity,  # type: ignore[arg-type]
            message=message,
            details=data,
        )
        self.log.info("check_naming_done", passed=result.passed, severity=result.severity)
        return result

    # ------------------------------------------------------------------
    # LLM helper with retry
    # ------------------------------------------------------------------

    def _call_llm(self, prompt: str) -> str:
        """Call Gemini with retry + exponential backoff, returning raw text."""
        backoff = INITIAL_BACKOFF

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
        )

        for attempt in range(1, MAX_RETRIES + 1):
            start = time.perf_counter()
            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=config,
                )
                latency = time.perf_counter() - start
                self.log.info(
                    "llm_call_success",
                    attempt=attempt,
                    latency_s=round(latency, 3),
                )
                text = response.text
                if text is None:
                    raise ValueError("Model returned empty response text.")
                return text

            except Exception:
                latency = time.perf_counter() - start
                self.log.warning(
                    "llm_call_failed",
                    attempt=attempt,
                    latency_s=round(latency, 3),
                    exc_info=True,
                )
                if attempt == MAX_RETRIES:
                    raise
                time.sleep(backoff)
                backoff *= 2

        raise RuntimeError("Exhausted retries without raising.")  # pragma: no cover
