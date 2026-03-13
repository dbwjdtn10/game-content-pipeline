"""Main CLI application for the Game Content Pipeline.

Entry point registered as ``gcpipe`` in pyproject.toml.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.panel import Panel

from src.cli.commands import export as export_cmd
from src.cli.commands import item as item_cmd
from src.cli.commands import monster as monster_cmd
from src.cli.commands import patch as patch_cmd
from src.cli.commands import quest as quest_cmd
from src.cli.commands import validate as validate_cmd
from src.cli.ui import (
    console,
    create_progress,
    print_error,
    print_info,
    print_pipeline_status,
    print_success,
)

# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="gcpipe",
    help="AI 기반 게임 콘텐츠 생성 파이프라인 CLI",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

# ---------------------------------------------------------------------------
# Register sub-command groups
# ---------------------------------------------------------------------------

app.add_typer(item_cmd.app, name="item", help="아이템 콘텐츠 생성 및 관리")
app.add_typer(monster_cmd.app, name="monster", help="몬스터 콘텐츠 생성 및 밸런싱")
app.add_typer(quest_cmd.app, name="quest", help="퀘스트 콘텐츠 생성 및 관리")
app.add_typer(patch_cmd.app, name="patch", help="패치 노트 생성")
app.add_typer(validate_cmd.app, name="validate", help="콘텐츠 검증")
app.add_typer(export_cmd.app, name="export", help="콘텐츠 내보내기")

# ---------------------------------------------------------------------------
# Pipeline command group
# ---------------------------------------------------------------------------

pipeline_app = typer.Typer(name="pipeline", help="파이프라인 실행 및 관리")
app.add_typer(pipeline_app, name="pipeline", help="파이프라인 실행 및 관리")


@pipeline_app.command("run")
def pipeline_run(
    config: Annotated[
        Optional[Path],
        typer.Option("--config", "-c", help="파이프라인 설정 파일 경로 (JSON)"),
    ] = None,
    content_type: Annotated[
        str,
        typer.Option("--type", "-t", help="생성할 콘텐츠 유형 (item, monster, quest, all)"),
    ] = "all",
    count: Annotated[
        int,
        typer.Option("--count", "-n", help="유형별 생성 수"),
    ] = 10,
    validate_flag: Annotated[
        bool,
        typer.Option("--validate/--no-validate", help="생성 후 검증 실행 여부"),
    ] = True,
    export_format: Annotated[
        Optional[str],
        typer.Option("--export", "-e", help="내보내기 형식 (json, csv, markdown)"),
    ] = None,
    output: Annotated[
        Optional[Path],
        typer.Option("--output", "-o", help="결과 출력 디렉터리"),
    ] = None,
) -> None:
    """전체 파이프라인을 실행합니다 (생성 -> 검증 -> 내보내기)."""
    try:
        console.print(
            Panel(
                f"[bold]콘텐츠 유형:[/bold] {content_type}\n"
                f"[bold]생성 수:[/bold] {count}\n"
                f"[bold]검증:[/bold] {'예' if validate_flag else '아니오'}\n"
                f"[bold]내보내기:[/bold] {export_format or '없음'}",
                title="[bold cyan]파이프라인 실행[/bold cyan]",
                border_style="cyan",
            )
        )

        # Load pipeline config if provided
        pipeline_config: dict = {}
        if config and config.exists():
            pipeline_config = json.loads(config.read_text(encoding="utf-8"))

        from src.pipeline.orchestrator import PipelineOrchestrator

        # Build YAML config from CLI parameters if no config file was provided
        if pipeline_config:
            import yaml
            yaml_str = yaml.dump(pipeline_config, allow_unicode=True)
        else:
            # Build a pipeline YAML from CLI arguments
            steps = []
            types_to_run = [content_type] if content_type != "all" else ["item", "monster", "quest"]

            for ct in types_to_run:
                steps.append({
                    "name": f"generate_{ct}s",
                    "generator": "generate",
                    "params": {"content_type": ct, "count": count},
                })
                if validate_flag:
                    steps.append({
                        "name": f"validate_{ct}s",
                        "generator": "validate",
                        "params": {"content_type": ct},
                        "depends_on": [f"generate_{ct}s"],
                    })
                if export_format:
                    dep = f"validate_{ct}s" if validate_flag else f"generate_{ct}s"
                    out_path = str(output / f"{ct}s.{export_format}") if output else None
                    step = {
                        "name": f"export_{ct}s",
                        "generator": "export",
                        "params": {"export_format": export_format},
                        "depends_on": [dep],
                    }
                    if out_path:
                        step["params"]["output_path"] = out_path
                    steps.append(step)

            import yaml
            yaml_str = yaml.dump(
                {"name": "cli_pipeline", "steps": steps},
                allow_unicode=True,
            )

        orchestrator = PipelineOrchestrator()

        with create_progress() as progress:
            task = progress.add_task("파이프라인 실행 중...", total=1)
            result = orchestrator.run(yaml_str)
            progress.update(task, completed=1)

        # Display result
        result_dict = result.to_dict()
        print_pipeline_status(result_dict)

        if result.all_passed:
            print_success("파이프라인 실행 완료")
        else:
            print_error(f"파이프라인 실패: {len(result.failed_steps)}개 단계 실패")

    except typer.Exit:
        raise
    except Exception as exc:
        print_error(f"파이프라인 실행 실패: {exc}")
        raise typer.Exit(code=1)


@pipeline_app.command("status")
def pipeline_status() -> None:
    """현재 파이프라인 상태를 조회합니다."""
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session as SASession
        from src.config import get_settings
        from src.storage.repository import PipelineRepository

        eng = create_engine(get_settings().database_url, pool_pre_ping=True)
        with SASession(eng) as session:
            repo = PipelineRepository(session)
            runs = repo.list_runs(limit=10)
            if not runs:
                print_info("파이프라인 실행 기록이 없습니다.")
                return
            status_data = {
                "stages": [
                    {
                        "name": f"{run.name} ({run.id})",
                        "status": run.status,
                        "detail": str(run.started_at or ""),
                    }
                    for run in runs
                ]
            }
            print_pipeline_status(status_data)
    except Exception as exc:
        print_error(f"상태 조회 실패: {exc}")
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# Content command group (query/manage stored content)
# ---------------------------------------------------------------------------

content_app = typer.Typer(name="content", help="저장된 콘텐츠 조회 및 관리")
app.add_typer(content_app, name="content", help="저장된 콘텐츠 조회 및 관리")


@content_app.command("list")
def content_list(
    content_type: Annotated[
        Optional[str],
        typer.Option("--type", "-t", help="콘텐츠 유형 필터 (item, monster, quest)"),
    ] = None,
    limit: Annotated[
        int,
        typer.Option("--limit", "-n", help="표시할 최대 개수"),
    ] = 20,
    output: Annotated[
        Optional[Path],
        typer.Option("--output", "-o", help="결과를 저장할 파일 경로"),
    ] = None,
) -> None:
    """저장된 콘텐츠 목록을 조회합니다."""
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session as SASession
        from src.config import get_settings
        from src.storage.repository import ContentRepository

        eng = create_engine(get_settings().database_url, pool_pre_ping=True)
        with SASession(eng) as session:
            repo = ContentRepository(session)
            items_raw = repo.list_all(content_type=content_type, limit=limit)
            # Convert ORM objects to dicts while session is open
            items = [
                {
                    "id": cv.id,
                    "content_type": cv.content_type,
                    "content_id": cv.content_id,
                    "version": cv.version,
                    "status": cv.status,
                    "data": cv.data,
                }
                for cv in items_raw
            ]

        if not items:
            print_info("저장된 콘텐츠가 없습니다.")
            return

        from src.cli.ui import print_generation_result

        print_generation_result(items, title=f"저장된 콘텐츠 ({content_type or '전체'})")

        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(
                json.dumps(items, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            print_success(f"결과가 {output}에 저장되었습니다.")

    except Exception as exc:
        print_error(f"콘텐츠 조회 실패: {exc}")
        raise typer.Exit(code=1)


@content_app.command("delete")
def content_delete(
    content_id: Annotated[
        str,
        typer.Argument(help="삭제할 콘텐츠 ID"),
    ],
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="확인 없이 삭제"),
    ] = False,
) -> None:
    """저장된 콘텐츠를 삭제합니다."""
    try:
        if not force:
            confirm = typer.confirm(f"콘텐츠 '{content_id}'를 삭제하시겠습니까?")
            if not confirm:
                print_info("삭제가 취소되었습니다.")
                raise typer.Exit()

        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session as SASession
        from src.config import get_settings
        from src.storage.repository import ContentRepository

        eng = create_engine(get_settings().database_url, pool_pre_ping=True)
        with SASession(eng) as session:
            repo = ContentRepository(session)
            cv = repo.get_by_id(content_id)
            if cv is None:
                print_error(f"콘텐츠 '{content_id}'를 찾을 수 없습니다.")
                raise typer.Exit(code=1)
            session.delete(cv)
            session.commit()
        print_success(f"콘텐츠 '{content_id}'가 삭제되었습니다.")

    except typer.Exit:
        raise
    except Exception as exc:
        print_error(f"콘텐츠 삭제 실패: {exc}")
        raise typer.Exit(code=1)


@content_app.command("inspect")
def content_inspect(
    content_id: Annotated[
        str,
        typer.Argument(help="조회할 콘텐츠 ID"),
    ],
) -> None:
    """저장된 콘텐츠 상세 정보를 조회합니다."""
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session as SASession
        from src.config import get_settings
        from src.storage.repository import ContentRepository

        eng = create_engine(get_settings().database_url, pool_pre_ping=True)
        with SASession(eng) as session:
            repo = ContentRepository(session)
            cv = repo.get_by_id(content_id)

            if cv is None:
                print_error(f"콘텐츠 '{content_id}'를 찾을 수 없습니다.")
                raise typer.Exit(code=1)

            item = {
                "id": cv.id,
                "content_type": cv.content_type,
                "content_id": cv.content_id,
                "version": cv.version,
                "status": cv.status,
                "data": cv.data,
                "validation_result": cv.validation_result,
                "created_at": str(cv.created_at),
                "reviewed_by": cv.reviewed_by,
                "review_comment": cv.review_comment,
            }

        from rich.syntax import Syntax

        formatted = json.dumps(item, ensure_ascii=False, indent=2)
        syntax = Syntax(formatted, "json", theme="monokai", line_numbers=True)
        console.print(Panel(syntax, title=f"콘텐츠 상세: {content_id}", border_style="cyan"))

    except typer.Exit:
        raise
    except Exception as exc:
        print_error(f"콘텐츠 조회 실패: {exc}")
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# Version callback
# ---------------------------------------------------------------------------

def _version_callback(value: bool) -> None:
    if value:
        console.print("[bold cyan]gcpipe[/bold cyan] v0.1.0")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        Optional[bool],
        typer.Option("--version", "-v", help="버전 정보 표시", callback=_version_callback, is_eager=True),
    ] = None,
) -> None:
    """AI 기반 게임 콘텐츠 생성 파이프라인 CLI."""


if __name__ == "__main__":
    app()
