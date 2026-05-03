#!/usr/bin/env python3
"""Ingest API usage and enforce budget gates for async research."""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional


SUCCESS = 0
INVALID_REQUEST = 2
MALFORMED = 4

LEDGER_NAME = "cost_ledger.csv"
LEDGER_HEADER = [
    "date",
    "item_id",
    "role",
    "model_or_tool",
    "usage_source",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "input_usd",
    "output_usd",
    "api_usd",
    "compute_usd",
    "amount_usd",
    "human_minutes",
    "status",
    "actual",
    "monthly_budget_usd",
    "weekly_budget_usd",
    "notes",
]
AMOUNT_FIELDS = ("amount_usd", "cost_usd", "usd", "total_usd", "api_usd", "compute_usd")
DATE_FIELDS = ("date", "created_at", "timestamp", "period_start")

INPUT_TOKEN_PATHS = (
    ("usage", "input_tokens"),
    ("usage", "prompt_tokens"),
    ("usage", "prompt_token_count"),
    ("usage_metadata", "input_token_count"),
    ("usage_metadata", "prompt_token_count"),
    ("body", "usage", "input_tokens"),
    ("body", "usage", "prompt_tokens"),
    ("response", "usage", "input_tokens"),
    ("response", "usage", "prompt_tokens"),
    ("response", "body", "usage", "input_tokens"),
    ("response", "body", "usage", "prompt_tokens"),
)
OUTPUT_TOKEN_PATHS = (
    ("usage", "output_tokens"),
    ("usage", "completion_tokens"),
    ("usage", "completion_token_count"),
    ("usage_metadata", "output_token_count"),
    ("usage_metadata", "candidates_token_count"),
    ("body", "usage", "output_tokens"),
    ("body", "usage", "completion_tokens"),
    ("response", "usage", "output_tokens"),
    ("response", "usage", "completion_tokens"),
    ("response", "body", "usage", "output_tokens"),
    ("response", "body", "usage", "completion_tokens"),
)
TOTAL_TOKEN_PATHS = (
    ("usage", "total_tokens"),
    ("usage", "total_token_count"),
    ("usage_metadata", "total_token_count"),
    ("body", "usage", "total_tokens"),
    ("response", "usage", "total_tokens"),
    ("response", "body", "usage", "total_tokens"),
)


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def safe_float(value: Any) -> Optional[float]:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def safe_int(value: Any) -> Optional[int]:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


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


def value_at_path(payload: Any, path: tuple[str, ...]) -> Any:
    current = payload
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def first_int(payload: dict[str, Any], paths: tuple[tuple[str, ...], ...]) -> Optional[int]:
    for path in paths:
        parsed = safe_int(value_at_path(payload, path))
        if parsed is not None:
            return parsed
    return None


def read_usage_records(path: Path) -> list[dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"cannot read usage file {path}: {exc}") from exc

    records: list[dict[str, Any]] = []
    if path.suffix == ".jsonl":
        for line_number, raw in enumerate(text.splitlines(), start=1):
            if not raw.strip():
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"malformed JSONL at {path}:{line_number}: {exc}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"usage JSONL row is not an object at {path}:{line_number}")
            records.append(payload)
        return records

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed usage JSON in {path}: {exc}") from exc
    if isinstance(payload, dict):
        if isinstance(payload.get("data"), list):
            for index, item in enumerate(payload["data"]):
                if not isinstance(item, dict):
                    raise ValueError(f"usage data row is not an object at index {index}")
                records.append(item)
            return records
        return [payload]
    if isinstance(payload, list):
        for index, item in enumerate(payload):
            if not isinstance(item, dict):
                raise ValueError(f"usage JSON row is not an object at index {index}")
            records.append(item)
        return records
    raise ValueError(f"usage file is not a JSON object, array, or JSONL object stream: {path}")


def usage_from_record(record: dict[str, Any]) -> tuple[int, int, int]:
    input_tokens = first_int(record, INPUT_TOKEN_PATHS)
    output_tokens = first_int(record, OUTPUT_TOKEN_PATHS)
    total_tokens = first_int(record, TOTAL_TOKEN_PATHS)

    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens
    if input_tokens is None and total_tokens is not None and output_tokens is not None:
        input_tokens = max(total_tokens - output_tokens, 0)
    if output_tokens is None and total_tokens is not None and input_tokens is not None:
        output_tokens = max(total_tokens - input_tokens, 0)

    if input_tokens is None and output_tokens is None and total_tokens is None:
        raise ValueError("no token usage fields found")
    return input_tokens or 0, output_tokens or 0, total_tokens or (input_tokens or 0) + (output_tokens or 0)


def aggregate_usage(records: list[dict[str, Any]]) -> dict[str, int]:
    if not records:
        raise ValueError("usage file contains no records")
    input_tokens = 0
    output_tokens = 0
    total_tokens = 0
    for record in records:
        item_input, item_output, item_total = usage_from_record(record)
        input_tokens += item_input
        output_tokens += item_output
        total_tokens += item_total
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


def ledger_path(ops_dir: Path) -> Path:
    return ops_dir / LEDGER_NAME


def read_ledger_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.exists() or path.stat().st_size == 0:
        return list(LEDGER_HEADER), []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = [{str(key): str(value) for key, value in row.items() if key is not None} for row in reader]
    merged = list(fieldnames)
    for field in LEDGER_HEADER:
        if field not in merged:
            merged.append(field)
    return merged, rows


def atomic_write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with tmp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
    os.replace(tmp, path)


def append_ledger_row(path: Path, row: dict[str, Any]) -> None:
    fieldnames, rows = read_ledger_rows(path)
    rows.append({field: row.get(field, "") for field in fieldnames})
    atomic_write_csv(path, fieldnames, rows)


def ledger_amount(row: dict[str, str]) -> float:
    for field in AMOUNT_FIELDS:
        value = safe_float(row.get(field))
        if value is not None:
            return value
    return 0.0


def ledger_date(row: dict[str, str]) -> Optional[datetime]:
    for field in DATE_FIELDS:
        parsed = parse_datetime(row.get(field))
        if parsed is not None:
            return parsed
    return None


def max_budget(rows: list[dict[str, str]], field: str) -> Optional[float]:
    values = [safe_float(row.get(field)) for row in rows]
    values = [value for value in values if value is not None and value > 0]
    return max(values) if values else None


def cost_window(path: Path, now: datetime, monthly_budget: Optional[float], weekly_budget: Optional[float]) -> dict[str, Any]:
    _, rows = read_ledger_rows(path)
    monthly_budget = monthly_budget or max_budget(rows, "monthly_budget_usd")
    weekly_budget = weekly_budget or max_budget(rows, "weekly_budget_usd")

    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    week_start = now - timedelta(days=now.weekday())
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)

    monthly_cost = 0.0
    weekly_cost = 0.0
    undated_cost = 0.0
    input_tokens = 0
    output_tokens = 0
    total_tokens = 0
    actual_usage_rows = 0
    for row in rows:
        amount = ledger_amount(row)
        parsed_date = ledger_date(row)
        if parsed_date is None:
            undated_cost += amount
        else:
            if parsed_date >= month_start:
                monthly_cost += amount
            if parsed_date >= week_start:
                weekly_cost += amount
        row_input = safe_int(row.get("input_tokens")) or 0
        row_output = safe_int(row.get("output_tokens")) or 0
        row_total = safe_int(row.get("total_tokens")) or row_input + row_output
        input_tokens += row_input
        output_tokens += row_output
        total_tokens += row_total
        if row.get("actual", "").strip().lower() == "true" and row_total > 0:
            actual_usage_rows += 1

    if rows and all(ledger_date(row) is None for row in rows):
        monthly_cost = undated_cost
        weekly_cost = undated_cost

    return {
        "row_count": len(rows),
        "monthly_cost_usd": round(monthly_cost, 6),
        "weekly_cost_usd": round(weekly_cost, 6),
        "monthly_budget_usd": monthly_budget,
        "weekly_budget_usd": weekly_budget,
        "monthly_usage_ratio": round(monthly_cost / monthly_budget, 6) if monthly_budget else None,
        "weekly_usage_ratio": round(weekly_cost / weekly_budget, 6) if weekly_budget else None,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "actual_usage_rows": actual_usage_rows,
    }


def run_ingest_usage(args: argparse.Namespace) -> int:
    try:
        usage = aggregate_usage(read_usage_records(args.usage_file))
    except ValueError as exc:
        print_json({"ok": False, "reason": "usage_ingest_failed", "error": str(exc), "usage_file": str(args.usage_file)})
        return MALFORMED

    input_usd = round(usage["input_tokens"] / 1_000_000 * args.input_usd_per_1m, 8)
    output_usd = round(usage["output_tokens"] / 1_000_000 * args.output_usd_per_1m, 8)
    api_usd = args.api_usd if args.api_usd is not None else round(input_usd + output_usd, 8)
    amount_usd = round(api_usd + args.compute_usd, 8)
    row = {
        "date": args.date or iso_now(),
        "item_id": args.item_id,
        "role": args.role,
        "model_or_tool": args.model,
        "usage_source": str(args.usage_file),
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "total_tokens": usage["total_tokens"],
        "input_usd": input_usd,
        "output_usd": output_usd,
        "api_usd": api_usd,
        "compute_usd": args.compute_usd,
        "amount_usd": amount_usd,
        "human_minutes": args.human_minutes,
        "status": args.status,
        "actual": "true",
        "monthly_budget_usd": args.monthly_budget_usd if args.monthly_budget_usd is not None else "",
        "weekly_budget_usd": args.weekly_budget_usd if args.weekly_budget_usd is not None else "",
        "notes": args.notes or "programmatic_usage_ingest",
    }
    path = args.ledger or ledger_path(args.ops_dir)
    if not args.dry_run:
        append_ledger_row(path, row)
    print_json(
        {
            "ok": True,
            "action": "dry_run_usage_ingested" if args.dry_run else "usage_ingested",
            "ledger": str(path),
            "row": row,
        }
    )
    return SUCCESS


def run_budget_check(args: argparse.Namespace) -> int:
    path = args.ledger or ledger_path(args.ops_dir)
    now = datetime.now(timezone.utc)
    window = cost_window(path, now, args.monthly_budget_usd, args.weekly_budget_usd)
    proposed_cost = round(args.proposed_api_usd + args.proposed_compute_usd, 8)
    projected_monthly = round(window["monthly_cost_usd"] + proposed_cost, 8)
    projected_weekly = round(window["weekly_cost_usd"] + proposed_cost, 8)
    monthly_budget = window["monthly_budget_usd"]
    weekly_budget = window["weekly_budget_usd"]
    projected_monthly_ratio = round(projected_monthly / monthly_budget, 6) if monthly_budget else None
    projected_weekly_ratio = round(projected_weekly / weekly_budget, 6) if weekly_budget else None
    monthly_halt = projected_monthly_ratio is not None and projected_monthly_ratio >= args.threshold
    weekly_halt = projected_weekly_ratio is not None and projected_weekly_ratio >= args.threshold
    halt = monthly_halt or weekly_halt
    result = {
        "ok": not halt,
        "halt": halt,
        "action": args.action,
        "item_id": args.item_id,
        "ledger": str(path),
        "threshold": args.threshold,
        "proposed_cost_usd": proposed_cost,
        "monthly_cost_usd": window["monthly_cost_usd"],
        "weekly_cost_usd": window["weekly_cost_usd"],
        "projected_monthly_cost_usd": projected_monthly,
        "projected_weekly_cost_usd": projected_weekly,
        "monthly_budget_usd": monthly_budget,
        "weekly_budget_usd": weekly_budget,
        "projected_monthly_usage_ratio": projected_monthly_ratio,
        "projected_weekly_usage_ratio": projected_weekly_ratio,
        "reason": "budget_threshold_exceeded" if halt else "budget_available",
        "next_step": "route to needs_human before promotion or expensive work" if halt else "continue",
    }
    print_json(result)
    return INVALID_REQUEST if halt else SUCCESS


def run_summary(args: argparse.Namespace) -> int:
    path = args.ledger or ledger_path(args.ops_dir)
    window = cost_window(path, datetime.now(timezone.utc), args.monthly_budget_usd, args.weekly_budget_usd)
    print_json({"ok": True, "ledger": str(path), **window})
    return SUCCESS


def add_budget_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--monthly-budget-usd", type=float)
    parser.add_argument("--weekly-budget-usd", type=float)


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Programmatically ingest API usage and check budgets.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest = subparsers.add_parser("ingest-usage", help="Append actual API token usage to cost_ledger.csv.")
    ingest.add_argument("ops_dir", type=Path)
    ingest.add_argument("--usage-file", type=Path, required=True)
    ingest.add_argument("--item-id", required=True)
    ingest.add_argument("--role", required=True)
    ingest.add_argument("--model", required=True)
    ingest.add_argument("--input-usd-per-1m", type=float, default=0.0)
    ingest.add_argument("--output-usd-per-1m", type=float, default=0.0)
    ingest.add_argument("--api-usd", type=float)
    ingest.add_argument("--compute-usd", type=float, default=0.0)
    ingest.add_argument("--human-minutes", type=float, default=0.0)
    ingest.add_argument("--status", default="completed")
    ingest.add_argument("--notes")
    ingest.add_argument("--date")
    ingest.add_argument("--ledger", type=Path)
    ingest.add_argument("--dry-run", action="store_true")
    add_budget_args(ingest)

    budget = subparsers.add_parser("budget-check", help="Exit nonzero when projected spend crosses a threshold.")
    budget.add_argument("ops_dir", type=Path)
    budget.add_argument("--item-id", required=True)
    budget.add_argument("--action", default="expensive_task")
    budget.add_argument("--proposed-api-usd", type=float, default=0.0)
    budget.add_argument("--proposed-compute-usd", type=float, default=0.0)
    budget.add_argument("--threshold", type=float, default=0.8)
    budget.add_argument("--ledger", type=Path)
    add_budget_args(budget)

    summary = subparsers.add_parser("summary", help="Summarize current ledger spend and actual usage tokens.")
    summary.add_argument("ops_dir", type=Path)
    summary.add_argument("--ledger", type=Path)
    add_budget_args(summary)

    return parser.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    if args.command == "ingest-usage":
        return run_ingest_usage(args)
    if args.command == "budget-check":
        return run_budget_check(args)
    if args.command == "summary":
        return run_summary(args)
    print_json({"ok": False, "reason": "unknown_command", "command": args.command})
    return INVALID_REQUEST


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
