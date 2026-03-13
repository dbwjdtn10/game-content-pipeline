"""JSON exporter for game content data."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class JsonExporter:
    """Writes content data to a formatted JSON file."""

    def export(
        self,
        data: Any,
        output_path: str | Path,
        *,
        indent: int = 2,
        ensure_ascii: bool = False,
    ) -> Path:
        """Serialize *data* as pretty-printed JSON and write to *output_path*.

        Parameters
        ----------
        data:
            Any JSON-serialisable object (dict, list, etc.).
        output_path:
            Destination file path.  Parent directories are created if absent.
        indent:
            JSON indentation level.
        ensure_ascii:
            When ``False`` (default) non-ASCII characters (e.g. Korean)
            are written as-is rather than escaped.

        Returns
        -------
        Path
            Resolved path to the written file.
        """
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=indent, ensure_ascii=ensure_ascii)

        logger.info("json_export.complete", output_path=str(path), size=path.stat().st_size)
        return path
