#!/usr/bin/env python3
"""Validate read-only data foundation readiness files."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, Optional

from async_research_workflow.scripts.data_source_audit import (
    EXPERIMENT_READY_STATUSES,
    SOURCE_ID_PATTERN,
    canonical_row,
    freshness_window,
    parse_date,
    parse_register,
    row_map,
    split_table_row,
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
    if report.get("reason") in {"source_audit_malformed", "source_audit_validation_failed"}:
        return MALFORMED
    if report.get("error_count", 0):
        return MALFORMED
    if report.get("warning_count", 0):
        return VALIDATION_FINDINGS
    return SUCCESS


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
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
