#!/usr/bin/env python3
"""Escalate an async research task to a higher review tier."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from validate_json_artifact import load_json, validate
from validate_transition import validate_payload
from version_metadata import apply_default_versions


SUCCESS = 0
VALIDATION_FAILED = 2
INVALID_REQUEST = 3
MALFORMED = 4

STATUS_SCHEMA = Path(__file__).resolve().parents[1] / "task_status.schema.json"
SCHEMA_VERSION = "1.0"

ESCALATABLE_STATUSES = {"awaiting_review", "single_review", "panel_review"}

DEFAULT_REQUIRED_REVIEWERS = {
    0: [],
    1: ["primary"],
    2: ["primary", "methodology"],
    3: ["primary", "methodology", "skeptic"],
}

DEFAULT_MAX_REVISIONS = {
    0: 1,
    1: 1,
    2: 2,
    3: 1,
}


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def resolve_status_path(task_dir: Path) -> Path:
    if task_dir.is_dir():
        return task_dir / "status.json"
    return task_dir


def load_status(task_dir: Path) -> dict[str, Any]:
    status_path = resolve_status_path(task_dir)
    try:
        payload = json.loads(status_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"status file not found: {status_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed JSON in {status_path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"status file is not an object: {status_path}")
    return payload


def review_tier(status: dict[str, Any]) -> int:
    policy = status.get("review_policy")
    if isinstance(policy, dict):
        tier = policy.get("tier")
        if isinstance(tier, int) and not isinstance(tier, bool) and 0 <= tier <= 3:
            return tier
    return 1


def target_review_status(target_tier: int) -> str:
    if target_tier >= 2:
        return "panel_review"
    return "single_review"


def max_int(current: Any, default: int) -> int:
    if isinstance(current, int) and not isinstance(current, bool):
        return max(current, default)
    return default


def apply_escalation(
    status: dict[str, Any],
    target_tier: int,
    reason: str,
    reviewer: Optional[str],
    requested_at: str,
    human_required: bool,
) -> dict[str, Any]:
    current_status = status.get("status")
    current_tier = review_tier(status)
    if current_status not in ESCALATABLE_STATUSES:
        raise ValueError(
            f"cannot escalate from status {current_status!r}; expected one of {sorted(ESCALATABLE_STATUSES)}"
        )
    if target_tier <= current_tier:
        raise ValueError(f"target tier {target_tier} is not higher than current tier {current_tier}")
    if not reason.strip():
        raise ValueError("escalation reason must be non-empty")

    updated = dict(status)
    updated.setdefault("schema_version", SCHEMA_VERSION)
    apply_default_versions(updated)
    policy = dict(updated.get("review_policy") or {})
    required_reviewers = list(DEFAULT_REQUIRED_REVIEWERS[target_tier])
    policy.update(
        {
            "tier": target_tier,
            "required_reviewers": required_reviewers,
            "panel_required": target_tier >= 2,
            "human_required_for_acceptance": bool(policy.get("human_required_for_acceptance")) or human_required,
        }
    )

    updated["previous_status"] = current_status
    updated["status"] = target_review_status(target_tier)
    updated["last_transition_reason"] = "review_tier_escalated"
    updated["updated_at"] = requested_at
    updated["review_policy"] = policy
    updated["escalate_to_tier"] = target_tier
    updated["escalation_reason"] = reason.strip()
    updated["escalation_requested_by"] = reviewer
    updated["escalation_requested_at"] = requested_at
    updated["max_revisions"] = max_int(updated.get("max_revisions"), DEFAULT_MAX_REVISIONS[target_tier])
    if not isinstance(updated.get("revision_count"), int) or isinstance(updated.get("revision_count"), bool):
        updated["revision_count"] = 0
    if not isinstance(updated.get("revision_limit_hit"), bool):
        updated["revision_limit_hit"] = False

    return updated


def validate_updated_status(status: dict[str, Any]) -> tuple[int, list[dict[str, Any]]]:
    schema = load_json(STATUS_SCHEMA)
    if not isinstance(schema, dict):
        return MALFORMED, [{"path": "$", "message": f"schema is not an object: {STATUS_SCHEMA}"}]
    schema_errors = [error.to_dict() for error in validate(status, schema)]
    if schema_errors:
        return VALIDATION_FAILED, schema_errors

    transition_code, transition_result = validate_payload(status)
    if transition_code != SUCCESS:
        return VALIDATION_FAILED, [transition_result]
    return SUCCESS, []


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def run_apply(args: argparse.Namespace) -> int:
    task_dir = args.task_dir
    status_path = resolve_status_path(task_dir)
    try:
        status = load_status(task_dir)
    except ValueError as exc:
        print_json({"ok": False, "reason": "status_load_failed", "error": str(exc), "task_dir": str(task_dir)})
        return MALFORMED

    current_tier = review_tier(status)
    requested_at = iso_now()
    try:
        updated = apply_escalation(
            status,
            args.to_tier,
            args.reason,
            args.reviewer,
            requested_at,
            args.human_required,
        )
    except ValueError as exc:
        print_json(
            {
                "ok": False,
                "reason": "invalid_escalation_request",
                "error": str(exc),
                "current_tier": current_tier,
                "requested_tier": args.to_tier,
                "task_dir": str(task_dir),
            }
        )
        return INVALID_REQUEST

    code, errors = validate_updated_status(updated)
    if code != SUCCESS:
        print_json({"ok": False, "reason": "status_validation_failed", "errors": errors, "task_dir": str(task_dir)})
        return code

    if not args.dry_run:
        atomic_write_json(status_path, updated)

    print_json(
        {
            "ok": True,
            "action": "dry_run_escalated" if args.dry_run else "escalated",
            "task_dir": str(task_dir),
            "previous_tier": current_tier,
            "tier": args.to_tier,
            "status": updated["status"],
            "required_reviewers": updated["review_policy"]["required_reviewers"],
            "panel_required": updated["review_policy"]["panel_required"],
            "human_required_for_acceptance": updated["review_policy"]["human_required_for_acceptance"],
        }
    )
    return SUCCESS


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Escalate a task to a higher review tier.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    apply_parser = subparsers.add_parser("apply", help="Update status.json to require a higher review tier.")
    apply_parser.add_argument("task_dir", type=Path)
    apply_parser.add_argument("--to-tier", required=True, type=int, choices=[1, 2, 3])
    apply_parser.add_argument("--reason", required=True)
    apply_parser.add_argument(
        "--reviewer",
        choices=["primary", "methodology", "skeptic", "aggregator", "scheduler", "human"],
        default=None,
    )
    apply_parser.add_argument("--human-required", action="store_true")
    apply_parser.add_argument("--dry-run", action="store_true")

    return parser.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    if args.command == "apply":
        return run_apply(args)
    print_json({"ok": False, "reason": "unknown_command", "command": args.command})
    return INVALID_REQUEST


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
