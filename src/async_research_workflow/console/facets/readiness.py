"""Console snapshot facet helpers."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from async_research_workflow.console.facets.base import command_hint
from async_research_workflow.console.facets.base import iso_now
from async_research_workflow.console.facets.base import unavailable
from async_research_workflow.scripts import autonomy_readiness_gate
from async_research_workflow.scripts import health_check

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
    accepted_memory = report.get("checks", {}).get("accepted_memory", {})
    return {
        "available": True,
        "status": "available",
        "verdict": report.get("summary", {}).get("highest_severity", "unavailable"),
        "exit_code": 0,
        "alerts": alerts,
        "blockers": blockers,
        "warnings": [item for item in alerts if item.get("severity") != "error"],
        "next_step": next_step,
        "summary": report.get("summary", {}),
        "checks": report.get("checks", {}),
        "thresholds": report.get("thresholds", {}),
        "stale_accepted_evidence": accepted_memory.get("stale_outputs", []) if isinstance(accepted_memory, dict) else [],
        "due_accepted_evidence": accepted_memory.get("due_outputs", []) if isinstance(accepted_memory, dict) else [],
        "recovery_commands": health_recovery_commands(ops_dir, report),
    }

def health_recovery_commands(ops_dir: Path, report: dict[str, Any]) -> list[dict[str, str]]:
    alerts = report.get("alerts", []) if isinstance(report.get("alerts"), list) else []
    checks = {str(alert.get("check")) for alert in alerts if isinstance(alert, dict)}
    commands = [
        command_hint("Run health dry-run", ["async-research", "health", str(ops_dir), "--dry-run"]),
        command_hint("Run workflow check", ["async-research", "workflow", "check", str(ops_dir)]),
    ]
    if checks & {"monthly_budget_threshold", "weekly_budget_threshold"}:
        commands.append(command_hint("Inspect cost summary", ["async-research", "cost", "summary", str(ops_dir)]))
    if checks & {"source_governance_errors", "source_freshness_warnings", "blocked_data_sources", "data_foundation_findings"}:
        commands.extend(
            [
                command_hint("Validate source register", ["async-research", "source", "validate", str(ops_dir)]),
                command_hint("Review source freshness", ["async-research", "source", "freshness", str(ops_dir)]),
                command_hint("Open data dashboard", ["async-research", "data", "dashboard", str(ops_dir)]),
            ]
        )
    if checks & {"stale_accepted_evidence", "accepted_memory_revalidation_due"}:
        commands.append(command_hint("Write revalidation schedule", ["async-research", "accepted", "revalidation", str(ops_dir), "--write-schedule"]))
    if checks & {"stale_locks", "malformed_status_files", "stuck_tasks", "revision_limit_breaches"}:
        commands.append(command_hint("Inspect readiness", ["async-research", "readiness", str(ops_dir), "--dry-run"]))
    seen: set[str] = set()
    unique = []
    for command in commands:
        if command["command"] in seen:
            continue
        seen.add(command["command"])
        unique.append(command)
    return unique
