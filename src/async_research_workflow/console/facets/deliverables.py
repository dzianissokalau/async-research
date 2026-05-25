"""Console snapshot facet helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from async_research_workflow.console.artifacts import artifact_link
from async_research_workflow.console.facets.base import RECENT_LIMIT
from async_research_workflow.console.facets.base import count_values
from async_research_workflow.console.facets.base import issue
from async_research_workflow.console.facets.base import unavailable
from async_research_workflow.scripts import deliverable_maturity

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
