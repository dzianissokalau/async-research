#!/usr/bin/env python3
"""Deterministic queue-capacity gates for async research jobs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Iterable, Optional


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

    return parser.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    if args.command == "discovery-gate":
        return run_discovery_gate(args)
    print_json({"ok": False, "reason": "unknown_command", "command": args.command})
    return INVALID


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
