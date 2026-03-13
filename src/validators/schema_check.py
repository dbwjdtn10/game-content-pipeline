"""JSON schema validation using Pydantic for structural checks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog
from pydantic import BaseModel, ValidationError, create_model
from pydantic.fields import FieldInfo

from src.validators.models import ValidationResult

logger = structlog.get_logger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMA_DIR = PROJECT_ROOT / "game_data" / "schema"

# JSON Schema type -> Python type mapping
_JSON_TYPE_MAP: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


class SchemaValidator:
    """Validates game data against JSON schemas stored in game_data/schema/."""

    def __init__(self) -> None:
        self.log = logger.bind(validator="SchemaValidator")
        self._schema_cache: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate(
        self,
        data: dict[str, Any] | list[dict[str, Any]],
        schema_path: str | Path,
    ) -> ValidationResult:
        """Validate *data* against the JSON schema at *schema_path*.

        *schema_path* can be either an absolute path or a filename
        relative to ``game_data/schema/``.
        """
        path = self._resolve_schema_path(schema_path)
        self.log.info("schema_validate_start", schema=str(path))

        schema = self._load_schema(path)

        items = data if isinstance(data, list) else [data]
        all_errors: list[dict[str, Any]] = []

        for idx, item in enumerate(items):
            errors = self._validate_item(item, schema)
            if errors:
                all_errors.append({"index": idx, "errors": errors})

        if all_errors:
            total_errors = sum(len(e["errors"]) for e in all_errors)
            return ValidationResult(
                passed=False,
                check_name="schema_validation",
                severity="error",
                message=f"Schema validation failed with {total_errors} error(s).",
                details={"validation_errors": all_errors},
            )

        return ValidationResult(
            passed=True,
            check_name="schema_validation",
            severity="info",
            message="Data conforms to the schema.",
        )

    # ------------------------------------------------------------------
    # Internal validation logic
    # ------------------------------------------------------------------

    def _validate_item(
        self,
        item: dict[str, Any],
        schema: dict[str, Any],
    ) -> list[str]:
        """Validate a single item dict against a JSON-schema-like definition.

        Returns a list of human-readable error strings (empty if valid).
        """
        errors: list[str] = []

        required = set(schema.get("required", []))
        properties: dict[str, dict[str, Any]] = schema.get("properties", {})
        additional = schema.get("additionalProperties", True)

        # Check required fields
        for field in required:
            if field not in item:
                errors.append(f"Missing required field: '{field}'")

        # Validate each declared property
        for field, field_schema in properties.items():
            if field not in item:
                continue
            value = item[field]
            field_errors = self._validate_value(value, field_schema, field)
            errors.extend(field_errors)

        # Check for undeclared fields
        if additional is False:
            extra = set(item.keys()) - set(properties.keys())
            for field in extra:
                errors.append(f"Unexpected additional field: '{field}'")

        return errors

    def _validate_value(
        self,
        value: Any,
        field_schema: dict[str, Any],
        field_name: str,
    ) -> list[str]:
        """Validate a single value against its field schema."""
        errors: list[str] = []

        # Type check (supports union via list of types)
        expected_types = field_schema.get("type")
        if expected_types is not None:
            if isinstance(expected_types, str):
                expected_types = [expected_types]
            if not self._type_matches(value, expected_types):
                errors.append(
                    f"Field '{field_name}': expected type "
                    f"{expected_types}, got {type(value).__name__}"
                )
                return errors  # skip further checks if type is wrong

        # Enum
        enum = field_schema.get("enum")
        if enum is not None and value not in enum:
            errors.append(f"Field '{field_name}': value '{value}' not in {enum}")

        # String constraints
        if isinstance(value, str):
            min_len = field_schema.get("minLength")
            max_len = field_schema.get("maxLength")
            if min_len is not None and len(value) < min_len:
                errors.append(
                    f"Field '{field_name}': string length {len(value)} < minLength {min_len}"
                )
            if max_len is not None and len(value) > max_len:
                errors.append(
                    f"Field '{field_name}': string length {len(value)} > maxLength {max_len}"
                )
            pattern = field_schema.get("pattern")
            if pattern is not None:
                import re
                if not re.match(pattern, value):
                    errors.append(
                        f"Field '{field_name}': value does not match pattern '{pattern}'"
                    )

        # Numeric constraints
        if isinstance(value, (int, float)):
            minimum = field_schema.get("minimum")
            maximum = field_schema.get("maximum")
            if minimum is not None and value < minimum:
                errors.append(f"Field '{field_name}': value {value} < minimum {minimum}")
            if maximum is not None and value > maximum:
                errors.append(f"Field '{field_name}': value {value} > maximum {maximum}")

        # Array constraints
        if isinstance(value, list):
            min_items = field_schema.get("minItems")
            if min_items is not None and len(value) < min_items:
                errors.append(
                    f"Field '{field_name}': array length {len(value)} < minItems {min_items}"
                )
            items_schema = field_schema.get("items")
            if items_schema is not None:
                for i, element in enumerate(value):
                    sub_errors = self._validate_value(
                        element, items_schema, f"{field_name}[{i}]"
                    )
                    errors.extend(sub_errors)

        # Nested object
        if isinstance(value, dict) and field_schema.get("properties"):
            sub_errors = self._validate_item(value, field_schema)
            errors.extend(sub_errors)

        return errors

    @staticmethod
    def _type_matches(value: Any, expected_types: list[str]) -> bool:
        """Check whether *value* matches any of the expected JSON-schema types."""
        for t in expected_types:
            if t == "null" and value is None:
                return True
            if t == "string" and isinstance(value, str):
                return True
            if t == "integer" and isinstance(value, int) and not isinstance(value, bool):
                return True
            if t == "number" and isinstance(value, (int, float)) and not isinstance(value, bool):
                return True
            if t == "boolean" and isinstance(value, bool):
                return True
            if t == "array" and isinstance(value, list):
                return True
            if t == "object" and isinstance(value, dict):
                return True
        return False

    # ------------------------------------------------------------------
    # Schema loading
    # ------------------------------------------------------------------

    def _load_schema(self, path: Path) -> dict[str, Any]:
        """Load and cache a JSON schema file."""
        key = str(path)
        if key not in self._schema_cache:
            if not path.exists():
                raise FileNotFoundError(f"Schema file not found: {path}")
            with path.open("r", encoding="utf-8") as fh:
                self._schema_cache[key] = json.load(fh)
        return self._schema_cache[key]

    @staticmethod
    def _resolve_schema_path(schema_path: str | Path) -> Path:
        """Resolve a schema path, treating relative paths as relative to
        the ``game_data/schema/`` directory."""
        p = Path(schema_path)
        if p.is_absolute():
            return p
        return SCHEMA_DIR / p
