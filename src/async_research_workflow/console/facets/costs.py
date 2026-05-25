"""Console snapshot facet helpers."""

from __future__ import annotations

import csv
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from async_research_workflow.console.facets.base import RECENT_LIMIT
from async_research_workflow.console.facets.base import command_hint
from async_research_workflow.console.facets.base import issue
from async_research_workflow.scripts import health_check

def budget_state(ratio: Any) -> str:
    if (
        not isinstance(ratio, (int, float))
        or isinstance(ratio, bool)
        or not math.isfinite(ratio)
    ):
        return "unconfigured"
    if ratio >= 1:
        return "over_budget"
    if ratio >= 0.8:
        return "pressure"
    return "ok"

def cost_number(row: dict[str, str], fields: Iterable[str]) -> float:
    for field in fields:
        value = health_check.safe_float(row.get(field))
        if value is not None:
            return value
    return 0.0

def cost_flag(row: dict[str, str], fields: Iterable[str]) -> bool | None:
    true_values = {"1", "true", "yes", "y", "required", "requires_approval", "approved"}
    false_values = {"0", "false", "no", "n", "none", "not_required", "not required"}
    for field in fields:
        raw = row.get(field)
        if raw is None:
            continue
        value = str(raw).strip().lower()
        if value in true_values:
            return True
        if value in false_values:
            return False
    return None

def cost_label(row: dict[str, Any], fields: Iterable[str], fallback: str = "unavailable") -> str:
    for field in fields:
        value = row.get(field)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return fallback

def cost_dimension_summary(rows: list[dict[str, Any]], fields: Iterable[str]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = cost_label(row, fields)
        group = groups.setdefault(
            key,
            {
                "label": key,
                "row_count": 0,
                "amount_usd": 0.0,
                "actual_spend_usd": 0.0,
                "estimated_spend_usd": 0.0,
                "api_usd": 0.0,
                "compute_usd": 0.0,
                "data_usd": 0.0,
                "total_tokens": 0,
            },
        )
        amount = health_check.safe_float(row.get("amount_usd")) or 0.0
        group["row_count"] += 1
        group["amount_usd"] += amount
        if row.get("actual_usage") is True:
            group["actual_spend_usd"] += amount
        else:
            group["estimated_spend_usd"] += amount
        group["api_usd"] += health_check.safe_float(row.get("api_usd")) or 0.0
        group["compute_usd"] += health_check.safe_float(row.get("compute_usd")) or 0.0
        group["data_usd"] += health_check.safe_float(row.get("data_usd")) or 0.0
        group["total_tokens"] += int(row.get("total_tokens") or 0)
    return [
        {
            **group,
            "amount_usd": round(group["amount_usd"], 4),
            "actual_spend_usd": round(group["actual_spend_usd"], 4),
            "estimated_spend_usd": round(group["estimated_spend_usd"], 4),
            "api_usd": round(group["api_usd"], 4),
            "compute_usd": round(group["compute_usd"], 4),
            "data_usd": round(group["data_usd"], 4),
        }
        for group in sorted(groups.values(), key=lambda item: item["amount_usd"], reverse=True)
    ][:RECENT_LIMIT]

def cost_task_summaries(detail_rows: list[dict[str, Any]], task_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    task_by_id = {str(row.get("task_id")): row for row in task_rows if row.get("task_id")}
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in detail_rows:
        item_id = str(row.get("item_id") or "").strip() or "unmapped"
        grouped.setdefault(item_id, []).append(row)

    summaries: list[dict[str, Any]] = []
    for item_id, rows in grouped.items():
        task = task_by_id.get(item_id, {})
        budget = task.get("budget") if isinstance(task.get("budget"), dict) else {}
        planned_api = health_check.safe_float(budget.get("max_api_usd")) or 0.0
        planned_compute = health_check.safe_float(budget.get("max_compute_usd")) or 0.0
        planned_total = health_check.safe_float(budget.get("max_total_usd")) or round(planned_api + planned_compute, 4)
        amount_total = sum(health_check.safe_float(row.get("amount_usd")) or 0.0 for row in rows)
        actual_total = sum((health_check.safe_float(row.get("amount_usd")) or 0.0) for row in rows if row.get("actual_usage") is True)
        estimated_total = round(amount_total - actual_total, 4)
        api_total = sum(health_check.safe_float(row.get("api_usd")) or 0.0 for row in rows)
        compute_total = sum(health_check.safe_float(row.get("compute_usd")) or 0.0 for row in rows)
        data_total = sum(health_check.safe_float(row.get("data_usd")) or 0.0 for row in rows)
        network_rows = [row for row in rows if row.get("network_use") is True]
        external_rows = [row for row in rows if row.get("external_service") != "unavailable" or row.get("network_use") is True]
        explicit_approval = any(row.get("approval_required") is True for row in rows)
        task_requires_approval = bool(task.get("requires_human")) and (
            bool(task.get("allow_network")) or planned_total > 0 or amount_total > 0
        )
        approval_required = explicit_approval or task_requires_approval
        budget_ratio = round(amount_total / planned_total, 4) if planned_total else None
        summaries.append(
            {
                "item_id": item_id,
                "task_id": task.get("task_id", item_id if item_id.startswith("TASK-") else "unavailable"),
                "task_title": task.get("title", "unavailable"),
                "task_status": task.get("status", "unavailable"),
                "task_type": task.get("type", "unavailable"),
                "planned_api_usd": round(planned_api, 4),
                "planned_compute_usd": round(planned_compute, 4),
                "planned_total_usd": round(planned_total, 4),
                "actual_spend_usd": round(actual_total, 4),
                "estimated_spend_usd": round(estimated_total, 4),
                "amount_usd": round(amount_total, 4),
                "api_usd": round(api_total, 4),
                "compute_usd": round(compute_total, 4),
                "data_usd": round(data_total, 4),
                "budget_ratio": budget_ratio,
                "budget_state": budget_state(budget_ratio),
                "row_count": len(rows),
                "roles": sorted({cost_label(row, ("role",)) for row in rows}),
                "models": sorted({cost_label(row, ("model_or_tool", "provider")) for row in rows}),
                "usage_sources": sorted({cost_label(row, ("usage_source",)) for row in rows}),
                "network_use": bool(task.get("allow_network")) or bool(network_rows),
                "network_row_count": len(network_rows),
                "external_service_count": len(external_rows),
                "approval_required": approval_required,
                "approval_status": "required" if approval_required else "not indicated",
            }
        )
    return sorted(summaries, key=lambda item: (item["approval_required"] is False, -item["amount_usd"], item["item_id"]))[:RECENT_LIMIT]

def cost_ledger_detail_rows(ledger_path: Path, now: datetime) -> list[dict[str, Any]]:
    if not ledger_path.exists():
        return []
    rows: list[dict[str, Any]] = []
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    week_start = now - timedelta(days=now.weekday())
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    with ledger_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for index, row in enumerate(reader, start=1):
            parsed = {str(key): str(value) for key, value in row.items() if key is not None}
            date = health_check.row_date(parsed)
            amount = health_check.row_amount(parsed)
            input_usd = cost_number(parsed, ("input_usd",))
            output_usd = cost_number(parsed, ("output_usd",))
            api_usd = cost_number(parsed, ("api_usd", "estimated_api_usd"))
            if api_usd == 0.0:
                api_usd = input_usd + output_usd
            compute_usd = cost_number(parsed, ("compute_usd", "estimated_compute_usd"))
            data_usd = cost_number(parsed, ("data_usd", "external_data_usd", "paid_data_usd"))
            actual_usage = parsed.get("actual", "").strip().lower() == "true"
            network_use = cost_flag(parsed, ("network_use", "network_used", "allow_network", "external_network"))
            if network_use is None:
                usage_source = parsed.get("usage_source", "").lower()
                model_or_tool = parsed.get("model_or_tool", "").lower()
                network_use = any(token in usage_source or token in model_or_tool for token in ("api", "batch", "provider", "openai", "anthropic", "web"))
            approval_required = cost_flag(
                parsed,
                (
                    "approval_required",
                    "requires_approval",
                    "paid_service_requires_approval",
                    "human_approval_required",
                ),
            )
            input_tokens = health_check.row_int(parsed, health_check.INPUT_TOKEN_FIELDS)
            output_tokens = health_check.row_int(parsed, health_check.OUTPUT_TOKEN_FIELDS)
            total_tokens = health_check.row_int(parsed, health_check.TOTAL_TOKEN_FIELDS) or input_tokens + output_tokens
            rows.append(
                {
                    "row_number": index,
                    "date": parsed.get("date") or parsed.get("created_at") or parsed.get("timestamp") or parsed.get("period_start") or "unavailable",
                    "item_id": parsed.get("item_id", ""),
                    "role": parsed.get("role", ""),
                    "model_or_tool": parsed.get("model_or_tool", ""),
                    "provider": parsed.get("provider") or parsed.get("model_provider") or "",
                    "usage_source": parsed.get("usage_source", ""),
                    "external_service": parsed.get("external_service") or parsed.get("service") or parsed.get("provider") or "unavailable",
                    "amount_usd": round(amount, 4),
                    "api_usd": round(api_usd, 4),
                    "compute_usd": round(compute_usd, 4),
                    "data_usd": round(data_usd, 4),
                    "input_usd": round(input_usd, 4),
                    "output_usd": round(output_usd, 4),
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": total_tokens,
                    "status": parsed.get("status", ""),
                    "actual": parsed.get("actual", ""),
                    "actual_usage": actual_usage,
                    "network_use": bool(network_use),
                    "approval_required": bool(approval_required),
                    "notes": parsed.get("notes", ""),
                    "in_current_month": bool(date and date >= month_start),
                    "in_current_week": bool(date and date >= week_start),
                    "sort_date": date.isoformat() if date else "",
                }
            )
    return rows

def cost_snapshot(ops_dir: Path, now: datetime, task_rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    ledger_path = ops_dir / "cost_ledger.csv"
    try:
        cost = health_check.scan_cost_ledger(ledger_path, None, None, now)
        detail_rows = cost_ledger_detail_rows(ledger_path, now)
    except Exception as exc:
        warning = issue(
            "warning",
            "cost_ledger_unreadable",
            "cost ledger could not be parsed",
            ledger_path,
            str(exc),
        )
        return {
            "available": False,
            "status": "unavailable",
            "path": str(ledger_path),
            "exists": ledger_path.exists(),
            "month_spend_usd": 0.0,
            "week_spend_usd": 0.0,
            "monthly_budget_usd": None,
            "weekly_budget_usd": None,
            "monthly_usage_ratio": None,
            "weekly_usage_ratio": None,
            "budget_pressure": False,
            "summary": {},
            "recent_rows": [],
            "top_spend_rows": [],
            "task_costs": [],
            "role_costs": [],
            "model_provider_costs": [],
            "recovery_commands": [command_hint("Inspect cost summary", ["async-research", "cost", "summary", str(ops_dir)])],
            "warnings": [warning],
        }
    monthly_ratio = cost.get("monthly_usage_ratio")
    weekly_ratio = cost.get("weekly_usage_ratio")
    warnings: list[dict[str, Any]] = []
    if not cost.get("exists"):
        warnings.append(issue("warning", "cost_ledger_missing", "cost ledger is missing", ops_dir / "cost_ledger.csv"))
    for name, ratio in (("monthly", monthly_ratio), ("weekly", weekly_ratio)):
        if isinstance(ratio, (int, float)) and ratio >= 0.8:
            warnings.append(
                issue(
                    "warning",
                    f"{name}_budget_pressure",
                    f"{name} cost is at least 80% of configured budget",
                    ops_dir / "cost_ledger.csv",
                    {"usage_ratio": ratio},
                )
            )
    task_costs = cost_task_summaries(detail_rows, task_rows or [])
    role_costs = cost_dimension_summary(detail_rows, ("role",))
    model_provider_costs = cost_dimension_summary(detail_rows, ("provider", "model_or_tool"))
    return {
        "available": True,
        "status": "available",
        "path": cost.get("ledger_path"),
        "exists": cost.get("exists", False),
        "row_count": cost.get("row_count", 0),
        "month_spend_usd": cost.get("monthly_cost_usd", 0.0),
        "week_spend_usd": cost.get("weekly_cost_usd", 0.0),
        "monthly_budget_usd": cost.get("monthly_budget_usd"),
        "weekly_budget_usd": cost.get("weekly_budget_usd"),
        "monthly_usage_ratio": monthly_ratio,
        "weekly_usage_ratio": weekly_ratio,
        "monthly_budget_state": budget_state(monthly_ratio),
        "weekly_budget_state": budget_state(weekly_ratio),
        "input_tokens": cost.get("input_tokens", 0),
        "output_tokens": cost.get("output_tokens", 0),
        "total_tokens": cost.get("total_tokens", 0),
        "actual_usage_rows": cost.get("actual_usage_rows", 0),
        "budget_pressure": bool(warnings),
        "recent_rows": sorted(detail_rows, key=lambda row: (row["sort_date"], row["row_number"]), reverse=True)[:RECENT_LIMIT],
        "top_spend_rows": sorted(detail_rows, key=lambda row: row["amount_usd"], reverse=True)[:RECENT_LIMIT],
        "task_costs": task_costs,
        "role_costs": role_costs,
        "model_provider_costs": model_provider_costs,
        "summary": {
            "row_count": cost.get("row_count", 0),
            "month_spend_usd": cost.get("monthly_cost_usd", 0.0),
            "week_spend_usd": cost.get("weekly_cost_usd", 0.0),
            "monthly_budget_state": budget_state(monthly_ratio),
            "weekly_budget_state": budget_state(weekly_ratio),
            "total_tokens": cost.get("total_tokens", 0),
            "actual_usage_rows": cost.get("actual_usage_rows", 0),
            "task_cost_count": len(task_costs),
            "approval_required_count": len([row for row in task_costs if row["approval_required"]]),
            "network_use_count": len([row for row in detail_rows if row.get("network_use") is True]),
            "external_service_count": len([row for row in detail_rows if row.get("external_service") != "unavailable"]),
            "actual_spend_usd": round(sum(row["amount_usd"] for row in detail_rows if row.get("actual_usage") is True), 4),
            "estimated_spend_usd": round(sum(row["amount_usd"] for row in detail_rows if row.get("actual_usage") is not True), 4),
            "api_usd": round(sum(row["api_usd"] for row in detail_rows), 4),
            "compute_usd": round(sum(row["compute_usd"] for row in detail_rows), 4),
            "data_usd": round(sum(row["data_usd"] for row in detail_rows), 4),
        },
        "recovery_commands": [
            command_hint("Inspect cost summary", ["async-research", "cost", "summary", str(ops_dir)]),
            command_hint("Run health dry-run", ["async-research", "health", str(ops_dir), "--dry-run"]),
        ],
        "warnings": warnings,
    }
