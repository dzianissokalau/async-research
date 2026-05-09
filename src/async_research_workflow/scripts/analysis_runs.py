#!/usr/bin/env python3
"""Preflight analysis-run tasks against accepted experiment plans."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from async_research_workflow.resources import schema_path
from async_research_workflow.scripts.data_foundations import data_foundation_report
from async_research_workflow.scripts.data_source_audit import assess_source_refs
from async_research_workflow.scripts.update_accepted_outputs_index import (
    DEFAULT_INDEX_NAME,
    read_index_rows,
    utc_now,
)
from async_research_workflow.scripts.validate_experiment_plan import (
    PLAN_SCHEMA,
    load_plan,
    schema_errors as experiment_schema_errors,
    validate_hard_gates,
)
from async_research_workflow.scripts.validate_json_artifact import load_json, validate


SUCCESS = 0
VALIDATION_FAILED = 2
INVALID_REQUEST = 3
MALFORMED = 4

FRAMEWORK_VERSION = "analysis_run_v1.0"
MANIFEST_RELATIVE_PATH = Path("artifacts/analysis_run/run_manifest.json")
MANIFEST_SCHEMA = schema_path("analysis_run.schema.json")
RESULT_ACCEPTANCE_SCHEMA = schema_path("result_acceptance.schema.json")
STATUS_SCHEMA = schema_path("task_status.schema.json")
TASK_REF_RE = re.compile(r"\bTASK-[0-9]{4}\b")
INDEX_REF_RE = re.compile(r"\[([0-9]+)\]")
ALLOWED_PREFLIGHT_STATUSES = {"ready_for_worker", "in_progress"}

METHOD_FAMILY_TOKENS: dict[str, set[str]] = {
    "descriptive_statistics": {"descriptive", "summary", "statistics", "statistic"},
    "associative_analysis": {"associative", "association", "correlation", "regression"},
    "regression": {"regression", "linear", "glm"},
    "matching": {"matching", "match"},
    "forecasting": {"forecast", "forecasting", "time", "series", "time_series"},
    "classification": {"classification", "classifier"},
    "predictive_model": {
        "classification",
        "classifier",
        "forecast",
        "forecasting",
        "matching",
        "model",
        "prediction",
        "predictive",
        "regression",
        "tree",
        "xgboost",
    },
    "causal_design": {
        "causal",
        "difference",
        "differences",
        "did",
        "instrumental",
        "iv",
        "matching",
        "placebo",
        "rd",
        "regression_discontinuity",
    },
    "simulation": {"simulation", "sim"},
    "other": {"other"},
}


class PreflightMalformed(ValueError):
    """Raised when required task state cannot be parsed safely."""


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


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


def parse_now(value: Optional[str]) -> datetime:
    if not value:
        return utc_now()
    text = value.strip()
    try:
        if len(text) == 10:
            return datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("--now must use YYYY-MM-DD or ISO-8601 datetime") from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def schema_errors(payload: dict[str, Any], schema: Path) -> list[dict[str, str]]:
    try:
        loaded_schema = load_json(schema)
    except ValueError as exc:
        return [{"path": str(schema), "message": str(exc)}]
    if not isinstance(loaded_schema, dict):
        return [{"path": str(schema), "message": "schema is not an object"}]
    return [error.to_dict() for error in validate(payload, loaded_schema)]


def read_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = load_json(path)
    except ValueError as exc:
        raise PreflightMalformed(str(exc)) from exc
    if not isinstance(payload, dict):
        raise PreflightMalformed(f"JSON artifact is not an object: {path}")
    return payload


def resolved(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def is_relative_to(path: Path, base: Path) -> bool:
    try:
        resolved(path).relative_to(resolved(base))
        return True
    except ValueError:
        return False


def workspace_root(ops_dir: Path) -> Path:
    return ops_dir.parent if ops_dir.name == "research_ops" else ops_dir.parent


def workspace_path(ops_dir: Path, value: Any) -> Optional[Path]:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text == "none":
        return None
    candidate = Path(text)
    if candidate.is_absolute():
        return candidate
    if candidate.parts and candidate.parts[0] == ops_dir.name:
        return workspace_root(ops_dir) / candidate
    return ops_dir / candidate


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


def normalize_key(value: Any) -> str:
    text = normalize_text(value).lower()
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def path_text(path: Optional[Path]) -> Optional[str]:
    return str(path) if path is not None else None


def task_id_from_dir(task_dir: Path) -> str:
    match = TASK_REF_RE.search(task_dir.name)
    return match.group(0) if match else ""


def load_status(task_dir: Path, failures: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    status_path = task_dir / "status.json"
    if not status_path.exists():
        add_failure(failures, "task_status_exists", "Task status.json is required.", str(status_path))
        return None
    status = read_json_object(status_path)
    status_schema_errors = schema_errors(status, STATUS_SCHEMA)
    if status_schema_errors:
        add_failure(failures, "task_status_schema", "status.json failed task status schema validation.", status_schema_errors)
    if status.get("type") != "run_analysis":
        add_failure(
            failures,
            "task_type",
            "Preflight only supports run_analysis tasks.",
            {"expected": "run_analysis", "actual": status.get("type")},
        )
    if status.get("status") not in ALLOWED_PREFLIGHT_STATUSES:
        add_failure(
            failures,
            "task_status_runnable",
            "Analysis preflight may start only from ready_for_worker or in_progress tasks.",
            {"allowed": sorted(ALLOWED_PREFLIGHT_STATUSES), "actual": status.get("status")},
        )
    expected_id = task_id_from_dir(task_dir)
    if expected_id and status.get("id") != expected_id:
        add_failure(
            failures,
            "task_identity",
            "Task directory id and status.json id must match.",
            {"task_dir": task_dir.name, "status_id": status.get("id")},
        )
    return status


def load_manifest(task_dir: Path, failures: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    manifest_path = task_dir / MANIFEST_RELATIVE_PATH
    if not manifest_path.exists():
        add_failure(
            failures,
            "manifest_exists",
            "Analysis run manifest is required before preflight.",
            str(manifest_path),
        )
        return None
    manifest = read_json_object(manifest_path)
    manifest_errors = schema_errors(manifest, MANIFEST_SCHEMA)
    if manifest_errors:
        add_failure(failures, "manifest_schema", "run_manifest.json failed analysis-run schema validation.", manifest_errors)
    if manifest.get("framework_version") != FRAMEWORK_VERSION:
        add_failure(
            failures,
            "manifest_framework_version",
            "Manifest must record analysis_run_v1.0.",
            {"expected": FRAMEWORK_VERSION, "actual": manifest.get("framework_version")},
        )
    return manifest


def find_task_dir_by_id(ops_dir: Path, task_id: str) -> tuple[Optional[Path], Optional[str]]:
    tasks_dir = ops_dir / "tasks"
    if not tasks_dir.exists():
        return None, f"tasks directory not found: {tasks_dir}"
    candidates = sorted(path for path in tasks_dir.iterdir() if path.is_dir() and path.name.startswith(task_id))
    verified: list[Path] = []
    for candidate in candidates:
        status_path = candidate / "status.json"
        if not status_path.exists():
            continue
        try:
            status = read_json_object(status_path)
        except PreflightMalformed:
            continue
        if status.get("id") == task_id:
            verified.append(candidate)
    if len(verified) == 1:
        return verified[0], None
    if len(verified) > 1:
        return None, f"multiple task directories have status id {task_id}: {[str(path) for path in verified]}"
    if len(candidates) == 1:
        return candidates[0], None
    if len(candidates) > 1:
        return None, f"multiple task directories match {task_id}: {[str(path) for path in candidates]}"
    return None, f"task directory for {task_id} not found"


def indexed_accepted_task(ops_dir: Path, task_id: str, now: datetime) -> Optional[dict[str, str]]:
    rows = read_index_rows(ops_dir / DEFAULT_INDEX_NAME, now=now)
    for row in rows:
        if row.get("task_id") == task_id:
            return row
    return None


def plan_ref_index(ref: Any, prefix: str) -> Optional[int]:
    text = normalize_text(ref)
    if not text.startswith(prefix):
        return None
    match = INDEX_REF_RE.search(text)
    if match is None:
        return None
    return int(match.group(1))


def compatible_method_family(method_family: str, method_class: Any) -> bool:
    family = normalize_key(method_family)
    method = normalize_key(method_class)
    if family == "other":
        return True
    if method == family or method.startswith(f"{family}_") or family in method:
        return True
    method_tokens = set(method.split("_"))
    allowed = METHOD_FAMILY_TOKENS.get(family, set())
    if method in allowed:
        return True
    if method_tokens & allowed:
        return True
    return any(token in method for token in allowed if len(token) >= 4)


def validate_manifest_identity(
    task_dir: Path,
    status: Optional[dict[str, Any]],
    manifest: dict[str, Any],
    failures: list[dict[str, Any]],
) -> None:
    expected_task_id = task_id_from_dir(task_dir)
    if status is not None and manifest.get("task_id") != status.get("id"):
        add_failure(
            failures,
            "manifest_task_identity",
            "Manifest task_id must match status.json id.",
            {"manifest": manifest.get("task_id"), "status": status.get("id")},
        )
    if expected_task_id and manifest.get("task_id") != expected_task_id:
        add_failure(
            failures,
            "manifest_task_identity",
            "Manifest task_id must match task directory id.",
            {"manifest": manifest.get("task_id"), "task_dir": task_dir.name},
        )
    if manifest.get("task_type") != "run_analysis":
        add_failure(
            failures,
            "manifest_task_type",
            "Manifest task_type must be run_analysis.",
            {"actual": manifest.get("task_type")},
        )


def validate_path_containment(
    ops_dir: Path,
    task_dir: Path,
    manifest: dict[str, Any],
    failures: list[dict[str, Any]],
) -> None:
    checks: list[tuple[str, Any]] = [
        ("analysis_config_path", manifest.get("analysis_config_path")),
        ("runner.parameters_ref", (manifest.get("runner") or {}).get("parameters_ref")),
    ]
    for index, item in enumerate(manifest.get("data_versions") or []):
        if isinstance(item, dict) and "artifact_path" in item:
            checks.append((f"data_versions[{index}].artifact_path", item.get("artifact_path")))
    for index, item in enumerate(manifest.get("baseline_refs") or []):
        if isinstance(item, dict):
            checks.append((f"baseline_refs[{index}].expected_output_path", item.get("expected_output_path")))
    for index, item in enumerate(manifest.get("planned_outputs") or []):
        if isinstance(item, dict):
            checks.append((f"planned_outputs[{index}].path", item.get("path")))
    for index, item in enumerate(manifest.get("output_paths") or []):
        checks.append((f"output_paths[{index}]", item))

    escaped: list[dict[str, str]] = []
    for field, raw_value in checks:
        candidate = workspace_path(ops_dir, raw_value)
        if candidate is None:
            continue
        if not is_relative_to(candidate, task_dir):
            escaped.append({"field": field, "path": normalize_text(raw_value), "resolved_path": str(resolved(candidate))})
    if escaped:
        add_failure(
            failures,
            "output_paths_inside_task_folder",
            "Analysis manifest paths must stay inside the current task folder except accepted plan input artifacts.",
            escaped,
        )


def validate_accepted_plan(
    ops_dir: Path,
    manifest: dict[str, Any],
    now: datetime,
    failures: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]], Optional[Path], dict[str, Any]]:
    plan_report: dict[str, Any] = {
        "task_id": manifest.get("accepted_plan_task_id"),
        "task_dir": None,
        "artifact_path": manifest.get("accepted_plan_path"),
        "indexed": False,
    }
    plan_task_id = normalize_text(manifest.get("accepted_plan_task_id"))
    if not plan_task_id:
        add_failure(failures, "accepted_plan_reference", "Manifest must reference accepted_plan_task_id.")
        return None, None, None, plan_report

    plan_task_dir, find_error = find_task_dir_by_id(ops_dir, plan_task_id)
    if plan_task_dir is None:
        add_failure(failures, "accepted_plan_task_exists", "Accepted experiment plan task must exist.", find_error)
        return None, None, None, plan_report
    plan_report["task_dir"] = str(plan_task_dir)

    try:
        plan_status = read_json_object(plan_task_dir / "status.json")
    except PreflightMalformed as exc:
        raise PreflightMalformed(f"accepted plan status is malformed: {exc}") from exc
    status_errors = schema_errors(plan_status, STATUS_SCHEMA)
    if status_errors:
        add_failure(failures, "accepted_plan_status_schema", "Accepted plan status.json failed schema validation.", status_errors)
    if plan_status.get("type") != "experiment_plan":
        add_failure(
            failures,
            "accepted_plan_task_type",
            "Accepted plan task must have type experiment_plan.",
            {"actual": plan_status.get("type")},
        )
    if plan_status.get("status") != "accepted":
        add_failure(
            failures,
            "accepted_plan_task_accepted",
            "Accepted plan task must already be accepted.",
            {"actual": plan_status.get("status")},
        )

    accepted_row = indexed_accepted_task(ops_dir, plan_task_id, now)
    plan_report["indexed"] = accepted_row is not None
    if accepted_row is None:
        add_failure(
            failures,
            "accepted_plan_indexed",
            "Accepted plan task must appear in accepted_outputs_index.md.",
            {"task_id": plan_task_id, "index": str(ops_dir / DEFAULT_INDEX_NAME)},
        )
    else:
        plan_report["index_row"] = accepted_row
        accepted_plan_revalidation_status = accepted_row.get("revalidation_status")
        if accepted_plan_revalidation_status in {"stale", "superseded"}:
            add_failure(
                failures,
                "accepted_plan_current",
                "Accepted plan memory is stale or superseded and must be revalidated before analysis starts.",
                accepted_row,
            )
        elif accepted_plan_revalidation_status in {"due", "scheduled"}:
            add_warning(
                warnings,
                "accepted_plan_current",
                "Accepted plan memory is due or scheduled for revalidation before analysis starts.",
                accepted_row,
            )

    accepted_plan_path = workspace_path(ops_dir, manifest.get("accepted_plan_path"))
    if accepted_plan_path is None:
        add_failure(failures, "accepted_plan_artifact_exists", "accepted_plan_path must point to the plan artifact.")
    elif not is_relative_to(accepted_plan_path, plan_task_dir):
        add_failure(
            failures,
            "accepted_plan_artifact_containment",
            "accepted_plan_path must stay inside the accepted plan task folder.",
            {"path": manifest.get("accepted_plan_path"), "task_dir": str(plan_task_dir)},
        )
    elif not accepted_plan_path.exists():
        add_failure(
            failures,
            "accepted_plan_artifact_exists",
            "Accepted experiment plan artifact is missing.",
            str(accepted_plan_path),
        )

    acceptance_path = workspace_path(ops_dir, manifest.get("accepted_plan_result_acceptance_path"))
    if acceptance_path is None:
        add_failure(
            failures,
            "accepted_plan_result_acceptance_exists",
            "accepted_plan_result_acceptance_path must point to result_acceptance.json.",
        )
    elif not is_relative_to(acceptance_path, plan_task_dir):
        add_failure(
            failures,
            "accepted_plan_result_acceptance_containment",
            "accepted_plan_result_acceptance_path must stay inside the accepted plan task folder.",
            {"path": manifest.get("accepted_plan_result_acceptance_path"), "task_dir": str(plan_task_dir)},
        )
    elif not acceptance_path.exists():
        add_failure(
            failures,
            "accepted_plan_result_acceptance_exists",
            "Accepted plan result_acceptance.json is missing.",
            str(acceptance_path),
        )
    elif acceptance_path.name != "result_acceptance.json" or acceptance_path.parent.name != "review_panel":
        add_failure(
            failures,
            "accepted_plan_result_acceptance_path",
            "accepted_plan_result_acceptance_path must point to review_panel/result_acceptance.json.",
            {"path": str(acceptance_path), "expected_tail": "review_panel/result_acceptance.json"},
        )
    else:
        acceptance_payload = read_json_object(acceptance_path)
        acceptance_errors = schema_errors(acceptance_payload, RESULT_ACCEPTANCE_SCHEMA)
        if acceptance_errors:
            add_failure(
                failures,
                "accepted_plan_result_acceptance_schema",
                "Accepted plan result_acceptance.json failed result acceptance schema validation.",
                acceptance_errors,
            )

    if accepted_plan_path is None or not accepted_plan_path.exists():
        return plan_status, None, accepted_plan_path, plan_report

    try:
        plan = load_plan(accepted_plan_path)
    except ValueError as exc:
        raise PreflightMalformed(f"accepted experiment plan artifact is malformed: {exc}") from exc

    plan_errors = experiment_schema_errors(plan, PLAN_SCHEMA)
    plan_failures, plan_warnings, refs, data_foundations = validate_hard_gates(plan, ops_dir, plan_status)
    plan_report.update(
        {
            "experiment_id": plan.get("experiment_id"),
            "plan_task_id": plan.get("task_id"),
            "data_audit_refs": refs,
            "data_foundations": data_foundations,
            "plan_warnings": plan_warnings,
        }
    )
    if plan_errors or plan_failures:
        add_failure(
            failures,
            "accepted_plan_valid",
            "Accepted plan artifact no longer passes experiment validate.",
            {"schema_errors": plan_errors, "hard_gate_failures": plan_failures},
        )
    for warning in plan_warnings:
        add_warning(warnings, "accepted_plan_valid", "Accepted plan validation warning.", warning)

    if manifest.get("experiment_plan_id") != plan.get("experiment_id"):
        add_failure(
            failures,
            "experiment_plan_id_matches",
            "Manifest experiment_plan_id must match the accepted plan experiment_id.",
            {"manifest": manifest.get("experiment_plan_id"), "plan": plan.get("experiment_id")},
        )
    if manifest.get("accepted_plan_task_id") != plan.get("task_id"):
        add_failure(
            failures,
            "accepted_plan_task_id_matches",
            "Manifest accepted_plan_task_id must match the accepted plan task_id.",
            {"manifest": manifest.get("accepted_plan_task_id"), "plan": plan.get("task_id")},
        )
    return plan_status, plan, accepted_plan_path, plan_report


def validate_source_and_data_refs(
    ops_dir: Path,
    manifest: dict[str, Any],
    plan: Optional[dict[str, Any]],
    now: datetime,
    failures: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest_refs = sorted(
        {
            normalize_text(item.get("source_id"))
            for item in manifest.get("data_versions") or []
            if isinstance(item, dict) and normalize_text(item.get("source_id"))
        }
    )
    if plan is not None:
        plan_refs = sorted(str(item) for item in plan.get("data_audit_refs", []) if isinstance(item, str))
        if manifest_refs != plan_refs:
            add_failure(
                failures,
                "data_refs_match_plan",
                "Manifest data_versions source IDs must match accepted plan data_audit_refs.",
                {"manifest": manifest_refs, "plan": plan_refs},
            )

    source_report = assess_source_refs(
        ops_dir,
        manifest_refs,
        use_case="experiment_planning",
        claim_impact="medium",
        now=now,
    )
    if not source_report.get("ok"):
        add_failure(failures, "source_governance_allowed", "Manifest source refs are not currently allowed.", source_report)
    for warning in source_report.get("warnings", []):
        add_warning(warnings, "source_governance_allowed", "Source governance warning.", warning)

    foundation_report = data_foundation_report(ops_dir, now=now)
    if foundation_report.get("error_count", 0):
        add_failure(
            failures,
            "data_foundations",
            "Data foundation files are malformed or inconsistent.",
            {
                "error_count": foundation_report.get("error_count", 0),
                "errors": foundation_report.get("errors", []),
            },
        )
    if foundation_report.get("warning_count", 0):
        add_warning(
            warnings,
            "data_foundations",
            "Data foundation warnings are present.",
            {
                "warning_count": foundation_report.get("warning_count", 0),
                "warnings": foundation_report.get("warnings", []),
                "active_idea_gap_refs": foundation_report.get("active_idea_gap_refs", []),
            },
        )
    return source_report, foundation_report


def validate_method_metric_baselines_budget(
    manifest: dict[str, Any],
    plan: Optional[dict[str, Any]],
    status: Optional[dict[str, Any]],
    failures: list[dict[str, Any]],
) -> None:
    if plan is None:
        return

    candidate_methods = plan.get("candidate_methods")
    candidate_ref = (manifest.get("candidate_method") or {}).get("planned_method_ref")
    candidate_index = plan_ref_index(candidate_ref, "experiment_plan.candidate_methods")
    candidate = None
    if not isinstance(candidate_methods, list) or not candidate_methods:
        add_failure(failures, "method_family_allowed", "Accepted plan must include candidate_methods.")
    elif candidate_index is None or candidate_index >= len(candidate_methods):
        add_failure(
            failures,
            "method_family_allowed",
            "Manifest candidate_method.planned_method_ref must point to an accepted plan candidate method.",
            {"planned_method_ref": candidate_ref, "available_count": len(candidate_methods)},
        )
    else:
        candidate = candidate_methods[candidate_index]
        if isinstance(candidate, dict) and not compatible_method_family(
            normalize_text(manifest.get("method_family")),
            candidate.get("method_class"),
        ):
            add_failure(
                failures,
                "method_family_allowed",
                "Manifest method_family is not compatible with the referenced accepted plan method.",
                {"method_family": manifest.get("method_family"), "method_class": candidate.get("method_class")},
            )

    plan_metric = normalize_text((plan.get("metrics") or {}).get("primary_metric"))
    manifest_metric = normalize_text((manifest.get("primary_metric") or {}).get("name"))
    if plan_metric and manifest_metric != plan_metric:
        add_failure(
            failures,
            "primary_metric_matches",
            "Manifest primary metric must match the accepted plan primary metric.",
            {"manifest": manifest_metric, "plan": plan_metric},
        )

    baselines = plan.get("baselines") if isinstance(plan.get("baselines"), list) else []
    planned_paths = {
        normalize_text(item.get("path"))
        for item in manifest.get("planned_outputs") or []
        if isinstance(item, dict) and normalize_text(item.get("path"))
    }
    output_paths = {normalize_text(item) for item in manifest.get("output_paths") or [] if normalize_text(item)}
    available_outputs = planned_paths | output_paths
    represented_baseline_indices: set[int] = set()
    for index, baseline in enumerate(manifest.get("baseline_refs") or []):
        if not isinstance(baseline, dict):
            continue
        baseline_ref = baseline.get("planned_baseline_ref")
        baseline_index = plan_ref_index(baseline_ref, "experiment_plan.baselines")
        if baseline_index is None or baseline_index >= len(baselines):
            add_failure(
                failures,
                "baseline_outputs_required",
                "Manifest baseline_refs must point to accepted plan baselines.",
                {"planned_baseline_ref": baseline_ref, "available_count": len(baselines)},
            )
        else:
            represented_baseline_indices.add(baseline_index)
        expected_output = normalize_text(baseline.get("expected_output_path"))
        if expected_output and expected_output not in available_outputs:
            add_failure(
                failures,
                "baseline_outputs_required",
                "Baseline expected output must be included in planned_outputs or output_paths.",
                {"baseline_index": index, "expected_output_path": expected_output},
            )
    missing_baselines = [
        {"baseline_index": index, "name": baseline.get("name") if isinstance(baseline, dict) else ""}
        for index, baseline in enumerate(baselines)
        if index not in represented_baseline_indices
    ]
    if missing_baselines:
        add_failure(
            failures,
            "baseline_outputs_required",
            "Every accepted plan baseline must have a manifest baseline ref and planned output.",
            missing_baselines,
        )

    plan_budget = plan.get("budget") if isinstance(plan.get("budget"), dict) else {}
    if status is not None:
        status_minutes = status.get("max_minutes")
        plan_minutes = plan_budget.get("max_runtime_minutes")
        if isinstance(status_minutes, (int, float)) and isinstance(plan_minutes, (int, float)) and status_minutes > plan_minutes:
            add_failure(
                failures,
                "budget_within_plan",
                "Analysis task max_minutes exceeds accepted plan budget.",
                {"analysis_task": status_minutes, "accepted_plan": plan_minutes},
            )
        status_budget = status.get("budget") if isinstance(status.get("budget"), dict) else {}
        for status_key, plan_key in (("max_api_usd", "max_api_usd"), ("max_compute_usd", "max_compute_usd")):
            status_value = status_budget.get(status_key)
            plan_value = plan_budget.get(plan_key)
            if isinstance(status_value, (int, float)) and isinstance(plan_value, (int, float)) and status_value > plan_value:
                add_failure(
                    failures,
                    "budget_within_plan",
                    f"Analysis task {status_key} exceeds accepted plan budget.",
                    {"analysis_task": status_value, "accepted_plan": plan_value},
                )

    runtime = manifest.get("runtime_minutes")
    plan_minutes = plan_budget.get("max_runtime_minutes")
    if isinstance(runtime, (int, float)) and isinstance(plan_minutes, (int, float)) and runtime > plan_minutes:
        add_failure(
            failures,
            "budget_within_plan",
            "Manifest runtime_minutes exceeds accepted plan budget.",
            {"manifest": runtime, "accepted_plan": plan_minutes},
        )
    cost = manifest.get("cost") if isinstance(manifest.get("cost"), dict) else {}
    for manifest_key, plan_key in (("api_usd", "max_api_usd"), ("compute_usd", "max_compute_usd")):
        manifest_value = cost.get(manifest_key)
        plan_value = plan_budget.get(plan_key)
        if isinstance(manifest_value, (int, float)) and isinstance(plan_value, (int, float)) and manifest_value > plan_value:
            add_failure(
                failures,
                "budget_within_plan",
                f"Manifest {manifest_key} exceeds accepted plan budget.",
                {"manifest": manifest_value, "accepted_plan": plan_value},
            )


def text_for_accepted_memory_scan(ops_dir: Path, task_dir: Path, manifest: dict[str, Any]) -> str:
    parts = [json.dumps(manifest, sort_keys=True)]
    task_md = task_dir / "task.md"
    if task_md.exists():
        try:
            parts.append(task_md.read_text(encoding="utf-8"))
        except OSError:
            pass
    config_path = workspace_path(ops_dir, manifest.get("analysis_config_path"))
    if config_path is not None and config_path.exists() and is_relative_to(config_path, task_dir):
        try:
            parts.append(config_path.read_text(encoding="utf-8"))
        except OSError:
            pass
    parameters_path = workspace_path(ops_dir, (manifest.get("runner") or {}).get("parameters_ref"))
    if parameters_path is not None and parameters_path.exists() and is_relative_to(parameters_path, task_dir):
        try:
            parts.append(parameters_path.read_text(encoding="utf-8"))
        except OSError:
            pass
    return "\n".join(parts)


def validate_accepted_memory(
    ops_dir: Path,
    task_dir: Path,
    manifest: dict[str, Any],
    now: datetime,
    failures: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    rows = read_index_rows(ops_dir / DEFAULT_INDEX_NAME, now=now)
    stale_by_task = {row["task_id"]: row for row in rows if row.get("revalidation_status") == "stale"}
    due_by_task = {row["task_id"]: row for row in rows if row.get("revalidation_status") == "due"}
    accepted_plan_task_id = normalize_text(manifest.get("accepted_plan_task_id"))
    task_refs = sorted(set(TASK_REF_RE.findall(text_for_accepted_memory_scan(ops_dir, task_dir, manifest))))
    scanned_refs = [task_id for task_id in task_refs if task_id != accepted_plan_task_id and task_id != normalize_text(manifest.get("task_id"))]
    stale_refs = [stale_by_task[task_id] for task_id in scanned_refs if task_id in stale_by_task]
    due_refs = [due_by_task[task_id] for task_id in scanned_refs if task_id in due_by_task]
    if stale_refs:
        add_failure(
            failures,
            "stale_accepted_memory_reuse",
            "Analysis task cites stale accepted memory as current evidence.",
            stale_refs,
        )
    if due_refs:
        add_warning(
            warnings,
            "due_accepted_memory_reuse",
            "Analysis task cites accepted memory due for revalidation.",
            due_refs,
        )
    return {
        "index": str(ops_dir / DEFAULT_INDEX_NAME),
        "task_refs": task_refs,
        "stale_refs": stale_refs,
        "due_refs": due_refs,
    }


def preflight(args: argparse.Namespace) -> int:
    try:
        now = parse_now(args.now)
    except ValueError as exc:
        print_json({"ok": False, "reason": "invalid_now", "error": str(exc), "now": args.now})
        return INVALID_REQUEST

    task_dir = args.task_dir
    ops_dir = args.ops_dir
    failures: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    manifest_path = task_dir / MANIFEST_RELATIVE_PATH
    report: dict[str, Any] = {
        "ok": False,
        "action": "analysis_preflight",
        "task_dir": str(task_dir),
        "ops_dir": str(ops_dir),
        "manifest_path": str(manifest_path),
        "run_id": None,
        "experiment_plan_id": None,
        "accepted_plan_task_id": None,
        "hard_gate_failures": failures,
        "warnings": warnings,
    }

    try:
        status = load_status(task_dir, failures)
        manifest = load_manifest(task_dir, failures)
        if manifest is not None:
            report.update(
                {
                    "run_id": manifest.get("run_id"),
                    "experiment_plan_id": manifest.get("experiment_plan_id"),
                    "accepted_plan_task_id": manifest.get("accepted_plan_task_id"),
                }
            )
            validate_manifest_identity(task_dir, status, manifest, failures)
            validate_path_containment(ops_dir, task_dir, manifest, failures)
            plan_status, plan, plan_path, accepted_plan_report = validate_accepted_plan(ops_dir, manifest, now, failures, warnings)
            report["accepted_plan"] = accepted_plan_report
            report["accepted_plan_path"] = path_text(plan_path)
            source_report, foundation_report = validate_source_and_data_refs(ops_dir, manifest, plan, now, failures, warnings)
            report["source_governance"] = source_report
            report["data_foundations"] = foundation_report
            validate_method_metric_baselines_budget(manifest, plan, status, failures)
            report["accepted_memory"] = validate_accepted_memory(ops_dir, task_dir, manifest, now, failures, warnings)
            if plan_status is not None:
                report["accepted_plan_status"] = {
                    "id": plan_status.get("id"),
                    "type": plan_status.get("type"),
                    "status": plan_status.get("status"),
                }
    except PreflightMalformed as exc:
        report.update(
            {
                "ok": False,
                "reason": "malformed_task_state",
                "error": str(exc),
                "failure_count": len(failures),
                "warning_count": len(warnings),
                "next_step": "repair malformed task artifacts before analysis starts",
            }
        )
        print_json(report)
        return MALFORMED

    ok = not failures
    if failures:
        next_step = "repair blockers before analysis starts"
    elif warnings:
        next_step = "review warnings before analysis starts"
    else:
        next_step = "run analysis"
    report.update(
        {
            "ok": ok,
            "failure_count": len(failures),
            "warning_count": len(warnings),
            "next_step": next_step,
        }
    )
    print_json(report)
    return SUCCESS if ok and not warnings else VALIDATION_FAILED


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preflight analysis-run tasks against accepted experiment plans.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    preflight_parser = subparsers.add_parser(
        "preflight",
        help="Read-only safety check before a run_analysis task starts.",
        description=(
            "Read-only safety check for one run_analysis task: validates status.json, "
            "run_manifest.json, accepted experiment plan linkage, source/data readiness, "
            "method and metric alignment, budgets, output paths, and stale accepted memory."
        ),
    )
    preflight_parser.add_argument("task_dir", type=Path, help="run_analysis task directory to preflight.")
    preflight_parser.add_argument("--ops-dir", type=Path, required=True, help="research_ops directory.")
    preflight_parser.add_argument("--now", help="Override current time for deterministic source/data and memory checks.")
    return parser.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    if args.command == "preflight":
        return preflight(args)
    print_json({"ok": False, "reason": "unknown_command", "command": args.command})
    return INVALID_REQUEST


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
