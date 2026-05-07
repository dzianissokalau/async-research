#!/usr/bin/env python3
"""Initialize and maintain idea catalog workspace files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any

from async_research_workflow.idea_catalog import CATALOG_FILE
from async_research_workflow.idea_catalog import CATALOG_TEMPLATE
from async_research_workflow.idea_catalog import IDEAS_DIR
from async_research_workflow.idea_catalog import PRIORITIZATION_FILE
from async_research_workflow.idea_catalog import PRIORITIZATION_TEMPLATE
from async_research_workflow.idea_catalog import STORED_STATUSES
from async_research_workflow.idea_catalog import candidate_summary
from async_research_workflow.idea_catalog import catalog_list_report
from async_research_workflow.idea_catalog import catalog_show_report
from async_research_workflow.idea_catalog import catalog_validation_exit_code
from async_research_workflow.idea_catalog import catalog_validation_report
from async_research_workflow.idea_catalog import hard_gate_blocked
from async_research_workflow.idea_catalog import markdown_cells
from async_research_workflow.idea_catalog import read_catalog
from async_research_workflow.idea_catalog import validate_candidate_record


SUCCESS = 0
VALIDATION_FAILED = 2
INVALID_REQUEST = 3
MALFORMED = 4

STARTER_FILES = (
    (Path(IDEAS_DIR) / CATALOG_FILE, CATALOG_TEMPLATE),
    (Path(IDEAS_DIR) / PRIORITIZATION_FILE, PRIORITIZATION_TEMPLATE),
)
IDEA_ID_RE = re.compile(r"\bIDEA-[0-9]{4}\b")
TASK_ID_RE = re.compile(r"\bTASK-[0-9]{4}\b")
CLUSTER_ID_RE = re.compile(r"\bCL-[0-9]{4}\b")
CATALOG_MARKER_RE = re.compile(r"\bcatalog\s*:\s*([a-z_]+)\b", re.IGNORECASE)
IDEA_ID_PATTERN = re.compile(r"^IDEA-[0-9]{4}$")
PROMOTABLE_NEXT_TASKS = {"hypothesis_card", "data_readiness", "literature_extract"}
CAPTURE_DRAFT_POLICY_VERSION = "catalog_capture_dry_run_v1.0"


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def normalize_title(value: Any) -> str:
    text = " ".join(str(value or "").lower().split())
    text = re.sub(r"[^a-z0-9 ]+", "", text)
    return " ".join(text.split())


def combined_row_text(row: dict[str, Any]) -> str:
    values = [str(value) for key, value in row.items() if key not in {"row_number", "row_id"}]
    return " ".join(values)


def parse_markdown_table_rows(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not path.exists():
        return [], [{"path": str(path), "reason": "markdown_table_missing"}]
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return [], [{"path": str(path), "reason": "markdown_table_read_failed", "error": str(exc)}]
    except UnicodeDecodeError as exc:
        return [], [{"path": str(path), "reason": "markdown_table_read_failed", "error": str(exc)}]

    header: list[str] | None = None
    rows: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for raw in lines:
        line = raw.strip()
        if not line.startswith("|"):
            continue
        cells = markdown_cells(line)
        if cells and all(set(cell.replace(":", "").strip()) <= {"-"} for cell in cells):
            continue
        if header is None:
            header = [cell.lower().strip().replace(" ", "_") for cell in cells]
            continue
        if len(cells) != len(header):
            warnings.append(
                {
                    "path": str(path),
                    "reason": "malformed_markdown_table_row",
                    "row": line,
                    "expected_cells": len(header),
                    "actual_cells": len(cells),
                }
            )
            continue
        row = {key: value.strip() for key, value in zip(header, cells)}
        row["row_number"] = len(rows) + 1
        row["row_id"] = f"row-{row['row_number']}"
        rows.append(row)
    return rows, warnings


def source_report(path: Path) -> dict[str, Any]:
    rows, warnings = parse_markdown_table_rows(path)
    return {
        "path": str(path),
        "exists": path.exists(),
        "row_count": len(rows),
        "warnings": warnings,
    }


def catalog_marker(row: dict[str, Any]) -> str | None:
    match = CATALOG_MARKER_RE.search(combined_row_text(row))
    if not match:
        return None
    status = match.group(1).lower().strip()
    return status if status in STORED_STATUSES else "candidate"


def row_idea_id(row: dict[str, Any]) -> str | None:
    item = str(row.get("item") or "").strip()
    if IDEA_ID_PATTERN.match(item):
        return item
    match = IDEA_ID_RE.search(combined_row_text(row))
    return match.group(0) if match else None


def row_title(row: dict[str, Any]) -> str:
    title = str(row.get("title") or "").strip()
    if title:
        return title
    return f"Captured discovery row {row.get('row_id', 'unknown')}"


def row_next_task(row: dict[str, Any]) -> str:
    next_task = str(row.get("next_task") or "").strip()
    return next_task if next_task in PROMOTABLE_NEXT_TASKS else "data_readiness"


def row_task_refs(row: dict[str, Any]) -> set[str]:
    return set(TASK_ID_RE.findall(combined_row_text(row)))


def row_cluster_id(row: dict[str, Any]) -> str | None:
    match = CLUSTER_ID_RE.search(combined_row_text(row))
    return match.group(0) if match else None


def explicit_duplicate_marker(row: dict[str, Any] | None, title: str = "") -> bool:
    text = combined_row_text(row) if row is not None else title
    normalized = text.lower()
    return "duplicate" in normalized or "near_duplicate" in normalized


def capture_draft_score() -> dict[str, Any]:
    return {
        "mission_policy_version": CAPTURE_DRAFT_POLICY_VERSION,
        "budget_mode": "normal",
        "decision_impact": 1,
        "novelty": 1,
        "data_availability": 1,
        "feasibility": 1,
        "robustness_risk": 5,
        "cost": 1,
        "killability": 1,
        "reuse_potential": 1,
        "weighted_total": 0.0,
        "promotion_threshold": 14.0,
        "minimum_killability": 3,
        "max_promotions_per_week": 3,
        "budget_pressure_threshold": 0.8,
        "budget_mode_reason": "dry_run_capture_requires_human_completion",
        "budget_usage": {
            "monthly_usage_ratio": None,
            "weekly_usage_ratio": None,
            "monthly_cost_usd": 0.0,
            "weekly_cost_usd": 0.0,
            "monthly_budget_usd": None,
            "weekly_budget_usd": None,
        },
        "hard_gate_results": [
            {
                "gate": "human_completed_capture",
                "passed": False,
                "reason": "dry-run capture draft requires human completion before write mode",
            }
        ],
        "score_explanation": "Conservative dry-run capture draft; score must be replaced before promotion.",
    }


def capture_candidate_payload(
    idea_id: str,
    title: str,
    next_task: str = "data_readiness",
    source_discovery_path: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "id": idea_id,
        "status": "needs_human",
        "title": title,
        "question": f"Needs human completion: what is the smallest useful test for {title}?",
        "why_it_might_matter": "Captured by dry-run catalog planning; requires human completion before write mode.",
        "required_data": ["needs human supplied data requirements"],
        "minimum_viable_test": "Define a bounded test before promotion.",
        "baseline": "Needs human supplied baseline.",
        "main_risks": ["incomplete capture draft"],
        "kill_reason": "Reject if a bounded, evidence-backed next test cannot be defined.",
        "score": capture_draft_score(),
        "recommended_next_task": next_task,
        "human_gate_reason": "dry-run capture draft needs human completion before catalog write mode",
        "status_reason": "captured as a dry-run proposal, not durable catalog state",
    }
    if source_discovery_path:
        payload["source_discovery_path"] = source_discovery_path
    return payload


def record_refs(record: dict[str, Any]) -> set[str]:
    payload = record["payload"]
    refs: set[str] = set()
    for field in ("accepted_output_refs", "rejected_result_refs"):
        values = payload.get(field)
        if isinstance(values, list):
            refs.update(str(value) for value in values if str(value).strip())
    return refs


def duplicate_matches(
    records: list[dict[str, Any]],
    idea_id: str | None,
    title: str,
    task_refs: set[str] | None = None,
    cluster_id: str | None = None,
    explicit_duplicate: bool = False,
) -> list[dict[str, Any]]:
    normalized = normalize_title(title)
    refs = task_refs or set()
    matches: list[dict[str, Any]] = []
    for record in records:
        summary = candidate_summary(record)
        reasons: list[str] = []
        if idea_id and summary["idea_id"] == idea_id:
            reasons.append("same_idea_id")
        if normalized and normalize_title(summary["title"]) == normalized:
            reasons.append("same_normalized_title")
        shared_refs = sorted(refs & record_refs(record))
        if shared_refs:
            reasons.append("same_accepted_or_rejected_task_ref")
        existing_cluster = str(record["payload"].get("cluster_id") or "").strip()
        if cluster_id and existing_cluster == cluster_id:
            reasons.append("same_cluster_id")
        if explicit_duplicate and reasons:
            reasons.append("explicit_duplicate_marker")
        if reasons:
            matches.append(
                {
                    "idea_id": summary["idea_id"],
                    "title": summary["title"],
                    "status": summary["status"],
                    "path": summary["path"],
                    "reasons": sorted(set(reasons)),
                    "shared_task_refs": shared_refs,
                }
            )
    reason_rank = {
        "same_idea_id": 0,
        "explicit_duplicate_marker": 1,
        "same_normalized_title": 2,
        "same_accepted_or_rejected_task_ref": 3,
        "same_cluster_id": 4,
    }
    return sorted(matches, key=lambda item: (min(reason_rank[reason] for reason in item["reasons"]), item["idea_id"]))


def capture_source_from_args(args: argparse.Namespace) -> tuple[dict[str, Any] | None, list[dict[str, Any]], int]:
    if args.from_inbox and args.title:
        return None, [{"reason": "conflicting_capture_inputs", "message": "use either --from-inbox or --title"}], INVALID_REQUEST
    if not args.from_inbox and not args.title:
        return None, [{"reason": "missing_capture_input", "message": "provide --from-inbox or --title"}], INVALID_REQUEST
    if args.from_inbox:
        rows, warnings = parse_markdown_table_rows(args.ops_dir / "discovery_inbox.md")
        target = args.from_inbox.strip()
        match: dict[str, Any] | None = None
        row_id_match = re.fullmatch(r"row-([0-9]+)", target)
        if row_id_match:
            row_number = int(row_id_match.group(1))
            match = next((row for row in rows if row.get("row_number") == row_number), None)
        else:
            match = next(
                (
                    row
                    for row in rows
                    if target in {str(row.get("item") or "").strip(), row_idea_id(row) or ""}
                ),
                None,
            )
        if match is None:
            return None, [
                {
                    "reason": "inbox_row_not_found",
                    "from_inbox": target,
                    "warnings": warnings,
                }
            ], INVALID_REQUEST
        return match, warnings, SUCCESS
    return None, [], SUCCESS


def build_capture_plan(
    ops_dir: Path,
    idea_id: str | None,
    title: str,
    source_row: dict[str, Any] | None = None,
) -> dict[str, Any]:
    model = read_catalog(ops_dir)
    row_refs = row_task_refs(source_row) if source_row is not None else set()
    cluster_id = row_cluster_id(source_row) if source_row is not None else None
    duplicate = explicit_duplicate_marker(source_row, title)
    matches = duplicate_matches(model["candidates"], idea_id, title, row_refs, cluster_id, duplicate)
    source_discovery_path = None
    if source_row is not None:
        source_discovery_path = f"discovery_inbox.md#{source_row['row_id']}"

    if not idea_id:
        return {
            "route": "needs_human",
            "reason": "missing_idea_id",
            "changed": False,
            "duplicate_matches": matches,
            "would_write": [],
            "proposal": {
                "title": title,
                "required_human_decision": "choose a canonical IDEA-0000 id before write mode",
            },
        }
    if not IDEA_ID_PATTERN.match(idea_id):
        return {
            "route": "needs_human",
            "reason": "invalid_idea_id",
            "changed": False,
            "duplicate_matches": matches,
            "would_write": [],
            "proposal": {
                "idea_id": idea_id,
                "title": title,
                "required_human_decision": "replace id with IDEA-0000 format",
            },
        }

    reason_rank = {
        "same_idea_id": 0,
        "explicit_duplicate_marker": 1,
        "same_normalized_title": 2,
        "same_accepted_or_rejected_task_ref": 3,
        "same_cluster_id": 4,
    }
    strongest = None
    if matches:
        strongest = min(matches[0]["reasons"], key=lambda reason: reason_rank.get(reason, 99))
    strongest_matches = [match for match in matches if strongest in match["reasons"]] if strongest else []
    if matches and (strongest == "same_idea_id" or len(strongest_matches) == 1):
        return {
            "route": "update_existing",
            "reason": strongest,
            "changed": False,
            "duplicate_matches": matches,
            "would_write": [],
            "proposal": {
                "idea_id": idea_id,
                "title": title,
                "required_human_decision": "inspect the existing catalog record before creating or updating",
            },
        }
    if len(strongest_matches) > 1 or duplicate:
        return {
            "route": "needs_human",
            "reason": "ambiguous_or_explicit_duplicate",
            "changed": False,
            "duplicate_matches": matches,
            "would_write": [],
            "proposal": {
                "idea_id": idea_id,
                "title": title,
                "required_human_decision": "resolve duplicate candidates before write mode",
            },
        }

    payload = capture_candidate_payload(
        idea_id,
        title,
        row_next_task(source_row) if source_row is not None else "data_readiness",
        source_discovery_path,
    )
    target_path = ops_dir / IDEAS_DIR / f"{idea_id}.json"
    return {
        "route": "create",
        "reason": "no_duplicate_found",
        "changed": True,
        "duplicate_matches": [],
        "proposal": {
            "idea_id": idea_id,
            "title": title,
            "candidate": payload,
        },
        "would_write": [
            {
                "action": "create_canonical_idea_json",
                "path": str(target_path),
                "content": payload,
            }
        ],
    }


def proposal_without_content(change: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in change.items()
        if key != "content"
    }


def lifecycle_recommendation(record: dict[str, Any], ops_dir: Path) -> dict[str, Any]:
    payload = record["payload"]
    summary = candidate_summary(record)
    status = summary["status"]
    _warnings, failures = validate_candidate_record(record, ops_dir)
    base = {
        "idea_id": summary["idea_id"],
        "path": summary["path"],
        "current_status": status,
        "title": summary["title"],
    }
    if failures:
        return {
            **base,
            "recommended_status": "needs_human",
            "reason": "validation_failures_require_human_review",
            "validation_failure_reasons": sorted({item["reason"] for item in failures}),
        }
    if status != "candidate":
        return {
            **base,
            "recommended_status": status,
            "reason": "stored_status_already_explicit",
        }

    score = payload.get("score") if isinstance(payload.get("score"), dict) else {}
    if not score:
        return {**base, "recommended_status": "needs_human", "reason": "missing_score"}
    duplicate_status = str(payload.get("duplicate_status") or "new").strip()
    if duplicate_status in {"duplicate", "near_duplicate"}:
        return {**base, "recommended_status": "needs_human", "reason": "duplicate_status_needs_human"}
    if hard_gate_blocked(payload):
        return {**base, "recommended_status": "park", "reason": "failed_hard_gates"}
    next_task = str(payload.get("recommended_next_task") or "").strip()
    if next_task == "reject":
        return {**base, "recommended_status": "reject", "reason": "candidate_recommends_reject"}
    weighted_total = score.get("weighted_total")
    promotion_threshold = score.get("promotion_threshold")
    killability = score.get("killability")
    minimum_killability = score.get("minimum_killability")
    if (
        isinstance(weighted_total, (int, float))
        and not isinstance(weighted_total, bool)
        and isinstance(promotion_threshold, (int, float))
        and not isinstance(promotion_threshold, bool)
        and isinstance(killability, (int, float))
        and not isinstance(killability, bool)
        and isinstance(minimum_killability, (int, float))
        and not isinstance(minimum_killability, bool)
    ):
        if weighted_total >= promotion_threshold and killability >= minimum_killability and next_task in PROMOTABLE_NEXT_TASKS:
            return {**base, "recommended_status": "promote", "reason": "score_and_gates_pass"}
        return {**base, "recommended_status": "park", "reason": "below_promotion_threshold"}
    return {**base, "recommended_status": "needs_human", "reason": "score_threshold_fields_missing"}


def status_update_change(recommendation: dict[str, Any]) -> dict[str, Any] | None:
    current = recommendation["current_status"]
    target = recommendation["recommended_status"]
    if current == target:
        return None
    fields = {
        "status": target,
        "status_reason": recommendation["reason"],
    }
    if target == "needs_human":
        fields["human_gate_reason"] = f"maintenance dry-run recommends human review: {recommendation['reason']}"
    if target in {"park", "reject"}:
        fields["revisit_condition"] = "Revisit after a human reviews this maintenance proposal."
    return {
        "action": "update_idea_status",
        "path": recommendation["path"],
        "idea_id": recommendation["idea_id"],
        "from_status": current,
        "to_status": target,
        "reason": recommendation["reason"],
        "fields": fields,
    }


def run_capture(args: argparse.Namespace) -> int:
    if args.write:
        print_json(
            {
                "ok": False,
                "action": "idea_capture_refused",
                "reason": "write_mode_deferred_to_phase_7",
                "message": "Phase 6 capture is dry-run only; rerun with --dry-run and apply manually if desired.",
            }
        )
        return INVALID_REQUEST
    source_row, source_warnings, source_code = capture_source_from_args(args)
    if source_code != SUCCESS:
        print_json(
            {
                "ok": False,
                "action": "idea_capture_failed",
                "ops_dir": str(args.ops_dir),
                "failures": source_warnings,
            }
        )
        return source_code

    title = row_title(source_row) if source_row is not None else str(args.title or "").strip()
    if not title:
        print_json(
            {
                "ok": False,
                "action": "idea_capture_failed",
                "ops_dir": str(args.ops_dir),
                "failures": [
                    {
                        "reason": "missing_title",
                        "message": "provide a non-empty --title or capture an inbox row with a title",
                    }
                ],
            }
        )
        return INVALID_REQUEST
    idea_id = args.idea_id or (row_idea_id(source_row) if source_row is not None else None)
    plan = build_capture_plan(args.ops_dir, idea_id, title, source_row)
    print_json(
        {
            "ok": True,
            "action": "idea_capture_planned",
            "ops_dir": str(args.ops_dir),
            "dry_run": True,
            "input": {
                "from_inbox": args.from_inbox,
                "title": args.title,
                "idea_id": args.idea_id,
            },
            "source_row": source_row,
            "source_warnings": source_warnings,
            **plan,
            "would_not_write": [
                {"path": str(args.ops_dir / "queue.md"), "reason": "catalog capture dry-run never edits queue.md"},
                {"path": str(args.ops_dir / "tasks"), "reason": "catalog capture dry-run never creates task folders"},
            ],
        }
    )
    return SUCCESS


def run_maintain(args: argparse.Namespace) -> int:
    if args.write:
        print_json(
            {
                "ok": False,
                "action": "idea_catalog_maintenance_refused",
                "reason": "write_mode_deferred_to_phase_7",
                "message": "Phase 6 maintenance is dry-run only; rerun with --dry-run to inspect proposals.",
            }
        )
        return INVALID_REQUEST

    inbox_rows, inbox_warnings = parse_markdown_table_rows(args.ops_dir / "discovery_inbox.md")
    model = read_catalog(args.ops_dir)
    proposals: list[dict[str, Any]] = []
    ignored_rows: list[dict[str, Any]] = []
    proposed_changes: list[dict[str, Any]] = []
    for row in inbox_rows:
        marker = catalog_marker(row)
        if marker is None:
            ignored_rows.append(
                {
                    "row_id": row["row_id"],
                    "item": row.get("item"),
                    "title": row.get("title"),
                    "reason": "missing_catalog_marker",
                }
            )
            continue
        idea_id = row_idea_id(row)
        plan = build_capture_plan(args.ops_dir, idea_id, row_title(row), row)
        proposal = {
            "row_id": row["row_id"],
            "catalog_marker": marker,
            "item": row.get("item"),
            "title": row.get("title"),
            **plan,
        }
        proposals.append(proposal)
        proposed_changes.extend(proposal_without_content(change) for change in plan["would_write"])

    recommendations = [lifecycle_recommendation(record, args.ops_dir) for record in model["candidates"]]
    for recommendation in recommendations:
        change = status_update_change(recommendation)
        if change is not None:
            proposed_changes.append(change)

    print_json(
        {
            "ok": True,
            "action": "idea_catalog_maintenance_planned",
            "ops_dir": str(args.ops_dir),
            "dry_run": True,
            "sources_read": {
                "discovery_inbox": {
                    "path": str(args.ops_dir / "discovery_inbox.md"),
                    "row_count": len(inbox_rows),
                    "warnings": inbox_warnings,
                },
                "canonical_ideas": {
                    "path": str(args.ops_dir / IDEAS_DIR),
                    "candidate_count": model["candidate_count"],
                    "warnings": model["warnings"],
                    "failures": model["failures"],
                },
                "accepted_outputs_index": source_report(args.ops_dir / "accepted_outputs_index.md"),
                "rejected_ideas": source_report(args.ops_dir / "discovery" / "rejected_ideas.md"),
            },
            "inbox_capture_proposals": proposals,
            "ignored_inbox_rows": ignored_rows,
            "catalog_recommendations": recommendations,
            "proposed_file_changes": proposed_changes,
            "would_not_write": [
                {"path": str(args.ops_dir / "queue.md"), "reason": "maintenance dry-run never edits queue.md"},
                {"path": str(args.ops_dir / "tasks"), "reason": "maintenance dry-run never creates task folders"},
            ],
            "changed": bool(proposed_changes),
        }
    )
    return SUCCESS


def init_plan(ops_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    planned: list[dict[str, Any]] = []
    existing: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    ideas_dir = ops_dir / IDEAS_DIR

    if not ops_dir.exists():
        failures.append({
            "path": str(ops_dir),
            "reason": "ops_dir_missing",
            "message": "run async-research init first or choose an existing research_ops directory",
        })
        return planned, existing, failures
    if not ops_dir.is_dir():
        failures.append({
            "path": str(ops_dir),
            "reason": "ops_dir_not_directory",
            "message": "catalog initialization requires a research_ops directory",
        })
        return planned, existing, failures
    if ideas_dir.exists() and not ideas_dir.is_dir():
        failures.append({
            "path": str(ideas_dir),
            "reason": "ideas_path_not_directory",
            "message": "research_ops/ideas must be a directory",
        })
        return planned, existing, failures

    for relative_path, content in STARTER_FILES:
        path = ops_dir / relative_path
        entry = {
            "path": str(path),
            "relative_path": relative_path.as_posix(),
        }
        if path.exists():
            if path.is_dir():
                failures.append({
                    **entry,
                    "reason": "catalog_file_path_is_directory",
                    "message": "expected a catalog file but found a directory",
                })
            else:
                existing.append({**entry, "action": "preserve_existing"})
            continue
        planned.append({
            **entry,
            "action": "create",
            "bytes": len(content.encode("utf-8")),
        })

    return planned, existing, failures


def create_missing_files(ops_dir: Path, planned: list[dict[str, Any]]) -> list[dict[str, Any]]:
    added: list[dict[str, Any]] = []
    templates = {relative_path.as_posix(): content for relative_path, content in STARTER_FILES}
    for change in planned:
        relative = str(change["relative_path"])
        path = ops_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as handle:
            handle.write(templates[relative])
        added.append({**change, "action": "created"})
    return added


def run_init(args: argparse.Namespace) -> int:
    if args.write and args.dry_run:
        print_json({
            "ok": False,
            "reason": "conflicting_flags",
            "message": "use either --dry-run or --write, not both",
        })
        return INVALID_REQUEST

    dry_run = not args.write
    ops_dir = args.ops_dir
    planned, existing, failures = init_plan(ops_dir)
    ideas_dir = ops_dir / IDEAS_DIR
    lock_dir = ideas_dir / "LOCK"
    warnings: list[dict[str, Any]] = []

    if failures:
        print_json({
            "ok": False,
            "action": "idea_catalog_init_failed",
            "ops_dir": str(ops_dir),
            "planned_changes": planned,
            "existing_files": existing,
            "failures": failures,
        })
        return MALFORMED

    if args.write and lock_dir.exists():
        print_json({
            "ok": False,
            "action": "idea_catalog_init_refused",
            "reason": "catalog_locked",
            "ops_dir": str(ops_dir),
            "lock_dir": str(lock_dir),
            "planned_changes": planned,
            "existing_files": existing,
        })
        return VALIDATION_FAILED

    if dry_run:
        if lock_dir.exists():
            warnings.append({
                "reason": "catalog_locked",
                "message": "ideas/LOCK exists; --write will be refused until the lock is removed",
                "path": str(lock_dir),
            })
        print_json({
            "ok": True,
            "action": "idea_catalog_init_planned",
            "ops_dir": str(ops_dir),
            "catalog_dir": str(ideas_dir),
            "dry_run": True,
            "would_write": planned,
            "existing_files": existing,
            "warnings": warnings,
            "changed": bool(planned),
        })
        return SUCCESS

    try:
        added = create_missing_files(ops_dir, planned)
    except FileExistsError as exc:
        print_json({
            "ok": False,
            "action": "idea_catalog_init_refused",
            "reason": "catalog_file_created_concurrently",
            "error": str(exc),
            "ops_dir": str(ops_dir),
        })
        return VALIDATION_FAILED
    except OSError as exc:
        print_json({
            "ok": False,
            "action": "idea_catalog_init_failed",
            "reason": "write_failed",
            "error": str(exc),
            "ops_dir": str(ops_dir),
        })
        return MALFORMED

    print_json({
        "ok": True,
        "action": "idea_catalog_initialized",
        "ops_dir": str(ops_dir),
        "catalog_dir": str(ideas_dir),
        "files_added": added,
        "existing_files": existing,
        "changed": bool(added),
    })
    return SUCCESS


def run_validate(args: argparse.Namespace) -> int:
    report = catalog_validation_report(args.ops_dir)
    print_json(report)
    return catalog_validation_exit_code(report)


def run_list(args: argparse.Namespace) -> int:
    report = catalog_list_report(args.ops_dir, args.status)
    print_json(report)
    return SUCCESS if report["ok"] else MALFORMED


def run_show(args: argparse.Namespace) -> int:
    report = catalog_show_report(args.ops_dir, args.idea_id)
    print_json(report)
    if report["ok"]:
        return SUCCESS
    if report.get("reason") == "idea_not_found":
        return INVALID_REQUEST
    return catalog_validation_exit_code(report)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Initialize and maintain idea catalog workspace files.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser(
        "init",
        help="Add missing idea catalog starter files.",
        description="Preview or create missing research_ops/ideas starter files without overwriting existing files.",
    )
    init.add_argument("ops_dir", type=Path, help="Path to the research_ops workspace.")
    init.add_argument("--dry-run", action="store_true", help="Preview missing files without writing; this is the default.")
    init.add_argument("--write", action="store_true", help="Create only missing idea catalog files.")
    init.set_defaults(func=run_init)

    validate = subparsers.add_parser(
        "validate",
        help="Validate the durable idea catalog.",
        description="Read research_ops/ideas and report schema, lifecycle, reference, and projection problems without mutating files.",
    )
    validate.add_argument("ops_dir", type=Path, help="Path to the research_ops workspace.")
    validate.set_defaults(func=run_validate)

    list_cmd = subparsers.add_parser(
        "list",
        help="List canonical idea catalog records.",
        description="List ideas from canonical research_ops/ideas/IDEA-*.json records without reading Markdown as source of truth.",
    )
    list_cmd.add_argument("ops_dir", type=Path, help="Path to the research_ops workspace.")
    list_cmd.add_argument("--status", choices=STORED_STATUSES, help="Filter by stored idea status.")
    list_cmd.set_defaults(func=run_list)

    show = subparsers.add_parser(
        "show",
        help="Show one canonical idea catalog record.",
        description="Show one idea from research_ops/ideas/IDEA-*.json with its derived display summary.",
    )
    show.add_argument("ops_dir", type=Path, help="Path to the research_ops workspace.")
    show.add_argument("idea_id", help="Canonical idea id such as IDEA-0001.")
    show.set_defaults(func=run_show)

    maintain = subparsers.add_parser(
        "maintain",
        help="Preview catalog maintenance proposals.",
        description="Read discovery_inbox.md and canonical ideas, then print conservative dry-run capture and lifecycle proposals without mutating files.",
    )
    maintain.add_argument("ops_dir", type=Path, help="Path to the research_ops workspace.")
    maintain.add_argument("--dry-run", action="store_true", help="Preview proposals without writing; this is the default.")
    maintain.add_argument("--write", action="store_true", help="Reserved for Phase 7; refused in Phase 6.")
    maintain.set_defaults(func=run_maintain)

    capture = subparsers.add_parser(
        "capture",
        help="Preview explicit discovery-to-catalog capture.",
        description="Build one dry-run canonical IDEA JSON proposal from a discovery inbox row or explicit title without mutating files.",
    )
    capture.add_argument("ops_dir", type=Path, help="Path to the research_ops workspace.")
    capture.add_argument("--from-inbox", help="Discovery inbox item id or row-N selector to capture explicitly.")
    capture.add_argument("--id", dest="idea_id", help="Canonical IDEA-0000 id for the proposed catalog record.")
    capture.add_argument("--title", help="Title for an explicit title-only capture proposal.")
    capture.add_argument("--dry-run", action="store_true", help="Preview proposals without writing; this is the default.")
    capture.add_argument("--write", action="store_true", help="Reserved for Phase 7; refused in Phase 6.")
    capture.set_defaults(func=run_capture)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
