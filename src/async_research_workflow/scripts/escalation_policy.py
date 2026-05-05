#!/usr/bin/env python3
"""Evaluate deterministic human-escalation rules for async research tasks."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from async_research_workflow.resources import schema_path
from async_research_workflow.scripts.data_source_audit import (
    EXPERIMENT_READY_STATUSES,
    parse_register,
    validate_rows,
)
from async_research_workflow.scripts.health_check import parse_datetime, row_amount
from async_research_workflow.scripts.validate_json_artifact import load_json, validate
from async_research_workflow.scripts.validate_transition import validate_payload
from async_research_workflow.scripts.version_metadata import apply_default_versions


SUCCESS = 0
ESCALATION_REQUIRED = 2
VALIDATION_FAILED = 3
MALFORMED = 4

SCHEMA_VERSION = "1.0"
FRAMEWORK_VERSION = "escalation_policy_v1.0"
STATUS_SCHEMA = schema_path("task_status.schema.json")
CLAIM_ORDER = {"none": 0, "weak": 1, "suggestive": 2, "moderate": 3, "strong": 4}
ESCALATABLE_STATUSES = {
    "inbox",
    "ready_for_planning",
    "ready_for_worker",
    "in_progress",
    "awaiting_review",
    "single_review",
    "panel_review",
    "needs_revision",
    "needs_human",
}
VAGUE_HUMAN_REASONS = {
    "",
    "needs human",
    "needs_human",
    "human required",
    "manual review",
    "review needed",
    "blocked",
    "unknown",
    "n/a",
}


POLICY_ROWS: list[dict[str, Any]] = [
    {
        "trigger": "required_source_unaudited",
        "condition": "A task data_audit_refs item is missing from data_source_audit.md or is not available/usable_with_caveats.",
        "severity": "high",
        "routing_destination": "needs_human",
        "required_human_decision": "approve_data_use or create data_readiness task",
        "available_decisions": ["approve_data_use", "request_data_readiness", "pause", "reject"],
        "default_safe_action": "pause worker execution before using the source",
        "retry_behavior": "retry after data_source_audit.md records an experiment-ready source status",
        "ledger_update_behavior": "record the approval or rejection with async-research decision before resuming",
    },
    {
        "trigger": "source_freshness_expired",
        "condition": "A required data source last_checked date is older than the configured freshness window.",
        "severity": "high",
        "routing_destination": "needs_human",
        "required_human_decision": "refresh source or approve stale use with caveats",
        "available_decisions": ["refresh_source", "approve_data_use", "pause", "reject"],
        "default_safe_action": "pause until the source is refreshed or explicitly approved",
        "retry_behavior": "retry after last_checked is updated or a human stale-use approval is logged",
        "ledger_update_behavior": "record the refresh or stale-use approval in decisions.md",
    },
    {
        "trigger": "accepted_memory_conflict",
        "condition": "Worker output explicitly states it conflicts with accepted memory.",
        "severity": "critical",
        "routing_destination": "needs_human",
        "required_human_decision": "decide whether accepted memory or new evidence should be revised",
        "available_decisions": ["approve", "request_revision", "pause", "reject", "override"],
        "default_safe_action": "do not update accepted memory",
        "retry_behavior": "retry only after the contradiction is resolved or scoped as a new hypothesis",
        "ledger_update_behavior": "record the memory decision and related artifacts in decisions.md",
    },
    {
        "trigger": "reviewer_disagreement_beyond_threshold",
        "condition": "Reviewer claim-strength scores differ by the configured threshold or decisions are materially split.",
        "severity": "high",
        "routing_destination": "needs_human",
        "required_human_decision": "choose revision, rejection, higher-tier review, or acceptance with caveats",
        "available_decisions": ["request_revision", "approve", "pause", "reject", "override"],
        "default_safe_action": "do not accept the result",
        "retry_behavior": "retry after one bounded revision or an added independent review",
        "ledger_update_behavior": "record the chosen route in decisions.md",
    },
    {
        "trigger": "high_confidence_weak_evidence",
        "condition": "A result or review reports confidence >= 0.85 while claim_strength/evidence_strength is weak or none.",
        "severity": "high",
        "routing_destination": "needs_human",
        "required_human_decision": "lower claim strength, request revision, or reject overconfident output",
        "available_decisions": ["request_revision", "approve", "pause", "reject"],
        "default_safe_action": "block acceptance and require caveat correction",
        "retry_behavior": "retry after the output restates proportional claim strength",
        "ledger_update_behavior": "record the claim-strength decision in decisions.md",
    },
    {
        "trigger": "task_exceeds_budget",
        "condition": "Logged task cost exceeds status.json budget.max_api_usd + budget.max_compute_usd.",
        "severity": "high",
        "routing_destination": "needs_human",
        "required_human_decision": "approve budget overrun or stop the task",
        "available_decisions": ["approve_budget", "pause", "reject"],
        "default_safe_action": "stop paid work",
        "retry_behavior": "retry only after a budget approval or lowered scope",
        "ledger_update_behavior": "record approval with async-research decision and preserve cost_ledger.csv rows",
    },
    {
        "trigger": "revision_limit_hit",
        "condition": "revision_limit_hit is true or revision_count >= max_revisions while more revision is needed.",
        "severity": "medium",
        "routing_destination": "needs_human",
        "required_human_decision": "decide whether another revision is worth the cost",
        "available_decisions": ["resume", "pause", "reject", "override"],
        "default_safe_action": "pause revisions",
        "retry_behavior": "retry only after human approval resets or overrides the revision limit",
        "ledger_update_behavior": "record the revision decision in decisions.md",
    },
    {
        "trigger": "strategic_or_business_action",
        "condition": "Output proposes a strategic, investment, public, pricing, policy, or business action.",
        "severity": "critical",
        "routing_destination": "needs_human",
        "required_human_decision": "approve or reject the action before it influences decisions",
        "available_decisions": ["approve", "approve_public", "approve_high_stakes", "pause", "reject"],
        "default_safe_action": "do not act on the recommendation",
        "retry_behavior": "retry after human narrows the claim to research evidence or approves action use",
        "ledger_update_behavior": "record the approval scope in decisions.md",
    },
    {
        "trigger": "accepted_memory_lacks_citations",
        "condition": "A result that would affect accepted memory lacks DS-* refs, URLs, or markdown citations.",
        "severity": "high",
        "routing_destination": "needs_human",
        "required_human_decision": "supply citations, request revision, or reject memory update",
        "available_decisions": ["request_revision", "approve", "pause", "reject"],
        "default_safe_action": "do not write accepted evidence",
        "retry_behavior": "retry after citations are added and result acceptance is rerun",
        "ledger_update_behavior": "record any citation override in decisions.md",
    },
    {
        "trigger": "ambiguous_task_contract",
        "condition": "task.md is missing or contains unresolved TODO/TBD/ambiguous markers.",
        "severity": "medium",
        "routing_destination": "needs_human",
        "required_human_decision": "clarify scope, pause, or reject the task",
        "available_decisions": ["resume", "pause", "reject"],
        "default_safe_action": "pause before worker execution",
        "retry_behavior": "retry after task.md and status.json allowed paths are clarified",
        "ledger_update_behavior": "record the clarification decision in decisions.md",
    },
    {
        "trigger": "unauthorized_scope_change",
        "condition": "Worker output explicitly requests scope expansion or reports work outside authorized scope.",
        "severity": "high",
        "routing_destination": "needs_human",
        "required_human_decision": "approve scope change, narrow the task, or reject output",
        "available_decisions": ["approve", "request_revision", "pause", "reject"],
        "default_safe_action": "do not continue beyond the original task contract",
        "retry_behavior": "retry after a human updates task.md/status.json allowed scope",
        "ledger_update_behavior": "record the scope decision in decisions.md",
    },
    {
        "trigger": "unverifiable_hidden_assumptions",
        "condition": "Worker or reviewer marks assumptions as hidden or unverifiable.",
        "severity": "high",
        "routing_destination": "needs_human",
        "required_human_decision": "approve assumptions, request evidence, or reject the result",
        "available_decisions": ["approve", "request_revision", "pause", "reject"],
        "default_safe_action": "do not accept the result",
        "retry_behavior": "retry after assumptions are made explicit and testable",
        "ledger_update_behavior": "record the assumption decision in decisions.md",
    },
]

POLICY_BY_TRIGGER = {row["trigger"]: row for row in POLICY_ROWS}
SEVERITY_RANK = {"medium": 1, "high": 2, "critical": 3}


def iso_now(now: Optional[datetime] = None) -> str:
    current = now or datetime.now(timezone.utc)
    return current.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def resolve_task_dir(path: Path) -> Path:
    return path.parent if path.name == "status.json" else path


def infer_ops_dir(task_dir: Path) -> Optional[Path]:
    if task_dir.parent.name == "tasks":
        return task_dir.parent.parent
    for parent in task_dir.parents:
        if parent.name == "research_ops":
            return parent
    return None


def load_status(task_dir: Path) -> dict[str, Any]:
    payload = load_json(task_dir / "status.json")
    if not isinstance(payload, dict):
        raise ValueError(f"status file is not an object: {task_dir / 'status.json'}")
    return payload


def extract_json_objects(text: str) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    for match in re.finditer(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE):
        try:
            payload = json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            objects.append(payload)
    return objects


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def worker_payloads(task_dir: Path) -> list[dict[str, Any]]:
    worker_output = task_dir / "worker_output.md"
    if not worker_output.exists():
        return []
    return extract_json_objects(read_text(worker_output))


def load_reviews(task_dir: Path) -> list[dict[str, Any]]:
    reviews: list[dict[str, Any]] = []
    for path in sorted((task_dir / "reviews").glob("*.md")):
        objects = extract_json_objects(read_text(path))
        if objects:
            reviews.append(objects[0])
    return reviews


def load_aggregate(task_dir: Path) -> dict[str, Any]:
    path = task_dir / "review_panel" / "aggregate.json"
    if not path.exists():
        return {}
    try:
        payload = load_json(path)
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


def flag_enabled(payloads: list[dict[str, Any]], keys: set[str]) -> bool:
    for payload in payloads:
        flags = payload.get("escalation_flags")
        if isinstance(flags, dict) and any(flags.get(key) is True for key in keys):
            return True
        if any(payload.get(key) is True for key in keys):
            return True
    return False


def text_has_any(text: str, patterns: Iterable[str]) -> bool:
    lowered = text.lower()
    return any(pattern in lowered for pattern in patterns)


def text_has_citation(text: str) -> bool:
    return bool(
        re.search(r"\bDS-[0-9]{4}\b", text)
        or re.search(r"https?://", text)
        or re.search(r"\[[^\]]+\]\([^)]+\)", text)
    )


def task_cost_usd(ops_dir: Path, task_id: str) -> float:
    path = ops_dir / "cost_ledger.csv"
    if not path.exists():
        return 0.0
    total = 0.0
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if str(row.get("item_id", "")).strip() == task_id:
                total += row_amount({str(key): str(value) for key, value in row.items() if key is not None})
    return round(total, 4)


def source_rows(ops_dir: Path) -> tuple[dict[str, dict[str, str]], list[dict[str, Any]]]:
    path = ops_dir / "data_source_audit.md"
    try:
        schema_version, rows = parse_register(path)
    except ValueError as exc:
        return {}, [{"reason": "malformed_register", "path": str(path), "message": str(exc)}]
    errors = validate_rows(schema_version, rows)
    if errors:
        return {}, [{"reason": "invalid_register", "path": str(path), "errors": errors}]
    return {row["source_id"]: row for row in rows}, []


def add_trigger(triggers: list[dict[str, Any]], trigger: str, message: str, details: Any = None) -> None:
    policy = POLICY_BY_TRIGGER[trigger]
    payload = {
        "trigger": trigger,
        "severity": policy["severity"],
        "message": message,
        "routing_destination": policy["routing_destination"],
        "required_human_decision": policy["required_human_decision"],
    }
    if details is not None:
        payload["details"] = details
    triggers.append(payload)


def evaluate_sources(status: dict[str, Any], ops_dir: Path, now: datetime, freshness_days: int, triggers: list[dict[str, Any]]) -> None:
    refs = status.get("data_audit_refs")
    if not isinstance(refs, list) or not refs:
        return
    rows, row_errors = source_rows(ops_dir)
    if row_errors:
        add_trigger(triggers, "required_source_unaudited", "data_source_audit.md is missing or invalid", row_errors)
        return
    for ref in refs:
        if not isinstance(ref, str):
            continue
        row = rows.get(ref)
        if row is None:
            add_trigger(triggers, "required_source_unaudited", f"{ref} is not present in data_source_audit.md", {"source_id": ref})
            continue
        if row.get("status") not in EXPERIMENT_READY_STATUSES:
            add_trigger(
                triggers,
                "required_source_unaudited",
                f"{ref} is not experiment-ready",
                {"source_id": ref, "source_status": row.get("status")},
            )
            continue
        checked = parse_datetime(row.get("last_checked"))
        if checked is None:
            add_trigger(
                triggers,
                "source_freshness_expired",
                f"{ref} has no valid last_checked date",
                {"source_id": ref, "last_checked": row.get("last_checked")},
            )
            continue
        age_days = (now - checked).total_seconds() / 86400
        if age_days > freshness_days:
            add_trigger(
                triggers,
                "source_freshness_expired",
                f"{ref} freshness expired",
                {"source_id": ref, "last_checked": row.get("last_checked"), "age_days": round(age_days, 1), "freshness_days": freshness_days},
            )


def evaluate_reviews(task_dir: Path, threshold: int, triggers: list[dict[str, Any]]) -> None:
    reviews = load_reviews(task_dir)
    strengths = [review.get("claim_strength") for review in reviews if review.get("claim_strength") in CLAIM_ORDER]
    if len(strengths) >= 2:
        spread = max(CLAIM_ORDER[strength] for strength in strengths) - min(CLAIM_ORDER[strength] for strength in strengths)
        if spread >= threshold:
            add_trigger(
                triggers,
                "reviewer_disagreement_beyond_threshold",
                "reviewer claim-strength disagreement exceeds threshold",
                {"claim_strengths": strengths, "threshold": threshold, "spread": spread},
            )
    decisions = [review.get("decision") for review in reviews if isinstance(review.get("decision"), str)]
    if decisions and {"accept", "accept_with_caveats"} & set(decisions) and {"needs_revision", "needs_human", "reject"} & set(decisions):
        add_trigger(
            triggers,
            "reviewer_disagreement_beyond_threshold",
            "reviewer decisions are materially split",
            {"decisions": decisions},
        )
    aggregate = load_aggregate(task_dir)
    disagreements = aggregate.get("disagreements")
    if isinstance(disagreements, list) and any(str(item).strip().lower() not in {"", "none"} for item in disagreements):
        add_trigger(
            triggers,
            "reviewer_disagreement_beyond_threshold",
            "aggregate review records disagreements",
            {"disagreements": disagreements},
        )


def evaluate_confidence(payloads: list[dict[str, Any]], reviews: list[dict[str, Any]], confidence_threshold: float, triggers: list[dict[str, Any]]) -> None:
    records = [*payloads, *reviews]
    for record in records:
        confidence = record.get("confidence")
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
            continue
        claim = record.get("claim_strength") or record.get("evidence_strength")
        if confidence >= confidence_threshold and claim in {"none", "weak"}:
            add_trigger(
                triggers,
                "high_confidence_weak_evidence",
                "high confidence is paired with weak evidence",
                {"confidence": confidence, "claim_strength": claim},
            )


def evaluate_budget(status: dict[str, Any], ops_dir: Path, triggers: list[dict[str, Any]]) -> None:
    task_id = str(status.get("id") or "")
    budget = status.get("budget")
    if not task_id or not isinstance(budget, dict):
        return
    budget_cap = float(budget.get("max_api_usd") or 0) + float(budget.get("max_compute_usd") or 0)
    spent = task_cost_usd(ops_dir, task_id)
    if budget_cap <= 0:
        if spent > 0:
            add_trigger(
                triggers,
                "task_exceeds_budget",
                "task spent money while status budget allows no spend",
                {"task_id": task_id, "spent_usd": spent, "budget_cap_usd": budget_cap},
            )
        return
    if spent > budget_cap:
        add_trigger(
            triggers,
            "task_exceeds_budget",
            "task cost exceeds status budget",
            {"task_id": task_id, "spent_usd": spent, "budget_cap_usd": budget_cap},
        )


def evaluate_contract(task_dir: Path, status: dict[str, Any], triggers: list[dict[str, Any]]) -> None:
    task_md = task_dir / "task.md"
    text = read_text(task_md)
    allowed_paths = status.get("allowed_paths")
    ambiguous = False
    reasons: list[str] = []
    if not text.strip():
        ambiguous = True
        reasons.append("task.md missing or empty")
    if text_has_any(text, ["<todo", "todo:", "tbd", "???", "ambiguous", "unclear scope"]):
        ambiguous = True
        reasons.append("task.md contains unresolved ambiguity markers")
    if not isinstance(allowed_paths, list) or not allowed_paths:
        ambiguous = True
        reasons.append("allowed_paths missing")
    if ambiguous:
        add_trigger(triggers, "ambiguous_task_contract", "task contract is ambiguous", {"task_md": str(task_md), "reasons": reasons})


def evaluate_output_markers(task_dir: Path, status: dict[str, Any], payloads: list[dict[str, Any]], triggers: list[dict[str, Any]]) -> None:
    worker_text = read_text(task_dir / "worker_output.md")
    if flag_enabled(payloads, {"accepted_memory_conflict", "conflicts_with_accepted_memory"}) or text_has_any(
        worker_text,
        ["conflicts with accepted memory", "contradicts accepted memory", "contradicts accepted_outputs_index"],
    ):
        add_trigger(triggers, "accepted_memory_conflict", "output conflicts with accepted memory", {"worker_output": str(task_dir / "worker_output.md")})

    if flag_enabled(payloads, {"proposes_strategic_action", "strategic_or_business_action"}) or text_has_any(
        worker_text,
        ["strategic action", "investment recommendation", "pricing decision", "policy recommendation", "business decision"],
    ):
        add_trigger(triggers, "strategic_or_business_action", "output proposes a strategic or business action", {"worker_output": str(task_dir / "worker_output.md")})

    if flag_enabled(payloads, {"scope_change_requested", "unauthorized_scope_change"}) or text_has_any(
        worker_text,
        ["scope change requested", "outside authorized scope", "expanded the scope"],
    ):
        add_trigger(triggers, "unauthorized_scope_change", "output changes or requests change to authorized scope", {"worker_output": str(task_dir / "worker_output.md")})

    if flag_enabled(payloads, {"hidden_assumptions", "unverifiable_hidden_assumptions"}) or text_has_any(
        worker_text,
        ["hidden assumptions", "unverifiable assumption", "reviewers cannot verify"],
    ):
        add_trigger(triggers, "unverifiable_hidden_assumptions", "output depends on hidden or unverifiable assumptions", {"worker_output": str(task_dir / "worker_output.md")})

    affects_memory = status.get("status") in {"awaiting_review", "single_review", "panel_review", "accepted"}
    recommendation = (status.get("result") or {}).get("recommendation") if isinstance(status.get("result"), dict) else None
    if worker_text.strip() and affects_memory and recommendation in {"ready", "usable_with_caveats", None} and not text_has_citation(worker_text):
        add_trigger(triggers, "accepted_memory_lacks_citations", "accepted-memory candidate lacks citations", {"worker_output": str(task_dir / "worker_output.md")})


def evaluate_task(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    task_dir = resolve_task_dir(args.task_dir)
    ops_dir = args.ops_dir or infer_ops_dir(task_dir)
    if ops_dir is None:
        return {"ok": False, "reason": "ops_dir_required", "task_dir": str(task_dir)}, MALFORMED
    now = parse_datetime(args.now) if args.now else datetime.now(timezone.utc)
    if now is None:
        now = datetime.now(timezone.utc)

    try:
        status = load_status(task_dir)
    except ValueError as exc:
        return {"ok": False, "reason": "status_load_failed", "error": str(exc), "task_dir": str(task_dir)}, MALFORMED

    payloads = worker_payloads(task_dir)
    reviews = load_reviews(task_dir)
    triggers: list[dict[str, Any]] = []
    evaluate_sources(status, ops_dir, now, args.source_freshness_days, triggers)
    evaluate_reviews(task_dir, args.reviewer_disagreement_threshold, triggers)
    evaluate_confidence(payloads, reviews, args.confidence_threshold, triggers)
    evaluate_budget(status, ops_dir, triggers)
    evaluate_contract(task_dir, status, triggers)
    evaluate_output_markers(task_dir, status, payloads, triggers)

    revision_count = status.get("revision_count")
    max_revisions = status.get("max_revisions")
    if status.get("revision_limit_hit") is True or (
        isinstance(revision_count, int)
        and isinstance(max_revisions, int)
        and not isinstance(revision_count, bool)
        and not isinstance(max_revisions, bool)
        and max_revisions >= 0
        and revision_count >= max_revisions
        and status.get("status") in {"needs_revision", "in_progress", "awaiting_review", "single_review", "panel_review"}
    ):
        add_trigger(
            triggers,
            "revision_limit_hit",
            "revision limit is hit or would be exceeded",
            {"revision_count": revision_count, "max_revisions": max_revisions, "revision_limit_hit": status.get("revision_limit_hit")},
        )

    deduped: dict[str, dict[str, Any]] = {}
    for trigger in triggers:
        deduped.setdefault(trigger["trigger"], trigger)
    triggers = sorted(deduped.values(), key=lambda item: (-SEVERITY_RANK[item["severity"]], item["trigger"]))
    report = {
        "ok": not triggers,
        "task_dir": str(task_dir),
        "ops_dir": str(ops_dir),
        "policy_version": FRAMEWORK_VERSION,
        "route": "needs_human" if triggers else "continue",
        "trigger_count": len(triggers),
        "triggered_triggers": [item["trigger"] for item in triggers],
        "triggers": triggers,
        "human_gate": build_human_gate(triggers, now) if triggers else None,
    }
    if args.apply and triggers:
        apply_report, code = apply_escalation(task_dir, ops_dir, status, report["human_gate"])
        report.update(apply_report)
        return report, code
    return report, ESCALATION_REQUIRED if triggers else SUCCESS


def build_human_gate(triggers: list[dict[str, Any]], now: datetime) -> dict[str, Any]:
    primary = triggers[0]
    policy = POLICY_BY_TRIGGER[primary["trigger"]]
    reasons = [trigger["message"] for trigger in triggers[:3]]
    if len(triggers) > 3:
        reasons.append(f"{len(triggers) - 3} additional trigger(s)")
    return {
        "policy_version": FRAMEWORK_VERSION,
        "trigger": primary["trigger"],
        "triggered_at": iso_now(now),
        "severity": primary["severity"],
        "reason": "; ".join(reasons),
        "required_human_decision": policy["required_human_decision"],
        "available_decisions": policy["available_decisions"],
        "default_safe_action": policy["default_safe_action"],
        "retry_behavior": policy["retry_behavior"],
        "ledger_update_behavior": policy["ledger_update_behavior"],
        "triggered_triggers": [trigger["trigger"] for trigger in triggers],
        "details": triggers,
    }


def validate_status_schema(status: dict[str, Any]) -> list[dict[str, Any]]:
    schema = load_json(STATUS_SCHEMA)
    if not isinstance(schema, dict):
        return [{"path": "$", "message": f"status schema is not an object: {STATUS_SCHEMA}"}]
    return [error.to_dict() for error in validate(status, schema)]


def apply_escalation(task_dir: Path, ops_dir: Path, status: dict[str, Any], human_gate: dict[str, Any]) -> tuple[dict[str, Any], int]:
    current_status = status.get("status")
    if current_status not in ESCALATABLE_STATUSES:
        return {
            "ok": False,
            "action": "escalation_not_applied",
            "reason": "status_not_escalatable",
            "status": current_status,
            "human_gate": human_gate,
        }, VALIDATION_FAILED

    updated = apply_default_versions(dict(status))
    updated.setdefault("schema_version", SCHEMA_VERSION)
    updated["requires_human"] = True
    updated["human_gate_reason"] = human_gate["reason"]
    updated["human_gate"] = human_gate
    framework_versions = dict(updated.get("framework_versions") or {})
    framework_versions["escalation_policy"] = FRAMEWORK_VERSION
    updated["framework_versions"] = framework_versions
    if current_status != "needs_human":
        updated["previous_status"] = current_status
        updated["status"] = "needs_human"
        updated["last_transition_reason"] = f"escalation_policy_{human_gate['trigger']}"
        updated["updated_at"] = human_gate["triggered_at"]

    schema_errors = validate_status_schema(updated)
    if schema_errors:
        return {"ok": False, "action": "escalation_not_applied", "reason": "status_schema_invalid", "errors": schema_errors}, MALFORMED
    if current_status != "needs_human":
        transition_code, transition_result = validate_payload(updated, decisions_path=ops_dir / "decisions.md")
        if transition_code != SUCCESS:
            return {"ok": False, "action": "escalation_not_applied", "reason": "invalid_transition", "errors": [transition_result]}, VALIDATION_FAILED

    atomic_write_json(task_dir / "status.json", updated)
    return {
        "ok": False,
        "action": "escalation_applied",
        "status": "needs_human",
        "human_gate": human_gate,
        "status_path": str(task_dir / "status.json"),
    }, ESCALATION_REQUIRED


def structured_human_gate_errors(status: dict[str, Any], task_dir: Path) -> list[dict[str, Any]]:
    if status.get("status") != "needs_human":
        return []
    errors: list[dict[str, Any]] = []
    gate = status.get("human_gate")
    reason = status.get("human_gate_reason")
    if not isinstance(reason, str) or reason.strip().lower() in VAGUE_HUMAN_REASONS:
        errors.append({"task_dir": str(task_dir), "field": "human_gate_reason", "reason": "missing_or_vague_reason"})
    if not isinstance(gate, dict):
        errors.append({"task_dir": str(task_dir), "field": "human_gate", "reason": "missing_structured_human_gate"})
        return errors
    required = [
        "policy_version",
        "trigger",
        "severity",
        "reason",
        "required_human_decision",
        "available_decisions",
        "default_safe_action",
        "retry_behavior",
        "ledger_update_behavior",
    ]
    for field in required:
        if field not in gate or not gate[field]:
            errors.append({"task_dir": str(task_dir), "field": f"human_gate.{field}", "reason": "required_field_missing"})
    if not isinstance(gate.get("available_decisions"), list) or not gate.get("available_decisions"):
        errors.append({"task_dir": str(task_dir), "field": "human_gate.available_decisions", "reason": "clear_decisions_required"})
    if gate.get("trigger") not in POLICY_BY_TRIGGER:
        errors.append({"task_dir": str(task_dir), "field": "human_gate.trigger", "reason": "unknown_policy_trigger"})
    return errors


def scan_needs_human(ops_dir: Path) -> tuple[dict[str, Any], int]:
    if not ops_dir.exists():
        return {"ok": False, "reason": "ops_dir_missing", "ops_dir": str(ops_dir)}, MALFORMED
    errors: list[dict[str, Any]] = []
    scanned = 0
    for status_path in sorted((ops_dir / "tasks").glob("*/status.json")):
        try:
            status = load_json(status_path)
        except ValueError as exc:
            errors.append({"status_path": str(status_path), "reason": "status_load_failed", "error": str(exc)})
            continue
        if not isinstance(status, dict):
            errors.append({"status_path": str(status_path), "reason": "status_not_object"})
            continue
        scanned += 1
        errors.extend(structured_human_gate_errors(status, status_path.parent))
    return {
        "ok": not errors,
        "action": "needs_human_scanned",
        "ops_dir": str(ops_dir),
        "task_count": scanned,
        "error_count": len(errors),
        "errors": errors,
    }, SUCCESS if not errors else ESCALATION_REQUIRED


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate deterministic escalation policy rules.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list", help="Print the escalation policy trigger table as JSON.")

    scan = subparsers.add_parser("scan-needs-human", help="Validate that needs_human tasks have structured gates.")
    scan.add_argument("ops_dir", type=Path)

    evaluate = subparsers.add_parser("evaluate", help="Evaluate one task against deterministic escalation triggers.")
    evaluate.add_argument("task_dir", type=Path)
    evaluate.add_argument("--ops-dir", type=Path)
    evaluate.add_argument("--apply", action="store_true", help="Write needs_human status when escalation is required.")
    evaluate.add_argument("--now", help="Override current time for deterministic tests.")
    evaluate.add_argument("--source-freshness-days", type=int, default=90)
    evaluate.add_argument("--reviewer-disagreement-threshold", type=int, default=2)
    evaluate.add_argument("--confidence-threshold", type=float, default=0.85)
    return parser.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    if args.command == "list":
        print_json({"ok": True, "policy_version": FRAMEWORK_VERSION, "triggers": POLICY_ROWS})
        return SUCCESS
    if args.command == "scan-needs-human":
        payload, code = scan_needs_human(args.ops_dir)
        print_json(payload)
        return code
    if args.command == "evaluate":
        payload, code = evaluate_task(args)
        print_json(payload)
        return code
    print_json({"ok": False, "reason": "unknown_command"})
    return MALFORMED


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
