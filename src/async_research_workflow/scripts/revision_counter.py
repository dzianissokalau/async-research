#!/usr/bin/env python3
"""Apply bounded revision-counter routing for async research tasks."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from datetime import datetime, timezone
from typing import Any, Iterable

from async_research_workflow.resources import schema_path
from async_research_workflow.scripts.validate_json_artifact import load_json, validate
from async_research_workflow.scripts.validate_transition import validate_payload
from async_research_workflow.scripts.version_metadata import apply_default_versions


SUCCESS = 0
VALIDATION_FAILED = 2
MALFORMED = 4

DEFAULT_MAX_REVISIONS = {
    0: 1,
    1: 1,
    2: 2,
    3: 1,
}

REVISION_REQUEST_REASON = "reviewer_requested_revision"
REVISION_LIMIT_REASON = "revision_limit_exceeded"
DEFAULT_SCHEMA = schema_path("task_status.schema.json")
SCHEMA_VERSION = "1.0"
CLAIM_STRENGTH_POLICY = "weakest_current_review"


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def print_json(payload: dict) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def resolve_task_dir(path: Path) -> Path:
    if path.name == "status.json":
        return path.parent
    return path


def status_path(task_dir: Path) -> Path:
    return task_dir / "status.json"


def load_status(task_dir: Path) -> dict[str, Any]:
    path = status_path(task_dir)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"status file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"status file is not an object: {path}")
    return payload


def review_tier(payload: dict[str, Any]) -> int:
    policy = payload.get("review_policy")
    if isinstance(policy, dict):
        tier = policy.get("tier")
        if isinstance(tier, int) and not isinstance(tier, bool) and tier in DEFAULT_MAX_REVISIONS:
            return tier
    return 1


def default_max_revisions(tier: int) -> int:
    return DEFAULT_MAX_REVISIONS.get(tier, DEFAULT_MAX_REVISIONS[1])


def normalize_revision_fields(payload: dict[str, Any]) -> None:
    tier = review_tier(payload)
    if not isinstance(payload.get("revision_count"), int) or isinstance(payload.get("revision_count"), bool):
        payload["revision_count"] = 0
    if not isinstance(payload.get("max_revisions"), int) or isinstance(payload.get("max_revisions"), bool):
        payload["max_revisions"] = default_max_revisions(tier)
    if not isinstance(payload.get("revision_limit_hit"), bool):
        payload["revision_limit_hit"] = False


def validate_status_payload(payload: dict[str, Any], schema: dict) -> tuple[int, list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []
    schema_errors = validate(payload, schema)
    errors.extend(error.to_dict() for error in schema_errors)

    transition_code, transition_result = validate_payload(payload)
    if transition_code != SUCCESS:
        errors.append(transition_result)

    if errors:
        return VALIDATION_FAILED, errors
    return SUCCESS, []


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def clear_stale_claim_strength(payload: dict[str, Any], reason: str) -> None:
    result = dict(payload.get("result") or {})
    result["claim_strength"] = None
    result["claim_strength_stale"] = True
    result["claim_strength_revalidation_required"] = True
    result["claim_strength_revalidation_reason"] = reason
    result["claim_strength_revalidated_at"] = None
    result["claim_strength_policy"] = CLAIM_STRENGTH_POLICY
    payload["result"] = result


def apply_revision_request(task_dir: Path, schema: dict, reviewer: str, reason: str, dry_run: bool) -> int:
    payload = load_status(task_dir)
    normalize_revision_fields(payload)

    current_status = payload.get("status")
    revision_count = int(payload["revision_count"])
    max_revisions = int(payload["max_revisions"])
    now = iso_now()
    limit_will_block = revision_count >= max_revisions

    updated = dict(payload)
    updated.setdefault("schema_version", SCHEMA_VERSION)
    apply_default_versions(updated)
    updated["previous_status"] = current_status
    updated["updated_at"] = now

    if limit_will_block:
        updated["status"] = "needs_human"
        updated["last_transition_reason"] = REVISION_LIMIT_REASON
        updated["revision_limit_hit"] = True
        updated["requires_human"] = True
        updated["human_gate_reason"] = (
            f"{reviewer} requested another revision after "
            f"{revision_count}/{max_revisions} allowed revisions"
        )
        clear_stale_claim_strength(updated, REVISION_LIMIT_REASON)
        result_code = SUCCESS
    else:
        updated["status"] = "needs_revision"
        updated["last_transition_reason"] = reason
        updated["revision_count"] = revision_count + 1
        updated["revision_limit_hit"] = updated["revision_count"] >= max_revisions
        clear_stale_claim_strength(updated, reason)
        result_code = SUCCESS

    validation_code, errors = validate_status_payload(updated, schema)
    if validation_code != SUCCESS:
        print_json(
            {
                "ok": False,
                "reason": "revision_update_invalid",
                "errors": errors,
                "task_dir": str(task_dir),
            }
        )
        return validation_code

    if not dry_run:
        atomic_write_json(status_path(task_dir), updated)

    print_json(
        {
            "ok": True,
            "action": "dry_run_revision_request" if dry_run else "revision_request_applied",
            "task_dir": str(task_dir),
            "previous_status": current_status,
            "new_status": updated["status"],
            "revision_count": updated["revision_count"],
            "max_revisions": updated["max_revisions"],
            "revision_limit_hit": updated["revision_limit_hit"],
        }
    )
    return result_code


def inspect_task(task_dir: Path, schema: dict) -> int:
    payload = load_status(task_dir)
    normalize_revision_fields(payload)
    validation_code, errors = validate_status_payload(payload, schema)
    print_json(
        {
            "ok": validation_code == SUCCESS,
            "task_dir": str(task_dir),
            "status": payload.get("status"),
            "revision_count": payload.get("revision_count"),
            "max_revisions": payload.get("max_revisions"),
            "revision_limit_hit": payload.get("revision_limit_hit"),
            "errors": errors,
        }
    )
    return validation_code


def limit_hit(payload: dict[str, Any]) -> bool:
    normalize_revision_fields(payload)
    revision_count = int(payload["revision_count"])
    max_revisions = int(payload["max_revisions"])
    return (
        bool(payload.get("revision_limit_hit"))
        or payload.get("last_transition_reason") == REVISION_LIMIT_REASON
        or revision_count >= max_revisions
    )


def task_summary(task_dir: Path, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": payload.get("id", task_dir.name),
        "task_dir": str(task_dir),
        "status": payload.get("status"),
        "revision_count": payload.get("revision_count"),
        "max_revisions": payload.get("max_revisions"),
        "revision_limit_hit": payload.get("revision_limit_hit"),
        "human_gate_reason": payload.get("human_gate_reason"),
    }


def scan_limits(tasks_dir: Path, markdown: bool) -> int:
    hits: list[dict[str, Any]] = []
    for path in sorted(tasks_dir.glob("*/status.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        if limit_hit(payload):
            hits.append(task_summary(path.parent, payload))

    if markdown:
        print("| Task | Status | Revisions | Human gate |")
        print("| --- | --- | ---: | --- |")
        for item in hits:
            gate = item.get("human_gate_reason") or ""
            print(
                f"| {item['task_id']} | {item['status']} | "
                f"{item['revision_count']}/{item['max_revisions']} | {gate} |"
            )
    else:
        print_json({"revision_limit_hits": hits, "count": len(hits)})
    return SUCCESS


def load_schema(path: Path) -> dict:
    schema = load_json(path)
    if not isinstance(schema, dict):
        raise ValueError(f"schema is not an object: {path}")
    return schema


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply or inspect async research revision counters.")
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    subparsers = parser.add_subparsers(dest="command", required=True)

    defaults = subparsers.add_parser("defaults", help="Print default max revisions for a review tier.")
    defaults.add_argument("--tier", type=int, choices=sorted(DEFAULT_MAX_REVISIONS), required=True)

    request = subparsers.add_parser("request", help="Request a bounded task revision.")
    request.add_argument("task_dir", type=Path)
    request.add_argument("--reviewer", default="reviewer")
    request.add_argument("--reason", default=REVISION_REQUEST_REASON)
    request.add_argument("--dry-run", action="store_true")

    inspect = subparsers.add_parser("inspect", help="Inspect revision fields for a task.")
    inspect.add_argument("task_dir", type=Path)

    scan = subparsers.add_parser("scan-limits", help="List tasks that hit revision limits.")
    scan.add_argument("tasks_dir", type=Path)
    scan.add_argument("--markdown", action="store_true")

    return parser.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)

    if args.command == "defaults":
        print_json({"tier": args.tier, "max_revisions": default_max_revisions(args.tier)})
        return SUCCESS

    if args.command == "scan-limits":
        return scan_limits(args.tasks_dir, args.markdown)

    try:
        schema = load_schema(args.schema)
    except ValueError as exc:
        print_json({"ok": False, "reason": "schema_load_failed", "error": str(exc)})
        return MALFORMED

    task_dir = resolve_task_dir(args.task_dir)
    try:
        if args.command == "request":
            return apply_revision_request(task_dir, schema, args.reviewer, args.reason, args.dry_run)
        if args.command == "inspect":
            return inspect_task(task_dir, schema)
    except ValueError as exc:
        print_json({"ok": False, "reason": "status_load_failed", "error": str(exc), "task_dir": str(task_dir)})
        return MALFORMED

    return MALFORMED


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
