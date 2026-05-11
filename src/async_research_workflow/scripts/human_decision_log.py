#!/usr/bin/env python3
"""Append and validate structured human decisions for async research tasks."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from async_research_workflow.resources import schema_path
from async_research_workflow.scripts.decision_log import (
    DECISIONS,
    append_decision,
    has_decision,
    normalize_related_artifacts,
    read_decisions,
)
from async_research_workflow.scripts.validate_json_artifact import load_json, validate
from async_research_workflow.scripts.validate_transition import ALLOWED, validate_payload
from async_research_workflow.scripts.version_metadata import apply_default_versions


SUCCESS = 0
INVALID_REQUEST = 2
VALIDATION_FAILED = 3
MALFORMED = 4

STATUS_SCHEMA = schema_path("task_status.schema.json")
SCHEMA_VERSION = "1.0"

RESOLUTION_STATUS_BY_DECISION = {
    "approve": "ready_for_worker",
    "resume": "ready_for_worker",
    "pause": "paused",
    "reject": "rejected",
    "override": "ready_for_worker",
}


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def decisions_path(ops_dir: Path) -> Path:
    return ops_dir / "decisions.md"


def resolve_task_dir(path: Path) -> Path:
    if path.name == "status.json":
        return path.parent
    return path


def load_status(task_dir: Path) -> dict[str, Any]:
    path = task_dir / "status.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"status file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"status file is not an object: {path}")
    return payload


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def validate_status(status: dict[str, Any], decision_log_path: Path) -> tuple[int, list[dict[str, Any]]]:
    schema = load_json(STATUS_SCHEMA)
    if not isinstance(schema, dict):
        return MALFORMED, [{"path": "$", "message": f"schema is not an object: {STATUS_SCHEMA}"}]

    errors = [error.to_dict() for error in validate(status, schema)]
    transition_code, transition_result = validate_payload(status, decisions_path=decision_log_path)
    if transition_code != SUCCESS:
        errors.append(transition_result)

    if errors:
        return VALIDATION_FAILED, errors
    return SUCCESS, []


def validate_status_schema(status: dict[str, Any]) -> tuple[int, list[dict[str, Any]]]:
    schema = load_json(STATUS_SCHEMA)
    if not isinstance(schema, dict):
        return MALFORMED, [{"path": "$", "message": f"schema is not an object: {STATUS_SCHEMA}"}]
    errors = [error.to_dict() for error in validate(status, schema)]
    if errors:
        return VALIDATION_FAILED, errors
    return SUCCESS, []


def decision_row(args: argparse.Namespace, item_id: str) -> dict[str, Any]:
    return {
        "date": args.date or iso_now(),
        "item_id": item_id,
        "decision": args.decision,
        "reason": args.reason,
        "approver": args.approver,
        "related_artifacts": normalize_related_artifacts(args.related_artifact or []),
    }


def run_append(args: argparse.Namespace) -> int:
    if not args.reason.strip() or not args.approver.strip():
        print_json({"ok": False, "reason": "reason_and_approver_required"})
        return INVALID_REQUEST
    path = decisions_path(args.ops_dir)
    row = decision_row(args, args.item_id)
    if args.dry_run:
        print_json({"ok": True, "action": "dry_run_decision_appended", "decisions": str(path), "row": row})
        return SUCCESS
    append_decision(path, row)
    print_json({"ok": True, "action": "decision_appended", "decisions": str(path), "row": row})
    return SUCCESS


def run_check(args: argparse.Namespace) -> int:
    path = decisions_path(args.ops_dir)
    decisions = args.decision if args.decision else None
    found = has_decision(path, args.item_id, decisions)
    print_json(
        {
            "ok": found,
            "decisions": str(path),
            "item_id": args.item_id,
            "accepted_decisions": decisions,
        }
    )
    return SUCCESS if found else VALIDATION_FAILED


def target_status_for_decision(decision: str, requested_status: Optional[str]) -> str:
    if requested_status:
        return requested_status
    if decision not in RESOLUTION_STATUS_BY_DECISION:
        raise ValueError(f"decision {decision!r} cannot resolve a needs_human task without --status")
    return RESOLUTION_STATUS_BY_DECISION[decision]


def run_resolve_task(args: argparse.Namespace) -> int:
    task_dir = resolve_task_dir(args.task_dir)
    path = decisions_path(args.ops_dir)
    try:
        status = load_status(task_dir)
        new_status = target_status_for_decision(args.decision, args.status)
    except ValueError as exc:
        print_json({"ok": False, "reason": "invalid_request", "error": str(exc)})
        return INVALID_REQUEST

    current_status = status.get("status")
    task_id = status.get("id")
    if current_status != "needs_human":
        print_json({"ok": False, "reason": "task_not_needs_human", "status": current_status, "task_dir": str(task_dir)})
        return INVALID_REQUEST
    if not isinstance(task_id, str) or not task_id.strip():
        print_json({"ok": False, "reason": "missing_task_id", "task_dir": str(task_dir)})
        return INVALID_REQUEST
    if new_status not in ALLOWED.get("needs_human", set()):
        print_json(
            {
                "ok": False,
                "reason": "invalid_resolution_status",
                "status": new_status,
                "allowed": sorted(ALLOWED.get("needs_human", set())),
            }
        )
        return INVALID_REQUEST

    updated = dict(status)
    updated.setdefault("schema_version", SCHEMA_VERSION)
    apply_default_versions(updated)
    if not str(updated.get("human_gate_opened_at") or "").strip():
        opened_at = status.get("updated_at")
        if isinstance(opened_at, str) and opened_at.strip():
            updated["human_gate_opened_at"] = opened_at
    updated["previous_status"] = "needs_human"
    updated["status"] = new_status
    updated["last_transition_reason"] = f"human_decision_{args.decision}"
    updated["updated_at"] = args.date or iso_now()
    updated["requires_human"] = False
    if new_status in {"ready_for_worker", "paused", "rejected"}:
        updated["human_gate_reason"] = None

    row = decision_row(args, task_id)
    schema_code, schema_errors = validate_status_schema(updated)
    if schema_code != SUCCESS:
        print_json({"ok": False, "reason": "resolved_status_schema_invalid", "errors": schema_errors, "task_dir": str(task_dir)})
        return schema_code

    if args.dry_run:
        print_json(
            {
                "ok": True,
                "action": "dry_run_resolved",
                "task_id": task_id,
                "task_dir": str(task_dir),
                "previous_status": current_status,
                "status": new_status,
                "decisions": str(path),
                "decision": row,
            }
        )
        return SUCCESS

    append_decision(path, row)
    code, errors = validate_status(updated, path)
    if code != SUCCESS:
        print_json({"ok": False, "reason": "resolved_status_invalid", "errors": errors, "task_dir": str(task_dir)})
        return code

    atomic_write_json(task_dir / "status.json", updated)

    print_json(
        {
            "ok": True,
            "action": "resolved",
            "task_id": task_id,
            "task_dir": str(task_dir),
            "previous_status": current_status,
            "status": new_status,
            "decisions": str(path),
            "decision": row,
        }
    )
    return SUCCESS


def month_matches(value: str, month: Optional[str]) -> bool:
    if not month:
        return True
    return value.startswith(month)


def summarize_rows(rows: list[dict[str, str]]) -> dict[str, Any]:
    by_decision: dict[str, int] = {}
    by_reason: dict[str, int] = {}
    by_approver: dict[str, int] = {}
    for row in rows:
        decision = row.get("decision", "unknown") or "unknown"
        reason = row.get("reason", "unknown") or "unknown"
        approver = row.get("approver", "unknown") or "unknown"
        by_decision[decision] = by_decision.get(decision, 0) + 1
        by_reason[reason] = by_reason.get(reason, 0) + 1
        by_approver[approver] = by_approver.get(approver, 0) + 1
    return {
        "decision_count": len(rows),
        "by_decision": dict(sorted(by_decision.items())),
        "by_reason": dict(sorted(by_reason.items())),
        "by_approver": dict(sorted(by_approver.items())),
    }


def markdown_summary(report: dict[str, Any]) -> str:
    lines = [
        f"# Human Decision Summary: {report['month']}",
        "",
        f"Decision rows: {report['decision_count']}",
        "",
        "## By Decision",
        "",
    ]
    for key, value in report["by_decision"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## By Reason", ""])
    for key, value in report["by_reason"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## By Approver", ""])
    for key, value in report["by_approver"].items():
        lines.append(f"- {key}: {value}")
    return "\n".join(lines).rstrip() + "\n"


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def run_summarize(args: argparse.Namespace) -> int:
    path = decisions_path(args.ops_dir)
    rows = [row for row in read_decisions(path) if month_matches(row.get("date", ""), args.month)]
    report = {
        "ok": True,
        "decisions": str(path),
        "month": args.month or "all",
        **summarize_rows(rows),
    }
    if args.output:
        atomic_write_text(args.output, markdown_summary(report))
        report["output"] = str(args.output)
    print_json(report)
    return SUCCESS


def add_decision_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--decision", required=True, choices=sorted(DECISIONS))
    parser.add_argument("--reason", required=True)
    parser.add_argument("--approver", required=True)
    parser.add_argument("--related-artifact", action="append", default=[])
    parser.add_argument("--date")


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Append and inspect human decisions.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    append = subparsers.add_parser("append", help="Append a structured decision row.")
    append.add_argument("ops_dir", type=Path)
    append.add_argument("--item-id", required=True)
    add_decision_args(append)
    append.add_argument("--dry-run", action="store_true")

    check = subparsers.add_parser("check", help="Check whether an item has a decision row.")
    check.add_argument("ops_dir", type=Path)
    check.add_argument("--item-id", required=True)
    check.add_argument("--decision", action="append", choices=sorted(DECISIONS))

    resolve = subparsers.add_parser("resolve-task", help="Append a decision row and resolve a needs_human task.")
    resolve.add_argument("ops_dir", type=Path)
    resolve.add_argument("task_dir", type=Path)
    add_decision_args(resolve)
    resolve.add_argument("--status", choices=sorted(ALLOWED["needs_human"]))
    resolve.add_argument("--dry-run", action="store_true")

    summarize = subparsers.add_parser("summarize", help="Summarize decision rows for calibration.")
    summarize.add_argument("ops_dir", type=Path)
    summarize.add_argument("--month")
    summarize.add_argument("--output", type=Path)

    return parser.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    if args.command == "append":
        return run_append(args)
    if args.command == "check":
        return run_check(args)
    if args.command == "resolve-task":
        return run_resolve_task(args)
    if args.command == "summarize":
        return run_summarize(args)
    print_json({"ok": False, "reason": "unknown_command", "command": args.command})
    return INVALID_REQUEST


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
