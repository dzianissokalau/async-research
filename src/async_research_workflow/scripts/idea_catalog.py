#!/usr/bin/env python3
"""Initialize and maintain idea catalog workspace files."""

from __future__ import annotations

import argparse
import copy
from datetime import datetime
from datetime import timedelta
from datetime import timezone
import json
import os
from pathlib import Path
import re
import shutil
import sys
from typing import Any

from async_research_workflow.idea_catalog import CATALOG_FILE
from async_research_workflow.idea_catalog import CATALOG_BLOCK_END
from async_research_workflow.idea_catalog import CATALOG_BLOCK_START
from async_research_workflow.idea_catalog import CATALOG_TEMPLATE
from async_research_workflow.idea_catalog import IDEAS_DIR
from async_research_workflow.idea_catalog import PRIORITIZATION_BLOCKS
from async_research_workflow.idea_catalog import PRIORITIZATION_FILE
from async_research_workflow.idea_catalog import PRIORITIZATION_TEMPLATE
from async_research_workflow.idea_catalog import STORED_STATUSES
from async_research_workflow.idea_catalog import blockers_for_payload
from async_research_workflow.idea_catalog import candidate_summary
from async_research_workflow.idea_catalog import catalog_list_report
from async_research_workflow.idea_catalog import catalog_show_report
from async_research_workflow.idea_catalog import catalog_validation_exit_code
from async_research_workflow.idea_catalog import catalog_validation_report
from async_research_workflow.idea_catalog import catalog_validation_report_from_model
from async_research_workflow.idea_catalog import derived_display_label
from async_research_workflow.idea_catalog import hard_gate_blocked
from async_research_workflow.idea_catalog import markdown_cells
from async_research_workflow.idea_catalog import prioritization_markers
from async_research_workflow.idea_catalog import promotion_sort_key
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
CATALOG_LOCK_TTL = timedelta(minutes=30)
TIMESTAMP_PLACEHOLDER = "TO_BE_SET_AT_WRITE_TIME"


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


class CatalogLockError(RuntimeError):
    def __init__(self, payload: dict[str, Any]):
        super().__init__(str(payload.get("reason", "catalog_lock_error")))
        self.payload = payload


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def utc_timestamp(now: datetime | None = None) -> str:
    value = now or utc_now()
    return value.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def filename_timestamp(now: datetime | None = None) -> str:
    return utc_timestamp(now).replace("-", "").replace(":", "").replace("Z", "")


def parse_utc_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def read_lock_owner(lock_dir: Path) -> dict[str, Any]:
    owner_path = lock_dir / "owner.json"
    try:
        payload = json.loads(owner_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def stale_lock_target(lock_dir: Path, now: datetime) -> Path:
    base = lock_dir.with_name(f"LOCK.stale.{filename_timestamp(now)}")
    target = base
    index = 1
    while target.exists():
        target = lock_dir.with_name(f"{base.name}.{index}")
        index += 1
    return target


def acquire_catalog_lock(ops_dir: Path, command: str) -> dict[str, Any]:
    ideas_dir = ops_dir / IDEAS_DIR
    if not ideas_dir.exists():
        raise CatalogLockError(
            {
                "ok": False,
                "reason": "ideas_dir_missing",
                "message": "run async-research idea catalog init before write mode",
                "path": str(ideas_dir),
            }
        )
    if not ideas_dir.is_dir():
        raise CatalogLockError(
            {
                "ok": False,
                "reason": "ideas_path_not_directory",
                "message": "research_ops/ideas must be a directory",
                "path": str(ideas_dir),
            }
        )

    lock_dir = ideas_dir / "LOCK"
    now = utc_now()
    try:
        lock_dir.mkdir()
    except FileExistsError:
        owner = read_lock_owner(lock_dir)
        expires_at = parse_utc_timestamp(owner.get("lock_expires_at"))
        if expires_at is None or expires_at > now:
            raise CatalogLockError(
                {
                    "ok": False,
                    "reason": "catalog_locked",
                    "message": "another idea catalog write transaction owns research_ops/ideas/LOCK",
                    "lock_dir": str(lock_dir),
                    "owner": owner,
                }
            )
        stale_target = stale_lock_target(lock_dir, now)
        try:
            lock_dir.rename(stale_target)
            lock_dir.mkdir()
        except OSError as exc:
            raise CatalogLockError(
                {
                    "ok": False,
                    "reason": "catalog_lock_stale_rotation_failed",
                    "message": "stale catalog lock could not be moved before retry",
                    "lock_dir": str(lock_dir),
                    "stale_target": str(stale_target),
                    "error": str(exc),
                }
            ) from exc
    except OSError as exc:
        raise CatalogLockError(
            {
                "ok": False,
                "reason": "catalog_lock_create_failed",
                "message": "could not acquire research_ops/ideas/LOCK",
                "lock_dir": str(lock_dir),
                "error": str(exc),
            }
        ) from exc

    owner = {
        "command": command,
        "pid": os.getpid(),
        "started_at": utc_timestamp(now),
        "lock_expires_at": utc_timestamp(now + CATALOG_LOCK_TTL),
    }
    try:
        (lock_dir / "owner.json").write_text(json.dumps(owner, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except OSError as exc:
        shutil.rmtree(lock_dir, ignore_errors=True)
        raise CatalogLockError(
            {
                "ok": False,
                "reason": "catalog_lock_owner_write_failed",
                "message": "catalog lock was acquired but owner.json could not be written",
                "lock_dir": str(lock_dir),
                "error": str(exc),
            }
        ) from exc
    return {"lock_dir": str(lock_dir), "owner": owner}


def release_catalog_lock(lock: dict[str, Any] | None) -> None:
    if not lock:
        return
    lock_dir = Path(str(lock["lock_dir"]))
    shutil.rmtree(lock_dir, ignore_errors=True)


def markdown_cell(value: Any) -> str:
    if value is None:
        return ""
    text = " ".join(str(value).split())
    return text.replace("|", "\\|")


def score_cell(value: Any) -> str:
    if isinstance(value, bool):
        return ""
    if isinstance(value, (int, float)):
        return str(value)
    return ""


def generated_block(start_marker: str, rows: list[list[Any]], headers: list[str]) -> str:
    lines = [start_marker, "| " + " | ".join(headers) + " |"]
    separators = ["---:" if header.endswith("_score") else "---" for header in headers]
    lines.append("| " + " | ".join(separators) + " |")
    for row in rows:
        lines.append("| " + " | ".join(markdown_cell(value) for value in row) + " |")
    return "\n".join(lines)


def render_catalog_block(records: list[dict[str, Any]]) -> str:
    headers = ["idea_id", "status", "title", "weighted_score", "next_task", "blockers", "promoted_task_id", "updated_at"]
    rows = []
    for record in sorted(records, key=lambda item: str(item.get("idea_id") or item.get("filename_id") or "")):
        summary = candidate_summary(record)
        rows.append(
            [
                summary["idea_id"],
                summary["status"],
                summary["title"],
                score_cell(summary["weighted_score"]),
                summary.get("recommended_next_task") or "",
                ", ".join(summary["blockers"]),
                summary.get("promoted_task_id") or "",
                summary.get("updated_at") or "",
            ]
        )
    return generated_block(CATALOG_BLOCK_START, rows, headers) + "\n" + CATALOG_BLOCK_END


def prioritization_records(section: str, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if section == "RECOMMENDED-PROMOTIONS":
        return sorted([record for record in records if record["status"] == "promote"], key=promotion_sort_key)
    if section == "PARKED":
        return sorted([record for record in records if record["status"] == "park"], key=lambda item: str(item["idea_id"]))
    if section == "REJECTED":
        return sorted([record for record in records if record["status"] == "reject"], key=lambda item: str(item["idea_id"]))
    if section == "BLOCKERS":
        return sorted(
            [
                record
                for record in records
                if blockers_for_payload(record["payload"]) or record["status"] == "needs_human"
            ],
            key=lambda item: str(item["idea_id"]),
        )
    return []


def render_prioritization_block(section: str, records: list[dict[str, Any]]) -> str:
    start_marker, end_marker = prioritization_markers(section)
    headers = ["idea_id", "status", "title", "weighted_score", "next_task", "reason", "updated_at"]
    rows = []
    for record in prioritization_records(section, records):
        payload = record["payload"]
        summary = candidate_summary(record)
        reason = payload.get("status_reason") or payload.get("human_gate_reason") or ", ".join(summary["blockers"])
        rows.append(
            [
                summary["idea_id"],
                summary["status"],
                summary["title"],
                score_cell(summary["weighted_score"]),
                summary.get("recommended_next_task") or "",
                reason or "",
                summary.get("updated_at") or "",
            ]
        )
    return generated_block(start_marker, rows, headers) + "\n" + end_marker


def replace_generated_block(content: bytes, start_marker: str, end_marker: str, replacement: str) -> bytes:
    start = start_marker.encode("utf-8")
    end = end_marker.encode("utf-8")
    start_index = content.find(start)
    end_index = content.find(end)
    if start_index == -1 or end_index == -1 or end_index < start_index:
        raise ValueError("generated_block_missing_or_malformed")
    end_index += len(end)
    return content[:start_index] + replacement.encode("utf-8") + content[end_index:]


def projection_base_bytes(path: Path, template: str) -> bytes:
    if path.exists():
        return path.read_bytes()
    return template.encode("utf-8")


def render_catalog_projection_bytes(ops_dir: Path, records: list[dict[str, Any]]) -> bytes:
    path = ops_dir / IDEAS_DIR / CATALOG_FILE
    content = projection_base_bytes(path, CATALOG_TEMPLATE)
    return replace_generated_block(content, CATALOG_BLOCK_START, CATALOG_BLOCK_END, render_catalog_block(records))


def render_prioritization_projection_bytes(ops_dir: Path, records: list[dict[str, Any]]) -> bytes:
    path = ops_dir / IDEAS_DIR / PRIORITIZATION_FILE
    content = projection_base_bytes(path, PRIORITIZATION_TEMPLATE)
    for section in PRIORITIZATION_BLOCKS:
        start_marker, end_marker = prioritization_markers(section)
        content = replace_generated_block(content, start_marker, end_marker, render_prioritization_block(section, records))
    return content


def atomic_write_bytes(path: Path, content: bytes) -> bool:
    if path.exists() and path.read_bytes() == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    temp_path.write_bytes(content)
    temp_path.replace(path)
    return True


def json_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def record_for_payload(ops_dir: Path, payload: dict[str, Any], path: Path | None = None) -> dict[str, Any]:
    idea_id = str(payload.get("id") or "").strip()
    target = path or (ops_dir / IDEAS_DIR / f"{idea_id}.json")
    return {
        "path": str(target),
        "filename_id": target.stem,
        "idea_id": idea_id,
        "status": str(payload.get("status") or "candidate"),
        "derived_label": derived_display_label(payload),
        "payload": payload,
    }


def records_after_payloads(ops_dir: Path, model: dict[str, Any], payloads_by_path: dict[Path, dict[str, Any]]) -> list[dict[str, Any]]:
    records_by_path: dict[str, dict[str, Any]] = {
        str(record["path"]): {
            **record,
            "payload": copy.deepcopy(record["payload"]),
        }
        for record in model["candidates"]
    }
    for path, payload in payloads_by_path.items():
        records_by_path[str(path)] = record_for_payload(ops_dir, payload, path)
    return sorted(records_by_path.values(), key=lambda item: str(item.get("idea_id") or item.get("filename_id") or ""))


def validate_records_for_write(ops_dir: Path, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for record in records:
        _warnings, record_failures = validate_candidate_record(record, ops_dir)
        failures.extend(record_failures)
    return failures


def write_catalog_outputs(
    ops_dir: Path,
    model: dict[str, Any],
    payloads_by_path: dict[Path, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    records = records_after_payloads(ops_dir, model, payloads_by_path)
    validation_failures = validate_records_for_write(ops_dir, records)
    if validation_failures:
        return [], validation_failures, {}

    try:
        catalog_bytes = render_catalog_projection_bytes(ops_dir, records)
        prioritization_bytes = render_prioritization_projection_bytes(ops_dir, records)
    except (OSError, ValueError) as exc:
        return [], [
            {
                "severity": "failure",
                "reason": "generated_projection_render_failed",
                "message": str(exc),
                "path": str(ops_dir / IDEAS_DIR),
                "category": "malformed",
            }
        ], {}

    files_written: list[dict[str, Any]] = []
    try:
        for path in sorted(payloads_by_path):
            changed = atomic_write_bytes(path, json_bytes(payloads_by_path[path]))
            if changed:
                files_written.append({"path": str(path), "action": "write_canonical_idea_json"})

        projection_paths = {
            ops_dir / IDEAS_DIR / CATALOG_FILE: catalog_bytes,
            ops_dir / IDEAS_DIR / PRIORITIZATION_FILE: prioritization_bytes,
        }
        for path, content in projection_paths.items():
            changed = atomic_write_bytes(path, content)
            if changed:
                files_written.append({"path": str(path), "action": "regenerate_projection"})
    except OSError as exc:
        return files_written, [
            {
                "severity": "failure",
                "reason": "catalog_write_failed",
                "message": str(exc),
                "path": str(ops_dir / IDEAS_DIR),
                "category": "malformed",
            }
        ], {}

    post_model = read_catalog(ops_dir)
    validation = catalog_validation_report_from_model(ops_dir, post_model)
    return files_written, validation.get("failures", []), validation


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


def catalog_marker_details(row: dict[str, Any]) -> dict[str, Any] | None:
    match = CATALOG_MARKER_RE.search(combined_row_text(row))
    if not match:
        return None
    raw_status = match.group(1).lower().strip()
    defaulted = raw_status not in STORED_STATUSES
    return {
        "status": raw_status if not defaulted else "candidate",
        "raw_marker": raw_status,
        "marker_text": match.group(0),
        "defaulted": defaulted,
    }


def catalog_marker(row: dict[str, Any]) -> str | None:
    details = catalog_marker_details(row)
    return str(details["status"]) if details else None


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
    model: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if model is None:
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
        "proposed_decision_history_entry": {
            "at": TIMESTAMP_PLACEHOLDER,
            "from_status": current,
            "to_status": target,
            "reason": recommendation["reason"],
            "actor": "catalog_maintenance_dry_run",
        },
    }


def apply_status_update(
    payload: dict[str, Any],
    target_status: str,
    reason: str,
    revisit_condition: str | None,
    actor: str,
    now: datetime,
) -> tuple[dict[str, Any], bool]:
    updated = copy.deepcopy(payload)
    before = copy.deepcopy(updated)
    current_status = str(updated.get("status") or "candidate")
    updated["status"] = target_status
    updated["status_reason"] = reason

    if target_status == "needs_human":
        updated["human_gate_reason"] = f"catalog maintenance write recommends human review: {reason}"
    if target_status == "park":
        updated["revisit_condition"] = revisit_condition or "Revisit after a human reviews this catalog status."
    if target_status == "reject":
        updated["revisit_condition"] = revisit_condition or "Reopen only if a human records a new decision."

    if updated == before:
        return updated, False

    history = updated.get("decision_history")
    if not isinstance(history, list):
        history = []
    history.append(
        {
            "at": utc_timestamp(now),
            "from_status": current_status,
            "to_status": target_status,
            "reason": reason,
            "actor": actor,
        }
    )
    updated["decision_history"] = history
    updated["updated_at"] = utc_timestamp(now)
    return updated, True


def find_catalog_record(model: dict[str, Any], idea_id: str) -> dict[str, Any] | None:
    matches = [record for record in model["candidates"] if record["idea_id"] == idea_id]
    if len(matches) == 1:
        return matches[0]
    return None


def duplicate_record_failure(model: dict[str, Any], idea_id: str) -> dict[str, Any] | None:
    matches = [record for record in model["candidates"] if record["idea_id"] == idea_id]
    if len(matches) <= 1:
        return None
    return {
        "severity": "failure",
        "reason": "duplicate_idea_id",
        "message": f"idea id {idea_id} appears in multiple canonical JSON files",
        "idea_id": idea_id,
        "paths": [record["path"] for record in matches],
        "category": "malformed",
    }


def capture_source_and_plan(args: argparse.Namespace, model: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    source_row, source_warnings, source_code = capture_source_from_args(args)
    if source_code != SUCCESS:
        return source_code, {
            "ok": False,
            "action": "idea_capture_failed",
            "ops_dir": str(args.ops_dir),
            "failures": source_warnings,
        }

    title = row_title(source_row) if source_row is not None else str(args.title or "").strip()
    if not title:
        return INVALID_REQUEST, {
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
    idea_id = args.idea_id or (row_idea_id(source_row) if source_row is not None else None)
    plan = build_capture_plan(args.ops_dir, idea_id, title, source_row, model=model)
    return SUCCESS, {
        "source_row": source_row,
        "source_warnings": source_warnings,
        "input": {
            "from_inbox": args.from_inbox,
            "title": args.title,
            "idea_id": args.idea_id,
        },
        **plan,
    }


def capture_write(args: argparse.Namespace) -> int:
    if args.dry_run:
        print_json(
            {
                "ok": False,
                "action": "idea_capture_failed",
                "reason": "conflicting_flags",
                "message": "use either --dry-run or --write, not both",
            }
        )
        return INVALID_REQUEST

    lock: dict[str, Any] | None = None
    try:
        lock = acquire_catalog_lock(args.ops_dir, "idea capture --write")
        model = read_catalog(args.ops_dir)
        if model["failures"]:
            print_json(
                {
                    "ok": False,
                    "action": "idea_capture_write_failed",
                    "reason": "catalog_read_failed",
                    "ops_dir": str(args.ops_dir),
                    "lock": lock,
                    "warnings": model["warnings"],
                    "failures": model["failures"],
                }
            )
            return catalog_validation_exit_code(catalog_validation_report_from_model(args.ops_dir, model))

        source_code, payload = capture_source_and_plan(args, model)
        if source_code != SUCCESS:
            print_json(payload)
            return source_code
        if payload["route"] != "create" or not payload.get("would_write"):
            print_json(
                {
                    "ok": False,
                    "action": "idea_capture_write_refused",
                    "reason": "capture_write_requires_create_plan",
                    "ops_dir": str(args.ops_dir),
                    "dry_run_plan": payload,
                }
            )
            return INVALID_REQUEST

        change = payload["would_write"][0]
        target_path = Path(str(change["path"]))
        if target_path.exists() and not args.update_existing:
            print_json(
                {
                    "ok": False,
                    "action": "idea_capture_write_refused",
                    "reason": "target_idea_exists",
                    "message": "refusing to overwrite existing canonical idea without --update-existing",
                    "path": str(target_path),
                }
            )
            return VALIDATION_FAILED

        now = utc_now()
        candidate = copy.deepcopy(change["content"])
        candidate.setdefault("created_at", utc_timestamp(now))
        candidate["updated_at"] = utc_timestamp(now)
        payloads_by_path = {target_path: candidate}
        files_written, failures, validation = write_catalog_outputs(args.ops_dir, model, payloads_by_path)
        if failures:
            print_json(
                {
                    "ok": False,
                    "action": "idea_capture_write_failed",
                    "reason": "post_write_validation_failed" if files_written else "proposed_catalog_validation_failed",
                    "ops_dir": str(args.ops_dir),
                    "failures": failures,
                    "files_written": files_written,
                }
            )
            return VALIDATION_FAILED

        print_json(
            {
                "ok": True,
                "action": "idea_capture_written",
                "ops_dir": str(args.ops_dir),
                "dry_run": False,
                "changed": bool(files_written),
                "lock": lock,
                "files_written": files_written,
                "candidate": candidate,
                "validation": {
                    "ok": validation.get("ok", False),
                    "candidate_count": validation.get("candidate_count", 0),
                    "warning_count": len(validation.get("warnings", [])),
                    "failure_count": len(validation.get("failures", [])),
                },
                "would_not_write": [
                    {"path": str(args.ops_dir / "queue.md"), "reason": "catalog capture write mode never edits queue.md"},
                    {"path": str(args.ops_dir / "tasks"), "reason": "catalog capture write mode never creates task folders"},
                ],
            }
        )
        return SUCCESS
    except CatalogLockError as exc:
        print_json({"ok": False, "action": "idea_capture_write_refused", **exc.payload})
        return VALIDATION_FAILED
    finally:
        release_catalog_lock(lock)


def run_capture(args: argparse.Namespace) -> int:
    if args.write:
        return capture_write(args)
    model = read_catalog(args.ops_dir)
    source_code, payload = capture_source_and_plan(args, model)
    if source_code != SUCCESS:
        print_json(payload)
        return source_code
    print_json(
        {
            "ok": True,
            "action": "idea_capture_planned",
            "ops_dir": str(args.ops_dir),
            "dry_run": True,
            **payload,
            "would_not_write": [
                {"path": str(args.ops_dir / "queue.md"), "reason": "catalog capture dry-run never edits queue.md"},
                {"path": str(args.ops_dir / "tasks"), "reason": "catalog capture dry-run never creates task folders"},
            ],
        }
    )
    return SUCCESS


def build_maintenance_plan(ops_dir: Path, model: dict[str, Any] | None = None) -> dict[str, Any]:
    inbox_rows, inbox_warnings = parse_markdown_table_rows(ops_dir / "discovery_inbox.md")
    if model is None:
        model = read_catalog(ops_dir)
    proposals: list[dict[str, Any]] = []
    ignored_rows: list[dict[str, Any]] = []
    proposed_changes: list[dict[str, Any]] = []
    for row in inbox_rows:
        marker_details = catalog_marker_details(row)
        if marker_details is None:
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
        plan = build_capture_plan(ops_dir, idea_id, row_title(row), row, model=model)
        proposal = {
            "row_id": row["row_id"],
            "catalog_marker": marker_details["status"],
            "raw_catalog_marker": marker_details["raw_marker"],
            "catalog_marker_text": marker_details["marker_text"],
            "catalog_marker_defaulted": marker_details["defaulted"],
            "item": row.get("item"),
            "title": row.get("title"),
            **plan,
        }
        proposals.append(proposal)
        proposed_changes.extend(proposal_without_content(change) for change in plan["would_write"])

    recommendations = [lifecycle_recommendation(record, ops_dir) for record in model["candidates"]]
    for recommendation in recommendations:
        change = status_update_change(recommendation)
        if change is not None:
            proposed_changes.append(change)

    return {
        "sources_read": {
            "discovery_inbox": {
                "path": str(ops_dir / "discovery_inbox.md"),
                "row_count": len(inbox_rows),
                "warnings": inbox_warnings,
            },
            "canonical_ideas": {
                "path": str(ops_dir / IDEAS_DIR),
                "candidate_count": model["candidate_count"],
                "warnings": model["warnings"],
                "failures": model["failures"],
            },
            "accepted_outputs_index": source_report(ops_dir / "accepted_outputs_index.md"),
            "rejected_ideas": source_report(ops_dir / "discovery" / "rejected_ideas.md"),
        },
        "inbox_capture_proposals": proposals,
        "ignored_inbox_rows": ignored_rows,
        "catalog_recommendations": recommendations,
        "proposed_file_changes": proposed_changes,
        "changed": bool(proposed_changes),
    }


def maintenance_payloads_from_plan(
    ops_dir: Path,
    model: dict[str, Any],
    plan: dict[str, Any],
    now: datetime,
    update_existing: bool = False,
) -> tuple[dict[Path, dict[str, Any]], list[dict[str, Any]]]:
    failures: list[dict[str, Any]] = []
    payloads_by_path: dict[Path, dict[str, Any]] = {}

    for proposal in plan["inbox_capture_proposals"]:
        if proposal.get("route") != "create":
            continue
        candidate = copy.deepcopy(proposal["proposal"]["candidate"])
        candidate.setdefault("created_at", utc_timestamp(now))
        candidate["updated_at"] = utc_timestamp(now)
        path = ops_dir / IDEAS_DIR / f"{candidate['id']}.json"
        if path.exists() and not update_existing:
            failures.append(
                {
                    "severity": "failure",
                    "reason": "target_idea_exists",
                    "message": "refusing to overwrite existing canonical idea without --update-existing",
                    "path": str(path),
                    "idea_id": candidate["id"],
                }
            )
            continue
        payloads_by_path[path] = candidate

    records_by_id = {record["idea_id"]: record for record in model["candidates"]}
    for change in plan["proposed_file_changes"]:
        if change.get("action") != "update_idea_status":
            continue
        idea_id = str(change["idea_id"])
        record = records_by_id.get(idea_id)
        duplicate = duplicate_record_failure(model, idea_id)
        if duplicate is not None:
            failures.append(duplicate)
            continue
        if record is None:
            failures.append(
                {
                    "severity": "failure",
                    "reason": "idea_not_found",
                    "message": "maintenance proposed a status update for a missing idea",
                    "idea_id": idea_id,
                    "path": change.get("path"),
                }
            )
            continue
        fields = change.get("fields", {})
        updated, changed = apply_status_update(
            record["payload"],
            str(change["to_status"]),
            str(change["reason"]),
            fields.get("revisit_condition") if isinstance(fields, dict) else None,
            "catalog_maintenance_write",
            now,
        )
        if changed:
            payloads_by_path[Path(str(record["path"]))] = updated

    return payloads_by_path, failures


def maintain_write(args: argparse.Namespace) -> int:
    if args.dry_run:
        print_json(
            {
                "ok": False,
                "action": "idea_catalog_maintenance_failed",
                "reason": "conflicting_flags",
                "message": "use either --dry-run or --write, not both",
            }
        )
        return INVALID_REQUEST

    lock: dict[str, Any] | None = None
    try:
        lock = acquire_catalog_lock(args.ops_dir, "idea catalog maintain --write")
        model = read_catalog(args.ops_dir)
        if model["failures"]:
            print_json(
                {
                    "ok": False,
                    "action": "idea_catalog_maintenance_write_failed",
                    "reason": "catalog_read_failed",
                    "ops_dir": str(args.ops_dir),
                    "lock": lock,
                    "warnings": model["warnings"],
                    "failures": model["failures"],
                }
            )
            return catalog_validation_exit_code(catalog_validation_report_from_model(args.ops_dir, model))

        plan = build_maintenance_plan(args.ops_dir, model)
        payloads_by_path, plan_failures = maintenance_payloads_from_plan(
            args.ops_dir,
            model,
            plan,
            utc_now(),
            update_existing=args.update_existing,
        )
        if plan_failures:
            print_json(
                {
                    "ok": False,
                    "action": "idea_catalog_maintenance_write_failed",
                    "reason": "unsafe_maintenance_write",
                    "ops_dir": str(args.ops_dir),
                    "failures": plan_failures,
                    "dry_run_plan": plan,
                }
            )
            return VALIDATION_FAILED

        files_written, failures, validation = write_catalog_outputs(args.ops_dir, model, payloads_by_path)
        if failures:
            print_json(
                {
                    "ok": False,
                    "action": "idea_catalog_maintenance_write_failed",
                    "reason": "post_write_validation_failed" if files_written else "proposed_catalog_validation_failed",
                    "ops_dir": str(args.ops_dir),
                    "failures": failures,
                    "files_written": files_written,
                    "dry_run_plan": plan,
                }
            )
            return VALIDATION_FAILED

        print_json(
            {
                "ok": True,
                "action": "idea_catalog_maintenance_written",
                "ops_dir": str(args.ops_dir),
                "dry_run": False,
                "changed": bool(files_written),
                "lock": lock,
                "files_written": files_written,
                **plan,
                "validation": {
                    "ok": validation.get("ok", False),
                    "candidate_count": validation.get("candidate_count", 0),
                    "warning_count": len(validation.get("warnings", [])),
                    "failure_count": len(validation.get("failures", [])),
                },
                "would_not_write": [
                    {"path": str(args.ops_dir / "queue.md"), "reason": "maintenance write mode never edits queue.md"},
                    {"path": str(args.ops_dir / "tasks"), "reason": "maintenance write mode never creates task folders"},
                ],
            }
        )
        return SUCCESS
    except CatalogLockError as exc:
        print_json({"ok": False, "action": "idea_catalog_maintenance_write_refused", **exc.payload})
        return VALIDATION_FAILED
    finally:
        release_catalog_lock(lock)


def run_maintain(args: argparse.Namespace) -> int:
    if args.write:
        return maintain_write(args)

    plan = build_maintenance_plan(args.ops_dir)
    print_json(
        {
            "ok": True,
            "action": "idea_catalog_maintenance_planned",
            "ops_dir": str(args.ops_dir),
            "dry_run": True,
            **plan,
            "would_not_write": [
                {"path": str(args.ops_dir / "queue.md"), "reason": "maintenance dry-run never edits queue.md"},
                {"path": str(args.ops_dir / "tasks"), "reason": "maintenance dry-run never creates task folders"},
            ],
        }
    )
    return SUCCESS


def status_change_plan(
    ops_dir: Path,
    model: dict[str, Any],
    idea_id: str,
    target_status: str,
    reason: str,
    revisit_condition: str | None,
    actor: str,
    now: datetime,
) -> tuple[int, dict[str, Any], dict[Path, dict[str, Any]]]:
    if not IDEA_ID_PATTERN.match(idea_id):
        return INVALID_REQUEST, {
            "ok": False,
            "action": "idea_status_change_failed",
            "reason": "invalid_idea_id",
            "idea_id": idea_id,
            "message": "idea id must use IDEA-0000 format",
        }, {}
    duplicate = duplicate_record_failure(model, idea_id)
    if duplicate is not None:
        return MALFORMED, {
            "ok": False,
            "action": "idea_status_change_failed",
            "reason": "duplicate_idea_id",
            "idea_id": idea_id,
            "failures": [duplicate],
        }, {}
    record = find_catalog_record(model, idea_id)
    if record is None:
        return INVALID_REQUEST, {
            "ok": False,
            "action": "idea_status_change_failed",
            "reason": "idea_not_found",
            "idea_id": idea_id,
            "next_step": "run async-research idea catalog list to inspect available ideas",
        }, {}

    updated, changed = apply_status_update(record["payload"], target_status, reason, revisit_condition, actor, now)
    change = {
        "action": "update_idea_status",
        "path": record["path"],
        "idea_id": idea_id,
        "from_status": record["status"],
        "to_status": target_status,
        "reason": reason,
        "fields": {
            "status": target_status,
            "status_reason": reason,
            "revisit_condition": updated.get("revisit_condition"),
        },
        "proposed_decision_history_entry": {
            "at": utc_timestamp(now) if changed else TIMESTAMP_PLACEHOLDER,
            "from_status": str(record["payload"].get("status") or "candidate"),
            "to_status": target_status,
            "reason": reason,
            "actor": actor,
        },
    }
    payloads_by_path = {Path(str(record["path"])): updated} if changed else {}
    return SUCCESS, {
        "ok": True,
        "action": "idea_status_change_planned",
        "ops_dir": str(ops_dir),
        "idea_id": idea_id,
        "dry_run": True,
        "changed": changed,
        "proposed_file_changes": [change] if changed else [],
        "proposal": change,
    }, payloads_by_path


def run_status_command(args: argparse.Namespace, target_status: str) -> int:
    if target_status == "park" and not args.revisit:
        print_json(
            {
                "ok": False,
                "action": "idea_status_change_failed",
                "reason": "missing_revisit_condition",
                "message": "parked ideas require --revisit",
            }
        )
        return INVALID_REQUEST
    if not args.reason:
        print_json(
            {
                "ok": False,
                "action": "idea_status_change_failed",
                "reason": "missing_status_reason",
                "message": f"{target_status} requires --reason",
            }
        )
        return INVALID_REQUEST
    if args.write and args.dry_run:
        print_json(
            {
                "ok": False,
                "action": "idea_status_change_failed",
                "reason": "conflicting_flags",
                "message": "use either --dry-run or --write, not both",
            }
        )
        return INVALID_REQUEST

    if not args.write:
        model = read_catalog(args.ops_dir)
        code, payload, _changes = status_change_plan(
            args.ops_dir,
            model,
            args.idea_id,
            target_status,
            args.reason,
            args.revisit,
            "catalog_status_dry_run",
            utc_now(),
        )
        print_json(payload)
        return code

    lock: dict[str, Any] | None = None
    try:
        lock = acquire_catalog_lock(args.ops_dir, f"idea {target_status} --write")
        model = read_catalog(args.ops_dir)
        if model["failures"]:
            print_json(
                {
                    "ok": False,
                    "action": "idea_status_change_write_failed",
                    "reason": "catalog_read_failed",
                    "ops_dir": str(args.ops_dir),
                    "warnings": model["warnings"],
                    "failures": model["failures"],
                }
            )
            return catalog_validation_exit_code(catalog_validation_report_from_model(args.ops_dir, model))
        code, payload, payloads_by_path = status_change_plan(
            args.ops_dir,
            model,
            args.idea_id,
            target_status,
            args.reason,
            args.revisit,
            "catalog_status_write",
            utc_now(),
        )
        if code != SUCCESS:
            print_json(payload)
            return code
        files_written, failures, validation = write_catalog_outputs(args.ops_dir, model, payloads_by_path)
        if failures:
            print_json(
                {
                    "ok": False,
                    "action": "idea_status_change_write_failed",
                    "reason": "post_write_validation_failed" if files_written else "proposed_catalog_validation_failed",
                    "ops_dir": str(args.ops_dir),
                    "failures": failures,
                    "files_written": files_written,
                    "dry_run_plan": payload,
                }
            )
            return VALIDATION_FAILED
        print_json(
            {
                **payload,
                "action": "idea_status_change_written",
                "dry_run": False,
                "changed": bool(files_written),
                "lock": lock,
                "files_written": files_written,
                "validation": {
                    "ok": validation.get("ok", False),
                    "candidate_count": validation.get("candidate_count", 0),
                    "warning_count": len(validation.get("warnings", [])),
                    "failure_count": len(validation.get("failures", [])),
                },
                "would_not_write": [
                    {"path": str(args.ops_dir / "queue.md"), "reason": "idea status write mode never edits queue.md"},
                    {"path": str(args.ops_dir / "tasks"), "reason": "idea status write mode never creates task folders"},
                ],
            }
        )
        return SUCCESS
    except CatalogLockError as exc:
        print_json({"ok": False, "action": "idea_status_change_write_refused", **exc.payload})
        return VALIDATION_FAILED
    finally:
        release_catalog_lock(lock)


def run_park(args: argparse.Namespace) -> int:
    return run_status_command(args, "park")


def run_reject(args: argparse.Namespace) -> int:
    return run_status_command(args, "reject")


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
        help="Preview or write catalog maintenance proposals.",
        description="Read discovery_inbox.md and canonical ideas, then plan or apply conservative capture and lifecycle maintenance.",
    )
    maintain.add_argument("ops_dir", type=Path, help="Path to the research_ops workspace.")
    maintain.add_argument("--dry-run", action="store_true", help="Preview proposals without writing; this is the default.")
    maintain.add_argument("--write", action="store_true", help="Apply safe maintenance changes under research_ops/ideas/LOCK.")
    maintain.add_argument("--update-existing", action="store_true", help="Allow write mode to replace an existing IDEA JSON target when a create plan races with an existing file.")
    maintain.set_defaults(func=run_maintain)

    capture = subparsers.add_parser(
        "capture",
        help="Preview or write explicit discovery-to-catalog capture.",
        description="Build or write one canonical IDEA JSON record from a discovery inbox row or explicit title.",
    )
    capture.add_argument("ops_dir", type=Path, help="Path to the research_ops workspace.")
    capture.add_argument("--from-inbox", help="Discovery inbox item id or row-N selector to capture explicitly.")
    capture.add_argument("--id", dest="idea_id", help="Canonical IDEA-0000 id for the proposed catalog record.")
    capture.add_argument("--title", help="Title for an explicit title-only capture proposal.")
    capture.add_argument("--dry-run", action="store_true", help="Preview proposals without writing; this is the default.")
    capture.add_argument("--write", action="store_true", help="Create the canonical IDEA JSON and regenerate projections under research_ops/ideas/LOCK.")
    capture.add_argument("--update-existing", action="store_true", help="Allow write mode to replace an existing IDEA JSON target.")
    capture.set_defaults(func=run_capture)

    park = subparsers.add_parser(
        "park",
        help="Preview or write an explicit catalog park decision.",
        description="Move one canonical catalog idea to park with a reason and revisit condition.",
    )
    park.add_argument("ops_dir", type=Path, help="Path to the research_ops workspace.")
    park.add_argument("idea_id", help="Canonical IDEA-0000 id to park.")
    park.add_argument("--reason", required=True, help="Reason for parking the idea.")
    park.add_argument("--revisit", required=True, help="Concrete condition for revisiting the parked idea.")
    park.add_argument("--dry-run", action="store_true", help="Preview the status change without writing; this is the default.")
    park.add_argument("--write", action="store_true", help="Apply the status change under research_ops/ideas/LOCK.")
    park.set_defaults(func=run_park)

    reject = subparsers.add_parser(
        "reject",
        help="Preview or write an explicit catalog rejection.",
        description="Move one canonical catalog idea to reject with a reason.",
    )
    reject.add_argument("ops_dir", type=Path, help="Path to the research_ops workspace.")
    reject.add_argument("idea_id", help="Canonical IDEA-0000 id to reject.")
    reject.add_argument("--reason", required=True, help="Reason for rejecting the idea.")
    reject.add_argument("--revisit", help="Optional reopen condition; a conservative default is used when omitted.")
    reject.add_argument("--dry-run", action="store_true", help="Preview the status change without writing; this is the default.")
    reject.add_argument("--write", action="store_true", help="Apply the status change under research_ops/ideas/LOCK.")
    reject.set_defaults(func=run_reject)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
