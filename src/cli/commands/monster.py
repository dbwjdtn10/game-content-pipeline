"""Monster content generation and balancing commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.cli.ui import (
    console,
    create_progress,
    print_error,
    print_generation_result,
    print_success,
)

app = typer.Typer(name="monster", help="몬스터 콘텐츠 생성 및 밸런싱")


@app.command("generate")
def generate(
    region: Annotated[
        str,
        typer.Option("--region", "-r", help="몬스터 출현 지역 (예: 화산 지대)"),
    ] = "평원",
    count: Annotated[
        int,
        typer.Option("--count", "-c", help="생성할 몬스터 수"),
    ] = 10,
    level_range: Annotated[
        str,
        typer.Option("--level-range", "-l", help="몬스터 레벨 범위 (예: 50-60)"),
    ] = "1-10",
    difficulty: Annotated[
        str,
        typer.Option("--difficulty", "-d", help="난이도 (normal, elite, boss)"),
    ] = "normal",
    output: Annotated[
        Optional[Path],
        typer.Option("--output", "-o", help="결과를 저장할 파일 경로"),
    ] = None,
) -> None:
    """몬스터를 AI로 생성합니다."""
    try:
        parts = level_range.split("-")
        if len(parts) != 2:
            print_error("레벨 범위는 '최소-최대' 형식이어야 합니다 (예: 50-60)")
            raise typer.Exit(code=1)
        min_level, max_level = int(parts[0]), int(parts[1])

        console.print(
            f"\n[bold cyan]몬스터 생성 시작[/bold cyan]\n"
            f"  지역: [white]{region}[/white]\n"
            f"  개수: [white]{count}[/white]\n"
            f"  레벨 범위: [white]{min_level}-{max_level}[/white]\n"
            f"  난이도: [white]{difficulty}[/white]\n"
        )

        from src.generators import MonsterGenerator

        generator = MonsterGenerator()

        generated_monsters: list[dict] = []
        with create_progress() as progress:
            task = progress.add_task("몬스터 생성 중...", total=count)
            results = generator.generate(
                region=region,
                count=count,
                level_range=(min_level, max_level),
                difficulty=difficulty,
            )
            generated_monsters = [
                r.model_dump(by_alias=True) if hasattr(r, "model_dump") else r
                for r in (results if isinstance(results, list) else [results])
            ]
            progress.update(task, completed=count)

        # Run validation (balance checks against seed data)
        validation_results = []
        try:
            from src.validators.balance import BalanceValidator

            balance = BalanceValidator()
            seed_items = generator.load_seed(generator.SEED_FILE)
            for m in generated_monsters:
                validation_results.append(balance.check_stat_range(m, seed_items))
        except Exception:
            pass

        print_generation_result(generated_monsters, validation_results, title="몬스터 생성 결과")

        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(
                json.dumps(generated_monsters, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print_success(f"결과가 {output}에 저장되었습니다.")

        try:
            from sqlalchemy import create_engine
            from sqlalchemy.orm import Session as SASession
            from src.config import get_settings
            from src.storage.repository import ContentRepository

            eng = create_engine(get_settings().database_url, pool_pre_ping=True)
            with SASession(eng) as session:
                repo = ContentRepository(session)
                for m_data in generated_monsters:
                    content_id = m_data.get("name", "unknown")
                    repo.create_version("monster", content_id, m_data)
                session.commit()
            print_success("결과가 저장소에 저장되었습니다.")
        except Exception:
            pass

    except typer.Exit:
        raise
    except Exception as exc:
        print_error(f"몬스터 생성 실패: {exc}")
        raise typer.Exit(code=1)


@app.command("balance")
def balance(
    source: Annotated[
        Path,
        typer.Option("--source", "-s", help="밸런싱할 몬스터 데이터 파일 경로"),
    ],
    target_level: Annotated[
        int,
        typer.Option("--target-level", "-t", help="목표 레벨"),
    ] = 50,
    difficulty: Annotated[
        str,
        typer.Option("--difficulty", "-d", help="목표 난이도 (normal, elite, boss)"),
    ] = "normal",
    output: Annotated[
        Optional[Path],
        typer.Option("--output", "-o", help="밸런스 리포트 저장 경로"),
    ] = None,
) -> None:
    """몬스터 밸런스를 분석하고 조정합니다."""
    try:
        if not source.exists():
            print_error(f"파일을 찾을 수 없습니다: {source}")
            raise typer.Exit(code=1)

        console.print(
            f"\n[bold cyan]몬스터 밸런스 분석[/bold cyan]\n"
            f"  소스: [white]{source}[/white]\n"
            f"  목표 레벨: [white]{target_level}[/white]\n"
            f"  난이도: [white]{difficulty}[/white]\n"
        )

        monsters = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(monsters, list):
            monsters = [monsters]

        from src.generators import MonsterGenerator

        gen = MonsterGenerator()

        with create_progress() as progress:
            task = progress.add_task("밸런스 분석 중...", total=len(monsters))
            results = gen.balance(
                str(source),
                target_level=target_level,
                difficulty=difficulty,
            )
            progress.update(task, completed=len(monsters))

        # Display balance suggestions
        from rich.table import Table
        table = Table(title="밸런스 분석 결과", show_lines=True)
        table.add_column("몬스터", style="cyan")
        table.add_column("필드", style="white")
        table.add_column("현재값", style="yellow")
        table.add_column("제안값", style="green")
        table.add_column("사유", style="dim")
        for s in results:
            table.add_row(s.monster_name, s.field, str(s.current_value), str(s.suggested_value), s.reason)
        console.print(table)

        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            report_data = [s.model_dump() for s in results]
            if str(output).endswith(".md"):
                lines = [f"# 몬스터 밸런스 리포트\n"]
                lines.append(f"- 소스: {source}")
                lines.append(f"- 목표 레벨: {target_level}")
                lines.append(f"- 난이도: {difficulty}\n")
                for r in report_data:
                    lines.append(f"## {r.get('monster_name', 'unknown')}")
                    lines.append(f"- 필드: {r.get('field', '')}")
                    lines.append(f"- 현재값: {r.get('current_value', '')}")
                    lines.append(f"- 제안값: {r.get('suggested_value', '')}")
                    lines.append(f"- 사유: {r.get('reason', '')}\n")
                output.write_text("\n".join(lines), encoding="utf-8")
            else:
                output.write_text(
                    json.dumps(report_data, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            print_success(f"리포트가 {output}에 저장되었습니다.")

    except typer.Exit:
        raise
    except Exception as exc:
        print_error(f"밸런스 분석 실패: {exc}")
        raise typer.Exit(code=1)
