#!/usr/bin/env python3
"""Parse and validate foundation update proposal artifacts."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any, Iterable


SUCCESS = 0
MALFORMED = 4

PROPOSAL_VERSION = "foundation_update_proposal_v1"
ALLOWED_TARGETS = {"data", "library"}

DATA_OPERATION_TARGET_PATHS = {
    "upsert_data_source": "data_source_audit.md",
    "upsert_data_profile": "data/profiles/{row_id}.md",
    "upsert_data_catalog_row": "data/data_catalog.md",
    "upsert_data_access_row": "data/data_access.md",
    "upsert_join_map_row": "data/join_map.md",
    "upsert_known_data_gap": "data/known_data_gaps.md",
}
LIBRARY_OPERATION_TARGET_PATHS = {
    "upsert_lit_source": "library/source_library.md",
    "upsert_topic_summary": "library/knowledge_index.md",
    "upsert_claim": "library/claim_map.md",
    "upsert_method": "library/method_index.md",
    "upsert_open_question": "library/open_questions.md",
    "append_library_update_log": "library/library_update_log.md",
}
OPERATION_TARGET_PATHS = {
    **DATA_OPERATION_TARGET_PATHS,
    **LIBRARY_OPERATION_TARGET_PATHS,
}
DATA_OPERATIONS = set(DATA_OPERATION_TARGET_PATHS)
LIBRARY_OPERATIONS = set(LIBRARY_OPERATION_TARGET_PATHS)
ALLOWED_OPERATIONS = DATA_OPERATIONS | LIBRARY_OPERATIONS

ENVELOPE_REQUIRED_FIELDS = (
    "proposal_version",
    "proposal_id",
    "source_task_id",
    "target",
    "created_by",
    "rationale",
    "operations",
)
OPERATION_REQUIRED_FIELDS = (
    "operation_id",
    "operation",
    "target_path",
    "row_id",
    "payload",
    "preserve_manual_notes",
)

PROPOSAL_ID_RE = re.compile(r"^PROP-[0-9]{4}(?:-[A-Za-z0-9][A-Za-z0-9_-]*)?$")
TASK_ID_RE = re.compile(r"^TASK-[0-9]{4}(?:-[A-Za-z0-9][A-Za-z0-9_-]*)?$")
DS_ID_RE = re.compile(r"^DS-[0-9]{4}$")
DG_ID_RE = re.compile(r"^DG-[0-9]{4}$")
LIT_ID_RE = re.compile(r"^LIT-[0-9]{4}$")
SAFE_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]*$")


@dataclass(frozen=True)
class ProposalCandidate:
    path: Path
    source_type: str
    data: Any
    location: str | None = None


@dataclass(frozen=True)
class FoundationProposal:
    path: Path
    source_type: str
    proposal_id: str
    source_task_id: str
    target: str
    created_by: str
    rationale: str
    operations: tuple[dict[str, Any], ...]
    raw: dict[str, Any]
    location: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "path": str(self.path),
            "source_type": self.source_type,
            "proposal_id": self.proposal_id,
            "source_task_id": self.source_task_id,
            "target": self.target,
            "created_by": self.created_by,
            "rationale": self.rationale,
            "operation_count": len(self.operations),
            "operations": list(self.operations),
        }
        if self.location is not None:
            payload["location"] = self.location
        return payload


@dataclass(frozen=True)
class ProposalParseResult:
    proposals: tuple[FoundationProposal, ...]
    diagnostics: tuple[dict[str, Any], ...]

    @property
    def ok(self) -> bool:
        return not any(item.get("severity") == "error" for item in self.diagnostics)

    @property
    def error_count(self) -> int:
        return sum(1 for item in self.diagnostics if item.get("severity") == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for item in self.diagnostics if item.get("severity") == "warning")

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "proposal_version": PROPOSAL_VERSION,
            "proposal_count": len(self.proposals),
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "proposals": [proposal.to_dict() for proposal in self.proposals],
            "diagnostics": list(self.diagnostics),
        }


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def diagnostic(
    severity: str,
    reason: str,
    path: Path,
    message: str,
    remediation: str,
    *,
    proposal_id: str | None = None,
    operation_id: str | None = None,
    location: str | None = None,
    **details: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "severity": severity,
        "reason": reason,
        "path": str(path),
        "message": message,
        "remediation": remediation,
    }
    if proposal_id:
        payload["proposal_id"] = proposal_id
    if operation_id:
        payload["operation_id"] = operation_id
    if location:
        payload["location"] = location
    payload.update(details)
    return payload


def _string_field(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _operation_target(operation: str) -> str | None:
    if operation in DATA_OPERATIONS:
        return "data"
    if operation in LIBRARY_OPERATIONS:
        return "library"
    return None


def _safe_relative_target_path(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or "\\" in text:
        return None
    path = PurePosixPath(text)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        return None
    return path.as_posix()


def _expected_target_path(operation: str, row_id: str | None) -> str | None:
    template = OPERATION_TARGET_PATHS.get(operation)
    if template is None:
        return None
    if "{row_id}" in template:
        if row_id is None:
            return None
        return template.format(row_id=row_id)
    return template


def _row_id_valid(operation: str, row_id: str) -> tuple[bool, str]:
    if operation in {
        "upsert_data_source",
        "upsert_data_profile",
        "upsert_data_catalog_row",
        "upsert_data_access_row",
    }:
        return bool(DS_ID_RE.fullmatch(row_id)), "use a governed DS-0000 source id"
    if operation == "upsert_known_data_gap":
        return bool(DG_ID_RE.fullmatch(row_id)), "use a DG-0000 known data gap id"
    if operation == "upsert_lit_source":
        return bool(LIT_ID_RE.fullmatch(row_id)), "use a library LIT-0000 source id"
    return bool(SAFE_ID_RE.fullmatch(row_id)), "use a stable non-empty id without spaces"


def _json_candidates(path: Path) -> tuple[list[ProposalCandidate], list[dict[str, Any]]]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return [], [
            diagnostic(
                "error",
                "proposal_file_missing",
                path,
                f"{path} does not exist",
                "provide an existing proposal JSON file or worker_output.md file",
            )
        ]
    except OSError as exc:
        return [], [
            diagnostic(
                "error",
                "proposal_file_read_failed",
                path,
                f"cannot read proposal file: {exc}",
                "fix file permissions or rerun with a readable file",
            )
        ]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return [], [
            diagnostic(
                "error",
                "malformed_json",
                path,
                f"proposal JSON is malformed at line {exc.lineno}, column {exc.colno}: {exc.msg}",
                "write valid JSON using the foundation_update_proposal_v1 envelope",
                location=f"line {exc.lineno}",
            )
        ]
    return [ProposalCandidate(path=path, source_type="json_artifact", data=data)], []


def _is_closing_fence(line: str, fence_char: str, fence_len: int) -> bool:
    stripped = line.strip()
    return stripped.startswith(fence_char * fence_len) and set(stripped) <= {fence_char}


def _markdown_candidates(path: Path) -> tuple[list[ProposalCandidate], list[dict[str, Any]]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return [], [
            diagnostic(
                "error",
                "proposal_file_missing",
                path,
                f"{path} does not exist",
                "provide an existing proposal JSON file or worker_output.md file",
            )
        ]
    except OSError as exc:
        return [], [
            diagnostic(
                "error",
                "proposal_file_read_failed",
                path,
                f"cannot read proposal file: {exc}",
                "fix file permissions or rerun with a readable file",
            )
        ]

    candidates: list[ProposalCandidate] = []
    diagnostics: list[dict[str, Any]] = []
    in_block = False
    info = ""
    fence_char = ""
    fence_len = 0
    block_lines: list[str] = []
    start_line = 0

    for line_number, line in enumerate(lines, start=1):
        stripped = line.lstrip()
        if not in_block:
            match = re.match(r"(`{3,}|~{3,})(.*)$", stripped)
            if match is None:
                continue
            fence = match.group(1)
            in_block = True
            info = match.group(2).strip()
            fence_char = fence[0]
            fence_len = len(fence)
            block_lines = []
            start_line = line_number
            continue
        if _is_closing_fence(stripped, fence_char, fence_len):
            if PROPOSAL_VERSION in info:
                block_text = "\n".join(block_lines)
                try:
                    data = json.loads(block_text)
                except json.JSONDecodeError as exc:
                    diagnostics.append(
                        diagnostic(
                            "error",
                            "malformed_json",
                            path,
                            f"fenced proposal JSON is malformed at line {start_line + exc.lineno}, column {exc.colno}: {exc.msg}",
                            "write valid JSON inside the fenced foundation_update_proposal_v1 block",
                            location=f"line {start_line}",
                        )
                    )
                else:
                    candidates.append(
                        ProposalCandidate(
                            path=path,
                            source_type="worker_output_fence",
                            data=data,
                            location=f"line {start_line}",
                        )
                    )
            in_block = False
            info = ""
            fence_char = ""
            fence_len = 0
            block_lines = []
            start_line = 0
            continue
        block_lines.append(line)

    if in_block and PROPOSAL_VERSION in info:
        diagnostics.append(
            diagnostic(
                "error",
                "unterminated_proposal_fence",
                path,
                f"foundation proposal fence opened at line {start_line} has no closing fence",
                "close the fenced code block before submitting the worker output",
                location=f"line {start_line}",
            )
        )
    return candidates, diagnostics


def _validate_operation(
    operation: Any,
    *,
    index: int,
    proposal_id: str | None,
    proposal_target: str | None,
    path: Path,
    location: str | None,
    seen_operation_ids: set[str],
) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    if not isinstance(operation, dict):
        return [
            diagnostic(
                "error",
                "invalid_operation_object",
                path,
                f"operation at index {index} must be an object",
                "replace the operation entry with an object containing operation_id, operation, target_path, row_id, payload, and preserve_manual_notes",
                proposal_id=proposal_id,
                location=location,
                operation_index=index,
            )
        ]

    operation_id = _string_field(operation.get("operation_id"))
    operation_name = _string_field(operation.get("operation"))
    row_id = _string_field(operation.get("row_id"))
    target_path = _safe_relative_target_path(operation.get("target_path"))

    for field in OPERATION_REQUIRED_FIELDS:
        if field not in operation:
            diagnostics.append(
                diagnostic(
                    "error",
                    "missing_operation_field",
                    path,
                    f"operation at index {index} is missing required field {field}",
                    f"add {field} to the operation object",
                    proposal_id=proposal_id,
                    operation_id=operation_id,
                    location=location,
                    field=field,
                    operation_index=index,
                )
            )

    if operation_id is None:
        diagnostics.append(
            diagnostic(
                "error",
                "invalid_operation_id",
                path,
                f"operation at index {index} must have a non-empty string operation_id",
                "set operation_id to a stable id such as OP-0001",
                proposal_id=proposal_id,
                location=location,
                operation_index=index,
            )
        )
    elif not SAFE_ID_RE.fullmatch(operation_id):
        diagnostics.append(
            diagnostic(
                "error",
                "invalid_operation_id",
                path,
                f"operation_id {operation_id} is not a safe id",
                "use letters, numbers, dashes, underscores, dots, or colons, and start with a letter",
                proposal_id=proposal_id,
                operation_id=operation_id,
                location=location,
            )
        )
    elif operation_id in seen_operation_ids:
        diagnostics.append(
            diagnostic(
                "error",
                "duplicate_operation_id",
                path,
                f"operation_id {operation_id} appears more than once in proposal {proposal_id or '<unknown>'}",
                "make operation_id values unique within the proposal",
                proposal_id=proposal_id,
                operation_id=operation_id,
                location=location,
            )
        )
    else:
        seen_operation_ids.add(operation_id)

    if operation_name is None:
        diagnostics.append(
            diagnostic(
                "error",
                "invalid_operation_name",
                path,
                f"operation at index {index} must have a non-empty string operation",
                "set operation to one of the v1 data or library operation names",
                proposal_id=proposal_id,
                operation_id=operation_id,
                location=location,
                operation_index=index,
            )
        )
    elif operation_name not in ALLOWED_OPERATIONS:
        diagnostics.append(
            diagnostic(
                "error",
                "unknown_operation",
                path,
                f"operation {operation_name} is not supported by foundation_update_proposal_v1",
                "use one of the allowed v1 data or library operation names",
                proposal_id=proposal_id,
                operation_id=operation_id,
                location=location,
                operation=operation_name,
            )
        )
    elif proposal_target in ALLOWED_TARGETS and _operation_target(operation_name) != proposal_target:
        diagnostics.append(
            diagnostic(
                "error",
                "operation_target_mismatch",
                path,
                f"operation {operation_name} is not valid for target {proposal_target}",
                "use data operations only with target=data and library operations only with target=library",
                proposal_id=proposal_id,
                operation_id=operation_id,
                location=location,
                operation=operation_name,
            )
        )

    if row_id is None:
        diagnostics.append(
            diagnostic(
                "error",
                "invalid_row_id",
                path,
                f"operation at index {index} must have a non-empty string row_id",
                "set row_id to the durable row identifier this operation proposes to upsert",
                proposal_id=proposal_id,
                operation_id=operation_id,
                location=location,
                operation_index=index,
            )
        )
    elif operation_name in ALLOWED_OPERATIONS:
        valid, remediation = _row_id_valid(operation_name, row_id)
        if not valid:
            diagnostics.append(
                diagnostic(
                    "error",
                    "invalid_row_id",
                    path,
                    f"row_id {row_id} is not valid for operation {operation_name}",
                    remediation,
                    proposal_id=proposal_id,
                    operation_id=operation_id,
                    location=location,
                    row_id=row_id,
                    operation=operation_name,
                )
            )

    if target_path is None:
        diagnostics.append(
            diagnostic(
                "error",
                "invalid_target_path",
                path,
                f"operation at index {index} must use a safe relative POSIX target_path",
                "use a workspace-relative path without leading slash, backslashes, dot segments, or ..",
                proposal_id=proposal_id,
                operation_id=operation_id,
                location=location,
                operation_index=index,
            )
        )
    elif operation_name in ALLOWED_OPERATIONS:
        expected = _expected_target_path(operation_name, row_id)
        if expected is not None and target_path != expected:
            diagnostics.append(
                diagnostic(
                    "error",
                    "unexpected_target_path",
                    path,
                    f"operation {operation_name} targets {target_path}, expected {expected}",
                    "set target_path to the canonical file for this operation",
                    proposal_id=proposal_id,
                    operation_id=operation_id,
                    location=location,
                    operation=operation_name,
                    target_path=target_path,
                    expected_target_path=expected,
                )
            )

    if not isinstance(operation.get("payload"), dict):
        diagnostics.append(
            diagnostic(
                "error",
                "invalid_payload",
                path,
                f"operation {operation_id or f'at index {index}'} must include a payload object",
                "set payload to an object whose keys match the target table or profile contract",
                proposal_id=proposal_id,
                operation_id=operation_id,
                location=location,
            )
        )

    if not isinstance(operation.get("preserve_manual_notes"), bool):
        diagnostics.append(
            diagnostic(
                "error",
                "invalid_preserve_manual_notes",
                path,
                f"operation {operation_id or f'at index {index}'} must set preserve_manual_notes to true or false",
                "choose whether later apply tooling must preserve human-maintained notes",
                proposal_id=proposal_id,
                operation_id=operation_id,
                location=location,
            )
        )
    return diagnostics


def _validate_candidate(candidate: ProposalCandidate) -> tuple[FoundationProposal | None, list[dict[str, Any]]]:
    path = candidate.path
    data = candidate.data
    diagnostics: list[dict[str, Any]] = []
    if not isinstance(data, dict):
        return None, [
            diagnostic(
                "error",
                "invalid_proposal_object",
                path,
                "foundation proposal must be a JSON object",
                "wrap the v1 envelope in a single JSON object",
                location=candidate.location,
            )
        ]

    proposal_id = _string_field(data.get("proposal_id"))
    target = _string_field(data.get("target"))

    for field in ENVELOPE_REQUIRED_FIELDS:
        if field not in data:
            diagnostics.append(
                diagnostic(
                    "error",
                    "missing_proposal_field",
                    path,
                    f"proposal is missing required field {field}",
                    f"add {field} to the foundation_update_proposal_v1 envelope",
                    proposal_id=proposal_id,
                    location=candidate.location,
                    field=field,
                )
            )

    if data.get("proposal_version") != PROPOSAL_VERSION:
        diagnostics.append(
            diagnostic(
                "error",
                "invalid_proposal_version",
                path,
                f"proposal_version must be {PROPOSAL_VERSION}",
                "set proposal_version exactly to foundation_update_proposal_v1",
                proposal_id=proposal_id,
                location=candidate.location,
            )
        )

    if proposal_id is None:
        diagnostics.append(
            diagnostic(
                "error",
                "invalid_proposal_id",
                path,
                "proposal_id must be a non-empty string",
                "set proposal_id to a stable id such as PROP-0001",
                location=candidate.location,
            )
        )
    elif not PROPOSAL_ID_RE.fullmatch(proposal_id):
        diagnostics.append(
            diagnostic(
                "error",
                "invalid_proposal_id",
                path,
                f"proposal_id {proposal_id} does not match PROP-0000",
                "use a proposal id such as PROP-0001, optionally followed by a slug",
                proposal_id=proposal_id,
                location=candidate.location,
            )
        )

    source_task_id = _string_field(data.get("source_task_id"))
    if source_task_id is None:
        diagnostics.append(
            diagnostic(
                "error",
                "invalid_source_task_id",
                path,
                "source_task_id must be a non-empty string",
                "set source_task_id to the source task id, such as TASK-0001-example",
                proposal_id=proposal_id,
                location=candidate.location,
            )
        )
    elif not TASK_ID_RE.fullmatch(source_task_id):
        diagnostics.append(
            diagnostic(
                "error",
                "invalid_source_task_id",
                path,
                f"source_task_id {source_task_id} does not match TASK-0000 or TASK-0000-slug",
                "use the durable task id or task directory prefix",
                proposal_id=proposal_id,
                location=candidate.location,
                source_task_id=source_task_id,
            )
        )

    if target not in ALLOWED_TARGETS:
        diagnostics.append(
            diagnostic(
                "error",
                "invalid_target",
                path,
                f"target must be one of {sorted(ALLOWED_TARGETS)}",
                "set target to data or library",
                proposal_id=proposal_id,
                location=candidate.location,
                target=target,
            )
        )

    created_by = _string_field(data.get("created_by"))
    if created_by is None:
        diagnostics.append(
            diagnostic(
                "error",
                "invalid_created_by",
                path,
                "created_by must be a non-empty string",
                "set created_by to the proposal author role, such as worker",
                proposal_id=proposal_id,
                location=candidate.location,
            )
        )

    rationale = _string_field(data.get("rationale"))
    if rationale is None:
        diagnostics.append(
            diagnostic(
                "error",
                "invalid_rationale",
                path,
                "rationale must be a non-empty string",
                "explain why these foundation rows should change",
                proposal_id=proposal_id,
                location=candidate.location,
            )
        )

    operations = data.get("operations")
    if not isinstance(operations, list):
        diagnostics.append(
            diagnostic(
                "error",
                "invalid_operations",
                path,
                "operations must be a list",
                "set operations to a list of proposal operation objects",
                proposal_id=proposal_id,
                location=candidate.location,
            )
        )
        operations = []

    seen_operation_ids: set[str] = set()
    for index, operation in enumerate(operations):
        diagnostics.extend(
            _validate_operation(
                operation,
                index=index,
                proposal_id=proposal_id,
                proposal_target=target,
                path=path,
                location=candidate.location,
                seen_operation_ids=seen_operation_ids,
            )
        )

    if diagnostics:
        return None, diagnostics
    assert proposal_id is not None
    assert source_task_id is not None
    assert target is not None
    assert created_by is not None
    assert rationale is not None
    return (
        FoundationProposal(
            path=path,
            source_type=candidate.source_type,
            proposal_id=proposal_id,
            source_task_id=source_task_id,
            target=target,
            created_by=created_by,
            rationale=rationale,
            operations=tuple(dict(operation) for operation in operations),
            raw=dict(data),
            location=candidate.location,
        ),
        [],
    )


def _reject_duplicate_proposal_ids(
    proposals: list[FoundationProposal],
    diagnostics: list[dict[str, Any]],
) -> tuple[list[FoundationProposal], list[dict[str, Any]]]:
    by_id: dict[str, list[FoundationProposal]] = {}
    for proposal in proposals:
        by_id.setdefault(proposal.proposal_id, []).append(proposal)

    duplicate_ids = {proposal_id for proposal_id, items in by_id.items() if len(items) > 1}
    for proposal_id in sorted(duplicate_ids):
        items = by_id[proposal_id]
        paths = [str(item.path) for item in items]
        same_file = len({str(item.path) for item in items}) == 1
        reason = "duplicate_proposal_id_in_file" if same_file else "duplicate_proposal_id"
        for item in items:
            diagnostics.append(
                diagnostic(
                    "error",
                    reason,
                    item.path,
                    f"proposal_id {proposal_id} appears more than once",
                    "make proposal_id unique so reviewers can reference one unambiguous proposal",
                    proposal_id=proposal_id,
                    location=item.location,
                    duplicate_paths=paths,
                )
            )
    return [item for item in proposals if item.proposal_id not in duplicate_ids], diagnostics


def _candidate_json_artifact(path: Path) -> bool:
    if "proposal" in path.name.lower():
        return True
    try:
        return PROPOSAL_VERSION in path.read_text(encoding="utf-8")
    except OSError:
        return False


def load_proposal_paths(paths: Iterable[Path]) -> ProposalParseResult:
    candidates: list[ProposalCandidate] = []
    diagnostics: list[dict[str, Any]] = []
    for path in paths:
        if path.suffix.lower() == ".json":
            found, issues = _json_candidates(path)
        elif path.suffix.lower() in {".md", ".markdown"}:
            found, issues = _markdown_candidates(path)
        else:
            found, issues = [], [
                diagnostic(
                    "error",
                    "unsupported_proposal_document",
                    path,
                    f"{path} is not a supported proposal document",
                    "use a standalone .json proposal artifact or a worker_output.md file with a fenced v1 block",
                )
            ]
        candidates.extend(found)
        diagnostics.extend(issues)

    proposals: list[FoundationProposal] = []
    for candidate in candidates:
        proposal, issues = _validate_candidate(candidate)
        diagnostics.extend(issues)
        if proposal is not None:
            proposals.append(proposal)
    proposals, diagnostics = _reject_duplicate_proposal_ids(proposals, diagnostics)
    return ProposalParseResult(proposals=tuple(proposals), diagnostics=tuple(diagnostics))


def discover_task_proposals(task_dir: Path) -> ProposalParseResult:
    paths: list[Path] = []
    worker_output = task_dir / "worker_output.md"
    if worker_output.exists():
        paths.append(worker_output)
    artifacts_dir = task_dir / "artifacts"
    if artifacts_dir.exists():
        paths.extend(path for path in sorted(artifacts_dir.rglob("*.json")) if _candidate_json_artifact(path))
    return load_proposal_paths(paths)


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only validation for foundation_update_proposal_v1 artifacts.")
    parser.add_argument("paths", nargs="*", type=Path, help="Proposal JSON files or worker_output.md files to inspect.")
    parser.add_argument("--task-dir", type=Path, help="Discover proposal artifacts under one task directory.")
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    if args.task_dir and args.paths:
        print_json(
            {
                "ok": False,
                "proposal_version": PROPOSAL_VERSION,
                "proposal_count": 0,
                "error_count": 1,
                "warning_count": 0,
                "proposals": [],
                "diagnostics": [
                    diagnostic(
                        "error",
                        "conflicting_inputs",
                        args.task_dir,
                        "pass either --task-dir or explicit paths, not both",
                        "rerun with one input mode",
                    )
                ],
            }
        )
        return MALFORMED
    result = discover_task_proposals(args.task_dir) if args.task_dir else load_proposal_paths(args.paths)
    print_json(result.to_dict())
    return SUCCESS if result.ok else MALFORMED


if __name__ == "__main__":
    raise SystemExit(main())
