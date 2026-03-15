"""Abstract base class for all content generators."""

from __future__ import annotations

import abc
import json
import time
from pathlib import Path
from typing import Any, TypeVar

import structlog
from google import genai
from google.genai import types
from pydantic import BaseModel

from src.config import get_settings

logger = structlog.get_logger(__name__)

T = TypeVar("T", bound=BaseModel)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PROMPTS_DIR = PROJECT_ROOT / "prompts"
SEED_DIR = PROJECT_ROOT / "game_data" / "seed"
WORLD_SETTING_PATH = PROJECT_ROOT / "game_data" / "seed" / "world_setting.md"

DEFAULT_MODEL = "gemini-2.0-flash"
MAX_RETRIES = 3
INITIAL_BACKOFF = 1.0


class BaseGenerator(abc.ABC):
    """Abstract base generator that wraps Gemini API calls with retry logic,
    structured output, and seed-data helpers."""

    def __init__(self, *, model: str = DEFAULT_MODEL) -> None:
        settings = get_settings()
        self.client = genai.Client(api_key=settings.gemini_api_key)
        self.model = model
        self.log = logger.bind(generator=self.__class__.__name__)

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abc.abstractmethod
    def generate(self, *args: Any, **kwargs: Any) -> Any:
        """Generate content.  Subclasses define their own signature."""

    @abc.abstractmethod
    def _build_prompt(self, **kwargs: Any) -> str:
        """Build the full prompt string for the LLM call."""

    @abc.abstractmethod
    def _parse_response(self, raw: str) -> Any:
        """Parse the raw JSON string returned by the LLM."""

    # ------------------------------------------------------------------
    # LLM call with retry
    # ------------------------------------------------------------------

    def _call_llm(
        self,
        prompt: str,
        *,
        response_schema: type[BaseModel] | None = None,
        system_instruction: str | None = None,
    ) -> str:
        """Call Gemini with retry + exponential backoff.

        Returns the raw text content from the model response.
        """
        backoff = INITIAL_BACKOFF

        config_kwargs: dict[str, Any] = {
            "response_mime_type": "application/json",
        }
        if response_schema is not None:
            config_kwargs["response_schema"] = response_schema
        if system_instruction is not None:
            config_kwargs["system_instruction"] = system_instruction

        generation_config = types.GenerateContentConfig(**config_kwargs)

        for attempt in range(1, MAX_RETRIES + 1):
            start = time.perf_counter()
            try:
                self.log.info(
                    "llm_call_start",
                    attempt=attempt,
                    model=self.model,
                )

                response = self.client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=generation_config,
                )

                latency = time.perf_counter() - start
                usage = response.usage_metadata
                self.log.info(
                    "llm_call_success",
                    attempt=attempt,
                    latency_s=round(latency, 3),
                    prompt_tokens=getattr(usage, "prompt_token_count", None),
                    completion_tokens=getattr(usage, "candidates_token_count", None),
                    total_tokens=getattr(usage, "total_token_count", None),
                    cache_hit=getattr(usage, "cached_content_token_count", 0) > 0,
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

        # Unreachable, but keeps mypy happy.
        raise RuntimeError("Exhausted retries without raising.")  # pragma: no cover

    # ------------------------------------------------------------------
    # Feedback support for regeneration loop
    # ------------------------------------------------------------------

    def _append_feedback(self, prompt: str, feedback: str) -> str:
        """Append corrective feedback to the prompt for regeneration."""
        if not feedback:
            return prompt
        return (
            f"{prompt}\n\n"
            "--- IMPORTANT: CORRECTIVE FEEDBACK FROM PREVIOUS ATTEMPT ---\n"
            f"{feedback}\n"
            "--- END FEEDBACK ---\n"
        )

    # ------------------------------------------------------------------
    # Seed / reference data helpers (cached)
    # ------------------------------------------------------------------

    _seed_cache: dict[str, list[dict[str, Any]]] = {}
    _world_setting_cache: str | None = None
    _prompt_template_cache: dict[str, str] = {}

    @classmethod
    def load_seed(cls, filename: str) -> list[dict[str, Any]]:
        """Load a JSON seed file from ``game_data/seed/`` (cached)."""
        if filename in cls._seed_cache:
            return cls._seed_cache[filename]
        path = SEED_DIR / filename
        if not path.exists():
            logger.warning("seed_file_not_found", path=str(path))
            return []
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        result = data if isinstance(data, list) else [data]
        cls._seed_cache[filename] = result
        return result

    @classmethod
    def load_world_setting(cls) -> str:
        """Load the world-setting markdown for tone/lore reference (cached)."""
        if cls._world_setting_cache is not None:
            return cls._world_setting_cache
        if not WORLD_SETTING_PATH.exists():
            logger.warning("world_setting_not_found", path=str(WORLD_SETTING_PATH))
            return ""
        cls._world_setting_cache = WORLD_SETTING_PATH.read_text(encoding="utf-8")
        return cls._world_setting_cache

    @classmethod
    def load_prompt_template(cls, name: str) -> str:
        """Load a prompt template from the prompts directory (cached).

        Looks in ``prompts/v1/<name>.txt`` by default.
        """
        if name in cls._prompt_template_cache:
            return cls._prompt_template_cache[name]
        path = PROMPTS_DIR / "v1" / f"{name}.txt"
        if not path.exists():
            logger.warning("prompt_template_not_found", path=str(path))
            return ""
        result = path.read_text(encoding="utf-8")
        cls._prompt_template_cache[name] = result
        return result

    @classmethod
    def clear_cache(cls) -> None:
        """Clear all cached seed data, world settings, and prompt templates."""
        cls._seed_cache.clear()
        cls._world_setting_cache = None
        cls._prompt_template_cache.clear()

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    @staticmethod
    def _filter_by_level_range(
        items: list[dict[str, Any]],
        level_range: tuple[int, int],
        level_key: str = "level_requirement",
    ) -> list[dict[str, Any]]:
        """Return items whose level falls within *level_range* (inclusive)."""
        lo, hi = level_range
        return [
            item
            for item in items
            if lo <= item.get(level_key, 0) <= hi
        ]

    @staticmethod
    def _to_json_block(data: Any, *, indent: int = 2) -> str:
        """Serialize *data* to a pretty JSON string for prompt inclusion."""
        return json.dumps(data, ensure_ascii=False, indent=indent)
