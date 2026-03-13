"""Patch note generation commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.cli.ui import console, create_progress, print_error, print_generation_result, print_success

app = typer.Typer(name="patch", help="패치 노트 생성")


@app.command("generate")
def generate(
    changes: Annotated[
        Path,
        typer.Option("--changes", "-c", help="변경 사항 JSON 파일 경로"),
    ],
    tone: Annotated[
        str,
        typer.Option("--tone", "-t", help="패치 노트 톤 (formal, casual, hype)"),
    ] = "formal",
    patch_format: Annotated[
        str,
        typer.Option("--format", "-f", help="출력 형식 (markdown, html, text)"),
    ] = "markdown",
    output: Annotated[
        Optional[Path],
        typer.Option("--output", "-o", help="결과를 저장할 파일 경로"),
    ] = None,
) -> None:
    """변경 사항을 기반으로 패치 노트를 AI로 생성합니다."""
    try:
        if not changes.exists():
            print_error(f"파일을 찾을 수 없습니다: {changes}")
            raise typer.Exit(code=1)

        console.print(
            f"\n[bold cyan]패치 노트 생성 시작[/bold cyan]\n"
            f"  변경 사항: [white]{changes}[/white]\n"
            f"  톤: [white]{tone}[/white]\n"
            f"  형식: [white]{patch_format}[/white]\n"
        )

        from src.generators import PatchGenerator

        generator = PatchGenerator()

        with create_progress() as progress:
            task = progress.add_task("패치 노트 생성 중...", total=1)
            result = generator.generate(
                changes_file=str(changes),
                tone=tone,
            )
            progress.update(task, completed=1)

        # Display result (PatchNote Pydantic model)
        result_dict = result.model_dump()
        generated_items = [result_dict]
        print_generation_result(generated_items, title="패치 노트 생성 결과")

        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(
                json.dumps(result_dict, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print_success(f"패치 노트가 {output}에 저장되었습니다.")

        print_success("패치 노트 생성 완료")

    except typer.Exit:
        raise
    except Exception as exc:
        print_error(f"패치 노트 생성 실패: {exc}")
        raise typer.Exit(code=1)
