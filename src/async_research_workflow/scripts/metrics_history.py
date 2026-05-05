#!/usr/bin/env python3
"""Maintain metrics baseline and append-only history for async research."""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import re
import sys
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from async_research_workflow.scripts.decision_log import read_decisions
from async_research_workflow.scripts.update_accepted_outputs_index import memory_decay_report


SUCCESS = 0
INVALID_REQUEST = 2
MALFORMED = 4

SCHEMA_VERSION = "1.0"
BASELINE_NAME = "metrics_baseline.json"
HISTORY_NAME = "metrics_history.jsonl"
AMOUNT_FIELDS = ("amount_usd", "cost_usd", "usd", "total_usd", "api_usd", "compute_usd")
HUMAN_MINUTE_FIELDS = ("human_minutes", "minutes", "human_time_minutes")
IDEA_ID_PATTERN = re.compile(r"IDEA-[0-9]{4}")
COMPLETED_STATUSES = {"accepted", "rejected", "synthesized"}
DEFAULT_ACCEPTED_OUTPUT_FRESHNESS_DAYS = 90

METRIC_KEYS = [
    "tasks_created",
    "tasks_accepted",
    "tasks_rejected",
    "ideas_generated",
    "ideas_promoted",
    "ideas_rejected",
    "human_minutes",
    "estimated_cost_usd",
    "panel_reviews",
    "revision_loops",
    "autonomous_completion_rate",
    "needs_human_rate",
    "false_accept_rate",
    "false_reject_rate",
    "cost_per_accepted_output",
    "reviewer_disagreement_rate",
    "stale_memory_reuse_count",
    "unaudited_source_block_count",
    "source_freshness_warning_count",
    "revision_limit_hit_count",
    "average_task_age_hours",
    "queue_overload_count",
    "readiness_gate_skip_count",
    "accepted_outputs_revalidated_count",
    "accepted_outputs_expired_count",
]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().replace(microsecond=0).isoformat().replace("+00:00", "Z")


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def safe_float(value: Any) -> Optional[float]:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


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


def read_json_object(path: Path) -> Optional[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def markdown_rows(path: Path) -> list[list[str]]:
    if not path.exists():
        return []
    rows: list[list[str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line.startswith("|") or "---" in line:
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if not cells or cells[0].lower() in {"id", "task", "item", "date"}:
            continue
        if any(cells):
            rows.append(cells)
    return rows


def markdown_table_dicts(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    header: Optional[list[str]] = None
    rows: list[dict[str, str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line.startswith("|") or "---" in line:
            continue
        cells = [cell.strip().replace("\\|", "|") for cell in line.strip("|").split("|")]
        if not cells:
            continue
        if header is None:
            header = [cell.lower().strip().replace(" ", "_") for cell in cells]
            continue
        if len(cells) != len(header):
            continue
        row = {key: value for key, value in zip(header, cells)}
        if any(value.strip() for value in row.values()):
            rows.append(row)
    return rows


def idea_ids_from_rows(rows: list[list[str]]) -> set[str]:
    ids: set[str] = set()
    for row in rows:
        for cell in row:
            match = IDEA_ID_PATTERN.search(cell)
            if match:
                ids.add(match.group(0))
                break
    return ids


def row_has_value(row: list[str], values: set[str]) -> bool:
    return any(cell.strip().lower() in values for cell in row)


def task_status_items(ops_dir: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for status_path in sorted((ops_dir / "tasks").glob("*/status.json")):
        payload = read_json_object(status_path)
        if payload is not None:
            items.append({"task_dir": status_path.parent, "status_path": status_path, "payload": payload})
    return items


def task_statuses(ops_dir: Path) -> list[dict[str, Any]]:
    return [item["payload"] for item in task_status_items(ops_dir)]


def discovery_metrics(ops_dir: Path) -> dict[str, int]:
    discovery_inbox_rows = markdown_rows(ops_dir / "discovery_inbox.md")
    rejected_rows = markdown_rows(ops_dir / "discovery" / "rejected_ideas.md")
    idea_jsons = [path for path in sorted((ops_dir / "discovery").glob("IDEA-*.json")) if read_json_object(path) is not None]

    generated_ids = set(path.stem for path in idea_jsons)
    generated_ids.update(idea_ids_from_rows(discovery_inbox_rows))
    generated_ids.update(idea_ids_from_rows(rejected_rows))

    promoted = 0
    rejected = 0
    for path in idea_jsons:
        payload = read_json_object(path) or {}
        status = payload.get("status")
        if status == "promote":
            promoted += 1
        if status == "reject":
            rejected += 1

    for row in discovery_inbox_rows:
        if row_has_value(row, {"promote", "promoted"}) or (row and row[-1].strip().lower() == "yes"):
            promoted += 1
        if row_has_value(row, {"reject", "rejected"}):
            rejected += 1

    rejected += len(rejected_rows)

    generated_count = len(generated_ids) if generated_ids else len(idea_jsons) + len(discovery_inbox_rows) + len(rejected_rows)
    return {
        "ideas_generated": generated_count,
        "ideas_promoted": promoted,
        "ideas_rejected": rejected,
    }


def amount_from_row(row: dict[str, str], fields: tuple[str, ...]) -> float:
    for field in fields:
        value = safe_float(row.get(field))
        if value is not None:
            return value
    return 0.0


def cost_metrics(ops_dir: Path) -> dict[str, float]:
    ledger_path = ops_dir / "cost_ledger.csv"
    if not ledger_path.exists():
        return {"estimated_cost_usd": 0.0, "ledger_human_minutes": 0.0}

    total_cost = 0.0
    total_minutes = 0.0
    with ledger_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            clean = {str(k): str(v) for k, v in row.items() if k is not None}
            total_cost += amount_from_row(clean, AMOUNT_FIELDS)
            total_minutes += amount_from_row(clean, HUMAN_MINUTE_FIELDS)
    return {
        "estimated_cost_usd": round(total_cost, 4),
        "ledger_human_minutes": round(total_minutes, 2),
    }


def review_panel_count(ops_dir: Path, statuses: list[dict[str, Any]]) -> int:
    aggregate_count = 0
    for aggregate_path in sorted((ops_dir / "tasks").glob("*/review_panel/aggregate.json")):
        aggregate = read_json_object(aggregate_path)
        if not aggregate:
            continue
        tier = aggregate.get("tier")
        if isinstance(tier, int) and not isinstance(tier, bool) and tier >= 2:
            aggregate_count += 1
    if aggregate_count:
        return aggregate_count

    count = 0
    for status in statuses:
        policy = status.get("review_policy")
        if isinstance(policy, dict):
            tier = policy.get("tier")
            if policy.get("panel_required") is True or (isinstance(tier, int) and not isinstance(tier, bool) and tier >= 2):
                count += 1
    return count


def revision_loop_count(statuses: list[dict[str, Any]]) -> int:
    total = 0
    for status in statuses:
        value = status.get("revision_count")
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            total += value
    return total


def revision_limit_hit_count(statuses: list[dict[str, Any]]) -> int:
    count = 0
    for status in statuses:
        revision_count = status.get("revision_count")
        max_revisions = status.get("max_revisions")
        if status.get("revision_limit_hit") is True:
            count += 1
            continue
        if (
            isinstance(revision_count, int)
            and not isinstance(revision_count, bool)
            and isinstance(max_revisions, int)
            and not isinstance(max_revisions, bool)
            and max_revisions > 0
            and revision_count >= max_revisions
        ):
            count += 1
    return count


def task_result(status: dict[str, Any]) -> dict[str, Any]:
    result = status.get("result")
    return result if isinstance(result, dict) else {}


def human_touched_task_ids(ops_dir: Path, statuses: list[dict[str, Any]]) -> set[str]:
    touched = {
        str(row.get("item_id"))
        for row in read_decisions(ops_dir / "decisions.md")
        if isinstance(row.get("item_id"), str) and str(row.get("item_id")).strip()
    }
    for status in statuses:
        task_id = str(status.get("id", ""))
        if not task_id:
            continue
        if status.get("requires_human") is True or status.get("status") == "needs_human":
            touched.add(task_id)
        if isinstance(status.get("human_gate_reason"), str) and status.get("human_gate_reason", "").strip():
            touched.add(task_id)
        if status.get("previous_status") == "needs_human":
            touched.add(task_id)
    return touched


def autonomous_completion_rate(ops_dir: Path, statuses: list[dict[str, Any]]) -> float:
    completed = [status for status in statuses if status.get("status") in COMPLETED_STATUSES]
    if not completed:
        return 0.0
    touched = human_touched_task_ids(ops_dir, statuses)
    autonomous = [status for status in completed if str(status.get("id", "")) not in touched]
    return round(len(autonomous) / len(completed), 4)


def needs_human_rate(statuses: list[dict[str, Any]]) -> float:
    if not statuses:
        return 0.0
    count = sum(1 for status in statuses if status.get("status") == "needs_human" or status.get("requires_human") is True)
    return round(count / len(statuses), 4)


def task_blocker_text(item: dict[str, Any]) -> str:
    payload = item["payload"]
    parts = [
        str(payload.get("status", "")),
        str(payload.get("last_transition_reason", "")),
        str(payload.get("human_gate_reason", "")),
        json.dumps(payload.get("result", {}), sort_keys=True),
    ]
    return " ".join(parts).lower()


def task_blocker_text_count(items: list[dict[str, Any]], needles: tuple[str, ...]) -> int:
    count = 0
    for item in items:
        payload = item["payload"]
        if payload.get("status") != "needs_human" and payload.get("requires_human") is not True:
            continue
        text = task_blocker_text(item)
        if any(needle in text for needle in needles):
            count += 1
    return count


def review_aggregates(ops_dir: Path) -> list[dict[str, Any]]:
    aggregates: list[dict[str, Any]] = []
    for aggregate_path in sorted((ops_dir / "tasks").glob("*/review_panel/aggregate.json")):
        aggregate = read_json_object(aggregate_path)
        if aggregate is not None:
            aggregates.append(aggregate)
    return aggregates


def has_review_disagreement(aggregate: dict[str, Any]) -> bool:
    disagreements = aggregate.get("disagreements")
    if isinstance(disagreements, list) and any(str(item).strip().lower() not in {"", "none"} for item in disagreements):
        return True
    decisions = []
    for review in aggregate.get("reviews", []):
        if isinstance(review, dict) and isinstance(review.get("decision"), str):
            decisions.append(review["decision"])
    return len(set(decisions)) > 1


def reviewer_disagreement_rate(aggregates: list[dict[str, Any]]) -> float:
    if not aggregates:
        return 0.0
    count = sum(1 for aggregate in aggregates if has_review_disagreement(aggregate))
    return round(count / len(aggregates), 4)


def failed_result_acceptance(task_dir: Path) -> bool:
    record = read_json_object(task_dir / "review_panel" / "result_acceptance.json")
    if not record:
        return False
    for gate in record.get("hard_gate_results", []):
        if isinstance(gate, dict) and gate.get("passed") is not True:
            return True
    return False


def false_accept_count(items: list[dict[str, Any]]) -> int:
    count = 0
    for item in items:
        status = item["payload"]
        if status.get("status") != "accepted":
            continue
        result = task_result(status)
        aggregate = read_json_object(item["task_dir"] / "review_panel" / "aggregate.json") or {}
        if failed_result_acceptance(item["task_dir"]):
            count += 1
        elif result.get("claim_strength_stale") is True or result.get("claim_strength_revalidation_required") is True:
            count += 1
        elif aggregate and aggregate.get("aggregate_decision") not in {"accepted", None}:
            count += 1
    return count


def false_reject_count(items: list[dict[str, Any]]) -> int:
    count = 0
    for item in items:
        status = item["payload"]
        if status.get("status") != "rejected":
            continue
        aggregate = read_json_object(item["task_dir"] / "review_panel" / "aggregate.json") or {}
        decisions = [
            review.get("decision")
            for review in aggregate.get("reviews", [])
            if isinstance(review, dict)
        ]
        if aggregate.get("aggregate_decision") == "accepted" or (decisions and all(decision in {"accept", "accept_with_caveats"} for decision in decisions)):
            count += 1
    return count


def accepted_outputs_expired_count(ops_dir: Path, now: datetime, freshness_days: int = DEFAULT_ACCEPTED_OUTPUT_FRESHNESS_DAYS) -> int:
    report = memory_decay_report(ops_dir, now=now)
    return int(report.get("stale_count", 0))


def accepted_outputs_due_count(ops_dir: Path, now: datetime) -> int:
    report = memory_decay_report(ops_dir, now=now)
    return int(report.get("due_count", 0))


def accepted_outputs_revalidated_count(statuses: list[dict[str, Any]]) -> int:
    count = 0
    for status in statuses:
        if status.get("status") != "accepted":
            continue
        result = task_result(status)
        if isinstance(result.get("revalidation_status"), str) and result["revalidation_status"] == "revalidated":
            count += 1
    return count


def average_task_age_hours(statuses: list[dict[str, Any]], now: datetime) -> float:
    ages: list[float] = []
    for status in statuses:
        created = parse_datetime(status.get("created_at"))
        if created is None:
            continue
        ages.append(max(0.0, (now - created).total_seconds() / 3600))
    if not ages:
        return 0.0
    return round(sum(ages) / len(ages), 2)


def load_health_report(ops_dir: Path) -> dict[str, Any]:
    return read_json_object(ops_dir / "health_report.json") or {}


def health_alert_count(health: dict[str, Any], checks: set[str]) -> int:
    alerts = health.get("alerts")
    if not isinstance(alerts, list):
        return 0
    return sum(1 for alert in alerts if isinstance(alert, dict) and str(alert.get("check")) in checks)


def cost_per_accepted_output(estimated_cost: float, accepted_count: int) -> float:
    if accepted_count <= 0:
        return 0.0
    return round(estimated_cost / accepted_count, 4)


def autonomy_metrics(
    ops_dir: Path,
    items: list[dict[str, Any]],
    statuses: list[dict[str, Any]],
    base_metrics: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    accepted_count = int(base_metrics["tasks_accepted"])
    rejected_count = int(base_metrics["tasks_rejected"])
    false_accepts = false_accept_count(items)
    false_rejects = false_reject_count(items)
    aggregates = review_aggregates(ops_dir)
    health = load_health_report(ops_dir)

    return {
        "autonomous_completion_rate": autonomous_completion_rate(ops_dir, statuses),
        "needs_human_rate": needs_human_rate(statuses),
        "false_accept_rate": round(false_accepts / accepted_count, 4) if accepted_count else 0.0,
        "false_reject_rate": round(false_rejects / rejected_count, 4) if rejected_count else 0.0,
        "cost_per_accepted_output": cost_per_accepted_output(float(base_metrics["estimated_cost_usd"]), accepted_count),
        "reviewer_disagreement_rate": reviewer_disagreement_rate(aggregates),
        "stale_memory_reuse_count": task_blocker_text_count(items, ("stale memory", "stale accepted", "accepted memory is stale")),
        "unaudited_source_block_count": task_blocker_text_count(items, ("unaudited source", "data_sources_not_experiment_ready")),
        "source_freshness_warning_count": health_alert_count(health, {"source_freshness_warnings"}),
        "revision_limit_hit_count": revision_limit_hit_count(statuses),
        "average_task_age_hours": average_task_age_hours(statuses, now),
        "queue_overload_count": health_alert_count(health, {"queue_depth", "discovery_inbox_overload"}),
        "readiness_gate_skip_count": health_alert_count(health, {"readiness_gate_skip", "readiness_gate_blocked"}),
        "accepted_outputs_revalidated_count": accepted_outputs_revalidated_count(statuses),
        "accepted_outputs_expired_count": accepted_outputs_expired_count(ops_dir, now),
    }


def health_cost_view(ops_dir: Path) -> dict[str, Any]:
    health = load_health_report(ops_dir)
    checks = health.get("checks") if isinstance(health.get("checks"), dict) else {}
    cost = checks.get("cost") if isinstance(checks.get("cost"), dict) else {}
    return {
        "estimated_cost_usd": cost.get("monthly_cost_usd", cost_metrics(ops_dir)["estimated_cost_usd"]),
        "monthly_budget_usd": cost.get("monthly_budget_usd"),
        "weekly_budget_usd": cost.get("weekly_budget_usd"),
        "monthly_usage_ratio": cost.get("monthly_usage_ratio"),
        "weekly_usage_ratio": cost.get("weekly_usage_ratio"),
        "actual_usage_rows": cost.get("actual_usage_rows"),
    }


def operational_view(ops_dir: Path, metrics: dict[str, Any]) -> dict[str, Any]:
    health = load_health_report(ops_dir)
    checks = health.get("checks") if isinstance(health.get("checks"), dict) else {}
    accepted_memory = checks.get("accepted_memory") if isinstance(checks.get("accepted_memory"), dict) else memory_decay_report(ops_dir, now=utc_now())
    return {
        "autonomy": {
            "current_estimated_autonomy_pct": round(float(metrics["autonomous_completion_rate"]) * 100, 2),
            "autonomous_completion_rate": metrics["autonomous_completion_rate"],
            "needs_human_rate": metrics["needs_human_rate"],
        },
        "budget": health_cost_view(ops_dir),
        "queue": {
            "queue_depth": checks.get("queue_depth"),
            "discovery_inbox_count": checks.get("discovery_inbox_count"),
            "queue_overload_count": metrics["queue_overload_count"],
            "readiness_gate_skip_count": metrics["readiness_gate_skip_count"],
        },
        "source_risk": {
            "unaudited_source_block_count": metrics["unaudited_source_block_count"],
            "source_freshness_warning_count": metrics.get("source_freshness_warning_count", 0),
            "source_governance": checks.get("source_governance"),
            "stale_memory_reuse_count": metrics["stale_memory_reuse_count"],
            "accepted_outputs_expired_count": metrics["accepted_outputs_expired_count"],
            "accepted_outputs_revalidated_count": metrics["accepted_outputs_revalidated_count"],
            "accepted_memory": accepted_memory,
        },
        "review_risk": {
            "reviewer_disagreement_rate": metrics["reviewer_disagreement_rate"],
            "revision_limit_hit_count": metrics["revision_limit_hit_count"],
            "false_accept_rate": metrics["false_accept_rate"],
            "false_reject_rate": metrics["false_reject_rate"],
        },
    }


def human_minutes(ops_dir: Path, explicit_minutes: Optional[float], minutes_per_decision: float) -> float:
    if explicit_minutes is not None:
        return round(explicit_minutes, 2)
    ledger_minutes = cost_metrics(ops_dir)["ledger_human_minutes"]
    if ledger_minutes > 0:
        return round(ledger_minutes, 2)
    decision_count = len(read_decisions(ops_dir / "decisions.md"))
    return round(decision_count * minutes_per_decision, 2)


def collect_metrics(
    ops_dir: Path,
    human_minutes_override: Optional[float],
    minutes_per_decision: float,
) -> dict[str, Any]:
    items = task_status_items(ops_dir)
    statuses = [item["payload"] for item in items]
    status_values = [str(status.get("status", "unknown")) for status in statuses]
    discovery = discovery_metrics(ops_dir)
    costs = cost_metrics(ops_dir)
    base = {
        "tasks_created": len(statuses),
        "tasks_accepted": sum(1 for status in status_values if status == "accepted"),
        "tasks_rejected": sum(1 for status in status_values if status == "rejected"),
        "ideas_generated": discovery["ideas_generated"],
        "ideas_promoted": discovery["ideas_promoted"],
        "ideas_rejected": discovery["ideas_rejected"],
        "human_minutes": human_minutes(ops_dir, human_minutes_override, minutes_per_decision),
        "estimated_cost_usd": costs["estimated_cost_usd"],
        "panel_reviews": review_panel_count(ops_dir, statuses),
        "revision_loops": revision_loop_count(statuses),
    }
    return {**base, **autonomy_metrics(ops_dir, items, statuses, base, utc_now())}


def snapshot(
    ops_dir: Path,
    period: str,
    label: str,
    human_minutes_override: Optional[float],
    minutes_per_decision: float,
) -> dict[str, Any]:
    generated_at = iso_now()
    metrics = collect_metrics(ops_dir, human_minutes_override, minutes_per_decision)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "period": period,
        "label": label,
        "ops_dir": str(ops_dir),
        "metrics": metrics,
        "operational_view": operational_view(ops_dir, metrics),
    }


def baseline_payload(snapshot_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "created_at": snapshot_payload["generated_at"],
        "baseline_label": snapshot_payload["label"],
        "metrics": snapshot_payload["metrics"],
        "operational_view": snapshot_payload.get("operational_view", {}),
    }


def baseline_path(ops_dir: Path) -> Path:
    return ops_dir / BASELINE_NAME


def history_path(ops_dir: Path) -> Path:
    return ops_dir / HISTORY_NAME


def ensure_baseline(ops_dir: Path, snapshot_payload: dict[str, Any], force: bool = False) -> bool:
    path = baseline_path(ops_dir)
    if path.exists() and not force:
        return False
    atomic_write_json(path, baseline_payload(snapshot_payload))
    return True


def read_history(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def run_init(args: argparse.Namespace) -> int:
    snap = snapshot(args.ops_dir, args.period, args.label, args.human_minutes, args.minutes_per_decision)
    created = ensure_baseline(args.ops_dir, snap, force=args.force)
    if not created and not args.force:
        print_json({"ok": True, "action": "baseline_exists", "baseline": str(baseline_path(args.ops_dir))})
        return SUCCESS
    print_json({"ok": True, "action": "baseline_initialized", "baseline": str(baseline_path(args.ops_dir)), "metrics": snap["metrics"]})
    return SUCCESS


def run_append(args: argparse.Namespace) -> int:
    snap = snapshot(args.ops_dir, args.period, args.label, args.human_minutes, args.minutes_per_decision)
    baseline_created = ensure_baseline(args.ops_dir, snap, force=False)
    append_jsonl(history_path(args.ops_dir), snap)
    weekly_digest = update_weekly_digest(args.ops_dir, snap) if args.update_weekly_digest else None
    print_json(
        {
            "ok": True,
            "action": "snapshot_appended",
            "baseline": str(baseline_path(args.ops_dir)),
            "baseline_created": baseline_created,
            "history": str(history_path(args.ops_dir)),
            "metrics": snap["metrics"],
            "operational_view": snap["operational_view"],
            "weekly_digest": str(weekly_digest) if weekly_digest is not None else None,
        }
    )
    return SUCCESS


def metric_value(payload: dict[str, Any], key: str) -> float:
    metrics = payload.get("metrics")
    if not isinstance(metrics, dict):
        return 0.0
    value = safe_float(metrics.get(key))
    return value if value is not None else 0.0


def month_matches(payload: dict[str, Any], month: Optional[str]) -> bool:
    if not month:
        return True
    generated_at = str(payload.get("generated_at", ""))
    return generated_at.startswith(month)


def trend(start: float, end: float) -> dict[str, Any]:
    delta = round(end - start, 4)
    percent_change = None if start == 0 else round(delta / start, 4)
    return {
        "start": start,
        "end": end,
        "delta": delta,
        "percent_change": percent_change,
    }


def build_summary(ops_dir: Path, month: Optional[str]) -> dict[str, Any]:
    baseline = read_json_object(baseline_path(ops_dir)) or {}
    rows = [row for row in read_history(history_path(ops_dir)) if month_matches(row, month)]
    first = rows[0] if rows else baseline
    last = rows[-1] if rows else baseline
    trends = {
        key: trend(metric_value(first, key), metric_value(last, key))
        for key in METRIC_KEYS
    }
    return {
        "ok": True,
        "ops_dir": str(ops_dir),
        "month": month or "all",
        "baseline": str(baseline_path(ops_dir)),
        "history": str(history_path(ops_dir)),
        "snapshot_count": len(rows),
        "trends": trends,
    }


def markdown_summary(summary: dict[str, Any]) -> str:
    lines = [
        f"# Metrics Trend Summary: {summary['month']}",
        "",
        f"Snapshots: {summary['snapshot_count']}",
        "",
        "| Metric | Start | End | Delta | Percent change |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for key in METRIC_KEYS:
        item = summary["trends"][key]
        pct = "n/a" if item["percent_change"] is None else f"{item['percent_change']:.2%}"
        lines.append(f"| {key} | {item['start']} | {item['end']} | {item['delta']} | {pct} |")
    return "\n".join(lines) + "\n"


def format_percent(value: Any) -> str:
    numeric = safe_float(value)
    if numeric is None:
        return "n/a"
    return f"{numeric:.0%}"


def format_usd(value: Any) -> str:
    numeric = safe_float(value)
    if numeric is None:
        return "n/a"
    return f"USD {numeric:.2f}"


def autonomy_digest_section(snapshot_payload: dict[str, Any]) -> str:
    metrics = snapshot_payload.get("metrics") if isinstance(snapshot_payload.get("metrics"), dict) else {}
    view = snapshot_payload.get("operational_view") if isinstance(snapshot_payload.get("operational_view"), dict) else {}
    queue = view.get("queue") if isinstance(view.get("queue"), dict) else {}
    budget = view.get("budget") if isinstance(view.get("budget"), dict) else {}
    source = view.get("source_risk") if isinstance(view.get("source_risk"), dict) else {}
    review = view.get("review_risk") if isinstance(view.get("review_risk"), dict) else {}
    current_autonomy = float(metrics.get("autonomous_completion_rate", 0.0)) * 100
    lines = [
        "## Autonomy Metrics",
        "",
        f"- Current estimated autonomy: {current_autonomy:.0f}%",
        f"- Autonomous completion rate: {format_percent(metrics.get('autonomous_completion_rate'))}",
        f"- Needs human rate: {format_percent(metrics.get('needs_human_rate'))}",
        f"- Cost per accepted output: {format_usd(metrics.get('cost_per_accepted_output'))}",
        f"- Budget view: monthly usage {format_percent(budget.get('monthly_usage_ratio'))}, weekly usage {format_percent(budget.get('weekly_usage_ratio'))}",
        f"- Queue view: queue depth {queue.get('queue_depth', 'n/a')}, discovery inbox {queue.get('discovery_inbox_count', 'n/a')}, overload count {queue.get('queue_overload_count', 0)}",
        (
            "- Source-risk view: "
            f"{source.get('unaudited_source_block_count', 0)} unaudited source blocks, "
            f"{source.get('source_freshness_warning_count', 0)} source freshness warnings, "
            f"{source.get('stale_memory_reuse_count', 0)} stale-memory reuse flags, "
            f"{source.get('accepted_outputs_expired_count', 0)} expired accepted outputs"
        ),
        (
            "- Review-risk view: "
            f"{format_percent(review.get('reviewer_disagreement_rate'))} reviewer disagreement, "
            f"{review.get('revision_limit_hit_count', 0)} revision-limit hits, "
            f"{format_percent(review.get('false_accept_rate'))} false-accept proxy, "
            f"{format_percent(review.get('false_reject_rate'))} false-reject proxy"
        ),
    ]
    accepted_memory = source.get("accepted_memory") if isinstance(source.get("accepted_memory"), dict) else {}
    if accepted_memory:
        lines.append(
            "- Accepted-memory view: "
            f"{accepted_memory.get('due_count', 0)} due for refresh, "
            f"{accepted_memory.get('stale_count', 0)} stale, "
            f"{accepted_memory.get('superseded_count', 0)} superseded"
        )
        due_or_stale = []
        for row in accepted_memory.get("stale_outputs", []) or []:
            if isinstance(row, dict):
                due_or_stale.append(f"{row.get('task_id')} stale since {row.get('next_recheck_date')}")
        for row in accepted_memory.get("due_outputs", []) or []:
            if isinstance(row, dict):
                due_or_stale.append(f"{row.get('task_id')} due {row.get('next_recheck_date')}")
        if due_or_stale:
            lines.append("- Evidence due for refresh: " + "; ".join(due_or_stale[:5]))
    return "\n".join(lines) + "\n"


def update_weekly_digest(ops_dir: Path, snapshot_payload: dict[str, Any]) -> Path:
    path = ops_dir / "weekly_digest.md"
    section = autonomy_digest_section(snapshot_payload)
    if path.exists():
        text = path.read_text(encoding="utf-8")
    else:
        text = "# Weekly Digest\n"
    pattern = re.compile(r"\n?## Autonomy Metrics\n.*?(?=\n## |\Z)", re.DOTALL)
    stripped = pattern.sub("", text).rstrip()
    if "\n## Cost Summary" in stripped:
        updated = stripped.replace("\n## Cost Summary", "\n\n" + section.rstrip() + "\n\n## Cost Summary", 1)
    else:
        updated = stripped + "\n\n" + section.rstrip()
    atomic_write_text(path, updated.rstrip() + "\n")
    return path


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def run_summarize(args: argparse.Namespace) -> int:
    summary = build_summary(args.ops_dir, args.month)
    if args.output:
        atomic_write_text(args.output, markdown_summary(summary))
        summary["output"] = str(args.output)
    print_json(summary)
    return SUCCESS


def add_snapshot_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("ops_dir", type=Path)
    parser.add_argument("--period", default="weekly")
    parser.add_argument("--label", default="manual")
    parser.add_argument("--human-minutes", type=float)
    parser.add_argument("--minutes-per-decision", type=float, default=5.0)


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Maintain metrics_baseline.json and metrics_history.jsonl.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="Create or refresh metrics_baseline.json.")
    add_snapshot_args(init)
    init.add_argument("--force", action="store_true")

    append = subparsers.add_parser("append-snapshot", help="Append one metrics snapshot to metrics_history.jsonl.")
    add_snapshot_args(append)
    append.add_argument("--update-weekly-digest", action="store_true", help="Refresh the weekly digest Autonomy Metrics section.")

    summarize = subparsers.add_parser("summarize", help="Summarize metric trends from history.")
    summarize.add_argument("ops_dir", type=Path)
    summarize.add_argument("--month")
    summarize.add_argument("--output", type=Path)

    return parser.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    if args.command == "init":
        return run_init(args)
    if args.command == "append-snapshot":
        return run_append(args)
    if args.command == "summarize":
        return run_summarize(args)
    print_json({"ok": False, "reason": "unknown_command", "command": args.command})
    return INVALID_REQUEST


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
