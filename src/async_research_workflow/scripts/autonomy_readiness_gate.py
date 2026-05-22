#!/usr/bin/env python3
"""Pre-loop readiness gate for autonomous async research runs.

The gate is intentionally stricter than a health report. It answers the
scheduler-facing question: should the next autonomous loop start now?
"""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any, Iterable, Optional

from async_research_workflow.idea_catalog import catalog_surface_summary
from async_research_workflow.scripts.check_schema_versions import (
    DEFAULT_SCHEMA_VERSION,
    scan_schema_versions,
)
from async_research_workflow.scripts import needs_human_policy
from async_research_workflow.scripts.data_foundations import data_foundation_report
from async_research_workflow.scripts import knowledge_library
from async_research_workflow.scripts.analysis_surface import analysis_dashboard_report
from async_research_workflow.scripts.data_source_audit import (
    EXPERIMENT_READY_STATUSES,
    parse_register,
    validate_rows,
)
from async_research_workflow.scripts.health_check import (
    DEFAULT_STATUS_SCHEMA,
    load_status_schema,
    load_task_statuses,
    lock_owner,
    markdown_table_row_count,
    parse_datetime,
    scan_cost_ledger,
    status_counts,
)
from async_research_workflow.scripts.metrics_history import read_history
from async_research_workflow.scripts.update_accepted_outputs_index import memory_decay_report


SUCCESS = 0
WARNINGS = 2
SKIP_LOOP = 3
INVALID_STATE = 4
HUMAN_REQUIRED = 5

SCHEMA_VERSION = "1.0"
ACTIVE_STATUSES = {
    "inbox",
    "ready_for_planning",
    "ready_for_worker",
    "in_progress",
    "awaiting_review",
    "single_review",
    "panel_review",
    "needs_revision",
}
REVIEW_QUEUE_STATUSES = {"awaiting_review", "single_review", "panel_review"}
SOURCE_GOVERNED_TASK_TYPES = {"experiment_plan", "run_analysis", "evaluate_results"}
LIBRARY_SUPPORT_REQUIRED_TASK_TYPES = {"hypothesis_card", "experiment_plan"}
REQUIRED_OPERATIONAL_FILES = [
    "queue.md",
    "daily_status.md",
    "data_source_audit.md",
    "cost_ledger.csv",
    "metrics_baseline.json",
    "metrics_history.jsonl",
    "accepted_outputs_index.md",
    "evidence_ledger.md",
    "rejected_results.md",
    "discovery_inbox.md",
    "decisions.md",
    "weekly_digest.md",
    "escalation_policy.md",
]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now(now: Optional[datetime] = None) -> str:
    current = now or utc_now()
    return current.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def normalize_key(value: Any) -> str:
    return " ".join(str(value or "").lower().split())


def issue(
    severity: str,
    check: str,
    message: str,
    details: Any = None,
    action: str = "inspect and resolve before running autonomous workers",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "severity": severity,
        "check": check,
        "message": message,
        "blocking": severity == "error",
        "action": action,
    }
    if details is not None:
        payload["details"] = details
    return payload


def required_file_issues(ops_dir: Path) -> list[dict[str, Any]]:
    missing = []
    for relative in REQUIRED_OPERATIONAL_FILES:
        path = ops_dir / relative
        if not path.exists():
            missing.append({"path": str(path), "reason": "missing_required_operational_file"})
    if not missing:
        return []
    return [
        issue(
            "error",
            "missing_operational_files",
            f"{len(missing)} required operational file(s) missing",
            missing,
            "restore the starter pack file or regenerate it before scheduling workers",
        )
    ]


def active_tasks(statuses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in statuses if item["payload"].get("status") in ACTIVE_STATUSES]


def review_queue_tasks(statuses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in statuses if item["payload"].get("status") in REVIEW_QUEUE_STATUSES]


def needs_human_tasks(statuses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tasks = []
    for item in statuses:
        payload = item["payload"]
        if payload.get("status") == "needs_human" or payload.get("requires_human") is True:
            tasks.append(
                {
                    "task_id": payload.get("id", item["task_dir"].name),
                    "task_dir": str(item["task_dir"]),
                    "status_path": str(item["status_path"]),
                    "status": payload.get("status"),
                    "human_gate_reason": payload.get("human_gate_reason"),
                }
            )
    return tasks


def mode_policy_needs_human_routes(statuses: list[dict[str, Any]], ops_dir: Path) -> list[dict[str, Any]]:
    routes: list[dict[str, Any]] = []
    for item in statuses:
        payload = item["payload"]
        if payload.get("status") != "needs_human":
            continue
        resolution = needs_human_policy.evaluate_policy(ops_dir, item["task_dir"], payload)
        routes.append(
            {
                "task_id": payload.get("id", item["task_dir"].name),
                "task_dir": str(item["task_dir"]),
                "status_path": str(item["status_path"]),
                "status": payload.get("status"),
                "human_gate_reason": payload.get("human_gate_reason"),
                "can_auto_resolve": resolution.get("can_auto_resolve") is True,
                "human_required": resolution.get("human_required") is True,
                "mode": resolution.get("mode"),
                "gate_category": resolution.get("gate_category"),
                "gate_categories": resolution.get("gate_categories", []),
                "policy_reason": resolution.get("reason"),
                "target_status": resolution.get("target_status"),
                "policy_action": resolution.get("policy_action"),
                "resolution": resolution,
            }
        )
    return routes


def source_governance_applies(payload: dict[str, Any]) -> bool:
    return str(payload.get("type") or "").strip() in SOURCE_GOVERNED_TASK_TYPES


def source_dependent_governed_tasks(statuses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for item in active_tasks(statuses):
        payload = item["payload"]
        refs = payload.get("data_audit_refs")
        if not source_governance_applies(payload) or not isinstance(refs, list) or not refs:
            continue
        tasks.append(
            {
                "task_id": payload.get("id", item["task_dir"].name),
                "task_dir": str(item["task_dir"]),
                "status_path": str(item["status_path"]),
                "status": payload.get("status"),
                "type": payload.get("type"),
                "data_audit_refs": [ref for ref in refs if isinstance(ref, str)],
            }
        )
    return tasks


def idea_library_refs(ops_dir: Path, idea_id: str) -> list[str]:
    if not idea_id:
        return []
    path = ops_dir / "ideas" / f"{idea_id}.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    refs = payload.get("library_refs") if isinstance(payload, dict) else None
    if not isinstance(refs, list):
        return []
    return [str(ref).strip() for ref in refs if str(ref).strip()]


def task_library_refs(ops_dir: Path, payload: dict[str, Any]) -> list[str]:
    refs = payload.get("library_refs")
    if isinstance(refs, list):
        direct = [str(ref).strip() for ref in refs if str(ref).strip()]
        if direct:
            return direct
    required_sources = payload.get("required_sources")
    if isinstance(required_sources, dict) and isinstance(required_sources.get("library_refs"), list):
        nested = [str(ref).strip() for ref in required_sources["library_refs"] if str(ref).strip()]
        if nested:
            return nested
    idea_id = str(payload.get("catalog_idea_id") or "").strip()
    if not idea_id:
        catalog_promotion = payload.get("catalog_promotion")
        if isinstance(catalog_promotion, dict):
            idea_id = str(catalog_promotion.get("catalog_idea_id") or "").strip()
    return idea_library_refs(ops_dir, idea_id)


def library_dependent_tasks(statuses: list[dict[str, Any]], ops_dir: Path) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for item in active_tasks(statuses):
        payload = item["payload"]
        task_type = str(payload.get("type") or "").strip()
        if task_type not in LIBRARY_SUPPORT_REQUIRED_TASK_TYPES:
            continue
        refs = task_library_refs(ops_dir, payload)
        if not refs:
            continue
        tasks.append(
            {
                "task_id": payload.get("id", item["task_dir"].name),
                "task_dir": str(item["task_dir"]),
                "status_path": str(item["status_path"]),
                "status": payload.get("status"),
                "type": task_type,
                "library_refs": refs,
            }
        )
    return tasks


def scan_stale_locks_at(tasks_dir: Path, stale_minutes: float, now: datetime) -> list[dict[str, Any]]:
    stale: list[dict[str, Any]] = []
    now_ts = now.timestamp()
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


def duplicate_active_tasks(statuses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in active_tasks(statuses):
        payload = item["payload"]
        key = (normalize_key(payload.get("type")), normalize_key(payload.get("title")))
        if not key[0] or not key[1]:
            continue
        grouped[key].append(
            {
                "task_id": payload.get("id", item["task_dir"].name),
                "task_dir": str(item["task_dir"]),
                "status_path": str(item["status_path"]),
                "status": payload.get("status"),
                "type": payload.get("type"),
                "title": payload.get("title"),
            }
        )
    duplicates = []
    for (task_type, title), tasks in sorted(grouped.items()):
        if len(tasks) > 1:
            duplicates.append({"type": task_type, "title": title, "tasks": tasks})
    return duplicates


def schema_issues(ops_dir: Path, expected_version: str) -> list[dict[str, Any]]:
    scan = scan_schema_versions(ops_dir, expected_version)
    if scan["error_count"] == 0 and scan["warning_count"] == 0:
        return []
    return [
        issue(
            "error",
            "schema_version_validity",
            f"{scan['error_count'] + scan['warning_count']} schema-version issue(s) detected",
            {
                "expected_schema_version": scan["expected_schema_version"],
                "errors": scan["errors"],
                "warnings": scan["warnings"],
            },
            "run check_schema_versions.py and repair or quarantine invalid artifacts",
        )
    ]


def status_issues(malformed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not malformed:
        return []
    return [
        issue(
            "error",
            "malformed_or_partial_status",
            f"{len(malformed)} malformed, partial, or schema-invalid status file(s)",
            malformed,
            "run recover_status_json.py on each affected task before scheduling workers",
        )
    ]


def data_source_rows(ops_dir: Path) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    path = ops_dir / "data_source_audit.md"
    try:
        schema_version, rows = parse_register(path)
    except ValueError as exc:
        return [], [
            issue(
                "error",
                "data_source_audit_register",
                "data source audit register is missing or malformed",
                {"path": str(path), "error": str(exc)},
                "repair data_source_audit.md before running source-dependent workers",
            )
        ]
    errors = validate_rows(schema_version, rows)
    if errors:
        return rows, [
            issue(
                "error",
                "data_source_audit_register",
                "data source audit register has validation errors",
                {"path": str(path), "errors": errors},
                "repair data_source_audit.md before running source-dependent workers",
            )
        ]
    return rows, []


def stale_source_details(row: dict[str, str], now: datetime, stale_source_days: int) -> Optional[dict[str, Any]]:
    parsed = parse_datetime(row.get("last_checked"))
    if parsed is None:
        return {
            "source_id": row.get("source_id"),
            "path": "data_source_audit.md",
            "last_checked": row.get("last_checked"),
            "reason": "missing_or_invalid_last_checked",
        }
    age_days = (now - parsed).total_seconds() / 86400
    if age_days <= stale_source_days:
        return None
    return {
        "source_id": row.get("source_id"),
        "path": "data_source_audit.md",
        "last_checked": row.get("last_checked"),
        "age_days": round(age_days, 1),
        "stale_source_days": stale_source_days,
    }


def source_issues(statuses: list[dict[str, Any]], ops_dir: Path, now: datetime, stale_source_days: int) -> list[dict[str, Any]]:
    rows, register_issues = data_source_rows(ops_dir)
    if register_issues:
        return register_issues
    by_id = {row["source_id"]: row for row in rows}
    blocking: list[dict[str, Any]] = []

    for item in active_tasks(statuses):
        payload = item["payload"]
        if not source_governance_applies(payload):
            continue
        refs = payload.get("data_audit_refs")
        if not isinstance(refs, list) or not refs:
            continue
        for ref in refs:
            if not isinstance(ref, str):
                continue
            row = by_id.get(ref)
            detail = {
                "task_id": payload.get("id", item["task_dir"].name),
                "task_dir": str(item["task_dir"]),
                "status_path": str(item["status_path"]),
                "task_type": payload.get("type"),
                "source_id": ref,
            }
            if row is None:
                blocking.append({**detail, "reason": "missing_data_source_audit_entry"})
                continue
            status = row.get("status")
            if status not in EXPERIMENT_READY_STATUSES:
                blocking.append({**detail, "reason": "source_not_experiment_ready", "source_status": status})
                continue
            stale = stale_source_details(row, now, stale_source_days)
            if stale is not None:
                blocking.append({**detail, "reason": "source_audit_stale", **stale})

    if blocking:
        return [
            issue(
                "error",
                "stale_or_unaudited_data_sources",
                f"{len(blocking)} active task source reference(s) are unaudited, not ready, or stale",
                blocking,
                "approve, refresh, or remove the source dependency before running workers",
            )
        ]
    return []


def data_foundation_issues(report: dict[str, Any], statuses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    finding_count = report.get("warning_count", 0) + report.get("error_count", 0)
    if not finding_count:
        return []
    governed_tasks = source_dependent_governed_tasks(statuses)
    error_count = report.get("error_count", 0)
    severity = "error" if error_count and governed_tasks else "warning"
    action = (
        "repair malformed data foundation files before running experiment or analysis workers"
        if severity == "error"
        else "run async-research data validate research_ops and resolve findings before source-dependent experiment work"
    )
    return [
        issue(
            severity,
            "data_foundation_findings",
            f"{finding_count} data-foundation finding(s)",
            {
                "error_count": error_count,
                "errors": report.get("errors", []),
                "warning_count": report.get("warning_count", 0),
                "warnings": report.get("warnings", []),
                "active_idea_gap_refs": report.get("active_idea_gap_refs", []),
                "source_dependent_tasks": governed_tasks,
            },
            action,
        )
    ]


def knowledge_library_issues(report: dict[str, Any], statuses: list[dict[str, Any]], ops_dir: Path) -> list[dict[str, Any]]:
    finding_count = report.get("warning_count", 0) + report.get("error_count", 0)
    if not finding_count:
        return []
    dependent_tasks = library_dependent_tasks(statuses, ops_dir)
    error_count = report.get("error_count", 0)
    severity = "error" if error_count and dependent_tasks else "warning"
    action = (
        "repair malformed knowledge library rows before running library-dependent hypothesis or experiment work"
        if severity == "error"
        else "run async-research library validate research_ops and review library findings before relying on library memory"
    )
    return [
        issue(
            severity,
            "knowledge_library_findings",
            f"{finding_count} knowledge-library finding(s)",
            {
                "error_count": error_count,
                "errors": report.get("errors", []),
                "warning_count": report.get("warning_count", 0),
                "warnings": report.get("warnings", []),
                "source_count": report.get("source_count", 0),
                "row_counts": report.get("row_counts", {}),
                "open_question_count": report.get("open_question_count", 0),
                "library_dependent_tasks": dependent_tasks,
            },
            action,
        )
    ]


def accepted_output_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    header: Optional[list[str]] = None
    rows: list[dict[str, str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line.startswith("|") or "---" in line:
            continue
        cells = [cell.strip().replace("\\|", "|") for cell in line.strip("|").split("|")]
        if header is None:
            header = [cell.lower().strip().replace(" ", "_") for cell in cells]
            continue
        if len(cells) == len(header) and any(cells):
            rows.append(dict(zip(header, cells)))
    return rows


def stale_accepted_evidence_issues(ops_dir: Path, now: datetime, freshness_days: int) -> list[dict[str, Any]]:
    report = memory_decay_report(ops_dir, now=now)
    stale = report.get("stale_outputs") if isinstance(report.get("stale_outputs"), list) else []
    due = report.get("due_outputs") if isinstance(report.get("due_outputs"), list) else []
    warnings: list[dict[str, Any]] = []
    if stale:
        warnings.append(
            issue(
                "warning",
                "stale_accepted_evidence",
                f"{len(stale)} accepted output(s) are stale or missing valid recheck dates",
                {"index": report.get("index"), "stale_outputs": stale, "fallback_freshness_days": freshness_days},
                "refresh stale accepted outputs before using them as current evidence",
            )
        )
    if due:
        warnings.append(
            issue(
                "warning",
                "accepted_memory_revalidation_due",
                f"{len(due)} accepted output(s) are due for revalidation soon",
                {"index": report.get("index"), "due_outputs": due},
                "schedule revalidation before relying on these outputs as current evidence",
            )
        )
    if not warnings:
        return []
    return warnings


def latest_metrics_snapshot(ops_dir: Path) -> Optional[dict[str, Any]]:
    rows = read_history(ops_dir / "metrics_history.jsonl")
    return rows[-1] if rows else None


def metrics_snapshot_issues(ops_dir: Path, now: datetime, stale_hours: float) -> list[dict[str, Any]]:
    snapshot = latest_metrics_snapshot(ops_dir)
    path = ops_dir / "metrics_history.jsonl"
    if snapshot is None:
        return [
            issue(
                "error",
                "metrics_snapshot_missing",
                "metrics_history.jsonl has no readable snapshots",
                {"path": str(path)},
                "run metrics_history.py append-snapshot before scheduling workers",
            )
        ]
    parsed = parse_datetime(snapshot.get("generated_at"))
    if parsed is None:
        return [
            issue(
                "warning",
                "metrics_snapshot_stale",
                "latest metrics snapshot has no valid generated_at",
                {"path": str(path), "generated_at": snapshot.get("generated_at")},
                "append a fresh metrics snapshot soon",
            )
        ]
    age_hours = (now - parsed).total_seconds() / 3600
    if age_hours > stale_hours:
        return [
            issue(
                "warning",
                "metrics_snapshot_stale",
                "latest metrics snapshot is stale",
                {"path": str(path), "generated_at": snapshot.get("generated_at"), "age_hours": round(age_hours, 2), "stale_hours": stale_hours},
                "append a fresh metrics snapshot soon",
            )
        ]
    return []


def failed_previous_run_issues(ops_dir: Path) -> list[dict[str, Any]]:
    path = ops_dir / "health_report.json"
    if not path.exists():
        return []
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [
            issue(
                "error",
                "failed_previous_run",
                "previous health_report.json is malformed",
                {"path": str(path), "error": str(exc)},
                "repair health_report.json or regenerate it before running workers",
            )
        ]
    if not isinstance(report, dict):
        return []
    highest = (report.get("summary") or {}).get("highest_severity") if isinstance(report.get("summary"), dict) else None
    alerts = report.get("alerts") if isinstance(report.get("alerts"), list) else []
    error_alerts = [alert for alert in alerts if isinstance(alert, dict) and alert.get("severity") == "error"]
    if highest == "error" or error_alerts:
        return [
            issue(
                "error",
                "failed_previous_run",
                "previous health report contains error-level alerts",
                {"path": str(path), "highest_severity": highest, "error_alerts": error_alerts},
                "resolve previous health errors before starting the next loop",
            )
        ]
    warning_alerts = [alert for alert in alerts if isinstance(alert, dict) and alert.get("severity") == "warning"]
    if warning_alerts:
        return [
            issue(
                "warning",
                "previous_health_warnings",
                "previous health report contains warning-level alerts",
                {"path": str(path), "warning_alerts": warning_alerts},
                "inspect previous warnings before relying on unattended execution",
            )
        ]
    return []


def classify_decision(
    invalids: list[dict[str, Any]],
    human: list[dict[str, Any]],
    skips: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> tuple[str, int]:
    if invalids:
        return "invalid_ops_state", INVALID_STATE
    if human:
        return "human_required", HUMAN_REQUIRED
    if skips:
        return "skip_loop", SKIP_LOOP
    if warnings:
        return "safe_with_warnings", WARNINGS
    return "safe_to_run", SUCCESS


def append_daily_status(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "",
        f"## Readiness Gate {report['generated_at']}",
        "",
        f"- Decision: {report['decision']}",
        f"- Exit code: {report['exit_code']}",
        f"- Expensive workers allowed: {str(report['expensive_workers_allowed']).lower()}",
        f"- Warnings: {len(report['warnings'])}",
        f"- Blockers: {len(report['blockers'])}",
    ]
    if report["blockers"]:
        lines.append("- Blockers:")
        for blocker in report["blockers"]:
            lines.append(f"  - [{blocker['check']}] {blocker['message']}")
    if report["warnings"]:
        lines.append("- Warnings:")
        for warning in report["warnings"]:
            lines.append(f"  - [{warning['check']}] {warning['message']}")
    if not report["blockers"] and not report["warnings"]:
        lines.append("- Issues: none")
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def report_summary(statuses: list[dict[str, Any]], alerts: list[dict[str, Any]], exit_code: int) -> dict[str, Any]:
    highest = "ok"
    if any(alert.get("severity") == "error" for alert in alerts):
        highest = "error"
    elif any(alert.get("severity") == "warning" for alert in alerts):
        highest = "warning"
    return {
        "task_count": len(statuses),
        "alert_count": len(alerts),
        "highest_severity": highest,
        "readiness_exit_code": exit_code,
    }


def build_gate_report(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    now = parse_datetime(args.now) if args.now else utc_now()
    if now is None:
        now = utc_now()
    ops_dir = args.ops_dir
    tasks_dir = ops_dir / "tasks"
    schema = load_status_schema(args.status_schema)
    statuses, malformed = load_task_statuses(tasks_dir, schema)
    counts = status_counts(statuses)
    active = active_tasks(statuses)
    review_queue = review_queue_tasks(statuses)
    cost = scan_cost_ledger(ops_dir / "cost_ledger.csv", args.monthly_budget_usd, args.weekly_budget_usd, now)
    idea_catalog = catalog_surface_summary(ops_dir)
    data_foundations = data_foundation_report(ops_dir, now)
    library = knowledge_library.library_report(ops_dir, now, args.library_stale_days)
    analysis_surface = analysis_dashboard_report(ops_dir, now=now, max_items=10)

    invalids: list[dict[str, Any]] = []
    human: list[dict[str, Any]] = []
    skips: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    invalids.extend(required_file_issues(ops_dir))
    invalids.extend(schema_issues(ops_dir, args.expected_schema_version))
    invalids.extend(status_issues(malformed))
    previous_health = failed_previous_run_issues(ops_dir)
    invalids.extend([item for item in previous_health if item.get("severity") == "error"])
    warnings.extend([item for item in previous_health if item.get("severity") == "warning"])

    stale_locks = scan_stale_locks_at(tasks_dir, args.stale_lock_minutes, now)
    if stale_locks:
        skips.append(
            issue(
                "error",
                "stale_locks",
                f"{len(stale_locks)} stale lock(s) detected",
                stale_locks,
                "inspect locks and release or recover interrupted workers before starting a new loop",
            )
        )

    needs_human = needs_human_tasks(statuses)
    mode_policy_routes = mode_policy_needs_human_routes(statuses, ops_dir)
    auto_resolvable_human = [item for item in mode_policy_routes if item.get("can_auto_resolve") is True]
    blocking_human = [item for item in mode_policy_routes if item.get("can_auto_resolve") is not True]
    legacy_requires_human = [
        item
        for item in needs_human
        if item.get("status") != "needs_human"
        or not any(route.get("status_path") == item.get("status_path") for route in mode_policy_routes)
    ]
    human_blockers = blocking_human + legacy_requires_human
    if human_blockers:
        human.append(
            issue(
                "error",
                "unresolved_needs_human",
                f"{len(human_blockers)} task(s) require human decision under the current interaction mode",
                human_blockers,
                "resolve needs_human tasks explicitly or switch to a policy-backed mode before scheduling workers",
            )
        )
    if auto_resolvable_human:
        warnings.append(
            issue(
                "warning",
                "mode_policy_auto_resolvable_needs_human",
                f"{len(auto_resolvable_human)} needs_human task(s) can be auto-resolved by interaction-mode policy",
                auto_resolvable_human,
                "run async-research workflow next to inspect the audited auto-resolution command",
            )
        )

    if len(active) > args.max_active:
        skips.append(
            issue(
                "error",
                "queue_overload",
                f"active task count {len(active)} exceeds max_active {args.max_active}",
                {"active_task_count": len(active), "max_active": args.max_active, "active_tasks": [
                    {
                        "task_id": item["payload"].get("id", item["task_dir"].name),
                        "task_dir": str(item["task_dir"]),
                        "status": item["payload"].get("status"),
                    }
                    for item in active
                ]},
                "skip loop until active queue capacity is available",
            )
        )

    if len(review_queue) > args.reviewer_capacity:
        skips.append(
            issue(
                "error",
                "reviewer_capacity",
                f"review queue count {len(review_queue)} exceeds reviewer capacity {args.reviewer_capacity}",
                {"review_queue_count": len(review_queue), "reviewer_capacity": args.reviewer_capacity, "tasks": [
                    {
                        "task_id": item["payload"].get("id", item["task_dir"].name),
                        "task_dir": str(item["task_dir"]),
                        "status": item["payload"].get("status"),
                    }
                    for item in review_queue
                ]},
                "skip loop until reviewers or aggregators clear the review queue",
            )
        )

    monthly_ratio = cost.get("monthly_usage_ratio")
    weekly_ratio = cost.get("weekly_usage_ratio")
    if (
        (isinstance(monthly_ratio, (int, float)) and monthly_ratio >= args.budget_threshold)
        or (isinstance(weekly_ratio, (int, float)) and weekly_ratio >= args.budget_threshold)
    ):
        skips.append(
            issue(
                "error",
                "budget_pressure",
                "budget pressure exceeds readiness threshold",
                {"cost": cost, "budget_threshold": args.budget_threshold},
                "skip expensive workers until budget is approved or resets",
            )
        )

    duplicates = duplicate_active_tasks(statuses)
    if duplicates:
        skips.append(
            issue(
                "error",
                "duplicate_active_tasks",
                f"{len(duplicates)} duplicate active task group(s) detected",
                duplicates,
                "merge, pause, or reject duplicates before starting another loop",
            )
        )

    human.extend(source_issues(statuses, ops_dir, now, args.stale_source_days))
    data_foundation_alerts = data_foundation_issues(data_foundations, statuses)
    human.extend([item for item in data_foundation_alerts if item.get("severity") == "error"])
    warnings.extend([item for item in data_foundation_alerts if item.get("severity") == "warning"])
    knowledge_library_alerts = knowledge_library_issues(library, statuses, ops_dir)
    human.extend([item for item in knowledge_library_alerts if item.get("severity") == "error"])
    warnings.extend([item for item in knowledge_library_alerts if item.get("severity") == "warning"])
    warnings.extend(stale_accepted_evidence_issues(ops_dir, now, args.accepted_output_freshness_days))
    warnings.extend(metrics_snapshot_issues(ops_dir, now, args.metrics_stale_hours))
    if idea_catalog["failure_count"]:
        warnings.append(
            issue(
                "warning",
                "idea_catalog_state",
                f"idea catalog has {idea_catalog['failure_count']} validation failure(s)",
                {
                    "validation_exit_code": idea_catalog["validation_exit_code"],
                    "failures": idea_catalog["failures"],
                },
                "run idea catalog validate and repair canonical JSON or projection state before promoting ideas",
            )
        )
    if idea_catalog["stale_projection_warnings"]:
        warnings.append(
            issue(
                "warning",
                "idea_catalog_projection_stale",
                f"idea catalog has {len(idea_catalog['stale_projection_warnings'])} stale projection warning(s)",
                idea_catalog["stale_projection_warnings"],
                "refresh or inspect catalog projections before relying on portfolio summaries",
            )
        )
    analysis_summary = analysis_surface.get("summary") if isinstance(analysis_surface.get("summary"), dict) else {}
    analysis_sections = analysis_surface.get("sections") if isinstance(analysis_surface.get("sections"), dict) else {}
    if analysis_summary.get("malformed_read_model_count", 0):
        invalids.append(
            issue(
                "error",
                "analysis_surface_malformed_inputs",
                f"{analysis_summary.get('malformed_read_model_count', 0)} analysis surface input(s) are missing or malformed",
                analysis_sections.get("malformed_read_model_inputs", []),
                "repair malformed analysis status or acceptance inputs before scheduling workers",
            )
        )
    if analysis_summary.get("preflight_blocked_count", 0):
        human.append(
            issue(
                "error",
                "analysis_preflight_blockers",
                f"{analysis_summary.get('preflight_blocked_count', 0)} active analysis task(s) have preflight blockers",
                analysis_sections.get("preflight_blockers", []),
                "resolve analysis preflight blockers before running analysis workers",
            )
        )
    if analysis_summary.get("preflight_warning_count", 0):
        warnings.append(
            issue(
                "warning",
                "analysis_preflight_warnings",
                f"{analysis_summary.get('preflight_warning_count', 0)} active analysis task(s) need warning review before execution",
                analysis_sections.get("preflight_warnings", []),
                "review warning-only analysis preflights before starting those runs",
            )
        )
    if analysis_summary.get("completed_missing_validation_count", 0):
        warnings.append(
            issue(
                "warning",
                "analysis_validation_missing",
                f"{analysis_summary.get('completed_missing_validation_count', 0)} completed analysis run(s) are missing clean validation",
                analysis_sections.get("completed_runs_missing_validation", []),
                "run analysis validate-run and validate-results before accepting empirical results",
            )
        )
    if analysis_summary.get("revalidation_needed_count", 0):
        warnings.append(
            issue(
                "warning",
                "analysis_revalidation_needed",
                f"{analysis_summary.get('revalidation_needed_count', 0)} empirical evidence item(s) need revalidation attention",
                analysis_sections.get("revalidation_needed", []),
                "review stale, due, or manual-review empirical evidence before reusing it as current memory",
            )
        )
    if analysis_summary.get("claim_caps_or_human_review_count", 0):
        warnings.append(
            issue(
                "warning",
                "analysis_claim_caps_or_human_review",
                f"{analysis_summary.get('claim_caps_or_human_review_count', 0)} empirical claim(s) are capped, blocked, or need human review",
                analysis_sections.get("claim_caps_and_human_review", []),
                "revise the claim, lower the claim strength, or complete human review before acceptance",
            )
        )

    decision, exit_code = classify_decision(invalids, human, skips, warnings)
    blockers = invalids + human + skips
    alerts = warnings + blockers
    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": iso_now(now),
        "ops_dir": str(ops_dir),
        "decision": decision,
        "exit_code": exit_code,
        "expensive_workers_allowed": exit_code in {SUCCESS, WARNINGS},
        "scheduler_action": "continue" if exit_code in {SUCCESS, WARNINGS} else "do_not_start_expensive_workers",
        "warnings": warnings,
        "blockers": blockers,
        "alerts": alerts,
        "summary": report_summary(statuses, alerts, exit_code),
        "checks": {
            "status_counts": counts,
            "active_task_count": len(active),
            "review_queue_count": len(review_queue),
            "needs_human_tasks": needs_human,
            "mode_policy_needs_human_routes": mode_policy_routes,
            "stale_locks": stale_locks,
            "duplicate_active_tasks": duplicates,
            "malformed_status_files": malformed,
            "schema_versions": scan_schema_versions(ops_dir, args.expected_schema_version),
            "queue_depth": markdown_table_row_count(ops_dir / "queue.md"),
            "discovery_inbox_count": markdown_table_row_count(ops_dir / "discovery_inbox.md"),
            "cost": cost,
            "data_foundations": data_foundations,
            "knowledge_library": library,
            "latest_metrics_snapshot": latest_metrics_snapshot(ops_dir),
            "accepted_memory": memory_decay_report(ops_dir, now=now),
            "idea_catalog": idea_catalog,
            "analysis_surface": analysis_surface,
        },
        "thresholds": {
            "max_active": args.max_active,
            "reviewer_capacity": args.reviewer_capacity,
            "stale_lock_minutes": args.stale_lock_minutes,
            "budget_ratio": args.budget_threshold,
            "stale_source_days": args.stale_source_days,
            "accepted_output_freshness_days": args.accepted_output_freshness_days,
            "metrics_stale_hours": args.metrics_stale_hours,
            "library_stale_days": args.library_stale_days,
            "expected_schema_version": args.expected_schema_version,
        },
    }
    return report, exit_code


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Determine whether another autonomous research loop is safe to run.")
    parser.add_argument("ops_dir", nargs="?", type=Path, default=Path("research_ops"))
    parser.add_argument("--status-schema", type=Path, default=DEFAULT_STATUS_SCHEMA)
    parser.add_argument("--expected-schema-version", default=DEFAULT_SCHEMA_VERSION)
    parser.add_argument("--max-active", type=int, default=10)
    parser.add_argument("--reviewer-capacity", type=int, default=5)
    parser.add_argument("--stale-lock-minutes", type=float, default=60.0)
    parser.add_argument("--budget-threshold", type=float, default=0.8)
    parser.add_argument("--monthly-budget-usd", type=float)
    parser.add_argument("--weekly-budget-usd", type=float)
    parser.add_argument("--stale-source-days", type=int, default=90)
    parser.add_argument("--accepted-output-freshness-days", type=int, default=90)
    parser.add_argument("--metrics-stale-hours", type=float, default=168.0)
    parser.add_argument("--library-stale-days", type=int, default=knowledge_library.SURFACE_STALE_DAYS)
    parser.add_argument("--report-path", type=Path)
    parser.add_argument("--daily-status-path", type=Path)
    parser.add_argument("--no-daily-status", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--now", help="Override current time for deterministic tests, ISO-8601.")
    return parser.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    if not args.ops_dir.exists():
        print_json({"ok": False, "reason": "ops_dir_missing", "ops_dir": str(args.ops_dir)})
        return INVALID_STATE
    report, exit_code = build_gate_report(args)
    report_path = args.report_path or args.ops_dir / "health_report.json"
    daily_status_path = args.daily_status_path or args.ops_dir / "daily_status.md"
    if not args.dry_run:
        atomic_write_json(report_path, report)
        if not args.no_daily_status:
            append_daily_status(daily_status_path, report)
    print_json(
        {
            "ok": exit_code in {SUCCESS, WARNINGS},
            "action": "dry_run_readiness_checked" if args.dry_run else "readiness_checked",
            "decision": report["decision"],
            "exit_code": exit_code,
            "expensive_workers_allowed": report["expensive_workers_allowed"],
            "scheduler_action": report["scheduler_action"],
            "warning_count": len(report["warnings"]),
            "blocker_count": len(report["blockers"]),
            "report_path": str(report_path),
            "daily_status_path": None if args.no_daily_status else str(daily_status_path),
            "warnings": report["warnings"],
            "blockers": report["blockers"],
        }
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
