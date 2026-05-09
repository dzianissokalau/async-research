#!/usr/bin/env python3
"""Initialize knowledge library workspace files."""

from __future__ import annotations

import argparse
from datetime import datetime
from datetime import timezone
import json
from pathlib import Path
import re
import sys
import tempfile
from typing import Any


SUCCESS = 0
VALIDATION_FINDINGS = 2
INVALID_REQUEST = 3
MALFORMED = 4
SURFACE_STALE_DAYS = 180

LIBRARY_DIR = "library"
SOURCE_LIBRARY_FILE = "source_library.md"
KNOWLEDGE_INDEX_FILE = "knowledge_index.md"
CLAIM_MAP_FILE = "claim_map.md"
METHOD_INDEX_FILE = "method_index.md"
OPEN_QUESTIONS_FILE = "open_questions.md"
UPDATE_LOG_FILE = "library_update_log.md"

SOURCE_LIBRARY_TEMPLATE = """# Source Library

<!-- LIBRARY-SOURCES: schema_version=1.0 -->
| source_id | status | trust_tier | type | title | author_or_publisher | location | reviewed_date | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
<!-- /LIBRARY-SOURCES -->

## Notes

Free-form notes. Tooling must not edit this section. Empty library state
is valid during cold start.
"""

KNOWLEDGE_INDEX_TEMPLATE = """# Knowledge Index

<!-- LIBRARY-KNOWLEDGE: schema_version=1.0 -->
| topic | summary | source_refs | confidence | caveats | updated_at |
| --- | --- | --- | --- | --- | --- |
<!-- /LIBRARY-KNOWLEDGE -->

## Notes

Free-form notes. Tooling must not edit this section. Empty library state
is valid during cold start.
"""

CLAIM_MAP_TEMPLATE = """# Claim Map

<!-- LIBRARY-CLAIMS: schema_version=1.0 -->
| claim | source_refs | claim_strength | disputed_status | caveats | reviewed_date |
| --- | --- | --- | --- | --- | --- |
<!-- /LIBRARY-CLAIMS -->

## Notes

Free-form notes. Tooling must not edit this section. Empty library state
is valid during cold start.
"""

METHOD_INDEX_TEMPLATE = """# Method Index

<!-- LIBRARY-METHODS: schema_version=1.0 -->
| method | use_case | assumptions | source_refs | risks | reviewed_date |
| --- | --- | --- | --- | --- | --- |
<!-- /LIBRARY-METHODS -->

## Notes

Free-form notes. Tooling must not edit this section. Empty library state
is valid during cold start.
"""

OPEN_QUESTIONS_TEMPLATE = """# Open Questions

<!-- LIBRARY-OPEN-QUESTIONS: schema_version=1.0 -->
| question_id | question | why_it_matters | source_refs | next_task | status |
| --- | --- | --- | --- | --- | --- |
<!-- /LIBRARY-OPEN-QUESTIONS -->

## Notes

Free-form notes. Tooling must not edit this section. Empty library state
is valid during cold start.
"""

UPDATE_LOG_TEMPLATE = """# Library Update Log

<!-- LIBRARY-UPDATE-LOG: schema_version=1.0 -->
| date | task_id | files_updated | reviewer_or_approver | notes |
| --- | --- | --- | --- | --- |
<!-- /LIBRARY-UPDATE-LOG -->

## Notes

Free-form notes. Tooling must not edit this section. Empty library state
is valid during cold start.
"""

STARTER_FILES = (
    (Path(LIBRARY_DIR) / SOURCE_LIBRARY_FILE, SOURCE_LIBRARY_TEMPLATE),
    (Path(LIBRARY_DIR) / KNOWLEDGE_INDEX_FILE, KNOWLEDGE_INDEX_TEMPLATE),
    (Path(LIBRARY_DIR) / CLAIM_MAP_FILE, CLAIM_MAP_TEMPLATE),
    (Path(LIBRARY_DIR) / METHOD_INDEX_FILE, METHOD_INDEX_TEMPLATE),
    (Path(LIBRARY_DIR) / OPEN_QUESTIONS_FILE, OPEN_QUESTIONS_TEMPLATE),
    (Path(LIBRARY_DIR) / UPDATE_LOG_FILE, UPDATE_LOG_TEMPLATE),
)
LIT_ID_RE = re.compile(r"^LIT-[0-9]{4}$")
DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
TASK_ID_RE = re.compile(r"^TASK-[0-9]{4}$")
SOURCE_STATUSES = {"candidate", "trusted", "context_only", "disputed", "deprecated"}
TRUST_TIERS = {"primary", "supporting", "background", "weak", "unknown"}
CLAIM_STRENGTHS = {"none", "weak", "suggestive", "moderate", "strong"}
NO_VALUE_MARKERS = {"", "none", "n/a", "na", "unknown", "todo", "tbd", "yyyy-mm-dd"}
TABLE_SPECS = {
    Path(LIBRARY_DIR) / SOURCE_LIBRARY_FILE: {
        "start": "<!-- LIBRARY-SOURCES: schema_version=1.0 -->",
        "end": "<!-- /LIBRARY-SOURCES -->",
        "headers": ["source_id", "status", "trust_tier", "type", "title", "author_or_publisher", "location", "reviewed_date", "notes"],
    },
    Path(LIBRARY_DIR) / KNOWLEDGE_INDEX_FILE: {
        "start": "<!-- LIBRARY-KNOWLEDGE: schema_version=1.0 -->",
        "end": "<!-- /LIBRARY-KNOWLEDGE -->",
        "headers": ["topic", "summary", "source_refs", "confidence", "caveats", "updated_at"],
    },
    Path(LIBRARY_DIR) / CLAIM_MAP_FILE: {
        "start": "<!-- LIBRARY-CLAIMS: schema_version=1.0 -->",
        "end": "<!-- /LIBRARY-CLAIMS -->",
        "headers": ["claim", "source_refs", "claim_strength", "disputed_status", "caveats", "reviewed_date"],
    },
    Path(LIBRARY_DIR) / METHOD_INDEX_FILE: {
        "start": "<!-- LIBRARY-METHODS: schema_version=1.0 -->",
        "end": "<!-- /LIBRARY-METHODS -->",
        "headers": ["method", "use_case", "assumptions", "source_refs", "risks", "reviewed_date"],
    },
    Path(LIBRARY_DIR) / OPEN_QUESTIONS_FILE: {
        "start": "<!-- LIBRARY-OPEN-QUESTIONS: schema_version=1.0 -->",
        "end": "<!-- /LIBRARY-OPEN-QUESTIONS -->",
        "headers": ["question_id", "question", "why_it_matters", "source_refs", "next_task", "status"],
    },
    Path(LIBRARY_DIR) / UPDATE_LOG_FILE: {
        "start": "<!-- LIBRARY-UPDATE-LOG: schema_version=1.0 -->",
        "end": "<!-- /LIBRARY-UPDATE-LOG -->",
        "headers": ["date", "task_id", "files_updated", "reviewer_or_approver", "notes"],
    },
}


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def field_has_value(value: Any) -> bool:
    return str(value or "").strip().lower() not in NO_VALUE_MARKERS


def field_has_text(value: Any) -> bool:
    return bool(str(value or "").strip())


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


def issue(severity: str, reason: str, path: Path, message: str, **details: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "severity": severity,
        "reason": reason,
        "path": str(path),
        "message": message,
    }
    payload.update(details)
    return payload


def parse_now(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    text = value.strip()
    try:
        if len(text) == 10:
            return datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError as exc:
        raise ValueError("--now must use YYYY-MM-DD or ISO-8601 datetime") from exc


def split_table_row(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return []
    return [cell.strip() for cell in stripped.strip("|").split("|")]


def separator_cells(cells: list[str]) -> bool:
    return bool(cells) and all(cell and set(cell) <= {"-", ":", " "} for cell in cells)


def date_value(value: Any) -> datetime | None:
    text = normalize_text(value)
    if not DATE_RE.fullmatch(text):
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def parse_source_refs(value: Any, path: Path, line: int, field: str) -> tuple[list[str], list[dict[str, Any]]]:
    text = normalize_text(value)
    if not field_has_value(text):
        return [], []
    refs: list[str] = []
    errors: list[dict[str, Any]] = []
    for token in re.split(r"[\s,;]+", text):
        token = token.strip()
        if not token:
            continue
        if LIT_ID_RE.fullmatch(token):
            refs.append(token)
            continue
        errors.append(
            issue(
                "error",
                "invalid_library_source_ref",
                path,
                f"{field} contains invalid library source ref {token}",
                line=line,
                ref=token,
                field=field,
            )
        )
    return refs, errors


def parse_generated_table(path: Path, relative: Path, spec: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return [], []
    except OSError as exc:
        return [], [issue("error", "library_file_read_failed", path, f"cannot read {relative}: {exc}")]

    lines = text.splitlines()
    start_marker = str(spec["start"])
    end_marker = str(spec["end"])
    start_lines = [idx for idx, line in enumerate(lines) if line.strip() == start_marker]
    end_lines = [idx for idx, line in enumerate(lines) if line.strip() == end_marker]
    if len(start_lines) != 1 or len(end_lines) != 1:
        return [], [
            issue(
                "error",
                "malformed_library_generated_block",
                path,
                f"{relative} must contain exactly one generated block",
                start_marker=start_marker,
                end_marker=end_marker,
            )
        ]
    start = start_lines[0]
    end = end_lines[0]
    if end <= start:
        return [], [
            issue(
                "error",
                "malformed_library_generated_block",
                path,
                f"{relative} generated block end marker must follow start marker",
                start_line=start + 1,
                end_line=end + 1,
            )
        ]

    block_lines = [
        (line_number, line)
        for line_number, line in enumerate(lines[start + 1:end], start=start + 2)
        if line.strip()
    ]
    if len(block_lines) < 2:
        return [], [
            issue(
                "error",
                "malformed_library_generated_block",
                path,
                f"{relative} generated block must include a header and separator row",
                line=start + 1,
            )
        ]

    expected_headers = list(spec["headers"])
    header_line, header_text = block_lines[0]
    header = [cell.lower() for cell in split_table_row(header_text)]
    errors: list[dict[str, Any]] = []
    if header != expected_headers:
        errors.append(
            issue(
                "error",
                "invalid_library_table_header",
                path,
                f"{relative} header does not match the library contract",
                line=header_line,
                expected=expected_headers,
                actual=header,
            )
        )
        return [], errors

    separator_line, separator_text = block_lines[1]
    separator = split_table_row(separator_text)
    if len(separator) != len(expected_headers) or not separator_cells(separator):
        errors.append(
            issue(
                "error",
                "invalid_library_table_separator",
                path,
                f"{relative} separator row is malformed",
                line=separator_line,
            )
        )
        return [], errors

    rows: list[dict[str, Any]] = []
    for line_number, row_text in block_lines[2:]:
        cells = split_table_row(row_text)
        if not cells:
            errors.append(
                issue(
                    "error",
                    "malformed_library_table_row",
                    path,
                    f"generated block row is not a Markdown table row",
                    line=line_number,
                )
            )
            continue
        if len(cells) != len(expected_headers):
            errors.append(
                issue(
                    "error",
                    "malformed_library_table_row",
                    path,
                    f"markdown table row has {len(cells)} cells but header has {len(expected_headers)}",
                    line=line_number,
                )
            )
            continue
        row = dict(zip(expected_headers, cells))
        row["_line"] = line_number
        row["_path"] = str(path)
        rows.append(row)
    return rows, errors


def atomic_write_text(path: Path, text: str) -> bool:
    existing = path.read_text(encoding="utf-8") if path.exists() else None
    if existing == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(text)
        temp_path = Path(handle.name)
    temp_path.replace(path)
    return True


def init_plan(ops_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    failures: list[dict[str, Any]] = []
    if not ops_dir.exists():
        failures.append(
            {
                "reason": "ops_dir_missing",
                "path": str(ops_dir),
                "message": "research_ops directory does not exist",
            }
        )
        return [], [], failures
    if not ops_dir.is_dir():
        failures.append(
            {
                "reason": "ops_dir_not_directory",
                "path": str(ops_dir),
                "message": "research_ops path must be a directory",
            }
        )
        return [], [], failures

    library_dir = ops_dir / LIBRARY_DIR
    if library_dir.exists() and not library_dir.is_dir():
        failures.append(
            {
                "reason": "library_path_not_directory",
                "path": str(library_dir),
                "message": "research_ops/library must be a directory",
            }
        )
        return [], [], failures

    missing: list[dict[str, Any]] = []
    existing: list[dict[str, Any]] = []
    for relative, template in STARTER_FILES:
        path = ops_dir / relative
        item = {
            "relative_path": str(relative),
            "path": str(path),
            "bytes": len(template.encode("utf-8")),
        }
        if path.exists() and not path.is_file():
            failures.append(
                {
                    "reason": "library_file_path_not_file",
                    "path": str(path),
                    "message": "library starter path must be a file",
                }
            )
            continue
        if path.exists():
            existing.append(item)
        else:
            missing.append(item)
    return missing, existing, failures


def source_library_warnings_and_errors(rows: list[dict[str, Any]], path: Path, now: datetime, stale_days: int | None) -> tuple[set[str], list[dict[str, Any]], list[dict[str, Any]]]:
    source_ids: set[str] = set()
    seen: dict[str, int] = {}
    warnings: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for row in rows:
        line = int(row.get("_line") or 0)
        source_id = normalize_text(row.get("source_id"))
        if not source_id:
            errors.append(issue("error", "library_source_id_missing", path, "source_library row is missing source_id", line=line))
            continue
        if not LIT_ID_RE.fullmatch(source_id):
            errors.append(
                issue(
                    "error",
                    "invalid_library_source_id",
                    path,
                    "source_library source_id must use LIT-0000 format",
                    line=line,
                    source_id=source_id,
                )
            )
            continue
        if source_id in seen:
            errors.append(
                issue(
                    "error",
                    "duplicate_library_source_id",
                    path,
                    "source_library contains duplicate LIT-* source IDs",
                    line=line,
                    source_id=source_id,
                    first_line=seen[source_id],
                )
            )
        else:
            seen[source_id] = line
            source_ids.add(source_id)

        status = normalize_text(row.get("status")).lower()
        if not field_has_text(status):
            warnings.append(issue("warning", "library_source_status_missing", path, "source row should declare a status", line=line, source_id=source_id))
        elif status not in SOURCE_STATUSES:
            errors.append(issue("error", "invalid_library_source_status", path, "source status is not in the V1 library status vocabulary", line=line, source_id=source_id, status=status))

        trust_tier = normalize_text(row.get("trust_tier")).lower()
        if not field_has_text(trust_tier):
            warnings.append(issue("warning", "library_source_trust_tier_missing", path, "source row should declare a trust tier", line=line, source_id=source_id))
        elif trust_tier not in TRUST_TIERS:
            errors.append(issue("error", "invalid_library_trust_tier", path, "source trust_tier is not in the V1 library trust-tier vocabulary", line=line, source_id=source_id, trust_tier=trust_tier))

        if not field_has_value(row.get("location")):
            warnings.append(issue("warning", "library_source_location_missing", path, "source row should include a source location or path", line=line, source_id=source_id))
        if not field_has_value(row.get("author_or_publisher")):
            warnings.append(issue("warning", "library_source_provenance_missing", path, "source row should include author or publisher provenance", line=line, source_id=source_id))

        if status in {"context_only", "disputed", "deprecated"} and not field_has_value(row.get("notes")):
            warnings.append(issue("warning", "library_source_status_without_notes", path, "context-only, disputed, and deprecated sources should explain the caveat in notes", line=line, source_id=source_id, status=status))

        reviewed_date = normalize_text(row.get("reviewed_date"))
        if field_has_value(reviewed_date):
            reviewed = date_value(reviewed_date)
            if reviewed is None:
                warnings.append(issue("warning", "library_reviewed_date_invalid", path, "reviewed_date should use YYYY-MM-DD", line=line, source_id=source_id, reviewed_date=reviewed_date))
            elif stale_days is not None and (now - reviewed).days > stale_days:
                warnings.append(issue("warning", "library_source_review_stale", path, "source review is older than configured stale-days", line=line, source_id=source_id, reviewed_date=reviewed_date, stale_days=stale_days))
    return source_ids, warnings, errors


def reference_errors(rows: list[dict[str, Any]], path: Path, field: str, source_ids: set[str]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for row in rows:
        line = int(row.get("_line") or 0)
        refs, ref_errors = parse_source_refs(row.get(field), path, line, field)
        errors.extend(ref_errors)
        for ref in refs:
            if ref not in source_ids:
                errors.append(
                    issue(
                        "error",
                        "unknown_library_source_ref",
                        path,
                        "library row references a LIT-* source missing from source_library.md",
                        line=line,
                        ref=ref,
                        field=field,
                    )
                )
    return errors


def claim_warnings_and_errors(rows: list[dict[str, Any]], path: Path, source_ids: set[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    warnings: list[dict[str, Any]] = []
    errors = reference_errors(rows, path, "source_refs", source_ids)
    for row in rows:
        line = int(row.get("_line") or 0)
        claim = normalize_text(row.get("claim"))
        refs, _ref_errors = parse_source_refs(row.get("source_refs"), path, line, "source_refs")
        if not refs:
            warnings.append(issue("warning", "library_claim_without_source_refs", path, "claim row should include at least one LIT-* source ref", line=line, claim=claim))
        strength = normalize_text(row.get("claim_strength")).lower()
        if field_has_value(strength) and strength not in CLAIM_STRENGTHS:
            errors.append(issue("error", "invalid_library_claim_strength", path, "claim_strength is not in the task-contract vocabulary", line=line, claim=claim, claim_strength=strength))
        disputed = normalize_text(row.get("disputed_status")).lower()
        needs_caveat = strength in {"moderate", "strong"} or disputed in {"disputed", "deprecated", "context_only"}
        if needs_caveat and not field_has_value(row.get("caveats")):
            warnings.append(issue("warning", "library_claim_without_caveats", path, "strong/moderate or disputed claims should include caveats", line=line, claim=claim, claim_strength=strength, disputed_status=disputed))
    return warnings, errors


def update_log_warnings(rows: list[dict[str, Any]], path: Path) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    for row in rows:
        line = int(row.get("_line") or 0)
        task_id = normalize_text(row.get("task_id"))
        approver = normalize_text(row.get("reviewer_or_approver"))
        if not field_has_value(task_id) and not field_has_value(approver):
            warnings.append(issue("warning", "library_update_log_missing_provenance", path, "update log rows should include task ID or reviewer/approver provenance", line=line))
        if field_has_value(task_id) and not TASK_ID_RE.fullmatch(task_id):
            warnings.append(issue("warning", "library_update_log_task_id_invalid", path, "task_id should use TASK-0000 format", line=line, task_id=task_id))
    return warnings


def count_by_value(rows: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = normalize_text(row.get(field)).lower()
        if not value:
            value = "unspecified"
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def row_preview(row: dict[str, Any], fields: list[str]) -> dict[str, Any]:
    preview = {
        field: normalize_text(row.get(field))
        for field in fields
        if normalize_text(row.get(field))
    }
    if row.get("_line"):
        preview["line"] = row["_line"]
    if row.get("_path"):
        preview["path"] = row["_path"]
    return preview


def open_question_previews(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    closed_statuses = {"closed", "resolved", "answered", "done"}
    previews: list[dict[str, Any]] = []
    for row in rows:
        status = normalize_text(row.get("status")).lower()
        if status in closed_statuses:
            continue
        previews.append(row_preview(row, ["question_id", "question", "why_it_matters", "source_refs", "next_task", "status"]))
    return previews


def library_report(ops_dir: Path, now: datetime | None = None, stale_days: int | None = None) -> dict[str, Any]:
    current = now or datetime.now(timezone.utc)
    library_dir = ops_dir / LIBRARY_DIR
    warnings: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    rows_by_relative: dict[str, list[dict[str, Any]]] = {}

    if not ops_dir.exists() or not ops_dir.is_dir():
        errors.append(issue("error", "ops_dir_missing", ops_dir, "research_ops directory does not exist or is not a directory"))
        return {
            "ok": False,
            "action": "knowledge_library_validated",
            "ops_dir": str(ops_dir),
            "library_dir": str(library_dir),
            "source_count": 0,
            "row_counts": {},
            "warning_count": 0,
            "warnings": [],
            "error_count": len(errors),
            "errors": errors,
        }

    if not library_dir.exists():
        warnings.append(issue("warning", "library_dir_missing", library_dir, "research_ops/library is missing; run library init to bootstrap it"))
        return {
            "ok": True,
            "action": "knowledge_library_validated",
            "ops_dir": str(ops_dir),
            "library_dir": str(library_dir),
            "source_count": 0,
            "row_counts": {},
            "warning_count": len(warnings),
            "warnings": warnings,
            "error_count": 0,
            "errors": [],
        }
    if not library_dir.is_dir():
        errors.append(issue("error", "library_path_not_directory", library_dir, "research_ops/library must be a directory"))
        return {
            "ok": False,
            "action": "knowledge_library_validated",
            "ops_dir": str(ops_dir),
            "library_dir": str(library_dir),
            "source_count": 0,
            "row_counts": {},
            "warning_count": 0,
            "warnings": [],
            "error_count": len(errors),
            "errors": errors,
        }

    for relative, _template in STARTER_FILES:
        path = ops_dir / relative
        if not path.exists():
            warnings.append(issue("warning", "library_file_missing", path, f"expected knowledge library file is missing: {relative}", relative_path=str(relative)))
            continue
        if not path.is_file():
            errors.append(issue("error", "library_file_path_not_file", path, "library starter path must be a file", relative_path=str(relative)))
            continue
        spec = TABLE_SPECS[relative]
        rows, table_errors = parse_generated_table(path, relative, spec)
        rows_by_relative[str(relative)] = rows
        errors.extend(table_errors)

    source_path = ops_dir / LIBRARY_DIR / SOURCE_LIBRARY_FILE
    source_rows = rows_by_relative.get(str(Path(LIBRARY_DIR) / SOURCE_LIBRARY_FILE), [])
    source_ids, source_warnings, source_errors = source_library_warnings_and_errors(source_rows, source_path, current, stale_days)
    warnings.extend(source_warnings)
    errors.extend(source_errors)

    for filename in (KNOWLEDGE_INDEX_FILE, METHOD_INDEX_FILE, OPEN_QUESTIONS_FILE):
        relative = str(Path(LIBRARY_DIR) / filename)
        errors.extend(reference_errors(rows_by_relative.get(relative, []), ops_dir / relative, "source_refs", source_ids))

    claim_warnings, claim_errors = claim_warnings_and_errors(
        rows_by_relative.get(str(Path(LIBRARY_DIR) / CLAIM_MAP_FILE), []),
        ops_dir / LIBRARY_DIR / CLAIM_MAP_FILE,
        source_ids,
    )
    warnings.extend(claim_warnings)
    errors.extend(claim_errors)
    warnings.extend(
        update_log_warnings(
            rows_by_relative.get(str(Path(LIBRARY_DIR) / UPDATE_LOG_FILE), []),
            ops_dir / LIBRARY_DIR / UPDATE_LOG_FILE,
        )
    )

    knowledge_rows = rows_by_relative.get(str(Path(LIBRARY_DIR) / KNOWLEDGE_INDEX_FILE), [])
    claim_rows = rows_by_relative.get(str(Path(LIBRARY_DIR) / CLAIM_MAP_FILE), [])
    method_rows = rows_by_relative.get(str(Path(LIBRARY_DIR) / METHOD_INDEX_FILE), [])
    open_question_rows = rows_by_relative.get(str(Path(LIBRARY_DIR) / OPEN_QUESTIONS_FILE), [])
    update_rows = rows_by_relative.get(str(Path(LIBRARY_DIR) / UPDATE_LOG_FILE), [])
    open_questions = open_question_previews(open_question_rows)
    risky_sources = [
        row_preview(row, ["source_id", "status", "trust_tier", "title", "location", "reviewed_date", "notes"])
        for row in source_rows
        if normalize_text(row.get("status")).lower() in {"context_only", "disputed", "deprecated"}
    ]
    row_counts = {relative: len(rows) for relative, rows in sorted(rows_by_relative.items())}
    return {
        "ok": not errors,
        "action": "knowledge_library_validated",
        "ops_dir": str(ops_dir),
        "library_dir": str(library_dir),
        "source_count": len(source_ids),
        "row_counts": row_counts,
        "topic_count": len(knowledge_rows),
        "claim_count": len(claim_rows),
        "method_count": len(method_rows),
        "open_question_count": len(open_questions),
        "update_log_count": len(update_rows),
        "source_status_counts": count_by_value(source_rows, "status"),
        "source_trust_tier_counts": count_by_value(source_rows, "trust_tier"),
        "claim_strength_counts": count_by_value(claim_rows, "claim_strength"),
        "risky_source_count": len(risky_sources),
        "risky_sources": risky_sources[:10],
        "open_questions": open_questions[:10],
        "warning_count": len(warnings),
        "warnings": warnings,
        "error_count": len(errors),
        "errors": errors,
    }


def validation_exit_code(report: dict[str, Any]) -> int:
    if report.get("error_count", 0):
        return MALFORMED
    if report.get("warning_count", 0):
        return VALIDATION_FINDINGS
    return SUCCESS


def command_init(args: argparse.Namespace) -> int:
    if args.dry_run and args.write:
        print_json(
            {
                "ok": False,
                "action": "library_init_failed",
                "reason": "conflicting_flags",
                "message": "use either --dry-run or --write, not both",
            }
        )
        return INVALID_REQUEST

    dry_run = not args.write
    missing, existing, failures = init_plan(args.ops_dir)
    if failures:
        print_json(
            {
                "ok": False,
                "action": "library_init_failed",
                "dry_run": dry_run,
                "changed": False,
                "failures": failures,
            }
        )
        return MALFORMED

    if dry_run:
        print_json(
            {
                "ok": True,
                "action": "library_init_planned",
                "dry_run": True,
                "changed": bool(missing),
                "would_write": missing,
                "existing_files": existing,
                "next_step": "rerun with --write to add missing library starter files",
            }
        )
        return SUCCESS

    files_added: list[dict[str, Any]] = []
    try:
        for relative, template in STARTER_FILES:
            path = args.ops_dir / relative
            if path.exists():
                continue
            atomic_write_text(path, template)
            files_added.append(
                {
                    "relative_path": str(relative),
                    "path": str(path),
                    "bytes": len(template.encode("utf-8")),
                }
            )
    except OSError as exc:
        print_json(
            {
                "ok": False,
                "action": "library_init_failed",
                "dry_run": False,
                "changed": bool(files_added),
                "files_added": files_added,
                "reason": "write_failed",
                "error": str(exc),
            }
        )
        return MALFORMED

    _, existing_after, _ = init_plan(args.ops_dir)
    print_json(
        {
            "ok": True,
            "action": "library_initialized",
            "dry_run": False,
            "changed": bool(files_added),
            "files_added": files_added,
            "existing_files": [
                item for item in existing_after
                if item["relative_path"] not in {added["relative_path"] for added in files_added}
            ],
        }
    )
    return SUCCESS


def command_validate(args: argparse.Namespace) -> int:
    try:
        now = parse_now(args.now)
    except ValueError as exc:
        print_json({"ok": False, "action": "knowledge_library_validated", "reason": "invalid_now", "message": str(exc)})
        return INVALID_REQUEST
    stale_days = args.stale_days
    if stale_days is not None and stale_days < 0:
        print_json({"ok": False, "action": "knowledge_library_validated", "reason": "invalid_stale_days", "message": "--stale-days must be non-negative"})
        return INVALID_REQUEST
    report = library_report(args.ops_dir, now=now, stale_days=stale_days)
    print_json(report)
    return validation_exit_code(report)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Initialize knowledge library workspace files.")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser(
        "init",
        help="Add missing knowledge library starter files.",
        description="Preview or add missing research_ops/library starter files without overwriting existing files.",
    )
    init.add_argument("ops_dir", type=Path, help="Path to research_ops workspace.")
    init.add_argument("--dry-run", action="store_true", help="Explicitly report missing library files without writing.")
    init.add_argument("--write", action="store_true", help="Create only missing library files.")
    init.set_defaults(func=command_init)
    validate = sub.add_parser(
        "validate",
        help="Validate knowledge library Markdown contracts.",
        description="Read-only validation for research_ops/library generated blocks, source IDs, source refs, metadata, and update provenance.",
    )
    validate.add_argument("ops_dir", type=Path, help="Path to research_ops workspace.")
    validate.add_argument("--now", help="Override current time for deterministic stale review checks.")
    validate.add_argument("--stale-days", type=int, help="Warn when reviewed_date is older than this many days.")
    validate.set_defaults(func=command_validate)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
