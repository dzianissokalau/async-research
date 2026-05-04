#!/usr/bin/env python3
"""Route malformed or invalid task status.json files to needs_human.

Validators should stay strict. This wrapper is the fail-closed recovery path:
it preserves the bad status file, writes a minimal valid needs_human status,
and verifies that the recovered state passes schema and transition checks.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from validate_json_artifact import load_json, validate
from validate_transition import ALLOWED, RECOVERY_REASON, STATUSES, validate_payload
from version_metadata import apply_default_versions
from async_research_workflow.resources import schema_path


SUCCESS = 0
INVALID = 4

TASK_ID_PATTERN = re.compile(r"TASK-[0-9]{4}")
DEFAULT_SCHEMA = schema_path("task_status.schema.json")
SCHEMA_VERSION = "1.0"


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def print_json(payload: dict) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def resolve_task_dir(path: Path) -> Path:
    if path.name == "status.json":
        return path.parent
    return path


def load_status(path: Path) -> tuple[Optional[dict[str, Any]], str, list[dict[str, str]]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, "missing_status_json", []
    except json.JSONDecodeError as exc:
        return None, "malformed_status_json", [{"path": "$", "message": str(exc)}]

    if not isinstance(payload, dict):
        return None, "status_json_not_object", [{"path": "$", "message": "expected object"}]
    return payload, "", []


def schema_enum(schema: dict, field: str) -> set[Any]:
    properties = schema.get("properties", {})
    field_schema = properties.get(field, {})
    values = field_schema.get("enum", [])
    return set(values) if isinstance(values, list) else set()


def valid_task_id(value: Any) -> bool:
    return isinstance(value, str) and TASK_ID_PATTERN.fullmatch(value) is not None


def derive_task_id(task_dir: Path, payload: Optional[dict[str, Any]]) -> str:
    if payload and valid_task_id(payload.get("id")):
        return str(payload["id"])
    match = TASK_ID_PATTERN.search(task_dir.name)
    if match:
        return match.group(0)
    return "TASK-0000"


def bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and minimum <= value <= maximum:
        return value
    return default


def string_or_default(value: Any, default: str) -> str:
    if isinstance(value, str) and value.strip():
        return value
    return default


def string_list_or_default(value: Any, default: list[str]) -> list[str]:
    if isinstance(value, list) and value and all(isinstance(item, str) and item.strip() for item in value):
        return value
    return default


def default_allowed_path(task_dir: Path) -> str:
    try:
        return str(task_dir.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(task_dir)


def recovery_previous_status(payload: Optional[dict[str, Any]]) -> Optional[str]:
    if not payload:
        return None
    previous = payload.get("status")
    if isinstance(previous, str) and previous in STATUSES and "needs_human" in ALLOWED.get(previous, set()):
        return previous
    return None


def validate_current(
    payload: Optional[dict[str, Any]],
    schema: dict,
    load_reason: str,
    load_errors: list[dict[str, str]],
) -> tuple[bool, str, list[dict[str, Any]]]:
    if payload is None:
        return False, load_reason, load_errors

    schema_errors = validate(payload, schema)
    if schema_errors:
        return False, "schema_validation_failed", [error.to_dict() for error in schema_errors]

    transition_code, transition_result = validate_payload(payload)
    if transition_code != SUCCESS:
        return False, "transition_validation_failed", [transition_result]

    return True, "already_valid", []


def build_recovery_payload(
    task_dir: Path,
    payload: Optional[dict[str, Any]],
    schema: dict,
    failure_reason: str,
    quarantine_name: Optional[str],
) -> dict[str, Any]:
    now = iso_now()
    task_types = schema_enum(schema, "type")
    task_type = payload.get("type") if payload else None
    if task_type not in task_types:
        task_type = "admin"

    title = string_or_default(
        payload.get("title") if payload else None,
        f"Recovered status for {task_dir.name}",
    )

    allowed_paths = string_list_or_default(
        payload.get("allowed_paths") if payload else None,
        [default_allowed_path(task_dir)],
    )

    allowed_tools = string_list_or_default(
        payload.get("allowed_tools") if payload else None,
        ["read_files", "write_task_files"],
    )

    human_gate_reason = f"status.json recovered after {failure_reason}"
    if quarantine_name:
        human_gate_reason = f"{human_gate_reason}; original saved as {quarantine_name}"

    return apply_default_versions({
        "schema_version": SCHEMA_VERSION,
        "id": derive_task_id(task_dir, payload),
        "title": title,
        "type": task_type,
        "status": "needs_human",
        "previous_status": recovery_previous_status(payload),
        "last_transition_reason": RECOVERY_REASON,
        "priority": bounded_int(payload.get("priority") if payload else None, 3, 1, 5),
        "revision_count": bounded_int(payload.get("revision_count") if payload else None, 0, 0, 5),
        "max_revisions": bounded_int(payload.get("max_revisions") if payload else None, 0, 0, 5),
        "revision_limit_hit": False,
        "created_at": string_or_default(payload.get("created_at") if payload else None, now),
        "updated_at": now,
        "lock_owner": None,
        "lock_expires_at": None,
        "allowed_paths": allowed_paths,
        "allowed_tools": allowed_tools,
        "allow_browsing": False,
        "allow_code_execution": False,
        "allow_network": False,
        "max_minutes": bounded_int(payload.get("max_minutes") if payload else None, 15, 1, 240),
        "max_turns": bounded_int(payload.get("max_turns") if payload else None, 1, 1, 20),
        "model_tier": "status_recovery",
        "review_policy": {
            "tier": 0,
            "required_reviewers": [],
            "panel_required": False,
            "human_required_for_acceptance": True,
        },
        "escalate_to_tier": None,
        "escalation_reason": None,
        "escalation_requested_by": None,
        "escalation_requested_at": None,
        "requires_human": True,
        "human_gate_reason": human_gate_reason,
        "budget": {
            "max_api_usd": 0,
            "max_compute_usd": 0,
        },
        "result": {
            "recommendation": "needs_human",
            "claim_strength": "none",
            "followup_count": 0,
        },
    })


def validate_recovery(payload: dict[str, Any], schema: dict) -> tuple[bool, list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []
    schema_errors = validate(payload, schema)
    errors.extend(error.to_dict() for error in schema_errors)

    transition_code, transition_result = validate_payload(payload)
    if transition_code != SUCCESS:
        errors.append(transition_result)

    return not errors, errors


def quarantine_path(task_dir: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = task_dir / f"status.invalid.{stamp}.{os.getpid()}.json"
    if not base.exists():
        return base
    counter = 1
    while True:
        candidate = task_dir / f"status.invalid.{stamp}.{os.getpid()}.{counter}.json"
        if not candidate.exists():
            return candidate
        counter += 1


def write_recovered_status(status_path: Path, recovery_payload: dict[str, Any], quarantine: Optional[Path]) -> None:
    tmp = status_path.with_name(f".status.recovery.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(recovery_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if status_path.exists() and quarantine is not None:
        status_path.rename(quarantine)
    os.replace(tmp, status_path)


def recover(path: Path, schema_path: Path, force: bool, dry_run: bool) -> int:
    task_dir = resolve_task_dir(path)
    status_path = task_dir / "status.json"
    if not task_dir.exists() or not task_dir.is_dir():
        print_json({"ok": False, "reason": "task_dir_missing", "task_dir": str(task_dir)})
        return INVALID

    try:
        schema = load_json(schema_path)
    except ValueError as exc:
        print_json({"ok": False, "reason": "schema_load_failed", "error": str(exc), "schema": str(schema_path)})
        return INVALID
    if not isinstance(schema, dict):
        print_json({"ok": False, "reason": "schema_not_object", "schema": str(schema_path)})
        return INVALID

    payload, load_reason, load_errors = load_status(status_path)
    is_valid, failure_reason, validation_errors = validate_current(payload, schema, load_reason, load_errors)
    if is_valid and not force:
        print_json({"ok": True, "action": "already_valid", "status": str(status_path)})
        return SUCCESS

    quarantine = quarantine_path(task_dir) if status_path.exists() else None
    recovery_payload = build_recovery_payload(
        task_dir,
        payload,
        schema,
        "forced_recovery" if force and is_valid else failure_reason,
        quarantine.name if quarantine is not None else None,
    )
    recovery_ok, recovery_errors = validate_recovery(recovery_payload, schema)
    if not recovery_ok:
        print_json(
            {
                "ok": False,
                "reason": "recovery_payload_invalid",
                "status": str(status_path),
                "errors": recovery_errors,
            }
        )
        return INVALID

    if not dry_run:
        try:
            write_recovered_status(status_path, recovery_payload, quarantine)
        except OSError as exc:
            print_json({"ok": False, "reason": "recovery_write_failed", "error": str(exc), "status": str(status_path)})
            return INVALID

    print_json(
        {
            "ok": True,
            "action": "dry_run_recover" if dry_run else "recovered",
            "status": str(status_path),
            "new_status": "needs_human",
            "failure_reason": "forced_recovery" if force and is_valid else failure_reason,
            "validation_errors": validation_errors,
            "quarantine": str(quarantine) if quarantine is not None else None,
        }
    )
    return SUCCESS


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Recover malformed or invalid task status.json files.")
    parser.add_argument("path", type=Path, help="Task directory or path to status.json")
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--force", action="store_true", help="Route even a currently valid status.json to needs_human")
    parser.add_argument("--dry-run", action="store_true", help="Report recovery without writing files")
    return parser.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    return recover(args.path, args.schema, args.force, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
