#!/usr/bin/env python3
"""Validate mission_scoring_v1.0 policy files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from validate_json_artifact import load_json, validate
from async_research_workflow.resources import schema_path


SUCCESS = 0
VALIDATION_FAILED = 2
MALFORMED = 4

SCHEMA = schema_path("mission_policy.schema.json")
SCORING_DIMENSIONS = {
    "decision_impact",
    "data_availability",
    "killability",
    "feasibility",
    "reuse_potential",
    "novelty",
    "robustness_risk",
    "cost",
}
POSITIVE_DIMENSIONS = {
    "decision_impact",
    "data_availability",
    "killability",
    "feasibility",
    "reuse_potential",
    "novelty",
}
PENALTY_DIMENSIONS = {"robustness_risk", "cost"}
MISSION_DIMENSIONS = {
    "quality_robustness",
    "decision_usefulness",
    "feasibility",
    "cost_efficiency",
    "novelty",
    "autonomy",
    "speed",
}
REQUIRED_HARD_GATES = {
    "research_question_present",
    "data_path_identified",
    "minimum_viable_test_present",
    "baseline_or_comparison_present",
    "kill_reason_present",
    "minimum_killability_met",
    "direct_experiment_blocked",
}
REQUIRED_APPROVALS = {
    "mission_policy_change",
    "public_or_high_stakes_claim",
    "expensive_compute_or_paid_data",
    "private_scraped_or_sensitive_data",
}


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def schema_errors(policy: dict[str, Any], schema_path: Path) -> list[dict[str, str]]:
    schema = load_json(schema_path)
    if not isinstance(schema, dict):
        return [{"path": "$", "message": f"schema is not an object: {schema_path}"}]
    return [error.to_dict() for error in validate(policy, schema)]


def promotion_errors(policy: dict[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    promotion = policy.get("promotion")
    if not isinstance(promotion, dict):
        return [{"gate": "promotion_policy", "message": "promotion must be an object"}]
    normal = promotion.get("normal")
    constrained = promotion.get("budget_constrained")
    if not isinstance(normal, dict) or not isinstance(constrained, dict):
        return [{"gate": "promotion_policy", "message": "normal and budget_constrained modes are required"}]

    for mode, config in (("normal", normal), ("budget_constrained", constrained)):
        promotion_threshold = config.get("promotion_threshold")
        park_threshold = config.get("park_threshold")
        max_promotions = config.get("max_promotions_per_week")
        if is_number(promotion_threshold) and is_number(park_threshold) and park_threshold > promotion_threshold:
            errors.append({"gate": "promotion_policy", "message": f"{mode}.park_threshold cannot exceed promotion_threshold"})
        if isinstance(max_promotions, int) and max_promotions < 0:
            errors.append({"gate": "promotion_policy", "message": f"{mode}.max_promotions_per_week cannot be negative"})

    comparisons = [
        ("promotion_threshold", ">="),
        ("park_threshold", ">="),
        ("minimum_killability", ">="),
    ]
    for key, _relation in comparisons:
        normal_value = normal.get(key)
        constrained_value = constrained.get(key)
        if is_number(normal_value) and is_number(constrained_value) and constrained_value < normal_value:
            errors.append({"gate": "budget_constrained_policy", "message": f"budget_constrained.{key} must be >= normal.{key}"})
    normal_promotions = normal.get("max_promotions_per_week")
    constrained_promotions = constrained.get("max_promotions_per_week")
    if isinstance(normal_promotions, int) and isinstance(constrained_promotions, int) and constrained_promotions > normal_promotions:
        errors.append(
            {
                "gate": "budget_constrained_policy",
                "message": "budget_constrained.max_promotions_per_week must be <= normal.max_promotions_per_week",
            }
        )
    return errors


def budget_pressure_errors(policy: dict[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    pressure = policy.get("budget_pressure")
    promotion = policy.get("promotion")
    if not isinstance(pressure, dict):
        return [{"gate": "budget_pressure", "message": "budget_pressure must be an object"}]
    threshold = pressure.get("threshold")
    if not is_number(threshold) or threshold <= 0 or threshold > 1:
        errors.append({"gate": "budget_pressure", "message": "budget_pressure.threshold must be > 0 and <= 1"})
    modes = set(promotion.keys()) if isinstance(promotion, dict) else set()
    for field in ("default_mode", "constrained_mode"):
        value = pressure.get(field)
        if value not in modes:
            errors.append({"gate": "budget_pressure", "message": f"budget_pressure.{field} must reference a promotion mode"})
    if pressure.get("default_mode") == pressure.get("constrained_mode"):
        errors.append({"gate": "budget_pressure", "message": "default_mode and constrained_mode must differ"})
    return errors


def validate_policy_contract(policy: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    errors.extend({"gate": "schema", "message": item["message"], "path": item["path"]} for item in schema_errors(policy, SCHEMA))

    weights = policy.get("weights")
    if not isinstance(weights, dict):
        errors.append({"gate": "weights", "message": "weights must be an object"})
    else:
        keys = set(weights)
        if keys != SCORING_DIMENSIONS:
            errors.append(
                {
                    "gate": "weights",
                    "message": "weights must match the scoring dimensions exactly",
                    "missing": sorted(SCORING_DIMENSIONS - keys),
                    "extra": sorted(keys - SCORING_DIMENSIONS),
                }
            )
        for dimension in sorted(SCORING_DIMENSIONS & keys):
            value = weights.get(dimension)
            if not is_number(value):
                errors.append({"gate": "weights", "message": f"weights.{dimension} must be numeric"})
            elif dimension in POSITIVE_DIMENSIONS and value <= 0:
                errors.append({"gate": "weights", "message": f"weights.{dimension} must be positive"})
            elif dimension in PENALTY_DIMENSIONS and value >= 0:
                errors.append({"gate": "weights", "message": f"weights.{dimension} must be negative"})
        if all(is_number(weights.get(dimension)) for dimension in SCORING_DIMENSIONS):
            if weights["novelty"] > weights["decision_impact"]:
                errors.append({"gate": "mission_alignment", "message": "novelty weight cannot exceed decision_impact"})
            if weights["novelty"] > weights["data_availability"]:
                errors.append({"gate": "mission_alignment", "message": "novelty weight cannot exceed data_availability"})
            if weights["novelty"] > weights["killability"]:
                errors.append({"gate": "mission_alignment", "message": "novelty weight cannot exceed killability"})
            if abs(weights["robustness_risk"]) < weights["novelty"]:
                errors.append({"gate": "mission_alignment", "message": "robustness_risk penalty must be at least as strong as novelty"})
            if abs(weights["cost"]) < weights["novelty"]:
                errors.append({"gate": "mission_alignment", "message": "cost penalty must be at least as strong as novelty"})

    dimension_map = policy.get("dimension_map")
    if not isinstance(dimension_map, dict):
        errors.append({"gate": "dimension_map", "message": "dimension_map must be an object"})
    else:
        keys = set(dimension_map)
        if keys != SCORING_DIMENSIONS:
            errors.append(
                {
                    "gate": "dimension_map",
                    "message": "dimension_map must map every scoring dimension exactly once",
                    "missing": sorted(SCORING_DIMENSIONS - keys),
                    "extra": sorted(keys - SCORING_DIMENSIONS),
                }
            )
        covered: set[str] = set()
        for dimension in sorted(SCORING_DIMENSIONS & keys):
            refs = dimension_map.get(dimension)
            if not isinstance(refs, list) or not refs:
                errors.append({"gate": "dimension_map", "message": f"dimension_map.{dimension} must be a non-empty list"})
                continue
            invalid = [ref for ref in refs if ref not in MISSION_DIMENSIONS]
            if invalid:
                errors.append({"gate": "dimension_map", "message": f"dimension_map.{dimension} has unknown mission dimensions", "details": invalid})
            covered.update(ref for ref in refs if ref in MISSION_DIMENSIONS)
        missing_mission_dimensions = MISSION_DIMENSIONS - covered
        if missing_mission_dimensions:
            warnings.append(
                {
                    "gate": "dimension_map",
                    "message": "some mission dimensions are not represented in candidate scoring",
                    "details": sorted(missing_mission_dimensions),
                }
            )

    hard_gates = policy.get("hard_gates")
    if not isinstance(hard_gates, list):
        errors.append({"gate": "hard_gates", "message": "hard_gates must be an array"})
    else:
        missing_hard_gates = REQUIRED_HARD_GATES - set(str(item) for item in hard_gates)
        if missing_hard_gates:
            errors.append({"gate": "hard_gates", "message": "required hard gates are missing", "missing": sorted(missing_hard_gates)})

    approvals = policy.get("human_approval_required_for")
    if not isinstance(approvals, list):
        errors.append({"gate": "human_approval", "message": "human_approval_required_for must be an array"})
    else:
        missing_approvals = REQUIRED_APPROVALS - set(str(item) for item in approvals)
        if missing_approvals:
            errors.append({"gate": "human_approval", "message": "required human approval thresholds are missing", "missing": sorted(missing_approvals)})

    calibration = policy.get("calibration")
    if isinstance(calibration, dict):
        required_inputs = calibration.get("required_inputs")
        if isinstance(required_inputs, list):
            missing_inputs = {"accepted_outputs_index", "rejected_ideas", "cost_ledger"} - set(str(item) for item in required_inputs)
            if missing_inputs:
                errors.append({"gate": "calibration", "message": "calibration inputs are missing", "missing": sorted(missing_inputs)})

    errors.extend(promotion_errors(policy))
    errors.extend(budget_pressure_errors(policy))
    return errors, warnings


def parse_policy(path: Path) -> dict[str, Any]:
    payload = load_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"mission policy is not an object: {path}")
    return payload


def run_validate(args: argparse.Namespace) -> int:
    try:
        policy = parse_policy(args.policy)
    except ValueError as exc:
        print_json({"ok": False, "reason": "mission_policy_load_failed", "error": str(exc), "policy": str(args.policy)})
        return MALFORMED

    errors, warnings = validate_policy_contract(policy)
    ok = not errors
    print_json(
        {
            "ok": ok,
            "action": "validated" if ok else "validation_failed",
            "policy": str(args.policy),
            "mission_id": policy.get("mission_id"),
            "mission_policy_version": policy.get("mission_policy_version"),
            "framework_version": policy.get("framework_version"),
            "weight_count": len(policy.get("weights", {})) if isinstance(policy.get("weights"), dict) else 0,
            "hard_gate_count": len(policy.get("hard_gates", [])) if isinstance(policy.get("hard_gates"), list) else 0,
            "errors": errors,
            "warnings": warnings,
        }
    )
    return SUCCESS if ok else VALIDATION_FAILED


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a mission_scoring_v1.0 policy file.")
    parser.add_argument("policy", type=Path)
    return parser.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    return run_validate(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
