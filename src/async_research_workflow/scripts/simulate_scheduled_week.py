#!/usr/bin/env python3
"""Simulate one scheduled week of async research operations with fixtures.

The simulation is intentionally model-free and API-free. It creates an isolated
research_ops fixture, then drives the same helper scripts that scheduled jobs
would use: readiness gate, idea scoring, review aggregation, result acceptance,
accepted-output indexing, health checks, and metrics snapshots.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import importlib
import io
import json
import os
import shutil
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional


SUCCESS = 0
FAILED = 1
SCHEMA_VERSION = "1.0"

LEDGER_HEADER = [
    "date",
    "item_id",
    "role",
    "model_or_tool",
    "usage_source",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "input_usd",
    "output_usd",
    "api_usd",
    "compute_usd",
    "amount_usd",
    "human_minutes",
    "status",
    "actual",
    "monthly_budget_usd",
    "weekly_budget_usd",
    "notes",
]

REQUIRED_OPS_FILES = {
    "queue.md": "# Queue\n\n| task | priority | status | type | next_runner | notes |\n| --- | ---: | --- | --- | --- | --- |\n",
    "daily_status.md": "# Daily Status\n\nFixture scheduled-week simulation has not started.\n",
    "accepted_outputs_index.md": (
        "| accepted_date | task_id | title | key_finding | claim_type | freshness_window_days | next_recheck_date | "
        "revalidation_status | source_ids | claim_strength | caveats | followups | supersedes | superseded_by | evidence_link |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
    ),
    "evidence_ledger.md": (
        "| date | task_id | result_id | claim_strength | source_ids | revalidation_status | supersedes | superseded_by | claim | evidence_link | limitations | followups |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
    ),
    "rejected_results.md": "| date | task_id | route | claim_strength | reason | evidence_link |\n| --- | --- | --- | --- | --- | --- |\n",
    "discovery_inbox.md": "| item | title | source | status | score | next_task | notes |\n| --- | --- | --- | --- | ---: | --- | --- |\n",
    "decisions.md": "# Human Decisions\n\n| date | item_id | decision | approver | reason | next_status |\n| --- | --- | --- | --- | --- | --- |\n",
    "weekly_digest.md": "# Weekly Digest\n\nFixture scheduled-week simulation pending.\n",
    "escalation_policy.md": "# Research Ops Escalation Policy\n\nPolicy version: `escalation_policy_v1.0`\n",
}


class SimulationFailure(RuntimeError):
    """Raised when a simulated scheduled step violates an executable contract."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_at(day: date, hour: int = 9) -> str:
    return datetime(day.year, day.month, day.day, hour, 0, 0, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SimulationFailure(f"JSON artifact is not an object: {path}")
    return payload


def append_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(text)


def append_markdown_row(path: Path, row: Iterable[Any]) -> None:
    append_text(path, "| " + " | ".join(str(item).replace("|", "/") for item in row) + " |\n")


def script_module_name(name: str) -> str:
    return name[:-3] if name.endswith(".py") else name


def run_script(
    name: str,
    args: list[str],
    expected: Iterable[int] = (SUCCESS,),
) -> tuple[int, dict[str, Any]]:
    module_name = script_module_name(name)
    module = importlib.import_module(f"async_research_workflow.scripts.{module_name}")
    stdout = io.StringIO()
    stderr = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            return_code = int(module.main(list(args)))
    except SystemExit as exc:
        return_code = int(exc.code) if isinstance(exc.code, int) else FAILED
    expected_codes = set(expected)
    text = stdout.getvalue().strip()
    try:
        payload = json.loads(text) if text else {}
    except json.JSONDecodeError as exc:
        raise SimulationFailure(
            f"{name} returned non-JSON stdout: {text!r}; stderr={stderr.getvalue().strip()!r}"
        ) from exc
    if return_code not in expected_codes:
        raise SimulationFailure(
            f"{name} {' '.join(args)} exited {return_code}, expected {sorted(expected_codes)}; "
            f"stdout={text!r}; stderr={stderr.getvalue().strip()!r}"
        )
    return return_code, payload


def default_work_dir() -> Path:
    base = Path("/private/tmp")
    if not base.exists():
        base = Path(os.environ.get("TMPDIR", "/tmp"))
    return base / f"async_research_scheduled_week_{os.getpid()}"


def ensure_empty_work_dir(path: Path) -> None:
    if path.exists():
        resolved = path.resolve()
        safe_roots = [Path("/private/tmp").resolve(), Path(os.environ.get("TMPDIR", "/tmp")).resolve()]
        if not any(str(resolved).startswith(str(root)) for root in safe_roots):
            raise SimulationFailure(f"refusing to delete non-temporary work dir: {path}")
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def ensure_simulation_work_dir_isolated(work_dir: Path, source_ops_dir: Path) -> None:
    resolved_work = work_dir.resolve()
    resolved_source = source_ops_dir.resolve()
    if resolved_work == resolved_source or is_relative_to(resolved_work, resolved_source) or is_relative_to(resolved_source, resolved_work):
        raise SimulationFailure(
            f"simulation work_dir must not overlap source ops_dir: work_dir={work_dir}, ops_dir={source_ops_dir}"
        )


def write_cost_ledger_header(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        csv.DictWriter(handle, fieldnames=LEDGER_HEADER).writeheader()


def append_cost(
    ops_dir: Path,
    when: date,
    item_id: str,
    role: str,
    amount: float,
    notes: str,
    total_tokens: int = 0,
    actual: bool = False,
) -> None:
    ledger = ops_dir / "cost_ledger.csv"
    if not ledger.exists():
        write_cost_ledger_header(ledger)
    row = {
        "date": when.isoformat(),
        "item_id": item_id,
        "role": role,
        "model_or_tool": "fixture-noop",
        "usage_source": "scheduled_week_simulation",
        "input_tokens": str(total_tokens // 2) if total_tokens else "",
        "output_tokens": str(total_tokens - (total_tokens // 2)) if total_tokens else "",
        "total_tokens": str(total_tokens) if total_tokens else "",
        "input_usd": "",
        "output_usd": "",
        "api_usd": f"{amount:.4f}",
        "compute_usd": "0.0000",
        "amount_usd": f"{amount:.4f}",
        "human_minutes": "0",
        "status": "simulated",
        "actual": "true" if actual else "false",
        "monthly_budget_usd": "100.00",
        "weekly_budget_usd": "25.00",
        "notes": notes,
    }
    with ledger.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=LEDGER_HEADER)
        writer.writerow(row)


def simulated_cost(ops_dir: Path) -> float:
    ledger = ops_dir / "cost_ledger.csv"
    if not ledger.exists():
        return 0.0
    total = 0.0
    with ledger.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                total += float(row.get("amount_usd") or 0)
            except ValueError:
                continue
    return round(total, 4)


def initial_metrics(day: date, ops_dir: Path) -> dict[str, Any]:
    generated_at = iso_at(day, 0)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "period": "weekly",
        "label": "scheduled-week-initial",
        "ops_dir": str(ops_dir),
        "metrics": {
            "tasks_created": 0,
            "tasks_accepted": 0,
            "tasks_rejected": 0,
            "ideas_generated": 0,
            "ideas_promoted": 0,
            "ideas_rejected": 0,
            "human_minutes": 0,
            "estimated_cost_usd": 0.0,
            "panel_reviews": 0,
            "revision_loops": 0,
            "autonomous_completion_rate": 0.0,
            "needs_human_rate": 0.0,
            "false_accept_rate": 0.0,
            "false_reject_rate": 0.0,
            "cost_per_accepted_output": 0.0,
            "reviewer_disagreement_rate": 0.0,
            "stale_memory_reuse_count": 0,
            "unaudited_source_block_count": 0,
            "source_freshness_warning_count": 0,
            "revision_limit_hit_count": 0,
            "average_task_age_hours": 0.0,
            "queue_overload_count": 0,
            "readiness_gate_skip_count": 0,
            "accepted_outputs_revalidated_count": 0,
            "accepted_outputs_expired_count": 0,
        },
        "operational_view": {
            "autonomy": {"status": "initial"},
            "budget": {"estimated_cost_usd": 0.0},
            "queue": {"queue_depth": 0, "discovery_inbox_count": 0},
        },
    }


def initial_health(day: date, ops_dir: Path) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": iso_at(day, 0),
        "ops_dir": str(ops_dir),
        "alerts": [],
        "summary": {"task_count": 0, "alert_count": 0, "highest_severity": "ok"},
        "checks": {
            "status_counts": {},
            "queue_depth": 0,
            "discovery_inbox_count": 0,
            "cost": {
                "monthly_cost_usd": 0.0,
                "weekly_cost_usd": 0.0,
                "monthly_budget_usd": 100.0,
                "weekly_budget_usd": 25.0,
                "monthly_usage_ratio": 0.0,
                "weekly_usage_ratio": 0.0,
                "actual_usage_rows": 0,
            },
        },
    }


def prepare_ops_fixture(source_ops_dir: Path, work_dir: Path, start_day: date) -> Path:
    ops_dir = work_dir / "research_ops"
    ops_dir.mkdir(parents=True, exist_ok=True)
    for relative, text in REQUIRED_OPS_FILES.items():
        source = source_ops_dir / relative
        if source.exists() and relative in {"escalation_policy.md"}:
            atomic_write_text(ops_dir / relative, source.read_text(encoding="utf-8"))
        else:
            atomic_write_text(ops_dir / relative, text)

    for directory in ("tasks", "discovery", "review_panel", "batches"):
        (ops_dir / directory).mkdir(parents=True, exist_ok=True)

    atomic_write_text(
        ops_dir / "data_source_audit.md",
        "\n".join(
            [
                "# Data Source Audit Register",
                "",
                "Schema version: 1.0",
                "",
                "| source_id | source_name | url_or_domain | publisher_owner | source_tier | approval_status | approved_use_cases | blocked_use_cases | freshness_window_days | known_limitations | citation_requirements | last_reviewed | approved_by | review_notes |",
                "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
                f"| DS-0001 | Simulated official price data | fixture://scheduled-week/price-data | Scheduled Week Fixture | tier_1_official | approved | experiment_planning; accepted_evidence; context | none | 90 | Synthetic fixture source only. | Cite DS-0001 in accepted evidence. | {start_day.isoformat()} | simulation | Approved fixture source for no-op simulation. |",
            ]
        )
        + "\n",
    )
    write_cost_ledger_header(ops_dir / "cost_ledger.csv")
    metrics = initial_metrics(start_day, ops_dir)
    atomic_write_json(ops_dir / "metrics_baseline.json", {"schema_version": SCHEMA_VERSION, "created_at": metrics["generated_at"], "baseline_label": metrics["label"], "metrics": metrics["metrics"], "operational_view": metrics["operational_view"]})
    atomic_write_text(ops_dir / "metrics_history.jsonl", json.dumps(metrics, sort_keys=True) + "\n")
    atomic_write_json(ops_dir / "health_report.json", initial_health(start_day, ops_dir))
    atomic_write_text(ops_dir / "review_panel" / "policy.md", "# Review Panel Policy\n\nUse fixture reviewers only during scheduled-week simulation.\n")
    atomic_write_text(ops_dir / "review_panel" / "reviewer_registry.md", "# Reviewer Registry\n\n| role | fixture |\n| --- | --- |\n| primary | yes |\n| methodology | yes |\n")
    atomic_write_text(ops_dir / "discovery" / "clusters.md", "# Discovery Clusters\n\nNo clusters before simulation.\n")
    return ops_dir


def base_status(
    task_dir: Path,
    task_id: str,
    title: str,
    task_type: str,
    status: str,
    previous_status: Optional[str],
    reason: str,
    when: date,
    review_tier: int = 1,
    required_reviewers: Optional[list[str]] = None,
) -> dict[str, Any]:
    if required_reviewers is None:
        required_reviewers = ["primary"] if review_tier == 1 else ["primary", "methodology"]
    return {
        "schema_version": SCHEMA_VERSION,
        "prompt_versions": {
            "planner": "planner_v1.0",
            "discovery_scout": "discovery_scout_v1.0",
            "worker": "worker_v1.0",
            "primary_reviewer": "primary_reviewer_v1.0",
            "methodology_reviewer": "methodology_reviewer_v1.0",
            "review_aggregator": "review_aggregator_v1.0",
            "health_monitor": "health_monitor_v1.0",
        },
        "framework_versions": {
            "mission_scoring": "mission_scoring_v1.0",
            "idea_evaluation": "idea_evaluation_v1.0",
            "exploration": "exploration_v1.0",
            "result_acceptance": "result_acceptance_v1.0",
            "review_aggregation": "review_aggregation_v1.0",
            "accepted_outputs_index": "accepted_outputs_index_v1.0",
            "schema_versioning": "schema_versioning_v1.0",
            "data_source_audit": "data_source_audit_v1.0",
            "escalation_policy": "escalation_policy_v1.0",
        },
        "id": task_id,
        "title": title,
        "type": task_type,
        "status": status,
        "previous_status": previous_status,
        "last_transition_reason": reason,
        "priority": 2,
        "revision_count": 0,
        "max_revisions": 1,
        "revision_limit_hit": False,
        "created_at": iso_at(when, 10),
        "updated_at": iso_at(when, 10),
        "lock_owner": None,
        "lock_expires_at": None,
        "allowed_paths": [task_dir.as_posix(), "research_ops/discovery/IDEA-*.json"],
        "allowed_tools": ["read_files", "write_task_files", "run_helper_scripts"],
        "allow_browsing": False,
        "allow_code_execution": False,
        "allow_network": False,
        "max_minutes": 45,
        "max_turns": 6,
        "model_tier": "fixture-noop",
        "review_policy": {
            "tier": review_tier,
            "required_reviewers": required_reviewers,
            "panel_required": review_tier >= 2,
            "human_required_for_acceptance": False,
        },
        "escalate_to_tier": None,
        "escalation_reason": None,
        "escalation_requested_by": None,
        "escalation_requested_at": None,
        "requires_human": status == "needs_human",
        "human_gate_reason": None,
        "budget": {"max_api_usd": 0.0, "max_compute_usd": 0.0},
        "result": {"recommendation": None, "claim_strength": None, "followup_count": 0},
    }


def task_dir(ops_dir: Path, task_id: str, slug: str) -> Path:
    path = ops_dir / "tasks" / f"{task_id}-{slug}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_review(task: Path, role: str, decision: str, claim_strength: str, confidence: float, concerns: Optional[list[str]] = None) -> None:
    payload = {
        "reviewer_role": role,
        "decision": decision,
        "claim_strength": claim_strength,
        "confidence": confidence,
        "prompt_version": f"{role}_reviewer_v1.0" if role != "primary" else "primary_reviewer_v1.0",
        "framework_versions": {"result_acceptance": "result_acceptance_v1.0"},
        "main_concerns": concerns or [],
    }
    reviews = task / "reviews"
    reviews.mkdir(parents=True, exist_ok=True)
    atomic_write_text(reviews / f"{role}.md", "```json\n" + json.dumps(payload, indent=2, sort_keys=True) + "\n```\n")


def readiness_gate(ops_dir: Path, when: date) -> tuple[int, dict[str, Any]]:
    return run_script(
        "autonomy_readiness_gate.py",
        [str(ops_dir), "--now", iso_at(when, 8), "--dry-run"],
        expected=(0, 2, 3, 4, 5),
    )


def append_daily_event(ops_dir: Path, when: date, message: str) -> None:
    append_text(ops_dir / "daily_status.md", f"\n## Simulation Day {when.isoformat()}\n\n- {message}\n")


def day1_discovery(ops_dir: Path, when: date) -> dict[str, Any]:
    candidate = ops_dir / "discovery" / "IDEA-0701.json"
    atomic_write_json(
        candidate,
        {
            "schema_version": SCHEMA_VERSION,
            "id": "IDEA-0701",
            "title": "Fixture price-data readiness signal",
            "question": "Can approved fixture price data support a bounded data-readiness task?",
            "why_it_might_matter": "It verifies that discovery can create low-cost follow-up work without a model call.",
            "required_data": ["DS-0001"],
            "minimum_viable_test": "Create a data-readiness task and verify source governance.",
            "baseline": "No accepted data-readiness evidence.",
            "main_risks": ["fixture source is synthetic"],
            "kill_reason": "Reject if the source audit does not allow accepted evidence.",
            "recommended_next_task": "data_readiness",
            "score": {
                "decision_impact": 4,
                "data_availability": 5,
                "killability": 5,
                "feasibility": 5,
                "reuse_potential": 5,
                "novelty": 2,
                "robustness_risk": 1,
                "cost": 1,
            },
        },
    )
    _, scored = run_script("score_idea_candidate.py", [str(candidate), "--ops-dir", str(ops_dir)])
    append_markdown_row(
        ops_dir / "discovery_inbox.md",
        ["IDEA-0701", "Fixture price-data readiness signal", "scheduled-week", scored.get("status", "candidate"), scored.get("weighted_total", "n/a"), "data_readiness", "model-free discovery fixture"],
    )
    append_cost(ops_dir, when, "IDEA-0701", "discovery_scout", 0.002, "fixture discovery scout wrote and scored one candidate", total_tokens=200)
    append_daily_event(ops_dir, when, "Discovery scout wrote `IDEA-0701` and scored it with fixture data.")
    return {"candidate": str(candidate), "score": scored}


def day2_plan_tasks(ops_dir: Path, when: date) -> dict[str, Any]:
    accepted_task = task_dir(ops_dir, "TASK-0701", "sim-data-readiness")
    rejected_task = task_dir(ops_dir, "TASK-0702", "sim-weak-output")
    atomic_write_text(
        accepted_task / "task.md",
        "# TASK-0701 Simulated Data Readiness\n\nVerify that DS-0001 can support accepted fixture evidence.\n",
    )
    atomic_write_text(
        rejected_task / "task.md",
        "# TASK-0702 Simulated Weak Output\n\nProduce a deliberately weak output that should be rejected by review.\n",
    )
    status = base_status(
        accepted_task,
        "TASK-0701",
        "Simulated data-readiness acceptance path",
        "data_readiness",
        "ready_for_worker",
        None,
        "simulation_planner_created_task",
        when,
        review_tier=2,
    )
    status["data_audit_refs"] = ["DS-0001"]
    status["result"] = {
        "recommendation": None,
        "claim_strength": None,
        "claim_type": "source_data_readiness",
        "freshness_window_days": 90,
        "source_ids": ["DS-0001"],
        "caveats": ["fixture-only source; use for workflow testing, not market claims"],
        "followup_count": 0,
    }
    atomic_write_json(accepted_task / "status.json", status)

    weak_status = base_status(
        rejected_task,
        "TASK-0702",
        "Simulated rejected weak-output path",
        "data_readiness",
        "ready_for_worker",
        None,
        "simulation_planner_created_task",
        when,
        review_tier=1,
    )
    atomic_write_json(rejected_task / "status.json", weak_status)
    append_markdown_row(ops_dir / "queue.md", ["TASK-0701", "2", "ready_for_worker", "data_readiness", "worker", "simulation success path"])
    append_markdown_row(ops_dir / "queue.md", ["TASK-0702", "3", "ready_for_worker", "data_readiness", "worker", "simulation rejection path"])
    append_cost(ops_dir, when, "TASK-0701", "planner", 0.003, "fixture planner created accepted-path task", total_tokens=250)
    append_cost(ops_dir, when, "TASK-0702", "planner", 0.003, "fixture planner created rejected-path task", total_tokens=250)
    append_daily_event(ops_dir, when, "Planner created `TASK-0701` and `TASK-0702` from fixture discovery output.")
    return {"created_tasks": [str(accepted_task), str(rejected_task)]}


def day3_worker_completion(ops_dir: Path, when: date) -> dict[str, Any]:
    task = task_dir(ops_dir, "TASK-0701", "sim-data-readiness")
    status = read_json(task / "status.json")
    status["previous_status"] = "awaiting_review"
    status["status"] = "panel_review"
    status["last_transition_reason"] = "simulation_worker_completed_and_panel_review_started"
    status["updated_at"] = iso_at(when, 11)
    status["result"].update(
        {
            "key_finding": "DS-0001 is approved for accepted_evidence in the scheduled-week fixture.",
            "accepted_date": when.isoformat(),
            "next_recheck_date": (when + timedelta(days=90)).isoformat(),
            "revalidation_status": "current",
            "source_ids": ["DS-0001"],
            "followup_count": 0,
        }
    )
    atomic_write_json(task / "status.json", status)
    atomic_write_text(
        task / "worker_output.md",
        "# Simulated Data Readiness Output\n\n"
        "DS-0001 is approved for accepted_evidence and experiment_planning in this isolated fixture.\n\n"
        "## Evidence\n\n"
        "- Data audit refs: DS-0001\n"
        "- Scope: scheduled-week simulation only.\n",
    )
    append_cost(ops_dir, when, "TASK-0701", "worker", 0.006, "fixture worker completed acceptance-path output", total_tokens=500)
    append_daily_event(ops_dir, when, "Worker completed `TASK-0701` and routed it to panel review.")
    return {"completed_task": str(task)}


def day4_review_acceptance(ops_dir: Path, when: date) -> dict[str, Any]:
    task = task_dir(ops_dir, "TASK-0701", "sim-data-readiness")
    write_review(task, "primary", "accept_with_caveats", "suggestive", 0.88, ["Fixture source is synthetic and must not be reused as real market evidence."])
    write_review(task, "methodology", "accept_with_caveats", "suggestive", 0.84, ["Methodology path is sufficient for a no-op lifecycle test."])
    _, aggregated = run_script("aggregate_reviews.py", [str(task)])
    _, index = run_script("update_accepted_outputs_index.py", ["update", str(ops_dir), "--now", iso_at(when, 12)])
    _, revalidation = run_script("update_accepted_outputs_index.py", ["revalidation-report", str(ops_dir), "--now", iso_at(when, 12), "--write-schedule"])
    append_cost(ops_dir, when, "TASK-0701", "review_panel", 0.004, "fixture primary and methodology reviews accepted with caveats", total_tokens=350)
    append_daily_event(ops_dir, when, "Primary and methodology reviewers accepted `TASK-0701`; ledgers and accepted-output index were updated.")
    return {"aggregate": aggregated, "index": index, "revalidation": revalidation}


def day5_rejection_and_human_gate(ops_dir: Path, when: date) -> dict[str, Any]:
    weak_task = task_dir(ops_dir, "TASK-0702", "sim-weak-output")
    status = read_json(weak_task / "status.json")
    status["previous_status"] = "awaiting_review"
    status["status"] = "single_review"
    status["last_transition_reason"] = "simulation_worker_completed_and_primary_review_started"
    status["updated_at"] = iso_at(when, 10)
    status["result"] = {
        "recommendation": None,
        "claim_strength": None,
        "followup_count": 0,
    }
    atomic_write_json(weak_task / "status.json", status)
    atomic_write_text(
        weak_task / "worker_output.md",
        "# Simulated Weak Output\n\nThis output intentionally lacks a useful finding and should be rejected.\n",
    )
    write_review(weak_task, "primary", "reject", "none", 0.93, ["No actionable data-readiness finding."])
    _, rejected = run_script("aggregate_reviews.py", [str(weak_task)])

    human_task = task_dir(ops_dir, "TASK-0703", "sim-human-needed")
    atomic_write_text(
        human_task / "task.md",
        "# TASK-0703 Simulated Human Gate\n\nThis fixture verifies that unresolved human decisions stop later scheduled workers.\n",
    )
    human_status = base_status(
        human_task,
        "TASK-0703",
        "Simulated human decision blocker",
        "data_readiness",
        "needs_human",
        "ready_for_worker",
        "simulation_detected_ambiguous_task_contract",
        when,
        review_tier=1,
    )
    human_status["requires_human"] = True
    human_status["human_gate_reason"] = "Ambiguous task contract in scheduled-week fixture requires owner decision before workers continue."
    human_status["human_gate"] = {
        "policy_version": "escalation_policy_v1.0",
        "trigger": "ambiguous_task_contract",
        "triggered_at": iso_at(when, 13),
        "severity": "high",
        "reason": human_status["human_gate_reason"],
        "required_human_decision": "Clarify whether the fixture should be expanded, paused, or rejected.",
        "available_decisions": ["approve", "pause", "reject", "revise_scope"],
        "default_safe_action": "pause expensive scheduled workers",
        "retry_behavior": "resume only after async-research decision records a resolution",
        "ledger_update_behavior": "append a structured row to decisions.md",
        "triggered_triggers": ["ambiguous_task_contract"],
        "details": [{"artifact": "TASK-0703/task.md", "issue": "simulated ambiguity"}],
    }
    atomic_write_json(human_task / "status.json", human_status)
    append_markdown_row(ops_dir / "queue.md", ["TASK-0703", "1", "needs_human", "data_readiness", "human", "simulation structured human gate"])
    append_cost(ops_dir, when, "TASK-0702", "worker_review", 0.005, "fixture worker and review exercised rejection path", total_tokens=450)
    append_cost(ops_dir, when, "TASK-0703", "planner", 0.001, "fixture planner created structured needs_human task", total_tokens=100)
    append_daily_event(ops_dir, when, "`TASK-0702` was rejected and `TASK-0703` was routed to structured `needs_human`.")
    return {"rejected": rejected, "needs_human_task": str(human_task)}


def inject_readiness_skip_alert(ops_dir: Path, when: date, gate: dict[str, Any]) -> None:
    report_path = ops_dir / "health_report.json"
    report = read_json(report_path) if report_path.exists() else initial_health(when, ops_dir)
    alerts = report.get("alerts") if isinstance(report.get("alerts"), list) else []
    alerts.append(
        {
            "severity": "warning",
            "check": "readiness_gate_skip",
            "message": f"scheduled-week simulation skipped expensive workers because readiness gate returned {gate.get('decision')}",
            "details": {"exit_code": gate.get("exit_code"), "blocker_count": gate.get("blocker_count")},
        }
    )
    report["alerts"] = alerts
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    summary["alert_count"] = len(alerts)
    summary["highest_severity"] = "error" if any(alert.get("severity") == "error" for alert in alerts) else ("warning" if alerts else "ok")
    report["summary"] = summary
    atomic_write_json(report_path, report)


def day6_skip(ops_dir: Path, when: date, gate: dict[str, Any]) -> dict[str, Any]:
    inject_readiness_skip_alert(ops_dir, when, gate)
    append_daily_event(ops_dir, when, f"Readiness gate returned `{gate.get('decision')}`; expensive workers intentionally skipped.")
    return {"skipped": True, "gate_decision": gate.get("decision"), "exit_code": gate.get("exit_code")}


def day7_health_and_metrics(ops_dir: Path, when: date, prior_skip_count: int) -> dict[str, Any]:
    _, health = run_script(
        "health_check.py",
        [
            str(ops_dir),
            "--now",
            iso_at(when, 12),
            "--report-path",
            str(ops_dir / "health_report.json"),
            "--no-daily-status",
        ],
    )
    if prior_skip_count:
        report = read_json(ops_dir / "health_report.json")
        for index in range(prior_skip_count):
            inject_readiness_skip_alert(ops_dir, when, {"decision": "human_required", "exit_code": 5, "blocker_count": index + 1})
        report = read_json(ops_dir / "health_report.json")
    else:
        report = read_json(ops_dir / "health_report.json")
    _, metrics = run_script("metrics_history.py", ["append-snapshot", str(ops_dir), "--label", "scheduled_week_simulation", "--update-weekly-digest"])
    append_daily_event(ops_dir, when, "Weekly health and autonomy metrics snapshot completed.")
    return {"health": health, "health_report": report, "metrics": metrics}


def task_status_counts(ops_dir: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for status_path in sorted((ops_dir / "tasks").glob("*/status.json")):
        payload = read_json(status_path)
        status = str(payload.get("status", "unknown"))
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items()))


def markdown_contains(path: Path, text: str) -> bool:
    return path.exists() and text in path.read_text(encoding="utf-8")


def needs_human_structured(ops_dir: Path) -> bool:
    found = False
    for status_path in sorted((ops_dir / "tasks").glob("*/status.json")):
        payload = read_json(status_path)
        if payload.get("status") != "needs_human":
            continue
        found = True
        gate = payload.get("human_gate")
        required = {
            "policy_version",
            "trigger",
            "triggered_at",
            "severity",
            "reason",
            "required_human_decision",
            "available_decisions",
            "default_safe_action",
            "retry_behavior",
            "ledger_update_behavior",
        }
        if not isinstance(gate, dict) or not required <= set(gate):
            return False
    return found


def final_queue_size(ops_dir: Path) -> int:
    count = 0
    queue = ops_dir / "queue.md"
    if not queue.exists():
        return 0
    for raw in queue.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line.startswith("|") or "---" in line:
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if cells and cells[0].lower() in {"task", "id", "item"}:
            continue
        if any(cells):
            count += 1
    return count


def metrics_history_has_simulation(ops_dir: Path) -> bool:
    history = ops_dir / "metrics_history.jsonl"
    if not history.exists():
        return False
    return any("scheduled_week_simulation" in line for line in history.read_text(encoding="utf-8").splitlines())


def run_week(args: argparse.Namespace) -> dict[str, Any]:
    start_day = date.fromisoformat(args.start_date)
    work_dir = args.work_dir
    ensure_simulation_work_dir_isolated(work_dir, args.ops_dir)
    ensure_empty_work_dir(work_dir)
    ops_dir = prepare_ops_fixture(args.ops_dir, work_dir, start_day)

    events: list[dict[str, Any]] = []
    readiness_skips = 0
    days_completed = 0

    for offset in range(7):
        current_day = start_day + timedelta(days=offset)
        code, gate = readiness_gate(ops_dir, current_day)
        if code not in {0, 2}:
            readiness_skips += 1
        event: dict[str, Any] = {
            "day": offset + 1,
            "date": current_day.isoformat(),
            "readiness_exit_code": code,
            "readiness_decision": gate.get("decision"),
        }
        if offset == 0 and code in {0, 2}:
            event["step"] = "discovery_scout"
            event["result"] = day1_discovery(ops_dir, current_day)
        elif offset == 1 and code in {0, 2}:
            event["step"] = "task_creation"
            event["result"] = day2_plan_tasks(ops_dir, current_day)
        elif offset == 2 and code in {0, 2}:
            event["step"] = "worker_completion"
            event["result"] = day3_worker_completion(ops_dir, current_day)
        elif offset == 3 and code in {0, 2}:
            event["step"] = "review_aggregation_and_acceptance"
            event["result"] = day4_review_acceptance(ops_dir, current_day)
        elif offset == 4 and code in {0, 2}:
            event["step"] = "rejection_and_needs_human"
            event["result"] = day5_rejection_and_human_gate(ops_dir, current_day)
        elif offset == 5:
            event["step"] = "readiness_skip"
            event["result"] = day6_skip(ops_dir, current_day, gate)
        elif offset == 6:
            event["step"] = "weekly_health_and_metrics"
            event["result"] = day7_health_and_metrics(ops_dir, current_day, readiness_skips)
        else:
            event["step"] = "intentional_noop"
            event["result"] = {"reason": "readiness gate was not safe"}
        events.append(event)
        days_completed += 1

    counts = task_status_counts(ops_dir)
    queue_size = final_queue_size(ops_dir)
    accepted_ledger_updated = markdown_contains(ops_dir / "evidence_ledger.md", "TASK-0701")
    rejected_ledger_updated = markdown_contains(ops_dir / "rejected_results.md", "TASK-0702")
    accepted_index_updated = markdown_contains(ops_dir / "accepted_outputs_index.md", "TASK-0701")
    metrics_recorded = metrics_history_has_simulation(ops_dir)
    structured_human = needs_human_structured(ops_dir)
    queue_within_limit = queue_size <= args.max_queue_size

    ok = all(
        [
            days_completed == 7,
            counts.get("accepted", 0) >= 1,
            counts.get("rejected", 0) >= 1,
            counts.get("needs_human", 0) >= 1,
            readiness_skips >= 1,
            queue_within_limit,
            accepted_ledger_updated,
            rejected_ledger_updated,
            accepted_index_updated,
            metrics_recorded,
            structured_human,
        ]
    )

    return {
        "ok": ok,
        "source_ops_dir": str(args.ops_dir),
        "simulated_ops_dir": str(ops_dir),
        "work_dir": str(work_dir),
        "work_dir_kept": args.keep_work_dir,
        "external_api_calls": 0,
        "days_completed": days_completed,
        "readiness_gate_runs": 7,
        "readiness_skips": readiness_skips,
        "status_counts": counts,
        "accepted_count": counts.get("accepted", 0),
        "rejected_count": counts.get("rejected", 0),
        "needs_human_count": counts.get("needs_human", 0),
        "needs_human_structured": structured_human,
        "final_queue_size": queue_size,
        "max_queue_size": args.max_queue_size,
        "queue_growth_within_limit": queue_within_limit,
        "simulated_cost_usd": simulated_cost(ops_dir),
        "accepted_ledger_updated": accepted_ledger_updated,
        "rejected_ledger_updated": rejected_ledger_updated,
        "accepted_index_updated": accepted_index_updated,
        "metrics_history_recorded": metrics_recorded,
        "weekly_digest_updated": markdown_contains(ops_dir / "weekly_digest.md", "scheduled_week_simulation")
        or markdown_contains(ops_dir / "weekly_digest.md", "Autonomy Metrics"),
        "events": events,
    }


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simulate seven scheduled async research days with fixture outputs.")
    parser.add_argument("ops_dir", nargs="?", type=Path, default=Path("research_ops"))
    parser.add_argument("--work-dir", type=Path, default=default_work_dir())
    parser.add_argument("--keep-work-dir", action="store_true")
    parser.add_argument("--start-date", default=utc_now().date().isoformat(), help="First simulated day, YYYY-MM-DD.")
    parser.add_argument("--max-queue-size", type=int, default=10)
    return parser.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    if not args.ops_dir.exists():
        print_json({"ok": False, "reason": "ops_dir_missing", "ops_dir": str(args.ops_dir)})
        return FAILED
    try:
        report = run_week(args)
    except Exception as exc:
        print_json({"ok": False, "reason": "simulation_failed", "error": str(exc), "work_dir": str(args.work_dir)})
        if not args.keep_work_dir:
            shutil.rmtree(args.work_dir, ignore_errors=True)
        return FAILED

    if not args.keep_work_dir:
        shutil.rmtree(args.work_dir, ignore_errors=True)
    print_json(report)
    return SUCCESS if report["ok"] else FAILED


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
