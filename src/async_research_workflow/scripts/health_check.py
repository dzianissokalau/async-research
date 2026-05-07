#!/usr/bin/env python3
"""Generate an async research workflow health report."""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

from async_research_workflow.idea_catalog import catalog_surface_summary
from async_research_workflow.resources import schema_path
from async_research_workflow.scripts.check_schema_versions import (
    DEFAULT_SCHEMA_VERSION,
    scan_schema_versions,
)
from async_research_workflow.scripts.data_source_audit import source_governance_report
from async_research_workflow.scripts.update_accepted_outputs_index import memory_decay_report
from async_research_workflow.scripts.validate_json_artifact import load_json, validate


SUCCESS = 0
INVALID = 4

NONTERMINAL_STATUSES = {
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
AMOUNT_FIELDS = ("amount_usd", "cost_usd", "usd", "total_usd", "api_usd", "compute_usd")
DATE_FIELDS = ("date", "created_at", "timestamp", "period_start")
INPUT_TOKEN_FIELDS = ("input_tokens", "prompt_tokens")
OUTPUT_TOKEN_FIELDS = ("output_tokens", "completion_tokens")
TOTAL_TOKEN_FIELDS = ("total_tokens",)
DEFAULT_STATUS_SCHEMA = schema_path("task_status.schema.json")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now(now: Optional[datetime] = None) -> str:
    current = now or utc_now()
    return current.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def print_json(payload: dict) -> None:
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
        try:
            parsed = datetime.strptime(value[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def safe_float(value: Any) -> Optional[float]:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def markdown_table_row_count(path: Path) -> int:
    if not path.exists():
        return 0
    count = 0
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line.startswith("|") or "---" in line:
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if cells and cells[0].lower() in {"id", "task", "item"}:
            continue
        if any(cells):
            count += 1
    return count


def load_status_schema(path: Path) -> Optional[dict]:
    try:
        schema = load_json(path)
    except ValueError:
        return None
    return schema if isinstance(schema, dict) else None


def validate_status_payload(payload: dict[str, Any], schema: Optional[dict]) -> list[dict[str, str]]:
    if schema is None:
        return []
    return [error.to_dict() for error in validate(payload, schema)]


def load_task_statuses(tasks_dir: Path, schema: Optional[dict]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    statuses: list[dict[str, Any]] = []
    malformed: list[dict[str, Any]] = []
    if not tasks_dir.exists():
        return statuses, malformed

    for status_path in sorted(tasks_dir.glob("*/status.json")):
        task_dir = status_path.parent
        try:
            payload = json.loads(status_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            malformed.append(
                {
                    "task_dir": str(task_dir),
                    "status_path": str(status_path),
                    "reason": "malformed_json",
                    "error": str(exc),
                }
            )
            continue
        except OSError as exc:
            malformed.append(
                {
                    "task_dir": str(task_dir),
                    "status_path": str(status_path),
                    "reason": "read_failed",
                    "error": str(exc),
                }
            )
            continue

        if not isinstance(payload, dict):
            malformed.append(
                {
                    "task_dir": str(task_dir),
                    "status_path": str(status_path),
                    "reason": "status_not_object",
                }
            )
            continue

        schema_errors = validate_status_payload(payload, schema)
        if schema_errors:
            malformed.append(
                {
                    "task_dir": str(task_dir),
                    "status_path": str(status_path),
                    "task_id": payload.get("id", task_dir.name),
                    "reason": "schema_validation_failed",
                    "errors": schema_errors,
                }
            )

        statuses.append({"task_dir": task_dir, "status_path": status_path, "payload": payload})
    return statuses, malformed


def lock_owner(task_dir: Path) -> dict[str, Any]:
    owner_path = task_dir / "LOCK" / "owner.json"
    try:
        owner = json.loads(owner_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}
    return owner if isinstance(owner, dict) else {}


def scan_stale_locks(tasks_dir: Path, stale_minutes: float) -> list[dict[str, Any]]:
    stale: list[dict[str, Any]] = []
    now_ts = time.time()
    if not tasks_dir.exists():
        return stale
    for lock_dir in sorted(tasks_dir.glob("*/LOCK")):
        if not lock_dir.is_dir():
            continue
        task_dir = lock_dir.parent
        age_minutes = (now_ts - lock_dir.stat().st_mtime) / 60
        if age_minutes >= stale_minutes:
            stale.append(
                {
                    "task_dir": str(task_dir),
                    "lock_dir": str(lock_dir),
                    "age_minutes": round(age_minutes, 2),
                    "owner": lock_owner(task_dir),
                }
            )
    return stale


def status_counts(statuses: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in statuses:
        status = str(item["payload"].get("status", "unknown"))
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items()))


def revision_limit_breaches(statuses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    breaches: list[dict[str, Any]] = []
    for item in statuses:
        payload = item["payload"]
        revision_count = payload.get("revision_count")
        max_revisions = payload.get("max_revisions")
        limit_hit = payload.get("revision_limit_hit") is True
        if (
            limit_hit
            or (
                isinstance(revision_count, int)
                and not isinstance(revision_count, bool)
                and isinstance(max_revisions, int)
                and not isinstance(max_revisions, bool)
                and revision_count >= max_revisions
            )
        ):
            breaches.append(
                {
                    "task_id": payload.get("id", item["task_dir"].name),
                    "task_dir": str(item["task_dir"]),
                    "status": payload.get("status"),
                    "revision_count": revision_count,
                    "max_revisions": max_revisions,
                    "revision_limit_hit": limit_hit,
                }
            )
    return breaches


def stuck_tasks(
    statuses: list[dict[str, Any]],
    stuck_days: float,
    in_progress_stuck_hours: float,
    now: datetime,
) -> list[dict[str, Any]]:
    stuck: list[dict[str, Any]] = []
    general_cutoff = now - timedelta(days=stuck_days)
    in_progress_cutoff = now - timedelta(hours=in_progress_stuck_hours)

    for item in statuses:
        payload = item["payload"]
        status = payload.get("status")
        if status not in NONTERMINAL_STATUSES:
            continue
        updated_at = parse_datetime(payload.get("updated_at"))
        if updated_at is None:
            continue
        cutoff = in_progress_cutoff if status == "in_progress" else general_cutoff
        if updated_at <= cutoff:
            stuck.append(
                {
                    "task_id": payload.get("id", item["task_dir"].name),
                    "task_dir": str(item["task_dir"]),
                    "status": status,
                    "updated_at": updated_at.isoformat().replace("+00:00", "Z"),
                    "age_hours": round((now - updated_at).total_seconds() / 3600, 2),
                }
            )
    return stuck


def row_amount(row: dict[str, str]) -> float:
    for field in AMOUNT_FIELDS:
        value = safe_float(row.get(field))
        if value is not None:
            return value
    return 0.0


def row_date(row: dict[str, str]) -> Optional[datetime]:
    for field in DATE_FIELDS:
        parsed = parse_datetime(row.get(field))
        if parsed is not None:
            return parsed
    return None


def row_int(row: dict[str, str], fields: tuple[str, ...]) -> int:
    for field in fields:
        value = safe_float(row.get(field))
        if value is not None and value >= 0:
            return int(value)
    return 0


def max_budget_from_ledger(rows: list[dict[str, str]], field: str) -> Optional[float]:
    values = [safe_float(row.get(field)) for row in rows]
    values = [value for value in values if value is not None and value > 0]
    return max(values) if values else None


def scan_cost_ledger(
    ledger_path: Path,
    monthly_budget_usd: Optional[float],
    weekly_budget_usd: Optional[float],
    now: datetime,
) -> dict[str, Any]:
    if not ledger_path.exists():
        return {
            "ledger_path": str(ledger_path),
            "exists": False,
            "monthly_cost_usd": 0.0,
            "weekly_cost_usd": 0.0,
            "monthly_budget_usd": monthly_budget_usd,
            "weekly_budget_usd": weekly_budget_usd,
            "monthly_usage_ratio": None,
            "weekly_usage_ratio": None,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "actual_usage_rows": 0,
        }

    rows: list[dict[str, str]] = []
    with ledger_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append({str(k): str(v) for k, v in row.items() if k is not None})

    monthly_budget = monthly_budget_usd or max_budget_from_ledger(rows, "monthly_budget_usd")
    weekly_budget = weekly_budget_usd or max_budget_from_ledger(rows, "weekly_budget_usd")

    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    week_start = now - timedelta(days=now.weekday())
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)

    monthly_cost = 0.0
    weekly_cost = 0.0
    undated_cost = 0.0
    input_tokens = 0
    output_tokens = 0
    total_tokens = 0
    actual_usage_rows = 0
    for row in rows:
        amount = row_amount(row)
        parsed_date = row_date(row)
        row_input = row_int(row, INPUT_TOKEN_FIELDS)
        row_output = row_int(row, OUTPUT_TOKEN_FIELDS)
        row_total = row_int(row, TOTAL_TOKEN_FIELDS) or row_input + row_output
        input_tokens += row_input
        output_tokens += row_output
        total_tokens += row_total
        if row.get("actual", "").strip().lower() == "true" and row_total > 0:
            actual_usage_rows += 1
        if parsed_date is None:
            undated_cost += amount
            continue
        if parsed_date >= month_start:
            monthly_cost += amount
        if parsed_date >= week_start:
            weekly_cost += amount

    if rows and all(row_date(row) is None for row in rows):
        monthly_cost = undated_cost
        weekly_cost = undated_cost

    return {
        "ledger_path": str(ledger_path),
        "exists": True,
        "row_count": len(rows),
        "monthly_cost_usd": round(monthly_cost, 4),
        "weekly_cost_usd": round(weekly_cost, 4),
        "monthly_budget_usd": monthly_budget,
        "weekly_budget_usd": weekly_budget,
        "monthly_usage_ratio": round(monthly_cost / monthly_budget, 4) if monthly_budget else None,
        "weekly_usage_ratio": round(weekly_cost / weekly_budget, 4) if weekly_budget else None,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "actual_usage_rows": actual_usage_rows,
    }


def add_alert(alerts: list[dict[str, Any]], severity: str, check: str, message: str, details: Any = None) -> None:
    alert: dict[str, Any] = {
        "severity": severity,
        "check": check,
        "message": message,
    }
    if details is not None:
        alert["details"] = details
    alerts.append(alert)


def append_daily_status(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "",
        f"## Health Check {report['generated_at']}",
        "",
        f"- Alert count: {report['summary']['alert_count']}",
        f"- Task count: {report['summary']['task_count']}",
        f"- Needs human: {report['checks']['status_counts'].get('needs_human', 0)}",
        f"- In progress: {report['checks']['status_counts'].get('in_progress', 0)}",
        f"- Stale locks: {len(report['checks']['stale_locks'])}",
        f"- Revision limit breaches: {len(report['checks']['revision_limit_breaches'])}",
    ]
    if report["alerts"]:
        lines.append("- Alerts:")
        for alert in report["alerts"]:
            lines.append(f"  - [{alert['severity']}] {alert['check']}: {alert['message']}")
    else:
        lines.append("- Alerts: none")
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    ops_dir = args.ops_dir
    tasks_dir = ops_dir / "tasks"
    now = parse_datetime(args.now) if args.now else utc_now()
    if now is None:
        now = utc_now()
    schema = load_status_schema(args.status_schema)
    statuses, malformed = load_task_statuses(tasks_dir, schema)
    counts = status_counts(statuses)
    stale = scan_stale_locks(tasks_dir, args.stale_lock_minutes)
    revision_breaches = revision_limit_breaches(statuses)
    stuck = stuck_tasks(statuses, args.stuck_days, args.in_progress_stuck_hours, now)
    queue_depth = markdown_table_row_count(ops_dir / "queue.md")
    discovery_count = markdown_table_row_count(ops_dir / "discovery_inbox.md")
    schema_versions = scan_schema_versions(ops_dir, args.expected_schema_version)
    source_governance = source_governance_report(ops_dir, now)
    accepted_memory = memory_decay_report(ops_dir, now=now)
    idea_catalog = catalog_surface_summary(ops_dir)
    cost = scan_cost_ledger(
        ops_dir / "cost_ledger.csv",
        args.monthly_budget_usd,
        args.weekly_budget_usd,
        now,
    )

    alerts: list[dict[str, Any]] = []
    if stale:
        add_alert(alerts, "warning", "stale_locks", f"{len(stale)} stale lock(s) detected", stale)
    if queue_depth > args.queue_depth_threshold:
        add_alert(alerts, "warning", "queue_depth", f"queue depth {queue_depth} exceeds threshold {args.queue_depth_threshold}")
    if counts.get("needs_human", 0) > args.needs_human_threshold:
        add_alert(
            alerts,
            "warning",
            "needs_human_overload",
            f"needs_human count {counts.get('needs_human', 0)} exceeds threshold {args.needs_human_threshold}",
        )
    if counts.get("in_progress", 0) > args.in_progress_threshold:
        add_alert(
            alerts,
            "warning",
            "in_progress_overload",
            f"in_progress count {counts.get('in_progress', 0)} exceeds threshold {args.in_progress_threshold}",
        )
    if revision_breaches:
        add_alert(
            alerts,
            "warning",
            "revision_limit_breaches",
            f"{len(revision_breaches)} task(s) hit revision limits",
            revision_breaches,
        )
    if discovery_count > args.discovery_inbox_threshold:
        add_alert(
            alerts,
            "warning",
            "discovery_inbox_overload",
            f"discovery inbox count {discovery_count} exceeds threshold {args.discovery_inbox_threshold}",
        )
    if malformed:
        add_alert(
            alerts,
            "error",
            "malformed_status_files",
            f"{len(malformed)} malformed or schema-invalid status file(s)",
            malformed,
        )
    schema_version_issue_count = schema_versions["warning_count"] + schema_versions["error_count"]
    if schema_version_issue_count:
        add_alert(
            alerts,
            "warning",
            "schema_version_warnings",
            f"{schema_version_issue_count} JSON artifact(s) need schema version attention",
            {
                "expected_schema_version": schema_versions["expected_schema_version"],
                "warnings": schema_versions["warnings"],
                "errors": schema_versions["errors"],
            },
        )
    if stuck:
        add_alert(alerts, "warning", "stuck_tasks", f"{len(stuck)} task(s) stuck in the same status", stuck)
    if source_governance.get("error_count", 0):
        add_alert(
            alerts,
            "error",
            "source_governance_errors",
            f"{source_governance.get('error_count', 0)} source-governance error(s)",
            source_governance.get("errors"),
        )
    stale_sources = source_governance.get("stale_sources") if isinstance(source_governance.get("stale_sources"), list) else []
    if stale_sources:
        add_alert(
            alerts,
            "warning",
            "source_freshness_warnings",
            f"{len(stale_sources)} source(s) are past freshness window",
            stale_sources,
        )
    if accepted_memory.get("stale_count", 0):
        add_alert(
            alerts,
            "warning",
            "stale_accepted_evidence",
            f"{accepted_memory.get('stale_count', 0)} accepted output(s) are past their freshness window",
            accepted_memory.get("stale_outputs"),
        )
    if accepted_memory.get("due_count", 0):
        add_alert(
            alerts,
            "warning",
            "accepted_memory_revalidation_due",
            f"{accepted_memory.get('due_count', 0)} accepted output(s) are due for revalidation soon",
            accepted_memory.get("due_outputs"),
        )
    if idea_catalog["failure_count"]:
        add_alert(
            alerts,
            "warning",
            "idea_catalog_state",
            f"idea catalog has {idea_catalog['failure_count']} validation failure(s)",
            {
                "validation_exit_code": idea_catalog["validation_exit_code"],
                "failures": idea_catalog["failures"],
            },
        )
    elif idea_catalog["stale_projection_warnings"]:
        add_alert(
            alerts,
            "warning",
            "idea_catalog_projection_stale",
            f"idea catalog has {len(idea_catalog['stale_projection_warnings'])} stale projection warning(s)",
            idea_catalog["stale_projection_warnings"],
        )

    monthly_ratio = cost.get("monthly_usage_ratio")
    if monthly_ratio is not None and monthly_ratio >= args.budget_threshold:
        add_alert(
            alerts,
            "warning",
            "monthly_budget_threshold",
            f"monthly cost is {monthly_ratio:.0%} of budget",
            cost,
        )
    weekly_ratio = cost.get("weekly_usage_ratio")
    if weekly_ratio is not None and weekly_ratio >= args.budget_threshold:
        add_alert(
            alerts,
            "warning",
            "weekly_budget_threshold",
            f"weekly cost is {weekly_ratio:.0%} of budget",
            cost,
        )

    return {
        "schema_version": "1.0",
        "generated_at": iso_now(now),
        "ops_dir": str(ops_dir),
        "summary": {
            "task_count": len(statuses),
            "alert_count": len(alerts),
            "highest_severity": "error" if any(alert["severity"] == "error" for alert in alerts) else ("warning" if alerts else "ok"),
        },
        "alerts": alerts,
        "checks": {
            "status_counts": counts,
            "queue_depth": queue_depth,
            "discovery_inbox_count": discovery_count,
            "stale_locks": stale,
            "revision_limit_breaches": revision_breaches,
            "malformed_status_files": malformed,
            "schema_version_warnings": schema_versions,
            "stuck_tasks": stuck,
            "cost": cost,
            "source_governance": source_governance,
            "accepted_memory": accepted_memory,
            "idea_catalog": idea_catalog,
        },
        "thresholds": {
            "stale_lock_minutes": args.stale_lock_minutes,
            "queue_depth": args.queue_depth_threshold,
            "needs_human": args.needs_human_threshold,
            "in_progress": args.in_progress_threshold,
            "discovery_inbox": args.discovery_inbox_threshold,
            "budget_ratio": args.budget_threshold,
            "stuck_days": args.stuck_days,
            "in_progress_stuck_hours": args.in_progress_stuck_hours,
            "expected_schema_version": args.expected_schema_version,
        },
    }


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate async research health_report.json.")
    parser.add_argument("ops_dir", nargs="?", type=Path, default=Path("research_ops"))
    parser.add_argument("--status-schema", type=Path, default=DEFAULT_STATUS_SCHEMA)
    parser.add_argument("--stale-lock-minutes", type=float, default=60.0)
    parser.add_argument("--queue-depth-threshold", type=int, default=20)
    parser.add_argument("--needs-human-threshold", type=int, default=3)
    parser.add_argument("--in-progress-threshold", type=int, default=3)
    parser.add_argument("--discovery-inbox-threshold", type=int, default=20)
    parser.add_argument("--budget-threshold", type=float, default=0.8)
    parser.add_argument("--expected-schema-version", default=DEFAULT_SCHEMA_VERSION)
    parser.add_argument("--monthly-budget-usd", type=float)
    parser.add_argument("--weekly-budget-usd", type=float)
    parser.add_argument("--stuck-days", type=float, default=7.0)
    parser.add_argument("--in-progress-stuck-hours", type=float, default=24.0)
    parser.add_argument("--report-path", type=Path)
    parser.add_argument("--daily-status-path", type=Path)
    parser.add_argument("--no-daily-status", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--now", help="Override current time for deterministic tests, ISO-8601.")
    return parser.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    report = build_report(args)
    report_path = args.report_path or args.ops_dir / "health_report.json"
    daily_status_path = args.daily_status_path or args.ops_dir / "daily_status.md"

    if not args.dry_run:
        atomic_write_json(report_path, report)
        if not args.no_daily_status:
            append_daily_status(daily_status_path, report)

    print_json(
        {
            "ok": True,
            "action": "dry_run_health_checked" if args.dry_run else "health_checked",
            "report_path": str(report_path),
            "daily_status_path": None if args.no_daily_status else str(daily_status_path),
            "alert_count": report["summary"]["alert_count"],
            "highest_severity": report["summary"]["highest_severity"],
        }
    )
    return SUCCESS


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
