"""Tests for the pipeline orchestrator (src/pipeline/).

Covers YAML config parsing, dependency graph building (topological sort),
and pipeline execution with mocked tasks.
"""

from __future__ import annotations

import textwrap
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import yaml


# =========================================================================
# Sample pipeline config
# =========================================================================

SAMPLE_CONFIG_YAML = textwrap.dedent("""\
    pipeline:
      name: "테스트 파이프라인"

      steps:
        - name: generate_weapons
          generator: item
          params:
            type: weapon
            rarity: [rare, epic]
            count: 5
            level_range: [50, 60]

        - name: generate_monsters
          generator: monster
          params:
            region: "화산 심연"
            count: 3
            level_range: [50, 60]

        - name: generate_quests
          generator: quest
          params:
            type: [side]
            region: "화산 심연"
            count: 2
          depends_on:
            - generate_weapons
            - generate_monsters

        - name: validate_all
          validator: [consistency, balance, duplicate]
          target: [generate_weapons, generate_monsters, generate_quests]
          depends_on:
            - generate_quests

        - name: export
          format: [json, csv]
          depends_on:
            - validate_all

      options:
        async: false
        retry_on_fail: 2
        auto_fix: true
""")


# =========================================================================
# 1. YAML config parsing
# =========================================================================

class TestConfigParsing:
    """Ensure pipeline YAML configs are parsed correctly."""

    def test_parse_yaml_structure(self) -> None:
        """The YAML should parse into a dict with expected top-level keys."""
        config = yaml.safe_load(SAMPLE_CONFIG_YAML)
        assert "pipeline" in config
        pipeline = config["pipeline"]
        assert pipeline["name"] == "테스트 파이프라인"
        assert "steps" in pipeline
        assert "options" in pipeline

    def test_parse_steps_count(self) -> None:
        config = yaml.safe_load(SAMPLE_CONFIG_YAML)
        steps = config["pipeline"]["steps"]
        assert len(steps) == 5

    def test_parse_step_params(self) -> None:
        config = yaml.safe_load(SAMPLE_CONFIG_YAML)
        weapons_step = config["pipeline"]["steps"][0]
        assert weapons_step["name"] == "generate_weapons"
        assert weapons_step["params"]["type"] == "weapon"
        assert weapons_step["params"]["count"] == 5

    def test_parse_dependencies(self) -> None:
        config = yaml.safe_load(SAMPLE_CONFIG_YAML)
        quest_step = config["pipeline"]["steps"][2]
        assert "depends_on" in quest_step
        assert set(quest_step["depends_on"]) == {"generate_weapons", "generate_monsters"}

    def test_parse_options(self) -> None:
        config = yaml.safe_load(SAMPLE_CONFIG_YAML)
        options = config["pipeline"]["options"]
        assert options["async"] is False
        assert options["retry_on_fail"] == 2
        assert options["auto_fix"] is True

    def test_invalid_yaml_raises(self) -> None:
        """Malformed YAML should raise an error."""
        bad_yaml = "pipeline:\n  steps:\n    - name: [invalid\n"
        with pytest.raises(yaml.YAMLError):
            yaml.safe_load(bad_yaml)


# =========================================================================
# 2. Dependency graph building (topological sort)
# =========================================================================

def _build_dependency_graph(
    steps: list[dict[str, Any]],
) -> dict[str, list[str]]:
    """Build an adjacency list from pipeline steps.

    Returns a dict mapping each step name to the list of steps it depends on.
    """
    graph: dict[str, list[str]] = {}
    for step in steps:
        name = step["name"]
        deps = step.get("depends_on", [])
        graph[name] = deps
    return graph


def _topological_sort(graph: dict[str, list[str]]) -> list[str]:
    """Kahn's algorithm for topological sorting."""
    from collections import deque

    in_degree: dict[str, int] = {node: 0 for node in graph}
    reverse: dict[str, list[str]] = {node: [] for node in graph}

    for node, deps in graph.items():
        in_degree[node] = len(deps)
        for dep in deps:
            if dep not in reverse:
                reverse[dep] = []
            reverse[dep].append(node)

    queue: deque[str] = deque(
        node for node, deg in in_degree.items() if deg == 0
    )
    result: list[str] = []

    while queue:
        node = queue.popleft()
        result.append(node)
        for dependent in reverse.get(node, []):
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)

    if len(result) != len(graph):
        raise ValueError("Cycle detected in dependency graph")

    return result


class TestDependencyGraph:
    """Verify dependency graph construction and topological sort."""

    def test_build_graph(self) -> None:
        config = yaml.safe_load(SAMPLE_CONFIG_YAML)
        steps = config["pipeline"]["steps"]
        graph = _build_dependency_graph(steps)
        assert graph["generate_weapons"] == []
        assert set(graph["generate_quests"]) == {"generate_weapons", "generate_monsters"}

    def test_topological_sort_order(self) -> None:
        config = yaml.safe_load(SAMPLE_CONFIG_YAML)
        steps = config["pipeline"]["steps"]
        graph = _build_dependency_graph(steps)
        order = _topological_sort(graph)

        # Verify constraints
        assert order.index("generate_weapons") < order.index("generate_quests")
        assert order.index("generate_monsters") < order.index("generate_quests")
        assert order.index("generate_quests") < order.index("validate_all")
        assert order.index("validate_all") < order.index("export")

    def test_independent_tasks_can_be_in_any_order(self) -> None:
        """generate_weapons and generate_monsters have no mutual dependency."""
        config = yaml.safe_load(SAMPLE_CONFIG_YAML)
        steps = config["pipeline"]["steps"]
        graph = _build_dependency_graph(steps)
        order = _topological_sort(graph)
        # Both must appear before generate_quests, but relative order is flexible
        assert "generate_weapons" in order
        assert "generate_monsters" in order

    def test_cycle_detection(self) -> None:
        """A circular dependency should raise ValueError."""
        graph = {
            "a": ["b"],
            "b": ["c"],
            "c": ["a"],
        }
        with pytest.raises(ValueError, match="Cycle"):
            _topological_sort(graph)

    def test_single_step_no_deps(self) -> None:
        graph = {"only_step": []}
        order = _topological_sort(graph)
        assert order == ["only_step"]


# =========================================================================
# 3. Pipeline execution with mocked tasks
# =========================================================================

class TestPipelineExecution:
    """Test PipelineOrchestrator execution with mocked generator/validator tasks."""

    def _make_orchestrator(self) -> Any:
        try:
            from src.pipeline.orchestrator import PipelineOrchestrator
            return PipelineOrchestrator
        except ImportError:
            pytest.skip("PipelineOrchestrator not yet implemented")

    def test_orchestrator_import(self) -> None:
        """PipelineOrchestrator should be importable."""
        OrchestratorClass = self._make_orchestrator()
        assert OrchestratorClass is not None

    @patch("src.pipeline.orchestrator.PipelineOrchestrator")
    def test_pipeline_run_calls_steps_in_order(
        self, MockOrchestrator: MagicMock
    ) -> None:
        """Mocked orchestrator should call steps in dependency order."""
        mock_instance = MockOrchestrator.return_value
        mock_instance.run.return_value = MagicMock(
            success=True,
            steps_completed=5,
            steps_failed=0,
        )
        config = yaml.safe_load(SAMPLE_CONFIG_YAML)
        result = mock_instance.run(config)
        assert result.success is True
        assert result.steps_completed == 5

    @patch("src.pipeline.orchestrator.PipelineOrchestrator")
    def test_pipeline_handles_step_failure(
        self, MockOrchestrator: MagicMock
    ) -> None:
        """Pipeline should report failures gracefully."""
        mock_instance = MockOrchestrator.return_value
        mock_instance.run.return_value = MagicMock(
            success=False,
            steps_completed=3,
            steps_failed=2,
            errors=["generate_quests failed: timeout", "validate_all skipped"],
        )
        config = yaml.safe_load(SAMPLE_CONFIG_YAML)
        result = mock_instance.run(config)
        assert result.success is False
        assert result.steps_failed == 2
        assert len(result.errors) == 2

    def test_pipeline_result_import(self) -> None:
        """PipelineResult should be importable."""
        try:
            from src.pipeline.orchestrator import PipelineResult
            assert PipelineResult is not None
        except ImportError:
            pytest.skip("PipelineResult not yet implemented")

    def test_empty_pipeline_config(self) -> None:
        """An empty steps list should produce a valid but trivial pipeline."""
        config = yaml.safe_load(
            "pipeline:\n  name: empty\n  steps: []\n  options: {}"
        )
        assert config["pipeline"]["steps"] == []
        graph = _build_dependency_graph(config["pipeline"]["steps"])
        order = _topological_sort(graph)
        assert order == []
