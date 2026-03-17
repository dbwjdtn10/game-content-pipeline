"""Content validation commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from src.cli.ui import (
    console,
    create_progress,
    print_error,
    print_success,
    print_validation_report,
    print_warning,
)

app = typer.Typer(name="validate", help="콘텐츠 검증")


VALIDATOR_MAP = {
    "consistency": "ConsistencyValidator",
    "balance": "BalanceValidator",
    "duplicate": "DuplicateValidator",
    "schema": "SchemaValidator",
}


@app.callback(invoke_without_command=True)
def validate(
    target: Annotated[
        Path,
        typer.Option("--target", "-t", help="검증할 콘텐츠 JSON 파일 경로"),
    ],
    check: Annotated[
        str,
        typer.Option("--check", "-c", help="실행할 검증 (쉼표 구분: consistency,balance,duplicate,schema)"),
    ] = "consistency,balance,duplicate",
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="검증 결과를 저장할 파일 경로"),
    ] = None,
) -> None:
    """콘텐츠 파일에 대해 검증을 실행합니다."""
    try:
        if not target.exists():
            print_error(f"파일을 찾을 수 없습니다: {target}")
            raise typer.Exit(code=1)

        check_names = [c.strip() for c in check.split(",")]
        invalid_checks = [c for c in check_names if c not in VALIDATOR_MAP]
        if invalid_checks:
            print_warning(
                f"알 수 없는 검증 항목: {', '.join(invalid_checks)}. "
                f"사용 가능: {', '.join(VALIDATOR_MAP.keys())}"
            )
            check_names = [c for c in check_names if c in VALIDATOR_MAP]

        if not check_names:
            print_error("유효한 검증 항목이 없습니다.")
            raise typer.Exit(code=1)

        console.print(
            f"\n[bold cyan]콘텐츠 검증 시작[/bold cyan]\n"
            f"  대상: [white]{target}[/white]\n"
            f"  검증 항목: [white]{', '.join(check_names)}[/white]\n"
        )

        data = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            data = [data]

        from src.validators.balance import BalanceValidator
        from src.validators.consistency import ConsistencyValidator
        from src.validators.duplicate import DuplicateValidator
        from src.validators.schema_check import SchemaValidator

        validator_instances = {
            "balance": BalanceValidator(),
            "consistency": ConsistencyValidator(),
            "duplicate": DuplicateValidator(),
            "schema": SchemaValidator(),
        }

        all_results = []

        with create_progress() as progress:
            task = progress.add_task("검증 실행 중...", total=len(check_names))
            for check_name in check_names:
                validator = validator_instances.get(check_name)
                if validator is None:
                    progress.advance(task)
                    continue

                if check_name == "balance":
                    # Balance checks: compare each item against the full set
                    for item in data:
                        all_results.append(validator.check_stat_range(item, data))
                        all_results.append(validator.check_rarity_hierarchy(item, data))
                        all_results.append(validator.check_level_curve(item, data))
                elif check_name == "duplicate":
                    # Duplicate checks: compare names and descriptions
                    names = [d.get("name", "") for d in data]
                    descriptions = [d.get("description", "") for d in data]
                    for item in data:
                        all_results.append(
                            validator.check_name_similarity(item.get("name", ""), names)
                        )
                        all_results.append(
                            validator.check_description_similarity(
                                item.get("description", ""), descriptions
                            )
                        )
                elif check_name == "consistency":
                    # Consistency checks require world setting and existing names
                    from src.generators.base import BaseGenerator
                    world_setting = BaseGenerator.load_world_setting()
                    names = [d.get("name", "") for d in data]
                    for item in data:
                        content_str = json.dumps(item, ensure_ascii=False)
                        all_results.append(validator.check_tone(content_str, world_setting))
                        all_results.append(validator.check_naming(item.get("name", ""), names))
                elif check_name == "schema":
                    # Schema validation requires a schema file path
                    # Try to detect content type from data
                    from src.validators.models import ValidationResult
                    all_results.append(ValidationResult(
                        passed=True,
                        check_name="schema_validation",
                        severity="info",
                        message="Schema validation skipped: no schema path specified via CLI.",
                    ))
                progress.advance(task)

        print_validation_report(all_results)

        # Summary counts
        passed = sum(1 for r in all_results if (r.passed if hasattr(r, "passed") else r.get("passed", True)))
        failed = len(all_results) - passed

        if failed > 0:
            print_warning(f"총 {len(all_results)}개 검증 중 {failed}개 실패")
        else:
            print_success(f"총 {len(all_results)}개 검증 모두 통과")

        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            report_data = [
                r.model_dump() if hasattr(r, "model_dump") else r
                for r in all_results
            ]
            output.write_text(
                json.dumps(report_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print_success(f"검증 결과가 {output}에 저장되었습니다.")

    except typer.Exit:
        raise
    except Exception as exc:
        print_error(f"검증 실패: {exc}")
        raise typer.Exit(code=1)
