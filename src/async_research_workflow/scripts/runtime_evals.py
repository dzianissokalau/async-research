#!/usr/bin/env python3
"""Build and run trace-driven runtime evaluation suites."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import statistics
import sys
from typing import Any, Iterable

from async_research_workflow.resources import schema_path
from async_research_workflow.scripts import runtime_artifacts
from async_research_workflow.scripts.validate_json_artifact import load_json
from async_research_workflow.scripts.validate_json_artifact import validate


SUCCESS = 0
VALIDATION_FAILED = 2
INVALID_REQUEST = 3
MALFORMED = 4

SCHEMA_VERSION = "1.0"
SUITE_FRAMEWORK_VERSION = "runtime_eval_suite_v1.0"
RUN_FRAMEWORK_VERSION = "runtime_eval_run_v1.0"

EVALS_DIR = Path("evals")
RUNS_DIR = EVALS_DIR / "runs"
SUITE_SCHEMA_NAME = "runtime_eval_suite.schema.json"
RUN_SCHEMA_NAME = "runtime_eval_run.schema.json"
NO_VALUE_MARKERS = {"", "none", "unknown", "n/a", "na", "todo", "tbd"}
UNSUPPORTED_CLAIM_OUTCOMES = {"unsupported", "contradicted", "unverifiable"}
GROUNDED_CLAIM_OUTCOMES = {"supported", "weakly_supported"}
FRESHNESS_FAILURE_OUTCOMES = {"stale"}
HIGHER_IS_BETTER = {
    "grounded_claim_rate",
    "task_success_rate",
    "accepted_output_rate",
    "reproducibility_pass_rate",
}
LOWER_IS_BETTER = {
    "unsupported_claim_rate",
    "freshness_failure_rate",
    "stale_evidence_reuse_rate",
    "cost_per_accepted_report_usd",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def load_json_optional(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def load_json_required(path: Path) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, issue("file_missing", "JSON file does not exist", path=str(path))
    except json.JSONDecodeError as exc:
        return None, issue("invalid_json", f"JSON file is malformed: {exc.msg}", path=str(path))
    if not isinstance(payload, dict):
        return None, issue("json_not_object", "JSON file must contain an object", path=str(path))
    return payload, None


def issue(reason: str, message: str, **extra: Any) -> dict[str, Any]:
    payload = {"reason": reason, "message": message}
    payload.update({key: value for key, value in extra.items() if value is not None})
    return payload


def numeric(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def integer(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


def ratio(numerator: float, denominator: float, *, empty_value: float) -> float:
    if denominator <= 0:
        return empty_value
    return round(numerator / denominator, 6)


def workspace_path(ops_dir: Path, path_text: Any) -> Path | None:
    if not isinstance(path_text, str):
        return None
    posix = PurePosixPath(path_text)
    if posix.is_absolute() or not posix.parts:
        return None
    if posix.parts[0] != "research_ops":
        return None
    if any(part in {"", ".", ".."} for part in posix.parts):
        return None
    candidate = (ops_dir.parent / Path(*posix.parts)).resolve(strict=False)
    try:
        candidate.relative_to(ops_dir.resolve(strict=False))
    except ValueError:
        return None
    return candidate


def ref_for_path(ops_dir: Path, path: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(ops_dir.parent.resolve(strict=False)).as_posix()
    except ValueError:
        return path.as_posix()


def path_inside_ops(ops_dir: Path, path: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(ops_dir.resolve(strict=False))
    except ValueError:
        return False
    return True


def safe_output_path(ops_dir: Path, output: Path) -> Path | None:
    candidate = output if output.is_absolute() else ops_dir.parent / output
    candidate = candidate.resolve(strict=False)
    if not path_inside_ops(ops_dir, candidate):
        return None
    if not path_inside_ops(ops_dir / EVALS_DIR, candidate):
        return None
    return candidate


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        return rows
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return rows
    for line in lines:
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def task_dir_for_id(ops_dir: Path, task_id: str) -> Path | None:
    direct = ops_dir / "tasks" / task_id
    if direct.is_dir():
        return direct
    matches = sorted(path for path in (ops_dir / "tasks").glob(f"{task_id}-*") if path.is_dir())
    return matches[0] if matches else None


def load_task_status(ops_dir: Path, task_id: str) -> tuple[Path | None, dict[str, Any]]:
    task_dir = task_dir_for_id(ops_dir, task_id)
    if task_dir is None:
        return None, {}
    status = load_json_optional(task_dir / "status.json") or {}
    return task_dir, status


def load_workspace_brief(ops_dir: Path, status: dict[str, Any]) -> dict[str, Any]:
    if isinstance(status.get("research_brief"), dict):
        return dict(status["research_brief"])
    brief_ref = status.get("research_brief_ref")
    if isinstance(brief_ref, str):
        resolved = workspace_path(ops_dir, brief_ref)
        if resolved is not None:
            payload = load_json_optional(resolved)
            if payload is not None:
                return payload
    default = ops_dir / "briefs" / "research_brief.json"
    payload = load_json_optional(default)
    if payload is not None:
        return payload
    return {}


def compact_input_brief(ops_dir: Path, status: dict[str, Any], task_id: str) -> dict[str, Any]:
    brief = load_workspace_brief(ops_dir, status)
    if brief:
        return {
            "brief_id": brief.get("brief_id") or brief.get("id") or "workspace_brief",
            "clarified_objective": brief.get("clarified_objective") or brief.get("objective") or brief.get("user_question") or "",
            "target_audience": brief.get("target_audience") or "",
            "intended_output_maturity": brief.get("intended_output_maturity") or "",
            "target_venue": brief.get("target_venue") or "",
            "allowed_source_classes": brief.get("allowed_source_classes") if isinstance(brief.get("allowed_source_classes"), list) else [],
            "forbidden_source_classes": brief.get("forbidden_source_classes") if isinstance(brief.get("forbidden_source_classes"), list) else [],
            "public_claims_policy": brief.get("public_claims_policy") or "",
        }
    return {
        "brief_id": f"{task_id}_task_contract",
        "clarified_objective": status.get("title") or task_id,
        "target_audience": status.get("target_audience") or "",
        "intended_output_maturity": status.get("target_maturity") or "",
        "target_venue": status.get("target_venue") or "",
        "allowed_source_classes": [],
        "forbidden_source_classes": [],
        "public_claims_policy": "task_contract",
    }


def trace_cost(trace: dict[str, Any]) -> float:
    cost = trace.get("cost") if isinstance(trace.get("cost"), dict) else {}
    return round(numeric(cost.get("api_usd")) + numeric(cost.get("compute_usd")), 6)


def trace_tokens(trace: dict[str, Any]) -> int:
    usage = trace.get("token_usage") if isinstance(trace.get("token_usage"), dict) else {}
    return integer(usage.get("total_tokens"))


def evidence_stale(evidence: dict[str, Any]) -> bool:
    freshness = evidence.get("freshness_status") if isinstance(evidence.get("freshness_status"), dict) else {}
    return str(freshness.get("status") or "").lower() == "stale"


def evidence_unsupported(evidence: dict[str, Any]) -> bool:
    license_policy = str(evidence.get("license_or_use_policy") or "").strip().lower()
    permission = evidence.get("permission_basis") if isinstance(evidence.get("permission_basis"), dict) else {}
    spans = evidence.get("span_refs")
    return license_policy in NO_VALUE_MARKERS or permission.get("type") == "none" or not isinstance(spans, list) or not spans


def claim_outcome_counts(claim_report: dict[str, Any]) -> dict[str, int]:
    raw = claim_report.get("outcome_counts") if isinstance(claim_report.get("outcome_counts"), dict) else {}
    outcomes = {
        "supported": 0,
        "weakly_supported": 0,
        "unsupported": 0,
        "contradicted": 0,
        "stale": 0,
        "unverifiable": 0,
    }
    for key in outcomes:
        outcomes[key] = integer(raw.get(key))
    return outcomes


def task_is_accepted(status: dict[str, Any], result_acceptance: dict[str, Any]) -> bool:
    if result_acceptance.get("acceptance_ok") is True or result_acceptance.get("status") in {"pass", "accepted"}:
        return True
    if result_acceptance.get("ok") is True:
        return True
    return status.get("status") in {"accepted", "synthesized"}


def has_reviewer_disagreement(aggregate: dict[str, Any]) -> bool:
    disagreements = aggregate.get("disagreements")
    if isinstance(disagreements, list):
        return any(str(item).strip().lower() not in {"", "none", "no disagreement", "no_disagreement"} for item in disagreements)
    if isinstance(disagreements, str):
        return disagreements.strip().lower() not in {"", "none", "no disagreement", "no_disagreement"}
    return False


def case_metrics(
    traces: list[dict[str, Any]],
    evidence_rows: list[dict[str, Any]],
    claim_report: dict[str, Any],
    *,
    accepted: bool,
    reviewer_disagreement: bool,
) -> dict[str, Any]:
    outcomes = claim_outcome_counts(claim_report)
    claim_count = integer(claim_report.get("claim_count")) or sum(outcomes.values())
    grounded = sum(outcomes[outcome] for outcome in GROUNDED_CLAIM_OUTCOMES)
    unsupported = sum(outcomes[outcome] for outcome in UNSUPPORTED_CLAIM_OUTCOMES)
    stale_claims = sum(outcomes[outcome] for outcome in FRESHNESS_FAILURE_OUTCOMES)
    total_cost = round(sum(trace_cost(trace) for trace in traces), 6)
    total_latency = round(sum(numeric(trace.get("duration_ms")) for trace in traces), 3)
    total_tokens = sum(trace_tokens(trace) for trace in traces)
    stale_evidence_count = sum(1 for evidence in evidence_rows if evidence_stale(evidence))
    unsupported_evidence_count = sum(1 for evidence in evidence_rows if evidence_unsupported(evidence))
    accepted_output = 1.0 if accepted else 0.0
    return {
        "trace_count": len(traces),
        "evidence_object_count": len(evidence_rows),
        "claim_count": claim_count,
        "grounded_claim_count": grounded,
        "unsupported_claim_count": unsupported,
        "stale_claim_count": stale_claims,
        "grounded_claim_rate": ratio(grounded, claim_count, empty_value=1.0),
        "unsupported_claim_rate": ratio(unsupported, claim_count, empty_value=0.0),
        "freshness_failure_rate": ratio(stale_claims + stale_evidence_count, max(claim_count + len(evidence_rows), 1), empty_value=0.0),
        "stale_evidence_count": stale_evidence_count,
        "unsupported_evidence_count": unsupported_evidence_count,
        "task_success": accepted_output,
        "accepted_output": accepted_output,
        "cost_usd": total_cost,
        "latency_ms": total_latency,
        "token_count": total_tokens,
        "reviewer_disagreement": 1.0 if reviewer_disagreement else 0.0,
        "reproducibility_pass": 1.0,
    }


def aggregate_metrics(metrics_rows: list[dict[str, Any]]) -> dict[str, Any]:
    case_count = len(metrics_rows)
    total_claims = sum(integer(row.get("claim_count")) for row in metrics_rows)
    grounded_claims = sum(integer(row.get("grounded_claim_count")) for row in metrics_rows)
    unsupported_claims = sum(integer(row.get("unsupported_claim_count")) for row in metrics_rows)
    stale_evidence = sum(integer(row.get("stale_evidence_count")) for row in metrics_rows)
    evidence_count = sum(integer(row.get("evidence_object_count")) for row in metrics_rows)
    accepted_count = sum(1 for row in metrics_rows if numeric(row.get("accepted_output")) >= 1.0)
    total_cost = round(sum(numeric(row.get("cost_usd")) for row in metrics_rows), 6)
    accepted_latencies = [numeric(row.get("latency_ms")) for row in metrics_rows if numeric(row.get("accepted_output")) >= 1.0]
    return {
        "case_count": case_count,
        "grounded_claim_rate": ratio(grounded_claims, total_claims, empty_value=1.0),
        "unsupported_claim_rate": ratio(unsupported_claims, total_claims, empty_value=0.0),
        "task_success_rate": ratio(sum(numeric(row.get("task_success")) for row in metrics_rows), case_count, empty_value=0.0),
        "accepted_output_rate": ratio(sum(numeric(row.get("accepted_output")) for row in metrics_rows), case_count, empty_value=0.0),
        "cost_per_accepted_report_usd": round(total_cost / accepted_count, 6) if accepted_count else 0.0,
        "median_latency_to_accepted_report_ms": round(statistics.median(accepted_latencies), 3) if accepted_latencies else 0.0,
        "freshness_failure_rate": ratio(sum(numeric(row.get("freshness_failure_rate")) for row in metrics_rows), case_count, empty_value=0.0),
        "stale_evidence_reuse_rate": ratio(stale_evidence, evidence_count, empty_value=0.0),
        "reviewer_disagreement_rate": ratio(sum(numeric(row.get("reviewer_disagreement")) for row in metrics_rows), case_count, empty_value=0.0),
        "reproducibility_pass_rate": ratio(sum(numeric(row.get("reproducibility_pass")) for row in metrics_rows), case_count, empty_value=0.0),
        "total_cost_usd": total_cost,
        "accepted_report_count": accepted_count,
    }


def evidence_reference(evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "evidence_id": evidence.get("evidence_id"),
        "source_uri": evidence.get("source_uri"),
        "content_hash": evidence.get("content_hash"),
        "snapshot_path": evidence.get("snapshot_path"),
        "span_refs": evidence.get("span_refs") if isinstance(evidence.get("span_refs"), list) else [],
        "freshness_status": evidence.get("freshness_status") if isinstance(evidence.get("freshness_status"), dict) else {},
        "license_or_use_policy": evidence.get("license_or_use_policy") or "",
    }


def case_from_task(
    ops_dir: Path,
    *,
    case_index: int,
    task_id: str,
    traces: list[dict[str, Any]],
    evidence_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    task_dir, status = load_task_status(ops_dir, task_id)
    result_acceptance_path = task_dir / "review_panel" / "result_acceptance.json" if task_dir else None
    aggregate_path = task_dir / "review_panel" / "aggregate.json" if task_dir else None
    result_acceptance = load_json_optional(result_acceptance_path) if result_acceptance_path else None
    aggregate = load_json_optional(aggregate_path) if aggregate_path else None
    result_acceptance = result_acceptance or {}
    aggregate = aggregate or {}
    claim_report = result_acceptance.get("claim_verification") if isinstance(result_acceptance.get("claim_verification"), dict) else {}
    accepted = task_is_accepted(status, result_acceptance)
    reviewer_disagreement = has_reviewer_disagreement(aggregate)
    metrics = case_metrics(traces, evidence_rows, claim_report, accepted=accepted, reviewer_disagreement=reviewer_disagreement)
    evidence_ids = [str(row.get("evidence_id")) for row in evidence_rows if row.get("evidence_id")]
    artifact_paths = {
        "trace_ledger": "research_ops/runtime/traces.jsonl",
        "evidence_ledger": "research_ops/runtime/evidence_objects.jsonl",
    }
    if task_dir is not None:
        artifact_paths["task_status"] = ref_for_path(ops_dir, task_dir / "status.json")
    if result_acceptance_path is not None and result_acceptance_path.is_file():
        artifact_paths["result_acceptance"] = ref_for_path(ops_dir, result_acceptance_path)
    if aggregate_path is not None and aggregate_path.is_file():
        artifact_paths["review_aggregate"] = ref_for_path(ops_dir, aggregate_path)
    known_limitations = [
        "automated graders check trace, evidence, citation, cost, and acceptance artifacts only",
        "subjective expert preference requires a separately recorded human-calibrated rubric",
    ]
    if not claim_report:
        known_limitations.append("no claim-verification artifact was available for this case")
    return {
        "case_id": f"EVAL-{case_index:04d}",
        "task_id": task_id,
        "source_trace_ids": [str(trace.get("trace_id")) for trace in traces if trace.get("trace_id")],
        "source_evidence_ids": evidence_ids,
        "input_brief": compact_input_brief(ops_dir, status, task_id),
        "expected_behavior": {
            "accepted_output_required": bool(result_acceptance),
            "claim_verification_required": bool(claim_report.get("required")),
            "required_evidence_ids": evidence_ids,
            "min_grounded_claim_rate": 1.0,
            "max_unsupported_claim_rate": 0.0,
            "max_freshness_failure_rate": 0.0,
            "reproducibility_required": True,
            "stop_conditions": [
                "no live network, paid calls, or credentials during default eval run",
                "human-calibrated rubric graders must be marked separately",
            ],
        },
        "gold_or_reference_evidence": [evidence_reference(evidence) for evidence in evidence_rows],
        "grader": {
            "type": "composite",
            "automated": True,
            "human_calibrated": False,
            "checks": [
                "schema_path_hash",
                "groundedness",
                "citation_support",
                "task_success",
                "cost_latency",
                "human_review_placeholder",
            ],
        },
        "metrics": metrics,
        "known_limitations": known_limitations,
        "artifacts": artifact_paths,
    }


def build_suite(
    ops_dir: Path,
    *,
    suite_id: str,
    now: str,
    policy_id: str,
    model_routing_policy: str,
) -> tuple[int, dict[str, Any]]:
    validation_code, validation = runtime_artifacts.validate_runtime_workspace(ops_dir)
    if validation_code == runtime_artifacts.MALFORMED:
        return MALFORMED, validation
    if validation.get("errors"):
        return VALIDATION_FAILED, {
            "ok": False,
            "action": "eval_build_from_traces",
            "reason": "runtime_artifacts_invalid",
            "ops_dir": str(ops_dir),
            "read_only": True,
            "changed": False,
            "errors": validation.get("errors", []),
            "warnings": validation.get("warnings", []),
        }
    traces = read_jsonl(ops_dir / runtime_artifacts.TRACE_LEDGER)
    evidence_rows = read_jsonl(ops_dir / runtime_artifacts.EVIDENCE_LEDGER)
    if not traces:
        return VALIDATION_FAILED, {
            "ok": False,
            "action": "eval_build_from_traces",
            "reason": "runtime_traces_missing",
            "ops_dir": str(ops_dir),
            "read_only": True,
            "changed": False,
            "errors": [issue("runtime_traces_missing", "eval build-from-traces requires at least one runtime trace")],
            "warnings": validation.get("warnings", []),
        }
    task_ids = sorted({str(trace.get("task_id")) for trace in traces if isinstance(trace.get("task_id"), str)})
    cases: list[dict[str, Any]] = []
    for index, task_id in enumerate(task_ids, start=1):
        task_traces = [trace for trace in traces if trace.get("task_id") == task_id]
        task_evidence = [evidence for evidence in evidence_rows if evidence.get("task_id") == task_id]
        cases.append(case_from_task(ops_dir, case_index=index, task_id=task_id, traces=task_traces, evidence_rows=task_evidence))
    suite = {
        "schema_version": SCHEMA_VERSION,
        "framework_version": SUITE_FRAMEWORK_VERSION,
        "suite_id": suite_id,
        "built_at": now,
        "source_ops_dir": str(ops_dir),
        "runtime_policy": policy_id,
        "model_routing_policy": model_routing_policy,
        "human_calibration": {
            "status": "not_included",
            "required_for": ["expert_preference_win_rate", "task_success_rubric_override"],
        },
        "release_policy": {
            "baseline_required": True,
            "regressions_block_release": True,
            "quality_claims_require_eval_evidence": True,
            "deep_research_comparisons": "out_of_scope_until_phase_10",
        },
        "case_count": len(cases),
        "metrics": aggregate_metrics([case["metrics"] for case in cases]),
        "cases": cases,
        "known_limitations": [
            "default evals are deterministic and offline",
            "paid live model calls are not required or performed",
            "expert preference requires explicit human calibration before use in release claims",
        ],
    }
    schema_errors = [error.to_dict() for error in validate(suite, load_json(schema_path(SUITE_SCHEMA_NAME)))]
    if schema_errors:
        return MALFORMED, {
            "ok": False,
            "action": "eval_build_from_traces",
            "reason": "eval_suite_schema_invalid",
            "ops_dir": str(ops_dir),
            "read_only": True,
            "changed": False,
            "suite": suite,
            "errors": schema_errors,
            "warnings": validation.get("warnings", []),
        }
    return SUCCESS, suite


def build_from_traces_command(args: argparse.Namespace) -> int:
    now = args.now or utc_now()
    code, suite_or_error = build_suite(
        args.ops_dir,
        suite_id=args.suite_id,
        now=now,
        policy_id=args.runtime_policy,
        model_routing_policy=args.model_routing_policy,
    )
    if code != SUCCESS:
        print_json(suite_or_error)
        return code
    output_path = safe_output_path(args.ops_dir, args.output or args.ops_dir / EVALS_DIR / f"{args.suite_id}.json")
    if output_path is None:
        print_json(
            {
                "ok": False,
                "action": "eval_build_from_traces",
                "reason": "unsafe_output_path",
                "ops_dir": str(args.ops_dir),
                "output": str(args.output),
                "changed": False,
                "errors": [issue("unsafe_output_path", "eval suite output must stay under research_ops/evals")],
                "warnings": [],
            }
        )
        return INVALID_REQUEST
    if args.write:
        atomic_write_json(output_path, suite_or_error)
    print_json(
        {
            "ok": True,
            "action": "eval_build_from_traces",
            "ops_dir": str(args.ops_dir),
            "suite_path": str(output_path),
            "changed": bool(args.write),
            "read_only": not args.write,
            "summary": suite_or_error["metrics"],
            "suite": suite_or_error,
            "errors": [],
            "warnings": [],
        }
    )
    return SUCCESS


def validate_suite_payload(suite: dict[str, Any]) -> list[dict[str, Any]]:
    return [error.to_dict() for error in validate(suite, load_json(schema_path(SUITE_SCHEMA_NAME)))]


def validate_run_payload(run: dict[str, Any]) -> list[dict[str, Any]]:
    return [error.to_dict() for error in validate(run, load_json(schema_path(RUN_SCHEMA_NAME)))]


def snapshot_hash_findings(source_ops_dir: Path, case: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for evidence in case.get("gold_or_reference_evidence", []):
        if not isinstance(evidence, dict):
            continue
        evidence_id = str(evidence.get("evidence_id") or "unknown")
        snapshot_ref = evidence.get("snapshot_path")
        snapshot_path = workspace_path(source_ops_dir, snapshot_ref)
        if snapshot_path is None:
            findings.append(issue("snapshot_path_invalid", "evidence snapshot path must stay under research_ops", evidence_id=evidence_id, path=snapshot_ref))
            continue
        if not snapshot_path.is_file():
            findings.append(issue("snapshot_missing", "evidence snapshot is missing", evidence_id=evidence_id, path=str(snapshot_path)))
            continue
        expected = str(evidence.get("content_hash") or "")
        actual = sha256_file(snapshot_path)
        if expected != actual:
            findings.append(
                issue(
                    "snapshot_hash_mismatch",
                    "evidence snapshot hash does not match the eval suite reference",
                    evidence_id=evidence_id,
                    expected=expected,
                    actual=actual,
                )
            )
    return findings


def grade_case(case: dict[str, Any], source_ops_dir: Path | None) -> dict[str, Any]:
    metrics = dict(case.get("metrics") if isinstance(case.get("metrics"), dict) else {})
    expected = case.get("expected_behavior") if isinstance(case.get("expected_behavior"), dict) else {}
    checks: list[dict[str, Any]] = []
    automated_failures: list[dict[str, Any]] = []

    hash_findings = snapshot_hash_findings(source_ops_dir, case) if source_ops_dir is not None else [
        issue("source_ops_dir_missing", "source_ops_dir is unavailable, so snapshot reproducibility cannot be checked")
    ]
    checks.append(
        {
            "name": "schema_path_hash",
            "status": "pass" if not hash_findings else "fail",
            "findings": hash_findings,
        }
    )
    automated_failures.extend(hash_findings)

    grounded_rate = numeric(metrics.get("grounded_claim_rate"))
    min_grounded = numeric(expected.get("min_grounded_claim_rate"))
    grounded_ok = grounded_rate >= min_grounded
    checks.append(
        {
            "name": "groundedness",
            "status": "pass" if grounded_ok else "fail",
            "observed": grounded_rate,
            "threshold": min_grounded,
        }
    )
    if not grounded_ok:
        automated_failures.append(issue("groundedness_regression", "grounded claim rate is below the eval case threshold"))

    unsupported_rate = numeric(metrics.get("unsupported_claim_rate"))
    max_unsupported = numeric(expected.get("max_unsupported_claim_rate"))
    freshness_rate = numeric(metrics.get("freshness_failure_rate"))
    max_freshness = numeric(expected.get("max_freshness_failure_rate"))
    citation_ok = unsupported_rate <= max_unsupported and freshness_rate <= max_freshness
    checks.append(
        {
            "name": "citation_support",
            "status": "pass" if citation_ok else "fail",
            "unsupported_claim_rate": unsupported_rate,
            "max_unsupported_claim_rate": max_unsupported,
            "freshness_failure_rate": freshness_rate,
            "max_freshness_failure_rate": max_freshness,
        }
    )
    if unsupported_rate > max_unsupported:
        automated_failures.append(issue("unsupported_claim_rate_exceeded", "unsupported claim rate exceeds the eval case threshold"))
    if freshness_rate > max_freshness:
        automated_failures.append(issue("freshness_failure_rate_exceeded", "freshness failure rate exceeds the eval case threshold"))

    accepted_required = expected.get("accepted_output_required") is True
    task_success = numeric(metrics.get("task_success"))
    accepted_output = numeric(metrics.get("accepted_output"))
    task_ok = task_success >= 1.0 and (not accepted_required or accepted_output >= 1.0)
    checks.append(
        {
            "name": "task_success",
            "status": "pass" if task_ok else "fail",
            "accepted_output_required": accepted_required,
            "task_success": task_success,
            "accepted_output": accepted_output,
        }
    )
    if not task_ok:
        automated_failures.append(issue("task_success_failed", "case did not satisfy accepted-output or task-success expectations"))

    cost_ok = numeric(metrics.get("cost_usd")) >= 0 and numeric(metrics.get("latency_ms")) >= 0
    checks.append(
        {
            "name": "cost_latency",
            "status": "pass" if cost_ok else "fail",
            "cost_usd": numeric(metrics.get("cost_usd")),
            "latency_ms": numeric(metrics.get("latency_ms")),
        }
    )
    if not cost_ok:
        automated_failures.append(issue("cost_latency_invalid", "cost and latency metrics must be non-negative"))

    checks.append(
        {
            "name": "human_review_placeholder",
            "status": "manual_placeholder",
            "message": "expert preference and subjective task-success rubrics require separately recorded human calibration",
        }
    )
    metrics["reproducibility_pass"] = 0.0 if automated_failures else 1.0
    return {
        "case_id": case.get("case_id"),
        "task_id": case.get("task_id"),
        "status": "pass" if not automated_failures else "fail",
        "metrics": metrics,
        "checks": checks,
        "findings": automated_failures,
        "known_limitations": case.get("known_limitations") if isinstance(case.get("known_limitations"), list) else [],
    }


def run_suite(suite_path: Path, *, run_id: str, now: str) -> tuple[int, dict[str, Any]]:
    suite, error = load_json_required(suite_path)
    if error is not None or suite is None:
        return INVALID_REQUEST, {
            "ok": False,
            "action": "eval_run",
            "changed": False,
            "read_only": True,
            "errors": [error or issue("eval_suite_missing", "eval suite could not be loaded")],
            "warnings": [],
        }
    schema_errors = validate_suite_payload(suite)
    if schema_errors:
        return VALIDATION_FAILED, {
            "ok": False,
            "action": "eval_run",
            "suite_path": str(suite_path),
            "changed": False,
            "read_only": True,
            "errors": schema_errors,
            "warnings": [],
        }
    source_ops_dir_text = suite.get("source_ops_dir")
    source_ops_dir = Path(source_ops_dir_text) if isinstance(source_ops_dir_text, str) and source_ops_dir_text else None
    if source_ops_dir is not None and not source_ops_dir.is_dir():
        source_ops_dir = None
    cases = suite.get("cases") if isinstance(suite.get("cases"), list) else []
    case_results = [grade_case(case, source_ops_dir) for case in cases if isinstance(case, dict)]
    metrics = aggregate_metrics([result["metrics"] for result in case_results])
    failures = [finding for result in case_results for finding in result.get("findings", [])]
    residual_risks = list(suite.get("known_limitations") if isinstance(suite.get("known_limitations"), list) else [])
    residual_risks.append("human-calibrated evals are tracked separately from automated deterministic graders")
    run = {
        "ok": not failures,
        "schema_version": SCHEMA_VERSION,
        "framework_version": RUN_FRAMEWORK_VERSION,
        "action": "eval_run",
        "run_id": run_id,
        "suite_id": suite.get("suite_id"),
        "suite_path": str(suite_path),
        "evaluated_at": now,
        "status": "pass" if not failures else "fail",
        "runtime_policy": suite.get("runtime_policy"),
        "model_routing_policy": suite.get("model_routing_policy"),
        "human_calibration": suite.get("human_calibration"),
        "metrics": metrics,
        "case_results": case_results,
        "residual_risks": residual_risks,
        "errors": failures,
        "warnings": [],
        "changed": False,
        "read_only": True,
    }
    run_schema_errors = validate_run_payload(run)
    if run_schema_errors:
        return MALFORMED, {
            "ok": False,
            "action": "eval_run",
            "suite_path": str(suite_path),
            "changed": False,
            "read_only": True,
            "errors": run_schema_errors,
            "warnings": [],
            "run": run,
        }
    return (SUCCESS if not failures else VALIDATION_FAILED), run


def default_run_output_path(suite_path: Path, run: dict[str, Any]) -> Path:
    suite, _ = load_json_required(suite_path)
    source_ops_dir = suite.get("source_ops_dir") if isinstance(suite, dict) else None
    if isinstance(source_ops_dir, str) and source_ops_dir:
        return Path(source_ops_dir) / RUNS_DIR / f"{run['run_id']}.json"
    return suite_path.parent / "runs" / f"{run['run_id']}.json"


def run_suite_command(args: argparse.Namespace) -> int:
    now = args.now or utc_now()
    run_id = args.run_id or f"RUN-{now.replace(':', '').replace('-', '').replace('Z', 'Z')}"
    code, run = run_suite(args.eval_suite, run_id=run_id, now=now)
    if code in {SUCCESS, VALIDATION_FAILED} and args.write:
        output = args.output or default_run_output_path(args.eval_suite, run)
        suite, _ = load_json_required(args.eval_suite)
        source_ops_dir = Path(suite["source_ops_dir"]) if isinstance(suite, dict) and isinstance(suite.get("source_ops_dir"), str) else None
        if source_ops_dir is None:
            print_json(
                {
                    "ok": False,
                    "action": "eval_run",
                    "reason": "source_ops_dir_missing",
                    "changed": False,
                    "errors": [issue("source_ops_dir_missing", "cannot safely write eval run without source_ops_dir")],
                    "warnings": [],
                }
            )
            return INVALID_REQUEST
        output_path = safe_output_path(source_ops_dir, output)
        if output_path is None:
            print_json(
                {
                    "ok": False,
                    "action": "eval_run",
                    "reason": "unsafe_output_path",
                    "output": str(output),
                    "changed": False,
                    "errors": [issue("unsafe_output_path", "eval run output must stay under research_ops/evals")],
                    "warnings": [],
                }
            )
            return INVALID_REQUEST
        atomic_write_json(output_path, {**run, "changed": True, "read_only": False})
        run["output_path"] = str(output_path)
        run["changed"] = True
        run["read_only"] = False
    print_json(run)
    return code


def metric_delta(baseline: dict[str, Any], candidate: dict[str, Any], metric: str) -> dict[str, Any]:
    base_value = numeric(baseline.get(metric))
    candidate_value = numeric(candidate.get(metric))
    return {
        "baseline": base_value,
        "candidate": candidate_value,
        "delta": round(candidate_value - base_value, 6),
    }


def compare_runs(
    baseline_path: Path,
    candidate_path: Path,
    *,
    cost_tolerance_usd: float,
) -> tuple[int, dict[str, Any]]:
    baseline, baseline_error = load_json_required(baseline_path)
    candidate, candidate_error = load_json_required(candidate_path)
    load_errors = [error for error in (baseline_error, candidate_error) if error is not None]
    if load_errors or baseline is None or candidate is None:
        return INVALID_REQUEST, {
            "ok": False,
            "action": "eval_compare",
            "changed": False,
            "read_only": True,
            "errors": load_errors,
            "warnings": [],
        }
    schema_errors = validate_run_payload(baseline) + validate_run_payload(candidate)
    if schema_errors:
        return VALIDATION_FAILED, {
            "ok": False,
            "action": "eval_compare",
            "changed": False,
            "read_only": True,
            "errors": schema_errors,
            "warnings": [],
        }
    baseline_metrics = baseline.get("metrics") if isinstance(baseline.get("metrics"), dict) else {}
    candidate_metrics = candidate.get("metrics") if isinstance(candidate.get("metrics"), dict) else {}
    deltas = {
        metric: metric_delta(baseline_metrics, candidate_metrics, metric)
        for metric in sorted(HIGHER_IS_BETTER | LOWER_IS_BETTER | {"reviewer_disagreement_rate"})
    }
    failures: list[dict[str, Any]] = []
    if candidate.get("status") != "pass":
        failures.append(issue("candidate_eval_failed", "candidate eval run did not pass deterministic graders"))
    for metric in HIGHER_IS_BETTER:
        if numeric(candidate_metrics.get(metric)) < numeric(baseline_metrics.get(metric)):
            failures.append(issue("metric_regressed", "candidate metric is lower than baseline", metric=metric, **deltas[metric]))
    for metric in LOWER_IS_BETTER:
        tolerance = cost_tolerance_usd if metric == "cost_per_accepted_report_usd" else 0.0
        if numeric(candidate_metrics.get(metric)) > numeric(baseline_metrics.get(metric)) + tolerance:
            failures.append(issue("metric_regressed", "candidate metric is higher than baseline", metric=metric, **deltas[metric]))
    residual_risks = [
        "reviewer disagreement is reported but not automatically optimized away",
        "expert preference win rate requires human-calibrated paired review data",
    ]
    report = {
        "ok": not failures,
        "action": "eval_compare",
        "verdict": "pass" if not failures else "fail",
        "baseline_run_id": baseline.get("run_id"),
        "candidate_run_id": candidate.get("run_id"),
        "baseline_path": str(baseline_path),
        "candidate_path": str(candidate_path),
        "changed": False,
        "read_only": True,
        "metric_deltas": deltas,
        "release_policy": {
            "baseline_required": True,
            "regressions_block_release": True,
            "cost_tolerance_usd": cost_tolerance_usd,
            "status": "pass" if not failures else "blocked",
        },
        "errors": failures,
        "warnings": [],
        "residual_risks": residual_risks,
    }
    return (SUCCESS if not failures else VALIDATION_FAILED), report


def compare_command(args: argparse.Namespace) -> int:
    code, payload = compare_runs(args.baseline, args.candidate, cost_tolerance_usd=args.cost_tolerance_usd)
    print_json(payload)
    return code


def newest_payload(paths: list[Path], framework_version: str) -> tuple[Path | None, dict[str, Any] | None]:
    rows: list[tuple[str, Path, dict[str, Any]]] = []
    for path in paths:
        payload = load_json_optional(path)
        if not isinstance(payload, dict) or payload.get("framework_version") != framework_version:
            continue
        timestamp = str(payload.get("evaluated_at") or payload.get("built_at") or "")
        rows.append((timestamp, path, payload))
    if not rows:
        return None, None
    rows.sort(key=lambda item: (item[0], str(item[1])))
    _, path, payload = rows[-1]
    return path, payload


def empty_metrics() -> dict[str, Any]:
    return aggregate_metrics([])


def evals_snapshot(ops_dir: Path) -> dict[str, Any]:
    evals_dir = ops_dir / EVALS_DIR
    suite_paths = sorted(path for path in evals_dir.glob("*.json") if path.is_file()) if evals_dir.is_dir() else []
    run_paths = sorted(path for path in (ops_dir / RUNS_DIR).glob("*.json") if path.is_file()) if (ops_dir / RUNS_DIR).is_dir() else []
    latest_suite_path, latest_suite = newest_payload(suite_paths, SUITE_FRAMEWORK_VERSION)
    latest_run_path, latest_run = newest_payload(run_paths, RUN_FRAMEWORK_VERSION)
    metrics = (
        latest_run.get("metrics")
        if isinstance(latest_run, dict) and isinstance(latest_run.get("metrics"), dict)
        else latest_suite.get("metrics")
        if isinstance(latest_suite, dict) and isinstance(latest_suite.get("metrics"), dict)
        else empty_metrics()
    )
    return {
        "available": True,
        "status": "available" if latest_suite else "empty",
        "ok": latest_run.get("status") == "pass" if isinstance(latest_run, dict) else True,
        "read_only": True,
        "changed": False,
        "suite_count": len(suite_paths),
        "run_count": len(run_paths),
        "latest_suite": {
            "suite_id": latest_suite.get("suite_id") if isinstance(latest_suite, dict) else None,
            "path": str(latest_suite_path) if latest_suite_path else None,
            "case_count": latest_suite.get("case_count") if isinstance(latest_suite, dict) else 0,
            "built_at": latest_suite.get("built_at") if isinstance(latest_suite, dict) else None,
        },
        "latest_run": {
            "run_id": latest_run.get("run_id") if isinstance(latest_run, dict) else None,
            "path": str(latest_run_path) if latest_run_path else None,
            "status": latest_run.get("status") if isinstance(latest_run, dict) else None,
            "evaluated_at": latest_run.get("evaluated_at") if isinstance(latest_run, dict) else None,
        },
        "metrics": metrics,
        "release_policy": {
            "baseline_required": True,
            "regressions_block_release": True,
            "quality_claims_require_eval_evidence": True,
        },
        "warnings": [],
        "errors": latest_run.get("errors", [])[:5] if isinstance(latest_run, dict) and isinstance(latest_run.get("errors"), list) else [],
        "recovery_commands": [
            {
                "label": "Build eval suite",
                "command": ["async-research", "eval", "build-from-traces", str(ops_dir), "--write"],
            },
            {
                "label": "Run latest eval suite",
                "command": ["async-research", "eval", "run", str(latest_suite_path or ops_dir / EVALS_DIR / "runtime-trace-suite.json"), "--write"],
            },
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build, run, and compare trace-driven runtime eval suites.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build-from-traces", help="Build an eval suite from runtime traces and evidence.")
    build.add_argument("ops_dir", type=Path, help="Path to the research_ops workspace.")
    build.add_argument("--suite-id", default="runtime-trace-suite", help="Stable eval suite id.")
    build.add_argument("--output", type=Path, help="Output JSON path under research_ops/evals.")
    build.add_argument("--write", action="store_true", help="Write the suite JSON under research_ops/evals.")
    build.add_argument("--now", help="Override built_at timestamp for deterministic fixtures.")
    build.add_argument("--runtime-policy", default="runtime_policy_v1.0", help="Runtime policy label recorded in the suite.")
    build.add_argument("--model-routing-policy", default="model_routing_unset", help="Model-routing policy label recorded in the suite.")
    build.set_defaults(func=build_from_traces_command)

    run = subparsers.add_parser("run", help="Run deterministic graders for one eval suite.")
    run.add_argument("eval_suite", type=Path, help="Eval suite JSON file.")
    run.add_argument("--run-id", help="Stable run id for deterministic fixtures.")
    run.add_argument("--output", type=Path, help="Output JSON path under research_ops/evals/runs.")
    run.add_argument("--write", action="store_true", help="Write the eval run JSON under research_ops/evals/runs.")
    run.add_argument("--now", help="Override evaluated_at timestamp for deterministic fixtures.")
    run.set_defaults(func=run_suite_command)

    compare = subparsers.add_parser("compare", help="Compare a candidate eval run against a baseline run.")
    compare.add_argument("baseline", type=Path, help="Baseline eval run JSON.")
    compare.add_argument("candidate", type=Path, help="Candidate eval run JSON.")
    compare.add_argument("--cost-tolerance-usd", type=float, default=0.0, help="Allowed cost-per-accepted-report increase.")
    compare.set_defaults(func=compare_command)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv or []))
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
