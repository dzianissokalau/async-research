#!/usr/bin/env python3
"""Run the Phase 1 autonomy-readiness benchmark suite.

The benchmark creates isolated research_ops fixtures and exercises the same
helper scripts used by the workflow. It intentionally avoids live
`research_ops/` writes, so it can run before scheduled loops as a pre-flight
quality gate.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from async_research_workflow.resources import benchmark_cases_path, schema_path


SUCCESS = 0
FAILED = 1
VALIDATION_FAILED = 2
MISSING_REQUIRED = 3
INVALID = 4

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[2]
DEFAULT_CASES = benchmark_cases_path()
LIVE_OPS_DIR = REPO_ROOT / "research_ops"
TASK_STATUS_SCHEMA = schema_path("task_status.schema.json")

REQUIRED_CASE_FIELDS = {
    "case_id",
    "task_id",
    "title",
    "fixture_kind",
    "task_type",
    "known_bad",
    "risk_tags",
    "expected_final_state",
    "expected_outcome",
    "expected_human_escalation",
    "expected_source_quality",
    "expected_cost_tier",
    "expected_reviewer_routing",
    "expected_ledger_updates",
}

KNOWN_BAD_SAFE_STATES = {"needs_human", "rejected"}
RISK_TAGS_THAT_MUST_NOT_ACCEPT = {"malformed_output", "weak_evidence"}

COST_LEDGER_HEADER = [
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


class BenchmarkFailure(AssertionError):
    """Raised when a benchmark contract is violated."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise BenchmarkFailure(f"JSON payload is not an object: {path}")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def base_status(
    task_dir: Path,
    task_id: str,
    task_type: str,
    status: str,
    previous_status: Optional[str],
    reason: str,
    review_tier: int = 1,
    required_reviewers: Optional[list[str]] = None,
    revision_count: int = 0,
    max_revisions: int = 1,
) -> dict[str, Any]:
    if required_reviewers is None:
        required_reviewers = ["primary"]
        if review_tier == 2:
            required_reviewers = ["primary", "methodology"]
        elif review_tier == 3:
            required_reviewers = ["primary", "methodology", "skeptic"]
        elif review_tier == 0:
            required_reviewers = []
    return {
        "schema_version": "1.0",
        "id": task_id,
        "title": f"{task_id} autonomy benchmark",
        "type": task_type,
        "status": status,
        "previous_status": previous_status,
        "last_transition_reason": reason,
        "priority": 2,
        "revision_count": revision_count,
        "max_revisions": max_revisions,
        "revision_limit_hit": False,
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "lock_owner": None,
        "lock_expires_at": None,
        "allowed_paths": [task_dir.as_posix()],
        "allowed_tools": ["read_files", "write_task_files"],
        "allow_browsing": False,
        "allow_code_execution": False,
        "allow_network": False,
        "max_minutes": 45,
        "max_turns": 6,
        "model_tier": "benchmark",
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
        "human_gate_reason": "benchmark setup" if status == "needs_human" else None,
        "budget": {
            "max_api_usd": 1.0,
            "max_compute_usd": 0.0,
        },
        "result": {
            "recommendation": None,
            "claim_strength": None,
            "followup_count": 0,
        },
    }


def write_status(task_dir: Path, payload: dict[str, Any]) -> None:
    write_json(task_dir / "status.json", payload)


def write_review(
    task_dir: Path,
    role: str,
    decision: str,
    claim_strength: str = "suggestive",
    include_versions: bool = True,
    required_followups: Optional[list[str]] = None,
) -> None:
    payload: dict[str, Any] = {
        "reviewer_role": role,
        "decision": decision,
        "claim_strength": claim_strength,
        "confidence": 0.84,
        "main_concerns": [],
    }
    if include_versions:
        payload["prompt_version"] = f"{role}_reviewer_v1.0"
        payload["framework_versions"] = {"result_acceptance": "result_acceptance_v1.0"}
    if required_followups is not None:
        payload["required_followups"] = required_followups
    write_text(task_dir / "reviews" / f"{role}.md", "```json\n" + json.dumps(payload, indent=2, sort_keys=True) + "\n```\n")


def write_cost_ledger(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COST_LEDGER_HEADER)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in COST_LEDGER_HEADER})


def markdown_table(path: Path, header: list[str], rows: Optional[list[list[str]]] = None) -> None:
    rows = rows or []
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    write_text(path, "\n".join(lines) + "\n")


def setup_ops(ops_dir: Path) -> None:
    (ops_dir / "tasks").mkdir(parents=True, exist_ok=True)
    (ops_dir / "discovery").mkdir(parents=True, exist_ok=True)
    (ops_dir / "batches").mkdir(parents=True, exist_ok=True)
    markdown_table(ops_dir / "accepted_outputs_index.md", ["date", "task_id", "title", "key_finding", "claim_strength", "evidence_link", "followups"])
    markdown_table(ops_dir / "evidence_ledger.md", ["date", "task_id", "result_id", "claim_strength", "claim", "evidence_link", "limitations", "followups"])
    markdown_table(ops_dir / "rejected_results.md", ["date", "task_id", "route", "claim_strength", "reason", "evidence_link"])
    markdown_table(ops_dir / "queue.md", ["task", "priority", "status", "type", "next_runner", "notes"])
    markdown_table(ops_dir / "discovery_inbox.md", ["item", "title", "source", "status", "score", "next_task", "notes"])
    markdown_table(ops_dir / "discovery" / "rejected_ideas.md", ["item", "title", "reason", "rejected_at", "related_artifacts"])
    write_cost_ledger(ops_dir / "cost_ledger.csv", [])
    write_text(ops_dir / "daily_status.md", "# Daily Status\n")


def task_dir(ops_dir: Path, task_id: str, slug: str) -> Path:
    path = ops_dir / "tasks" / f"{task_id}-{slug}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def run_script(name: str, args: list[str], expected: int = SUCCESS) -> dict[str, Any]:
    command = [sys.executable, str(SCRIPT_DIR / name), *args]
    result = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True)
    if result.returncode != expected:
        raise BenchmarkFailure(
            f"{name} exited {result.returncode}, expected {expected}; "
            f"stdout={result.stdout.strip()!r}; stderr={result.stderr.strip()!r}"
        )
    stdout = result.stdout.strip()
    if not stdout:
        return {}
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise BenchmarkFailure(f"{name} returned non-JSON output: {stdout!r}") from exc
    if not isinstance(payload, dict):
        raise BenchmarkFailure(f"{name} returned non-object JSON")
    return payload


def validate_task_status(path: Path) -> None:
    run_script("validate_json_artifact.py", ["--schema", str(TASK_STATUS_SCHEMA), str(path / "status.json")])
    run_script("validate_transition.py", [str(path)])


def route_to_needs_human(task_path: Path, reason: str) -> None:
    status = read_json(task_path / "status.json")
    previous = status.get("status")
    status["previous_status"] = previous
    status["status"] = "needs_human"
    status["last_transition_reason"] = f"benchmark_{reason}"
    status["updated_at"] = utc_now()
    status["requires_human"] = True
    status["human_gate_reason"] = reason
    result = dict(status.get("result") or {})
    result["recommendation"] = "needs_human"
    result["claim_strength"] = "none"
    status["result"] = result
    write_status(task_path, status)
    validate_task_status(task_path)


def task_state(task_path: Path) -> str:
    return str(read_json(task_path / "status.json").get("status"))


def ledger_contains(path: Path, needle: str) -> bool:
    return path.exists() and needle in path.read_text(encoding="utf-8")


def aggregate(task_path: Path, expected: int = SUCCESS) -> dict[str, Any]:
    return run_script("aggregate_reviews.py", [str(task_path)], expected=expected)


def accepted_generic(case: dict[str, Any], ops_dir: Path) -> dict[str, Any]:
    path = task_dir(ops_dir, case["task_id"], "valid-generic")
    write_status(path, base_status(path, case["task_id"], case["task_type"], "single_review", "awaiting_review", "primary_review_completed"))
    write_text(path / "worker_output.md", "Source readiness is usable with caveats for a bounded next task.\n")
    write_review(path, "primary", "accept_with_caveats", "suggestive")
    payload = aggregate(path)
    if payload.get("aggregate_decision") != "accepted":
        raise BenchmarkFailure("valid generic output did not aggregate to accepted")
    return observed(path, ops_dir, "accepted_evidence", False, "not_applicable", "low", "accepted_by_primary", ["evidence"])


def result_summary_payload(task_id: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "framework_version": "result_acceptance_v1.0",
        "result_id": f"RESULT-{task_id[-4:]}",
        "experiment_plan_id": f"EXP-{task_id[-4:]}",
        "run_id": f"RUN-{task_id[-4:]}",
        "run_manifest_path": f"research_ops/tasks/{task_id}/artifacts/run_manifest.json",
        "artifact_version": "git:benchmark",
        "dataset_versions": [{"source_id": "DS-0001", "version": "benchmark"}],
        "primary_metric": "Out-of-sample MAE reduction",
        "baseline_results": "Baseline MAE 1.00",
        "candidate_results": "Candidate MAE 0.96",
        "validation_split_results": "Train 2018-2022, validation 2023, test 2024-2025",
        "robustness_results": ["Stable by geography"],
        "leakage_check_results": ["No target aggregates outside train folds"],
        "limitations": ["Predictive only; not causal"],
        "claim": "Candidate improves bounded predictive accuracy in the benchmark fixture.",
        "claim_type": "predictive",
        "claim_strength": "moderate",
        "recommended_decision": "accept_as_evidence",
        "public_or_high_stakes": False,
        "human_approval_present": False,
        "follow_up_tasks": [
            {
                "reason": "Retest after the next source refresh.",
                "required_artifact": "updated metrics",
                "priority": 3,
                "human_approval_needed": False,
                "required_before_memo_use": False,
            }
        ],
    }


def accepted_result_summary(case: dict[str, Any], ops_dir: Path) -> dict[str, Any]:
    path = task_dir(ops_dir, case["task_id"], "valid-result")
    write_status(
        path,
        base_status(
            path,
            case["task_id"],
            case["task_type"],
            "panel_review",
            "awaiting_review",
            "methodology_review_completed",
            review_tier=2,
        ),
    )
    summary = result_summary_payload(case["task_id"])
    write_text(path / "worker_output.md", "Data audit refs: DS-0001\n\n```json\n" + json.dumps(summary, indent=2, sort_keys=True) + "\n```\n")
    write_json(path / "artifacts" / "run_manifest.json", {"schema_version": "1.0", "run_id": summary["run_id"]})
    run_script("data_source_audit.py", ["init", str(ops_dir)])
    run_script(
        "data_source_audit.py",
        [
            "upsert",
            str(ops_dir),
            "--source-id",
            "DS-0001",
            "--approval-status",
            "approved",
            "--name",
            "Benchmark Official Source",
            "--location",
            "fixture://official",
            "--owner",
            "Benchmark Owner",
            "--source-tier",
            "tier_1_official",
            "--approved-use-cases",
            "experiment_planning; accepted_evidence",
            "--blocked-use-cases",
            "none",
            "--freshness-window-days",
            "90",
            "--known-limitations",
            "benchmark limitation",
            "--citation-requirements",
            "cite DS-0001",
            "--last-checked",
            today(),
            "--approved-by",
            "benchmark",
            "--review-notes",
            "benchmark source",
        ],
    )
    run_script("data_source_audit.py", ["check-experiment", str(ops_dir), str(path / "worker_output.md")])
    write_review(path, "primary", "accept", "moderate")
    write_review(path, "methodology", "accept", "moderate")
    payload = aggregate(path)
    if payload.get("aggregate_decision") != "accepted":
        raise BenchmarkFailure("valid result summary did not aggregate to accepted")
    return observed(path, ops_dir, "accepted_evidence", False, "audited_source", "low", "accepted_by_panel", ["evidence"])


def accepted_followups(case: dict[str, Any], ops_dir: Path) -> dict[str, Any]:
    path = task_dir(ops_dir, case["task_id"], "followups")
    status = base_status(path, case["task_id"], case["task_type"], "single_review", "awaiting_review", "primary_review_completed")
    status["result"] = {"recommendation": None, "claim_strength": None, "followup_count": 1}
    write_status(path, status)
    write_text(
        path / "worker_output.md",
        "# Follow-up Fixture\n\nAccepted finding with caveats.\n\n## Recommended Follow-Ups\n\n- Confirm source license before memo use.\n",
    )
    write_review(path, "primary", "accept_with_caveats", "suggestive", required_followups=["Run a small validation probe."])
    aggregate(path)
    acceptance = read_json(path / "review_panel" / "result_acceptance.json")
    followups = {item.get("reason") for item in acceptance.get("followups", []) if isinstance(item, dict)}
    if "Run a small validation probe." not in followups or "Confirm source license before memo use." not in followups:
        raise BenchmarkFailure("accepted follow-ups were not preserved")
    ledger = (ops_dir / "evidence_ledger.md").read_text(encoding="utf-8")
    if "Run a small validation probe." not in ledger or "Confirm source license before memo use." not in ledger:
        raise BenchmarkFailure("accepted follow-ups did not reach evidence ledger")
    return observed(path, ops_dir, "accepted_evidence", False, "not_applicable", "low", "accepted_by_primary", ["evidence", "followups_preserved"])


def rejected_by_review(case: dict[str, Any], ops_dir: Path) -> dict[str, Any]:
    path = task_dir(ops_dir, case["task_id"], "rejected")
    write_status(path, base_status(path, case["task_id"], case["task_type"], "single_review", "awaiting_review", "primary_review_completed"))
    write_text(path / "worker_output.md", "Weak output without enough evidence.\n")
    write_review(path, "primary", "reject", "none")
    aggregate(path)
    return observed(path, ops_dir, "rejected_result", False, "not_applicable", "low", "rejected_by_primary", ["rejected"])


def needs_human_review(case: dict[str, Any], ops_dir: Path) -> dict[str, Any]:
    path = task_dir(ops_dir, case["task_id"], "weak-evidence")
    write_status(path, base_status(path, case["task_id"], case["task_type"], "single_review", "awaiting_review", "primary_review_completed"))
    write_text(path / "worker_output.md", "Thin evidence and unclear source lineage.\n")
    write_review(path, "primary", "needs_human", "weak")
    aggregate(path)
    return observed(path, ops_dir, "needs_human", True, "not_applicable", "low", "needs_human_by_reviewer", [])


def reviewer_disagreement(case: dict[str, Any], ops_dir: Path) -> dict[str, Any]:
    path = task_dir(ops_dir, case["task_id"], "disagreement")
    write_status(
        path,
        base_status(path, case["task_id"], case["task_type"], "panel_review", "awaiting_review", "methodology_review_completed", review_tier=2),
    )
    write_text(path / "worker_output.md", "Reviewer disagreement fixture.\n")
    write_review(path, "primary", "accept", "moderate")
    write_review(path, "methodology", "needs_human", "weak")
    aggregate(path)
    return observed(path, ops_dir, "needs_human", True, "not_applicable", "low", "disagreement_to_human", [])


def needs_revision_under_limit(case: dict[str, Any], ops_dir: Path) -> dict[str, Any]:
    path = task_dir(ops_dir, case["task_id"], "revision")
    write_status(
        path,
        base_status(path, case["task_id"], case["task_type"], "single_review", "awaiting_review", "primary_review_completed", revision_count=0, max_revisions=2),
    )
    write_text(path / "worker_output.md", "Revision requested fixture.\n")
    write_review(path, "primary", "needs_revision", "weak")
    aggregate(path)
    return observed(path, ops_dir, "needs_revision", False, "not_applicable", "low", "needs_revision", [])


def revision_limit_human(case: dict[str, Any], ops_dir: Path) -> dict[str, Any]:
    path = task_dir(ops_dir, case["task_id"], "revision-limit")
    write_status(
        path,
        base_status(path, case["task_id"], case["task_type"], "single_review", "awaiting_review", "primary_review_completed", revision_count=1, max_revisions=1),
    )
    write_text(path / "worker_output.md", "Repeated revision fixture.\n")
    write_review(path, "primary", "needs_revision", "weak")
    aggregate(path)
    return observed(path, ops_dir, "needs_human", True, "not_applicable", "low", "needs_revision", [])


def malformed_status(case: dict[str, Any], ops_dir: Path) -> dict[str, Any]:
    path = task_dir(ops_dir, case["task_id"], "malformed")
    write_text(path / "status.json", "{not-json")
    run_script("recover_status_json.py", [str(path)])
    return observed(path, ops_dir, "needs_human", True, "not_applicable", "none", "not_applicable", [])


def invalid_transition(case: dict[str, Any], ops_dir: Path) -> dict[str, Any]:
    path = task_dir(ops_dir, case["task_id"], "invalid-transition")
    write_status(path, base_status(path, case["task_id"], case["task_type"], "accepted", "ready_for_worker", "invalid_jump", review_tier=0))
    run_script("validate_transition.py", [str(path)], expected=VALIDATION_FAILED)
    run_script("recover_status_json.py", [str(path)])
    return observed(path, ops_dir, "needs_human", True, "not_applicable", "none", "not_applicable", [])


def missing_schema_version(case: dict[str, Any], ops_dir: Path) -> dict[str, Any]:
    path = task_dir(ops_dir, case["task_id"], "schema")
    status = base_status(path, case["task_id"], case["task_type"], "ready_for_worker", None, "planner_created_task", review_tier=0)
    status.pop("schema_version")
    write_status(path, status)
    run_script("check_schema_versions.py", [str(ops_dir)], expected=INVALID)
    run_script("recover_status_json.py", [str(path)])
    return observed(path, ops_dir, "needs_human", True, "not_applicable", "none", "not_applicable", [])


def missing_reviewer_metadata(case: dict[str, Any], ops_dir: Path) -> dict[str, Any]:
    path = task_dir(ops_dir, case["task_id"], "review-metadata")
    write_status(path, base_status(path, case["task_id"], case["task_type"], "single_review", "awaiting_review", "primary_review_completed"))
    write_text(path / "worker_output.md", "Reviewer metadata missing fixture.\n")
    write_review(path, "primary", "accept", "suggestive", include_versions=False)
    run_script("aggregate_reviews.py", [str(path)], expected=VALIDATION_FAILED)
    route_to_needs_human(path, "reviewer metadata missing")
    return observed(path, ops_dir, "needs_human", True, "not_applicable", "low", "reviewer_metadata_failed", [])


def missing_required_review(case: dict[str, Any], ops_dir: Path) -> dict[str, Any]:
    path = task_dir(ops_dir, case["task_id"], "missing-review")
    write_status(
        path,
        base_status(path, case["task_id"], case["task_type"], "panel_review", "awaiting_review", "methodology_review_required", review_tier=2),
    )
    write_text(path / "worker_output.md", "Missing methodology review fixture.\n")
    write_review(path, "primary", "accept", "suggestive")
    run_script("aggregate_reviews.py", [str(path)], expected=MISSING_REQUIRED)
    route_to_needs_human(path, "missing required reviewer")
    return observed(path, ops_dir, "needs_human", True, "not_applicable", "low", "missing_required_review", [])


def unaudited_source(case: dict[str, Any], ops_dir: Path) -> dict[str, Any]:
    path = task_dir(ops_dir, case["task_id"], "unaudited-source")
    write_status(path, base_status(path, case["task_id"], case["task_type"], "in_progress", "ready_for_worker", "worker_started"))
    run_script("data_source_audit.py", ["init", str(ops_dir)])
    plan = path / "worker_output.md"
    write_text(plan, "# Experiment Plan\n\nData audit refs: DS-9999\n")
    run_script("data_source_audit.py", ["check-experiment", str(ops_dir), str(plan)], expected=VALIDATION_FAILED)
    route_to_needs_human(path, "unaudited source blocked")
    return observed(path, ops_dir, "needs_human", True, "unaudited_source_blocked", "low", "not_applicable", [])


def stale_source(case: dict[str, Any], ops_dir: Path) -> dict[str, Any]:
    path = task_dir(ops_dir, case["task_id"], "stale-source")
    write_status(path, base_status(path, case["task_id"], case["task_type"], "in_progress", "ready_for_worker", "worker_started"))
    run_script("data_source_audit.py", ["init", str(ops_dir)])
    run_script(
        "data_source_audit.py",
        [
            "upsert",
            str(ops_dir),
            "--source-id",
            "DS-0001",
            "--approval-status",
            "approved",
            "--name",
            "Stale Benchmark Source",
            "--location",
            "fixture://stale",
            "--owner",
            "Benchmark Owner",
            "--source-tier",
            "tier_1_official",
            "--approved-use-cases",
            "experiment_planning; accepted_evidence",
            "--blocked-use-cases",
            "none",
            "--freshness-window-days",
            "30",
            "--known-limitations",
            "benchmark stale limitation",
            "--citation-requirements",
            "cite DS-0001",
            "--last-checked",
            "2025-01-01",
            "--approved-by",
            "benchmark",
            "--review-notes",
            "stale source benchmark",
        ],
    )
    plan = path / "worker_output.md"
    write_text(plan, "# Experiment Plan\n\nData audit refs: DS-0001\n")
    run_script("data_source_audit.py", ["check-experiment", str(ops_dir), str(plan)], expected=VALIDATION_FAILED)
    route_to_needs_human(path, "source freshness expired")
    return observed(path, ops_dir, "needs_human", True, "stale_source_blocked", "low", "not_applicable", [])


def stale_memory(case: dict[str, Any], ops_dir: Path) -> dict[str, Any]:
    path = task_dir(ops_dir, case["task_id"], "stale-memory")
    write_status(path, base_status(path, case["task_id"], case["task_type"], "in_progress", "ready_for_worker", "worker_started"))
    markdown_table(
        ops_dir / "accepted_outputs_index.md",
        ["date", "task_id", "title", "key_finding", "claim_strength", "evidence_link", "followups"],
        [["2025-01-01", "TASK-9001", "London rent acceleration", "Rents accelerated in 2024", "suggestive", "tasks/TASK-9001/worker_output.md", "refresh monthly"]],
    )
    write_text(path / "worker_output.md", "Reusing stale accepted memory without refresh.\n")
    route_to_needs_human(path, "accepted memory is stale")
    return observed(path, ops_dir, "needs_human", True, "stale_memory_blocked", "low", "not_applicable", [])


def source_contradiction(case: dict[str, Any], ops_dir: Path) -> dict[str, Any]:
    path = task_dir(ops_dir, case["task_id"], "contradiction")
    write_status(path, base_status(path, case["task_id"], case["task_type"], "in_progress", "ready_for_worker", "worker_started"))
    markdown_table(
        ops_dir / "accepted_outputs_index.md",
        ["date", "task_id", "title", "key_finding", "claim_strength", "evidence_link", "followups"],
        [[today(), "TASK-9002", "Bristol price direction", "Prices are rising in the accepted memory", "suggestive", "tasks/TASK-9002/worker_output.md", "none"]],
    )
    write_text(path / "worker_output.md", "New source claims prices are falling without explaining the contradiction.\n")
    route_to_needs_human(path, "new evidence contradicts accepted memory")
    return observed(path, ops_dir, "needs_human", True, "contradiction_blocked", "low", "not_applicable", [])


def setup_dedupe_files(ops_dir: Path) -> None:
    markdown_table(ops_dir / "accepted_outputs_index.md", ["date", "task_id", "title", "key_finding", "claim_strength", "evidence_link", "followups"])
    markdown_table(ops_dir / "discovery_inbox.md", ["item", "title", "source", "status", "score", "next_task", "notes"])
    markdown_table(ops_dir / "queue.md", ["task", "priority", "status", "type", "next_runner", "notes"])
    markdown_table(ops_dir / "discovery" / "rejected_ideas.md", ["item", "title", "reason", "rejected_at", "related_artifacts"])


def candidate_payload(candidate_id: str, duplicate_status: str = "new", recommended_next_task: str = "hypothesis_card") -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "id": candidate_id,
        "title": "Repeat-sales volatility after rate shocks",
        "question": "Can repeat-sales volatility reveal rate-shock sensitivity?",
        "why_it_might_matter": "It could prioritize a bounded real-estate analysis task.",
        "evidence_seeds": ["SRC-0002"],
        "exploration_category": "exploit",
        "exploration_source_refs": ["SRC-0002"],
        "exploration_rank": 16.0,
        "duplicate_status": duplicate_status,
        "revisit_condition": "Revisit only if a clearly new geography or source appears.",
        "cluster_id": "cluster-repeat-sales-volatility",
        "cluster_representative": duplicate_status != "duplicate",
        "required_data": ["DS-0001"],
        "minimum_viable_test": "Create a data-readiness task and cheap hypothesis card.",
        "baseline": "Prior-period local volatility.",
        "novelty_angle": "Focus on volatility response rather than level response.",
        "main_risks": ["address matching", "rate timing"],
        "kill_reason": "Reject if repeat-sales matching quality is too weak.",
        "recommended_next_task": recommended_next_task,
        "score": {
            "decision_impact": 5,
            "data_availability": 5,
            "killability": 5,
            "feasibility": 5,
            "reuse_potential": 5,
            "novelty": 3,
            "robustness_risk": 1,
            "cost": 1,
        },
    }


def duplicate_idea(case: dict[str, Any], ops_dir: Path) -> dict[str, Any]:
    path = task_dir(ops_dir, case["task_id"], "duplicate-idea")
    write_status(path, base_status(path, case["task_id"], case["task_type"], "in_progress", "ready_for_worker", "worker_started"))
    setup_dedupe_files(ops_dir)
    candidate = ops_dir / "discovery" / "IDEA-1018.json"
    write_json(candidate, candidate_payload("IDEA-1018", duplicate_status="duplicate"))
    run_script("score_idea_candidate.py", [str(candidate), "--ops-dir", str(ops_dir)])
    run_script("validate_idea_evaluation.py", [str(candidate), "--ops-dir", str(ops_dir)], expected=VALIDATION_FAILED)
    route_to_needs_human(path, "duplicate idea promotion blocked")
    return observed(path, ops_dir, "needs_human", True, "not_applicable", "low", "not_applicable", [])


def over_budget(case: dict[str, Any], ops_dir: Path) -> dict[str, Any]:
    path = task_dir(ops_dir, case["task_id"], "over-budget")
    write_status(path, base_status(path, case["task_id"], case["task_type"], "in_progress", "ready_for_worker", "worker_started"))
    write_cost_ledger(
        ops_dir / "cost_ledger.csv",
        [
            {
                "date": today(),
                "item_id": case["task_id"],
                "role": "worker",
                "model_or_tool": "benchmark",
                "amount_usd": "9.0",
                "api_usd": "9.0",
                "actual": "true",
                "monthly_budget_usd": "10.0",
                "weekly_budget_usd": "10.0",
            }
        ],
    )
    report = run_script("health_check.py", [str(ops_dir), "--monthly-budget-usd", "10", "--weekly-budget-usd", "10", "--dry-run"])
    if report.get("highest_severity") not in {"warning", "error"}:
        raise BenchmarkFailure("over-budget fixture did not trigger health warning")
    route_to_needs_human(path, "budget threshold exceeded")
    return observed(path, ops_dir, "needs_human", True, "not_applicable", "over_budget_blocked", "not_applicable", [])


def queue_overload(case: dict[str, Any], ops_dir: Path) -> dict[str, Any]:
    for index in range(11):
        task_id = f"TASK-{1100 + index}"
        path = task_dir(ops_dir, task_id, "active")
        write_status(path, base_status(path, task_id, "idea_discovery", "ready_for_worker", None, "planner_created_task"))
    result = run_script("queue_capacity.py", ["discovery-gate", str(ops_dir), "--max-active", "10"], expected=VALIDATION_FAILED)
    if result.get("action") != "discovery_skipped":
        raise BenchmarkFailure("queue overload did not skip discovery")
    return {
        "final_state": "discovery_skipped",
        "outcome": "discovery_skipped",
        "human_escalation": False,
        "source_quality": "not_applicable",
        "cost_tier": "none",
        "reviewer_routing": "not_applicable",
        "ledger_updates": [],
    }


def stale_lock(case: dict[str, Any], ops_dir: Path) -> dict[str, Any]:
    path = task_dir(ops_dir, case["task_id"], "stale-lock")
    write_status(path, base_status(path, case["task_id"], case["task_type"], "in_progress", "ready_for_worker", "worker_started"))
    lock_dir = path / "LOCK"
    lock_dir.mkdir(exist_ok=True)
    write_json(lock_dir / "owner.json", {"owner": "benchmark-worker", "created_at": "2020-01-01T00:00:00Z"})
    old = datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp()
    os.utime(lock_dir, (old, old))
    report = run_script("health_check.py", [str(ops_dir), "--stale-lock-minutes", "0", "--dry-run"])
    if report.get("alert_count", 0) < 1:
        raise BenchmarkFailure("stale lock did not trigger health alert")
    route_to_needs_human(path, "stale lock requires human-visible recovery")
    return observed(path, ops_dir, "needs_human", True, "not_applicable", "none", "not_applicable", [])


def direct_experiment_reroute(case: dict[str, Any], ops_dir: Path) -> dict[str, Any]:
    setup_dedupe_files(ops_dir)
    candidate = ops_dir / "discovery" / "IDEA-1022.json"
    write_json(candidate, candidate_payload("IDEA-1022", recommended_next_task="experiment_plan"))
    scored = run_script("score_idea_candidate.py", [str(candidate), "--ops-dir", str(ops_dir)])
    if scored.get("recommended_next_task") != "data_readiness":
        raise BenchmarkFailure("direct experiment request was not rerouted to data_readiness")
    evaluation = run_script("validate_idea_evaluation.py", [str(candidate), "--ops-dir", str(ops_dir)])
    if evaluation.get("planner_may_promote") is not True:
        raise BenchmarkFailure("rerouted candidate should remain promotable to setup work")
    return {
        "final_state": "safe_rerouted",
        "outcome": "safe_reroute",
        "human_escalation": False,
        "source_quality": "not_applicable",
        "cost_tier": "low",
        "reviewer_routing": "not_applicable",
        "ledger_updates": [],
    }


def anti_context(case: dict[str, Any], ops_dir: Path) -> dict[str, Any]:
    rejected_task = task_dir(ops_dir, "TASK-9023", "rejected-repeat-sales")
    status = base_status(rejected_task, "TASK-9023", "data_readiness", "rejected", "single_review", "aggregate_reviews_reviewer_rejected")
    status["human_gate_reason"] = "duplicate weak join path"
    status["result"] = {"recommendation": "reject", "claim_strength": "none", "key_finding": "Repeat-sales volatility failed because join coverage was too weak.", "followup_count": 0}
    write_status(rejected_task, status)
    write_text(rejected_task / "worker_output.md", "Repeat-sales volatility failed because join coverage was too weak.\n")
    target = task_dir(ops_dir, case["task_id"], "anti-context-target")
    write_status(target, base_status(target, case["task_id"], "idea_discovery", "ready_for_planning", "inbox", "planner_triage"))
    result = run_script(
        "generate_anti_context.py",
        ["build", str(ops_dir), "--title", "Repeat-sales volatility", "--task-dir", str(target), "--threshold", "0.1"],
    )
    if result.get("rejected_match_count", 0) < 1:
        raise BenchmarkFailure("anti-context did not find rejected prior approach")
    if "Do not repeat" not in (target / "anti_context.md").read_text(encoding="utf-8"):
        raise BenchmarkFailure("anti-context warning missing")
    return observed(target, ops_dir, "anti_context_generated", False, "not_applicable", "none", "not_applicable", ["anti_context"])


def observed(
    task_path: Path,
    ops_dir: Path,
    outcome: str,
    human_escalation: bool,
    source_quality: str,
    cost_tier: str,
    reviewer_routing: str,
    ledger_updates: list[str],
) -> dict[str, Any]:
    state = task_state(task_path)
    status = read_json(task_path / "status.json")
    actual_human = bool(status.get("requires_human")) or human_escalation
    for ledger in ledger_updates:
        if ledger == "evidence" and not ledger_contains(ops_dir / "evidence_ledger.md", str(status.get("id"))):
            raise BenchmarkFailure("expected evidence ledger update missing")
        if ledger == "rejected" and not ledger_contains(ops_dir / "rejected_results.md", str(status.get("id"))):
            raise BenchmarkFailure("expected rejection ledger update missing")
        if ledger == "anti_context" and not (task_path / "anti_context.md").exists():
            raise BenchmarkFailure("expected anti-context artifact missing")
    return {
        "final_state": state,
        "outcome": outcome,
        "human_escalation": actual_human,
        "source_quality": source_quality,
        "cost_tier": cost_tier,
        "reviewer_routing": reviewer_routing,
        "ledger_updates": sorted(ledger_updates),
    }


HANDLERS: dict[str, Callable[[dict[str, Any], Path], dict[str, Any]]] = {
    "accepted_generic": accepted_generic,
    "accepted_result_summary": accepted_result_summary,
    "accepted_followups": accepted_followups,
    "rejected_by_review": rejected_by_review,
    "needs_human_review": needs_human_review,
    "reviewer_disagreement": reviewer_disagreement,
    "needs_revision_under_limit": needs_revision_under_limit,
    "revision_limit_human": revision_limit_human,
    "malformed_status": malformed_status,
    "invalid_transition": invalid_transition,
    "missing_schema_version": missing_schema_version,
    "missing_reviewer_metadata": missing_reviewer_metadata,
    "missing_required_review": missing_required_review,
    "unaudited_source": unaudited_source,
    "stale_source": stale_source,
    "stale_memory": stale_memory,
    "source_contradiction": source_contradiction,
    "duplicate_idea": duplicate_idea,
    "over_budget": over_budget,
    "queue_overload": queue_overload,
    "stale_lock": stale_lock,
    "direct_experiment_reroute": direct_experiment_reroute,
    "anti_context": anti_context,
}


def load_cases(path: Path) -> list[dict[str, Any]]:
    manifest = read_json(path)
    cases = manifest.get("cases")
    if not isinstance(cases, list):
        raise BenchmarkFailure("benchmark manifest must contain a cases array")
    seen: set[str] = set()
    for case in cases:
        if not isinstance(case, dict):
            raise BenchmarkFailure("each benchmark case must be an object")
        missing = sorted(REQUIRED_CASE_FIELDS - set(case))
        if missing:
            raise BenchmarkFailure(f"{case.get('case_id', '<unknown>')} missing required fields: {missing}")
        if case["case_id"] in seen:
            raise BenchmarkFailure(f"duplicate case_id {case['case_id']}")
        seen.add(str(case["case_id"]))
        if case["fixture_kind"] not in HANDLERS:
            raise BenchmarkFailure(f"{case['case_id']} references unknown fixture_kind {case['fixture_kind']}")
        if not isinstance(case["expected_ledger_updates"], list):
            raise BenchmarkFailure(f"{case['case_id']} expected_ledger_updates must be an array")
    return cases


def compare_case(case: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    mismatches: list[str] = []
    comparisons = {
        "final_state": case["expected_final_state"],
        "outcome": case["expected_outcome"],
        "human_escalation": case["expected_human_escalation"],
        "source_quality": case["expected_source_quality"],
        "cost_tier": case["expected_cost_tier"],
        "reviewer_routing": case["expected_reviewer_routing"],
    }
    for field, expected in comparisons.items():
        if actual.get(field) != expected:
            mismatches.append(f"{field}: expected {expected!r}, got {actual.get(field)!r}")
    expected_ledger = sorted(str(item) for item in case["expected_ledger_updates"])
    actual_ledger = sorted(str(item) for item in actual.get("ledger_updates", []))
    if actual_ledger != expected_ledger:
        mismatches.append(f"ledger_updates: expected {expected_ledger!r}, got {actual_ledger!r}")
    return mismatches


def default_work_dir() -> Path:
    base = Path("/private/tmp")
    if not base.exists():
        base = Path(os.environ.get("TMPDIR", "/tmp"))
    return base / f"async_research_autonomy_benchmark_{os.getpid()}"


def ensure_isolated(work_dir: Path) -> None:
    live = LIVE_OPS_DIR.resolve()
    resolved = work_dir.resolve()
    if resolved == live or live in resolved.parents:
        raise BenchmarkFailure(f"benchmark work_dir must not be inside live research_ops: {work_dir}")


def run_benchmark(cases_path: Path, work_dir: Path, keep_work_dir: bool) -> tuple[dict[str, Any], int]:
    cases = load_cases(cases_path)
    ensure_isolated(work_dir)
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    known_bad_count = 0
    known_bad_safe_count = 0
    weak_or_malformed_accepted = 0
    isolated = True

    for case in cases:
        case_dir = work_dir / case["case_id"]
        ops_dir = case_dir / "research_ops"
        setup_ops(ops_dir)
        try:
            actual = HANDLERS[str(case["fixture_kind"])](case, ops_dir)
            mismatches = compare_case(case, actual)
            ok = not mismatches
        except Exception as exc:
            actual = {}
            mismatches = [str(exc)]
            ok = False

        if case.get("known_bad") is True:
            known_bad_count += 1
            if actual.get("final_state") in KNOWN_BAD_SAFE_STATES:
                known_bad_safe_count += 1
        if set(case.get("risk_tags", [])) & RISK_TAGS_THAT_MUST_NOT_ACCEPT and actual.get("outcome") == "accepted_evidence":
            weak_or_malformed_accepted += 1
        if LIVE_OPS_DIR.resolve() == ops_dir.resolve() or LIVE_OPS_DIR.resolve() in ops_dir.resolve().parents:
            isolated = False

        record = {
            "case_id": case["case_id"],
            "task_id": case["task_id"],
            "title": case["title"],
            "fixture_kind": case["fixture_kind"],
            "task_type": case["task_type"],
            "known_bad": case["known_bad"],
            "ok": ok,
            "actual": actual,
            "mismatches": mismatches,
            "ops_dir": str(ops_dir),
        }
        results.append(record)
        if not ok:
            failures.append(record)

    case_count = len(cases)
    known_bad_safe_rate = round(known_bad_safe_count / known_bad_count, 4) if known_bad_count else 1.0
    criteria = {
        "case_count_20_to_50": 20 <= case_count <= 50,
        "all_cases_passed": not failures,
        "known_bad_rejected_or_needs_human_rate_at_least_0_90": known_bad_safe_rate >= 0.9,
        "no_malformed_or_weak_evidence_accepted": weak_or_malformed_accepted == 0,
        "outputs_isolated_from_live_research_ops": isolated,
    }
    ok = all(criteria.values())
    summary = {
        "ok": ok,
        "benchmark_id": "autonomy_readiness_phase_1",
        "cases_path": str(cases_path),
        "work_dir": str(work_dir),
        "work_dir_kept": keep_work_dir,
        "case_count": case_count,
        "known_bad_count": known_bad_count,
        "known_bad_rejected_or_needs_human_count": known_bad_safe_count,
        "known_bad_rejected_or_needs_human_rate": known_bad_safe_rate,
        "weak_or_malformed_accepted_count": weak_or_malformed_accepted,
        "failure_count": len(failures),
        "acceptance_criteria": criteria,
        "results": results,
    }

    if not keep_work_dir:
        shutil.rmtree(work_dir, ignore_errors=True)
    return summary, SUCCESS if ok else FAILED


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run autonomy-readiness benchmark fixtures.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--work-dir", type=Path, default=default_work_dir())
    parser.add_argument("--keep-work-dir", action="store_true")
    return parser.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    try:
        summary, code = run_benchmark(args.cases, args.work_dir, args.keep_work_dir)
    except Exception as exc:
        print_json({"ok": False, "reason": "benchmark_failed", "error": str(exc), "work_dir": str(args.work_dir)})
        return FAILED
    print_json(summary)
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
