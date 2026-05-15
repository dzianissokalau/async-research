#!/usr/bin/env python3
"""Deterministic queue-capacity gates for async research jobs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Iterable, Optional

from async_research_workflow.console import snapshot as console_snapshot


SUCCESS = 0
SKIP = 2
INVALID = 4

DEFAULT_ACTIVE_STATUSES = {
    "inbox",
    "ready_for_planning",
    "ready_for_worker",
    "in_progress",
    "awaiting_review",
    "single_review",
    "panel_review",
    "needs_revision",
    "needs_human",
}
LIST_GROUPS = ("all", "active", "ready_for_worker", "in_progress", "review", "human", "blocked", "malformed")


class QueueCapacityParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        print_json({"ok": False, "reason": "invalid_invocation", "error": message})
        raise SystemExit(INVALID)


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def load_task_status(path: Path) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, "missing_status_json"
    except json.JSONDecodeError as exc:
        return None, f"malformed_status_json: {exc}"
    except OSError as exc:
        return None, f"status_read_failed: {exc}"
    if not isinstance(payload, dict):
        return None, "status_json_not_object"
    return payload, None


def scan_tasks(ops_dir: Path, active_statuses: set[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    active: list[dict[str, Any]] = []
    malformed: list[dict[str, Any]] = []
    tasks_dir = ops_dir / "tasks"
    if not tasks_dir.exists():
        return active, malformed

    for status_path in sorted(tasks_dir.glob("*/status.json")):
        task_dir = status_path.parent
        payload, error = load_task_status(status_path)
        if error is not None:
            malformed.append({"task_dir": str(task_dir), "status_path": str(status_path), "reason": error})
            continue
        assert payload is not None
        status = payload.get("status")
        if status in active_statuses:
            active.append(
                {
                    "task_id": payload.get("id", task_dir.name),
                    "task_dir": str(task_dir),
                    "status": status,
                    "priority": payload.get("priority"),
                    "updated_at": payload.get("updated_at"),
                }
            )
    return active, malformed


def run_discovery_gate(args: argparse.Namespace) -> int:
    active_statuses = set(args.active_status or DEFAULT_ACTIVE_STATUSES)
    active, malformed = scan_tasks(args.ops_dir, active_statuses)
    blocked = bool(malformed) or len(active) > args.max_active
    reason = None
    if malformed:
        reason = "malformed_status_files"
    elif blocked:
        reason = "active_queue_over_capacity"
    else:
        reason = "capacity_available"

    print_json(
        {
            "ok": not blocked,
            "action": "discovery_skipped" if blocked else "discovery_allowed",
            "reason": reason,
            "ops_dir": str(args.ops_dir),
            "active_task_count": len(active),
            "max_active": args.max_active,
            "active_statuses": sorted(active_statuses),
            "active_tasks": active,
            "malformed_status_files": malformed,
            "next_step": (
                "skip discovery and append a brief daily_status.md note"
                if blocked
                else "continue discovery"
            ),
        }
    )
    return SKIP if blocked else SUCCESS


def queue_row(row: dict[str, Any], include_files: bool) -> dict[str, Any]:
    result = {
        "task_id": row.get("task_id"),
        "title": row.get("title"),
        "status": row.get("status"),
        "previous_status": row.get("previous_status"),
        "type": row.get("type"),
        "requires_human": row.get("requires_human"),
        "human_gate_reason": row.get("human_gate_reason"),
        "revision_count": row.get("revision_count"),
        "max_revisions": row.get("max_revisions"),
        "revision_limit_hit": row.get("revision_limit_hit"),
        "lock_state": row.get("lock_state"),
        "status_validation": row.get("status_validation"),
        "transition_validation": row.get("transition_validation"),
        "task_dir": row.get("task_dir"),
        "status_path": row.get("status_path"),
    }
    if include_files:
        result["files"] = row.get("files", [])
    return result


def group_rows(tasks: dict[str, Any], group: str) -> list[dict[str, Any]]:
    all_rows = tasks.get("all") if isinstance(tasks.get("all"), list) else []
    if group == "all":
        return [row for row in all_rows if isinstance(row, dict)]
    if group in {"active", "review", "human", "blocked"}:
        rows = tasks.get(group) if isinstance(tasks.get(group), list) else []
        return [row for row in rows if isinstance(row, dict)]
    if group == "ready_for_worker":
        return [row for row in all_rows if isinstance(row, dict) and row.get("status") == "ready_for_worker"]
    if group == "in_progress":
        return [row for row in all_rows if isinstance(row, dict) and row.get("status") == "in_progress"]
    if group == "malformed":
        return [
            row
            for row in all_rows
            if isinstance(row, dict)
            and isinstance(row.get("status_validation"), dict)
            and row["status_validation"].get("valid") is False
        ]
    return []


def status_filtered(rows: list[dict[str, Any]], statuses: list[str] | None) -> list[dict[str, Any]]:
    if not statuses or "all" in statuses:
        return rows
    accepted = set(statuses)
    return [row for row in rows if str(row.get("status")) in accepted]


def sorted_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda row: (str(row.get("task_id") or ""), str(row.get("status") or ""), str(row.get("task_dir") or "")))


def run_list(args: argparse.Namespace) -> int:
    if args.limit < 0:
        print_json(
            {
                "ok": False,
                "action": "queue_list_refused",
                "reason": "invalid_limit",
                "limit": args.limit,
                "read_only": True,
                "changed": False,
                "next_step": "rerun queue list with --limit 0 or a positive integer",
            }
        )
        return INVALID
    if not args.ops_dir.exists() or not args.ops_dir.is_dir():
        print_json(
            {
                "ok": False,
                "action": "queue_list_refused",
                "reason": "ops_dir_missing",
                "ops_dir": str(args.ops_dir),
                "read_only": True,
                "changed": False,
                "next_step": f"initialize a workspace before listing tasks: async-research init {args.ops_dir}",
            }
        )
        return INVALID

    snapshot = console_snapshot.snapshot(args.ops_dir)
    tasks = snapshot.get("tasks") if isinstance(snapshot.get("tasks"), dict) else {}
    rows = sorted_rows(status_filtered(group_rows(tasks, args.group), args.status))
    limit = args.limit
    returned = rows[:limit] if limit else rows
    all_rows = tasks.get("all") if isinstance(tasks.get("all"), list) else []
    ready_for_worker_count = sum(1 for row in all_rows if isinstance(row, dict) and row.get("status") == "ready_for_worker")
    in_progress_count = sum(1 for row in all_rows if isinstance(row, dict) and row.get("status") == "in_progress")
    malformed_rows = group_rows(tasks, "malformed")
    print_json(
        {
            "ok": True,
            "action": "queue_listed",
            "ops_dir": str(args.ops_dir),
            "read_only": True,
            "changed": False,
            "group": args.group,
            "status_filter": args.status or [],
            "limit": limit,
            "tasks": [queue_row(row, args.include_files) for row in returned],
            "summary": {
                "task_total": tasks.get("total", 0),
                "board_total": tasks.get("board_total", 0),
                "status_counts": tasks.get("status_counts", {}),
                "active_count": len(tasks.get("active", []) if isinstance(tasks.get("active"), list) else []),
                "ready_for_worker_count": ready_for_worker_count,
                "in_progress_count": in_progress_count,
                "review_count": len(tasks.get("review", []) if isinstance(tasks.get("review"), list) else []),
                "human_count": len(tasks.get("human", []) if isinstance(tasks.get("human"), list) else []),
                "blocked_count": len(tasks.get("blocked", []) if isinstance(tasks.get("blocked"), list) else []),
                "malformed_status_count": len(tasks.get("malformed_statuses", []) if isinstance(tasks.get("malformed_statuses"), list) else []),
                "malformed_row_count": len(malformed_rows),
                "stale_lock_count": len(tasks.get("stale_locks", []) if isinstance(tasks.get("stale_locks"), list) else []),
                "filtered_count": len(rows),
                "returned_count": len(returned),
                "truncated": bool(limit and len(rows) > limit),
            },
            "available_groups": list(LIST_GROUPS),
            "next_step": f"run async-research workflow next {args.ops_dir} to choose the next safe action",
        }
    )
    return SUCCESS


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = QueueCapacityParser(description="Check async research queue capacity.")
    subparsers = parser.add_subparsers(dest="command", required=True, parser_class=QueueCapacityParser)

    discovery = subparsers.add_parser("discovery-gate", help="Skip discovery when active task capacity is overloaded.")
    discovery.add_argument("ops_dir", type=Path)
    discovery.add_argument("--max-active", type=int, default=10)
    discovery.add_argument(
        "--active-status",
        action="append",
        help="Status counted as active. Repeat to override the default active-status set.",
    )
    list_cmd = subparsers.add_parser("list", help="List queue and task-board state without mutating the workspace.")
    list_cmd.add_argument("ops_dir", type=Path)
    list_cmd.add_argument("--group", choices=LIST_GROUPS, default="all", help="Task group to return.")
    list_cmd.add_argument("--status", action="append", help="Only include tasks with this status. Repeat to include multiple statuses.")
    list_cmd.add_argument("--limit", type=int, default=50, help="Maximum rows to return; use 0 for no limit.")
    list_cmd.add_argument("--include-files", action="store_true", help="Include task-local file link metadata.")

    return parser.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    if args.command == "discovery-gate":
        return run_discovery_gate(args)
    if args.command == "list":
        return run_list(args)
    print_json({"ok": False, "reason": "unknown_command", "command": args.command})
    return INVALID


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
