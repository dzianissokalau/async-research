#!/usr/bin/env python3
"""Validate async research experiment plans against experimentation_v1.0."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable, Optional

from async_research_workflow.resources import schema_path
from async_research_workflow.scripts.data_foundations import data_foundation_report
from async_research_workflow.scripts.data_source_audit import (
    EXPERIMENT_READY_STATUSES,
    load_valid_register,
    row_map,
)
from async_research_workflow.scripts.validate_json_artifact import load_json, validate


SUCCESS = 0
VALIDATION_FAILED = 2
INVALID_REQUEST = 3
MALFORMED = 4

SCHEMA_VERSION = "1.0"
FRAMEWORK_VERSION = "experimentation_v1.0"
PLAN_SCHEMA = schema_path("experiment_plan.schema.json")
STATUS_SCHEMA = schema_path("task_status.schema.json")
APPROVED_BASELINE_FAMILIES = {
    "naive_local_median",
    "prior_period_value",
    "geography_time_fixed_effects",
    "hedonic_regression_core_fields",
    "regularized_regression_benchmark",
}
LEAKAGE_FIELDS = [
    "feature_availability_before_prediction_date",
    "target_aggregates_train_only",
    "geography_summaries_time_safe",
    "publication_lags_modeled",
    "joins_point_in_time_or_versioned",
    "duplicate_or_repeat_transactions_handled",
]
SCORE_FIELDS = [
    "question_clarity",
    "data_readiness",
    "baseline_strength",
    "validation_design",
    "leakage_control",
    "robustness_design",
    "cost_realism",
    "decision_usefulness",
    "reproducibility",
    "claim_disciplined",
]


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def nonempty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def nonempty_list(value: Any) -> bool:
    return isinstance(value, list) and any(str(item).strip() for item in value)


def read_json_object(path: Path) -> dict[str, Any]:
    payload = load_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"JSON artifact is not an object: {path}")
    return payload


def extract_fenced_json(text: str) -> dict[str, Any]:
    for match in re.finditer(r"```(?:json|experiment_plan)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE):
        candidate = match.group(1).strip()
        if not candidate.startswith("{"):
            continue
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and (
            payload.get("framework_version") == FRAMEWORK_VERSION or "experiment_id" in payload
        ):
            return payload
    raise ValueError("no experiment plan JSON block found")


def load_plan(path: Path) -> dict[str, Any]:
    if path.suffix.lower() == ".json":
        return read_json_object(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"cannot read experiment plan {path}: {exc}") from exc
    return extract_fenced_json(text)


def infer_ops_dir(plan_path: Path, task_dir: Optional[Path]) -> Optional[Path]:
    if task_dir is not None:
        resolved = task_dir.resolve()
        if resolved.parent.name == "tasks":
            return resolved.parent.parent
    for parent in [plan_path.resolve(), *plan_path.resolve().parents]:
        if parent.name == "research_ops":
            return parent
        if parent.name == "tasks" and parent.parent.name == "research_ops":
            return parent.parent
    return None


def schema_errors(payload: dict[str, Any], schema_path: Path) -> list[dict[str, str]]:
    schema = load_json(schema_path)
    if not isinstance(schema, dict):
        return [{"path": "$", "message": f"schema is not an object: {schema_path}"}]
    return [error.to_dict() for error in validate(payload, schema)]


def load_task_status(task_dir: Optional[Path]) -> tuple[Optional[dict[str, Any]], list[dict[str, str]]]:
    if task_dir is None:
        return None, []
    try:
        status = read_json_object(task_dir / "status.json")
    except ValueError as exc:
        return None, [{"path": str(task_dir / "status.json"), "message": str(exc)}]
    return status, schema_errors(status, STATUS_SCHEMA)


def score_summary(plan: dict[str, Any]) -> dict[str, Any]:
    scores = plan.get("scores")
    if not isinstance(scores, dict):
        return {"total": 0, "average": 0, "minimum": 0, "missing": SCORE_FIELDS}
    values = [scores.get(field) for field in SCORE_FIELDS if isinstance(scores.get(field), int) and not isinstance(scores.get(field), bool)]
    missing = [field for field in SCORE_FIELDS if field not in scores]
    total = sum(values)
    average = round(total / len(values), 2) if values else 0
    minimum = min(values) if values else 0
    return {
        "total": total,
        "average": average,
        "minimum": minimum,
        "missing": missing,
    }


def add_failure(failures: list[dict[str, Any]], gate: str, message: str, details: Any = None) -> None:
    item: dict[str, Any] = {"gate": gate, "message": message}
    if details is not None:
        item["details"] = details
    failures.append(item)


def add_warning(warnings: list[dict[str, Any]], gate: str, message: str, details: Any = None) -> None:
    item: dict[str, Any] = {"gate": gate, "message": message}
    if details is not None:
        item["details"] = details
    warnings.append(item)


def validate_data_audit_refs(
    plan: dict[str, Any],
    ops_dir: Optional[Path],
    failures: list[dict[str, Any]],
) -> list[str]:
    refs = [str(item) for item in plan.get("data_audit_refs", []) if isinstance(item, str)]
    if not refs:
        add_failure(failures, "data_audit_refs", "Experiment plan must reference at least one DS-0000 data source.")
        return refs
    if ops_dir is None:
        add_failure(failures, "data_audit_refs", "Cannot infer research_ops directory; pass --ops-dir.")
        return refs
    try:
        _, rows = load_valid_register(ops_dir)
    except ValueError as exc:
        add_failure(failures, "data_audit_refs", "Data source audit register is missing or invalid.", str(exc))
        return refs
    by_id = row_map(rows)
    missing = [ref for ref in refs if ref not in by_id]
    not_ready = [
        {"source_id": ref, "status": by_id[ref]["status"]}
        for ref in refs
        if ref in by_id and by_id[ref]["status"] not in EXPERIMENT_READY_STATUSES
    ]
    if missing:
        add_failure(failures, "data_audit_refs", "Referenced data sources are missing from audit register.", missing)
    if not_ready:
        add_failure(failures, "data_audit_refs", "Referenced data sources are not experiment-ready.", not_ready)
    return refs


def validate_data_foundations(
    ops_dir: Optional[Path],
    failures: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> Optional[dict[str, Any]]:
    if ops_dir is None:
        return None
    report = data_foundation_report(ops_dir)
    if report.get("error_count", 0):
        add_failure(
            failures,
            "data_foundations",
            "Data foundation files are malformed or inconsistent.",
            {
                "error_count": report.get("error_count", 0),
                "errors": report.get("errors", []),
            },
        )
    if report.get("warning_count", 0):
        add_warning(
            warnings,
            "data_foundations",
            "Data foundation readiness warnings are present.",
            {
                "warning_count": report.get("warning_count", 0),
                "warnings": report.get("warnings", []),
                "active_idea_gap_refs": report.get("active_idea_gap_refs", []),
            },
        )
    return report


def validate_hard_gates(
    plan: dict[str, Any],
    ops_dir: Optional[Path],
    task_status: Optional[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str], Optional[dict[str, Any]]]:
    failures: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    refs = validate_data_audit_refs(plan, ops_dir, failures)
    data_foundations = validate_data_foundations(ops_dir, failures, warnings)

    baselines = plan.get("baselines")
    if not isinstance(baselines, list) or not baselines:
        add_failure(failures, "baselines", "At least one baseline is required.")
    else:
        approved = [
            item.get("family")
            for item in baselines
            if isinstance(item, dict) and item.get("family") in APPROVED_BASELINE_FAMILIES
        ]
        if not approved:
            add_failure(
                failures,
                "baselines",
                "At least one approved simple baseline family is required.",
                sorted(APPROVED_BASELINE_FAMILIES),
            )

    validation = plan.get("validation_design")
    if not isinstance(validation, dict):
        add_failure(failures, "validation_design", "Validation design is required.")
    else:
        for field in ("time_split", "spatial_holdout_or_blocked_validation", "leakage_review"):
            if not nonempty_text(validation.get(field)):
                add_failure(failures, "validation_design", f"{field} must be non-empty.")
        for field in ("segment_level_error_analysis", "missingness_and_join_quality_checks"):
            if not nonempty_list(validation.get(field)):
                add_failure(failures, "validation_design", f"{field} must include at least one check.")

    metrics = plan.get("metrics")
    if not isinstance(metrics, dict) or not nonempty_text(metrics.get("primary_metric")):
        add_failure(failures, "metrics", "Primary success metric is required.")
    if not isinstance(plan.get("success_criteria"), list) or not plan.get("success_criteria"):
        add_failure(failures, "success_criteria", "At least one success criterion is required.")
    if not isinstance(plan.get("failure_criteria"), list) or not plan.get("failure_criteria"):
        add_failure(failures, "failure_criteria", "At least one failure criterion is required.")

    leakage = plan.get("leakage_checklist")
    if not isinstance(leakage, dict):
        add_failure(failures, "leakage_checklist", "Leakage checklist is required.")
    else:
        for field in LEAKAGE_FIELDS:
            value = leakage.get(field)
            if value == "fail":
                add_failure(failures, "leakage_checklist", f"{field} is marked fail.")
            elif value in {"caveat", "not_applicable"}:
                add_warning(warnings, "leakage_checklist", f"{field} is marked {value}.", field)

    outputs = plan.get("outputs")
    if not isinstance(outputs, dict):
        add_failure(failures, "outputs", "Outputs object is required.")
    else:
        if not nonempty_text(outputs.get("output_dir")):
            add_failure(failures, "outputs", "output_dir is required.")
        if not nonempty_text(outputs.get("run_manifest_path")):
            add_failure(failures, "outputs", "run_manifest_path is required.")

    claim_limits = plan.get("claim_limits")
    if not isinstance(claim_limits, dict):
        add_failure(failures, "claim_limits", "Claim limits are required.")
    else:
        if not nonempty_text(claim_limits.get("claim_limit_text")):
            add_failure(failures, "claim_limits", "claim_limit_text is required.")
        if claim_limits.get("strongest_supported_claim") == "causal" and claim_limits.get("causal_claim_allowed") is not True:
            add_failure(failures, "claim_limits", "Causal strongest claim requires causal_claim_allowed=true.")
        if claim_limits.get("public_claim_allowed") is True:
            add_warning(warnings, "claim_limits", "Public claims require human approval before publication.")

    budget = plan.get("budget")
    if isinstance(budget, dict) and task_status is not None:
        task_budget = task_status.get("budget")
        if isinstance(task_budget, dict):
            plan_api = budget.get("max_api_usd")
            plan_compute = budget.get("max_compute_usd")
            task_api = task_budget.get("max_api_usd")
            task_compute = task_budget.get("max_compute_usd")
            if isinstance(plan_api, (int, float)) and isinstance(task_api, (int, float)) and plan_api > task_api:
                add_failure(failures, "budget", "Plan API budget exceeds task status budget.", {"plan": plan_api, "task": task_api})
            if isinstance(plan_compute, (int, float)) and isinstance(task_compute, (int, float)) and plan_compute > task_compute:
                add_failure(
                    failures,
                    "budget",
                    "Plan compute budget exceeds task status budget.",
                    {"plan": plan_compute, "task": task_compute},
                )

    if task_status is not None:
        if task_status.get("type") != "experiment_plan":
            add_failure(failures, "task_status", "Task status type must be experiment_plan.")
        status_refs = task_status.get("data_audit_refs")
        if isinstance(status_refs, list) and sorted(status_refs) != sorted(refs):
            add_failure(failures, "task_status", "Plan data_audit_refs must match status.json data_audit_refs.", {"plan": refs, "status": status_refs})
        framework_versions = task_status.get("framework_versions")
        if not isinstance(framework_versions, dict) or framework_versions.get("experimentation") != FRAMEWORK_VERSION:
            add_failure(failures, "task_status", "status.json must record experimentation_v1.0.")

    summary = score_summary(plan)
    if summary["minimum"] < 2:
        add_warning(warnings, "scores", "At least one experimentation score is below 2.", summary)
    if summary["average"] and summary["average"] < 3:
        add_warning(warnings, "scores", "Experimentation score average is below 3.", summary)

    return failures, warnings, refs, data_foundations


def validate_plan(args: argparse.Namespace) -> int:
    try:
        plan = load_plan(args.plan)
    except ValueError as exc:
        print_json({"ok": False, "reason": "plan_load_failed", "error": str(exc), "plan": str(args.plan)})
        return MALFORMED

    status, status_errors = load_task_status(args.task_dir)
    plan_errors = schema_errors(plan, args.schema)
    ops_dir = args.ops_dir or infer_ops_dir(args.plan, args.task_dir)
    failures, warnings, refs, data_foundations = validate_hard_gates(plan, ops_dir, status)

    if status_errors:
        failures.append({"gate": "task_status_schema", "message": "Task status failed schema validation.", "details": status_errors})
    if plan_errors:
        failures.append({"gate": "experiment_plan_schema", "message": "Experiment plan failed schema validation.", "details": plan_errors})

    ok = not failures
    report = {
        "ok": ok,
        "plan": str(args.plan),
        "task_dir": str(args.task_dir) if args.task_dir else None,
        "ops_dir": str(ops_dir) if ops_dir else None,
        "schema_version": plan.get("schema_version"),
        "framework_version": plan.get("framework_version"),
        "experiment_id": plan.get("experiment_id"),
        "task_id": plan.get("task_id"),
        "data_audit_refs": refs,
        "data_foundations": data_foundations,
        "score_summary": score_summary(plan),
        "hard_gate_failures": failures,
        "warnings": warnings,
        "next_step": "route to Tier 2 review" if ok else "revise experiment plan before review or run_analysis",
    }
    print_json(report)
    return SUCCESS if ok else VALIDATION_FAILED


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate an experiment plan against experimentation_v1.0.")
    parser.add_argument("plan", type=Path, help="Path to experiment_plan.json or markdown with a fenced JSON plan block.")
    parser.add_argument("--schema", type=Path, default=PLAN_SCHEMA)
    parser.add_argument("--ops-dir", type=Path)
    parser.add_argument("--task-dir", type=Path)
    return parser.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    if args.schema != PLAN_SCHEMA and not args.schema.exists():
        print_json({"ok": False, "reason": "schema_missing", "schema": str(args.schema)})
        return INVALID_REQUEST
    return validate_plan(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
