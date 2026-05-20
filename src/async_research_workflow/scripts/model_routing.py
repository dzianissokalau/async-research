#!/usr/bin/env python3
"""Validate provider-neutral model routing policies for research roles."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any, Iterable

from async_research_workflow.resources import schema_path
from async_research_workflow.scripts import runtime_evals
from async_research_workflow.scripts.validate_json_artifact import load_json
from async_research_workflow.scripts.validate_json_artifact import validate


SUCCESS = 0
VALIDATION_FAILED = 2
INVALID_REQUEST = 3
MALFORMED = 4

SCHEMA_NAME = "model_routing_policy.schema.json"
SCHEMA_VERSION = "1.0"
FRAMEWORK_VERSION = "model_routing_policy_v1.0"
DEFAULT_POLICY_ID = "repo_first_model_routing_v1"
DEFAULT_POLICY_RELATIVE_PATH = Path("prompts") / "model_routing_policy.json"
REQUIRED_ROLES = (
    "planner",
    "worker",
    "extractor",
    "methodology_reviewer",
    "skeptic_reviewer",
    "synthesizer",
)
REQUIRED_HARD_RULE_OWNERS = {
    "validators",
    "task_contracts",
    "runtime_adapter_permissions",
}
PROVIDER_MARKERS = (
    "openai",
    "anthropic",
    "claude",
    "gemini",
    "gpt-",
    "gpt_",
    "mistral",
    "cohere",
    "perplexity",
)
MODEL_TIERS = {"deterministic", "cheap", "standard", "frontier", "human"}
REASONING_EFFORTS = {"none", "low", "medium", "high", "xhigh", "human"}
ROLE_REQUIRED_FIELDS = {
    "role",
    "model_tier",
    "reasoning_effort",
    "prompt_posture",
    "budget",
    "escalation_triggers",
    "fallback",
    "hard_rules_owned_by",
    "stop_conditions",
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


def issue(reason: str, message: str, **extra: Any) -> dict[str, Any]:
    payload = {"reason": reason, "message": message}
    payload.update({key: value for key, value in extra.items() if value is not None})
    return payload


def role_policy(
    *,
    role: str,
    model_tier: str,
    reasoning_effort: str,
    prompt_posture: str,
    max_api_usd: float,
    escalation_triggers: list[str],
    fallback_tier: str,
    fallback_conditions: list[str],
    hard_rules_owned_by: list[str],
    stop_conditions: list[str],
) -> dict[str, Any]:
    return {
        "role": role,
        "model_tier": model_tier,
        "reasoning_effort": reasoning_effort,
        "prompt_posture": prompt_posture,
        "budget": {
            "max_api_usd": max_api_usd,
            "max_compute_usd": 0.0,
        },
        "escalation_triggers": escalation_triggers,
        "fallback": {
            "model_tier": fallback_tier,
            "conditions": fallback_conditions,
        },
        "hard_rules_owned_by": hard_rules_owned_by,
        "stop_conditions": stop_conditions,
    }


def default_policy(*, now: str | None = None, policy_id: str = DEFAULT_POLICY_ID) -> dict[str, Any]:
    timestamp = now or utc_now()
    validator_refs = ["validators", "task_contracts", "runtime_adapter_permissions"]
    review_refs = ["claim_verification", "result_acceptance", "deliverable_maturity"]
    roles = {
        "planner": role_policy(
            role="planner",
            model_tier="frontier",
            reasoning_effort="high",
            prompt_posture=(
                "Brief-aware planner with concise instructions; use contracts and validators for hard gates "
                "instead of repeating brittle procedural lists."
            ),
            max_api_usd=0.25,
            escalation_triggers=[
                "ambiguous broad research request",
                "private/public boundary ambiguity",
                "public claims or paid services appear in the brief",
            ],
            fallback_tier="standard",
            fallback_conditions=["maintenance task with ready brief and no new research scope"],
            hard_rules_owned_by=validator_refs,
            stop_conditions=["brief validation fails", "task contract would broaden permissions", "human gate required"],
        ),
        "worker": role_policy(
            role="worker",
            model_tier="standard",
            reasoning_effort="medium",
            prompt_posture=(
                "Bounded execution inside the task contract; runtime adapters emit traces and evidence while "
                "workflow commands own state transitions."
            ),
            max_api_usd=0.10,
            escalation_triggers=[
                "task contract lacks required runtime permission",
                "unsupported material claim would be needed",
                "budget would exceed task cap",
            ],
            fallback_tier="cheap",
            fallback_conditions=["simple extraction or formatting with validated inputs"],
            hard_rules_owned_by=validator_refs,
            stop_conditions=["runtime adapter fails closed", "claim verification blocks output", "review gate requires revision"],
        ),
        "extractor": role_policy(
            role="extractor",
            model_tier="deterministic",
            reasoning_effort="none",
            prompt_posture="Prefer deterministic parsers or cheap models for repeatable extraction from normalized evidence.",
            max_api_usd=0.0,
            escalation_triggers=[
                "source format cannot be parsed deterministically",
                "extracted spans conflict with evidence metadata",
            ],
            fallback_tier="cheap",
            fallback_conditions=["deterministic parser cannot preserve required span mapping"],
            hard_rules_owned_by=["schemas", "validators", "runtime_adapter_permissions"],
            stop_conditions=["span mapping is missing", "license/use metadata is unknown and material", "snapshot hash mismatch"],
        ),
        "methodology_reviewer": role_policy(
            role="methodology_reviewer",
            model_tier="frontier",
            reasoning_effort="high",
            prompt_posture="Use a strong independent reviewer only at methodology-sensitive gates with the evidence packet, not sibling reviews.",
            max_api_usd=0.35,
            escalation_triggers=[
                "empirical or causal result",
                "reviewer disagreement",
                "working-paper or submission-ready maturity target",
            ],
            fallback_tier="human",
            fallback_conditions=["model review cannot resolve methodology risk"],
            hard_rules_owned_by=["validators", *review_refs, "reviewer_isolation"],
            stop_conditions=["review context lacks artifacts", "independence is compromised", "human-only methodology judgment required"],
        ),
        "skeptic_reviewer": role_policy(
            role="skeptic_reviewer",
            model_tier="frontier",
            reasoning_effort="high",
            prompt_posture="Target contradictions, stale evidence, overclaiming, and unsupported citations against explicit evidence objects.",
            max_api_usd=0.30,
            escalation_triggers=[
                "contradicted claim",
                "moderate or strong public claim",
                "stale evidence reused as current fact",
            ],
            fallback_tier="human",
            fallback_conditions=["public, high-stakes, or unsupported claim risk remains after review"],
            hard_rules_owned_by=["validators", *review_refs, "accepted_memory_freshness"],
            stop_conditions=["evidence refs cannot be inspected", "claim verifier marks material claims unsupported", "human gate required"],
        ),
        "synthesizer": role_policy(
            role="synthesizer",
            model_tier="standard",
            reasoning_effort="medium",
            prompt_posture="Maturity-aware synthesis over accepted evidence only; quality claims must cite eval and review artifacts.",
            max_api_usd=0.20,
            escalation_triggers=[
                "public-facing maturity target",
                "quality comparison claim",
                "accepted evidence is stale or contradicted",
            ],
            fallback_tier="cheap",
            fallback_conditions=["weekly digest over current accepted memory only"],
            hard_rules_owned_by=["validators", "accepted_outputs_index", "claim_verification", "deliverable_maturity", "runtime_evals"],
            stop_conditions=["accepted memory is stale", "claim caps are unresolved", "eval evidence is missing for quality claims"],
        ),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "framework_version": FRAMEWORK_VERSION,
        "policy_id": policy_id,
        "created_at": timestamp,
        "updated_at": timestamp,
        "status": "candidate",
        "provider_policy": "provider_neutral",
        "hard_rules": {
            "owned_by": sorted(REQUIRED_HARD_RULE_OWNERS | {"claim_verification", "result_acceptance", "runtime_evals"}),
            "prompt_boundary": (
                "Prompts describe role posture and context needs. Validators, task contracts, runtime adapter "
                "permissions, claim verification, and eval comparison enforce hard rules."
            ),
        },
        "adoption_gate": {
            "baseline_prompt_variants_retained": True,
            "eval_compare_required": True,
            "candidate_must_match_or_improve": [
                "grounded_claim_rate",
                "unsupported_claim_rate",
                "task_success_rate",
                "accepted_output_rate",
                "freshness_failure_rate",
                "reproducibility_pass_rate",
                "cost_per_accepted_report_usd",
            ],
            "quality_claims_require_eval_evidence": True,
            "deep_research_comparisons": "out_of_scope_until_phase_10_benchmark_pack",
        },
        "cost_controls": {
            "default_max_api_usd": 0.35,
            "default_max_compute_usd": 0.0,
            "paid_calls_require_task_contract": True,
            "role_budgets": {role: route["budget"] for role, route in roles.items()},
        },
        "roles": roles,
        "known_limitations": [
            "The policy chooses capability tiers, not a proprietary provider or model name.",
            "Eval checks compare deterministic trace-driven runs; live model quality requires separately recorded calibrated runs.",
            "Human gates remain required for credentials, paid services, public claims, and unresolved product judgment.",
        ],
    }


def load_policy(path: Path) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, issue("policy_missing", "model routing policy file does not exist", path=str(path))
    except json.JSONDecodeError as exc:
        return None, issue("invalid_json", f"model routing policy JSON is malformed: {exc.msg}", path=str(path))
    except OSError as exc:
        return None, issue("policy_unreadable", str(exc), path=str(path))
    if not isinstance(payload, dict):
        return None, issue("policy_not_object", "model routing policy must be a JSON object", path=str(path))
    return payload, None


def nested_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from nested_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from nested_strings(item)


def provider_lock_findings(policy: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for text in nested_strings(policy):
        lowered = text.lower()
        if lowered == "provider_neutral":
            continue
        for marker in PROVIDER_MARKERS:
            if marker in lowered:
                findings.append(
                    issue(
                        "provider_hardcoded",
                        "model routing policy must use provider-neutral tiers rather than a proprietary provider or model name",
                        marker=marker,
                        value=text,
                    )
                )
                return findings
    return findings


def semantic_findings(policy: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    roles = policy.get("roles") if isinstance(policy.get("roles"), dict) else {}
    missing_roles = [role for role in REQUIRED_ROLES if role not in roles]
    if missing_roles:
        errors.append(issue("required_roles_missing", "model routing policy must define every required research role", roles=missing_roles))
    hard_rules = policy.get("hard_rules") if isinstance(policy.get("hard_rules"), dict) else {}
    owners = set(item for item in hard_rules.get("owned_by", []) if isinstance(item, str))
    missing_owners = sorted(REQUIRED_HARD_RULE_OWNERS - owners)
    if missing_owners:
        errors.append(issue("hard_rule_owner_missing", "hard safety rules must be owned by validators and contracts, not prompts only", owners=missing_owners))
    adoption_gate = policy.get("adoption_gate") if isinstance(policy.get("adoption_gate"), dict) else {}
    if adoption_gate.get("baseline_prompt_variants_retained") is not True:
        errors.append(issue("baseline_variants_not_retained", "old prompt variants must remain available as baselines"))
    if adoption_gate.get("eval_compare_required") is not True:
        errors.append(issue("eval_compare_not_required", "prompt and routing changes must require eval comparison before adoption"))
    if adoption_gate.get("quality_claims_require_eval_evidence") is not True:
        errors.append(issue("quality_claims_not_eval_gated", "quality claims must require eval evidence"))
    if "phase_10" not in str(adoption_gate.get("deep_research_comparisons") or "").lower():
        errors.append(issue("deep_research_comparison_gate_missing", "Deep Research-style comparisons must remain gated until Phase 10 benchmark evidence"))
    cost_controls = policy.get("cost_controls") if isinstance(policy.get("cost_controls"), dict) else {}
    if cost_controls.get("paid_calls_require_task_contract") is not True:
        errors.append(issue("paid_calls_not_contract_gated", "paid calls must require explicit task-contract permission"))
    errors.extend(provider_lock_findings(policy))
    for role, route in roles.items():
        if not isinstance(route, dict):
            errors.append(issue("role_route_not_object", "each role route must be a JSON object", role=role))
            continue
        missing_fields = sorted(field for field in ROLE_REQUIRED_FIELDS if field not in route)
        if missing_fields:
            errors.append(issue("role_required_fields_missing", "role route is missing required fields", role=role, fields=missing_fields))
        if route.get("role") != role:
            errors.append(issue("role_key_mismatch", "role object must match its roles map key", role=role))
        if route.get("model_tier") not in MODEL_TIERS:
            errors.append(issue("role_model_tier_invalid", "role model_tier must be a supported capability tier", role=role, value=route.get("model_tier")))
        if route.get("reasoning_effort") not in REASONING_EFFORTS:
            errors.append(
                issue("role_reasoning_effort_invalid", "role reasoning_effort must be one of the supported effort labels", role=role, value=route.get("reasoning_effort"))
            )
        if not isinstance(route.get("prompt_posture"), str) or not route.get("prompt_posture", "").strip():
            errors.append(issue("role_prompt_posture_missing", "role prompt_posture must describe posture without carrying hard rules", role=role))
        budget = route.get("budget") if isinstance(route.get("budget"), dict) else None
        if budget is None:
            errors.append(issue("role_budget_missing", "role route must define budget caps", role=role))
        else:
            for field in ("max_api_usd", "max_compute_usd"):
                value = budget.get(field)
                if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                    errors.append(issue("role_budget_invalid", "role budget values must be non-negative numbers", role=role, field=field, value=value))
        fallback = route.get("fallback") if isinstance(route.get("fallback"), dict) else None
        if fallback is None or fallback.get("model_tier") not in MODEL_TIERS:
            errors.append(issue("role_fallback_invalid", "role fallback must name a supported fallback model tier", role=role))
        elif not isinstance(fallback.get("conditions"), list):
            errors.append(issue("role_fallback_conditions_missing", "role fallback must list its conditions", role=role))
        for list_field in ("escalation_triggers", "hard_rules_owned_by", "stop_conditions"):
            values = route.get(list_field)
            if not isinstance(values, list) or not any(isinstance(item, str) and item.strip() for item in values):
                errors.append(issue("role_list_field_missing", "role route list field must include at least one non-empty string", role=role, field=list_field))
        route_owners = set(item for item in route.get("hard_rules_owned_by", []) if isinstance(item, str))
        if not route_owners:
            errors.append(issue("role_hard_rule_owner_missing", "each role must name deterministic hard-rule owners", role=role))
        if route.get("model_tier") == "frontier" and not route.get("escalation_triggers"):
            errors.append(issue("frontier_route_without_triggers", "frontier model routes must be tied to escalation triggers", role=role))
        if role == "extractor" and route.get("model_tier") not in {"deterministic", "cheap"}:
            errors.append(issue("extractor_too_expensive", "extractor should default to deterministic or cheap execution", role=role))
        if "validator" not in " ".join(str(item).lower() for item in route.get("hard_rules_owned_by", [])):
            warnings.append(issue("role_validator_reference_missing", "route does not explicitly reference validators as hard-rule owners", role=role))
    return errors, warnings


def validate_policy_payload(policy: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    schema_errors = [error.to_dict() for error in validate(policy, load_json(schema_path(SCHEMA_NAME)))]
    semantic_errors, warnings = semantic_findings(policy)
    return [*schema_errors, *semantic_errors], warnings


def resolve_output_path(ops_dir: Path, output: Path | None = None) -> Path | None:
    if output is None:
        candidate = ops_dir / DEFAULT_POLICY_RELATIVE_PATH
    elif output.is_absolute():
        candidate = output
    elif output.parts and output.parts[0] == ops_dir.name:
        candidate = ops_dir.parent / output
    else:
        candidate = ops_dir / output
    candidate = candidate.resolve(strict=False)
    try:
        candidate.relative_to((ops_dir / "prompts").resolve(strict=False))
    except ValueError:
        return None
    return candidate


def validate_command(args: argparse.Namespace) -> int:
    policy, load_error = load_policy(args.policy)
    if load_error is not None or policy is None:
        print_json(
            {
                "ok": False,
                "action": "model_routing_validate",
                "changed": False,
                "read_only": True,
                "policy_path": str(args.policy),
                "errors": [load_error or issue("policy_unavailable", "policy could not be loaded")],
                "warnings": [],
            }
        )
        return INVALID_REQUEST
    errors, warnings = validate_policy_payload(policy)
    print_json(
        {
            "ok": not errors,
            "action": "model_routing_validate",
            "changed": False,
            "read_only": True,
            "policy_path": str(args.policy),
            "policy_id": policy.get("policy_id"),
            "errors": errors,
            "warnings": warnings,
            "policy": policy if args.include_policy else None,
        }
    )
    return SUCCESS if not errors else VALIDATION_FAILED


def init_command(args: argparse.Namespace) -> int:
    if not args.ops_dir.is_dir():
        print_json(
            {
                "ok": False,
                "action": "model_routing_init",
                "reason": "ops_dir_missing",
                "changed": False,
                "read_only": True,
                "dry_run": not args.write,
                "errors": [issue("ops_dir_missing", "initialize research_ops before creating model routing policy", path=str(args.ops_dir))],
                "warnings": [],
            }
        )
        return INVALID_REQUEST
    output_path = resolve_output_path(args.ops_dir, args.output)
    if output_path is None:
        print_json(
            {
                "ok": False,
                "action": "model_routing_init",
                "reason": "unsafe_output_path",
                "changed": False,
                "read_only": True,
                "errors": [issue("unsafe_output_path", "model routing policy output must stay under research_ops/prompts")],
                "warnings": [],
            }
        )
        return INVALID_REQUEST
    policy = default_policy(now=args.now, policy_id=args.policy_id)
    errors, warnings = validate_policy_payload(policy)
    if errors:
        print_json(
            {
                "ok": False,
                "action": "model_routing_init",
                "reason": "default_policy_invalid",
                "changed": False,
                "read_only": True,
                "errors": errors,
                "warnings": warnings,
            }
        )
        return MALFORMED
    exists = output_path.exists()
    if exists and not args.force and args.write:
        print_json(
            {
                "ok": False,
                "action": "model_routing_init",
                "reason": "policy_exists",
                "changed": False,
                "read_only": True,
                "policy_path": str(output_path),
                "errors": [issue("policy_exists", "use --force to replace an existing model routing policy")],
                "warnings": warnings,
            }
        )
        return INVALID_REQUEST
    if args.write:
        atomic_write_json(output_path, policy)
    print_json(
        {
            "ok": True,
            "action": "model_routing_init",
            "changed": bool(args.write),
            "read_only": not args.write,
            "dry_run": not args.write,
            "policy_path": str(output_path),
            "policy_id": policy["policy_id"],
            "operation": "update" if exists else "create",
            "policy": policy,
            "errors": [],
            "warnings": warnings,
            "next_step": (
                "run async-research model-routing validate on the written policy"
                if args.write
                else "rerun with --write to create research_ops/prompts/model_routing_policy.json"
            ),
        }
    )
    return SUCCESS


def selected_escalations(args: argparse.Namespace, route: dict[str, Any]) -> list[dict[str, Any]]:
    escalations: list[dict[str, Any]] = []
    claim_strength = str(args.claim_strength or "").lower()
    if args.public_claims:
        escalations.append(issue("public_claims", "public claims require methodology or skeptic review before publication"))
    if claim_strength in {"moderate", "strong", "causal"}:
        escalations.append(issue("claim_strength", "moderate, strong, or causal claims require stronger review routing", claim_strength=claim_strength))
    if args.task_type in {"experiment_plan", "run_analysis", "evaluate_results"} and route.get("role") not in {"methodology_reviewer", "skeptic_reviewer"}:
        escalations.append(issue("methodology_sensitive_task", "methodology-sensitive work should receive methodology review", task_type=args.task_type))
    return escalations


def select_command(args: argparse.Namespace) -> int:
    policy, load_error = load_policy(args.policy)
    if load_error is not None or policy is None:
        print_json(
            {
                "ok": False,
                "action": "model_routing_select",
                "changed": False,
                "read_only": True,
                "errors": [load_error or issue("policy_unavailable", "policy could not be loaded")],
                "warnings": [],
            }
        )
        return INVALID_REQUEST
    errors, warnings = validate_policy_payload(policy)
    if errors:
        print_json(
            {
                "ok": False,
                "action": "model_routing_select",
                "changed": False,
                "read_only": True,
                "policy_id": policy.get("policy_id"),
                "errors": errors,
                "warnings": warnings,
            }
        )
        return VALIDATION_FAILED
    roles = policy.get("roles") if isinstance(policy.get("roles"), dict) else {}
    route = roles.get(args.role)
    if not isinstance(route, dict):
        print_json(
            {
                "ok": False,
                "action": "model_routing_select",
                "reason": "unknown_role",
                "changed": False,
                "read_only": True,
                "role": args.role,
                "available_roles": sorted(roles),
                "errors": [issue("unknown_role", "role is not defined in the model routing policy", role=args.role)],
                "warnings": warnings,
            }
        )
        return INVALID_REQUEST
    escalations = selected_escalations(args, route)
    print_json(
        {
            "ok": True,
            "action": "model_routing_select",
            "changed": False,
            "read_only": True,
            "policy_id": policy.get("policy_id"),
            "role": args.role,
            "task_type": args.task_type,
            "route": route,
            "recommended_escalations": escalations,
            "warnings": warnings,
            "errors": [],
        }
    )
    return SUCCESS


def eval_check_command(args: argparse.Namespace) -> int:
    policy, load_error = load_policy(args.policy)
    if load_error is not None or policy is None:
        print_json(
            {
                "ok": False,
                "action": "model_routing_eval_check",
                "changed": False,
                "read_only": True,
                "errors": [load_error or issue("policy_unavailable", "policy could not be loaded")],
                "warnings": [],
            }
        )
        return INVALID_REQUEST
    errors, warnings = validate_policy_payload(policy)
    if errors:
        print_json(
            {
                "ok": False,
                "action": "model_routing_eval_check",
                "changed": False,
                "read_only": True,
                "policy_id": policy.get("policy_id"),
                "errors": errors,
                "warnings": warnings,
            }
        )
        return VALIDATION_FAILED
    compare_code, compare_report = runtime_evals.compare_runs(
        args.baseline,
        args.candidate,
        cost_tolerance_usd=args.cost_tolerance_usd,
    )
    candidate, candidate_error = runtime_evals.load_json_required(args.candidate)
    policy_id = str(policy.get("policy_id") or "")
    policy_mismatch = None
    if candidate_error is None and isinstance(candidate, dict):
        candidate_policy = str(candidate.get("model_routing_policy") or "")
        if candidate_policy != policy_id:
            policy_mismatch = issue(
                "candidate_policy_mismatch",
                "candidate eval run must record the policy_id being adopted",
                expected=policy_id,
                actual=candidate_policy,
            )
    adoption_errors = list(compare_report.get("errors", []) if isinstance(compare_report.get("errors"), list) else [])
    if policy_mismatch is not None:
        adoption_errors.append(policy_mismatch)
    ok = compare_code == SUCCESS and not adoption_errors
    print_json(
        {
            "ok": ok,
            "action": "model_routing_eval_check",
            "verdict": "pass" if ok else "fail",
            "changed": False,
            "read_only": True,
            "policy_id": policy_id,
            "baseline": str(args.baseline),
            "candidate": str(args.candidate),
            "adoption_eligible": ok,
            "compare": compare_report,
            "errors": adoption_errors,
            "warnings": warnings,
            "next_step": (
                "policy can be activated only through the normal prompt or schedule change process"
                if ok
                else "keep the current prompt/routing baseline and fix the candidate before adoption"
            ),
        }
    )
    return SUCCESS if ok else VALIDATION_FAILED


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate provider-neutral model routing policy and eval adoption gates.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="Create a default model routing policy under research_ops/prompts.")
    init.add_argument("ops_dir", type=Path)
    init.add_argument("--output", type=Path, help="Output path under research_ops/prompts.")
    init.add_argument("--policy-id", default=DEFAULT_POLICY_ID, help="Stable policy id recorded in eval runs.")
    init.add_argument("--write", action="store_true", help="Write the policy. Without this, the command is read-only.")
    init.add_argument("--force", action="store_true", help="Replace an existing policy when writing.")
    init.add_argument("--now", help="Override timestamps for deterministic fixtures.")
    init.set_defaults(func=init_command)

    validate_cmd = subparsers.add_parser("validate", help="Validate one model routing policy JSON file.")
    validate_cmd.add_argument("policy", type=Path)
    validate_cmd.add_argument("--include-policy", action="store_true", help="Echo the validated policy in the JSON output.")
    validate_cmd.set_defaults(func=validate_command)

    select = subparsers.add_parser("select", help="Select the configured route for one role.")
    select.add_argument("policy", type=Path)
    select.add_argument("--role", required=True, choices=REQUIRED_ROLES)
    select.add_argument("--task-type", default="literature_extract")
    select.add_argument("--claim-strength", default="")
    select.add_argument("--public-claims", action="store_true")
    select.set_defaults(func=select_command)

    eval_check = subparsers.add_parser("eval-check", help="Check whether a candidate routing policy can be adopted.")
    eval_check.add_argument("policy", type=Path)
    eval_check.add_argument("--baseline", required=True, type=Path, help="Baseline eval run JSON.")
    eval_check.add_argument("--candidate", required=True, type=Path, help="Candidate eval run JSON.")
    eval_check.add_argument("--cost-tolerance-usd", type=float, default=0.0)
    eval_check.set_defaults(func=eval_check_command)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv or []))
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
