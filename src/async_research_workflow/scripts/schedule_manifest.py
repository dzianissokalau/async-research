"""Schedule manifest helpers for recurring-job intent in research_ops."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from async_research_workflow.scripts import autonomy_readiness_gate
from async_research_workflow.scripts.decision_log import append_decision


SUCCESS = 0
VALIDATION_FAILED = 2
INVALID_REQUEST = 3
MALFORMED = 4
SCHEMA_VERSION = "1.0"
STATUS_CHOICES = ("enabled", "disabled")
DEFAULT_DISABLED_REASON = "schedule intent only; trigger/install arrives in later slices"
ACTIVE_RUN_STATUSES = {"queued", "starting", "running", "in_progress"}
TERMINAL_RUN_STATUSES = {
    "accepted",
    "blocked",
    "cancelled",
    "canceled",
    "completed",
    "done",
    "error",
    "failed",
    "rejected",
    "skipped",
    "success",
    "succeeded",
}


@dataclass(frozen=True)
class ScheduleSpec:
    job_id: str
    description: str
    cadence: str
    prompt_id: str
    max_runtime_minutes: int
    concurrency_key: str
    concurrency_limit: int = 1


DEFAULT_SCHEDULES = (
    ScheduleSpec(
        job_id="discovery-scout-daily",
        description="Collect candidate ideas and source leads for later planning.",
        cadence="daily",
        prompt_id="discovery_scout",
        max_runtime_minutes=30,
        concurrency_key="discovery",
    ),
    ScheduleSpec(
        job_id="planner-hourly",
        description="Promote eligible ideas into bounded task proposals.",
        cadence="hourly",
        prompt_id="planner",
        max_runtime_minutes=20,
        concurrency_key="planning",
    ),
    ScheduleSpec(
        job_id="worker-loop",
        description="Process one ready worker task when readiness and cost gates allow.",
        cadence="hourly",
        prompt_id="worker",
        max_runtime_minutes=45,
        concurrency_key="worker",
    ),
    ScheduleSpec(
        job_id="primary-reviewer-loop",
        description="Run the primary reviewer for tasks awaiting review.",
        cadence="hourly",
        prompt_id="primary_reviewer",
        max_runtime_minutes=30,
        concurrency_key="review",
    ),
    ScheduleSpec(
        job_id="panel-reviewer-loop",
        description="Run specialist panel reviewers for review-panel work.",
        cadence="hourly",
        prompt_id="panel_reviewer",
        max_runtime_minutes=30,
        concurrency_key="review",
    ),
    ScheduleSpec(
        job_id="weekly-synthesizer",
        description="Summarize accepted outcomes, metrics, and operator state.",
        cadence="weekly",
        prompt_id="synthesizer",
        max_runtime_minutes=45,
        concurrency_key="synthesis",
    ),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_time(value: str | None = None) -> datetime:
    if not value:
        return datetime.now(timezone.utc).replace(microsecond=0)
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(microsecond=0)


def compact_time(value: str | None = None) -> str:
    return parse_time(value).strftime("%Y%m%d-%H%M%S")


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def schedule_path(ops_dir: Path) -> Path:
    return ops_dir / "schedules.json"


def history_path(ops_dir: Path) -> Path:
    return ops_dir / "schedules_history.jsonl"


def rel_path(ops_dir: Path, path: Path) -> str:
    try:
        return str(path.relative_to(ops_dir))
    except ValueError:
        return str(path)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def normalize_text(value: Any) -> str:
    return str(value if value is not None else "").strip()


def normalize_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def active_prompt_versions(ops_dir: Path) -> dict[str, str]:
    manifest = ops_dir / "prompts" / "versions.json"
    if not manifest.exists():
        return {}
    try:
        parsed = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    prompts = parsed.get("prompts")
    if not isinstance(prompts, dict):
        return {}
    versions: dict[str, str] = {}
    for prompt_id, payload in prompts.items():
        if isinstance(payload, dict):
            version = normalize_text(payload.get("active_version"))
            if version:
                versions[str(prompt_id)] = version
    return versions


def prompt_binding(prompt_id: str, prompt_version: str = "") -> dict[str, str]:
    binding = {"prompt_id": prompt_id}
    if prompt_version:
        binding["prompt_version"] = prompt_version
    return binding


def default_manifest(ops_dir: Path, now: str) -> dict[str, Any]:
    versions = active_prompt_versions(ops_dir)
    jobs = []
    for spec in DEFAULT_SCHEDULES:
        jobs.append(
            {
                "job_id": spec.job_id,
                "description": spec.description,
                "status": "disabled",
                "disabled_reason": DEFAULT_DISABLED_REASON,
                "cadence": spec.cadence,
                "timezone": "UTC",
                "prompt_binding": prompt_binding(spec.prompt_id, versions.get(spec.prompt_id, f"{spec.prompt_id}_v1.0")),
                "max_runtime_minutes": spec.max_runtime_minutes,
                "concurrency_key": spec.concurrency_key,
                "concurrency_limit": spec.concurrency_limit,
                "updated_at": now,
                "updated_by": "system",
            }
        )
    return {"schema_version": SCHEMA_VERSION, "jobs": jobs}


def read_manifest(ops_dir: Path) -> tuple[int, dict[str, Any]]:
    path = schedule_path(ops_dir)
    if not path.exists():
        return INVALID_REQUEST, {"ok": False, "reason": "schedule_manifest_missing", "path": str(path), "changed": False}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return MALFORMED, {"ok": False, "reason": "schedule_manifest_malformed", "path": str(path), "error": str(exc), "changed": False}
    except OSError as exc:
        return MALFORMED, {"ok": False, "reason": "schedule_manifest_unreadable", "path": str(path), "error": str(exc), "changed": False}
    if not isinstance(parsed, dict):
        return MALFORMED, {"ok": False, "reason": "schedule_manifest_not_object", "path": str(path), "changed": False}
    return SUCCESS, parsed


def normalize_job(raw: dict[str, Any]) -> dict[str, Any]:
    binding = raw.get("prompt_binding") if isinstance(raw.get("prompt_binding"), dict) else {}
    prompt_id = normalize_text(raw.get("prompt_id") or raw.get("prompt") or binding.get("prompt_id"))
    prompt_version = normalize_text(raw.get("prompt_version") or binding.get("prompt_version"))
    status = normalize_text(raw.get("status")) or "disabled"
    job = {
        "job_id": normalize_text(raw.get("job_id") or raw.get("id") or raw.get("name")),
        "description": normalize_text(raw.get("description")),
        "status": status,
        "disabled_reason": normalize_text(raw.get("disabled_reason")),
        "cadence": normalize_text(raw.get("cadence") or raw.get("schedule")),
        "timezone": normalize_text(raw.get("timezone")) or "UTC",
        "prompt_binding": prompt_binding(prompt_id, prompt_version) if prompt_id else {},
        "max_runtime_minutes": raw.get("max_runtime_minutes"),
        "concurrency_key": normalize_text(raw.get("concurrency_key") or raw.get("concurrency_group")),
        "concurrency_limit": raw.get("concurrency_limit"),
        "updated_at": normalize_text(raw.get("updated_at")),
        "updated_by": normalize_text(raw.get("updated_by")),
    }
    return job


def validate_manifest_payload(payload: dict[str, Any], ops_dir: Path | None = None) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    jobs = payload.get("jobs")
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append({"field": "schema_version", "reason": "unsupported_schema_version", "expected": SCHEMA_VERSION})
    if not isinstance(jobs, list):
        errors.append({"field": "jobs", "reason": "required_list_missing"})
        jobs = []
    seen: set[str] = set()
    prompt_versions = active_prompt_versions(ops_dir) if ops_dir is not None else {}
    normalized_jobs = [normalize_job(job) for job in jobs if isinstance(job, dict)]
    for index, job in enumerate(normalized_jobs):
        prefix = f"jobs[{index}]"
        job_id = job["job_id"]
        if not job_id:
            errors.append({"field": f"{prefix}.job_id", "reason": "required_field_missing"})
        elif job_id in seen:
            errors.append({"field": f"{prefix}.job_id", "reason": "duplicate_job_id", "job_id": job_id})
        seen.add(job_id)
        if job["status"] not in STATUS_CHOICES:
            errors.append({"field": f"{prefix}.status", "reason": "unsupported_status", "expected": list(STATUS_CHOICES)})
        if not job["cadence"]:
            errors.append({"field": f"{prefix}.cadence", "reason": "required_field_missing"})
        prompt_id = normalize_text(job.get("prompt_binding", {}).get("prompt_id"))
        if not prompt_id:
            errors.append({"field": f"{prefix}.prompt_binding.prompt_id", "reason": "required_field_missing"})
        elif prompt_versions and prompt_id not in prompt_versions:
            errors.append({"field": f"{prefix}.prompt_binding.prompt_id", "reason": "unknown_prompt_id", "prompt_id": prompt_id})
        if not prompt_versions:
            warnings.append({"field": f"{prefix}.prompt_binding", "reason": "prompt_library_not_initialized"})
        max_runtime = normalize_int(job["max_runtime_minutes"], -1)
        if max_runtime < 1 or max_runtime > 1440:
            errors.append({"field": f"{prefix}.max_runtime_minutes", "reason": "must_be_between_1_and_1440"})
        concurrency_limit = normalize_int(job["concurrency_limit"], -1)
        if not job["concurrency_key"]:
            errors.append({"field": f"{prefix}.concurrency_key", "reason": "required_field_missing"})
        if concurrency_limit < 1 or concurrency_limit > 20:
            errors.append({"field": f"{prefix}.concurrency_limit", "reason": "must_be_between_1_and_20"})
        if job["status"] == "disabled" and not job["disabled_reason"]:
            warnings.append({"field": f"{prefix}.disabled_reason", "reason": "disabled_without_reason", "job_id": job_id})
    if len(normalized_jobs) != len(jobs):
        errors.append({"field": "jobs", "reason": "job_entries_must_be_objects"})
    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "job_count": len(normalized_jobs),
        "enabled_count": sum(1 for job in normalized_jobs if job["status"] == "enabled"),
        "disabled_count": sum(1 for job in normalized_jobs if job["status"] == "disabled"),
    }


def summary(jobs: list[dict[str, Any]], validation: dict[str, Any]) -> dict[str, Any]:
    return {
        "job_count": len(jobs),
        "enabled_count": sum(1 for job in jobs if job.get("status") == "enabled"),
        "disabled_count": sum(1 for job in jobs if job.get("status") == "disabled"),
        "invalid_count": len(validation.get("errors", [])),
    }


def read_history(ops_dir: Path, limit: int = 20) -> list[dict[str, Any]]:
    path = history_path(ops_dir)
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            rows.append(parsed)
    return rows[-limit:]


def append_schedule_decision(ops_dir: Path, job_id: str, action: str, reason: str, author: str) -> None:
    append_decision(
        ops_dir / "decisions.md",
        {
            "date": utc_now(),
            "item_id": f"schedule:{job_id}",
            "decision": "acknowledge",
            "reason": f"schedule_{action}: {reason}",
            "approver": author,
            "related_artifacts": "schedules.json",
        },
    )


def append_history(ops_dir: Path, *, job_id: str, action: str, reason: str, author: str, now: str, validation: dict[str, Any]) -> dict[str, Any]:
    row = {
        "timestamp": now,
        "action": action,
        "job_id": job_id,
        "reason": reason,
        "author": author,
        "path": "schedules.json",
        "validation_ok": bool(validation.get("ok")),
    }
    append_jsonl(history_path(ops_dir), row)
    return row


def schedule_snapshot(ops_dir: Path) -> dict[str, Any]:
    path = schedule_path(ops_dir)
    code, payload = read_manifest(ops_dir)
    if code != SUCCESS:
        return {
            "available": False,
            "status": "unavailable",
            "path": str(path),
            "history_path": str(history_path(ops_dir)),
            "jobs": [],
            "summary": {"job_count": 0, "enabled_count": 0, "disabled_count": 0, "invalid_count": 0},
            "validation": payload,
            "history": read_history(ops_dir),
            "warnings": [{"severity": "warning", "reason": payload.get("reason"), "message": "schedule manifest is not available", "path": str(path)}],
        }
    raw_jobs = payload.get("jobs") if isinstance(payload.get("jobs"), list) else []
    jobs = [normalize_job(job) for job in raw_jobs if isinstance(job, dict)]
    validation = validate_manifest_payload(payload, ops_dir)
    return {
        "available": True,
        "status": "available" if validation["ok"] else "invalid",
        "path": str(path),
        "history_path": str(history_path(ops_dir)),
        "schema_version": payload.get("schema_version"),
        "jobs": jobs,
        "summary": summary(jobs, validation),
        "validation": validation,
        "history": read_history(ops_dir),
        "warnings": validation.get("warnings", []),
    }


def init_manifest(ops_dir: Path, *, force: bool = False, now: str | None = None) -> tuple[int, dict[str, Any]]:
    if not ops_dir.is_dir():
        return INVALID_REQUEST, {
            "ok": False,
            "reason": "ops_dir_missing",
            "message": "Initialize research_ops before creating the schedule manifest.",
            "changed": False,
            "read_only": True,
        }
    path = schedule_path(ops_dir)
    timestamp = now or utc_now()
    if path.exists() and not force:
        snapshot = schedule_snapshot(ops_dir)
        return SUCCESS, {
            "ok": True,
            "action": "schedule_manifest_exists",
            "changed": False,
            "read_only": True,
            "path": str(path),
            "schedule": snapshot,
        }
    manifest = default_manifest(ops_dir, timestamp)
    validation = validate_manifest_payload(manifest, ops_dir)
    atomic_write_json(path, manifest)
    history = append_history(
        ops_dir,
        job_id="*",
        action="initialized",
        reason="schedule manifest initialized",
        author="system",
        now=timestamp,
        validation=validation,
    )
    append_schedule_decision(ops_dir, "*", "initialized", "schedule manifest initialized", "system")
    return SUCCESS, {
        "ok": True,
        "action": "schedule_manifest_initialized",
        "changed": True,
        "read_only": False,
        "path": str(path),
        "manifest": manifest,
        "validation": validation,
        "history": history,
    }


def write_manifest_with_history(
    ops_dir: Path,
    manifest: dict[str, Any],
    *,
    job_id: str,
    action: str,
    reason: str,
    author: str,
    now: str | None = None,
) -> tuple[int, dict[str, Any]]:
    timestamp = now or utc_now()
    validation = validate_manifest_payload(manifest, ops_dir)
    if not validation["ok"]:
        return VALIDATION_FAILED, {
            "ok": False,
            "reason": "schedule_validation_failed",
            "changed": False,
            "read_only": True,
            "validation": validation,
        }
    atomic_write_json(schedule_path(ops_dir), manifest)
    history = append_history(ops_dir, job_id=job_id, action=action, reason=reason, author=author, now=timestamp, validation=validation)
    append_schedule_decision(ops_dir, job_id, action, reason, author)
    return SUCCESS, {
        "ok": True,
        "action": f"schedule_{action}",
        "changed": True,
        "read_only": False,
        "job_id": job_id,
        "path": str(schedule_path(ops_dir)),
        "manifest": manifest,
        "validation": validation,
        "history": history,
    }


def find_job(manifest: dict[str, Any], job_id: str) -> tuple[list[dict[str, Any]], int | None]:
    jobs = manifest.setdefault("jobs", [])
    if not isinstance(jobs, list):
        manifest["jobs"] = []
        jobs = manifest["jobs"]
    for index, job in enumerate(jobs):
        if isinstance(job, dict) and normalize_job(job)["job_id"] == job_id:
            return jobs, index
    return jobs, None


def upsert_schedule(
    ops_dir: Path,
    job_id: str,
    *,
    description: str,
    cadence: str,
    prompt_id: str,
    prompt_version: str = "",
    max_runtime_minutes: int,
    concurrency_key: str,
    concurrency_limit: int,
    status: str = "disabled",
    disabled_reason: str = "",
    reason: str,
    author: str,
    now: str | None = None,
) -> tuple[int, dict[str, Any]]:
    if not job_id:
        return INVALID_REQUEST, {"ok": False, "reason": "job_id_required", "changed": False}
    code, manifest = read_manifest(ops_dir)
    if code != SUCCESS:
        init_code, init_payload = init_manifest(ops_dir, now=now)
        if init_code != SUCCESS:
            return init_code, init_payload
        manifest = init_payload["manifest"]
    timestamp = now or utc_now()
    if not prompt_version:
        prompt_version = active_prompt_versions(ops_dir).get(prompt_id, "")
    if status == "disabled" and not disabled_reason:
        disabled_reason = DEFAULT_DISABLED_REASON
    jobs, index = find_job(manifest, job_id)
    job = {
        "job_id": job_id,
        "description": description,
        "status": status,
        "disabled_reason": disabled_reason if status == "disabled" else "",
        "cadence": cadence,
        "timezone": "UTC",
        "prompt_binding": prompt_binding(prompt_id, prompt_version),
        "max_runtime_minutes": int(max_runtime_minutes),
        "concurrency_key": concurrency_key,
        "concurrency_limit": int(concurrency_limit),
        "updated_at": timestamp,
        "updated_by": author,
    }
    if index is None:
        jobs.append(job)
        action = "created"
    else:
        jobs[index] = job
        action = "updated"
    return write_manifest_with_history(ops_dir, manifest, job_id=job_id, action=action, reason=reason, author=author, now=timestamp)


def set_status(
    ops_dir: Path,
    job_id: str,
    status: str,
    *,
    reason: str,
    author: str,
    disabled_reason: str = "",
    now: str | None = None,
) -> tuple[int, dict[str, Any]]:
    if status not in STATUS_CHOICES:
        return INVALID_REQUEST, {"ok": False, "reason": "unsupported_status", "changed": False, "allowed": list(STATUS_CHOICES)}
    code, manifest = read_manifest(ops_dir)
    if code != SUCCESS:
        return code, manifest
    jobs, index = find_job(manifest, job_id)
    if index is None:
        return INVALID_REQUEST, {"ok": False, "reason": "unknown_job", "job_id": job_id, "changed": False}
    timestamp = now or utc_now()
    job = normalize_job(jobs[index])
    job["status"] = status
    job["disabled_reason"] = disabled_reason if status == "disabled" else ""
    job["updated_at"] = timestamp
    job["updated_by"] = author
    jobs[index] = job
    return write_manifest_with_history(ops_dir, manifest, job_id=job_id, action=status, reason=reason, author=author, now=timestamp)


def validate_schedule(ops_dir: Path) -> tuple[int, dict[str, Any]]:
    code, manifest = read_manifest(ops_dir)
    if code != SUCCESS:
        return code, manifest
    validation = validate_manifest_payload(manifest, ops_dir)
    return (
        SUCCESS if validation["ok"] else VALIDATION_FAILED,
        {
            "ok": validation["ok"],
            "action": "schedule_manifest_validated",
            "changed": False,
            "read_only": True,
            "path": str(schedule_path(ops_dir)),
            "validation": validation,
            "summary": summary([normalize_job(job) for job in manifest.get("jobs", []) if isinstance(job, dict)], validation),
        },
    )


def list_schedules(ops_dir: Path) -> tuple[int, dict[str, Any]]:
    snapshot = schedule_snapshot(ops_dir)
    payload = dict(snapshot)
    payload.update({"ok": snapshot.get("available", False), "action": "schedule_manifest_listed", "changed": False, "read_only": True})
    return SUCCESS if snapshot.get("available") else INVALID_REQUEST, payload


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-").lower()
    return slug or "job"


def preview_run_id(job_id: str, now: str | None = None) -> str:
    return f"local-{compact_time(now)}-{safe_slug(job_id)}"


def command_string(argv: list[str]) -> str:
    return shlex.join(argv)


def jobs_by_id(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw_jobs = manifest.get("jobs") if isinstance(manifest.get("jobs"), list) else []
    rows: dict[str, dict[str, Any]] = {}
    for raw in raw_jobs:
        if isinstance(raw, dict):
            job = normalize_job(raw)
            if job["job_id"]:
                rows[job["job_id"]] = job
    return rows


def prompt_preview(ops_dir: Path, job: dict[str, Any]) -> dict[str, Any]:
    binding = job.get("prompt_binding") if isinstance(job.get("prompt_binding"), dict) else {}
    prompt_id = normalize_text(binding.get("prompt_id"))
    prompt_version = normalize_text(binding.get("prompt_version"))
    path = ops_dir / "prompts" / f"{prompt_id}.md" if prompt_id else ops_dir / "prompts"
    return {
        "prompt_id": prompt_id,
        "prompt_version": prompt_version,
        "prompt_path": str(path),
        "prompt_exists": bool(prompt_id and path.exists()),
    }


def planned_execution(ops_dir: Path, job: dict[str, Any], prompt: dict[str, Any], run_id: str) -> dict[str, Any]:
    run_artifact_dir = ops_dir / "run_artifacts" / run_id
    return {
        "runner": "codex_exec",
        "cwd": str(Path.cwd()),
        "ops_dir": str(ops_dir),
        "job_id": job["job_id"],
        "run_id": run_id,
        "run_artifact_dir": str(run_artifact_dir),
        "prompt_path": prompt["prompt_path"],
        "prompt_version": prompt.get("prompt_version") or "",
        "max_runtime_minutes": normalize_int(job.get("max_runtime_minutes"), 0),
        "concurrency_key": normalize_text(job.get("concurrency_key")),
        "concurrency_limit": normalize_int(job.get("concurrency_limit"), 1),
    }


def planned_command(ops_dir: Path, job: dict[str, Any], prompt: dict[str, Any], run_id: str) -> list[str]:
    execution = planned_execution(ops_dir, job, prompt, run_id)
    prompt_text = (
        f"Run schedule job {job['job_id']} for {ops_dir}. "
        f"Use prompt file {prompt['prompt_path']} at version {prompt.get('prompt_version') or 'unavailable'}. "
        f"Respect max_runtime_minutes={execution['max_runtime_minutes']} and concurrency_key={execution['concurrency_key']}. "
        f"Write run artifacts under {execution['run_artifact_dir']}."
    )
    return ["codex", "exec", "--json", prompt_text]


def is_active_run(payload: dict[str, Any]) -> bool:
    status = normalize_text(payload.get("status")).lower()
    if normalize_text(payload.get("finished_at")):
        return False
    if status in TERMINAL_RUN_STATUSES:
        return False
    if status in ACTIVE_RUN_STATUSES:
        return True
    return bool(status or normalize_text(payload.get("started_at")))


def concurrency_snapshot(ops_dir: Path, job: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    run_artifacts = ops_dir / "run_artifacts"
    concurrency_key = normalize_text(job.get("concurrency_key"))
    concurrency_limit = normalize_int(job.get("concurrency_limit"), 1)
    active_runs: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    schedule_jobs = jobs_by_id(manifest)
    if run_artifacts.exists():
        for run_dir in sorted(path for path in run_artifacts.iterdir() if path.is_dir()):
            run_json = run_dir / "run.json"
            if not run_json.exists():
                continue
            try:
                parsed = json.loads(run_json.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                warnings.append({"path": str(run_json), "reason": "run_json_unreadable", "message": str(exc)})
                continue
            if not isinstance(parsed, dict) or not is_active_run(parsed):
                continue
            run_job_id = normalize_text(parsed.get("job_id"))
            run_concurrency_key = normalize_text(parsed.get("concurrency_key"))
            if not run_concurrency_key and run_job_id in schedule_jobs:
                run_concurrency_key = normalize_text(schedule_jobs[run_job_id].get("concurrency_key"))
            if run_concurrency_key != concurrency_key:
                continue
            active_runs.append(
                {
                    "run_id": normalize_text(parsed.get("run_id")) or run_dir.name,
                    "run_dir": str(run_dir),
                    "job_id": run_job_id or "unavailable",
                    "status": normalize_text(parsed.get("status")) or "unknown",
                    "started_at": normalize_text(parsed.get("started_at")) or "unavailable",
                }
            )
    active_count = len(active_runs)
    return {
        "ok": active_count < concurrency_limit,
        "path": str(run_artifacts),
        "concurrency_key": concurrency_key,
        "concurrency_limit": concurrency_limit,
        "active_count": active_count,
        "active_runs": active_runs,
        "warnings": warnings,
    }


def readiness_snapshot(ops_dir: Path, now: str | None = None) -> dict[str, Any]:
    argv = [str(ops_dir), "--dry-run", "--no-daily-status"]
    if now:
        argv.extend(["--now", now])
    try:
        args = autonomy_readiness_gate.parse_args(argv)
        report, exit_code = autonomy_readiness_gate.build_gate_report(args)
    except Exception as exc:
        return {
            "checked": True,
            "ok": False,
            "exit_code": INVALID_REQUEST,
            "reason": "readiness_check_failed",
            "error": str(exc),
            "warnings": [],
            "blockers": [
                {
                    "severity": "error",
                    "check": "readiness_check_failed",
                    "message": str(exc),
                    "blocking": True,
                }
            ],
        }
    return {
        "checked": True,
        "ok": exit_code in {autonomy_readiness_gate.SUCCESS, autonomy_readiness_gate.WARNINGS},
        "exit_code": exit_code,
        "decision": report.get("decision"),
        "scheduler_action": report.get("scheduler_action"),
        "warning_count": len(report.get("warnings", [])),
        "blocker_count": len(report.get("blockers", [])),
        "warnings": report.get("warnings", []),
        "blockers": report.get("blockers", []),
    }


def skipped_readiness(reason: str) -> dict[str, Any]:
    return {
        "checked": False,
        "ok": False,
        "reason": reason,
        "warnings": [],
        "blockers": [],
    }


def blocker(check: str, message: str, details: Any = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "severity": "error",
        "check": check,
        "message": message,
        "blocking": True,
    }
    if details is not None:
        payload["details"] = details
    return payload


def trigger_dry_run(ops_dir: Path, job_id: str, *, now: str | None = None) -> tuple[int, dict[str, Any]]:
    if not ops_dir.is_dir():
        return INVALID_REQUEST, {
            "ok": False,
            "action": "trigger_now_dry_run",
            "reason": "ops_dir_missing",
            "message": "Initialize research_ops before previewing a trigger.",
            "would_run": False,
            "blocked": True,
            "no_process_started": True,
            "changed": False,
            "read_only": True,
        }
    code, manifest = read_manifest(ops_dir)
    if code != SUCCESS:
        payload = dict(manifest)
        payload.update(
            {
                "action": "trigger_now_dry_run",
                "would_run": False,
                "blocked": True,
                "no_process_started": True,
                "read_only": True,
                "changed": False,
            }
        )
        return code, payload
    validation = validate_manifest_payload(manifest, ops_dir)
    if not validation["ok"]:
        return VALIDATION_FAILED, {
            "ok": False,
            "action": "trigger_now_dry_run",
            "reason": "schedule_validation_failed",
            "message": "Fix schedule validation errors before previewing a trigger.",
            "validation": validation,
            "would_run": False,
            "blocked": True,
            "no_process_started": True,
            "changed": False,
            "read_only": True,
        }
    jobs = jobs_by_id(manifest)
    job = jobs.get(job_id)
    if job is None:
        return INVALID_REQUEST, {
            "ok": False,
            "action": "trigger_now_dry_run",
            "reason": "unknown_job",
            "message": f"Unknown schedule job: {job_id}",
            "job_id": job_id,
            "would_run": False,
            "blocked": True,
            "no_process_started": True,
            "changed": False,
            "read_only": True,
        }

    try:
        run_id = preview_run_id(job_id, now)
    except ValueError as exc:
        return INVALID_REQUEST, {
            "ok": False,
            "action": "trigger_now_dry_run",
            "reason": "invalid_now",
            "message": "Use an ISO-8601 timestamp for --now.",
            "error": str(exc),
            "job_id": job_id,
            "would_run": False,
            "blocked": True,
            "no_process_started": True,
            "changed": False,
            "read_only": True,
        }
    prompt = prompt_preview(ops_dir, job)
    execution = planned_execution(ops_dir, job, prompt, run_id)
    command_argv = planned_command(ops_dir, job, prompt, run_id)
    blocks: list[dict[str, Any]] = []
    warnings = list(validation.get("warnings", []))
    if job.get("status") != "enabled":
        blocks.append(blocker("schedule_disabled", f"{job_id} is disabled and cannot be triggered.", {"status": job.get("status")}))
    if not prompt["prompt_exists"]:
        blocks.append(blocker("prompt_file_missing", "The bound prompt file is missing.", prompt))

    concurrency = concurrency_snapshot(ops_dir, job, manifest)
    warnings.extend(concurrency.get("warnings", []))
    if not concurrency["ok"]:
        blocks.append(
            blocker(
                "concurrency_limit_reached",
                f"Concurrency group {concurrency['concurrency_key']} already has {concurrency['active_count']} active run(s).",
                concurrency,
            )
        )

    readiness = skipped_readiness("preliminary_trigger_checks_failed")
    if not blocks:
        readiness = readiness_snapshot(ops_dir, now=now)
        if not readiness["ok"]:
            blocks.append(blocker("readiness_blocked", "Readiness check says expensive workers should not start.", readiness))

    would_run = not blocks
    payload = {
        "ok": would_run,
        "action": "trigger_now_dry_run",
        "reason": None if would_run else "trigger_blocked",
        "changed": False,
        "read_only": True,
        "job_id": job_id,
        "job": job,
        "would_run": would_run,
        "blocked": bool(blocks),
        "blockers": blocks,
        "warnings": warnings,
        "run_id": run_id,
        "run_artifact_dir": str(ops_dir / "run_artifacts" / run_id),
        "prompt": prompt,
        "readiness": readiness,
        "concurrency": concurrency,
        "planned_execution": execution,
        "planned_command_argv": command_argv,
        "planned_command": command_string(command_argv),
        "no_process_started": True,
        "next_step": "Slice 10 can execute this preview when trigger-now execution lands." if would_run else "Resolve the trigger blockers, then rerun the dry run.",
    }
    return SUCCESS if would_run else VALIDATION_FAILED, payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage research_ops schedule intent manifests.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    init = subparsers.add_parser("init", help="Create research_ops/schedules.json with default recurring-job intent.")
    init.add_argument("ops_dir", type=Path)
    init.add_argument("--force", action="store_true", help="Replace an existing schedule manifest.")
    init.add_argument("--now", help="Override the initialization timestamp.")
    list_cmd = subparsers.add_parser("list", help="List schedule jobs and validation state.")
    list_cmd.add_argument("ops_dir", type=Path)
    validate = subparsers.add_parser("validate", help="Validate research_ops/schedules.json.")
    validate.add_argument("ops_dir", type=Path)
    upsert = subparsers.add_parser("upsert", help="Create or update one schedule job.")
    upsert.add_argument("ops_dir", type=Path)
    upsert.add_argument("job_id")
    upsert.add_argument("--description", required=True)
    upsert.add_argument("--cadence", required=True)
    upsert.add_argument("--prompt-id", required=True)
    upsert.add_argument("--prompt-version", default="")
    upsert.add_argument("--max-runtime-minutes", type=int, required=True)
    upsert.add_argument("--concurrency-key", required=True)
    upsert.add_argument("--concurrency-limit", type=int, default=1)
    upsert.add_argument("--status", choices=STATUS_CHOICES, default="disabled")
    upsert.add_argument("--disabled-reason", default="")
    upsert.add_argument("--message", required=True)
    upsert.add_argument("--author", default="human")
    upsert.add_argument("--now")
    set_status_parser = subparsers.add_parser("set-status", help="Enable or disable schedule intent for one job.")
    set_status_parser.add_argument("ops_dir", type=Path)
    set_status_parser.add_argument("job_id")
    set_status_parser.add_argument("--status", choices=STATUS_CHOICES, required=True)
    set_status_parser.add_argument("--message", required=True)
    set_status_parser.add_argument("--author", default="human")
    set_status_parser.add_argument("--disabled-reason", default="")
    set_status_parser.add_argument("--now")
    trigger = subparsers.add_parser("trigger-dry-run", help="Preview one trigger-now run without launching a process.")
    trigger.add_argument("ops_dir", type=Path)
    trigger.add_argument("job_id")
    trigger.add_argument("--now", help="Override trigger preview timestamp.")
    args = parser.parse_args(argv)
    if args.command == "init":
        code, payload = init_manifest(args.ops_dir, force=args.force, now=args.now)
    elif args.command == "list":
        code, payload = list_schedules(args.ops_dir)
    elif args.command == "validate":
        code, payload = validate_schedule(args.ops_dir)
    elif args.command == "upsert":
        code, payload = upsert_schedule(
            args.ops_dir,
            args.job_id,
            description=args.description,
            cadence=args.cadence,
            prompt_id=args.prompt_id,
            prompt_version=args.prompt_version,
            max_runtime_minutes=args.max_runtime_minutes,
            concurrency_key=args.concurrency_key,
            concurrency_limit=args.concurrency_limit,
            status=args.status,
            disabled_reason=args.disabled_reason,
            reason=args.message,
            author=args.author,
            now=args.now,
        )
    elif args.command == "set-status":
        code, payload = set_status(
            args.ops_dir,
            args.job_id,
            args.status,
            reason=args.message,
            author=args.author,
            disabled_reason=args.disabled_reason,
            now=args.now,
        )
    elif args.command == "trigger-dry-run":
        code, payload = trigger_dry_run(args.ops_dir, args.job_id, now=args.now)
    else:
        code, payload = INVALID_REQUEST, {"ok": False, "reason": "unknown_command"}
    print_json(payload)
    return int(code)


if __name__ == "__main__":
    raise SystemExit(main())
