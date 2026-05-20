#!/usr/bin/env python3
"""Build and query structured evidence memory plus targeted reflections."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Any, Iterable

from async_research_workflow.resources import schema_path
from async_research_workflow.scripts.update_accepted_outputs_index import DEFAULT_INDEX_NAME
from async_research_workflow.scripts.update_accepted_outputs_index import read_index_rows
from async_research_workflow.scripts.validate_json_artifact import load_json
from async_research_workflow.scripts.validate_json_artifact import validate


SUCCESS = 0
INVALID = 2
UNSAFE = 3
MALFORMED = 4

INDEX_RELATIVE_PATH = Path("memory") / "evidence_memory_index.json"
REFLECTION_LEDGER_RELATIVE_PATH = Path("reflections") / "targeted_reflections.jsonl"
INDEX_SCHEMA_NAME = "evidence_memory_index.schema.json"
REFLECTION_SCHEMA_NAME = "targeted_reflection.schema.json"
INDEX_FRAMEWORK_VERSION = "evidence_memory_index_v1.0"
REFLECTION_FRAMEWORK_VERSION = "targeted_reflection_v1.0"
REFLECTION_ID_RE = re.compile(r"^REFL-[0-9]{6}$")
TASK_ID_RE = re.compile(r"^TASK-[0-9]{4}$")
EVIDENCE_ID_RE = re.compile(r"^EVID-[0-9]{6}$")
CLAIM_ID_RE = re.compile(r"^CLM-[0-9]{4,6}$")
SOURCE_ID_RE = re.compile(r"\bDS-[0-9]{4}\b")
NO_VALUE = {"", "none", "unknown", "n/a", "na"}
STOPWORDS = {
    "and",
    "are",
    "but",
    "for",
    "from",
    "has",
    "have",
    "into",
    "that",
    "the",
    "this",
    "with",
    "without",
}
FAILURE_CLASSES = (
    "source_quality",
    "stale_evidence",
    "contradiction",
    "citation_gap",
    "unsupported_claim",
    "route_policy",
    "reviewer_disagreement",
    "reproducibility",
    "cost_budget",
    "scope_ambiguity",
)
AFFECTED_STAGES = (
    "clarifier",
    "planner",
    "runtime",
    "extraction",
    "verification",
    "review",
    "synthesis",
    "deliverable",
    "eval",
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.strptime(text[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def atomic_append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(existing + json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def read_jsonl(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if not path.exists():
        return rows, warnings
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return rows, [{"reason": "jsonl_read_failed", "path": str(path), "message": str(exc)}]
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            warnings.append(
                {
                    "reason": "malformed_jsonl",
                    "path": str(path),
                    "line_number": line_number,
                    "message": exc.msg,
                }
            )
            continue
        if isinstance(payload, dict):
            payload.setdefault("_ledger_path", str(path))
            payload.setdefault("_line_number", line_number)
            rows.append(payload)
        else:
            warnings.append(
                {
                    "reason": "jsonl_entry_not_object",
                    "path": str(path),
                    "line_number": line_number,
                    "message": "reflection ledger entries must be JSON objects",
                }
            )
    return rows, warnings


def relative_research_ops_path(ops_dir: Path, path: Path) -> str:
    try:
        rel = path.resolve(strict=False).relative_to(ops_dir.resolve(strict=False))
    except ValueError:
        return str(path)
    return (Path("research_ops") / rel).as_posix()


def workspace_path(ops_dir: Path, path_text: Any) -> Path | None:
    if not isinstance(path_text, str) or not path_text.strip():
        return None
    posix = PurePosixPath(path_text.strip())
    if posix.is_absolute() or not posix.parts:
        return None
    if posix.parts[0] == "research_ops":
        parts = posix.parts[1:]
    else:
        parts = posix.parts
    if any(part in {"", ".", ".."} for part in parts):
        return None
    candidate = (ops_dir / Path(*parts)).resolve(strict=False)
    try:
        candidate.relative_to(ops_dir.resolve(strict=False))
    except ValueError:
        return None
    return candidate


def output_path_for(ops_dir: Path, output: Path | None) -> Path | None:
    if output is None:
        return ops_dir / INDEX_RELATIVE_PATH
    if output.is_absolute():
        candidate = output.resolve(strict=False)
    else:
        candidate = (ops_dir / output).resolve(strict=False)
    try:
        candidate.relative_to(ops_dir.resolve(strict=False))
    except ValueError:
        return None
    return candidate


def normalize_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip() and str(item).strip().lower() not in NO_VALUE]
    if isinstance(value, str):
        return [item.strip() for item in re.split(r"[,;]", value) if item.strip() and item.strip().lower() not in NO_VALUE]
    return []


def unique(values: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    rows: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text.lower() in NO_VALUE or text in seen:
            continue
        rows.append(text)
        seen.add(text)
    return rows


def tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) > 2 and token not in STOPWORDS
    }


def similarity(query: str, text: str) -> float:
    query_tokens = tokens(query)
    text_tokens = tokens(text)
    if not query_tokens or not text_tokens:
        return 0.0
    return len(query_tokens & text_tokens) / len(query_tokens | text_tokens)


def task_dir_for_id(ops_dir: Path, task_id: str) -> Path | None:
    tasks_dir = ops_dir / "tasks"
    if not tasks_dir.is_dir():
        return None
    direct = tasks_dir / task_id
    if direct.is_dir():
        return direct
    return next((path for path in sorted(tasks_dir.glob(f"{task_id}-*")) if path.is_dir()), None)


def task_status_for_id(ops_dir: Path, task_id: str) -> dict[str, Any]:
    task_dir = task_dir_for_id(ops_dir, task_id)
    return read_json(task_dir / "status.json") if task_dir is not None else {}


def task_title(ops_dir: Path, task_id: str, fallback: str = "") -> str:
    status = task_status_for_id(ops_dir, task_id)
    return str(status.get("title") or fallback or task_id)


def load_runtime_evidence_by_task(ops_dir: Path) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    path = ops_dir / "runtime" / "evidence_objects.jsonl"
    rows, warnings = read_jsonl(path)
    by_task: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        task_id = str(row.get("task_id") or "")
        if not task_id:
            warnings.append({"reason": "runtime_evidence_missing_task_id", "path": str(path), "evidence_id": row.get("evidence_id")})
            continue
        by_task.setdefault(task_id, []).append(row)
    return by_task, warnings


def claim_reports_for_task(task_dir: Path) -> list[tuple[Path, dict[str, Any]]]:
    candidates = [
        task_dir / "artifacts" / "claim_verification.json",
        task_dir / "artifacts" / "claim_verification" / "claims.json",
        task_dir / "review_panel" / "result_acceptance.json",
    ]
    reports: list[tuple[Path, dict[str, Any]]] = []
    for path in candidates:
        payload = read_json(path)
        if not payload:
            continue
        if isinstance(payload.get("claim_verification"), dict):
            reports.append((path, payload["claim_verification"]))
        elif isinstance(payload.get("claims"), list):
            reports.append((path, payload))
    return reports


def ref_evidence_ids(refs: Any) -> list[str]:
    ids: list[str] = []
    if not isinstance(refs, list):
        return ids
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        evidence_id = str(ref.get("evidence_id") or ref.get("id") or "").strip()
        if EVIDENCE_ID_RE.match(evidence_id):
            ids.append(evidence_id)
    return ids


def claims_for_task(ops_dir: Path, task_id: str) -> tuple[list[dict[str, Any]], list[str]]:
    task_dir = task_dir_for_id(ops_dir, task_id)
    if task_dir is None:
        return [], []
    claims: list[dict[str, Any]] = []
    artifact_paths: list[str] = []
    for path, report in claim_reports_for_task(task_dir):
        artifact_paths.append(relative_research_ops_path(ops_dir, path))
        for claim in report.get("claims", []):
            if isinstance(claim, dict):
                claims.append(claim)
    return claims, artifact_paths


def load_deliverable_links_by_task(ops_dir: Path) -> dict[str, list[dict[str, Any]]]:
    manifest = read_json(ops_dir / "deliverables" / "deliverable_manifest.json") or {}
    links: dict[str, list[dict[str, Any]]] = {}
    deliverables = manifest.get("deliverables") if isinstance(manifest.get("deliverables"), list) else []
    for deliverable in deliverables:
        if not isinstance(deliverable, dict):
            continue
        link = {
            "deliverable_id": deliverable.get("deliverable_id"),
            "title": deliverable.get("title"),
            "target_maturity": deliverable.get("target_maturity"),
            "path": "research_ops/deliverables/deliverable_manifest.json",
        }
        for task_id in normalize_list(deliverable.get("source_task_ids")):
            links.setdefault(task_id, []).append({key: value for key, value in link.items() if value})
    return links


def evidence_freshness_status(row_status: str, runtime_rows: list[dict[str, Any]], claims: list[dict[str, Any]]) -> str:
    statuses = {str(row_status or "").strip().lower()}
    for evidence in runtime_rows:
        freshness = evidence.get("freshness_status")
        if isinstance(freshness, dict):
            statuses.add(str(freshness.get("status") or "").strip().lower())
    for claim in claims:
        statuses.add(str(claim.get("verification_status") or "").strip().lower())
    if "contradicted" in statuses:
        return "contradicted"
    if "stale" in statuses:
        return "stale"
    if "due" in statuses or "scheduled" in statuses:
        return "due"
    if "superseded" in statuses:
        return "superseded"
    if "unknown" in statuses:
        return "unknown"
    return "current"


def contradiction_edges_for_claims(task_id: str, claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    for claim in claims:
        if claim.get("verification_status") != "contradicted":
            continue
        claim_id = str(claim.get("claim_id") or "unknown")
        evidence_ids = unique(ref_evidence_ids(claim.get("evidence_refs")) + ref_evidence_ids(claim.get("citation_refs")))
        if not evidence_ids:
            evidence_ids = ["unknown"]
        for evidence_id in evidence_ids:
            edges.append(
                {
                    "from_claim_id": claim_id,
                    "to_evidence_id": evidence_id,
                    "task_id": task_id,
                    "reason": str(claim.get("failure_reason") or "claim contradicted by mapped evidence"),
                }
            )
    return edges


def memory_entry_from_row(
    ops_dir: Path,
    index_number: int,
    row: dict[str, str],
    runtime_by_task: dict[str, list[dict[str, Any]]],
    deliverable_links_by_task: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    task_id = str(row.get("task_id") or "")
    runtime_rows = runtime_by_task.get(task_id, [])
    claims, claim_artifact_paths = claims_for_task(ops_dir, task_id)
    runtime_evidence_ids = [str(item.get("evidence_id")) for item in runtime_rows if EVIDENCE_ID_RE.match(str(item.get("evidence_id") or ""))]
    claim_ids = [str(claim.get("claim_id")) for claim in claims if CLAIM_ID_RE.match(str(claim.get("claim_id") or ""))]
    claim_evidence_ids: list[str] = []
    for claim in claims:
        claim_evidence_ids.extend(ref_evidence_ids(claim.get("evidence_refs")))
        claim_evidence_ids.extend(ref_evidence_ids(claim.get("citation_refs")))
    source_ids = unique(SOURCE_ID_RE.findall(str(row.get("source_ids") or "")))
    source_uris = unique(item.get("source_uri") for item in runtime_rows)
    contradiction_edges = contradiction_edges_for_claims(task_id, claims)
    task_dir = task_dir_for_id(ops_dir, task_id)
    task_paths = [
        relative_research_ops_path(ops_dir, task_dir / "status.json") if task_dir is not None else "",
        *(claim_artifact_paths),
    ]
    return {
        "memory_id": f"MEM-{index_number:06d}",
        "task_id": task_id,
        "title": str(row.get("title") or task_title(ops_dir, task_id)),
        "key_finding": str(row.get("key_finding") or ""),
        "claim_ids": unique(claim_ids),
        "evidence_ids": unique([*runtime_evidence_ids, *claim_evidence_ids]),
        "source_ids": source_ids,
        "source_uris": source_uris,
        "freshness_status": evidence_freshness_status(str(row.get("revalidation_status") or ""), runtime_rows, claims),
        "accepted_memory_status": str(row.get("revalidation_status") or "current"),
        "task_lineage": {
            "task_id": task_id,
            "task_dir": relative_research_ops_path(ops_dir, task_dir) if task_dir is not None else "missing",
            "supersedes": normalize_list(row.get("supersedes")),
            "superseded_by": normalize_list(row.get("superseded_by")),
            "source_of_truth_paths": unique(task_paths + [str(row.get("evidence_link") or "")]),
        },
        "deliverable_links": deliverable_links_by_task.get(task_id, []),
        "contradiction_edges": contradiction_edges,
        "accepted_memory_row": row,
    }


def schema_errors(payload: dict[str, Any], schema_name: str) -> list[dict[str, Any]]:
    try:
        schema = load_json(schema_path(schema_name))
    except ValueError as exc:
        return [{"reason": "schema_load_failed", "message": str(exc)}]
    if not isinstance(schema, dict):
        return [{"reason": "schema_not_object", "message": f"{schema_name} is not a JSON object"}]
    return [error.to_dict() for error in validate(payload, schema)]


def reflection_is_expired(record: dict[str, Any], now: datetime) -> bool:
    expires_at = parse_datetime(record.get("expires_at"))
    return expires_at is not None and expires_at < now


def normalize_reflection_record(record: dict[str, Any], ops_dir: Path, now: datetime) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    warnings: list[dict[str, Any]] = []
    payload = {key: value for key, value in record.items() if not str(key).startswith("_")}
    errors = schema_errors(payload, REFLECTION_SCHEMA_NAME)
    if errors:
        return None, [{"reason": "reflection_schema_invalid", "record": payload.get("reflection_id"), "details": errors}]
    review = payload.get("review_evidence") if isinstance(payload.get("review_evidence"), dict) else {}
    review_path = workspace_path(ops_dir, review.get("path"))
    if review_path is None or not review_path.is_file():
        warnings.append(
            {
                "reason": "reflection_review_evidence_missing",
                "reflection_id": payload.get("reflection_id"),
                "path": review.get("path"),
                "message": "reflection review evidence must point to an existing file under research_ops",
            }
        )
    if reflection_is_expired(payload, now):
        payload["status"] = "expired"
    return payload, warnings


def load_reflection_records(ops_dir: Path, now: datetime | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    current = now or utc_now()
    path = ops_dir / REFLECTION_LEDGER_RELATIVE_PATH
    rows, warnings = read_jsonl(path)
    normalized: list[dict[str, Any]] = []
    for row in rows:
        record, record_warnings = normalize_reflection_record(row, ops_dir, current)
        warnings.extend(record_warnings)
        if record is not None:
            normalized.append(record)
    return normalized, warnings


def build_evidence_memory_index(ops_dir: Path, now: datetime | None = None) -> tuple[int, dict[str, Any]]:
    current = now or utc_now()
    ops_dir = Path(ops_dir)
    if not ops_dir.is_dir():
        return MALFORMED, {
            "ok": False,
            "action": "evidence_memory_update",
            "reason": "ops_dir_missing",
            "ops_dir": str(ops_dir),
            "read_only": True,
            "changed": False,
            "errors": [{"reason": "ops_dir_missing", "path": str(ops_dir)}],
            "warnings": [],
        }

    accepted_index_path = ops_dir / DEFAULT_INDEX_NAME
    rows = read_index_rows(accepted_index_path, now=current)
    runtime_by_task, runtime_warnings = load_runtime_evidence_by_task(ops_dir)
    deliverable_links = load_deliverable_links_by_task(ops_dir)
    entries = [
        memory_entry_from_row(ops_dir, index, row, runtime_by_task, deliverable_links)
        for index, row in enumerate(rows, start=1)
    ]
    reflections, reflection_warnings = load_reflection_records(ops_dir, now=current)
    active_reflections = [row for row in reflections if row.get("status") == "active"]
    contradiction_edges = [edge for entry in entries for edge in entry.get("contradiction_edges", [])]
    stale_entries = [entry for entry in entries if entry.get("freshness_status") in {"stale", "due", "contradicted"}]
    warnings: list[dict[str, Any]] = [*runtime_warnings, *reflection_warnings]
    if not accepted_index_path.exists():
        warnings.append(
            {
                "reason": "accepted_memory_index_missing",
                "path": str(accepted_index_path),
                "message": "structured evidence memory has no accepted outputs to index yet",
            }
        )
    for entry in stale_entries:
        warnings.append(
            {
                "reason": "stale_or_contradicted_evidence_visible",
                "memory_id": entry.get("memory_id"),
                "task_id": entry.get("task_id"),
                "freshness_status": entry.get("freshness_status"),
            }
        )

    payload = {
        "ok": True,
        "action": "evidence_memory_update",
        "schema_version": "1.0",
        "framework_version": INDEX_FRAMEWORK_VERSION,
        "generated_at": iso_now(current),
        "ops_dir": str(ops_dir),
        "read_only": True,
        "changed": False,
        "source_files": {
            "accepted_outputs_index": str(accepted_index_path),
            "runtime_evidence_objects": str(ops_dir / "runtime" / "evidence_objects.jsonl"),
            "targeted_reflections": str(ops_dir / REFLECTION_LEDGER_RELATIVE_PATH),
            "deliverable_manifest": str(ops_dir / "deliverables" / "deliverable_manifest.json"),
        },
        "entry_count": len(entries),
        "contradiction_count": len(contradiction_edges),
        "stale_evidence_count": len(stale_entries),
        "reflection_count": len(active_reflections),
        "entries": entries,
        "contradiction_edges": contradiction_edges,
        "targeted_reflections": active_reflections,
        "warnings": warnings,
    }
    errors = schema_errors(payload, INDEX_SCHEMA_NAME)
    if errors:
        payload["ok"] = False
        payload["errors"] = errors
        return INVALID, payload
    payload["errors"] = []
    return SUCCESS, payload


def run_update(args: argparse.Namespace) -> int:
    now = parse_datetime(args.now) if args.now else utc_now()
    if now is None:
        print_json({"ok": False, "reason": "invalid_now", "now": args.now})
        return INVALID
    output_path = output_path_for(args.ops_dir, args.output)
    if output_path is None:
        print_json(
            {
                "ok": False,
                "reason": "output_outside_research_ops",
                "ops_dir": str(args.ops_dir),
                "output": str(args.output),
            }
        )
        return UNSAFE
    code, payload = build_evidence_memory_index(args.ops_dir, now=now)
    payload["read_only"] = bool(args.dry_run)
    payload["changed"] = False
    payload["index_path"] = str(output_path)
    if code == SUCCESS and not args.dry_run:
        write_payload = dict(payload)
        write_payload["read_only"] = False
        write_payload["changed"] = True
        atomic_write_json(output_path, write_payload)
        payload["changed"] = True
    payload["action"] = "evidence_memory_dry_run" if args.dry_run else "evidence_memory_update"
    print_json(payload)
    return code


def load_or_build_index(ops_dir: Path, now: datetime) -> tuple[int, dict[str, Any]]:
    index_path = ops_dir / INDEX_RELATIVE_PATH
    payload = read_json(index_path)
    if payload and payload.get("framework_version") == INDEX_FRAMEWORK_VERSION:
        return SUCCESS, payload
    code, built = build_evidence_memory_index(ops_dir, now=now)
    built["read_only"] = True
    built["changed"] = False
    built.setdefault("warnings", []).append(
        {
            "reason": "index_built_read_only",
            "path": str(index_path),
            "message": "query used a read-only in-memory index because no current index file was found",
        }
    )
    return code, built


def entry_matches_query(entry: dict[str, Any], query: str) -> float:
    haystack = " ".join(
        [
            str(entry.get("title") or ""),
            str(entry.get("key_finding") or ""),
            " ".join(entry.get("claim_ids") or []),
            " ".join(entry.get("evidence_ids") or []),
            " ".join(entry.get("source_ids") or []),
            " ".join(entry.get("source_uris") or []),
        ]
    )
    return similarity(query, haystack)


def filter_entries(payload: dict[str, Any], args: argparse.Namespace) -> list[dict[str, Any]]:
    query = str(args.query or "").strip()
    rows = payload.get("entries") if isinstance(payload.get("entries"), list) else []
    matches: list[dict[str, Any]] = []
    for entry in rows:
        if not isinstance(entry, dict):
            continue
        if args.freshness_status and entry.get("freshness_status") != args.freshness_status:
            continue
        if args.source_id and args.source_id not in entry.get("source_ids", []):
            continue
        if args.contradictions_only and not entry.get("contradiction_edges"):
            continue
        score = entry_matches_query(entry, query) if query else 1.0
        if query and score <= 0:
            continue
        item = dict(entry)
        item["similarity"] = round(score, 3)
        matches.append(item)
    matches.sort(key=lambda item: item.get("similarity", 0), reverse=True)
    return matches[: args.limit]


def reflection_text(record: dict[str, Any]) -> str:
    return " ".join(
        str(record.get(key) or "")
        for key in (
            "failure_class",
            "trigger_condition",
            "affected_stage",
            "mitigation",
            "anti_context_injection",
            "task_title",
        )
    )


def targeted_reflection_matches(
    ops_dir: Path,
    query: str,
    *,
    threshold: float = 0.2,
    max_items: int = 3,
    failure_class: str | None = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    current = now or utc_now()
    records, _warnings = load_reflection_records(ops_dir, now=current)
    query_text = str(query or "").strip()
    matches: list[dict[str, Any]] = []
    for record in records:
        if record.get("status") != "active":
            continue
        if failure_class and record.get("failure_class") != failure_class:
            continue
        score = similarity(query_text, reflection_text(record)) if query_text else 1.0
        if failure_class and not query_text:
            score = 1.0
        if score < threshold:
            continue
        item = dict(record)
        item["similarity"] = round(score, 3)
        matches.append(item)
    matches.sort(key=lambda item: item.get("similarity", 0), reverse=True)
    return matches[:max_items]


def run_query(args: argparse.Namespace) -> int:
    now = parse_datetime(args.now) if args.now else utc_now()
    if now is None:
        print_json({"ok": False, "reason": "invalid_now", "now": args.now})
        return INVALID
    code, payload = load_or_build_index(args.ops_dir, now)
    if code not in {SUCCESS, INVALID}:
        print_json(payload)
        return code
    matches = filter_entries(payload, args)
    reflections = targeted_reflection_matches(
        args.ops_dir,
        args.query or "",
        threshold=args.reflection_threshold,
        max_items=args.limit,
        failure_class=args.failure_class,
        now=now,
    )
    result = {
        "ok": code == SUCCESS,
        "action": "evidence_memory_query",
        "ops_dir": str(args.ops_dir),
        "read_only": True,
        "changed": False,
        "query": args.query or "",
        "entry_count": payload.get("entry_count", 0),
        "match_count": len(matches),
        "matches": matches,
        "targeted_reflection_count": len(reflections),
        "targeted_reflections": reflections,
        "summary": {
            "contradiction_count": payload.get("contradiction_count", 0),
            "stale_evidence_count": payload.get("stale_evidence_count", 0),
            "reflection_count": payload.get("reflection_count", 0),
        },
        "warnings": payload.get("warnings", []),
        "errors": payload.get("errors", []),
    }
    print_json(result)
    return code


def infer_ops_dir(task_dir: Path) -> Path | None:
    task_dir = task_dir.resolve(strict=False)
    if task_dir.name == "status.json":
        task_dir = task_dir.parent
    parent = task_dir.parent
    if parent.name != "tasks":
        return None
    ops_dir = parent.parent
    return ops_dir if ops_dir.name == "research_ops" else None


def next_reflection_id(ops_dir: Path) -> str:
    rows, _warnings = read_jsonl(ops_dir / REFLECTION_LEDGER_RELATIVE_PATH)
    max_id = 0
    for row in rows:
        match = re.match(r"^REFL-([0-9]{6})$", str(row.get("reflection_id") or ""))
        if match:
            max_id = max(max_id, int(match.group(1)))
    return f"REFL-{max_id + 1:06d}"


def resolve_review_evidence(ops_dir: Path, task_dir: Path, raw_path: Path) -> Path | None:
    candidates = []
    if raw_path.is_absolute():
        candidates.append(raw_path)
    else:
        candidates.append(task_dir / raw_path)
        candidates.append(ops_dir / raw_path)
    for candidate in candidates:
        resolved = candidate.resolve(strict=False)
        try:
            resolved.relative_to(ops_dir.resolve(strict=False))
        except ValueError:
            continue
        if resolved.is_file():
            return resolved
    return None


def build_reflection_record(args: argparse.Namespace, now: datetime) -> tuple[dict[str, Any] | None, list[dict[str, Any]], Path | None]:
    task_dir = args.task_dir.resolve(strict=False)
    ops_dir = infer_ops_dir(task_dir)
    if ops_dir is None:
        return None, [{"reason": "task_dir_not_under_research_ops", "task_dir": str(args.task_dir)}], None
    status = read_json(task_dir / "status.json")
    if not status:
        return None, [{"reason": "task_status_missing", "path": str(task_dir / "status.json")}], ops_dir
    task_id = str(status.get("id") or task_dir.name)
    if not TASK_ID_RE.match(task_id):
        return None, [{"reason": "invalid_task_id", "task_id": task_id}], ops_dir
    review_path = resolve_review_evidence(ops_dir, task_dir, args.review_evidence)
    if review_path is None:
        return None, [{"reason": "review_evidence_missing_or_unsafe", "path": str(args.review_evidence)}], ops_dir
    record = {
        "schema_version": "1.0",
        "framework_version": REFLECTION_FRAMEWORK_VERSION,
        "reflection_id": args.reflection_id or next_reflection_id(ops_dir),
        "created_at": iso_now(now),
        "task_id": task_id,
        "task_title": str(status.get("title") or task_dir.name),
        "failure_class": args.failure_class,
        "trigger_condition": args.trigger_condition,
        "affected_stage": args.affected_stage,
        "mitigation": args.mitigation,
        "anti_context_injection": args.anti_context,
        "review_evidence": {
            "path": relative_research_ops_path(ops_dir, review_path),
            "summary": args.review_summary or args.trigger_condition,
        },
        "source_task_dir": relative_research_ops_path(ops_dir, task_dir),
        "status": args.status,
    }
    if args.expires_at:
        record["expires_at"] = args.expires_at
    errors = schema_errors(record, REFLECTION_SCHEMA_NAME)
    return (None if errors else record), errors, ops_dir


def run_record_reflection(args: argparse.Namespace) -> int:
    now = parse_datetime(args.now) if args.now else utc_now()
    if now is None:
        print_json({"ok": False, "reason": "invalid_now", "now": args.now})
        return INVALID
    record, errors, ops_dir = build_reflection_record(args, now)
    if record is None or ops_dir is None:
        print_json(
            {
                "ok": False,
                "action": "reflection_record",
                "read_only": True,
                "changed": False,
                "errors": errors,
            }
        )
        return INVALID
    ledger_path = ops_dir / REFLECTION_LEDGER_RELATIVE_PATH
    if not args.dry_run:
        atomic_append_jsonl(ledger_path, record)
    print_json(
        {
            "ok": True,
            "action": "reflection_record",
            "ops_dir": str(ops_dir),
            "ledger_path": str(ledger_path),
            "reflection": record,
            "read_only": bool(args.dry_run),
            "changed": not args.dry_run,
            "errors": [],
            "warnings": [],
        }
    )
    return SUCCESS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build/query structured evidence memory and record targeted reflections.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    update = subparsers.add_parser("update", help="Build research_ops/memory/evidence_memory_index.json from repo artifacts.")
    update.add_argument("ops_dir", type=Path, help="Path to research_ops.")
    update.add_argument("--dry-run", action="store_true", help="Build the index payload without writing it.")
    update.add_argument("--output", type=Path, help="Override output path under research_ops.")
    update.add_argument("--now", help="Override generated_at for deterministic tests.")
    update.set_defaults(func=run_update)

    query = subparsers.add_parser("query", help="Query structured evidence memory and targeted reflections.")
    query.add_argument("ops_dir", type=Path, help="Path to research_ops.")
    query.add_argument("--query", help="Text to match against titles, findings, sources, claims, and reflections.")
    query.add_argument("--freshness-status", choices=["current", "due", "stale", "superseded", "contradicted", "unknown"], help="Limit evidence entries by freshness status.")
    query.add_argument("--source-id", help="Limit evidence entries to one DS-* source id.")
    query.add_argument("--contradictions-only", action="store_true", help="Return only entries with contradiction edges.")
    query.add_argument("--failure-class", choices=FAILURE_CLASSES, help="Limit targeted reflections to one failure class.")
    query.add_argument("--reflection-threshold", type=float, default=0.2, help="Minimum reflection relevance score.")
    query.add_argument("--limit", type=int, default=10, help="Maximum memory and reflection matches to return.")
    query.add_argument("--now", help="Override current time for deterministic reflection expiry.")
    query.set_defaults(func=run_query)

    record = subparsers.add_parser("record-reflection", help="Record one targeted reflection in research_ops/reflections.")
    record.add_argument("task_dir", type=Path, help="Task directory under research_ops/tasks.")
    record.add_argument("--failure-class", choices=FAILURE_CLASSES, required=True)
    record.add_argument("--trigger-condition", required=True)
    record.add_argument("--affected-stage", choices=AFFECTED_STAGES, required=True)
    record.add_argument("--mitigation", required=True)
    record.add_argument("--anti-context", required=True, help="Future anti-context injection text for relevant planning tasks.")
    record.add_argument("--review-evidence", type=Path, required=True, help="Review artifact path under the task or research_ops.")
    record.add_argument("--review-summary", help="Short evidence summary to store with the reflection.")
    record.add_argument("--reflection-id", help="Explicit reflection id such as REFL-000001.")
    record.add_argument("--status", choices=["active", "suppressed", "superseded"], default="active")
    record.add_argument("--expires-at", help="Optional ISO timestamp after which this reflection is not injected.")
    record.add_argument("--dry-run", action="store_true", help="Validate and print the record without writing the JSONL ledger.")
    record.add_argument("--now", help="Override created_at for deterministic tests.")
    record.set_defaults(func=run_record_reflection)

    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv or []))
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
