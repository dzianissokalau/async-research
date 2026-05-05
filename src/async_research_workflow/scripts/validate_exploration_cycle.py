#!/usr/bin/env python3
"""Validate async research exploration cycles against exploration_v1.0."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable, Optional

from async_research_workflow.resources import schema_path
from async_research_workflow.scripts.validate_json_artifact import load_json, validate


SUCCESS = 0
VALIDATION_FAILED = 2
INVALID_REQUEST = 3
MALFORMED = 4

SCHEMA_VERSION = "1.0"
FRAMEWORK_VERSION = "exploration_v1.0"
PLAN_SCHEMA = schema_path("exploration_cycle.schema.json")
STATUS_SCHEMA = schema_path("task_status.schema.json")
SOURCE_HEADER = [
    "source_id",
    "source_name",
    "source_type",
    "location",
    "allowed_browsing",
    "update_cadence",
    "trust_level",
    "expected_idea_types",
    "last_checked",
]
SOURCE_ID_PATTERN = re.compile(r"^SRC-[0-9]{4}$")
DATE_PATTERN = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
ALLOWED_SOURCE_TYPES = {"internal", "official_data", "literature", "repo_artifact", "user_seed", "web"}
ALLOWED_TRUST_LEVELS = {"high", "medium", "low"}
DEFAULT_LIMITS = {
    "max_sources_scanned": 10,
    "max_raw_candidates": 20,
    "max_kept_candidates": 10,
    "max_discovery_inbox_additions": 5,
    "max_promotions_to_tasks": 3,
}
CATEGORIES = ("exploit", "adjacent", "speculative")


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def split_markdown_row(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return []
    return [cell.strip() for cell in stripped.strip("|").split("|")]


def read_json_object(path: Path) -> dict[str, Any]:
    payload = load_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"JSON artifact is not an object: {path}")
    return payload


def extract_fenced_json(text: str) -> dict[str, Any]:
    for match in re.finditer(r"```(?:json|exploration_cycle)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE):
        candidate = match.group(1).strip()
        if not candidate.startswith("{"):
            continue
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and (
            payload.get("framework_version") == FRAMEWORK_VERSION or "exploration_id" in payload
        ):
            return payload
    raise ValueError("no exploration cycle JSON block found")


def load_cycle(path: Path) -> dict[str, Any]:
    if path.suffix.lower() == ".json":
        return read_json_object(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"cannot read exploration cycle {path}: {exc}") from exc
    return extract_fenced_json(text)


def schema_errors(payload: dict[str, Any], schema_path: Path) -> list[dict[str, str]]:
    schema = load_json(schema_path)
    if not isinstance(schema, dict):
        return [{"path": "$", "message": f"schema is not an object: {schema_path}"}]
    return [error.to_dict() for error in validate(payload, schema)]


def infer_ops_dir(cycle_path: Path, task_dir: Optional[Path]) -> Optional[Path]:
    if task_dir is not None:
        resolved = task_dir.resolve()
        if resolved.parent.name == "tasks":
            return resolved.parent.parent
    for parent in [cycle_path.resolve(), *cycle_path.resolve().parents]:
        if parent.name == "research_ops":
            return parent
        if parent.name == "tasks" and parent.parent.name == "research_ops":
            return parent.parent
    return None


def resolve_source_register_path(cycle: dict[str, Any], ops_dir: Optional[Path]) -> Optional[Path]:
    raw = cycle.get("source_register_path")
    if not isinstance(raw, str) or not raw.strip():
        return None
    path = Path(raw)
    if path.is_absolute():
        return path
    if ops_dir is not None:
        ops_dir = ops_dir.resolve()
        parts = path.parts
        if parts and parts[0] == "research_ops":
            return ops_dir.parent / path
        return ops_dir / path
    return path


def parse_source_register(path: Path) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [], [{"path": str(path), "message": f"cannot read source register: {exc}"}]

    rows: list[dict[str, str]] = []
    in_table = False
    for raw in text.splitlines():
        cells = split_markdown_row(raw)
        if not cells:
            if in_table:
                break
            continue
        normalized = [cell.lower() for cell in cells]
        if normalized == SOURCE_HEADER:
            in_table = True
            continue
        if in_table and all(set(cell) <= {"-", ":", " "} for cell in cells):
            continue
        if in_table:
            if len(cells) != len(SOURCE_HEADER):
                errors.append({"path": str(path), "message": f"source register row has {len(cells)} cells: {raw}"})
                continue
            rows.append(dict(zip(SOURCE_HEADER, cells)))

    if not in_table:
        errors.append({"path": str(path), "message": "source register is missing required markdown table"})
    if not rows:
        errors.append({"path": str(path), "message": "source register has no sources"})

    seen: set[str] = set()
    for index, row in enumerate(rows, start=1):
        prefix = f"{path}:row[{index}]"
        source_id = row.get("source_id", "")
        if SOURCE_ID_PATTERN.match(source_id) is None:
            errors.append({"path": f"{prefix}.source_id", "message": "source_id must match SRC-0000"})
        elif source_id in seen:
            errors.append({"path": f"{prefix}.source_id", "message": f"duplicate source_id {source_id}"})
        seen.add(source_id)

        if row.get("source_type") not in ALLOWED_SOURCE_TYPES:
            errors.append({"path": f"{prefix}.source_type", "message": f"unsupported source_type {row.get('source_type')!r}"})
        if row.get("allowed_browsing") not in {"yes", "no"}:
            errors.append({"path": f"{prefix}.allowed_browsing", "message": "allowed_browsing must be yes or no"})
        if row.get("trust_level") not in ALLOWED_TRUST_LEVELS:
            errors.append({"path": f"{prefix}.trust_level", "message": f"unsupported trust_level {row.get('trust_level')!r}"})
        if not row.get("location"):
            errors.append({"path": f"{prefix}.location", "message": "location is required"})
        if not DATE_PATTERN.match(row.get("last_checked", "")):
            errors.append({"path": f"{prefix}.last_checked", "message": "last_checked must use YYYY-MM-DD"})
    return rows, errors


def load_task_status(task_dir: Optional[Path]) -> tuple[Optional[dict[str, Any]], list[dict[str, str]]]:
    if task_dir is None:
        return None, []
    try:
        status = read_json_object(task_dir / "status.json")
    except ValueError as exc:
        return None, [{"path": str(task_dir / "status.json"), "message": str(exc)}]
    return status, schema_errors(status, STATUS_SCHEMA)


def add_failure(failures: list[dict[str, Any]], gate: str, message: str, details: Any = None) -> None:
    item: dict[str, Any] = {"gate": gate, "message": message}
    if details is not None:
        item["details"] = details
    failures.append(item)


def add_warning(warnings: list[dict[str, Any]], gate: str, message: str, details: Any = None) -> None:
    item: dict[str, Any] = {"gate": gate, "message": message}
    if details is not None:
        item["details"] = details
    warnings.append(item)


def candidate_distribution(candidates: list[dict[str, Any]]) -> dict[str, int]:
    counts = {category: 0 for category in CATEGORIES}
    for candidate in candidates:
        category = candidate.get("category")
        if category in counts:
            counts[category] += 1
    return counts


def validate_exploration_hard_gates(
    cycle: dict[str, Any],
    ops_dir: Optional[Path],
    task_status: Optional[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    failures: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    source_register = resolve_source_register_path(cycle, ops_dir)
    source_rows: list[dict[str, str]] = []
    if source_register is None:
        add_failure(failures, "source_register", "source_register_path is required.")
    else:
        source_rows, source_errors = parse_source_register(source_register)
        if source_errors:
            add_failure(failures, "source_register", "Source register is missing or invalid.", source_errors)
    source_ids = {row["source_id"] for row in source_rows if "source_id" in row}

    budget = cycle.get("exploration_budget")
    if isinstance(budget, dict):
        for key, default in DEFAULT_LIMITS.items():
            value = budget.get(key)
            if isinstance(value, int) and not isinstance(value, bool) and value > default:
                add_failure(failures, "exploration_budget", f"{key} exceeds framework default limit {default}.", {"value": value})
    else:
        add_failure(failures, "exploration_budget", "Exploration budget is required.")

    sources_scanned = cycle.get("sources_scanned")
    if not isinstance(sources_scanned, list) or not sources_scanned:
        add_failure(failures, "sources_scanned", "At least one approved source must be scanned.")
    elif source_ids:
        unknown = [source for source in sources_scanned if source not in source_ids]
        if unknown:
            add_failure(failures, "sources_scanned", "Scanned sources must exist in source register.", unknown)

    if isinstance(budget, dict):
        limits = [
            ("sources_scanned", len(sources_scanned) if isinstance(sources_scanned, list) else 0, "max_sources_scanned"),
            ("raw_candidate_count", cycle.get("raw_candidate_count"), "max_raw_candidates"),
            ("kept_candidates", cycle.get("kept_candidates"), "max_kept_candidates"),
            ("discovery_inbox_additions", cycle.get("discovery_inbox_additions"), "max_discovery_inbox_additions"),
            ("promotions_to_tasks", cycle.get("promotions_to_tasks"), "max_promotions_to_tasks"),
        ]
        for observed_key, observed, limit_key in limits:
            limit = budget.get(limit_key)
            if isinstance(observed, int) and isinstance(limit, int) and observed > limit:
                add_failure(failures, "limits", f"{observed_key} exceeds {limit_key}.", {"observed": observed, "limit": limit})

    candidates = cycle.get("candidates") if isinstance(cycle.get("candidates"), list) else []
    distribution = candidate_distribution([candidate for candidate in candidates if isinstance(candidate, dict)])
    if candidates and cycle.get("kept_candidates") != len(candidates):
        add_failure(failures, "kept_candidates", "kept_candidates must equal the number of candidate records.", {"declared": cycle.get("kept_candidates"), "actual": len(candidates)})

    candidate_ids: set[str] = set()
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        candidate_id = candidate.get("id")
        if isinstance(candidate_id, str):
            if candidate_id in candidate_ids:
                add_failure(failures, "candidates", f"duplicate candidate id {candidate_id}")
            candidate_ids.add(candidate_id)
        refs = candidate.get("source_refs")
        if not isinstance(refs, list) or not refs:
            add_failure(failures, "candidate_sources", f"{candidate_id or 'candidate'} must include source_refs.")
        elif source_ids:
            unknown_refs = [ref for ref in refs if ref not in source_ids]
            if unknown_refs:
                add_failure(failures, "candidate_sources", f"{candidate_id or 'candidate'} has source_refs missing from source register.", unknown_refs)
        if candidate.get("status") in {"park", "reject"}:
            revisit = str(candidate.get("revisit_condition", "")).strip().lower()
            if not revisit or revisit in {"none", "n/a", "na"}:
                add_failure(failures, "revisit_condition", f"{candidate_id or 'candidate'} must include a concrete revisit condition when parked or rejected.")
        if candidate.get("recommended_next_task") == "experiment_plan":
            add_failure(failures, "direct_experiment_block", f"{candidate_id or 'candidate'} may not route directly to experiment_plan.")
        if candidate.get("duplicate_status") == "duplicate" and candidate.get("status") == "promote":
            add_failure(failures, "duplicate_handling", f"{candidate_id or 'candidate'} is duplicate but promoted.")
        drift_penalty = candidate.get("drift_penalty")
        if isinstance(drift_penalty, (int, float)) and not isinstance(drift_penalty, bool) and drift_penalty > 2:
            if candidate.get("status") == "promote":
                add_failure(failures, "drift_control", f"{candidate_id or 'candidate'} has high drift penalty but is promoted.")
            else:
                add_warning(warnings, "drift_control", f"{candidate_id or 'candidate'} has high drift penalty.", drift_penalty)

    health = cycle.get("health_summary")
    if isinstance(health, dict):
        declared = health.get("category_distribution")
        if isinstance(declared, dict):
            declared_distribution = {category: declared.get(category, 0) for category in CATEGORIES}
            if declared_distribution != distribution:
                add_failure(failures, "category_distribution", "health_summary.category_distribution must match candidates.", {"declared": declared_distribution, "actual": distribution})
        if health.get("limits_respected") is not True:
            add_failure(failures, "limits", "health_summary.limits_respected must be true.")
        if isinstance(budget, dict):
            requested = health.get("human_decisions_requested")
            max_human = budget.get("max_human_decisions")
            if isinstance(requested, int) and isinstance(max_human, int) and requested > max_human:
                add_failure(failures, "human_load", "human decisions requested exceeds budget.", {"requested": requested, "limit": max_human})

    duplicate_summary = cycle.get("duplicate_summary")
    if not isinstance(duplicate_summary, dict) or duplicate_summary.get("checked_against_accepted_outputs") is not True:
        add_failure(failures, "duplicate_check", "Exploration must check accepted outputs for duplicates.")

    parking_summary = cycle.get("parking_summary")
    if isinstance(parking_summary, dict):
        parked_count = sum(1 for candidate in candidates if isinstance(candidate, dict) and candidate.get("status") == "park")
        rejected_count = sum(1 for candidate in candidates if isinstance(candidate, dict) and candidate.get("status") == "reject")
        if parking_summary.get("parked_count") != parked_count:
            add_failure(failures, "parking_summary", "parked_count must match candidate statuses.", {"declared": parking_summary.get("parked_count"), "actual": parked_count})
        if parking_summary.get("rejected_count") != rejected_count:
            add_failure(failures, "parking_summary", "rejected_count must match candidate statuses.", {"declared": parking_summary.get("rejected_count"), "actual": rejected_count})
        if (parked_count or rejected_count) and parking_summary.get("parked_written_to_log") is not True:
            add_failure(failures, "parking_summary", "Parked or rejected ideas must be written to a log.")

    targets = cycle.get("category_targets")
    if isinstance(targets, dict):
        target_sum = sum(float(targets.get(category, 0)) for category in CATEGORIES if isinstance(targets.get(category), (int, float)))
        if abs(target_sum - 1.0) > 0.01:
            add_failure(failures, "category_targets", "category_targets must sum to 1.0.", {"sum": round(target_sum, 4)})
        if distribution["speculative"] > max(1, int(max(len(candidates), 1) * 0.25)):
            add_warning(warnings, "category_distribution", "Speculative candidates exceed the low-cost default envelope.", distribution)

    if task_status is not None:
        if task_status.get("type") != "idea_discovery":
            add_failure(failures, "task_status", "Task status type must be idea_discovery.")
        framework_versions = task_status.get("framework_versions")
        if not isinstance(framework_versions, dict) or framework_versions.get("exploration") != FRAMEWORK_VERSION:
            add_failure(failures, "task_status", "status.json must record exploration_v1.0.")

    return failures, warnings, distribution


def validate_cycle(args: argparse.Namespace) -> int:
    try:
        cycle = load_cycle(args.cycle)
    except ValueError as exc:
        print_json({"ok": False, "reason": "cycle_load_failed", "error": str(exc), "cycle": str(args.cycle)})
        return MALFORMED

    status, status_errors = load_task_status(args.task_dir)
    cycle_errors = schema_errors(cycle, args.schema)
    ops_dir = args.ops_dir or infer_ops_dir(args.cycle, args.task_dir)
    failures, warnings, distribution = validate_exploration_hard_gates(cycle, ops_dir, status)

    if status_errors:
        failures.append({"gate": "task_status_schema", "message": "Task status failed schema validation.", "details": status_errors})
    if cycle_errors:
        failures.append({"gate": "exploration_cycle_schema", "message": "Exploration cycle failed schema validation.", "details": cycle_errors})

    ok = not failures
    report = {
        "ok": ok,
        "cycle": str(args.cycle),
        "task_dir": str(args.task_dir) if args.task_dir else None,
        "ops_dir": str(ops_dir) if ops_dir else None,
        "schema_version": cycle.get("schema_version"),
        "framework_version": cycle.get("framework_version"),
        "exploration_id": cycle.get("exploration_id"),
        "task_id": cycle.get("task_id"),
        "category_distribution": distribution,
        "hard_gate_failures": failures,
        "warnings": warnings,
        "next_step": "score candidates and update discovery inbox" if ok else "revise exploration cycle before review or promotion",
    }
    print_json(report)
    return SUCCESS if ok else VALIDATION_FAILED


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate an exploration cycle against exploration_v1.0.")
    parser.add_argument("cycle", type=Path, help="Path to exploration_cycle.json or markdown with a fenced JSON cycle block.")
    parser.add_argument("--schema", type=Path, default=PLAN_SCHEMA)
    parser.add_argument("--ops-dir", type=Path)
    parser.add_argument("--task-dir", type=Path)
    return parser.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    if args.schema != PLAN_SCHEMA and not args.schema.exists():
        print_json({"ok": False, "reason": "schema_missing", "schema": str(args.schema)})
        return INVALID_REQUEST
    return validate_cycle(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
