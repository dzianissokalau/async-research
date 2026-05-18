#!/usr/bin/env python3
"""Manage deliverable maturity manifests and readiness checks."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SUCCESS = 0
VALIDATION_FAILED = 2
INVALID_REQUEST = 3
MALFORMED = 4

SCHEMA_VERSION = "1.0"
FRAMEWORK_VERSION = "deliverable_maturity_v1.0"
DELIVERABLES_DIR = "deliverables"
MANIFEST_NAME = "deliverable_manifest.json"
PROJECTION_NAME = "deliverable_manifest.md"

DELIVERABLE_ID_RE = re.compile(r"^DELIV-[0-9]{4}$")
TASK_ID_RE = re.compile(r"^TASK-[0-9]{4}$")
NO_VALUE_MARKERS = {"", "none", "n/a", "na", "unknown", "todo", "tbd"}
GATE_STATUS_CHOICES = (
    "not_required",
    "missing",
    "partial",
    "passed_with_caveats",
    "passed",
    "waived_by_human",
)
PASSING_GATE_STATUSES = {"passed", "passed_with_caveats", "waived_by_human"}
CRITIC_REVIEW_ID_RE = re.compile(r"^CRITIC-[0-9]{4}$")
CRITIC_REVIEW_STATUS_CHOICES = ("draft", "completed", "superseded")
CRITIC_REVIEWER_ROLE_CHOICES = (
    "adversarial_critic",
    "methodology_critic",
    "external_critic",
    "human_editorial_critic",
)
SEVERITY_LEVELS = ("critical", "major", "minor", "note")

MATURITY_LEVELS: tuple[dict[str, Any], ...] = (
    {
        "level": 0,
        "id": "research_note",
        "label": "Research note",
        "meaning": "Bounded finding or evidence note for internal use.",
    },
    {
        "level": 1,
        "id": "internal_draft",
        "label": "Internal draft",
        "meaning": "Coherent internal synthesis assembled from accepted task outputs.",
    },
    {
        "level": 2,
        "id": "shareable_memo",
        "label": "Shareable memo",
        "meaning": "Polished memo for a known non-academic audience.",
    },
    {
        "level": 3,
        "id": "working_paper",
        "label": "Working paper",
        "meaning": "Public working paper or preprint-quality research artifact.",
    },
    {
        "level": 4,
        "id": "submission_ready_manuscript",
        "label": "Submission-ready manuscript",
        "meaning": "Venue-targeted manuscript ready for journal or conference submission workflow.",
    },
)
MATURITY_ORDER = {item["id"]: int(item["level"]) for item in MATURITY_LEVELS}
MATURITY_BY_LEVEL = {int(item["level"]): item["id"] for item in MATURITY_LEVELS}
MATURITY_CHOICES = tuple(MATURITY_ORDER)

OUTPUT_TYPE_CHOICES = (
    "research_note",
    "internal_draft",
    "memo",
    "report",
    "paper",
    "working_paper",
    "manuscript",
    "presentation",
    "other",
)

GATES_BY_MATURITY: dict[str, tuple[str, ...]] = {
    "research_note": (
        "source_caveat_checks",
        "claim_strength_review",
        "task_review",
    ),
    "internal_draft": (
        "accepted_evidence_linkage",
        "caveat_audit",
        "internal_workflow_disclosure",
        "draft_completeness_check",
    ),
    "shareable_memo": (
        "target_audience_declared",
        "clean_prose_pass",
        "figures_tables_embedded_and_narrated",
        "reader_trust_citations",
        "unresolved_gaps_disclosed",
        "internal_workflow_source_label_cleanup",
        "final_prose_pass",
    ),
    "working_paper": (
        "related_work_synthesis",
        "contribution_statement",
        "methods_detail",
        "reproducibility_notes",
        "formal_limitations",
        "formal_citations",
        "complete_bibliography",
        "adversarial_review",
    ),
    "submission_ready_manuscript": (
        "target_venue_declared",
        "venue_style_compliance",
        "formal_references",
        "data_code_availability",
        "figure_table_requirements",
        "response_matrix_closed",
        "independent_final_editorial_review",
    ),
}

MANUSCRIPT_GATES: tuple[dict[str, str], ...] = (
    {
        "gate_id": "target_audience_declared",
        "label": "Target audience declared",
        "category": "target",
        "minimum_maturity": "shareable_memo",
    },
    {
        "gate_id": "clean_prose_pass",
        "label": "Clean prose pass",
        "category": "prose",
        "minimum_maturity": "shareable_memo",
    },
    {
        "gate_id": "figures_tables_embedded_and_narrated",
        "label": "Figures and tables embedded, captioned, numbered, referenced, and narrated",
        "category": "figures_tables",
        "minimum_maturity": "shareable_memo",
    },
    {
        "gate_id": "reader_trust_citations",
        "label": "Reader-trust citations",
        "category": "citations",
        "minimum_maturity": "shareable_memo",
    },
    {
        "gate_id": "unresolved_gaps_disclosed",
        "label": "Unresolved gaps disclosed",
        "category": "limitations",
        "minimum_maturity": "shareable_memo",
    },
    {
        "gate_id": "internal_workflow_source_label_cleanup",
        "label": "Internal workflow and source labels cleaned up",
        "category": "prose",
        "minimum_maturity": "shareable_memo",
    },
    {
        "gate_id": "final_prose_pass",
        "label": "Final prose pass",
        "category": "prose",
        "minimum_maturity": "shareable_memo",
    },
    {
        "gate_id": "related_work_synthesis",
        "label": "Related-work completeness",
        "category": "related_work",
        "minimum_maturity": "working_paper",
    },
    {
        "gate_id": "contribution_statement",
        "label": "Contribution statement",
        "category": "argument",
        "minimum_maturity": "working_paper",
    },
    {
        "gate_id": "methods_detail",
        "label": "Methods specification",
        "category": "methods",
        "minimum_maturity": "working_paper",
    },
    {
        "gate_id": "reproducibility_notes",
        "label": "Reproducibility notes",
        "category": "reproducibility",
        "minimum_maturity": "working_paper",
    },
    {
        "gate_id": "formal_limitations",
        "label": "Limitations and caveats",
        "category": "limitations",
        "minimum_maturity": "working_paper",
    },
    {
        "gate_id": "formal_citations",
        "label": "Formal citations",
        "category": "citations",
        "minimum_maturity": "working_paper",
    },
    {
        "gate_id": "complete_bibliography",
        "label": "Complete bibliography",
        "category": "citations",
        "minimum_maturity": "working_paper",
    },
    {
        "gate_id": "target_venue_declared",
        "label": "Target venue declared",
        "category": "target",
        "minimum_maturity": "submission_ready_manuscript",
    },
    {
        "gate_id": "venue_style_compliance",
        "label": "Venue style compliance",
        "category": "target",
        "minimum_maturity": "submission_ready_manuscript",
    },
    {
        "gate_id": "formal_references",
        "label": "Formal references",
        "category": "citations",
        "minimum_maturity": "submission_ready_manuscript",
    },
    {
        "gate_id": "data_code_availability",
        "label": "Data and code availability",
        "category": "reproducibility",
        "minimum_maturity": "submission_ready_manuscript",
    },
    {
        "gate_id": "figure_table_requirements",
        "label": "Venue figure and table requirements",
        "category": "figures_tables",
        "minimum_maturity": "submission_ready_manuscript",
    },
)
MANUSCRIPT_GATE_BY_ID = {item["gate_id"]: item for item in MANUSCRIPT_GATES}
MANUSCRIPT_GATE_IDS = tuple(MANUSCRIPT_GATE_BY_ID)

INDEPENDENCE_ORDER = {
    "none": 0,
    "same_agent_visible": 1,
    "separate_agent": 2,
    "different_model": 3,
    "human": 4,
    "external": 5,
}
INDEPENDENCE_CHOICES = tuple(INDEPENDENCE_ORDER)
MINIMUM_INDEPENDENCE_BY_MATURITY = {
    "research_note": "none",
    "internal_draft": "none",
    "shareable_memo": "same_agent_visible",
    "working_paper": "separate_agent",
    "submission_ready_manuscript": "different_model",
}
INDEPENDENCE_CEILING = {
    "none": "internal_draft",
    "same_agent_visible": "internal_draft",
    "separate_agent": "working_paper",
    "different_model": "submission_ready_manuscript",
    "human": "submission_ready_manuscript",
    "external": "submission_ready_manuscript",
}


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def field_has_value(value: Any) -> bool:
    return str(value or "").strip().lower() not in NO_VALUE_MARKERS


def normalized_unique(values: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def parse_key_value_options(values: Iterable[str], option_name: str) -> tuple[dict[str, str], list[dict[str, Any]]]:
    parsed: dict[str, str] = {}
    errors: list[dict[str, Any]] = []
    for raw in values:
        text = str(raw or "").strip()
        if "=" not in text:
            errors.append(
                {
                    "reason": "invalid_key_value_option",
                    "message": f"{option_name} must use gate_id=value syntax",
                    "value": text,
                }
            )
            continue
        key, value = text.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key not in MANUSCRIPT_GATE_BY_ID:
            errors.append(
                {
                    "reason": "unknown_manuscript_gate",
                    "message": f"{option_name} references an unknown manuscript gate",
                    "gate": key,
                }
            )
            continue
        if not value:
            errors.append(
                {
                    "reason": "empty_key_value_option",
                    "message": f"{option_name} requires a non-empty value",
                    "gate": key,
                }
            )
            continue
        parsed[key] = value
    return parsed, errors


def required_gates_for(maturity: str) -> list[str]:
    target_level = MATURITY_ORDER[maturity]
    gates: list[str] = []
    for level in MATURITY_LEVELS:
        if int(level["level"]) <= target_level:
            gates.extend(GATES_BY_MATURITY[level["id"]])
    return normalized_unique(gates)


def minimum_independence_for(maturity: str) -> str:
    return MINIMUM_INDEPENDENCE_BY_MATURITY[maturity]


def higher_independence(left: str, right: str) -> str:
    return left if INDEPENDENCE_ORDER[left] >= INDEPENDENCE_ORDER[right] else right


def manuscript_gate_required(gate_id: str, target_maturity: str) -> bool:
    definition = MANUSCRIPT_GATE_BY_ID[gate_id]
    return MATURITY_ORDER[target_maturity] >= MATURITY_ORDER[definition["minimum_maturity"]]


def gate_status_is_satisfied(row: dict[str, Any]) -> bool:
    status = str(row.get("status") or "missing")
    if status not in PASSING_GATE_STATUSES:
        return False
    if status == "waived_by_human" and not field_has_value(row.get("waiver_rationale")):
        return False
    return True


def default_manuscript_gate_row(gate_id: str, target_maturity: str, completed: set[str], now: str | None = None) -> dict[str, Any]:
    definition = MANUSCRIPT_GATE_BY_ID[gate_id]
    required = manuscript_gate_required(gate_id, target_maturity)
    if gate_id in completed:
        status = "passed"
    elif required:
        status = "missing"
    else:
        status = "not_required"
    return {
        "gate_id": gate_id,
        "label": definition["label"],
        "category": definition["category"],
        "minimum_maturity": definition["minimum_maturity"],
        "required": required,
        "status": status,
        "rationale": "",
        "waiver_rationale": "",
        "evidence": [],
        "updated_at": now,
    }


def existing_manuscript_gate_map(deliverable: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = deliverable.get("manuscript_gates", [])
    if not isinstance(rows, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        gate_id = str(row.get("gate_id") or "")
        if gate_id in MANUSCRIPT_GATE_BY_ID:
            result[gate_id] = row
    return result


def normalized_manuscript_gates(deliverable: dict[str, Any], target_maturity: str, now: str | None = None) -> list[dict[str, Any]]:
    completed = set(str(item) for item in deliverable.get("completed_gates", []) if str(item or "").strip())
    existing = existing_manuscript_gate_map(deliverable)
    rows: list[dict[str, Any]] = []
    for gate_id in MANUSCRIPT_GATE_IDS:
        row = default_manuscript_gate_row(gate_id, target_maturity, completed, now)
        current = existing.get(gate_id)
        if isinstance(current, dict):
            for field in ("status", "rationale", "waiver_rationale", "updated_at"):
                if field in current:
                    row[field] = current[field]
            evidence = current.get("evidence", [])
            if isinstance(evidence, list):
                row["evidence"] = [str(item) for item in evidence if str(item or "").strip()]
        row["required"] = manuscript_gate_required(gate_id, target_maturity)
        if row["required"] and row["status"] == "not_required":
            row["status"] = "passed" if gate_id in completed else "missing"
        elif not row["required"] and row["status"] == "missing":
            row["status"] = "not_required"
        rows.append(row)
    return rows


def sync_completed_gates(required_gates: list[str], completed_gates: list[str], manuscript_gates: list[dict[str, Any]]) -> list[str]:
    manuscript_ids = set(MANUSCRIPT_GATE_IDS)
    synced = [gate for gate in completed_gates if gate not in manuscript_ids]
    for gate in required_gates:
        if gate not in manuscript_ids:
            continue
        row = next((item for item in manuscript_gates if item.get("gate_id") == gate), None)
        if row is not None and gate_status_is_satisfied(row):
            synced.append(gate)
    return normalized_unique(synced)


def apply_manuscript_gate_options(
    rows: list[dict[str, Any]],
    args: argparse.Namespace,
    now: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    status_updates, status_errors = parse_key_value_options(args.manuscript_gate or [], "--manuscript-gate")
    rationale_updates, rationale_errors = parse_key_value_options(args.gate_rationale or [], "--gate-rationale")
    waiver_updates, waiver_errors = parse_key_value_options(args.waiver_rationale or [], "--waiver-rationale")
    evidence_updates, evidence_errors = parse_key_value_options(args.gate_evidence or [], "--gate-evidence")
    errors = status_errors + rationale_errors + waiver_errors + evidence_errors
    by_id = {row["gate_id"]: row for row in rows}
    for gate in args.complete_gate or []:
        if gate == "all":
            for row in rows:
                if row.get("required"):
                    row["status"] = "passed"
                    row["updated_at"] = now
        elif gate in by_id:
            by_id[gate]["status"] = "passed"
            by_id[gate]["updated_at"] = now
    for gate_id, status in status_updates.items():
        if status not in GATE_STATUS_CHOICES:
            errors.append(
                {
                    "reason": "invalid_manuscript_gate_status",
                    "message": "manuscript gate status is not supported",
                    "gate": gate_id,
                    "status": status,
                    "allowed_statuses": list(GATE_STATUS_CHOICES),
                }
            )
            continue
        by_id[gate_id]["status"] = status
        by_id[gate_id]["updated_at"] = now
    for gate_id, rationale in rationale_updates.items():
        by_id[gate_id]["rationale"] = rationale
        by_id[gate_id]["updated_at"] = now
    for gate_id, rationale in waiver_updates.items():
        by_id[gate_id]["waiver_rationale"] = rationale
        by_id[gate_id]["updated_at"] = now
    for gate_id, evidence in evidence_updates.items():
        current = by_id[gate_id].get("evidence")
        evidence_rows = current if isinstance(current, list) else []
        evidence_rows.append(evidence)
        by_id[gate_id]["evidence"] = normalized_unique(evidence_rows)
        by_id[gate_id]["updated_at"] = now
    for row in rows:
        if row.get("status") == "waived_by_human" and not field_has_value(row.get("waiver_rationale")):
            errors.append(
                {
                    "reason": "waiver_rationale_required",
                    "message": "waived_by_human manuscript gates require waiver_rationale",
                    "gate": row.get("gate_id"),
                }
            )
    return rows, errors


def manuscript_gate_shape_errors(rows: Any, item_path: str) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    if rows is None:
        return errors
    if not isinstance(rows, list):
        return [{"reason": "manuscript_gates_not_array", "path": item_path, "message": "manuscript_gates must be an array"}]
    for index, row in enumerate(rows):
        row_path = f"{item_path}/manuscript_gates/{index}"
        if not isinstance(row, dict):
            errors.append({"reason": "manuscript_gate_not_object", "path": row_path, "message": "manuscript gate entries must be objects"})
            continue
        gate_id = str(row.get("gate_id") or "")
        if gate_id not in MANUSCRIPT_GATE_BY_ID:
            errors.append({"reason": "unknown_manuscript_gate", "path": row_path, "message": "gate_id must be a known manuscript gate", "gate": gate_id})
        status = str(row.get("status") or "")
        if status not in GATE_STATUS_CHOICES:
            errors.append(
                {
                    "reason": "invalid_manuscript_gate_status",
                    "path": row_path,
                    "message": "status must be a known manuscript gate status",
                    "gate": gate_id,
                    "status": status,
                }
            )
        if status == "waived_by_human" and not field_has_value(row.get("waiver_rationale")):
            errors.append(
                {
                    "reason": "waiver_rationale_required",
                    "path": row_path,
                    "message": "waived_by_human manuscript gates require waiver_rationale",
                    "gate": gate_id,
                }
            )
        evidence = row.get("evidence", [])
        if not isinstance(evidence, list):
            errors.append({"reason": "manuscript_gate_evidence_not_array", "path": row_path, "message": "evidence must be an array"})
    return errors


def critic_review_shape_errors(rows: Any, item_path: str) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    if rows is None:
        return errors
    if not isinstance(rows, list):
        return [{"reason": "critic_reviews_not_array", "path": item_path, "message": "critic_reviews must be an array"}]
    for index, row in enumerate(rows):
        row_path = f"{item_path}/critic_reviews/{index}"
        if not isinstance(row, dict):
            errors.append({"reason": "critic_review_not_object", "path": row_path, "message": "critic review entries must be objects"})
            continue
        review_id = str(row.get("review_id") or "")
        if not validate_critic_review_id(review_id):
            errors.append({"reason": "invalid_critic_review_id", "path": row_path, "message": "review_id must match CRITIC-0000", "review_id": review_id})
        role = str(row.get("reviewer_role") or "")
        if role not in CRITIC_REVIEWER_ROLE_CHOICES:
            errors.append({"reason": "invalid_critic_reviewer_role", "path": row_path, "message": "reviewer_role must be a known critic role", "reviewer_role": role})
        independence = str(row.get("independence_type") or "")
        if independence not in INDEPENDENCE_ORDER:
            errors.append({"reason": "invalid_critic_independence", "path": row_path, "message": "independence_type must be a known independence level", "independence_type": independence})
        status = str(row.get("status") or "")
        if status not in CRITIC_REVIEW_STATUS_CHOICES:
            errors.append({"reason": "invalid_critic_review_status", "path": row_path, "message": "status must be a known critic review status", "status": status})
        ceiling = str(row.get("recommended_maturity_ceiling") or "")
        if ceiling not in MATURITY_ORDER:
            errors.append({"reason": "invalid_critic_maturity_ceiling", "path": row_path, "message": "recommended_maturity_ceiling must be a known maturity level", "recommended_maturity_ceiling": ceiling})
        confidence = row.get("confidence")
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= confidence <= 1:
            errors.append({"reason": "invalid_critic_confidence", "path": row_path, "message": "confidence must be a number between 0 and 1"})
        distribution = row.get("severity_distribution")
        if not isinstance(distribution, dict):
            errors.append({"reason": "critic_severity_distribution_not_object", "path": row_path, "message": "severity_distribution must be an object"})
        else:
            for level in SEVERITY_LEVELS:
                count = distribution.get(level, 0)
                if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                    errors.append({"reason": "invalid_critic_severity_count", "path": row_path, "message": f"{level} severity count must be a non-negative integer", "severity": level})
        required_revision_rows = row.get("required_revision_rows", [])
        if not isinstance(required_revision_rows, list):
            errors.append({"reason": "critic_required_revision_rows_not_array", "path": row_path, "message": "required_revision_rows must be an array"})
        review_task_id = str(row.get("review_task_id") or "")
        if review_task_id and validate_task_ids([review_task_id]):
            errors.append({"reason": "invalid_critic_review_task_id", "path": row_path, "message": "review_task_id must match TASK-0000", "review_task_id": review_task_id})
        artifact_path = str(row.get("artifact_path") or "")
        if artifact_path and not safe_relative_path(artifact_path):
            errors.append({"reason": "unsafe_critic_artifact_path", "path": row_path, "message": "artifact_path must be relative to research_ops and cannot contain ..", "artifact_path": artifact_path})
    return errors


def manifest_path(ops_dir: Path) -> Path:
    return ops_dir / DELIVERABLES_DIR / MANIFEST_NAME


def projection_path(ops_dir: Path) -> Path:
    return ops_dir / DELIVERABLES_DIR / PROJECTION_NAME


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def empty_manifest() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "framework_version": FRAMEWORK_VERSION,
        "maturity_taxonomy": [dict(item) for item in MATURITY_LEVELS],
        "deliverables": [],
    }


def manifest_shape_errors(payload: dict[str, Any], path: Path) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    deliverables = payload.get("deliverables", [])
    if not isinstance(deliverables, list):
        return [{"reason": "deliverables_not_array", "path": str(path), "message": "deliverables must be an array"}]
    for index, item in enumerate(deliverables):
        item_path = f"{path}#/deliverables/{index}"
        if not isinstance(item, dict):
            errors.append({"reason": "deliverable_not_object", "path": item_path, "message": "deliverable entries must be objects"})
            continue
        deliverable_id = str(item.get("deliverable_id") or "")
        if not validate_deliverable_id(deliverable_id):
            errors.append({"reason": "invalid_deliverable_id", "path": item_path, "message": "deliverable_id must match DELIV-0000", "deliverable_id": deliverable_id})
        for field in ("target_maturity", "current_maturity"):
            value = str(item.get(field) or "")
            if value not in MATURITY_ORDER:
                errors.append({"reason": "invalid_maturity", "path": item_path, "message": f"{field} must be a known maturity level", "field": field, "value": value})
        source_task_ids = item.get("source_task_ids", [])
        if not isinstance(source_task_ids, list):
            errors.append({"reason": "source_task_ids_not_array", "path": item_path, "message": "source_task_ids must be an array"})
        else:
            invalid_tasks = validate_task_ids(str(value) for value in source_task_ids)
            if invalid_tasks:
                errors.append({"reason": "invalid_source_task_id", "path": item_path, "message": "source task ids must match TASK-0000", "source_task_ids": invalid_tasks})
        for field in ("required_gates", "completed_gates", "open_gaps"):
            if not isinstance(item.get(field, []), list):
                errors.append({"reason": f"{field}_not_array", "path": item_path, "message": f"{field} must be an array"})
        errors.extend(manuscript_gate_shape_errors(item.get("manuscript_gates"), item_path))
        errors.extend(critic_review_shape_errors(item.get("critic_reviews"), item_path))
        review = item.get("review_independence", {})
        if not isinstance(review, dict):
            errors.append({"reason": "review_independence_not_object", "path": item_path, "message": "review_independence must be an object"})
            continue
        for field in ("minimum_required", "achieved"):
            value = str(review.get(field) or "")
            if value not in INDEPENDENCE_ORDER:
                errors.append({"reason": "invalid_review_independence", "path": item_path, "message": f"{field} must be a known independence level", "field": field, "value": value})
    return errors


def load_manifest(ops_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    path = manifest_path(ops_dir)
    if not path.exists():
        return empty_manifest(), []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return empty_manifest(), [{"reason": "manifest_malformed_json", "path": str(path), "message": str(exc)}]
    except OSError as exc:
        return empty_manifest(), [{"reason": "manifest_read_failed", "path": str(path), "message": str(exc)}]
    if not isinstance(payload, dict):
        return empty_manifest(), [{"reason": "manifest_not_object", "path": str(path), "message": "manifest JSON must be an object"}]
    errors: list[dict[str, Any]] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append({"reason": "schema_version_mismatch", "path": str(path), "message": "deliverable manifest schema_version must be 1.0"})
    if payload.get("framework_version") != FRAMEWORK_VERSION:
        errors.append({"reason": "framework_version_mismatch", "path": str(path), "message": f"deliverable manifest framework_version must be {FRAMEWORK_VERSION}"})
    payload.setdefault("maturity_taxonomy", [dict(item) for item in MATURITY_LEVELS])
    payload.setdefault("deliverables", [])
    errors.extend(manifest_shape_errors(payload, path))
    return payload, errors


def safe_relative_path(value: str) -> bool:
    if not value:
        return True
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts


def validate_deliverable_id(value: str) -> bool:
    return DELIVERABLE_ID_RE.fullmatch(value) is not None


def validate_task_ids(values: Iterable[str]) -> list[str]:
    errors = []
    for value in values:
        if TASK_ID_RE.fullmatch(value) is None:
            errors.append(value)
    return errors


def validate_critic_review_id(value: str) -> bool:
    return CRITIC_REVIEW_ID_RE.fullmatch(value) is not None


def next_deliverable_id(deliverables: list[dict[str, Any]]) -> str:
    existing = {
        int(match.group(1))
        for item in deliverables
        if isinstance(item, dict)
        for match in [re.match(r"^DELIV-([0-9]{4})$", str(item.get("deliverable_id", "")))]
        if match is not None
    }
    value = 1
    while value in existing:
        value += 1
    return f"DELIV-{value:04d}"


def next_critic_review_id(deliverable: dict[str, Any]) -> str:
    existing = {
        int(match.group(1))
        for item in critic_review_rows(deliverable)
        for match in [re.match(r"^CRITIC-([0-9]{4})$", str(item.get("review_id", "")))]
        if match is not None
    }
    value = 1
    while value in existing:
        value += 1
    return f"CRITIC-{value:04d}"


def find_deliverable(manifest: dict[str, Any], deliverable_id: str) -> dict[str, Any] | None:
    for item in manifest.get("deliverables", []):
        if isinstance(item, dict) and item.get("deliverable_id") == deliverable_id:
            return item
    return None


def source_task_statuses(ops_dir: Path, task_ids: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for task_id in task_ids:
        matches = sorted((ops_dir / "tasks").glob(f"{task_id}-*/status.json"))
        if not matches:
            rows.append({"task_id": task_id, "found": False, "accepted": False, "status": "missing", "path": ""})
            continue
        status_path = matches[0]
        try:
            payload = json.loads(status_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            rows.append(
                {
                    "task_id": task_id,
                    "found": True,
                    "accepted": False,
                    "status": "malformed",
                    "path": str(status_path.relative_to(ops_dir)),
                    "error": str(exc),
                }
            )
            continue
        status = str(payload.get("status") or "")
        rows.append(
            {
                "task_id": task_id,
                "found": True,
                "accepted": status == "accepted",
                "status": status or "missing",
                "title": str(payload.get("title") or ""),
                "path": str(status_path.relative_to(ops_dir)),
            }
        )
    return rows


def normalize_open_gap(index: int, text: str) -> dict[str, Any]:
    return {
        "gap_id": f"GAP-{index:04d}",
        "severity": "major",
        "description": text.strip(),
        "status": "open",
        "source": "deliverable_target",
    }


def severity_distribution(args: argparse.Namespace) -> dict[str, int]:
    return {
        "critical": args.critical_findings,
        "major": args.major_findings,
        "minor": args.minor_findings,
        "note": args.note_findings,
    }


def normalize_severity_distribution(value: Any) -> dict[str, int]:
    distribution = {level: 0 for level in SEVERITY_LEVELS}
    if not isinstance(value, dict):
        return distribution
    for level in SEVERITY_LEVELS:
        raw = value.get(level, 0)
        if isinstance(raw, int) and not isinstance(raw, bool) and raw >= 0:
            distribution[level] = raw
    return distribution


def critic_review_rows(deliverable: dict[str, Any]) -> list[dict[str, Any]]:
    rows = deliverable.get("critic_reviews", [])
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def completed_critic_reviews(deliverable: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in critic_review_rows(deliverable) if row.get("status") == "completed"]


def effective_critic_independence(deliverable: dict[str, Any]) -> str:
    achieved = "none"
    review = deliverable.get("review_independence")
    if isinstance(review, dict) and str(review.get("achieved") or "none") in INDEPENDENCE_ORDER:
        achieved = str(review.get("achieved") or "none")
    for row in completed_critic_reviews(deliverable):
        independence = str(row.get("independence_type") or "none")
        if independence in INDEPENDENCE_ORDER:
            achieved = higher_independence(achieved, independence)
    return achieved


def critic_review_required(target_maturity: str) -> bool:
    return MATURITY_ORDER[target_maturity] >= MATURITY_ORDER["working_paper"]


def critic_review_summary(deliverable: dict[str, Any], target_maturity: str) -> dict[str, Any]:
    rows = critic_review_rows(deliverable)
    completed = completed_critic_reviews(deliverable)
    required = critic_review_required(target_maturity)
    required_independence = minimum_independence_for(target_maturity)
    eligible = [
        row
        for row in completed
        if INDEPENDENCE_ORDER.get(str(row.get("independence_type") or "none"), 0) >= INDEPENDENCE_ORDER[required_independence]
    ]
    latest = rows[-1] if rows else None
    latest_completed = completed[-1] if completed else None
    eligible_review = eligible[-1] if eligible else None
    recommended_ceiling = critic_ceiling(deliverable)
    satisfied = not required or eligible_review is not None
    if not required:
        status = "not_required"
    elif not rows:
        status = "missing"
    elif eligible_review is None:
        status = "partial"
    else:
        status = "passed"
    return {
        "required": required,
        "status": status,
        "satisfied": satisfied,
        "required_independence": required_independence,
        "review_count": len(rows),
        "completed_count": len(completed),
        "eligible_review_id": eligible_review.get("review_id") if eligible_review else "",
        "latest_review": latest or {},
        "latest_completed_review": latest_completed or {},
        "severity_distribution": normalize_severity_distribution((latest_completed or latest or {}).get("severity_distribution", {})),
        "recommended_maturity_ceiling": recommended_ceiling,
        "required_revision_rows": list((latest_completed or latest or {}).get("required_revision_rows", []))
        if isinstance((latest_completed or latest or {}).get("required_revision_rows", []), list)
        else [],
    }


def critic_review_gate_satisfied(deliverable: dict[str, Any], target_maturity: str) -> bool:
    return bool(critic_review_summary(deliverable, target_maturity)["satisfied"])


def critic_ceiling(deliverable: dict[str, Any]) -> str:
    completed = completed_critic_reviews(deliverable)
    if not completed:
        return "shareable_memo"
    ceiling = str(completed[-1].get("recommended_maturity_ceiling") or "")
    return ceiling if ceiling in MATURITY_ORDER else "internal_draft"


def review_independence_payload(maturity: str, achieved: str = "none", reviewer: str = "", notes: str = "") -> dict[str, Any]:
    return {
        "minimum_required": minimum_independence_for(maturity),
        "achieved": achieved,
        "same_agent_review": achieved == "same_agent_visible",
        "reviewer": reviewer,
        "notes": notes,
    }


def build_deliverable(args: argparse.Namespace, manifest: dict[str, Any], now: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []
    deliverables = manifest.get("deliverables", [])
    deliverable_id = args.deliverable_id or next_deliverable_id(deliverables)
    if not validate_deliverable_id(deliverable_id):
        errors.append({"reason": "invalid_deliverable_id", "message": "deliverable id must match DELIV-0000", "deliverable_id": deliverable_id})
    if find_deliverable(manifest, deliverable_id) is not None:
        errors.append({"reason": "deliverable_exists", "message": f"{deliverable_id} already exists", "deliverable_id": deliverable_id})
    invalid_tasks = validate_task_ids(args.source_task or [])
    if invalid_tasks:
        errors.append({"reason": "invalid_source_task_id", "message": "source task ids must match TASK-0000", "source_task_ids": invalid_tasks})
    if args.primary_artifact and not safe_relative_path(args.primary_artifact):
        errors.append({"reason": "unsafe_primary_artifact", "message": "primary artifact must be relative to research_ops and cannot contain ..", "primary_artifact": args.primary_artifact})
    if errors:
        return None, errors

    target_maturity = args.target_maturity
    current_maturity = args.current_maturity
    required_gates = normalized_unique(required_gates_for(target_maturity) + list(args.required_gate or []))
    completed_gates: list[str] = []
    for gate in args.complete_gate or []:
        if gate == "all":
            completed_gates.extend(required_gates)
        else:
            completed_gates.append(gate)
    completed_gates = normalized_unique(completed_gates)
    manuscript_gates = normalized_manuscript_gates({"completed_gates": completed_gates}, target_maturity, now)
    manuscript_gates, gate_errors = apply_manuscript_gate_options(manuscript_gates, args, now)
    if gate_errors:
        errors.extend(gate_errors)
        return None, errors
    completed_gates = sync_completed_gates(required_gates, completed_gates, manuscript_gates)
    return {
        "schema_version": SCHEMA_VERSION,
        "framework_version": FRAMEWORK_VERSION,
        "deliverable_id": deliverable_id,
        "title": args.title.strip(),
        "output_type": args.output_type,
        "target_audience": (args.target_audience or "").strip(),
        "target_venue": (args.target_venue or "").strip(),
        "venue_style_profile": (args.venue_style_profile or "").strip(),
        "target_maturity": target_maturity,
        "current_maturity": current_maturity,
        "source_task_ids": normalized_unique(args.source_task or []),
        "primary_artifact": (args.primary_artifact or "").strip(),
        "owner": (args.owner or "").strip(),
        "required_gates": required_gates,
        "completed_gates": completed_gates,
        "manuscript_gates": manuscript_gates,
        "critic_reviews": [],
        "review_independence": review_independence_payload(
            target_maturity,
            args.review_independence,
            args.reviewer or "",
            args.review_notes or "",
        ),
        "open_gaps": [normalize_open_gap(index, gap) for index, gap in enumerate(args.open_gap or [], start=1) if gap.strip()],
        "last_reviewed_at": args.last_reviewed_at,
        "created_at": now,
        "updated_at": now,
    }, []


def update_deliverable(args: argparse.Namespace, item: dict[str, Any], now: str) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    invalid_tasks = validate_task_ids(args.source_task or [])
    if invalid_tasks:
        errors.append({"reason": "invalid_source_task_id", "message": "source task ids must match TASK-0000", "source_task_ids": invalid_tasks})
    if args.primary_artifact and not safe_relative_path(args.primary_artifact):
        errors.append({"reason": "unsafe_primary_artifact", "message": "primary artifact must be relative to research_ops and cannot contain ..", "primary_artifact": args.primary_artifact})
    if errors:
        return errors

    if args.title:
        item["title"] = args.title.strip()
    for field in (
        "output_type",
        "target_audience",
        "target_venue",
        "venue_style_profile",
        "target_maturity",
        "current_maturity",
        "primary_artifact",
        "owner",
        "last_reviewed_at",
    ):
        value = getattr(args, field)
        if value is not None:
            item[field] = value.strip() if isinstance(value, str) else value
    if args.source_task:
        item["source_task_ids"] = normalized_unique(list(item.get("source_task_ids", [])) + list(args.source_task))
    if args.required_gate:
        item["required_gates"] = normalized_unique(list(item.get("required_gates", [])) + list(args.required_gate))
    target_maturity = item.get("target_maturity", "research_note")
    item["required_gates"] = normalized_unique(list(item.get("required_gates", [])) + required_gates_for(target_maturity))
    completed = list(item.get("completed_gates", []))
    for gate in args.complete_gate or []:
        if gate == "all":
            completed.extend(item.get("required_gates", []))
        else:
            completed.append(gate)
    item["completed_gates"] = normalized_unique(completed)
    manuscript_gates = normalized_manuscript_gates(item, target_maturity, now)
    manuscript_gates, gate_errors = apply_manuscript_gate_options(manuscript_gates, args, now)
    if gate_errors:
        return gate_errors
    item["manuscript_gates"] = manuscript_gates
    item["completed_gates"] = sync_completed_gates(item["required_gates"], item["completed_gates"], manuscript_gates)
    if args.clear_open_gaps:
        item["open_gaps"] = []
    if args.open_gap:
        existing = list(item.get("open_gaps", []))
        start = len(existing) + 1
        existing.extend(normalize_open_gap(index, gap) for index, gap in enumerate(args.open_gap, start=start) if gap.strip())
        item["open_gaps"] = existing
    review = item.get("review_independence")
    if not isinstance(review, dict):
        review = review_independence_payload(target_maturity)
    review["minimum_required"] = higher_independence(
        str(review.get("minimum_required") or "none"),
        minimum_independence_for(target_maturity),
    )
    if args.review_independence is not None:
        review["achieved"] = args.review_independence
        review["same_agent_review"] = args.review_independence == "same_agent_visible"
    if args.reviewer is not None:
        review["reviewer"] = args.reviewer
    if args.review_notes is not None:
        review["notes"] = args.review_notes
    item["review_independence"] = review
    item["updated_at"] = now
    return []


def build_critic_review(args: argparse.Namespace, deliverable: dict[str, Any], now: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []
    review_id = args.review_id or next_critic_review_id(deliverable)
    if not validate_critic_review_id(review_id):
        errors.append({"reason": "invalid_critic_review_id", "message": "review_id must match CRITIC-0000", "review_id": review_id})
    if any(row.get("review_id") == review_id for row in critic_review_rows(deliverable)):
        errors.append({"reason": "critic_review_exists", "message": f"{review_id} already exists", "review_id": review_id})
    if args.review_task_id and validate_task_ids([args.review_task_id]):
        errors.append({"reason": "invalid_critic_review_task_id", "message": "review_task_id must match TASK-0000", "review_task_id": args.review_task_id})
    if args.artifact_path and not safe_relative_path(args.artifact_path):
        errors.append({"reason": "unsafe_critic_artifact_path", "message": "artifact path must be relative to research_ops and cannot contain ..", "artifact_path": args.artifact_path})
    for level, count in severity_distribution(args).items():
        if count < 0:
            errors.append({"reason": "invalid_critic_severity_count", "message": "severity counts must be non-negative integers", "severity": level, "count": count})
    if not 0 <= args.confidence <= 1:
        errors.append({"reason": "invalid_critic_confidence", "message": "confidence must be a number between 0 and 1", "confidence": args.confidence})
    if errors:
        return None, errors
    return {
        "review_id": review_id,
        "reviewer_role": args.reviewer_role,
        "independence_type": args.independence_type,
        "reviewer": (args.reviewer or "").strip(),
        "model_or_reviewer": (args.model_or_reviewer or "").strip(),
        "confidence": args.confidence,
        "severity_distribution": severity_distribution(args),
        "recommended_maturity_ceiling": args.recommended_maturity_ceiling,
        "required_revision_rows": normalized_unique(args.required_revision_row or []),
        "review_task_id": (args.review_task_id or "").strip(),
        "artifact_path": (args.artifact_path or "").strip(),
        "status": args.status,
        "notes": (args.notes or "").strip(),
        "created_at": now,
        "updated_at": now,
    }, []


def apply_critic_review(args: argparse.Namespace, deliverable: dict[str, Any], now: str) -> list[dict[str, Any]]:
    critic, errors = build_critic_review(args, deliverable, now)
    if errors or critic is None:
        return errors
    reviews = critic_review_rows(deliverable)
    reviews.append(critic)
    deliverable["critic_reviews"] = reviews
    target_maturity = str(deliverable.get("target_maturity") or "research_note")
    deliverable["required_gates"] = normalized_unique(list(deliverable.get("required_gates", [])) + required_gates_for(target_maturity))
    if critic.get("status") == "completed" and critic_review_required(target_maturity) and critic_review_gate_satisfied(deliverable, target_maturity):
        deliverable["completed_gates"] = normalized_unique(list(deliverable.get("completed_gates", [])) + ["adversarial_review"])
    review = deliverable.get("review_independence")
    if not isinstance(review, dict):
        review = review_independence_payload(target_maturity)
    achieved = str(review.get("achieved") or "none")
    independence = str(critic.get("independence_type") or "none")
    review["achieved"] = higher_independence(achieved, independence)
    review["same_agent_review"] = review["achieved"] == "same_agent_visible"
    review["minimum_required"] = higher_independence(
        str(review.get("minimum_required") or "none"),
        minimum_independence_for(target_maturity),
    )
    if field_has_value(critic.get("reviewer")):
        review["reviewer"] = critic["reviewer"]
    review["notes"] = critic.get("notes") or review.get("notes", "")
    deliverable["review_independence"] = review
    deliverable["last_reviewed_at"] = now
    deliverable["updated_at"] = now
    return []


def gate_ceiling(deliverable: dict[str, Any]) -> str:
    completed = set(deliverable.get("completed_gates", []))
    highest = "research_note"
    for maturity in MATURITY_CHOICES:
        required = set(required_gates_for(maturity))
        manuscript_rows = {row["gate_id"]: row for row in normalized_manuscript_gates(deliverable, maturity)}
        manuscript_gate_ids = set(manuscript_rows)
        derived_required = {"adversarial_review"} & required
        non_manuscript_required = required - manuscript_gate_ids - derived_required
        manuscript_required = required & manuscript_gate_ids
        manuscript_complete = all(gate_status_is_satisfied(manuscript_rows[gate]) for gate in manuscript_required)
        derived_complete = all(critic_review_gate_satisfied(deliverable, maturity) for gate in derived_required)
        if non_manuscript_required.issubset(completed) and manuscript_complete and derived_complete:
            highest = maturity
    return highest


def metadata_ceiling(deliverable: dict[str, Any]) -> str:
    source_task_ids = deliverable.get("source_task_ids", [])
    if not isinstance(source_task_ids, list) or not source_task_ids:
        return "research_note"
    if not field_has_value(deliverable.get("target_audience")):
        return "internal_draft"
    if not field_has_value(deliverable.get("target_venue")):
        return "working_paper"
    return "submission_ready_manuscript"


def independence_ceiling(deliverable: dict[str, Any]) -> str:
    achieved = effective_critic_independence(deliverable)
    return INDEPENDENCE_CEILING.get(achieved, "internal_draft")


def min_maturity(*values: str) -> str:
    return min(values, key=lambda value: MATURITY_ORDER.get(value, 0))


def checklist(deliverable: dict[str, Any], target_maturity: str) -> list[dict[str, Any]]:
    completed = set(deliverable.get("completed_gates", []))
    manuscript_rows = {row["gate_id"]: row for row in normalized_manuscript_gates(deliverable, target_maturity)}
    rows = []
    for gate in required_gates_for(target_maturity):
        if gate in manuscript_rows:
            gate_row = manuscript_rows[gate]
            rows.append(
                {
                    "gate": gate,
                    "label": gate_row["label"],
                    "category": gate_row["category"],
                    "status": gate_row["status"],
                    "required": True,
                    "satisfied": gate_status_is_satisfied(gate_row),
                    "rationale": gate_row.get("rationale", ""),
                    "waiver_rationale": gate_row.get("waiver_rationale", ""),
                    "evidence": gate_row.get("evidence", []),
                }
            )
            continue
        if gate == "adversarial_review":
            critic = critic_review_summary(deliverable, target_maturity)
            rows.append(
                {
                    "gate": gate,
                    "status": critic["status"],
                    "required": True,
                    "satisfied": critic["satisfied"],
                    "critic_review": critic,
                }
            )
            continue
        rows.append(
            {
                "gate": gate,
                "status": "passed" if gate in completed else "missing",
                "required": True,
                "satisfied": gate in completed,
            }
        )
    return rows


def open_gap_rows(deliverable: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for item in deliverable.get("open_gaps", []):
        if isinstance(item, dict):
            rows.append(item)
        elif str(item).strip():
            rows.append(normalize_open_gap(len(rows) + 1, str(item)))
    return rows


def read_model(ops_dir: Path, deliverable: dict[str, Any], target_override: str | None = None) -> dict[str, Any]:
    target_maturity = target_override or str(deliverable.get("target_maturity") or "research_note")
    current_maturity = str(deliverable.get("current_maturity") or "research_note")
    source_tasks = source_task_statuses(ops_dir, [str(item) for item in deliverable.get("source_task_ids", [])])
    rows = checklist(deliverable, target_maturity)
    manuscript_rows = normalized_manuscript_gates(deliverable, target_maturity)
    missing_gates = [row for row in rows if not row.get("satisfied")]
    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    if MATURITY_ORDER[current_maturity] < MATURITY_ORDER[target_maturity]:
        blockers.append(
            {
                "reason": "current_maturity_below_target",
                "message": f"current maturity {current_maturity} is below target {target_maturity}",
                "current_maturity": current_maturity,
                "target_maturity": target_maturity,
            }
        )
    if MATURITY_ORDER[target_maturity] >= MATURITY_ORDER["internal_draft"] and not source_tasks:
        blockers.append({"reason": "source_tasks_missing", "message": "internal drafts and above must link accepted source tasks"})
    for task in source_tasks:
        if not task.get("accepted"):
            blockers.append(
                {
                    "reason": "source_task_not_accepted",
                    "message": f"{task['task_id']} is not an accepted source task",
                    "task_id": task["task_id"],
                    "status": task.get("status"),
                }
            )
    for row in missing_gates:
        blockers.append(
            {
                "reason": "gate_missing",
                "message": f"required gate {row['gate']} is not complete",
                "gate": row["gate"],
                "status": row.get("status"),
            }
        )
    for row in manuscript_rows:
        if not row.get("required"):
            continue
        status = str(row.get("status") or "missing")
        if status == "waived_by_human" and not field_has_value(row.get("waiver_rationale")):
            blockers.append(
                {
                    "reason": "waiver_rationale_required",
                    "message": "waived_by_human manuscript gates require waiver_rationale",
                    "gate": row.get("gate_id"),
                }
            )
        elif status == "passed_with_caveats":
            warnings.append(
                {
                    "reason": "manuscript_gate_passed_with_caveats",
                    "message": f"manuscript gate {row['gate_id']} passed with caveats",
                    "gate": row["gate_id"],
                    "rationale": row.get("rationale", ""),
                }
            )
    if MATURITY_ORDER[target_maturity] >= MATURITY_ORDER["shareable_memo"] and not field_has_value(deliverable.get("target_audience")):
        blockers.append({"reason": "target_audience_missing", "message": "shareable deliverables and above require target_audience"})
    if MATURITY_ORDER[target_maturity] >= MATURITY_ORDER["submission_ready_manuscript"] and not field_has_value(deliverable.get("target_venue")):
        blockers.append({"reason": "target_venue_missing", "message": "submission-ready manuscripts require target_venue"})

    review = deliverable.get("review_independence") if isinstance(deliverable.get("review_independence"), dict) else {}
    stored_achieved = str(review.get("achieved") or "none")
    achieved = effective_critic_independence(deliverable)
    required_independence = higher_independence(str(review.get("minimum_required") or "none"), minimum_independence_for(target_maturity))
    if INDEPENDENCE_ORDER.get(achieved, 0) < INDEPENDENCE_ORDER[required_independence]:
        blockers.append(
            {
                "reason": "review_independence_below_required",
                "message": f"review independence {achieved} is below required {required_independence}",
                "achieved": achieved,
                "minimum_required": required_independence,
            }
        )
    critic = critic_review_summary(deliverable, target_maturity)
    if critic["required"] and critic["review_count"] == 0:
        blockers.append({"reason": "critic_review_missing", "message": "working papers and above require a distinct adversarial critic review"})
    elif critic["required"] and not critic["satisfied"]:
        blockers.append(
            {
                "reason": "critic_review_independence_below_required",
                "message": f"critic review independence is below required {critic['required_independence']}",
                "required_independence": critic["required_independence"],
                "review_count": critic["review_count"],
                "completed_count": critic["completed_count"],
            }
        )
    if critic["required"] and MATURITY_ORDER[critic["recommended_maturity_ceiling"]] < MATURITY_ORDER[target_maturity]:
        blockers.append(
            {
                "reason": "critic_recommended_ceiling_below_target",
                "message": f"latest critic ceiling {critic['recommended_maturity_ceiling']} is below target {target_maturity}",
                "recommended_maturity_ceiling": critic["recommended_maturity_ceiling"],
                "target_maturity": target_maturity,
            }
        )
    if critic["required_revision_rows"]:
        warnings.append(
            {
                "reason": "critic_required_revision_rows_present",
                "message": "critic review has required revision rows that should be tracked in the response matrix",
                "required_revision_count": len(critic["required_revision_rows"]),
            }
        )
    gaps = open_gap_rows(deliverable)
    unresolved_gaps = [gap for gap in gaps if str(gap.get("status", "open")).lower() not in {"closed", "resolved", "waived"}]
    if unresolved_gaps and MATURITY_ORDER[target_maturity] >= MATURITY_ORDER["working_paper"]:
        blockers.append({"reason": "open_gaps_block_maturity", "message": "working papers and above cannot have unresolved open gaps", "open_gap_count": len(unresolved_gaps)})
    elif unresolved_gaps:
        warnings.append({"reason": "open_gaps_present", "message": "open gaps must stay visible until closed or waived", "open_gap_count": len(unresolved_gaps)})

    verified_ceiling = min_maturity(current_maturity, gate_ceiling(deliverable), metadata_ceiling(deliverable), independence_ceiling(deliverable), critic_ceiling(deliverable))
    target_ready = not blockers and MATURITY_ORDER[verified_ceiling] >= MATURITY_ORDER[target_maturity]
    if MATURITY_ORDER[current_maturity] > MATURITY_ORDER[verified_ceiling]:
        warnings.append(
            {
                "reason": "declared_current_maturity_exceeds_verified_ceiling",
                "message": f"declared current maturity {current_maturity} exceeds verified ceiling {verified_ceiling}",
                "current_maturity": current_maturity,
                "verified_maturity_ceiling": verified_ceiling,
            }
        )

    return {
        "deliverable_id": deliverable.get("deliverable_id"),
        "manifest_path": str(manifest_path(ops_dir)),
        "read_only": True,
        "target_ready": target_ready,
        "maturity": {
            "current": current_maturity,
            "target": target_maturity,
            "verified_ceiling": verified_ceiling,
            "gate_ceiling": gate_ceiling(deliverable),
            "metadata_ceiling": metadata_ceiling(deliverable),
            "independence_ceiling": independence_ceiling(deliverable),
            "critic_ceiling": critic_ceiling(deliverable),
            "taxonomy": [dict(item) for item in MATURITY_LEVELS],
        },
        "deliverable": {
            "title": deliverable.get("title"),
            "output_type": deliverable.get("output_type"),
            "target_audience": deliverable.get("target_audience"),
            "target_venue": deliverable.get("target_venue"),
            "venue_style_profile": deliverable.get("venue_style_profile", ""),
            "source_task_ids": deliverable.get("source_task_ids", []),
            "primary_artifact": deliverable.get("primary_artifact"),
        },
        "checklist": rows,
        "manuscript_checklist": manuscript_rows,
        "critic_review": critic,
        "review_independence": {
            **review,
            "minimum_required": required_independence,
            "same_agent_review": achieved == "same_agent_visible",
            "stored_achieved": stored_achieved,
            "achieved": achieved,
        },
        "source_tasks": source_tasks,
        "open_gaps": gaps,
        "blockers": blockers,
        "warnings": warnings,
    }


def markdown_escape(value: Any) -> str:
    text = str(value if value is not None else "").replace("\n", " ").strip()
    return re.sub(r"\s+", " ", text).replace("|", "\\|") or "none"


def write_projection(ops_dir: Path, manifest: dict[str, Any]) -> None:
    header = [
        "deliverable_id",
        "title",
        "output_type",
        "target_audience",
        "target_venue",
        "current_maturity",
        "target_maturity",
        "source_task_ids",
        "open_gaps",
        "manuscript_gates",
        "critic_review",
        "waivers",
    ]
    lines = [
        "# Deliverable Manifest",
        "",
        "This is the human-readable projection of `deliverable_manifest.json`.",
        "",
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    for item in manifest.get("deliverables", []):
        target_maturity = str(item.get("target_maturity") or "research_note")
        manuscript_rows = normalized_manuscript_gates(item, target_maturity)
        required_manuscript = [row for row in manuscript_rows if row.get("required")]
        satisfied_manuscript = [row for row in required_manuscript if gate_status_is_satisfied(row)]
        waived_manuscript = [row for row in required_manuscript if row.get("status") == "waived_by_human"]
        critic = critic_review_summary(item, target_maturity)
        row = {
            "deliverable_id": item.get("deliverable_id"),
            "title": item.get("title"),
            "output_type": item.get("output_type"),
            "target_audience": item.get("target_audience"),
            "target_venue": item.get("target_venue"),
            "current_maturity": item.get("current_maturity"),
            "target_maturity": item.get("target_maturity"),
            "source_task_ids": ", ".join(item.get("source_task_ids", [])),
            "open_gaps": len(open_gap_rows(item)),
            "manuscript_gates": f"{len(satisfied_manuscript)}/{len(required_manuscript)}",
            "critic_review": f"{critic['status']} ({critic['recommended_maturity_ceiling']})",
            "waivers": len(waived_manuscript),
        }
        lines.append("| " + " | ".join(markdown_escape(row.get(column)) for column in header) + " |")
    lines.append("")
    atomic_write_text(projection_path(ops_dir), "\n".join(lines))


def write_manifest(ops_dir: Path, manifest: dict[str, Any]) -> None:
    atomic_write_json(manifest_path(ops_dir), manifest)
    write_projection(ops_dir, manifest)


def cmd_init(args: argparse.Namespace) -> int:
    now = args.now or utc_now()
    manifest, errors = load_manifest(args.ops_dir)
    if errors:
        print_json({"ok": False, "action": "deliverable_init_failed", "errors": errors})
        return MALFORMED
    deliverable, build_errors = build_deliverable(args, manifest, now)
    if build_errors or deliverable is None:
        print_json({"ok": False, "action": "deliverable_init_failed", "errors": build_errors})
        return INVALID_REQUEST
    manifest["deliverables"].append(deliverable)
    write_manifest(args.ops_dir, manifest)
    model = read_model(args.ops_dir, deliverable)
    print_json({"ok": True, "action": "deliverable_initialized", **model})
    return SUCCESS


def cmd_target(args: argparse.Namespace) -> int:
    now = args.now or utc_now()
    manifest, errors = load_manifest(args.ops_dir)
    if errors:
        print_json({"ok": False, "action": "deliverable_target_failed", "errors": errors})
        return MALFORMED
    item = find_deliverable(manifest, args.deliverable_id)
    if item is None:
        print_json({"ok": False, "action": "deliverable_target_failed", "reason": "deliverable_missing", "deliverable_id": args.deliverable_id})
        return INVALID_REQUEST
    update_errors = update_deliverable(args, item, now)
    if update_errors:
        print_json({"ok": False, "action": "deliverable_target_failed", "errors": update_errors})
        return INVALID_REQUEST
    write_manifest(args.ops_dir, manifest)
    model = read_model(args.ops_dir, item)
    print_json({"ok": True, "action": "deliverable_target_updated", **model})
    return SUCCESS


def cmd_critic(args: argparse.Namespace) -> int:
    now = args.now or utc_now()
    manifest, errors = load_manifest(args.ops_dir)
    if errors:
        print_json({"ok": False, "action": "deliverable_critic_failed", "errors": errors})
        return MALFORMED
    item = find_deliverable(manifest, args.deliverable_id)
    if item is None:
        print_json({"ok": False, "action": "deliverable_critic_failed", "reason": "deliverable_missing", "deliverable_id": args.deliverable_id})
        return INVALID_REQUEST
    update_errors = apply_critic_review(args, item, now)
    if update_errors:
        print_json({"ok": False, "action": "deliverable_critic_failed", "errors": update_errors})
        return INVALID_REQUEST
    write_manifest(args.ops_dir, manifest)
    model = read_model(args.ops_dir, item)
    print_json({"ok": True, "action": "deliverable_critic_recorded", **model})
    return SUCCESS


def cmd_check(args: argparse.Namespace) -> int:
    manifest, errors = load_manifest(args.ops_dir)
    if errors:
        print_json({"ok": False, "action": "deliverable_check_failed", "read_only": True, "errors": errors})
        return MALFORMED
    item = find_deliverable(manifest, args.deliverable_id)
    if item is None:
        print_json({"ok": False, "action": "deliverable_check_failed", "read_only": True, "reason": "deliverable_missing", "deliverable_id": args.deliverable_id})
        return INVALID_REQUEST
    model = read_model(args.ops_dir, item, args.target_maturity)
    ok = bool(model["target_ready"])
    print_json({"ok": ok, "action": "deliverable_checked", **model})
    return SUCCESS if ok else VALIDATION_FAILED


def add_common_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("ops_dir", type=Path, help="Path to the research_ops workspace.")


def add_update_options(parser: argparse.ArgumentParser, *, init: bool) -> None:
    if init:
        parser.add_argument("--deliverable-id", help="Explicit deliverable id such as DELIV-0001; defaults to the next available id.")
        parser.add_argument("--title", required=True, help="Human-readable deliverable title.")
        parser.add_argument("--output-type", choices=OUTPUT_TYPE_CHOICES, required=True, help="Declared deliverable output type.")
        parser.add_argument("--target-maturity", choices=MATURITY_CHOICES, default="internal_draft", help="Intended maturity level.")
        parser.add_argument("--current-maturity", choices=MATURITY_CHOICES, default="research_note", help="Current declared maturity level.")
    else:
        parser.add_argument("deliverable_id", help="Deliverable id such as DELIV-0001.")
        parser.add_argument("--title", help="Human-readable deliverable title.")
        parser.add_argument("--output-type", choices=OUTPUT_TYPE_CHOICES, help="Declared deliverable output type.")
        parser.add_argument("--target-maturity", choices=MATURITY_CHOICES, help="Intended maturity level.")
        parser.add_argument("--current-maturity", choices=MATURITY_CHOICES, help="Current declared maturity level.")
    parser.add_argument("--target-audience", help="Known reader or audience for shareable and external deliverables.")
    parser.add_argument("--target-venue", help="Venue, publication, client, or submission target.")
    parser.add_argument("--venue-style-profile", help="Optional venue or style profile used for submission-readiness checks.")
    parser.add_argument("--source-task", action="append", default=[], help="Accepted source task id to link, such as TASK-0001. Repeatable.")
    parser.add_argument("--primary-artifact", help="Primary artifact path relative to research_ops.")
    parser.add_argument("--owner", help="Human or agent owner for maturity follow-through.")
    parser.add_argument("--required-gate", action="append", default=[], help="Additional required gate id to track. Repeatable.")
    parser.add_argument("--complete-gate", action="append", default=[], help="Completed gate id to mark; use `all` with target to complete all current required gates.")
    parser.add_argument(
        "--manuscript-gate",
        action="append",
        default=[],
        metavar="GATE=STATUS",
        help="Set a manuscript-quality gate status. Repeatable. Status values: " + ", ".join(GATE_STATUS_CHOICES),
    )
    parser.add_argument("--gate-rationale", action="append", default=[], metavar="GATE=TEXT", help="Attach rationale or caveat text to a manuscript gate.")
    parser.add_argument("--waiver-rationale", action="append", default=[], metavar="GATE=TEXT", help="Required human rationale for a waived manuscript gate.")
    parser.add_argument("--gate-evidence", action="append", default=[], metavar="GATE=TEXT", help="Attach evidence, artifact, or section reference to a manuscript gate.")
    parser.add_argument("--review-independence", choices=INDEPENDENCE_CHOICES, default="none" if init else None, help="Achieved review independence.")
    parser.add_argument("--reviewer", help="Reviewer identity or role for the latest maturity review.")
    parser.add_argument("--review-notes", help="Short review-independence note.")
    parser.add_argument("--open-gap", action="append", default=[], help="Open deliverable gap that must remain visible. Repeatable.")
    if not init:
        parser.add_argument("--clear-open-gaps", action="store_true", help="Clear open gaps after they are resolved or waived elsewhere.")
    else:
        parser.set_defaults(clear_open_gaps=False)
    parser.add_argument("--last-reviewed-at", help="ISO-8601 timestamp for the latest deliverable-level review.")
    parser.add_argument("--now", help="Override current timestamp for deterministic tests.")


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage deliverable maturity manifests and readiness checks.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="Create or append a deliverable maturity manifest entry.")
    add_common_options(init)
    add_update_options(init, init=True)
    init.set_defaults(func=cmd_init)

    target = subparsers.add_parser("target", help="Update target metadata, gates, and maturity status for one deliverable.")
    add_common_options(target)
    add_update_options(target, init=False)
    target.set_defaults(func=cmd_target)

    critic = subparsers.add_parser("critic", help="Record an adversarial critic review for one deliverable.")
    add_common_options(critic)
    critic.add_argument("deliverable_id", help="Deliverable id such as DELIV-0001.")
    critic.add_argument("--review-id", help="Explicit critic review id such as CRITIC-0001; defaults to the next available id.")
    critic.add_argument("--reviewer-role", choices=CRITIC_REVIEWER_ROLE_CHOICES, default="adversarial_critic", help="Critic role used for this deliverable-level review.")
    critic.add_argument("--independence-type", choices=INDEPENDENCE_CHOICES, required=True, help="Independence level achieved by this critic review.")
    critic.add_argument("--reviewer", help="Reviewer identity or role label.")
    critic.add_argument("--model-or-reviewer", help="Model name, human reviewer, or external reviewer identity when available.")
    critic.add_argument("--confidence", type=float, required=True, help="Reviewer confidence from 0 to 1.")
    critic.add_argument("--recommended-maturity-ceiling", choices=MATURITY_CHOICES, required=True, help="Highest maturity this critic review recommends before further revision.")
    critic.add_argument("--critical", type=int, default=0, dest="critical_findings", help="Number of critical critic findings.")
    critic.add_argument("--major", type=int, default=0, dest="major_findings", help="Number of major critic findings.")
    critic.add_argument("--minor", type=int, default=0, dest="minor_findings", help="Number of minor critic findings.")
    critic.add_argument("--note", type=int, default=0, dest="note_findings", help="Number of note-level critic findings.")
    critic.add_argument("--required-revision-row", action="append", default=[], help="Required revision or future response-matrix row. Repeatable.")
    critic.add_argument("--review-task-id", help="Optional critic_review task id that produced the review.")
    critic.add_argument("--artifact-path", help="Optional critic review artifact path relative to research_ops.")
    critic.add_argument("--status", choices=CRITIC_REVIEW_STATUS_CHOICES, default="completed", help="Lifecycle status for the critic review.")
    critic.add_argument("--notes", help="Short critic-stage notes.")
    critic.add_argument("--now", help="Override current timestamp for deterministic tests.")
    critic.set_defaults(func=cmd_critic)

    check = subparsers.add_parser("check", help="Read-only deliverable readiness check.")
    add_common_options(check)
    check.add_argument("deliverable_id", help="Deliverable id such as DELIV-0001.")
    check.add_argument("--target-maturity", choices=MATURITY_CHOICES, help="Override the target maturity for this check only.")
    check.set_defaults(func=cmd_check)
    return parser.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
