#!/usr/bin/env python3
"""Apply mission-weighted scoring to an async research idea candidate."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from async_research_workflow.scripts.cost_tracking import cost_window, ledger_path
from async_research_workflow.scripts.validate_json_artifact import load_json, validate
from async_research_workflow.scripts.validate_mission_policy import validate_policy_contract
from async_research_workflow.resources import mission_policy_path, schema_path


SUCCESS = 0
VALIDATION_FAILED = 2
INVALID_REQUEST = 3
MALFORMED = 4

DEFAULT_POLICY = mission_policy_path()
DEFAULT_SCHEMA = schema_path("idea_candidate.schema.json")
SCHEMA_VERSION = "1.0"

DIMENSIONS = [
    "decision_impact",
    "data_availability",
    "killability",
    "feasibility",
    "reuse_potential",
    "novelty",
    "robustness_risk",
    "cost",
]

PROMOTABLE_NEXT_TASKS = {"hypothesis_card", "data_readiness", "literature_extract"}
SCORE_BUDGET_MODES = {"normal", "budget_constrained"}
SEVERE_GATES = {
    "research_question_present",
    "data_path_identified",
    "minimum_viable_test_present",
    "baseline_or_comparison_present",
    "kill_reason_present",
}


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def non_empty_list(value: Any) -> bool:
    return isinstance(value, list) and any(str(item).strip() for item in value)


def dimension_value(score: dict[str, Any], name: str) -> int:
    raw = score.get(name)
    if name == "decision_impact" and raw is None:
        raw = score.get("impact")
    if not isinstance(raw, int) or isinstance(raw, bool) or not 1 <= raw <= 5:
        raise ValueError(f"score.{name} must be an integer from 1 to 5")
    return raw


def policy_version(policy: dict[str, Any]) -> str:
    version = policy.get("mission_policy_version")
    if not non_empty_string(version):
        raise ValueError("mission_policy_version is missing from policy")
    return str(version)


def policy_weights(policy: dict[str, Any]) -> dict[str, float]:
    weights = policy.get("weights")
    if not isinstance(weights, dict):
        raise ValueError("policy.weights must be an object")
    parsed: dict[str, float] = {}
    for dimension in DIMENSIONS:
        raw = weights.get(dimension)
        if not isinstance(raw, (int, float)) or isinstance(raw, bool):
            raise ValueError(f"policy.weights.{dimension} must be numeric")
        parsed[dimension] = float(raw)
    return parsed


def promotion_policy(policy: dict[str, Any], budget_mode: str) -> dict[str, Any]:
    promotion = policy.get("promotion")
    if not isinstance(promotion, dict):
        raise ValueError("policy.promotion must be an object")
    selected = promotion.get(budget_mode)
    if not isinstance(selected, dict):
        raise ValueError(f"policy.promotion.{budget_mode} must be an object")
    return selected


def budget_pressure_policy(policy: dict[str, Any]) -> dict[str, Any]:
    pressure = policy.get("budget_pressure")
    if not isinstance(pressure, dict):
        return {
            "threshold": 0.8,
            "default_mode": "normal",
            "constrained_mode": "budget_constrained",
        }
    threshold = pressure.get("threshold", 0.8)
    default_mode = pressure.get("default_mode", "normal")
    constrained_mode = pressure.get("constrained_mode", "budget_constrained")
    if not isinstance(threshold, (int, float)) or isinstance(threshold, bool) or threshold <= 0:
        raise ValueError("policy.budget_pressure.threshold must be positive")
    if default_mode not in SCORE_BUDGET_MODES:
        raise ValueError("policy.budget_pressure.default_mode must be a scoring budget mode")
    if constrained_mode not in SCORE_BUDGET_MODES:
        raise ValueError("policy.budget_pressure.constrained_mode must be a scoring budget mode")
    return {
        "threshold": float(threshold),
        "default_mode": str(default_mode),
        "constrained_mode": str(constrained_mode),
    }


def numeric_policy_value(policy: dict[str, Any], key: str) -> float:
    raw = policy.get(key)
    if not isinstance(raw, (int, float)) or isinstance(raw, bool):
        raise ValueError(f"promotion policy {key} must be numeric")
    return float(raw)


def integer_policy_value(policy: dict[str, Any], key: str) -> int:
    raw = policy.get(key)
    if not isinstance(raw, int) or isinstance(raw, bool):
        raise ValueError(f"promotion policy {key} must be an integer")
    return raw


def optional_integer_policy_value(policy: dict[str, Any], key: str, default: int) -> int:
    raw = policy.get(key, default)
    if not isinstance(raw, int) or isinstance(raw, bool):
        raise ValueError(f"promotion policy {key} must be an integer")
    return raw


def budget_usage_summary(window: Optional[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(window, dict):
        return {
            "monthly_usage_ratio": None,
            "weekly_usage_ratio": None,
            "monthly_cost_usd": 0.0,
            "weekly_cost_usd": 0.0,
            "monthly_budget_usd": None,
            "weekly_budget_usd": None,
        }
    return {
        "monthly_usage_ratio": window.get("monthly_usage_ratio"),
        "weekly_usage_ratio": window.get("weekly_usage_ratio"),
        "monthly_cost_usd": window.get("monthly_cost_usd", 0.0),
        "weekly_cost_usd": window.get("weekly_cost_usd", 0.0),
        "monthly_budget_usd": window.get("monthly_budget_usd"),
        "weekly_budget_usd": window.get("weekly_budget_usd"),
    }


def resolve_budget_mode(
    requested_mode: str,
    policy: dict[str, Any],
    ops_dir: Optional[Path],
    monthly_budget_usd: Optional[float],
    weekly_budget_usd: Optional[float],
    budget_threshold: Optional[float],
) -> tuple[str, dict[str, Any]]:
    if requested_mode != "auto":
        pressure = budget_pressure_policy(policy)
        return requested_mode, {
            "reason": f"manual_{requested_mode}",
            "threshold": budget_threshold if budget_threshold is not None else pressure["threshold"],
            "budget_usage": budget_usage_summary(None),
        }

    pressure = budget_pressure_policy(policy)
    threshold = budget_threshold if budget_threshold is not None else pressure["threshold"]
    if threshold <= 0:
        raise ValueError("budget threshold must be positive")

    if ops_dir is None:
        return pressure["default_mode"], {
            "reason": "auto_default_no_ops_dir",
            "threshold": threshold,
            "budget_usage": budget_usage_summary(None),
        }

    window = cost_window(ledger_path(ops_dir), datetime.now(timezone.utc), monthly_budget_usd, weekly_budget_usd)
    ratios = [
        ratio
        for ratio in (window.get("monthly_usage_ratio"), window.get("weekly_usage_ratio"))
        if isinstance(ratio, (int, float)) and not isinstance(ratio, bool)
    ]
    constrained = bool(ratios) and max(ratios) >= threshold
    mode = pressure["constrained_mode"] if constrained else pressure["default_mode"]
    return mode, {
        "reason": "auto_budget_threshold_exceeded" if constrained else "auto_budget_available",
        "threshold": threshold,
        "budget_usage": budget_usage_summary(window),
    }


def gate_result(gate: str, passed: bool, reason: str) -> dict[str, Any]:
    return {"gate": gate, "passed": passed, "reason": reason}


def hard_gate_results(candidate: dict[str, Any], dimensions: dict[str, int], minimum_killability: int) -> list[dict[str, Any]]:
    return [
        gate_result(
            "research_question_present",
            non_empty_string(candidate.get("question")),
            "question is present" if non_empty_string(candidate.get("question")) else "missing research question",
        ),
        gate_result(
            "data_path_identified",
            non_empty_list(candidate.get("required_data")) and dimensions["data_availability"] >= 2,
            "data path is identified" if non_empty_list(candidate.get("required_data")) and dimensions["data_availability"] >= 2 else "no credible data path yet",
        ),
        gate_result(
            "minimum_viable_test_present",
            non_empty_string(candidate.get("minimum_viable_test")),
            "minimum viable test is present" if non_empty_string(candidate.get("minimum_viable_test")) else "missing minimum viable test",
        ),
        gate_result(
            "baseline_or_comparison_present",
            non_empty_string(candidate.get("baseline")),
            "baseline is present" if non_empty_string(candidate.get("baseline")) else "missing baseline or comparison",
        ),
        gate_result(
            "kill_reason_present",
            non_empty_string(candidate.get("kill_reason")),
            "kill reason is present" if non_empty_string(candidate.get("kill_reason")) else "missing kill reason",
        ),
        gate_result(
            "minimum_killability_met",
            dimensions["killability"] >= minimum_killability,
            f"killability {dimensions['killability']} >= {minimum_killability}"
            if dimensions["killability"] >= minimum_killability
            else f"killability {dimensions['killability']} < {minimum_killability}",
        ),
    ]


def direct_experiment_gate(requested_task: Any, routed_task: str) -> dict[str, Any]:
    blocked = routed_task != "experiment_plan"
    if requested_task == "experiment_plan" and blocked:
        reason = f"requested experiment_plan was rerouted to {routed_task}"
    elif blocked:
        reason = "next task is not direct experiment planning"
    else:
        reason = "discovery may not promote directly to experiment planning"
    return gate_result("direct_experiment_blocked", blocked, reason)


def failed_gate_names(results: Iterable[dict[str, Any]]) -> list[str]:
    return [str(item.get("gate")) for item in results if item.get("passed") is not True]


def route_candidate(
    candidate: dict[str, Any],
    weighted_total: float,
    promotion_threshold: float,
    park_threshold: float,
    gates: list[dict[str, Any]],
) -> tuple[str, str]:
    failed = failed_gate_names(gates)
    requested = candidate.get("recommended_next_task")

    if any(gate in SEVERE_GATES for gate in failed):
        return "reject", "reject"
    if "minimum_killability_met" in failed:
        return "park", "park"
    if requested == "experiment_plan":
        requested = "data_readiness"

    if weighted_total >= promotion_threshold:
        next_task = requested if requested in PROMOTABLE_NEXT_TASKS else "data_readiness"
        return "promote", str(next_task)
    if weighted_total >= park_threshold:
        return "park", "park"
    return "reject", "reject"


def explanation(weighted_total: float, status: str, failed: list[str], version: str, budget_mode: str) -> str:
    if failed:
        if status == "promote":
            gate_text = ", ".join(failed)
            return (
                f"Mission policy {version} in {budget_mode} mode gives weighted_total={weighted_total:.2f}; "
                f"route={status} after routing adjustment because gates were noted: {gate_text}."
            )
        gate_text = ", ".join(failed)
        return (
            f"Mission policy {version} in {budget_mode} mode gives weighted_total={weighted_total:.2f}; "
            f"route={status} because hard gates failed: {gate_text}."
        )
    return (
        f"Mission policy {version} in {budget_mode} mode gives weighted_total={weighted_total:.2f}; "
        f"route={status} because mission-weighted score and hard gates allow it."
    )


def score_candidate(
    candidate: dict[str, Any],
    policy: dict[str, Any],
    budget_mode: str,
    budget_context: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    if not isinstance(candidate.get("score"), dict):
        raise ValueError("candidate.score must be an object")

    version = policy_version(policy)
    weights = policy_weights(policy)
    selected_policy = promotion_policy(policy, budget_mode)
    promotion_threshold = numeric_policy_value(selected_policy, "promotion_threshold")
    park_threshold = numeric_policy_value(selected_policy, "park_threshold")
    minimum_killability = integer_policy_value(selected_policy, "minimum_killability")
    max_promotions_per_week = optional_integer_policy_value(selected_policy, "max_promotions_per_week", 3)
    pressure_context = budget_context or {
        "reason": f"manual_{budget_mode}",
        "threshold": budget_pressure_policy(policy)["threshold"],
        "budget_usage": budget_usage_summary(None),
    }

    raw_score = candidate["score"]
    dimensions = {dimension: dimension_value(raw_score, dimension) for dimension in DIMENSIONS}
    weighted_total = round(sum(dimensions[name] * weights[name] for name in DIMENSIONS), 2)
    preliminary_gates = hard_gate_results(candidate, dimensions, minimum_killability)
    status, next_task = route_candidate(candidate, weighted_total, promotion_threshold, park_threshold, preliminary_gates)
    gates = preliminary_gates + [direct_experiment_gate(candidate.get("recommended_next_task"), next_task)]
    failed = failed_gate_names(gates)

    updated = dict(candidate)
    updated["schema_version"] = SCHEMA_VERSION
    updated["status"] = status
    updated["recommended_next_task"] = next_task
    updated_score = dict(raw_score)
    updated_score.pop("impact", None)
    updated_score.update(dimensions)
    updated_score.update(
        {
            "mission_policy_version": version,
            "budget_mode": budget_mode,
            "weighted_total": weighted_total,
            "promotion_threshold": promotion_threshold,
            "minimum_killability": minimum_killability,
            "max_promotions_per_week": max_promotions_per_week,
            "budget_pressure_threshold": pressure_context["threshold"],
            "budget_mode_reason": pressure_context["reason"],
            "budget_usage": pressure_context["budget_usage"],
            "hard_gate_results": gates,
            "score_explanation": explanation(weighted_total, status, failed, version, budget_mode),
        }
    )
    updated["score"] = updated_score
    return updated


def validate_candidate(candidate: dict[str, Any], schema_path: Path) -> tuple[int, list[dict[str, Any]]]:
    schema = load_json(schema_path)
    if not isinstance(schema, dict):
        return MALFORMED, [{"path": "$", "message": f"schema is not an object: {schema_path}"}]
    errors = [error.to_dict() for error in validate(candidate, schema)]
    if errors:
        return VALIDATION_FAILED, errors
    return SUCCESS, []


def run_score(args: argparse.Namespace) -> int:
    try:
        candidate = load_json(args.candidate)
        policy = load_json(args.policy)
    except ValueError as exc:
        print_json({"ok": False, "reason": "malformed_or_missing", "error": str(exc)})
        return MALFORMED

    if not isinstance(candidate, dict):
        print_json({"ok": False, "reason": "candidate_not_object", "candidate": str(args.candidate)})
        return MALFORMED
    if not isinstance(policy, dict):
        print_json({"ok": False, "reason": "policy_not_object", "policy": str(args.policy)})
        return MALFORMED

    policy_errors, policy_warnings = validate_policy_contract(policy)
    if policy_errors:
        print_json(
            {
                "ok": False,
                "reason": "mission_policy_validation_failed",
                "errors": policy_errors,
                "warnings": policy_warnings,
                "policy": str(args.policy),
            }
        )
        return VALIDATION_FAILED

    try:
        resolved_budget_mode, budget_context = resolve_budget_mode(
            args.budget_mode,
            policy,
            args.ops_dir,
            args.monthly_budget_usd,
            args.weekly_budget_usd,
            args.budget_threshold,
        )
        scored = score_candidate(candidate, policy, resolved_budget_mode, budget_context)
    except ValueError as exc:
        print_json({"ok": False, "reason": "scoring_failed", "error": str(exc), "candidate": str(args.candidate)})
        return INVALID_REQUEST

    code, errors = validate_candidate(scored, args.schema)
    if code != SUCCESS:
        print_json({"ok": False, "reason": "candidate_validation_failed", "errors": errors, "candidate": str(args.candidate)})
        return code

    if not args.dry_run:
        output = args.output if args.output is not None else args.candidate
        atomic_write_json(output, scored)

    print_json(
        {
            "ok": True,
            "action": "dry_run_scored" if args.dry_run else "scored",
            "candidate": str(args.candidate),
            "mission_policy_version": scored["score"]["mission_policy_version"],
            "budget_mode": scored["score"]["budget_mode"],
            "requested_budget_mode": args.budget_mode,
            "budget_mode_reason": scored["score"].get("budget_mode_reason"),
            "weighted_total": scored["score"]["weighted_total"],
            "status": scored["status"],
            "recommended_next_task": scored["recommended_next_task"],
            "minimum_killability": scored["score"]["minimum_killability"],
            "max_promotions_per_week": scored["score"]["max_promotions_per_week"],
            "failed_hard_gates": failed_gate_names(scored["score"]["hard_gate_results"]),
            "policy_warnings": policy_warnings,
        }
    )
    return SUCCESS


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply mission-weighted scoring to an idea candidate.")
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--budget-mode", choices=["normal", "budget_constrained", "auto"], default="normal")
    parser.add_argument("--ops-dir", type=Path, help="research_ops directory for automatic budget pressure detection")
    parser.add_argument("--monthly-budget-usd", type=float)
    parser.add_argument("--weekly-budget-usd", type=float)
    parser.add_argument("--budget-threshold", type=float)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    return run_score(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
