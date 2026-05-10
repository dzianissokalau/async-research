#!/usr/bin/env python3
"""Validate result_acceptance_v1.0 records for reviewed tasks."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from async_research_workflow.resources import schema_path
from async_research_workflow.scripts.analysis_runs import (
    MANIFEST_RELATIVE_PATH,
    PreflightMalformed,
    workspace_path,
)
from async_research_workflow.scripts.data_foundations import data_foundation_report
from async_research_workflow.scripts.data_source_audit import (
    SOURCE_REF_PATTERN,
    assess_source_refs,
)
from async_research_workflow.scripts.update_accepted_outputs_index import (
    freshness_window_for,
    iso_date as accepted_iso_date,
    next_recheck_date,
    normalize_claim_type,
)
from async_research_workflow.scripts.validate_json_artifact import load_json, validate


SUCCESS = 0
VALIDATION_FAILED = 2
MALFORMED = 4

SCHEMA_VERSION = "1.0"
FRAMEWORK_VERSION = "result_acceptance_v1.0"
CLAIM_STRENGTH_POLICY = "result_acceptance_v1.0_claim_caps"
ACCEPTANCE_SCHEMA = schema_path("result_acceptance.schema.json")
CLAIM_ORDER = {"none": 0, "weak": 1, "suggestive": 2, "moderate": 3, "strong": 4}
CLAIM_BY_SCORE = {score: claim for claim, score in CLAIM_ORDER.items()}
RESULT_TASK_TYPES = {"run_analysis", "evaluate_results"}
ANALYSIS_ARTIFACT_FILENAMES = {
    "metrics": "metrics.json",
    "diagnostics": "diagnostics.json",
    "robustness": "robustness_checks.json",
    "claim_gates": "claim_gates.json",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def load_json_optional(path: Path) -> Optional[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def load_status(task_dir: Path) -> dict[str, Any]:
    payload = load_json(task_dir / "status.json")
    if not isinstance(payload, dict):
        raise ValueError(f"status file is not an object: {task_dir / 'status.json'}")
    return payload


def extract_json_objects(text: str) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    for match in re.finditer(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE):
        candidate = match.group(1).strip()
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            objects.append(payload)
    return objects


def looks_like_result_summary(payload: dict[str, Any]) -> bool:
    if payload.get("framework_version") == FRAMEWORK_VERSION:
        return True
    result_keys = {
        "result_id",
        "run_id",
        "primary_metric",
        "baseline_results",
        "candidate_results",
        "validation_split_results",
        "robustness_results",
        "leakage_check_results",
        "claim_strength",
        "recommended_decision",
    }
    return len(result_keys & set(payload)) >= 4


def load_result_summary(task_dir: Path) -> Optional[dict[str, Any]]:
    artifact_summary = load_json_optional(task_dir / "artifacts" / "result_summary.json")
    if artifact_summary and looks_like_result_summary(artifact_summary):
        return artifact_summary
    worker_output = task_dir / "worker_output.md"
    if not worker_output.exists():
        return None
    for payload in extract_json_objects(worker_output.read_text(encoding="utf-8")):
        if looks_like_result_summary(payload):
            return payload
    return None


def first_summary_line(task_dir: Path) -> str:
    worker_output = task_dir / "worker_output.md"
    if not worker_output.exists():
        return ""
    in_code = False
    for raw in worker_output.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code or not line or line.startswith("#") or line.startswith("|"):
            continue
        if set(line) <= {"-", " "}:
            continue
        return re.sub(r"^[-*]\s+", "", line)
    return ""


def extract_source_refs_from_payload(value: Any) -> list[str]:
    refs: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"source_id", "source_ids", "data_audit_refs", "required_data"}:
                refs.update(SOURCE_REF_PATTERN.findall(str(item)))
            refs.update(extract_source_refs_from_payload(item))
    elif isinstance(value, list):
        for item in value:
            refs.update(extract_source_refs_from_payload(item))
    elif isinstance(value, str):
        refs.update(SOURCE_REF_PATTERN.findall(value))
    return sorted(refs)


def audited_source_refs(task_dir: Path, status: dict[str, Any], summary: Optional[dict[str, Any]]) -> list[str]:
    refs: set[str] = set()
    data_audit_refs = status.get("data_audit_refs")
    if isinstance(data_audit_refs, list):
        refs.update(str(item) for item in data_audit_refs if isinstance(item, str) and SOURCE_REF_PATTERN.match(item))
    result = status.get("result")
    if isinstance(result, dict):
        refs.update(extract_source_refs_from_payload(result))
    if isinstance(summary, dict):
        refs.update(extract_source_refs_from_payload(summary))
    worker_output = task_dir / "worker_output.md"
    if worker_output.exists():
        refs.update(SOURCE_REF_PATTERN.findall(worker_output.read_text(encoding="utf-8")))
    return sorted(refs)


def markdown_escape(value: Any) -> str:
    text = str(value if value is not None else "").replace("\n", " ").strip()
    text = re.sub(r"\s+", " ", text)
    return text.replace("|", "\\|") or "none"


def upsert_markdown_row(path: Path, header: list[str], row: dict[str, Any], key: str = "task_id") -> None:
    existing: list[str] = []
    if path.exists():
        existing = path.read_text(encoding="utf-8").splitlines()
    data_lines = [line for line in existing if line.strip().startswith("|") and "---" not in line]
    rows: list[list[str]] = []
    existing_header: list[str] = header
    for line in data_lines:
        cells = [cell.strip().replace("\\|", "|") for cell in line.strip().strip("|").split("|")]
        normalized = [cell.lower() for cell in cells]
        if normalized == header:
            existing_header = normalized
            continue
        if not rows and len(cells) >= 2 and any(cell in normalized for cell in ("task_id", "result_id", "date")):
            existing_header = normalized
            continue
        if len(cells) == len(header):
            rows.append(cells)
        elif len(cells) == len(existing_header):
            mapped = {column: value for column, value in zip(existing_header, cells)}
            rows.append([mapped.get(column, "") for column in header])
    key_index = header.index(key)
    row_cells = [markdown_escape(row.get(column, "")) for column in header]
    replaced = False
    for index, cells in enumerate(rows):
        if cells[key_index] == str(row[key]):
            rows[index] = row_cells
            replaced = True
            break
    if not replaced:
        rows.append(row_cells)
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    lines.extend("| " + " | ".join(cells) + " |" for cells in rows)
    atomic_write_text(path, "\n".join(lines) + "\n")


def infer_ops_dir(task_dir: Path) -> Optional[Path]:
    if task_dir.parent.name == "tasks":
        return task_dir.parent.parent
    for parent in task_dir.parents:
        if parent.name == "research_ops":
            return parent
    return None


def result_value(status: dict[str, Any], key: str) -> Any:
    result = status.get("result")
    if isinstance(result, dict):
        return result.get(key)
    return None


def nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def nonempty_list(value: Any) -> bool:
    return isinstance(value, list) and any(str(item).strip() for item in value)


def normalize_followup(item: Any, default_priority: int = 3) -> Optional[dict[str, Any]]:
    if isinstance(item, dict):
        reason = str(item.get("reason") or item.get("task") or item.get("description") or "").strip()
        if not reason:
            return None
        priority = item.get("priority") if isinstance(item.get("priority"), int) else default_priority
        return {
            "reason": reason,
            "required_artifact": str(item.get("required_artifact") or "unspecified"),
            "priority": max(1, min(5, priority)),
            "human_approval_needed": item.get("human_approval_needed") is True,
            "required_before_memo_use": item.get("required_before_memo_use") is True,
        }
    reason = str(item).strip()
    if not reason:
        return None
    return {
        "reason": reason,
        "required_artifact": "unspecified",
        "priority": default_priority,
        "human_approval_needed": False,
        "required_before_memo_use": False,
    }


def append_followups(target: list[dict[str, Any]], items: Any, default_priority: int = 3) -> None:
    if not isinstance(items, list):
        return
    seen = {followup["reason"].strip().lower() for followup in target}
    for item in items:
        followup = normalize_followup(item, default_priority=default_priority)
        if followup is None:
            continue
        key = followup["reason"].strip().lower()
        if key in seen:
            continue
        target.append(followup)
        seen.add(key)


def worker_output_followups(task_dir: Path) -> list[str]:
    path = task_dir / "worker_output.md"
    if not path.exists():
        return []
    followups: list[str] = []
    in_followups = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("#"):
            in_followups = "follow" in line.lower()
            continue
        if in_followups and line.startswith(("-", "*")):
            followups.append(re.sub(r"^[-*]\s+", "", line).strip())
    return [item for item in followups if item]


def claim_strength(status: dict[str, Any], aggregate: Optional[dict[str, Any]], summary: Optional[dict[str, Any]]) -> str:
    for value in (
        result_value(status, "claim_strength"),
        aggregate.get("aggregate_claim_strength") if isinstance(aggregate, dict) else None,
        summary.get("claim_strength") if isinstance(summary, dict) else None,
    ):
        if value in CLAIM_ORDER:
            return str(value)
    return "none"


def recommended_decision(status: dict[str, Any]) -> str:
    recommendation = result_value(status, "recommendation")
    if recommendation in {"ready", "usable_with_caveats", "needs_revision", "needs_human", "blocked", "reject"}:
        return str(recommendation)
    status_value = status.get("status")
    return {
        "accepted": "ready",
        "needs_revision": "needs_revision",
        "needs_human": "needs_human",
        "paused": "blocked",
        "rejected": "reject",
    }.get(str(status_value), "needs_human")


def route(status: dict[str, Any], summary: Optional[dict[str, Any]]) -> str:
    status_value = str(status.get("status"))
    if status_value == "accepted":
        if isinstance(summary, dict) and summary.get("recommended_decision") == "accept_negative_result":
            return "accept_negative_result"
        return "accept_as_evidence"
    if status_value == "needs_revision":
        return "needs_revision"
    if status_value == "needs_human":
        return "needs_human"
    if status_value == "paused":
        return "pause"
    if status_value == "rejected":
        return "reject"
    return "needs_human"


def add_gate(gates: list[dict[str, Any]], gate: str, passed: bool, reason: str) -> None:
    gates.append({"gate": gate, "passed": bool(passed), "reason": reason})


def summary_missing_fields(summary: dict[str, Any]) -> list[str]:
    required = [
        "result_id",
        "experiment_plan_id",
        "run_id",
        "run_manifest_path",
        "artifact_version",
        "dataset_versions",
        "primary_metric",
        "baseline_results",
        "candidate_results",
        "validation_split_results",
        "robustness_results",
        "leakage_check_results",
        "limitations",
        "claim",
        "claim_type",
        "claim_strength",
        "recommended_decision",
        "public_or_high_stakes",
        "follow_up_tasks",
    ]
    missing: list[str] = []
    empty_list_allowed = {"follow_up_tasks"}
    for field in required:
        value = summary.get(field)
        if isinstance(value, str) and not value.strip():
            missing.append(field)
        elif isinstance(value, list) and not value and field not in empty_list_allowed:
            missing.append(field)
        elif value is None:
            missing.append(field)
    return missing


def valid_analysis_run_manifest_path(value: Any) -> bool:
    return nonempty_string(value) and str(value).replace("\\", "/").endswith("/artifacts/analysis_run/run_manifest.json")


def canonical_path(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def ops_relative_path(ops_dir: Optional[Path], path: Optional[Path]) -> str:
    if path is None:
        return "none"
    if ops_dir is None:
        return path.as_posix()
    try:
        return path.relative_to(ops_dir.parent).as_posix()
    except ValueError:
        try:
            return path.relative_to(ops_dir).as_posix()
        except ValueError:
            return path.as_posix()


def parse_datetime_value(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.strptime(text[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def freshness_days(value: Any) -> Optional[int]:
    try:
        days = int(str(value))
    except (TypeError, ValueError):
        return None
    return days if days > 0 else None


def stale_artifact_triggers(
    *,
    accepted_date: str,
    freshness_window_days: str,
    manifest: Optional[dict[str, Any]],
    diagnostics: Optional[dict[str, Any]],
) -> list[dict[str, Any]]:
    days = freshness_days(freshness_window_days)
    accepted_at = parse_datetime_value(accepted_date)
    if days is None or accepted_at is None:
        return []
    cutoff = accepted_at - timedelta(days=days)
    triggers: list[dict[str, Any]] = []
    if isinstance(manifest, dict):
        for index, item in enumerate(manifest.get("data_versions", [])):
            if not isinstance(item, dict):
                continue
            accessed_at = parse_datetime_value(item.get("accessed_at"))
            if accessed_at is not None and accessed_at < cutoff:
                triggers.append(
                    {
                        "trigger": "stale_data_version",
                        "severity": "stale",
                        "field": f"data_versions[{index}].accessed_at",
                        "source_id": item.get("source_id"),
                        "accessed_at": item.get("accessed_at"),
                        "freshness_window_days": freshness_window_days,
                    }
                )
    if isinstance(diagnostics, dict):
        generated_at = parse_datetime_value(diagnostics.get("generated_at"))
        if generated_at is not None and generated_at < cutoff:
            triggers.append(
                {
                    "trigger": "stale_diagnostics",
                    "severity": "stale",
                    "field": "diagnostics.generated_at",
                    "generated_at": diagnostics.get("generated_at"),
                    "freshness_window_days": freshness_window_days,
                }
            )
    return triggers


def diagnostics_status_counts(diagnostics: Optional[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    if not isinstance(diagnostics, dict):
        return counts
    for value in diagnostics.values():
        if not isinstance(value, list):
            continue
        for item in value:
            if not isinstance(item, dict):
                continue
            status = str(item.get("status") or "").strip().lower()
            if status:
                counts[status] = counts.get(status, 0) + 1
    return counts


def diagnostic_review_triggers(diagnostics: Optional[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = diagnostics_status_counts(diagnostics)
    triggers: list[dict[str, Any]] = []
    if counts.get("fail", 0) > 0:
        triggers.append({"trigger": "diagnostics_failures_present", "severity": "manual_review", "count": counts["fail"]})
    if counts.get("warn", 0) > 0:
        triggers.append({"trigger": "diagnostics_warnings_present", "severity": "due", "count": counts["warn"]})
    return triggers


def revalidation_status_from_triggers(existing: Any, triggers: list[dict[str, Any]], freshness_window_days: str = "") -> str:
    explicit = str(existing or "current").strip().lower()
    if any(trigger.get("severity") == "stale" for trigger in triggers):
        return "stale"
    if any(trigger.get("severity") == "manual_review" for trigger in triggers):
        return "manual_review"
    if any(trigger.get("severity") == "due" for trigger in triggers):
        return "due"
    if freshness_window_days == "manual_review":
        return "manual_review"
    if explicit in {"", "current"}:
        return "current"
    return explicit or "current"


def resolve_analysis_manifest(
    task_dir: Path,
    ops_dir: Optional[Path],
    task_type: str,
    summary: Optional[dict[str, Any]],
) -> tuple[Optional[Path], Optional[Path], list[str]]:
    errors: list[str] = []
    if not isinstance(summary, dict):
        return None, None, ["structured result summary is absent"]
    manifest_value = summary.get("run_manifest_path")
    if not valid_analysis_run_manifest_path(manifest_value):
        return None, None, ["run_manifest_path must end in artifacts/analysis_run/run_manifest.json"]
    if task_type == "run_analysis":
        expected = task_dir / MANIFEST_RELATIVE_PATH
        resolved_manifest = workspace_path(ops_dir, manifest_value) if ops_dir is not None else Path(str(manifest_value))
        if resolved_manifest is None:
            errors.append("run_manifest_path could not be resolved")
        elif canonical_path(resolved_manifest) != canonical_path(expected):
            errors.append("run_analysis result summary must point to the same task's run manifest")
        return expected, task_dir, errors
    if ops_dir is None:
        return None, None, ["evaluate_results requires --ops-dir to resolve upstream run_manifest_path"]
    resolved_manifest = workspace_path(ops_dir, manifest_value)
    if resolved_manifest is None:
        return None, None, ["run_manifest_path could not be resolved"]
    if resolved_manifest.name != "run_manifest.json" or resolved_manifest.parent.name != "analysis_run":
        errors.append("run_manifest_path must point to an analysis_run/run_manifest.json artifact")
    try:
        analysis_task_dir = resolved_manifest.parents[2]
    except IndexError:
        analysis_task_dir = None
        errors.append("run_manifest_path does not include an upstream task directory")
    return resolved_manifest, analysis_task_dir, errors


def analysis_failure_reasons(failures: list[dict[str, Any]]) -> list[str]:
    reasons: list[str] = []
    for item in failures:
        reason = str(item.get("message") or item.get("reason") or item.get("gate") or "analysis validation failed")
        details = item.get("details")
        if details is not None:
            detail_text = json.dumps(details, sort_keys=True, default=str) if not isinstance(details, str) else details
            reason = f"{reason}: {detail_text}"
        reasons.append(reason)
    return reasons


def validate_analysis_run_for_acceptance(
    task_dir: Path,
    ops_dir: Optional[Path],
    summary: Optional[dict[str, Any]],
    task_type: str,
    *,
    required: bool,
    accepted_date: str,
    freshness_window_days: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    record: dict[str, Any] = {
        "required": required,
        "task_dir": "none",
        "run_manifest_path": "none",
        "run_id": None,
        "experiment_plan_id": None,
        "accepted_plan_task_id": None,
        "data_versions": [],
        "artifact_paths": {},
        "diagnostics": {"status_counts": {}},
        "claim_gates": {},
        "validation": {"ok": not required, "failure_count": 0, "warning_count": 0},
        "revalidation_triggers": [],
    }
    gates: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    manifest_path, analysis_task_dir, resolution_errors = resolve_analysis_manifest(task_dir, ops_dir, task_type, summary)
    if resolution_errors:
        failures.append({"gate": "analysis_run_manifest_path", "message": "; ".join(resolution_errors)})
    if analysis_task_dir is None or manifest_path is None:
        record["validation"] = {"ok": False, "failure_count": len(failures), "warning_count": 0}
        if required:
            add_gate(gates, "analysis_run_artifacts_valid", False, "; ".join(analysis_failure_reasons(failures)))
        return record, gates, warnings, failures

    record["task_dir"] = ops_relative_path(ops_dir, analysis_task_dir)
    record["run_manifest_path"] = ops_relative_path(ops_dir, manifest_path)
    record["artifact_paths"] = {
        name: ops_relative_path(ops_dir, analysis_task_dir / "artifacts" / "analysis_run" / filename)
        for name, filename in ANALYSIS_ARTIFACT_FILENAMES.items()
    }

    if ops_dir is None:
        failures.append({"gate": "analysis_ops_dir", "message": "analysis artifact validation requires --ops-dir"})
    else:
        from async_research_workflow.scripts import analysis_validation

        report, context = analysis_validation.validate_common(
            analysis_task_dir,
            ops_dir,
            None,
            "result_acceptance_analysis_validation",
        )
        failures.extend(report.get("hard_gate_failures", []))
        warnings.extend(report.get("warnings", []))
        if context is not None:
            manifest = context["manifest"]
            record.update(
                {
                    "run_id": manifest.get("run_id"),
                    "experiment_plan_id": manifest.get("experiment_plan_id"),
                    "accepted_plan_task_id": manifest.get("accepted_plan_task_id"),
                    "data_versions": manifest.get("data_versions") if isinstance(manifest.get("data_versions"), list) else [],
                }
            )
            try:
                outputs = analysis_validation.load_structured_outputs(
                    analysis_task_dir,
                    manifest,
                    failures,
                )
                analysis_validation.validate_required_output_files(ops_dir, manifest, failures)
                analysis_validation.validate_metrics_against_plan(outputs.get("metrics"), manifest, context.get("plan"), failures)
                analysis_validation.validate_robustness_semantics(
                    outputs.get("robustness"),
                    context.get("plan"),
                    failures,
                    warnings,
                )
                if isinstance(summary, dict):
                    analysis_validation.validate_summary_identity(summary, manifest, failures, warnings)
                    analysis_validation.validate_summary_substance(
                        ops_dir,
                        analysis_task_dir,
                        summary,
                        manifest,
                        outputs.get("metrics"),
                        failures,
                    )
                    record["claim_gates"] = analysis_validation.validate_claim_gates(
                        analysis_task_dir,
                        manifest,
                        summary,
                        outputs,
                        failures,
                        warnings,
                    )
                diagnostics = outputs.get("diagnostics")
                record["diagnostics"] = {
                    "path": record["artifact_paths"].get("diagnostics", "none"),
                    "generated_at": diagnostics.get("generated_at") if isinstance(diagnostics, dict) else None,
                    "status_counts": diagnostics_status_counts(diagnostics),
                }
                record["revalidation_triggers"] = stale_artifact_triggers(
                    accepted_date=accepted_date,
                    freshness_window_days=freshness_window_days,
                    manifest=manifest,
                    diagnostics=diagnostics,
                ) + diagnostic_review_triggers(diagnostics)
            except PreflightMalformed as exc:
                failures.append({"gate": "analysis_artifacts_malformed", "message": str(exc)})

    record["validation"] = {
        "ok": not failures,
        "failure_count": len(failures),
        "warning_count": len(warnings),
    }
    reason = "analysis run artifacts pass result acceptance validation" if not failures else "; ".join(analysis_failure_reasons(failures))
    if required:
        add_gate(gates, "analysis_run_artifacts_valid", not failures, reason)
    return record, gates, warnings, failures


def analysis_claim_gate_summary(analysis_run: Optional[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(analysis_run, dict):
        return {}
    claim_gates = analysis_run.get("claim_gates") if isinstance(analysis_run.get("claim_gates"), dict) else {}
    computed = claim_gates.get("computed") if isinstance(claim_gates.get("computed"), dict) else None
    artifact = claim_gates.get("artifact") if isinstance(claim_gates.get("artifact"), dict) else None
    return computed or artifact or {}


def cap_claim_strength(
    summary: Optional[dict[str, Any]],
    aggregate: Optional[dict[str, Any]],
    task_type: str = "",
    analysis_run: Optional[dict[str, Any]] = None,
) -> tuple[str, list[str]]:
    cap = CLAIM_ORDER["strong"]
    reasons: list[str] = []

    if not isinstance(summary, dict):
        cap = min(cap, CLAIM_ORDER["suggestive"])
        reasons.append("structured result summary absent; generic artifacts cap at suggestive")
    else:
        if task_type in RESULT_TASK_TYPES:
            if not nonempty_string(summary.get("run_id")) or not valid_analysis_run_manifest_path(summary.get("run_manifest_path")):
                cap = min(cap, CLAIM_ORDER["none"])
                reasons.append("result task lacks a reproducible analysis run manifest path")
        elif not nonempty_string(summary.get("run_id")) or not (
            nonempty_string(summary.get("run_manifest_path")) or nonempty_string(summary.get("artifact_version"))
        ):
            cap = min(cap, CLAIM_ORDER["none"])
            reasons.append("no reproducible run manifest or artifact version")
        if not nonempty_string(summary.get("baseline_results")):
            cap = min(cap, CLAIM_ORDER["weak"])
            reasons.append("baseline comparison absent")
        if not nonempty_list(summary.get("leakage_check_results")):
            cap = min(cap, CLAIM_ORDER["weak"])
            reasons.append("leakage checks absent")
        if not nonempty_list(summary.get("robustness_results")):
            cap = min(cap, CLAIM_ORDER["suggestive"])
            reasons.append("robustness checks absent")
        claim_type = str(summary.get("claim_type", "")).lower()
        if claim_type == "predictive":
            cap = min(cap, CLAIM_ORDER["moderate"])
            reasons.append("predictive validation caps claim at moderate")
        if claim_type == "causal" and not nonempty_list(summary.get("identification_tests")):
            cap = min(cap, CLAIM_ORDER["weak"])
            reasons.append("causal claim lacks identification tests")

    if isinstance(aggregate, dict):
        decisions = {
            review.get("decision")
            for review in aggregate.get("reviews", [])
            if isinstance(review, dict) and isinstance(review.get("decision"), str)
        }
        if len(decisions) > 1:
            cap = min(cap, CLAIM_ORDER["suggestive"])
            reasons.append("reviewer decisions differ; unresolved disagreement caps claim at suggestive")

    claim_gate = analysis_claim_gate_summary(analysis_run)
    gate_cap = claim_gate.get("max_claim_strength")
    gate_decision = claim_gate.get("claim_decision")
    if gate_cap in CLAIM_ORDER:
        cap = min(cap, CLAIM_ORDER[str(gate_cap)])
        if gate_cap != "strong":
            reasons.append(f"analysis claim gates cap claim at {gate_cap}")
    if gate_decision in {"rejected", "needs_human"}:
        cap = min(cap, CLAIM_ORDER["none"])
        reasons.append(f"analysis claim gates decision is {gate_decision}")

    return CLAIM_BY_SCORE[cap], reasons


def human_gate_status(status: dict[str, Any], summary: Optional[dict[str, Any]], claim: str) -> tuple[bool, bool, str]:
    public_or_high_stakes = isinstance(summary, dict) and summary.get("public_or_high_stakes") is True
    strong_claim = claim == "strong"
    required = public_or_high_stakes or strong_claim
    result = status.get("result") if isinstance(status.get("result"), dict) else {}
    satisfied = bool(
        (isinstance(summary, dict) and summary.get("human_approval_present") is True)
        or status.get("human_approval_present") is True
        or result.get("human_approval_present") is True
        or nonempty_string(result.get("human_approval_id"))
    )
    if not required:
        return False, True, "not required"
    if satisfied:
        return True, True, "human approval recorded"
    if public_or_high_stakes:
        return True, False, "public or high-stakes use requires human approval"
    return True, False, "strong claim requires human approval"


def evidence_link(ops_dir: Optional[Path], task_dir: Path, status: dict[str, Any]) -> str:
    link = result_value(status, "evidence_link")
    if nonempty_string(link):
        return str(link)
    worker_output = task_dir / "worker_output.md"
    target = worker_output if worker_output.exists() else task_dir
    if ops_dir is not None:
        try:
            return target.relative_to(ops_dir).as_posix()
        except ValueError:
            return target.as_posix()
    return target.as_posix()


def followups(
    status: dict[str, Any],
    summary: Optional[dict[str, Any]],
    aggregate: Optional[dict[str, Any]],
    task_dir: Path,
) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    if isinstance(summary, dict):
        append_followups(parsed, summary.get("follow_up_tasks"))
        if parsed:
            return parsed
    append_followups(parsed, result_value(status, "followups"))
    if parsed:
        return parsed
    if isinstance(aggregate, dict):
        for review in aggregate.get("reviews", []):
            if isinstance(review, dict):
                append_followups(parsed, review.get("required_followups"))
    append_followups(parsed, worker_output_followups(task_dir))

    followup_count = result_value(status, "followup_count")
    if not parsed and isinstance(followup_count, int) and followup_count > 0:
        append_followups(parsed, [f"{followup_count} follow-ups proposed; inspect worker_output.md for details."])
    return parsed


def scorecard(task_type: str, summary: Optional[dict[str, Any]], claim: str, cap: str, worker_output_present: bool) -> dict[str, int]:
    is_result_task = task_type in RESULT_TASK_TYPES
    has_summary = isinstance(summary, dict)
    return {
        "plan_compliance": 5 if not is_result_task or (has_summary and nonempty_string(summary.get("experiment_plan_id"))) else 1,
        "reproducibility": 5 if has_summary and nonempty_string(summary.get("run_id")) and (valid_analysis_run_manifest_path(summary.get("run_manifest_path")) if is_result_task else (nonempty_string(summary.get("run_manifest_path")) or nonempty_string(summary.get("artifact_version")))) else (3 if worker_output_present else 1),
        "baseline_comparison": 5 if has_summary and nonempty_string(summary.get("baseline_results")) else (3 if not is_result_task else 1),
        "metric_validity": 5 if has_summary and nonempty_string(summary.get("primary_metric")) else (3 if not is_result_task else 2),
        "validation_strength": 5 if has_summary and nonempty_string(summary.get("validation_split_results")) else (3 if not is_result_task else 2),
        "robustness_strength": 5 if has_summary and nonempty_list(summary.get("robustness_results")) else (3 if not is_result_task else 2),
        "leakage_safety": 5 if has_summary and nonempty_list(summary.get("leakage_check_results")) else (3 if not is_result_task else 1),
        "limitation_honesty": 5 if has_summary and nonempty_list(summary.get("limitations")) else (3 if not is_result_task else 2),
        "decision_usefulness": 4 if worker_output_present else 1,
        "claim_discipline": 5 if CLAIM_ORDER[claim] <= CLAIM_ORDER[cap] else 1,
    }


def aggregate_summary(aggregate: Optional[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(aggregate, dict):
        return {
            "aggregate_present": False,
            "aggregate_decision": None,
            "tier": None,
            "required_reviewers": [],
            "reviewer_count": 0,
            "disagreement_present": False,
        }
    disagreements = aggregate.get("disagreements")
    disagreement_present = isinstance(disagreements, list) and any(str(item).strip().lower() != "none" for item in disagreements)
    return {
        "aggregate_present": True,
        "aggregate_decision": aggregate.get("aggregate_decision"),
        "tier": aggregate.get("tier"),
        "required_reviewers": aggregate.get("required_reviewers") if isinstance(aggregate.get("required_reviewers"), list) else [],
        "reviewer_count": len(aggregate.get("reviews", [])) if isinstance(aggregate.get("reviews"), list) else 0,
        "disagreement_present": disagreement_present,
    }


def schema_errors(payload: dict[str, Any]) -> list[dict[str, str]]:
    schema = load_json(ACCEPTANCE_SCHEMA)
    if not isinstance(schema, dict):
        return [{"path": "$", "message": f"schema is not an object: {ACCEPTANCE_SCHEMA}"}]
    return [error.to_dict() for error in validate(payload, schema)]


def build_acceptance_record(
    task_dir: Path,
    status: dict[str, Any],
    aggregate: Optional[dict[str, Any]],
    ops_dir: Optional[Path],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    summary = load_result_summary(task_dir)
    task_type = str(status.get("type", "admin"))
    current_route = route(status, summary)
    claim = claim_strength(status, aggregate, summary)
    result = status.get("result") if isinstance(status.get("result"), dict) else {}
    preliminary_claim_type_value = (
        summary.get("claim_type")
        if task_type in RESULT_TASK_TYPES and isinstance(summary, dict) and nonempty_string(summary.get("claim_type"))
        else result.get("claim_type") or result.get("memory_claim_type")
    )
    preliminary_claim_type = normalize_claim_type(preliminary_claim_type_value, task_type)
    accepted_date = accepted_iso_date(result.get("accepted_date") or status.get("updated_at") or status.get("created_at"))
    preliminary_freshness_window = freshness_window_for(
        preliminary_claim_type,
        result.get("freshness_window_days") or result.get("freshness_window"),
    )
    worker_output_present = (task_dir / "worker_output.md").exists() and bool((task_dir / "worker_output.md").read_text(encoding="utf-8").strip())
    gates: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    accepted = current_route in {"accept_as_evidence", "accept_negative_result"}
    rejected = current_route == "reject"
    analysis_run: Optional[dict[str, Any]] = None
    analysis_failures: list[dict[str, Any]] = []
    if task_type in RESULT_TASK_TYPES and (accepted or rejected or isinstance(summary, dict)):
        analysis_run, analysis_gates, analysis_warnings, analysis_failures = validate_analysis_run_for_acceptance(
            task_dir,
            ops_dir,
            summary,
            task_type,
            required=accepted,
            accepted_date=accepted_date,
            freshness_window_days=preliminary_freshness_window,
        )
        gates.extend(analysis_gates)
        if accepted:
            warnings.extend(
                {"gate": warning.get("gate", "analysis_validation"), "message": warning.get("message", str(warning))}
                for warning in analysis_warnings
            )
        elif analysis_warnings:
            warnings.extend(
                {"gate": "analysis_validation_optional", "message": warning.get("message", str(warning))}
                for warning in analysis_warnings
            )
        if not accepted and analysis_failures:
            warnings.extend(
                {"gate": "analysis_validation_optional", "message": reason}
                for reason in analysis_failure_reasons(analysis_failures)
            )
    cap, cap_reasons = cap_claim_strength(summary, aggregate, task_type, analysis_run)

    worker_output_reason = "worker_output.md exists and is non-empty" if worker_output_present else "accepted evidence requires worker_output.md"
    if not accepted:
        worker_output_reason = "not required for non-accepted route"
    add_gate(gates, "worker_output_present", not accepted or worker_output_present, worker_output_reason)
    aggregate_reason = "review aggregate present" if isinstance(aggregate, dict) else "accepted evidence requires review aggregate"
    if not accepted:
        aggregate_reason = "not required for non-accepted route"
    add_gate(gates, "review_aggregate_present", not accepted or isinstance(aggregate, dict), aggregate_reason)
    if accepted and isinstance(aggregate, dict):
        add_gate(
            gates,
            "aggregate_accepts",
            aggregate.get("aggregate_decision") == "accepted",
            f"aggregate decision is {aggregate.get('aggregate_decision')}",
        )
    if accepted:
        stale = result_value(status, "claim_strength_stale") is True or result_value(status, "claim_strength_revalidation_required") is True
        add_gate(gates, "claim_strength_current", not stale and claim in CLAIM_ORDER, "claim strength is current" if not stale else "claim strength is stale")
        add_gate(
            gates,
            "claim_strength_cap",
            CLAIM_ORDER[claim] <= CLAIM_ORDER[cap],
            f"claim {claim} <= cap {cap}" if CLAIM_ORDER[claim] <= CLAIM_ORDER[cap] else f"claim {claim} exceeds cap {cap}: {'; '.join(cap_reasons)}",
        )
        key_finding = result_value(status, "key_finding")
        if not nonempty_string(key_finding) and isinstance(summary, dict):
            key_finding = summary.get("claim")
        if not nonempty_string(key_finding):
            key_finding = first_summary_line(task_dir)
        add_gate(gates, "key_finding_present", nonempty_string(key_finding), "key finding available" if nonempty_string(key_finding) else "accepted evidence requires a key finding")
        add_gate(gates, "evidence_link_present", nonempty_string(evidence_link(ops_dir, task_dir, status)), "evidence link available")

    if task_type in RESULT_TASK_TYPES and accepted:
        add_gate(gates, "result_summary_present", isinstance(summary, dict), "structured result summary present" if isinstance(summary, dict) else "result tasks require structured result summary")
        if isinstance(summary, dict):
            missing = summary_missing_fields(summary)
            add_gate(gates, "result_summary_required_fields", not missing, "required result summary fields present" if not missing else f"missing fields: {', '.join(missing)}")
            add_gate(
                gates,
                "run_manifest_path_points_to_analysis_run_manifest",
                valid_analysis_run_manifest_path(summary.get("run_manifest_path")),
                "run manifest path points to artifacts/analysis_run/run_manifest.json"
                if valid_analysis_run_manifest_path(summary.get("run_manifest_path"))
                else "result tasks require run_manifest_path ending in artifacts/analysis_run/run_manifest.json",
            )
            add_gate(gates, "baseline_comparison_present", nonempty_string(summary.get("baseline_results")), "baseline comparison present")
            add_gate(gates, "leakage_checks_present", nonempty_list(summary.get("leakage_check_results")), "leakage checks present")
            add_gate(gates, "robustness_checks_present", nonempty_list(summary.get("robustness_results")), "robustness checks present")
            failed_robustness = any("fail" in str(item).lower() for item in summary.get("robustness_results", []))
            limitations_text = " ".join(str(item).lower() for item in summary.get("limitations", []))
            add_gate(
                gates,
                "failed_robustness_disclosed",
                not failed_robustness or "fail" in limitations_text or "robust" in limitations_text,
                "failed robustness checks are disclosed" if failed_robustness else "no failed robustness checks detected",
            )

    source_ids = audited_source_refs(task_dir, status, summary)
    source_governance: dict[str, Any] = {
        "required": accepted and bool(source_ids),
        "source_ids": source_ids,
        "ok": True,
        "warnings": [],
        "blocked": [],
    }
    if accepted and source_ids:
        assessed = assess_source_refs(
            ops_dir,
            source_ids,
            use_case="accepted_evidence",
            claim_impact="high" if claim == "strong" else "medium",
        )
        source_governance.update(
            {
                "ok": assessed.get("ok") is True,
                "warnings": assessed.get("warnings", []),
                "blocked": assessed.get("blocked", []),
                "source_decisions": assessed.get("source_decisions", []),
                "audit_register": assessed.get("audit_register"),
            }
        )
        data_foundations = data_foundation_report(ops_dir)
        source_governance["data_foundations"] = data_foundations
        add_gate(
            gates,
            "audited_sources_cited",
            bool(source_ids),
            f"accepted evidence cites audited sources: {', '.join(source_ids)}",
        )
        add_gate(
            gates,
            "source_governance_allowed",
            assessed.get("ok") is True,
            "source governance allows accepted evidence" if assessed.get("ok") is True else "source governance blocks accepted evidence",
        )
        add_gate(
            gates,
            "data_foundations_valid",
            data_foundations.get("error_count", 0) == 0,
            "data foundation validator has no error-level findings"
            if data_foundations.get("error_count", 0) == 0
            else "data foundation validator blocks accepted evidence until malformed data files are repaired",
        )
    elif accepted:
        add_gate(
            gates,
            "audited_sources_cited",
            True,
            "no DS-* source dependency detected for this accepted output",
        )

    analysis_claim_type = analysis_claim_gate_summary(analysis_run).get("claim_type")
    summary_claim_type = summary.get("claim_type") if isinstance(summary, dict) else None
    memory_claim_type_value = result.get("claim_type") or result.get("memory_claim_type")
    if task_type in RESULT_TASK_TYPES:
        memory_claim_type_value = analysis_claim_type or summary_claim_type or memory_claim_type_value
    memory_claim_type = normalize_claim_type(memory_claim_type_value, task_type)
    freshness_window = freshness_window_for(memory_claim_type, result.get("freshness_window_days") or result.get("freshness_window"))
    memory_next_recheck = next_recheck_date(accepted_date, freshness_window, result.get("next_recheck_date"))
    revalidation_triggers = analysis_run.get("revalidation_triggers", []) if isinstance(analysis_run, dict) else []
    memory_revalidation_status = revalidation_status_from_triggers(
        result.get("revalidation_status"),
        revalidation_triggers,
        freshness_window,
    )
    accepted_memory = {
        "claim_type": memory_claim_type,
        "freshness_window_days": freshness_window,
        "next_recheck_date": memory_next_recheck,
        "revalidation_status": memory_revalidation_status,
        "supersedes": (
            ", ".join(str(item) for item in result.get("supersedes", []) if str(item).strip()) or "none"
            if isinstance(result.get("supersedes"), list)
            else str(result.get("supersedes") or "none")
        ),
        "superseded_by": (
            ", ".join(str(item) for item in result.get("superseded_by", []) if str(item).strip()) or "none"
            if isinstance(result.get("superseded_by"), list)
            else str(result.get("superseded_by") or "none")
        ),
    }

    human_required, human_satisfied, human_reason = human_gate_status(status, summary, claim)
    if accepted:
        add_gate(gates, "human_gate", not human_required or human_satisfied, human_reason)
    if cap_reasons:
        warnings.extend({"gate": "claim_strength_cap", "message": reason} for reason in cap_reasons)
    if accepted and revalidation_triggers:
        warnings.extend(
            {
                "gate": "analysis_revalidation_trigger",
                "message": f"{trigger.get('trigger')} marks accepted empirical evidence {trigger.get('severity', 'due')}",
            }
            for trigger in revalidation_triggers
        )

    explicit_result_id = result_value(status, "result_id")
    result_id = (
        summary.get("result_id")
        if isinstance(summary, dict) and nonempty_string(summary.get("result_id"))
        else explicit_result_id
        if nonempty_string(explicit_result_id)
        else str(status.get("id", task_dir.name))
    )
    evidence = evidence_link(ops_dir, task_dir, status)
    review_notes = []
    if accepted:
        review_notes.append("Accepted evidence must cite result_acceptance.json and evidence_ledger.md.")
    if rejected:
        review_notes.append("Rejected result should be visible in rejected_results.md.")

    record = {
        "schema_version": SCHEMA_VERSION,
        "framework_version": FRAMEWORK_VERSION,
        "task_id": status.get("id", task_dir.name),
        "task_type": task_type,
        "evaluated_at": utc_now(),
        "route": current_route,
        "recommended_decision": recommended_decision(status),
        "claim_strength": claim,
        "max_claim_strength": cap,
        "claim_strength_policy": CLAIM_STRENGTH_POLICY,
        "hard_gate_results": gates,
        "scorecard": scorecard(task_type, summary, claim, cap, worker_output_present),
        "reviewer_panel": aggregate_summary(aggregate),
        "human_gate": {"required": human_required, "satisfied": human_satisfied, "reason": human_reason},
        "source_governance": source_governance,
        "accepted_memory": accepted_memory,
        "analysis_run": analysis_run,
        "evidence_ledger": {
            "required": accepted,
            "ledger_path": "research_ops/evidence_ledger.md",
            "logged": False,
            "evidence_link": evidence,
        },
        "rejection_logging": {
            "required": rejected,
            "log_path": "research_ops/rejected_results.md",
            "logged": False,
        },
        "followups": followups(status, summary, aggregate, task_dir),
        "review_notes": review_notes,
        "_ledger_payload": {
            "result_id": result_id,
            "claim": summary.get("claim") if isinstance(summary, dict) else (result_value(status, "key_finding") or first_summary_line(task_dir) or "accepted output"),
            "limitations": "; ".join(summary.get("limitations", [])) if isinstance(summary, dict) and isinstance(summary.get("limitations"), list) else "see evidence",
            "claim_type": accepted_memory.get("claim_type", "general"),
            "run_manifest_path": analysis_run.get("run_manifest_path", "none") if isinstance(analysis_run, dict) else "none",
            "diagnostics_path": (
                (analysis_run.get("diagnostics") or {}).get("path", "none")
                if isinstance(analysis_run, dict) and isinstance(analysis_run.get("diagnostics"), dict)
                else "none"
            ),
            "claim_gates_path": (
                (analysis_run.get("artifact_paths") or {}).get("claim_gates", "none")
                if isinstance(analysis_run, dict) and isinstance(analysis_run.get("artifact_paths"), dict)
                else "none"
            ),
            "revalidation_triggers": "; ".join(
                str(trigger.get("trigger"))
                for trigger in revalidation_triggers
                if isinstance(trigger, dict) and trigger.get("trigger")
            )
            or "none",
        },
    }

    failures = [gate for gate in gates if gate.get("passed") is not True]
    failures.extend({"gate": "schema", "passed": False, "reason": error["message"], "path": error["path"]} for error in schema_errors({key: value for key, value in record.items() if not key.startswith("_")}))
    return record, failures, warnings


def update_ledgers(ops_dir: Path, record: dict[str, Any]) -> None:
    task_id = str(record["task_id"])
    ledger_payload = record.get("_ledger_payload") if isinstance(record.get("_ledger_payload"), dict) else {}
    followup_text = "; ".join(item["reason"] for item in record.get("followups", [])) or "none"
    if record["route"] in {"accept_as_evidence", "accept_negative_result"}:
        source_ids = ", ".join(record.get("source_governance", {}).get("source_ids", [])) or "none"
        accepted_memory = record.get("accepted_memory") if isinstance(record.get("accepted_memory"), dict) else {}
        upsert_markdown_row(
            ops_dir / "evidence_ledger.md",
            [
                "date",
                "task_id",
                "result_id",
                "claim_type",
                "claim_strength",
                "source_ids",
                "revalidation_status",
                "revalidation_triggers",
                "supersedes",
                "superseded_by",
                "run_manifest_path",
                "diagnostics_path",
                "claim_gates_path",
                "claim",
                "evidence_link",
                "limitations",
                "followups",
            ],
            {
                "date": today(),
                "task_id": task_id,
                "result_id": ledger_payload.get("result_id") or task_id,
                "claim_type": ledger_payload.get("claim_type") or accepted_memory.get("claim_type", "general"),
                "claim_strength": record["claim_strength"],
                "source_ids": source_ids,
                "revalidation_status": accepted_memory.get("revalidation_status", "current"),
                "revalidation_triggers": ledger_payload.get("revalidation_triggers") or "none",
                "supersedes": accepted_memory.get("supersedes", "none"),
                "superseded_by": accepted_memory.get("superseded_by", "none"),
                "run_manifest_path": ledger_payload.get("run_manifest_path") or "none",
                "diagnostics_path": ledger_payload.get("diagnostics_path") or "none",
                "claim_gates_path": ledger_payload.get("claim_gates_path") or "none",
                "claim": ledger_payload.get("claim") or "accepted output",
                "evidence_link": record["evidence_ledger"]["evidence_link"],
                "limitations": ledger_payload.get("limitations") or "see evidence",
                "followups": followup_text,
            },
            key="result_id",
        )
        record["evidence_ledger"]["logged"] = True
    if record["route"] == "reject":
        failed_gates = [gate["gate"] for gate in record["hard_gate_results"] if gate.get("passed") is not True]
        upsert_markdown_row(
            ops_dir / "rejected_results.md",
            [
                "date",
                "task_id",
                "route",
                "claim_type",
                "claim_strength",
                "reason",
                "claim",
                "run_manifest_path",
                "diagnostics_path",
                "claim_gates_path",
                "anti_context",
                "evidence_link",
            ],
            {
                "date": today(),
                "task_id": task_id,
                "route": record["route"],
                "claim_type": ledger_payload.get("claim_type") or record.get("accepted_memory", {}).get("claim_type", "general"),
                "claim_strength": record["claim_strength"],
                "reason": "; ".join(failed_gates) or "reviewer rejected",
                "claim": ledger_payload.get("claim") or "rejected empirical result",
                "run_manifest_path": ledger_payload.get("run_manifest_path") or "none",
                "diagnostics_path": ledger_payload.get("diagnostics_path") or "none",
                "claim_gates_path": ledger_payload.get("claim_gates_path") or "none",
                "anti_context": ledger_payload.get("limitations") or "preserve as rejected empirical anti-context",
                "evidence_link": record["evidence_ledger"]["evidence_link"],
            },
        )
        record["rejection_logging"]["logged"] = True


def validate_result_acceptance_for_task(
    task_dir: Path,
    status: Optional[dict[str, Any]] = None,
    aggregate: Optional[dict[str, Any]] = None,
    ops_dir: Optional[Path] = None,
    write: bool = False,
    update_ledger_files: bool = False,
    write_on_fail: bool = False,
) -> dict[str, Any]:
    if status is None:
        status = load_status(task_dir)
    if aggregate is None:
        aggregate = load_json_optional(task_dir / "review_panel" / "aggregate.json")
    if ops_dir is None:
        ops_dir = infer_ops_dir(task_dir)
    record, failures, warnings = build_acceptance_record(task_dir, status, aggregate, ops_dir)
    ok = not failures
    if write and (ok or write_on_fail):
        if update_ledger_files and ops_dir is not None and ok:
            update_ledgers(ops_dir, record)
        output_record = {key: value for key, value in record.items() if not key.startswith("_")}
        atomic_write_json(task_dir / "review_panel" / "result_acceptance.json", output_record)
    return {
        "ok": ok,
        "task_dir": str(task_dir),
        "task_id": record.get("task_id"),
        "route": record.get("route"),
        "claim_strength": record.get("claim_strength"),
        "max_claim_strength": record.get("max_claim_strength"),
        "source_governance": record.get("source_governance"),
        "hard_gate_failures": failures,
        "warnings": warnings,
        "record": {key: value for key, value in record.items() if not key.startswith("_")},
    }


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate result_acceptance_v1.0 for a reviewed task.")
    parser.add_argument("task_dir", type=Path)
    parser.add_argument("--ops-dir", type=Path)
    parser.add_argument("--write", action="store_true", help="Write review_panel/result_acceptance.json when valid.")
    parser.add_argument("--write-on-fail", action="store_true", help="Write result_acceptance.json even when gates fail.")
    parser.add_argument("--update-ledgers", action="store_true", help="Update evidence_ledger.md or rejected_results.md when valid.")
    return parser.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    try:
        result = validate_result_acceptance_for_task(
            args.task_dir,
            ops_dir=args.ops_dir,
            write=args.write or args.update_ledgers,
            update_ledger_files=args.update_ledgers,
            write_on_fail=args.write_on_fail,
        )
    except ValueError as exc:
        print_json({"ok": False, "reason": "result_acceptance_load_failed", "error": str(exc), "task_dir": str(args.task_dir)})
        return MALFORMED
    print_json(result)
    return SUCCESS if result["ok"] else VALIDATION_FAILED


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
