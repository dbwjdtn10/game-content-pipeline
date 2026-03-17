"""Pipeline orchestrator: parses YAML config, builds a DAG, and executes."""

from __future__ import annotations

import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog
import yaml
from celery import group

from src.pipeline.hooks import HookRegistry, PipelineHooks
from src.pipeline.tasks import (
    export_content_task,
    generate_content_task,
    validate_content_task,
)

logger = structlog.get_logger(__name__)


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class StepResult:
    """Result for a single pipeline step."""

    name: str
    status: StepStatus = StepStatus.PENDING
    result: Any = None
    error: str | None = None


@dataclass
class PipelineResult:
    """Aggregate result for the full pipeline execution."""

    pipeline_id: str
    status: str = "pending"
    step_results: dict[str, StepResult] = field(default_factory=dict)

    @property
    def failed_steps(self) -> list[StepResult]:
        return [
            s for s in self.step_results.values() if s.status == StepStatus.FAILED
        ]

    @property
    def all_passed(self) -> bool:
        return all(
            s.status == StepStatus.COMPLETED for s in self.step_results.values()
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "pipeline_id": self.pipeline_id,
            "status": self.status,
            "steps": {
                name: {
                    "status": sr.status.value,
                    "result": sr.result,
                    "error": sr.error,
                }
                for name, sr in self.step_results.items()
            },
        }


@dataclass
class PipelineStep:
    """Parsed representation of a single pipeline step."""

    name: str
    generator: str  # task type: generate / validate / export
    params: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)


class PipelineOrchestrator:
    """Parses a pipeline YAML config, builds a dependency graph, and
    dispatches steps via Celery groups/chains.

    Example YAML::

        name: item_pipeline
        steps:
          - name: generate_items
            generator: generate
            params:
              content_type: item
          - name: validate_items
            generator: validate
            params:
              content_type: item
            depends_on:
              - generate_items
          - name: export_items
            generator: export
            params:
              export_format: json
            depends_on:
              - validate_items
    """

    def __init__(
        self,
        hook_registry: HookRegistry | None = None,
        retry_on_fail: int = 0,
    ) -> None:
        self.hook_registry = hook_registry or HookRegistry()
        self.retry_on_fail = retry_on_fail

        # Register default logging hooks
        PipelineHooks().register_all(self.hook_registry)

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def parse_config(self, yaml_str: str) -> tuple[str, list[PipelineStep]]:
        """Parse a YAML pipeline config and return (pipeline_name, steps)."""
        cfg = yaml.safe_load(yaml_str)
        pipeline_name: str = cfg.get("name", "unnamed_pipeline")
        raw_steps: list[dict[str, Any]] = cfg.get("steps", [])

        steps: list[PipelineStep] = []
        for raw in raw_steps:
            steps.append(
                PipelineStep(
                    name=raw["name"],
                    generator=raw.get("generator", "generate"),
                    params=raw.get("params", {}),
                    depends_on=raw.get("depends_on", []),
                )
            )
        return pipeline_name, steps

    # ------------------------------------------------------------------
    # DAG / topological sort
    # ------------------------------------------------------------------

    @staticmethod
    def _topological_sort(steps: list[PipelineStep]) -> list[list[PipelineStep]]:
        """Return steps grouped into layers that respect dependencies.

        Each layer contains steps whose dependencies are satisfied by prior
        layers.  Steps within a layer can execute in parallel.
        """
        step_map: dict[str, PipelineStep] = {s.name: s for s in steps}
        in_degree: dict[str, int] = {s.name: 0 for s in steps}
        dependents: dict[str, list[str]] = defaultdict(list)

        for s in steps:
            for dep in s.depends_on:
                if dep not in step_map:
                    raise ValueError(
                        f"Step '{s.name}' depends on unknown step '{dep}'"
                    )
                in_degree[s.name] += 1
                dependents[dep].append(s.name)

        # BFS layer-by-layer
        queue: deque[str] = deque(
            name for name, deg in in_degree.items() if deg == 0
        )
        layers: list[list[PipelineStep]] = []

        while queue:
            layer_names = list(queue)
            queue.clear()
            layers.append([step_map[n] for n in layer_names])
            for name in layer_names:
                for dep_name in dependents[name]:
                    in_degree[dep_name] -= 1
                    if in_degree[dep_name] == 0:
                        queue.append(dep_name)

        resolved = sum(len(layer) for layer in layers)
        if resolved != len(steps):
            raise ValueError("Cycle detected in pipeline dependency graph")

        return layers

    # ------------------------------------------------------------------
    # Task mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _build_celery_signature(step: PipelineStep, prior_result: Any = None):
        """Create a Celery task signature for the given step."""
        params = dict(step.params)

        if step.generator == "generate":
            content_type = params.pop("content_type", "item")
            return generate_content_task.s(content_type, params)

        if step.generator == "validate":
            content_type = params.pop("content_type", "item")
            # When chained, the previous result is passed as the first
            # positional argument.  We extract ``data`` from it.
            data: dict[str, Any] = {}
            if isinstance(prior_result, dict):
                data = prior_result.get("data", prior_result)
            validators = params.pop("validators", None)
            return validate_content_task.s(content_type, data, validators)

        if step.generator == "export":
            data = {}
            if isinstance(prior_result, dict):
                data = prior_result.get("data", prior_result)
            export_format = params.pop("export_format", "json")
            output_path = params.pop("output_path", None)
            template_name = params.pop("template_name", None)
            return export_content_task.s(data, export_format, output_path, template_name)

        raise ValueError(f"Unknown generator type: {step.generator}")

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def run(self, yaml_config: str) -> PipelineResult:
        """Parse the YAML config and execute the pipeline synchronously.

        Independent steps within the same dependency layer are dispatched as
        a Celery :func:`group`; layers are chained sequentially.
        """
        pipeline_id = uuid.uuid4().hex[:12]
        pipeline_name, steps = self.parse_config(yaml_config)

        pipeline_result = PipelineResult(pipeline_id=pipeline_id)
        for step in steps:
            pipeline_result.step_results[step.name] = StepResult(name=step.name)

        self.hook_registry.dispatch(
            "on_pipeline_start", pipeline_id=pipeline_id, name=pipeline_name
        )

        try:
            layers = self._topological_sort(steps)
        except ValueError as exc:
            pipeline_result.status = "failed"
            logger.error("pipeline.dag_error", error=str(exc))
            return pipeline_result

        pipeline_result.status = "running"
        layer_results: dict[str, Any] = {}

        for layer in layers:
            tasks = []
            step_names: list[str] = []

            for step in layer:
                sr = pipeline_result.step_results[step.name]
                sr.status = StepStatus.RUNNING

                self.hook_registry.dispatch(
                    "on_step_start",
                    step_name=step.name,
                    pipeline_id=pipeline_id,
                )

                # Resolve prior results for dependencies
                prior = None
                if step.depends_on:
                    prior = layer_results.get(step.depends_on[0])

                sig = self._build_celery_signature(step, prior)
                tasks.append(sig)
                step_names.append(step.name)

            # Execute the layer
            if len(tasks) == 1:
                async_result = tasks[0].apply_async()
                results = [async_result.get(timeout=300)]
            else:
                grp = group(tasks)
                group_result = grp.apply_async()
                results = group_result.get(timeout=300)

            # Process results
            for step_name, result in zip(step_names, results):
                sr = pipeline_result.step_results[step_name]
                layer_results[step_name] = result

                if isinstance(result, dict) and result.get("status") == "error":
                    sr.status = StepStatus.FAILED
                    sr.error = result.get("error", "Unknown error")
                    sr.result = result

                    self.hook_registry.dispatch(
                        "on_step_failed",
                        step_name=step_name,
                        pipeline_id=pipeline_id,
                        error=sr.error,
                    )

                    # Retry logic
                    if self.retry_on_fail > 0:
                        sr = self._retry_step(
                            step_name,
                            steps,
                            layer_results,
                            pipeline_id,
                            sr,
                        )
                        pipeline_result.step_results[step_name] = sr
                else:
                    sr.status = StepStatus.COMPLETED
                    sr.result = result

                    self.hook_registry.dispatch(
                        "on_step_complete",
                        step_name=step_name,
                        pipeline_id=pipeline_id,
                        result=result,
                    )

        pipeline_result.status = (
            "completed" if pipeline_result.all_passed else "failed"
        )

        self.hook_registry.dispatch(
            "on_pipeline_complete",
            pipeline_id=pipeline_id,
            status=pipeline_result.status,
        )

        return pipeline_result

    def _retry_step(
        self,
        step_name: str,
        steps: list[PipelineStep],
        layer_results: dict[str, Any],
        pipeline_id: str,
        sr: StepResult,
    ) -> StepResult:
        """Retry a failed step up to ``self.retry_on_fail`` times."""
        step = next(s for s in steps if s.name == step_name)
        prior = None
        if step.depends_on:
            prior = layer_results.get(step.depends_on[0])

        for attempt in range(1, self.retry_on_fail + 1):
            logger.info(
                "pipeline.step.retry",
                step_name=step_name,
                attempt=attempt,
                pipeline_id=pipeline_id,
            )
            sig = self._build_celery_signature(step, prior)
            result = sig.apply_async().get(timeout=300)

            if isinstance(result, dict) and result.get("status") == "error":
                continue

            sr.status = StepStatus.COMPLETED
            sr.result = result
            sr.error = None
            layer_results[step_name] = result

            self.hook_registry.dispatch(
                "on_step_complete",
                step_name=step_name,
                pipeline_id=pipeline_id,
                result=result,
            )
            return sr

        return sr
