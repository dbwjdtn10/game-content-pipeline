"""Quest content generation commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.cli.ui import console, create_progress, print_error, print_generation_result, print_success

app = typer.Typer(name="quest", help="퀘스트 콘텐츠 생성 및 관리")


@app.command("generate")
def generate(
    quest_type: Annotated[
        str,
        typer.Option("--type", "-t", help="퀘스트 유형 (main, side, daily, event)"),
    ] = "side",
    region: Annotated[
        Optional[str],
        typer.Option("--region", "-r", help="퀘스트 지역 (예: 화산 지대)"),
    ] = None,
    npc: Annotated[
        Optional[str],
        typer.Option("--npc", help="퀘스트 NPC 이름 (예: 대장장이 가론)"),
    ] = None,
    count: Annotated[
        int,
        typer.Option("--count", "-c", help="생성할 퀘스트 수"),
    ] = 3,
    min_steps: Annotated[
        int,
        typer.Option("--min-steps", help="퀘스트 최소 단계 수"),
    ] = 3,
    max_steps: Annotated[
        int,
        typer.Option("--max-steps", help="퀘스트 최대 단계 수"),
    ] = 7,
    output: Annotated[
        Optional[Path],
        typer.Option("--output", "-o", help="결과를 저장할 파일 경로"),
    ] = None,
) -> None:
    """퀘스트를 AI로 생성합니다."""
    try:
        if min_steps > max_steps:
            print_error("최소 단계 수가 최대 단계 수보다 클 수 없습니다.")
            raise typer.Exit(code=1)

        console.print(
            f"\n[bold cyan]퀘스트 생성 시작[/bold cyan]\n"
            f"  유형: [white]{quest_type}[/white]\n"
            f"  지역: [white]{region or '없음'}[/white]\n"
            f"  NPC: [white]{npc or '없음'}[/white]\n"
            f"  개수: [white]{count}[/white]\n"
            f"  단계 범위: [white]{min_steps}-{max_steps}[/white]\n"
        )

        from src.generators import QuestGenerator

        generator = QuestGenerator()

        generated_quests: list[dict] = []
        with create_progress() as progress:
            task = progress.add_task("퀘스트 생성 중...", total=count)
            results = generator.generate(
                type=quest_type,
                region=region or "",
                npc=npc or "",
                count=count,
                min_steps=min_steps,
                max_steps=max_steps,
            )
            generated_quests = [
                r.model_dump(by_alias=True) if hasattr(r, "model_dump") else r
                for r in (results if isinstance(results, list) else [results])
            ]
            progress.update(task, completed=count)

        # Run validation (optional consistency checks)
        validation_results = []
        try:
            from src.validators.duplicate import DuplicateValidator

            dup = DuplicateValidator()
            existing_names = [q.get("name", "") for q in generated_quests]
            for q in generated_quests:
                validation_results.append(
                    dup.check_name_similarity(q.get("name", ""), existing_names)
                )
        except Exception:
            pass

        print_generation_result(generated_quests, validation_results, title="퀘스트 생성 결과")

        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(
                json.dumps(generated_quests, ensure_ascii=False, indent=2),
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
                for q_data in generated_quests:
                    content_id = q_data.get("name", "unknown")
                    repo.create_version("quest", content_id, q_data)
                session.commit()
            print_success("결과가 저장소에 저장되었습니다.")
        except Exception:
            pass

    except typer.Exit:
        raise
    except Exception as exc:
        print_error(f"퀘스트 생성 실패: {exc}")
        raise typer.Exit(code=1)
