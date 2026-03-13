"""Pipeline lifecycle hooks with a simple registry pattern."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable

import structlog

logger = structlog.get_logger(__name__)

# Type alias for hook callbacks
HookCallback = Callable[..., None]


class HookRegistry:
    """Registry that stores and dispatches pipeline lifecycle hooks."""

    def __init__(self) -> None:
        self._hooks: dict[str, list[HookCallback]] = defaultdict(list)

    def register(self, event: str, callback: HookCallback) -> None:
        """Register a callback for a given event name."""
        self._hooks[event].append(callback)

    def unregister(self, event: str, callback: HookCallback) -> None:
        """Remove a previously registered callback."""
        try:
            self._hooks[event].remove(callback)
        except ValueError:
            pass

    def dispatch(self, event: str, **kwargs: Any) -> None:
        """Dispatch an event, calling all registered callbacks."""
        for callback in self._hooks.get(event, []):
            try:
                callback(**kwargs)
            except Exception:
                logger.exception("hook_callback_error", event=event)


class PipelineHooks:
    """Built-in structlog-based hooks for pipeline lifecycle events.

    Attach an instance to a :class:`HookRegistry` to get structured logging
    for every pipeline and step transition.
    """

    # ------------------------------------------------------------------
    # Step-level hooks
    # ------------------------------------------------------------------

    @staticmethod
    def on_step_start(*, step_name: str, pipeline_id: str, **_: Any) -> None:
        logger.info(
            "pipeline.step.start",
            step_name=step_name,
            pipeline_id=pipeline_id,
        )

    @staticmethod
    def on_step_complete(
        *, step_name: str, pipeline_id: str, result: Any = None, **_: Any
    ) -> None:
        logger.info(
            "pipeline.step.complete",
            step_name=step_name,
            pipeline_id=pipeline_id,
            result_summary=str(result)[:200] if result else None,
        )

    @staticmethod
    def on_step_failed(
        *, step_name: str, pipeline_id: str, error: str = "", **_: Any
    ) -> None:
        logger.error(
            "pipeline.step.failed",
            step_name=step_name,
            pipeline_id=pipeline_id,
            error=error,
        )

    # ------------------------------------------------------------------
    # Pipeline-level hooks
    # ------------------------------------------------------------------

    @staticmethod
    def on_pipeline_start(*, pipeline_id: str, name: str = "", **_: Any) -> None:
        logger.info(
            "pipeline.start",
            pipeline_id=pipeline_id,
            name=name,
        )

    @staticmethod
    def on_pipeline_complete(
        *, pipeline_id: str, status: str = "completed", **_: Any
    ) -> None:
        logger.info(
            "pipeline.complete",
            pipeline_id=pipeline_id,
            status=status,
        )

    def register_all(self, registry: HookRegistry) -> None:
        """Convenience method to register all built-in hooks."""
        registry.register("on_step_start", self.on_step_start)
        registry.register("on_step_complete", self.on_step_complete)
        registry.register("on_step_failed", self.on_step_failed)
        registry.register("on_pipeline_start", self.on_pipeline_start)
        registry.register("on_pipeline_complete", self.on_pipeline_complete)
