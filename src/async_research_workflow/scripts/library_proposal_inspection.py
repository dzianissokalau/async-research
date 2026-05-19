#!/usr/bin/env python3
"""Read-only inspection for knowledge library update proposals."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any, Iterable

from async_research_workflow.scripts import foundation_proposals
from async_research_workflow.scripts import knowledge_library


SUCCESS = 0
MALFORMED = 4

TOPIC_ID_RE = re.compile(r"^TOPIC-[0-9]{4}$")
CLAIM_ID_RE = re.compile(r"^CLAIM-[0-9]{4}$")
METHOD_ID_RE = re.compile(r"^METHOD-[0-9]{4}$")
OQ_ID_RE = re.compile(r"^OQ-[0-9]{4}$")

LIBRARY_TARGET_TABLES = {
    "upsert_lit_source": (Path(knowledge_library.LIBRARY_DIR) / knowledge_library.SOURCE_LIBRARY_FILE, "source_id"),
    "upsert_topic_summary": (Path(knowledge_library.LIBRARY_DIR) / knowledge_library.KNOWLEDGE_INDEX_FILE, "topic"),
    "upsert_claim": (Path(knowledge_library.LIBRARY_DIR) / knowledge_library.CLAIM_MAP_FILE, "claim"),
    "upsert_method": (Path(knowledge_library.LIBRARY_DIR) / knowledge_library.METHOD_INDEX_FILE, "method"),
    "upsert_open_question": (Path(knowledge_library.LIBRARY_DIR) / knowledge_library.OPEN_QUESTIONS_FILE, "question_id"),
}
SOURCE_REF_OPERATIONS = {
    "upsert_topic_summary",
    "upsert_claim",
    "upsert_method",
    "upsert_open_question",
}
SOURCE_REF_REQUIRED_OPERATIONS = {
    "upsert_topic_summary",
    "upsert_claim",
    "upsert_method",
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


def safe_resolve_library_target(ops_dir: Path, target_path: str) -> Path | None:
    library_root = (ops_dir / knowledge_library.LIBRARY_DIR).resolve(strict=False)
    candidate = (ops_dir / target_path).resolve(strict=False)
    try:
        candidate.relative_to(library_root)
    except ValueError:
        return None
    return candidate


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

    library_dir = ops_dir / knowledge_library.LIBRARY_DIR
    if not library_dir.exists() or not library_dir.is_dir():
        return existing, [
            issue(
                "library_dir_missing",
                library_dir,
                f"{library_dir} is not an existing research_ops/library directory",
                remediation="run library init or restore research_ops/library before inspecting proposals",
            )
        ]

    for relative, _template in knowledge_library.STARTER_FILES:
        path = ops_dir / relative
        if path.exists() and not path.is_file():
            blockers.append(
                issue(
                    "library_file_path_not_file",
                    path,
                    f"library path is not a file: {relative}",
                    remediation="restore the canonical library file before inspecting proposals",
                )
            )
            existing[str(relative)] = set()
            continue
        spec = knowledge_library.TABLE_SPECS[relative]
        rows, errors = knowledge_library.parse_generated_table(path, relative, spec)
        for item in errors:
            blockers.append(
                {
                    **item,
                    "remediation": f"repair {relative} before inspecting library proposals",
                }
            )
        existing[str(relative)] = {
            knowledge_library.normalize_text(row.get(field))
            for operation, (target_relative, field) in LIBRARY_TARGET_TABLES.items()
            if target_relative == relative
            for row in rows
            if knowledge_library.normalize_text(row.get(field))
        }
    return existing, blockers


def existing_values_for_operation(operation: str, existing: dict[str, set[str]]) -> set[str]:
    target = LIBRARY_TARGET_TABLES.get(operation)
    if target is None:
        return set()
    relative, _field = target
    return existing.get(str(relative), set())


def expected_target_path(operation: str) -> str:
    return foundation_proposals.LIBRARY_OPERATION_TARGET_PATHS[operation]


def validate_row_id(operation: str, row_id: str, existing: dict[str, set[str]]) -> tuple[bool, str]:
    if operation == "upsert_lit_source":
        return bool(knowledge_library.LIT_ID_RE.fullmatch(row_id)), "use a governed LIT-0000 source id"
    if operation == "upsert_topic_summary":
        existing_topics = existing_values_for_operation(operation, existing)
        if TOPIC_ID_RE.fullmatch(row_id) or row_id in existing_topics:
            return True, ""
        return False, "use a TOPIC-0000 id, or an existing topic key when updating a local table row"
    if operation == "upsert_claim":
        return bool(CLAIM_ID_RE.fullmatch(row_id)), "use a CLAIM-0000 id for claim proposals"
    if operation == "upsert_method":
        return bool(METHOD_ID_RE.fullmatch(row_id)), "use a METHOD-0000 id for method proposals"
    if operation == "upsert_open_question":
        return bool(OQ_ID_RE.fullmatch(row_id)), "use an OQ-0000 id for open-question proposals"
    return bool(foundation_proposals.SAFE_ID_RE.fullmatch(row_id)), "use a stable non-empty id without spaces"


def payload_identity_diagnostic(
    proposal: foundation_proposals.FoundationProposal,
    operation: dict[str, Any],
    row_id: str,
) -> dict[str, Any] | None:
    operation_name = str(operation.get("operation") or "")
    operation_id = str(operation.get("operation_id") or "unavailable")
    target_path = str(operation.get("target_path") or "unavailable")
    payload = operation.get("payload") if isinstance(operation.get("payload"), dict) else {}
    target = LIBRARY_TARGET_TABLES.get(operation_name)
    if target is None:
        return None
    _relative, field = target
    payload_value = knowledge_library.normalize_text(payload.get(field))
    if not payload_value:
        return operation_diagnostic(
            proposal.proposal_id,
            operation_id,
            operation_name,
            target_path,
            row_id,
            "blocked",
            f"payload must include {field} for {operation_name}",
            reason="payload_identity_missing",
            path=str(proposal.path),
            remediation=f"add payload.{field} so the proposed row can be validated against the target table",
            payload_id_field=field,
        )
    if operation_name in {"upsert_lit_source", "upsert_open_question"} and payload_value != row_id:
        return operation_diagnostic(
            proposal.proposal_id,
            operation_id,
            operation_name,
            target_path,
            row_id,
            "blocked",
            f"payload {field} {payload_value} does not match row_id {row_id}",
            reason="payload_row_id_mismatch",
            path=str(proposal.path),
            remediation=f"set payload.{field} to {row_id}",
            payload_id_field=field,
            payload_row_id=payload_value,
        )
    return None


def source_metadata_warning(
    proposal: foundation_proposals.FoundationProposal,
    operation: dict[str, Any],
    row_id: str,
) -> dict[str, Any] | None:
    payload = operation.get("payload") if isinstance(operation.get("payload"), dict) else {}
    status = knowledge_library.normalize_text(payload.get("status")).lower()
    trust_tier = knowledge_library.normalize_text(payload.get("trust_tier")).lower()
    missing: list[str] = []
    invalid: list[str] = []
    if not knowledge_library.field_has_text(status):
        missing.append("status")
    elif status not in knowledge_library.SOURCE_STATUSES:
        invalid.append("status")
    if not knowledge_library.field_has_text(trust_tier):
        missing.append("trust_tier")
    elif trust_tier not in knowledge_library.TRUST_TIERS:
        invalid.append("trust_tier")
    if not knowledge_library.field_has_value(payload.get("location")):
        missing.append("location")
    if not knowledge_library.field_has_value(payload.get("author_or_publisher")):
        missing.append("author_or_publisher")
    reviewed_date = knowledge_library.normalize_text(payload.get("reviewed_date"))
    if knowledge_library.field_has_value(reviewed_date) and knowledge_library.date_value(reviewed_date) is None:
        invalid.append("reviewed_date")
    operation_id = str(operation.get("operation_id") or "unavailable")
    target_path = str(operation.get("target_path") or "unavailable")
    operation_name = str(operation.get("operation") or "unavailable")
    if invalid:
        return operation_diagnostic(
            proposal.proposal_id,
            operation_id,
            operation_name,
            target_path,
            row_id,
            "blocked",
            f"source payload has invalid fields: {', '.join(invalid)}",
            reason="invalid_library_source_payload",
            path=str(proposal.path),
            remediation="use source_library.md status, trust_tier, and reviewed_date vocabularies",
            invalid_fields=invalid,
        )
    if missing:
        return operation_diagnostic(
            proposal.proposal_id,
            operation_id,
            operation_name,
            target_path,
            row_id,
            "warning",
            f"source payload is missing recommended metadata: {', '.join(missing)}",
            reason="library_source_metadata_missing",
            path=str(proposal.path),
            remediation="add source status, trust tier, location, and provenance before future apply review",
            missing_fields=missing,
        )
    return None


def parse_payload_source_refs(value: Any) -> tuple[list[str], list[str]]:
    if isinstance(value, list):
        tokens = [str(item).strip() for item in value if str(item).strip()]
    else:
        text = knowledge_library.normalize_text(value)
        if text.lower() in knowledge_library.NO_VALUE_MARKERS:
            tokens = []
        else:
            tokens = [token.strip() for token in re.split(r"[\s,;]+", text) if token.strip()]

    refs: list[str] = []
    invalid: list[str] = []
    for token in tokens:
        if knowledge_library.LIT_ID_RE.fullmatch(token):
            refs.append(token)
        else:
            invalid.append(token)
    return refs, invalid


def source_ref_diagnostic(
    proposal: foundation_proposals.FoundationProposal,
    operation: dict[str, Any],
    row_id: str,
    available_source_ids: set[str],
) -> dict[str, Any] | None:
    operation_name = str(operation.get("operation") or "unavailable")
    if operation_name not in SOURCE_REF_OPERATIONS:
        return None
    operation_id = str(operation.get("operation_id") or "unavailable")
    target_path = str(operation.get("target_path") or "unavailable")
    payload = operation.get("payload") if isinstance(operation.get("payload"), dict) else {}
    refs, invalid_refs = parse_payload_source_refs(payload.get("source_refs"))
    if invalid_refs:
        return operation_diagnostic(
            proposal.proposal_id,
            operation_id,
            operation_name,
            target_path,
            row_id,
            "blocked",
            "payload source_refs contains invalid LIT-* references",
            reason="invalid_library_source_ref",
            path=str(proposal.path),
            remediation="use comma, semicolon, space separated, or JSON-array LIT-0000 source refs",
            invalid_source_refs=invalid_refs,
        )
    unresolved = [ref for ref in refs if ref not in available_source_ids]
    if unresolved:
        return operation_diagnostic(
            proposal.proposal_id,
            operation_id,
            operation_name,
            target_path,
            row_id,
            "blocked",
            f"payload source_refs reference missing library sources: {', '.join(unresolved)}",
            reason="unknown_library_source_ref",
            path=str(proposal.path),
            remediation="add the referenced LIT-* sources to source_library.md or include matching upsert_lit_source operations in this proposal",
            unresolved_source_refs=unresolved,
        )
    if operation_name in SOURCE_REF_REQUIRED_OPERATIONS and not refs:
        return operation_diagnostic(
            proposal.proposal_id,
            operation_id,
            operation_name,
            target_path,
            row_id,
            "warning",
            "payload source_refs is empty",
            reason="library_source_refs_missing",
            path=str(proposal.path),
            remediation="add at least one LIT-* source ref before future apply review",
        )
    return None


def claim_payload_diagnostic(
    proposal: foundation_proposals.FoundationProposal,
    operation: dict[str, Any],
    row_id: str,
) -> dict[str, Any] | None:
    payload = operation.get("payload") if isinstance(operation.get("payload"), dict) else {}
    strength = knowledge_library.normalize_text(payload.get("claim_strength")).lower()
    operation_id = str(operation.get("operation_id") or "unavailable")
    target_path = str(operation.get("target_path") or "unavailable")
    if knowledge_library.field_has_value(strength) and strength not in knowledge_library.CLAIM_STRENGTHS:
        return operation_diagnostic(
            proposal.proposal_id,
            operation_id,
            "upsert_claim",
            target_path,
            row_id,
            "blocked",
            "claim_strength is not in the library claim-strength vocabulary",
            reason="invalid_library_claim_strength",
            path=str(proposal.path),
            remediation="use one of none, weak, suggestive, moderate, or strong",
            claim_strength=strength,
        )
    disputed = knowledge_library.normalize_text(payload.get("disputed_status")).lower()
    needs_caveat = strength in {"moderate", "strong"} or disputed in knowledge_library.RISKY_SOURCE_STATUSES
    if needs_caveat and not knowledge_library.field_has_value(payload.get("caveats")):
        return operation_diagnostic(
            proposal.proposal_id,
            operation_id,
            "upsert_claim",
            target_path,
            row_id,
            "warning",
            "moderate, strong, disputed, deprecated, or context-only claims should include caveats",
            reason="library_claim_without_caveats",
            path=str(proposal.path),
            remediation="add payload.caveats before future apply review",
        )
    return None


def update_log_warning(
    proposal: foundation_proposals.FoundationProposal,
    operation: dict[str, Any],
    row_id: str,
) -> dict[str, Any] | None:
    payload = operation.get("payload") if isinstance(operation.get("payload"), dict) else {}
    task_id = knowledge_library.normalize_text(payload.get("task_id"))
    approver = knowledge_library.normalize_text(payload.get("reviewer_or_approver"))
    operation_id = str(operation.get("operation_id") or "unavailable")
    target_path = str(operation.get("target_path") or "unavailable")
    if knowledge_library.field_has_value(task_id) and not knowledge_library.TASK_ID_RE.fullmatch(task_id):
        return operation_diagnostic(
            proposal.proposal_id,
            operation_id,
            "append_library_update_log",
            target_path,
            row_id,
            "warning",
            "task_id should use TASK-0000 format",
            reason="library_update_log_task_id_invalid",
            path=str(proposal.path),
            remediation="use the source task id without slug in payload.task_id",
            task_id=task_id,
        )
    if not knowledge_library.field_has_value(task_id) and not knowledge_library.field_has_value(approver):
        return operation_diagnostic(
            proposal.proposal_id,
            operation_id,
            "append_library_update_log",
            target_path,
            row_id,
            "warning",
            "update log payload should include task ID or reviewer/approver provenance",
            reason="library_update_log_missing_provenance",
            path=str(proposal.path),
            remediation="add payload.task_id or payload.reviewer_or_approver before future apply review",
        )
    return None


def proposed_source_ids(proposal: foundation_proposals.FoundationProposal) -> set[str]:
    source_ids: set[str] = set()
    for operation in proposal.operations:
        if operation.get("operation") != "upsert_lit_source":
            continue
        row_id = knowledge_library.normalize_text(operation.get("row_id"))
        if knowledge_library.LIT_ID_RE.fullmatch(row_id):
            source_ids.add(row_id)
    return source_ids


def existing_conflict(
    operation_name: str,
    row_id: str,
    operation: dict[str, Any],
    existing: dict[str, set[str]],
) -> str | None:
    values = existing_values_for_operation(operation_name, existing)
    payload = operation.get("payload") if isinstance(operation.get("payload"), dict) else {}
    target = LIBRARY_TARGET_TABLES.get(operation_name)
    if target is None:
        return None
    _relative, field = target
    payload_value = knowledge_library.normalize_text(payload.get(field))
    if row_id in values:
        return row_id
    if payload_value in values:
        return payload_value
    return None


def inspect_operation(
    proposal: foundation_proposals.FoundationProposal,
    operation: dict[str, Any],
    ops_dir: Path,
    existing: dict[str, set[str]],
    seen_row_keys: set[tuple[str, str, str]],
    available_source_ids: set[str],
) -> dict[str, Any]:
    operation_id = str(operation.get("operation_id") or "unavailable")
    operation_name = str(operation.get("operation") or "unavailable")
    target_path = str(operation.get("target_path") or "unavailable")
    row_id = str(operation.get("row_id") or "unavailable")

    if operation_name not in foundation_proposals.LIBRARY_OPERATIONS:
        return operation_diagnostic(
            proposal.proposal_id,
            operation_id,
            operation_name,
            target_path,
            row_id,
            "blocked",
            f"operation {operation_name} is not a library operation",
            reason="non_library_operation",
            path=str(proposal.path),
            remediation="use only library operations with target=library",
        )

    valid_row, row_remediation = validate_row_id(operation_name, row_id, existing)
    if not valid_row:
        return operation_diagnostic(
            proposal.proposal_id,
            operation_id,
            operation_name,
            target_path,
            row_id,
            "blocked",
            f"row_id {row_id} is not valid for {operation_name}",
            reason="invalid_library_row_id",
            path=str(proposal.path),
            remediation=row_remediation,
        )

    expected = expected_target_path(operation_name)
    if target_path != expected:
        return operation_diagnostic(
            proposal.proposal_id,
            operation_id,
            operation_name,
            target_path,
            row_id,
            "blocked",
            f"target_path {target_path} does not match canonical library target {expected}",
            reason="unexpected_library_target_path",
            path=str(proposal.path),
            remediation=f"set target_path to {expected}",
            expected_target_path=expected,
        )

    resolved_target = safe_resolve_library_target(ops_dir, target_path)
    if resolved_target is None:
        return operation_diagnostic(
            proposal.proposal_id,
            operation_id,
            operation_name,
            target_path,
            row_id,
            "blocked",
            f"target_path {target_path} resolves outside {ops_dir / knowledge_library.LIBRARY_DIR}",
            reason="target_path_outside_library",
            path=str(proposal.path),
            remediation="use a canonical research_ops-relative library target path",
        )
    if not resolved_target.exists():
        return operation_diagnostic(
            proposal.proposal_id,
            operation_id,
            operation_name,
            target_path,
            row_id,
            "blocked",
            "target knowledge library file is missing",
            reason="target_file_missing",
            path=str(resolved_target),
            remediation="restore the canonical knowledge library file before proposing updates",
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

    for check in (
        payload_identity_diagnostic,
        source_ref_diagnostic,
        claim_payload_diagnostic if operation_name == "upsert_claim" else None,
        source_metadata_warning if operation_name == "upsert_lit_source" else None,
        update_log_warning if operation_name == "append_library_update_log" else None,
    ):
        if check is None:
            continue
        if check is source_ref_diagnostic:
            diagnostic = check(proposal, operation, row_id, available_source_ids)
        else:
            diagnostic = check(proposal, operation, row_id)
        if diagnostic is not None:
            return diagnostic

    conflict_key = existing_conflict(operation_name, row_id, operation, existing)
    if conflict_key is not None:
        return operation_diagnostic(
            proposal.proposal_id,
            operation_id,
            operation_name,
            target_path,
            row_id,
            "warning",
            f"upsert would replace existing library row {conflict_key} in {target_path}",
            reason="existing_row_upsert",
            path=str(resolved_target),
            remediation="review the existing row and preserve manual notes before any future apply step",
            existing_row_key=conflict_key,
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


def inspect_library_proposals(ops_dir: Path, proposal_source: Path) -> dict[str, Any]:
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

    source_relative = str(Path(knowledge_library.LIBRARY_DIR) / knowledge_library.SOURCE_LIBRARY_FILE)
    existing_source_ids = existing.get(source_relative, set())
    for proposal in parse_result.proposals:
        proposal_blocked = bool(workspace_blockers)
        if proposal.target != "library":
            proposal_blocked = True
            diagnostic = operation_diagnostic(
                proposal.proposal_id,
                "proposal",
                "inspect_proposal",
                "proposal",
                "proposal",
                "blocked",
                f"proposal target {proposal.target} is not library",
                reason="non_library_proposal_target",
                path=str(proposal.path),
                remediation="inspect data proposals with the data proposal command",
            )
            operations.append(diagnostic)
            blockers.append(diagnostic)
        seen_row_keys: set[tuple[str, str, str]] = set()
        available_source_ids = existing_source_ids | proposed_source_ids(proposal)
        if not workspace_blockers and proposal.target == "library":
            for operation in proposal.operations:
                diagnostic = inspect_operation(
                    proposal,
                    operation,
                    ops_dir,
                    existing,
                    seen_row_keys,
                    available_source_ids,
                )
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
        return ["Fix blocked proposal diagnostics and rerun library inspect-proposals."]
    if warnings:
        return ["Review warnings before routing the accepted proposal to library apply-proposals --dry-run."]
    return ["Proposal diagnostics are clean for library review; no files were changed."]


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect knowledge library proposals without mutating research_ops.")
    parser.add_argument("ops_dir", type=Path, help="Path to the research_ops workspace.")
    parser.add_argument(
        "proposal_source",
        type=Path,
        help="Task directory, worker_output.md, JSON proposal artifact, or directory containing proposal artifacts.",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    payload = inspect_library_proposals(args.ops_dir, args.proposal_source)
    print_json(payload)
    return SUCCESS if payload["ok"] else MALFORMED


if __name__ == "__main__":
    raise SystemExit(main())
