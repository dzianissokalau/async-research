"""Console snapshot facet helpers."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from async_research_workflow.console.facets.base import RECENT_LIMIT
from async_research_workflow.console.facets.base import command_hint
from async_research_workflow.console.facets.base import tail_text
from async_research_workflow.console.facets.base import unavailable
from async_research_workflow.scripts import evidence_memory
from async_research_workflow.scripts import runtime_artifacts
from async_research_workflow.scripts import runtime_evals

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

def evals_snapshot(ops_dir: Path) -> dict[str, Any]:
    return runtime_evals.evals_snapshot(ops_dir)

def evidence_memory_snapshot(ops_dir: Path, now: datetime) -> dict[str, Any]:
    code, report = evidence_memory.build_evidence_memory_index(ops_dir, now=now)
    return {
        "available": code != evidence_memory.MALFORMED,
        "status": "available" if code == evidence_memory.SUCCESS else "findings",
        "ok": code == evidence_memory.SUCCESS,
        "read_only": True,
        "changed": False,
        "index_path": str(ops_dir / evidence_memory.INDEX_RELATIVE_PATH),
        "entry_count": report.get("entry_count", 0),
        "contradiction_count": report.get("contradiction_count", 0),
        "stale_evidence_count": report.get("stale_evidence_count", 0),
        "reflection_count": report.get("reflection_count", 0),
        "recent_contradiction_edges": report.get("contradiction_edges", [])[:RECENT_LIMIT],
        "recent_targeted_reflections": report.get("targeted_reflections", [])[:RECENT_LIMIT],
        "warnings": report.get("warnings", [])[:RECENT_LIMIT],
        "errors": report.get("errors", [])[:RECENT_LIMIT],
        "recovery_commands": [
            command_hint("Update evidence memory", ["async-research", "evidence-memory", "update", str(ops_dir)]),
            command_hint("Query evidence memory", ["async-research", "evidence-memory", "query", str(ops_dir)]),
        ],
    }
