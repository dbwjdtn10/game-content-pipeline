"""Item content generation commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.cli.ui import console, create_progress, print_error, print_generation_result, print_success

app = typer.Typer(name="item", help="아이템 콘텐츠 생성 및 관리")


@app.command("generate")
def generate(
    item_type: Annotated[
        str,
        typer.Option("--type", "-t", help="아이템 유형 (weapon, armor, accessory, consumable)"),
    ] = "weapon",
    rarity: Annotated[
        str,
        typer.Option("--rarity", "-r", help="아이템 희귀도 (common, uncommon, rare, epic, legendary)"),
    ] = "rare",
    count: Annotated[
        int,
        typer.Option("--count", "-c", help="생성할 아이템 수"),
    ] = 5,
    theme: Annotated[
        Optional[str],
        typer.Option("--theme", help="아이템 테마 (예: 화염, 얼음, 암흑)"),
    ] = None,
    level_range: Annotated[
        str,
        typer.Option("--level-range", "-l", help="아이템 레벨 범위 (예: 50-60)"),
    ] = "1-10",
    output: Annotated[
        Optional[Path],
        typer.Option("--output", "-o", help="결과를 저장할 파일 경로"),
    ] = None,
) -> None:
    """아이템을 AI로 생성합니다."""
    try:
        # Parse level range
        parts = level_range.split("-")
        if len(parts) != 2:
            print_error("레벨 범위는 '최소-최대' 형식이어야 합니다 (예: 50-60)")
            raise typer.Exit(code=1)
        min_level, max_level = int(parts[0]), int(parts[1])

        console.print(
            f"\n[bold cyan]아이템 생성 시작[/bold cyan]\n"
            f"  유형: [white]{item_type}[/white]\n"
            f"  희귀도: [white]{rarity}[/white]\n"
            f"  개수: [white]{count}[/white]\n"
            f"  레벨 범위: [white]{min_level}-{max_level}[/white]\n"
            f"  테마: [white]{theme or '없음'}[/white]\n"
        )

        from src.generators import ItemGenerator

        generator = ItemGenerator()

        generated_items: list[dict] = []
        with create_progress() as progress:
            task = progress.add_task("아이템 생성 중...", total=count)
            results = generator.generate(
                type=item_type,
                rarity=rarity,
                count=count,
                theme=theme or "",
                level_range=(min_level, max_level),
            )
            # Handle both list and single-item returns; convert Pydantic models to dicts
            if isinstance(results, list):
                generated_items = [
                    r.model_dump(by_alias=True) if hasattr(r, "model_dump") else r
                    for r in results
                ]
            else:
                generated_items = [results.model_dump(by_alias=True) if hasattr(results, "model_dump") else results]
            progress.update(task, completed=count)

        # Run validation
        validation_results = []
        try:
            from src.validators.balance import BalanceValidator

            balance = BalanceValidator()
            seed_items = generator.load_seed(generator.SEED_FILE)
            for item in generated_items:
                validation_results.append(balance.check_stat_range(item, seed_items))
                validation_results.append(balance.check_rarity_hierarchy(item, seed_items))
        except Exception:
            pass  # Validators are optional; don't block output

        # Display results
        print_generation_result(generated_items, validation_results, title="아이템 생성 결과")

        # Save to file
        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(generated_items, ensure_ascii=False, indent=2), encoding="utf-8")
            print_success(f"결과가 {output}에 저장되었습니다.")

        # Persist via repository
        try:
            from sqlalchemy import create_engine
            from sqlalchemy.orm import Session as SASession
            from src.config import get_settings
            from src.storage.repository import ContentRepository

            eng = create_engine(get_settings().database_url, pool_pre_ping=True)
            with SASession(eng) as session:
                repo = ContentRepository(session)
                for item_data in generated_items:
                    content_id = item_data.get("name", "unknown")
                    repo.create_version("item", content_id, item_data)
                session.commit()
            print_success("결과가 저장소에 저장되었습니다.")
        except Exception:
            pass  # Storage is optional

    except typer.Exit:
        raise
    except Exception as exc:
        print_error(f"아이템 생성 실패: {exc}")
        raise typer.Exit(code=1)
