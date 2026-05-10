#!/usr/bin/env python3
"""Validate completed analysis-run artifacts before result acceptance."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
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


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


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


def validate_robustness_semantics(robustness: Optional[dict[str, Any]], failures: list[dict[str, Any]]) -> None:
    if robustness is None:
        return
    invalid_support = [
        {
            "name": item.get("name"),
            "status": item.get("status"),
            "decision_impact": item.get("decision_impact"),
        }
        for item in robustness.get("planned_checks", [])
        if isinstance(item, dict)
        and normalize_text(item.get("decision_impact")) == "supports_claim"
        and normalize_text(item.get("status")) in {"not_run", "fail", "not_applicable"}
    ]
    if invalid_support:
        add_failure(
            failures,
            "robustness_semantics",
            "Robustness checks that did not pass cannot support a claim.",
            invalid_support,
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
        comparisons = ["run_id", "experiment_plan_id", "task_id", "claim_type", "claim_decision", "recommended_route", "max_claim_strength"]
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
        report.update(
            {
                "reason": "malformed_task_state",
                "error": str(exc),
                "next_step": "repair malformed task artifacts before analysis validation",
            }
        )
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
        manifest = context["manifest"]
        outputs = load_structured_outputs(args.task_dir, manifest, report["hard_gate_failures"])
        validate_required_output_files(args.ops_dir, manifest, report["hard_gate_failures"])
        validate_metrics_against_plan(outputs.get("metrics"), manifest, context.get("plan"), report["hard_gate_failures"])
        validate_robustness_semantics(outputs.get("robustness"), report["hard_gate_failures"])
        report["structured_outputs"] = {
            name: str(args.task_dir / ANALYSIS_RUN_DIR / spec[0])
            for name, spec in STRUCTURED_OUTPUTS.items()
        }
    return finalize_report(report, "validate result summary and claim gates", "repair analysis run blockers before result acceptance")


def validate_results(args: argparse.Namespace) -> int:
    report, context = validate_common(args.task_dir, args.ops_dir, args.now, "analysis_validate_results")
    if context is not None:
        manifest = context["manifest"]
        outputs = load_structured_outputs(args.task_dir, manifest, report["hard_gate_failures"])
        validate_required_output_files(args.ops_dir, manifest, report["hard_gate_failures"])
        validate_metrics_against_plan(outputs.get("metrics"), manifest, context.get("plan"), report["hard_gate_failures"])
        validate_robustness_semantics(outputs.get("robustness"), report["hard_gate_failures"])
        summary = load_result_summary(args.task_dir)
        if summary is None:
            add_failure(
                report["hard_gate_failures"],
                "result_summary_present",
                "worker_output.md or artifacts/result_summary.json must contain a structured result summary.",
            )
        else:
            validate_summary_identity(summary, manifest, report["hard_gate_failures"], report["warnings"])
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
