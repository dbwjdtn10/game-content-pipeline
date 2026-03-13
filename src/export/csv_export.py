"""CSV exporter with nested-data flattening for game content."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class CsvExporter:
    """Flattens nested dicts/lists and writes them as CSV rows."""

    # ------------------------------------------------------------------
    # Flattening helper
    # ------------------------------------------------------------------

    @staticmethod
    def _flatten(
        obj: dict[str, Any],
        parent_key: str = "",
        sep: str = ".",
    ) -> dict[str, Any]:
        """Recursively flatten a nested dict.

        Nested keys are joined with *sep* (e.g. ``stats.atk``).
        Lists are serialized as JSON-like strings so every row
        has a consistent column count.
        """
        items: list[tuple[str, Any]] = []
        for key, value in obj.items():
            new_key = f"{parent_key}{sep}{key}" if parent_key else key
            if isinstance(value, dict):
                items.extend(
                    CsvExporter._flatten(value, new_key, sep).items()
                )
            elif isinstance(value, list):
                # For simple scalar lists, join; for complex lists, repr
                if value and isinstance(value[0], dict):
                    import json

                    items.append((new_key, json.dumps(value, ensure_ascii=False)))
                else:
                    items.append((new_key, "; ".join(str(v) for v in value)))
            else:
                items.append((new_key, value))
        return dict(items)

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export(
        self,
        data: dict[str, Any] | list[dict[str, Any]],
        output_path: str | Path,
    ) -> Path:
        """Flatten *data* and write to a UTF-8 CSV file.

        Parameters
        ----------
        data:
            A single dict or a list of dicts.  Each dict becomes one row.
        output_path:
            Destination CSV file path.

        Returns
        -------
        Path
            Resolved path to the written file.
        """
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        rows: list[dict[str, Any]]
        if isinstance(data, dict):
            rows = [self._flatten(data)]
        else:
            rows = [self._flatten(item) for item in data]

        if not rows:
            path.write_text("", encoding="utf-8")
            return path

        # Gather all field names across rows (preserving order)
        fieldnames: list[str] = []
        seen: set[str] = set()
        for row in rows:
            for k in row:
                if k not in seen:
                    fieldnames.append(k)
                    seen.add(k)

        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)

        logger.info("csv_export.complete", output_path=str(path), rows=len(rows))
        return path
