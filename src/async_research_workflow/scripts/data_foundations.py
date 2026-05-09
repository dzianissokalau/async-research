#!/usr/bin/env python3
"""Validate read-only data foundation readiness files."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, Optional

from async_research_workflow.idea_catalog import catalog_surface_summary
from async_research_workflow.scripts.data_source_audit import (
    BLOCKED_GOVERNANCE_STATUSES,
    EXPERIMENT_READY_STATUSES,
    SOURCE_ID_PATTERN,
    canonical_row,
    freshness_window,
    parse_date,
    parse_register,
    row_map,
    source_age_days,
    source_stale,
    split_table_row,
    use_case_tokens,
    validate_rows,
)


SUCCESS = 0
VALIDATION_FINDINGS = 2
MALFORMED = 4

DATA_DIR_NAME = "data"
PROFILE_TEMPLATE_NAME = "DS-0000.md"
EXPECTED_DATA_FILES = (
    "data_catalog.md",
    "data_access.md",
    "join_map.md",
    "known_data_gaps.md",
    "profiles/README.md",
)
PROFILE_FILENAME_RE = re.compile(r"^DS-[0-9]{4}\.md$")
PROFILE_FIELD_RE = re.compile(r"^\s*(?:-\s*)?([A-Za-z][A-Za-z0-9_]*):\s*(.*)$")
GAP_REF_RE = re.compile(r"\bDG-[0-9]{4}\b")
NO_VALUE_MARKERS = {"", "none", "n/a", "na", "unknown", "todo", "tbd", "yyyy-mm-dd"}
ACTIVE_IDEA_STATUSES = {"", "candidate", "raw", "scored", "blocked"}
INACTIVE_IDEA_STATUSES = {"parked", "rejected", "promoted"}
REQUIRED_PROFILE_POLICY_FIELDS = ("approved_use_cases", "blocked_use_cases")
SOURCE_USE_CASE_CHOICES = ("discovery", "experiment_planning", "accepted_evidence", "context")
DEFAULT_DASHBOARD_USE_CASE = "experiment_planning"


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def field_has_value(value: Any) -> bool:
    return str(value or "").strip().lower() not in NO_VALUE_MARKERS


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


def normalize_compare(value: Any) -> str:
    return " ".join(normalize_text(value).lower().split())


def issue(
    severity: str,
    reason: str,
    path: Path,
    message: str,
    **details: Any,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "severity": severity,
        "reason": reason,
        "path": str(path),
        "message": message,
    }
    item.update(details)
    return item


def parse_now(value: Optional[str]) -> datetime:
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


def first_markdown_table(path: Path) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return [], []
    except OSError as exc:
        return [], [issue("error", "table_read_failed", path, f"cannot read {path}: {exc}")]

    header: list[str] = []
    rows: list[dict[str, str]] = []
    errors: list[dict[str, Any]] = []
    in_table = False
    for line_number, line in enumerate(text.splitlines(), start=1):
        cells = split_table_row(line)
        if not cells:
            if in_table:
                break
            continue
        if not in_table:
            header = [cell.strip().lower() for cell in cells]
            in_table = True
            continue
        if all(set(cell) <= {"-", ":", " "} for cell in cells):
            continue
        if len(cells) != len(header):
            errors.append(
                issue(
                    "error",
                    "malformed_data_table",
                    path,
                    f"markdown table row has {len(cells)} cells but header has {len(header)}",
                    line=line_number,
                )
            )
            continue
        rows.append(dict(zip(header, cells)))
    return rows, errors


def parse_profile(path: Path) -> dict[str, str]:
    fields: dict[str, str] = {}
    text = path.read_text(encoding="utf-8")
    for line in text.splitlines():
        match = PROFILE_FIELD_RE.match(line)
        if match is None:
            continue
        key = match.group(1).strip().lower()
        value = match.group(2).strip()
        fields.setdefault(key, value)
    return fields


def profile_paths(profile_dir: Path) -> tuple[list[Path], list[str]]:
    if not profile_dir.exists():
        return [], []
    paths: list[Path] = []
    ignored: list[str] = []
    for path in sorted(profile_dir.glob("*.md")):
        if path.name == "README.md":
            continue
        if path.name == PROFILE_TEMPLATE_NAME:
            ignored.append(str(path))
            continue
        paths.append(path)
    return paths, ignored


def load_profiles(profile_dir: Path, audit_by_id: dict[str, dict[str, str]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    profiles: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    paths, ignored_templates = profile_paths(profile_dir)
    seen: dict[str, Path] = {}
    for path in paths:
        filename_id = path.stem
        if PROFILE_FILENAME_RE.match(path.name) is None:
            errors.append(
                issue(
                    "error",
                    "invalid_profile_filename",
                    path,
                    "profile filename must use DS-0000.md format",
                    filename_id=filename_id,
                )
            )
        try:
            fields = parse_profile(path)
        except OSError as exc:
            errors.append(issue("error", "profile_read_failed", path, f"cannot read profile: {exc}"))
            continue

        source_id = normalize_text(fields.get("source_id"))
        if SOURCE_ID_PATTERN.match(source_id) is None:
            errors.append(
                issue(
                    "error",
                    "profile_source_id_missing_or_invalid",
                    path,
                    "profile source_id must exist and match DS-0000",
                    filename_id=filename_id,
                    source_id=source_id,
                )
            )
            continue
        if source_id != filename_id:
            errors.append(
                issue(
                    "error",
                    "profile_source_id_mismatch",
                    path,
                    "profile filename and internal source_id must match",
                    filename_id=filename_id,
                    source_id=source_id,
                )
            )
        if source_id in seen:
            errors.append(
                issue(
                    "error",
                    "duplicate_profile_id",
                    path,
                    f"profile source_id {source_id} appears in multiple profile files",
                    source_id=source_id,
                    first_path=str(seen[source_id]),
                )
            )
        else:
            seen[source_id] = path
        if source_id not in audit_by_id:
            errors.append(
                issue(
                    "error",
                    "profile_without_audit_row",
                    path,
                    f"profile {source_id} has no matching data_source_audit.md row",
                    source_id=source_id,
                )
            )
        profiles.append({"path": path, "source_id": source_id, "fields": fields})
    return profiles, warnings, errors, ignored_templates


def review_age_days(value: str, now: datetime) -> Optional[float]:
    reviewed = parse_date(value)
    if reviewed is None:
        return None
    return round((now - reviewed).total_seconds() / 86400, 1)


def profile_drift_warnings(
    profile: dict[str, Any],
    audit_row: dict[str, str],
    now: datetime,
    access_by_id: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    path = profile["path"]
    source_id = profile["source_id"]
    fields = profile["fields"]
    warnings: list[dict[str, Any]] = []
    comparisons = (
        ("source_name", "source_name"),
        ("audit_status", "approval_status"),
        ("approved_use_cases", "approved_use_cases"),
        ("blocked_use_cases", "blocked_use_cases"),
        ("reviewed_date", "last_reviewed"),
        ("reviewer", "approved_by"),
    )
    for profile_key, audit_key in comparisons:
        profile_value = fields.get(profile_key)
        if not field_has_value(profile_value):
            continue
        audit_value = audit_row.get(audit_key, "")
        if normalize_compare(profile_value) != normalize_compare(audit_value):
            warnings.append(
                issue(
                    "warning",
                    "profile_audit_projection_drift",
                    path,
                    f"profile {profile_key} differs from authoritative data_source_audit.md {audit_key}",
                    source_id=source_id,
                    profile_field=profile_key,
                    audit_field=audit_key,
                    profile_value=profile_value,
                    audit_value=audit_value,
                )
            )

    for field in REQUIRED_PROFILE_POLICY_FIELDS:
        if field_has_value(fields.get(field)):
            continue
        warnings.append(
            issue(
                "warning",
                "missing_profile_use_policy_field",
                path,
                f"profile {source_id} should record {field}",
                source_id=source_id,
                profile_field=field,
            )
        )

    reviewed_date = normalize_text(fields.get("reviewed_date"))
    if not field_has_value(reviewed_date):
        warnings.append(
            issue(
                "warning",
                "missing_profile_reviewed_date",
                path,
                f"profile {source_id} should record reviewed_date",
                source_id=source_id,
            )
        )
    else:
        age = review_age_days(reviewed_date, now)
        if age is None:
            warnings.append(
                issue(
                    "warning",
                    "invalid_profile_reviewed_date",
                    path,
                    "profile reviewed_date should use YYYY-MM-DD",
                    source_id=source_id,
                    reviewed_date=reviewed_date,
                )
            )
        elif freshness_window(audit_row) > 0 and age > freshness_window(audit_row):
            warnings.append(
                issue(
                    "warning",
                    "stale_profile_review",
                    path,
                    f"profile {source_id} is outside the audit freshness window",
                    source_id=source_id,
                    age_days=age,
                    freshness_window_days=freshness_window(audit_row),
                )
            )

    access_row = access_by_id.get(source_id, {})
    has_profile_access = any(
        field_has_value(fields.get(key))
        for key in ("location", "access_method", "access_notes", "contact_or_docs")
    )
    has_access_row = any(
        field_has_value(access_row.get(key))
        for key in ("access_method", "location", "access_check", "notes")
    )
    if not has_profile_access and not has_access_row:
        warnings.append(
            issue(
                "warning",
                "missing_access_notes",
                path,
                f"profile {source_id} should describe a verifiable access path",
                source_id=source_id,
            )
        )
    return warnings


def missing_profile_warnings(
    rows: list[dict[str, str]],
    profiles_by_id: dict[str, dict[str, Any]],
    audit_path: Path,
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    for row in rows:
        source_id = row["source_id"]
        if source_id in profiles_by_id:
            continue
        status = row.get("approval_status", "")
        if status in EXPERIMENT_READY_STATUSES:
            warnings.append(
                issue(
                    "warning",
                    "missing_experiment_ready_profile",
                    audit_path,
                    f"{source_id} is experiment-ready but has no data profile",
                    source_id=source_id,
                    approval_status=status,
                )
            )
        elif status == "explicitly_approved" and not field_has_value(row.get("review_notes")):
            warnings.append(
                issue(
                    "warning",
                    "explicitly_approved_profile_missing_context",
                    audit_path,
                    f"{source_id} is explicitly approved without a profile or review note explaining exact use",
                    source_id=source_id,
                    approval_status=status,
                )
            )
    return warnings


def audit_profile_link_warnings(
    rows: list[dict[str, str]],
    profiles: list[dict[str, Any]],
    ops_dir: Path,
    audit_path: Path,
) -> list[dict[str, Any]]:
    if not any("profile_path" in row for row in rows):
        return []

    profiles_by_path = {profile["path"]: profile for profile in profiles}
    warnings: list[dict[str, Any]] = []
    for row in rows:
        source_id = row["source_id"]
        approval_status = row.get("approval_status", "")
        profile_path = normalize_text(row.get("profile_path"))
        if not profile_path:
            if approval_status in EXPERIMENT_READY_STATUSES:
                warnings.append(
                    issue(
                        "warning",
                        "missing_audit_profile_link",
                        audit_path,
                        f"{source_id} is experiment-ready but profile_path is empty",
                        source_id=source_id,
                        approval_status=approval_status,
                    )
                )
            continue

        expected = f"data/profiles/{source_id}.md"
        if profile_path != expected:
            warnings.append(
                issue(
                    "warning",
                    "noncanonical_audit_profile_link",
                    audit_path,
                    f"{source_id} profile_path should use {expected}",
                    source_id=source_id,
                    profile_path=profile_path,
                    expected_profile_path=expected,
                )
            )

        linked_path = ops_dir / profile_path
        if not linked_path.exists():
            warnings.append(
                issue(
                    "warning",
                    "audit_profile_link_missing",
                    audit_path,
                    f"{source_id} profile_path points to a missing file",
                    source_id=source_id,
                    profile_path=profile_path,
                )
            )
            continue

        linked_profile = profiles_by_path.get(linked_path)
        if linked_profile is None:
            warnings.append(
                issue(
                    "warning",
                    "audit_profile_link_not_active_profile",
                    audit_path,
                    f"{source_id} profile_path does not point to an active DS-* profile",
                    source_id=source_id,
                    profile_path=profile_path,
                )
            )
            continue
        if linked_profile["source_id"] != source_id:
            warnings.append(
                issue(
                    "warning",
                    "audit_profile_link_source_mismatch",
                    audit_path,
                    f"{source_id} profile_path points to {linked_profile['source_id']}",
                    source_id=source_id,
                    linked_source_id=linked_profile["source_id"],
                    profile_path=profile_path,
                )
            )
    return warnings


def join_map_warnings(rows: list[dict[str, str]], path: Path, audit_by_id: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        join_id = normalize_text(row.get("join_id")) or f"row-{index}"
        left = normalize_text(row.get("left_source_id"))
        right = normalize_text(row.get("right_source_id"))
        caveats = normalize_text(row.get("caveats"))
        for side, source_id in (("left_source_id", left), ("right_source_id", right)):
            if field_has_value(source_id) and source_id not in audit_by_id:
                warnings.append(
                    issue(
                        "warning",
                        "join_source_missing_from_audit",
                        path,
                        f"{join_id} references {source_id}, which is absent from data_source_audit.md",
                        join_id=join_id,
                        source_id=source_id,
                        field=side,
                    )
                )
        if field_has_value(left) and field_has_value(right) and not field_has_value(caveats):
            warnings.append(
                issue(
                    "warning",
                    "join_without_caveats",
                    path,
                    f"{join_id} should state caveats before this join path is used",
                    join_id=join_id,
                )
            )
    return warnings


def known_gap_ids(rows: list[dict[str, str]]) -> set[str]:
    return {
        normalize_text(row.get("gap_id"))
        for row in rows
        if GAP_REF_RE.fullmatch(normalize_text(row.get("gap_id")))
    }


def active_idea_gap_warnings(ops_dir: Path, known_gaps: set[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    warnings: list[dict[str, Any]] = []
    references: list[dict[str, Any]] = []
    ideas_dir = ops_dir / "ideas"
    if not ideas_dir.exists():
        return warnings, references
    for path in sorted(ideas_dir.glob("IDEA-*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        status = normalize_text(payload.get("status")).lower()
        if status in INACTIVE_IDEA_STATUSES:
            continue
        if status and status not in ACTIVE_IDEA_STATUSES:
            continue
        refs = sorted(set(GAP_REF_RE.findall(json.dumps(payload, sort_keys=True))))
        if not refs:
            continue
        references.append({"path": str(path), "gap_ids": refs})
        missing = [ref for ref in refs if ref not in known_gaps]
        if missing:
            warnings.append(
                issue(
                    "warning",
                    "active_idea_unknown_data_gap",
                    path,
                    "active idea references data gap ids missing from data/known_data_gaps.md",
                    missing_gap_ids=missing,
                )
            )
    return warnings, references


def data_foundation_report(ops_dir: Path, now: Optional[datetime] = None) -> dict[str, Any]:
    current = now or datetime.now(timezone.utc)
    audit_register = ops_dir / "data_source_audit.md"
    data_dir = ops_dir / DATA_DIR_NAME
    try:
        schema_version, audit_rows = parse_register(audit_register)
    except ValueError as exc:
        return {
            "ok": False,
            "action": "data_foundations_validate",
            "reason": "source_audit_malformed",
            "ops_dir": str(ops_dir),
            "audit_register": str(audit_register),
            "data_dir": str(data_dir),
            "source_count": 0,
            "profile_count": 0,
            "warning_count": 0,
            "warnings": [],
            "error_count": 1,
            "errors": [issue("error", "source_audit_malformed", audit_register, str(exc))],
        }

    audit_errors = validate_rows(schema_version, audit_rows)
    if audit_errors:
        return {
            "ok": False,
            "action": "data_foundations_validate",
            "reason": "source_audit_validation_failed",
            "ops_dir": str(ops_dir),
            "audit_register": str(audit_register),
            "data_dir": str(data_dir),
            "source_count": len(audit_rows),
            "profile_count": 0,
            "warning_count": 0,
            "warnings": [],
            "error_count": len(audit_errors),
            "errors": audit_errors,
        }

    warnings: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    ignored_templates: list[str] = []
    audit_rows = [canonical_row(row) for row in audit_rows]
    audit_by_id = row_map(audit_rows)

    if not data_dir.exists():
        warnings.append(
            issue(
                "warning",
                "data_dir_missing",
                data_dir,
                "research_ops/data is missing; add Phase 1 starter files before deeper data readiness work",
            )
        )
        return {
            "ok": True,
            "action": "data_foundations_validate",
            "ops_dir": str(ops_dir),
            "audit_register": str(audit_register),
            "data_dir": str(data_dir),
            "source_count": len(audit_rows),
            "profile_count": 0,
            "warning_count": len(warnings),
            "warnings": warnings,
            "error_count": 0,
            "errors": [],
            "ignored_templates": ignored_templates,
            "active_idea_gap_refs": [],
        }

    for relative in EXPECTED_DATA_FILES:
        path = data_dir / relative
        if not path.exists():
            warnings.append(
                issue(
                    "warning",
                    "data_foundation_file_missing",
                    path,
                    f"expected data foundation file is missing: data/{relative}",
                    relative_path=f"data/{relative}",
                )
            )

    _catalog_rows, table_errors = first_markdown_table(data_dir / "data_catalog.md")
    errors.extend(table_errors)
    data_access_rows, table_errors = first_markdown_table(data_dir / "data_access.md")
    errors.extend(table_errors)
    join_rows, table_errors = first_markdown_table(data_dir / "join_map.md")
    errors.extend(table_errors)
    gap_rows, table_errors = first_markdown_table(data_dir / "known_data_gaps.md")
    errors.extend(table_errors)

    access_by_id = {
        normalize_text(row.get("source_id")): row
        for row in data_access_rows
        if field_has_value(row.get("source_id"))
    }
    profiles, profile_warnings, profile_errors, ignored_templates = load_profiles(data_dir / "profiles", audit_by_id)
    warnings.extend(profile_warnings)
    errors.extend(profile_errors)
    profiles_by_id = {
        profile["source_id"]: profile
        for profile in profiles
        if field_has_value(profile.get("source_id"))
    }

    warnings.extend(missing_profile_warnings(audit_rows, profiles_by_id, audit_register))
    warnings.extend(audit_profile_link_warnings(audit_rows, profiles, ops_dir, audit_register))
    for profile in profiles:
        audit_row = audit_by_id.get(profile["source_id"])
        if audit_row is None:
            continue
        warnings.extend(profile_drift_warnings(profile, audit_row, current, access_by_id))

    warnings.extend(join_map_warnings(join_rows, data_dir / "join_map.md", audit_by_id))
    gap_warnings, gap_refs = active_idea_gap_warnings(ops_dir, known_gap_ids(gap_rows))
    warnings.extend(gap_warnings)

    return {
        "ok": not errors,
        "action": "data_foundations_validate",
        "ops_dir": str(ops_dir),
        "audit_register": str(audit_register),
        "data_dir": str(data_dir),
        "source_count": len(audit_rows),
        "profile_count": len(profiles),
        "warning_count": len(warnings),
        "warnings": warnings,
        "error_count": len(errors),
        "errors": errors,
        "ignored_templates": ignored_templates,
        "active_idea_gap_refs": gap_refs,
    }


def validation_exit_code(report: dict[str, Any]) -> int:
    if report.get("reason") in {"source_audit_malformed", "source_audit_validation_failed"}:
        return MALFORMED
    if report.get("error_count", 0):
        return MALFORMED
    if report.get("warning_count", 0):
        return VALIDATION_FINDINGS
    return SUCCESS


def source_findings_by_id(report: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in report.get("errors", []) + report.get("warnings", []):
        if not isinstance(item, dict):
            continue
        source_id = normalize_text(item.get("source_id"))
        if not source_id:
            continue
        grouped.setdefault(source_id, []).append(
            {
                "severity": item.get("severity"),
                "reason": item.get("reason"),
                "message": item.get("message"),
                "path": item.get("path"),
            }
        )
    return grouped


def row_by_source_id(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    return {
        normalize_text(row.get("source_id")): row
        for row in rows
        if field_has_value(row.get("source_id"))
    }


def profile_by_source_id(profiles: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        normalize_text(profile.get("source_id")): profile
        for profile in profiles
        if field_has_value(profile.get("source_id"))
    }


def table_value(row: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = normalize_text(row.get(key))
        if field_has_value(value):
            return value
    return ""


def source_use_case_status(row: dict[str, str], use_case: str) -> tuple[bool, str]:
    approved_use_cases = use_case_tokens(row.get("approved_use_cases", ""))
    blocked_use_cases = use_case_tokens(row.get("blocked_use_cases", ""))
    if "all" in blocked_use_cases or use_case in blocked_use_cases:
        return False, "use_case_blocked"
    if "all" not in approved_use_cases and use_case not in approved_use_cases:
        return False, "use_case_not_approved"
    return True, "use_case_allowed"


def source_dashboard_row(
    row: dict[str, str],
    now: datetime,
    profiles_by_id: dict[str, dict[str, Any]],
    catalog_by_id: dict[str, dict[str, str]],
    access_by_id: dict[str, dict[str, str]],
    findings_by_id: dict[str, list[dict[str, Any]]],
    use_case: str,
) -> dict[str, Any]:
    source_id = row["source_id"]
    profile = profiles_by_id.get(source_id, {})
    profile_fields = profile.get("fields") if isinstance(profile.get("fields"), dict) else {}
    catalog_row = catalog_by_id.get(source_id, {})
    access_row = access_by_id.get(source_id, {})
    stale = source_stale(row, now)
    approved = row.get("approval_status") in EXPERIMENT_READY_STATUSES
    use_case_allowed, use_case_reason = source_use_case_status(row, use_case)
    usable_today = approved and not stale and use_case_allowed
    if usable_today:
        usability_reason = "approved_fresh_and_use_case_allowed"
    elif row.get("approval_status") not in EXPERIMENT_READY_STATUSES:
        usability_reason = f"approval_status_{row.get('approval_status') or 'unknown'}"
    elif stale:
        usability_reason = "source_review_stale"
    else:
        usability_reason = use_case_reason
    profile_path = table_value(catalog_row, "profile_path") or str(profile.get("path") or "")
    return {
        "source_id": source_id,
        "source_name": row.get("source_name"),
        "approval_status": row.get("approval_status"),
        "source_tier": row.get("source_tier"),
        "usable_today": usable_today,
        "usability_reason": usability_reason,
        "use_case": use_case,
        "use_case_allowed": use_case_allowed,
        "stale": stale,
        "last_reviewed": row.get("last_reviewed"),
        "age_days": source_age_days(row, now),
        "freshness_window_days": freshness_window(row),
        "approved_use_cases": row.get("approved_use_cases"),
        "blocked_use_cases": row.get("blocked_use_cases"),
        "known_limitations": row.get("known_limitations"),
        "citation_requirements": row.get("citation_requirements"),
        "profile_path": profile_path,
        "grain": table_value(catalog_row, "grain"),
        "geography": table_value(catalog_row, "geography"),
        "time_coverage": table_value(catalog_row, "time_coverage"),
        "access_summary": table_value(catalog_row, "access_summary", "access_method") or table_value(access_row, "access_method", "access_check"),
        "access_location": table_value(access_row, "location") or table_value(profile_fields, "location"),
        "dashboard_findings": findings_by_id.get(source_id, []),
    }


def gap_dashboard_rows(gap_rows: list[dict[str, str]], active_gap_refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    refs_by_gap: dict[str, list[str]] = {}
    for ref in active_gap_refs:
        path = normalize_text(ref.get("path"))
        for gap_id in ref.get("gap_ids", []):
            refs_by_gap.setdefault(str(gap_id), []).append(path)
    rows: list[dict[str, Any]] = []
    for row in gap_rows:
        gap_id = normalize_text(row.get("gap_id"))
        if not field_has_value(gap_id):
            continue
        rows.append(
            {
                "gap_id": gap_id,
                "status": normalize_text(row.get("status")) or "unknown",
                "affected_items": normalize_text(row.get("affected_items")),
                "data_needed": normalize_text(row.get("data_needed")),
                "blocker": normalize_text(row.get("blocker")),
                "next_step": normalize_text(row.get("next_step")),
                "active_idea_refs": sorted(set(refs_by_gap.get(gap_id, []))),
            }
        )
    return rows


def join_dashboard_rows(join_rows: list[dict[str, str]], audit_by_id: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(join_rows, start=1):
        join_id = normalize_text(row.get("join_id")) or f"row-{index}"
        left = normalize_text(row.get("left_source_id"))
        right = normalize_text(row.get("right_source_id"))
        caveats = normalize_text(row.get("caveats"))
        rows.append(
            {
                "join_id": join_id,
                "left_source_id": left,
                "left_status": audit_by_id.get(left, {}).get("approval_status", "missing") if field_has_value(left) else "missing",
                "right_source_id": right,
                "right_status": audit_by_id.get(right, {}).get("approval_status", "missing") if field_has_value(right) else "missing",
                "join_keys": normalize_text(row.get("join_keys")),
                "grain_after_join": normalize_text(row.get("grain_after_join")),
                "status": normalize_text(row.get("status")) or "unknown",
                "caveats": caveats,
                "has_caveats": field_has_value(caveats),
                "missing_source_ids": [
                    source_id
                    for source_id in (left, right)
                    if field_has_value(source_id) and source_id not in audit_by_id
                ],
            }
        )
    return rows


def data_blocked_ideas(
    catalog_summary: dict[str, Any],
    active_gap_refs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in catalog_summary.get("blocked_ideas", []):
        idea_id = normalize_text(item.get("idea_id")) or normalize_text(item.get("filename_id"))
        gap_reasons = item.get("data_or_evidence_gaps") if isinstance(item.get("data_or_evidence_gaps"), list) else []
        if item.get("recommended_next_task") != "data_readiness" and not gap_reasons:
            continue
        seen.add(idea_id)
        rows.append(
            {
                "idea_id": idea_id,
                "title": item.get("title"),
                "status": item.get("status"),
                "derived_label": item.get("derived_label"),
                "recommended_next_task": item.get("recommended_next_task"),
                "weighted_score": item.get("weighted_score"),
                "reasons": [
                    normalize_text(gap.get("reason")) or "data_or_evidence_gap"
                    for gap in gap_reasons
                    if isinstance(gap, dict)
                ] or ["data_readiness_required"],
                "gap_ids": [],
                "path": item.get("path"),
            }
        )
    for ref in active_gap_refs:
        path = normalize_text(ref.get("path"))
        idea_id = Path(path).stem if path else "unknown"
        if idea_id in seen:
            for row in rows:
                if row["idea_id"] == idea_id:
                    row["gap_ids"] = sorted(set(row.get("gap_ids", []) + list(ref.get("gap_ids", []))))
            continue
        rows.append(
            {
                "idea_id": idea_id,
                "title": "unavailable",
                "status": "active",
                "derived_label": "data_gap_ref",
                "recommended_next_task": "data_readiness",
                "weighted_score": "unavailable",
                "reasons": ["active_idea_data_gap_ref"],
                "gap_ids": list(ref.get("gap_ids", [])),
                "path": path,
            }
        )
    return sorted(rows, key=lambda item: str(item.get("idea_id")))


def catalog_dashboard_findings(catalog_summary: dict[str, Any]) -> list[dict[str, Any]]:
    warnings = catalog_summary.get("warnings") if isinstance(catalog_summary.get("warnings"), list) else []
    failures = catalog_summary.get("failures") if isinstance(catalog_summary.get("failures"), list) else []
    findings: list[dict[str, Any]] = []
    for item in warnings:
        if isinstance(item, dict):
            findings.append({**item, "surface": "idea_catalog", "severity": "warning"})
    for item in failures:
        if isinstance(item, dict):
            findings.append({**item, "surface": "idea_catalog", "severity": "error"})
    return findings


def dashboard_exit_code(data_exit_code: int, catalog_summary: dict[str, Any]) -> int:
    if data_exit_code == MALFORMED:
        return MALFORMED
    warning_count = int(catalog_summary.get("warning_count") or 0)
    failure_count = int(catalog_summary.get("failure_count") or 0)
    if warning_count or failure_count:
        return VALIDATION_FINDINGS
    return data_exit_code


def data_dashboard_report(
    ops_dir: Path,
    now: Optional[datetime] = None,
    use_case: str = DEFAULT_DASHBOARD_USE_CASE,
) -> dict[str, Any]:
    current = now or datetime.now(timezone.utc)
    validation = data_foundation_report(ops_dir, now=current)
    data_exit_code = validation_exit_code(validation)
    audit_register = ops_dir / "data_source_audit.md"
    data_dir = ops_dir / DATA_DIR_NAME
    audit_rows: list[dict[str, str]] = []
    audit_errors: list[dict[str, Any]] = []
    try:
        schema_version, parsed_rows = parse_register(audit_register)
        row_errors = validate_rows(schema_version, parsed_rows)
        if row_errors:
            audit_errors.extend(row_errors)
        else:
            audit_rows = [canonical_row(row) for row in parsed_rows]
    except ValueError as exc:
        audit_errors.append(issue("error", "source_audit_malformed", audit_register, str(exc)))

    audit_by_id = row_map(audit_rows) if audit_rows else {}
    catalog_rows, catalog_errors = first_markdown_table(data_dir / "data_catalog.md")
    access_rows, access_errors = first_markdown_table(data_dir / "data_access.md")
    join_rows, join_errors = first_markdown_table(data_dir / "join_map.md")
    gap_rows, gap_errors = first_markdown_table(data_dir / "known_data_gaps.md")
    profiles, profile_warnings, profile_errors, ignored_templates = load_profiles(data_dir / "profiles", audit_by_id) if audit_by_id else ([], [], [], [])
    findings_by_id = source_findings_by_id(validation)
    profiles_by_id = profile_by_source_id(profiles)
    catalog_by_id = row_by_source_id(catalog_rows)
    access_by_id = row_by_source_id(access_rows)
    source_rows = [
        source_dashboard_row(row, current, profiles_by_id, catalog_by_id, access_by_id, findings_by_id, use_case)
        for row in sorted(audit_rows, key=lambda item: item["source_id"])
    ]
    catalog_summary = catalog_surface_summary(ops_dir)
    catalog_findings = catalog_dashboard_findings(catalog_summary)
    exit_code = dashboard_exit_code(data_exit_code, catalog_summary)
    active_gap_refs = validation.get("active_idea_gap_refs") if isinstance(validation.get("active_idea_gap_refs"), list) else []
    gap_rows_dashboard = gap_dashboard_rows(gap_rows, active_gap_refs)
    join_rows_dashboard = join_dashboard_rows(join_rows, audit_by_id)
    validator_findings = validation.get("errors", []) + validation.get("warnings", [])

    approved_sources = [row for row in source_rows if row["approval_status"] in EXPERIMENT_READY_STATUSES]
    candidate_sources = [row for row in source_rows if row["approval_status"] == "candidate"]
    needs_review_sources = [row for row in source_rows if row["approval_status"] in {"unknown", "explicitly_approved"}]
    blocked_sources = [row for row in source_rows if row["approval_status"] in BLOCKED_GOVERNANCE_STATUSES]
    stale_sources = [row for row in source_rows if row["stale"]]
    usable_today = [row for row in source_rows if row["usable_today"]]
    ideas_blocked = data_blocked_ideas(catalog_summary, active_gap_refs)
    join_caveats = [row for row in join_rows_dashboard if row["has_caveats"] or row["missing_source_ids"]]
    table_parse_errors = catalog_errors + access_errors + join_errors + gap_errors
    catalog_failure_count = int(catalog_summary.get("failure_count") or 0)
    catalog_warning_count = int(catalog_summary.get("warning_count") or 0)
    return {
        "ok": validation.get("ok") is True and catalog_failure_count == 0,
        "action": "data_dashboard_rendered",
        "ops_dir": str(ops_dir),
        "audit_register": str(audit_register),
        "data_dir": str(data_dir),
        "use_case": use_case,
        "read_only": True,
        "changed": False,
        "generated_from": "data_foundation_validator_and_read_model",
        "validation_exit_code": exit_code,
        "summary": {
            "source_count": len(source_rows),
            "usable_today_count": len(usable_today),
            "approved_source_count": len(approved_sources),
            "candidate_source_count": len(candidate_sources),
            "needs_review_source_count": len(needs_review_sources),
            "blocked_source_count": len(blocked_sources),
            "stale_source_count": len(stale_sources),
            "data_gap_count": len(gap_rows_dashboard),
            "open_data_gap_count": len([row for row in gap_rows_dashboard if row["status"] not in {"closed", "resolved"}]),
            "ideas_blocked_by_data_count": len(ideas_blocked),
            "join_path_count": len(join_rows_dashboard),
            "join_caveat_count": len(join_caveats),
            "validator_warning_count": validation.get("warning_count", 0),
            "validator_error_count": validation.get("error_count", 0),
            "catalog_warning_count": catalog_warning_count,
            "catalog_failure_count": catalog_failure_count,
        },
        "operator_summary": {
            "use_case": use_case,
            "usable_today_source_ids": [row["source_id"] for row in usable_today],
            "attention_needed": sorted(
                set(
                    [row["source_id"] for row in blocked_sources]
                    + [row["source_id"] for row in stale_sources]
                    + [row["source_id"] for row in candidate_sources]
                    + [row["source_id"] for row in needs_review_sources]
                )
            ),
            "blocked_idea_ids": [row["idea_id"] for row in ideas_blocked],
        },
        "sections": {
            "usable_today_sources": usable_today,
            "approved_sources": approved_sources,
            "candidate_sources": candidate_sources,
            "needs_review_sources": needs_review_sources,
            "blocked_sources": blocked_sources,
            "stale_source_reviews": stale_sources,
            "data_gaps": gap_rows_dashboard,
            "ideas_blocked_by_data": ideas_blocked,
            "join_paths": join_rows_dashboard,
            "join_caveats": join_caveats,
            "validator_findings": validator_findings,
            "catalog_findings": catalog_findings,
        },
        "validation": validation,
        "catalog": {
            "ok": catalog_summary.get("ok") is True,
            "validation_exit_code": catalog_summary.get("validation_exit_code"),
            "warning_count": catalog_warning_count,
            "failure_count": catalog_failure_count,
        },
        "read_model_warnings": profile_warnings + list(catalog_summary.get("warnings", [])),
        "read_model_errors": audit_errors + table_parse_errors + profile_errors + list(catalog_summary.get("failures", [])),
        "ignored_templates": ignored_templates,
    }


def command_validate(args: argparse.Namespace) -> int:
    try:
        now = parse_now(args.now)
    except ValueError as exc:
        print_json({
            "ok": False,
            "action": "data_foundations_validate",
            "reason": "invalid_now",
            "error_count": 1,
            "errors": [{"reason": "invalid_now", "message": str(exc)}],
            "warning_count": 0,
            "warnings": [],
        })
        return MALFORMED

    report = data_foundation_report(args.ops_dir, now=now)
    print_json(report)
    return validation_exit_code(report)


def command_dashboard(args: argparse.Namespace) -> int:
    try:
        now = parse_now(args.now)
    except ValueError as exc:
        print_json({
            "ok": False,
            "action": "data_dashboard_rendered",
            "reason": "invalid_now",
            "validation_exit_code": MALFORMED,
            "error_count": 1,
            "errors": [{"reason": "invalid_now", "message": str(exc)}],
            "warning_count": 0,
            "warnings": [],
            "read_only": True,
            "changed": False,
        })
        return MALFORMED
    report = data_dashboard_report(args.ops_dir, now=now, use_case=args.use_case)
    print_json(report)
    return int(report["validation_exit_code"])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate read-only data foundation readiness files.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser(
        "validate",
        help="Validate research_ops/data readiness contracts.",
        description="Validate data profiles, access notes, join caveats, and known data gap references without writing files.",
    )
    validate.add_argument("ops_dir", type=Path, help="Path to research_ops.")
    validate.add_argument("--now", help="Override current time for deterministic freshness checks.")
    validate.set_defaults(func=command_validate)
    dashboard = subparsers.add_parser(
        "dashboard",
        help="Render a read-only data readiness dashboard.",
        description="Render approved, candidate, blocked, stale, gap-blocked, and join-caveat data views without writing files.",
    )
    dashboard.add_argument("ops_dir", type=Path, help="Path to research_ops.")
    dashboard.add_argument("--now", help="Override current time for deterministic freshness checks.")
    dashboard.add_argument("--use-case", choices=SOURCE_USE_CASE_CHOICES, default=DEFAULT_DASHBOARD_USE_CASE, help="Use case for usable-today source policy.")
    dashboard.set_defaults(func=command_dashboard)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
