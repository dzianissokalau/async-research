"""Shared prompt and framework version defaults for workflow helpers."""

from __future__ import annotations

from typing import Any


DEFAULT_PROMPT_VERSIONS = {
    "planner": "planner_v1.0",
    "discovery_scout": "discovery_scout_v1.0",
    "worker": "worker_v1.0",
    "primary_reviewer": "primary_reviewer_v1.0",
    "methodology_reviewer": "methodology_reviewer_v1.0",
    "skeptic_reviewer": "skeptic_reviewer_v1.0",
    "deliverable_critic": "deliverable_critic_v1.0",
    "review_aggregator": "review_aggregator_v1.0",
    "weekly_synthesizer": "weekly_synthesizer_v1.0",
    "health_monitor": "health_monitor_v1.0",
}

DEFAULT_FRAMEWORK_VERSIONS = {
    "mission_scoring": "mission_scoring_v1.0",
    "idea_evaluation": "idea_evaluation_v1.0",
    "experimentation": "experimentation_v1.0",
    "exploration": "exploration_v1.0",
    "result_acceptance": "result_acceptance_v1.0",
    "review_aggregation": "review_aggregation_v1.0",
    "accepted_outputs_index": "accepted_outputs_index_v1.0",
    "schema_versioning": "schema_versioning_v1.0",
    "data_source_audit": "data_source_audit_v1.0",
    "escalation_policy": "escalation_policy_v1.0",
    "model_routing": "model_routing_policy_v1.0",
}


def normalized_versions(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): str(item)
        for key, item in value.items()
        if isinstance(key, str) and key.strip() and isinstance(item, str) and item.strip()
    }


def apply_default_versions(payload: dict[str, Any]) -> dict[str, Any]:
    prompt_versions = normalized_versions(payload.get("prompt_versions"))
    for key, value in DEFAULT_PROMPT_VERSIONS.items():
        prompt_versions.setdefault(key, value)
    payload["prompt_versions"] = prompt_versions

    framework_versions = normalized_versions(payload.get("framework_versions"))
    for key, value in DEFAULT_FRAMEWORK_VERSIONS.items():
        framework_versions.setdefault(key, value)
    payload["framework_versions"] = framework_versions
    return payload


def version_summary(payload: dict[str, Any]) -> dict[str, dict[str, str]]:
    return {
        "prompt_versions": normalized_versions(payload.get("prompt_versions")),
        "framework_versions": normalized_versions(payload.get("framework_versions")),
    }
