#!/usr/bin/env python3
"""Maintain the async research accepted outputs index."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional


SUCCESS = 0
INVALID = 2
MALFORMED = 4

HEADER = [
    "accepted_date",
    "task_id",
    "title",
    "key_finding",
    "claim_type",
    "freshness_window_days",
    "next_recheck_date",
    "revalidation_status",
    "source_ids",
    "claim_strength",
    "caveats",
    "followups",
    "supersedes",
    "superseded_by",
    "evidence_link",
]
LEGACY_HEADERS = [
    ["date", "task_id", "title", "key_finding", "claim_strength", "evidence_link", "followups"],
    ["date", "task_id", "title", "claim_strength", "evidence_path", "followups"],
]
CLAIM_ORDER = {"none": 0, "weak": 1, "suggestive": 2, "moderate": 3, "strong": 4}
DEFAULT_INDEX_NAME = "accepted_outputs_index.md"
REVALIDATION_SCHEDULE_NAME = "revalidation_schedule.md"
MANUAL_REVIEW = "manual_review"
SOURCE_REF_PATTERN = re.compile(r"\bDS-[0-9]{4}\b")
CLAIM_TYPE_FRESHNESS: dict[str, int | str] = {
    "market_price": 45,
    "market_rent": 45,
    "market_inventory": 45,
    "market_supply": 45,
    "source_data_readiness": 90,
    "methodology_note": 180,
    "framework_workflow_doc": MANUAL_REVIEW,
    "evergreen_definition": MANUAL_REVIEW,
    "general": 90,
}
TASK_TYPE_CLAIM_TYPES = {
    "data_readiness": "source_data_readiness",
    "experiment_plan": "methodology_note",
    "hypothesis_card": "methodology_note",
    "code_patch": "framework_workflow_doc",
    "weekly_synthesis": "framework_workflow_doc",
    "status_update": "framework_workflow_doc",
    "admin": "framework_workflow_doc",
}
REVALIDATION_STATUSES = {
    "current",
    "due",
    "stale",
    "scheduled",
    "revalidated",
    "superseded",
    MANUAL_REVIEW,
}
STOPWORDS = {
    "and",
    "are",
    "but",
    "can",
    "for",
    "from",
    "has",
    "have",
    "into",
    "that",
    "the",
    "this",
    "with",
}
METADATA_KEYS = {
    "schema_version",
    "framework_version",
    "framework_versions",
    "prompt_version",
    "prompt_versions",
    "reviewer_role",
    "decision",
    "claim_strength",
    "confidence",
    "updated_at",
    "created_at",
    "model",
    "model_tier",
}
RESULT_SUMMARY_KEYS = {
    "result_id",
    "run_id",
    "primary_metric",
    "baseline_results",
    "candidate_results",
    "validation_split_results",
    "robustness_results",
    "leakage_check_results",
    "claim_strength",
    "recommended_decision",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def parse_datetime(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip() or value.strip() == MANUAL_REVIEW:
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


def iso_date(value: Any) -> str:
    if isinstance(value, str) and value.strip():
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(text).date().isoformat()
        except ValueError:
            if re.match(r"^\d{4}-\d{2}-\d{2}$", value[:10]):
                return value[:10]
    return utc_now().date().isoformat()


def normalize_claim_type(value: Any, task_type: str = "") -> str:
    if isinstance(value, str) and value.strip():
        normalized = value.strip().lower().replace(" ", "_").replace("-", "_")
        aliases = {
            "market_prices": "market_price",
            "price": "market_price",
            "rent": "market_rent",
            "inventory": "market_inventory",
            "supply": "market_supply",
            "data_readiness": "source_data_readiness",
            "source_readiness": "source_data_readiness",
            "methodology": "methodology_note",
            "framework": "framework_workflow_doc",
            "workflow": "framework_workflow_doc",
            "evergreen": "evergreen_definition",
        }
        return aliases.get(normalized, normalized if normalized in CLAIM_TYPE_FRESHNESS else "general")
    return TASK_TYPE_CLAIM_TYPES.get(str(task_type), "general")


def freshness_window_for(claim_type: str, explicit: Any = None) -> str:
    if isinstance(explicit, int) and not isinstance(explicit, bool) and explicit > 0:
        return str(explicit)
    if isinstance(explicit, str) and explicit.strip():
        text = explicit.strip().lower()
        if text in {MANUAL_REVIEW, "manual", "manual-only", "manual_only"}:
            return MANUAL_REVIEW
        try:
            value = int(text)
        except ValueError:
            value = 0
        if value > 0:
            return str(value)
    configured = CLAIM_TYPE_FRESHNESS.get(claim_type, CLAIM_TYPE_FRESHNESS["general"])
    return str(configured)


def next_recheck_date(accepted_date: str, freshness_window_days: str, explicit: Any = None) -> str:
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    if freshness_window_days == MANUAL_REVIEW:
        return MANUAL_REVIEW
    try:
        days = int(freshness_window_days)
    except ValueError:
        return MANUAL_REVIEW
    parsed = parse_datetime(accepted_date)
    if parsed is None:
        return MANUAL_REVIEW
    return (parsed + timedelta(days=days)).date().isoformat()


def revalidation_status(next_recheck: str, now: datetime, explicit: Any = None, superseded_by: str = "") -> str:
    if superseded_by and superseded_by != "none":
        return "superseded"
    explicit_text = str(explicit or "").strip().lower()
    if explicit_text == "superseded":
        return explicit_text
    if next_recheck == MANUAL_REVIEW:
        return explicit_text if explicit_text in REVALIDATION_STATUSES else MANUAL_REVIEW
    parsed = parse_datetime(next_recheck)
    if parsed is None:
        return "stale"
    days_until = (parsed.date() - now.date()).days
    if days_until < 0:
        return "stale"
    if days_until <= 7:
        return "due"
    if explicit_text in {"revalidated", "scheduled"}:
        return explicit_text
    return explicit_text if explicit_text in REVALIDATION_STATUSES and explicit_text != "stale" else "current"


def normalize_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in re.split(r"[;,]", value) if item.strip()]
    return []


def join_list(items: Iterable[Any]) -> str:
    values = [str(item).strip() for item in items if str(item).strip()]
    return ", ".join(dict.fromkeys(values)) or "none"


def result_object(status: dict[str, Any]) -> dict[str, Any]:
    result = status.get("result")
    return result if isinstance(result, dict) else {}


def result_string(status: dict[str, Any], *keys: str) -> str:
    result = result_object(status)
    for key in keys:
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def source_ids_for_task(status: dict[str, Any], task_dir: Path) -> list[str]:
    refs: set[str] = set()
    data_refs = status.get("data_audit_refs")
    if isinstance(data_refs, list):
        refs.update(str(item).strip() for item in data_refs if SOURCE_REF_PATTERN.match(str(item).strip()))
    result = result_object(status)
    for key in ("source_id", "source_ids", "data_audit_refs"):
        refs.update(SOURCE_REF_PATTERN.findall(str(result.get(key, ""))))
    acceptance = read_json(task_dir / "review_panel" / "result_acceptance.json")
    if acceptance:
        governance = acceptance.get("source_governance")
        if isinstance(governance, dict):
            refs.update(SOURCE_REF_PATTERN.findall(str(governance.get("source_ids", ""))))
    worker_output = task_dir / "worker_output.md"
    if worker_output.exists():
        refs.update(SOURCE_REF_PATTERN.findall(worker_output.read_text(encoding="utf-8")))
    return sorted(refs)


def caveats_for_task(status: dict[str, Any], task_dir: Path) -> str:
    result = result_object(status)
    for key in ("caveats", "limitations", "known_limitations"):
        value = result.get(key)
        if isinstance(value, list):
            return "; ".join(str(item).strip() for item in value if str(item).strip()) or "none"
        if isinstance(value, str) and value.strip():
            return value.strip()
    acceptance = read_json(task_dir / "review_panel" / "result_acceptance.json")
    if acceptance:
        notes = acceptance.get("review_notes")
        if isinstance(notes, list) and notes:
            return "; ".join(str(item).strip() for item in notes if str(item).strip()) or "none"
    return "none"


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def read_json(path: Path) -> Optional[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def extract_json_objects(text: str) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    for match in re.finditer(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL):
        candidate = match.group(1).strip()
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            objects.append(payload)
    return objects


def looks_like_result_summary(payload: dict[str, Any]) -> bool:
    if payload.get("framework_version") == "result_acceptance_v1.0":
        return True
    return len(RESULT_SUMMARY_KEYS & set(payload)) >= 4


def load_result_summary(task_dir: Path) -> Optional[dict[str, Any]]:
    artifact_summary = read_json(task_dir / "artifacts" / "result_summary.json")
    if artifact_summary and looks_like_result_summary(artifact_summary):
        return artifact_summary
    worker_output = task_dir / "worker_output.md"
    if not worker_output.exists():
        return None
    for payload in extract_json_objects(worker_output.read_text(encoding="utf-8")):
        if looks_like_result_summary(payload):
            return payload
    return None


def compact_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def metadata_key(line: str) -> str:
    if ":" not in line:
        return ""
    key = line.split(":", 1)[0].strip().lower().replace("-", "_").replace(" ", "_")
    return key


def is_metadata_line(line: str) -> bool:
    key = metadata_key(line)
    return key in METADATA_KEYS


def useful_key_finding(value: Any) -> str:
    text = compact_text(value)
    if not text:
        return ""
    if is_metadata_line(text):
        return ""
    if text.startswith("|") or set(text) <= {"-", " "}:
        return ""
    return re.sub(r"^[-*]\s+", "", text)


def normalize_followup_text(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("reason") or value.get("title") or value.get("task") or ""
    text = compact_text(value)
    text = re.sub(r"^[-*]\s+", "", text)
    text = re.sub(r"^(?:TASK|FOLLOW-?UP)\s*:\s*", "", text, flags=re.IGNORECASE)
    text = text.strip(" ;.")
    if text.lower() in {"none", "n/a", "na", "not applicable", "no follow-ups", "no followups"}:
        return ""
    return text


def followup_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def append_followup(target: list[str], seen: set[str], value: Any) -> None:
    text = normalize_followup_text(value)
    if not text:
        return
    key = followup_key(text)
    if not key or key in seen:
        return
    target.append(text)
    seen.add(key)


def append_followups(target: list[str], seen: set[str], values: Any) -> None:
    if isinstance(values, list):
        for value in values:
            append_followup(target, seen, value)
    elif isinstance(values, str):
        for value in re.split(r"[;\n]", values):
            append_followup(target, seen, value)


def markdown_escape(value: Any) -> str:
    text = str(value if value is not None else "").replace("\n", " ").strip()
    text = re.sub(r"\s+", " ", text)
    return text.replace("|", "\\|") or "none"


def markdown_unescape(value: str) -> str:
    return value.replace("\\|", "|").strip()


def split_markdown_row(line: str) -> list[str]:
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for char in line.strip().strip("|"):
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            current.append(char)
            escaped = True
        elif char == "|":
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    cells.append("".join(current).strip())
    return cells


def normalize_header(cells: list[str]) -> list[str]:
    return [cell.lower().strip().replace(" ", "_") for cell in cells]


def canonical_index_row(row: dict[str, str], now: Optional[datetime] = None) -> dict[str, str]:
    current = now or utc_now()
    task_id = row.get("task_id", "")
    accepted_date = row.get("accepted_date") or row.get("date") or iso_date("")
    claim_type = normalize_claim_type(row.get("claim_type"))
    freshness = row.get("freshness_window_days") or row.get("freshness_window") or freshness_window_for(claim_type)
    next_recheck = row.get("next_recheck_date") or next_recheck_date(accepted_date, freshness)
    superseded_by = row.get("superseded_by") or "none"
    status = row.get("revalidation_status") or revalidation_status(next_recheck, current, superseded_by=superseded_by)
    evidence_link = row.get("evidence_link") or row.get("evidence_path") or "none"
    return {
        "accepted_date": accepted_date,
        "task_id": task_id,
        "title": row.get("title") or task_id or "accepted output",
        "key_finding": row.get("key_finding") or row.get("title") or "accepted output",
        "claim_type": claim_type,
        "freshness_window_days": freshness,
        "next_recheck_date": next_recheck,
        "revalidation_status": revalidation_status(next_recheck, current, explicit=status, superseded_by=superseded_by),
        "source_ids": row.get("source_ids") or "none",
        "claim_strength": row.get("claim_strength") or "none",
        "caveats": row.get("caveats") or "none",
        "followups": row.get("followups") or "none",
        "supersedes": row.get("supersedes") or "none",
        "superseded_by": superseded_by,
        "evidence_link": evidence_link,
    }


def read_index_rows(index_path: Path, now: Optional[datetime] = None) -> list[dict[str, str]]:
    if not index_path.exists():
        return []
    rows: list[dict[str, str]] = []
    header: Optional[list[str]] = None
    for raw in index_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line.startswith("|") or "---" in line:
            continue
        cells = split_markdown_row(line)
        normalized = normalize_header(cells)
        if normalized == HEADER or normalized in LEGACY_HEADERS:
            header = normalized
            continue
        if header is None or len(cells) != len(header):
            continue
        row = {key: markdown_unescape(value) for key, value in zip(header, cells)}
        if row.get("task_id"):
            rows.append(canonical_index_row(row, now=now))
    return rows


def write_index(index_path: Path, rows: list[dict[str, str]], now: Optional[datetime] = None) -> None:
    lines = [
        "| " + " | ".join(HEADER) + " |",
        "| " + " | ".join("---" for _ in HEADER) + " |",
    ]
    for row in rows:
        canonical = canonical_index_row(row, now=now)
        lines.append("| " + " | ".join(markdown_escape(canonical.get(column, "")) for column in HEADER) + " |")
    atomic_write_text(index_path, "\n".join(lines) + "\n")


def first_summary_line(worker_output: Path) -> str:
    if not worker_output.exists():
        return "accepted output"
    in_code = False
    for raw in worker_output.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code or not line:
            continue
        if line.startswith("#") or line.startswith("|"):
            continue
        if set(line) <= {"-", " "}:
            continue
        finding = useful_key_finding(line)
        if finding:
            return finding
    return "accepted output"


def parse_followups(worker_output: Path) -> list[str]:
    if not worker_output.exists():
        return []
    lines = worker_output.read_text(encoding="utf-8").splitlines()
    followups: list[str] = []
    in_followups = False
    for raw in lines:
        line = raw.strip()
        if line.startswith("#"):
            in_followups = "follow" in line.lower()
            continue
        if in_followups and line.startswith(("-", "*")):
            followups.append(re.sub(r"^[-*]\s+", "", line))
    return followups


def key_finding_for_task(status: dict[str, Any], task_dir: Path, summary: Optional[dict[str, Any]]) -> str:
    result = result_object(status)
    for value in (
        result.get("key_finding"),
        summary.get("claim") if isinstance(summary, dict) else None,
        summary.get("candidate_results") if isinstance(summary, dict) else None,
    ):
        finding = useful_key_finding(value)
        if finding:
            return finding
    finding = first_summary_line(task_dir / "worker_output.md")
    if finding != "accepted output":
        return finding
    return useful_key_finding(status.get("title")) or "accepted output"


def followups_for_task(
    status: dict[str, Any],
    task_dir: Path,
    summary: Optional[dict[str, Any]],
    acceptance: Optional[dict[str, Any]],
) -> str:
    result = result_object(status)
    followups: list[str] = []
    seen: set[str] = set()
    if isinstance(summary, dict):
        append_followups(followups, seen, summary.get("follow_up_tasks"))
    append_followups(followups, seen, result.get("followups"))
    if isinstance(acceptance, dict):
        append_followups(followups, seen, acceptance.get("followups"))
    append_followups(followups, seen, parse_followups(task_dir / "worker_output.md"))
    if followups:
        return "; ".join(followups)
    followup_count = result.get("followup_count")
    if isinstance(followup_count, int) and followup_count > 0:
        return f"{followup_count} follow-ups proposed"
    return "none"


def result_value(status: dict[str, Any], key: str) -> Any:
    result = status.get("result")
    if isinstance(result, dict):
        return result.get(key)
    return None


def aggregate_claim_strength(task_dir: Path) -> Optional[str]:
    aggregate = read_json(task_dir / "review_panel" / "aggregate.json")
    if not aggregate:
        return None
    aggregate_strength = aggregate.get("aggregate_claim_strength")
    if aggregate_strength in CLAIM_ORDER:
        return str(aggregate_strength)
    strongest: Optional[str] = None
    for review in aggregate.get("reviews", []):
        if not isinstance(review, dict):
            continue
        claim = review.get("claim_strength")
        if claim in CLAIM_ORDER and (strongest is None or CLAIM_ORDER[claim] > CLAIM_ORDER[strongest]):
            strongest = claim
    return strongest


def task_relative_link(ops_dir: Path, path: Path) -> str:
    try:
        return path.relative_to(ops_dir).as_posix()
    except ValueError:
        return path.as_posix()


def row_from_task(ops_dir: Path, task_dir: Path, status: dict[str, Any], now: Optional[datetime] = None) -> dict[str, str]:
    current = now or utc_now()
    worker_output = task_dir / "worker_output.md"
    result = result_object(status)
    summary = load_result_summary(task_dir)
    acceptance = read_json(task_dir / "review_panel" / "result_acceptance.json")
    followups = followups_for_task(status, task_dir, summary, acceptance)

    evidence_link = result.get("evidence_link")
    if not isinstance(evidence_link, str) or not evidence_link.strip():
        evidence_link = task_relative_link(ops_dir, worker_output if worker_output.exists() else task_dir)

    key_finding = key_finding_for_task(status, task_dir, summary)

    claim_strength = result.get("claim_strength")
    if claim_strength not in CLAIM_ORDER:
        claim_strength = aggregate_claim_strength(task_dir) or "none"

    task_type = str(status.get("type", ""))
    claim_type = normalize_claim_type(result.get("claim_type") or result.get("memory_claim_type"), task_type)
    freshness = freshness_window_for(claim_type, result.get("freshness_window_days") or result.get("freshness_window"))
    accepted_date = iso_date(result.get("accepted_date") or status.get("updated_at") or status.get("created_at"))
    next_recheck = next_recheck_date(accepted_date, freshness, result.get("next_recheck_date"))
    supersedes = join_list(normalize_list(result.get("supersedes")))
    superseded_by = join_list(normalize_list(result.get("superseded_by")))

    row = {
        "accepted_date": accepted_date,
        "task_id": str(status.get("id") or task_dir.name),
        "title": str(status.get("title") or task_dir.name),
        "key_finding": str(key_finding),
        "claim_type": claim_type,
        "freshness_window_days": freshness,
        "next_recheck_date": next_recheck,
        "revalidation_status": revalidation_status(next_recheck, current, result.get("revalidation_status"), superseded_by),
        "source_ids": join_list(source_ids_for_task(status, task_dir)),
        "claim_strength": str(claim_strength),
        "caveats": caveats_for_task(status, task_dir),
        "followups": followups,
        "supersedes": supersedes,
        "superseded_by": superseded_by,
        "evidence_link": str(evidence_link),
    }
    return canonical_index_row(row, now=current)


def accepted_task_rows(ops_dir: Path, now: Optional[datetime] = None) -> list[dict[str, str]]:
    tasks_dir = ops_dir / "tasks"
    rows: list[dict[str, str]] = []
    if not tasks_dir.exists():
        return rows
    for status_path in sorted(tasks_dir.glob("*/status.json")):
        status = read_json(status_path)
        if not status or status.get("status") != "accepted":
            continue
        rows.append(row_from_task(ops_dir, status_path.parent, status, now=now))
    return rows


def upsert_rows(existing: list[dict[str, str]], accepted_rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], int, int]:
    positions = {row["task_id"]: index for index, row in enumerate(existing) if row.get("task_id")}
    rows = list(existing)
    added = 0
    updated = 0
    for row in accepted_rows:
        task_id = row["task_id"]
        if task_id in positions:
            rows[positions[task_id]] = row
            updated += 1
        else:
            positions[task_id] = len(rows)
            rows.append(row)
            added += 1
    return rows, added, updated


def tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) > 2 and token not in STOPWORDS
    }


def similarity(query: str, row: dict[str, str]) -> float:
    query_tokens = tokens(query)
    row_tokens = tokens(" ".join(row.get(key, "") for key in ("title", "key_finding")))
    if not query_tokens or not row_tokens:
        return 0.0
    return len(query_tokens & row_tokens) / len(query_tokens | row_tokens)


def refresh_memory_rows(rows: list[dict[str, str]], now: Optional[datetime] = None) -> list[dict[str, str]]:
    current = now or utc_now()
    return [canonical_index_row(row, now=current) for row in rows]


def memory_row_bucket(row: dict[str, str]) -> str:
    status = str(row.get("revalidation_status", "")).strip().lower()
    if status == "stale":
        return "stale_outputs"
    if status in {"due", "scheduled"}:
        return "due_outputs"
    if status == "superseded":
        return "superseded_outputs"
    if status == MANUAL_REVIEW:
        return "manual_review_outputs"
    return "current_outputs"


def memory_decay_report(ops_dir: Path, now: Optional[datetime] = None, index: Optional[Path] = None) -> dict[str, Any]:
    current = now or utc_now()
    index_path = index if index is not None else ops_dir / DEFAULT_INDEX_NAME
    rows = refresh_memory_rows(read_index_rows(index_path, now=current), now=current)
    buckets: dict[str, list[dict[str, str]]] = {
        "current_outputs": [],
        "due_outputs": [],
        "stale_outputs": [],
        "manual_review_outputs": [],
        "superseded_outputs": [],
    }
    for row in rows:
        buckets[memory_row_bucket(row)].append(row)
    return {
        "ok": True,
        "index": str(index_path),
        "generated_at": current.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "row_count": len(rows),
        "current_count": len(buckets["current_outputs"]),
        "due_count": len(buckets["due_outputs"]),
        "stale_count": len(buckets["stale_outputs"]),
        "manual_review_count": len(buckets["manual_review_outputs"]),
        "superseded_count": len(buckets["superseded_outputs"]),
        **buckets,
    }


def schedule_rows_from_report(report: dict[str, Any], scheduled_at: datetime) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for bucket, priority in (("stale_outputs", "1"), ("due_outputs", "2")):
        for row in report.get(bucket, []):
            if not isinstance(row, dict):
                continue
            status = str(row.get("revalidation_status", "stale"))
            rows.append(
                {
                    "scheduled_at": scheduled_at.date().isoformat(),
                    "task_id": str(row.get("task_id", "")),
                    "claim_type": str(row.get("claim_type", "general")),
                    "revalidation_status": status,
                    "next_recheck_date": str(row.get("next_recheck_date", "")),
                    "priority": priority,
                    "source_ids": str(row.get("source_ids", "none")),
                    "action": "refresh accepted evidence before reuse as a current fact",
                    "evidence_link": str(row.get("evidence_link", "none")),
                }
            )
    return rows


def write_revalidation_schedule(path: Path, rows: list[dict[str, str]]) -> None:
    header = [
        "scheduled_at",
        "task_id",
        "claim_type",
        "revalidation_status",
        "next_recheck_date",
        "priority",
        "source_ids",
        "action",
        "evidence_link",
    ]
    lines = [
        "# Revalidation Schedule",
        "",
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(markdown_escape(row.get(column, "")) for column in header) + " |")
    atomic_write_text(path, "\n".join(lines) + "\n")


def run_update(args: argparse.Namespace) -> int:
    ops_dir = args.ops_dir
    now = parse_datetime(args.now) if args.now else utc_now()
    if now is None:
        print_json({"ok": False, "reason": "invalid_now", "now": args.now})
        return INVALID
    index_path = args.index if args.index else ops_dir / DEFAULT_INDEX_NAME
    existing = read_index_rows(index_path, now=now)
    accepted_rows = accepted_task_rows(ops_dir, now=now)
    rows, added, updated = upsert_rows(existing, accepted_rows)
    rows = refresh_memory_rows(rows, now=now)
    if not args.dry_run:
        write_index(index_path, rows, now=now)
    report = memory_decay_report(ops_dir, now=now, index=index_path) if not args.dry_run else {
        "due_count": sum(1 for row in rows if row.get("revalidation_status") in {"due", "scheduled"}),
        "stale_count": sum(1 for row in rows if row.get("revalidation_status") == "stale"),
    }
    print_json(
        {
            "ok": True,
            "action": "dry_run_updated" if args.dry_run else "updated",
            "index": str(index_path),
            "accepted_tasks_found": len(accepted_rows),
            "rows_added": added,
            "rows_updated": updated,
            "total_rows": len(rows),
            "due_count": report["due_count"],
            "stale_count": report["stale_count"],
        }
    )
    return SUCCESS


def run_check_duplicate(args: argparse.Namespace) -> int:
    index_path = args.index if args.index else args.ops_dir / DEFAULT_INDEX_NAME
    rows = read_index_rows(index_path)
    matches = []
    for row in rows:
        score = similarity(args.title, row)
        if score >= args.threshold:
            match = dict(row)
            match["similarity"] = round(score, 3)
            matches.append(match)
    matches.sort(key=lambda row: row["similarity"], reverse=True)
    print_json(
        {
            "ok": True,
            "index": str(index_path),
            "duplicate_risk": bool(matches),
            "threshold": args.threshold,
            "matches": matches,
        }
    )
    return SUCCESS


def run_revalidation_report(args: argparse.Namespace) -> int:
    now = parse_datetime(args.now) if args.now else utc_now()
    if now is None:
        print_json({"ok": False, "reason": "invalid_now", "now": args.now})
        return INVALID
    index_path = args.index if args.index else args.ops_dir / DEFAULT_INDEX_NAME
    report = memory_decay_report(args.ops_dir, now=now, index=index_path)
    schedule_path = args.schedule_path or args.ops_dir / REVALIDATION_SCHEDULE_NAME
    if args.write_schedule:
        schedule_rows = schedule_rows_from_report(report, now)
        write_revalidation_schedule(schedule_path, schedule_rows)
        report["schedule_path"] = str(schedule_path)
        report["scheduled_count"] = len(schedule_rows)
    print_json(report)
    return SUCCESS


def run_check_memory_use(args: argparse.Namespace) -> int:
    now = parse_datetime(args.now) if args.now else utc_now()
    if now is None:
        print_json({"ok": False, "reason": "invalid_now", "now": args.now})
        return INVALID
    index_path = args.index if args.index else args.ops_dir / DEFAULT_INDEX_NAME
    rows = read_index_rows(index_path, now=now)
    stale_by_task = {row["task_id"]: row for row in rows if row.get("revalidation_status") == "stale"}
    due_by_task = {row["task_id"]: row for row in rows if row.get("revalidation_status") == "due"}
    try:
        text = args.artifact.read_text(encoding="utf-8")
    except OSError as exc:
        print_json({"ok": False, "reason": "artifact_read_failed", "artifact": str(args.artifact), "error": str(exc)})
        return MALFORMED
    task_refs = sorted(set(re.findall(r"\bTASK-[0-9]{4}\b", text)))
    stale_refs = [stale_by_task[task_id] for task_id in task_refs if task_id in stale_by_task]
    due_refs = [due_by_task[task_id] for task_id in task_refs if task_id in due_by_task]
    ok = not stale_refs or args.allow_stale
    print_json(
        {
            "ok": ok,
            "artifact": str(args.artifact),
            "index": str(index_path),
            "task_refs": task_refs,
            "stale_refs": stale_refs,
            "due_refs": due_refs,
            "reason": "memory_allowed" if ok else "stale_accepted_memory_reuse",
        }
    )
    return SUCCESS if ok else INVALID


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Maintain accepted_outputs_index.md.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    update = subparsers.add_parser("update", help="Upsert accepted task rows into the accepted outputs index.")
    update.add_argument("ops_dir", type=Path)
    update.add_argument("--index", type=Path, default=None)
    update.add_argument("--dry-run", action="store_true")
    update.add_argument("--now", help="Override current time for deterministic tests, ISO-8601.")

    duplicate = subparsers.add_parser("check-duplicate", help="Check a proposed title against accepted outputs.")
    duplicate.add_argument("ops_dir", type=Path)
    duplicate.add_argument("--title", required=True)
    duplicate.add_argument("--index", type=Path, default=None)
    duplicate.add_argument("--threshold", type=float, default=0.35)

    revalidation = subparsers.add_parser("revalidation-report", help="Report accepted-memory freshness and optional revalidation schedule.")
    revalidation.add_argument("ops_dir", type=Path)
    revalidation.add_argument("--index", type=Path, default=None)
    revalidation.add_argument("--now", help="Override current time for deterministic tests, ISO-8601.")
    revalidation.add_argument("--write-schedule", action="store_true")
    revalidation.add_argument("--schedule-path", type=Path)

    memory_use = subparsers.add_parser("check-memory-use", help="Fail if an artifact cites stale accepted task memory.")
    memory_use.add_argument("ops_dir", type=Path)
    memory_use.add_argument("artifact", type=Path)
    memory_use.add_argument("--index", type=Path, default=None)
    memory_use.add_argument("--now", help="Override current time for deterministic tests, ISO-8601.")
    memory_use.add_argument("--allow-stale", action="store_true")

    return parser.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    if args.command == "update":
        return run_update(args)
    if args.command == "check-duplicate":
        return run_check_duplicate(args)
    if args.command == "revalidation-report":
        return run_revalidation_report(args)
    if args.command == "check-memory-use":
        return run_check_memory_use(args)
    print_json({"ok": False, "reason": "unknown_command", "command": args.command})
    return INVALID


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
