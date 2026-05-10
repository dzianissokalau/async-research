#!/usr/bin/env python3
"""Read-only analysis-run dashboard and digest surface."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any, Iterable, Optional

from async_research_workflow.scripts import analysis_runs, analysis_validation
from async_research_workflow.scripts.analysis_runs import MANIFEST_RELATIVE_PATH
from async_research_workflow.scripts.update_accepted_outputs_index import (
    load_empirical_result_acceptance,
    read_index_rows,
)


SUCCESS = 0
VALIDATION_FINDINGS = 2
MALFORMED = 4

ACTIVE_ANALYSIS_STATUSES = {"ready_for_worker", "in_progress"}
REVIEWED_ANALYSIS_STATUSES = {
    "awaiting_review",
    "single_review",
    "panel_review",
    "accepted",
    "needs_revision",
    "needs_human",
    "rejected",
}
EMPIRICAL_TASK_TYPES = {"run_analysis", "evaluate_results"}
EMPIRICAL_CLAIM_TYPES = {"descriptive", "associative", "predictive", "causal", "probabilistic", "other"}
RESULT_ACCEPTANCE_RELATIVE_PATH = Path("review_panel/result_acceptance.json")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now(now: Optional[datetime] = None) -> str:
    current = now or utc_now()
    return current.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_now(value: Optional[str]) -> datetime:
    if not value:
        return utc_now()
    text = value.strip()
    try:
        if len(text) == 10:
            parsed = datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        else:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("--now must use YYYY-MM-DD or ISO-8601 datetime") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def read_json_object(path: Path) -> Optional[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def read_json_object_issue(ops_dir: Path, path: Path, reason_prefix: str) -> Optional[dict[str, Any]]:
    if not path.exists():
        return {"path": relative_path(ops_dir, path), "reason": f"{reason_prefix}_missing"}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"path": relative_path(ops_dir, path), "reason": f"{reason_prefix}_malformed", "error": str(exc)}
    if not isinstance(payload, dict):
        return {"path": relative_path(ops_dir, path), "reason": f"{reason_prefix}_not_object"}
    return None


def relative_path(ops_dir: Path, path: Path) -> str:
    try:
        return path.relative_to(ops_dir).as_posix()
    except ValueError:
        return path.as_posix()


def task_id_for(item: dict[str, Any]) -> str:
    payload = item["payload"]
    return str(payload.get("id") or item["task_dir"].name)


def task_summary(ops_dir: Path, item: dict[str, Any]) -> dict[str, Any]:
    payload = item["payload"]
    return {
        "task_id": task_id_for(item),
        "task_dir": relative_path(ops_dir, item["task_dir"]),
        "status": payload.get("status"),
        "type": payload.get("type"),
        "title": payload.get("title"),
        "updated_at": payload.get("updated_at"),
    }


def load_task_statuses(ops_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    tasks_dir = ops_dir / "tasks"
    items: list[dict[str, Any]] = []
    malformed: list[dict[str, Any]] = []
    if not tasks_dir.exists():
        return items, malformed
    for status_path in sorted(tasks_dir.glob("*/status.json")):
        payload = read_json_object(status_path)
        if payload is None:
            malformed.append(
                {
                    "task_dir": relative_path(ops_dir, status_path.parent),
                    "status_path": relative_path(ops_dir, status_path),
                    "reason": "status_unreadable_or_not_object",
                }
            )
            continue
        items.append({"task_dir": status_path.parent, "status_path": status_path, "payload": payload})
    return items, malformed


def run_json(entrypoint, argv: list[str | Path]) -> tuple[int, dict[str, Any]]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = entrypoint.main([str(arg) for arg in argv])
    text = stream.getvalue().strip()
    if not text:
        return code, {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return (
            MALFORMED,
            {
                "ok": False,
                "reason": "validator_output_malformed",
                "exit_code": code,
                "raw_output": text,
            },
        )
    return code, payload if isinstance(payload, dict) else {"ok": False, "payload": payload}


def gate_summaries(items: Any, limit: int) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    summaries: list[dict[str, Any]] = []
    for item in items[:limit]:
        if not isinstance(item, dict):
            continue
        summary = {
            "gate": item.get("gate") or item.get("check") or item.get("reason") or "unknown",
            "message": item.get("message") or item.get("reason") or "inspect validator output",
        }
        details = item.get("details")
        if details is not None:
            summary["details"] = details
        summaries.append(summary)
    return summaries


def active_analysis_tasks(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        item
        for item in items
        if item["payload"].get("type") == "run_analysis"
        and item["payload"].get("status") in ACTIVE_ANALYSIS_STATUSES
    ]


def completed_analysis_tasks(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    completed = []
    for item in items:
        payload = item["payload"]
        if payload.get("type") != "run_analysis":
            continue
        if payload.get("status") in REVIEWED_ANALYSIS_STATUSES:
            completed.append(item)
            continue
        manifest = read_json_object(item["task_dir"] / MANIFEST_RELATIVE_PATH)
        if isinstance(manifest, dict) and manifest.get("run_status") == "completed":
            completed.append(item)
    return completed


def review_stage_manifest_issue(ops_dir: Path, item: dict[str, Any]) -> Optional[dict[str, Any]]:
    payload = item["payload"]
    if payload.get("type") != "run_analysis" or payload.get("status") not in REVIEWED_ANALYSIS_STATUSES:
        return None
    issue = read_json_object_issue(ops_dir, item["task_dir"] / MANIFEST_RELATIVE_PATH, "run_manifest")
    if issue is None:
        return None
    return {**task_summary(ops_dir, item), **issue}


def preflight_entry(ops_dir: Path, item: dict[str, Any], now: datetime, limit: int) -> dict[str, Any]:
    code, payload = run_json(
        analysis_runs,
        ["preflight", item["task_dir"], "--ops-dir", ops_dir, "--now", iso_now(now)],
    )
    failures = gate_summaries(payload.get("hard_gate_failures"), limit)
    warnings = gate_summaries(payload.get("warnings"), limit)
    return {
        **task_summary(ops_dir, item),
        "run_id": payload.get("run_id"),
        "experiment_plan_id": payload.get("experiment_plan_id"),
        "accepted_plan_task_id": payload.get("accepted_plan_task_id"),
        "preflight_ok": payload.get("ok") is True,
        "safe_to_run": code == SUCCESS and payload.get("ok") is True,
        "exit_code": code,
        "malformed": code == MALFORMED,
        "next_step": payload.get("next_step"),
        "failure_count": int(payload.get("failure_count") or len(failures)),
        "warning_count": int(payload.get("warning_count") or len(warnings)),
        "blockers": failures,
        "warnings": warnings,
    }


def validation_entry(ops_dir: Path, item: dict[str, Any], now: datetime, limit: int) -> Optional[dict[str, Any]]:
    run_code, run_payload = run_json(
        analysis_validation,
        ["validate-run", item["task_dir"], "--ops-dir", ops_dir, "--now", iso_now(now)],
    )
    results_code, results_payload = run_json(
        analysis_validation,
        ["validate-results", item["task_dir"], "--ops-dir", ops_dir, "--now", iso_now(now)],
    )
    run_failures = gate_summaries(run_payload.get("hard_gate_failures"), limit)
    result_failures = gate_summaries(results_payload.get("hard_gate_failures"), limit)
    run_warnings = gate_summaries(run_payload.get("warnings"), limit)
    result_warnings = gate_summaries(results_payload.get("warnings"), limit)
    missing = run_payload.get("ok") is not True or results_payload.get("ok") is not True
    if not missing:
        return None
    return {
        **task_summary(ops_dir, item),
        "run_id": run_payload.get("run_id") or results_payload.get("run_id"),
        "experiment_plan_id": run_payload.get("experiment_plan_id") or results_payload.get("experiment_plan_id"),
        "validate_run_exit_code": run_code,
        "validate_results_exit_code": results_code,
        "malformed": run_code == MALFORMED or results_code == MALFORMED,
        "validate_run_ok": run_payload.get("ok") is True,
        "validate_results_ok": results_payload.get("ok") is True,
        "failure_count": int(run_payload.get("failure_count") or 0) + int(results_payload.get("failure_count") or 0),
        "warning_count": int(run_payload.get("warning_count") or 0) + int(results_payload.get("warning_count") or 0),
        "blockers": run_failures + result_failures,
        "warnings": run_warnings + result_warnings,
        "next_step": "run analysis validate-run and validate-results, then repair blockers before result acceptance",
    }


def malformed_validator_entries(
    active_entries: list[dict[str, Any]],
    validation_entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    malformed: list[dict[str, Any]] = []
    for entry in active_entries:
        if entry.get("exit_code") == MALFORMED:
            malformed.append(
                {
                    "task_id": entry.get("task_id"),
                    "task_dir": entry.get("task_dir"),
                    "status": entry.get("status"),
                    "type": entry.get("type"),
                    "reason": "analysis_preflight_malformed",
                    "validator": "analysis preflight",
                    "blockers": entry.get("blockers", []),
                }
            )
    for entry in validation_entries:
        validators = []
        if entry.get("validate_run_exit_code") == MALFORMED:
            validators.append("analysis validate-run")
        if entry.get("validate_results_exit_code") == MALFORMED:
            validators.append("analysis validate-results")
        if validators:
            malformed.append(
                {
                    "task_id": entry.get("task_id"),
                    "task_dir": entry.get("task_dir"),
                    "status": entry.get("status"),
                    "type": entry.get("type"),
                    "reason": "analysis_validation_malformed",
                    "validators": validators,
                    "blockers": entry.get("blockers", []),
                }
            )
    return malformed


def claim_gate_payload(task_dir: Path) -> Optional[dict[str, Any]]:
    return read_json_object(task_dir / "artifacts" / "analysis_run" / "claim_gates.json")


def claim_gate_attention(ops_dir: Path, item: dict[str, Any]) -> Optional[dict[str, Any]]:
    payload = claim_gate_payload(item["task_dir"])
    if payload is None:
        return None
    human_gate = payload.get("human_gate") if isinstance(payload.get("human_gate"), dict) else {}
    cap_reasons = payload.get("cap_reasons") if isinstance(payload.get("cap_reasons"), list) else []
    decision = payload.get("claim_decision")
    needs_attention = bool(cap_reasons) or decision in {"capped", "rejected", "needs_human"} or human_gate.get("required") is True
    if not needs_attention:
        return None
    return {
        **task_summary(ops_dir, item),
        "run_id": payload.get("run_id"),
        "experiment_plan_id": payload.get("experiment_plan_id"),
        "claim_type": payload.get("claim_type"),
        "requested_claim_strength": payload.get("requested_claim_strength"),
        "max_claim_strength": payload.get("max_claim_strength"),
        "claim_decision": decision,
        "recommended_route": payload.get("recommended_route"),
        "cap_reasons": cap_reasons,
        "human_gate": human_gate,
        "claim": payload.get("claim"),
    }


def claim_gate_summary_from_acceptance(record: dict[str, Any]) -> dict[str, Any]:
    analysis_run = record.get("analysis_run") if isinstance(record.get("analysis_run"), dict) else {}
    claim_gates = analysis_run.get("claim_gates") if isinstance(analysis_run.get("claim_gates"), dict) else {}
    computed = claim_gates.get("computed") if isinstance(claim_gates.get("computed"), dict) else None
    artifact = claim_gates.get("artifact") if isinstance(claim_gates.get("artifact"), dict) else None
    return computed or artifact or {}


def accepted_empirical_entry(ops_dir: Path, item: dict[str, Any], record: dict[str, Any]) -> Optional[dict[str, Any]]:
    analysis_run = record.get("analysis_run") if isinstance(record.get("analysis_run"), dict) else None
    if analysis_run is None:
        return None
    accepted_memory = record.get("accepted_memory") if isinstance(record.get("accepted_memory"), dict) else {}
    validation = analysis_run.get("validation") if isinstance(analysis_run.get("validation"), dict) else {}
    claim_gate = claim_gate_summary_from_acceptance(record)
    artifact_paths = analysis_run.get("artifact_paths") if isinstance(analysis_run.get("artifact_paths"), dict) else {}
    return {
        **task_summary(ops_dir, item),
        "route": record.get("route"),
        "claim_strength": record.get("claim_strength"),
        "max_claim_strength": record.get("max_claim_strength"),
        "claim_type": accepted_memory.get("claim_type") or claim_gate.get("claim_type"),
        "revalidation_status": accepted_memory.get("revalidation_status"),
        "next_recheck_date": accepted_memory.get("next_recheck_date"),
        "run_manifest_path": analysis_run.get("run_manifest_path"),
        "diagnostics_path": (analysis_run.get("diagnostics") or {}).get("path")
        if isinstance(analysis_run.get("diagnostics"), dict)
        else None,
        "claim_gates_path": artifact_paths.get("claim_gates"),
        "validation_ok": validation.get("ok") is True,
        "validation_failure_count": validation.get("failure_count", 0),
        "validation_warning_count": validation.get("warning_count", 0),
        "claim_decision": claim_gate.get("claim_decision"),
        "recommended_route": claim_gate.get("recommended_route"),
    }


def acceptance_revalidation_entry(
    ops_dir: Path,
    item: dict[str, Any],
    record: dict[str, Any],
    accepted_entry: dict[str, Any],
) -> Optional[dict[str, Any]]:
    analysis_run = record.get("analysis_run") if isinstance(record.get("analysis_run"), dict) else {}
    accepted_memory = record.get("accepted_memory") if isinstance(record.get("accepted_memory"), dict) else {}
    triggers = analysis_run.get("revalidation_triggers") if isinstance(analysis_run.get("revalidation_triggers"), list) else []
    status = accepted_memory.get("revalidation_status")
    if status not in {"stale", "due", "manual_review"} and not triggers:
        return None
    return {
        "task_id": accepted_entry["task_id"],
        "task_dir": accepted_entry["task_dir"],
        "claim_type": accepted_entry.get("claim_type"),
        "revalidation_status": status,
        "next_recheck_date": accepted_memory.get("next_recheck_date"),
        "run_manifest_path": accepted_entry.get("run_manifest_path"),
        "triggers": triggers,
    }


def accepted_records(
    ops_dir: Path,
    items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    accepted: list[dict[str, Any]] = []
    revalidation: list[dict[str, Any]] = []
    malformed: list[dict[str, Any]] = []
    for item in items:
        payload = item["payload"]
        if payload.get("type") not in EMPIRICAL_TASK_TYPES or payload.get("status") != "accepted":
            continue
        record_path = item["task_dir"] / RESULT_ACCEPTANCE_RELATIVE_PATH
        record, blockers = load_empirical_result_acceptance(item["task_dir"], payload)
        if blockers:
            malformed.append(
                {
                    **task_summary(ops_dir, item),
                    "path": relative_path(ops_dir, record_path),
                    "reason": "result_acceptance_invalid",
                    "blockers": blockers,
                }
            )
            continue
        if record is None:
            malformed.append(
                {
                    **task_summary(ops_dir, item),
                    "path": relative_path(ops_dir, record_path),
                    "reason": "result_acceptance_missing_or_malformed",
                }
            )
            continue
        entry = accepted_empirical_entry(ops_dir, item, record)
        if entry is None:
            malformed.append(
                {
                    **task_summary(ops_dir, item),
                    "path": relative_path(ops_dir, record_path),
                    "reason": "analysis_run_provenance_missing",
                }
            )
            continue
        accepted.append(entry)
        revalidation_entry = acceptance_revalidation_entry(ops_dir, item, record, entry)
        if revalidation_entry is not None:
            revalidation.append(revalidation_entry)
    return accepted, revalidation, malformed


def index_revalidation_rows(ops_dir: Path, accepted_task_ids: set[str], now: datetime, limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        index_rows = read_index_rows(ops_dir / "accepted_outputs_index.md", now=now)
    except ValueError:
        return rows
    for row in index_rows:
        if row.get("task_id") in accepted_task_ids:
            continue
        if row.get("claim_type") not in EMPIRICAL_CLAIM_TYPES:
            continue
        status = row.get("revalidation_status")
        if status not in {"stale", "due", "manual_review"}:
            continue
        rows.append(
            {
                "task_id": row.get("task_id"),
                "claim_type": row.get("claim_type"),
                "claim_strength": row.get("claim_strength"),
                "revalidation_status": status,
                "next_recheck_date": row.get("next_recheck_date"),
                "evidence_link": row.get("evidence_link"),
                "source": "accepted_outputs_index",
            }
        )
        if len(rows) >= limit:
            break
    return rows


def validation_exit_code(summary: dict[str, int], malformed_count: int) -> int:
    if malformed_count:
        return MALFORMED
    if (
        summary["preflight_blocked_count"]
        or summary["preflight_warning_count"]
        or summary["completed_missing_validation_count"]
        or summary["revalidation_needed_count"]
        or summary["claim_caps_or_human_review_count"]
    ):
        return VALIDATION_FINDINGS
    return SUCCESS


def analysis_dashboard_report(
    ops_dir: Path,
    now: Optional[datetime] = None,
    max_items: int = 10,
) -> dict[str, Any]:
    current = now or utc_now()
    items, malformed_statuses = load_task_statuses(ops_dir)
    active_entries = [preflight_entry(ops_dir, item, current, max_items) for item in active_analysis_tasks(items)]
    preflight_blockers = [entry for entry in active_entries if entry["failure_count"] > 0 or entry["preflight_ok"] is not True]
    preflight_warnings = [entry for entry in active_entries if entry["failure_count"] == 0 and entry["warning_count"] > 0]
    safe_to_run = [entry for entry in active_entries if entry["safe_to_run"]]
    completed_tasks = completed_analysis_tasks(items)
    missing_validation = [
        entry
        for entry in (
            validation_entry(ops_dir, item, current, max_items)
            for item in completed_tasks
        )
        if entry is not None
    ]
    accepted, acceptance_revalidation, malformed_acceptance = accepted_records(ops_dir, items)
    accepted_task_ids = {str(entry.get("task_id")) for entry in accepted}
    revalidation_needed = acceptance_revalidation + index_revalidation_rows(ops_dir, accepted_task_ids, current, max_items)
    claim_attention = [
        entry
        for entry in (claim_gate_attention(ops_dir, item) for item in completed_tasks)
        if entry is not None
    ]
    review_manifest_issues = [
        issue
        for issue in (review_stage_manifest_issue(ops_dir, item) for item in completed_tasks)
        if issue is not None
    ]
    malformed = (
        malformed_statuses
        + malformed_acceptance
        + review_manifest_issues
        + malformed_validator_entries(active_entries, missing_validation)
    )
    summary = {
        "active_run_analysis_count": len(active_entries),
        "safe_to_run_count": len(safe_to_run),
        "preflight_blocked_count": len(preflight_blockers),
        "preflight_warning_count": len(preflight_warnings),
        "completed_missing_validation_count": len(missing_validation),
        "accepted_empirical_evidence_count": len(accepted),
        "revalidation_needed_count": len(revalidation_needed),
        "claim_caps_or_human_review_count": len(claim_attention),
        "malformed_read_model_count": len(malformed),
    }
    exit_code = validation_exit_code(summary, len(malformed))
    operator_summary = {
        "safe_to_run_task_ids": [entry["task_id"] for entry in safe_to_run[:max_items]],
        "blocked_task_ids": [entry["task_id"] for entry in preflight_blockers[:max_items]],
        "completed_runs_needing_validation": [entry["task_id"] for entry in missing_validation[:max_items]],
        "claims_needing_attention": [entry["task_id"] for entry in claim_attention[:max_items]],
        "accepted_empirical_task_ids": [entry["task_id"] for entry in accepted[:max_items]],
    }
    return {
        "ok": exit_code == SUCCESS,
        "action": "analysis_dashboard_rendered",
        "ops_dir": str(ops_dir),
        "generated_at": iso_now(current),
        "read_only": True,
        "changed": False,
        "generated_from": "analysis_preflight_validate_results_and_result_acceptance_read_model",
        "validation_exit_code": exit_code,
        "summary": summary,
        "operator_summary": operator_summary,
        "sections": {
            "active_run_analysis": active_entries[:max_items],
            "safe_to_run": safe_to_run[:max_items],
            "preflight_blockers": preflight_blockers[:max_items],
            "preflight_warnings": preflight_warnings[:max_items],
            "completed_runs_missing_validation": missing_validation[:max_items],
            "accepted_empirical_evidence": accepted[:max_items],
            "revalidation_needed": revalidation_needed[:max_items],
            "claim_caps_and_human_review": claim_attention[:max_items],
            "malformed_read_model_inputs": malformed[:max_items],
        },
    }


def format_count(value: Any) -> str:
    return str(value if value is not None else 0)


def analysis_digest_section(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    sections = report.get("sections") if isinstance(report.get("sections"), dict) else {}
    safe = sections.get("safe_to_run") if isinstance(sections.get("safe_to_run"), list) else []
    blockers = sections.get("preflight_blockers") if isinstance(sections.get("preflight_blockers"), list) else []
    missing_validation = sections.get("completed_runs_missing_validation") if isinstance(sections.get("completed_runs_missing_validation"), list) else []
    claim_attention = sections.get("claim_caps_and_human_review") if isinstance(sections.get("claim_caps_and_human_review"), list) else []
    revalidation = sections.get("revalidation_needed") if isinstance(sections.get("revalidation_needed"), list) else []
    lines = [
        "## Analysis Surface",
        "",
        f"- Generated: {report.get('generated_at', 'none')}",
        f"- Active run_analysis: {format_count(summary.get('active_run_analysis_count'))}",
        f"- Safe to run: {format_count(summary.get('safe_to_run_count'))}",
        f"- Preflight blocked / warnings: {format_count(summary.get('preflight_blocked_count'))} / {format_count(summary.get('preflight_warning_count'))}",
        f"- Completed runs missing validation: {format_count(summary.get('completed_missing_validation_count'))}",
        f"- Accepted empirical evidence: {format_count(summary.get('accepted_empirical_evidence_count'))}",
        f"- Revalidation needed: {format_count(summary.get('revalidation_needed_count'))}",
        f"- Claim caps or human review: {format_count(summary.get('claim_caps_or_human_review_count'))}",
        f"- Malformed inputs: {format_count(summary.get('malformed_read_model_count'))}",
    ]
    if safe:
        lines.append("- Safe analyses:")
        for entry in safe[:5]:
            lines.append(f"  - {entry.get('task_id')}: {entry.get('next_step') or 'run analysis'}")
    else:
        lines.append("- Safe analyses: none")
    if blockers:
        lines.append("- Preflight blockers:")
        for entry in blockers[:5]:
            gates = ", ".join(str(item.get("gate")) for item in entry.get("blockers", [])[:3]) or "preflight"
            lines.append(f"  - {entry.get('task_id')}: {gates}")
    else:
        lines.append("- Preflight blockers: none")
    if missing_validation:
        lines.append("- Completed runs needing validation:")
        for entry in missing_validation[:5]:
            gates = ", ".join(str(item.get("gate")) for item in entry.get("blockers", [])[:3]) or "validation"
            lines.append(f"  - {entry.get('task_id')}: {gates}")
    else:
        lines.append("- Completed runs needing validation: none")
    if claim_attention:
        lines.append("- Blocked or capped claims:")
        for entry in claim_attention[:5]:
            reason = ", ".join(str(item) for item in entry.get("cap_reasons", [])[:2]) or str(entry.get("claim_decision") or "human review")
            lines.append(f"  - {entry.get('task_id')}: {entry.get('claim_type')} {entry.get('requested_claim_strength')} -> {entry.get('max_claim_strength')} ({reason})")
    else:
        lines.append("- Blocked or capped claims: none")
    if revalidation:
        lines.append("- Revalidation attention:")
        for entry in revalidation[:5]:
            lines.append(f"  - {entry.get('task_id')}: {entry.get('revalidation_status')} (next {entry.get('next_recheck_date')})")
    else:
        lines.append("- Revalidation attention: none")
    return "\n".join(lines) + "\n"


def command_dashboard(args: argparse.Namespace) -> int:
    try:
        now = parse_now(args.now)
    except ValueError as exc:
        print_json(
            {
                "ok": False,
                "action": "analysis_dashboard_rendered",
                "reason": "invalid_now",
                "error": str(exc),
                "read_only": True,
                "changed": False,
                "validation_exit_code": MALFORMED,
            }
        )
        return MALFORMED
    report = analysis_dashboard_report(args.ops_dir, now=now, max_items=args.max_items)
    print_json(report)
    return int(report["validation_exit_code"])


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render read-only analysis-run surfaces.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    dashboard = subparsers.add_parser(
        "dashboard",
        help="Render a read-only analysis dashboard.",
        description=(
            "Read-only dashboard for active run_analysis preflight state, completed-run validation gaps, "
            "accepted empirical evidence, revalidation triggers, and blocked or capped claims."
        ),
    )
    dashboard.add_argument("ops_dir", type=Path, help="Path to research_ops.")
    dashboard.add_argument("--now", help="Override current time for deterministic freshness checks.")
    dashboard.add_argument("--max-items", type=int, default=10, help="Maximum rows per dashboard section.")
    dashboard.set_defaults(func=command_dashboard)
    return parser.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    if not args.ops_dir.exists():
        print_json(
            {
                "ok": False,
                "action": "analysis_dashboard_rendered",
                "reason": "ops_dir_missing",
                "ops_dir": str(args.ops_dir),
                "read_only": True,
                "changed": False,
                "validation_exit_code": MALFORMED,
            }
        )
        return MALFORMED
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
