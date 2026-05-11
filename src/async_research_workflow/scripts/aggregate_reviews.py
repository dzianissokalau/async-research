#!/usr/bin/env python3
"""Deterministically aggregate async research review decisions."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from async_research_workflow.resources import schema_path
from async_research_workflow.scripts.validate_json_artifact import load_json, validate
from async_research_workflow.scripts.validate_result_acceptance import (
    validate_result_acceptance_for_task,
)
from async_research_workflow.scripts.validate_transition import validate_payload
from async_research_workflow.scripts.version_metadata import (
    apply_default_versions,
    version_summary,
)


SUCCESS = 0
VALIDATION_FAILED = 2
MISSING_REQUIRED = 3
MALFORMED = 4

REVIEWER_ROLES = {"primary", "methodology", "skeptic"}
ACCEPTING = {"accept", "accept_with_caveats"}
DECISIONS = ACCEPTING | {"needs_revision", "needs_human", "reject"}
CLAIM_STRENGTHS = {"none", "weak", "suggestive", "moderate", "strong"}
CLAIM_STRENGTH_ORDER = ["none", "weak", "suggestive", "moderate", "strong"]
CLAIM_STRENGTH_POLICY = "weakest_current_review"
AGGREGATE_DECISIONS = {"accepted", "needs_revision", "needs_human", "paused", "rejected"}

DEFAULT_REQUIRED_REVIEWERS = {
    0: [],
    1: ["primary"],
    2: ["primary", "methodology"],
    3: ["primary", "methodology", "skeptic"],
}
DEFAULT_MAX_REVISIONS = {
    0: 1,
    1: 1,
    2: 2,
    3: 1,
}

AGGREGATE_SCHEMA = schema_path("review_panel.schema.json")
STATUS_SCHEMA = schema_path("task_status.schema.json")
SCHEMA_VERSION = "1.0"


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def print_json(payload: dict) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def load_status(task_dir: Path) -> dict[str, Any]:
    path = task_dir / "status.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"status file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"status file is not an object: {path}")
    return payload


def review_tier(status: dict[str, Any]) -> int:
    policy = status.get("review_policy")
    if isinstance(policy, dict):
        tier = policy.get("tier")
        if isinstance(tier, int) and not isinstance(tier, bool) and 0 <= tier <= 3:
            return tier
    return 1


def required_reviewers(status: dict[str, Any], tier: int) -> list[str]:
    policy = status.get("review_policy")
    reviewers = None
    if isinstance(policy, dict):
        reviewers = policy.get("required_reviewers")
    if isinstance(reviewers, list):
        roles = [role for role in reviewers if isinstance(role, str) and role in REVIEWER_ROLES]
        if roles:
            return sorted(set(roles), key=roles.index)
    return list(DEFAULT_REQUIRED_REVIEWERS.get(tier, ["primary"]))


def normalize_revision_fields(status: dict[str, Any], tier: int) -> None:
    if not isinstance(status.get("revision_count"), int) or isinstance(status.get("revision_count"), bool):
        status["revision_count"] = 0
    if not isinstance(status.get("max_revisions"), int) or isinstance(status.get("max_revisions"), bool):
        status["max_revisions"] = DEFAULT_MAX_REVISIONS.get(tier, 1)
    if not isinstance(status.get("revision_limit_hit"), bool):
        status["revision_limit_hit"] = False


def extract_json_object(text: str) -> Any:
    for match in re.finditer(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE):
        candidate = match.group(1).strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue

    start = text.find("{")
    if start == -1:
        raise ValueError("no JSON object found")

    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : index + 1])

    raise ValueError("unterminated JSON object")


def read_review(path: Path) -> dict[str, Any]:
    try:
        payload = extract_json_object(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read review: {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"review JSON malformed: {path}: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError(f"review payload is not an object: {path}")
    return payload


def validate_review(path: Path, review: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    role = review.get("reviewer_role")
    decision = review.get("decision")
    claim_strength = review.get("claim_strength")
    prompt_version = review.get("prompt_version")
    framework_versions = review.get("framework_versions")
    confidence = review.get("confidence")
    requested_tier = review.get("escalate_to_tier")
    escalation_reason = review.get("escalation_reason")

    if role not in REVIEWER_ROLES:
        errors.append(f"{path}: reviewer_role must be one of {sorted(REVIEWER_ROLES)}")
    if decision not in DECISIONS:
        errors.append(f"{path}: decision must be one of {sorted(DECISIONS)}")
    if claim_strength not in CLAIM_STRENGTHS:
        errors.append(f"{path}: claim_strength must be one of {sorted(CLAIM_STRENGTHS)}")
    if not isinstance(prompt_version, str) or not prompt_version.strip():
        errors.append(f"{path}: prompt_version is required")
    if not isinstance(framework_versions, dict):
        errors.append(f"{path}: framework_versions must be an object")
    elif not isinstance(framework_versions.get("result_acceptance"), str) or not framework_versions.get("result_acceptance", "").strip():
        errors.append(f"{path}: framework_versions.result_acceptance is required")
    if not isinstance(review.get("main_concerns"), list):
        errors.append(f"{path}: main_concerns must be an array")
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= confidence <= 1:
        errors.append(f"{path}: confidence must be a number between 0 and 1")
    if requested_tier is not None:
        if not isinstance(requested_tier, int) or isinstance(requested_tier, bool) or not 0 <= requested_tier <= 3:
            errors.append(f"{path}: escalate_to_tier must be null or an integer from 0 to 3")
        if not isinstance(escalation_reason, str) or not escalation_reason.strip():
            errors.append(f"{path}: escalation_reason is required when escalate_to_tier is set")
    return errors


def load_reviews(task_dir: Path) -> tuple[dict[str, dict[str, Any]], list[str]]:
    reviews: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    reviews_dir = task_dir / "reviews"
    for path in sorted(reviews_dir.glob("*.md")):
        try:
            review = read_review(path)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        errors.extend(validate_review(path, review))
        role = review.get("reviewer_role")
        if isinstance(role, str) and role in REVIEWER_ROLES:
            reviews[role] = review
    return reviews, errors


def human_required_for_acceptance(status: dict[str, Any], reviews: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    policy = status.get("review_policy")
    if isinstance(policy, dict) and policy.get("human_required_for_acceptance") is True:
        reasons.append("review_policy_requires_human_acceptance")
    if status.get("requires_human") is True:
        reasons.append("status_requires_human")
    if any(review.get("claim_strength") == "strong" for review in reviews):
        reasons.append("strong_claim_requires_human")
    return bool(reasons), reasons


def review_summary_values(reviews: list[dict[str, Any]], key: str) -> list[str]:
    values: list[str] = []
    for review in reviews:
        raw = review.get(key)
        if isinstance(raw, list):
            values.extend(str(item) for item in raw if str(item).strip())
    return values


def unresolved_escalation_requests(reviews: Iterable[dict[str, Any]], tier: int) -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = []
    for review in reviews:
        requested_tier = review.get("escalate_to_tier")
        if isinstance(requested_tier, int) and not isinstance(requested_tier, bool) and requested_tier > tier:
            requests.append(
                {
                    "reviewer_role": review.get("reviewer_role"),
                    "requested_tier": requested_tier,
                    "reason": review.get("escalation_reason"),
                }
            )
    return requests


def escalation_summary(status: dict[str, Any]) -> dict[str, Any]:
    target_tier = status.get("escalate_to_tier")
    if not isinstance(target_tier, int) or isinstance(target_tier, bool):
        target_tier = None
    reason = status.get("escalation_reason")
    requested_by = status.get("escalation_requested_by")
    requested_at = status.get("escalation_requested_at")
    return {
        "requested": target_tier is not None,
        "target_tier": target_tier,
        "reason": reason if isinstance(reason, str) else None,
        "requested_by": requested_by if isinstance(requested_by, str) else None,
        "requested_at": requested_at if isinstance(requested_at, str) else None,
    }


def compute_route(
    tier: int,
    status: dict[str, Any],
    ordered_reviews: list[dict[str, Any]],
) -> tuple[str, str, bool, list[str], list[str], list[str]]:
    decisions = [str(review.get("decision")) for review in ordered_reviews]
    human_gate, human_reasons = human_required_for_acceptance(status, ordered_reviews)
    agreements: list[str] = []
    disagreements: list[str] = []
    trace: list[str] = [f"tier={tier}", f"decisions={','.join(decisions)}"]

    if decisions and all(decision in ACCEPTING for decision in decisions):
        agreements.append("All required reviewers accepted or accepted with caveats.")
    else:
        disagreements.append("Reviewer decisions are not unanimous acceptance.")

    if "reject" in decisions:
        trace.append("reject_blocks_acceptance")
        return "rejected", "reviewer_rejected", False, agreements, disagreements, trace

    if "needs_human" in decisions:
        trace.append("needs_human_routes_to_human")
        return "needs_human", "reviewer_requested_human", True, agreements, disagreements, trace

    if "needs_revision" in decisions:
        trace.append("needs_revision_routes_to_revision")
        return "needs_revision", "reviewer_requested_revision", False, agreements, disagreements, trace

    if decisions and all(decision in ACCEPTING for decision in decisions):
        if human_gate:
            trace.extend(human_reasons)
            return "needs_human", "human_gate_required_before_acceptance", True, agreements, disagreements, trace
        return "accepted", "all_required_reviewers_accept", False, agreements, disagreements, trace

    trace.append("no_deterministic_acceptance_path")
    return "needs_human", "aggregation_rule_fell_through", True, agreements, disagreements, trace


def apply_revision_limit(status: dict[str, Any], route: str, reason: str, tier: int) -> tuple[str, str, bool]:
    normalize_revision_fields(status, tier)
    if route != "needs_revision":
        return route, reason, bool(status.get("revision_limit_hit"))

    revision_count = int(status["revision_count"])
    max_revisions = int(status["max_revisions"])
    if revision_count >= max_revisions:
        status["revision_limit_hit"] = True
        status["requires_human"] = True
        status["human_gate_reason"] = f"reviewers requested revision after {revision_count}/{max_revisions} allowed revisions"
        return "needs_human", "revision_limit_exceeded", True

    status["revision_count"] = revision_count + 1
    status["revision_limit_hit"] = status["revision_count"] >= max_revisions
    return route, reason, bool(status["revision_limit_hit"])


def current_claim_strength(reviews: list[dict[str, Any]]) -> str:
    strengths = [str(review.get("claim_strength")) for review in reviews if review.get("claim_strength") in CLAIM_STRENGTHS]
    if not strengths:
        return "none"
    return min(strengths, key=CLAIM_STRENGTH_ORDER.index)


def review_start_status_for_tier(tier: int) -> str:
    return "single_review" if tier <= 1 else "panel_review"


def record_review_start_status(status: dict[str, Any], tier: int) -> dict[str, Any]:
    updated = apply_default_versions(dict(status))
    normalize_revision_fields(updated, tier)
    transition_time = iso_now()
    updated["previous_status"] = status.get("status")
    updated["status"] = review_start_status_for_tier(tier)
    updated["last_transition_reason"] = "review_start_recorded_before_aggregate"
    updated["updated_at"] = transition_time
    if not str(updated.get("review_started_at") or "").strip():
        updated["review_started_at"] = transition_time
    return updated


def mark_claim_strength_stale(result: dict[str, Any], reason: str) -> None:
    result["claim_strength"] = None
    result["claim_strength_stale"] = True
    result["claim_strength_revalidation_required"] = True
    result["claim_strength_revalidation_reason"] = reason
    result["claim_strength_revalidated_at"] = None
    result["claim_strength_policy"] = CLAIM_STRENGTH_POLICY


def mark_claim_strength_current(result: dict[str, Any], claim_strength: str) -> None:
    result["claim_strength"] = claim_strength
    result["claim_strength_stale"] = False
    result["claim_strength_revalidation_required"] = False
    result["claim_strength_revalidation_reason"] = None
    result["claim_strength_revalidated_at"] = iso_now()
    result["claim_strength_policy"] = CLAIM_STRENGTH_POLICY


def update_status(
    status: dict[str, Any],
    route: str,
    reason: str,
    human_gate_required: bool,
    tier: int,
    claim_strength: str,
) -> dict[str, Any]:
    updated = dict(status)
    updated.setdefault("schema_version", SCHEMA_VERSION)
    apply_default_versions(updated)
    if status.get("status") in {"single_review", "panel_review"} and not str(updated.get("review_started_at") or "").strip():
        started_at = status.get("updated_at")
        if isinstance(started_at, str) and started_at.strip():
            updated["review_started_at"] = started_at
    updated["previous_status"] = status.get("status")
    updated["status"] = route
    updated["last_transition_reason"] = f"aggregate_reviews_{reason}"
    transition_time = iso_now()
    updated["updated_at"] = transition_time

    if human_gate_required or route == "needs_human":
        updated["requires_human"] = True
        if not str(updated.get("human_gate_opened_at") or "").strip():
            updated["human_gate_opened_at"] = transition_time
        if not updated.get("human_gate_reason"):
            updated["human_gate_reason"] = reason

    result = dict(updated.get("result") or {})
    recommendation = {
        "accepted": "ready",
        "needs_revision": "needs_revision",
        "needs_human": "needs_human",
        "rejected": "reject",
        "paused": "blocked",
    }.get(route)
    if recommendation:
        result["recommendation"] = recommendation
    if route == "needs_revision" or reason == "revision_limit_exceeded":
        mark_claim_strength_stale(result, reason)
    elif route in {"accepted", "needs_human", "rejected"}:
        mark_claim_strength_current(result, claim_strength)
    updated["result"] = result

    normalize_revision_fields(updated, tier)
    return updated


def validate_payload_with_schema(payload: dict[str, Any], schema_path: Path) -> tuple[int, list[dict[str, Any]]]:
    schema = load_json(schema_path)
    if not isinstance(schema, dict):
        return MALFORMED, [{"path": "$", "message": f"schema is not an object: {schema_path}"}]
    errors = [error.to_dict() for error in validate(payload, schema)]
    if errors:
        return VALIDATION_FAILED, errors
    return SUCCESS, []


def validate_status(status: dict[str, Any]) -> tuple[int, list[dict[str, Any]]]:
    code, errors = validate_payload_with_schema(status, STATUS_SCHEMA)
    if code != SUCCESS:
        return code, errors
    transition_code, transition_result = validate_payload(status)
    if transition_code != SUCCESS:
        return VALIDATION_FAILED, [transition_result]
    return SUCCESS, []


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def write_markdown(path: Path, aggregate: dict[str, Any]) -> None:
    escalation = aggregate.get("escalation") if isinstance(aggregate.get("escalation"), dict) else {}
    lines = [
        f"# Review Aggregate: {aggregate['task_id']}",
        "",
        f"Decision: {aggregate['aggregate_decision']}",
        f"Routing reason: {aggregate['routing_reason']}",
        f"Human gate required: {str(aggregate['human_gate_required']).lower()}",
        f"Escalation: {format_escalation(escalation)}",
        "",
        "## Reviews",
    ]
    for review in aggregate["reviews"]:
        lines.append(f"- {review['reviewer_role']}: {review['decision']} ({review['claim_strength']}, confidence {review['confidence']})")
    lines.extend(["", "## Agreements"])
    lines.extend(f"- {item}" for item in aggregate.get("agreements", []) or ["none"])
    lines.extend(["", "## Disagreements"])
    lines.extend(f"- {item}" for item in aggregate.get("disagreements", []) or ["none"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def format_escalation(escalation: dict[str, Any]) -> str:
    if not escalation.get("requested"):
        return "none"
    target = escalation.get("target_tier")
    reason = escalation.get("reason") or "no reason recorded"
    requested_by = escalation.get("requested_by") or "unknown requester"
    return f"Tier {target} requested by {requested_by}: {reason}"


def aggregate_reviews(task_dir: Path, dry_run: bool, record_review_start: bool = False) -> int:
    if not task_dir.exists() or not task_dir.is_dir():
        print_json({"ok": False, "reason": "task_dir_missing", "task_dir": str(task_dir)})
        return MALFORMED

    try:
        status = load_status(task_dir)
    except ValueError as exc:
        print_json({"ok": False, "reason": "status_load_failed", "error": str(exc), "task_dir": str(task_dir)})
        return MALFORMED

    tier = review_tier(status)
    required = required_reviewers(status, tier)
    reviews_by_role, review_errors = load_reviews(task_dir)
    if review_errors:
        print_json({"ok": False, "reason": "review_validation_failed", "errors": review_errors, "task_dir": str(task_dir)})
        return VALIDATION_FAILED

    unresolved_escalations = unresolved_escalation_requests(reviews_by_role.values(), tier)
    if unresolved_escalations:
        print_json(
            {
                "ok": False,
                "reason": "review_requested_higher_tier",
                "escalation_requests": unresolved_escalations,
                "current_tier": tier,
                "task_dir": str(task_dir),
                "next_step": "run escalate_review_tier.py apply <task-dir> --to-tier <tier> --reason <reason>",
            }
        )
        return MISSING_REQUIRED

    missing = [role for role in required if role not in reviews_by_role]
    if missing:
        print_json(
            {
                "ok": False,
                "reason": "missing_required_reviews",
                "missing_required_reviews": missing,
                "required_reviewers": required,
                "task_dir": str(task_dir),
            }
        )
        return MISSING_REQUIRED

    ordered_roles = required + [role for role in sorted(reviews_by_role) if role not in required]
    ordered_reviews = [reviews_by_role[role] for role in ordered_roles]
    route, reason, human_gate_required, agreements, disagreements, trace = compute_route(tier, status, ordered_reviews)
    aggregate_claim_strength = current_claim_strength(ordered_reviews)

    base_status = dict(status)
    review_start_transition: Optional[dict[str, Any]] = None
    if status.get("status") == "awaiting_review" and record_review_start and route in AGGREGATE_DECISIONS:
        base_status = record_review_start_status(status, tier)
        start_status_code, start_status_errors = validate_status(base_status)
        if start_status_code != SUCCESS:
            print_json(
                {
                    "ok": False,
                    "reason": "review_start_validation_failed",
                    "errors": start_status_errors,
                    "task_dir": str(task_dir),
                    "attempted_review_start_status": base_status.get("status"),
                }
            )
            return start_status_code
        review_start_transition = {
            "from_status": status.get("status"),
            "to_status": base_status.get("status"),
            "reason": base_status.get("last_transition_reason"),
            "recorded_before_aggregate": not dry_run,
        }
        trace.append(f"review_start_recorded={base_status.get('status')}")

    mutable_status = dict(base_status)
    route, reason, revision_limit_hit = apply_revision_limit(mutable_status, route, reason, tier)
    already_at_route = base_status.get("status") == route
    if already_at_route:
        updated_status = apply_default_versions(dict(base_status))
        normalize_revision_fields(updated_status, tier)
    else:
        updated_status = update_status(mutable_status, route, reason, human_gate_required, tier, aggregate_claim_strength)

    aggregate = {
        "schema_version": SCHEMA_VERSION,
        **version_summary(apply_default_versions(dict(status))),
        "task_id": status.get("id", task_dir.name),
        "tier": tier,
        "required_reviewers": required,
        "missing_required_reviews": [],
        "reviews": ordered_reviews,
        "aggregate_decision": route,
        "routing_reason": reason,
        "aggregate_claim_strength": aggregate_claim_strength,
        "claim_strength_policy": CLAIM_STRENGTH_POLICY,
        "human_gate_required": human_gate_required or route == "needs_human",
        "revision_limit_hit": revision_limit_hit,
        "agreements": agreements,
        "disagreements": disagreements,
        "escalation": escalation_summary(status),
        "rule_trace": trace,
    }
    if review_start_transition is not None:
        aggregate["review_start_transition"] = review_start_transition

    aggregate_code, aggregate_errors = validate_payload_with_schema(aggregate, AGGREGATE_SCHEMA)
    if aggregate_code != SUCCESS:
        print_json({"ok": False, "reason": "aggregate_validation_failed", "errors": aggregate_errors, "task_dir": str(task_dir)})
        return aggregate_code

    status_code, status_errors = validate_status(updated_status)
    if status_code != SUCCESS:
        payload = {"ok": False, "reason": "status_validation_failed", "errors": status_errors, "task_dir": str(task_dir)}
        if status.get("status") == "awaiting_review" and route in {"accepted", "needs_revision", "paused", "rejected"}:
            intermediate = review_start_status_for_tier(tier)
            payload.update(
                {
                    "current_status": "awaiting_review",
                    "attempted_route": route,
                    "suggested_intermediate_status": intermediate,
                    "next_step": (
                        f"record the review-start transition awaiting_review -> {intermediate}, "
                        "or rerun async-research review aggregate with --record-review-start"
                    ),
                }
            )
        print_json(payload)
        return status_code

    result_acceptance: Optional[dict[str, Any]] = None
    if route in {"accepted", "rejected"}:
        result_acceptance = validate_result_acceptance_for_task(task_dir, updated_status, aggregate)
        if not result_acceptance.get("ok"):
            print_json(
                {
                    "ok": False,
                    "reason": "result_acceptance_validation_failed",
                    "errors": result_acceptance.get("hard_gate_failures", []),
                    "task_dir": str(task_dir),
                    "route": route,
                    "next_step": "revise worker output, lower claim strength, route to needs_human, or reject",
                }
            )
            return VALIDATION_FAILED

    if not dry_run:
        atomic_write_json(task_dir / "review_panel" / "aggregate.json", aggregate)
        write_markdown(task_dir / "review_panel" / "aggregate.md", aggregate)
        atomic_write_json(task_dir / "status.json", updated_status)
        if result_acceptance is not None:
            validate_result_acceptance_for_task(
                task_dir,
                updated_status,
                aggregate,
                write=True,
                update_ledger_files=True,
            )

    print_json(
        {
            "ok": True,
            "action": "dry_run_aggregated" if dry_run else "aggregated",
            "task_dir": str(task_dir),
            "aggregate_decision": route,
            "routing_reason": reason,
            "human_gate_required": aggregate["human_gate_required"],
            "revision_limit_hit": revision_limit_hit,
            "review_start_transition": review_start_transition,
        }
    )
    return SUCCESS


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deterministically aggregate async research reviews.")
    parser.add_argument("task_dir", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--record-review-start",
        action="store_true",
        help="When a reviewed task is still awaiting_review, validate and record the missing single_review/panel_review transition before aggregating.",
    )
    return parser.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    return aggregate_reviews(args.task_dir, args.dry_run, args.record_review_start)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
