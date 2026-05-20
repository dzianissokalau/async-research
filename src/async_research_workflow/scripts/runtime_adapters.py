#!/usr/bin/env python3
"""Bounded runtime adapter dry-runs and executions."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
import fnmatch
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import time
from typing import Any, Iterable
from urllib.parse import urlparse

try:
    import fcntl as _fcntl
except ImportError:  # pragma: no cover - Windows fallback
    _fcntl = None


SUCCESS = 0
VALIDATION_FAILED = 2
INVALID_REQUEST = 3
MALFORMED = 4

ADAPTER_TYPES = {
    "web_search",
    "web_open",
    "file_search",
    "file_fetch",
    "mcp_search",
    "mcp_fetch",
    "api_query",
    "code_execute",
}
NETWORK_CAPABLE_ADAPTERS = {"web_search", "web_open", "mcp_search", "mcp_fetch", "api_query"}
WEB_ADAPTERS = {"web_search", "web_open"}
MCP_ADAPTERS = {"mcp_search", "mcp_fetch"}
LOCAL_ADAPTERS = {"file_search", "file_fetch", "code_execute"}
EXTERNAL_ADAPTERS = NETWORK_CAPABLE_ADAPTERS
RUNTIME_PERMISSIONS_KEY = "runtime_permissions"
SOURCE_PREFERENCE_POLICY = (
    "official_api",
    "authoritative_downloadable_data",
    "official_page",
    "reputable_third_party_database",
    "general_web_page",
    "user_provided_source",
)
SOURCE_CLASS_RANK = {source_class: index for index, source_class in enumerate(SOURCE_PREFERENCE_POLICY)}
BROWSER_FALLBACK_REASONS = {"api_unavailable", "api_incomplete", "human_context_required"}
PARALLEL_RESEARCH_MODE = "parallel_research"
PARALLEL_BRANCH_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,48}$")
PARALLEL_RESEARCH_SHAPES = {
    "source_gathering",
    "literature_extraction",
    "market_map_slice",
    "policy_jurisdiction_comparison",
    "data_source_profiling",
}
MOCK_SOURCE_PROFILES: dict[str, dict[str, Any]] = {
    "statistical_api": {
        "adapter_types": {"api_query"},
        "source_class": "official_api",
        "tool_name": "mock_statistical_api",
    },
    "document_repository": {
        "adapter_types": {"api_query", "mcp_fetch", "web_open"},
        "source_class": "authoritative_downloadable_data",
        "tool_name": "mock_document_repository",
    },
    "search_endpoint": {
        "adapter_types": {"api_query", "web_search"},
        "source_class": "reputable_third_party_database",
        "tool_name": "mock_search_endpoint",
    },
    "private_mcp_source": {
        "adapter_types": {"mcp_search", "mcp_fetch"},
        "source_class": "user_provided_source",
        "tool_name": "mock_private_mcp_source",
    },
}

TRACE_LEDGER = Path("runtime") / "traces.jsonl"
EVIDENCE_LEDGER = Path("runtime") / "evidence_objects.jsonl"
SNAPSHOTS_DIR = Path("runtime") / "snapshots"
PARALLEL_MERGES_DIR = Path("runtime") / "parallel_merges"


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def issue(
    reason: str,
    message: str,
    *,
    field: str | None = None,
    expected: Any = None,
    actual: Any = None,
) -> dict[str, Any]:
    payload = {"reason": reason, "message": message}
    if field is not None:
        payload["field"] = field
    if expected is not None:
        payload["expected"] = expected
    if actual is not None:
        payload["actual"] = actual
    return payload


def sha256_text(text: str) -> str:
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def parse_json_file(path: Path) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, issue("file_missing", "JSON file does not exist", actual=str(path))
    except json.JSONDecodeError as exc:
        return None, issue("invalid_json", f"file is not valid JSON: {exc.msg}", actual=str(path))
    if not isinstance(payload, dict):
        return None, issue("json_not_object", "JSON file must contain an object", actual=str(path))
    return payload, None


def workspace_path(ops_dir: Path, path_text: Any) -> tuple[Path | None, str | None]:
    if not isinstance(path_text, str):
        return None, None
    posix = PurePosixPath(path_text)
    if posix.is_absolute() or not posix.parts:
        return None, None
    if posix.parts[0] != "research_ops":
        return None, None
    if any(part in {"", ".", ".."} for part in posix.parts):
        return None, None
    candidate = (ops_dir.parent / Path(*posix.parts)).resolve(strict=False)
    try:
        candidate.relative_to(ops_dir.resolve(strict=False))
    except ValueError:
        return None, None
    return candidate, Path(*posix.parts).as_posix()


def ref_for_path(ops_dir: Path, path: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(ops_dir.parent.resolve(strict=False)).as_posix()
    except ValueError:
        return path.as_posix()


def allowed_path(ref: str, allowed_paths: Iterable[Any]) -> bool:
    if not ref or ref.startswith("/") or any(part in {"", ".", ".."} for part in ref.split("/")):
        return False
    for raw_pattern in allowed_paths:
        if not isinstance(raw_pattern, str) or not raw_pattern.strip():
            continue
        pattern = raw_pattern.strip()
        if pattern.endswith("/**"):
            prefix = pattern[:-3]
            if ref == prefix or ref.startswith(f"{prefix}/"):
                return True
        if fnmatch.fnmatchcase(ref, pattern):
            return True
    return False


def numeric_value(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def numeric_value_or_zero(value: Any) -> float:
    parsed = numeric_value(value)
    return parsed if parsed is not None else 0.0


def integer_value(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def read_next_number(path: Path, key: str, prefix: str) -> int:
    highest = 0
    if not path.exists():
        return 1
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return 1
    for line in lines:
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        value = payload.get(key)
        if not isinstance(value, str) or not value.startswith(prefix):
            continue
        suffix = value.removeprefix(prefix)
        if suffix.isdigit():
            highest = max(highest, int(suffix))
    return highest + 1


def append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        if _fcntl is not None:
            _fcntl.flock(handle.fileno(), _fcntl.LOCK_EX)
        try:
            for row in rows:
                handle.write(json.dumps(row, sort_keys=True) + "\n")
            handle.flush()
        finally:
            if _fcntl is not None:
                _fcntl.flock(handle.fileno(), _fcntl.LOCK_UN)


def find_task_status(ops_dir: Path, task_id: str) -> tuple[Path | None, dict[str, Any] | None]:
    tasks_dir = ops_dir / "tasks"
    if not tasks_dir.is_dir():
        return None, None
    candidates = [tasks_dir / task_id / "status.json", *sorted(tasks_dir.glob(f"{task_id}-*/status.json"))]
    for path in candidates:
        if not path.is_file():
            continue
        payload, error = parse_json_file(path)
        if error is None and payload is not None:
            return path, payload
    return None, None


@dataclass
class RuntimeContext:
    ops_dir: Path
    task_id: str
    status_path: Path
    task_status: dict[str, Any]
    now: str
    next_evidence_number: int
    next_trace_number: int

    def next_evidence_id(self) -> str:
        value = f"EVID-{self.next_evidence_number:06d}"
        self.next_evidence_number += 1
        return value

    def next_trace_id(self) -> str:
        value = f"TRACE-{self.next_trace_number:06d}"
        self.next_trace_number += 1
        return value

    @property
    def status_ref(self) -> str:
        return ref_for_path(self.ops_dir, self.status_path)

    @property
    def allowed_paths(self) -> list[Any]:
        paths = self.task_status.get("allowed_paths")
        return paths if isinstance(paths, list) else []

    @property
    def runtime_permissions(self) -> dict[str, Any]:
        permissions = self.task_status.get(RUNTIME_PERMISSIONS_KEY)
        return permissions if isinstance(permissions, dict) else {}

    def runtime_write_allowed(self) -> bool:
        required = [
            "research_ops/runtime/traces.jsonl",
            "research_ops/runtime/evidence_objects.jsonl",
            "research_ops/runtime/snapshots/probe.txt",
        ]
        return all(allowed_path(ref, self.allowed_paths) for ref in required)

    def evidence_payload(
        self,
        *,
        adapter_type: str,
        source_uri: str,
        source_title: str,
        snapshot_ref: str,
        snapshot_text: str,
        license_or_use_policy: str,
        span_selector: str,
        span_type: str = "text",
        freshness_status: dict[str, Any] | None = None,
        cost: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        digest = sha256_text(snapshot_text)
        evidence_id = PurePosixPath(snapshot_ref).stem
        return {
            "schema_version": "1.0",
            "framework_version": "runtime_evidence_object_v1.0",
            "evidence_id": evidence_id,
            "task_id": self.task_id,
            "adapter_type": adapter_type,
            "source_uri": source_uri,
            "source_title": source_title,
            "retrieved_at": self.now,
            "content_hash": digest,
            "snapshot_path": snapshot_ref,
            "span_refs": [
                {
                    "span_id": f"SPAN-{int(evidence_id.removeprefix('EVID-')):04d}",
                    "span_type": span_type,
                    "selector": span_selector,
                    "content_hash": digest,
                }
            ],
            "license_or_use_policy": license_or_use_policy,
            "freshness_status": freshness_status
            or {"status": "current", "checked_at": self.now, "basis": "runtime adapter execution"},
            "cost": cost
            or {"api_usd": 0.0, "compute_usd": 0.0, "tokens": 0, "basis": "runtime adapter execution"},
            "permission_basis": {
                "type": "task_contract",
                "reference": self.status_ref,
                "capability": adapter_type,
            },
        }


@dataclass
class AdapterOutcome:
    status: str
    output_summary: str
    evidence_objects: list[dict[str, Any]] = field(default_factory=list)
    artifact_paths: list[str] = field(default_factory=list)
    error: dict[str, Any] | None = None
    snapshot_writes: list[tuple[str, str]] = field(default_factory=list)
    duration_ms: float = 0.0


class RuntimeAdapter:
    adapter_type = ""
    tool_name = ""
    local = True
    supports_mock = False

    def capabilities(self) -> dict[str, Any]:
        return {
            "adapter_type": self.adapter_type,
            "tool_name": self.tool_name,
            "read_only": True,
            "local": self.local,
            "mocked_only": self.supports_mock,
            "source_preference_policy": list(SOURCE_PREFERENCE_POLICY),
        }

    def dry_run(self, call: dict[str, Any], context: RuntimeContext) -> AdapterOutcome:
        evidence_id = context.next_evidence_id()
        snapshot_ref = f"research_ops/runtime/snapshots/{evidence_id}.txt"
        return AdapterOutcome(
            status="planned",
            output_summary=f"{self.tool_name} would write one trace and zero or more evidence objects.",
            artifact_paths=[
                snapshot_ref,
                "research_ops/runtime/evidence_objects.jsonl",
                "research_ops/runtime/traces.jsonl",
            ],
        )

    def execute(self, call: dict[str, Any], context: RuntimeContext) -> AdapterOutcome:
        raise NotImplementedError

    def to_trace(
        self,
        call: dict[str, Any],
        context: RuntimeContext,
        outcome: AdapterOutcome,
        *,
        route: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "framework_version": "runtime_trace_v1.0",
            "trace_id": context.next_trace_id(),
            "task_id": context.task_id,
            "adapter_type": self.adapter_type,
            "tool_name": self.tool_name,
            "input_summary": str(call.get("input_summary") or call.get("query") or call.get("source_path") or self.adapter_type),
            "output_summary": outcome.output_summary,
            "artifact_paths": outcome.artifact_paths,
            "return_code": "success" if outcome.status == "executed" else "blocked_by_policy",
            "duration_ms": round(outcome.duration_ms, 3),
            "token_usage": {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "basis": "not_applicable",
            },
            "cost": trace_cost(call),
            "error": outcome.error,
            "route_decision": route or route_decision(call, self, context),
        }

    def to_evidence_objects(self, outcome: AdapterOutcome) -> list[dict[str, Any]]:
        return outcome.evidence_objects


class FileFetchAdapter(RuntimeAdapter):
    adapter_type = "file_fetch"
    tool_name = "local_file_fetch"

    def execute(self, call: dict[str, Any], context: RuntimeContext) -> AdapterOutcome:
        started = time.monotonic()
        source_path, source_ref = workspace_path(context.ops_dir, call.get("source_path"))
        if source_path is None or source_ref is None:
            return blocked("invalid_source_path", "file_fetch source_path must be under research_ops/")
        if not allowed_path(source_ref, context.allowed_paths):
            return blocked("source_path_not_allowed", "file_fetch source_path is not in task allowed_paths")
        if source_path.suffix.lower() == ".pdf":
            return blocked("pdf_extraction_unavailable", "PDF extraction is not available in the standard-library runtime adapter")
        try:
            text = source_path.read_text(encoding="utf-8")
        except OSError as exc:
            return blocked("source_read_failed", f"file_fetch could not read source_path: {exc}")
        evidence_id = context.next_evidence_id()
        snapshot_ref = f"research_ops/runtime/snapshots/{evidence_id}.txt"
        evidence = context.evidence_payload(
            adapter_type=self.adapter_type,
            source_uri=f"file://{source_ref}",
            source_title=str(call.get("source_title") or source_path.name),
            snapshot_ref=snapshot_ref,
            snapshot_text=text,
            license_or_use_policy=str(call.get("license_or_use_policy") or "unknown"),
            span_selector=str(call.get("selector") or "file:full"),
            span_type="file",
            freshness_status=freshness_status(call, context),
            cost=evidence_cost(call),
        )
        return AdapterOutcome(
            status="executed",
            output_summary=f"Fetched {source_ref} into one runtime snapshot.",
            evidence_objects=[evidence],
            artifact_paths=[snapshot_ref, "research_ops/runtime/evidence_objects.jsonl", "research_ops/runtime/traces.jsonl"],
            snapshot_writes=[(snapshot_ref, text)],
            duration_ms=(time.monotonic() - started) * 1000,
        )


class FileSearchAdapter(RuntimeAdapter):
    adapter_type = "file_search"
    tool_name = "local_file_search"

    def execute(self, call: dict[str, Any], context: RuntimeContext) -> AdapterOutcome:
        started = time.monotonic()
        query = str(call.get("query") or "").strip()
        if not query:
            return blocked("missing_query", "file_search requires a non-empty query")
        source_values = call.get("source_paths")
        if not isinstance(source_values, list):
            source_values = [call.get("source_path")]
        matches: list[str] = []
        source_refs: list[str] = []
        limit = int(call.get("limit") or 20)
        for source_value in source_values:
            source_path, source_ref = workspace_path(context.ops_dir, source_value)
            if source_path is None or source_ref is None:
                return blocked("invalid_source_path", "file_search source paths must be under research_ops/")
            if not allowed_path(source_ref, context.allowed_paths):
                return blocked("source_path_not_allowed", "file_search source path is not in task allowed_paths")
            try:
                lines = source_path.read_text(encoding="utf-8").splitlines()
            except OSError as exc:
                return blocked("source_read_failed", f"file_search could not read source_path: {exc}")
            source_refs.append(source_ref)
            for line_number, line in enumerate(lines, start=1):
                if query.lower() in line.lower():
                    matches.append(f"{source_ref}:{line_number}: {line}")
                    if len(matches) >= limit:
                        break
            if len(matches) >= limit:
                break
        if not matches:
            return AdapterOutcome(
                status="executed",
                output_summary=f"No matches for query {query!r}.",
                artifact_paths=["research_ops/runtime/traces.jsonl"],
                duration_ms=(time.monotonic() - started) * 1000,
            )
        snapshot_text = "\n".join(matches) + "\n"
        evidence_id = context.next_evidence_id()
        snapshot_ref = f"research_ops/runtime/snapshots/{evidence_id}.txt"
        evidence = context.evidence_payload(
            adapter_type=self.adapter_type,
            source_uri=f"file-search://{','.join(source_refs)}",
            source_title=str(call.get("source_title") or f"Search results for {query}"),
            snapshot_ref=snapshot_ref,
            snapshot_text=snapshot_text,
            license_or_use_policy=str(call.get("license_or_use_policy") or "unknown"),
            span_selector=f"query:{query}",
            freshness_status=freshness_status(call, context),
            cost=evidence_cost(call),
        )
        return AdapterOutcome(
            status="executed",
            output_summary=f"Found {len(matches)} matching lines for query {query!r}.",
            evidence_objects=[evidence],
            artifact_paths=[snapshot_ref, "research_ops/runtime/evidence_objects.jsonl", "research_ops/runtime/traces.jsonl"],
            snapshot_writes=[(snapshot_ref, snapshot_text)],
            duration_ms=(time.monotonic() - started) * 1000,
        )


class CodeExecuteAdapter(RuntimeAdapter):
    adapter_type = "code_execute"
    tool_name = "local_code_summary"

    def execute(self, call: dict[str, Any], context: RuntimeContext) -> AdapterOutcome:
        started = time.monotonic()
        operation = str(call.get("operation") or "word_count")
        source_path, source_ref = workspace_path(context.ops_dir, call.get("source_path"))
        if source_path is None or source_ref is None:
            return blocked("invalid_source_path", "code_execute source_path must be under research_ops/")
        if not allowed_path(source_ref, context.allowed_paths):
            return blocked("source_path_not_allowed", "code_execute source_path is not in task allowed_paths")
        try:
            text = source_path.read_text(encoding="utf-8")
        except OSError as exc:
            return blocked("source_read_failed", f"code_execute could not read source_path: {exc}")
        if operation == "word_count":
            result = {"operation": operation, "source_path": source_ref, "word_count": len(text.split())}
        elif operation == "line_count":
            result = {"operation": operation, "source_path": source_ref, "line_count": len(text.splitlines())}
        elif operation == "sha256":
            result = {"operation": operation, "source_path": source_ref, "sha256": sha256_text(text)}
        else:
            return blocked("unsupported_code_operation", "code_execute supports word_count, line_count, and sha256 only")
        snapshot_text = json.dumps(result, indent=2, sort_keys=True) + "\n"
        evidence_id = context.next_evidence_id()
        snapshot_ref = f"research_ops/runtime/snapshots/{evidence_id}.txt"
        evidence = context.evidence_payload(
            adapter_type=self.adapter_type,
            source_uri=f"computed://{operation}/{source_ref}",
            source_title=str(call.get("source_title") or f"{operation} for {source_path.name}"),
            snapshot_ref=snapshot_ref,
            snapshot_text=snapshot_text,
            license_or_use_policy=str(call.get("license_or_use_policy") or "derived-from-source"),
            span_selector=f"computed:{operation}",
            span_type="computed",
            freshness_status=freshness_status(call, context),
            cost=evidence_cost(call),
        )
        return AdapterOutcome(
            status="executed",
            output_summary=f"Computed {operation} for {source_ref}.",
            evidence_objects=[evidence],
            artifact_paths=[snapshot_ref, "research_ops/runtime/evidence_objects.jsonl", "research_ops/runtime/traces.jsonl"],
            snapshot_writes=[(snapshot_ref, snapshot_text)],
            duration_ms=(time.monotonic() - started) * 1000,
        )


class MockExternalAdapter(RuntimeAdapter):
    local = False
    supports_mock = True

    def __init__(self, adapter_type: str, source_profile: str | None = None) -> None:
        self.adapter_type = adapter_type
        profile = mock_source_profile(adapter_type, source_profile)
        self.source_profile = source_profile if profile is not None else None
        self.tool_name = str(profile.get("tool_name")) if profile is not None else f"mock_{adapter_type}"

    def capabilities(self) -> dict[str, Any]:
        payload = super().capabilities()
        payload["mock_source_profiles"] = sorted(
            name
            for name, profile in MOCK_SOURCE_PROFILES.items()
            if self.adapter_type in profile["adapter_types"]
        )
        return payload

    def execute(self, call: dict[str, Any], context: RuntimeContext) -> AdapterOutcome:
        started = time.monotonic()
        mock_response = call.get("mock_response")
        if not isinstance(mock_response, dict):
            return blocked(
                "live_adapter_unavailable",
                f"{self.adapter_type} is mocked-only in Phase 3 and requires mock_response for offline execution",
            )
        content = mock_response.get("content")
        if content is None:
            content = json.dumps(mock_response.get("payload", mock_response), indent=2, sort_keys=True)
        snapshot_text = str(content)
        if not snapshot_text.endswith("\n"):
            snapshot_text += "\n"
        evidence_id = context.next_evidence_id()
        snapshot_ref = f"research_ops/runtime/snapshots/{evidence_id}.txt"
        source_uri = str(
            mock_response.get("source_uri")
            or call.get("source_uri")
            or f"mock://{self.adapter_type}/{call.get('api_name') or call.get('query') or evidence_id}"
        )
        evidence = context.evidence_payload(
            adapter_type=self.adapter_type,
            source_uri=source_uri,
            source_title=str(mock_response.get("source_title") or call.get("source_title") or f"Mock {self.adapter_type} response"),
            snapshot_ref=snapshot_ref,
            snapshot_text=snapshot_text,
            license_or_use_policy=str(mock_response.get("license_or_use_policy") or call.get("license_or_use_policy") or "fixture-only"),
            span_selector=str(mock_response.get("selector") or "mock_response:content"),
            freshness_status=freshness_status(call, context),
            cost=evidence_cost(call),
        )
        return AdapterOutcome(
            status="executed",
            output_summary=f"Recorded mocked {self.adapter_type} response as runtime evidence.",
            evidence_objects=[evidence],
            artifact_paths=[snapshot_ref, "research_ops/runtime/evidence_objects.jsonl", "research_ops/runtime/traces.jsonl"],
            snapshot_writes=[(snapshot_ref, snapshot_text)],
            duration_ms=(time.monotonic() - started) * 1000,
        )


def blocked(reason: str, message: str) -> AdapterOutcome:
    return AdapterOutcome(
        status="blocked",
        output_summary=message,
        error={"code": reason, "message": message, "category": "permission_blocker"},
    )


def evidence_cost(call: dict[str, Any]) -> dict[str, Any]:
    cost = call.get("estimated_cost")
    if not isinstance(cost, dict):
        return {"api_usd": 0.0, "compute_usd": 0.0, "tokens": 0, "basis": "runtime adapter execution"}
    tokens = integer_value(cost.get("tokens"))
    return {
        "api_usd": numeric_value(cost.get("api_usd")) or 0.0,
        "compute_usd": numeric_value(cost.get("compute_usd")) or 0.0,
        "tokens": tokens if tokens is not None else 0,
        "basis": str(cost.get("basis") or "runtime adapter execution"),
    }


def trace_cost(call: dict[str, Any]) -> dict[str, Any]:
    cost = evidence_cost(call)
    return {"api_usd": cost["api_usd"], "compute_usd": cost["compute_usd"], "basis": cost["basis"]}


def freshness_status(call: dict[str, Any], context: RuntimeContext) -> dict[str, Any]:
    freshness = call.get("freshness_status")
    if isinstance(freshness, dict):
        return freshness
    return {"status": "current", "checked_at": context.now, "basis": "runtime adapter execution"}


def normalized_source_class(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    source_class = value.strip()
    return source_class if source_class in SOURCE_CLASS_RANK else None


def mock_source_profile(adapter_type: str, profile_name: Any) -> dict[str, Any] | None:
    if not isinstance(profile_name, str):
        return None
    profile = MOCK_SOURCE_PROFILES.get(profile_name.strip())
    if profile is None or adapter_type not in profile["adapter_types"]:
        return None
    return profile


def source_class_for_call(call: dict[str, Any], adapter_type: str) -> str:
    source_class = normalized_source_class(call.get("source_class"))
    if source_class is not None:
        return source_class
    profile = mock_source_profile(adapter_type, call.get("source_profile"))
    if profile is not None:
        return str(profile["source_class"])
    if adapter_type == "api_query":
        return "official_api"
    if adapter_type == "web_open":
        return "official_page" if call.get("official_source") else "general_web_page"
    if adapter_type == "web_search":
        return "general_web_page"
    if adapter_type in MCP_ADAPTERS:
        return "user_provided_source"
    if adapter_type in LOCAL_ADAPTERS:
        return "user_provided_source"
    return "general_web_page"


def normalized_route_alternatives(call: dict[str, Any]) -> list[dict[str, Any]]:
    alternatives = call.get("route_alternatives")
    if not isinstance(alternatives, list):
        return []
    rows: list[dict[str, Any]] = []
    for alternative in alternatives:
        if not isinstance(alternative, dict):
            continue
        adapter_type = str(alternative.get("adapter_type") or "")
        source_class = normalized_source_class(alternative.get("source_class")) or source_class_for_call(
            alternative,
            adapter_type,
        )
        reason = str(alternative.get("rejection_reason") or alternative.get("reason") or "").strip()
        rows.append(
            {
                "adapter_type": adapter_type,
                "source_class": source_class,
                "reason": reason,
                "cost_estimate": evidence_cost(alternative),
                "freshness_expectation": alternative.get("freshness_expectation") or "",
                "license_or_use_policy_note": str(alternative.get("license_or_use_policy") or ""),
            }
        )
    return rows


def route_reason(call: dict[str, Any], adapter_type: str, source_class: str) -> str:
    explicit = str(call.get("route_reason") or call.get("selection_reason") or "").strip()
    if explicit:
        return explicit
    if adapter_type in WEB_ADAPTERS:
        fallback_reason = str(call.get("browser_fallback_reason") or call.get("fallback_reason") or "").strip()
        if fallback_reason:
            return f"browser fallback: {fallback_reason}"
    if source_class in {"official_api", "authoritative_downloadable_data"}:
        return "highest-preference structured source available for this request"
    return "selected by task-contract source policy and available adapter permissions"


def rejected_alternatives(call: dict[str, Any], selected_source_class: str) -> list[dict[str, Any]]:
    selected_rank = SOURCE_CLASS_RANK[selected_source_class]
    rows: list[dict[str, Any]] = []
    for alternative in normalized_route_alternatives(call):
        reason = alternative["reason"]
        alternative_rank = SOURCE_CLASS_RANK.get(str(alternative["source_class"]), len(SOURCE_PREFERENCE_POLICY))
        if not reason:
            reason = (
                "lower-preference than selected route"
                if selected_rank <= alternative_rank
                else "higher-preference route unavailable, incomplete, or gated for this request"
            )
        rows.append({**alternative, "reason": reason})
    return rows


def browser_fallback(call: dict[str, Any], adapter_type: str, context: RuntimeContext) -> dict[str, Any]:
    used = adapter_type in WEB_ADAPTERS
    reason = str(call.get("browser_fallback_reason") or call.get("fallback_reason") or "").strip()
    domain = str(call.get("domain") or "")
    source_uri = str(call.get("source_uri") or "")
    if not domain and source_uri:
        domain = urlparse(source_uri).hostname or ""
    allowed_domains = context.runtime_permissions.get("allowed_domains")
    domain_permitted = (
        isinstance(allowed_domains, list)
        and bool(domain)
        and domain_allowed(domain, allowed_domains)
    )
    allowed_by_contract = bool(context.task_status.get("allow_browsing")) and bool(context.task_status.get("allow_network")) and domain_permitted
    return {
        "used": used,
        "reason": reason if used else "not_browser_route",
        "allowed_by_task_contract": allowed_by_contract if used else False,
        "snapshot_required": used,
        "governance": (
            "web routes still require allow_browsing, allow_network, allowed_domains, mock_response, "
            "and runtime snapshot evidence"
        )
        if used
        else "not_applicable",
    }


def route_decision(call: dict[str, Any], adapter: RuntimeAdapter, context: RuntimeContext) -> dict[str, Any]:
    source_class = source_class_for_call(call, adapter.adapter_type)
    freshness = freshness_status(call, context)
    license_note = str(call.get("license_or_use_policy") or "")
    mock_response = call.get("mock_response")
    if not license_note and isinstance(mock_response, dict):
        license_note = str(mock_response.get("license_or_use_policy") or "")
    return {
        "selected_adapter": adapter.adapter_type,
        "selected_tool": adapter.tool_name,
        "selected_source_class": source_class,
        "source_preference_rank": SOURCE_CLASS_RANK[source_class] + 1,
        "source_preference_policy": list(SOURCE_PREFERENCE_POLICY),
        "rejected_alternatives": rejected_alternatives(call, source_class),
        "reason": route_reason(call, adapter.adapter_type, source_class),
        "cost_estimate": evidence_cost(call),
        "freshness_expectation": call.get("freshness_expectation")
        or {
            "status": freshness.get("status"),
            "basis": freshness.get("basis"),
        },
        "license_or_use_policy_note": license_note or "unknown",
        "browser_fallback": browser_fallback(call, adapter.adapter_type, context),
    }


def route_policy_findings(call: dict[str, Any], adapter_type: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if "source_class" in call and normalized_source_class(call.get("source_class")) is None:
        findings.append(
            issue(
                "unsupported_source_class",
                "source_class must be one of the source preference policy classes",
                field="source_class",
                actual=call.get("source_class"),
            )
        )
    profile_name = call.get("source_profile")
    if profile_name is not None and mock_source_profile(adapter_type, profile_name) is None:
        findings.append(
            issue(
                "unsupported_source_profile",
                "source_profile is not supported for this adapter type",
                field="source_profile",
                actual=profile_name,
            )
        )
    alternatives = call.get("route_alternatives")
    if alternatives is not None and not isinstance(alternatives, list):
        findings.append(issue("invalid_route_alternatives", "route_alternatives must be a list when present", field="route_alternatives"))
        return findings
    selected_source_class = source_class_for_call(call, adapter_type)
    selected_rank = SOURCE_CLASS_RANK[selected_source_class]
    for index, alternative in enumerate(alternatives or []):
        if not isinstance(alternative, dict):
            findings.append(issue("invalid_route_alternative", "route_alternatives entries must be objects", field=f"route_alternatives[{index}]"))
            continue
        alternative_class = normalized_source_class(alternative.get("source_class"))
        if "source_class" in alternative and alternative_class is None:
            findings.append(
                issue(
                    "unsupported_route_alternative_source_class",
                    "route alternative source_class must be one of the source preference policy classes",
                    field=f"route_alternatives[{index}].source_class",
                    actual=alternative.get("source_class"),
                )
            )
            continue
        alternative_class = alternative_class or source_class_for_call(alternative, str(alternative.get("adapter_type") or ""))
        alternative_rank = SOURCE_CLASS_RANK.get(alternative_class, len(SOURCE_PREFERENCE_POLICY))
        reason = str(alternative.get("rejection_reason") or alternative.get("reason") or "").strip()
        if alternative_rank < selected_rank and not reason:
            findings.append(
                issue(
                    "source_preference_rejection_missing",
                    "higher-preference route alternatives require a rejection reason",
                    field=f"route_alternatives[{index}].rejection_reason",
                )
            )
    if adapter_type in WEB_ADAPTERS:
        fallback_reason = str(call.get("browser_fallback_reason") or call.get("fallback_reason") or "").strip()
        if fallback_reason not in BROWSER_FALLBACK_REASONS:
            findings.append(
                issue(
                    "browser_fallback_reason_missing",
                    "browser routes require a fallback reason: api_unavailable, api_incomplete, or human_context_required",
                    field="browser_fallback_reason",
                    actual=fallback_reason,
                )
            )
    return findings


def adapter_for(adapter_type: str, call: dict[str, Any] | None = None) -> RuntimeAdapter | None:
    if adapter_type == "file_fetch":
        return FileFetchAdapter()
    if adapter_type == "file_search":
        return FileSearchAdapter()
    if adapter_type == "code_execute":
        return CodeExecuteAdapter()
    if adapter_type in EXTERNAL_ADAPTERS:
        profile = call.get("source_profile") if isinstance(call, dict) else None
        return MockExternalAdapter(adapter_type, source_profile=profile if isinstance(profile, str) else None)
    return None


def call_costs(calls: list[dict[str, Any]]) -> tuple[float, float]:
    api = 0.0
    compute = 0.0
    for call in calls:
        cost = call.get("estimated_cost")
        if not isinstance(cost, dict):
            continue
        api += numeric_value(cost.get("api_usd")) or 0.0
        compute += numeric_value(cost.get("compute_usd")) or 0.0
    return api, compute


def domain_allowed(host: str, allowed_domains: list[Any]) -> bool:
    normalized_host = host.lower().strip(".")
    for raw_domain in allowed_domains:
        domain = normalized_allowed_domain(raw_domain)
        if domain is None:
            continue
        if normalized_host == domain or normalized_host.endswith(f".{domain}"):
            return True
    return False


def normalized_allowed_domain(raw_domain: Any) -> str | None:
    if not isinstance(raw_domain, str):
        return None
    domain = raw_domain.lower().strip(".")
    labels = domain.split(".")
    if len(labels) < 2 or any(not label for label in labels):
        return None
    return domain


def parallel_permissions(context: RuntimeContext) -> dict[str, Any]:
    parallel = context.runtime_permissions.get("parallel_research")
    return parallel if isinstance(parallel, dict) else {}


def parallel_plan(request: dict[str, Any]) -> dict[str, Any]:
    plan = request.get("parallel_plan")
    return plan if isinstance(plan, dict) else {}


def is_parallel_request(request: dict[str, Any]) -> bool:
    return request.get("mode") == PARALLEL_RESEARCH_MODE


def branch_id_valid(value: Any) -> bool:
    return isinstance(value, str) and bool(PARALLEL_BRANCH_ID_RE.match(value.strip()))


def clean_branch_id(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def parallel_branch_for_call(call: dict[str, Any], plan_branches: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    branch_id = clean_branch_id(call.get("branch_id") or call.get("parallel_branch_id"))
    branch_shape = str(call.get("branch_shape") or "").strip()
    if not branch_id and not branch_shape:
        return {}
    branch_plan = (plan_branches or {}).get(branch_id, {})
    return {
        "branch_id": branch_id,
        "branch_shape": branch_shape or str(branch_plan.get("branch_shape") or ""),
        "branch_title": str(call.get("branch_title") or branch_plan.get("branch_title") or branch_id),
        "merge_role": "source_branch",
        "no_direct_acceptance": True,
    }


def branch_rows(plan: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    rows = plan.get("branches")
    if not isinstance(rows, list):
        return {}, [issue("parallel_branches_missing", "parallel_plan.branches must list each planned branch", field="parallel_plan.branches")]
    by_id: dict[str, dict[str, Any]] = {}
    findings: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            findings.append(issue("invalid_parallel_branch", "parallel_plan.branches entries must be objects", field=f"parallel_plan.branches[{index}]"))
            continue
        branch_id = clean_branch_id(row.get("branch_id"))
        if not branch_id_valid(branch_id):
            findings.append(
                issue(
                    "invalid_parallel_branch_id",
                    "parallel branch ids must be short filesystem-safe labels",
                    field=f"parallel_plan.branches[{index}].branch_id",
                    actual=row.get("branch_id"),
                )
            )
            continue
        if branch_id in by_id:
            findings.append(issue("duplicate_parallel_branch_id", "parallel branch ids must be unique", field=f"parallel_plan.branches[{index}].branch_id", actual=branch_id))
            continue
        by_id[branch_id] = row
    return by_id, findings


def source_refs_for_call(ops_dir: Path, call: dict[str, Any]) -> list[str]:
    values: list[Any] = []
    if "source_path" in call:
        values.append(call.get("source_path"))
    source_paths = call.get("source_paths")
    if isinstance(source_paths, list):
        values.extend(source_paths)
    refs: list[str] = []
    for value in values:
        _path, ref = workspace_path(ops_dir, value)
        if ref is not None:
            refs.append(ref)
    return refs


def path_inside_parallel_merge_dir(ops_dir: Path, ref: str) -> bool:
    path, normalized_ref = workspace_path(ops_dir, ref)
    return (
        path is not None
        and normalized_ref is not None
        and normalized_ref.startswith("research_ops/runtime/parallel_merges/")
        and normalized_ref.endswith(".md")
    )


def parallel_merge_ref(request: dict[str, Any], context: RuntimeContext) -> str:
    plan = parallel_plan(request)
    raw_ref = plan.get("merge_output_path")
    if isinstance(raw_ref, str) and raw_ref.strip():
        return raw_ref.strip()
    return f"research_ops/runtime/parallel_merges/{context.task_id}-parallel-merge.md"


def task_lock_owner(context: RuntimeContext) -> dict[str, Any]:
    owner_path = context.status_path.parent / "LOCK" / "owner.json"
    try:
        payload = json.loads(owner_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def parallel_lock_findings(plan: dict[str, Any], policy: dict[str, Any], context: RuntimeContext) -> list[dict[str, Any]]:
    if policy.get("require_task_lock") is not True:
        return []
    owner = task_lock_owner(context)
    if not owner:
        return [issue("task_lock_required", "parallel research requires an active task-local LOCK owned by the coordinator", field="runtime_permissions.parallel_research.require_task_lock")]
    coordinator = str(plan.get("coordinator_id") or "").strip()
    if coordinator and owner.get("owner") != coordinator:
        return [
            issue(
                "task_lock_owner_mismatch",
                "parallel research coordinator must match the active task lock owner",
                field="parallel_plan.coordinator_id",
                expected=owner.get("owner"),
                actual=coordinator,
            )
        ]
    return []


def parallel_request_findings(request: dict[str, Any], context: RuntimeContext, calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not is_parallel_request(request):
        return []

    findings: list[dict[str, Any]] = []
    policy = parallel_permissions(context)
    plan = parallel_plan(request)
    if not policy or policy.get("enabled") is not True:
        return [issue("parallel_research_not_allowed", "task contract must enable runtime_permissions.parallel_research before parallel runtime requests run", field=RUNTIME_PERMISSIONS_KEY)]
    if not isinstance(request.get("parallel_plan"), dict):
        findings.append(issue("parallel_plan_missing", "parallel_research mode requires a parallel_plan object", field="parallel_plan"))
    if plan.get("planner_controlled") is not True:
        findings.append(issue("parallel_not_planner_controlled", "parallel_plan.planner_controlled must be true", field="parallel_plan.planner_controlled"))
    if str(plan.get("merge_strategy") or "") != "deterministic_review_packet":
        findings.append(issue("parallel_merge_strategy_invalid", "parallel_plan.merge_strategy must be deterministic_review_packet", field="parallel_plan.merge_strategy"))
    if plan.get("review_packet_required") is not True:
        findings.append(issue("parallel_review_packet_required", "parallel requests must require a single reviewer packet", field="parallel_plan.review_packet_required"))
    if policy.get("merge_required") is not True:
        findings.append(issue("parallel_merge_required", "runtime_permissions.parallel_research.merge_required must be true", field="runtime_permissions.parallel_research.merge_required"))
    if policy.get("no_direct_acceptance") is not True:
        findings.append(issue("parallel_direct_acceptance_not_blocked", "runtime_permissions.parallel_research.no_direct_acceptance must be true", field="runtime_permissions.parallel_research.no_direct_acceptance"))

    max_branches = integer_value(policy.get("max_parallel_branches"))
    if max_branches is None or max_branches < 2:
        findings.append(issue("max_parallel_branches_missing", "parallel research requires max_parallel_branches >= 2", field="runtime_permissions.parallel_research.max_parallel_branches"))
        max_branches = 0
    per_branch_max_calls = integer_value(policy.get("per_branch_max_calls"))
    if per_branch_max_calls is None or per_branch_max_calls < 1:
        findings.append(issue("per_branch_max_calls_missing", "parallel research requires per_branch_max_calls >= 1", field="runtime_permissions.parallel_research.per_branch_max_calls"))
        per_branch_max_calls = 0
    per_branch_max_api = numeric_value(policy.get("per_branch_max_api_usd"))
    per_branch_max_compute = numeric_value(policy.get("per_branch_max_compute_usd"))
    if per_branch_max_api is None:
        findings.append(issue("per_branch_api_budget_missing", "parallel research requires per_branch_max_api_usd", field="runtime_permissions.parallel_research.per_branch_max_api_usd"))
        per_branch_max_api = 0.0
    if per_branch_max_compute is None:
        findings.append(issue("per_branch_compute_budget_missing", "parallel research requires per_branch_max_compute_usd", field="runtime_permissions.parallel_research.per_branch_max_compute_usd"))
        per_branch_max_compute = 0.0

    allowed_shapes_raw = policy.get("allowed_shapes")
    allowed_shapes = {item for item in allowed_shapes_raw if isinstance(item, str)} if isinstance(allowed_shapes_raw, list) else set()
    if not allowed_shapes or not allowed_shapes <= PARALLEL_RESEARCH_SHAPES:
        findings.append(
            issue(
                "parallel_allowed_shapes_invalid",
                "runtime_permissions.parallel_research.allowed_shapes must name supported parallel research shapes",
                field="runtime_permissions.parallel_research.allowed_shapes",
                actual=allowed_shapes_raw,
            )
        )
        allowed_shapes = set()

    merge_ref = parallel_merge_ref(request, context)
    if not path_inside_parallel_merge_dir(context.ops_dir, merge_ref):
        findings.append(
            issue(
                "parallel_merge_path_invalid",
                "parallel merge packets must be Markdown files under research_ops/runtime/parallel_merges/",
                field="parallel_plan.merge_output_path",
                actual=merge_ref,
            )
        )

    plan_branches, branch_findings = branch_rows(plan)
    findings.extend(branch_findings)
    call_branch_ids: set[str] = set()
    calls_by_branch: dict[str, list[dict[str, Any]]] = {}
    branch_api_costs: dict[str, float] = {}
    branch_compute_costs: dict[str, float] = {}
    for index, call in enumerate(calls):
        branch_id = clean_branch_id(call.get("branch_id") or call.get("parallel_branch_id"))
        branch_shape = str(call.get("branch_shape") or "").strip()
        if not branch_id_valid(branch_id):
            findings.append(issue("parallel_call_branch_missing", "parallel calls must include a valid branch_id", field=f"calls[{index}].branch_id", actual=call.get("branch_id")))
            continue
        call_branch_ids.add(branch_id)
        calls_by_branch.setdefault(branch_id, []).append(call)
        branch = plan_branches.get(branch_id)
        if branch is None:
            findings.append(issue("parallel_call_branch_not_planned", "each parallel call branch_id must appear in parallel_plan.branches", field=f"calls[{index}].branch_id", actual=branch_id))
        if branch_shape not in allowed_shapes:
            findings.append(issue("parallel_shape_not_allowed", "parallel call branch_shape is not allowed by task contract", field=f"calls[{index}].branch_shape", actual=branch_shape))
        if branch is not None and branch_shape and str(branch.get("branch_shape") or "") != branch_shape:
            findings.append(issue("parallel_branch_shape_mismatch", "call branch_shape must match the planned branch shape", field=f"calls[{index}].branch_shape", expected=branch.get("branch_shape"), actual=branch_shape))
        if call.get("accept_as_evidence") is True or call.get("acceptance_status") is not None:
            findings.append(issue("parallel_direct_acceptance_blocked", "parallel branch calls cannot request direct acceptance", field=f"calls[{index}].accept_as_evidence"))
        for unsafe_flag in ("skip_review", "skip_claim_verification", "skip_human_gate"):
            if call.get(unsafe_flag) is True:
                findings.append(issue("parallel_gate_skip_blocked", "parallel branch calls cannot skip review, claim verification, or human gates", field=f"calls[{index}].{unsafe_flag}"))
        if branch is not None:
            allowed_paths = branch.get("allowed_paths")
            if not isinstance(allowed_paths, list) or not allowed_paths:
                findings.append(issue("parallel_branch_allowed_paths_missing", "each planned parallel branch must declare allowed_paths", field=f"parallel_plan.branches[{branch_id}].allowed_paths"))
            else:
                for source_ref in source_refs_for_call(context.ops_dir, call):
                    if not allowed_path(source_ref, allowed_paths):
                        findings.append(
                            issue(
                                "parallel_branch_source_path_not_allowed",
                                "parallel call source_path must be inside the branch-specific allowed_paths",
                                field=f"calls[{index}].source_path",
                                actual=source_ref,
                            )
                        )
            branch_budget = branch.get("budget") if isinstance(branch.get("budget"), dict) else {}
            branch_api_limit = numeric_value(branch_budget.get("max_api_usd"))
            branch_compute_limit = numeric_value(branch_budget.get("max_compute_usd"))
            if branch_api_limit is None or branch_api_limit > per_branch_max_api:
                findings.append(issue("parallel_branch_api_budget_invalid", "branch max_api_usd must be present and not exceed the per-branch policy", field=f"parallel_plan.branches[{branch_id}].budget.max_api_usd", actual=branch_budget.get("max_api_usd")))
            if branch_compute_limit is None or branch_compute_limit > per_branch_max_compute:
                findings.append(issue("parallel_branch_compute_budget_invalid", "branch max_compute_usd must be present and not exceed the per-branch policy", field=f"parallel_plan.branches[{branch_id}].budget.max_compute_usd", actual=branch_budget.get("max_compute_usd")))
        cost = evidence_cost(call)
        branch_api_costs[branch_id] = branch_api_costs.get(branch_id, 0.0) + cost["api_usd"]
        branch_compute_costs[branch_id] = branch_compute_costs.get(branch_id, 0.0) + cost["compute_usd"]

    if len(call_branch_ids) < 2:
        findings.append(issue("parallel_branch_count_too_low", "parallel_research mode requires at least two planned branches", field="calls"))
    if max_branches and len(call_branch_ids) > max_branches:
        findings.append(issue("parallel_branch_count_exceeded", "parallel request exceeds max_parallel_branches", field="calls", actual=len(call_branch_ids)))
    for branch_id, branch_calls in calls_by_branch.items():
        if per_branch_max_calls and len(branch_calls) > per_branch_max_calls:
            findings.append(issue("parallel_branch_call_count_exceeded", "parallel branch exceeds per_branch_max_calls", field=f"branches.{branch_id}.calls", actual=len(branch_calls)))
        branch = plan_branches.get(branch_id)
        branch_budget = branch.get("budget") if isinstance(branch, dict) and isinstance(branch.get("budget"), dict) else {}
        branch_api_limit = numeric_value(branch_budget.get("max_api_usd"))
        branch_compute_limit = numeric_value(branch_budget.get("max_compute_usd"))
        if branch_api_limit is not None and branch_api_costs.get(branch_id, 0.0) > branch_api_limit:
            findings.append(issue("parallel_branch_api_budget_exceeded", "parallel branch exceeds its API budget", field=f"branches.{branch_id}.estimated_cost.api_usd", actual=round(branch_api_costs.get(branch_id, 0.0), 6)))
        if branch_compute_limit is not None and branch_compute_costs.get(branch_id, 0.0) > branch_compute_limit:
            findings.append(issue("parallel_branch_compute_budget_exceeded", "parallel branch exceeds its compute budget", field=f"branches.{branch_id}.estimated_cost.compute_usd", actual=round(branch_compute_costs.get(branch_id, 0.0), 6)))

    findings.extend(parallel_lock_findings(plan, policy, context))
    return findings


def cost_findings(call: dict[str, Any]) -> list[dict[str, Any]]:
    cost = call.get("estimated_cost")
    if cost is None:
        return []
    if not isinstance(cost, dict):
        return [issue("invalid_estimated_cost", "estimated_cost must be an object when present", field="estimated_cost")]
    findings: list[dict[str, Any]] = []
    for field_name in ("api_usd", "compute_usd"):
        if field_name in cost and numeric_value(cost.get(field_name)) is None:
            findings.append(
                issue(
                    "invalid_estimated_cost",
                    "estimated_cost monetary fields must be numbers",
                    field=f"estimated_cost.{field_name}",
                    actual=cost.get(field_name),
                )
            )
    if "tokens" in cost and integer_value(cost.get("tokens")) is None:
        findings.append(
            issue(
                "invalid_estimated_cost",
                "estimated_cost.tokens must be an integer",
                field="estimated_cost.tokens",
                actual=cost.get("tokens"),
            )
        )
    return findings


def policy_findings(call: dict[str, Any], context: RuntimeContext) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    adapter_type = call.get("adapter_type")
    if adapter_type not in ADAPTER_TYPES:
        return [issue("unsupported_adapter_type", "runtime call adapter_type is not supported", field="adapter_type", actual=adapter_type)]
    findings.extend(cost_findings(call))
    findings.extend(route_policy_findings(call, str(adapter_type)))
    allowed_tools = context.task_status.get("allowed_tools")
    tools = allowed_tools if isinstance(allowed_tools, list) else []
    if adapter_type not in tools and f"runtime:{adapter_type}" not in tools:
        findings.append(issue("adapter_not_allowed", "task allowed_tools must explicitly include the runtime adapter", field="allowed_tools", actual=tools))
    if adapter_type in WEB_ADAPTERS and not bool(context.task_status.get("allow_browsing")):
        findings.append(issue("browsing_not_allowed", "web adapters require allow_browsing=true", field="allow_browsing", actual=context.task_status.get("allow_browsing")))
    if adapter_type in NETWORK_CAPABLE_ADAPTERS and not bool(context.task_status.get("allow_network")):
        findings.append(issue("network_not_allowed", "network-capable adapters require allow_network=true", field="allow_network", actual=context.task_status.get("allow_network")))
    if adapter_type == "code_execute" and not bool(context.task_status.get("allow_code_execution")):
        findings.append(issue("code_execution_not_allowed", "code_execute requires allow_code_execution=true", field="allow_code_execution", actual=context.task_status.get("allow_code_execution")))
    if adapter_type in EXTERNAL_ADAPTERS and not isinstance(call.get("mock_response"), dict):
        findings.append(issue("mock_response_required", "external adapters are mocked-only and require mock_response", field="mock_response"))
    permissions = context.runtime_permissions
    if call.get("requires_credentials") and not permissions.get("allow_credentials"):
        findings.append(issue("credentials_not_allowed", "credential use requires runtime_permissions.allow_credentials=true", field=RUNTIME_PERMISSIONS_KEY))
    cost = evidence_cost(call)
    if (cost["api_usd"] > 0 or cost["compute_usd"] > 0) and not permissions.get("allow_paid_calls"):
        findings.append(issue("paid_calls_not_allowed", "paid runtime calls require runtime_permissions.allow_paid_calls=true", field=RUNTIME_PERMISSIONS_KEY))
    if adapter_type in WEB_ADAPTERS:
        allowed_domains = permissions.get("allowed_domains")
        if not isinstance(allowed_domains, list) or not allowed_domains:
            findings.append(issue("allowed_domains_missing", "web adapters require runtime_permissions.allowed_domains", field=RUNTIME_PERMISSIONS_KEY))
        else:
            for raw_domain in allowed_domains:
                if normalized_allowed_domain(raw_domain) is None:
                    findings.append(
                        issue(
                            "allowed_domain_too_broad",
                            "allowed_domains entries must be fully qualified domains, not TLDs or single-label names",
                            field="runtime_permissions.allowed_domains",
                            actual=raw_domain,
                        )
                    )
            source_uri = str(call.get("source_uri") or "")
            domain = str(call.get("domain") or "")
            if not domain and source_uri:
                domain = urlparse(source_uri).hostname or ""
            if not domain or not domain_allowed(domain, allowed_domains):
                findings.append(issue("domain_not_allowed", "web adapter domain is not allowed by task contract", field="domain", actual=domain))
    if adapter_type == "api_query":
        allowed_api_names = permissions.get("allowed_api_names")
        api_name = str(call.get("api_name") or "")
        if not isinstance(allowed_api_names, list) or api_name not in allowed_api_names:
            findings.append(issue("api_not_allowed", "api_query requires api_name in runtime_permissions.allowed_api_names", field="api_name", actual=api_name))
    if adapter_type in MCP_ADAPTERS:
        allowed_mcp_servers = permissions.get("allowed_mcp_servers")
        mcp_server = str(call.get("mcp_server") or "")
        if not isinstance(allowed_mcp_servers, list) or mcp_server not in allowed_mcp_servers:
            findings.append(issue("mcp_server_not_allowed", "MCP adapters require mcp_server in runtime_permissions.allowed_mcp_servers", field="mcp_server", actual=mcp_server))
    return findings


def request_findings(request: dict[str, Any], context: RuntimeContext, calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    permissions = context.runtime_permissions
    max_calls = permissions.get("max_calls")
    if not isinstance(max_calls, int) or isinstance(max_calls, bool) or max_calls < 0:
        findings.append(issue("max_calls_missing", "runtime_permissions.max_calls must be configured before runtime adapters run", field=RUNTIME_PERMISSIONS_KEY))
    elif len(calls) > max_calls:
        findings.append(issue("max_calls_exceeded", "runtime request exceeds task max_calls", field="calls", actual=len(calls)))
    api_cost, compute_cost = call_costs(calls)
    budget = context.task_status.get("budget") if isinstance(context.task_status.get("budget"), dict) else {}
    max_api = numeric_value(permissions.get("max_api_usd"))
    max_compute = numeric_value(permissions.get("max_compute_usd"))
    budget_api = numeric_value_or_zero(budget.get("max_api_usd"))
    budget_compute = numeric_value_or_zero(budget.get("max_compute_usd"))
    api_limit = min(value for value in [budget_api, max_api] if value is not None)
    compute_limit = min(value for value in [budget_compute, max_compute] if value is not None)
    if api_cost > api_limit:
        findings.append(issue("api_budget_exceeded", "runtime request exceeds API budget", field="estimated_cost.api_usd", actual=api_cost))
    if compute_cost > compute_limit:
        findings.append(issue("compute_budget_exceeded", "runtime request exceeds compute budget", field="estimated_cost.compute_usd", actual=compute_cost))
    if request.get("mode") not in {None, "vertical_slice", "single_task", PARALLEL_RESEARCH_MODE}:
        findings.append(issue("unsupported_request_mode", "runtime request mode must be omitted, vertical_slice, single_task, or parallel_research", field="mode", actual=request.get("mode")))
    findings.extend(parallel_request_findings(request, context, calls))
    return findings


def load_runtime_request(ops_dir: Path, request_path: Path) -> tuple[int, dict[str, Any] | None, RuntimeContext | None, list[dict[str, Any]]]:
    request, error = parse_json_file(request_path)
    if error is not None or request is None:
        return INVALID_REQUEST, None, None, [error or issue("invalid_request", "request could not be loaded")]
    calls = request.get("calls")
    if not isinstance(calls, list) or not all(isinstance(call, dict) for call in calls):
        return INVALID_REQUEST, request, None, [issue("invalid_calls", "runtime request requires calls as a list of objects", field="calls")]
    task_id = request.get("task_id")
    if not isinstance(task_id, str) or not task_id.startswith("TASK-"):
        return INVALID_REQUEST, request, None, [issue("invalid_task_id", "runtime request requires task_id", field="task_id", actual=task_id)]
    if not ops_dir.is_dir():
        return MALFORMED, request, None, [issue("ops_dir_missing", "runtime adapters require an existing research_ops directory", actual=str(ops_dir))]
    status_path, task_status = find_task_status(ops_dir, task_id)
    if status_path is None or task_status is None:
        return MALFORMED, request, None, [issue("task_contract_missing", "runtime adapters require a matching research_ops/tasks status.json", field="task_id", actual=task_id)]
    context = RuntimeContext(
        ops_dir=ops_dir,
        task_id=task_id,
        status_path=status_path,
        task_status=task_status,
        now=str(request.get("now") or iso_now()),
        next_evidence_number=read_next_number(ops_dir / EVIDENCE_LEDGER, "evidence_id", "EVID-"),
        next_trace_number=read_next_number(ops_dir / TRACE_LEDGER, "trace_id", "TRACE-"),
    )
    return SUCCESS, request, context, []


def summarize_call(
    index: int,
    adapter: RuntimeAdapter,
    outcome: AdapterOutcome,
    *,
    trace: dict[str, Any] | None,
    route: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "index": index,
        "adapter_type": adapter.adapter_type,
        "tool_name": adapter.tool_name,
        "status": outcome.status,
        "output_summary": outcome.output_summary,
        "artifact_paths": outcome.artifact_paths,
        "evidence_ids": [row.get("evidence_id") for row in outcome.evidence_objects],
        "route_decision": route,
    }
    if trace is not None:
        payload["trace_id"] = trace.get("trace_id")
    if outcome.error is not None:
        payload["error"] = outcome.error
    return payload


def markdown_cell(value: Any) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ").strip()


def bullet_rows(values: Any, fallback: str) -> list[str]:
    if not isinstance(values, list) or not values:
        return [f"- {fallback}"]
    rows = [f"- {markdown_cell(value)}" for value in values if str(value).strip()]
    return rows or [f"- {fallback}"]


def parallel_execution_summary(
    request: dict[str, Any],
    calls: list[dict[str, Any]],
    *,
    merge_ref: str | None,
    merge_written: bool,
) -> dict[str, Any]:
    if not is_parallel_request(request):
        return {}
    branch_ids = sorted(
        {
            clean_branch_id(call.get("branch_id") or call.get("parallel_branch_id"))
            for call in calls
            if branch_id_valid(clean_branch_id(call.get("branch_id") or call.get("parallel_branch_id")))
        }
    )
    shapes = sorted({str(call.get("branch_shape") or "").strip() for call in calls if str(call.get("branch_shape") or "").strip()})
    return {
        "parallel_mode": True,
        "parallel_branch_count": len(branch_ids),
        "parallel_branch_ids": branch_ids,
        "parallel_shapes": shapes,
        "parallel_merge_packet": merge_ref,
        "parallel_merge_packet_count": 1 if merge_written else 0,
    }


def build_parallel_merge_packet(
    request: dict[str, Any],
    context: RuntimeContext,
    calls: list[dict[str, Any]],
    call_summaries: list[dict[str, Any]],
    evidence_rows: list[dict[str, Any]],
    merge_ref: str,
) -> str:
    plan = parallel_plan(request)
    plan_branches, _findings = branch_rows(plan)
    summaries_by_branch: dict[str, list[dict[str, Any]]] = {}
    evidence_by_branch: dict[str, list[dict[str, Any]]] = {}
    for summary in call_summaries:
        branch = summary.get("parallel_branch") if isinstance(summary.get("parallel_branch"), dict) else {}
        branch_id = clean_branch_id(branch.get("branch_id"))
        if branch_id:
            summaries_by_branch.setdefault(branch_id, []).append(summary)
    for evidence in evidence_rows:
        branch = evidence.get("parallel_branch") if isinstance(evidence.get("parallel_branch"), dict) else {}
        branch_id = clean_branch_id(branch.get("branch_id"))
        if branch_id:
            evidence_by_branch.setdefault(branch_id, []).append(evidence)

    branch_ids = sorted(set(summaries_by_branch) | set(evidence_by_branch) | set(plan_branches))
    lock_owner = task_lock_owner(context)
    lines = [
        f"# Parallel Research Merge Packet - {context.task_id}",
        "",
        f"- Task: `{context.task_id}`",
        f"- Coordinator: `{markdown_cell(plan.get('coordinator_id') or 'unrecorded')}`",
        f"- Merge strategy: `{markdown_cell(plan.get('merge_strategy') or 'deterministic_review_packet')}`",
        f"- Merge path: `{merge_ref}`",
        f"- Concurrency key: `{markdown_cell(parallel_permissions(context).get('concurrency_key') or plan.get('concurrency_key') or 'unrecorded')}`",
        f"- Active task lock owner: `{markdown_cell(lock_owner.get('owner') or 'not_required_or_not_recorded')}`",
        f"- Direct acceptance from branch outputs: `blocked`",
        "",
        "## Branch Summary",
        "",
        "| Branch | Shape | Calls | Evidence IDs | Branch title |",
        "| --- | --- | ---: | --- | --- |",
    ]
    for branch_id in branch_ids:
        branch = plan_branches.get(branch_id, {})
        summaries = summaries_by_branch.get(branch_id, [])
        evidence_ids = [
            str(evidence.get("evidence_id"))
            for evidence in evidence_by_branch.get(branch_id, [])
            if evidence.get("evidence_id")
        ]
        shape = branch.get("branch_shape") or next(
            (
                summary.get("parallel_branch", {}).get("branch_shape")
                for summary in summaries
                if isinstance(summary.get("parallel_branch"), dict)
            ),
            "",
        )
        title = branch.get("branch_title") or branch_id
        lines.append(
            f"| `{markdown_cell(branch_id)}` | {markdown_cell(shape)} | {len(summaries)} | {markdown_cell(', '.join(evidence_ids) or 'none')} | {markdown_cell(title)} |"
        )

    lines.extend([
        "",
        "## Evidence Coverage",
        "",
        "| Branch | Evidence ID | Source title | Source URI | Snapshot |",
        "| --- | --- | --- | --- | --- |",
    ])
    for branch_id in branch_ids:
        for evidence in evidence_by_branch.get(branch_id, []):
            lines.append(
                "| "
                f"`{markdown_cell(branch_id)}` | `{markdown_cell(evidence.get('evidence_id'))}` | "
                f"{markdown_cell(evidence.get('source_title'))} | {markdown_cell(evidence.get('source_uri'))} | "
                f"`{markdown_cell(evidence.get('snapshot_path'))}` |"
            )
    if not any(evidence_by_branch.values()):
        lines.append("| none | none | none | none | none |")

    lines.extend([
        "",
        "## Contradictions",
        "",
        *bullet_rows(plan.get("contradictions"), "No contradictions recorded by the branch merge; reviewer must still check claim verification."),
        "",
        "## Unresolved Gaps",
        "",
        *bullet_rows(plan.get("unresolved_gaps"), "No unresolved gaps recorded by the planner-controlled merge."),
        "",
        "## Reviewer Packet",
        "",
        "- Inspect every referenced evidence object and snapshot before using branch output.",
        "- Run claim verification before result acceptance or deliverable maturity gates.",
        "- Treat this merge packet as review context only; it does not accept evidence, claims, or task state.",
        "- Preserve human gates for public claims, credentials, paid calls, private data, and unsafe source use.",
        "",
    ])
    return "\n".join(lines)


def attach_parallel_metadata(
    request: dict[str, Any],
    call: dict[str, Any],
    outcome: AdapterOutcome,
    trace: dict[str, Any] | None,
    *,
    merge_ref: str | None,
) -> dict[str, Any]:
    if not is_parallel_request(request):
        return {}
    plan_branches, _findings = branch_rows(parallel_plan(request))
    metadata = parallel_branch_for_call(call, plan_branches)
    if not metadata:
        return {}
    if merge_ref:
        metadata["merge_packet_path"] = merge_ref
    for evidence in outcome.evidence_objects:
        evidence["parallel_branch"] = dict(metadata)
    if trace is not None:
        trace["parallel_branch"] = dict(metadata)
        if merge_ref and merge_ref not in trace["artifact_paths"]:
            trace["artifact_paths"].append(merge_ref)
    return metadata


def run_runtime_request(ops_dir: Path, request_path: Path, *, execute: bool, now: str | None = None) -> tuple[int, dict[str, Any]]:
    load_code, request, context, load_errors = load_runtime_request(ops_dir, request_path)
    if load_code != SUCCESS or request is None or context is None:
        return load_code, {
            "ok": False,
            "action": "runtime_execute" if execute else "runtime_dry_run",
            "ops_dir": str(ops_dir),
            "request_path": str(request_path),
            "changed": False,
            "errors": load_errors,
        }
    if now is not None:
        context.now = now
    calls: list[dict[str, Any]] = list(request["calls"])
    global_findings = request_findings(request, context, calls)
    merge_ref = parallel_merge_ref(request, context) if is_parallel_request(request) else None
    if execute and not context.runtime_write_allowed():
        global_findings.append(issue("runtime_write_path_not_allowed", "task allowed_paths must include research_ops/runtime/** for runtime execution", field="allowed_paths", actual=context.allowed_paths))
        return VALIDATION_FAILED, {
            "ok": False,
            "action": "runtime_execute",
            "ops_dir": str(ops_dir),
            "request_path": str(request_path),
            "task_id": context.task_id,
            "schema_version": "runtime_adapters_v1.0",
            "changed": False,
            "read_only": False,
            "summary": {
                "call_count": len(calls),
                "blocked_call_count": len(calls),
                "trace_count": 0,
                "evidence_object_count": 0,
                "snapshot_count": 0,
                **parallel_execution_summary(request, calls, merge_ref=merge_ref, merge_written=False),
            },
            "calls": [],
            "errors": global_findings,
        }
    call_summaries: list[dict[str, Any]] = []
    traces: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []
    snapshot_writes: list[tuple[str, str]] = []
    blocked_count = 0
    merge_written = False

    for index, call in enumerate(calls):
        adapter_type = str(call.get("adapter_type") or "")
        adapter = adapter_for(adapter_type, call)
        if adapter is None:
            outcome = blocked("unsupported_adapter_type", "runtime call adapter_type is not supported")
            blocked_count += 1
            call_summaries.append({
                "index": index,
                "adapter_type": adapter_type,
                "status": "blocked",
                "output_summary": outcome.output_summary,
                "error": outcome.error,
            })
            continue
        route = route_decision(call, adapter, context)
        findings = [*global_findings, *policy_findings(call, context)]
        if findings:
            first = findings[0]
            outcome = blocked(str(first["reason"]), str(first["message"]))
            blocked_count += 1
        elif execute:
            outcome = adapter.execute(call, context)
            if outcome.status == "blocked":
                blocked_count += 1
        else:
            outcome = adapter.dry_run(call, context)
        trace = None
        if execute:
            trace = adapter.to_trace(call, context, outcome, route=route)
        parallel_metadata = attach_parallel_metadata(
            request,
            call,
            outcome,
            trace,
            merge_ref=merge_ref,
        )
        if execute:
            traces.append(trace)
            evidence_rows.extend(adapter.to_evidence_objects(outcome))
            snapshot_writes.extend(outcome.snapshot_writes)
        summary = summarize_call(index, adapter, outcome, trace=trace, route=route)
        if parallel_metadata:
            summary["parallel_branch"] = parallel_metadata
        call_summaries.append(summary)

    if execute:
        merge_write: tuple[Path, str] | None = None
        if is_parallel_request(request) and blocked_count == 0 and not global_findings and merge_ref is not None:
            merge_path, _normalized_ref = workspace_path(context.ops_dir, merge_ref)
            if merge_path is None:
                return MALFORMED, {
                    "ok": False,
                    "action": "runtime_execute",
                    "ops_dir": str(ops_dir),
                    "request_path": str(request_path),
                    "changed": False,
                    "errors": [issue("invalid_parallel_merge_path", "parallel merge path resolved outside research_ops", actual=merge_ref)],
                }
            merge_write = (
                merge_path,
                build_parallel_merge_packet(request, context, calls, call_summaries, evidence_rows, merge_ref),
            )
        for snapshot_ref, text in snapshot_writes:
            snapshot_path, _ = workspace_path(context.ops_dir, snapshot_ref)
            if snapshot_path is None:
                return MALFORMED, {
                    "ok": False,
                    "action": "runtime_execute",
                    "ops_dir": str(ops_dir),
                    "request_path": str(request_path),
                    "changed": False,
                    "errors": [issue("invalid_snapshot_path", "adapter produced a snapshot path outside research_ops", actual=snapshot_ref)],
                }
            snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            snapshot_path.write_text(text, encoding="utf-8")
        if merge_write is not None:
            merge_path, merge_text = merge_write
            merge_path.parent.mkdir(parents=True, exist_ok=True)
            merge_path.write_text(merge_text, encoding="utf-8")
            merge_written = True
        append_jsonl(context.ops_dir / EVIDENCE_LEDGER, evidence_rows)
        append_jsonl(context.ops_dir / TRACE_LEDGER, traces)

    ok = blocked_count == 0 and not global_findings
    parallel_summary = parallel_execution_summary(request, calls, merge_ref=merge_ref, merge_written=merge_written)
    payload = {
        "ok": ok,
        "action": "runtime_execute" if execute else "runtime_dry_run",
        "ops_dir": str(ops_dir),
        "request_path": str(request_path),
        "task_id": context.task_id,
        "schema_version": "runtime_adapters_v1.0",
        "changed": execute and bool(traces or evidence_rows or snapshot_writes),
        "read_only": not execute,
        "adapter_capabilities": [
            adapter.capabilities()
            for adapter_type in sorted(ADAPTER_TYPES)
            for adapter in [adapter_for(adapter_type)]
            if adapter is not None
        ],
        "summary": {
            "call_count": len(calls),
            "blocked_call_count": blocked_count,
            "trace_count": len(traces),
            "evidence_object_count": len(evidence_rows),
            "snapshot_count": len(snapshot_writes),
            **parallel_summary,
        },
        "calls": call_summaries,
        "errors": global_findings,
    }
    return (SUCCESS if ok else VALIDATION_FAILED), payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run bounded runtime adapter dry-runs, executions, or parallel research merge flows.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    dry_run = subparsers.add_parser("dry-run", help="Preview runtime adapter calls without writing artifacts.")
    dry_run.add_argument("ops_dir", type=Path, help="Path to the research_ops workspace.")
    dry_run.add_argument("--request", required=True, type=Path, help="Runtime request JSON file.")
    dry_run.add_argument("--now", help="Override execution timestamp for deterministic output.")

    execute = subparsers.add_parser("execute", help="Execute permitted local or mocked runtime adapter calls.")
    execute.add_argument("ops_dir", type=Path, help="Path to the research_ops workspace.")
    execute.add_argument("--request", required=True, type=Path, help="Runtime request JSON file.")
    execute.add_argument("--now", help="Override execution timestamp for deterministic output.")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv or []))
    code, payload = run_runtime_request(
        args.ops_dir,
        args.request,
        execute=args.command == "execute",
        now=args.now,
    )
    print_json(payload)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
