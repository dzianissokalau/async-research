#!/usr/bin/env python3
"""Validate and attach idea_evaluation_v1.0 records to scored candidates."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from async_research_workflow.resources import schema_path
from async_research_workflow.scripts.validate_json_artifact import load_json, validate


SUCCESS = 0
VALIDATION_FAILED = 2
INVALID_REQUEST = 3
MALFORMED = 4

SCHEMA_VERSION = "1.0"
FRAMEWORK_VERSION = "idea_evaluation_v1.0"
CANDIDATE_SCHEMA = schema_path("idea_candidate.schema.json")
EVALUATION_SCHEMA = schema_path("idea_evaluation.schema.json")
PROMOTION_ROUTES = {
    "hypothesis_card": "promote_to_hypothesis_card",
    "data_readiness": "promote_to_data_readiness",
    "literature_extract": "promote_to_literature_extract",
}
ALLOWED_PROMOTION_NEXT_TASKS = set(PROMOTION_ROUTES)
REQUIRED_DEDUPE_TARGETS = {"accepted_outputs_index", "discovery_inbox", "queue", "rejected_ideas"}
SENSITIVE_PATTERNS = re.compile(r"\b(private|scrap(?:e|ed|ing)|sensitive|personal|non[- ]?public|license restricted)\b", re.IGNORECASE)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def nonempty_list(value: Any) -> bool:
    return isinstance(value, list) and any(str(item).strip() for item in value)


def schema_errors(payload: dict[str, Any], schema_path: Path) -> list[dict[str, str]]:
    schema = load_json(schema_path)
    if not isinstance(schema, dict):
        return [{"path": "$", "message": f"schema is not an object: {schema_path}"}]
    return [error.to_dict() for error in validate(payload, schema)]


def markdown_rows(path: Path) -> list[list[str]]:
    if not path.exists():
        return []
    rows: list[list[str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line.startswith("|") or "---" in line:
            continue
        cells = [cell.strip().replace("\\|", "|") for cell in line.strip("|").split("|")]
        if not cells:
            continue
        if cells[0].lower() in {"date", "item", "id", "task", "source_id"}:
            continue
        if any(cells):
            rows.append(cells)
    return rows


def text_contains(path: Path, needle: str) -> bool:
    if not path.exists() or not needle:
        return False
    try:
        return needle.lower() in path.read_text(encoding="utf-8").lower()
    except OSError:
        return False


def candidate_title(candidate: dict[str, Any]) -> str:
    return str(candidate.get("title", "")).strip()


def rejection_logged(candidate: dict[str, Any], ops_dir: Optional[Path]) -> bool:
    if ops_dir is None:
        return False
    log = ops_dir / "discovery" / "rejected_ideas.md"
    candidate_id = str(candidate.get("id", ""))
    title = candidate_title(candidate)
    return text_contains(log, candidate_id) or text_contains(log, title)


def duplicate_checked(candidate: dict[str, Any], ops_dir: Optional[Path]) -> tuple[list[str], list[str]]:
    checked: list[str] = []
    missing: list[str] = []
    if ops_dir is None:
        return checked, sorted(REQUIRED_DEDUPE_TARGETS)

    targets = {
        "accepted_outputs_index": ops_dir / "accepted_outputs_index.md",
        "discovery_inbox": ops_dir / "discovery_inbox.md",
        "queue": ops_dir / "queue.md",
        "rejected_ideas": ops_dir / "discovery" / "rejected_ideas.md",
    }
    for name, path in targets.items():
        if path.exists():
            checked.append(name)
        else:
            missing.append(name)
    return checked, missing


def status_to_route(status: str, next_task: str) -> str:
    if status == "promote" and next_task in PROMOTION_ROUTES:
        return PROMOTION_ROUTES[next_task]
    if status == "park":
        return "park"
    if status == "reject":
        return "reject"
    return "needs_human"


def scorecard(candidate: dict[str, Any]) -> dict[str, Any]:
    score = candidate.get("score") if isinstance(candidate.get("score"), dict) else {}
    fields = [
        "decision_impact",
        "novelty",
        "data_availability",
        "feasibility",
        "killability",
        "robustness_risk",
        "cost",
        "reuse_potential",
        "weighted_total",
        "promotion_threshold",
        "minimum_killability",
    ]
    return {field: score.get(field) for field in fields}


def hard_gate_results(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    score = candidate.get("score") if isinstance(candidate.get("score"), dict) else {}
    existing = score.get("hard_gate_results")
    if isinstance(existing, list):
        return [item for item in existing if isinstance(item, dict)]
    return []


def failed_gates(candidate: dict[str, Any]) -> list[str]:
    return [str(item.get("gate")) for item in hard_gate_results(candidate) if item.get("passed") is not True]


def sensitive_data_flag(candidate: dict[str, Any]) -> bool:
    parts: list[str] = []
    for key in ("required_data", "main_risks", "evidence_seeds"):
        value = candidate.get(key)
        if isinstance(value, list):
            parts.extend(str(item) for item in value)
    for key in ("why_it_might_matter", "minimum_viable_test", "baseline", "novelty_angle", "kill_reason"):
        value = candidate.get(key)
        if isinstance(value, str):
            parts.append(value)
    return bool(SENSITIVE_PATTERNS.search(" ".join(parts)))


def build_evaluation(
    candidate: dict[str, Any],
    ops_dir: Optional[Path],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    failures: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    status = str(candidate.get("status", "candidate"))
    next_task = str(candidate.get("recommended_next_task", ""))
    route = status_to_route(status, next_task)
    checked, missing_dedupe = duplicate_checked(candidate, ops_dir)
    duplicate_status = str(candidate.get("duplicate_status", "new"))
    revisit_condition = str(candidate.get("revisit_condition", "none")).strip()
    is_rejected_or_parked = status in {"reject", "park"}
    is_promoted = status == "promote"
    blocked_reasons: list[str] = []
    review_notes: list[str] = []

    if missing_dedupe:
        failures.append({"gate": "dedupe", "message": "Required dedupe targets are missing.", "details": missing_dedupe})
        blocked_reasons.append("dedupe targets missing")
    if duplicate_status in {"duplicate", "near_duplicate"} and is_promoted:
        failures.append({"gate": "dedupe", "message": "Duplicate or near-duplicate candidate cannot be promoted."})
        blocked_reasons.append("duplicate risk")
    if next_task == "experiment_plan":
        failures.append({"gate": "direct_experiment_block", "message": "Idea evaluation cannot route directly to experiment_plan."})
        blocked_reasons.append("direct experiment route blocked")
    if is_promoted and next_task not in ALLOWED_PROMOTION_NEXT_TASKS:
        failures.append({"gate": "promotion_route", "message": "Promoted ideas must route to a safe setup task.", "details": next_task})
        blocked_reasons.append("unsafe promotion route")
    if failed_gates(candidate):
        failures.append({"gate": "hard_gates", "message": "Candidate has failed hard gates.", "details": failed_gates(candidate)})
        blocked_reasons.append("failed hard gates")
    if sensitive_data_flag(candidate):
        failures.append({"gate": "data_sensitivity", "message": "Candidate appears to depend on private, scraped, sensitive, or restricted data."})
        blocked_reasons.append("sensitive data")
    if is_rejected_or_parked and (not revisit_condition or revisit_condition.lower() in {"none", "n/a", "na"}):
        failures.append({"gate": "revisit_condition", "message": "Parked or rejected candidates require a concrete revisit condition."})
        blocked_reasons.append("missing revisit condition")

    logged = rejection_logged(candidate, ops_dir)
    rejection_required = is_rejected_or_parked
    if rejection_required and not logged:
        failures.append({"gate": "rejection_logging", "message": "Parked or rejected candidate must be logged in discovery/rejected_ideas.md."})
        blocked_reasons.append("rejection not logged")

    score = candidate.get("score") if isinstance(candidate.get("score"), dict) else {}
    weighted_total = score.get("weighted_total")
    promotion_threshold = score.get("promotion_threshold")
    minimum_killability = score.get("minimum_killability")
    killability = score.get("killability")
    if is_promoted:
        if isinstance(weighted_total, (int, float)) and isinstance(promotion_threshold, (int, float)) and weighted_total < promotion_threshold:
            failures.append({"gate": "score_threshold", "message": "Promoted candidate is below promotion threshold.", "details": {"weighted_total": weighted_total, "promotion_threshold": promotion_threshold}})
            blocked_reasons.append("below promotion threshold")
        if isinstance(killability, int) and isinstance(minimum_killability, int) and killability < minimum_killability:
            failures.append({"gate": "killability", "message": "Promoted candidate is below minimum killability.", "details": {"killability": killability, "minimum_killability": minimum_killability}})
            blocked_reasons.append("killability below threshold")

    required_text_fields = {
        "title": candidate.get("title"),
        "question": candidate.get("question"),
        "why_it_might_matter": candidate.get("why_it_might_matter"),
        "minimum_viable_test": candidate.get("minimum_viable_test"),
        "baseline": candidate.get("baseline"),
        "kill_reason": candidate.get("kill_reason"),
    }
    for field, value in required_text_fields.items():
        if not nonempty_string(value):
            failures.append({"gate": "required_fields", "message": f"{field} is required."})
            blocked_reasons.append(f"missing {field}")
    if not nonempty_list(candidate.get("required_data")):
        failures.append({"gate": "required_fields", "message": "required_data is required."})
        blocked_reasons.append("missing required_data")
    if not nonempty_list(candidate.get("main_risks")):
        failures.append({"gate": "required_fields", "message": "main_risks is required."})
        blocked_reasons.append("missing main_risks")

    if duplicate_status == "near_duplicate":
        warnings.append({"gate": "dedupe", "message": "Candidate is a near duplicate; reviewers should check cluster representative."})
    if candidate.get("exploration_category") == "speculative" and is_promoted:
        warnings.append({"gate": "portfolio", "message": "Speculative candidate promoted; ensure portfolio allocation remains within exploration policy."})

    planner_may_promote = is_promoted and not failures
    if planner_may_promote:
        promotion_reason = f"score {weighted_total} meets threshold and hard gates allow {next_task}"
        review_notes.append("Planner may promote only to the recommended setup task, not experiment execution.")
    elif is_rejected_or_parked and not failures:
        promotion_reason = f"candidate routed to {status}; no planner promotion"
    else:
        promotion_reason = "candidate blocked until hard gates are resolved"

    evaluation = {
        "schema_version": SCHEMA_VERSION,
        "framework_version": FRAMEWORK_VERSION,
        "candidate_id": candidate.get("id"),
        "evaluated_at": utc_now(),
        "route": route,
        "recommended_next_task": next_task if next_task in {"hypothesis_card", "data_readiness", "literature_extract", "park", "reject"} else "park",
        "mission_policy_version": score.get("mission_policy_version"),
        "scorecard": scorecard(candidate),
        "hard_gate_results": hard_gate_results(candidate),
        "dedupe": {
            "duplicate_status": duplicate_status,
            "checked_against": checked,
            "cluster_id": str(candidate.get("cluster_id", candidate.get("id", "cluster-unknown"))),
            "representative": candidate.get("cluster_representative", True) is True,
        },
        "rejection_logging": {
            "required": rejection_required,
            "log_path": "research_ops/discovery/rejected_ideas.md",
            "logged": logged,
            "rejection_kind": "temporary" if status == "park" else ("permanent" if status == "reject" else "none"),
            "revisit_condition": revisit_condition or "none",
        },
        "promotion_readiness": {
            "planner_may_promote": planner_may_promote,
            "promotion_reason": promotion_reason,
            "blocked_reasons": sorted(set(blocked_reasons)),
        },
        "review_notes": review_notes,
    }
    return evaluation, failures, warnings


def validate_candidate(candidate: dict[str, Any]) -> list[dict[str, str]]:
    return schema_errors(candidate, CANDIDATE_SCHEMA)


def validate_evaluation(evaluation: dict[str, Any]) -> list[dict[str, str]]:
    return schema_errors(evaluation, EVALUATION_SCHEMA)


def parse_candidate(path: Path) -> dict[str, Any]:
    payload = load_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"candidate is not an object: {path}")
    return payload


def run_validate(args: argparse.Namespace) -> int:
    try:
        candidate = parse_candidate(args.candidate)
    except ValueError as exc:
        print_json({"ok": False, "reason": "candidate_load_failed", "error": str(exc), "candidate": str(args.candidate)})
        return MALFORMED

    candidate_errors = validate_candidate(candidate)
    evaluation, failures, warnings = build_evaluation(candidate, args.ops_dir)
    evaluation_errors = validate_evaluation(evaluation)
    if candidate_errors:
        failures.append({"gate": "candidate_schema", "message": "Candidate failed schema validation.", "details": candidate_errors})
    if evaluation_errors:
        failures.append({"gate": "evaluation_schema", "message": "Idea evaluation failed schema validation.", "details": evaluation_errors})

    ok = not failures
    output_candidate = dict(candidate)
    output_candidate["idea_evaluation"] = evaluation
    if not args.dry_run and (ok or args.write_on_fail):
        output = args.output if args.output is not None else args.candidate
        atomic_write_json(output, output_candidate)

    print_json(
        {
            "ok": ok,
            "action": "dry_run_validated" if args.dry_run else ("validated" if ok else "validation_failed"),
            "candidate": str(args.candidate),
            "candidate_id": candidate.get("id"),
            "route": evaluation.get("route"),
            "recommended_next_task": evaluation.get("recommended_next_task"),
            "planner_may_promote": evaluation.get("promotion_readiness", {}).get("planner_may_promote"),
            "hard_gate_failures": failures,
            "warnings": warnings,
            "evaluation": evaluation,
            "next_step": "planner may promote candidate" if ok and evaluation["promotion_readiness"]["planner_may_promote"] else "do not promote candidate",
        }
    )
    return SUCCESS if ok else VALIDATION_FAILED


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate idea evaluation hard gates for a scored candidate.")
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--ops-dir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--write-on-fail", action="store_true")
    return parser.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    return run_validate(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
