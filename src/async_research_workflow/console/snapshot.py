"""Read-only console snapshot for local dashboard consumers.

JSON shape conventions:
- required-but-missing display values use the string ``"unavailable"``;
- optional details such as warning paths are omitted when absent;
- boolean safety markers are always present on the top-level envelope;
- timestamps are ISO-8601 UTC strings with a ``Z`` suffix.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from async_research_workflow.idea_catalog import catalog_dashboard_report
from async_research_workflow.scripts import analysis_surface
from async_research_workflow.scripts import autonomy_readiness_gate
from async_research_workflow.scripts import data_foundations
from async_research_workflow.scripts import health_check
from async_research_workflow.scripts import knowledge_library
from async_research_workflow.scripts import validate_transition


SNAPSHOT_SCHEMA_VERSION = "console_snapshot_v1.0"
RECENT_LIMIT = 5


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_now(value: str | None) -> datetime:
    if not value:
        return utc_now()
    parsed = health_check.parse_datetime(value)
    if parsed is None:
        raise ValueError(f"invalid --now value: {value}")
    return parsed


def iso_now(now: datetime) -> str:
    return now.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def issue(severity: str, reason: str, message: str, path: Path | str | None = None, details: Any = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "severity": severity,
        "reason": reason,
        "message": message,
    }
    if path is not None:
        payload["path"] = str(path)
    if details is not None:
        payload["details"] = details
    return payload


def unavailable(reason: str, message: str, path: Path | str | None = None, details: Any = None) -> dict[str, Any]:
    payload = {
        "available": False,
        "status": "unavailable",
        "reason": reason,
        "message": message,
        "summary": {},
        "warnings": [issue("warning", reason, message, path, details)],
    }
    if path is not None:
        payload["path"] = str(path)
    return payload


def compact_dashboard(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "available": True,
        "status": "available",
        "action": report.get("action"),
        "ok": report.get("ok"),
        "summary": report.get("summary", {}),
        "warnings": report.get("warnings", []),
        "sections": report.get("sections", {}),
    }


def guarded_dashboard(
    ops_dir: Path,
    required_path: Path | None,
    name: str,
    loader: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    if required_path is not None and not required_path.exists():
        return unavailable(
            f"{name}_files_missing",
            f"{name} dashboard files are missing",
            required_path,
        )
    try:
        return compact_dashboard(loader())
    except Exception as exc:
        return unavailable(
            f"{name}_dashboard_unavailable",
            f"{name} dashboard summary could not be rendered",
            ops_dir,
            str(exc),
        )


def markdown_table_rows(path: Path) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    warnings: list[dict[str, Any]] = []
    if not path.exists():
        return [], warnings
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        return [], [
            issue(
                "warning",
                "markdown_table_unreadable",
                "markdown table could not be read",
                path,
                str(exc),
            )
        ]
    header: list[str] | None = None
    rows: list[dict[str, str]] = []
    for line_number, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if not cells or all(not cell for cell in cells):
            continue
        if all(cell.replace("-", "").strip() == "" for cell in cells):
            continue
        if header is None:
            header = cells
            continue
        if len(cells) != len(header):
            warnings.append(
                issue(
                    "warning",
                    "malformed_markdown_table_row",
                    "markdown table row has a different number of cells than the header",
                    path,
                    {"line_number": line_number, "cell_count": len(cells), "header_count": len(header)},
                )
            )
            continue
        rows.append(dict(zip(header, cells)))
    return rows, warnings


def recent_markdown_rows(path: Path, limit: int = RECENT_LIMIT) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows, warnings = markdown_table_rows(path)
    return {
        "path": str(path),
        "exists": path.exists(),
        "count": len(rows),
        "recent_rows": rows[-limit:],
    }, warnings


def revalidation_state(rows: list[dict[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        status = str(row.get("revalidation_status") or "unavailable").strip() or "unavailable"
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items()))


def task_id(payload: dict[str, Any], fallback: Path) -> str:
    return str(payload.get("id") or fallback.name)


def task_file_links(task_dir: Path, status_path: Path) -> list[dict[str, Any]]:
    files = [
        ("Task brief", task_dir / "task.md"),
        ("Status JSON", status_path),
        ("Worker output", task_dir / "worker_output.md"),
        ("Review aggregate", task_dir / "review_panel" / "aggregate.md"),
        ("Review aggregate JSON", task_dir / "review_panel" / "aggregate.json"),
    ]
    return [
        {
            "label": label,
            "path": str(path),
            "exists": path.exists(),
        }
        for label, path in files
    ]


def task_lock_state(task_dir: Path, now: datetime) -> dict[str, Any]:
    lock_dir = task_dir / "LOCK"
    if not lock_dir.exists():
        return {
            "locked": False,
            "stale": False,
            "lock_dir": str(lock_dir),
            "age_minutes": None,
            "owner": None,
        }
    try:
        age_minutes = round((now.timestamp() - lock_dir.stat().st_mtime) / 60, 2)
    except OSError:
        age_minutes = None
    return {
        "locked": lock_dir.is_dir(),
        "stale": bool(age_minutes is not None and age_minutes >= 60.0),
        "lock_dir": str(lock_dir),
        "age_minutes": age_minutes,
        "owner": autonomy_readiness_gate.lock_owner(task_dir),
    }


def transition_summary(payload: dict[str, Any], status_path: Path) -> dict[str, Any]:
    status = payload.get("status")
    previous = payload.get("previous_status")
    decisions_path = validate_transition.infer_decisions_path(status_path)
    code, result = validate_transition.validate_payload(payload, decisions_path=decisions_path)
    return {
        "valid": code == validate_transition.SUCCESS,
        "exit_code": code,
        "reason": result.get("reason"),
        "previous_status": previous,
        "status": status,
        "allowed_next_statuses": sorted(validate_transition.ALLOWED.get(status, set())) if isinstance(status, str) else [],
    }


def status_validation_entry(status_path: Path, malformed_by_path: dict[str, dict[str, Any]]) -> dict[str, Any]:
    issue_record = malformed_by_path.get(str(status_path))
    if issue_record is None:
        return {
            "valid": True,
            "reason": "valid",
            "issues": [],
        }
    return {
        "valid": False,
        "reason": issue_record.get("reason", "invalid_status"),
        "issues": issue_record.get("errors") or [issue_record],
    }


def task_row(item: dict[str, Any], now: datetime, malformed_by_path: dict[str, dict[str, Any]]) -> dict[str, Any]:
    task_dir = item["task_dir"]
    status_path = item["status_path"]
    payload = item["payload"]
    transition = transition_summary(payload, status_path)
    return {
        "task_id": task_id(payload, task_dir),
        "title": payload.get("title", "unavailable"),
        "status": payload.get("status", "unknown"),
        "previous_status": payload.get("previous_status"),
        "type": payload.get("type", "unavailable"),
        "review_tier": (payload.get("review_policy") or {}).get("tier", "unavailable")
        if isinstance(payload.get("review_policy"), dict)
        else "unavailable",
        "revision_count": payload.get("revision_count", "unavailable"),
        "max_revisions": payload.get("max_revisions", "unavailable"),
        "revision_limit_hit": payload.get("revision_limit_hit", "unavailable"),
        "requires_human": payload.get("requires_human", False),
        "human_gate_reason": payload.get("human_gate_reason"),
        "human_gate": payload.get("human_gate") if isinstance(payload.get("human_gate"), dict) else None,
        "last_transition_reason": payload.get("last_transition_reason"),
        "allowed_paths": payload.get("allowed_paths", []),
        "allowed_next_statuses": transition["allowed_next_statuses"],
        "status_validation": status_validation_entry(status_path, malformed_by_path),
        "transition_validation": transition,
        "lock_state": task_lock_state(task_dir, now),
        "files": task_file_links(task_dir, status_path),
        "task_dir": str(task_dir),
        "status_path": str(status_path),
    }


def malformed_task_row(item: dict[str, Any], now: datetime) -> dict[str, Any]:
    raw_task_dir = item.get("task_dir")
    task_dir = Path(str(raw_task_dir)) if raw_task_dir else None
    raw_status_path = item.get("status_path")
    if raw_status_path:
        status_path = Path(str(raw_status_path))
    elif task_dir is not None:
        status_path = task_dir / "status.json"
    else:
        status_path = None
    task_id_value = str(item.get("task_id") or (task_dir.name if task_dir is not None else "") or "unavailable")
    return {
        "task_id": task_id_value,
        "title": "Invalid status.json",
        "status": "invalid",
        "previous_status": None,
        "type": "unavailable",
        "review_tier": "unavailable",
        "revision_count": "unavailable",
        "max_revisions": "unavailable",
        "revision_limit_hit": "unavailable",
        "requires_human": False,
        "human_gate_reason": item.get("reason"),
        "human_gate": None,
        "last_transition_reason": item.get("error") or item.get("reason"),
        "allowed_paths": [],
        "allowed_next_statuses": [],
        "status_validation": {
            "valid": False,
            "reason": item.get("reason", "invalid_status"),
            "issues": item.get("errors") or [item],
        },
        "transition_validation": {
            "valid": False,
            "exit_code": validate_transition.MALFORMED,
            "reason": item.get("reason", "invalid_status"),
            "previous_status": None,
            "status": "invalid",
            "allowed_next_statuses": [],
        },
        "lock_state": task_lock_state(task_dir, now)
        if task_dir is not None
        else {"locked": False, "stale": False, "lock_dir": "", "age_minutes": None, "owner": None},
        "files": task_file_links(task_dir, status_path) if task_dir is not None and status_path is not None else [],
        "task_dir": str(task_dir) if task_dir is not None else "",
        "status_path": str(status_path) if status_path is not None else "",
    }


def task_snapshot(ops_dir: Path, now: datetime, warnings: list[dict[str, Any]]) -> dict[str, Any]:
    tasks_dir = ops_dir / "tasks"
    schema = health_check.load_status_schema(health_check.DEFAULT_STATUS_SCHEMA)
    statuses, malformed = health_check.load_task_statuses(tasks_dir, schema)
    counts = health_check.status_counts(statuses)
    stale_locks = autonomy_readiness_gate.scan_stale_locks_at(tasks_dir, 60.0, now)
    malformed_by_path = {str(item.get("status_path")): item for item in malformed}
    rows = [task_row(item, now, malformed_by_path) for item in statuses]
    row_by_path = {str(item["status_path"]): row for item, row in zip(statuses, rows, strict=True)}
    status_paths = {str(status["status_path"]) for status in statuses}
    malformed_rows = [
        malformed_task_row(item, now)
        for item in malformed
        if str(item.get("status_path")) not in status_paths
    ]
    all_rows = sorted([*rows, *malformed_rows], key=lambda item: (str(item.get("task_id")), str(item.get("task_dir"))))
    active = [row_by_path[str(item["status_path"])] for item in autonomy_readiness_gate.active_tasks(statuses)]
    review = [row_by_path[str(item["status_path"])] for item in autonomy_readiness_gate.review_queue_tasks(statuses)]
    human = [
        row_by_path[str(item["status_path"])]
        for item in statuses
        if item["payload"].get("status") == "needs_human" or item["payload"].get("requires_human") is True
    ]
    blocked_statuses = {"needs_human", "paused"}
    blocked = [
        row_by_path[str(item["status_path"])]
        for item in statuses
        if item["payload"].get("status") in blocked_statuses or item["payload"].get("requires_human") is True
    ]
    for item in malformed:
        warnings.append(
            issue(
                "warning",
                "malformed_task_status",
                "task status could not be parsed or failed schema validation",
                item.get("status_path"),
                item,
            )
        )
    return {
        "tasks_dir": str(tasks_dir),
        "exists": tasks_dir.exists(),
        "total": len(statuses),
        "board_total": len(all_rows),
        "status_counts": counts,
        "status_filter_options": ["all", *sorted({str(item.get("status") or "unknown") for item in all_rows})],
        "all": all_rows,
        "active": active,
        "blocked": blocked,
        "review": review,
        "human": human,
        "malformed_statuses": malformed,
        "stale_locks": stale_locks,
    }


def workspace_snapshot(ops_dir: Path) -> dict[str, Any]:
    required = []
    for relative in autonomy_readiness_gate.REQUIRED_OPERATIONAL_FILES:
        path = ops_dir / relative
        required.append({"path": str(path), "relative_path": relative, "exists": path.exists()})
    missing = [item for item in required if not item["exists"]]
    return {
        "ops_dir": str(ops_dir),
        "exists": ops_dir.exists(),
        "is_dir": ops_dir.is_dir(),
        "starter_files": {
            "required_count": len(required),
            "available_count": len(required) - len(missing),
            "missing_count": len(missing),
            "missing": missing,
        },
    }


def readiness_snapshot(ops_dir: Path, now: datetime) -> dict[str, Any]:
    if not ops_dir.is_dir():
        return unavailable("ops_dir_missing", "readiness is unavailable until research_ops exists", ops_dir)
    try:
        args = autonomy_readiness_gate.parse_args([str(ops_dir), "--dry-run", "--no-daily-status", "--now", iso_now(now)])
        # build_gate_report is used here as a read-only report builder; writes live in the helper's main().
        report, exit_code = autonomy_readiness_gate.build_gate_report(args)
    except Exception as exc:
        return unavailable(
            "readiness_unavailable",
            "readiness report could not be generated",
            ops_dir,
            str(exc),
        )
    blockers = report.get("blockers", [])
    next_step = (
        "resolve blockers before running autonomous workers"
        if blockers
        else ("review warnings before starting expensive workers" if report.get("warnings") else "no readiness blockers")
    )
    return {
        "available": True,
        "status": "available",
        "verdict": report.get("decision"),
        "exit_code": exit_code,
        "blockers": blockers,
        "warnings": report.get("warnings", []),
        "next_step": next_step,
        "summary": report.get("summary", {}),
    }


def health_snapshot(ops_dir: Path, now: datetime) -> dict[str, Any]:
    if not ops_dir.is_dir():
        return unavailable("ops_dir_missing", "health is unavailable until research_ops exists", ops_dir)
    try:
        args = health_check.parse_args([str(ops_dir), "--dry-run", "--no-daily-status", "--now", iso_now(now)])
        # build_report is used here as a read-only report builder; writes live in the helper's main().
        report = health_check.build_report(args)
    except Exception as exc:
        return unavailable(
            "health_unavailable",
            "health report could not be generated",
            ops_dir,
            str(exc),
        )
    alerts = report.get("alerts", [])
    blockers = [item for item in alerts if item.get("severity") == "error"]
    next_step = (
        "repair health errors before continuing"
        if blockers
        else ("review health warnings" if alerts else "no health alerts")
    )
    return {
        "available": True,
        "status": "available",
        "verdict": report.get("summary", {}).get("highest_severity", "unavailable"),
        "exit_code": 0,
        "blockers": blockers,
        "warnings": [item for item in alerts if item.get("severity") != "error"],
        "next_step": next_step,
        "summary": report.get("summary", {}),
    }


def human_decisions_snapshot(ops_dir: Path, human_tasks: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    decisions, warnings = recent_markdown_rows(ops_dir / "decisions.md")
    return {
        "open_count": len(human_tasks),
        "blocked_task_refs": human_tasks,
        "recent_decision_rows": decisions["recent_rows"],
        "decision_log_path": decisions["path"],
        "decision_log_exists": decisions["exists"],
    }, warnings


def accepted_outputs_snapshot(ops_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows, warnings = markdown_table_rows(ops_dir / "accepted_outputs_index.md")
    return {
        "path": str(ops_dir / "accepted_outputs_index.md"),
        "exists": (ops_dir / "accepted_outputs_index.md").exists(),
        "count": len(rows),
        "recent_rows": rows[-RECENT_LIMIT:],
        "revalidation_state": revalidation_state(rows) if rows else {},
    }, warnings


def rejected_results_snapshot(ops_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    return recent_markdown_rows(ops_dir / "rejected_results.md")


def cost_snapshot(ops_dir: Path, now: datetime) -> dict[str, Any]:
    ledger_path = ops_dir / "cost_ledger.csv"
    try:
        cost = health_check.scan_cost_ledger(ledger_path, None, None, now)
    except Exception as exc:
        warning = issue(
            "warning",
            "cost_ledger_unreadable",
            "cost ledger could not be parsed",
            ledger_path,
            str(exc),
        )
        return {
            "available": False,
            "status": "unavailable",
            "path": str(ledger_path),
            "exists": ledger_path.exists(),
            "month_spend_usd": 0.0,
            "week_spend_usd": 0.0,
            "monthly_budget_usd": None,
            "weekly_budget_usd": None,
            "monthly_usage_ratio": None,
            "weekly_usage_ratio": None,
            "budget_pressure": False,
            "warnings": [warning],
        }
    monthly_ratio = cost.get("monthly_usage_ratio")
    weekly_ratio = cost.get("weekly_usage_ratio")
    warnings: list[dict[str, Any]] = []
    if not cost.get("exists"):
        warnings.append(issue("warning", "cost_ledger_missing", "cost ledger is missing", ops_dir / "cost_ledger.csv"))
    for name, ratio in (("monthly", monthly_ratio), ("weekly", weekly_ratio)):
        if isinstance(ratio, (int, float)) and ratio >= 0.8:
            warnings.append(
                issue(
                    "warning",
                    f"{name}_budget_pressure",
                    f"{name} cost is at least 80% of configured budget",
                    ops_dir / "cost_ledger.csv",
                    {"usage_ratio": ratio},
                )
            )
    return {
        "available": True,
        "status": "available",
        "path": cost.get("ledger_path"),
        "exists": cost.get("exists", False),
        "month_spend_usd": cost.get("monthly_cost_usd", 0.0),
        "week_spend_usd": cost.get("weekly_cost_usd", 0.0),
        "monthly_budget_usd": cost.get("monthly_budget_usd"),
        "weekly_budget_usd": cost.get("weekly_budget_usd"),
        "monthly_usage_ratio": monthly_ratio,
        "weekly_usage_ratio": weekly_ratio,
        "budget_pressure": bool(warnings),
        "warnings": warnings,
    }


def runs_snapshot(ops_dir: Path) -> dict[str, Any]:
    run_artifacts = ops_dir / "run_artifacts"
    if not run_artifacts.exists():
        return unavailable("run_artifacts_missing", "run artifacts are not available yet", run_artifacts)
    runs = []
    for run_dir in sorted([path for path in run_artifacts.iterdir() if path.is_dir()], key=lambda path: path.stat().st_mtime, reverse=True):
        run_json = run_dir / "run.json"
        payload: dict[str, Any] = {}
        if run_json.exists():
            try:
                parsed = json.loads(run_json.read_text(encoding="utf-8"))
                if isinstance(parsed, dict):
                    payload = parsed
            except (OSError, json.JSONDecodeError) as exc:
                payload = {"warning": f"run.json could not be read: {exc}"}
        runs.append(
            {
                "run_id": payload.get("run_id", run_dir.name),
                "run_dir": str(run_dir),
                "status": payload.get("status", "unavailable"),
                "task_id": payload.get("task_id", "unavailable"),
                "job_id": payload.get("job_id", "unavailable"),
                "started_at": payload.get("started_at", "unavailable"),
                "finished_at": payload.get("finished_at", "unavailable"),
            }
        )
    return {
        "available": True,
        "status": "available",
        "path": str(run_artifacts),
        "count": len(runs),
        "recent_runs": runs[:RECENT_LIMIT],
        "warnings": [],
    }


def dashboard_summaries(ops_dir: Path, now: datetime) -> dict[str, Any]:
    return {
        "ideas": guarded_dashboard(
            ops_dir,
            ops_dir / "ideas",
            "ideas",
            lambda: catalog_dashboard_report(ops_dir),
        ),
        "data": guarded_dashboard(
            ops_dir,
            ops_dir / "data",
            "data",
            lambda: data_foundations.data_dashboard_report(
                ops_dir,
                now=now,
                use_case=data_foundations.DEFAULT_DASHBOARD_USE_CASE,
            ),
        ),
        "library": guarded_dashboard(
            ops_dir,
            ops_dir / "library",
            "library",
            lambda: knowledge_library.library_dashboard_report(
                ops_dir,
                now=now,
                stale_days=knowledge_library.SURFACE_STALE_DAYS,
            ),
        ),
        "analysis": guarded_dashboard(
            ops_dir,
            None,
            "analysis",
            lambda: analysis_surface.analysis_dashboard_report(ops_dir, now=now, max_items=RECENT_LIMIT),
        ),
    }


def collect_unavailable_warnings(groups: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    for group in groups:
        if group.get("available") is False:
            warnings.extend(group.get("warnings", []))
    return warnings


def snapshot(ops_dir: Path, now: datetime | None = None) -> dict[str, Any]:
    current = now or utc_now()
    warnings: list[dict[str, Any]] = []
    workspace = workspace_snapshot(ops_dir)
    workspace_ready = ops_dir.is_dir()
    tasks = task_snapshot(ops_dir, current, warnings) if workspace_ready else {
        "tasks_dir": str(ops_dir / "tasks"),
        "exists": False,
        "total": 0,
        "board_total": 0,
        "status_counts": {},
        "status_filter_options": ["all"],
        "all": [],
        "active": [],
        "blocked": [],
        "review": [],
        "human": [],
        "malformed_statuses": [],
        "stale_locks": [],
    }
    readiness = readiness_snapshot(ops_dir, current)
    health = health_snapshot(ops_dir, current)
    human_decisions, human_decision_warnings = human_decisions_snapshot(ops_dir, tasks["human"])
    accepted_outputs, accepted_warnings = accepted_outputs_snapshot(ops_dir)
    rejected_results, rejected_warnings = rejected_results_snapshot(ops_dir)
    cost = cost_snapshot(ops_dir, current)
    dashboards = dashboard_summaries(ops_dir, current) if workspace_ready else {
        "ideas": unavailable("ops_dir_missing", "ideas dashboard is unavailable until research_ops exists", ops_dir),
        "data": unavailable("ops_dir_missing", "data dashboard is unavailable until research_ops exists", ops_dir),
        "library": unavailable("ops_dir_missing", "library dashboard is unavailable until research_ops exists", ops_dir),
        "analysis": unavailable("ops_dir_missing", "analysis dashboard is unavailable until research_ops exists", ops_dir),
    }
    runs = runs_snapshot(ops_dir) if workspace_ready else unavailable("ops_dir_missing", "runs are unavailable until research_ops exists", ops_dir)

    warnings.extend(human_decision_warnings)
    warnings.extend(accepted_warnings)
    warnings.extend(rejected_warnings)
    warnings.extend(cost.get("warnings", []))
    warnings.extend(collect_unavailable_warnings([readiness, health, runs, *dashboards.values()]))

    return {
        "ok": True,
        "action": "console_snapshot_rendered",
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "generated_at": iso_now(current),
        "read_only": True,
        "changed": False,
        "ops_dir": str(ops_dir),
        "workspace": workspace,
        "readiness": readiness,
        "health": health,
        "tasks": tasks,
        "human_decisions": human_decisions,
        "accepted_outputs": accepted_outputs,
        "rejected_results": rejected_results,
        "cost": cost,
        "ideas": dashboards["ideas"],
        "data": dashboards["data"],
        "library": dashboards["library"],
        "analysis": dashboards["analysis"],
        "runs": runs,
        "warnings": warnings,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render a read-only console snapshot for a research_ops workspace.")
    parser.add_argument("ops_dir", nargs="?", type=Path, default=Path("research_ops"), help="Path to the research_ops workspace.")
    parser.add_argument("--json", action="store_true", help="Render JSON output. JSON is the only Slice 1 output mode.")
    parser.add_argument("--now", help="Override current time for deterministic snapshot tests, ISO-8601.")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv or []))
    try:
        current = parse_now(args.now)
    except ValueError as exc:
        print_json({"ok": False, "action": "console_snapshot_rendered", "reason": "invalid_now", "message": str(exc), "read_only": True, "changed": False})
        return 3
    print_json(snapshot(args.ops_dir, now=current))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
