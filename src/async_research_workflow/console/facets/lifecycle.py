"""Console snapshot facet helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from async_research_workflow.console.artifacts import artifact_link
from async_research_workflow.console.facets.base import RECENT_LIMIT
from async_research_workflow.console.facets.base import command_hint

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
        "objective": "Anchor the project topic, scope, and intended target deliverable.",
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
        "label": "External Readiness Review",
        "objective": "Complete maturity review, resolve caveats, and decide whether the deliverable is ready to share.",
        "task_types": {"critic_review"},
        "keywords": ("review", "polish", "maturity", "qa", "acceptance"),
        "artifacts": (
            ("Human review queue", "human_review_queue.md"),
            ("Result acceptance policy", "result_acceptance_policy.md"),
            ("Rejected results", "rejected_results.md"),
        ),
        "owner": "reviewer",
        "next_task": "run maturity review and resolve remaining caveats",
        "command": ("Inspect workflow next", ["async-research", "workflow", "next", "<ops_dir>"]),
    },
]

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
        policy = task.get("mode_policy") if isinstance(task.get("mode_policy"), dict) else {}
        blockers.append(
            {
                "reason": str(task.get("human_gate_reason") or task.get("last_transition_reason") or task.get("status") or "blocked"),
                "task_id": task.get("task_id"),
                "status": task.get("status"),
                "task_dir": task.get("task_dir"),
                "mode_policy_status": policy.get("status"),
                "mode_policy_reason": policy.get("reason"),
                "gate_category": policy.get("gate_category"),
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
        "mode_policy": task.get("mode_policy", {}),
        "files": task.get("files", [])[:RECENT_LIMIT],
    }

def lifecycle_policy_gate_row(station: dict[str, Any], task: dict[str, Any]) -> dict[str, Any]:
    policy = task.get("mode_policy") if isinstance(task.get("mode_policy"), dict) else {}
    return {
        "station_id": station.get("id"),
        "station_label": station.get("label"),
        "task_id": task.get("task_id"),
        "title": task.get("title"),
        "task_dir": task.get("task_dir"),
        "status": task.get("status"),
        "gate_category": policy.get("gate_category"),
        "gate_categories": policy.get("gate_categories", []),
        "gate_trigger": policy.get("gate_trigger"),
        "policy_status": policy.get("status"),
        "policy_action": policy.get("policy_action"),
        "decision": policy.get("decision"),
        "target_status": policy.get("target_status"),
        "reason": policy.get("reason"),
        "instruction": policy.get("instruction"),
        "hard_stop_categories": policy.get("hard_stop_categories", []),
        "command": policy.get("auto_resolve_command"),
    }

def lifecycle_mode_effects(
    stations: list[dict[str, Any]],
    tasks_by_station: dict[str, list[dict[str, Any]]],
    mode: dict[str, Any],
    auto_decisions: dict[str, Any],
    current: dict[str, Any] | None,
) -> dict[str, Any]:
    auto_resolvable: list[dict[str, Any]] = []
    policy_blocked: list[dict[str, Any]] = []
    hard_stops: list[dict[str, Any]] = []
    policy_sequence: list[dict[str, Any]] = []
    stations_by_id = {str(station.get("id")): station for station in stations}
    for station_id, tasks in tasks_by_station.items():
        station = stations_by_id.get(station_id, {"id": station_id, "label": station_id})
        for task in tasks:
            policy = task.get("mode_policy") if isinstance(task.get("mode_policy"), dict) else {}
            if policy.get("applicable") is not True:
                continue
            row = lifecycle_policy_gate_row(station, task)
            if policy.get("can_auto_resolve") is True:
                auto_resolvable.append(row)
                policy_sequence.append({"kind": "auto_resolvable", **row})
            else:
                policy_blocked.append(row)
                policy_sequence.append({"kind": "policy_blocked", **row})
            if policy.get("hard_stop_categories"):
                hard_stops.append(row)
    blocked_stage = next((station for station in stations if station.get("status") == "blocked"), None)
    first_policy_gate = policy_sequence[0] if policy_sequence else None
    next_auto = first_policy_gate if first_policy_gate and first_policy_gate.get("kind") == "auto_resolvable" else None
    if next_auto:
        progression_label = "automatic_action_available"
    elif first_policy_gate or blocked_stage:
        progression_label = "blocked_by_policy_or_state"
    else:
        progression_label = "no_policy_blocker"
    return {
        "mode": mode.get("mode"),
        "risk_tolerance": mode.get("risk_tolerance"),
        "current_stage": {
            "id": current.get("id") if current else None,
            "label": current.get("label") if current else None,
            "status": current.get("status") if current else None,
        },
        "blocked_stage": {
            "id": blocked_stage.get("id") if blocked_stage else None,
            "label": blocked_stage.get("label") if blocked_stage else None,
            "status": blocked_stage.get("status") if blocked_stage else None,
        },
        "progression_label": progression_label,
        "next_automatic_action": next_auto,
        "auto_resolvable_gate_count": len(auto_resolvable),
        "auto_resolvable_gates": auto_resolvable[:RECENT_LIMIT],
        "policy_blocked_gate_count": len(policy_blocked),
        "policy_blocked_gates": policy_blocked[:RECENT_LIMIT],
        "hard_stop_count": len(hard_stops),
        "hard_stops": hard_stops[:RECENT_LIMIT],
        "auto_resolved_gate_count": auto_decisions.get("count", 0),
        "recent_auto_resolutions": auto_decisions.get("recent_rows", []),
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
    mode: dict[str, Any],
    auto_decisions: dict[str, Any],
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
        "mode_effects": lifecycle_mode_effects(stations, tasks_by_station, mode, auto_decisions, current),
        "stations": stations,
    }
