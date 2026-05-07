#!/usr/bin/env python3
"""Build and validate a lightweight human review surface.

The surface is markdown-first: daily_status.md gives the operator a compact
current-state readout, human_review_queue.md lists only actionable human
decisions, and weekly_digest.md gets a short supervision summary.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from typing import Any, Iterable, Optional

from async_research_workflow.idea_catalog import catalog_surface_summary
from async_research_workflow.scripts.cost_tracking import cost_window, ledger_path
from async_research_workflow.scripts.data_source_audit import source_governance_report
from async_research_workflow.scripts.decision_log import HEADER as DECISION_HEADER
from async_research_workflow.scripts.decision_log import (
    has_decision,
    markdown_escape,
    read_decisions,
    split_markdown_row,
)
from async_research_workflow.scripts.health_check import (
    DEFAULT_STATUS_SCHEMA,
    load_status_schema,
    load_task_statuses,
    markdown_table_row_count,
    parse_datetime,
    status_counts,
)


SUCCESS = 0
VALIDATION_FAILED = 2
MALFORMED = 4
SCHEMA_VERSION = "1.0"
QUEUE_NAME = "human_review_queue.md"
DAILY_NAME = "daily_status.md"
WEEKLY_NAME = "weekly_digest.md"

HUMAN_QUEUE_HEADER = [
    "decision_id",
    "task_id",
    "decision_needed",
    "reason_for_escalation",
    "available_options",
    "recommended_action",
    "consequence_of_ignoring",
    "urgency",
    "owner",
    "required_update_path_after_decision",
]

DAILY_REQUIRED_HEADINGS = [
    "What Ran",
    "What Changed",
    "Accepted",
    "Rejected",
    "Needs Human Decision",
    "Budget Used",
    "Risky Or Stale Sources",
    "Current Queue State",
    "Next Scheduled Tasks",
]

ACTIVE_STATUSES = {
    "inbox",
    "ready_for_planning",
    "ready_for_worker",
    "in_progress",
    "awaiting_review",
    "single_review",
    "panel_review",
    "needs_revision",
    "needs_human",
}
VALID_HUMAN_RESOLUTION_DECISIONS = {
    "approve",
    "resume",
    "pause",
    "reject",
    "approve_public",
    "approve_high_stakes",
    "approve_budget",
    "approve_data_use",
    "override",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now(now: Optional[datetime] = None) -> str:
    current = now or utc_now()
    return current.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_now(value: Optional[str]) -> datetime:
    if not value:
        return utc_now()
    parsed = parse_datetime(value)
    if parsed is None:
        raise ValueError(f"invalid --now value: {value}")
    return parsed


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def read_json_object(path: Path) -> Optional[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def safe_float(value: Any) -> Optional[float]:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def format_usd(value: Any) -> str:
    numeric = safe_float(value)
    if numeric is None:
        return "n/a"
    return f"USD {numeric:.2f}"


def format_percent(value: Any) -> str:
    numeric = safe_float(value)
    if numeric is None:
        return "n/a"
    return f"{numeric:.0%}"


def normalize_text(value: Any, default: str = "none") -> str:
    text = str(value if value is not None else "").replace("\n", " ").strip()
    text = re.sub(r"\s+", " ", text)
    return text or default


def task_id_for(item: dict[str, Any]) -> str:
    payload = item["payload"]
    return str(payload.get("id") or item["task_dir"].name)


def task_link(ops_dir: Path, item: dict[str, Any]) -> str:
    task_md = item["task_dir"] / "task.md"
    target = task_md if task_md.exists() else item["task_dir"]
    try:
        return target.relative_to(ops_dir).as_posix()
    except ValueError:
        return target.as_posix()


def result_object(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload.get("result")
    return result if isinstance(result, dict) else {}


def task_sort_key(item: dict[str, Any]) -> tuple[int, str]:
    payload = item["payload"]
    priority = payload.get("priority")
    if not isinstance(priority, int) or isinstance(priority, bool):
        priority = 5
    return priority, task_id_for(item)


def load_items(ops_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    schema = load_status_schema(DEFAULT_STATUS_SCHEMA)
    return load_task_statuses(ops_dir / "tasks", schema)


def latest_metrics_snapshot(ops_dir: Path) -> Optional[dict[str, Any]]:
    path = ops_dir / "metrics_history.jsonl"
    if not path.exists():
        return None
    latest: Optional[dict[str, Any]] = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            latest = payload
    return latest


def changed_recently(items: list[dict[str, Any]], now: datetime, hours: float = 24.0) -> list[dict[str, Any]]:
    cutoff = now - timedelta(hours=hours)
    changed: list[dict[str, Any]] = []
    for item in items:
        parsed = parse_datetime(item["payload"].get("updated_at"))
        if parsed is not None and parsed >= cutoff:
            changed.append(item)
    return sorted(changed, key=task_sort_key)


def accepted_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted([item for item in items if item["payload"].get("status") == "accepted"], key=task_sort_key)


def rejected_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted([item for item in items if item["payload"].get("status") == "rejected"], key=task_sort_key)


def active_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted([item for item in items if item["payload"].get("status") in ACTIVE_STATUSES], key=task_sort_key)


def human_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for item in items:
        payload = item["payload"]
        if payload.get("status") == "needs_human" or payload.get("requires_human") is True:
            result.append(item)
    return sorted(result, key=task_sort_key)


def severity_for(item: dict[str, Any]) -> str:
    gate = item["payload"].get("human_gate")
    if isinstance(gate, dict) and isinstance(gate.get("severity"), str):
        return gate["severity"]
    priority = item["payload"].get("priority")
    if priority == 1:
        return "high"
    if priority in {2, 3}:
        return "medium"
    return "low"


def urgency_for(item: dict[str, Any]) -> str:
    severity = severity_for(item)
    if severity == "critical":
        return "critical: inspect today before any scheduled worker"
    if severity == "high":
        return "high: inspect before next autonomous loop"
    if severity == "medium":
        return "medium: inspect during daily review"
    return "low: inspect during weekly review"


def human_gate(item: dict[str, Any]) -> dict[str, Any]:
    gate = item["payload"].get("human_gate")
    return gate if isinstance(gate, dict) else {}


def decision_id(item: dict[str, Any]) -> str:
    gate = human_gate(item)
    trigger = normalize_text(gate.get("trigger") or item["payload"].get("last_transition_reason"), "manual_review")
    trigger = re.sub(r"[^a-zA-Z0-9]+", "-", trigger).strip("-").lower() or "manual-review"
    return f"DEC-{task_id_for(item)}-{trigger}"


def available_options(item: dict[str, Any]) -> list[str]:
    gate = human_gate(item)
    raw = gate.get("available_decisions")
    if isinstance(raw, list):
        options = [str(value).strip() for value in raw if str(value).strip()]
        if options:
            return options
    return ["approve", "pause", "reject", "resume"]


def decision_needed(item: dict[str, Any]) -> str:
    gate = human_gate(item)
    return normalize_text(gate.get("required_human_decision"), "Resolve whether this task should resume, pause, or be rejected.")


def escalation_reason(item: dict[str, Any]) -> str:
    payload = item["payload"]
    gate = human_gate(item)
    return normalize_text(gate.get("reason") or payload.get("human_gate_reason") or payload.get("last_transition_reason"), "human review required")


def recommended_action(item: dict[str, Any], ops_dir: Path) -> str:
    gate = human_gate(item)
    options = ", ".join(available_options(item))
    task_path = item["task_dir"].as_posix()
    command = (
        "choose one option, then run "
        f"`async-research decision resolve-task {ops_dir.as_posix()} {task_path} "
        "--decision <option> --reason <reason> --approver <name>`"
    )
    safe_action = normalize_text(gate.get("default_safe_action"), "")
    if safe_action and safe_action != "none":
        return f"{command}; default safe action until then: {safe_action}; options: {options}"
    return f"{command}; options: {options}"


def consequence_of_ignoring(item: dict[str, Any]) -> str:
    gate = human_gate(item)
    retry = normalize_text(gate.get("retry_behavior"), "")
    if retry and retry != "none":
        return f"expensive workers remain blocked; {retry}"
    return "readiness gate keeps blocking expensive workers and the task remains unresolved"


def owner_for(item: dict[str, Any]) -> str:
    gate = human_gate(item)
    for key in ("owner", "assigned_owner", "approver"):
        value = gate.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    value = item["payload"].get("owner")
    return str(value).strip() if isinstance(value, str) and value.strip() else "human_operator"


def update_path_for(ops_dir: Path, item: dict[str, Any]) -> str:
    status_path = item["task_dir"] / "status.json"
    try:
        status_relative = status_path.relative_to(ops_dir).as_posix()
    except ValueError:
        status_relative = status_path.as_posix()
    return f"decisions.md plus {status_relative} via async-research decision resolve-task"


def review_queue_rows(ops_dir: Path, items: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in human_items(items):
        rows.append(
            {
                "decision_id": decision_id(item),
                "task_id": task_id_for(item),
                "decision_needed": decision_needed(item),
                "reason_for_escalation": escalation_reason(item),
                "available_options": ", ".join(available_options(item)),
                "recommended_action": recommended_action(item, ops_dir),
                "consequence_of_ignoring": consequence_of_ignoring(item),
                "urgency": urgency_for(item),
                "owner": owner_for(item),
                "required_update_path_after_decision": update_path_for(ops_dir, item),
            }
        )
    return rows


def estimate_review_minutes(open_human_count: int, active_count: int, alert_count: int) -> float:
    # Three minutes for the daily scan, two per decision, and a small premium for
    # active queue/alert context. This keeps the "under ten minutes" claim explicit.
    return round(3.0 + open_human_count * 2.0 + min(active_count, 8) * 0.25 + min(alert_count, 6) * 0.5, 2)


def markdown_table(header: list[str], rows: list[dict[str, Any]]) -> list[str]:
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(markdown_escape(row.get(column, "")) for column in header) + " |")
    return lines


def format_count_map(counts: dict[str, Any], keys: Iterable[str] | None = None) -> str:
    selected_keys = list(keys) if keys is not None else sorted(counts)
    pairs = [
        f"{key}: {counts.get(key, 0)}"
        for key in selected_keys
        if counts.get(key, 0) or keys is not None
    ]
    return ", ".join(pairs) if pairs else "none"


def task_summary_row(ops_dir: Path, item: dict[str, Any]) -> dict[str, str]:
    payload = item["payload"]
    result = result_object(payload)
    return {
        "task": task_id_for(item),
        "status": normalize_text(payload.get("status")),
        "priority": normalize_text(payload.get("priority")),
        "type": normalize_text(payload.get("type")),
        "title": normalize_text(payload.get("title")),
        "updated": normalize_text(payload.get("updated_at")),
        "link": task_link(ops_dir, item),
        "finding_or_reason": normalize_text(result.get("key_finding") or payload.get("last_transition_reason")),
    }


def read_health_report(ops_dir: Path) -> dict[str, Any]:
    return read_json_object(ops_dir / "health_report.json") or {}


def surface_model(ops_dir: Path, now: datetime) -> dict[str, Any]:
    items, malformed = load_items(ops_dir)
    statuses = [item["payload"] for item in items]
    counts = status_counts(items)
    open_human = human_items(items)
    active = active_items(items)
    health = read_health_report(ops_dir)
    alerts = health.get("alerts") if isinstance(health.get("alerts"), list) else []
    cost = cost_window(ledger_path(ops_dir), now, None, None)
    source = source_governance_report(ops_dir, now=now)
    metrics = latest_metrics_snapshot(ops_dir)
    queue_depth = markdown_table_row_count(ops_dir / "queue.md")
    discovery_depth = markdown_table_row_count(ops_dir / "discovery_inbox.md")
    catalog = catalog_surface_summary(ops_dir)
    review_minutes = estimate_review_minutes(len(open_human), len(active), len(alerts) + len(malformed))
    return {
        "ops_dir": ops_dir,
        "generated_at": iso_now(now),
        "items": items,
        "statuses": statuses,
        "malformed": malformed,
        "counts": counts,
        "open_human": open_human,
        "active": active,
        "accepted": accepted_items(items),
        "rejected": rejected_items(items),
        "changed": changed_recently(items, now),
        "health": health,
        "alerts": alerts,
        "cost": cost,
        "source": source,
        "metrics": metrics,
        "queue_depth": queue_depth,
        "discovery_depth": discovery_depth,
        "catalog": catalog,
        "review_minutes": review_minutes,
        "review_queue_rows": review_queue_rows(ops_dir, items),
    }


def human_review_queue_markdown(model: dict[str, Any]) -> str:
    rows = model["review_queue_rows"]
    lines = [
        "# Human Review Queue",
        "",
        f"Generated: {model['generated_at']}",
        f"Schema version: {SCHEMA_VERSION}",
        f"Open human decisions: {len(rows)}",
        f"Estimated review time: {model['review_minutes']} minutes",
        "",
    ]
    if not rows:
        lines.append("No open human decisions.")
        lines.append("")
    lines.extend(markdown_table(HUMAN_QUEUE_HEADER, rows))
    return "\n".join(lines).rstrip() + "\n"


def source_risk_lines(source: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    if source.get("error_count", 0):
        lines.append(f"- Source audit errors: {source.get('error_count')}")
    stale = source.get("stale_sources") if isinstance(source.get("stale_sources"), list) else []
    if stale:
        lines.append(f"- Stale sources: {len(stale)}")
        for item in stale[:5]:
            lines.append(
                f"  - {item.get('source_id')}: last reviewed {item.get('last_reviewed')}, "
                f"age {item.get('age_days')} days, window {item.get('freshness_window_days')} days"
            )
    if not lines:
        lines.append("- No risky or stale sources reported.")
    return lines


def catalog_daily_lines(catalog: dict[str, Any]) -> list[str]:
    status_counts_text = format_count_map(
        catalog["status_counts"],
        ["candidate", "promote", "park", "reject", "promoted", "needs_human"],
    )
    derived_counts_text = format_count_map(
        catalog["derived_label_counts"],
        ["raw", "scored", "blocked"],
    )
    lines = [
        f"- Catalog ideas: {catalog['candidate_count']}",
        f"- Stored statuses: {status_counts_text}",
        f"- Derived pipeline: {derived_counts_text}",
        f"- Parked / rejected: {catalog['parked_count']} / {catalog['rejected_count']}",
        f"- Top recommended promotions: {len(catalog['top_recommended_promotions'])}",
        f"- Data or evidence gap issues: {len(catalog['data_or_evidence_gap_issues'])}",
        f"- Stale projection warnings: {len(catalog['stale_projection_warnings'])}",
    ]
    if catalog["failure_count"]:
        lines.append(f"- Catalog validation failures: {catalog['failure_count']}")
    if catalog["top_recommended_promotions"]:
        lines.append("- Recommended promotions:")
        for item in catalog["top_recommended_promotions"][:3]:
            score = item.get("weighted_score")
            score_text = "n/a" if score is None else str(score)
            lines.append(
                f"  - {item.get('idea_id')}: {normalize_text(item.get('title'))} "
                f"({score_text}, next {normalize_text(item.get('recommended_next_task'))})"
            )
    if catalog["blocked_ideas"]:
        lines.append("- Blocked ideas:")
        for item in catalog["blocked_ideas"][:3]:
            blockers = item.get("blockers") if isinstance(item.get("blockers"), list) else []
            gap_reasons = [
                str(gap.get("reason"))
                for gap in item.get("data_or_evidence_gaps", [])
                if isinstance(gap, dict) and gap.get("reason")
            ]
            reason_text = ", ".join(blockers + gap_reasons) or "catalog validation gap"
            lines.append(f"  - {item.get('idea_id')}: {normalize_text(item.get('title'))} ({reason_text})")
    return lines


def daily_status_markdown(model: dict[str, Any]) -> str:
    ops_dir: Path = model["ops_dir"]
    counts = model["counts"]
    cost = model["cost"]
    health = model["health"]
    metrics = model["metrics"] if isinstance(model["metrics"], dict) else {}
    latest_metrics_time = metrics.get("generated_at", "none") if isinstance(metrics, dict) else "none"
    health_generated = health.get("generated_at", "none") if isinstance(health, dict) else "none"
    lines = [
        "# Daily Status",
        "",
        f"Generated: {model['generated_at']}",
        "Review target: under 10 minutes.",
        f"Estimated review time: {model['review_minutes']} minutes.",
        "",
        "## What Ran",
        "",
        f"- Latest health report: {health_generated}",
        f"- Latest metrics snapshot: {latest_metrics_time}",
        f"- Human review surface generated at: {model['generated_at']}",
        "",
        "## What Changed",
        "",
    ]
    changed_rows = [task_summary_row(ops_dir, item) for item in model["changed"][:8]]
    if changed_rows:
        lines.extend(markdown_table(["task", "status", "updated", "finding_or_reason"], changed_rows))
    else:
        lines.append("- No task status changed in the last 24 hours.")

    lines.extend(["", "## Accepted", ""])
    accepted_rows = [task_summary_row(ops_dir, item) for item in model["accepted"]]
    lines.append(f"Accepted: {counts.get('accepted', 0)}")
    if accepted_rows:
        lines.extend(markdown_table(["task", "title", "updated", "finding_or_reason"], accepted_rows))
    else:
        lines.append("- None.")

    lines.extend(["", "## Rejected", ""])
    rejected_rows = [task_summary_row(ops_dir, item) for item in model["rejected"]]
    lines.append(f"Rejected: {counts.get('rejected', 0)}")
    if rejected_rows:
        lines.extend(markdown_table(["task", "title", "updated", "finding_or_reason"], rejected_rows))
    else:
        lines.append("- None.")

    lines.extend(["", "## Needs Human Decision", ""])
    human_rows = [
        {
            "task": row["task_id"],
            "decision_needed": row["decision_needed"],
            "urgency": row["urgency"],
            "recommended_action": row["recommended_action"],
        }
        for row in model["review_queue_rows"]
    ]
    lines.append(f"Open human decisions: {len(human_rows)}")
    if human_rows:
        lines.extend(markdown_table(["task", "decision_needed", "urgency", "recommended_action"], human_rows))
    else:
        lines.append("- None. See `human_review_queue.md` for the empty queue.")

    lines.extend(
        [
            "",
            "## Budget Used",
            "",
            f"- Monthly spend: {format_usd(cost.get('monthly_cost_usd'))} / {format_usd(cost.get('monthly_budget_usd'))} ({format_percent(cost.get('monthly_usage_ratio'))})",
            f"- Weekly spend: {format_usd(cost.get('weekly_cost_usd'))} / {format_usd(cost.get('weekly_budget_usd'))} ({format_percent(cost.get('weekly_usage_ratio'))})",
            f"- Cost ledger rows: {cost.get('row_count', 0)}",
            f"- Actual usage rows: {cost.get('actual_usage_rows', 0)}",
            "",
            "## Risky Or Stale Sources",
            "",
        ]
    )
    lines.extend(source_risk_lines(model["source"]))

    lines.extend(["", "## Current Queue State", ""])
    active_count = len(model["active"])
    lines.extend(
        [
            f"- Task count: {sum(counts.values())}",
            f"- Active tasks: {active_count}",
            f"- Needs human: {counts.get('needs_human', 0)}",
            f"- Queue rows: {model['queue_depth']}",
            f"- Discovery inbox rows: {model['discovery_depth']}",
            f"- Health alerts: {len(model['alerts'])}",
            "",
        ]
    )
    if counts:
        count_rows = [{"status": key, "count": value} for key, value in sorted(counts.items())]
        lines.extend(markdown_table(["status", "count"], count_rows))
    else:
        lines.append("- No task statuses found.")

    lines.extend(["", "## Idea Catalog", ""])
    lines.extend(catalog_daily_lines(model["catalog"]))

    lines.extend(["", "## Next Scheduled Tasks", ""])
    next_rows = [task_summary_row(ops_dir, item) for item in model["active"][:8] if item["payload"].get("status") != "needs_human"]
    if next_rows:
        lines.extend(markdown_table(["task", "priority", "status", "type", "title", "link"], next_rows))
    elif human_rows:
        lines.append("- Resolve `needs_human` items before starting more scheduled workers.")
    else:
        lines.append("- No active scheduled tasks.")
    return "\n".join(lines).rstrip() + "\n"


def weekly_surface_section(model: dict[str, Any]) -> str:
    rows = model["review_queue_rows"]
    highest = "none"
    if rows:
        highest = rows[0]["urgency"]
    next_action = "No human action required."
    if rows:
        first = rows[0]
        next_action = f"{first['task_id']}: {first['decision_needed']}"
    lines = [
        "## Human Review Surface",
        "",
        f"- Generated: {model['generated_at']}",
        f"- Open human decisions: {len(rows)}",
        f"- Estimated review time: {model['review_minutes']} minutes",
        f"- Highest urgency: {highest}",
        f"- Next human action: {next_action}",
        f"- Queue file: `{QUEUE_NAME}`",
    ]
    return "\n".join(lines) + "\n"


def weekly_catalog_section(model: dict[str, Any]) -> str:
    catalog = model["catalog"]
    validation_state = "ok" if catalog["ok"] else f"{catalog['failure_count']} validation failure(s)"
    status_counts_text = format_count_map(
        catalog["status_counts"],
        ["candidate", "promote", "park", "reject", "promoted", "needs_human"],
    )
    derived_counts_text = format_count_map(
        catalog["derived_label_counts"],
        ["raw", "scored", "blocked"],
    )
    lines = [
        "## Idea Catalog Surface",
        "",
        f"- Catalog validation: {validation_state}",
        f"- Catalog ideas: {catalog['candidate_count']}",
        f"- Stored statuses: {status_counts_text}",
        f"- Derived pipeline: {derived_counts_text}",
        f"- Parked / rejected: {catalog['parked_count']} / {catalog['rejected_count']}",
        f"- Data or evidence gap issues: {len(catalog['data_or_evidence_gap_issues'])}",
        f"- Stale projection warnings: {len(catalog['stale_projection_warnings'])}",
    ]
    if catalog["top_recommended_promotions"]:
        lines.append("- Top recommended promotions:")
        for item in catalog["top_recommended_promotions"]:
            score = item.get("weighted_score")
            score_text = "n/a" if score is None else str(score)
            lines.append(
                f"  - {item.get('idea_id')}: {normalize_text(item.get('title'))} "
                f"({score_text}, next {normalize_text(item.get('recommended_next_task'))})"
            )
    else:
        lines.append("- Top recommended promotions: none")
    if catalog["blocked_ideas"]:
        lines.append("- Blocked ideas:")
        for item in catalog["blocked_ideas"][:5]:
            blockers = item.get("blockers") if isinstance(item.get("blockers"), list) else []
            gap_reasons = [
                str(gap.get("reason"))
                for gap in item.get("data_or_evidence_gaps", [])
                if isinstance(gap, dict) and gap.get("reason")
            ]
            reason_text = ", ".join(blockers + gap_reasons) or "catalog validation gap"
            lines.append(f"  - {item.get('idea_id')}: {normalize_text(item.get('title'))} ({reason_text})")
    else:
        lines.append("- Blocked ideas: none")
    if catalog["failure_count"]:
        lines.append(f"- Catalog validation failures: {catalog['failure_count']}")
    return "\n".join(lines) + "\n"


def update_weekly_digest(ops_dir: Path, model: dict[str, Any]) -> Path:
    path = ops_dir / WEEKLY_NAME
    text = path.read_text(encoding="utf-8") if path.exists() else "# Weekly Digest\n"
    section = weekly_surface_section(model).rstrip() + "\n\n" + weekly_catalog_section(model).rstrip()
    pattern = re.compile(r"\n?## (?:Human Review Surface|Idea Catalog Surface)\n.*?(?=\n## |\Z)", re.DOTALL)
    stripped = pattern.sub("", text).rstrip()
    updated = stripped + "\n\n" + section.rstrip() + "\n"
    atomic_write_text(path, updated)
    return path


def parse_queue_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    rows: list[dict[str, str]] = []
    header: Optional[list[str]] = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line.startswith("|") or "---" in line:
            continue
        cells = split_markdown_row(line)
        normalized = [cell.lower().strip().replace(" ", "_") for cell in cells]
        if normalized == HUMAN_QUEUE_HEADER:
            header = normalized
            continue
        if header is not None and len(cells) == len(header):
            row = {key: value.replace("\\|", "|").strip() for key, value in zip(header, cells)}
            if any(value.strip() for value in row.values()):
                rows.append(row)
    return rows


def task_ids(items: list[dict[str, Any]]) -> set[str]:
    return {task_id_for(item) for item in items}


def resolved_human_decision_errors(ops_dir: Path, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    decisions = ops_dir / "decisions.md"
    for item in items:
        payload = item["payload"]
        task_id = task_id_for(item)
        if payload.get("previous_status") != "needs_human":
            continue
        status = payload.get("status")
        if status not in {"ready_for_worker", "paused", "rejected"}:
            continue
        if not has_decision(decisions, task_id, VALID_HUMAN_RESOLUTION_DECISIONS):
            errors.append(
                {
                    "task_id": task_id,
                    "status": status,
                    "reason": "resolved_needs_human_without_decision_row",
                    "decisions": str(decisions),
                }
            )
    return errors


def decision_log_errors(ops_dir: Path) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    path = ops_dir / "decisions.md"
    if not path.exists():
        return [{"path": str(path), "reason": "decision_log_missing"}]
    for index, row in enumerate(read_decisions(path), start=1):
        for field in DECISION_HEADER:
            if not str(row.get(field, "")).strip():
                errors.append({"path": str(path), "row": index, "field": field, "reason": "decision_field_missing"})
    return errors


def validate_surface(ops_dir: Path, now: datetime, max_review_minutes: float) -> tuple[dict[str, Any], int]:
    model = surface_model(ops_dir, now)
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    daily_path = ops_dir / DAILY_NAME
    queue_path = ops_dir / QUEUE_NAME
    weekly_path = ops_dir / WEEKLY_NAME

    if not daily_path.exists():
        errors.append({"path": str(daily_path), "reason": "daily_status_missing"})
        daily_text = ""
    else:
        daily_text = daily_path.read_text(encoding="utf-8")
    if not queue_path.exists():
        errors.append({"path": str(queue_path), "reason": "human_review_queue_missing"})
        queue_text = ""
    else:
        queue_text = queue_path.read_text(encoding="utf-8")
    if not weekly_path.exists():
        warnings.append({"path": str(weekly_path), "reason": "weekly_digest_missing"})

    queue_rows = parse_queue_rows(queue_path)
    open_ids = task_ids(model["open_human"])
    row_ids = {row.get("task_id", "") for row in queue_rows if row.get("task_id")}
    missing = sorted(open_ids - row_ids)
    stale = sorted(row_ids - open_ids)
    for task_id in missing:
        errors.append({"task_id": task_id, "reason": "needs_human_missing_from_review_queue"})
    for task_id in stale:
        errors.append({"task_id": task_id, "reason": "stale_queue_item_not_needs_human"})

    for row in queue_rows:
        for field in HUMAN_QUEUE_HEADER:
            value = str(row.get(field, "")).strip()
            if not value or value.lower() == "none":
                errors.append({"task_id": row.get("task_id"), "field": field, "reason": "queue_field_missing"})

    for item in model["open_human"]:
        if escalation_reason(item).lower() in {"needs human", "human required", "none"}:
            errors.append({"task_id": task_id_for(item), "reason": "vague_human_reason"})

    for heading in DAILY_REQUIRED_HEADINGS:
        if f"## {heading}" not in daily_text:
            errors.append({"path": str(daily_path), "heading": heading, "reason": "daily_required_heading_missing"})
    expected_daily_markers = {
        f"Open human decisions: {len(open_ids)}": "daily_needs_human_count_mismatch",
        f"Accepted: {model['counts'].get('accepted', 0)}": "daily_accepted_count_mismatch",
        f"Rejected: {model['counts'].get('rejected', 0)}": "daily_rejected_count_mismatch",
        f"- Needs human: {model['counts'].get('needs_human', 0)}": "daily_status_count_mismatch",
    }
    for marker, reason in expected_daily_markers.items():
        if marker not in daily_text:
            errors.append({"path": str(daily_path), "expected": marker, "reason": reason})

    queue_marker = f"Open human decisions: {len(open_ids)}"
    if queue_marker not in queue_text:
        errors.append({"path": str(queue_path), "expected": queue_marker, "reason": "queue_open_count_mismatch"})

    if model["review_minutes"] > max_review_minutes:
        errors.append(
            {
                "reason": "review_surface_exceeds_time_budget",
                "estimated_review_minutes": model["review_minutes"],
                "max_review_minutes": max_review_minutes,
            }
        )

    errors.extend(decision_log_errors(ops_dir))
    errors.extend(resolved_human_decision_errors(ops_dir, model["items"]))

    report = {
        "ok": not errors,
        "action": "surface_validated",
        "ops_dir": str(ops_dir),
        "generated_at": model["generated_at"],
        "open_human_decisions": len(open_ids),
        "queue_rows": len(queue_rows),
        "estimated_review_minutes": model["review_minutes"],
        "max_review_minutes": max_review_minutes,
        "errors": errors,
        "warnings": warnings,
    }
    return report, SUCCESS if not errors else VALIDATION_FAILED


def run_update(args: argparse.Namespace) -> int:
    try:
        now = parse_now(args.now)
    except ValueError as exc:
        print_json({"ok": False, "reason": "invalid_now", "error": str(exc)})
        return MALFORMED
    model = surface_model(args.ops_dir, now)
    daily_text = daily_status_markdown(model)
    queue_text = human_review_queue_markdown(model)
    if args.dry_run:
        print_json(
            {
                "ok": True,
                "action": "dry_run_surface_built",
                "ops_dir": str(args.ops_dir),
                "open_human_decisions": len(model["review_queue_rows"]),
                "estimated_review_minutes": model["review_minutes"],
                "daily_status": str(args.ops_dir / DAILY_NAME),
                "human_review_queue": str(args.ops_dir / QUEUE_NAME),
            }
        )
        return SUCCESS

    atomic_write_text(args.ops_dir / DAILY_NAME, daily_text)
    atomic_write_text(args.ops_dir / QUEUE_NAME, queue_text)
    weekly = None if args.no_weekly else update_weekly_digest(args.ops_dir, model)
    validation, code = validate_surface(args.ops_dir, now, args.max_review_minutes)
    validation.update(
        {
            "action": "surface_updated" if code == SUCCESS else "surface_updated_with_validation_errors",
            "daily_status": str(args.ops_dir / DAILY_NAME),
            "human_review_queue": str(args.ops_dir / QUEUE_NAME),
            "weekly_digest": str(weekly) if weekly is not None else None,
        }
    )
    print_json(validation)
    return code


def run_validate(args: argparse.Namespace) -> int:
    try:
        now = parse_now(args.now)
    except ValueError as exc:
        print_json({"ok": False, "reason": "invalid_now", "error": str(exc)})
        return MALFORMED
    report, code = validate_surface(args.ops_dir, now, args.max_review_minutes)
    print_json(report)
    return code


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build or validate the human review markdown surface.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    update = subparsers.add_parser("update", help="Write daily_status.md, human_review_queue.md, and weekly digest section.")
    update.add_argument("ops_dir", type=Path)
    update.add_argument("--now")
    update.add_argument("--max-review-minutes", type=float, default=10.0)
    update.add_argument("--dry-run", action="store_true")
    update.add_argument("--no-weekly", action="store_true")

    validate = subparsers.add_parser("validate", help="Validate surface files against current task state.")
    validate.add_argument("ops_dir", type=Path)
    validate.add_argument("--now")
    validate.add_argument("--max-review-minutes", type=float, default=10.0)

    return parser.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    if not args.ops_dir.exists():
        print_json({"ok": False, "reason": "ops_dir_missing", "ops_dir": str(args.ops_dir)})
        return MALFORMED
    if args.command == "update":
        return run_update(args)
    if args.command == "validate":
        return run_validate(args)
    print_json({"ok": False, "reason": "unknown_command", "command": args.command})
    return MALFORMED


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
