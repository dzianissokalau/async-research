#!/usr/bin/env python3
"""Mode-aware policy resolver for structured needs_human task gates."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from async_research_workflow.scripts.interaction_mode import (
    ALL_INTERRUPT_CATEGORIES,
    HARD_STOP_INTERRUPT_CATEGORIES,
    inspect_mode_config,
)
from async_research_workflow.scripts.validate_transition import ALLOWED


POLICY_VERSION = "mode_needs_human_policy_v1.0"
POLICY_ACTOR = "async-research-mode-policy"
AUTO_MUTATION_MODES = {"supervised", "autonomous", "publication_guarded"}
MANUAL_COMPATIBLE_MODES = {"manual", "guided"}
KNOWN_GATE_CATEGORIES = set(ALL_INTERRUPT_CATEGORIES)
HARD_STOP_CATEGORIES = set(HARD_STOP_INTERRUPT_CATEGORIES)

GATE_CATEGORY_BY_TRIGGER = {
    "required_source_unaudited": "source_governance_missing",
    "source_freshness_expired": "source_freshness_or_approval",
    "accepted_memory_conflict": "result_acceptance_missing",
    "reviewer_disagreement_beyond_threshold": "review_disagreement",
    "high_confidence_weak_evidence": "quality_uncertainty",
    "task_exceeds_budget": "hard_budget_breach",
    "revision_limit_hit": "revision_limit_reached",
    "strategic_or_business_action": "legal_policy_sensitive_claim",
    "accepted_memory_lacks_citations": "source_governance_missing",
    "ambiguous_task_contract": "quality_uncertainty",
    "unauthorized_scope_change": "quality_uncertainty",
    "unverifiable_hidden_assumptions": "quality_uncertainty",
}

ACTION_BY_TRIGGER = {
    "accepted_memory_conflict": {
        "decision": "pause",
        "target_status": "paused",
        "policy_action": "park_accepted_memory_conflict",
        "instruction": "pause until accepted-memory conflict is reconciled",
        "required_auto_decision": None,
        "available_aliases": {"pause"},
    },
    "ambiguous_task_contract": {
        "decision": "pause",
        "target_status": "paused",
        "policy_action": "park_ambiguous_task_contract",
        "instruction": "pause because safe worker progress requires a clearer task contract",
        "required_auto_decision": None,
        "available_aliases": {"pause"},
    },
    "required_source_unaudited": {
        "decision": "pause",
        "target_status": "paused",
        "policy_action": "park_unaudited_source",
        "instruction": "pause because source governance evidence is missing",
        "required_auto_decision": None,
        "available_aliases": {"pause", "request_data_readiness"},
    },
    "revision_limit_hit": {
        "decision": "pause",
        "target_status": "paused",
        "policy_action": "park_revision_limit",
        "instruction": "pause because the revision limit is exhausted and must not be reset automatically",
        "required_auto_decision": None,
        "available_aliases": {"pause", "reject"},
    },
    "unauthorized_scope_change": {
        "decision": "pause",
        "target_status": "paused",
        "policy_action": "park_unauthorized_scope_change",
        "instruction": "pause before continuing outside the authorized task scope",
        "required_auto_decision": None,
        "available_aliases": {"pause"},
    },
}

ACTION_BY_CATEGORY = {
    "quality_uncertainty": {
        "decision": "resume",
        "target_status": "ready_for_worker",
        "policy_action": "bounded_revision",
        "instruction": "resume only for a bounded revision that fixes quality uncertainty before acceptance",
        "required_auto_decision": "allow_revision",
        "available_aliases": {"resume", "request_revision", "revise"},
    },
    "source_freshness_or_approval": {
        "decision": "resume",
        "target_status": "ready_for_worker",
        "policy_action": "refresh_or_substitute_source",
        "instruction": "resume only to refresh, substitute an already-approved source, or downgrade the claim",
        "required_auto_decision": "allow_source_substitution",
        "available_aliases": {"resume", "refresh_source", "request_revision"},
    },
    "source_governance_missing": {
        "decision": "resume",
        "target_status": "ready_for_worker",
        "policy_action": "bounded_source_governance_revision",
        "instruction": "resume only to add approved-source evidence, substitute approved sources, or downgrade the claim",
        "required_auto_decision": "allow_source_substitution",
        "available_aliases": {"resume", "request_revision", "refresh_source"},
    },
    "review_disagreement": {
        "decision": "resume",
        "target_status": "ready_for_worker",
        "policy_action": "bounded_review_revision",
        "instruction": "resume only for bounded revision or adjudication; do not accept disputed output",
        "required_auto_decision": "allow_revision",
        "available_aliases": {"resume", "request_revision"},
    },
    "revision_limit_reached": {
        "decision": "pause",
        "target_status": "paused",
        "policy_action": "park_revision_limit",
        "instruction": "pause instead of resetting revision limits automatically",
        "required_auto_decision": None,
        "available_aliases": {"pause", "reject"},
    },
    "idea_prioritization_ambiguity": {
        "decision": "resume",
        "target_status": "ready_for_worker",
        "policy_action": "apply_idea_prioritization_policy",
        "instruction": "resume only to apply configured idea scoring or park low-confidence ideas",
        "required_auto_decision": "allow_idea_prioritization",
        "available_aliases": {"resume", "park", "reject", "promote"},
    },
    "budget_warning": {
        "decision": "resume",
        "target_status": "ready_for_worker",
        "policy_action": "narrow_budget_scope",
        "instruction": "resume only to narrow scope or choose cheaper approved work before a budget breach",
        "required_auto_decision": "allow_resume",
        "available_aliases": {"resume", "pause"},
    },
    "result_acceptance_missing": {
        "decision": "pause",
        "target_status": "paused",
        "policy_action": "park_missing_result_acceptance",
        "instruction": "pause because result acceptance evidence cannot be skipped",
        "required_auto_decision": None,
        "available_aliases": {"pause", "reject"},
    },
    "deliverable_maturity_missing": {
        "decision": "pause",
        "target_status": "paused",
        "policy_action": "park_missing_deliverable_maturity",
        "instruction": "pause because deliverable maturity gates cannot be skipped",
        "required_auto_decision": None,
        "available_aliases": {"pause", "reject"},
    },
}


def normalize_key(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def normalized_available_decisions(gate: dict[str, Any]) -> set[str]:
    values = gate.get("available_decisions")
    if not isinstance(values, list):
        return set()
    return {normalize_key(value) for value in values if normalize_key(value)}


def categories_for_gate(gate: dict[str, Any]) -> list[str]:
    raw_values: list[Any] = []
    if gate.get("gate_category") is not None:
        raw_values.append(gate.get("gate_category"))
    if isinstance(gate.get("gate_categories"), list):
        raw_values.extend(gate.get("gate_categories", []))
    trigger = normalize_key(gate.get("trigger"))
    if trigger in GATE_CATEGORY_BY_TRIGGER:
        raw_values.append(GATE_CATEGORY_BY_TRIGGER[trigger])
    if isinstance(gate.get("triggered_triggers"), list):
        for item in gate.get("triggered_triggers", []):
            mapped = GATE_CATEGORY_BY_TRIGGER.get(normalize_key(item))
            if mapped:
                raw_values.append(mapped)

    categories: list[str] = []
    for value in raw_values:
        category = normalize_key(value)
        if category and category not in categories:
            categories.append(category)
    return categories


def constraint_summary(status: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_status": status.get("status"),
        "revision_count": status.get("revision_count"),
        "max_revisions": status.get("max_revisions"),
        "revision_limit_hit": status.get("revision_limit_hit"),
        "data_audit_refs": status.get("data_audit_refs", []),
        "budget": status.get("budget", {}),
        "review_policy": status.get("review_policy", {}),
        "result_recommendation": (status.get("result") or {}).get("recommendation")
        if isinstance(status.get("result"), dict)
        else None,
    }


def blocked_result(reason: str, **payload: Any) -> dict[str, Any]:
    return {
        "ok": False,
        "policy_version": POLICY_VERSION,
        "can_auto_resolve": False,
        "human_required": True,
        "reason": reason,
        **payload,
    }


def action_for_gate(gate: dict[str, Any], category: str) -> dict[str, Any] | None:
    trigger = normalize_key(gate.get("trigger"))
    if trigger in ACTION_BY_TRIGGER:
        return ACTION_BY_TRIGGER[trigger]
    return ACTION_BY_CATEGORY.get(category)


def action_is_available(gate: dict[str, Any], action: dict[str, Any]) -> bool:
    available = normalized_available_decisions(gate)
    if not available:
        return True
    decision = normalize_key(action.get("decision"))
    aliases = {normalize_key(value) for value in action.get("available_aliases", set())}
    return bool(available & ({decision} | aliases))


def evaluate_policy(ops_dir: Path, task_dir: Path, status: dict[str, Any]) -> dict[str, Any]:
    mode_report = inspect_mode_config(ops_dir)
    base = {
        "action": "mode_policy_evaluated",
        "task_dir": str(task_dir),
        "ops_dir": str(ops_dir),
        "mode_config": {
            "ok": mode_report.get("ok"),
            "reason": mode_report.get("reason"),
            "path": mode_report.get("path"),
            "defaulted": mode_report.get("defaulted"),
            "config_present": mode_report.get("config_present"),
        },
        "constraint_summary": constraint_summary(status),
    }

    if status.get("status") != "needs_human":
        return blocked_result(
            "task_not_needs_human",
            status=status.get("status"),
            **base,
        )

    if not mode_report.get("ok"):
        return blocked_result(
            "mode_config_invalid",
            errors=mode_report.get("errors", []),
            warnings=mode_report.get("warnings", []),
            **base,
        )

    config = mode_report.get("config") if isinstance(mode_report.get("config"), dict) else {}
    mode = normalize_key(config.get("mode"))
    risk_tolerance = normalize_key(config.get("risk_tolerance"))
    base.update({"mode": mode, "risk_tolerance": risk_tolerance})

    if mode in MANUAL_COMPATIBLE_MODES:
        return blocked_result(
            "manual_mode_requires_explicit_human_decision",
            **base,
        )
    if mode not in AUTO_MUTATION_MODES:
        return blocked_result(
            "mode_does_not_allow_auto_resolution",
            **base,
        )

    gate = status.get("human_gate")
    if not isinstance(gate, dict):
        return blocked_result(
            "missing_structured_human_gate",
            **base,
        )

    categories = categories_for_gate(gate)
    category = categories[0] if categories else ""
    base.update(
        {
            "gate_category": category or None,
            "gate_categories": categories,
            "gate_trigger": gate.get("trigger"),
            "gate_severity": gate.get("severity"),
        }
    )

    unknown = [item for item in categories if item not in KNOWN_GATE_CATEGORIES]
    if not category or unknown:
        return blocked_result(
            "unknown_gate_category",
            unknown_gate_categories=unknown,
            **base,
        )

    if category in HARD_STOP_CATEGORIES or any(item in HARD_STOP_CATEGORIES for item in categories):
        return blocked_result(
            "hard_stop_category_requires_human",
            hard_stop_categories=sorted(item for item in categories if item in HARD_STOP_CATEGORIES),
            **base,
        )

    interrupt_policy = config.get("interrupt_policy") if isinstance(config.get("interrupt_policy"), dict) else {}
    interrupt_only_for = {
        normalize_key(item)
        for item in interrupt_policy.get("interrupt_only_for", [])
        if normalize_key(item)
    }
    if category in interrupt_only_for:
        return blocked_result(
            "mode_interrupt_policy_requires_human",
            interrupt_only_for=sorted(interrupt_only_for),
            **base,
        )

    action = action_for_gate(gate, category)
    if action is None:
        return blocked_result(
            "no_policy_route_for_gate_category",
            **base,
        )

    auto_decisions = config.get("auto_decisions") if isinstance(config.get("auto_decisions"), dict) else {}
    required_auto_decision = action.get("required_auto_decision")
    if required_auto_decision and auto_decisions.get(required_auto_decision) is not True:
        return blocked_result(
            "auto_decision_not_enabled",
            required_auto_decision=required_auto_decision,
            **base,
        )

    target_status = str(action["target_status"])
    if target_status not in ALLOWED.get("needs_human", set()):
        return blocked_result(
            "policy_target_transition_not_allowed",
            target_status=target_status,
            allowed=sorted(ALLOWED.get("needs_human", set())),
            **base,
        )

    if not action_is_available(gate, action):
        return blocked_result(
            "gate_available_decisions_do_not_allow_policy_route",
            available_decisions=sorted(normalized_available_decisions(gate)),
            policy_decision=action["decision"],
            policy_action=action["policy_action"],
            **base,
        )

    audit_reason = (
        f"{POLICY_VERSION}; mode={mode}; category={category}; "
        f"action={action['policy_action']}; {action['instruction']}"
    )
    return {
        "ok": True,
        "policy_version": POLICY_VERSION,
        "can_auto_resolve": True,
        "human_required": False,
        "reason": "policy_allows_auto_resolution",
        "decision": action["decision"],
        "target_status": target_status,
        "policy_action": action["policy_action"],
        "instruction": action["instruction"],
        "required_auto_decision": required_auto_decision,
        "actor": POLICY_ACTOR,
        "confidence": "high",
        "audit_reason": audit_reason,
        "allowed_transition": "needs_human -> " + target_status,
        **base,
    }
