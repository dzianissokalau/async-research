"""Console snapshot facet helpers."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from async_research_workflow.console import outcomes
from async_research_workflow.console.artifacts import artifact_link
from async_research_workflow.console.facets.base import RECENT_LIMIT
from async_research_workflow.console.facets.base import command_hint
from async_research_workflow.console.facets.base import count_values
from async_research_workflow.console.facets.base import issue
from async_research_workflow.console.facets.base import markdown_table_rows
from async_research_workflow.console.facets.base import normalize_list_value
from async_research_workflow.console.facets.base import recent_markdown_rows
from async_research_workflow.console.facets.base import revalidation_state
from async_research_workflow.console.facets.base import unavailable
from async_research_workflow.scripts import update_accepted_outputs_index
from async_research_workflow.scripts.decision_log import auto_decision_row_errors
from async_research_workflow.scripts.decision_log import read_auto_decisions
from async_research_workflow.scripts.decision_log import read_decisions

def related_artifact_links(ops_dir: Path, value: Any) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    for item in normalize_list_value(value):
        path = Path(item)
        if not path.is_absolute() and item.startswith("research_ops/"):
            path = Path(*Path(item).parts[1:])
        links.append(artifact_link(ops_dir, path.name or "Artifact", path))
    return links[:RECENT_LIMIT]

def auto_decision_display_row(ops_dir: Path, row: dict[str, str]) -> dict[str, Any]:
    errors = auto_decision_row_errors(row)
    return {
        "date": row.get("date", ""),
        "item_id": row.get("item_id", ""),
        "mode": row.get("mode", ""),
        "policy_version": row.get("policy_version", ""),
        "decision": row.get("decision", ""),
        "target_status": row.get("target_status", ""),
        "reason": row.get("reason", ""),
        "confidence": row.get("confidence", ""),
        "actor": row.get("actor", ""),
        "related_artifacts": row.get("related_artifacts", ""),
        "artifact_links": related_artifact_links(ops_dir, row.get("related_artifacts")),
        "audit_complete": not errors,
        "audit_errors": errors,
    }

def auto_decisions_snapshot(ops_dir: Path) -> dict[str, Any]:
    path = ops_dir / "auto_decisions.md"
    warnings: list[dict[str, Any]] = []
    try:
        rows = read_auto_decisions(path)
    except (OSError, UnicodeDecodeError) as exc:
        return unavailable(
            "auto_decision_log_unreadable",
            "auto-decision log could not be read",
            path,
            str(exc),
        )
    display_rows = [auto_decision_display_row(ops_dir, row) for row in rows]
    invalid_rows = [row for row in display_rows if not row["audit_complete"]]
    if invalid_rows:
        warnings.append(
            issue(
                "warning",
                "auto_decision_audit_incomplete",
                "one or more auto-decision rows are missing required audit fields",
                path,
                {"invalid_row_count": len(invalid_rows)},
            )
        )
    return {
        "available": True,
        "status": "available" if path.exists() else "missing",
        "path": str(path),
        "exists": path.exists(),
        "count": len(rows),
        "recent_rows": display_rows[-RECENT_LIMIT:],
        "invalid_row_count": len(invalid_rows),
        "summary": {
            "by_mode": count_values(display_rows, lambda row: row.get("mode")),
            "by_decision": count_values(display_rows, lambda row: row.get("decision")),
            "by_target_status": count_values(display_rows, lambda row: row.get("target_status")),
            "audit_complete": len(invalid_rows) == 0,
        },
        "links": [artifact_link(ops_dir, "Auto-decision log", path)],
        "warnings": warnings,
    }

def human_decisions_snapshot(ops_dir: Path, human_tasks: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    decisions_path = ops_dir / "decisions.md"
    warnings: list[dict[str, Any]] = []
    try:
        decision_rows = read_decisions(decisions_path)
    except (OSError, UnicodeDecodeError) as exc:
        decision_rows = []
        warnings.append(
            issue(
                "warning",
                "decision_log_unreadable",
                "decision log could not be read",
                decisions_path,
                str(exc),
            )
        )
    return {
        "open_count": len(human_tasks),
        "blocked_task_refs": human_tasks,
        "recent_decision_rows": decision_rows[-RECENT_LIMIT:],
        "decision_log_path": str(decisions_path),
        "decision_log_exists": decisions_path.exists(),
        "decision_log_count": len(decision_rows),
    }, warnings

def accepted_outputs_snapshot(ops_dir: Path, now: datetime) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    index_path = ops_dir / "accepted_outputs_index.md"
    rows, warnings = markdown_table_rows(index_path)
    try:
        memory_decay = update_accepted_outputs_index.memory_decay_report(ops_dir, now=now, index=index_path)
    except Exception as exc:
        memory_decay = {
            "ok": False,
            "row_count": len(rows),
            "current_count": 0,
            "due_count": 0,
            "stale_count": 0,
            "manual_review_count": 0,
            "superseded_count": 0,
            "due_outputs": [],
            "stale_outputs": [],
        }
        warnings.append(
            issue(
                "warning",
                "accepted_memory_decay_unavailable",
                "accepted memory freshness could not be computed",
                index_path,
                str(exc),
            )
        )
    return {
        "path": str(index_path),
        "exists": index_path.exists(),
        "count": len(rows),
        "recent_rows": rows[-RECENT_LIMIT:],
        "revalidation_state": revalidation_state(rows) if rows else {},
        "memory_decay": memory_decay,
        "stale_rows": memory_decay.get("stale_outputs", [])[:RECENT_LIMIT],
        "due_rows": memory_decay.get("due_outputs", [])[:RECENT_LIMIT],
        "recovery_commands": [
            command_hint("Write revalidation schedule", ["async-research", "accepted", "revalidation", str(ops_dir), "--write-schedule"]),
            command_hint("Run health dry-run", ["async-research", "health", str(ops_dir), "--dry-run"]),
        ],
    }, warnings

def delivered_projects_snapshot(ops_dir: Path, now: datetime) -> dict[str, Any]:
    index = outcomes.build_index(ops_dir, now=now)
    rows = index["projects"]
    generated_paths = index["paths"]
    return {
        "available": True,
        "status": "available",
        "path": generated_paths["projects_jsonl"],
        "summary_path": generated_paths["summary_json"],
        "exists": Path(generated_paths["projects_jsonl"]).exists(),
        "summary_exists": Path(generated_paths["summary_json"]).exists(),
        "count": len(rows),
        "status_filter_options": ["all", *sorted({str(row.get("delivered_status") or "unavailable") for row in rows})],
        "rows": rows,
        "summary": index["summary"],
        "warnings": [],
    }

def rejected_results_snapshot(ops_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    return recent_markdown_rows(ops_dir / "rejected_results.md")
