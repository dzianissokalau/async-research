#!/usr/bin/env python3
"""Render read-only operational metrics for async research workspaces."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from async_research_workflow.resources import schema_path
from async_research_workflow.scripts.decision_log import read_decisions
from async_research_workflow.scripts.validate_json_artifact import load_json as load_schema_json
from async_research_workflow.scripts.validate_json_artifact import validate


SUCCESS = 0
INVALID_REQUEST = 3
MALFORMED = 4

SCHEMA_VERSION = "1.0"
UNAVAILABLE = "unavailable"

REVIEW_ACTIVE_STATUSES = {"awaiting_review", "single_review", "panel_review"}
TERMINAL_STATUSES = {"accepted", "rejected"}
HUMAN_STATUSES = {"needs_human"}

DIRECT_AMOUNT_FIELDS = ("amount_usd", "cost_usd", "usd", "total_usd")
COMPONENT_AMOUNT_FIELDS = ("api_usd", "compute_usd")
PROMOTION_START_FIELDS = ("promoted_at", "queued_at", "created_at")
REVIEW_START_FIELDS = ("review_started_at", "review_panel_started_at", "awaiting_review_since")
OPEN_REVIEW_START_FIELDS = REVIEW_START_FIELDS + ("updated_at",)
HUMAN_START_FIELDS = ("human_gate_opened_at", "needs_human_since", "updated_at")
RESOLVED_HUMAN_START_FIELDS = ("human_gate_opened_at", "needs_human_since")
STATUS_SCHEMA = load_schema_json(schema_path("task_status.schema.json"))


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_datetime(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.strptime(value[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def safe_float(value: Any) -> Optional[float]:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def rounded(value: float, digits: int = 2) -> float:
    return round(value, digits)


def first_datetime(payload: dict[str, Any], fields: Iterable[str]) -> tuple[Optional[datetime], str]:
    for field in fields:
        parsed = parse_datetime(payload.get(field))
        if parsed is not None:
            return parsed, field
    return None, UNAVAILABLE


def duration_between(start: Optional[datetime], end: Optional[datetime]) -> tuple[Optional[float], Optional[str]]:
    if start is None or end is None:
        return None, "missing_timestamp"
    if end < start:
        return None, "backwards_timestamp_range"
    return rounded((end - start).total_seconds() / 3600, 2), None


def read_json_object(path: Path) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        return None, "status_json_unreadable"
    except json.JSONDecodeError:
        return None, "status_json_malformed"
    if not isinstance(payload, dict):
        return None, "status_json_not_object"
    return payload, None


def task_id_for(path: Path, payload: dict[str, Any]) -> str:
    value = payload.get("id")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return path.parent.name


def review_tier(payload: dict[str, Any]) -> str:
    policy = payload.get("review_policy")
    if isinstance(policy, dict):
        tier = policy.get("tier")
        if isinstance(tier, int) and not isinstance(tier, bool):
            return str(tier)
        if isinstance(tier, str) and tier.strip():
            return tier.strip()
    return UNAVAILABLE


def task_record(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_dir": path.parent,
        "status_path": path,
        "task_id": task_id_for(path, payload),
        "status": str(payload.get("status", "unknown")),
        "tier": review_tier(payload),
        "payload": payload,
    }


def status_schema_errors(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [error.to_dict() for error in validate(payload, STATUS_SCHEMA)]


def read_task_records(ops_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    tasks_dir = ops_dir / "tasks"
    warnings: list[dict[str, Any]] = []
    if not tasks_dir.exists():
        return [], [{"reason": "tasks_dir_missing", "path": str(tasks_dir)}]

    records: list[dict[str, Any]] = []
    for status_path in sorted(tasks_dir.glob("*/status.json")):
        payload, reason = read_json_object(status_path)
        if payload is None:
            warnings.append({"reason": reason, "path": str(status_path)})
            continue
        errors = status_schema_errors(payload)
        if errors:
            warnings.append(
                {
                    "reason": "status_schema_invalid",
                    "path": str(status_path),
                    "error_count": len(errors),
                    "errors": errors[:5],
                }
            )
            continue
        records.append(task_record(status_path, payload))
    return records, warnings


def duration_summary(items: list[dict[str, Any]], value_key: str) -> dict[str, Any]:
    values = [float(item[value_key]) for item in items if isinstance(item.get(value_key), (int, float))]
    return {
        "item_count": len(items),
        "available_count": len(values),
        "unavailable_count": len(items) - len(values),
        "average_hours": rounded(sum(values) / len(values)) if values else UNAVAILABLE,
        "max_hours": rounded(max(values)) if values else UNAVAILABLE,
        "items": items,
    }


def grouped_duration_summary(items: list[dict[str, Any]], group_key: str, value_key: str) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        groups.setdefault(str(item.get(group_key, UNAVAILABLE)), []).append(item)
    return {
        key: duration_summary(group_items, value_key)
        for key, group_items in sorted(groups.items())
    }


def open_state_item(
    record: dict[str, Any],
    now: datetime,
    start_fields: tuple[str, ...],
    value_key: str,
) -> dict[str, Any]:
    start, start_field = first_datetime(record["payload"], start_fields)
    duration, reason = duration_between(start, now)
    item = {
        "task_id": record["task_id"],
        "status": record["status"],
        "tier": record["tier"],
        "since_field": start_field,
    }
    if duration is None:
        item[value_key] = UNAVAILABLE
        item["unavailable_reason"] = reason
    else:
        item[value_key] = duration
    return item


def open_state_summary(
    records: list[dict[str, Any]],
    now: datetime,
    predicate: Any,
    start_fields: tuple[str, ...],
) -> dict[str, Any]:
    items = [
        open_state_item(record, now, start_fields, "age_hours")
        for record in records
        if predicate(record)
    ]
    return duration_summary(items, "age_hours")


def review_latency_items(records: list[dict[str, Any]], now: datetime) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for record in records:
        payload = record["payload"]
        status = record["status"]
        if status in REVIEW_ACTIVE_STATUSES:
            start, start_field = first_datetime(payload, OPEN_REVIEW_START_FIELDS)
            duration, unavailable_reason = duration_between(start, now)
            item = {
                "task_id": record["task_id"],
                "status": status,
                "tier": record["tier"],
                "mode": "open",
                "start_field": start_field,
            }
        elif status in TERMINAL_STATUSES:
            start, start_field = first_datetime(payload, REVIEW_START_FIELDS)
            end, end_field = first_datetime(payload, ("updated_at",))
            duration, unavailable_reason = duration_between(start, end)
            item = {
                "task_id": record["task_id"],
                "status": status,
                "tier": record["tier"],
                "mode": "resolved",
                "start_field": start_field,
                "end_field": end_field,
            }
        else:
            continue
        if duration is None:
            item["latency_hours"] = UNAVAILABLE
            item["unavailable_reason"] = unavailable_reason
        else:
            item["latency_hours"] = duration
        items.append(item)
    return items


def decision_dates_by_item(ops_dir: Path) -> tuple[dict[str, datetime], int]:
    decisions = read_decisions(ops_dir / "decisions.md")
    dates: dict[str, datetime] = {}
    for row in decisions:
        item_id = str(row.get("item_id", "")).strip()
        parsed = parse_datetime(row.get("date"))
        if not item_id or parsed is None:
            continue
        if item_id not in dates or parsed > dates[item_id]:
            dates[item_id] = parsed
    return dates, len(decisions)


def human_decision_latency(records: list[dict[str, Any]], ops_dir: Path, now: datetime) -> dict[str, Any]:
    decision_dates, decision_count = decision_dates_by_item(ops_dir)
    open_items: list[dict[str, Any]] = []
    resolved_items: list[dict[str, Any]] = []

    for record in records:
        payload = record["payload"]
        is_open = record["status"] in HUMAN_STATUSES or payload.get("requires_human") is True
        if is_open:
            open_items.append(open_state_item(record, now, HUMAN_START_FIELDS, "age_hours"))
            continue
        if payload.get("previous_status") != "needs_human" and record["task_id"] not in decision_dates:
            continue
        start, start_field = first_datetime(payload, RESOLVED_HUMAN_START_FIELDS)
        end = decision_dates.get(record["task_id"])
        end_field = "decisions.md" if end is not None else UNAVAILABLE
        if end is None:
            end, end_field = first_datetime(payload, ("updated_at",))
        duration, unavailable_reason = duration_between(start, end)
        item = {
            "task_id": record["task_id"],
            "status": record["status"],
            "tier": record["tier"],
            "start_field": start_field,
            "end_field": end_field,
        }
        if duration is None:
            item["latency_hours"] = UNAVAILABLE
            item["unavailable_reason"] = unavailable_reason
        else:
            item["latency_hours"] = duration
        resolved_items.append(item)

    return {
        "decision_log_rows": decision_count,
        "open": duration_summary(open_items, "age_hours"),
        "resolved": duration_summary(resolved_items, "latency_hours"),
    }


def terminal_progression(records: list[dict[str, Any]]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for record in records:
        if record["status"] not in TERMINAL_STATUSES:
            continue
        payload = record["payload"]
        start, start_field = first_datetime(payload, PROMOTION_START_FIELDS)
        end, end_field = first_datetime(payload, ("updated_at",))
        duration, unavailable_reason = duration_between(start, end)
        item = {
            "task_id": record["task_id"],
            "status": record["status"],
            "tier": record["tier"],
            "start_field": start_field,
            "end_field": end_field,
        }
        if duration is None:
            item["latency_hours"] = UNAVAILABLE
            item["unavailable_reason"] = unavailable_reason
        else:
            item["latency_hours"] = duration
        items.append(item)

    return {
        "all": duration_summary(items, "latency_hours"),
        "by_status": grouped_duration_summary(items, "status", "latency_hours"),
    }


def amount_from_row(row: dict[str, str]) -> Optional[float]:
    for field in DIRECT_AMOUNT_FIELDS:
        value = safe_float(row.get(field))
        if value is not None:
            return value
    total = 0.0
    found = False
    for field in COMPONENT_AMOUNT_FIELDS:
        value = safe_float(row.get(field))
        if value is not None:
            found = True
            total += value
    return total if found else None


def read_cost_rows(ops_dir: Path) -> tuple[bool, list[dict[str, Any]]]:
    ledger = ops_dir / "cost_ledger.csv"
    if not ledger.exists():
        return False, []
    rows: list[dict[str, Any]] = []
    with ledger.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for line_number, raw in enumerate(reader, start=2):
            clean = {str(key): str(value) for key, value in raw.items() if key is not None}
            item_id = clean.get("item_id", "").strip()
            amount = amount_from_row(clean)
            rows.append(
                {
                    "item_id": item_id,
                    "item_key": Path(item_id).name if item_id else "",
                    "amount_usd": amount if amount is not None else UNAVAILABLE,
                    "amount_available": amount is not None,
                    "line_number": line_number,
                }
            )
    return True, rows


def status_ids(records: list[dict[str, Any]], status: str) -> set[str]:
    return {record["task_id"] for record in records if record["status"] == status}


def row_matches_id(row: dict[str, Any], item_id: str) -> bool:
    return row.get("item_id") == item_id or row.get("item_key") == item_id


def cost_coverage(rows: list[dict[str, Any]], ids: set[str]) -> dict[str, Any]:
    matched_ids: set[str] = set()
    known_cost = 0.0
    malformed_rows = 0
    for item_id in ids:
        matches = [row for row in rows if row_matches_id(row, item_id)]
        if not matches:
            continue
        matched_ids.add(item_id)
        for row in matches:
            if row.get("amount_available") is True:
                known_cost += float(row["amount_usd"])
            else:
                malformed_rows += 1
    unmatched_ids = sorted(ids - matched_ids)
    return {
        "known_cost_usd": rounded(known_cost, 4),
        "matched_count": len(matched_ids),
        "unmatched_count": len(unmatched_ids),
        "unmatched_ids": unmatched_ids,
        "malformed_cost_row_count": malformed_rows,
        "complete": bool(ids) and len(unmatched_ids) == 0 and malformed_rows == 0,
    }


def per_output_cost(coverage: dict[str, Any], count: int, available: bool) -> float | str:
    if not available or count <= 0 or coverage.get("complete") is not True:
        return UNAVAILABLE
    return rounded(float(coverage["known_cost_usd"]) / count, 4)


def cost_trends(records: list[dict[str, Any]], ops_dir: Path) -> dict[str, Any]:
    ledger_available, rows = read_cost_rows(ops_dir)
    accepted_ids = status_ids(records, "accepted")
    rejected_ids = status_ids(records, "rejected")
    accepted_coverage = cost_coverage(rows, accepted_ids) if ledger_available else cost_coverage([], accepted_ids)
    rejected_coverage = cost_coverage(rows, rejected_ids) if ledger_available else cost_coverage([], rejected_ids)
    known_total_cost = sum(float(row["amount_usd"]) for row in rows if row.get("amount_available") is True) if ledger_available else 0.0
    malformed_row_count = sum(1 for row in rows if row.get("amount_available") is not True) if ledger_available else 0
    mapped_cost = float(accepted_coverage["known_cost_usd"]) + float(rejected_coverage["known_cost_usd"])
    warnings = [
        {
            "reason": "cost_ledger_amount_unavailable",
            "path": str(ops_dir / "cost_ledger.csv"),
            "line_number": row["line_number"],
            "item_id": row.get("item_id", ""),
        }
        for row in rows
        if row.get("amount_available") is not True
    ]

    return {
        "status": "available" if ledger_available else UNAVAILABLE,
        "ledger_path": str(ops_dir / "cost_ledger.csv"),
        "ledger_row_count": len(rows),
        "total_cost_usd": rounded(known_total_cost, 4) if ledger_available and malformed_row_count == 0 else UNAVAILABLE,
        "known_total_cost_usd": rounded(known_total_cost, 4) if ledger_available else UNAVAILABLE,
        "malformed_cost_row_count": malformed_row_count if ledger_available else UNAVAILABLE,
        "accepted_output_count": len(accepted_ids),
        "accepted_output_matched_count": accepted_coverage["matched_count"] if ledger_available else UNAVAILABLE,
        "accepted_output_unmatched_count": accepted_coverage["unmatched_count"] if ledger_available else UNAVAILABLE,
        "accepted_output_unmatched_ids": accepted_coverage["unmatched_ids"] if ledger_available else [],
        "accepted_output_malformed_cost_row_count": accepted_coverage["malformed_cost_row_count"] if ledger_available else UNAVAILABLE,
        "accepted_output_cost_usd": accepted_coverage["known_cost_usd"] if ledger_available else UNAVAILABLE,
        "cost_per_accepted_output_usd": per_output_cost(accepted_coverage, len(accepted_ids), ledger_available),
        "rejected_output_count": len(rejected_ids),
        "rejected_output_matched_count": rejected_coverage["matched_count"] if ledger_available else UNAVAILABLE,
        "rejected_output_unmatched_count": rejected_coverage["unmatched_count"] if ledger_available else UNAVAILABLE,
        "rejected_output_unmatched_ids": rejected_coverage["unmatched_ids"] if ledger_available else [],
        "rejected_output_malformed_cost_row_count": rejected_coverage["malformed_cost_row_count"] if ledger_available else UNAVAILABLE,
        "rejected_output_cost_usd": rejected_coverage["known_cost_usd"] if ledger_available else UNAVAILABLE,
        "cost_per_rejected_output_usd": per_output_cost(rejected_coverage, len(rejected_ids), ledger_available),
        "unmapped_cost_usd": rounded(max(0.0, known_total_cost - mapped_cost), 4) if ledger_available else UNAVAILABLE,
        "warnings": warnings,
    }


def revision_loops(records: list[dict[str, Any]]) -> dict[str, Any]:
    counts: list[int] = []
    limit_hits = 0
    by_status: dict[str, int] = {}
    for record in records:
        payload = record["payload"]
        raw_count = payload.get("revision_count")
        count = raw_count if isinstance(raw_count, int) and not isinstance(raw_count, bool) and raw_count > 0 else 0
        counts.append(count)
        if count > 0:
            by_status[record["status"]] = by_status.get(record["status"], 0) + count
        max_revisions = payload.get("max_revisions")
        if payload.get("revision_limit_hit") is True:
            limit_hits += 1
        elif (
            count > 0
            and isinstance(max_revisions, int)
            and not isinstance(max_revisions, bool)
            and max_revisions > 0
            and count >= max_revisions
        ):
            limit_hits += 1
    return {
        "total_revision_loops": sum(counts),
        "tasks_with_revision_loops": sum(1 for count in counts if count > 0),
        "average_revision_loops_per_task": rounded(sum(counts) / len(records), 4) if records else UNAVAILABLE,
        "revision_limit_hit_count": limit_hits,
        "revision_loops_by_status": dict(sorted(by_status.items())),
    }


def status_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        counts[record["status"]] = counts.get(record["status"], 0) + 1
    return dict(sorted(counts.items()))


def build_read_model(ops_dir: Path, now: datetime) -> dict[str, Any]:
    records, warnings = read_task_records(ops_dir)
    review_items = review_latency_items(records, now)
    awaiting_review = open_state_summary(
        records,
        now,
        lambda record: record["status"] == "awaiting_review",
        ("awaiting_review_since", "updated_at"),
    )
    needs_human = open_state_summary(
        records,
        now,
        lambda record: record["status"] == "needs_human" or record["payload"].get("requires_human") is True,
        HUMAN_START_FIELDS,
    )

    cost = cost_trends(records, ops_dir)
    warnings.extend(cost.pop("warnings", []))

    return {
        "task_count": len(records),
        "status_counts": status_counts(records),
        "time_in_state": {
            "awaiting_review": awaiting_review,
            "needs_human": needs_human,
        },
        "review_latency": {
            "all": duration_summary(review_items, "latency_hours"),
            "by_tier": grouped_duration_summary(review_items, "tier", "latency_hours"),
            "by_status": grouped_duration_summary(review_items, "status", "latency_hours"),
        },
        "human_decision_latency": human_decision_latency(records, ops_dir, now),
        "promotion_to_terminal": terminal_progression(records),
        "cost": cost,
        "revision_loops": revision_loops(records),
        "warnings": warnings,
    }


def report(ops_dir: Path, now: datetime) -> tuple[int, dict[str, Any]]:
    if not ops_dir.exists() or not ops_dir.is_dir():
        return MALFORMED, {
            "ok": False,
            "reason": "workspace_missing",
            "ops_dir": str(ops_dir),
        }
    read_model = build_read_model(ops_dir, now)
    return SUCCESS, {
        "ok": True,
        "action": "operational_metrics_reported",
        "schema_version": SCHEMA_VERSION,
        "generated_at": iso_datetime(now),
        "ops_dir": str(ops_dir),
        "read_model": read_model,
        "warnings": read_model["warnings"],
    }


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render a read-only operational metrics read model for dashboard and digest consumers."
    )
    parser.add_argument("ops_dir", type=Path)
    parser.add_argument("--now", help="Override the report time as an ISO timestamp for deterministic checks.")
    return parser.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    now = parse_datetime(args.now) if args.now else utc_now()
    if now is None:
        print_json({"ok": False, "reason": "invalid_now", "now": args.now})
        return INVALID_REQUEST
    code, payload = report(args.ops_dir, now)
    print_json(payload)
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
