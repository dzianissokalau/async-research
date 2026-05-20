#!/usr/bin/env python3
"""Assess whether a research_ops workspace needs scalable state support."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from typing import Any


SUCCESS = 0
INVALID = 4


DEFAULT_MAX_TASK_STATUSES = 250
DEFAULT_MAX_RUNTIME_LEDGER_BYTES = 10_000_000
DEFAULT_MAX_EVAL_CASES = 500
DEFAULT_MAX_DASHBOARD_MS = 2000.0
DEFAULT_MAX_STALE_LOCKS = 0
DEFAULT_STALE_LOCK_MINUTES = 60.0

METRIC_SOURCES = {
    "task_status_count": "count of research_ops/tasks/*/status.json",
    "task_dir_count": "unique task directories containing status.json",
    "locked_task_count": "count of research_ops/tasks/*/LOCK directories",
    "stale_lock_count": "task LOCK directories older than stale_lock_minutes",
    "runtime_trace_count": "non-empty rows in research_ops/runtime/traces.jsonl",
    "runtime_evidence_object_count": "non-empty rows in research_ops/runtime/evidence_objects.jsonl",
    "trace_ledger_bytes": "file size of research_ops/runtime/traces.jsonl",
    "evidence_ledger_bytes": "file size of research_ops/runtime/evidence_objects.jsonl",
    "runtime_ledger_bytes": "sum of runtime trace and evidence ledger bytes",
    "parallel_merge_packet_count": "count of research_ops/runtime/parallel_merges/*.md files",
    "dashboard_snapshot_ms": "elapsed time to render the read-only console snapshot",
    "dashboard_snapshot_details": "status, warning count, or error returned by the read-only console snapshot",
    "eval_suite_count": "count of research_ops/evals/*.json suite files",
    "eval_run_count": "count of research_ops/evals/runs/*.json run files",
    "eval_case_count": "case and case_result rows in research_ops/evals JSON artifacts",
    "largest_eval_artifact_bytes": "largest file size among research_ops/evals JSON artifacts",
}


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json_optional(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def jsonl_count(path: Path) -> int:
    if not path.is_file():
        return 0
    try:
        with path.open(encoding="utf-8") as handle:
            return sum(1 for line in handle if line.strip())
    except OSError:
        return 0


def file_size(path: Path) -> int:
    try:
        return path.stat().st_size if path.is_file() else 0
    except OSError:
        return 0


def task_status_paths(ops_dir: Path) -> list[Path]:
    tasks_dir = ops_dir / "tasks"
    if not tasks_dir.is_dir():
        return []
    return sorted(path for path in tasks_dir.glob("*/status.json") if path.is_file())


def task_lock_dirs(ops_dir: Path) -> list[Path]:
    tasks_dir = ops_dir / "tasks"
    if not tasks_dir.is_dir():
        return []
    return sorted(path for path in tasks_dir.glob("*/LOCK") if path.is_dir())


def stale_lock_count(lock_dirs: list[Path], *, now: float, stale_minutes: float) -> int:
    stale = 0
    for lock_dir in lock_dirs:
        try:
            age_minutes = (now - lock_dir.stat().st_mtime) / 60
        except OSError:
            continue
        if age_minutes >= stale_minutes:
            stale += 1
    return stale


def eval_case_count(path: Path) -> int:
    payload = load_json_optional(path)
    cases = payload.get("cases") if isinstance(payload, dict) else None
    if isinstance(cases, list):
        return len(cases)
    case_results = payload.get("case_results") if isinstance(payload, dict) else None
    return len(case_results) if isinstance(case_results, list) else 0


def eval_metrics(ops_dir: Path) -> dict[str, Any]:
    evals_dir = ops_dir / "evals"
    run_dir = evals_dir / "runs"
    suite_paths = sorted(path for path in evals_dir.glob("*.json") if path.is_file()) if evals_dir.is_dir() else []
    run_paths = sorted(path for path in run_dir.glob("*.json") if path.is_file()) if run_dir.is_dir() else []
    case_counts = [eval_case_count(path) for path in [*suite_paths, *run_paths]]
    sizes = [file_size(path) for path in [*suite_paths, *run_paths]]
    return {
        "eval_suite_count": len(suite_paths),
        "eval_run_count": len(run_paths),
        "eval_case_count": sum(case_counts),
        "largest_eval_artifact_bytes": max(sizes, default=0),
    }


def dashboard_latency_ms(ops_dir: Path, now_text: str) -> tuple[float | None, dict[str, Any] | None]:
    try:
        from async_research_workflow.console import snapshot

        parsed_now = datetime.fromisoformat(now_text.replace("Z", "+00:00"))
        started = time.perf_counter()
        payload = snapshot.snapshot(ops_dir, now=parsed_now)
        elapsed = round((time.perf_counter() - started) * 1000, 3)
        return elapsed, {
            "status": payload.get("status"),
            "warning_count": len(payload.get("warnings", [])) if isinstance(payload.get("warnings"), list) else 0,
        }
    except Exception as exc:  # pragma: no cover - surfaced in JSON for operators
        return None, {"error": str(exc)}


def collect_metrics(args: argparse.Namespace, now_text: str) -> dict[str, Any]:
    ops_dir = args.ops_dir
    status_paths = task_status_paths(ops_dir)
    lock_dirs = task_lock_dirs(ops_dir)
    runtime_dir = ops_dir / "runtime"
    trace_ledger = runtime_dir / "traces.jsonl"
    evidence_ledger = runtime_dir / "evidence_objects.jsonl"
    dashboard_ms, dashboard_details = dashboard_latency_ms(ops_dir, now_text) if not args.skip_dashboard_latency else (None, None)
    metrics = {
        "task_status_count": len(status_paths),
        "task_dir_count": len({path.parent for path in status_paths}),
        "locked_task_count": len(lock_dirs),
        "stale_lock_count": stale_lock_count(lock_dirs, now=time.time(), stale_minutes=args.stale_lock_minutes),
        "runtime_trace_count": jsonl_count(trace_ledger),
        "runtime_evidence_object_count": jsonl_count(evidence_ledger),
        "trace_ledger_bytes": file_size(trace_ledger),
        "evidence_ledger_bytes": file_size(evidence_ledger),
        "runtime_ledger_bytes": file_size(trace_ledger) + file_size(evidence_ledger),
        "parallel_merge_packet_count": len(list((runtime_dir / "parallel_merges").glob("*.md"))) if (runtime_dir / "parallel_merges").is_dir() else 0,
        "dashboard_snapshot_ms": dashboard_ms,
        "dashboard_snapshot_details": dashboard_details or {},
    }
    metrics.update(eval_metrics(ops_dir))
    return metrics


def finding(reason: str, message: str, observed: Any, threshold: Any) -> dict[str, Any]:
    return {
        "severity": "warning",
        "reason": reason,
        "message": message,
        "observed": observed,
        "threshold": threshold,
    }


def findings_for(metrics: dict[str, Any], args: argparse.Namespace) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if metrics["task_status_count"] > args.max_task_statuses:
        findings.append(finding("task_status_count_high", "task status scans are approaching the file-backed comfort limit", metrics["task_status_count"], args.max_task_statuses))
    if metrics["runtime_ledger_bytes"] > args.max_runtime_ledger_bytes:
        findings.append(finding("runtime_ledger_bytes_high", "runtime ledgers may need summarization or rebuildable indexing", metrics["runtime_ledger_bytes"], args.max_runtime_ledger_bytes))
    if metrics["eval_case_count"] > args.max_eval_cases:
        findings.append(finding("eval_case_count_high", "eval artifacts may need sharding or derived indexes", metrics["eval_case_count"], args.max_eval_cases))
    dashboard_ms = metrics.get("dashboard_snapshot_ms")
    if isinstance(dashboard_ms, (int, float)) and dashboard_ms > args.max_dashboard_ms:
        findings.append(finding("dashboard_latency_high", "dashboard snapshot latency exceeds the configured threshold", dashboard_ms, args.max_dashboard_ms))
    if dashboard_ms is None and not args.skip_dashboard_latency:
        findings.append(finding("dashboard_snapshot_unavailable", "dashboard snapshot timing could not be measured", metrics.get("dashboard_snapshot_details"), "valid read-only console snapshot"))
    if metrics["stale_lock_count"] > args.max_stale_locks:
        findings.append(finding("stale_lock_count_high", "stale task locks indicate concurrency friction", metrics["stale_lock_count"], args.max_stale_locks))
    return findings


def decision_for(findings: list[dict[str, Any]], metrics: dict[str, Any], args: argparse.Namespace) -> str:
    if not findings:
        return "repo_files_sufficient"
    severe_scale = (
        metrics["task_status_count"] > args.max_task_statuses * 10
        or metrics["runtime_ledger_bytes"] > args.max_runtime_ledger_bytes * 10
        or metrics["eval_case_count"] > args.max_eval_cases * 10
    )
    if severe_scale:
        return "external_queue_or_read_model_needs_human_decision"
    return "optional_rebuildable_index_cache_candidate"


def assess(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    if not args.ops_dir.is_dir():
        return INVALID, {
            "ok": False,
            "action": "scaling_assessment",
            "reason": "ops_dir_missing",
            "ops_dir": str(args.ops_dir),
            "read_only": True,
            "changed": False,
            "errors": [{"reason": "ops_dir_missing", "message": "research_ops directory does not exist"}],
            "warnings": [],
        }
    now_text = args.now or utc_now()
    metrics = collect_metrics(args, now_text)
    findings = findings_for(metrics, args)
    decision = decision_for(findings, metrics, args)
    return SUCCESS, {
        "ok": True,
        "action": "scaling_assessment",
        "ops_dir": str(args.ops_dir),
        "assessed_at": now_text,
        "read_only": True,
        "changed": False,
        "decision": decision,
        "metrics": metrics,
        "thresholds": {
            "max_task_statuses": args.max_task_statuses,
            "max_runtime_ledger_bytes": args.max_runtime_ledger_bytes,
            "max_eval_cases": args.max_eval_cases,
            "max_dashboard_ms": args.max_dashboard_ms,
            "max_stale_locks": args.max_stale_locks,
            "stale_lock_minutes": args.stale_lock_minutes,
        },
        "backend_options": [
            {"id": "no_backend", "status": "selected" if decision == "repo_files_sufficient" else "available", "repo_first": True},
            {"id": "optional_rebuildable_index_cache", "status": "selected" if decision == "optional_rebuildable_index_cache_candidate" else "available", "repo_first": True},
            {"id": "append_only_event_log", "status": "defer_until_measured_need", "repo_first": True},
            {"id": "external_queue_or_read_model", "status": "human_decision_required", "repo_first": False},
        ],
        "source_of_truth": {
            "durable_audit_record": "research_ops files and task-local locks",
            "derived_values": METRIC_SOURCES,
            "non_negotiable": [
                "unique manual decisions stay in files",
                "backend caches must be rebuildable from research_ops",
                "CLI output must explain every derived value source",
            ],
        },
        "warnings": findings,
        "errors": [],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Assess file-backed scaling friction and backend need.")
    parser.add_argument("ops_dir", type=Path, help="Path to the research_ops workspace.")
    parser.add_argument("--now", help="Override assessment timestamp.")
    parser.add_argument("--max-task-statuses", type=int, default=DEFAULT_MAX_TASK_STATUSES)
    parser.add_argument("--max-runtime-ledger-bytes", type=int, default=DEFAULT_MAX_RUNTIME_LEDGER_BYTES)
    parser.add_argument("--max-eval-cases", type=int, default=DEFAULT_MAX_EVAL_CASES)
    parser.add_argument("--max-dashboard-ms", type=float, default=DEFAULT_MAX_DASHBOARD_MS)
    parser.add_argument("--max-stale-locks", type=int, default=DEFAULT_MAX_STALE_LOCKS)
    parser.add_argument("--stale-lock-minutes", type=float, default=DEFAULT_STALE_LOCK_MINUTES)
    parser.add_argument("--skip-dashboard-latency", action="store_true", help="Skip console snapshot timing.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    code, payload = assess(args)
    print_json(payload)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
