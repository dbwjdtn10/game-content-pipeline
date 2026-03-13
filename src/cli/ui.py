"""Rich UI utilities for beautiful terminal output."""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table
from rich.text import Text

console = Console()


# ---------------------------------------------------------------------------
# Progress bar factory
# ---------------------------------------------------------------------------

def create_progress() -> Progress:
    """Create a Rich progress bar configured for content generation tasks."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(bar_width=40),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
    )


# ---------------------------------------------------------------------------
# Generation result display
# ---------------------------------------------------------------------------

def print_generation_result(
    items: list[dict[str, Any]],
    validation_results: list[Any] | None = None,
    title: str = "생성 결과",
) -> None:
    """Display generated items in a Rich table with optional validation summary.

    Parameters
    ----------
    items:
        List of generated content dicts. Each dict should contain at least
        ``name`` and may contain ``type``, ``rarity``, ``level``, ``description``.
    validation_results:
        Optional list of ``ValidationResult`` objects.
    title:
        Panel title.
    """
    if not items:
        console.print(Panel("[yellow]생성된 콘텐츠가 없습니다.[/yellow]", title=title))
        return

    # -- Build items table --------------------------------------------------
    table = Table(
        title=title,
        show_header=True,
        header_style="bold cyan",
        border_style="bright_blue",
        show_lines=True,
    )

    # Determine columns from the first item's keys
    sample_keys = list(items[0].keys())
    display_keys = sample_keys[:8]  # cap at 8 columns for readability
    for key in display_keys:
        table.add_column(key, style="white", overflow="fold")

    for item in items:
        row = []
        for key in display_keys:
            value = item.get(key, "")
            if isinstance(value, (list, dict)):
                import json

                value = json.dumps(value, ensure_ascii=False)[:60]
            row.append(str(value))
        table.add_row(*row)

    console.print(table)

    # -- Validation summary -------------------------------------------------
    if validation_results:
        print_validation_report(validation_results)

    # -- Summary ------------------------------------------------------------
    console.print(
        Panel(
            f"[bold green]총 {len(items)}개 항목 생성 완료[/bold green]",
            border_style="green",
        )
    )


# ---------------------------------------------------------------------------
# Validation report display
# ---------------------------------------------------------------------------

def print_validation_report(results: list[Any]) -> None:
    """Display validation results in a styled Rich table.

    Parameters
    ----------
    results:
        List of ``ValidationResult`` objects (or dicts with the same shape).
    """
    if not results:
        console.print("[dim]검증 결과가 없습니다.[/dim]")
        return

    severity_style = {
        "info": "blue",
        "warning": "yellow",
        "error": "red",
    }

    table = Table(
        title="검증 결과",
        show_header=True,
        header_style="bold magenta",
        border_style="bright_magenta",
        show_lines=True,
    )
    table.add_column("상태", justify="center", width=6)
    table.add_column("검증 항목", style="white")
    table.add_column("심각도", justify="center")
    table.add_column("메시지", style="white", overflow="fold")

    passed_count = 0
    failed_count = 0

    for r in results:
        # Support both dict and object access
        if isinstance(r, dict):
            passed = r.get("passed", True)
            check = r.get("check_name", "unknown")
            severity = r.get("severity", "info")
            message = r.get("message", "")
        else:
            passed = r.passed
            check = r.check_name
            severity = r.severity
            message = r.message

        if passed:
            passed_count += 1
            status = Text("PASS", style="bold green")
        else:
            failed_count += 1
            status = Text("FAIL", style="bold red")

        sev_color = severity_style.get(severity, "white")
        table.add_row(
            status,
            check,
            Text(severity, style=f"bold {sev_color}"),
            message,
        )

    console.print(table)
    summary_parts = [
        f"[green]통과: {passed_count}[/green]",
        f"[red]실패: {failed_count}[/red]",
    ]
    console.print(Panel(" | ".join(summary_parts), title="검증 요약", border_style="cyan"))


# ---------------------------------------------------------------------------
# Pipeline status display
# ---------------------------------------------------------------------------

def print_pipeline_status(pipeline_status: dict[str, Any]) -> None:
    """Display pipeline execution status.

    Parameters
    ----------
    pipeline_status:
        Dict with keys like ``stage``, ``progress``, ``completed``, ``errors``.
    """
    table = Table(
        title="파이프라인 상태",
        show_header=True,
        header_style="bold cyan",
        border_style="bright_blue",
    )
    table.add_column("단계", style="white")
    table.add_column("상태", justify="center")
    table.add_column("상세", style="dim", overflow="fold")

    stages = pipeline_status.get("stages", [])
    if not stages and isinstance(pipeline_status, dict):
        # flat dict fallback
        for key, value in pipeline_status.items():
            status_text = Text("완료", style="bold green") if value else Text("대기", style="dim")
            table.add_row(key, status_text, str(value))
    else:
        for stage in stages:
            name = stage.get("name", "unknown")
            status = stage.get("status", "pending")
            detail = stage.get("detail", "")

            if status == "completed":
                status_text = Text("완료", style="bold green")
            elif status == "running":
                status_text = Text("실행 중", style="bold yellow")
            elif status == "failed":
                status_text = Text("실패", style="bold red")
            else:
                status_text = Text("대기", style="dim")

            table.add_row(name, status_text, detail)

    console.print(table)

    errors = pipeline_status.get("errors", [])
    if errors:
        console.print(
            Panel(
                "\n".join(f"[red]- {e}[/red]" for e in errors),
                title="오류 목록",
                border_style="red",
            )
        )


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def print_error(message: str) -> None:
    """Print a styled error message."""
    console.print(f"[bold red]오류:[/bold red] {message}")


def print_success(message: str) -> None:
    """Print a styled success message."""
    console.print(f"[bold green]성공:[/bold green] {message}")


def print_info(message: str) -> None:
    """Print a styled info message."""
    console.print(f"[bold blue]정보:[/bold blue] {message}")


def print_warning(message: str) -> None:
    """Print a styled warning message."""
    console.print(f"[bold yellow]경고:[/bold yellow] {message}")
