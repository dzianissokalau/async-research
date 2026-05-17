"""Read-only console snapshot for local dashboard consumers.

JSON shape conventions:
- required-but-missing display values use the string ``"unavailable"``;
- optional details such as warning paths are omitted when absent;
- boolean safety markers are always present on the top-level envelope;
- timestamps are ISO-8601 UTC strings with a ``Z`` suffix.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import shlex
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from async_research_workflow.console.artifacts import artifact_link
from async_research_workflow.console import outcomes
from async_research_workflow.idea_catalog import catalog_dashboard_report
from async_research_workflow.scripts import analysis_surface
from async_research_workflow.scripts import autonomy_readiness_gate
from async_research_workflow.scripts import data_source_audit
from async_research_workflow.scripts import data_foundations
from async_research_workflow.scripts import health_check
from async_research_workflow.scripts import knowledge_library
from async_research_workflow.scripts import prompt_library
from async_research_workflow.scripts import schedule_manifest
from async_research_workflow.scripts import update_accepted_outputs_index
from async_research_workflow.scripts import validate_transition
from async_research_workflow.scripts.decision_log import read_decisions


SNAPSHOT_SCHEMA_VERSION = "console_snapshot_v1.0"
RECENT_LIMIT = 5
LIFECYCLE_TASK_STATUS_ORDER = {
    "needs_human": 0,
    "paused": 1,
    "invalid": 2,
    "in_progress": 3,
    "awaiting_review": 4,
    "single_review": 5,
    "panel_review": 6,
    "ready_for_worker": 7,
    "ready_for_planning": 8,
    "inbox": 9,
    "needs_revision": 10,
    "accepted": 11,
    "synthesized": 12,
    "rejected": 13,
}
LIFECYCLE_BLOCKED_STATUSES = {"needs_human", "paused", "invalid"}
LIFECYCLE_ACTIVE_STATUSES = {"in_progress", "awaiting_review", "single_review", "panel_review"}
LIFECYCLE_QUEUED_STATUSES = {"inbox", "ready_for_planning", "ready_for_worker", "needs_revision"}
LIFECYCLE_COMPLETE_STATUSES = {"accepted", "synthesized"}
LIFECYCLE_STATIONS = [
    {
        "id": "topic",
        "label": "Topic / Research Objective",
        "objective": "Anchor the project topic, scope, and intended final deliverable.",
        "task_types": set(),
        "keywords": ("topic", "objective", "scope", "roadmap"),
        "artifacts": (("Workspace README", "README.md"), ("Research roadmap", "research_roadmap.md")),
        "owner": "human",
        "next_task": "clarify project objective and final deliverable",
        "command": ("Review next safe action", ["async-research", "workflow", "next", "<ops_dir>"]),
    },
    {
        "id": "discovery",
        "label": "Discovery Inbox",
        "objective": "Collect raw leads, clusters, rejected ideas, and intake notes.",
        "task_types": {"idea_discovery"},
        "keywords": ("discovery", "inbox", "candidate", "cluster"),
        "artifacts": (("Discovery inbox", "discovery_inbox.md"), ("Research inbox", "inbox.md"), ("Discovery clusters", "discovery/clusters.md")),
        "owner": "planner",
        "next_task": "turn discovery leads into scored ideas",
        "command": ("Inspect idea portfolio", ["async-research", "idea", "catalog", "dashboard", "<ops_dir>"]),
    },
    {
        "id": "idea_catalog",
        "label": "Idea Catalog",
        "objective": "Score, dedupe, promote, or park candidate research ideas.",
        "task_types": {"idea_dedupe", "idea_scoring", "hypothesis_card"},
        "keywords": ("idea", "catalog", "score", "hypothesis"),
        "artifacts": (("Idea catalog", "ideas/idea_catalog.md"), ("Idea prioritization", "ideas/prioritization.md")),
        "owner": "planner",
        "next_task": "promote a supported idea into a task",
        "command": ("Inspect idea portfolio", ["async-research", "idea", "catalog", "dashboard", "<ops_dir>"]),
    },
    {
        "id": "source_data",
        "label": "Source And Data Readiness",
        "objective": "Confirm source governance, data access, data gaps, and usable evidence foundations.",
        "task_types": {"data_readiness"},
        "keywords": ("source", "data", "readiness", "audit", "governance"),
        "artifacts": (
            ("Source audit", "data_source_audit.md"),
            ("Data catalog", "data/data_catalog.md"),
            ("Known data gaps", "data/known_data_gaps.md"),
        ),
        "owner": "data steward",
        "next_task": "clear source and data blockers",
        "command": ("Open data dashboard", ["async-research", "data", "dashboard", "<ops_dir>"]),
    },
    {
        "id": "knowledge_library",
        "label": "Knowledge Library / Literature",
        "objective": "Organize literature, claims, methods, open questions, and topic coverage.",
        "task_types": {"literature_extract"},
        "keywords": ("literature", "library", "knowledge", "claim", "method"),
        "artifacts": (
            ("Knowledge index", "library/knowledge_index.md"),
            ("Source library", "library/source_library.md"),
            ("Open questions", "library/open_questions.md"),
        ),
        "owner": "researcher",
        "next_task": "extract or validate literature coverage",
        "command": ("Open library dashboard", ["async-research", "library", "dashboard", "<ops_dir>"]),
    },
    {
        "id": "dataset_evidence",
        "label": "Dataset Or Evidence Build",
        "objective": "Build task-specific datasets, manifests, evidence ledgers, and reproducible inputs.",
        "task_types": {"experiment_plan"},
        "keywords": ("dataset", "evidence", "manifest", "build", "experiment plan"),
        "artifacts": (("Evidence ledger", "evidence_ledger.md"), ("Data join map", "data/join_map.md")),
        "owner": "worker",
        "next_task": "prepare reproducible evidence inputs",
        "command": ("Inspect workflow next", ["async-research", "workflow", "next", "<ops_dir>"]),
    },
    {
        "id": "analysis",
        "label": "Analysis / Hypothesis Testing",
        "objective": "Run analyses, evaluate results, and test accepted hypotheses against governed evidence.",
        "task_types": {"run_analysis", "evaluate_results"},
        "keywords": ("analysis", "hypothesis", "result", "evaluate", "test"),
        "artifacts": (("Analysis run notes", "analysis.md"),),
        "owner": "analyst",
        "next_task": "run or review the active analysis task",
        "command": ("Open analysis dashboard", ["async-research", "analysis", "dashboard", "<ops_dir>"]),
    },
    {
        "id": "synthesis",
        "label": "Synthesis / Memo",
        "objective": "Turn accepted evidence into memo sections, synthesis, and decision-ready findings.",
        "task_types": {"memo_section", "weekly_synthesis"},
        "keywords": ("synthesis", "memo", "section", "finding"),
        "artifacts": (("Accepted outputs", "accepted_outputs_index.md"), ("Weekly digest", "weekly_digest.md")),
        "owner": "writer",
        "next_task": "synthesize accepted evidence into memo or paper sections",
        "command": ("Inspect workflow next", ["async-research", "workflow", "next", "<ops_dir>"]),
    },
    {
        "id": "draft",
        "label": "Draft",
        "objective": "Assemble the paper, outline, or shareable draft from accepted synthesis.",
        "task_types": {"status_update"},
        "keywords": ("draft", "paper", "manuscript", "outline"),
        "artifacts": (("Accepted outputs", "accepted_outputs_index.md"), ("Research roadmap", "research_roadmap.md")),
        "owner": "writer",
        "next_task": "assemble or revise the current draft artifact",
        "command": ("Inspect workflow next", ["async-research", "workflow", "next", "<ops_dir>"]),
    },
    {
        "id": "final_review",
        "label": "Final Review And Polish",
        "objective": "Complete final review, resolve caveats, and decide whether the deliverable is ready to share.",
        "task_types": {"critic_review"},
        "keywords": ("review", "polish", "final", "qa", "acceptance"),
        "artifacts": (
            ("Human review queue", "human_review_queue.md"),
            ("Result acceptance policy", "result_acceptance_policy.md"),
            ("Rejected results", "rejected_results.md"),
        ),
        "owner": "reviewer",
        "next_task": "run final review and resolve remaining caveats",
        "command": ("Inspect workflow next", ["async-research", "workflow", "next", "<ops_dir>"]),
    },
]


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


def tail_text(path: Path, limit: int = 1200) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return text[-limit:]


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


def command_hint(label: str, argv: list[str]) -> dict[str, str]:
    return {
        "label": label,
        "command": " ".join(shlex.quote(str(part)) for part in argv),
    }


def limited(rows: list[dict[str, Any]], limit: int = RECENT_LIMIT) -> list[dict[str, Any]]:
    return rows[:limit]


def task_id(payload: dict[str, Any], fallback: Path) -> str:
    return str(payload.get("id") or fallback.name)


def task_file_links(ops_dir: Path, task_dir: Path, status_path: Path) -> list[dict[str, Any]]:
    files: list[tuple[str, Path]] = [
        ("Task brief", task_dir / "task.md"),
        ("Status JSON", status_path),
        ("Worker output", task_dir / "worker_output.md"),
        ("Review aggregate", task_dir / "review_panel" / "aggregate.md"),
        ("Review aggregate JSON", task_dir / "review_panel" / "aggregate.json"),
        ("Result acceptance", task_dir / "review_panel" / "result_acceptance.json"),
    ]
    seen = {path for _, path in files}
    for reviews_dir in (task_dir / "reviews", task_dir / "review_panel"):
        if reviews_dir.is_dir():
            for path in sorted([*reviews_dir.glob("*.md"), *reviews_dir.glob("*.json")]):
                if path not in seen:
                    files.append((path.name, path))
                    seen.add(path)
    artifacts_dir = task_dir / "artifacts"
    if artifacts_dir.is_dir():
        for path in sorted(item for item in artifacts_dir.rglob("*") if item.is_file())[:20]:
            if path not in seen:
                files.append((path.relative_to(task_dir).as_posix(), path))
                seen.add(path)
    return [artifact_link(ops_dir, label, path) for label, path in files]


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


def task_row(ops_dir: Path, item: dict[str, Any], now: datetime, malformed_by_path: dict[str, dict[str, Any]]) -> dict[str, Any]:
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
        "files": task_file_links(ops_dir, task_dir, status_path),
        "task_dir": str(task_dir),
        "status_path": str(status_path),
    }


def malformed_task_row(item: dict[str, Any], now: datetime, ops_dir: Path | None = None) -> dict[str, Any]:
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
    workspace_dir = ops_dir
    if workspace_dir is None and task_dir is not None and task_dir.parent.name == "tasks":
        workspace_dir = task_dir.parent.parent
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
        "files": task_file_links(workspace_dir, task_dir, status_path) if workspace_dir is not None and task_dir is not None and status_path is not None else [],
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
    rows = [task_row(ops_dir, item, now, malformed_by_path) for item in statuses]
    row_by_path = {str(item["status_path"]): row for item, row in zip(statuses, rows, strict=True)}
    status_paths = {str(status["status_path"]) for status in statuses}
    malformed_rows = [
        malformed_task_row(item, now, ops_dir)
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


def prompts_snapshot(ops_dir: Path) -> dict[str, Any]:
    try:
        return prompt_library.library_snapshot(ops_dir)
    except Exception as exc:
        return unavailable(
            "prompts_unavailable",
            "prompt library could not be read",
            ops_dir / "prompts",
            str(exc),
        )


def schedules_snapshot(ops_dir: Path) -> dict[str, Any]:
    try:
        return schedule_manifest.schedule_snapshot(ops_dir)
    except Exception as exc:
        return unavailable(
            "schedules_unavailable",
            "schedule manifest could not be read",
            ops_dir / "schedules.json",
            str(exc),
        )


def rejected_results_snapshot(ops_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    return recent_markdown_rows(ops_dir / "rejected_results.md")


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


def budget_state(ratio: Any) -> str:
    if (
        not isinstance(ratio, (int, float))
        or isinstance(ratio, bool)
        or not math.isfinite(ratio)
    ):
        return "unconfigured"
    if ratio >= 1:
        return "over_budget"
    if ratio >= 0.8:
        return "pressure"
    return "ok"


def cost_ledger_detail_rows(ledger_path: Path, now: datetime) -> list[dict[str, Any]]:
    if not ledger_path.exists():
        return []
    rows: list[dict[str, Any]] = []
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    week_start = now - timedelta(days=now.weekday())
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    with ledger_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for index, row in enumerate(reader, start=1):
            parsed = {str(key): str(value) for key, value in row.items() if key is not None}
            date = health_check.row_date(parsed)
            amount = health_check.row_amount(parsed)
            input_tokens = health_check.row_int(parsed, health_check.INPUT_TOKEN_FIELDS)
            output_tokens = health_check.row_int(parsed, health_check.OUTPUT_TOKEN_FIELDS)
            total_tokens = health_check.row_int(parsed, health_check.TOTAL_TOKEN_FIELDS) or input_tokens + output_tokens
            rows.append(
                {
                    "row_number": index,
                    "date": parsed.get("date") or parsed.get("created_at") or parsed.get("timestamp") or parsed.get("period_start") or "unavailable",
                    "item_id": parsed.get("item_id", ""),
                    "role": parsed.get("role", ""),
                    "model_or_tool": parsed.get("model_or_tool", ""),
                    "usage_source": parsed.get("usage_source", ""),
                    "amount_usd": round(amount, 4),
                    "api_usd": parsed.get("api_usd", ""),
                    "compute_usd": parsed.get("compute_usd", ""),
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": total_tokens,
                    "status": parsed.get("status", ""),
                    "actual": parsed.get("actual", ""),
                    "notes": parsed.get("notes", ""),
                    "in_current_month": bool(date and date >= month_start),
                    "in_current_week": bool(date and date >= week_start),
                    "sort_date": date.isoformat() if date else "",
                }
            )
    return rows


def cost_snapshot(ops_dir: Path, now: datetime) -> dict[str, Any]:
    ledger_path = ops_dir / "cost_ledger.csv"
    try:
        cost = health_check.scan_cost_ledger(ledger_path, None, None, now)
        detail_rows = cost_ledger_detail_rows(ledger_path, now)
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
            "summary": {},
            "recent_rows": [],
            "top_spend_rows": [],
            "recovery_commands": [command_hint("Inspect cost summary", ["async-research", "cost", "summary", str(ops_dir)])],
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
        "row_count": cost.get("row_count", 0),
        "month_spend_usd": cost.get("monthly_cost_usd", 0.0),
        "week_spend_usd": cost.get("weekly_cost_usd", 0.0),
        "monthly_budget_usd": cost.get("monthly_budget_usd"),
        "weekly_budget_usd": cost.get("weekly_budget_usd"),
        "monthly_usage_ratio": monthly_ratio,
        "weekly_usage_ratio": weekly_ratio,
        "monthly_budget_state": budget_state(monthly_ratio),
        "weekly_budget_state": budget_state(weekly_ratio),
        "input_tokens": cost.get("input_tokens", 0),
        "output_tokens": cost.get("output_tokens", 0),
        "total_tokens": cost.get("total_tokens", 0),
        "actual_usage_rows": cost.get("actual_usage_rows", 0),
        "budget_pressure": bool(warnings),
        "recent_rows": sorted(detail_rows, key=lambda row: (row["sort_date"], row["row_number"]), reverse=True)[:RECENT_LIMIT],
        "top_spend_rows": sorted(detail_rows, key=lambda row: row["amount_usd"], reverse=True)[:RECENT_LIMIT],
        "summary": {
            "row_count": cost.get("row_count", 0),
            "month_spend_usd": cost.get("monthly_cost_usd", 0.0),
            "week_spend_usd": cost.get("weekly_cost_usd", 0.0),
            "monthly_budget_state": budget_state(monthly_ratio),
            "weekly_budget_state": budget_state(weekly_ratio),
            "total_tokens": cost.get("total_tokens", 0),
            "actual_usage_rows": cost.get("actual_usage_rows", 0),
        },
        "recovery_commands": [
            command_hint("Inspect cost summary", ["async-research", "cost", "summary", str(ops_dir)]),
            command_hint("Run health dry-run", ["async-research", "health", str(ops_dir), "--dry-run"]),
        ],
        "warnings": warnings,
    }


def source_snapshot(ops_dir: Path, now: datetime, data_dashboard: dict[str, Any]) -> dict[str, Any]:
    audit_path = ops_dir / "data_source_audit.md"
    if not audit_path.exists():
        return unavailable("source_audit_missing", "source audit register is missing", audit_path)
    governance = data_source_audit.source_governance_report(ops_dir, now=now)
    sections = data_dashboard.get("sections", {}) if isinstance(data_dashboard.get("sections"), dict) else {}
    summary = data_dashboard.get("summary", {}) if isinstance(data_dashboard.get("summary"), dict) else {}
    candidate_sources = sections.get("candidate_sources", []) if isinstance(sections.get("candidate_sources"), list) else []
    needs_review_sources = sections.get("needs_review_sources", []) if isinstance(sections.get("needs_review_sources"), list) else []
    usable_today = sections.get("usable_today_sources", []) if isinstance(sections.get("usable_today_sources"), list) else []
    blocked_sources = sections.get("blocked_sources", []) if isinstance(sections.get("blocked_sources"), list) else governance.get("blocked_sources", [])
    stale_sources = sections.get("stale_source_reviews", []) if isinstance(sections.get("stale_source_reviews"), list) else governance.get("stale_sources", [])
    attention_by_id: dict[str, dict[str, Any]] = {}
    for reason, rows in (
        ("blocked", blocked_sources),
        ("stale", stale_sources),
        ("candidate", candidate_sources),
        ("needs_review", needs_review_sources),
    ):
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            source_id = str(row.get("source_id") or "").strip()
            if not source_id:
                continue
            merged = dict(attention_by_id.get(source_id, {}))
            merged.update(row)
            reasons = set(merged.get("attention_reasons", []))
            reasons.add(reason)
            merged["attention_reasons"] = sorted(reasons)
            attention_by_id[source_id] = merged
    warnings: list[dict[str, Any]] = []
    for item in governance.get("warnings", []) if isinstance(governance.get("warnings"), list) else []:
        warnings.append(issue("warning", str(item.get("reason", "source_governance_warning")), str(item.get("message", "source governance warning")), audit_path, item))
    for item in governance.get("errors", []) if isinstance(governance.get("errors"), list) else []:
        warnings.append(issue("error", "source_governance_error", str(item.get("message", item)), audit_path, item))
    return {
        "available": True,
        "status": "available",
        "path": str(audit_path),
        "ok": governance.get("ok") is True and not warnings,
        "source_count": governance.get("source_count", summary.get("source_count", 0)),
        "summary": {
            "source_count": governance.get("source_count", summary.get("source_count", 0)),
            "usable_today_count": len(usable_today),
            "blocked_source_count": len(blocked_sources) if isinstance(blocked_sources, list) else 0,
            "stale_source_count": len(stale_sources) if isinstance(stale_sources, list) else 0,
            "candidate_source_count": len(candidate_sources),
            "needs_review_source_count": len(needs_review_sources),
            "governance_error_count": governance.get("error_count", 0),
            "governance_warning_count": governance.get("warning_count", 0),
        },
        "approval_counts": governance.get("approval_counts", {}),
        "tier_counts": governance.get("tier_counts", {}),
        "usable_today_sources": limited(usable_today),
        "attention_sources": limited(list(attention_by_id.values()), 10),
        "blocked_sources": limited(blocked_sources if isinstance(blocked_sources, list) else []),
        "stale_sources": limited(stale_sources if isinstance(stale_sources, list) else []),
        "candidate_sources": limited(candidate_sources),
        "needs_review_sources": limited(needs_review_sources),
        "recovery_commands": [
            command_hint("Validate source register", ["async-research", "source", "validate", str(ops_dir)]),
            command_hint("Review source freshness", ["async-research", "source", "freshness", str(ops_dir)]),
            command_hint("Open data dashboard", ["async-research", "data", "dashboard", str(ops_dir)]),
        ],
        "warnings": warnings,
    }


def lifecycle_search_text(row: dict[str, Any]) -> str:
    values = [
        row.get("task_id"),
        row.get("title"),
        row.get("type"),
        row.get("project_type"),
        row.get("key_finding"),
        row.get("claim_type"),
        row.get("status"),
        row.get("delivered_status"),
    ]
    return " ".join(str(value or "").lower() for value in values)


def lifecycle_station_matches(station: dict[str, Any], row: dict[str, Any]) -> bool:
    row_type = str(row.get("type") or row.get("project_type") or "").strip()
    task_types = station.get("task_types", set())
    if row_type and row_type in task_types:
        return True
    text = lifecycle_search_text(row)
    return any(keyword in text for keyword in station.get("keywords", ()))


def lifecycle_station_for_row(row: dict[str, Any], fallback: str = "topic") -> str:
    for station in LIFECYCLE_STATIONS:
        if lifecycle_station_matches(station, row):
            return str(station["id"])
    return fallback


def lifecycle_output_rows(delivered_projects: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    by_station: dict[str, list[dict[str, Any]]] = {str(station["id"]): [] for station in LIFECYCLE_STATIONS}
    for project in delivered_projects.get("rows", []) if isinstance(delivered_projects.get("rows"), list) else []:
        if not isinstance(project, dict):
            continue
        station_id = lifecycle_station_for_row(project, fallback="synthesis")
        by_station.setdefault(station_id, []).append(
            {
                "task_id": project.get("task_id"),
                "title": project.get("title"),
                "status": project.get("delivered_status"),
                "accepted_date": project.get("accepted_date"),
                "claim_strength": project.get("claim_strength"),
                "key_finding": project.get("key_finding"),
                "links": project.get("links", []),
            }
        )
    return by_station


def lifecycle_task_rows(tasks: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    by_station: dict[str, list[dict[str, Any]]] = {str(station["id"]): [] for station in LIFECYCLE_STATIONS}
    for task in tasks.get("all", []) if isinstance(tasks.get("all"), list) else []:
        if not isinstance(task, dict):
            continue
        station_id = lifecycle_station_for_row(task)
        by_station.setdefault(station_id, []).append(task)
    for station_id, rows in by_station.items():
        by_station[station_id] = sorted(
            rows,
            key=lambda task: (
                LIFECYCLE_TASK_STATUS_ORDER.get(str(task.get("status") or ""), 99),
                str(task.get("task_id") or ""),
                str(task.get("task_dir") or ""),
            ),
        )
    return by_station


def lifecycle_is_blocked_task(task: dict[str, Any]) -> bool:
    status = str(task.get("status") or "")
    validation = task.get("status_validation") if isinstance(task.get("status_validation"), dict) else {}
    transition = task.get("transition_validation") if isinstance(task.get("transition_validation"), dict) else {}
    return (
        status in LIFECYCLE_BLOCKED_STATUSES
        or task.get("requires_human") is True
        or validation.get("valid") is False
        or transition.get("valid") is False
    )


def lifecycle_station_status(tasks: list[dict[str, Any]], outputs: list[dict[str, Any]], artifacts: list[dict[str, Any]]) -> str:
    statuses = {str(task.get("status") or "") for task in tasks}
    if any(lifecycle_is_blocked_task(task) for task in tasks):
        return "blocked"
    if statuses & LIFECYCLE_ACTIVE_STATUSES:
        return "active"
    if statuses & LIFECYCLE_QUEUED_STATUSES:
        return "queued"
    if outputs or statuses & LIFECYCLE_COMPLETE_STATUSES:
        return "complete"
    if any(link.get("exists") for link in artifacts):
        return "ready"
    return "missing"


def lifecycle_station_artifacts(ops_dir: Path, station: dict[str, Any]) -> list[dict[str, Any]]:
    links = []
    for label, relative in station.get("artifacts", ()):
        links.append(artifact_link(ops_dir, str(label), ops_dir / str(relative)))
    return links


def lifecycle_command_for_station(ops_dir: Path, station: dict[str, Any]) -> dict[str, str]:
    label, argv = station["command"]
    return command_hint(str(label), [str(ops_dir) if part == "<ops_dir>" else part for part in argv])


def lifecycle_command_for_task(ops_dir: Path, task: dict[str, Any]) -> dict[str, str]:
    task_dir = str(task.get("task_dir") or "")
    status = str(task.get("status") or "")
    if not task_dir:
        return command_hint("Inspect workflow next", ["async-research", "workflow", "next", str(ops_dir)])
    if lifecycle_is_blocked_task(task):
        return command_hint(
            "Dry-run human decision",
            ["async-research", "decision", "resolve-task", str(ops_dir), task_dir, "--decision", "resume", "--dry-run"],
        )
    if status == "ready_for_worker":
        return command_hint("Dry-run worker start", ["async-research", "workflow", "worker-start", task_dir, "--dry-run"])
    if status == "in_progress":
        return command_hint("Dry-run worker complete", ["async-research", "workflow", "worker-complete", task_dir, "--dry-run"])
    if status in {"awaiting_review", "single_review", "panel_review"}:
        return command_hint("Inspect review state", ["async-research", "workflow", "status", task_dir])
    if status in {"inbox", "ready_for_planning", "needs_revision"}:
        return command_hint("Inspect task status", ["async-research", "workflow", "status", task_dir])
    return command_hint("Inspect workflow next", ["async-research", "workflow", "next", str(ops_dir)])


def lifecycle_owner_for_task(task: dict[str, Any], fallback: str) -> str:
    lock_state = task.get("lock_state") if isinstance(task.get("lock_state"), dict) else {}
    owner = str(lock_state.get("owner") or "").strip()
    if owner and owner.lower() != "none":
        return owner
    status = str(task.get("status") or "")
    if lifecycle_is_blocked_task(task):
        return "human"
    if status in {"awaiting_review", "single_review", "panel_review"}:
        return "reviewer"
    if status in {"inbox", "ready_for_planning"}:
        return "planner"
    if status in {"ready_for_worker", "in_progress"}:
        return "worker"
    return fallback


def lifecycle_blockers_for_station(station_id: str, tasks: list[dict[str, Any]], sources: dict[str, Any], health: dict[str, Any]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    for task in tasks:
        if not lifecycle_is_blocked_task(task):
            continue
        blockers.append(
            {
                "reason": str(task.get("human_gate_reason") or task.get("last_transition_reason") or task.get("status") or "blocked"),
                "task_id": task.get("task_id"),
                "status": task.get("status"),
                "task_dir": task.get("task_dir"),
            }
        )
    if station_id == "source_data":
        for source in sources.get("blocked_sources", []) if isinstance(sources.get("blocked_sources"), list) else []:
            if not isinstance(source, dict):
                continue
            blockers.append(
                {
                    "reason": str(source.get("reason") or source.get("approval_status") or "blocked_source"),
                    "source_id": source.get("source_id"),
                    "status": source.get("approval_status") or source.get("status"),
                    "path": sources.get("path"),
                }
            )
    if station_id == "topic":
        for alert in health.get("blockers", []) if isinstance(health.get("blockers"), list) else []:
            if isinstance(alert, dict):
                blockers.append(
                    {
                        "reason": str(alert.get("message") or alert.get("check") or "health_blocker"),
                        "status": alert.get("severity"),
                        "path": alert.get("path"),
                    }
                )
    return blockers[:RECENT_LIMIT]


def lifecycle_task_summary(task: dict[str, Any] | None) -> dict[str, Any] | None:
    if not task:
        return None
    return {
        "task_id": task.get("task_id"),
        "title": task.get("title"),
        "status": task.get("status"),
        "type": task.get("type"),
        "requires_human": task.get("requires_human"),
        "task_dir": task.get("task_dir"),
        "files": task.get("files", [])[:RECENT_LIMIT],
    }


def lifecycle_station_summary(status: str, tasks: list[dict[str, Any]], outputs: list[dict[str, Any]], blockers: list[dict[str, Any]]) -> str:
    if blockers:
        return f"{len(blockers)} blocker(s), {len(tasks)} task(s), {len(outputs)} accepted output(s)"
    if status == "complete":
        return f"{len(outputs) or len(tasks)} completed output/task item(s)"
    if tasks:
        return f"{len(tasks)} task(s), {len(outputs)} accepted output(s)"
    if status == "ready":
        return "station artifacts are available; no task has claimed this station yet"
    return "no station artifacts or tasks found yet"


def lifecycle_snapshot(
    ops_dir: Path,
    tasks: dict[str, Any],
    accepted_outputs: dict[str, Any],
    delivered_projects: dict[str, Any],
    health: dict[str, Any],
    sources: dict[str, Any],
) -> dict[str, Any]:
    tasks_by_station = lifecycle_task_rows(tasks)
    outputs_by_station = lifecycle_output_rows(delivered_projects)
    stations: list[dict[str, Any]] = []
    for station in LIFECYCLE_STATIONS:
        station_id = str(station["id"])
        station_tasks = tasks_by_station.get(station_id, [])
        outputs = outputs_by_station.get(station_id, [])
        artifacts = lifecycle_station_artifacts(ops_dir, station)
        status = lifecycle_station_status(station_tasks, outputs, artifacts)
        blockers = lifecycle_blockers_for_station(station_id, station_tasks, sources, health)
        if blockers:
            status = "blocked"
        active_task = next(
            (
                task
                for task in station_tasks
                if lifecycle_is_blocked_task(task)
                or str(task.get("status") or "") in LIFECYCLE_ACTIVE_STATUSES | LIFECYCLE_QUEUED_STATUSES
            ),
            None,
        )
        next_command = lifecycle_command_for_task(ops_dir, active_task) if active_task else lifecycle_command_for_station(ops_dir, station)
        stations.append(
            {
                "id": station_id,
                "label": station["label"],
                "objective": station["objective"],
                "status": status,
                "summary": lifecycle_station_summary(status, station_tasks, outputs, blockers),
                "accepted_outputs": outputs[:RECENT_LIMIT],
                "active_task": lifecycle_task_summary(active_task),
                "blockers": blockers,
                "next_recommended_task": active_task.get("title") if active_task else station["next_task"],
                "next_command": next_command,
                "owner_runner": lifecycle_owner_for_task(active_task, str(station["owner"])) if active_task else station["owner"],
                "artifact_links": artifacts,
            }
        )

    completed = [station for station in stations if station["status"] == "complete"]
    active = [station for station in stations if station["status"] in {"blocked", "active", "queued"}]
    missing = [station for station in stations if station["status"] == "missing"]
    if active:
        current = active[0]
    elif completed:
        current = next((station for station in stations if station["status"] in {"missing", "ready"}), stations[-1] if stations else None)
    else:
        current = stations[0] if stations else None
    return {
        "available": True,
        "status": "available",
        "station_count": len(stations),
        "completed_count": len(completed),
        "active_count": len(active),
        "missing_count": len(missing),
        "accepted_output_count": accepted_outputs.get("count", 0),
        "current_station_id": current.get("id") if current else None,
        "current_station_label": current.get("label") if current else None,
        "next_action": (current.get("next_command") or {}).get("command") if current else "",
        "stations": stations,
    }


def runs_snapshot(ops_dir: Path) -> dict[str, Any]:
    run_artifacts = ops_dir / "run_artifacts"
    if not run_artifacts.exists():
        return unavailable("run_artifacts_missing", "run artifacts are not available yet", run_artifacts)
    runs = []
    run_dirs = [path for path in run_artifacts.iterdir() if path.is_dir() and not path.name.startswith(".")]
    for run_dir in sorted(run_dirs, key=lambda path: path.stat().st_mtime, reverse=True):
        run_json = run_dir / "run.json"
        payload: dict[str, Any] = {}
        if run_json.exists():
            try:
                parsed = json.loads(run_json.read_text(encoding="utf-8"))
                if isinstance(parsed, dict):
                    payload = parsed
            except (OSError, json.JSONDecodeError) as exc:
                payload = {"warning": f"run.json could not be read: {exc}"}
        artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), dict) else {}
        stdout_log = Path(artifacts.get("stdout_log") or run_dir / "stdout.log")
        stderr_log = Path(artifacts.get("stderr_log") or run_dir / "stderr.log")
        final_message = Path(artifacts.get("final_message") or run_dir / "final_message.md")
        runs.append(
            {
                "run_id": payload.get("run_id", run_dir.name),
                "run_dir": str(run_dir),
                "status": payload.get("status", "unavailable"),
                "task_id": payload.get("task_id", "unavailable"),
                "job_id": payload.get("job_id", "unavailable"),
                "started_at": payload.get("started_at", "unavailable"),
                "finished_at": payload.get("finished_at", "unavailable"),
                "exit_code": payload.get("exit_code"),
                "command": payload.get("command", []),
                "prompt_id": payload.get("prompt_id", "unavailable"),
                "prompt_version": payload.get("prompt_version", "unavailable"),
                "final_message_preview": payload.get("final_message_preview") or tail_text(final_message, 800),
                "stdout_tail": tail_text(stdout_log, 1200),
                "stderr_tail": tail_text(stderr_log, 1200),
                "artifacts": {
                    "run_json": str(run_json),
                    "events_jsonl": artifacts.get("events_jsonl") or str(run_dir / "events.jsonl"),
                    "final_message": str(final_message),
                    "stdout_log": str(stdout_log),
                    "stderr_log": str(stderr_log),
                },
                "usage_ingestion": payload.get("usage_ingestion", {}),
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
    accepted_outputs, accepted_warnings = accepted_outputs_snapshot(ops_dir, current)
    delivered_projects = delivered_projects_snapshot(ops_dir, current)
    rejected_results, rejected_warnings = rejected_results_snapshot(ops_dir)
    cost = cost_snapshot(ops_dir, current)
    prompts = prompts_snapshot(ops_dir) if workspace_ready else unavailable("ops_dir_missing", "prompts are unavailable until research_ops exists", ops_dir)
    schedules = schedules_snapshot(ops_dir) if workspace_ready else unavailable("ops_dir_missing", "schedules are unavailable until research_ops exists", ops_dir)
    dashboards = dashboard_summaries(ops_dir, current) if workspace_ready else {
        "ideas": unavailable("ops_dir_missing", "ideas dashboard is unavailable until research_ops exists", ops_dir),
        "data": unavailable("ops_dir_missing", "data dashboard is unavailable until research_ops exists", ops_dir),
        "library": unavailable("ops_dir_missing", "library dashboard is unavailable until research_ops exists", ops_dir),
        "analysis": unavailable("ops_dir_missing", "analysis dashboard is unavailable until research_ops exists", ops_dir),
    }
    sources = source_snapshot(ops_dir, current, dashboards["data"]) if workspace_ready else unavailable("ops_dir_missing", "sources are unavailable until research_ops exists", ops_dir)
    runs = runs_snapshot(ops_dir) if workspace_ready else unavailable("ops_dir_missing", "runs are unavailable until research_ops exists", ops_dir)
    lifecycle = lifecycle_snapshot(ops_dir, tasks, accepted_outputs, delivered_projects, health, sources) if workspace_ready else unavailable(
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
    warnings.extend(collect_unavailable_warnings([readiness, health, prompts, schedules, sources, runs, lifecycle, *dashboards.values()]))

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
