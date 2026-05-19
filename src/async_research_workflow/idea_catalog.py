"""Read-only idea catalog parsing and projection helpers."""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
from datetime import datetime
from datetime import timezone
import json
from pathlib import Path
import re
from typing import Any

from async_research_workflow.resources import schema_path
from async_research_workflow.scripts.validate_json_artifact import load_json
from async_research_workflow.scripts.validate_json_artifact import validate


IDEAS_DIR = "ideas"
CATALOG_FILE = "idea_catalog.md"
PRIORITIZATION_FILE = "prioritization.md"

CATALOG_BLOCK = "IDEA-CATALOG"
CATALOG_BLOCK_START = "<!-- IDEA-CATALOG: AUTO-MAINTAINED - DO NOT EDIT INSIDE THIS BLOCK -->"
CATALOG_BLOCK_END = "<!-- /IDEA-CATALOG -->"

PRIORITIZATION_BLOCKS = (
    "RECOMMENDED-PROMOTIONS",
    "PARKED",
    "REJECTED",
    "BLOCKERS",
)
STORED_STATUSES = (
    "candidate",
    "promote",
    "park",
    "reject",
    "promoted",
    "needs_human",
)
PROMOTABLE_NEXT_TASKS = {"hypothesis_card", "data_readiness", "literature_extract"}
PROMOTION_TASK_TYPES = ("literature_extract", "data_readiness", "hypothesis_card", "experiment_plan")
UNSAFE_DUPLICATE_STATUSES = {"duplicate", "near_duplicate"}
NONE_MARKERS = {"", "none", "n/a", "na", "tbd", "todo"}
MALFORMED_WARNING_REASONS = {
    "duplicate_idea_id",
    "filename_id_mismatch",
    "generated_block_missing",
    "generated_block_malformed",
    "malformed_markdown_table_row",
    "catalog_table_missing_idea_id_column",
}
MALFORMED_FAILURE_REASONS = {
    "ops_dir_missing",
    "ops_dir_not_directory",
    "ideas_path_not_directory",
    "malformed_candidate_json",
    "candidate_json_read_failed",
    "candidate_json_not_object",
    "candidate_json_missing_payload",
    "candidate_schema_validation_failed",
    "scored_idea_missing_mission_policy_version",
}
STALE_PROJECTION_SURFACE_REASONS = {
    "catalog_projection_missing",
    "prioritization_projection_missing",
    "duplicate_projection_row",
    "orphaned_projection_row",
    "orphaned_json_record",
    "generated_block_missing",
    "generated_block_malformed",
    "malformed_markdown_table_row",
    "catalog_table_missing_idea_id_column",
}
DATA_OR_EVIDENCE_GAP_REASONS = {
    "direct_experiment_route_blocked",
    "library_ref_unresolved",
    "missing_accepted_output_ref",
    "missing_cluster_ref",
    "missing_data_ref",
    "missing_rejected_idea_ref",
    "missing_rejected_result_ref",
    "needs_human_missing_human_gate_reason",
    "promote_failed_hard_gates",
    "promote_missing_recommended_next_task",
    "promote_score_threshold_missing",
    "promote_unsafe_next_task",
    "score_threshold_missing",
}
UNAVAILABLE = "unavailable"
SCORE_DIMENSIONS = (
    "decision_impact",
    "data_availability",
    "killability",
    "feasibility",
    "reuse_potential",
    "novelty",
    "robustness_risk",
    "cost",
)
ACTIVE_DASHBOARD_STATUSES = {"candidate", "promote", "needs_human"}
TERMINAL_TASK_STATUSES = {"accepted", "rejected"}
IDEA_ID_RE = re.compile(r"\bIDEA-[0-9]{4}\b")
TASK_ID_RE = re.compile(r"\bTASK-[0-9]{4}\b")
COST_AMOUNT_FIELDS = ("amount_usd", "cost_usd", "usd", "total_usd")
COST_COMPONENT_FIELDS = ("api_usd", "compute_usd")

CATALOG_TEMPLATE = f"""# Idea Catalog

{CATALOG_BLOCK_START}
| idea_id | status | title | weighted_score | next_task | blockers | promoted_task_id | updated_at |
| --- | --- | --- | ---: | --- | --- | --- | --- |
{CATALOG_BLOCK_END}

## Notes

Free-form notes. Tooling must not edit this section.
"""


def issue(severity: str, reason: str, path: Path, message: str, **details: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "severity": severity,
        "reason": reason,
        "path": str(path),
        "message": message,
    }
    payload.update(details)
    return payload


def prioritization_markers(section: str) -> tuple[str, str]:
    return (
        f"<!-- IDEA-PRIORITIZATION: {section} AUTO-MAINTAINED -->",
        f"<!-- /IDEA-PRIORITIZATION: {section} -->",
    )


def prioritization_template_section(section: str) -> str:
    start_marker, end_marker = prioritization_markers(section)
    return f"{start_marker}\n{end_marker}"


PRIORITIZATION_TEMPLATE = (
    "# Idea Prioritization\n\n"
    + "\n\n".join(prioritization_template_section(section) for section in PRIORITIZATION_BLOCKS)
    + "\n\n## Notes\n\nFree-form notes. Tooling must not edit this section.\n"
)


def markdown_cells(line: str) -> list[str]:
    text = line.strip()
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|"):
        text = text[:-1]
    return [cell.strip() for cell in text.split("|")]


def is_separator_row(cells: list[str]) -> bool:
    return bool(cells) and all(set(cell.replace(":", "").strip()) <= {"-"} for cell in cells)


def parse_markdown_table(block_text: str, path: Path, block_name: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    table_lines = [line for line in block_text.splitlines() if line.strip().startswith("|")]
    table = {"headers": [], "rows": [], "row_count": 0}
    warnings: list[dict[str, Any]] = []
    if not table_lines:
        return table, warnings

    headers = markdown_cells(table_lines[0])
    table["headers"] = headers
    data_lines = table_lines[1:]
    if data_lines and is_separator_row(markdown_cells(data_lines[0])):
        data_lines = data_lines[1:]

    for index, line in enumerate(data_lines, start=1):
        cells = markdown_cells(line)
        if len(cells) != len(headers):
            warnings.append(issue(
                "warning",
                "malformed_markdown_table_row",
                path,
                f"{block_name} row has {len(cells)} cells but expected {len(headers)}",
                block=block_name,
                row_index=index,
                row=line.strip(),
            ))
            continue
        table["rows"].append(dict(zip(headers, cells)))

    table["row_count"] = len(table["rows"])
    return table, warnings


def extract_generated_block(text: str, path: Path, block_name: str, start_marker: str, end_marker: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    warnings: list[dict[str, Any]] = []
    start = text.find(start_marker)
    end = text.find(end_marker)
    block = {
        "name": block_name,
        "start_marker": start_marker,
        "end_marker": end_marker,
        "present": start != -1 and end != -1 and start < end,
        "text": "",
        "table": {"headers": [], "rows": [], "row_count": 0},
    }
    if start == -1 or end == -1:
        missing = "start" if start == -1 else "end"
        warnings.append(issue(
            "warning",
            "generated_block_missing",
            path,
            f"{block_name} generated block is missing its {missing} marker",
            block=block_name,
            missing_marker=missing,
        ))
        return block, warnings
    if end < start:
        warnings.append(issue(
            "warning",
            "generated_block_malformed",
            path,
            f"{block_name} generated block end marker appears before start marker",
            block=block_name,
        ))
        return block, warnings

    block_text = text[start + len(start_marker):end]
    table, table_warnings = parse_markdown_table(block_text, path, block_name)
    block["text"] = block_text
    block["table"] = table
    warnings.extend(table_warnings)
    return block, warnings


def parse_catalog_projection(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    projection = {
        "path": str(path),
        "exists": path.exists(),
        "block": {
            "name": CATALOG_BLOCK,
            "present": False,
            "table": {"headers": [], "rows": [], "row_count": 0},
        },
        "row_ids": [],
    }
    warnings: list[dict[str, Any]] = []
    if not path.exists():
        warnings.append(issue("warning", "catalog_projection_missing", path, "ideas/idea_catalog.md is missing"))
        return projection, warnings

    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        warnings.append(issue("warning", "catalog_projection_read_failed", path, str(exc)))
        return projection, warnings
    except OSError as exc:
        warnings.append(issue("warning", "catalog_projection_read_failed", path, str(exc)))
        return projection, warnings

    block, block_warnings = extract_generated_block(text, path, CATALOG_BLOCK, CATALOG_BLOCK_START, CATALOG_BLOCK_END)
    projection["block"] = block
    warnings.extend(block_warnings)

    rows = block["table"]["rows"]
    headers = block["table"]["headers"]
    if rows and "idea_id" not in headers:
        warnings.append(issue(
            "warning",
            "catalog_table_missing_idea_id_column",
            path,
            "idea catalog generated table does not include an idea_id column",
        ))
    projection["row_ids"] = [str(row.get("idea_id", "")).strip() for row in rows if str(row.get("idea_id", "")).strip()]
    return projection, warnings


def parse_prioritization_projection(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    projection = {
        "path": str(path),
        "exists": path.exists(),
        "blocks": {},
    }
    warnings: list[dict[str, Any]] = []
    if not path.exists():
        warnings.append(issue("warning", "prioritization_projection_missing", path, "ideas/prioritization.md is missing"))
        return projection, warnings

    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        warnings.append(issue("warning", "prioritization_projection_read_failed", path, str(exc)))
        return projection, warnings
    except OSError as exc:
        warnings.append(issue("warning", "prioritization_projection_read_failed", path, str(exc)))
        return projection, warnings

    for section in PRIORITIZATION_BLOCKS:
        start_marker, end_marker = prioritization_markers(section)
        block, block_warnings = extract_generated_block(text, path, section, start_marker, end_marker)
        projection["blocks"][section] = block
        warnings.extend(block_warnings)
    return projection, warnings


def parse_candidate_json(path: Path) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, issue("failure", "malformed_candidate_json", path, str(exc))
    except UnicodeDecodeError as exc:
        return None, issue("failure", "malformed_candidate_json", path, str(exc))
    except OSError as exc:
        return None, issue("failure", "candidate_json_read_failed", path, str(exc))
    if not isinstance(payload, dict):
        return None, issue("failure", "candidate_json_not_object", path, "candidate JSON must be an object")
    return payload, None


def parse_lock_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def catalog_lock_warning(lock_dir: Path) -> dict[str, Any] | None:
    if not lock_dir.exists():
        return None
    owner_path = lock_dir / "owner.json"
    owner: dict[str, Any] = {}
    try:
        payload = json.loads(owner_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            owner = payload
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        owner = {}
    expires_at = parse_lock_timestamp(owner.get("lock_expires_at"))
    now = datetime.now(timezone.utc).replace(microsecond=0)
    stale = expires_at is not None and expires_at <= now
    return issue(
        "warning",
        "catalog_lock_stale" if stale else "catalog_lock_present",
        lock_dir,
        "research_ops/ideas/LOCK is stale and may be moved by the next write command"
        if stale
        else "research_ops/ideas/LOCK is present; write commands will refuse until it expires or is released",
        owner=owner,
    )


def hard_gate_blocked(payload: dict[str, Any]) -> bool:
    score = payload.get("score")
    if not isinstance(score, dict):
        return False
    gates = score.get("hard_gate_results")
    if not isinstance(gates, list):
        return False
    return any(isinstance(gate, dict) and gate.get("passed") is not True for gate in gates)


def derived_display_label(payload: dict[str, Any]) -> str:
    status = str(payload.get("status") or "candidate")
    if status == "candidate" and not isinstance(payload.get("score"), dict):
        return "raw"
    if status == "candidate" and hard_gate_blocked(payload):
        return "blocked"
    if status == "candidate" and isinstance(payload.get("score"), dict):
        return "scored"
    return status


def read_candidate_records(ideas_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for path in sorted(ideas_dir.glob("IDEA-*.json")):
        payload, error = parse_candidate_json(path)
        filename_id = path.stem
        if error is not None:
            failures.append(error)
            continue
        if payload is None:
            failures.append(issue(
                "failure",
                "candidate_json_missing_payload",
                path,
                "candidate JSON parser returned neither a payload nor an error",
            ))
            continue
        idea_id = str(payload.get("id", "")).strip()
        record = {
            "path": str(path),
            "filename_id": filename_id,
            "idea_id": idea_id,
            "status": str(payload.get("status") or "candidate"),
            "derived_label": derived_display_label(payload),
            "payload": payload,
        }
        if idea_id != filename_id:
            warnings.append(issue(
                "warning",
                "filename_id_mismatch",
                path,
                f"filename id {filename_id} does not match JSON id {idea_id or '<missing>'}",
                filename_id=filename_id,
                idea_id=idea_id,
            ))
        records.append(record)
    return records, warnings, failures


def duplicate_id_warnings(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    paths_by_id: dict[str, list[str]] = defaultdict(list)
    for record in records:
        if record["idea_id"]:
            paths_by_id[record["idea_id"]].append(record["path"])
    duplicates = {idea_id: paths for idea_id, paths in paths_by_id.items() if len(paths) > 1}
    warnings = [
        issue(
            "warning",
            "duplicate_idea_id",
            Path(paths[0]),
            f"idea id {idea_id} appears in multiple canonical JSON files",
            idea_id=idea_id,
            paths=paths,
        )
        for idea_id, paths in sorted(duplicates.items())
    ]
    return warnings, duplicates


def projection_staleness_warnings(records: list[dict[str, Any]], catalog_projection: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    row_ids = [str(item) for item in catalog_projection.get("row_ids", [])]
    json_ids = sorted(record["idea_id"] for record in records if record["idea_id"])
    row_id_set = set(row_ids)
    json_id_set = set(json_ids)
    catalog_path = Path(catalog_projection["path"])

    row_counts = Counter(row_ids)
    duplicate_rows = sorted(idea_id for idea_id, count in row_counts.items() if count > 1)
    for idea_id in duplicate_rows:
        warnings.append(issue(
            "warning",
            "duplicate_projection_row",
            catalog_path,
            f"idea id {idea_id} appears more than once in idea_catalog.md",
            idea_id=idea_id,
        ))

    orphaned_rows = sorted(row_id_set - json_id_set)
    for idea_id in orphaned_rows:
        warnings.append(issue(
            "warning",
            "orphaned_projection_row",
            catalog_path,
            f"idea_catalog.md row {idea_id} has no canonical JSON record",
            idea_id=idea_id,
        ))

    orphaned_json = sorted(json_id_set - row_id_set)
    if catalog_projection.get("exists") and catalog_projection.get("block", {}).get("present"):
        for idea_id in orphaned_json:
            warnings.append(issue(
                "warning",
                "orphaned_json_record",
                catalog_path,
                f"canonical JSON record {idea_id} is missing from idea_catalog.md",
                idea_id=idea_id,
            ))

    return warnings, {
        "json_ids": json_ids,
        "catalog_row_ids": row_ids,
        "duplicate_projection_rows": duplicate_rows,
        "orphaned_projection_rows": orphaned_rows,
        "orphaned_json_records": orphaned_json,
    }


def status_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    return dict(sorted(Counter(record["status"] for record in records).items()))


def derived_label_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    return dict(sorted(Counter(record["derived_label"] for record in records).items()))


def nonempty_text(value: Any) -> bool:
    return isinstance(value, str) and value.strip().lower() not in NONE_MARKERS


def text_contains(path: Path, needle: str) -> bool:
    if not needle or not path.exists() or not path.is_file():
        return False
    try:
        return needle.lower() in path.read_text(encoding="utf-8").lower()
    except (OSError, UnicodeDecodeError):
        return False


def candidate_schema_errors(payload: dict[str, Any]) -> list[dict[str, str]]:
    schema = load_json(schema_path("idea_candidate.schema.json"))
    if not isinstance(schema, dict):
        return [{"path": "$", "message": "idea candidate schema is not an object"}]
    return [error.to_dict() for error in validate(payload, schema)]


def candidate_issue(
    severity: str,
    reason: str,
    record: dict[str, Any],
    message: str,
    category: str = "validation",
    **details: Any,
) -> dict[str, Any]:
    path = Path(str(record.get("path", "")))
    payload = {
        "candidate_id": record.get("idea_id") or record.get("filename_id"),
        "category": category,
        **details,
    }
    return issue(severity, reason, path, message, **payload)


def warning_as_failure(warning: dict[str, Any]) -> dict[str, Any]:
    return {
        **warning,
        "severity": "failure",
        "category": "malformed",
        "message": f"catalog validation treats this parser warning as invalid state: {warning.get('message', '')}",
    }


def failed_gate_names(score: dict[str, Any]) -> list[str]:
    gates = score.get("hard_gate_results")
    if not isinstance(gates, list):
        return []
    return sorted(
        str(gate.get("gate"))
        for gate in gates
        if isinstance(gate, dict) and gate.get("passed") is not True and str(gate.get("gate", "")).strip()
    )


def numeric_score(score: dict[str, Any], field: str) -> int | float | None:
    value = score.get(field)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    return None


def ref_missing_failure(
    record: dict[str, Any],
    reason: str,
    ref_field: str,
    ref: str,
    target: Path,
    category: str = "validation",
) -> dict[str, Any]:
    return candidate_issue(
        "failure",
        reason,
        record,
        f"{ref_field} reference {ref} was not found in {target}",
        category=category,
        ref_field=ref_field,
        ref=ref,
        target=str(target),
    )


def task_id_exists(ops_dir: Path, task_id: str) -> bool:
    if text_contains(ops_dir / "queue.md", task_id):
        return True
    if text_contains(ops_dir / "accepted_outputs_index.md", task_id):
        return True

    tasks_dir = ops_dir / "tasks"
    if not tasks_dir.exists() or not tasks_dir.is_dir():
        return False
    for path in tasks_dir.glob(f"{task_id}*"):
        if path.is_dir():
            return True
    for status_path in tasks_dir.glob("*/status.json"):
        try:
            payload = json.loads(status_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and str(payload.get("id", "")).strip() == task_id:
            return True
    return False


def reference_issues(record: dict[str, Any], ops_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    payload = record["payload"]
    warnings: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    ref_targets = (
        ("accepted_output_refs", "missing_accepted_output_ref", ops_dir / "accepted_outputs_index.md"),
        ("rejected_idea_refs", "missing_rejected_idea_ref", ops_dir / "discovery" / "rejected_ideas.md"),
        ("rejected_result_refs", "missing_rejected_result_ref", ops_dir / "rejected_results.md"),
        ("data_refs", "missing_data_ref", ops_dir / "data_source_audit.md"),
    )
    for field, reason, target in ref_targets:
        refs = payload.get(field)
        if not isinstance(refs, list):
            continue
        for ref in [str(item).strip() for item in refs if str(item).strip()]:
            if not text_contains(target, ref):
                failures.append(ref_missing_failure(record, reason, field, ref, target))

    library_refs = payload.get("library_refs")
    if isinstance(library_refs, list):
        library_source = ops_dir / "library" / "source_library.md"
        for ref in [str(item).strip() for item in library_refs if str(item).strip()]:
            if not text_contains(library_source, ref):
                warnings.append(candidate_issue(
                    "warning",
                    "library_ref_unresolved",
                    record,
                    f"library_refs reference {ref} could not be resolved because the knowledge library is optional in this phase",
                    ref_field="library_refs",
                    ref=ref,
                    target=str(library_source),
                ))

    cluster_id = str(payload.get("cluster_id", "")).strip()
    if cluster_id and not text_contains(ops_dir / "discovery" / "clusters.md", cluster_id):
        failures.append(ref_missing_failure(
            record,
            "missing_cluster_ref",
            "cluster_id",
            cluster_id,
            ops_dir / "discovery" / "clusters.md",
        ))

    return warnings, failures


def validate_candidate_record(record: dict[str, Any], ops_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    payload = record["payload"]
    status = str(payload.get("status") or "candidate")
    next_task = str(payload.get("recommended_next_task") or "").strip()
    score = payload.get("score") if isinstance(payload.get("score"), dict) else None
    warnings: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    schema_errors = candidate_schema_errors(payload)
    if schema_errors:
        failures.append(candidate_issue(
            "failure",
            "candidate_schema_validation_failed",
            record,
            "candidate JSON failed idea_candidate.schema.json validation",
            category="malformed",
            errors=schema_errors,
        ))

    if score is not None and not nonempty_text(score.get("mission_policy_version")):
        failures.append(candidate_issue(
            "failure",
            "scored_idea_missing_mission_policy_version",
            record,
            "scored idea is missing score.mission_policy_version",
            category="malformed",
        ))

    if status == "promote":
        if not nonempty_text(payload.get("kill_reason")):
            failures.append(candidate_issue(
                "failure",
                "promote_missing_kill_reason",
                record,
                "promotable idea requires a kill_reason",
            ))
        if not nonempty_text(next_task):
            failures.append(candidate_issue(
                "failure",
                "promote_missing_recommended_next_task",
                record,
                "promotable idea requires recommended_next_task",
            ))
        elif next_task not in PROMOTABLE_NEXT_TASKS:
            failures.append(candidate_issue(
                "failure",
                "promote_unsafe_next_task",
                record,
                "promotable idea must route to hypothesis_card, data_readiness, or literature_extract",
                recommended_next_task=next_task,
            ))

        duplicate_status = str(payload.get("duplicate_status") or "new")
        if duplicate_status in UNSAFE_DUPLICATE_STATUSES:
            failures.append(candidate_issue(
                "failure",
                "promote_duplicate_or_near_duplicate",
                record,
                "duplicate or near-duplicate idea cannot be promoted",
                duplicate_status=duplicate_status,
            ))

    if next_task == "experiment_plan":
        failures.append(candidate_issue(
            "failure",
            "direct_experiment_route_blocked",
            record,
            "idea catalog cannot route directly from discovery to experiment_plan",
            recommended_next_task=next_task,
        ))

    if score is not None:
        threshold_fields = ("weighted_total", "promotion_threshold", "killability", "minimum_killability")
        missing_threshold_fields = [field for field in threshold_fields if numeric_score(score, field) is None]
        if missing_threshold_fields:
            target = failures if status == "promote" else warnings
            target.append(candidate_issue(
                "failure" if status == "promote" else "warning",
                "promote_score_threshold_missing" if status == "promote" else "score_threshold_missing",
                record,
                "scored idea is missing threshold fields",
                missing_fields=missing_threshold_fields,
            ))
        else:
            weighted_total = numeric_score(score, "weighted_total")
            promotion_threshold = numeric_score(score, "promotion_threshold")
            killability = numeric_score(score, "killability")
            minimum_killability = numeric_score(score, "minimum_killability")
            if status == "promote" and weighted_total is not None and promotion_threshold is not None and weighted_total < promotion_threshold:
                failures.append(candidate_issue(
                    "failure",
                    "promote_below_score_threshold",
                    record,
                    "promotable idea weighted score is below its recorded promotion threshold",
                    weighted_total=weighted_total,
                    promotion_threshold=promotion_threshold,
                ))
            if status == "promote" and killability is not None and minimum_killability is not None and killability < minimum_killability:
                failures.append(candidate_issue(
                    "failure",
                    "promote_below_minimum_killability",
                    record,
                    "promotable idea killability is below its recorded minimum",
                    killability=killability,
                    minimum_killability=minimum_killability,
                ))

        gates = failed_gate_names(score)
        if status == "promote" and gates:
            failures.append(candidate_issue(
                "failure",
                "promote_failed_hard_gates",
                record,
                "promotable idea has failed hard gates",
                failed_hard_gates=gates,
            ))

    if status in {"park", "reject"}:
        if not nonempty_text(payload.get("status_reason")) and not nonempty_text(payload.get("kill_reason")):
            failures.append(candidate_issue(
                "failure",
                "parked_or_rejected_missing_reason",
                record,
                "parked or rejected idea requires status_reason or kill_reason",
            ))
        if not nonempty_text(payload.get("revisit_condition")):
            failures.append(candidate_issue(
                "failure",
                "parked_or_rejected_missing_revisit_condition",
                record,
                "parked or rejected idea requires a concrete revisit_condition",
            ))

    if status == "needs_human" and not nonempty_text(payload.get("human_gate_reason")):
        failures.append(candidate_issue(
            "failure",
            "needs_human_missing_human_gate_reason",
            record,
            "needs_human idea requires human_gate_reason",
        ))

    if status == "promoted":
        promoted_task_id = str(payload.get("promoted_task_id") or "").strip()
        if not promoted_task_id:
            failures.append(candidate_issue(
                "failure",
                "promoted_missing_promoted_task_id",
                record,
                "promoted idea requires promoted_task_id",
            ))
        elif not task_id_exists(ops_dir, promoted_task_id):
            failures.append(candidate_issue(
                "failure",
                "stale_promoted_task_id",
                record,
                "promoted_task_id was not found in queue.md, tasks/, or accepted_outputs_index.md",
                promoted_task_id=promoted_task_id,
            ))

    ref_warnings, ref_failures = reference_issues(record, ops_dir)
    warnings.extend(ref_warnings)
    failures.extend(ref_failures)
    return warnings, failures


def catalog_validation_report_from_model(ops_dir: Path, model: dict[str, Any]) -> dict[str, Any]:
    warnings = [
        warning
        for warning in model["warnings"]
        if warning.get("reason") not in MALFORMED_WARNING_REASONS
    ]
    failures = list(model["failures"])

    for warning in model["warnings"]:
        if warning.get("reason") in MALFORMED_WARNING_REASONS:
            failures.append(warning_as_failure(warning))

    for record in model["candidates"]:
        record_warnings, record_failures = validate_candidate_record(record, ops_dir)
        warnings.extend(record_warnings)
        failures.extend(record_failures)

    return {
        "ok": not failures,
        "action": "idea_catalog_validated",
        "ops_dir": model["ops_dir"],
        "ideas_dir": model["ideas_dir"],
        "catalog_path": model["catalog_projection"]["path"],
        "prioritization_path": model["prioritization_projection"]["path"],
        "candidate_count": model["candidate_count"],
        "status_counts": model["status_counts"],
        "derived_label_counts": model["derived_label_counts"],
        "duplicate_idea_ids": model["duplicate_idea_ids"],
        "projection_staleness": model["projection_staleness"],
        "warnings": warnings,
        "failures": failures,
    }


def catalog_validation_report(ops_dir: Path) -> dict[str, Any]:
    return catalog_validation_report_from_model(ops_dir, read_catalog(ops_dir))


def catalog_validation_exit_code(report: dict[str, Any]) -> int:
    failures = report.get("failures", [])
    if not failures:
        return 0
    if any(item.get("category") == "malformed" or item.get("reason") in MALFORMED_FAILURE_REASONS for item in failures):
        return 4
    return 2


def blockers_for_payload(payload: dict[str, Any]) -> list[str]:
    score = payload.get("score")
    if not isinstance(score, dict):
        return []
    return failed_gate_names(score)


def candidate_summary(record: dict[str, Any]) -> dict[str, Any]:
    payload = record["payload"]
    score = payload.get("score") if isinstance(payload.get("score"), dict) else {}
    return {
        "idea_id": record["idea_id"],
        "filename_id": record["filename_id"],
        "status": record["status"],
        "derived_label": record["derived_label"],
        "title": str(payload.get("title") or ""),
        "weighted_score": score.get("weighted_total") if isinstance(score, dict) else None,
        "recommended_next_task": payload.get("recommended_next_task"),
        "human_priority": payload.get("human_priority"),
        "blockers": blockers_for_payload(payload),
        "promoted_task_id": payload.get("promoted_task_id"),
        "updated_at": payload.get("updated_at"),
        "path": record["path"],
    }


def complete_status_counts(counts: dict[str, int]) -> dict[str, int]:
    complete = {status: int(counts.get(status, 0)) for status in STORED_STATUSES}
    for status, count in sorted(counts.items()):
        if status not in complete:
            complete[status] = count
    return complete


def complete_pipeline_counts(counts: dict[str, int]) -> dict[str, int]:
    complete = {label: int(counts.get(label, 0)) for label in ("raw", "scored", "blocked")}
    for label, count in sorted(counts.items()):
        if label not in complete:
            complete[label] = count
    return complete


def surface_issue_summary(item: dict[str, Any]) -> dict[str, Any]:
    summary = {
        "reason": item.get("reason"),
        "candidate_id": item.get("candidate_id"),
        "path": item.get("path"),
        "message": item.get("message"),
    }
    for field in (
        "idea_id",
        "filename_id",
        "ref_field",
        "ref",
        "target",
        "recommended_next_task",
        "failed_hard_gates",
        "missing_fields",
        "block",
    ):
        if field in item:
            summary[field] = item[field]
    return {key: value for key, value in summary.items() if value not in (None, "", [])}


def issue_is_data_or_evidence_gap(item: dict[str, Any]) -> bool:
    reason = item.get("reason")
    if reason in DATA_OR_EVIDENCE_GAP_REASONS:
        return True
    gates = item.get("failed_hard_gates")
    if not isinstance(gates, list):
        return False
    evidence_words = ("data", "evidence", "source", "readiness", "accepted")
    return any(any(word in str(gate).lower() for word in evidence_words) for gate in gates)


def promotion_sort_key(record: dict[str, Any]) -> tuple[int, float, str]:
    summary = candidate_summary(record)
    priority = summary.get("human_priority")
    if not isinstance(priority, int) or isinstance(priority, bool):
        priority = 99
    weighted = summary.get("weighted_score")
    if not isinstance(weighted, (int, float)) or isinstance(weighted, bool):
        weighted = -1.0
    return priority, -float(weighted), str(summary.get("idea_id") or summary.get("filename_id") or "")


def catalog_surface_summary(ops_dir: Path, max_promotions: int = 5) -> dict[str, Any]:
    """Return a compact read-only catalog summary for operator surfaces."""
    model = read_catalog(ops_dir)
    validation = catalog_validation_report_from_model(ops_dir, model)
    validation_exit_code = catalog_validation_exit_code(validation)
    records = model["candidates"]
    status_summary = complete_status_counts(validation["status_counts"])
    derived_summary = complete_pipeline_counts(validation["derived_label_counts"])

    issues = validation["warnings"] + validation["failures"]
    stale_projection_warnings = [
        surface_issue_summary(item)
        for item in issues
        if item.get("reason") in STALE_PROJECTION_SURFACE_REASONS
    ]
    data_or_evidence_gaps = [
        surface_issue_summary(item)
        for item in issues
        if issue_is_data_or_evidence_gap(item)
    ]

    gaps_by_candidate: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for gap in data_or_evidence_gaps:
        candidate_id = str(gap.get("candidate_id") or gap.get("idea_id") or "")
        if candidate_id:
            gaps_by_candidate[candidate_id].append(gap)

    blocked_ideas: list[dict[str, Any]] = []
    for record in sorted(records, key=lambda item: str(item.get("idea_id") or item.get("filename_id") or "")):
        summary = candidate_summary(record)
        idea_id = str(summary.get("idea_id") or summary.get("filename_id") or "")
        gap_reasons = gaps_by_candidate.get(idea_id, [])
        if summary.get("derived_label") != "blocked" and not gap_reasons:
            continue
        blocked_ideas.append(
            {
                **summary,
                "data_or_evidence_gaps": gap_reasons,
            }
        )

    top_promotions = [
        candidate_summary(record)
        for record in sorted(
            [record for record in records if record["status"] == "promote"],
            key=promotion_sort_key,
        )[:max_promotions]
    ]

    return {
        "ok": validation["ok"],
        "validation_exit_code": validation_exit_code,
        "candidate_count": validation["candidate_count"],
        "status_counts": status_summary,
        "derived_label_counts": derived_summary,
        "parked_count": status_summary.get("park", 0),
        "rejected_count": status_summary.get("reject", 0),
        "blocked_count": derived_summary.get("blocked", 0),
        "top_recommended_promotions": top_promotions,
        "blocked_ideas": blocked_ideas,
        "data_or_evidence_gap_issues": data_or_evidence_gaps,
        "stale_projection_warnings": stale_projection_warnings,
        "warning_count": len(validation["warnings"]),
        "failure_count": len(validation["failures"]),
        "warnings": [surface_issue_summary(item) for item in validation["warnings"]],
        "failures": [surface_issue_summary(item) for item in validation["failures"]],
    }


def dashboard_available(value: Any) -> Any:
    if value is None:
        return UNAVAILABLE
    if isinstance(value, str) and not value.strip():
        return UNAVAILABLE
    return value


def dashboard_score_value(score: dict[str, Any] | None, field: str) -> Any:
    if not isinstance(score, dict):
        return UNAVAILABLE
    return dashboard_available(score.get(field))


def dashboard_issue_summary(item: dict[str, Any]) -> dict[str, Any]:
    summary = surface_issue_summary(item)
    summary["severity"] = item.get("severity", UNAVAILABLE)
    summary["category"] = item.get("category", "validation")
    return summary


def dashboard_issue_sort_key(item: dict[str, Any]) -> tuple[int, str, str, str]:
    severity_rank = 0 if item.get("severity") == "failure" else 1
    candidate_id = str(item.get("candidate_id") or item.get("idea_id") or "")
    return severity_rank, candidate_id, str(item.get("reason") or ""), str(item.get("path") or "")


def dashboard_issues_by_candidate(issues: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in issues:
        candidate_id = str(item.get("candidate_id") or item.get("idea_id") or "").strip()
        if candidate_id:
            grouped[candidate_id].append(item)
    for candidate_issues in grouped.values():
        candidate_issues.sort(key=dashboard_issue_sort_key)
    return grouped


def dashboard_idea_summary(record: dict[str, Any], issues_by_candidate: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    summary = candidate_summary(record)
    idea_id = str(summary.get("idea_id") or summary.get("filename_id") or "")
    payload = record["payload"]
    score = payload.get("score") if isinstance(payload.get("score"), dict) else None
    issues = issues_by_candidate.get(idea_id, [])
    return {
        "idea_id": dashboard_available(summary.get("idea_id")),
        "filename_id": dashboard_available(summary.get("filename_id")),
        "status": dashboard_available(summary.get("status")),
        "derived_label": dashboard_available(summary.get("derived_label")),
        "title": dashboard_available(summary.get("title")),
        "weighted_score": dashboard_score_value(score, "weighted_total"),
        "recommended_next_task": dashboard_available(summary.get("recommended_next_task")),
        "human_priority": dashboard_available(summary.get("human_priority")),
        "hard_gate_blockers": summary.get("blockers", []),
        "issue_count": len(issues),
        "top_issue_reasons": [str(item.get("reason")) for item in issues[:3] if item.get("reason")],
        "promoted_task_id": dashboard_available(summary.get("promoted_task_id")),
        "updated_at": dashboard_available(summary.get("updated_at")),
        "path": summary.get("path"),
    }


def dashboard_score_summary(record: dict[str, Any]) -> dict[str, Any]:
    payload = record["payload"]
    score = payload.get("score") if isinstance(payload.get("score"), dict) else None
    summary = candidate_summary(record)
    return {
        "idea_id": dashboard_available(summary.get("idea_id")),
        "title": dashboard_available(summary.get("title")),
        "status": dashboard_available(summary.get("status")),
        "score_available": isinstance(score, dict),
        "mission_policy_version": dashboard_score_value(score, "mission_policy_version"),
        "budget_mode": dashboard_score_value(score, "budget_mode"),
        "weighted_total": dashboard_score_value(score, "weighted_total"),
        "promotion_threshold": dashboard_score_value(score, "promotion_threshold"),
        "minimum_killability": dashboard_score_value(score, "minimum_killability"),
        "max_promotions_per_week": dashboard_score_value(score, "max_promotions_per_week"),
        "dimensions": {
            dimension: dashboard_score_value(score, dimension)
            for dimension in SCORE_DIMENSIONS
        },
        "hard_gate_failures": failed_gate_names(score) if isinstance(score, dict) else UNAVAILABLE,
        "score_explanation": dashboard_score_value(score, "score_explanation"),
    }


def dashboard_next_tasks(
    records: list[dict[str, Any]],
    issues_by_candidate: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if record["status"] not in ACTIVE_DASHBOARD_STATUSES:
            continue
        task = str(dashboard_available(record["payload"].get("recommended_next_task")))
        grouped[task].append(dashboard_idea_summary(record, issues_by_candidate))

    return [
        {
            "recommended_next_task": task,
            "idea_count": len(ideas),
            "ideas": sorted(ideas, key=lambda item: str(item.get("idea_id") or item.get("filename_id") or "")),
        }
        for task, ideas in sorted(
            grouped.items(),
            key=lambda item: (item[0] == UNAVAILABLE, item[0]),
        )
    ]


def dashboard_idea_task_links(records: list[dict[str, Any]], issues_by_candidate: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    for record in sorted(records, key=lambda item: str(item.get("idea_id") or item.get("filename_id") or "")):
        payload = record["payload"]
        promoted_task_id = str(payload.get("promoted_task_id") or "").strip()
        if not promoted_task_id:
            continue
        summary = candidate_summary(record)
        idea_id = str(summary.get("idea_id") or summary.get("filename_id") or "")
        issues = issues_by_candidate.get(idea_id, [])
        stale = any(item.get("reason") == "stale_promoted_task_id" for item in issues)
        if stale:
            link_status = "stale"
        elif summary.get("status") == "promoted":
            link_status = "available"
        else:
            link_status = "unverified_non_promoted_status"
        links.append(
            {
                "idea_id": dashboard_available(summary.get("idea_id")),
                "title": dashboard_available(summary.get("title")),
                "status": dashboard_available(summary.get("status")),
                "promoted_task_id": promoted_task_id,
                "link_status": link_status,
                "path": summary.get("path"),
            }
        )
    return links


def parse_trace_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.strptime(value[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def trace_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def rounded_hours(start: datetime | None, end: datetime | None) -> tuple[float | str, str | None]:
    if start is None or end is None:
        return UNAVAILABLE, "missing_timestamp"
    if end < start:
        return UNAVAILABLE, "backwards_timestamp_range"
    return round((end - start).total_seconds() / 3600, 2), None


def first_payload_datetime(payload: dict[str, Any], fields: tuple[str, ...]) -> tuple[datetime | None, str]:
    for field in fields:
        parsed = parse_trace_datetime(payload.get(field))
        if parsed is not None:
            return parsed, field
    return None, UNAVAILABLE


def decision_history(payload: dict[str, Any]) -> list[dict[str, Any]]:
    history = payload.get("decision_history")
    if not isinstance(history, list):
        return []
    return [entry for entry in history if isinstance(entry, dict)]


def transition_datetime(payload: dict[str, Any], to_status: str) -> tuple[datetime | None, str]:
    matches: list[tuple[datetime, str]] = []
    for index, entry in enumerate(decision_history(payload)):
        if str(entry.get("to_status") or "") != to_status:
            continue
        parsed = parse_trace_datetime(entry.get("at"))
        if parsed is not None:
            matches.append((parsed, f"decision_history[{index}].at"))
    if matches:
        return sorted(matches, key=lambda item: item[0])[0]

    current_status = str(payload.get("status") or "candidate")
    if to_status == "candidate" and current_status in {"candidate", "promote", "promoted", "park", "reject", "needs_human"}:
        created, field = first_payload_datetime(payload, ("created_at",))
        if created is not None:
            return created, field
    if current_status == to_status:
        return first_payload_datetime(payload, ("updated_at", "created_at"))
    return None, UNAVAILABLE


def promotion_proposal_refs(payload: dict[str, Any]) -> list[dict[str, Any]]:
    refs = payload.get("promotion_proposal_refs")
    if not isinstance(refs, list):
        return []
    return [ref for ref in refs if isinstance(ref, dict)]


def first_promotion_ref_datetime(payload: dict[str, Any]) -> tuple[datetime | None, str]:
    matches: list[tuple[datetime, str]] = []
    for index, ref in enumerate(promotion_proposal_refs(payload)):
        parsed = parse_trace_datetime(ref.get("created_at"))
        if parsed is not None:
            matches.append((parsed, f"promotion_proposal_refs[{index}].created_at"))
    if matches:
        return sorted(matches, key=lambda item: item[0])[0]
    return None, UNAVAILABLE


def read_task_trace_records(ops_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    tasks_dir = ops_dir / "tasks"
    if not tasks_dir.exists() or not tasks_dir.is_dir():
        return [], []

    records: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for status_path in sorted(tasks_dir.glob("*/status.json")):
        try:
            payload = json.loads(status_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            warnings.append(issue("warning", "task_status_json_malformed", status_path, str(exc)))
            continue
        except (OSError, UnicodeDecodeError) as exc:
            warnings.append(issue("warning", "task_status_read_failed", status_path, str(exc)))
            continue
        if not isinstance(payload, dict):
            warnings.append(issue("warning", "task_status_not_object", status_path, "task status JSON must be an object"))
            continue
        task_id = str(payload.get("id") or status_path.parent.name).strip()
        records.append(
            {
                "task_id": task_id,
                "task_dir": str(status_path.parent),
                "status_path": str(status_path),
                "status": str(payload.get("status") or UNAVAILABLE),
                "payload": payload,
            }
        )
    return records, warnings


def task_record_matches_idea(task_record: dict[str, Any], idea_id: str, promoted_task_id: str | None) -> bool:
    payload = task_record.get("payload", {})
    if promoted_task_id and task_record.get("task_id") == promoted_task_id:
        return True
    for field in ("origin_idea_id", "catalog_idea_id"):
        if str(payload.get(field) or "").strip() == idea_id:
            return True
    promotion = payload.get("catalog_promotion")
    if isinstance(promotion, dict):
        for field in ("origin_idea_id", "catalog_idea_id"):
            if str(promotion.get(field) or "").strip() == idea_id:
                return True
    return False


def linked_task_records(record: dict[str, Any], task_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    payload = record["payload"]
    idea_id = str(record.get("idea_id") or payload.get("id") or "").strip()
    promoted_task_id = str(payload.get("promoted_task_id") or "").strip() or None
    return [
        task_record
        for task_record in task_records
        if task_record_matches_idea(task_record, idea_id, promoted_task_id)
    ]


def task_created_datetime(task_records: list[dict[str, Any]], payload: dict[str, Any]) -> tuple[datetime | None, str]:
    matches: list[tuple[datetime, str]] = []
    for task_record in task_records:
        task_payload = task_record.get("payload", {})
        parsed, field = first_payload_datetime(task_payload, ("created_at",))
        if parsed is not None:
            matches.append((parsed, f"{task_record['task_id']}.{field}"))
    if matches:
        return sorted(matches, key=lambda item: item[0])[0]
    return first_promotion_ref_datetime(payload)


def markdown_table_rows_with_lines(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    warnings: list[dict[str, Any]] = []
    if not path.exists():
        return [], warnings
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        return [], [issue("warning", "markdown_table_read_failed", path, str(exc))]

    header: list[str] | None = None
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip().startswith("|"):
            continue
        cells = markdown_cells(line)
        if is_separator_row(cells):
            continue
        if header is None:
            header = [cell.lower().strip().replace(" ", "_") for cell in cells]
            continue
        if len(cells) != len(header):
            warnings.append(issue(
                "warning",
                "malformed_markdown_table_row",
                path,
                f"table row has {len(cells)} cells but expected {len(header)}",
                line_number=line_number,
                row=line.strip(),
            ))
            continue
        row = dict(zip(header, cells))
        row["line_number"] = line_number
        rows.append(row)
    return rows, warnings


def task_id_from_text(value: Any) -> str:
    match = TASK_ID_RE.search(str(value or ""))
    return match.group(0) if match else ""


def idea_id_from_text(value: Any) -> str:
    match = IDEA_ID_RE.search(str(value or ""))
    return match.group(0) if match else ""


def read_accepted_output_rows(ops_dir: Path) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    path = ops_dir / "accepted_outputs_index.md"
    rows, warnings = markdown_table_rows_with_lines(path)
    by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        task_id = task_id_from_text(row.get("task_id"))
        if not task_id:
            continue
        by_task[task_id].append(
            {
                "task_id": task_id,
                "accepted_date": row.get("accepted_date"),
                "title": row.get("title"),
                "evidence_link": row.get("evidence_link"),
                "line_number": row.get("line_number"),
                "path": str(path),
            }
        )
    return dict(by_task), warnings


def read_queue_trace_rows(ops_dir: Path) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    path = ops_dir / "queue.md"
    rows, warnings = markdown_table_rows_with_lines(path)
    by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        task_text = row.get("task_id") or row.get("task") or row.get("task_dir_name") or row.get("notes")
        task_id = task_id_from_text(task_text)
        if not task_id:
            continue
        by_task[task_id].append(
            {
                "task_id": task_id,
                "task": row.get("task"),
                "task_dir_name": row.get("task_dir_name"),
                "priority": row.get("priority"),
                "status": row.get("status"),
                "type": row.get("type"),
                "next_runner": row.get("next_runner"),
                "notes": row.get("notes"),
                "origin_idea_id": idea_id_from_text(row.get("notes")),
                "line_number": row.get("line_number"),
                "path": str(path),
            }
        )
    return dict(by_task), warnings


def terminal_datetime(
    task_records: list[dict[str, Any]],
    accepted_rows_by_task: dict[str, list[dict[str, Any]]],
) -> tuple[datetime | None, str, str]:
    matches: list[tuple[datetime, str, str]] = []
    for task_record in task_records:
        task_id = str(task_record.get("task_id") or "")
        status = str(task_record.get("status") or "")
        accepted_rows = accepted_rows_by_task.get(task_id, [])
        if accepted_rows:
            for row in accepted_rows:
                parsed = parse_trace_datetime(row.get("accepted_date"))
                if parsed is not None:
                    matches.append((parsed, f"accepted_outputs_index.md:{row['line_number']}:accepted_date", "accepted"))
        if status in TERMINAL_TASK_STATUSES:
            parsed, field = first_payload_datetime(task_record.get("payload", {}), ("updated_at",))
            if parsed is not None:
                matches.append((parsed, f"{task_id}.{field}", status))
    if not matches:
        return None, UNAVAILABLE, UNAVAILABLE
    return sorted(matches, key=lambda item: item[0])[0]


def duration_item(
    idea_id: str,
    title: str,
    start: datetime | None,
    start_field: str,
    end: datetime | None,
    end_field: str,
    **extra: Any,
) -> dict[str, Any]:
    hours, reason = rounded_hours(start, end)
    item = {
        "idea_id": idea_id,
        "title": title,
        "start_field": start_field,
        "end_field": end_field,
        "start_at": trace_timestamp(start) if start is not None else UNAVAILABLE,
        "end_at": trace_timestamp(end) if end is not None else UNAVAILABLE,
        "duration_hours": hours,
    }
    if reason:
        item["unavailable_reason"] = reason
    item.update({key: value for key, value in extra.items() if value not in (None, "", [])})
    return item


def duration_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    values = [float(item["duration_hours"]) for item in items if isinstance(item.get("duration_hours"), (int, float))]
    return {
        "item_count": len(items),
        "available_count": len(values),
        "unavailable_count": len(items) - len(values),
        "average_hours": round(sum(values) / len(values), 2) if values else UNAVAILABLE,
        "max_hours": round(max(values), 2) if values else UNAVAILABLE,
        "items": items,
    }


def idea_duration_items(
    record: dict[str, Any],
    task_records: list[dict[str, Any]],
    accepted_rows_by_task: dict[str, list[dict[str, Any]]],
    now: datetime,
) -> dict[str, dict[str, Any]]:
    payload = record["payload"]
    summary = candidate_summary(record)
    idea_id = str(summary.get("idea_id") or summary.get("filename_id") or "")
    title = str(summary.get("title") or "")
    captured_at, captured_field = first_payload_datetime(payload, ("captured_at", "created_at"))
    candidate_at, candidate_field = transition_datetime(payload, "candidate")
    promote_at, promote_field = transition_datetime(payload, "promote")
    created_at, created_field = task_created_datetime(task_records, payload)
    terminal_at, terminal_field, terminal_status = terminal_datetime(task_records, accepted_rows_by_task)
    parked_at, parked_field = transition_datetime(payload, "park")

    items = {
        "capture_to_candidate": duration_item(
            idea_id,
            title,
            captured_at,
            captured_field,
            candidate_at,
            candidate_field,
        ),
        "candidate_to_promote": duration_item(
            idea_id,
            title,
            candidate_at,
            candidate_field,
            promote_at,
            promote_field,
        ),
        "promote_to_task_creation": duration_item(
            idea_id,
            title,
            promote_at,
            promote_field,
            created_at,
            created_field,
        ),
        "task_creation_to_terminal_output": duration_item(
            idea_id,
            title,
            created_at,
            created_field,
            terminal_at,
            terminal_field,
            terminal_status=terminal_status,
        ),
    }
    if str(payload.get("status") or "") == "park":
        items["parked_idea_age"] = duration_item(
            idea_id,
            title,
            parked_at,
            parked_field,
            now,
            "now",
        )
    return items


def failed_gate_counter(records: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for record in records:
        for gate in blockers_for_payload(record["payload"]):
            counts[gate] += 1
        human_gate_reason = str(record["payload"].get("human_gate_reason") or "").strip()
        if human_gate_reason:
            counts["human_gate"] += 1
    return dict(sorted(counts.items()))


def amount_from_cost_row(row: dict[str, str]) -> float | None:
    for field in COST_AMOUNT_FIELDS:
        raw = row.get(field)
        if raw is None or str(raw).strip() == "":
            continue
        try:
            return float(str(raw).strip())
        except ValueError:
            return None
    total = 0.0
    found = False
    for field in COST_COMPONENT_FIELDS:
        raw = row.get(field)
        if raw is None or str(raw).strip() == "":
            continue
        try:
            total += float(str(raw).strip())
            found = True
        except ValueError:
            return None
    return total if found else None


def read_cost_ledger_rows(ops_dir: Path) -> tuple[bool, list[dict[str, Any]], list[dict[str, Any]]]:
    path = ops_dir / "cost_ledger.csv"
    if not path.exists():
        return False, [], []
    warnings: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for line_number, raw in enumerate(reader, start=2):
                clean = {str(key): str(value) for key, value in raw.items() if key is not None}
                item_id = clean.get("item_id", "").strip()
                amount = amount_from_cost_row(clean)
                if amount is None and any(str(clean.get(field, "")).strip() for field in (*COST_AMOUNT_FIELDS, *COST_COMPONENT_FIELDS)):
                    warnings.append(issue(
                        "warning",
                        "cost_ledger_amount_unavailable",
                        path,
                        "cost ledger row amount could not be parsed",
                        line_number=line_number,
                        item_id=item_id,
                    ))
                rows.append(
                    {
                        "line_number": line_number,
                        "item_id": item_id,
                        "item_key": Path(item_id).name if item_id else "",
                        "amount_usd": amount if amount is not None else UNAVAILABLE,
                        "amount_available": amount is not None,
                    }
                )
    except (OSError, UnicodeDecodeError) as exc:
        return True, [], [issue("warning", "cost_ledger_read_failed", path, str(exc))]
    return True, rows, warnings


def cost_rows_for_task(rows: list[dict[str, Any]], task_id: str) -> list[dict[str, Any]]:
    return [row for row in rows if row.get("item_id") == task_id or row.get("item_key") == task_id]


def accepted_promoted_task_ids(
    records: list[dict[str, Any]],
    all_task_records: list[dict[str, Any]],
    accepted_rows_by_task: dict[str, list[dict[str, Any]]],
) -> list[str]:
    task_ids: set[str] = set()
    for record in records:
        payload = record["payload"]
        promoted_task_id = str(payload.get("promoted_task_id") or "").strip()
        linked_tasks = linked_task_records(record, all_task_records)
        for task_record in linked_tasks:
            task_id = str(task_record.get("task_id") or "")
            if task_record.get("status") == "accepted" or accepted_rows_by_task.get(task_id):
                task_ids.add(task_id)
        if promoted_task_id and accepted_rows_by_task.get(promoted_task_id):
            task_ids.add(promoted_task_id)
    return sorted(task_ids)


def queue_rows_for_idea(
    record: dict[str, Any],
    task_records: list[dict[str, Any]],
    queue_rows_by_task: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    payload = record["payload"]
    task_ids = {str(task.get("task_id") or "") for task in task_records}
    promoted_task_id = str(payload.get("promoted_task_id") or "").strip()
    if promoted_task_id:
        task_ids.add(promoted_task_id)
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int]] = set()
    for task_id in sorted(task_id for task_id in task_ids if task_id):
        for row in queue_rows_by_task.get(task_id, []):
            key = (task_id, str(row.get("path") or ""), int(row.get("line_number") or 0))
            if key not in seen:
                rows.append(row)
                seen.add(key)
    return rows


def cost_per_accepted_promoted_idea(
    ops_dir: Path,
    accepted_task_ids: list[str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    ledger_available, cost_rows, warnings = read_cost_ledger_rows(ops_dir)
    if not ledger_available:
        return {
            "status": UNAVAILABLE,
            "reason": "cost_ledger_missing",
            "ledger_path": str(ops_dir / "cost_ledger.csv"),
            "accepted_promoted_idea_count": len(accepted_task_ids),
            "cost_per_accepted_promoted_idea_usd": UNAVAILABLE,
            "matched_task_ids": [],
            "unmatched_task_ids": accepted_task_ids,
            "malformed_cost_row_count": UNAVAILABLE,
        }, warnings
    if not accepted_task_ids:
        return {
            "status": UNAVAILABLE,
            "reason": "no_accepted_promoted_ideas",
            "ledger_path": str(ops_dir / "cost_ledger.csv"),
            "accepted_promoted_idea_count": 0,
            "cost_per_accepted_promoted_idea_usd": UNAVAILABLE,
            "matched_task_ids": [],
            "unmatched_task_ids": [],
            "malformed_cost_row_count": 0,
        }, warnings

    matched: set[str] = set()
    unmatched: list[str] = []
    total = 0.0
    malformed = 0
    for task_id in accepted_task_ids:
        rows = cost_rows_for_task(cost_rows, task_id)
        if not rows:
            unmatched.append(task_id)
            continue
        matched.add(task_id)
        for row in rows:
            if row.get("amount_available") is True:
                total += float(row["amount_usd"])
            else:
                malformed += 1
    complete = not unmatched and malformed == 0
    return {
        "status": "available" if complete else UNAVAILABLE,
        "reason": None if complete else "incomplete_cost_coverage",
        "ledger_path": str(ops_dir / "cost_ledger.csv"),
        "accepted_promoted_idea_count": len(accepted_task_ids),
        "accepted_promoted_task_ids": accepted_task_ids,
        "matched_task_ids": sorted(matched),
        "unmatched_task_ids": unmatched,
        "malformed_cost_row_count": malformed,
        "known_cost_usd": round(total, 4),
        "cost_per_accepted_promoted_idea_usd": round(total / len(accepted_task_ids), 4) if complete else UNAVAILABLE,
    }, warnings


def linked_task_summary(
    task_record: dict[str, Any],
    accepted_rows_by_task: dict[str, list[dict[str, Any]]],
    queue_rows_by_task: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    payload = task_record.get("payload", {})
    task_id = str(task_record.get("task_id") or "")
    return {
        "task_id": task_id,
        "status": task_record.get("status", UNAVAILABLE),
        "type": dashboard_available(payload.get("type")),
        "title": dashboard_available(payload.get("title")),
        "task_dir": task_record.get("task_dir"),
        "status_path": task_record.get("status_path"),
        "created_at": dashboard_available(payload.get("created_at")),
        "updated_at": dashboard_available(payload.get("updated_at")),
        "origin_idea_id": dashboard_available(payload.get("origin_idea_id") or payload.get("catalog_idea_id")),
        "promotion_route": dashboard_available(payload.get("promotion_route")),
        "routing_reason": dashboard_available(payload.get("routing_reason")),
        "promotion_preflight_hash": dashboard_available(payload.get("promotion_preflight_hash")),
        "promotion_transaction_id": dashboard_available(payload.get("promotion_transaction_id")),
        "queue_rows": queue_rows_by_task.get(task_id, []),
        "accepted_outputs": accepted_rows_by_task.get(task_id, []),
    }


def idea_trace_timeline(
    payload: dict[str, Any],
    linked_tasks: list[dict[str, Any]],
    accepted_rows_by_task: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for event, fields in (
        ("captured", ("captured_at", "created_at")),
        ("candidate", ()),
        ("promote", ()),
        ("park", ()),
        ("reject", ()),
        ("promoted", ()),
    ):
        if event == "captured":
            at, source = first_payload_datetime(payload, fields)
        else:
            at, source = transition_datetime(payload, event)
        if at is not None:
            events.append({"event": event, "at": trace_timestamp(at), "source": source})

    for task_record in linked_tasks:
        task_payload = task_record.get("payload", {})
        task_id = str(task_record.get("task_id") or "")
        created, created_field = first_payload_datetime(task_payload, ("created_at",))
        if created is not None:
            events.append({"event": "task_created", "at": trace_timestamp(created), "source": f"{task_id}.{created_field}", "task_id": task_id})
        if task_record.get("status") in TERMINAL_TASK_STATUSES:
            updated, updated_field = first_payload_datetime(task_payload, ("updated_at",))
            if updated is not None:
                events.append(
                    {
                        "event": f"task_{task_record['status']}",
                        "at": trace_timestamp(updated),
                        "source": f"{task_id}.{updated_field}",
                        "task_id": task_id,
                    }
                )
        for row in accepted_rows_by_task.get(task_id, []):
            accepted_at = parse_trace_datetime(row.get("accepted_date"))
            if accepted_at is not None:
                events.append(
                    {
                        "event": "accepted_output_indexed",
                        "at": trace_timestamp(accepted_at),
                        "source": f"accepted_outputs_index.md:{row['line_number']}:accepted_date",
                        "task_id": task_id,
                    }
                )
    return sorted(events, key=lambda item: (item["at"], item["event"], item.get("task_id", "")))


def idea_traceability_summary(
    records: list[dict[str, Any]],
    task_records: list[dict[str, Any]],
    accepted_rows_by_task: dict[str, list[dict[str, Any]]],
    queue_rows_by_task: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    linked_ideas = 0
    accepted_promoted_ideas = 0
    rejected_promoted_ideas = 0
    linked_task_count = 0
    queue_link_count = 0
    for record in records:
        tasks = linked_task_records(record, task_records)
        linked_task_count += len(tasks)
        if queue_rows_by_task is not None:
            queue_link_count += len(queue_rows_for_idea(record, tasks, queue_rows_by_task))
        if tasks or str(record["payload"].get("promoted_task_id") or "").strip():
            linked_ideas += 1
        if any(task.get("status") == "accepted" or accepted_rows_by_task.get(str(task.get("task_id") or "")) for task in tasks):
            accepted_promoted_ideas += 1
        if any(task.get("status") == "rejected" for task in tasks):
            rejected_promoted_ideas += 1
    return {
        "linked_idea_count": linked_ideas,
        "linked_task_count": linked_task_count,
        "queue_link_count": queue_link_count,
        "accepted_promoted_idea_count": accepted_promoted_ideas,
        "rejected_promoted_idea_count": rejected_promoted_ideas,
    }


def idea_metrics_read_model(ops_dir: Path, now: datetime) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    model = read_catalog(ops_dir)
    validation = catalog_validation_report_from_model(ops_dir, model)
    task_records, task_warnings = read_task_trace_records(ops_dir)
    accepted_rows_by_task, accepted_warnings = read_accepted_output_rows(ops_dir)
    queue_rows_by_task, queue_warnings = read_queue_trace_rows(ops_dir)
    records = model["candidates"]
    warnings = [*validation["warnings"], *task_warnings, *accepted_warnings, *queue_warnings]

    metric_items: dict[str, list[dict[str, Any]]] = {
        "capture_to_candidate": [],
        "candidate_to_promote": [],
        "promote_to_task_creation": [],
        "task_creation_to_terminal_output": [],
        "parked_idea_age": [],
    }
    for record in records:
        tasks = linked_task_records(record, task_records)
        durations = idea_duration_items(record, tasks, accepted_rows_by_task, now)
        for key, item in durations.items():
            metric_items.setdefault(key, []).append(item)

    duplicate_count = sum(
        1
        for record in records
        if str(record["payload"].get("duplicate_status") or "new") in {"duplicate", "near_duplicate"}
    )
    accepted_task_ids = accepted_promoted_task_ids(records, task_records, accepted_rows_by_task)
    cost, cost_warnings = cost_per_accepted_promoted_idea(ops_dir, accepted_task_ids)
    warnings.extend(cost_warnings)

    candidate_count = len(records)
    return {
        "catalog_validation": {
            "ok": validation["ok"],
            "validation_exit_code": catalog_validation_exit_code(validation),
            "warning_count": len(validation["warnings"]),
            "failure_count": len(validation["failures"]),
        },
        "idea_count": candidate_count,
        "status_counts": complete_status_counts(validation["status_counts"]),
        "traceability": idea_traceability_summary(records, task_records, accepted_rows_by_task, queue_rows_by_task),
        "lifecycle_durations": {
            key: duration_summary(items)
            for key, items in metric_items.items()
        },
        "duplicate_rate": {
            "status": "available" if candidate_count else UNAVAILABLE,
            "duplicate_or_near_duplicate_count": duplicate_count,
            "idea_count": candidate_count,
            "rate": round(duplicate_count / candidate_count, 4) if candidate_count else UNAVAILABLE,
        },
        "blocker_frequency": {
            "status": "available" if candidate_count else UNAVAILABLE,
            "idea_count": candidate_count,
            "blockers": failed_gate_counter(records),
        },
        "cost_per_accepted_promoted_idea": cost,
        "warnings": warnings,
        "failures": validation["failures"],
    }, warnings


def idea_metrics_report(ops_dir: Path, now: datetime) -> dict[str, Any]:
    read_model, warnings = idea_metrics_read_model(ops_dir, now)
    failures = read_model["failures"]
    exit_code = catalog_validation_exit_code({"failures": failures})
    return {
        "ok": not failures,
        "action": "idea_metrics_reported",
        "schema_version": "idea_lifecycle_metrics_v1.0",
        "generated_at": trace_timestamp(now),
        "ops_dir": str(ops_dir),
        "read_only": True,
        "changed": False,
        "read_model": read_model,
        "warnings": warnings,
        "failures": failures,
        "validation_exit_code": exit_code,
    }


def idea_trace_report(ops_dir: Path, idea_id: str, now: datetime) -> dict[str, Any]:
    model = read_catalog(ops_dir)
    validation = catalog_validation_report_from_model(ops_dir, model)
    if model["failures"]:
        return {
            "ok": False,
            "action": "idea_trace_failed",
            "reason": "catalog_read_failed",
            "ops_dir": str(ops_dir),
            "idea_id": idea_id,
            "read_only": True,
            "changed": False,
            "warnings": model["warnings"],
            "failures": model["failures"],
            "validation_exit_code": catalog_validation_exit_code(validation),
        }
    matches = [record for record in model["candidates"] if record["idea_id"] == idea_id]
    if not matches:
        return {
            "ok": False,
            "action": "idea_trace_failed",
            "reason": "idea_not_found",
            "ops_dir": str(ops_dir),
            "idea_id": idea_id,
            "read_only": True,
            "changed": False,
            "warnings": validation["warnings"],
            "failures": [],
            "validation_exit_code": 3,
            "next_step": "run async-research idea catalog list to inspect available ideas",
        }
    if len(matches) > 1:
        failure = issue(
            "failure",
            "duplicate_idea_id",
            Path(matches[0]["path"]),
            f"idea id {idea_id} appears in multiple canonical JSON files",
            category="malformed",
            idea_id=idea_id,
            paths=[record["path"] for record in matches],
        )
        return {
            "ok": False,
            "action": "idea_trace_failed",
            "reason": "duplicate_idea_id",
            "ops_dir": str(ops_dir),
            "idea_id": idea_id,
            "read_only": True,
            "changed": False,
            "warnings": validation["warnings"],
            "failures": [failure],
            "validation_exit_code": 4,
        }

    task_records, task_warnings = read_task_trace_records(ops_dir)
    accepted_rows_by_task, accepted_warnings = read_accepted_output_rows(ops_dir)
    queue_rows_by_task, queue_warnings = read_queue_trace_rows(ops_dir)
    record = matches[0]
    linked_tasks = linked_task_records(record, task_records)
    durations = idea_duration_items(record, linked_tasks, accepted_rows_by_task, now)
    return {
        "ok": not validation["failures"],
        "action": "idea_trace_reported",
        "schema_version": "idea_trace_v1.0",
        "generated_at": trace_timestamp(now),
        "ops_dir": str(ops_dir),
        "idea_id": idea_id,
        "read_only": True,
        "changed": False,
        "summary": candidate_summary(record),
        "candidate": record["payload"],
        "timeline": idea_trace_timeline(record["payload"], linked_tasks, accepted_rows_by_task),
        "linked_tasks": [linked_task_summary(task, accepted_rows_by_task, queue_rows_by_task) for task in linked_tasks],
        "queue_rows": queue_rows_for_idea(record, linked_tasks, queue_rows_by_task),
        "durations": durations,
        "warnings": [*validation["warnings"], *task_warnings, *accepted_warnings, *queue_warnings],
        "failures": validation["failures"],
        "validation_exit_code": catalog_validation_exit_code(validation),
    }


def catalog_dashboard_report(ops_dir: Path, max_blockers: int = 10) -> dict[str, Any]:
    """Return a read-only portfolio dashboard derived from the catalog read model."""
    model = read_catalog(ops_dir)
    validation = catalog_validation_report_from_model(ops_dir, model)
    validation_exit_code = catalog_validation_exit_code(validation)
    records = model["candidates"]
    task_records, task_warnings = read_task_trace_records(ops_dir)
    accepted_rows_by_task, accepted_warnings = read_accepted_output_rows(ops_dir)
    queue_rows_by_task, queue_warnings = read_queue_trace_rows(ops_dir)
    traceability = idea_traceability_summary(records, task_records, accepted_rows_by_task, queue_rows_by_task)
    issues = validation["failures"] + validation["warnings"]
    issues_by_candidate = dashboard_issues_by_candidate(issues)
    sorted_records = sorted(records, key=lambda item: str(item.get("idea_id") or item.get("filename_id") or ""))
    active_records = [record for record in records if record["status"] in ACTIVE_DASHBOARD_STATUSES]
    top_blockers = [
        dashboard_issue_summary(item)
        for item in sorted(issues, key=dashboard_issue_sort_key)[:max(0, max_blockers)]
    ]

    return {
        "ok": validation["ok"],
        "action": "idea_catalog_dashboard_rendered",
        "ops_dir": model["ops_dir"],
        "ideas_dir": model["ideas_dir"],
        "catalog_path": model["catalog_projection"]["path"],
        "prioritization_path": model["prioritization_projection"]["path"],
        "read_only": True,
        "changed": False,
        "generated_from": "catalog_read_model_and_validator",
        "validation_exit_code": validation_exit_code,
        "summary": {
            "candidate_count": validation["candidate_count"],
            "status_counts": complete_status_counts(validation["status_counts"]),
            "derived_label_counts": complete_pipeline_counts(validation["derived_label_counts"]),
            "active_candidate_count": len(active_records),
            "parked_count": int(validation["status_counts"].get("park", 0)),
            "promoted_count": int(validation["status_counts"].get("promoted", 0)),
            "rejected_count": int(validation["status_counts"].get("reject", 0)),
            "total_issue_count": len(issues),
            "displayed_blocker_count": len(top_blockers),
            "score_dimension_count": len(records),
            "next_recommended_task_count": len(dashboard_next_tasks(records, issues_by_candidate)),
            "idea_to_task_link_count": len(dashboard_idea_task_links(records, issues_by_candidate)),
            "traceability": traceability,
            "warning_count": len(validation["warnings"]),
            "failure_count": len(validation["failures"]),
        },
        "sections": {
            "candidate_ideas": [
                dashboard_idea_summary(record, issues_by_candidate)
                for record in sorted(active_records, key=promotion_sort_key)
            ],
            "parked_ideas": [
                dashboard_idea_summary(record, issues_by_candidate)
                for record in sorted_records
                if record["status"] == "park"
            ],
            "promoted_ideas": [
                dashboard_idea_summary(record, issues_by_candidate)
                for record in sorted_records
                if record["status"] == "promoted"
            ],
            "rejected_ideas": [
                dashboard_idea_summary(record, issues_by_candidate)
                for record in sorted_records
                if record["status"] == "reject"
            ],
            "top_blockers": top_blockers,
            "score_dimensions": [
                dashboard_score_summary(record)
                for record in sorted_records
            ],
            "next_recommended_tasks": dashboard_next_tasks(records, issues_by_candidate),
            "idea_to_task_links": dashboard_idea_task_links(records, issues_by_candidate),
        },
        "warnings": [*validation["warnings"], *task_warnings, *accepted_warnings, *queue_warnings],
        "failures": validation["failures"],
    }


def catalog_list_report(ops_dir: Path, status: str | None = None) -> dict[str, Any]:
    model = read_catalog(ops_dir)
    if model["failures"]:
        return {
            "ok": False,
            "action": "idea_catalog_list_failed",
            "ops_dir": model["ops_dir"],
            "warnings": model["warnings"],
            "failures": model["failures"],
            "ideas": [],
        }
    records = model["candidates"]
    if status:
        records = [record for record in records if record["status"] == status]
    ideas = [candidate_summary(record) for record in records]
    return {
        "ok": True,
        "action": "idea_catalog_listed",
        "ops_dir": model["ops_dir"],
        "ideas_dir": model["ideas_dir"],
        "status": status,
        "candidate_count": len(ideas),
        "status_counts": model["status_counts"],
        "derived_label_counts": model["derived_label_counts"],
        "warnings": model["warnings"],
        "failures": [],
        "ideas": ideas,
    }


def catalog_show_report(ops_dir: Path, idea_id: str) -> dict[str, Any]:
    model = read_catalog(ops_dir)
    if model["failures"]:
        return {
            "ok": False,
            "action": "idea_catalog_show_failed",
            "reason": "catalog_read_failed",
            "ops_dir": model["ops_dir"],
            "idea_id": idea_id,
            "warnings": model["warnings"],
            "failures": model["failures"],
        }

    matches = [record for record in model["candidates"] if record["idea_id"] == idea_id]
    if not matches:
        return {
            "ok": False,
            "action": "idea_catalog_show_failed",
            "reason": "idea_not_found",
            "ops_dir": model["ops_dir"],
            "idea_id": idea_id,
            "warnings": model["warnings"],
            "failures": [],
            "next_step": "run async-research idea catalog list to inspect available ideas",
        }
    if len(matches) > 1:
        return {
            "ok": False,
            "action": "idea_catalog_show_failed",
            "reason": "duplicate_idea_id",
            "ops_dir": model["ops_dir"],
            "idea_id": idea_id,
            "warnings": model["warnings"],
            "failures": [
                issue(
                    "failure",
                    "duplicate_idea_id",
                    Path(matches[0]["path"]),
                    f"idea id {idea_id} appears in multiple canonical JSON files",
                    category="malformed",
                    idea_id=idea_id,
                    paths=[record["path"] for record in matches],
                )
            ],
        }

    record = matches[0]
    record_warnings, record_failures = validate_candidate_record(record, ops_dir)
    return {
        "ok": True,
        "action": "idea_catalog_shown",
        "ops_dir": model["ops_dir"],
        "idea_id": idea_id,
        "summary": candidate_summary(record),
        "candidate": record["payload"],
        "warnings": model["warnings"],
        "failures": [],
        "validation": {
            "ok": not record_failures,
            "warnings": record_warnings,
            "failures": record_failures,
        },
    }


def read_catalog(ops_dir: Path) -> dict[str, Any]:
    ideas_dir = ops_dir / IDEAS_DIR
    warnings: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []

    catalog_projection = {
        "path": str(ideas_dir / CATALOG_FILE),
        "exists": False,
        "block": {
            "name": CATALOG_BLOCK,
            "present": False,
            "table": {"headers": [], "rows": [], "row_count": 0},
        },
        "row_ids": [],
    }
    prioritization_projection = {
        "path": str(ideas_dir / PRIORITIZATION_FILE),
        "exists": False,
        "blocks": {},
    }
    projection_staleness = {
        "json_ids": [],
        "catalog_row_ids": [],
        "duplicate_projection_rows": [],
        "orphaned_projection_rows": [],
        "orphaned_json_records": [],
    }
    duplicate_ids: dict[str, list[str]] = {}

    if not ops_dir.exists():
        failures.append(issue("failure", "ops_dir_missing", ops_dir, "research_ops directory is missing"))
    elif not ops_dir.is_dir():
        failures.append(issue("failure", "ops_dir_not_directory", ops_dir, "research_ops path is not a directory"))
    elif not ideas_dir.exists():
        warnings.append(issue("warning", "catalog_cold_start", ideas_dir, "research_ops/ideas is missing; run idea catalog init to bootstrap it"))
    elif not ideas_dir.is_dir():
        failures.append(issue("failure", "ideas_path_not_directory", ideas_dir, "research_ops/ideas must be a directory"))
    else:
        lock_warning = catalog_lock_warning(ideas_dir / "LOCK")
        if lock_warning is not None:
            warnings.append(lock_warning)

        records, record_warnings, record_failures = read_candidate_records(ideas_dir)
        warnings.extend(record_warnings)
        failures.extend(record_failures)

        catalog_projection, catalog_warnings = parse_catalog_projection(ideas_dir / CATALOG_FILE)
        prioritization_projection, prioritization_warnings = parse_prioritization_projection(ideas_dir / PRIORITIZATION_FILE)
        warnings.extend(catalog_warnings)
        warnings.extend(prioritization_warnings)

        duplicate_warnings, duplicate_ids = duplicate_id_warnings(records)
        stale_warnings, projection_staleness = projection_staleness_warnings(records, catalog_projection)
        warnings.extend(duplicate_warnings)
        warnings.extend(stale_warnings)

    return {
        "ok": not failures,
        "ops_dir": str(ops_dir),
        "ideas_dir": str(ideas_dir),
        "candidate_count": len(records),
        "candidates": records,
        "status_counts": status_counts(records),
        "derived_label_counts": derived_label_counts(records),
        "duplicate_idea_ids": duplicate_ids,
        "projection_staleness": projection_staleness,
        "catalog_projection": catalog_projection,
        "prioritization_projection": prioritization_projection,
        "warnings": warnings,
        "failures": failures,
    }
