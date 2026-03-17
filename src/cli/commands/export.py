"""Content export commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from src.cli.ui import console, create_progress, print_error, print_info, print_success

app = typer.Typer(name="export", help="콘텐츠 내보내기")

SUPPORTED_FORMATS = ("json", "csv", "markdown")


@app.callback(invoke_without_command=True)
def export(
    source: Annotated[
        Path,
        typer.Option("--source", "-s", help="내보낼 콘텐츠 JSON 파일 경로"),
    ],
    export_format: Annotated[
        str,
        typer.Option("--format", "-f", help="출력 형식 (json, csv, markdown)"),
    ] = "json",
    template: Annotated[
        Path | None,
        typer.Option("--template", "-t", help="Jinja2 템플릿 파일 경로 (markdown 형식에서 사용)"),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="출력 디렉터리 또는 파일 경로"),
    ] = None,
) -> None:
    """콘텐츠를 다양한 형식으로 내보냅니다."""
    try:
        if not source.exists():
            print_error(f"파일을 찾을 수 없습니다: {source}")
            raise typer.Exit(code=1)

        if export_format not in SUPPORTED_FORMATS:
            print_error(
                f"지원하지 않는 형식: {export_format}. "
                f"사용 가능: {', '.join(SUPPORTED_FORMATS)}"
            )
            raise typer.Exit(code=1)

        console.print(
            f"\n[bold cyan]콘텐츠 내보내기[/bold cyan]\n"
            f"  소스: [white]{source}[/white]\n"
            f"  형식: [white]{export_format}[/white]\n"
            f"  템플릿: [white]{template or '없음'}[/white]\n"
            f"  출력: [white]{output or '자동'}[/white]\n"
        )

        data = json.loads(source.read_text(encoding="utf-8"))

        # Determine output path
        if output is None:
            ext_map = {"json": ".json", "csv": ".csv", "markdown": ".md"}
            ext = ext_map.get(export_format, ".json")
            output = source.with_suffix(ext)
            if export_format == "json" and output == source:
                output = source.with_name(f"{source.stem}_exported{ext}")

        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with create_progress() as progress:
            task = progress.add_task("내보내기 중...", total=1)

            if export_format == "json":
                from src.export import JsonExporter

                exporter = JsonExporter()
                exporter.export(data, output_path)

            elif export_format == "csv":
                from src.export import CsvExporter

                exporter = CsvExporter()
                exporter.export(data, output_path)

            elif export_format == "markdown":
                from src.export import MarkdownExporter

                if template and template.exists():
                    # Use the template's parent dir as template_dir and its name as template_name
                    exporter = MarkdownExporter(template_dir=template.parent)
                    exporter.export(data, template.name, output_path)
                else:
                    if template:
                        from src.cli.ui import print_warning

                        print_warning(f"템플릿 파일을 찾을 수 없습니다: {template}. 기본 형식을 사용합니다.")
                    exporter = MarkdownExporter()
                    exporter.export(data, "default.md.j2", output_path)

            progress.update(task, completed=1)

        # Print summary
        record_count = len(data) if isinstance(data, list) else 1
        print_info(f"총 {record_count}개 레코드 내보내기 완료")
        print_success(f"결과가 {output_path}에 저장되었습니다.")

    except typer.Exit:
        raise
    except Exception as exc:
        print_error(f"내보내기 실패: {exc}")
        raise typer.Exit(code=1)
