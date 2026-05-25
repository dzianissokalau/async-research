"""Console snapshot facet helpers."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from async_research_workflow.console.artifacts import artifact_link
from async_research_workflow.console.facets.base import RECENT_LIMIT
from async_research_workflow.console.facets.base import command_hint
from async_research_workflow.console.facets.base import compact_text
from async_research_workflow.console.facets.base import extract_validation_commands
from async_research_workflow.console.facets.base import first_section
from async_research_workflow.console.facets.base import issue
from async_research_workflow.console.facets.base import markdown_bullets
from async_research_workflow.console.facets.base import markdown_sections
from async_research_workflow.console.facets.base import normalize_list_value
from async_research_workflow.console.facets.base import reference_ids_from_text
from async_research_workflow.console.facets.base import safe_read_embedded_json
from async_research_workflow.console.facets.base import safe_read_json
from async_research_workflow.console.facets.base import tail_text
from async_research_workflow.scripts import autonomy_readiness_gate
from async_research_workflow.scripts import health_check
from async_research_workflow.scripts import needs_human_policy
from async_research_workflow.scripts import validate_transition

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

def claim_verification_summary(acceptance: dict[str, Any]) -> tuple[list[str], list[str]]:
    report = acceptance.get("claim_verification") if isinstance(acceptance.get("claim_verification"), dict) else {}
    if not report:
        return [], []
    checks = [
        f"claim verification: {report.get('status', 'unknown')}",
        f"verified claims: {report.get('claim_count', 0)}",
    ]
    if report.get("max_claim_strength"):
        checks.append(f"claim verification cap: {report.get('max_claim_strength')}")
    gaps: list[str] = []
    for blocker in report.get("acceptance_blockers", []):
        if isinstance(blocker, dict):
            gaps.append(f"{blocker.get('claim_id', 'claim')}: {blocker.get('message') or blocker.get('reason')}")
    for blocker in report.get("readiness_blockers", []):
        if isinstance(blocker, dict):
            text = f"{blocker.get('claim_id', 'claim')}: {blocker.get('message') or blocker.get('reason')}"
            if text not in gaps:
                gaps.append(text)
    return checks[:RECENT_LIMIT], gaps[:RECENT_LIMIT]

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
    claim_verification_checks, claim_verification_gaps = claim_verification_summary(acceptance)
    evidence_gaps.extend(claim_verification_gaps)
    validation_checks = [
        f"status validation: {payload.get('status') or 'unknown'}",
        *claim_gate_summary(task_dir),
        *claim_verification_checks,
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

def task_mode_policy(ops_dir: Path, task_dir: Path, payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("status") != "needs_human":
        return {
            "applicable": False,
            "status": "not_applicable",
            "reason": "task_not_needs_human",
            "can_auto_resolve": False,
            "human_required": False,
        }
    try:
        result = needs_human_policy.evaluate_policy(ops_dir, task_dir, payload)
    except Exception as exc:
        return {
            "applicable": True,
            "status": "unavailable",
            "reason": "mode_policy_unavailable",
            "message": str(exc),
            "can_auto_resolve": False,
            "human_required": True,
        }
    can_auto_resolve = result.get("can_auto_resolve") is True
    status = "auto_resolvable" if can_auto_resolve else "human_required"
    return {
        "applicable": True,
        "status": status,
        "policy_version": result.get("policy_version"),
        "mode": result.get("mode"),
        "risk_tolerance": result.get("risk_tolerance"),
        "can_auto_resolve": can_auto_resolve,
        "human_required": result.get("human_required") is not False,
        "reason": result.get("reason"),
        "decision": result.get("decision"),
        "target_status": result.get("target_status"),
        "policy_action": result.get("policy_action"),
        "instruction": result.get("instruction"),
        "required_auto_decision": result.get("required_auto_decision"),
        "actor": result.get("actor"),
        "confidence": result.get("confidence"),
        "gate_category": result.get("gate_category"),
        "gate_categories": result.get("gate_categories", []),
        "gate_trigger": result.get("gate_trigger"),
        "hard_stop_categories": result.get("hard_stop_categories", []),
        "interrupt_only_for": result.get("interrupt_only_for", []),
        "auto_resolve_command": command_hint(
            "Auto-resolve by policy",
            ["async-research", "decision", "auto-resolve-task", str(ops_dir), str(task_dir)],
        )
        if can_auto_resolve
        else None,
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
        "mode_policy": task_mode_policy(ops_dir, task_dir, payload),
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
        "mode_policy": {
            "applicable": False,
            "status": "not_applicable",
            "reason": "invalid_task_status",
            "can_auto_resolve": False,
            "human_required": False,
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
