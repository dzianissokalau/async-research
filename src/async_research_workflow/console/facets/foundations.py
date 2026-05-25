"""Console snapshot facet helpers."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from async_research_workflow.console.artifacts import artifact_link
from async_research_workflow.console.facets.base import RECENT_LIMIT
from async_research_workflow.console.facets.base import command_hint
from async_research_workflow.console.facets.base import issue
from async_research_workflow.console.facets.base import limited
from async_research_workflow.console.facets.base import unavailable
from async_research_workflow.scripts import data_source_audit

def dashboard_summaries(
    ops_dir: Path,
    now: datetime,
    *,
    ideas_loader: Callable[[], dict[str, Any]],
    data_loader: Callable[[], dict[str, Any]],
    library_loader: Callable[[], dict[str, Any]],
    analysis_loader: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    return {
        "ideas": guarded_dashboard(
            ops_dir,
            ops_dir / "ideas",
            "ideas",
            ideas_loader,
        ),
        "data": guarded_dashboard(
            ops_dir,
            ops_dir / "data",
            "data",
            data_loader,
        ),
        "library": guarded_dashboard(
            ops_dir,
            ops_dir / "library",
            "library",
            library_loader,
        ),
        "analysis": guarded_dashboard(
            ops_dir,
            None,
            "analysis",
            analysis_loader,
        ),
    }

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
