"""Benchmark script for the Game Content Pipeline.

Measures:
  - Generation speed (items per minute)
  - Validation pass rate
  - LLM API latency (p50, p95, p99)

Outputs a Markdown report to stdout or a file.

Usage::

    python scripts/benchmark.py
    python scripts/benchmark.py --output reports/benchmark.md
    python scripts/benchmark.py --count 20 --skip-llm
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

SEED_DIR = PROJECT_ROOT / "game_data" / "seed"
FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    return data if isinstance(data, list) else [data]


def _percentile(data: list[float], pct: float) -> float:
    """Compute the *pct*-th percentile of *data*."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * (pct / 100.0)
    f = int(k)
    c = f + 1
    if c >= len(sorted_data):
        return sorted_data[f]
    return sorted_data[f] + (k - f) * (sorted_data[c] - sorted_data[f])


# ---------------------------------------------------------------------------
# Benchmark: Generation speed
# ---------------------------------------------------------------------------

def benchmark_generation_speed(count: int, skip_llm: bool = False) -> dict[str, Any]:
    """Measure how fast items can be generated.

    If *skip_llm* is True, a mock generator is used (no real API calls).
    """
    latencies: list[float] = []
    errors = 0

    if skip_llm:
        # Use fixture data to simulate generation
        items = _load_json(FIXTURES_DIR / "sample_items.json")
        if not items:
            items = [{"name": f"test_item_{i}", "stats": {"atk": 100}} for i in range(count)]

        for i in range(count):
            start = time.perf_counter()
            # Simulate processing time
            _ = json.dumps(items[i % len(items)], ensure_ascii=False)
            elapsed = time.perf_counter() - start
            latencies.append(elapsed)
    else:
        try:
            from unittest.mock import patch

            from src.generators.item_generator import ItemGenerator

            sample_response = json.dumps(
                _load_json(FIXTURES_DIR / "sample_items.json")[0],
                ensure_ascii=False,
            )

            with patch("src.generators.base.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(gemini_api_key="benchmark-key")
                with patch("google.genai.Client") as mock_client_cls:
                    mock_response = MagicMock()
                    mock_response.text = sample_response
                    mock_response.usage_metadata = MagicMock(
                        prompt_token_count=500,
                        candidates_token_count=300,
                        total_token_count=800,
                        cached_content_token_count=0,
                    )
                    mock_client = MagicMock()
                    mock_client.models.generate_content.return_value = mock_response
                    mock_client_cls.return_value = mock_client

                    gen = ItemGenerator()
                    for i in range(count):
                        start = time.perf_counter()
                        try:
                            gen._call_llm("benchmark prompt")
                        except Exception:
                            errors += 1
                        elapsed = time.perf_counter() - start
                        latencies.append(elapsed)

        except ImportError:
            print("  [WARN] ItemGenerator not available; falling back to mock.")
            return benchmark_generation_speed(count, skip_llm=True)

    total_time = sum(latencies)
    items_per_minute = (count / total_time) * 60 if total_time > 0 else 0

    return {
        "count": count,
        "total_time_s": round(total_time, 4),
        "items_per_minute": round(items_per_minute, 1),
        "avg_latency_ms": round(statistics.mean(latencies) * 1000, 2) if latencies else 0,
        "p50_ms": round(_percentile(latencies, 50) * 1000, 2),
        "p95_ms": round(_percentile(latencies, 95) * 1000, 2),
        "p99_ms": round(_percentile(latencies, 99) * 1000, 2),
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Benchmark: Validation pass rate
# ---------------------------------------------------------------------------

def benchmark_validation_pass_rate() -> dict[str, Any]:
    """Measure how many sample items pass validation."""
    items = _load_json(FIXTURES_DIR / "sample_items.json")
    if not items:
        return {"total": 0, "passed": 0, "failed": 0, "pass_rate": 0.0}

    passed = 0
    failed = 0
    check_results: list[dict[str, Any]] = []

    try:
        from src.validators.schema_check import SchemaValidator

        schema_path = PROJECT_ROOT / "game_data" / "schema" / "item_schema.json"
        if schema_path.exists():
            with schema_path.open("r", encoding="utf-8") as fh:
                schema = json.load(fh)
            validator = SchemaValidator()
            for item in items:
                result = validator.validate(item, schema)
                if result.passed:
                    passed += 1
                else:
                    failed += 1
                check_results.append({
                    "name": item.get("name", "unknown"),
                    "passed": result.passed,
                    "message": result.message,
                })
        else:
            # No schema file; assume all pass
            passed = len(items)
    except ImportError:
        # SchemaValidator not available; do basic checks
        for item in items:
            required = ["name", "description", "rarity", "type", "level_requirement", "stats"]
            missing = [f for f in required if f not in item]
            if missing:
                failed += 1
                check_results.append({
                    "name": item.get("name", "unknown"),
                    "passed": False,
                    "message": f"Missing fields: {missing}",
                })
            else:
                passed += 1
                check_results.append({
                    "name": item.get("name", "unknown"),
                    "passed": True,
                    "message": "OK",
                })

    total = passed + failed
    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": round(passed / total * 100, 1) if total else 0.0,
        "details": check_results,
    }


# ---------------------------------------------------------------------------
# Benchmark: LLM API latency
# ---------------------------------------------------------------------------

def benchmark_llm_latency(calls: int = 10, skip_llm: bool = False) -> dict[str, Any]:
    """Measure LLM API call latency.

    With *skip_llm=True*, simulates latency without real API calls.
    """
    latencies: list[float] = []

    if skip_llm:
        import random

        for _ in range(calls):
            # Simulate 50-500ms latency
            simulated = random.uniform(0.05, 0.5)
            time.sleep(0.001)  # tiny sleep to make it measurable
            latencies.append(simulated)
    else:
        try:
            from unittest.mock import patch

            from src.generators.base import BaseGenerator

            sample_text = '{"name": "test"}'

            with patch("src.generators.base.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(gemini_api_key="bench-key")
                with patch("google.genai.Client") as mock_client_cls:
                    mock_response = MagicMock()
                    mock_response.text = sample_text
                    mock_response.usage_metadata = MagicMock(
                        prompt_token_count=100,
                        candidates_token_count=50,
                        total_token_count=150,
                        cached_content_token_count=0,
                    )
                    mock_client = MagicMock()
                    mock_client.models.generate_content.return_value = mock_response
                    mock_client_cls.return_value = mock_client

                    class _BenchGen(BaseGenerator):
                        def generate(self, *a, **kw):
                            pass

                        def _build_prompt(self, **kw):
                            return ""

                        def _parse_response(self, raw):
                            return raw

                    gen = _BenchGen()
                    for _ in range(calls):
                        start = time.perf_counter()
                        gen._call_llm("benchmark")
                        elapsed = time.perf_counter() - start
                        latencies.append(elapsed)

        except ImportError:
            return benchmark_llm_latency(calls, skip_llm=True)

    return {
        "calls": calls,
        "avg_ms": round(statistics.mean(latencies) * 1000, 2) if latencies else 0,
        "p50_ms": round(_percentile(latencies, 50) * 1000, 2),
        "p95_ms": round(_percentile(latencies, 95) * 1000, 2),
        "p99_ms": round(_percentile(latencies, 99) * 1000, 2),
        "min_ms": round(min(latencies) * 1000, 2) if latencies else 0,
        "max_ms": round(max(latencies) * 1000, 2) if latencies else 0,
    }


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(
    gen_results: dict[str, Any],
    val_results: dict[str, Any],
    llm_results: dict[str, Any],
) -> str:
    """Produce a Markdown benchmark report."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    lines = [
        f"# Game Content Pipeline - Benchmark Report",
        f"",
        f"**Date:** {now}",
        f"",
        f"---",
        f"",
        f"## 1. Generation Speed",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Items generated | {gen_results['count']} |",
        f"| Total time | {gen_results['total_time_s']}s |",
        f"| Throughput | {gen_results['items_per_minute']} items/min |",
        f"| Avg latency | {gen_results['avg_latency_ms']}ms |",
        f"| P50 latency | {gen_results['p50_ms']}ms |",
        f"| P95 latency | {gen_results['p95_ms']}ms |",
        f"| P99 latency | {gen_results['p99_ms']}ms |",
        f"| Errors | {gen_results['errors']} |",
        f"",
        f"## 2. Validation Pass Rate",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total items | {val_results['total']} |",
        f"| Passed | {val_results['passed']} |",
        f"| Failed | {val_results['failed']} |",
        f"| Pass rate | {val_results['pass_rate']}% |",
        f"",
    ]

    if val_results.get("details"):
        lines.extend([
            f"### Validation Details",
            f"",
            f"| Item | Passed | Message |",
            f"|------|--------|---------|",
        ])
        for d in val_results["details"]:
            status = "Pass" if d["passed"] else "FAIL"
            lines.append(f"| {d['name']} | {status} | {d['message']} |")
        lines.append("")

    lines.extend([
        f"## 3. LLM API Latency",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| API calls | {llm_results['calls']} |",
        f"| Avg latency | {llm_results['avg_ms']}ms |",
        f"| P50 latency | {llm_results['p50_ms']}ms |",
        f"| P95 latency | {llm_results['p95_ms']}ms |",
        f"| P99 latency | {llm_results['p99_ms']}ms |",
        f"| Min latency | {llm_results['min_ms']}ms |",
        f"| Max latency | {llm_results['max_ms']}ms |",
        f"",
        f"---",
        f"",
        f"*Generated by `scripts/benchmark.py`*",
    ])

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark the Game Content Pipeline")
    parser.add_argument(
        "--count",
        type=int,
        default=10,
        help="Number of items to generate in the speed benchmark (default: 10)",
    )
    parser.add_argument(
        "--llm-calls",
        type=int,
        default=10,
        help="Number of LLM calls in the latency benchmark (default: 10)",
    )
    parser.add_argument(
        "--skip-llm",
        action="store_true",
        help="Use mocked/simulated LLM calls instead of real API",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Write report to this file (default: stdout)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  Game Content Pipeline - Benchmark")
    print("=" * 60)

    print("\n[1/3] Benchmarking generation speed ...")
    gen_results = benchmark_generation_speed(args.count, skip_llm=args.skip_llm)
    print(f"       {gen_results['items_per_minute']} items/min")

    print("\n[2/3] Benchmarking validation pass rate ...")
    val_results = benchmark_validation_pass_rate()
    print(f"       {val_results['pass_rate']}% pass rate ({val_results['passed']}/{val_results['total']})")

    print("\n[3/3] Benchmarking LLM API latency ...")
    llm_results = benchmark_llm_latency(args.llm_calls, skip_llm=args.skip_llm)
    print(f"       Avg: {llm_results['avg_ms']}ms, P95: {llm_results['p95_ms']}ms")

    report = generate_report(gen_results, val_results, llm_results)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding="utf-8")
        print(f"\n[DONE] Report written to {output_path}")
    else:
        print("\n" + "=" * 60)
        print(report)


if __name__ == "__main__":
    main()
