#!/usr/bin/env python3
"""Guarded apply helpers for reviewed foundation update proposals."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import socket
from datetime import datetime, timezone
from typing import Any, Iterable

from async_research_workflow.scripts import data_foundations
from async_research_workflow.scripts import data_proposal_inspection
from async_research_workflow.scripts import data_source_audit
from async_research_workflow.scripts import foundation_proposals
from async_research_workflow.scripts import knowledge_library
from async_research_workflow.scripts import library_proposal_inspection
from async_research_workflow.scripts import validate_result_acceptance
from async_research_workflow.proposals import engine as proposal_engine


SUCCESS = 0
VALIDATION_FAILED = 2
INVALID_REQUEST = 3
MALFORMED = 4

TARGETS = {"data", "library"}
ACCEPTED_ROUTES = {"accept_as_evidence", "accept_negative_result"}
TASK_ID_PREFIX_RE = re.compile(r"^(TASK-[0-9]{4})")
PROFILE_FIELD_RE = re.compile(r"^(\s*(?:-\s*)?)([A-Za-z][A-Za-z0-9_]*)(\s*:\s*)(.*)$")

DATA_TABLES = {
    "upsert_data_catalog_row": ("data/data_catalog.md", "source_id"),
    "upsert_data_access_row": ("data/data_access.md", "source_id"),
    "upsert_join_map_row": ("data/join_map.md", "join_id"),
    "upsert_known_data_gap": ("data/known_data_gaps.md", "gap_id"),
}
LIBRARY_TABLES = library_proposal_inspection.LIBRARY_TARGET_TABLES
LIBRARY_APPEND_OPERATIONS = {"append_library_update_log"}


class ApplyError(RuntimeError):
    def __init__(self, payload: dict[str, Any], code: int = MALFORMED):
        super().__init__(str(payload.get("reason", "foundation_apply_failed")))
        self.payload = payload
        self.code = code


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
    except ValueError:
        return False
    return True


def clean_cell(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    return " ".join(text.split()).replace("|", "/")


def write_text_atomic(path: Path, text: str) -> bool:
    existing = path.read_text(encoding="utf-8") if path.exists() else None
    if existing == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
    return True


def file_sha256(path: Path) -> str | None:
    return proposal_engine.file_sha256(path)


def split_table_row(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return []
    return [cell.strip().replace("\\|", "|") for cell in stripped.strip("|").split("|")]


def is_separator(cells: list[str]) -> bool:
    return bool(cells) and all(cell and set(cell) <= {"-", ":", " "} for cell in cells)


def render_table(headers: list[str], rows: list[dict[str, Any]]) -> list[str]:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _header in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(clean_cell(row.get(header, "")) for header in headers) + " |")
    return lines


def join_document(lines: list[str], final_newline: bool = True) -> str:
    text = "\n".join(lines)
    if final_newline:
        text += "\n"
    return text


def parse_first_table(path: Path) -> tuple[list[str], list[str], list[dict[str, str]], list[str]]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    header_index: int | None = None
    headers: list[str] = []
    for index, line in enumerate(lines):
        cells = split_table_row(line)
        if not cells:
            continue
        if index + 1 >= len(lines):
            continue
        separator = split_table_row(lines[index + 1])
        if not is_separator(separator):
            continue
        header_index = index
        headers = [cell.strip().lower() for cell in cells]
        break
    if header_index is None:
        raise ApplyError(
            {
                "ok": False,
                "reason": "markdown_table_missing",
                "path": str(path),
                "message": "target file does not contain a writable Markdown table",
            }
        )
    row_start = header_index + 2
    row_end = row_start
    rows: list[dict[str, str]] = []
    while row_end < len(lines):
        cells = split_table_row(lines[row_end])
        if not cells:
            break
        if len(cells) != len(headers):
            raise ApplyError(
                {
                    "ok": False,
                    "reason": "malformed_markdown_table_row",
                    "path": str(path),
                    "line": row_end + 1,
                    "message": "target table row width does not match header width",
                }
            )
        rows.append(dict(zip(headers, cells)))
        row_end += 1
    return lines[:header_index], headers, rows, lines[row_end:]


def replace_first_table(path: Path, headers: list[str], rows: list[dict[str, Any]]) -> bool:
    prefix, _old_headers, _old_rows, suffix = parse_first_table(path)
    return write_text_atomic(path, join_document(prefix + render_table(headers, rows) + suffix))


def upsert_rows(
    rows: list[dict[str, Any]],
    key_field: str,
    payload: dict[str, Any],
    *,
    row_id: str | None = None,
) -> tuple[list[dict[str, Any]], str]:
    key_value = clean_cell(payload.get(key_field) or row_id)
    if not key_value:
        raise ApplyError(
            {
                "ok": False,
                "reason": "row_key_missing",
                "message": f"payload must include {key_field}",
                "field": key_field,
            },
            VALIDATION_FAILED,
        )
    next_rows = [dict(row) for row in rows]
    next_row = dict(payload)
    next_row[key_field] = key_value
    for index, row in enumerate(next_rows):
        if clean_cell(row.get(key_field)) == key_value:
            if {key: clean_cell(value) for key, value in row.items()} == {
                key: clean_cell(value) for key, value in next_row.items()
            }:
                return next_rows, "unchanged"
            next_rows[index] = next_row
            return next_rows, "updated"
    next_rows.append(next_row)
    return next_rows, "inserted"


def write_data_table_operation(ops_dir: Path, operation: dict[str, Any]) -> dict[str, Any]:
    operation_name = str(operation["operation"])
    relative, key_field = DATA_TABLES[operation_name]
    path = ops_dir / relative
    prefix, headers, rows, suffix = parse_first_table(path)
    if key_field not in headers:
        raise ApplyError(
            {
                "ok": False,
                "reason": "target_key_field_missing",
                "path": str(path),
                "field": key_field,
            },
            VALIDATION_FAILED,
        )
    next_rows, action = upsert_rows(
        rows,
        key_field,
        operation["payload"],
        row_id=str(operation["row_id"]),
    )
    changed = write_text_atomic(path, join_document(prefix + render_table(headers, next_rows) + suffix))
    return {
        "path": str(path),
        "target_path": relative,
        "operation_id": operation["operation_id"],
        "operation": operation_name,
        "row_id": operation["row_id"],
        "action": action,
        "changed": changed,
    }


def write_data_source_operation(ops_dir: Path, operation: dict[str, Any]) -> dict[str, Any]:
    path = ops_dir / data_source_audit.REGISTER_NAME
    _schema_version, rows = data_source_audit.parse_register(path)
    current = data_source_audit.row_map(rows)
    row_id = str(operation["row_id"])
    payload = {key: clean_cell(value) for key, value in operation["payload"].items()}
    payload["source_id"] = row_id
    row = data_source_audit.canonical_row({**current.get(row_id, {}), **payload})
    optional_fields = data_source_audit.declared_optional_fields(path)
    for field in optional_fields:
        row.setdefault(field, "")
    current[row_id] = row
    next_rows = sorted((data_source_audit.canonical_row(item) for item in current.values()), key=lambda item: item["source_id"])
    headers = data_source_audit.FIELDS + [
        field for field in data_source_audit.OPTIONAL_FIELDS if field in optional_fields or any(field in item for item in next_rows)
    ]
    changed = replace_first_table(path, headers, next_rows)
    return {
        "path": str(path),
        "target_path": data_source_audit.REGISTER_NAME,
        "operation_id": operation["operation_id"],
        "operation": operation["operation"],
        "row_id": row_id,
        "action": "upserted",
        "changed": changed,
    }


def profile_fields(row_id: str, payload: dict[str, Any]) -> dict[str, str]:
    source_name = clean_cell(payload.get("source_name") or payload.get("name") or row_id)
    return {
        "source_id": row_id,
        "source_name": source_name,
        "profile_status": clean_cell(payload.get("profile_status") or "reviewed"),
        "audit_register": clean_cell(payload.get("audit_register") or "../../data_source_audit.md"),
        "audit_status": clean_cell(payload.get("audit_status") or payload.get("approval_status") or "candidate"),
        "reviewed_date": clean_cell(payload.get("reviewed_date") or payload.get("last_reviewed") or datetime.now(timezone.utc).date().isoformat()),
        "reviewer": clean_cell(payload.get("reviewer") or payload.get("approved_by") or "proposal_apply"),
        "location": clean_cell(payload.get("location") or payload.get("url_or_domain")),
        "access_method": clean_cell(payload.get("access_method")),
        "access_notes": clean_cell(payload.get("access_notes")),
        "owner_or_publisher": clean_cell(payload.get("owner_or_publisher") or payload.get("publisher_owner")),
        "contact_or_docs": clean_cell(payload.get("contact_or_docs")),
        "approved_use_cases": clean_cell(payload.get("approved_use_cases") or "none"),
        "blocked_use_cases": clean_cell(payload.get("blocked_use_cases") or "none"),
        "privacy_or_licensing_restrictions": clean_cell(payload.get("privacy_or_licensing_restrictions") or payload.get("known_limitations") or "none recorded"),
        "fields": clean_cell(payload.get("fields")),
        "grain": clean_cell(payload.get("grain")),
        "geography": clean_cell(payload.get("geography")),
        "time_coverage": clean_cell(payload.get("time_coverage")),
        "refresh_cadence": clean_cell(payload.get("refresh_cadence")),
        "known_limitations": clean_cell(payload.get("known_limitations") or "none recorded"),
        "missingness_or_bias_risks": clean_cell(payload.get("missingness_or_bias_risks")),
        "freshness_notes": clean_cell(payload.get("freshness_notes")),
        "join_keys": clean_cell(payload.get("join_keys")),
        "plausible_joins": clean_cell(payload.get("plausible_joins")),
        "join_risks": clean_cell(payload.get("join_risks")),
        "readiness_summary": clean_cell(payload.get("readiness_summary") or payload.get("review_notes") or "reviewed proposal update"),
        "recommended_next_task": clean_cell(payload.get("recommended_next_task") or "none"),
        "kill_reason_if_unusable": clean_cell(payload.get("kill_reason_if_unusable") or "none recorded"),
    }


def render_new_profile(row_id: str, payload: dict[str, Any]) -> str:
    fields = profile_fields(row_id, payload)
    title = fields["source_name"] or row_id
    sections = [
        f"# {row_id}: {title}",
        "",
        f"source_id: {fields['source_id']}",
        f"source_name: {fields['source_name']}",
        f"profile_status: {fields['profile_status']}",
        f"audit_register: {fields['audit_register']}",
        f"audit_status: {fields['audit_status']}",
        f"reviewed_date: {fields['reviewed_date']}",
        f"reviewer: {fields['reviewer']}",
        "",
        "## Location And Access",
        "",
        f"- location: {fields['location']}",
        f"- access_method: {fields['access_method']}",
        f"- access_notes: {fields['access_notes']}",
        "",
        "## Owner Or Publisher",
        "",
        f"- owner_or_publisher: {fields['owner_or_publisher']}",
        f"- contact_or_docs: {fields['contact_or_docs']}",
        "",
        "## Use Policy",
        "",
        f"- approved_use_cases: {fields['approved_use_cases']}",
        f"- blocked_use_cases: {fields['blocked_use_cases']}",
        f"- privacy_or_licensing_restrictions: {fields['privacy_or_licensing_restrictions']}",
        "",
        "## Coverage And Grain",
        "",
        f"- fields: {fields['fields']}",
        f"- grain: {fields['grain']}",
        f"- geography: {fields['geography']}",
        f"- time_coverage: {fields['time_coverage']}",
        f"- refresh_cadence: {fields['refresh_cadence']}",
        "",
        "## Quality And Limitations",
        "",
        f"- known_limitations: {fields['known_limitations']}",
        f"- missingness_or_bias_risks: {fields['missingness_or_bias_risks']}",
        f"- freshness_notes: {fields['freshness_notes']}",
        "",
        "## Join Keys And Risks",
        "",
        f"- join_keys: {fields['join_keys']}",
        f"- plausible_joins: {fields['plausible_joins']}",
        f"- join_risks: {fields['join_risks']}",
        "",
        "## Review Notes",
        "",
        f"- readiness_summary: {fields['readiness_summary']}",
        f"- recommended_next_task: {fields['recommended_next_task']}",
        f"- kill_reason_if_unusable: {fields['kill_reason_if_unusable']}",
    ]
    return "\n".join(sections) + "\n"


def update_existing_profile_text(text: str, row_id: str, payload: dict[str, Any]) -> str:
    fields = profile_fields(row_id, payload)
    seen: set[str] = set()
    lines: list[str] = []
    for line in text.splitlines():
        match = PROFILE_FIELD_RE.match(line)
        if match is None:
            lines.append(line)
            continue
        prefix, key, colon, _old = match.groups()
        normalized = key.lower()
        if normalized not in fields:
            lines.append(line)
            continue
        seen.add(normalized)
        lines.append(f"{prefix}{key}{colon}{fields[normalized]}")
    missing = [key for key, value in fields.items() if key not in seen and value]
    if missing:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend(["## Proposal Apply Fields", ""])
        lines.extend(f"- {key}: {fields[key]}" for key in missing)
    return "\n".join(lines) + "\n"


def write_data_profile_operation(ops_dir: Path, operation: dict[str, Any]) -> dict[str, Any]:
    row_id = str(operation["row_id"])
    path = (ops_dir / str(operation["target_path"])).resolve(strict=False)
    if not is_relative_to(path, ops_dir):
        raise ApplyError(
            {
                "ok": False,
                "reason": "target_path_outside_workspace",
                "message": "data profile proposal target path must stay inside the research_ops workspace",
                "target_path": operation["target_path"],
                "operation_id": operation["operation_id"],
                "operation": operation["operation"],
                "row_id": row_id,
            },
            MALFORMED,
        )
    payload = operation["payload"]
    if path.exists():
        next_text = update_existing_profile_text(path.read_text(encoding="utf-8"), row_id, payload)
        action = "updated"
    else:
        next_text = render_new_profile(row_id, payload)
        action = "created"
    changed = write_text_atomic(path, next_text)
    return {
        "path": str(path),
        "target_path": operation["target_path"],
        "operation_id": operation["operation_id"],
        "operation": operation["operation"],
        "row_id": row_id,
        "action": action if changed else "unchanged",
        "changed": changed,
    }


def parse_marker_table(path: Path, relative: Path, spec: dict[str, Any]) -> tuple[list[str], list[str], list[dict[str, Any]], list[str]]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    start_marker = str(spec["start"])
    end_marker = str(spec["end"])
    try:
        start = next(index for index, line in enumerate(lines) if line.strip() == start_marker)
        end = next(index for index, line in enumerate(lines) if line.strip() == end_marker)
    except StopIteration as exc:
        raise ApplyError(
            {
                "ok": False,
                "reason": "generated_block_missing",
                "path": str(path),
                "relative_path": str(relative),
            },
            VALIDATION_FAILED,
        ) from exc
    if end <= start:
        raise ApplyError(
            {
                "ok": False,
                "reason": "generated_block_malformed",
                "path": str(path),
                "relative_path": str(relative),
            },
            VALIDATION_FAILED,
        )
    block = [line for line in lines[start + 1:end] if line.strip()]
    headers = list(spec["headers"])
    rows: list[dict[str, Any]] = []
    if block:
        parsed_headers = [cell.lower() for cell in split_table_row(block[0])]
        if parsed_headers != headers:
            raise ApplyError(
                {
                    "ok": False,
                    "reason": "generated_block_header_mismatch",
                    "path": str(path),
                    "expected": headers,
                    "actual": parsed_headers,
                },
                VALIDATION_FAILED,
            )
        for line in block[2:]:
            cells = split_table_row(line)
            if not cells:
                continue
            if len(cells) != len(headers):
                raise ApplyError(
                    {
                        "ok": False,
                        "reason": "generated_block_row_malformed",
                        "path": str(path),
                        "row": line,
                    },
                    VALIDATION_FAILED,
                )
            rows.append(dict(zip(headers, cells)))
    return lines[: start + 1], headers, rows, lines[end:]


def write_library_table_operation(ops_dir: Path, operation: dict[str, Any]) -> dict[str, Any]:
    operation_name = str(operation["operation"])
    if operation_name in LIBRARY_APPEND_OPERATIONS:
        relative = Path(foundation_proposals.LIBRARY_OPERATION_TARGET_PATHS[operation_name])
        key_field = None
    else:
        relative, key_field = LIBRARY_TABLES[operation_name]
    path = ops_dir / relative
    spec = knowledge_library.TABLE_SPECS[relative]
    prefix, headers, rows, suffix = parse_marker_table(path, relative, spec)
    payload = dict(operation["payload"])
    if operation_name in LIBRARY_APPEND_OPERATIONS:
        next_row = {header: clean_cell(payload.get(header, "")) for header in headers}
        if any(all(clean_cell(row.get(header)) == next_row[header] for header in headers) for row in rows):
            action = "unchanged"
            next_rows = rows
        else:
            action = "appended"
            next_rows = rows + [next_row]
    else:
        row_id = str(operation["row_id"])
        assert key_field is not None
        next_rows, action = upsert_rows(rows, key_field, payload, row_id=row_id)
    changed = write_text_atomic(path, join_document(prefix + render_table(headers, next_rows) + suffix))
    return {
        "path": str(path),
        "target_path": str(relative),
        "operation_id": operation["operation_id"],
        "operation": operation_name,
        "row_id": operation["row_id"],
        "action": action,
        "changed": changed,
    }


def target_file_paths(proposals: Iterable[foundation_proposals.FoundationProposal], ops_dir: Path, target: str) -> list[Path]:
    paths: set[Path] = set()
    for proposal in proposals:
        if proposal.target != target:
            continue
        for operation in proposal.operations:
            target_path = str(operation.get("target_path") or "")
            if not target_path:
                continue
            candidate = (ops_dir / target_path).resolve(strict=False)
            if is_relative_to(candidate, ops_dir):
                paths.add(candidate)
    return sorted(paths)


def proposal_document_paths(parse_result: foundation_proposals.ProposalParseResult) -> list[Path]:
    return sorted({proposal.path.resolve(strict=False) for proposal in parse_result.proposals})


def proposal_source_result(target: str, proposal_source: Path) -> foundation_proposals.ProposalParseResult:
    if target == "data":
        return data_proposal_inspection.proposal_source_result(proposal_source)
    return library_proposal_inspection.proposal_source_result(proposal_source)


def inspect_payload(target: str, ops_dir: Path, proposal_source: Path) -> dict[str, Any]:
    if target == "data":
        return data_proposal_inspection.inspect_data_proposals(ops_dir, proposal_source)
    return library_proposal_inspection.inspect_library_proposals(ops_dir, proposal_source)


def validator_commands(target: str, operations: Iterable[dict[str, Any]], ops_dir: Path) -> list[str]:
    if target == "library":
        return [f"async-research library validate {ops_dir}"]
    operation_names = {str(operation.get("operation")) for operation in operations}
    commands: list[str] = []
    if "upsert_data_source" in operation_names:
        commands.append(f"async-research source validate {ops_dir}")
    if operation_names:
        commands.append(f"async-research data validate {ops_dir}")
    return commands


def build_preflight_hash(
    *,
    target: str,
    parse_result: foundation_proposals.ProposalParseResult,
    target_paths: list[Path],
) -> str:
    state = {
        "target": target,
        "proposal_documents": proposal_engine.file_hashes(proposal_document_paths(parse_result)),
        "proposals": [proposal.raw for proposal in parse_result.proposals if proposal.target == target],
        "target_files": proposal_engine.file_hashes(target_paths),
    }
    return proposal_engine.stable_json_hash(state)


def task_id_prefix(value: str) -> str:
    match = TASK_ID_PREFIX_RE.match(value)
    return match.group(1) if match else value


def source_task_dirs(ops_dir: Path, source_task_id: str) -> list[Path]:
    tasks_dir = ops_dir / "tasks"
    if not tasks_dir.exists():
        return []
    candidates: list[Path] = []
    direct = tasks_dir / source_task_id
    if direct.exists():
        candidates.append(direct)
    prefix = task_id_prefix(source_task_id)
    for path in sorted(tasks_dir.glob(f"{source_task_id}*")) + sorted(tasks_dir.glob(f"{prefix}*")):
        if path.is_dir() and path not in candidates:
            candidates.append(path)
    return candidates


def load_json_file(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def status_accepts_proposal(ops_dir: Path, proposal: foundation_proposals.FoundationProposal) -> dict[str, Any]:
    expected = task_id_prefix(proposal.source_task_id)
    for task_dir in source_task_dirs(ops_dir, proposal.source_task_id):
        status_path = task_dir / "status.json"
        payload = load_json_file(status_path)
        if not payload:
            continue
        status_id = str(payload.get("id") or task_id_prefix(task_dir.name))
        if status_id != expected:
            continue
        accepted = payload.get("status") == "accepted"
        return {
            "proposal_id": proposal.proposal_id,
            "source_task_id": proposal.source_task_id,
            "accepted": accepted,
            "proof_type": "task_status",
            "path": str(status_path),
            "status": payload.get("status"),
        }
    return {
        "proposal_id": proposal.proposal_id,
        "source_task_id": proposal.source_task_id,
        "accepted": False,
        "proof_type": "task_status",
        "path": None,
        "status": "missing",
    }


def accepted_artifact_result(
    ops_dir: Path,
    proposal: foundation_proposals.FoundationProposal,
    accepted_artifact: Path | None,
) -> dict[str, Any] | None:
    if accepted_artifact is None:
        return None
    path = accepted_artifact.resolve(strict=False)
    if not is_relative_to(path, ops_dir):
        return {
            "proposal_id": proposal.proposal_id,
            "source_task_id": proposal.source_task_id,
            "accepted": False,
            "proof_type": "accepted_artifact",
            "path": str(path),
            "reason": "accepted_artifact_outside_workspace",
        }
    payload = load_json_file(path)
    if payload is None:
        return {
            "proposal_id": proposal.proposal_id,
            "source_task_id": proposal.source_task_id,
            "accepted": False,
            "proof_type": "accepted_artifact",
            "path": str(path),
            "reason": "accepted_artifact_unreadable",
        }
    expected = task_id_prefix(proposal.source_task_id)
    schema_errors = validate_result_acceptance.schema_errors(payload)
    gates = payload.get("hard_gate_results") if isinstance(payload.get("hard_gate_results"), list) else []
    failed_gates = [gate for gate in gates if isinstance(gate, dict) and gate.get("passed") is not True]
    accepted = (
        not schema_errors
        and str(payload.get("task_id")) == expected
        and payload.get("route") in ACCEPTED_ROUTES
        and not failed_gates
    )
    result: dict[str, Any] = {
        "proposal_id": proposal.proposal_id,
        "source_task_id": proposal.source_task_id,
        "accepted": accepted,
        "proof_type": "accepted_artifact",
        "path": str(path),
        "task_id": payload.get("task_id"),
        "route": payload.get("route"),
    }
    if schema_errors:
        result["schema_errors"] = schema_errors
    if failed_gates:
        result["failed_gates"] = failed_gates
    if str(payload.get("task_id")) != expected:
        result["reason"] = "accepted_artifact_task_mismatch"
    elif payload.get("route") not in ACCEPTED_ROUTES:
        result["reason"] = "accepted_artifact_not_accepted_route"
    elif schema_errors:
        result["reason"] = "accepted_artifact_schema_invalid"
    elif failed_gates:
        result["reason"] = "accepted_artifact_gate_failed"
    return result


def acceptance_results(
    ops_dir: Path,
    proposals: Iterable[foundation_proposals.FoundationProposal],
    target: str,
    accepted_artifact: Path | None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for proposal in proposals:
        if proposal.target != target:
            continue
        status_result = status_accepts_proposal(ops_dir, proposal)
        if status_result["accepted"]:
            results.append(status_result)
            continue
        artifact_result = accepted_artifact_result(ops_dir, proposal, accepted_artifact)
        results.append(artifact_result or status_result)
    return results


def operation_plan_items(inspection: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for operation in inspection.get("operations", []):
        items.append(
            {
                "proposal_id": operation.get("proposal_id"),
                "operation_id": operation.get("operation_id"),
                "operation": operation.get("operation"),
                "target_path": operation.get("target_path"),
                "row_id": operation.get("row_id"),
                "status": operation.get("status"),
                "message": operation.get("message"),
                "reason": operation.get("reason"),
            }
        )
    return items


def build_apply_plan(
    target: str,
    ops_dir: Path,
    proposal_source: Path,
    *,
    accepted_artifact: Path | None = None,
) -> tuple[dict[str, Any], foundation_proposals.ProposalParseResult]:
    parse_result = proposal_source_result(target, proposal_source)
    inspection = inspect_payload(target, ops_dir, proposal_source)
    target_paths = target_file_paths(parse_result.proposals, ops_dir, target)
    operations = [
        operation
        for proposal in parse_result.proposals
        if proposal.target == target
        for operation in proposal.operations
    ]
    preflight_hash = build_preflight_hash(
        target=target,
        parse_result=parse_result,
        target_paths=target_paths,
    )
    acceptance = acceptance_results(ops_dir, parse_result.proposals, target, accepted_artifact)
    blockers = list(inspection.get("blockers", []))
    warnings = list(inspection.get("warnings", []))
    payload = {
        "ok": not blockers,
        "action": f"{target}_proposal_apply_planned",
        "target": target,
        "mode": "dry-run",
        "dry_run": True,
        "changed": False,
        "ops_dir": str(ops_dir),
        "proposal_source": str(proposal_source),
        "preflight_hash": preflight_hash,
        "proposals_found": inspection.get("proposals_found", 0),
        "valid_proposals": inspection.get("valid_proposals", 0),
        "invalid_proposals": inspection.get("invalid_proposals", 0),
        "warnings": warnings,
        "blockers": blockers,
        "proposed_file_edits": operation_plan_items(inspection),
        "target_files": [
            {"path": str(path), "exists": path.exists(), "sha256": file_sha256(path)}
            for path in target_paths
        ],
        "post_write_validators": validator_commands(target, operations, ops_dir),
        "write_preconditions": {
            "requires_write_flag": True,
            "requires_matching_preflight_hash": True,
            "requires_accepted_task_or_artifact": True,
            "requires_foundation_lock": True,
            "requires_post_write_validation": True,
            "acceptance": acceptance,
        },
        "next_steps": apply_next_steps(blockers, warnings),
    }
    return payload, parse_result


def apply_next_steps(blockers: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> list[str]:
    if blockers:
        return ["Fix blockers and rerun apply-proposals in dry-run mode."]
    if warnings:
        return ["Review warning-only upserts, then rerun with --write and the matching preflight hash after acceptance proof is present."]
    return ["Review the dry-run plan, then rerun with --write and the matching preflight hash after acceptance proof is present."]


def lock_path(ops_dir: Path, target: str) -> Path:
    return ops_dir / f".foundation_{target}_apply.LOCK"


def acquire_lock(ops_dir: Path, target: str) -> proposal_engine.DirectoryLock:
    path = lock_path(ops_dir, target)
    owner = {
        "target": target,
        "pid": os.getpid(),
        "hostname": socket.gethostname(),
        "acquired_at": utc_now(),
    }
    return proposal_engine.acquire_directory_lock(
        path,
        owner,
        on_exists=lambda lock_dir, existing: ApplyError(
            {
                "ok": False,
                "reason": "foundation_apply_locked",
                "message": f"{target} proposal apply is already locked",
                "lock_dir": str(lock_dir),
                "owner": existing,
            },
            VALIDATION_FAILED,
        ),
        on_failure=lambda lock_dir, exc: ApplyError(
            {
                "ok": False,
                "reason": "foundation_apply_lock_failed",
                "message": f"could not acquire {target} proposal apply lock",
                "lock_dir": str(lock_dir),
                "error": str(exc),
            },
            MALFORMED,
        ),
    )


def release_lock(lock: proposal_engine.DirectoryLock | None) -> None:
    proposal_engine.release_directory_lock(lock)


def snapshot_files(paths: Iterable[Path]) -> dict[Path, bytes | None]:
    return proposal_engine.snapshot_files(paths)


def rollback_files(snapshots: dict[Path, bytes | None]) -> dict[str, Any]:
    def write_snapshot(path: Path, content: bytes) -> bool:
        return write_text_atomic(path, content.decode("utf-8"))

    rollback_actions = proposal_engine.restore_file_snapshots(
        snapshots,
        write_snapshot,
        absent_action="removed_created_file",
        absent_failed_action="remove_created_file_failed",
        restored_action="restored_snapshot",
        restored_failed_action="restore_snapshot_failed",
    )
    actions = [
        {key: value for key, value in action.items() if key != "changed"}
        for action in rollback_actions
        if not action.get("error")
        if not (action["action"] == "removed_created_file" and action.get("changed") is False)
    ]
    failures = [{"path": action["path"], "error": action["error"]} for action in rollback_actions if action.get("error")]
    return {"ok": not failures, "actions": actions, "failures": failures}


def run_module_json(module: Any, argv: list[str]) -> tuple[int, dict[str, Any], str]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = int(module.main(argv))
    text = stream.getvalue()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = {"ok": code == 0, "raw_output": text}
    return code, payload if isinstance(payload, dict) else {"ok": code == 0, "value": payload}, text


def run_validators(target: str, operations: Iterable[dict[str, Any]], ops_dir: Path) -> list[dict[str, Any]]:
    operation_names = {str(operation.get("operation")) for operation in operations}
    checks: list[tuple[str, Any, list[str]]] = []
    if target == "data":
        if "upsert_data_source" in operation_names:
            checks.append((f"async-research source validate {ops_dir}", data_source_audit, ["validate", str(ops_dir)]))
        if operation_names:
            checks.append((f"async-research data validate {ops_dir}", data_foundations, ["validate", str(ops_dir)]))
    else:
        checks.append((f"async-research library validate {ops_dir}", knowledge_library, ["validate", str(ops_dir)]))
    results: list[dict[str, Any]] = []
    for command, module, argv in checks:
        code, payload, _text = run_module_json(module, argv)
        passed = code == SUCCESS or (code == VALIDATION_FAILED and payload.get("ok") is True)
        results.append(
            {
                "command": command,
                "status": "passed" if passed else "failed",
                "exit_code": code,
                "payload": payload,
            }
        )
    return results


def apply_operation(ops_dir: Path, target: str, operation: dict[str, Any]) -> dict[str, Any]:
    operation_name = str(operation["operation"])
    if target == "data":
        if operation_name == "upsert_data_source":
            return write_data_source_operation(ops_dir, operation)
        if operation_name == "upsert_data_profile":
            return write_data_profile_operation(ops_dir, operation)
        return write_data_table_operation(ops_dir, operation)
    return write_library_table_operation(ops_dir, operation)


def apply_write(
    target: str,
    ops_dir: Path,
    proposal_source: Path,
    *,
    preflight_hash: str,
    accepted_artifact: Path | None = None,
) -> tuple[int, dict[str, Any]]:
    lock: proposal_engine.DirectoryLock | None = None
    source_lock: dict[str, Any] | None = None
    try:
        lock = acquire_lock(ops_dir, target)
        if target == "data":
            source_lock = data_source_audit.acquire_source_register_lock(ops_dir, "data apply-proposals")
        plan, parse_result = build_apply_plan(
            target,
            ops_dir,
            proposal_source,
            accepted_artifact=accepted_artifact,
        )
        if plan["blockers"]:
            return MALFORMED, {
                **plan,
                "ok": False,
                "action": f"{target}_proposal_apply_failed",
                "mode": "write",
                "dry_run": False,
                "reason": "inspection_blockers",
            }
        if plan["preflight_hash"] != preflight_hash:
            return INVALID_REQUEST, {
                "ok": False,
                "action": f"{target}_proposal_apply_failed",
                "reason": "preflight_hash_mismatch",
                "expected_preflight_hash": plan["preflight_hash"],
                "provided_preflight_hash": preflight_hash,
                "lock": {"path": str(lock.path), "owner": lock.owner},
            }
        acceptance = plan["write_preconditions"]["acceptance"]
        acceptance_blockers = [item for item in acceptance if not item.get("accepted")]
        if acceptance_blockers:
            return MALFORMED, {
                "ok": False,
                "action": f"{target}_proposal_apply_failed",
                "reason": "accepted_task_or_artifact_required",
                "acceptance": acceptance,
                "lock": {"path": str(lock.path), "owner": lock.owner},
                "next_step": "mark the source task accepted or pass --accepted-artifact pointing to a valid result_acceptance.json",
            }
        operations = [
            operation
            for proposal in parse_result.proposals
            if proposal.target == target
            for operation in proposal.operations
        ]
        target_paths = target_file_paths(parse_result.proposals, ops_dir, target)
        snapshots = snapshot_files(target_paths)
        writes: list[dict[str, Any]] = []
        try:
            for operation in operations:
                writes.append(apply_operation(ops_dir, target, operation))
            validation = run_validators(target, operations, ops_dir)
            if any(item["status"] != "passed" for item in validation):
                rollback = rollback_files(snapshots)
                return VALIDATION_FAILED, {
                    "ok": False,
                    "action": f"{target}_proposal_apply_failed",
                    "reason": "post_write_validation_failed",
                    "changed": any(item.get("changed") for item in writes),
                    "writes": writes,
                    "validation": validation,
                    "rollback": rollback,
                    "lock": {"path": str(lock.path), "owner": lock.owner},
                }
        except ApplyError as exc:
            rollback = rollback_files(snapshots)
            return exc.code, {
                **exc.payload,
                "action": f"{target}_proposal_apply_failed",
                "changed": any(item.get("changed") for item in writes),
                "writes": writes,
                "rollback": rollback,
                "lock": {"path": str(lock.path), "owner": lock.owner},
            }
        except Exception as exc:
            rollback = rollback_files(snapshots)
            return MALFORMED, {
                "ok": False,
                "action": f"{target}_proposal_apply_failed",
                "reason": "apply_exception",
                "error": str(exc),
                "changed": any(item.get("changed") for item in writes),
                "writes": writes,
                "rollback": rollback,
                "lock": {"path": str(lock.path), "owner": lock.owner},
            }
        return SUCCESS, {
            "ok": True,
            "action": f"{target}_proposals_applied",
            "target": target,
            "mode": "write",
            "dry_run": False,
            "changed": any(item.get("changed") for item in writes),
            "ops_dir": str(ops_dir),
            "proposal_source": str(proposal_source),
            "preflight_hash": preflight_hash,
            "writes": writes,
            "validation": validation,
            "lock": {"path": str(lock.path), "owner": lock.owner},
        }
    except data_source_audit.SourceRegisterLockError as exc:
        return VALIDATION_FAILED, exc.payload
    except ApplyError as exc:
        return exc.code, exc.payload
    finally:
        data_source_audit.release_source_register_lock(source_lock)
        release_lock(lock)


def parse_args(target: str, argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=f"Apply accepted {target} foundation proposals with dry-run preflight, locks, rollback, and validation."
    )
    parser.add_argument("ops_dir", type=Path, help="Path to the research_ops workspace.")
    parser.add_argument(
        "proposal_source",
        type=Path,
        help="Task directory, worker_output.md, JSON proposal artifact, or directory containing proposal artifacts.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Preview the apply plan without writing. This is the default.")
    mode.add_argument("--write", action="store_true", help="Apply the accepted proposal after all write preconditions pass.")
    parser.add_argument("--preflight-hash", help="Dry-run preflight hash required for --write.")
    parser.add_argument(
        "--accepted-artifact",
        "--acceptance-artifact",
        dest="accepted_artifact",
        type=Path,
        help="Optional in-workspace review_panel/result_acceptance.json accepted proof when the source task status is not accepted.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    args.target = target
    return args


def main_for_target(target: str, argv: Iterable[str] | None = None) -> int:
    if target not in TARGETS:
        raise ValueError(f"unsupported target: {target}")
    args = parse_args(target, argv)
    if args.write and not args.preflight_hash:
        print_json(
            {
                "ok": False,
                "action": f"{target}_proposal_apply_failed",
                "reason": "preflight_hash_required",
                "message": "--write requires --preflight-hash from a clean dry run",
            }
        )
        return INVALID_REQUEST
    if not args.write:
        plan, _parse_result = build_apply_plan(
            target,
            args.ops_dir,
            args.proposal_source,
            accepted_artifact=args.accepted_artifact,
        )
        print_json(plan)
        return SUCCESS if plan["ok"] else MALFORMED
    code, payload = apply_write(
        target,
        args.ops_dir,
        args.proposal_source,
        preflight_hash=args.preflight_hash,
        accepted_artifact=args.accepted_artifact,
    )
    print_json(payload)
    return code
