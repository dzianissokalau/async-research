#!/usr/bin/env python3
"""Validate workflow JSON artifacts against the local schema subset.

This is not a full JSON Schema implementation. It supports the subset used by
the async research workflow schemas: type, required, properties, items, enum,
pattern, minimum, maximum, and minItems. Schemas that introduce unsupported assertion
keywords fail closed so authors do not accidentally rely on checks this helper
does not perform.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable, List


SUCCESS = 0
VALIDATION_FAILED = 2
MALFORMED = 4
SUPPORTED_SCHEMA_KEYWORDS = {
    "$id",
    "$schema",
    "description",
    "enum",
    "items",
    "maximum",
    "minItems",
    "minimum",
    "pattern",
    "properties",
    "required",
    "title",
    "type",
}


class ValidationError:
    def __init__(self, path: str, message: str) -> None:
        self.path = path
        self.message = message

    def to_dict(self) -> dict:
        return {"path": self.path, "message": self.message}


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed JSON in {path}: {exc}") from exc


def json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int) and not isinstance(value, bool):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unknown"


def type_matches(value: Any, expected: Any) -> bool:
    actual = json_type(value)
    expected_types = expected if isinstance(expected, list) else [expected]
    for expected_type in expected_types:
        if expected_type == actual:
            return True
        if expected_type == "number" and actual == "integer":
            return True
    return False


def validate(instance: Any, schema: dict, path: str = "$") -> List[ValidationError]:
    errors: List[ValidationError] = []

    if path == "$":
        unsupported = schema_keyword_errors(schema)
        if unsupported:
            return unsupported

    if "type" in schema and not type_matches(instance, schema["type"]):
        errors.append(ValidationError(path, f"expected type {schema['type']}, got {json_type(instance)}"))
        return errors

    if "enum" in schema and instance not in schema["enum"]:
        errors.append(ValidationError(path, f"value {instance!r} is not in enum {schema['enum']!r}"))

    if isinstance(instance, dict):
        required = schema.get("required", [])
        for key in required:
            if key not in instance:
                errors.append(ValidationError(f"{path}.{key}", "required field missing"))

        properties = schema.get("properties", {})
        for key, subschema in properties.items():
            if key in instance:
                errors.extend(validate(instance[key], subschema, f"{path}.{key}"))

    if isinstance(instance, list) and "items" in schema:
        for index, item in enumerate(instance):
            errors.extend(validate(item, schema["items"], f"{path}[{index}]"))

    if isinstance(instance, list) and "minItems" in schema:
        minimum_items = schema["minItems"]
        if isinstance(minimum_items, int) and len(instance) < minimum_items:
            errors.append(ValidationError(path, f"array length {len(instance)!r} is below minItems {minimum_items!r}"))

    if isinstance(instance, str) and "pattern" in schema:
        if re.match(schema["pattern"], instance) is None:
            errors.append(ValidationError(path, f"value {instance!r} does not match pattern {schema['pattern']!r}"))

    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(ValidationError(path, f"value {instance!r} is below minimum {schema['minimum']!r}"))
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append(ValidationError(path, f"value {instance!r} is above maximum {schema['maximum']!r}"))

    return errors


def schema_keyword_errors(schema: Any, path: str = "$") -> List[ValidationError]:
    """Return unsupported schema keywords used by this local validator.

    `properties` keys are artifact field names, not schema keywords, so their
    values are traversed as nested schemas. Unsupported JSON Schema constructs
    such as anyOf, oneOf, allOf, $ref, const, maxItems, and
    additionalProperties intentionally fail closed here.
    """

    errors: List[ValidationError] = []
    if not isinstance(schema, dict):
        return errors

    for key, value in schema.items():
        if key not in SUPPORTED_SCHEMA_KEYWORDS:
            errors.append(ValidationError(f"{path}.{key}", "unsupported schema keyword"))
            continue
        if key == "properties":
            if isinstance(value, dict):
                for property_name, subschema in value.items():
                    errors.extend(schema_keyword_errors(subschema, f"{path}.properties.{property_name}"))
            continue
        if key == "items":
            if isinstance(value, dict):
                errors.extend(schema_keyword_errors(value, f"{path}.items"))
            elif isinstance(value, list):
                errors.append(ValidationError(f"{path}.items", "array-form items are unsupported"))

    return errors


def print_json(payload: dict) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a workflow JSON artifact.")
    parser.add_argument("artifact", type=Path, help="Path to the JSON artifact to validate")
    parser.add_argument("--schema", required=True, type=Path, help="Path to the JSON schema")
    return parser.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)

    try:
        schema = load_json(args.schema)
        artifact = load_json(args.artifact)
    except ValueError as exc:
        print_json({"ok": False, "reason": "malformed_or_missing", "error": str(exc)})
        return MALFORMED

    unsupported = schema_keyword_errors(schema)
    if unsupported:
        print_json(
            {
                "ok": False,
                "reason": "unsupported_schema_keywords",
                "schema": str(args.schema),
                "errors": [error.to_dict() for error in unsupported],
            }
        )
        return VALIDATION_FAILED

    errors = validate(artifact, schema)
    if errors:
        print_json(
            {
                "ok": False,
                "reason": "schema_validation_failed",
                "artifact": str(args.artifact),
                "schema": str(args.schema),
                "errors": [error.to_dict() for error in errors],
            }
        )
        return VALIDATION_FAILED

    print_json({"ok": True, "artifact": str(args.artifact), "schema": str(args.schema)})
    return SUCCESS


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
