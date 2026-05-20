"""Read-only console snapshot for local dashboard consumers.

JSON shape conventions:
- required-but-missing display values use the string ``"unavailable"``;
- optional details such as warning paths are omitted when absent;
- boolean safety markers are always present on the top-level envelope;
- timestamps are ISO-8601 UTC strings with a ``Z`` suffix.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import shlex
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from async_research_workflow.console.artifacts import artifact_link
from async_research_workflow.console import outcomes
from async_research_workflow.idea_catalog import catalog_dashboard_report
from async_research_workflow.scripts import analysis_surface
from async_research_workflow.scripts import autonomy_readiness_gate
from async_research_workflow.scripts import data_source_audit
from async_research_workflow.scripts import data_foundations
from async_research_workflow.scripts import deliverable_maturity
from async_research_workflow.scripts import health_check
from async_research_workflow.scripts import knowledge_library
from async_research_workflow.scripts import prompt_library
from async_research_workflow.scripts import runtime_artifacts
from async_research_workflow.scripts import schedule_manifest
from async_research_workflow.scripts import update_accepted_outputs_index
from async_research_workflow.scripts import validate_transition
from async_research_workflow.scripts.decision_log import read_decisions


SNAPSHOT_SCHEMA_VERSION = "console_snapshot_v1.0"
RECENT_LIMIT = 5
LIFECYCLE_TASK_STATUS_ORDER = {
    "needs_human": 0,
    "paused": 1,
    "invalid": 2,
    "in_progress": 3,
    "awaiting_review": 4,
    "single_review": 5,
    "panel_review": 6,
    "ready_for_worker": 7,
    "ready_for_planning": 8,
    "inbox": 9,
    "needs_revision": 10,
    "accepted": 11,
    "synthesized": 12,
    "rejected": 13,
}
LIFECYCLE_BLOCKED_STATUSES = {"needs_human", "paused", "invalid"}
LIFECYCLE_ACTIVE_STATUSES = {"in_progress", "awaiting_review", "single_review", "panel_review"}
LIFECYCLE_QUEUED_STATUSES = {"inbox", "ready_for_planning", "ready_for_worker", "needs_revision"}
LIFECYCLE_COMPLETE_STATUSES = {"accepted", "synthesized"}
LIFECYCLE_STATIONS = [
    {
        "id": "topic",
        "label": "Topic / Research Objective",
        "objective": "Anchor the project topic, scope, and intended target deliverable.",
        "task_types": set(),
        "keywords": ("topic", "objective", "scope", "roadmap"),
        "artifacts": (("Workspace README", "README.md"), ("Research roadmap", "research_roadmap.md")),
        "owner": "human",
        "next_task": "clarify project objective and final deliverable",
        "command": ("Review next safe action", ["async-research", "workflow", "next", "<ops_dir>"]),
    },
    {
        "id": "discovery",
        "label": "Discovery Inbox",
        "objective": "Collect raw leads, clusters, rejected ideas, and intake notes.",
        "task_types": {"idea_discovery"},
        "keywords": ("discovery", "inbox", "candidate", "cluster"),
        "artifacts": (("Discovery inbox", "discovery_inbox.md"), ("Research inbox", "inbox.md"), ("Discovery clusters", "discovery/clusters.md")),
        "owner": "planner",
        "next_task": "turn discovery leads into scored ideas",
        "command": ("Inspect idea portfolio", ["async-research", "idea", "catalog", "dashboard", "<ops_dir>"]),
    },
    {
        "id": "idea_catalog",
        "label": "Idea Catalog",
        "objective": "Score, dedupe, promote, or park candidate research ideas.",
        "task_types": {"idea_dedupe", "idea_scoring", "hypothesis_card"},
        "keywords": ("idea", "catalog", "score", "hypothesis"),
        "artifacts": (("Idea catalog", "ideas/idea_catalog.md"), ("Idea prioritization", "ideas/prioritization.md")),
        "owner": "planner",
        "next_task": "promote a supported idea into a task",
        "command": ("Inspect idea portfolio", ["async-research", "idea", "catalog", "dashboard", "<ops_dir>"]),
    },
    {
        "id": "source_data",
        "label": "Source And Data Readiness",
        "objective": "Confirm source governance, data access, data gaps, and usable evidence foundations.",
        "task_types": {"data_readiness"},
        "keywords": ("source", "data", "readiness", "audit", "governance"),
        "artifacts": (
            ("Source audit", "data_source_audit.md"),
            ("Data catalog", "data/data_catalog.md"),
            ("Known data gaps", "data/known_data_gaps.md"),
        ),
        "owner": "data steward",
        "next_task": "clear source and data blockers",
        "command": ("Open data dashboard", ["async-research", "data", "dashboard", "<ops_dir>"]),
    },
    {
        "id": "knowledge_library",
        "label": "Knowledge Library / Literature",
        "objective": "Organize literature, claims, methods, open questions, and topic coverage.",
        "task_types": {"literature_extract"},
        "keywords": ("literature", "library", "knowledge", "claim", "method"),
        "artifacts": (
            ("Knowledge index", "library/knowledge_index.md"),
            ("Source library", "library/source_library.md"),
            ("Open questions", "library/open_questions.md"),
        ),
        "owner": "researcher",
        "next_task": "extract or validate literature coverage",
        "command": ("Open library dashboard", ["async-research", "library", "dashboard", "<ops_dir>"]),
    },
    {
        "id": "dataset_evidence",
        "label": "Dataset Or Evidence Build",
        "objective": "Build task-specific datasets, manifests, evidence ledgers, and reproducible inputs.",
        "task_types": {"experiment_plan"},
        "keywords": ("dataset", "evidence", "manifest", "build", "experiment plan"),
        "artifacts": (("Evidence ledger", "evidence_ledger.md"), ("Data join map", "data/join_map.md")),
        "owner": "worker",
        "next_task": "prepare reproducible evidence inputs",
        "command": ("Inspect workflow next", ["async-research", "workflow", "next", "<ops_dir>"]),
    },
    {
        "id": "analysis",
        "label": "Analysis / Hypothesis Testing",
        "objective": "Run analyses, evaluate results, and test accepted hypotheses against governed evidence.",
        "task_types": {"run_analysis", "evaluate_results"},
        "keywords": ("analysis", "hypothesis", "result", "evaluate", "test"),
        "artifacts": (("Analysis run notes", "analysis.md"),),
        "owner": "analyst",
        "next_task": "run or review the active analysis task",
        "command": ("Open analysis dashboard", ["async-research", "analysis", "dashboard", "<ops_dir>"]),
    },
    {
        "id": "synthesis",
        "label": "Synthesis / Memo",
        "objective": "Turn accepted evidence into memo sections, synthesis, and decision-ready findings.",
        "task_types": {"memo_section", "weekly_synthesis"},
        "keywords": ("synthesis", "memo", "section", "finding"),
        "artifacts": (("Accepted outputs", "accepted_outputs_index.md"), ("Weekly digest", "weekly_digest.md")),
        "owner": "writer",
        "next_task": "synthesize accepted evidence into memo or paper sections",
        "command": ("Inspect workflow next", ["async-research", "workflow", "next", "<ops_dir>"]),
    },
    {
        "id": "draft",
        "label": "Draft",
        "objective": "Assemble the paper, outline, or shareable draft from accepted synthesis.",
        "task_types": {"status_update"},
        "keywords": ("draft", "paper", "manuscript", "outline"),
        "artifacts": (("Accepted outputs", "accepted_outputs_index.md"), ("Research roadmap", "research_roadmap.md")),
        "owner": "writer",
        "next_task": "assemble or revise the current draft artifact",
        "command": ("Inspect workflow next", ["async-research", "workflow", "next", "<ops_dir>"]),
    },
    {
        "id": "final_review",
        "label": "External Readiness Review",
        "objective": "Complete maturity review, resolve caveats, and decide whether the deliverable is ready to share.",
        "task_types": {"critic_review"},
        "keywords": ("review", "polish", "maturity", "qa", "acceptance"),
        "artifacts": (
            ("Human review queue", "human_review_queue.md"),
            ("Result acceptance policy", "result_acceptance_policy.md"),
            ("Rejected results", "rejected_results.md"),
        ),
        "owner": "reviewer",
        "next_task": "run maturity review and resolve remaining caveats",
        "command": ("Inspect workflow next", ["async-research", "workflow", "next", "<ops_dir>"]),
    },
]


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_now(value: str | None) -> datetime:
    if not value:
        return utc_now()
    parsed = health_check.parse_datetime(value)
    if parsed is None:
        raise ValueError(f"invalid --now value: {value}")
    return parsed


def iso_now(now: datetime) -> str:
    return now.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def tail_text(path: Path, limit: int = 1200) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return text[-limit:]


def issue(severity: str, reason: str, message: str, path: Path | str | None = None, details: Any = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "severity": severity,
        "reason": reason,
        "message": message,
    }
    if path is not None:
        payload["path"] = str(path)
    if details is not None:
        payload["details"] = details
    return payload


def unavailable(reason: str, message: str, path: Path | str | None = None, details: Any = None) -> dict[str, Any]:
    payload = {
        "available": False,
        "status": "unavailable",
        "reason": reason,
        "message": message,
        "summary": {},
        "warnings": [issue("warning", reason, message, path, details)],
    }
    if path is not None:
        payload["path"] = str(path)
    return payload


def dashboard_links(ops_dir: Path, report: dict[str, Any], name: str) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    if name == "ideas":
        for label, key in (("Idea catalog", "catalog_path"), ("Idea prioritization", "prioritization_path")):
            value = report.get(key)
            if value:
                links.append(artifact_link(ops_dir, label, Path(str(value))))
    elif name == "library":
        for label, relative in (
            ("Source library", "library/source_library.md"),
            ("Knowledge index", "library/knowledge_index.md"),
            ("Claim map", "library/claim_map.md"),
            ("Method index", "library/method_index.md"),
            ("Open questions", "library/open_questions.md"),
        ):
            links.append(artifact_link(ops_dir, label, ops_dir / relative))
    elif name == "data":
        for label, relative in (
            ("Data catalog", "data/data_catalog.md"),
            ("Known data gaps", "data/known_data_gaps.md"),
            ("Join map", "data/join_map.md"),
            ("Source audit", "data_source_audit.md"),
        ):
            links.append(artifact_link(ops_dir, label, ops_dir / relative))
    return links


def compact_dashboard(report: dict[str, Any], ops_dir: Path, name: str) -> dict[str, Any]:
    return {
        "available": True,
        "status": "available",
        "action": report.get("action"),
        "ok": report.get("ok"),
        "summary": report.get("summary", {}),
        "warnings": report.get("warnings", []),
        "failures": report.get("failures", []),
        "sections": report.get("sections", {}),
        "operator_summary": report.get("operator_summary", {}),
        "links": dashboard_links(ops_dir, report, name),
    }


def guarded_dashboard(
    ops_dir: Path,
    required_path: Path | None,
    name: str,
    loader: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    if required_path is not None and not required_path.exists():
        return unavailable(
            f"{name}_files_missing",
            f"{name} dashboard files are missing",
            required_path,
        )
    try:
        return compact_dashboard(loader(), ops_dir, name)
    except Exception as exc:
        return unavailable(
            f"{name}_dashboard_unavailable",
            f"{name} dashboard summary could not be rendered",
            ops_dir,
            str(exc),
        )


def markdown_table_rows(path: Path) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    warnings: list[dict[str, Any]] = []
    if not path.exists():
        return [], warnings
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        return [], [
            issue(
                "warning",
                "markdown_table_unreadable",
                "markdown table could not be read",
                path,
                str(exc),
            )
        ]
    header: list[str] | None = None
    rows: list[dict[str, str]] = []
    for line_number, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if not cells or all(not cell for cell in cells):
            continue
        if all(cell.replace("-", "").strip() == "" for cell in cells):
            continue
        if header is None:
            header = cells
            continue
        if len(cells) != len(header):
            warnings.append(
                issue(
                    "warning",
                    "malformed_markdown_table_row",
                    "markdown table row has a different number of cells than the header",
                    path,
                    {"line_number": line_number, "cell_count": len(cells), "header_count": len(header)},
                )
            )
            continue
        rows.append(dict(zip(header, cells)))
    return rows, warnings


def recent_markdown_rows(path: Path, limit: int = RECENT_LIMIT) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows, warnings = markdown_table_rows(path)
    return {
        "path": str(path),
        "exists": path.exists(),
        "count": len(rows),
        "recent_rows": rows[-limit:],
    }, warnings


def revalidation_state(rows: list[dict[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        status = str(row.get("revalidation_status") or "unavailable").strip() or "unavailable"
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items()))


def command_hint(label: str, argv: list[str]) -> dict[str, str]:
    return {
        "label": label,
        "command": " ".join(shlex.quote(str(part)) for part in argv),
    }


def limited(rows: list[dict[str, Any]], limit: int = RECENT_LIMIT) -> list[dict[str, Any]]:
    return rows[:limit]


def safe_read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def safe_read_embedded_json(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}
    for match in re.finditer(r"```(?:json)?\s*(.*?)```", text, re.IGNORECASE | re.DOTALL):
        try:
            payload = json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            continue
        return payload if isinstance(payload, dict) else {}
    start = text.find("{")
    if start < 0:
        return {}
    decoder = json.JSONDecoder()
    try:
        payload, _index = decoder.raw_decode(text[start:])
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def normalize_heading(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def markdown_sections(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return {}
    sections: dict[str, list[str]] = {"intro": []}
    current = "intro"
    for raw in lines:
        stripped = raw.strip()
        if stripped.startswith("## "):
            current = normalize_heading(stripped[3:])
            sections.setdefault(current, [])
            continue
        if stripped.startswith("# "):
            continue
        if stripped:
            sections.setdefault(current, []).append(stripped)
    return {key: "\n".join(value).strip() for key, value in sections.items() if "\n".join(value).strip()}


def first_section(sections: dict[str, str], *names: str) -> str:
    for name in names:
        text = sections.get(normalize_heading(name), "").strip()
        if text:
            return text
    return ""


def compact_text(value: Any, fallback: str = "unavailable", limit: int = 900) -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    if not text or text.lower() == "none":
        return fallback
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def normalize_list_value(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        rows = value
    elif isinstance(value, tuple):
        rows = list(value)
    elif isinstance(value, dict):
        rows = [f"{key}: {val}" for key, val in value.items()]
    else:
        text = str(value).strip()
        if not text or text.lower() == "none":
            return []
        rows = re.split(r"\s*(?:;|\n)\s*", text)
    output: list[str] = []
    for item in rows:
        text = str(item).strip().strip("-").strip()
        if text and text.lower() != "none" and text not in output:
            output.append(text)
    return output


def markdown_bullets(text: str, limit: int = RECENT_LIMIT) -> list[str]:
    rows: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("-", "*")):
            rows.append(stripped[1:].strip())
        elif stripped and not rows:
            rows.append(stripped)
        if len(rows) >= limit:
            break
    return [row for row in rows if row]


def reference_ids_from_text(*texts: str) -> list[str]:
    refs: list[str] = []
    for text in texts:
        for match in re.findall(r"\b(?:DS|LIT|IDEA|TASK)-[A-Za-z0-9_-]+\b", text):
            if match not in refs:
                refs.append(match)
    return refs


def extract_validation_commands(*paths: Path) -> list[str]:
    commands: list[str] = []
    patterns = [
        re.compile(r"`((?:\.venv/bin/)?async-research\s+[^`]+)`"),
        re.compile(r"((?:\.venv/bin/)?async-research\s+[A-Za-z0-9][^\n]+)"),
    ]
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for pattern in patterns:
            for match in pattern.findall(text):
                command = str(match).strip().rstrip(".")
                if command and command not in commands:
                    commands.append(command)
                if len(commands) >= RECENT_LIMIT:
                    return commands
    return commands


def task_trigger(payload: dict[str, Any], sections: dict[str, str]) -> str:
    for key in ("catalog_idea_id", "origin_idea_id", "parent_task_id", "triggered_by_task_id"):
        value = compact_text(payload.get(key), "", 240)
        if value:
            return value
    promotion = payload.get("catalog_promotion")
    if isinstance(promotion, dict):
        value = compact_text(promotion.get("catalog_idea_id") or promotion.get("source"), "", 240)
        if value:
            return value
    context = first_section(sections, "Cross-Task Anti-Context", "Context")
    if context:
        return compact_text(context, limit=360)
    return compact_text(payload.get("last_transition_reason"), "not recorded", 360)


def task_input_artifacts(payload: dict[str, Any], sections: dict[str, str]) -> list[str]:
    rows = normalize_list_value(payload.get("allowed_paths"))
    rows.extend(markdown_bullets(first_section(sections, "Context"), RECENT_LIMIT))
    output: list[str] = []
    for row in rows:
        if row not in output:
            output.append(row)
    return output[:8]


def task_output_artifacts(task_dir: Path, sections: dict[str, str], files: list[dict[str, Any]]) -> list[str]:
    rows = markdown_bullets(first_section(sections, "Required Output", "Output", "Deliverables"), RECENT_LIMIT)
    existing = [
        f"{file.get('label')}: {file.get('relative_path') or file.get('path')}"
        for file in files
        if file.get("exists") and file.get("label") in {"Worker output", "Result acceptance", "Review aggregate", "Review aggregate JSON"}
    ]
    rows.extend(existing)
    if (task_dir / "artifacts").is_dir():
        rows.append("Task artifacts directory")
    output: list[str] = []
    for row in rows:
        if row not in output:
            output.append(row)
    return output[:8]


def next_task_text(payload: dict[str, Any], sections: dict[str, str]) -> str:
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    followups = normalize_list_value(result.get("followups"))
    if followups:
        return followups[0]
    recommendation = compact_text(result.get("recommendation"), "", 240)
    if recommendation:
        return recommendation
    required = first_section(sections, "Required Output")
    match = re.search(r"recommended next task:?\s*`?([A-Za-z0-9_\- ]+)`?", required, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    status = str(payload.get("status") or "")
    if status in {"awaiting_review", "single_review", "panel_review"}:
        return "complete or aggregate review"
    if status in {"accepted", "synthesized"}:
        return "inspect downstream lifecycle station"
    if payload.get("requires_human") or status == "needs_human":
        return "resolve the human gate"
    if status == "ready_for_worker":
        return "run the worker"
    return "inspect workflow next"


def task_dependencies(payload: dict[str, Any], sections: dict[str, str], worker_text: str) -> list[str]:
    rows = [f"data source: {ref}" for ref in normalize_list_value(payload.get("data_audit_refs"))]
    rows.extend(reference_ids_from_text(json.dumps(payload, sort_keys=True), "\n".join(sections.values()), worker_text))
    output: list[str] = []
    for row in rows:
        if row not in output:
            output.append(row)
    return output[:8]


def task_explainability(ops_dir: Path, task_dir: Path, payload: dict[str, Any], files: list[dict[str, Any]]) -> dict[str, Any]:
    task_path = task_dir / "task.md"
    worker_path = task_dir / "worker_output.md"
    sections = markdown_sections(task_path)
    worker_text = tail_text(worker_path, 2000)
    objective = first_section(sections, "Objective", "Scope", "Context")
    research_question = first_section(sections, "Research Question", "Question")
    if not research_question:
        research_question = objective
    return {
        "available": bool(sections or worker_text or payload),
        "rationale": compact_text(objective or payload.get("title"), limit=700),
        "research_question": compact_text(research_question or payload.get("title"), limit=700),
        "trigger": task_trigger(payload, sections),
        "input_artifacts": task_input_artifacts(payload, sections),
        "output_artifacts": task_output_artifacts(task_dir, sections, files),
        "dependencies": task_dependencies(payload, sections, worker_text),
        "unblocks": normalize_list_value((payload.get("result") or {}).get("followups") if isinstance(payload.get("result"), dict) else None),
        "next_recommended_task": next_task_text(payload, sections),
        "next_command": command_hint("Inspect workflow next", ["async-research", "workflow", "next", str(ops_dir)]),
        "validation_commands": extract_validation_commands(worker_path, task_dir / "review_panel" / "aggregate.md"),
    }


def read_task_reviews(task_dir: Path, aggregate: dict[str, Any]) -> list[dict[str, Any]]:
    reviews = aggregate.get("reviews")
    if isinstance(reviews, list):
        return [review for review in reviews if isinstance(review, dict)]
    loaded: list[dict[str, Any]] = []
    reviews_dir = task_dir / "reviews"
    if reviews_dir.is_dir():
        for path in sorted(reviews_dir.glob("*.md")):
            payload = safe_read_embedded_json(path)
            if payload:
                loaded.append(payload)
    return loaded


def confidence_summary(reviews: list[dict[str, Any]]) -> dict[str, Any]:
    values = [
        float(review["confidence"])
        for review in reviews
        if isinstance(review.get("confidence"), (int, float)) and not isinstance(review.get("confidence"), bool)
    ]
    if not values:
        return {"count": 0, "min": None, "average": None}
    return {
        "count": len(values),
        "min": round(min(values), 3),
        "average": round(sum(values) / len(values), 3),
    }


def review_modes(payload: dict[str, Any], aggregate: dict[str, Any], acceptance: dict[str, Any], reviews: list[dict[str, Any]]) -> list[str]:
    modes: list[str] = []
    policy = payload.get("review_policy") if isinstance(payload.get("review_policy"), dict) else {}
    panel = acceptance.get("reviewer_panel") if isinstance(acceptance.get("reviewer_panel"), dict) else {}
    reviewer_count = panel.get("reviewer_count") if isinstance(panel.get("reviewer_count"), int) else len(reviews)
    tier = aggregate.get("tier") if isinstance(aggregate.get("tier"), int) else policy.get("tier")
    if reviewer_count > 1 or policy.get("panel_required") is True or (isinstance(tier, int) and tier >= 2):
        modes.append("panel-based")
    if reviews:
        modes.append("independent")
    human_gate = acceptance.get("human_gate") if isinstance(acceptance.get("human_gate"), dict) else {}
    if policy.get("human_required_for_acceptance") is True or human_gate.get("satisfied") is True and human_gate.get("required") is True:
        modes.append("human-approved")
    if not modes:
        modes.append("same-agent or not recorded")
    return modes


def source_gate_summary(payload: dict[str, Any], acceptance: dict[str, Any]) -> dict[str, Any]:
    source = acceptance.get("source_governance") if isinstance(acceptance.get("source_governance"), dict) else {}
    source_ids = normalize_list_value(source.get("source_ids") if source else payload.get("data_audit_refs"))
    blocked = source.get("blocked") if isinstance(source.get("blocked"), list) else []
    warnings = source.get("warnings") if isinstance(source.get("warnings"), list) else []
    if source:
        status = "pass" if source.get("ok") is True and not blocked else "blocked"
    elif source_ids:
        status = "not checked"
    else:
        status = "not applicable"
    return {
        "status": status,
        "required": source.get("required") if source else bool(source_ids),
        "source_ids": source_ids,
        "blocked": blocked[:RECENT_LIMIT],
        "warnings": warnings[:RECENT_LIMIT],
    }


def claim_gate_summary(task_dir: Path) -> list[str]:
    checks: list[str] = []
    for path in sorted((task_dir / "artifacts").glob("**/claim_gates.json")):
        payload = safe_read_json(path)
        gates = payload.get("claim_gate_results") if isinstance(payload.get("claim_gate_results"), list) else []
        counts: dict[str, int] = {}
        for gate in gates:
            if not isinstance(gate, dict):
                continue
            status = str(gate.get("status") or "unknown")
            counts[status] = counts.get(status, 0) + 1
        if counts:
            summary = ", ".join(f"{status}: {count}" for status, count in sorted(counts.items()))
            checks.append(f"{path.name}: {summary}")
        if payload.get("claim_decision"):
            checks.append(f"claim decision: {payload.get('claim_decision')}")
        if payload.get("max_claim_strength"):
            checks.append(f"max claim strength: {payload.get('max_claim_strength')}")
    return checks[:RECENT_LIMIT]


def reproducibility_checks(acceptance: dict[str, Any], task_dir: Path) -> list[str]:
    checks: list[str] = []
    scorecard = acceptance.get("scorecard") if isinstance(acceptance.get("scorecard"), dict) else {}
    if "reproducibility" in scorecard:
        checks.append(f"scorecard reproducibility: {scorecard['reproducibility']}")
    analysis_run = acceptance.get("analysis_run") if isinstance(acceptance.get("analysis_run"), dict) else {}
    if analysis_run.get("run_id"):
        checks.append(f"analysis run: {analysis_run['run_id']}")
    for filename in ("run_manifest.json", "metrics.json", "diagnostics.json", "robustness_checks.json"):
        if any(task_dir.glob(f"artifacts/**/{filename}")):
            checks.append(f"{filename} present")
    return checks[:RECENT_LIMIT]


def task_qa_summary(task_dir: Path, payload: dict[str, Any]) -> dict[str, Any]:
    aggregate = safe_read_json(task_dir / "review_panel" / "aggregate.json")
    acceptance = safe_read_json(task_dir / "review_panel" / "result_acceptance.json")
    reviews = read_task_reviews(task_dir, aggregate)
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    caveats = normalize_list_value(result.get("caveats"))
    caveats.extend(normalize_list_value(acceptance.get("review_notes") if acceptance else []))
    evidence_gaps: list[str] = []
    for review in reviews:
        evidence_gaps.extend(normalize_list_value(review.get("evidence_gaps")))
    hard_gates = acceptance.get("hard_gate_results") if isinstance(acceptance.get("hard_gate_results"), list) else []
    failed_gates = [
        f"{gate.get('gate')}: {gate.get('reason')}"
        for gate in hard_gates
        if isinstance(gate, dict) and gate.get("passed") is False
    ]
    evidence_gaps.extend(failed_gates)
    source_gate = source_gate_summary(payload, acceptance)
    validation_checks = [
        f"status validation: {payload.get('status') or 'unknown'}",
        *claim_gate_summary(task_dir),
    ]
    if source_gate["status"] != "not applicable":
        validation_checks.append(f"source gate: {source_gate['status']}")
    panel = acceptance.get("reviewer_panel") if isinstance(acceptance.get("reviewer_panel"), dict) else {}
    return {
        "available": bool(aggregate or acceptance or reviews or result),
        "review_status": compact_text(panel.get("aggregate_decision") or aggregate.get("aggregate_decision") or payload.get("status")),
        "routing_reason": compact_text(aggregate.get("routing_reason") or payload.get("last_transition_reason"), "unavailable", 360),
        "review_modes": review_modes(payload, aggregate, acceptance, reviews),
        "review_chain": [
            {
                "role": review.get("reviewer_role") or review.get("role") or "unavailable",
                "decision": review.get("decision", "unavailable"),
                "confidence": review.get("confidence"),
                "claim_strength": review.get("claim_strength", "unavailable"),
                "concerns": normalize_list_value(review.get("main_concerns"))[:3],
                "evidence_gaps": normalize_list_value(review.get("evidence_gaps"))[:3],
            }
            for review in reviews[:RECENT_LIMIT]
        ],
        "reviewer_confidence": confidence_summary(reviews),
        "claim_strength": compact_text(
            acceptance.get("claim_strength") or aggregate.get("aggregate_claim_strength") or result.get("claim_strength"),
            "none",
            120,
        ),
        "max_claim_strength": compact_text(acceptance.get("max_claim_strength"), "unavailable", 120),
        "caveats": caveats[:RECENT_LIMIT],
        "evidence_gaps": evidence_gaps[:RECENT_LIMIT],
        "source_gate": source_gate,
        "reproducibility_checks": reproducibility_checks(acceptance, task_dir),
        "validation_checks": validation_checks[:RECENT_LIMIT],
        "scorecard": acceptance.get("scorecard") if isinstance(acceptance.get("scorecard"), dict) else {},
        "result_acceptance": {
            "route": compact_text(acceptance.get("route"), "unavailable", 160),
            "recommended_decision": compact_text(acceptance.get("recommended_decision"), "unavailable", 160),
        },
    }


def task_id(payload: dict[str, Any], fallback: Path) -> str:
    return str(payload.get("id") or fallback.name)


def task_file_links(ops_dir: Path, task_dir: Path, status_path: Path) -> list[dict[str, Any]]:
    files: list[tuple[str, Path]] = [
        ("Task brief", task_dir / "task.md"),
        ("Status JSON", status_path),
        ("Worker output", task_dir / "worker_output.md"),
        ("Review aggregate", task_dir / "review_panel" / "aggregate.md"),
        ("Review aggregate JSON", task_dir / "review_panel" / "aggregate.json"),
        ("Result acceptance", task_dir / "review_panel" / "result_acceptance.json"),
    ]
    seen = {path for _, path in files}
    for reviews_dir in (task_dir / "reviews", task_dir / "review_panel"):
        if reviews_dir.is_dir():
            for path in sorted([*reviews_dir.glob("*.md"), *reviews_dir.glob("*.json")]):
                if path not in seen:
                    files.append((path.name, path))
                    seen.add(path)
    artifacts_dir = task_dir / "artifacts"
    if artifacts_dir.is_dir():
        for path in sorted(item for item in artifacts_dir.rglob("*") if item.is_file())[:20]:
            if path not in seen:
                files.append((path.relative_to(task_dir).as_posix(), path))
                seen.add(path)
    return [artifact_link(ops_dir, label, path) for label, path in files]


def task_lock_state(task_dir: Path, now: datetime) -> dict[str, Any]:
    lock_dir = task_dir / "LOCK"
    if not lock_dir.exists():
        return {
            "locked": False,
            "stale": False,
            "lock_dir": str(lock_dir),
            "age_minutes": None,
            "owner": None,
        }
    try:
        age_minutes = round((now.timestamp() - lock_dir.stat().st_mtime) / 60, 2)
    except OSError:
        age_minutes = None
    return {
        "locked": lock_dir.is_dir(),
        "stale": bool(age_minutes is not None and age_minutes >= 60.0),
        "lock_dir": str(lock_dir),
        "age_minutes": age_minutes,
        "owner": autonomy_readiness_gate.lock_owner(task_dir),
    }


def transition_summary(payload: dict[str, Any], status_path: Path) -> dict[str, Any]:
    status = payload.get("status")
    previous = payload.get("previous_status")
    decisions_path = validate_transition.infer_decisions_path(status_path)
    code, result = validate_transition.validate_payload(payload, decisions_path=decisions_path)
    return {
        "valid": code == validate_transition.SUCCESS,
        "exit_code": code,
        "reason": result.get("reason"),
        "previous_status": previous,
        "status": status,
        "allowed_next_statuses": sorted(validate_transition.ALLOWED.get(status, set())) if isinstance(status, str) else [],
    }


def status_validation_entry(status_path: Path, malformed_by_path: dict[str, dict[str, Any]]) -> dict[str, Any]:
    issue_record = malformed_by_path.get(str(status_path))
    if issue_record is None:
        return {
            "valid": True,
            "reason": "valid",
            "issues": [],
        }
    return {
        "valid": False,
        "reason": issue_record.get("reason", "invalid_status"),
        "issues": issue_record.get("errors") or [issue_record],
    }


def task_row(ops_dir: Path, item: dict[str, Any], now: datetime, malformed_by_path: dict[str, dict[str, Any]]) -> dict[str, Any]:
    task_dir = item["task_dir"]
    status_path = item["status_path"]
    payload = item["payload"]
    transition = transition_summary(payload, status_path)
    files = task_file_links(ops_dir, task_dir, status_path)
    budget = payload.get("budget") if isinstance(payload.get("budget"), dict) else {}
    max_api_usd = health_check.safe_float(budget.get("max_api_usd"))
    max_compute_usd = health_check.safe_float(budget.get("max_compute_usd"))
    return {
        "task_id": task_id(payload, task_dir),
        "title": payload.get("title", "unavailable"),
        "status": payload.get("status", "unknown"),
        "previous_status": payload.get("previous_status"),
        "type": payload.get("type", "unavailable"),
        "review_tier": (payload.get("review_policy") or {}).get("tier", "unavailable")
        if isinstance(payload.get("review_policy"), dict)
        else "unavailable",
        "revision_count": payload.get("revision_count", "unavailable"),
        "max_revisions": payload.get("max_revisions", "unavailable"),
        "revision_limit_hit": payload.get("revision_limit_hit", "unavailable"),
        "requires_human": payload.get("requires_human", False),
        "human_gate_reason": payload.get("human_gate_reason"),
        "human_gate": payload.get("human_gate") if isinstance(payload.get("human_gate"), dict) else None,
        "last_transition_reason": payload.get("last_transition_reason"),
        "allow_network": payload.get("allow_network", False),
        "model_tier": payload.get("model_tier", "unavailable"),
        "max_minutes": payload.get("max_minutes", "unavailable"),
        "budget": {
            "max_api_usd": max_api_usd if max_api_usd is not None else 0.0,
            "max_compute_usd": max_compute_usd if max_compute_usd is not None else 0.0,
            "max_total_usd": round((max_api_usd or 0.0) + (max_compute_usd or 0.0), 4),
        },
        "allowed_paths": payload.get("allowed_paths", []),
        "allowed_next_statuses": transition["allowed_next_statuses"],
        "status_validation": status_validation_entry(status_path, malformed_by_path),
        "transition_validation": transition,
        "lock_state": task_lock_state(task_dir, now),
        "files": files,
        "explainability": task_explainability(ops_dir, task_dir, payload, files),
        "qa": task_qa_summary(task_dir, payload),
        "task_dir": str(task_dir),
        "status_path": str(status_path),
    }


def malformed_task_row(item: dict[str, Any], now: datetime, ops_dir: Path | None = None) -> dict[str, Any]:
    raw_task_dir = item.get("task_dir")
    task_dir = Path(str(raw_task_dir)) if raw_task_dir else None
    raw_status_path = item.get("status_path")
    if raw_status_path:
        status_path = Path(str(raw_status_path))
    elif task_dir is not None:
        status_path = task_dir / "status.json"
    else:
        status_path = None
    task_id_value = str(item.get("task_id") or (task_dir.name if task_dir is not None else "") or "unavailable")
    workspace_dir = ops_dir
    if workspace_dir is None and task_dir is not None and task_dir.parent.name == "tasks":
        workspace_dir = task_dir.parent.parent
    return {
        "task_id": task_id_value,
        "title": "Invalid status.json",
        "status": "invalid",
        "previous_status": None,
        "type": "unavailable",
        "review_tier": "unavailable",
        "revision_count": "unavailable",
        "max_revisions": "unavailable",
        "revision_limit_hit": "unavailable",
        "requires_human": False,
        "human_gate_reason": item.get("reason"),
        "human_gate": None,
        "last_transition_reason": item.get("error") or item.get("reason"),
        "allow_network": False,
        "model_tier": "unavailable",
        "max_minutes": "unavailable",
        "budget": {
            "max_api_usd": 0.0,
            "max_compute_usd": 0.0,
            "max_total_usd": 0.0,
        },
        "allowed_paths": [],
        "allowed_next_statuses": [],
        "status_validation": {
            "valid": False,
            "reason": item.get("reason", "invalid_status"),
            "issues": item.get("errors") or [item],
        },
        "transition_validation": {
            "valid": False,
            "exit_code": validate_transition.MALFORMED,
            "reason": item.get("reason", "invalid_status"),
            "previous_status": None,
            "status": "invalid",
            "allowed_next_statuses": [],
        },
        "lock_state": task_lock_state(task_dir, now)
        if task_dir is not None
        else {"locked": False, "stale": False, "lock_dir": "", "age_minutes": None, "owner": None},
        "files": task_file_links(workspace_dir, task_dir, status_path) if workspace_dir is not None and task_dir is not None and status_path is not None else [],
        "explainability": {
            "available": False,
            "rationale": "unavailable",
            "research_question": "unavailable",
            "trigger": item.get("reason", "invalid_status"),
            "input_artifacts": [],
            "output_artifacts": [],
            "dependencies": [],
            "unblocks": [],
            "next_recommended_task": "fix status.json",
            "next_command": command_hint("Validate workflow", ["async-research", "workflow", "check", str(workspace_dir or "")]),
            "validation_commands": [],
        },
        "qa": {
            "available": False,
            "review_status": "invalid",
            "routing_reason": item.get("reason", "invalid_status"),
            "review_modes": ["not recorded"],
            "review_chain": [],
            "reviewer_confidence": {"count": 0, "min": None, "average": None},
            "claim_strength": "none",
            "max_claim_strength": "unavailable",
            "caveats": [],
            "evidence_gaps": item.get("errors") or [item],
            "source_gate": {"status": "not applicable", "required": False, "source_ids": [], "blocked": [], "warnings": []},
            "reproducibility_checks": [],
            "validation_checks": ["status validation: invalid"],
            "scorecard": {},
            "result_acceptance": {"route": "unavailable", "recommended_decision": "unavailable"},
        },
        "task_dir": str(task_dir) if task_dir is not None else "",
        "status_path": str(status_path) if status_path is not None else "",
    }


def task_snapshot(ops_dir: Path, now: datetime, warnings: list[dict[str, Any]]) -> dict[str, Any]:
    tasks_dir = ops_dir / "tasks"
    schema = health_check.load_status_schema(health_check.DEFAULT_STATUS_SCHEMA)
    statuses, malformed = health_check.load_task_statuses(tasks_dir, schema)
    counts = health_check.status_counts(statuses)
    stale_locks = autonomy_readiness_gate.scan_stale_locks_at(tasks_dir, 60.0, now)
    malformed_by_path = {str(item.get("status_path")): item for item in malformed}
    rows = [task_row(ops_dir, item, now, malformed_by_path) for item in statuses]
    row_by_path = {str(item["status_path"]): row for item, row in zip(statuses, rows, strict=True)}
    status_paths = {str(status["status_path"]) for status in statuses}
    malformed_rows = [
        malformed_task_row(item, now, ops_dir)
        for item in malformed
        if str(item.get("status_path")) not in status_paths
    ]
    all_rows = sorted([*rows, *malformed_rows], key=lambda item: (str(item.get("task_id")), str(item.get("task_dir"))))
    active = [row_by_path[str(item["status_path"])] for item in autonomy_readiness_gate.active_tasks(statuses)]
    review = [row_by_path[str(item["status_path"])] for item in autonomy_readiness_gate.review_queue_tasks(statuses)]
    human = [
        row_by_path[str(item["status_path"])]
        for item in statuses
        if item["payload"].get("status") == "needs_human" or item["payload"].get("requires_human") is True
    ]
    blocked_statuses = {"needs_human", "paused"}
    blocked = [
        row_by_path[str(item["status_path"])]
        for item in statuses
        if item["payload"].get("status") in blocked_statuses or item["payload"].get("requires_human") is True
    ]
    for item in malformed:
        warnings.append(
            issue(
                "warning",
                "malformed_task_status",
                "task status could not be parsed or failed schema validation",
                item.get("status_path"),
                item,
            )
        )
    return {
        "tasks_dir": str(tasks_dir),
        "exists": tasks_dir.exists(),
        "total": len(statuses),
        "board_total": len(all_rows),
        "status_counts": counts,
        "status_filter_options": ["all", *sorted({str(item.get("status") or "unknown") for item in all_rows})],
        "all": all_rows,
        "active": active,
        "blocked": blocked,
        "review": review,
        "human": human,
        "malformed_statuses": malformed,
        "stale_locks": stale_locks,
    }


def workspace_snapshot(ops_dir: Path) -> dict[str, Any]:
    required = []
    for relative in autonomy_readiness_gate.REQUIRED_OPERATIONAL_FILES:
        path = ops_dir / relative
        required.append({"path": str(path), "relative_path": relative, "exists": path.exists()})
    missing = [item for item in required if not item["exists"]]
    return {
        "ops_dir": str(ops_dir),
        "exists": ops_dir.exists(),
        "is_dir": ops_dir.is_dir(),
        "starter_files": {
            "required_count": len(required),
            "available_count": len(required) - len(missing),
            "missing_count": len(missing),
            "missing": missing,
        },
    }


def readiness_snapshot(ops_dir: Path, now: datetime) -> dict[str, Any]:
    if not ops_dir.is_dir():
        return unavailable("ops_dir_missing", "readiness is unavailable until research_ops exists", ops_dir)
    try:
        args = autonomy_readiness_gate.parse_args([str(ops_dir), "--dry-run", "--no-daily-status", "--now", iso_now(now)])
        # build_gate_report is used here as a read-only report builder; writes live in the helper's main().
        report, exit_code = autonomy_readiness_gate.build_gate_report(args)
    except Exception as exc:
        return unavailable(
            "readiness_unavailable",
            "readiness report could not be generated",
            ops_dir,
            str(exc),
        )
    blockers = report.get("blockers", [])
    next_step = (
        "resolve blockers before running autonomous workers"
        if blockers
        else ("review warnings before starting expensive workers" if report.get("warnings") else "no readiness blockers")
    )
    return {
        "available": True,
        "status": "available",
        "verdict": report.get("decision"),
        "exit_code": exit_code,
        "blockers": blockers,
        "warnings": report.get("warnings", []),
        "next_step": next_step,
        "summary": report.get("summary", {}),
    }


def health_snapshot(ops_dir: Path, now: datetime) -> dict[str, Any]:
    if not ops_dir.is_dir():
        return unavailable("ops_dir_missing", "health is unavailable until research_ops exists", ops_dir)
    try:
        args = health_check.parse_args([str(ops_dir), "--dry-run", "--no-daily-status", "--now", iso_now(now)])
        # build_report is used here as a read-only report builder; writes live in the helper's main().
        report = health_check.build_report(args)
    except Exception as exc:
        return unavailable(
            "health_unavailable",
            "health report could not be generated",
            ops_dir,
            str(exc),
        )
    alerts = report.get("alerts", [])
    blockers = [item for item in alerts if item.get("severity") == "error"]
    next_step = (
        "repair health errors before continuing"
        if blockers
        else ("review health warnings" if alerts else "no health alerts")
    )
    accepted_memory = report.get("checks", {}).get("accepted_memory", {})
    return {
        "available": True,
        "status": "available",
        "verdict": report.get("summary", {}).get("highest_severity", "unavailable"),
        "exit_code": 0,
        "alerts": alerts,
        "blockers": blockers,
        "warnings": [item for item in alerts if item.get("severity") != "error"],
        "next_step": next_step,
        "summary": report.get("summary", {}),
        "checks": report.get("checks", {}),
        "thresholds": report.get("thresholds", {}),
        "stale_accepted_evidence": accepted_memory.get("stale_outputs", []) if isinstance(accepted_memory, dict) else [],
        "due_accepted_evidence": accepted_memory.get("due_outputs", []) if isinstance(accepted_memory, dict) else [],
        "recovery_commands": health_recovery_commands(ops_dir, report),
    }


def human_decisions_snapshot(ops_dir: Path, human_tasks: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    decisions_path = ops_dir / "decisions.md"
    warnings: list[dict[str, Any]] = []
    try:
        decision_rows = read_decisions(decisions_path)
    except (OSError, UnicodeDecodeError) as exc:
        decision_rows = []
        warnings.append(
            issue(
                "warning",
                "decision_log_unreadable",
                "decision log could not be read",
                decisions_path,
                str(exc),
            )
        )
    return {
        "open_count": len(human_tasks),
        "blocked_task_refs": human_tasks,
        "recent_decision_rows": decision_rows[-RECENT_LIMIT:],
        "decision_log_path": str(decisions_path),
        "decision_log_exists": decisions_path.exists(),
        "decision_log_count": len(decision_rows),
    }, warnings


def accepted_outputs_snapshot(ops_dir: Path, now: datetime) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    index_path = ops_dir / "accepted_outputs_index.md"
    rows, warnings = markdown_table_rows(index_path)
    try:
        memory_decay = update_accepted_outputs_index.memory_decay_report(ops_dir, now=now, index=index_path)
    except Exception as exc:
        memory_decay = {
            "ok": False,
            "row_count": len(rows),
            "current_count": 0,
            "due_count": 0,
            "stale_count": 0,
            "manual_review_count": 0,
            "superseded_count": 0,
            "due_outputs": [],
            "stale_outputs": [],
        }
        warnings.append(
            issue(
                "warning",
                "accepted_memory_decay_unavailable",
                "accepted memory freshness could not be computed",
                index_path,
                str(exc),
            )
        )
    return {
        "path": str(index_path),
        "exists": index_path.exists(),
        "count": len(rows),
        "recent_rows": rows[-RECENT_LIMIT:],
        "revalidation_state": revalidation_state(rows) if rows else {},
        "memory_decay": memory_decay,
        "stale_rows": memory_decay.get("stale_outputs", [])[:RECENT_LIMIT],
        "due_rows": memory_decay.get("due_outputs", [])[:RECENT_LIMIT],
        "recovery_commands": [
            command_hint("Write revalidation schedule", ["async-research", "accepted", "revalidation", str(ops_dir), "--write-schedule"]),
            command_hint("Run health dry-run", ["async-research", "health", str(ops_dir), "--dry-run"]),
        ],
    }, warnings


def delivered_projects_snapshot(ops_dir: Path, now: datetime) -> dict[str, Any]:
    index = outcomes.build_index(ops_dir, now=now)
    rows = index["projects"]
    generated_paths = index["paths"]
    return {
        "available": True,
        "status": "available",
        "path": generated_paths["projects_jsonl"],
        "summary_path": generated_paths["summary_json"],
        "exists": Path(generated_paths["projects_jsonl"]).exists(),
        "summary_exists": Path(generated_paths["summary_json"]).exists(),
        "count": len(rows),
        "status_filter_options": ["all", *sorted({str(row.get("delivered_status") or "unavailable") for row in rows})],
        "rows": rows,
        "summary": index["summary"],
        "warnings": [],
    }


def count_values(rows: Iterable[dict[str, Any]], getter: Callable[[dict[str, Any]], Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(getter(row) or "unavailable")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def compact_deliverable(model: dict[str, Any]) -> dict[str, Any]:
    deliverable = model.get("deliverable") if isinstance(model.get("deliverable"), dict) else {}
    editorial_qa = model.get("editorial_qa") if isinstance(model.get("editorial_qa"), dict) else {}
    return {
        "deliverable_id": model.get("deliverable_id"),
        "title": deliverable.get("title", "unavailable"),
        "output_type": deliverable.get("output_type", "unavailable"),
        "target_audience": deliverable.get("target_audience", ""),
        "target_venue": deliverable.get("target_venue", ""),
        "primary_artifact": deliverable.get("primary_artifact", ""),
        "source_task_ids": deliverable.get("source_task_ids", []),
        "target_ready": model.get("target_ready") is True,
        "readiness_label": model.get("readiness_label") or editorial_qa.get("honest_status", "unavailable"),
        "maturity": model.get("maturity", {}),
        "task_acceptance": model.get("task_acceptance", {}),
        "editorial_qa": editorial_qa,
        "checklist": model.get("checklist", []),
        "manuscript_checklist": model.get("manuscript_checklist", []),
        "critic_review": model.get("critic_review", {}),
        "response_matrix": model.get("response_matrix", {}),
        "review_independence": model.get("review_independence", {}),
        "open_gaps": model.get("open_gaps", []),
        "blockers": model.get("blockers", []),
        "warnings": model.get("warnings", []),
    }


def deliverables_snapshot(ops_dir: Path) -> dict[str, Any]:
    if not ops_dir.is_dir():
        return unavailable("ops_dir_missing", "deliverables are unavailable until research_ops exists", ops_dir)
    manifest_path = deliverable_maturity.manifest_path(ops_dir)
    projection_path = deliverable_maturity.projection_path(ops_dir)
    links = [
        artifact_link(ops_dir, "Deliverable manifest", manifest_path),
        artifact_link(ops_dir, "Deliverable projection", projection_path),
    ]
    manifest, errors = deliverable_maturity.load_manifest(ops_dir)
    warnings = [
        issue("warning", str(error.get("reason", "deliverable_manifest_invalid")), str(error.get("message", "deliverable manifest issue")), error.get("path"), error)
        for error in errors
    ]
    if errors:
        return {
            "available": True,
            "status": "malformed",
            "ok": False,
            "path": str(manifest_path),
            "exists": manifest_path.exists(),
            "count": 0,
            "summary": {
                "deliverable_count": 0,
                "target_ready_count": 0,
                "blocked_count": 0,
                "warning_count": len(warnings),
            },
            "rows": [],
            "attention_rows": [],
            "links": links,
            "warnings": warnings,
            "errors": errors,
        }

    rows: list[dict[str, Any]] = []
    for item in manifest.get("deliverables", []):
        if not isinstance(item, dict):
            continue
        try:
            rows.append(compact_deliverable(deliverable_maturity.read_model(ops_dir, item)))
        except Exception as exc:
            warnings.append(
                issue(
                    "warning",
                    "deliverable_read_model_unavailable",
                    "deliverable read model could not be rendered",
                    manifest_path,
                    {"deliverable_id": item.get("deliverable_id"), "error": str(exc)},
                )
            )

    attention_rows = [row for row in rows if not row.get("target_ready") or row.get("warnings")]
    summary = {
        "deliverable_count": len(rows),
        "target_ready_count": sum(1 for row in rows if row.get("target_ready")),
        "blocked_count": sum(1 for row in rows if row.get("blockers")),
        "warning_count": len(warnings) + sum(len(row.get("warnings", [])) for row in rows),
        "open_gap_count": sum(int((row.get("editorial_qa") or {}).get("open_gap_count") or 0) for row in rows),
        "open_critical_major_response_count": sum(
            int((row.get("editorial_qa") or {}).get("open_critical_major_response_count") or 0) for row in rows
        ),
        "same_agent_review_count": sum(1 for row in rows if (row.get("review_independence") or {}).get("same_agent_review") is True),
        "maturity_targets": count_values(rows, lambda row: (row.get("maturity") or {}).get("target")),
        "maturity_current": count_values(rows, lambda row: (row.get("maturity") or {}).get("current")),
        "readiness_labels": count_values(rows, lambda row: row.get("readiness_label")),
    }
    return {
        "available": True,
        "status": "available",
        "ok": summary["blocked_count"] == 0,
        "path": str(manifest_path),
        "exists": manifest_path.exists(),
        "count": len(rows),
        "summary": summary,
        "rows": rows,
        "attention_rows": attention_rows[:RECENT_LIMIT],
        "links": links,
        "warnings": warnings,
    }


def prompts_snapshot(ops_dir: Path) -> dict[str, Any]:
    try:
        return prompt_library.library_snapshot(ops_dir)
    except Exception as exc:
        return unavailable(
            "prompts_unavailable",
            "prompt library could not be read",
            ops_dir / "prompts",
            str(exc),
        )


def schedules_snapshot(ops_dir: Path) -> dict[str, Any]:
    try:
        return schedule_manifest.schedule_snapshot(ops_dir)
    except Exception as exc:
        return unavailable(
            "schedules_unavailable",
            "schedule manifest could not be read",
            ops_dir / "schedules.json",
            str(exc),
        )


def rejected_results_snapshot(ops_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    return recent_markdown_rows(ops_dir / "rejected_results.md")


def health_recovery_commands(ops_dir: Path, report: dict[str, Any]) -> list[dict[str, str]]:
    alerts = report.get("alerts", []) if isinstance(report.get("alerts"), list) else []
    checks = {str(alert.get("check")) for alert in alerts if isinstance(alert, dict)}
    commands = [
        command_hint("Run health dry-run", ["async-research", "health", str(ops_dir), "--dry-run"]),
        command_hint("Run workflow check", ["async-research", "workflow", "check", str(ops_dir)]),
    ]
    if checks & {"monthly_budget_threshold", "weekly_budget_threshold"}:
        commands.append(command_hint("Inspect cost summary", ["async-research", "cost", "summary", str(ops_dir)]))
    if checks & {"source_governance_errors", "source_freshness_warnings", "blocked_data_sources", "data_foundation_findings"}:
        commands.extend(
            [
                command_hint("Validate source register", ["async-research", "source", "validate", str(ops_dir)]),
                command_hint("Review source freshness", ["async-research", "source", "freshness", str(ops_dir)]),
                command_hint("Open data dashboard", ["async-research", "data", "dashboard", str(ops_dir)]),
            ]
        )
    if checks & {"stale_accepted_evidence", "accepted_memory_revalidation_due"}:
        commands.append(command_hint("Write revalidation schedule", ["async-research", "accepted", "revalidation", str(ops_dir), "--write-schedule"]))
    if checks & {"stale_locks", "malformed_status_files", "stuck_tasks", "revision_limit_breaches"}:
        commands.append(command_hint("Inspect readiness", ["async-research", "readiness", str(ops_dir), "--dry-run"]))
    seen: set[str] = set()
    unique = []
    for command in commands:
        if command["command"] in seen:
            continue
        seen.add(command["command"])
        unique.append(command)
    return unique


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


def source_snapshot(ops_dir: Path, now: datetime, data_dashboard: dict[str, Any]) -> dict[str, Any]:
    audit_path = ops_dir / "data_source_audit.md"
    if not audit_path.exists():
        return unavailable("source_audit_missing", "source audit register is missing", audit_path)
    governance = data_source_audit.source_governance_report(ops_dir, now=now)
    sections = data_dashboard.get("sections", {}) if isinstance(data_dashboard.get("sections"), dict) else {}
    summary = data_dashboard.get("summary", {}) if isinstance(data_dashboard.get("summary"), dict) else {}
    candidate_sources = sections.get("candidate_sources", []) if isinstance(sections.get("candidate_sources"), list) else []
    needs_review_sources = sections.get("needs_review_sources", []) if isinstance(sections.get("needs_review_sources"), list) else []
    usable_today = sections.get("usable_today_sources", []) if isinstance(sections.get("usable_today_sources"), list) else []
    blocked_sources = sections.get("blocked_sources", []) if isinstance(sections.get("blocked_sources"), list) else governance.get("blocked_sources", [])
    stale_sources = sections.get("stale_source_reviews", []) if isinstance(sections.get("stale_source_reviews"), list) else governance.get("stale_sources", [])
    governance_blocked_by_id = {
        str(item.get("source_id")): item
        for item in governance.get("blocked_sources", [])
        if isinstance(item, dict) and item.get("source_id")
    }
    enriched_blocked_sources: list[dict[str, Any]] = []
    for row in blocked_sources if isinstance(blocked_sources, list) else []:
        if not isinstance(row, dict):
            continue
        source_id = str(row.get("source_id") or "").strip()
        merged = dict(row)
        governance_row = governance_blocked_by_id.get(source_id, {})
        if "available_actions" not in merged and isinstance(governance_row.get("available_actions"), list):
            merged["available_actions"] = governance_row["available_actions"]
        if "available_actions" not in merged:
            merged["available_actions"] = data_source_audit.source_blocker_actions(ops_dir, "accepted_evidence", merged)
        enriched_blocked_sources.append(merged)
    blocked_sources = enriched_blocked_sources
    attention_by_id: dict[str, dict[str, Any]] = {}
    for reason, rows in (
        ("blocked", blocked_sources),
        ("stale", stale_sources),
        ("candidate", candidate_sources),
        ("needs_review", needs_review_sources),
    ):
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            source_id = str(row.get("source_id") or "").strip()
            if not source_id:
                continue
            merged = dict(attention_by_id.get(source_id, {}))
            merged.update(row)
            reasons = set(merged.get("attention_reasons", []))
            reasons.add(reason)
            merged["attention_reasons"] = sorted(reasons)
            attention_by_id[source_id] = merged
    warnings: list[dict[str, Any]] = []
    for item in governance.get("warnings", []) if isinstance(governance.get("warnings"), list) else []:
        warnings.append(issue("warning", str(item.get("reason", "source_governance_warning")), str(item.get("message", "source governance warning")), audit_path, item))
    for item in governance.get("errors", []) if isinstance(governance.get("errors"), list) else []:
        warnings.append(issue("error", "source_governance_error", str(item.get("message", item)), audit_path, item))
    return {
        "available": True,
        "status": "available",
        "path": str(audit_path),
        "ok": governance.get("ok") is True and not warnings,
        "source_count": governance.get("source_count", summary.get("source_count", 0)),
        "summary": {
            "source_count": governance.get("source_count", summary.get("source_count", 0)),
            "usable_today_count": len(usable_today),
            "blocked_source_count": len(blocked_sources) if isinstance(blocked_sources, list) else 0,
            "stale_source_count": len(stale_sources) if isinstance(stale_sources, list) else 0,
            "candidate_source_count": len(candidate_sources),
            "needs_review_source_count": len(needs_review_sources),
            "governance_error_count": governance.get("error_count", 0),
            "governance_warning_count": governance.get("warning_count", 0),
        },
        "approval_counts": governance.get("approval_counts", {}),
        "tier_counts": governance.get("tier_counts", {}),
        "usable_today_sources": limited(usable_today),
        "attention_sources": limited(list(attention_by_id.values()), 10),
        "blocked_sources": limited(blocked_sources if isinstance(blocked_sources, list) else []),
        "stale_sources": limited(stale_sources if isinstance(stale_sources, list) else []),
        "candidate_sources": limited(candidate_sources),
        "needs_review_sources": limited(needs_review_sources),
        "recovery_commands": [
            command_hint("Validate source register", ["async-research", "source", "validate", str(ops_dir)]),
            command_hint("Review source freshness", ["async-research", "source", "freshness", str(ops_dir)]),
            command_hint("Open data dashboard", ["async-research", "data", "dashboard", str(ops_dir)]),
        ],
        "warnings": warnings,
    }


def lifecycle_search_text(row: dict[str, Any]) -> str:
    values = [
        row.get("task_id"),
        row.get("title"),
        row.get("type"),
        row.get("project_type"),
        row.get("key_finding"),
        row.get("claim_type"),
        row.get("status"),
        row.get("delivered_status"),
    ]
    return " ".join(str(value or "").lower() for value in values)


def lifecycle_station_matches(station: dict[str, Any], row: dict[str, Any]) -> bool:
    row_type = str(row.get("type") or row.get("project_type") or "").strip()
    task_types = station.get("task_types", set())
    if row_type and row_type in task_types:
        return True
    text = lifecycle_search_text(row)
    return any(keyword in text for keyword in station.get("keywords", ()))


def lifecycle_station_for_row(row: dict[str, Any], fallback: str = "topic") -> str:
    for station in LIFECYCLE_STATIONS:
        if lifecycle_station_matches(station, row):
            return str(station["id"])
    return fallback


def lifecycle_output_rows(delivered_projects: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    by_station: dict[str, list[dict[str, Any]]] = {str(station["id"]): [] for station in LIFECYCLE_STATIONS}
    for project in delivered_projects.get("rows", []) if isinstance(delivered_projects.get("rows"), list) else []:
        if not isinstance(project, dict):
            continue
        station_id = lifecycle_station_for_row(project, fallback="synthesis")
        by_station.setdefault(station_id, []).append(
            {
                "task_id": project.get("task_id"),
                "title": project.get("title"),
                "status": project.get("delivered_status"),
                "accepted_date": project.get("accepted_date"),
                "claim_strength": project.get("claim_strength"),
                "key_finding": project.get("key_finding"),
                "links": project.get("links", []),
            }
        )
    return by_station


def lifecycle_task_rows(tasks: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    by_station: dict[str, list[dict[str, Any]]] = {str(station["id"]): [] for station in LIFECYCLE_STATIONS}
    for task in tasks.get("all", []) if isinstance(tasks.get("all"), list) else []:
        if not isinstance(task, dict):
            continue
        station_id = lifecycle_station_for_row(task)
        by_station.setdefault(station_id, []).append(task)
    for station_id, rows in by_station.items():
        by_station[station_id] = sorted(
            rows,
            key=lambda task: (
                LIFECYCLE_TASK_STATUS_ORDER.get(str(task.get("status") or ""), 99),
                str(task.get("task_id") or ""),
                str(task.get("task_dir") or ""),
            ),
        )
    return by_station


def lifecycle_is_blocked_task(task: dict[str, Any]) -> bool:
    status = str(task.get("status") or "")
    validation = task.get("status_validation") if isinstance(task.get("status_validation"), dict) else {}
    transition = task.get("transition_validation") if isinstance(task.get("transition_validation"), dict) else {}
    return (
        status in LIFECYCLE_BLOCKED_STATUSES
        or task.get("requires_human") is True
        or validation.get("valid") is False
        or transition.get("valid") is False
    )


def lifecycle_station_status(tasks: list[dict[str, Any]], outputs: list[dict[str, Any]], artifacts: list[dict[str, Any]]) -> str:
    statuses = {str(task.get("status") or "") for task in tasks}
    if any(lifecycle_is_blocked_task(task) for task in tasks):
        return "blocked"
    if statuses & LIFECYCLE_ACTIVE_STATUSES:
        return "active"
    if statuses & LIFECYCLE_QUEUED_STATUSES:
        return "queued"
    if outputs or statuses & LIFECYCLE_COMPLETE_STATUSES:
        return "complete"
    if any(link.get("exists") for link in artifacts):
        return "ready"
    return "missing"


def lifecycle_station_artifacts(ops_dir: Path, station: dict[str, Any]) -> list[dict[str, Any]]:
    links = []
    for label, relative in station.get("artifacts", ()):
        links.append(artifact_link(ops_dir, str(label), ops_dir / str(relative)))
    return links


def lifecycle_command_for_station(ops_dir: Path, station: dict[str, Any]) -> dict[str, str]:
    label, argv = station["command"]
    return command_hint(str(label), [str(ops_dir) if part == "<ops_dir>" else part for part in argv])


def lifecycle_command_for_task(ops_dir: Path, task: dict[str, Any]) -> dict[str, str]:
    task_dir = str(task.get("task_dir") or "")
    status = str(task.get("status") or "")
    if not task_dir:
        return command_hint("Inspect workflow next", ["async-research", "workflow", "next", str(ops_dir)])
    if lifecycle_is_blocked_task(task):
        return command_hint(
            "Dry-run human decision",
            ["async-research", "decision", "resolve-task", str(ops_dir), task_dir, "--decision", "resume", "--dry-run"],
        )
    if status == "ready_for_worker":
        return command_hint("Dry-run worker start", ["async-research", "workflow", "worker-start", task_dir, "--dry-run"])
    if status == "in_progress":
        return command_hint("Dry-run worker complete", ["async-research", "workflow", "worker-complete", task_dir, "--dry-run"])
    if status in {"awaiting_review", "single_review", "panel_review"}:
        return command_hint("Inspect review state", ["async-research", "workflow", "status", task_dir])
    if status in {"inbox", "ready_for_planning", "needs_revision"}:
        return command_hint("Inspect task status", ["async-research", "workflow", "status", task_dir])
    return command_hint("Inspect workflow next", ["async-research", "workflow", "next", str(ops_dir)])


def lifecycle_owner_for_task(task: dict[str, Any], fallback: str) -> str:
    lock_state = task.get("lock_state") if isinstance(task.get("lock_state"), dict) else {}
    owner = str(lock_state.get("owner") or "").strip()
    if owner and owner.lower() != "none":
        return owner
    status = str(task.get("status") or "")
    if lifecycle_is_blocked_task(task):
        return "human"
    if status in {"awaiting_review", "single_review", "panel_review"}:
        return "reviewer"
    if status in {"inbox", "ready_for_planning"}:
        return "planner"
    if status in {"ready_for_worker", "in_progress"}:
        return "worker"
    return fallback


def lifecycle_blockers_for_station(station_id: str, tasks: list[dict[str, Any]], sources: dict[str, Any], health: dict[str, Any]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    for task in tasks:
        if not lifecycle_is_blocked_task(task):
            continue
        blockers.append(
            {
                "reason": str(task.get("human_gate_reason") or task.get("last_transition_reason") or task.get("status") or "blocked"),
                "task_id": task.get("task_id"),
                "status": task.get("status"),
                "task_dir": task.get("task_dir"),
            }
        )
    if station_id == "source_data":
        for source in sources.get("blocked_sources", []) if isinstance(sources.get("blocked_sources"), list) else []:
            if not isinstance(source, dict):
                continue
            blockers.append(
                {
                    "reason": str(source.get("reason") or source.get("approval_status") or "blocked_source"),
                    "source_id": source.get("source_id"),
                    "status": source.get("approval_status") or source.get("status"),
                    "path": sources.get("path"),
                }
            )
    if station_id == "topic":
        for alert in health.get("blockers", []) if isinstance(health.get("blockers"), list) else []:
            if isinstance(alert, dict):
                blockers.append(
                    {
                        "reason": str(alert.get("message") or alert.get("check") or "health_blocker"),
                        "status": alert.get("severity"),
                        "path": alert.get("path"),
                    }
                )
    return blockers[:RECENT_LIMIT]


def lifecycle_task_summary(task: dict[str, Any] | None) -> dict[str, Any] | None:
    if not task:
        return None
    return {
        "task_id": task.get("task_id"),
        "title": task.get("title"),
        "status": task.get("status"),
        "type": task.get("type"),
        "requires_human": task.get("requires_human"),
        "task_dir": task.get("task_dir"),
        "files": task.get("files", [])[:RECENT_LIMIT],
    }


def lifecycle_station_summary(status: str, tasks: list[dict[str, Any]], outputs: list[dict[str, Any]], blockers: list[dict[str, Any]]) -> str:
    if blockers:
        return f"{len(blockers)} blocker(s), {len(tasks)} task(s), {len(outputs)} accepted output(s)"
    if status == "complete":
        return f"{len(outputs) or len(tasks)} completed output/task item(s)"
    if tasks:
        return f"{len(tasks)} task(s), {len(outputs)} accepted output(s)"
    if status == "ready":
        return "station artifacts are available; no task has claimed this station yet"
    return "no station artifacts or tasks found yet"


def lifecycle_snapshot(
    ops_dir: Path,
    tasks: dict[str, Any],
    accepted_outputs: dict[str, Any],
    delivered_projects: dict[str, Any],
    health: dict[str, Any],
    sources: dict[str, Any],
) -> dict[str, Any]:
    tasks_by_station = lifecycle_task_rows(tasks)
    outputs_by_station = lifecycle_output_rows(delivered_projects)
    stations: list[dict[str, Any]] = []
    for station in LIFECYCLE_STATIONS:
        station_id = str(station["id"])
        station_tasks = tasks_by_station.get(station_id, [])
        outputs = outputs_by_station.get(station_id, [])
        artifacts = lifecycle_station_artifacts(ops_dir, station)
        status = lifecycle_station_status(station_tasks, outputs, artifacts)
        blockers = lifecycle_blockers_for_station(station_id, station_tasks, sources, health)
        if blockers:
            status = "blocked"
        active_task = next(
            (
                task
                for task in station_tasks
                if lifecycle_is_blocked_task(task)
                or str(task.get("status") or "") in LIFECYCLE_ACTIVE_STATUSES | LIFECYCLE_QUEUED_STATUSES
            ),
            None,
        )
        next_command = lifecycle_command_for_task(ops_dir, active_task) if active_task else lifecycle_command_for_station(ops_dir, station)
        stations.append(
            {
                "id": station_id,
                "label": station["label"],
                "objective": station["objective"],
                "status": status,
                "summary": lifecycle_station_summary(status, station_tasks, outputs, blockers),
                "accepted_outputs": outputs[:RECENT_LIMIT],
                "active_task": lifecycle_task_summary(active_task),
                "blockers": blockers,
                "next_recommended_task": active_task.get("title") if active_task else station["next_task"],
                "next_command": next_command,
                "owner_runner": lifecycle_owner_for_task(active_task, str(station["owner"])) if active_task else station["owner"],
                "artifact_links": artifacts,
            }
        )

    completed = [station for station in stations if station["status"] == "complete"]
    active = [station for station in stations if station["status"] in {"blocked", "active", "queued"}]
    missing = [station for station in stations if station["status"] == "missing"]
    if active:
        current = active[0]
    elif completed:
        current = next((station for station in stations if station["status"] in {"missing", "ready"}), stations[-1] if stations else None)
    else:
        current = stations[0] if stations else None
    return {
        "available": True,
        "status": "available",
        "station_count": len(stations),
        "completed_count": len(completed),
        "active_count": len(active),
        "missing_count": len(missing),
        "accepted_output_count": accepted_outputs.get("count", 0),
        "current_station_id": current.get("id") if current else None,
        "current_station_label": current.get("label") if current else None,
        "next_action": (current.get("next_command") or {}).get("command") if current else "",
        "stations": stations,
    }


def runs_snapshot(ops_dir: Path) -> dict[str, Any]:
    run_artifacts = ops_dir / "run_artifacts"
    if not run_artifacts.exists():
        return unavailable("run_artifacts_missing", "run artifacts are not available yet", run_artifacts)
    runs = []
    run_dirs = [path for path in run_artifacts.iterdir() if path.is_dir() and not path.name.startswith(".")]
    for run_dir in sorted(run_dirs, key=lambda path: path.stat().st_mtime, reverse=True):
        run_json = run_dir / "run.json"
        payload: dict[str, Any] = {}
        if run_json.exists():
            try:
                parsed = json.loads(run_json.read_text(encoding="utf-8"))
                if isinstance(parsed, dict):
                    payload = parsed
            except (OSError, json.JSONDecodeError) as exc:
                payload = {"warning": f"run.json could not be read: {exc}"}
        artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), dict) else {}
        stdout_log = Path(artifacts.get("stdout_log") or run_dir / "stdout.log")
        stderr_log = Path(artifacts.get("stderr_log") or run_dir / "stderr.log")
        final_message = Path(artifacts.get("final_message") or run_dir / "final_message.md")
        runs.append(
            {
                "run_id": payload.get("run_id", run_dir.name),
                "run_dir": str(run_dir),
                "status": payload.get("status", "unavailable"),
                "task_id": payload.get("task_id", "unavailable"),
                "job_id": payload.get("job_id", "unavailable"),
                "started_at": payload.get("started_at", "unavailable"),
                "finished_at": payload.get("finished_at", "unavailable"),
                "exit_code": payload.get("exit_code"),
                "command": payload.get("command", []),
                "prompt_id": payload.get("prompt_id", "unavailable"),
                "prompt_version": payload.get("prompt_version", "unavailable"),
                "final_message_preview": payload.get("final_message_preview") or tail_text(final_message, 800),
                "stdout_tail": tail_text(stdout_log, 1200),
                "stderr_tail": tail_text(stderr_log, 1200),
                "artifacts": {
                    "run_json": str(run_json),
                    "events_jsonl": artifacts.get("events_jsonl") or str(run_dir / "events.jsonl"),
                    "final_message": str(final_message),
                    "stdout_log": str(stdout_log),
                    "stderr_log": str(stderr_log),
                },
                "usage_ingestion": payload.get("usage_ingestion", {}),
            }
        )
    return {
        "available": True,
        "status": "available",
        "path": str(run_artifacts),
        "count": len(runs),
        "recent_runs": runs[:RECENT_LIMIT],
        "warnings": [],
    }


def runtime_snapshot(ops_dir: Path) -> dict[str, Any]:
    code, report = runtime_artifacts.validate_runtime_workspace(ops_dir)
    summary = report.get("summary", {}) if isinstance(report.get("summary"), dict) else {}
    errors = report.get("errors", []) if isinstance(report.get("errors"), list) else []
    warnings = report.get("warnings", []) if isinstance(report.get("warnings"), list) else []
    return {
        "available": code != runtime_artifacts.MALFORMED,
        "status": "available" if code == runtime_artifacts.SUCCESS else "findings",
        "ok": code == runtime_artifacts.SUCCESS,
        "read_only": True,
        "changed": False,
        "trace_count": summary.get("runtime_trace_count", 0),
        "evidence_object_count": summary.get("evidence_object_count", 0),
        "unsupported_or_stale_evidence_count": summary.get("unsupported_or_stale_evidence_count", 0),
        "latest_runtime_errors": summary.get("latest_runtime_errors", []),
        "summary": summary,
        "ledger_paths": report.get("ledger_paths", {}),
        "errors": errors[:RECENT_LIMIT],
        "warnings": warnings[:RECENT_LIMIT],
        "recovery_commands": [
            command_hint("Validate runtime ledgers", ["async-research", "runtime", "validate", str(ops_dir)]),
            command_hint("Summarize runtime ledgers", ["async-research", "runtime", "summary", str(ops_dir)]),
        ],
    }


def dashboard_summaries(ops_dir: Path, now: datetime) -> dict[str, Any]:
    return {
        "ideas": guarded_dashboard(
            ops_dir,
            ops_dir / "ideas",
            "ideas",
            lambda: catalog_dashboard_report(ops_dir),
        ),
        "data": guarded_dashboard(
            ops_dir,
            ops_dir / "data",
            "data",
            lambda: data_foundations.data_dashboard_report(
                ops_dir,
                now=now,
                use_case=data_foundations.DEFAULT_DASHBOARD_USE_CASE,
            ),
        ),
        "library": guarded_dashboard(
            ops_dir,
            ops_dir / "library",
            "library",
            lambda: knowledge_library.library_dashboard_report(
                ops_dir,
                now=now,
                stale_days=knowledge_library.SURFACE_STALE_DAYS,
            ),
        ),
        "analysis": guarded_dashboard(
            ops_dir,
            None,
            "analysis",
            lambda: analysis_surface.analysis_dashboard_report(ops_dir, now=now, max_items=RECENT_LIMIT),
        ),
    }


def collect_unavailable_warnings(groups: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    for group in groups:
        if group.get("available") is False:
            warnings.extend(group.get("warnings", []))
    return warnings


def snapshot(ops_dir: Path, now: datetime | None = None) -> dict[str, Any]:
    current = now or utc_now()
    warnings: list[dict[str, Any]] = []
    workspace = workspace_snapshot(ops_dir)
    workspace_ready = ops_dir.is_dir()
    tasks = task_snapshot(ops_dir, current, warnings) if workspace_ready else {
        "tasks_dir": str(ops_dir / "tasks"),
        "exists": False,
        "total": 0,
        "board_total": 0,
        "status_counts": {},
        "status_filter_options": ["all"],
        "all": [],
        "active": [],
        "blocked": [],
        "review": [],
        "human": [],
        "malformed_statuses": [],
        "stale_locks": [],
    }
    readiness = readiness_snapshot(ops_dir, current)
    health = health_snapshot(ops_dir, current)
    human_decisions, human_decision_warnings = human_decisions_snapshot(ops_dir, tasks["human"])
    accepted_outputs, accepted_warnings = accepted_outputs_snapshot(ops_dir, current)
    delivered_projects = delivered_projects_snapshot(ops_dir, current)
    deliverables = deliverables_snapshot(ops_dir) if workspace_ready else unavailable("ops_dir_missing", "deliverables are unavailable until research_ops exists", ops_dir)
    rejected_results, rejected_warnings = rejected_results_snapshot(ops_dir)
    cost = cost_snapshot(ops_dir, current, tasks.get("all", []))
    prompts = prompts_snapshot(ops_dir) if workspace_ready else unavailable("ops_dir_missing", "prompts are unavailable until research_ops exists", ops_dir)
    schedules = schedules_snapshot(ops_dir) if workspace_ready else unavailable("ops_dir_missing", "schedules are unavailable until research_ops exists", ops_dir)
    dashboards = dashboard_summaries(ops_dir, current) if workspace_ready else {
        "ideas": unavailable("ops_dir_missing", "ideas dashboard is unavailable until research_ops exists", ops_dir),
        "data": unavailable("ops_dir_missing", "data dashboard is unavailable until research_ops exists", ops_dir),
        "library": unavailable("ops_dir_missing", "library dashboard is unavailable until research_ops exists", ops_dir),
        "analysis": unavailable("ops_dir_missing", "analysis dashboard is unavailable until research_ops exists", ops_dir),
    }
    sources = source_snapshot(ops_dir, current, dashboards["data"]) if workspace_ready else unavailable("ops_dir_missing", "sources are unavailable until research_ops exists", ops_dir)
    runs = runs_snapshot(ops_dir) if workspace_ready else unavailable("ops_dir_missing", "runs are unavailable until research_ops exists", ops_dir)
    runtime = runtime_snapshot(ops_dir) if workspace_ready else unavailable("ops_dir_missing", "runtime is unavailable until research_ops exists", ops_dir)
    lifecycle = lifecycle_snapshot(ops_dir, tasks, accepted_outputs, delivered_projects, health, sources) if workspace_ready else unavailable(
        "ops_dir_missing",
        "lifecycle is unavailable until research_ops exists",
        ops_dir,
    )

    warnings.extend(human_decision_warnings)
    warnings.extend(accepted_warnings)
    warnings.extend(rejected_warnings)
    warnings.extend(cost.get("warnings", []))
    if sources.get("available") is not False:
        warnings.extend(sources.get("warnings", []))
    if deliverables.get("available") is not False:
        warnings.extend(deliverables.get("warnings", []))
    if runtime.get("available") is not False:
        warnings.extend(runtime.get("warnings", []))
        warnings.extend(runtime.get("errors", []))
    warnings.extend(collect_unavailable_warnings([readiness, health, prompts, schedules, sources, runs, runtime, lifecycle, deliverables, *dashboards.values()]))

    return {
        "ok": True,
        "action": "console_snapshot_rendered",
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "generated_at": iso_now(current),
        "read_only": True,
        "changed": False,
        "ops_dir": str(ops_dir),
        "workspace": workspace,
        "readiness": readiness,
        "health": health,
        "tasks": tasks,
        "human_decisions": human_decisions,
        "accepted_outputs": accepted_outputs,
        "delivered_projects": delivered_projects,
        "deliverables": deliverables,
        "rejected_results": rejected_results,
        "cost": cost,
        "sources": sources,
        "prompts": prompts,
        "schedules": schedules,
        "ideas": dashboards["ideas"],
        "data": dashboards["data"],
        "library": dashboards["library"],
        "analysis": dashboards["analysis"],
        "lifecycle": lifecycle,
        "runs": runs,
        "runtime": runtime,
        "warnings": warnings,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render a read-only console snapshot for a research_ops workspace.")
    parser.add_argument("ops_dir", nargs="?", type=Path, default=Path("research_ops"), help="Path to the research_ops workspace.")
    parser.add_argument("--json", action="store_true", help="Render JSON output. JSON is the only Slice 1 output mode.")
    parser.add_argument("--now", help="Override current time for deterministic snapshot tests, ISO-8601.")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv or []))
    try:
        current = parse_now(args.now)
    except ValueError as exc:
        print_json({"ok": False, "action": "console_snapshot_rendered", "reason": "invalid_now", "message": str(exc), "read_only": True, "changed": False})
        return 3
    print_json(snapshot(args.ops_dir, now=current))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
