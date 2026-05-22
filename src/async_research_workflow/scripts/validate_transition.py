#!/usr/bin/env python3
"""Validate async research task status transitions.

The validator reads a task status.json file and checks that previous_status ->
status is allowed by the workflow state machine.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Dict, Iterable, Optional, Set

from async_research_workflow.scripts.decision_log import has_auto_decision
from async_research_workflow.scripts.decision_log import has_decision


SUCCESS = 0
INVALID_TRANSITION = 2
UNKNOWN_STATUS = 3
MALFORMED = 4


STATUSES: Set[str] = {
    "inbox",
    "ready_for_planning",
    "ready_for_worker",
    "in_progress",
    "awaiting_review",
    "single_review",
    "panel_review",
    "accepted",
    "needs_revision",
    "needs_human",
    "paused",
    "rejected",
    "synthesized",
}


INITIAL_STATUSES: Set[str] = {
    "inbox",
    "ready_for_planning",
    "ready_for_worker",
}


ALLOWED: Dict[Optional[str], Set[str]] = {
    None: INITIAL_STATUSES,
    "inbox": {"ready_for_planning", "paused", "rejected"},
    "ready_for_planning": {"ready_for_worker", "needs_human", "paused", "rejected"},
    "ready_for_worker": {"in_progress", "needs_human", "paused", "rejected"},
    "in_progress": {"awaiting_review", "needs_human", "paused", "rejected"},
    "awaiting_review": {"single_review", "panel_review", "needs_human"},
    "single_review": {"accepted", "needs_revision", "needs_human", "paused", "rejected", "panel_review"},
    "panel_review": {"accepted", "needs_revision", "needs_human", "paused", "rejected"},
    "needs_revision": {"ready_for_worker", "needs_human", "paused", "rejected"},
    "needs_human": {"ready_for_worker", "paused", "rejected"},
    "accepted": {"synthesized"},
    "paused": set(),
    "rejected": set(),
    "synthesized": set(),
}


UNCHANGED_ALLOWED: Set[str] = {
    "panel_review",
}


RECOVERY_REASON = "status_json_recovery"
HUMAN_RESOLUTION_DECISIONS = {
    "approve",
    "resume",
    "pause",
    "reject",
    "approve_public",
    "approve_high_stakes",
    "approve_budget",
    "approve_data_use",
    "override",
}
AUTO_RESOLUTION_REQUIRED_FIELDS = {
    "policy_version",
    "mode",
    "gate_category",
    "policy_action",
    "decision",
    "target_status",
    "actor",
    "reason",
    "confidence",
    "applied_at",
}


def resolve_status_path(path: Path) -> Path:
    if path.is_dir():
        return path / "status.json"
    return path


def load_status(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"status file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed JSON in {path}: {exc}") from exc


def infer_decisions_path(status_path: Path) -> Optional[Path]:
    task_dir = status_path.parent
    if task_dir.parent.name == "tasks":
        return task_dir.parent.parent / "decisions.md"
    return None


def infer_auto_decisions_path(decision_log_path: Optional[Path]) -> Optional[Path]:
    if decision_log_path is None:
        return None
    return decision_log_path.with_name("auto_decisions.md")


def human_decision_required(previous: Any, status: Any) -> bool:
    return previous == "needs_human" and status in ALLOWED.get("needs_human", set())


def auto_decision_required(payload: Dict[str, Any]) -> bool:
    reason = payload.get("last_transition_reason")
    return isinstance(reason, str) and reason.startswith("mode_policy_auto_")


def validate_payload(
    payload: Dict[str, Any],
    decisions_path: Optional[Path] = None,
) -> tuple[int, Dict[str, Any]]:
    status = payload.get("status")
    previous = payload.get("previous_status")
    reason = payload.get("last_transition_reason")
    task_id = payload.get("id")

    result: Dict[str, Any] = {
        "ok": False,
        "task_id": task_id,
        "previous_status": previous,
        "status": status,
        "last_transition_reason": reason,
    }

    if status not in STATUSES:
        result["reason"] = "unknown_status"
        return UNKNOWN_STATUS, result

    if previous is not None and previous not in STATUSES:
        result["reason"] = "unknown_previous_status"
        return UNKNOWN_STATUS, result

    if previous == status:
        if status in UNCHANGED_ALLOWED:
            result.update({"ok": True, "reason": "unchanged_allowed"})
            return SUCCESS, result
        result["reason"] = "unchanged_status_not_allowed"
        return INVALID_TRANSITION, result

    if not reason or not isinstance(reason, str):
        result["reason"] = "missing_last_transition_reason"
        return MALFORMED, result

    if previous is None and status == "needs_human" and reason == RECOVERY_REASON:
        result.update({"ok": True, "reason": "recovery_transition"})
        return SUCCESS, result

    allowed_next = ALLOWED.get(previous, set())
    if status not in allowed_next:
        result["reason"] = "invalid_transition"
        result["allowed_next"] = sorted(allowed_next)
        return INVALID_TRANSITION, result

    if human_decision_required(previous, status):
        result["human_decision_required"] = True
        result["decisions_path"] = str(decisions_path) if decisions_path is not None else None
        if not isinstance(task_id, str) or not task_id.strip():
            result["reason"] = "missing_task_id_for_human_decision"
            return MALFORMED, result
        if decisions_path is None:
            result["reason"] = "missing_decision_log_path"
            return MALFORMED, result
        if not has_decision(decisions_path, task_id, HUMAN_RESOLUTION_DECISIONS):
            result["reason"] = "missing_human_decision"
            result["required_decisions"] = sorted(HUMAN_RESOLUTION_DECISIONS)
            return INVALID_TRANSITION, result
        if auto_decision_required(payload):
            resolution = payload.get("auto_resolution")
            result["auto_decision_required"] = True
            auto_decisions_path = infer_auto_decisions_path(decisions_path)
            result["auto_decisions_path"] = str(auto_decisions_path) if auto_decisions_path is not None else None
            if not isinstance(resolution, dict):
                result["reason"] = "missing_auto_resolution"
                return MALFORMED, result
            missing = sorted(
                field
                for field in AUTO_RESOLUTION_REQUIRED_FIELDS
                if not str(resolution.get(field, "") or "").strip()
            )
            if missing:
                result["reason"] = "incomplete_auto_resolution"
                result["missing_fields"] = missing
                return MALFORMED, result
            if auto_decisions_path is None:
                result["reason"] = "missing_auto_decision_log_path"
                return MALFORMED, result
            if not has_auto_decision(
                auto_decisions_path,
                task_id,
                policy_version=str(resolution.get("policy_version")),
                decision=str(resolution.get("decision")),
                target_status=str(resolution.get("target_status")),
                actor=str(resolution.get("actor")),
                mode=str(resolution.get("mode")),
            ):
                result["reason"] = "missing_auto_decision"
                result["required_auto_decision"] = {
                    "item_id": task_id,
                    "policy_version": resolution.get("policy_version"),
                    "decision": resolution.get("decision"),
                    "target_status": resolution.get("target_status"),
                    "actor": resolution.get("actor"),
                    "mode": resolution.get("mode"),
                }
                return INVALID_TRANSITION, result

    result.update({"ok": True, "reason": "valid_transition"})
    return SUCCESS, result


def print_json(payload: Dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def print_transition_table() -> None:
    rows = []
    for previous, next_values in ALLOWED.items():
        previous_label = "null" if previous is None else previous
        if next_values:
            rows.append({"previous_status": previous_label, "allowed_next": sorted(next_values)})
        else:
            rows.append({"previous_status": previous_label, "allowed_next": []})
    print_json(
        {
            "allowed_transitions": rows,
            "unchanged_allowed": sorted(UNCHANGED_ALLOWED),
            "recovery_exception": {
                "previous_status": None,
                "status": "needs_human",
                "last_transition_reason": RECOVERY_REASON,
            },
        }
    )


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a status.json workflow transition.")
    parser.add_argument("path", nargs="?", type=Path, help="Path to status.json or a task directory")
    parser.add_argument("--decisions", type=Path, help="Path to research_ops/decisions.md")
    parser.add_argument("--list", action="store_true", help="Print allowed transitions and exit")
    return parser.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)

    if args.list:
        print_transition_table()
        return SUCCESS

    if args.path is None:
        print_json({"ok": False, "reason": "missing_path"})
        return MALFORMED

    status_path = resolve_status_path(args.path)
    try:
        payload = load_status(status_path)
    except ValueError as exc:
        print_json({"ok": False, "reason": "malformed_or_missing", "error": str(exc), "path": str(status_path)})
        return MALFORMED

    decisions_path = args.decisions if args.decisions is not None else infer_decisions_path(status_path)
    code, result = validate_payload(payload, decisions_path=decisions_path)
    result["path"] = str(status_path)
    print_json(result)
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
