"""Read-only idea catalog parsing and projection helpers."""

from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
from typing import Any


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
