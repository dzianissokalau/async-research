#!/usr/bin/env python3
"""Validate and summarize runtime evidence objects and trace ledgers."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
from typing import Any, Iterable

from async_research_workflow.resources import schema_path
from async_research_workflow.scripts.validate_json_artifact import load_json
from async_research_workflow.scripts.validate_json_artifact import validate


SUCCESS = 0
VALIDATION_FINDINGS = 2
INVALID_REQUEST = 3
MALFORMED = 4

RUNTIME_DIR = Path("runtime")
TRACE_LEDGER = RUNTIME_DIR / "traces.jsonl"
EVIDENCE_LEDGER = RUNTIME_DIR / "evidence_objects.jsonl"
SNAPSHOTS_DIR = RUNTIME_DIR / "snapshots"

EVIDENCE_SCHEMA_NAME = "runtime_evidence_object.schema.json"
TRACE_SCHEMA_NAME = "runtime_trace.schema.json"
NO_VALUE_MARKERS = {"", "unknown", "missing", "none", "n/a", "na", "todo", "tbd"}
TRACE_SUCCESS_CODES = {"0", "success", "ok", "dry_run", "blocked_by_policy"}
WEB_ADAPTERS = {"web_search", "web_open"}


@dataclass
class LedgerEntry:
    kind: str
    path: Path
    line_number: int
    payload: dict[str, Any]


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def issue(
    severity: str,
    reason: str,
    path: Path,
    message: str,
    *,
    line_number: int | None = None,
    evidence_id: str | None = None,
    trace_id: str | None = None,
    field: str | None = None,
    expected: Any = None,
    actual: Any = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "severity": severity,
        "reason": reason,
        "path": str(path),
        "message": message,
    }
    if line_number is not None:
        payload["line_number"] = line_number
    if evidence_id:
        payload["evidence_id"] = evidence_id
    if trace_id:
        payload["trace_id"] = trace_id
    if field:
        payload["field"] = field
    if expected is not None:
        payload["expected"] = expected
    if actual is not None:
        payload["actual"] = actual
    return payload


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


def parse_timestamp(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def workspace_path(ops_dir: Path, path_text: Any) -> Path | None:
    if not isinstance(path_text, str):
        return None
    posix = PurePosixPath(path_text)
    if posix.is_absolute() or not posix.parts:
        return None
    if posix.parts[0] != "research_ops":
        return None
    if any(part in {"", ".", ".."} for part in posix.parts):
        return None
    candidate = (ops_dir.parent / Path(*posix.parts)).resolve(strict=False)
    try:
        candidate.relative_to(ops_dir.resolve(strict=False))
    except ValueError:
        return None
    return candidate


def task_exists(ops_dir: Path, task_id: Any) -> bool:
    if not isinstance(task_id, str):
        return False
    tasks_dir = ops_dir / "tasks"
    if not tasks_dir.is_dir():
        return False
    if (tasks_dir / task_id).is_dir():
        return True
    return any(path.is_dir() for path in tasks_dir.glob(f"{task_id}-*"))


def sha256_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def read_jsonl(path: Path, kind: str, errors: list[dict[str, Any]]) -> list[LedgerEntry]:
    if not path.exists():
        return []
    entries: list[LedgerEntry] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        errors.append(issue("error", "ledger_read_failed", path, f"cannot read {path}: {exc}"))
        return entries
    for index, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(
                issue(
                    "error",
                    "malformed_jsonl",
                    path,
                    f"line is not valid JSON: {exc.msg}",
                    line_number=index,
                )
            )
            continue
        if not isinstance(payload, dict):
            errors.append(
                issue(
                    "error",
                    "jsonl_entry_not_object",
                    path,
                    "runtime ledger entries must be JSON objects",
                    line_number=index,
                )
            )
            continue
        entries.append(LedgerEntry(kind=kind, path=path, line_number=index, payload=payload))
    return entries


def validate_against_schema(entry: LedgerEntry, schema: dict[str, Any], errors: list[dict[str, Any]]) -> None:
    for error in validate(entry.payload, schema):
        errors.append(
            issue(
                "error",
                "schema_validation_failed",
                entry.path,
                error.message,
                line_number=entry.line_number,
                evidence_id=entry.payload.get("evidence_id"),
                trace_id=entry.payload.get("trace_id"),
                field=error.path,
            )
        )


def validate_task_link(entry: LedgerEntry, ops_dir: Path, errors: list[dict[str, Any]]) -> None:
    task_id = entry.payload.get("task_id")
    if isinstance(task_id, str) and task_exists(ops_dir, task_id):
        return
    errors.append(
        issue(
            "error",
            "task_link_missing",
            entry.path,
            "runtime artifact task_id must link to an existing research_ops/tasks entry",
            line_number=entry.line_number,
            evidence_id=entry.payload.get("evidence_id"),
            trace_id=entry.payload.get("trace_id"),
            field="task_id",
            actual=task_id,
        )
    )


def validate_runtime_path(
    entry: LedgerEntry,
    ops_dir: Path,
    field: str,
    value: Any,
    errors: list[dict[str, Any]],
    *,
    must_exist: bool,
) -> Path | None:
    resolved = workspace_path(ops_dir, value)
    if resolved is None:
        errors.append(
            issue(
                "error",
                "path_outside_research_ops",
                entry.path,
                "runtime artifact paths must be relative paths under research_ops/",
                line_number=entry.line_number,
                evidence_id=entry.payload.get("evidence_id"),
                trace_id=entry.payload.get("trace_id"),
                field=field,
                actual=value,
            )
        )
        return None
    if must_exist and not resolved.is_file():
        errors.append(
            issue(
                "error",
                "artifact_missing",
                entry.path,
                "runtime evidence snapshot_path must point to an existing file",
                line_number=entry.line_number,
                evidence_id=entry.payload.get("evidence_id"),
                trace_id=entry.payload.get("trace_id"),
                field=field,
                actual=value,
            )
        )
        return None
    return resolved


def validate_evidence_entry(
    entry: LedgerEntry,
    ops_dir: Path,
    schema: dict[str, Any],
    errors: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> None:
    validate_against_schema(entry, schema, errors)
    validate_task_link(entry, ops_dir, errors)

    if not parse_timestamp(entry.payload.get("retrieved_at")):
        errors.append(
            issue(
                "error",
                "invalid_timestamp",
                entry.path,
                "retrieved_at must be an ISO-8601 timestamp",
                line_number=entry.line_number,
                evidence_id=entry.payload.get("evidence_id"),
                field="retrieved_at",
                actual=entry.payload.get("retrieved_at"),
            )
        )
    freshness = entry.payload.get("freshness_status")
    if isinstance(freshness, dict) and not parse_timestamp(freshness.get("checked_at")):
        errors.append(
            issue(
                "error",
                "invalid_timestamp",
                entry.path,
                "freshness_status.checked_at must be an ISO-8601 timestamp",
                line_number=entry.line_number,
                evidence_id=entry.payload.get("evidence_id"),
                field="freshness_status.checked_at",
                actual=freshness.get("checked_at"),
            )
        )

    snapshot = validate_runtime_path(
        entry,
        ops_dir,
        "snapshot_path",
        entry.payload.get("snapshot_path"),
        errors,
        must_exist=True,
    )
    content_hash = entry.payload.get("content_hash")
    if snapshot is not None:
        actual_hash = sha256_digest(snapshot)
        if content_hash == "unknown":
            errors.append(
                issue(
                    "error",
                    "content_hash_missing",
                    entry.path,
                    "snapshot_path exists, so content_hash must be a sha256 digest",
                    line_number=entry.line_number,
                    evidence_id=entry.payload.get("evidence_id"),
                    field="content_hash",
                    actual=content_hash,
                )
            )
        elif content_hash != actual_hash:
            errors.append(
                issue(
                    "error",
                    "content_hash_mismatch",
                    entry.path,
                    "content_hash does not match snapshot_path bytes",
                    line_number=entry.line_number,
                    evidence_id=entry.payload.get("evidence_id"),
                    field="content_hash",
                    expected=actual_hash,
                    actual=content_hash,
                )
            )

    license_policy = normalize_text(entry.payload.get("license_or_use_policy")).lower()
    if license_policy in NO_VALUE_MARKERS:
        warnings.append(
            issue(
                "warning",
                "license_or_use_policy_missing",
                entry.path,
                "license_or_use_policy is missing or unknown; downstream acceptance must treat this as unsupported until resolved",
                line_number=entry.line_number,
                evidence_id=entry.payload.get("evidence_id"),
                field="license_or_use_policy",
                actual=entry.payload.get("license_or_use_policy"),
            )
        )
    permission = entry.payload.get("permission_basis")
    if isinstance(permission, dict) and permission.get("type") == "none":
        warnings.append(
            issue(
                "warning",
                "permission_basis_missing",
                entry.path,
                "permission_basis.type is none; adapters must fail closed unless task-contract permission or a human gate is recorded",
                line_number=entry.line_number,
                evidence_id=entry.payload.get("evidence_id"),
                field="permission_basis.type",
                actual=permission.get("type"),
            )
        )


def validate_trace_entry(entry: LedgerEntry, ops_dir: Path, schema: dict[str, Any], errors: list[dict[str, Any]]) -> None:
    validate_against_schema(entry, schema, errors)
    validate_task_link(entry, ops_dir, errors)
    for index, path_text in enumerate(entry.payload.get("artifact_paths") or []):
        validate_runtime_path(
            entry,
            ops_dir,
            f"artifact_paths[{index}]",
            path_text,
            errors,
            must_exist=False,
        )
    route = entry.payload.get("route_decision")
    if isinstance(route, dict):
        if route.get("selected_adapter") != entry.payload.get("adapter_type"):
            errors.append(
                issue(
                    "error",
                    "route_selected_adapter_mismatch",
                    entry.path,
                    "route_decision.selected_adapter must match adapter_type",
                    line_number=entry.line_number,
                    trace_id=entry.payload.get("trace_id"),
                    field="route_decision.selected_adapter",
                    expected=entry.payload.get("adapter_type"),
                    actual=route.get("selected_adapter"),
                )
            )
        fallback = route.get("browser_fallback")
        if entry.payload.get("adapter_type") in WEB_ADAPTERS:
            if not isinstance(fallback, dict) or fallback.get("used") is not True:
                errors.append(
                    issue(
                        "error",
                        "browser_fallback_not_recorded",
                        entry.path,
                        "web adapter traces must record browser_fallback.used=true",
                        line_number=entry.line_number,
                        trace_id=entry.payload.get("trace_id"),
                        field="route_decision.browser_fallback.used",
                    )
                )
            elif fallback.get("snapshot_required") is not True:
                errors.append(
                    issue(
                        "error",
                        "browser_fallback_snapshot_not_required",
                        entry.path,
                        "browser fallback traces must require a runtime snapshot when used as evidence",
                        line_number=entry.line_number,
                        trace_id=entry.payload.get("trace_id"),
                        field="route_decision.browser_fallback.snapshot_required",
                        actual=fallback.get("snapshot_required"),
                    )
                )


def evidence_is_unsupported(payload: dict[str, Any]) -> bool:
    license_policy = normalize_text(payload.get("license_or_use_policy")).lower()
    permission = payload.get("permission_basis")
    spans = payload.get("span_refs")
    return (
        license_policy in NO_VALUE_MARKERS
        or (isinstance(permission, dict) and permission.get("type") == "none")
        or not isinstance(spans, list)
        or len(spans) == 0
    )


def evidence_is_stale(payload: dict[str, Any]) -> bool:
    freshness = payload.get("freshness_status")
    return isinstance(freshness, dict) and freshness.get("status") == "stale"


def trace_has_error(payload: dict[str, Any]) -> bool:
    error = payload.get("error")
    if isinstance(error, dict):
        return True
    return normalize_text(payload.get("return_code")).lower() not in TRACE_SUCCESS_CODES


def latest_runtime_errors(trace_entries: list[LedgerEntry], limit: int = 5) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for entry in reversed(trace_entries):
        payload = entry.payload
        if not trace_has_error(payload):
            continue
        rows.append(
            {
                "trace_id": payload.get("trace_id"),
                "task_id": payload.get("task_id"),
                "adapter_type": payload.get("adapter_type"),
                "tool_name": payload.get("tool_name"),
                "return_code": payload.get("return_code"),
                "error": payload.get("error"),
                "line_number": entry.line_number,
                "ledger_path": str(entry.path),
            }
        )
        if len(rows) >= limit:
            break
    return rows


def summary_from_entries(
    evidence_entries: list[LedgerEntry],
    trace_entries: list[LedgerEntry],
    errors: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    stale_count = sum(1 for entry in evidence_entries if evidence_is_stale(entry.payload))
    unsupported_count = sum(1 for entry in evidence_entries if evidence_is_unsupported(entry.payload))
    unsupported_or_stale_ids = {
        entry.payload.get("evidence_id")
        for entry in evidence_entries
        if evidence_is_stale(entry.payload) or evidence_is_unsupported(entry.payload)
    }
    route_decisions = [
        entry.payload.get("route_decision")
        for entry in trace_entries
        if isinstance(entry.payload.get("route_decision"), dict)
    ]
    browser_fallback_count = sum(
        1
        for route in route_decisions
        if isinstance(route.get("browser_fallback"), dict) and route["browser_fallback"].get("used") is True
    )
    parallel_branches = {
        str(branch.get("branch_id"))
        for entry in trace_entries
        for branch in [entry.payload.get("parallel_branch")]
        if isinstance(branch, dict) and branch.get("branch_id")
    }
    parallel_merge_packets = {
        str(path)
        for entry in trace_entries
        for path in (entry.payload.get("artifact_paths") or [])
        if isinstance(path, str) and path.startswith("research_ops/runtime/parallel_merges/")
    }
    return {
        "runtime_trace_count": len(trace_entries),
        "evidence_object_count": len(evidence_entries),
        "unsupported_evidence_count": unsupported_count,
        "stale_evidence_count": stale_count,
        "unsupported_or_stale_evidence_count": len(unsupported_or_stale_ids),
        "route_decision_count": len(route_decisions),
        "browser_fallback_count": browser_fallback_count,
        "parallel_branch_count": len(parallel_branches),
        "parallel_trace_count": sum(1 for entry in trace_entries if isinstance(entry.payload.get("parallel_branch"), dict)),
        "parallel_merge_packet_count": len(parallel_merge_packets),
        "latest_runtime_errors": latest_runtime_errors(trace_entries),
        "validation_error_count": len(errors),
        "warning_count": len(warnings),
    }


def ledger_paths(ops_dir: Path) -> dict[str, str]:
    return {
        "traces": str(ops_dir / TRACE_LEDGER),
        "evidence_objects": str(ops_dir / EVIDENCE_LEDGER),
        "snapshots_dir": str(ops_dir / SNAPSHOTS_DIR),
    }


def validate_runtime_workspace(ops_dir: Path) -> tuple[int, dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    ops_dir = Path(ops_dir)
    if not ops_dir.is_dir():
        payload = {
            "ok": False,
            "action": "runtime_validate",
            "reason": "ops_dir_missing",
            "ops_dir": str(ops_dir),
            "read_only": True,
            "changed": False,
            "ledger_paths": ledger_paths(ops_dir),
            "summary": {},
            "errors": [
                issue(
                    "error",
                    "ops_dir_missing",
                    ops_dir,
                    "runtime validation requires an existing research_ops directory",
                )
            ],
            "warnings": [],
        }
        return MALFORMED, payload

    try:
        evidence_schema = load_json(schema_path(EVIDENCE_SCHEMA_NAME))
        trace_schema = load_json(schema_path(TRACE_SCHEMA_NAME))
    except ValueError as exc:
        errors.append(issue("error", "schema_load_failed", ops_dir, str(exc)))
        evidence_schema = {}
        trace_schema = {}

    evidence_entries = read_jsonl(ops_dir / EVIDENCE_LEDGER, "evidence", errors)
    trace_entries = read_jsonl(ops_dir / TRACE_LEDGER, "trace", errors)
    for entry in evidence_entries:
        validate_evidence_entry(entry, ops_dir, evidence_schema, errors, warnings)
    for entry in trace_entries:
        validate_trace_entry(entry, ops_dir, trace_schema, errors)

    summary = summary_from_entries(evidence_entries, trace_entries, errors, warnings)
    payload = {
        "ok": not errors,
        "action": "runtime_validate",
        "ops_dir": str(ops_dir),
        "schema_version": "runtime_artifacts_v1.0",
        "read_only": True,
        "changed": False,
        "ledger_paths": ledger_paths(ops_dir),
        "summary": summary,
        "errors": errors,
        "warnings": warnings,
    }
    return (SUCCESS if not errors else VALIDATION_FINDINGS), payload


def runtime_summary(ops_dir: Path) -> tuple[int, dict[str, Any]]:
    code, report = validate_runtime_workspace(ops_dir)
    return code, {
        "ok": report.get("ok", False),
        "action": "runtime_summary",
        "ops_dir": str(ops_dir),
        "schema_version": "runtime_artifacts_v1.0",
        "read_only": True,
        "changed": False,
        "ledger_paths": report.get("ledger_paths", ledger_paths(ops_dir)),
        "summary": report.get("summary", {}),
        "errors": report.get("errors", []),
        "warnings": report.get("warnings", []),
    }


def inspect_evidence(ops_dir: Path, evidence_id: str) -> tuple[int, dict[str, Any]]:
    code, report = validate_runtime_workspace(ops_dir)
    if code == MALFORMED:
        return code, report

    evidence_entries = read_jsonl(Path(ops_dir) / EVIDENCE_LEDGER, "evidence", [])
    trace_entries = read_jsonl(Path(ops_dir) / TRACE_LEDGER, "trace", [])
    match = next((entry for entry in evidence_entries if entry.payload.get("evidence_id") == evidence_id), None)
    if match is None:
        return INVALID_REQUEST, {
            "ok": False,
            "action": "runtime_inspect_evidence",
            "reason": "evidence_not_found",
            "ops_dir": str(ops_dir),
            "evidence_id": evidence_id,
            "read_only": True,
            "changed": False,
            "ledger_paths": ledger_paths(Path(ops_dir)),
            "errors": [
                issue(
                    "error",
                    "evidence_not_found",
                    Path(ops_dir) / EVIDENCE_LEDGER,
                    "evidence_id was not found in the runtime evidence ledger",
                    evidence_id=evidence_id,
                )
            ],
            "warnings": [],
        }

    task_id = match.payload.get("task_id")
    related_traces = [
        entry.payload
        for entry in trace_entries
        if entry.payload.get("task_id") == task_id
    ]
    target_errors = [
        item
        for item in report.get("errors", [])
        if item.get("evidence_id") == evidence_id
    ]
    workspace_errors = [
        item
        for item in report.get("errors", [])
        if item.get("evidence_id") != evidence_id
    ]
    target_warnings = [
        item
        for item in report.get("warnings", [])
        if item.get("evidence_id") == evidence_id
    ]
    payload = {
        "ok": code == SUCCESS and not target_errors,
        "action": "runtime_inspect_evidence",
        "ops_dir": str(ops_dir),
        "evidence_id": evidence_id,
        "read_only": True,
        "changed": False,
        "ledger_path": str(match.path),
        "line_number": match.line_number,
        "evidence": match.payload,
        "related_traces": related_traces[-5:],
        "errors": target_errors + workspace_errors,
        "warnings": target_warnings,
    }
    if code != SUCCESS or target_errors:
        return VALIDATION_FINDINGS, payload
    return SUCCESS, payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate and summarize runtime evidence and trace ledgers.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_cmd = subparsers.add_parser("validate", help="Validate runtime evidence objects and trace ledgers.")
    validate_cmd.add_argument("ops_dir", type=Path, help="Path to the research_ops workspace.")

    summary_cmd = subparsers.add_parser("summary", help="Summarize runtime evidence and trace ledgers.")
    summary_cmd.add_argument("ops_dir", type=Path, help="Path to the research_ops workspace.")

    inspect_cmd = subparsers.add_parser("inspect-evidence", help="Inspect one runtime evidence object by id.")
    inspect_cmd.add_argument("ops_dir", type=Path, help="Path to the research_ops workspace.")
    inspect_cmd.add_argument("evidence_id", help="Evidence id such as EVID-000001.")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv or []))
    if args.command == "validate":
        code, payload = validate_runtime_workspace(args.ops_dir)
    elif args.command == "summary":
        code, payload = runtime_summary(args.ops_dir)
    else:
        code, payload = inspect_evidence(args.ops_dir, args.evidence_id)
    print_json(payload)
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
