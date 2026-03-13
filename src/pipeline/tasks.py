"""Celery tasks for asynchronous content generation, validation, and export."""

from __future__ import annotations

import json
import traceback
from typing import Any

from celery import Celery

from src.config import get_settings

settings = get_settings()

celery_app = Celery(
    "game_content",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)


@celery_app.task(bind=True, name="pipeline.generate_content", max_retries=3)
def generate_content_task(
    self: Any,
    content_type: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate game content using the appropriate generator.

    Parameters
    ----------
    content_type:
        One of ``item``, ``monster``, ``quest``, ``skill``.
    params:
        Extra keyword arguments forwarded to the generator.

    Returns
    -------
    dict
        Generated content data or an error envelope.
    """
    params = params or {}
    try:
        # Lazy import to avoid import-time side-effects in workers
        from src.generators import (
            ItemGenerator,
            MonsterGenerator,
            QuestGenerator,
            SkillGenerator,
        )

        generator_map: dict[str, type] = {
            "item": ItemGenerator,
            "monster": MonsterGenerator,
            "quest": QuestGenerator,
            "skill": SkillGenerator,
        }

        generator_cls = generator_map.get(content_type)
        if generator_cls is None:
            return {
                "status": "error",
                "error": f"Unknown content type: {content_type}",
            }

        generator = generator_cls()
        result = generator.generate(**params)

        # Convert result to JSON-serializable form
        if hasattr(result, "model_dump"):
            result = result.model_dump(mode="json")
        elif isinstance(result, list):
            result = [
                item.model_dump(mode="json") if hasattr(item, "model_dump") else item
                for item in result
            ]
        elif not isinstance(result, dict):
            result = json.loads(json.dumps(result, default=str))

        return {"status": "success", "content_type": content_type, "data": result}

    except Exception as exc:
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)


@celery_app.task(bind=True, name="pipeline.validate_content", max_retries=2)
def validate_content_task(
    self: Any,
    content_type: str,
    data: dict[str, Any],
    validators: list[str] | None = None,
) -> dict[str, Any]:
    """Validate generated content through the validator chain.

    Parameters
    ----------
    content_type:
        Content type identifier.
    data:
        The generated content dictionary.
    validators:
        Optional list of validator names to apply.  When *None* all
        registered validators run.

    Returns
    -------
    dict
        Validation results with per-check details.
    """
    try:
        from src.validators import (
            BalanceValidator,
            ConsistencyValidator,
            DuplicateValidator,
            SchemaValidator,
        )

        available_validators: dict[str, type] = {
            "schema": SchemaValidator,
            "balance": BalanceValidator,
            "consistency": ConsistencyValidator,
            "duplicate": DuplicateValidator,
        }

        to_run = validators or list(available_validators.keys())
        results: list[dict[str, Any]] = []
        all_passed = True

        # Wrap data as list for consistent processing
        items = data if isinstance(data, list) else [data]

        for name in to_run:
            validator_cls = available_validators.get(name)
            if validator_cls is None:
                results.append(
                    {
                        "check_name": name,
                        "passed": False,
                        "severity": "error",
                        "message": f"Unknown validator: {name}",
                    }
                )
                all_passed = False
                continue

            validator = validator_cls()
            check_results: list = []

            if name == "schema":
                # SchemaValidator requires a schema path; use convention-based path
                from pathlib import Path
                schema_path = Path(__file__).resolve().parents[2] / "game_data" / "schema" / f"{content_type}_schema.json"
                if schema_path.exists():
                    r = validator.validate(data, schema_path)
                    check_results = [r]
                else:
                    from src.validators.models import ValidationResult
                    check_results = [ValidationResult(
                        passed=True,
                        check_name="schema_validation",
                        severity="info",
                        message=f"Schema file not found for '{content_type}', skipping.",
                    )]
            elif name == "balance":
                # BalanceValidator checks individual items against the pool
                for item in items:
                    check_results.append(validator.check_stat_range(item, items))
                    check_results.append(validator.check_rarity_hierarchy(item, items))
            elif name == "duplicate":
                # DuplicateValidator checks names and descriptions
                existing_names = [i.get("name", "") for i in items]
                existing_descs = [i.get("description", "") for i in items]
                for item in items:
                    check_results.append(
                        validator.check_name_similarity(item.get("name", ""), existing_names)
                    )
                    check_results.append(
                        validator.check_description_similarity(item.get("description", ""), existing_descs)
                    )
            elif name == "consistency":
                # ConsistencyValidator uses LLM; check naming conventions
                existing_names = [i.get("name", "") for i in items]
                for item in items:
                    check_results.append(
                        validator.check_naming(item.get("name", ""), existing_names)
                    )

            for r in check_results:
                entry = r.model_dump() if hasattr(r, "model_dump") else r
                results.append(entry)
                if not entry.get("passed", True):
                    all_passed = False

        return {
            "status": "success",
            "passed": all_passed,
            "content_type": content_type,
            "checks": results,
        }

    except Exception as exc:
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)


@celery_app.task(bind=True, name="pipeline.export_content", max_retries=2)
def export_content_task(
    self: Any,
    data: dict[str, Any],
    export_format: str = "json",
    output_path: str | None = None,
    template_name: str | None = None,
) -> dict[str, Any]:
    """Export content to the requested format.

    Parameters
    ----------
    data:
        The content data to export.
    export_format:
        One of ``json``, ``csv``, ``markdown``.
    output_path:
        File path for the exported output.
    template_name:
        Jinja2 template name (only used for ``markdown`` format).

    Returns
    -------
    dict
        Status envelope with the output path.
    """
    try:
        from src.export import CsvExporter, JsonExporter, MarkdownExporter

        if output_path is None:
            output_path = f"output/export.{export_format}"

        if export_format == "json":
            JsonExporter().export(data, output_path)
        elif export_format == "csv":
            CsvExporter().export(data, output_path)
        elif export_format == "markdown":
            MarkdownExporter().export(
                data, template_name or "default.md.j2", output_path
            )
        else:
            return {"status": "error", "error": f"Unknown format: {export_format}"}

        return {"status": "success", "format": export_format, "output_path": output_path}

    except Exception as exc:
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)
