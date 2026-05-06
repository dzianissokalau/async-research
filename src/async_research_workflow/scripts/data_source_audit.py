#!/usr/bin/env python3
"""Maintain and check the async research data source audit register."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
from datetime import datetime, timezone
from typing import Any, Iterable, Optional


SUCCESS = 0
VALIDATION_FAILED = 2
INVALID_REQUEST = 3
MALFORMED = 4

REGISTER_NAME = "data_source_audit.md"
SCHEMA_VERSION = "1.0"
SOURCE_ID_PATTERN = re.compile(r"^DS-[0-9]{4}$")
DATE_PATTERN = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
SOURCE_REF_PATTERN = re.compile(r"\bDS-[0-9]{4}\b")
SOURCE_TIERS = {
    "tier_1_official",
    "tier_2_institutional",
    "tier_3_media",
    "tier_4_untrusted",
}
APPROVAL_STATUSES = {
    "unknown",
    "candidate",
    "approved",
    "approved_with_caveats",
    "explicitly_approved",
    "blocked",
    "restricted",
    "deprecated",
}
LEGACY_STATUS_ALIASES = {
    "available": "approved",
    "usable_with_caveats": "approved_with_caveats",
}
STATUSES = APPROVAL_STATUSES | set(LEGACY_STATUS_ALIASES)
EXPERIMENT_READY_STATUSES = {"approved", "approved_with_caveats"}
HIGH_IMPACT_TIERS = {"tier_1_official", "tier_2_institutional"}
FIELDS = [
    "source_id",
    "source_name",
    "url_or_domain",
    "publisher_owner",
    "source_tier",
    "approval_status",
    "approved_use_cases",
    "blocked_use_cases",
    "freshness_window_days",
    "known_limitations",
    "citation_requirements",
    "last_reviewed",
    "approved_by",
    "review_notes",
]
NEW_SOURCE_REQUIRED_FIELDS = {
    "source_name": "--source-name",
    "url_or_domain": "--url-or-domain",
    "publisher_owner": "--publisher-owner",
}
LEGACY_FIELDS = [
    "source_id",
    "status",
    "name",
    "location",
    "owner",
    "last_checked",
    "readiness_notes",
]


def iso_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def audit_path(ops_dir: Path) -> Path:
    return ops_dir / REGISTER_NAME


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def clean_cell(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    return text.replace("\n", " ").replace("|", "/")


def empty_register_text() -> str:
    header = [
        "# Data Source Audit Register",
        "",
        f"Schema version: {SCHEMA_VERSION}",
        "",
        "| " + " | ".join(FIELDS) + " |",
        "| " + " | ".join("---" for _ in FIELDS) + " |",
    ]
    return "\n".join(header) + "\n"


def normalize_approval_status(value: str) -> str:
    text = str(value or "").strip()
    return LEGACY_STATUS_ALIASES.get(text, text)


def canonical_row(row: dict[str, str]) -> dict[str, str]:
    approval_status = normalize_approval_status(row.get("approval_status") or row.get("status") or "unknown")
    source_name = row.get("source_name") or row.get("name") or ""
    url_or_domain = row.get("url_or_domain") or row.get("location") or ""
    publisher_owner = row.get("publisher_owner") or row.get("owner") or ""
    last_reviewed = row.get("last_reviewed") or row.get("last_checked") or ""
    review_notes = row.get("review_notes") or row.get("readiness_notes") or ""
    approved_use_cases = row.get("approved_use_cases") or "none"
    blocked_use_cases = row.get("blocked_use_cases") or "none"
    known_limitations = row.get("known_limitations") or review_notes or "none recorded"
    citation_requirements = row.get("citation_requirements") or "cite source id and source URL/domain"
    approved_by = row.get("approved_by") or ("research_ops" if approval_status in EXPERIMENT_READY_STATUSES else "none")
    source_tier = row.get("source_tier") or "tier_4_untrusted"
    freshness_window_days = row.get("freshness_window_days") or "90"

    canonical = {
        "source_id": row.get("source_id", ""),
        "source_name": source_name,
        "url_or_domain": url_or_domain,
        "publisher_owner": publisher_owner,
        "source_tier": source_tier,
        "approval_status": approval_status,
        "approved_use_cases": approved_use_cases,
        "blocked_use_cases": blocked_use_cases,
        "freshness_window_days": freshness_window_days,
        "known_limitations": known_limitations,
        "citation_requirements": citation_requirements,
        "last_reviewed": last_reviewed,
        "approved_by": approved_by,
        "review_notes": review_notes,
    }
    # Backward-compatible aliases for existing helpers.
    canonical["status"] = canonical["approval_status"]
    canonical["name"] = canonical["source_name"]
    canonical["location"] = canonical["url_or_domain"]
    canonical["owner"] = canonical["publisher_owner"]
    canonical["last_checked"] = canonical["last_reviewed"]
    canonical["readiness_notes"] = canonical["review_notes"]
    return canonical


def format_rows(rows: list[dict[str, str]]) -> str:
    lines = empty_register_text().rstrip("\n").splitlines()
    for row in sorted((canonical_row(item) for item in rows), key=lambda item: item["source_id"]):
        cells = [clean_cell(row.get(field, "")) for field in FIELDS]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def split_table_row(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return []
    return [cell.strip() for cell in stripped.strip("|").split("|")]


def parse_register(path: Path) -> tuple[str, list[dict[str, str]]]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ValueError(f"data source audit register not found: {path}") from exc
    except OSError as exc:
        raise ValueError(f"cannot read data source audit register {path}: {exc}") from exc

    schema_version = ""
    for line in text.splitlines():
        if line.lower().startswith("schema version:"):
            schema_version = line.split(":", 1)[1].strip()
            break

    rows: list[dict[str, str]] = []
    in_table = False
    table_fields = FIELDS
    for line in text.splitlines():
        cells = split_table_row(line)
        if not cells:
            if in_table:
                break
            continue
        normalized = [cell.lower() for cell in cells]
        if normalized in (FIELDS, LEGACY_FIELDS):
            table_fields = normalized
            in_table = True
            continue
        if in_table and all(set(cell) <= {"-", ":", " "} for cell in cells):
            continue
        if in_table:
            if len(cells) != len(table_fields):
                raise ValueError(f"malformed data source audit row with {len(cells)} cells: {line}")
            rows.append(canonical_row(dict(zip(table_fields, cells))))

    if not schema_version:
        raise ValueError("data source audit register is missing Schema version")
    if not in_table:
        raise ValueError("data source audit register is missing the required markdown table")
    return schema_version, rows


def validate_rows(schema_version: str, rows: list[dict[str, str]]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if schema_version != SCHEMA_VERSION:
        errors.append({"path": "$.schema_version", "message": f"expected {SCHEMA_VERSION}, got {schema_version!r}"})

    seen: set[str] = set()
    for index, row in enumerate(rows, start=1):
        prefix = f"$.rows[{index}]"
        source_id = row.get("source_id", "")
        approval_status = normalize_approval_status(row.get("approval_status", ""))
        source_tier = row.get("source_tier", "")
        if SOURCE_ID_PATTERN.match(source_id) is None:
            errors.append({"path": f"{prefix}.source_id", "message": "source_id must match DS-0000"})
        elif source_id in seen:
            errors.append({"path": f"{prefix}.source_id", "message": f"duplicate source_id {source_id}"})
        seen.add(source_id)

        if approval_status not in APPROVAL_STATUSES:
            errors.append({"path": f"{prefix}.approval_status", "message": f"approval_status {approval_status!r} is not allowed"})
        if source_tier not in SOURCE_TIERS:
            errors.append({"path": f"{prefix}.source_tier", "message": f"source_tier {source_tier!r} is not allowed"})
        for required in FIELDS:
            if not row.get(required, "").strip():
                errors.append({"path": f"{prefix}.{required}", "message": "required field missing"})
        if row.get("last_reviewed") and DATE_PATTERN.match(row["last_reviewed"]) is None:
            errors.append({"path": f"{prefix}.last_reviewed", "message": "last_reviewed must use YYYY-MM-DD"})
        try:
            freshness = int(str(row.get("freshness_window_days", "")).strip())
        except ValueError:
            freshness = 0
        if freshness <= 0:
            errors.append({"path": f"{prefix}.freshness_window_days", "message": "freshness_window_days must be a positive integer"})
        if approval_status in EXPERIMENT_READY_STATUSES and not row.get("approved_by", "").strip():
            errors.append({"path": f"{prefix}.approved_by", "message": "approved sources must record approved_by"})
    return errors


def load_valid_register(ops_dir: Path) -> tuple[Path, list[dict[str, str]]]:
    path = audit_path(ops_dir)
    schema_version, rows = parse_register(path)
    errors = validate_rows(schema_version, rows)
    if errors:
        first = errors[0]
        raise ValueError(f"{first['path']}: {first['message']}")
    return path, rows


def row_map(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    return {row["source_id"]: canonical_row(row) for row in rows}


def extract_source_refs(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ValueError(f"experiment plan not found: {path}") from exc
    except OSError as exc:
        raise ValueError(f"cannot read experiment plan {path}: {exc}") from exc
    refs = sorted(set(SOURCE_REF_PATTERN.findall(text)))
    return refs


def parse_date(value: str) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def source_age_days(row: dict[str, str], now: datetime) -> Optional[float]:
    reviewed = parse_date(row.get("last_reviewed", ""))
    if reviewed is None:
        return None
    return round((now - reviewed).total_seconds() / 86400, 1)


def freshness_window(row: dict[str, str]) -> int:
    try:
        return int(str(row.get("freshness_window_days", "0")).strip())
    except ValueError:
        return 0


def source_stale(row: dict[str, str], now: datetime) -> bool:
    age = source_age_days(row, now)
    window = freshness_window(row)
    return age is None or window <= 0 or age > window


def use_case_tokens(value: str) -> set[str]:
    tokens = {
        token.strip().lower()
        for token in re.split(r"[;,]", str(value or ""))
        if token.strip()
    }
    return set() if tokens == {"none"} else tokens


def decision(
    source_id: str,
    allowed: bool,
    severity: str,
    reason: str,
    row: Optional[dict[str, str]] = None,
    action: str = "inspect data_source_audit.md",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "source_id": source_id,
        "allowed": allowed,
        "severity": severity,
        "reason": reason,
        "action": action,
    }
    if row is not None:
        payload.update(
            {
                "source_name": row.get("source_name"),
                "source_tier": row.get("source_tier"),
                "approval_status": row.get("approval_status"),
                "approved_use_cases": row.get("approved_use_cases"),
                "blocked_use_cases": row.get("blocked_use_cases"),
                "freshness_window_days": row.get("freshness_window_days"),
                "last_reviewed": row.get("last_reviewed"),
                "citation_requirements": row.get("citation_requirements"),
            }
        )
    return payload


def source_governance_report(ops_dir: Path, now: Optional[datetime] = None) -> dict[str, Any]:
    current = now or datetime.now(timezone.utc)
    path = audit_path(ops_dir)
    try:
        schema_version, rows = parse_register(path)
    except ValueError as exc:
        return {
            "ok": False,
            "audit_register": str(path),
            "error_count": 1,
            "errors": [{"reason": "malformed_register", "message": str(exc)}],
            "warning_count": 0,
            "warnings": [],
        }
    errors = validate_rows(schema_version, rows)
    tier_counts: dict[str, int] = {tier: 0 for tier in sorted(SOURCE_TIERS)}
    approval_counts: dict[str, int] = {status: 0 for status in sorted(APPROVAL_STATUSES)}
    stale_sources: list[dict[str, Any]] = []
    for row in rows:
        tier_counts[row["source_tier"]] = tier_counts.get(row["source_tier"], 0) + 1
        approval_counts[row["approval_status"]] = approval_counts.get(row["approval_status"], 0) + 1
        if source_stale(row, current):
            stale_sources.append(
                {
                    "source_id": row["source_id"],
                    "source_name": row["source_name"],
                    "source_tier": row["source_tier"],
                    "approval_status": row["approval_status"],
                    "last_reviewed": row["last_reviewed"],
                    "age_days": source_age_days(row, current),
                    "freshness_window_days": freshness_window(row),
                }
            )
    warnings = [
        {
            "reason": "source_freshness_warning",
            "message": f"{len(stale_sources)} source(s) are past freshness window",
            "sources": stale_sources,
        }
    ] if stale_sources else []
    return {
        "ok": not errors,
        "audit_register": str(path),
        "source_count": len(rows),
        "error_count": len(errors),
        "errors": errors,
        "warning_count": len(warnings),
        "warnings": warnings,
        "stale_sources": stale_sources,
        "tier_counts": dict(sorted(tier_counts.items())),
        "approval_counts": dict(sorted(approval_counts.items())),
    }


def assess_source_refs(
    ops_dir: Path,
    refs: list[str],
    use_case: str,
    claim_impact: str,
    now: Optional[datetime] = None,
    allow_tier4_explicit: bool = False,
) -> dict[str, Any]:
    current = now or datetime.now(timezone.utc)
    try:
        path, rows = load_valid_register(ops_dir)
    except ValueError as exc:
        return {
            "ok": False,
            "reason": "audit_check_failed",
            "audit_register": str(audit_path(ops_dir)),
            "blocked": [{"reason": str(exc)}],
            "warnings": [],
            "source_decisions": [],
        }

    by_id = row_map(rows)
    decisions: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    supporting_tier_1_or_2 = False

    for ref in refs:
        row = by_id.get(ref)
        if row is None:
            item = decision(ref, False, "error", "source_id is missing from data_source_audit.md", action="create or approve the source before use")
            decisions.append(item)
            blocked.append(item)
            continue

        approval_status = row["approval_status"]
        source_tier = row["source_tier"]
        approved_use_cases = use_case_tokens(row.get("approved_use_cases", ""))
        blocked_use_cases = use_case_tokens(row.get("blocked_use_cases", ""))
        if source_tier in HIGH_IMPACT_TIERS and approval_status in EXPERIMENT_READY_STATUSES:
            supporting_tier_1_or_2 = True

        if approval_status not in EXPERIMENT_READY_STATUSES and not (allow_tier4_explicit and approval_status == "explicitly_approved"):
            item = decision(ref, False, "error", f"approval_status {approval_status} is not approved for {use_case}", row, "approve or replace the source")
            decisions.append(item)
            blocked.append(item)
            continue

        if "all" in blocked_use_cases or use_case in blocked_use_cases:
            item = decision(ref, False, "error", f"use case {use_case} is blocked for this source", row, "choose an approved source or update the audit decision")
            decisions.append(item)
            blocked.append(item)
            continue

        if "all" not in approved_use_cases and use_case not in approved_use_cases:
            item = decision(ref, False, "error", f"use case {use_case} is not listed in approved_use_cases", row, "approve this use case or choose another source")
            decisions.append(item)
            blocked.append(item)
            continue

        if source_tier == "tier_4_untrusted" and not (allow_tier4_explicit and approval_status == "explicitly_approved"):
            item = decision(ref, False, "error", "tier_4_untrusted is blocked without explicit human approval", row, "replace with tier 1/2 support or log explicit approval")
            decisions.append(item)
            blocked.append(item)
            continue

        if source_tier == "tier_3_media" and use_case in {"experiment_planning", "accepted_evidence"}:
            item = decision(ref, True, "warning", "tier_3_media may provide context but cannot independently justify promotion", row, "pair with tier 1 or tier 2 support")
            decisions.append(item)
            warnings.append(item)
        else:
            decisions.append(decision(ref, True, "ok", "source is approved for this use", row, "cite source id and limitations"))

        if source_stale(row, current):
            stale = decision(
                ref,
                claim_impact not in {"high"} and use_case not in {"experiment_planning", "accepted_evidence"},
                "error" if claim_impact == "high" or use_case in {"experiment_planning", "accepted_evidence"} else "warning",
                "source freshness window has expired",
                row,
                "refresh source review or log human stale-use approval",
            )
            if stale["allowed"]:
                warnings.append(stale)
            else:
                blocked.append(stale)

    if claim_impact == "high" and not supporting_tier_1_or_2:
        item = decision(
            "claim",
            False,
            "error",
            "high-impact claims require at least one tier_1_official or tier_2_institutional approved source",
            action="add tier 1/2 support or lower the claim impact",
        )
        blocked.append(item)
        decisions.append(item)

    if use_case in {"experiment_planning", "accepted_evidence"}:
        approved_support = [
            item for item in decisions
            if item.get("allowed") is True and item.get("source_tier") in HIGH_IMPACT_TIERS
        ]
        contextual_only = [
            item for item in decisions
            if item.get("allowed") is True and item.get("source_tier") == "tier_3_media"
        ]
        if contextual_only and not approved_support:
            item = decision(
                "claim",
                False,
                "error",
                "tier_3_media sources cannot independently justify promotion or accepted evidence",
                action="add tier 1/2 support",
            )
            blocked.append(item)
            decisions.append(item)

    return {
        "ok": not blocked,
        "reason": "sources_allowed" if not blocked else "source_governance_blocked",
        "audit_register": str(path),
        "use_case": use_case,
        "claim_impact": claim_impact,
        "source_refs": refs,
        "blocked": blocked,
        "warnings": warnings,
        "source_decisions": decisions,
    }


def cmd_init(args: argparse.Namespace) -> int:
    path = audit_path(args.ops_dir)
    if path.exists() and not args.force:
        print_json({"ok": True, "action": "exists", "path": str(path)})
        return SUCCESS
    atomic_write_text(path, empty_register_text())
    print_json({"ok": True, "action": "initialized", "path": str(path)})
    return SUCCESS


def cmd_upsert(args: argparse.Namespace) -> int:
    path = audit_path(args.ops_dir)
    if not path.exists():
        atomic_write_text(path, empty_register_text())

    try:
        schema_version, rows = parse_register(path)
    except ValueError as exc:
        print_json({"ok": False, "reason": "malformed_register", "error": str(exc), "path": str(path)})
        return MALFORMED

    existing_errors = validate_rows(schema_version, rows)
    if existing_errors:
        print_json({"ok": False, "reason": "audit_validation_failed", "errors": existing_errors, "path": str(path)})
        return VALIDATION_FAILED

    current = row_map(rows)
    source_id = args.source_id
    new_source = source_id not in current
    row = current.get(
        source_id,
        {
            "source_id": source_id,
            "source_name": "",
            "url_or_domain": "",
            "publisher_owner": "",
            "source_tier": "tier_4_untrusted",
            "approval_status": "unknown",
            "approved_use_cases": "none",
            "blocked_use_cases": "none",
            "freshness_window_days": "90",
            "known_limitations": "none recorded",
            "citation_requirements": "cite source id and source URL/domain",
            "last_reviewed": iso_date(),
            "approved_by": "none",
            "review_notes": "none",
        },
    )
    updates = {
        "source_name": args.source_name,
        "url_or_domain": args.url_or_domain,
        "publisher_owner": args.publisher_owner,
        "source_tier": args.source_tier,
        "approval_status": args.approval_status or args.status,
        "approved_use_cases": args.approved_use_cases,
        "blocked_use_cases": args.blocked_use_cases,
        "freshness_window_days": args.freshness_window_days,
        "known_limitations": args.known_limitations,
        "citation_requirements": args.citation_requirements,
        "last_reviewed": args.last_reviewed,
        "approved_by": args.approved_by,
        "review_notes": args.review_notes,
    }
    for key, value in updates.items():
        if value is not None:
            row[key] = clean_cell(value)
    row = canonical_row(row)
    if not row.get("last_reviewed"):
        row["last_reviewed"] = iso_date()
    current[source_id] = row
    next_rows = list(current.values())

    errors = validate_rows(schema_version, next_rows)
    if errors:
        payload = {"ok": False, "reason": "audit_validation_failed", "errors": errors, "path": str(path)}
        if new_source:
            missing_new_source_fields = [
                flag for field, flag in NEW_SOURCE_REQUIRED_FIELDS.items() if not str(row.get(field, "")).strip()
            ]
            if missing_new_source_fields:
                payload.update(
                    {
                        "required_for_new_source": missing_new_source_fields,
                        "next_step": (
                            "rerun source upsert with --source-name, --url-or-domain, and --publisher-owner; "
                            "omitted governance fields use conservative defaults"
                        ),
                    }
                )
        print_json(payload)
        return VALIDATION_FAILED

    atomic_write_text(path, format_rows(next_rows))
    print_json({"ok": True, "action": "upserted", "source_id": source_id, "approval_status": row["approval_status"], "path": str(path)})
    return SUCCESS


def cmd_validate(args: argparse.Namespace) -> int:
    path = audit_path(args.ops_dir)
    try:
        schema_version, rows = parse_register(path)
    except ValueError as exc:
        print_json({"ok": False, "reason": "malformed_register", "error": str(exc), "path": str(path)})
        return MALFORMED

    errors = validate_rows(schema_version, rows)
    if errors:
        print_json({"ok": False, "reason": "audit_validation_failed", "errors": errors, "path": str(path)})
        return VALIDATION_FAILED

    counts: dict[str, int] = {status: 0 for status in sorted(APPROVAL_STATUSES)}
    tier_counts: dict[str, int] = {tier: 0 for tier in sorted(SOURCE_TIERS)}
    for row in rows:
        counts[row["approval_status"]] += 1
        tier_counts[row["source_tier"]] += 1
    print_json({"ok": True, "path": str(path), "source_count": len(rows), "approval_status_counts": counts, "tier_counts": tier_counts})
    return SUCCESS


def cmd_check_experiment(args: argparse.Namespace) -> int:
    try:
        refs = extract_source_refs(args.experiment_plan)
    except ValueError as exc:
        print_json({"ok": False, "reason": "audit_check_failed", "error": str(exc)})
        return MALFORMED

    if not refs:
        print_json(
            {
                "ok": False,
                "reason": "missing_data_audit_refs",
                "experiment_plan": str(args.experiment_plan),
                "audit_register": str(audit_path(args.ops_dir)),
            }
        )
        return VALIDATION_FAILED

    assessed = assess_source_refs(
        args.ops_dir,
        refs,
        use_case="experiment_planning",
        claim_impact=args.claim_impact,
    )
    if not assessed["ok"]:
        print_json({"ok": False, "experiment_plan": str(args.experiment_plan), **assessed})
        return VALIDATION_FAILED

    print_json(
        {
            "ok": True,
            "experiment_plan": str(args.experiment_plan),
            "audit_register": assessed["audit_register"],
            "data_audit_refs": refs,
            "warnings": assessed["warnings"],
            "source_decisions": assessed["source_decisions"],
        }
    )
    return SUCCESS


def cmd_check_claim(args: argparse.Namespace) -> int:
    try:
        refs = extract_source_refs(args.artifact)
    except ValueError as exc:
        print_json({"ok": False, "reason": "artifact_check_failed", "error": str(exc)})
        return MALFORMED
    if not refs:
        print_json({"ok": False, "reason": "missing_data_audit_refs", "artifact": str(args.artifact)})
        return VALIDATION_FAILED
    assessed = assess_source_refs(
        args.ops_dir,
        refs,
        use_case=args.use_case,
        claim_impact=args.claim_impact,
        allow_tier4_explicit=args.allow_tier4_explicit,
    )
    print_json({"ok": assessed["ok"], "artifact": str(args.artifact), **assessed})
    return SUCCESS if assessed["ok"] else VALIDATION_FAILED


def cmd_explain(args: argparse.Namespace) -> int:
    assessed = assess_source_refs(
        args.ops_dir,
        [args.source_id],
        use_case=args.use_case,
        claim_impact=args.claim_impact,
        allow_tier4_explicit=args.allow_tier4_explicit,
    )
    print_json({"ok": assessed["ok"], "source_id": args.source_id, **assessed})
    return SUCCESS if assessed["ok"] else VALIDATION_FAILED


def cmd_freshness(args: argparse.Namespace) -> int:
    now = parse_date(args.now) if args.now else datetime.now(timezone.utc)
    if now is None:
        print_json({"ok": False, "reason": "invalid_now", "now": args.now})
        return INVALID_REQUEST
    report = source_governance_report(args.ops_dir, now)
    print_json(report)
    return SUCCESS if report.get("ok") else VALIDATION_FAILED


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Maintain the data source audit register.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="Create research_ops/data_source_audit.md if needed")
    init.add_argument("ops_dir", type=Path)
    init.add_argument("--force", action="store_true")
    init.set_defaults(func=cmd_init)

    upsert = subparsers.add_parser(
        "upsert",
        help="Add or update a data source audit entry",
        epilog="New source rows require --source-name, --url-or-domain, and --publisher-owner.",
    )
    upsert.add_argument("ops_dir", type=Path)
    upsert.add_argument("--source-id", required=True)
    upsert.add_argument("--status", choices=sorted(STATUSES), help="Deprecated alias for --approval-status.")
    upsert.add_argument("--approval-status", choices=sorted(APPROVAL_STATUSES))
    upsert.add_argument("--name", "--source-name", dest="source_name")
    upsert.add_argument("--location", "--url-or-domain", dest="url_or_domain")
    upsert.add_argument("--owner", "--publisher-owner", dest="publisher_owner")
    upsert.add_argument("--source-tier", choices=sorted(SOURCE_TIERS))
    upsert.add_argument("--approved-use-cases")
    upsert.add_argument("--blocked-use-cases")
    upsert.add_argument("--freshness-window-days")
    upsert.add_argument("--known-limitations")
    upsert.add_argument("--citation-requirements")
    upsert.add_argument("--last-checked", "--last-reviewed", dest="last_reviewed")
    upsert.add_argument("--approved-by")
    upsert.add_argument("--readiness-notes", "--review-notes", dest="review_notes")
    upsert.set_defaults(func=cmd_upsert)

    validate = subparsers.add_parser("validate", help="Validate the audit register")
    validate.add_argument("ops_dir", type=Path)
    validate.set_defaults(func=cmd_validate)

    check = subparsers.add_parser("check-experiment", help="Verify an experiment plan references ready audit entries")
    check.add_argument("ops_dir", type=Path)
    check.add_argument("experiment_plan", type=Path)
    check.add_argument("--claim-impact", choices=["low", "medium", "high"], default="medium")
    check.set_defaults(func=cmd_check_experiment)

    claim = subparsers.add_parser("check-claim", help="Verify an artifact cites allowed sources for claim use.")
    claim.add_argument("ops_dir", type=Path)
    claim.add_argument("artifact", type=Path)
    claim.add_argument("--use-case", choices=["discovery", "experiment_planning", "accepted_evidence", "context"], default="accepted_evidence")
    claim.add_argument("--claim-impact", choices=["low", "medium", "high"], default="medium")
    claim.add_argument("--allow-tier4-explicit", action="store_true")
    claim.set_defaults(func=cmd_check_claim)

    explain = subparsers.add_parser("explain", help="Explain why one source is allowed or blocked.")
    explain.add_argument("ops_dir", type=Path)
    explain.add_argument("source_id")
    explain.add_argument("--use-case", choices=["discovery", "experiment_planning", "accepted_evidence", "context"], default="experiment_planning")
    explain.add_argument("--claim-impact", choices=["low", "medium", "high"], default="medium")
    explain.add_argument("--allow-tier4-explicit", action="store_true")
    explain.set_defaults(func=cmd_explain)

    freshness = subparsers.add_parser("freshness-report", help="Report source governance and freshness warnings.")
    freshness.add_argument("ops_dir", type=Path)
    freshness.add_argument("--now")
    freshness.set_defaults(func=cmd_freshness)

    return parser.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    if hasattr(args, "source_id") and SOURCE_ID_PATTERN.match(args.source_id) is None:
        print_json({"ok": False, "reason": "invalid_source_id", "source_id": args.source_id})
        return INVALID_REQUEST
    if hasattr(args, "last_reviewed") and args.last_reviewed is not None and DATE_PATTERN.match(args.last_reviewed) is None:
        print_json({"ok": False, "reason": "invalid_last_reviewed", "last_reviewed": args.last_reviewed})
        return INVALID_REQUEST
    if hasattr(args, "freshness_window_days") and args.freshness_window_days is not None:
        try:
            freshness = int(args.freshness_window_days)
        except ValueError:
            freshness = 0
        if freshness <= 0:
            print_json({"ok": False, "reason": "invalid_freshness_window_days", "freshness_window_days": args.freshness_window_days})
            return INVALID_REQUEST
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
