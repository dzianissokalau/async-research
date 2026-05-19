#!/usr/bin/env python3
"""Read-only inspection for data foundation update proposals."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any, Iterable

from async_research_workflow.scripts import foundation_proposals
from async_research_workflow.scripts.data_foundations import first_markdown_table
from async_research_workflow.scripts.data_foundations import normalize_text
from async_research_workflow.scripts.data_source_audit import canonical_row
from async_research_workflow.scripts.data_source_audit import parse_register
from async_research_workflow.scripts.data_source_audit import row_map
from async_research_workflow.scripts.data_source_audit import validate_rows


SUCCESS = 0
MALFORMED = 4

DS_ID_RE = re.compile(r"^DS-[0-9]{4}$")
DG_ID_RE = re.compile(r"^DG-[0-9]{4}$")
SAFE_ROW_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]*$")

DATA_ROW_ID_FIELDS = {
    "upsert_data_source": "source_id",
    "upsert_data_profile": "source_id",
    "upsert_data_catalog_row": "source_id",
    "upsert_data_access_row": "source_id",
    "upsert_join_map_row": "join_id",
    "upsert_known_data_gap": "gap_id",
}

DATA_TARGET_TABLES = {
    "upsert_data_catalog_row": ("data/data_catalog.md", "source_id"),
    "upsert_data_access_row": ("data/data_access.md", "source_id"),
    "upsert_join_map_row": ("data/join_map.md", "join_id"),
    "upsert_known_data_gap": ("data/known_data_gaps.md", "gap_id"),
}


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def operation_diagnostic(
    proposal_id: str,
    operation_id: str,
    operation: str,
    target_path: str,
    row_id: str,
    status: str,
    message: str,
    *,
    reason: str | None = None,
    path: str | None = None,
    remediation: str | None = None,
    **details: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "proposal_id": proposal_id,
        "operation_id": operation_id,
        "operation": operation,
        "target_path": target_path,
        "row_id": row_id,
        "status": status,
        "message": message,
    }
    if reason:
        payload["reason"] = reason
    if path:
        payload["path"] = path
    if remediation:
        payload["remediation"] = remediation
    payload.update(details)
    return payload


def parser_diagnostic_to_blocker(item: dict[str, Any]) -> dict[str, Any]:
    status = "warning" if item.get("severity") == "warning" else "blocked"
    return operation_diagnostic(
        str(item.get("proposal_id") or "unavailable"),
        str(item.get("operation_id") or "unavailable"),
        str(item.get("operation") or "unavailable"),
        str(item.get("target_path") or "unavailable"),
        str(item.get("row_id") or "unavailable"),
        status,
        str(item.get("message") or "proposal parser rejected this input"),
        reason=str(item.get("reason") or "proposal_parse_error"),
        path=str(item.get("path") or ""),
        remediation=str(item.get("remediation") or "fix the proposal and rerun inspection"),
    )


def safe_resolve_under(root: Path, relative_path: str) -> Path | None:
    root_resolved = root.resolve(strict=False)
    candidate = (root / relative_path).resolve(strict=False)
    try:
        candidate.relative_to(root_resolved)
    except ValueError:
        return None
    return candidate


def proposal_source_result(proposal_source: Path) -> foundation_proposals.ProposalParseResult:
    if proposal_source.is_file():
        return foundation_proposals.load_proposal_paths([proposal_source])
    if proposal_source.is_dir():
        if (proposal_source / "worker_output.md").exists() or (proposal_source / "artifacts").exists():
            return foundation_proposals.discover_task_proposals(proposal_source)
        paths = discover_directory_proposal_documents(proposal_source)
        return foundation_proposals.load_proposal_paths(paths)
    return foundation_proposals.load_proposal_paths([proposal_source])


def looks_like_proposal_json(path: Path) -> bool:
    if "proposal" in path.name.lower():
        return True
    try:
        return foundation_proposals.PROPOSAL_VERSION in path.read_text(encoding="utf-8")
    except OSError:
        return False


def discover_directory_proposal_documents(directory: Path) -> list[Path]:
    paths: list[Path] = []
    for path in sorted(directory.rglob("*.json")):
        if looks_like_proposal_json(path):
            paths.append(path)
    for path in sorted(directory.rglob("*.md")):
        if path.name == "worker_output.md" or "proposal" in path.name.lower():
            paths.append(path)
    return paths


def issue(
    reason: str,
    path: Path,
    message: str,
    *,
    remediation: str,
    severity: str = "error",
    **details: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "severity": severity,
        "reason": reason,
        "path": str(path),
        "message": message,
        "remediation": remediation,
    }
    payload.update(details)
    return payload


def load_audit_rows(ops_dir: Path) -> tuple[dict[str, dict[str, str]], list[dict[str, Any]]]:
    audit_path = ops_dir / "data_source_audit.md"
    try:
        schema_version, rows = parse_register(audit_path)
    except ValueError as exc:
        return {}, [
            issue(
                "source_audit_malformed",
                audit_path,
                str(exc),
                remediation="repair data_source_audit.md before inspecting data proposals",
            )
        ]
    errors = validate_rows(schema_version, rows)
    if errors:
        return {}, [
            {
                **item,
                "remediation": "repair data_source_audit.md before inspecting data proposals",
            }
            for item in errors
        ]
    return row_map([canonical_row(row) for row in rows]), []


def load_table_index(path: Path, row_id_field: str) -> tuple[set[str], list[dict[str, Any]]]:
    rows, errors = first_markdown_table(path)
    blockers = [
        {
            **item,
            "remediation": f"repair {path} before inspecting data proposals",
        }
        for item in errors
    ]
    if not path.exists():
        blockers.append(
            issue(
                "target_table_missing",
                path,
                f"required data foundation table is missing: {path}",
                remediation="restore the starter data foundation file before inspecting proposals",
            )
        )
    ids = {normalize_text(row.get(row_id_field)) for row in rows if normalize_text(row.get(row_id_field))}
    return ids, blockers


def load_existing_state(ops_dir: Path) -> tuple[dict[str, set[str]], list[dict[str, Any]]]:
    existing: dict[str, set[str]] = {}
    blockers: list[dict[str, Any]] = []
    if not ops_dir.exists() or not ops_dir.is_dir():
        return existing, [
            issue(
                "ops_dir_missing",
                ops_dir,
                f"{ops_dir} is not an existing research_ops directory",
                remediation="rerun with an initialized research_ops directory",
            )
        ]

    audit_by_id, audit_blockers = load_audit_rows(ops_dir)
    existing["upsert_data_source"] = set(audit_by_id)
    blockers.extend(audit_blockers)

    profile_dir = ops_dir / "data" / "profiles"
    if not profile_dir.exists():
        blockers.append(
            issue(
                "profile_dir_missing",
                profile_dir,
                f"required data profile directory is missing: {profile_dir}",
                remediation="restore research_ops/data/profiles before inspecting profile proposals",
            )
        )
        existing["upsert_data_profile"] = set()
    else:
        existing["upsert_data_profile"] = {
            path.stem
            for path in profile_dir.glob("DS-*.md")
            if path.name != "DS-0000.md"
        }

    for operation, (relative, row_id_field) in DATA_TARGET_TABLES.items():
        ids, table_blockers = load_table_index(ops_dir / relative, row_id_field)
        existing[operation] = ids
        blockers.extend(table_blockers)
    return existing, blockers


def expected_target_path(operation: str, row_id: str) -> str:
    template = foundation_proposals.DATA_OPERATION_TARGET_PATHS[operation]
    return template.format(row_id=row_id)


def validate_row_id(operation: str, row_id: str) -> tuple[bool, str]:
    if operation in {
        "upsert_data_source",
        "upsert_data_profile",
        "upsert_data_catalog_row",
        "upsert_data_access_row",
    }:
        return bool(DS_ID_RE.fullmatch(row_id)), "use a governed DS-0000 source id"
    if operation == "upsert_known_data_gap":
        return bool(DG_ID_RE.fullmatch(row_id)), "use a DG-0000 known data gap id"
    return bool(SAFE_ROW_ID_RE.fullmatch(row_id)), "use a stable non-empty row id without spaces"


def payload_id_diagnostic(
    proposal: foundation_proposals.FoundationProposal,
    operation: dict[str, Any],
    row_id: str,
) -> dict[str, Any] | None:
    operation_name = str(operation.get("operation") or "")
    payload = operation.get("payload") if isinstance(operation.get("payload"), dict) else {}
    id_field = DATA_ROW_ID_FIELDS.get(operation_name)
    if id_field is None:
        return None
    payload_row_id = normalize_text(payload.get(id_field))
    if not payload_row_id:
        return operation_diagnostic(
            proposal.proposal_id,
            str(operation.get("operation_id") or "unavailable"),
            operation_name,
            str(operation.get("target_path") or "unavailable"),
            row_id,
            "blocked",
            f"payload must include {id_field} matching row_id {row_id}",
            reason="payload_row_id_missing",
            path=str(proposal.path),
            remediation=f"add payload.{id_field} with value {row_id}",
            payload_id_field=id_field,
        )
    if payload_row_id != row_id:
        return operation_diagnostic(
            proposal.proposal_id,
            str(operation.get("operation_id") or "unavailable"),
            operation_name,
            str(operation.get("target_path") or "unavailable"),
            row_id,
            "blocked",
            f"payload {id_field} {payload_row_id} does not match row_id {row_id}",
            reason="payload_row_id_mismatch",
            path=str(proposal.path),
            remediation=f"set payload.{id_field} to {row_id}",
            payload_id_field=id_field,
            payload_row_id=payload_row_id,
        )
    return None


def inspect_operation(
    proposal: foundation_proposals.FoundationProposal,
    operation: dict[str, Any],
    ops_dir: Path,
    existing: dict[str, set[str]],
    seen_row_keys: set[tuple[str, str, str]],
) -> dict[str, Any]:
    operation_id = str(operation.get("operation_id") or "unavailable")
    operation_name = str(operation.get("operation") or "unavailable")
    target_path = str(operation.get("target_path") or "unavailable")
    row_id = str(operation.get("row_id") or "unavailable")

    if operation_name not in foundation_proposals.DATA_OPERATIONS:
        return operation_diagnostic(
            proposal.proposal_id,
            operation_id,
            operation_name,
            target_path,
            row_id,
            "blocked",
            f"operation {operation_name} is not a data foundation operation",
            reason="non_data_operation",
            path=str(proposal.path),
            remediation="use only data operations with target=data",
        )

    valid_row, row_remediation = validate_row_id(operation_name, row_id)
    if not valid_row:
        return operation_diagnostic(
            proposal.proposal_id,
            operation_id,
            operation_name,
            target_path,
            row_id,
            "blocked",
            f"row_id {row_id} is not valid for {operation_name}",
            reason="invalid_data_row_id",
            path=str(proposal.path),
            remediation=row_remediation,
        )

    expected = expected_target_path(operation_name, row_id)
    if target_path != expected:
        return operation_diagnostic(
            proposal.proposal_id,
            operation_id,
            operation_name,
            target_path,
            row_id,
            "blocked",
            f"target_path {target_path} does not match canonical data target {expected}",
            reason="unexpected_data_target_path",
            path=str(proposal.path),
            remediation=f"set target_path to {expected}",
            expected_target_path=expected,
        )

    resolved_target = safe_resolve_under(ops_dir, target_path)
    if resolved_target is None:
        return operation_diagnostic(
            proposal.proposal_id,
            operation_id,
            operation_name,
            target_path,
            row_id,
            "blocked",
            f"target_path {target_path} resolves outside {ops_dir}",
            reason="target_path_outside_workspace",
            path=str(proposal.path),
            remediation="use a canonical research_ops-relative data target path",
        )

    if operation_name == "upsert_data_profile":
        if not resolved_target.parent.exists():
            return operation_diagnostic(
                proposal.proposal_id,
                operation_id,
                operation_name,
                target_path,
                row_id,
                "blocked",
                "data profile target directory is missing",
                reason="target_profile_dir_missing",
                path=str(resolved_target.parent),
                remediation="restore research_ops/data/profiles before proposing profile updates",
            )
    elif not resolved_target.exists():
        return operation_diagnostic(
            proposal.proposal_id,
            operation_id,
            operation_name,
            target_path,
            row_id,
            "blocked",
            "target data foundation table is missing",
            reason="target_file_missing",
            path=str(resolved_target),
            remediation="restore the canonical data foundation file before proposing updates",
        )

    duplicate_key = (operation_name, target_path, row_id)
    if duplicate_key in seen_row_keys:
        return operation_diagnostic(
            proposal.proposal_id,
            operation_id,
            operation_name,
            target_path,
            row_id,
            "blocked",
            f"proposal repeats {operation_name} for row_id {row_id}",
            reason="duplicate_proposed_row",
            path=str(proposal.path),
            remediation="merge duplicate row updates into one operation",
        )
    seen_row_keys.add(duplicate_key)

    payload_diagnostic = payload_id_diagnostic(proposal, operation, row_id)
    if payload_diagnostic is not None:
        return payload_diagnostic

    if row_id in existing.get(operation_name, set()):
        return operation_diagnostic(
            proposal.proposal_id,
            operation_id,
            operation_name,
            target_path,
            row_id,
            "warning",
            f"upsert would replace existing {row_id} in {target_path}",
            reason="existing_row_upsert",
            path=str(resolved_target),
            remediation="review the existing row and preserve manual notes before any future apply step",
        )

    return operation_diagnostic(
        proposal.proposal_id,
        operation_id,
        operation_name,
        target_path,
        row_id,
        "valid",
        f"operation can be reviewed for {target_path}",
        path=str(resolved_target),
    )


def invalid_proposal_count(parse_result: foundation_proposals.ProposalParseResult, invalid_ids: set[str]) -> int:
    parse_error_ids = {
        str(item.get("proposal_id"))
        for item in parse_result.diagnostics
        if item.get("severity") == "error" and item.get("proposal_id")
    }
    anonymous_parse_errors = sum(
        1
        for item in parse_result.diagnostics
        if item.get("severity") == "error" and not item.get("proposal_id")
    )
    return len(invalid_ids | parse_error_ids) + anonymous_parse_errors


def inspect_data_proposals(ops_dir: Path, proposal_source: Path) -> dict[str, Any]:
    parse_result = proposal_source_result(proposal_source)
    existing, workspace_blockers = load_existing_state(ops_dir)
    operations: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    invalid_ids: set[str] = set()
    valid_ids: set[str] = set()

    for item in parse_result.diagnostics:
        diagnostic = parser_diagnostic_to_blocker(item)
        if item.get("severity") == "warning":
            warnings.append(diagnostic)
        else:
            blockers.append(diagnostic)

    for item in workspace_blockers:
        blockers.append(
            operation_diagnostic(
                "workspace",
                "workspace",
                "inspect_workspace",
                str(item.get("path") or ops_dir),
                "workspace",
                "blocked",
                str(item.get("message") or "workspace cannot be inspected"),
                reason=str(item.get("reason") or "workspace_blocked"),
                path=str(item.get("path") or ops_dir),
                remediation=str(item.get("remediation") or "repair workspace and rerun inspection"),
            )
        )

    for proposal in parse_result.proposals:
        proposal_blocked = bool(workspace_blockers)
        if proposal.target != "data":
            proposal_blocked = True
            diagnostic = operation_diagnostic(
                proposal.proposal_id,
                "proposal",
                "inspect_proposal",
                "proposal",
                "proposal",
                "blocked",
                f"proposal target {proposal.target} is not data",
                reason="non_data_proposal_target",
                path=str(proposal.path),
                remediation="inspect library proposals with the library proposal command when available",
            )
            operations.append(diagnostic)
            blockers.append(diagnostic)
        seen_row_keys: set[tuple[str, str, str]] = set()
        if not workspace_blockers and proposal.target == "data":
            for operation in proposal.operations:
                diagnostic = inspect_operation(proposal, operation, ops_dir, existing, seen_row_keys)
                operations.append(diagnostic)
                if diagnostic["status"] == "blocked":
                    proposal_blocked = True
                    blockers.append(diagnostic)
                elif diagnostic["status"] == "warning":
                    warnings.append(diagnostic)
        if proposal_blocked:
            invalid_ids.add(proposal.proposal_id)
        else:
            valid_ids.add(proposal.proposal_id)

    if not parse_result.proposals and not parse_result.diagnostics:
        blockers.append(
            operation_diagnostic(
                "unavailable",
                "proposal_source",
                "discover_proposals",
                str(proposal_source),
                "unavailable",
                "blocked",
                "no foundation_update_proposal_v1 proposals were found",
                reason="no_proposals_found",
                path=str(proposal_source),
                remediation="provide a task directory, worker_output.md, JSON proposal artifact, or proposal artifact directory",
            )
        )

    valid_proposals = len(valid_ids)
    invalid_proposals = invalid_proposal_count(parse_result, invalid_ids)
    proposal_total = valid_proposals + invalid_proposals
    next_steps = next_step_messages(blockers, warnings)
    return {
        "ok": not blockers,
        "ops_dir": str(ops_dir),
        "proposal_source": str(proposal_source),
        "proposals_found": proposal_total,
        "valid_proposals": valid_proposals,
        "invalid_proposals": invalid_proposals,
        "operations": operations,
        "warnings": warnings,
        "blockers": blockers,
        "next_steps": next_steps,
        "read_only": True,
        "changed": False,
    }


def next_step_messages(blockers: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> list[str]:
    if blockers:
        return ["Fix blocked proposal diagnostics and rerun data inspect-proposals."]
    if warnings:
        return ["Review warnings before routing the accepted proposal to a future guarded apply workflow."]
    return ["Proposal diagnostics are clean for data review; no files were changed."]


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect data foundation proposals without mutating research_ops.")
    parser.add_argument("ops_dir", type=Path, help="Path to the research_ops workspace.")
    parser.add_argument(
        "proposal_source",
        type=Path,
        help="Task directory, worker_output.md, JSON proposal artifact, or directory containing proposal artifacts.",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    payload = inspect_data_proposals(args.ops_dir, args.proposal_source)
    print_json(payload)
    return SUCCESS if payload["ok"] else MALFORMED


if __name__ == "__main__":
    raise SystemExit(main())
