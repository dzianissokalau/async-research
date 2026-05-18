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
    ),
    "working_paper": (
        "related_work_synthesis",
        "contribution_statement",
        "methods_detail",
        "reproducibility_notes",
        "formal_limitations",
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
    return {
        "schema_version": SCHEMA_VERSION,
        "framework_version": FRAMEWORK_VERSION,
        "deliverable_id": deliverable_id,
        "title": args.title.strip(),
        "output_type": args.output_type,
        "target_audience": (args.target_audience or "").strip(),
        "target_venue": (args.target_venue or "").strip(),
        "target_maturity": target_maturity,
        "current_maturity": current_maturity,
        "source_task_ids": normalized_unique(args.source_task or []),
        "primary_artifact": (args.primary_artifact or "").strip(),
        "owner": (args.owner or "").strip(),
        "required_gates": required_gates,
        "completed_gates": completed_gates,
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
    for field in ("output_type", "target_audience", "target_venue", "target_maturity", "current_maturity", "primary_artifact", "owner", "last_reviewed_at"):
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


def gate_ceiling(deliverable: dict[str, Any]) -> str:
    completed = set(deliverable.get("completed_gates", []))
    highest = "research_note"
    for maturity in MATURITY_CHOICES:
        required = set(required_gates_for(maturity))
        if required.issubset(completed):
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
    review = deliverable.get("review_independence")
    achieved = "none"
    if isinstance(review, dict):
        achieved = str(review.get("achieved") or "none")
    return INDEPENDENCE_CEILING.get(achieved, "internal_draft")


def min_maturity(*values: str) -> str:
    return min(values, key=lambda value: MATURITY_ORDER.get(value, 0))


def checklist(deliverable: dict[str, Any], target_maturity: str) -> list[dict[str, Any]]:
    completed = set(deliverable.get("completed_gates", []))
    rows = []
    for gate in required_gates_for(target_maturity):
        rows.append(
            {
                "gate": gate,
                "status": "passed" if gate in completed else "missing",
                "required": True,
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
    missing_gates = [row["gate"] for row in rows if row["status"] != "passed"]
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
    for gate in missing_gates:
        blockers.append({"reason": "gate_missing", "message": f"required gate {gate} is not complete", "gate": gate})
    if MATURITY_ORDER[target_maturity] >= MATURITY_ORDER["shareable_memo"] and not field_has_value(deliverable.get("target_audience")):
        blockers.append({"reason": "target_audience_missing", "message": "shareable deliverables and above require target_audience"})
    if MATURITY_ORDER[target_maturity] >= MATURITY_ORDER["submission_ready_manuscript"] and not field_has_value(deliverable.get("target_venue")):
        blockers.append({"reason": "target_venue_missing", "message": "submission-ready manuscripts require target_venue"})

    review = deliverable.get("review_independence") if isinstance(deliverable.get("review_independence"), dict) else {}
    achieved = str(review.get("achieved") or "none")
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
    gaps = open_gap_rows(deliverable)
    unresolved_gaps = [gap for gap in gaps if str(gap.get("status", "open")).lower() not in {"closed", "resolved", "waived"}]
    if unresolved_gaps and MATURITY_ORDER[target_maturity] >= MATURITY_ORDER["working_paper"]:
        blockers.append({"reason": "open_gaps_block_maturity", "message": "working papers and above cannot have unresolved open gaps", "open_gap_count": len(unresolved_gaps)})
    elif unresolved_gaps:
        warnings.append({"reason": "open_gaps_present", "message": "open gaps must stay visible until closed or waived", "open_gap_count": len(unresolved_gaps)})

    verified_ceiling = min_maturity(current_maturity, gate_ceiling(deliverable), metadata_ceiling(deliverable), independence_ceiling(deliverable))
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
            "taxonomy": [dict(item) for item in MATURITY_LEVELS],
        },
        "deliverable": {
            "title": deliverable.get("title"),
            "output_type": deliverable.get("output_type"),
            "target_audience": deliverable.get("target_audience"),
            "target_venue": deliverable.get("target_venue"),
            "source_task_ids": deliverable.get("source_task_ids", []),
            "primary_artifact": deliverable.get("primary_artifact"),
        },
        "checklist": rows,
        "review_independence": {
            **review,
            "minimum_required": required_independence,
            "same_agent_review": achieved == "same_agent_visible",
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
    header = ["deliverable_id", "title", "output_type", "target_audience", "target_venue", "current_maturity", "target_maturity", "source_task_ids", "open_gaps"]
    lines = [
        "# Deliverable Manifest",
        "",
        "This is the human-readable projection of `deliverable_manifest.json`.",
        "",
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    for item in manifest.get("deliverables", []):
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
    parser.add_argument("--source-task", action="append", default=[], help="Accepted source task id to link, such as TASK-0001. Repeatable.")
    parser.add_argument("--primary-artifact", help="Primary artifact path relative to research_ops.")
    parser.add_argument("--owner", help="Human or agent owner for maturity follow-through.")
    parser.add_argument("--required-gate", action="append", default=[], help="Additional required gate id to track. Repeatable.")
    parser.add_argument("--complete-gate", action="append", default=[], help="Completed gate id to mark; use `all` with target to complete all current required gates.")
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
