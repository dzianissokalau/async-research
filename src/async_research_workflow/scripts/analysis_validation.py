#!/usr/bin/env python3
"""Validate completed analysis-run artifacts before result acceptance."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable, Optional

from async_research_workflow.resources import schema_path
from async_research_workflow.scripts import analysis_claim_gates
from async_research_workflow.scripts.analysis_runs import (
    MANIFEST_RELATIVE_PATH,
    MANIFEST_SCHEMA,
    STATUS_SCHEMA,
    PreflightMalformed,
    add_failure,
    add_warning,
    parse_now,
    path_text,
    read_json_object,
    schema_errors,
    task_id_from_dir,
    validate_accepted_memory,
    validate_accepted_plan,
    validate_manifest_identity,
    validate_method_metric_baselines_budget,
    validate_path_containment,
    validate_source_and_data_refs,
    workspace_path,
)
from async_research_workflow.scripts.validate_result_acceptance import load_result_summary


SUCCESS = 0
VALIDATION_FAILED = 2
INVALID_REQUEST = 3
MALFORMED = 4

ANALYSIS_RUN_DIR = Path("artifacts/analysis_run")
STRUCTURED_OUTPUTS = {
    "metrics": ("metrics.json", schema_path("analysis_metrics.schema.json")),
    "diagnostics": ("diagnostics.json", schema_path("analysis_diagnostics.schema.json")),
    "robustness": ("robustness_checks.json", schema_path("analysis_robustness_checks.schema.json")),
}
CLAIM_GATES_SCHEMA = schema_path("analysis_claim_gates.schema.json")
COMPLETED_MANIFEST_FIELDS = ["completed_at", "runtime_minutes", "cost"]
IDENTITY_FIELDS = ["run_id", "experiment_plan_id", "task_id"]
OUT_OF_SAMPLE_SPLIT_ROLES = {"validation", "test", "holdout", "backtest"}
PLANNED_METRIC_ROLES = {"baseline", "candidate", "validation"}


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


def normalize_compare_text(value: Any) -> str:
    return re.sub(r"\s+", " ", normalize_text(value).lower())


def text_tokens(value: Any) -> set[str]:
    return {token for token in re.split(r"[^a-z0-9]+", normalize_text(value).lower()) if token}


def value_text(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return normalize_text(value)


def contains_text(haystack: Any, needle: Any) -> bool:
    needle_text = normalize_compare_text(needle)
    return bool(needle_text) and needle_text in normalize_compare_text(haystack)


def planned_metric_refs(plan: Optional[dict[str, Any]]) -> set[str]:
    if not isinstance(plan, dict):
        return set()
    metrics = plan.get("metrics") if isinstance(plan.get("metrics"), dict) else {}
    refs = {"experiment_plan.metrics.primary_metric"} if normalize_text(metrics.get("primary_metric")) else set()
    secondary_metrics = metrics.get("secondary_metrics") if isinstance(metrics.get("secondary_metrics"), list) else []
    refs.update(f"experiment_plan.metrics.secondary_metrics[{index}]" for index, _metric in enumerate(secondary_metrics))
    return refs


def planned_metric_texts(manifest: dict[str, Any], plan: Optional[dict[str, Any]]) -> list[str]:
    texts: list[str] = []
    manifest_metric = normalize_text((manifest.get("primary_metric") or {}).get("name"))
    if manifest_metric:
        texts.append(manifest_metric)
    if isinstance(plan, dict):
        metrics = plan.get("metrics") if isinstance(plan.get("metrics"), dict) else {}
        primary = normalize_text(metrics.get("primary_metric"))
        if primary:
            texts.append(primary)
        secondary = metrics.get("secondary_metrics") if isinstance(metrics.get("secondary_metrics"), list) else []
        texts.extend(normalize_text(item) for item in secondary if normalize_text(item))
    return texts


def metric_name_is_planned(metric_name: Any, planned_texts: list[str]) -> bool:
    name_tokens = text_tokens(metric_name)
    if not name_tokens:
        return False
    for planned_text in planned_texts:
        planned_tokens = text_tokens(planned_text)
        if name_tokens <= planned_tokens:
            return True
    return False


def planned_robustness_refs(plan: Optional[dict[str, Any]]) -> set[str]:
    if not isinstance(plan, dict) or not isinstance(plan.get("robustness_checks"), list):
        return set()
    return {f"experiment_plan.robustness_checks[{index}]" for index, _item in enumerate(plan["robustness_checks"])}


def canonical_path(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def workspace_relative_text(ops_dir: Path, path: Path) -> str:
    try:
        return str(canonical_path(path).relative_to(canonical_path(ops_dir.parent)))
    except ValueError:
        return str(path)


def mark_malformed(report: dict[str, Any], exc: PreflightMalformed) -> None:
    report.update(
        {
            "reason": "malformed_task_state",
            "error": str(exc),
            "next_step": "repair malformed task artifacts before analysis validation",
        }
    )


def load_status_for_validation(task_dir: Path, failures: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    status_path = task_dir / "status.json"
    if not status_path.exists():
        add_failure(failures, "task_status_exists", "Task status.json is required.", str(status_path))
        return None
    status = read_json_object(status_path)
    status_errors = schema_errors(status, STATUS_SCHEMA)
    if status_errors:
        add_failure(failures, "task_status_schema", "status.json failed task status schema validation.", status_errors)
    if status.get("type") != "run_analysis":
        add_failure(
            failures,
            "task_type",
            "Analysis validation only supports run_analysis tasks.",
            {"expected": "run_analysis", "actual": status.get("type")},
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


def load_manifest_for_validation(task_dir: Path, failures: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    manifest_path = task_dir / MANIFEST_RELATIVE_PATH
    if not manifest_path.exists():
        add_failure(
            failures,
            "manifest_exists",
            "Analysis run manifest is required before validation.",
            str(manifest_path),
        )
        return None
    manifest = read_json_object(manifest_path)
    manifest_errors = schema_errors(manifest, MANIFEST_SCHEMA)
    if manifest_errors:
        add_failure(failures, "manifest_schema", "run_manifest.json failed analysis-run schema validation.", manifest_errors)
    return manifest


def validate_completed_manifest(manifest: dict[str, Any], failures: list[dict[str, Any]]) -> None:
    if manifest.get("run_status") != "completed":
        add_failure(
            failures,
            "run_completed",
            "Analysis validation requires a completed run manifest.",
            {"expected": "completed", "actual": manifest.get("run_status")},
        )
    missing = [field for field in COMPLETED_MANIFEST_FIELDS if field not in manifest]
    if missing:
        add_failure(
            failures,
            "run_completion_fields",
            "Completed analysis runs must record completion time, runtime, and cost.",
            {"missing": missing},
        )


def artifact_identity_errors(name: str, payload: dict[str, Any], manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in IDENTITY_FIELDS:
        if payload.get(field) != manifest.get(field):
            errors.append(f"{name}.{field}={payload.get(field)!r} does not match manifest {manifest.get(field)!r}")
    return errors


def load_structured_outputs(
    task_dir: Path,
    manifest: dict[str, Any],
    failures: list[dict[str, Any]],
) -> dict[str, Optional[dict[str, Any]]]:
    outputs: dict[str, Optional[dict[str, Any]]] = {}
    for name, (filename, output_schema) in STRUCTURED_OUTPUTS.items():
        path = task_dir / ANALYSIS_RUN_DIR / filename
        if not path.exists():
            add_failure(failures, f"{name}_exists", f"Analysis {name} artifact is required.", str(path))
            outputs[name] = None
            continue
        payload = read_json_object(path)
        errors = schema_errors(payload, output_schema)
        if errors:
            add_failure(failures, f"{name}_schema", f"{filename} failed schema validation.", errors)
        identity_errors = artifact_identity_errors(name, payload, manifest)
        if identity_errors:
            add_failure(
                failures,
                f"{name}_identity",
                f"{filename} must share run_id, experiment_plan_id, and task_id with run_manifest.json.",
                identity_errors,
            )
        outputs[name] = payload
    return outputs


def validate_required_output_files(
    ops_dir: Path,
    manifest: dict[str, Any],
    failures: list[dict[str, Any]],
) -> None:
    missing: list[dict[str, Any]] = []
    for index, item in enumerate(manifest.get("planned_outputs") or []):
        if not isinstance(item, dict) or item.get("required_for_acceptance") is not True:
            continue
        path = workspace_path(ops_dir, item.get("path"))
        if path is None or not path.exists():
            missing.append({"field": f"planned_outputs[{index}].path", "path": item.get("path")})
    for index, item in enumerate(manifest.get("baseline_refs") or []):
        if not isinstance(item, dict):
            continue
        path = workspace_path(ops_dir, item.get("expected_output_path"))
        if path is None or not path.exists():
            missing.append({"field": f"baseline_refs[{index}].expected_output_path", "path": item.get("expected_output_path")})
    if missing:
        add_failure(
            failures,
            "required_output_files_exist",
            "Required analysis outputs and baseline outputs must exist before validation passes.",
            missing,
        )


def validate_metrics_against_plan(
    metrics: Optional[dict[str, Any]],
    manifest: dict[str, Any],
    plan: Optional[dict[str, Any]],
    failures: list[dict[str, Any]],
) -> None:
    if metrics is None:
        return
    manifest_metric = normalize_text((manifest.get("primary_metric") or {}).get("name"))
    metrics_metric = normalize_text(metrics.get("primary_metric_name"))
    plan_metric = normalize_text(((plan or {}).get("metrics") or {}).get("primary_metric"))
    expected_metric = plan_metric or manifest_metric
    if expected_metric and metrics_metric != expected_metric:
        add_failure(
            failures,
            "primary_metric_matches_plan",
            "Analysis metrics primary_metric_name must match the accepted plan primary metric.",
            {"metrics": metrics_metric, "manifest": manifest_metric, "plan": plan_metric},
        )

    if plan is not None:
        baselines = plan.get("baselines") if isinstance(plan.get("baselines"), list) else []
        represented = {
            normalize_text(item.get("planned_baseline_ref"))
            for item in metrics.get("baseline_comparisons", [])
            if isinstance(item, dict)
        }
        missing_baselines = [
            {"baseline_index": index, "expected_ref": f"experiment_plan.baselines[{index}]"}
            for index, _baseline in enumerate(baselines)
            if f"experiment_plan.baselines[{index}]" not in represented
        ]
        if missing_baselines:
            add_failure(
                failures,
                "baseline_comparisons_match_plan",
                "Every accepted plan baseline must be represented in metrics.baseline_comparisons.",
                missing_baselines,
            )

    allowed_refs = planned_metric_refs(plan)
    allowed_texts = planned_metric_texts(manifest, plan)
    unplanned_metrics: list[dict[str, Any]] = []
    metric_collections = (
        ("baseline_metrics", metrics.get("baseline_metrics", [])),
        ("candidate_metrics", metrics.get("candidate_metrics", [])),
        ("validation_metrics", metrics.get("validation_metrics", [])),
        ("metric_rows", metrics.get("metric_rows", [])),
        ("baseline_comparisons", metrics.get("baseline_comparisons", [])),
    )
    for collection_name, rows in metric_collections:
        if not isinstance(rows, list):
            continue
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            role = normalize_text(row.get("role")).lower()
            planned_ref = normalize_text(row.get("planned_metric_ref"))
            metric_name = normalize_text(row.get("metric_name"))
            needs_planned_metric = collection_name != "metric_rows" or role in PLANNED_METRIC_ROLES
            if planned_ref and allowed_refs and planned_ref not in allowed_refs:
                unplanned_metrics.append(
                    {
                        "field": f"{collection_name}[{index}].planned_metric_ref",
                        "value": planned_ref,
                        "allowed": sorted(allowed_refs),
                    }
                )
            if needs_planned_metric and allowed_refs and not planned_ref and collection_name != "baseline_comparisons":
                unplanned_metrics.append(
                    {
                        "field": f"{collection_name}[{index}].planned_metric_ref",
                        "value": "",
                        "allowed": sorted(allowed_refs),
                    }
                )
            if needs_planned_metric and allowed_texts and not metric_name_is_planned(metric_name, allowed_texts):
                unplanned_metrics.append(
                    {
                        "field": f"{collection_name}[{index}].metric_name",
                        "value": metric_name,
                        "allowed_metric_texts": allowed_texts,
                    }
                )
    if unplanned_metrics:
        add_failure(
            failures,
            "planned_metrics_match_plan",
            "Metric rows must reference metrics that were planned by the accepted experiment plan.",
            unplanned_metrics,
        )

    validation_splits = [
        item
        for item in metrics.get("validation_splits", [])
        if isinstance(item, dict) and normalize_text(item.get("split_role")).lower() in OUT_OF_SAMPLE_SPLIT_ROLES
    ]
    if not validation_splits:
        add_failure(
            failures,
            "out_of_sample_validation_present",
            "Analysis metrics must include validation, test, holdout, or backtest split metadata.",
        )

    metric_deviations = [
        item
        for item in manifest.get("deviations_from_plan", [])
        if isinstance(item, dict) and "metric" in normalize_text(item.get("field")).lower()
    ]
    if metric_deviations:
        add_failure(
            failures,
            "unplanned_metric_changes",
            "Metric deviations from the accepted plan require human decision before result acceptance.",
            metric_deviations,
        )


def validate_robustness_semantics(
    robustness: Optional[dict[str, Any]],
    plan: Optional[dict[str, Any]],
    failures: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> None:
    if robustness is None:
        return
    planned_refs = planned_robustness_refs(plan)
    invalid_refs = [
        {
            "field": f"planned_checks[{index}].planned_check_ref",
            "value": normalize_text(item.get("planned_check_ref")),
            "allowed": sorted(planned_refs),
        }
        for index, item in enumerate(robustness.get("planned_checks", []))
        if isinstance(item, dict)
        and planned_refs
        and normalize_text(item.get("planned_check_ref")) not in planned_refs
    ]
    if invalid_refs:
        add_failure(
            failures,
            "robustness_checks_match_plan",
            "Robustness planned_check_ref values must come from the accepted experiment plan.",
            invalid_refs,
        )

    invalid_support = [
        {
            "name": item.get("name"),
            "status": item.get("status"),
            "decision_impact": item.get("decision_impact"),
        }
        for item in robustness.get("planned_checks", [])
        if isinstance(item, dict)
        and normalize_text(item.get("decision_impact")).lower() == "supports_claim"
        and normalize_text(item.get("status")).lower() in {"not_run", "fail", "not_applicable"}
    ]
    if invalid_support:
        add_failure(
            failures,
            "robustness_semantics",
            "Robustness checks that did not pass cannot support a claim.",
            invalid_support,
        )

    caps = [
        {"name": item.get("name"), "status": item.get("status"), "result": item.get("result")}
        for item in robustness.get("planned_checks", [])
        if isinstance(item, dict) and normalize_text(item.get("decision_impact")).lower() == "caps_claim"
    ]
    if caps:
        add_warning(
            warnings,
            "robustness_caps_claim",
            "Robustness checks marked caps_claim must be reflected in claim-gate caps before result acceptance.",
            caps,
        )


def validate_summary_identity(summary: dict[str, Any], manifest: dict[str, Any], failures: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> None:
    missing = [field for field in IDENTITY_FIELDS if not normalize_text(summary.get(field))]
    if missing:
        add_warning(
            warnings,
            "result_summary_identity_present",
            "Result summary should record run_id, experiment_plan_id, and task_id; validator used manifest context.",
            {"missing": missing},
        )
    mismatches = [
        f"{field}: summary={summary.get(field)!r}, manifest={manifest.get(field)!r}"
        for field in IDENTITY_FIELDS
        if normalize_text(summary.get(field)) and summary.get(field) != manifest.get(field)
    ]
    if mismatches:
        add_failure(
            failures,
            "result_summary_identity_matches",
            "Result summary identity must match run_manifest.json.",
            mismatches,
        )


def metric_result_is_summarized(summary_text: Any, rows: Any) -> bool:
    if not isinstance(rows, list):
        return False
    for row in rows:
        if not isinstance(row, dict):
            continue
        if contains_text(summary_text, row.get("metric_name")) and contains_text(summary_text, value_text(row.get("value"))):
            return True
    return False


def validation_split_is_summarized(summary_text: Any, metrics: dict[str, Any]) -> bool:
    splits = metrics.get("validation_splits") if isinstance(metrics.get("validation_splits"), list) else []
    for split in splits:
        if not isinstance(split, dict):
            continue
        candidates = [split.get("split_name"), split.get("time_window"), split.get("split_role")]
        if any(contains_text(summary_text, candidate) for candidate in candidates):
            return True
    return False


def validate_summary_substance(
    ops_dir: Path,
    task_dir: Path,
    summary: dict[str, Any],
    manifest: dict[str, Any],
    metrics: Optional[dict[str, Any]],
    failures: list[dict[str, Any]],
) -> None:
    mismatches: list[dict[str, Any]] = []
    expected_manifest_path = canonical_path(task_dir / MANIFEST_RELATIVE_PATH)
    summary_manifest_path = workspace_path(ops_dir, summary.get("run_manifest_path"))
    if summary_manifest_path is None or canonical_path(summary_manifest_path) != expected_manifest_path:
        mismatches.append(
            {
                "field": "run_manifest_path",
                "summary": summary.get("run_manifest_path"),
                "expected": workspace_relative_text(ops_dir, expected_manifest_path),
            }
        )

    expected_metric = normalize_text((metrics or {}).get("primary_metric_name")) or normalize_text(
        (manifest.get("primary_metric") or {}).get("name")
    )
    if expected_metric and normalize_compare_text(summary.get("primary_metric")) != normalize_compare_text(expected_metric):
        mismatches.append(
            {
                "field": "primary_metric",
                "summary": summary.get("primary_metric"),
                "expected": expected_metric,
            }
        )

    if isinstance(metrics, dict):
        if not metric_result_is_summarized(summary.get("baseline_results"), metrics.get("baseline_metrics")):
            mismatches.append(
                {
                    "field": "baseline_results",
                    "summary": summary.get("baseline_results"),
                    "expected": "a baseline metric name and value from metrics.baseline_metrics",
                }
            )
        if not metric_result_is_summarized(summary.get("candidate_results"), metrics.get("candidate_metrics")):
            mismatches.append(
                {
                    "field": "candidate_results",
                    "summary": summary.get("candidate_results"),
                    "expected": "a candidate metric name and value from metrics.candidate_metrics",
                }
            )
        if not validation_split_is_summarized(summary.get("validation_split_results"), metrics):
            mismatches.append(
                {
                    "field": "validation_split_results",
                    "summary": summary.get("validation_split_results"),
                    "expected": "a validation split name, role, or time window from metrics.validation_splits",
                }
            )

    if mismatches:
        add_failure(
            failures,
            "result_summary_matches_outputs",
            "Result summary fields must match the current manifest and structured metrics outputs.",
            mismatches,
        )


def load_claim_gate_artifact(
    task_dir: Path,
    failures: list[dict[str, Any]],
) -> Optional[dict[str, Any]]:
    path = task_dir / ANALYSIS_RUN_DIR / "claim_gates.json"
    if not path.exists():
        add_failure(failures, "claim_gates_exists", "analysis claim_gates.json artifact is required.", str(path))
        return None
    payload = read_json_object(path)
    errors = schema_errors(payload, CLAIM_GATES_SCHEMA)
    if errors:
        add_failure(failures, "claim_gates_schema", "claim_gates.json failed schema validation.", errors)
    return payload


def has_caps_claim(robustness: Optional[dict[str, Any]]) -> bool:
    if not isinstance(robustness, dict):
        return False
    return any(
        isinstance(item, dict) and normalize_text(item.get("decision_impact")).lower() == "caps_claim"
        for item in robustness.get("planned_checks", [])
    )


def computed_caps_robustness(computed: dict[str, Any]) -> bool:
    return any(
        isinstance(item, dict)
        and item.get("gate") == "robustness_decision_impact"
        and item.get("status") == "cap"
        for item in computed.get("claim_gate_results", [])
    )


def validate_claim_gates(
    task_dir: Path,
    manifest: dict[str, Any],
    summary: dict[str, Any],
    outputs: dict[str, Optional[dict[str, Any]]],
    failures: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    existing = load_claim_gate_artifact(task_dir, failures)
    computed = analysis_claim_gates.evaluate_claim_gates(
        summary,
        metrics=outputs.get("metrics"),
        diagnostics=outputs.get("diagnostics"),
        robustness=outputs.get("robustness"),
        trusted_identity={
            "run_id": normalize_text(manifest.get("run_id")),
            "experiment_plan_id": normalize_text(manifest.get("experiment_plan_id")),
            "task_id": normalize_text(manifest.get("task_id")),
        },
    )
    computed_errors = analysis_claim_gates.schema_errors(computed, "analysis_claim_gates.schema.json")
    if computed_errors:
        add_failure(failures, "claim_gates_computed_schema", "Computed claim gates failed their schema.", computed_errors)

    if existing is not None:
        comparisons = [
            "run_id",
            "experiment_plan_id",
            "task_id",
            "claim",
            "claim_type",
            "requested_claim_strength",
            "max_claim_strength",
            "claim_decision",
            "recommended_route",
            "cap_reasons",
            "human_gate",
            "claim_gate_results",
            "review_notes",
        ]
        mismatches = [
            {"field": field, "claim_gates_json": existing.get(field), "computed": computed.get(field)}
            for field in comparisons
            if existing.get(field) != computed.get(field)
        ]
        if mismatches:
            add_failure(
                failures,
                "claim_gates_match_outputs",
                "claim_gates.json must match the current result summary and structured artifacts.",
                mismatches,
            )

    if has_caps_claim(outputs.get("robustness")) and not computed_caps_robustness(computed):
        add_failure(
            failures,
            "robustness_caps_claim_reflected",
            "Robustness checks marked caps_claim must produce a robustness_decision_impact cap in claim gates.",
        )

    decision = computed.get("claim_decision")
    if decision in {"rejected", "needs_human"}:
        add_failure(
            failures,
            "claim_gate_decision",
            "Claim gates block result acceptance until the claim is revised or reviewed.",
            {"claim_decision": decision, "recommended_route": computed.get("recommended_route"), "cap_reasons": computed.get("cap_reasons")},
        )
    elif decision == "capped":
        add_warning(
            warnings,
            "claim_gate_decision",
            "Claim gates cap the requested claim strength.",
            {"max_claim_strength": computed.get("max_claim_strength"), "cap_reasons": computed.get("cap_reasons")},
        )
    return {"computed": computed, "artifact": existing}


def build_base_report(action: str, task_dir: Path, ops_dir: Path) -> dict[str, Any]:
    return {
        "ok": False,
        "action": action,
        "task_dir": str(task_dir),
        "ops_dir": str(ops_dir),
        "manifest_path": str(task_dir / MANIFEST_RELATIVE_PATH),
        "run_id": None,
        "experiment_plan_id": None,
        "accepted_plan_task_id": None,
        "hard_gate_failures": [],
        "warnings": [],
    }


def validate_common(
    task_dir: Path,
    ops_dir: Path,
    now_value: Optional[str],
    action: str,
) -> tuple[dict[str, Any], Optional[dict[str, Any]]]:
    report = build_base_report(action, task_dir, ops_dir)
    failures = report["hard_gate_failures"]
    warnings = report["warnings"]
    try:
        now = parse_now(now_value)
    except ValueError as exc:
        report.update({"reason": "invalid_now", "error": str(exc), "next_step": "rerun with a valid --now value"})
        return report, None

    try:
        status = load_status_for_validation(task_dir, failures)
        manifest = load_manifest_for_validation(task_dir, failures)
        if manifest is None:
            return report, None
        report.update(
            {
                "run_id": manifest.get("run_id"),
                "experiment_plan_id": manifest.get("experiment_plan_id"),
                "accepted_plan_task_id": manifest.get("accepted_plan_task_id"),
            }
        )
        validate_manifest_identity(task_dir, status, manifest, failures)
        validate_path_containment(ops_dir, task_dir, manifest, failures)
        validate_completed_manifest(manifest, failures)
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
        mark_malformed(report, exc)
        return report, None

    return report, {"status": status, "manifest": manifest, "plan": plan}


def finalize_report(report: dict[str, Any], clean_next_step: str, blocked_next_step: str) -> int:
    failures = report["hard_gate_failures"]
    warnings = report["warnings"]
    if report.get("reason") in {"invalid_now"}:
        print_json(report)
        return INVALID_REQUEST
    if report.get("reason") == "malformed_task_state":
        report.update({"failure_count": len(failures), "warning_count": len(warnings)})
        print_json(report)
        return MALFORMED

    ok = not failures
    report.update(
        {
            "ok": ok,
            "failure_count": len(failures),
            "warning_count": len(warnings),
            "next_step": blocked_next_step if failures else "review warnings before result acceptance" if warnings else clean_next_step,
        }
    )
    print_json(report)
    return SUCCESS if ok and not warnings else VALIDATION_FAILED


def validate_run(args: argparse.Namespace) -> int:
    report, context = validate_common(args.task_dir, args.ops_dir, args.now, "analysis_validate_run")
    if context is not None:
        try:
            manifest = context["manifest"]
            outputs = load_structured_outputs(args.task_dir, manifest, report["hard_gate_failures"])
            validate_required_output_files(args.ops_dir, manifest, report["hard_gate_failures"])
            validate_metrics_against_plan(outputs.get("metrics"), manifest, context.get("plan"), report["hard_gate_failures"])
            validate_robustness_semantics(
                outputs.get("robustness"),
                context.get("plan"),
                report["hard_gate_failures"],
                report["warnings"],
            )
            report["structured_outputs"] = {
                name: str(args.task_dir / ANALYSIS_RUN_DIR / spec[0])
                for name, spec in STRUCTURED_OUTPUTS.items()
            }
        except PreflightMalformed as exc:
            mark_malformed(report, exc)
    return finalize_report(report, "validate result summary and claim gates", "repair analysis run blockers before result acceptance")


def validate_results(args: argparse.Namespace) -> int:
    report, context = validate_common(args.task_dir, args.ops_dir, args.now, "analysis_validate_results")
    if context is not None:
        try:
            manifest = context["manifest"]
            outputs = load_structured_outputs(args.task_dir, manifest, report["hard_gate_failures"])
            validate_required_output_files(args.ops_dir, manifest, report["hard_gate_failures"])
            validate_metrics_against_plan(outputs.get("metrics"), manifest, context.get("plan"), report["hard_gate_failures"])
            validate_robustness_semantics(
                outputs.get("robustness"),
                context.get("plan"),
                report["hard_gate_failures"],
                report["warnings"],
            )
            summary = load_result_summary(args.task_dir)
            if summary is None:
                add_failure(
                    report["hard_gate_failures"],
                    "result_summary_present",
                    "worker_output.md or artifacts/result_summary.json must contain a structured result summary.",
                )
            else:
                validate_summary_identity(summary, manifest, report["hard_gate_failures"], report["warnings"])
                validate_summary_substance(
                    args.ops_dir,
                    args.task_dir,
                    summary,
                    manifest,
                    outputs.get("metrics"),
                    report["hard_gate_failures"],
                )
                report["claim_gates"] = validate_claim_gates(
                    args.task_dir,
                    manifest,
                    summary,
                    outputs,
                    report["hard_gate_failures"],
                    report["warnings"],
                )
                report["result_summary"] = {
                    "result_id": summary.get("result_id"),
                    "claim_type": summary.get("claim_type"),
                    "claim_strength": summary.get("claim_strength"),
                    "recommended_decision": summary.get("recommended_decision"),
                }
        except PreflightMalformed as exc:
            mark_malformed(report, exc)
    return finalize_report(report, "ready for result acceptance review", "repair result validation blockers before result acceptance")


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate completed analysis-run artifacts before result acceptance.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("validate-run", "Validate a completed run manifest and structured analysis artifacts."),
        ("validate-results", "Validate result summary and claim gates against completed analysis artifacts."),
    ):
        command = subparsers.add_parser(name, help=help_text, description=help_text)
        command.add_argument("task_dir", type=Path, help="run_analysis task directory to validate.")
        command.add_argument("--ops-dir", type=Path, required=True, help="research_ops directory.")
        command.add_argument("--now", help="Override current time for deterministic source/data and memory checks.")
    return parser.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    if args.command == "validate-run":
        return validate_run(args)
    if args.command == "validate-results":
        return validate_results(args)
    print_json({"ok": False, "reason": "unknown_command", "command": args.command})
    return INVALID_REQUEST


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
