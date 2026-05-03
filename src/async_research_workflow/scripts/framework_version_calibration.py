#!/usr/bin/env python3
"""Group accepted async research outputs by framework version."""

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

from version_metadata import DEFAULT_FRAMEWORK_VERSIONS, normalized_versions, version_summary


SUCCESS = 0
INVALID = 2


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def parse_datetime(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def month_key(value: Any) -> str:
    parsed = parse_datetime(value)
    if parsed is None:
        return "unknown"
    return parsed.strftime("%Y-%m")


def load_json_object(path: Path) -> Optional[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def accepted_tasks(ops_dir: Path, month: Optional[str]) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for status_path in sorted((ops_dir / "tasks").glob("*/status.json")):
        status = load_json_object(status_path)
        if not status or status.get("status") != "accepted":
            continue
        task_month = month_key(status.get("updated_at") or status.get("created_at"))
        if month is not None and task_month != month:
            continue
        tasks.append(
            {
                "task_id": str(status.get("id") or status_path.parent.name),
                "title": str(status.get("title") or status_path.parent.name),
                "task_dir": str(status_path.parent),
                "month": task_month,
                **version_summary(status),
            }
        )
    return tasks


def group_by_framework(tasks: list[dict[str, Any]]) -> dict[str, dict[str, list[dict[str, str]]]]:
    framework_names = sorted(DEFAULT_FRAMEWORK_VERSIONS)
    groups: dict[str, dict[str, list[dict[str, str]]]] = {name: {} for name in framework_names}
    for task in tasks:
        versions = normalized_versions(task.get("framework_versions"))
        for framework in framework_names:
            version = versions.get(framework, "unknown")
            groups[framework].setdefault(version, []).append(
                {
                    "task_id": task["task_id"],
                    "title": task["title"],
                    "month": task["month"],
                    "task_dir": task["task_dir"],
                }
            )
    return groups


def build_report(ops_dir: Path, month: Optional[str]) -> dict[str, Any]:
    tasks = accepted_tasks(ops_dir, month)
    return {
        "ok": True,
        "ops_dir": str(ops_dir),
        "month": month or "all",
        "accepted_task_count": len(tasks),
        "accepted_tasks": tasks,
        "framework_groups": group_by_framework(tasks),
    }


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def markdown_report(report: dict[str, Any]) -> str:
    lines = [
        f"# Framework Version Calibration: {report['month']}",
        "",
        f"Accepted tasks: {report['accepted_task_count']}",
        "",
    ]
    for framework, versions in report["framework_groups"].items():
        lines.extend([f"## {framework}", ""])
        if not versions:
            lines.extend(["No accepted outputs.", ""])
            continue
        for version, tasks in sorted(versions.items()):
            lines.append(f"### {version}")
            if not tasks:
                lines.append("- none")
            for task in tasks:
                lines.append(f"- {task['task_id']}: {task['title']}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Group accepted outputs by framework version for calibration.")
    parser.add_argument("ops_dir", nargs="?", type=Path, default=Path("research_ops"))
    parser.add_argument("--month", help="Optional YYYY-MM month filter.")
    parser.add_argument("--output", type=Path, help="Optional markdown report path.")
    return parser.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    if not args.ops_dir.exists():
        print_json({"ok": False, "reason": "ops_dir_missing", "ops_dir": str(args.ops_dir)})
        return INVALID

    report = build_report(args.ops_dir, args.month)
    if args.output:
        atomic_write_text(args.output, markdown_report(report))
        report["output"] = str(args.output)
    print_json(report)
    return SUCCESS


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
