"""Read-only idea catalog parsing and projection helpers."""

from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
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
    "scored_idea_missing_mission_policy_version",
}

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
        library_index = ops_dir / "knowledge" / "knowledge_index.md"
        for ref in [str(item).strip() for item in library_refs if str(item).strip()]:
            if not text_contains(library_index, ref):
                warnings.append(candidate_issue(
                    "warning",
                    "library_ref_unresolved",
                    record,
                    f"library_refs reference {ref} could not be resolved because the knowledge library is optional in this phase",
                    ref_field="library_refs",
                    ref=ref,
                    target=str(library_index),
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
