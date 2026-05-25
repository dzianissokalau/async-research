"""Read-only console snapshot for local dashboard consumers.

JSON shape conventions:
- required-but-missing display values use the string ``"unavailable"``;
- optional details such as warning paths are omitted when absent;
- boolean safety markers are always present on the top-level envelope;
- timestamps are ISO-8601 UTC strings with a ``Z`` suffix.
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from async_research_workflow.console.facets.base import RECENT_LIMIT
from async_research_workflow.console.facets.base import collect_unavailable_warnings
from async_research_workflow.console.facets.base import command_hint
from async_research_workflow.console.facets.base import compact_text
from async_research_workflow.console.facets.base import count_values
from async_research_workflow.console.facets.base import extract_validation_commands
from async_research_workflow.console.facets.base import first_section
from async_research_workflow.console.facets.base import iso_now
from async_research_workflow.console.facets.base import issue
from async_research_workflow.console.facets.base import limited
from async_research_workflow.console.facets.base import markdown_bullets
from async_research_workflow.console.facets.base import markdown_sections
from async_research_workflow.console.facets.base import markdown_table_rows
from async_research_workflow.console.facets.base import normalize_heading
from async_research_workflow.console.facets.base import normalize_list_value
from async_research_workflow.console.facets.base import parse_now
from async_research_workflow.console.facets.base import print_json
from async_research_workflow.console.facets.base import recent_markdown_rows
from async_research_workflow.console.facets.base import reference_ids_from_text
from async_research_workflow.console.facets.base import revalidation_state
from async_research_workflow.console.facets.base import safe_read_embedded_json
from async_research_workflow.console.facets.base import safe_read_json
from async_research_workflow.console.facets.base import tail_text
from async_research_workflow.console.facets.base import unavailable
from async_research_workflow.console.facets.base import utc_now
from async_research_workflow.console.facets.costs import budget_state
from async_research_workflow.console.facets.costs import cost_dimension_summary
from async_research_workflow.console.facets.costs import cost_flag
from async_research_workflow.console.facets.costs import cost_label
from async_research_workflow.console.facets.costs import cost_ledger_detail_rows
from async_research_workflow.console.facets.costs import cost_number
from async_research_workflow.console.facets.costs import cost_snapshot
from async_research_workflow.console.facets.costs import cost_task_summaries
from async_research_workflow.console.facets.deliverables import compact_deliverable
from async_research_workflow.console.facets.deliverables import deliverables_snapshot
from async_research_workflow.console.facets.foundations import compact_dashboard
from async_research_workflow.console.facets.foundations import dashboard_links
from async_research_workflow.console.facets.foundations import dashboard_summaries
from async_research_workflow.console.facets.foundations import guarded_dashboard
from async_research_workflow.console.facets.foundations import source_snapshot
from async_research_workflow.console.facets.lifecycle import LIFECYCLE_ACTIVE_STATUSES
from async_research_workflow.console.facets.lifecycle import LIFECYCLE_BLOCKED_STATUSES
from async_research_workflow.console.facets.lifecycle import LIFECYCLE_COMPLETE_STATUSES
from async_research_workflow.console.facets.lifecycle import LIFECYCLE_QUEUED_STATUSES
from async_research_workflow.console.facets.lifecycle import LIFECYCLE_STATIONS
from async_research_workflow.console.facets.lifecycle import LIFECYCLE_TASK_STATUS_ORDER
from async_research_workflow.console.facets.lifecycle import lifecycle_blockers_for_station
from async_research_workflow.console.facets.lifecycle import lifecycle_command_for_station
from async_research_workflow.console.facets.lifecycle import lifecycle_command_for_task
from async_research_workflow.console.facets.lifecycle import lifecycle_is_blocked_task
from async_research_workflow.console.facets.lifecycle import lifecycle_mode_effects
from async_research_workflow.console.facets.lifecycle import lifecycle_output_rows
from async_research_workflow.console.facets.lifecycle import lifecycle_owner_for_task
from async_research_workflow.console.facets.lifecycle import lifecycle_policy_gate_row
from async_research_workflow.console.facets.lifecycle import lifecycle_search_text
from async_research_workflow.console.facets.lifecycle import lifecycle_snapshot
from async_research_workflow.console.facets.lifecycle import lifecycle_station_artifacts
from async_research_workflow.console.facets.lifecycle import lifecycle_station_for_row
from async_research_workflow.console.facets.lifecycle import lifecycle_station_matches
from async_research_workflow.console.facets.lifecycle import lifecycle_station_status
from async_research_workflow.console.facets.lifecycle import lifecycle_station_summary
from async_research_workflow.console.facets.lifecycle import lifecycle_task_rows
from async_research_workflow.console.facets.lifecycle import lifecycle_task_summary
from async_research_workflow.console.facets.mode import interaction_mode_snapshot
from async_research_workflow.console.facets.mode import prompts_snapshot
from async_research_workflow.console.facets.mode import schedules_snapshot
from async_research_workflow.console.facets.outcomes import accepted_outputs_snapshot
from async_research_workflow.console.facets.outcomes import auto_decision_display_row
from async_research_workflow.console.facets.outcomes import auto_decisions_snapshot
from async_research_workflow.console.facets.outcomes import delivered_projects_snapshot
from async_research_workflow.console.facets.outcomes import human_decisions_snapshot
from async_research_workflow.console.facets.outcomes import rejected_results_snapshot
from async_research_workflow.console.facets.outcomes import related_artifact_links
from async_research_workflow.console.facets.readiness import health_recovery_commands
from async_research_workflow.console.facets.readiness import health_snapshot
from async_research_workflow.console.facets.readiness import readiness_snapshot
from async_research_workflow.console.facets.runtime import evals_snapshot
from async_research_workflow.console.facets.runtime import evidence_memory_snapshot
from async_research_workflow.console.facets.runtime import runs_snapshot
from async_research_workflow.console.facets.runtime import runtime_snapshot
from async_research_workflow.console.facets.tasks import claim_gate_summary
from async_research_workflow.console.facets.tasks import claim_verification_summary
from async_research_workflow.console.facets.tasks import confidence_summary
from async_research_workflow.console.facets.tasks import malformed_task_row
from async_research_workflow.console.facets.tasks import next_task_text
from async_research_workflow.console.facets.tasks import read_task_reviews
from async_research_workflow.console.facets.tasks import reproducibility_checks
from async_research_workflow.console.facets.tasks import review_modes
from async_research_workflow.console.facets.tasks import source_gate_summary
from async_research_workflow.console.facets.tasks import status_validation_entry
from async_research_workflow.console.facets.tasks import task_dependencies
from async_research_workflow.console.facets.tasks import task_explainability
from async_research_workflow.console.facets.tasks import task_file_links
from async_research_workflow.console.facets.tasks import task_id
from async_research_workflow.console.facets.tasks import task_input_artifacts
from async_research_workflow.console.facets.tasks import task_lock_state
from async_research_workflow.console.facets.tasks import task_mode_policy
from async_research_workflow.console.facets.tasks import task_output_artifacts
from async_research_workflow.console.facets.tasks import task_qa_summary
from async_research_workflow.console.facets.tasks import task_row
from async_research_workflow.console.facets.tasks import task_snapshot
from async_research_workflow.console.facets.tasks import task_trigger
from async_research_workflow.console.facets.tasks import transition_summary
from async_research_workflow.console.facets.tasks import workspace_snapshot
from async_research_workflow.idea_catalog import catalog_dashboard_report
from async_research_workflow.scripts import analysis_surface
from async_research_workflow.scripts import autonomy_readiness_gate
from async_research_workflow.scripts import data_foundations
from async_research_workflow.scripts import health_check
from async_research_workflow.scripts import knowledge_library


SNAPSHOT_SCHEMA_VERSION = "console_snapshot_v1.0"


def empty_task_snapshot(ops_dir: Path) -> dict[str, Any]:
    return {
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


def unavailable_dashboards(ops_dir: Path) -> dict[str, Any]:
    return {
        "ideas": unavailable("ops_dir_missing", "ideas dashboard is unavailable until research_ops exists", ops_dir),
        "data": unavailable("ops_dir_missing", "data dashboard is unavailable until research_ops exists", ops_dir),
        "library": unavailable("ops_dir_missing", "library dashboard is unavailable until research_ops exists", ops_dir),
        "analysis": unavailable("ops_dir_missing", "analysis dashboard is unavailable until research_ops exists", ops_dir),
    }


def collect_dashboard_facets(ops_dir: Path, current: datetime) -> dict[str, Any]:
    return dashboard_summaries(
        ops_dir,
        current,
        ideas_loader=lambda: catalog_dashboard_report(ops_dir),
        data_loader=lambda: data_foundations.data_dashboard_report(
            ops_dir,
            now=current,
            use_case=data_foundations.DEFAULT_DASHBOARD_USE_CASE,
        ),
        library_loader=lambda: knowledge_library.library_dashboard_report(
            ops_dir,
            now=current,
            stale_days=knowledge_library.SURFACE_STALE_DAYS,
        ),
        analysis_loader=lambda: analysis_surface.analysis_dashboard_report(ops_dir, now=current, max_items=RECENT_LIMIT),
    )


def snapshot(ops_dir: Path, now: datetime | None = None) -> dict[str, Any]:
    current = now or utc_now()
    warnings: list[dict[str, Any]] = []
    workspace = workspace_snapshot(ops_dir)
    workspace_ready = ops_dir.is_dir()
    tasks = task_snapshot(ops_dir, current, warnings) if workspace_ready else empty_task_snapshot(ops_dir)
    readiness = readiness_snapshot(ops_dir, current)
    health = health_snapshot(ops_dir, current)
    human_decisions, human_decision_warnings = human_decisions_snapshot(ops_dir, tasks["human"])
    accepted_outputs, accepted_warnings = accepted_outputs_snapshot(ops_dir, current)
    delivered_projects = delivered_projects_snapshot(ops_dir, current)
    mode = interaction_mode_snapshot(ops_dir) if workspace_ready else unavailable("ops_dir_missing", "interaction mode is unavailable until research_ops exists", ops_dir)
    auto_decisions = auto_decisions_snapshot(ops_dir) if workspace_ready else unavailable("ops_dir_missing", "auto decisions are unavailable until research_ops exists", ops_dir)
    deliverables = deliverables_snapshot(ops_dir) if workspace_ready else unavailable("ops_dir_missing", "deliverables are unavailable until research_ops exists", ops_dir)
    rejected_results, rejected_warnings = rejected_results_snapshot(ops_dir)
    cost = cost_snapshot(ops_dir, current, tasks.get("all", []))
    prompts = prompts_snapshot(ops_dir) if workspace_ready else unavailable("ops_dir_missing", "prompts are unavailable until research_ops exists", ops_dir)
    schedules = schedules_snapshot(ops_dir) if workspace_ready else unavailable("ops_dir_missing", "schedules are unavailable until research_ops exists", ops_dir)
    dashboards = collect_dashboard_facets(ops_dir, current) if workspace_ready else unavailable_dashboards(ops_dir)
    sources = source_snapshot(ops_dir, current, dashboards["data"]) if workspace_ready else unavailable("ops_dir_missing", "sources are unavailable until research_ops exists", ops_dir)
    runs = runs_snapshot(ops_dir) if workspace_ready else unavailable("ops_dir_missing", "runs are unavailable until research_ops exists", ops_dir)
    runtime = runtime_snapshot(ops_dir) if workspace_ready else unavailable("ops_dir_missing", "runtime is unavailable until research_ops exists", ops_dir)
    evals = evals_snapshot(ops_dir) if workspace_ready else unavailable("ops_dir_missing", "evals are unavailable until research_ops exists", ops_dir)
    structured_memory = evidence_memory_snapshot(ops_dir, current) if workspace_ready else unavailable("ops_dir_missing", "evidence memory is unavailable until research_ops exists", ops_dir)
    lifecycle = lifecycle_snapshot(ops_dir, tasks, accepted_outputs, delivered_projects, health, sources, mode, auto_decisions) if workspace_ready else unavailable(
        "ops_dir_missing",
        "lifecycle is unavailable until research_ops exists",
        ops_dir,
    )

    warnings.extend(human_decision_warnings)
    warnings.extend(accepted_warnings)
    warnings.extend(rejected_warnings)
    warnings.extend(cost.get("warnings", []))
    if sources.get("available") is not False:
        warnings.extend(sources.get("warnings", []))
    if deliverables.get("available") is not False:
        warnings.extend(deliverables.get("warnings", []))
    warnings.extend(mode.get("warnings", []))
    warnings.extend(mode.get("errors", []))
    if auto_decisions.get("available") is not False:
        warnings.extend(auto_decisions.get("warnings", []))
    if runtime.get("available") is not False:
        warnings.extend(runtime.get("warnings", []))
        warnings.extend(runtime.get("errors", []))
    if evals.get("available") is not False:
        warnings.extend(evals.get("warnings", []))
        warnings.extend(evals.get("errors", []))
    if structured_memory.get("available") is not False:
        warnings.extend(structured_memory.get("warnings", []))
        warnings.extend(structured_memory.get("errors", []))
    warnings.extend(collect_unavailable_warnings([readiness, health, prompts, schedules, sources, runs, runtime, evals, structured_memory, lifecycle, deliverables, mode, auto_decisions, *dashboards.values()]))

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
        "delivered_projects": delivered_projects,
        "deliverables": deliverables,
        "interaction_mode": mode,
        "auto_decisions": auto_decisions,
        "rejected_results": rejected_results,
        "cost": cost,
        "sources": sources,
        "prompts": prompts,
        "schedules": schedules,
        "ideas": dashboards["ideas"],
        "data": dashboards["data"],
        "library": dashboards["library"],
        "analysis": dashboards["analysis"],
        "lifecycle": lifecycle,
        "runs": runs,
        "runtime": runtime,
        "evals": evals,
        "evidence_memory": structured_memory,
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
