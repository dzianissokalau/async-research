#!/usr/bin/env python3
"""Public workflow orchestration for the canonical post-worker loop."""

from __future__ import annotations

import argparse
import contextlib
import importlib
import io
import json
import os
import shlex
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
import sys
from typing import Any, Iterable, Sequence

from async_research_workflow.console import snapshot as console_snapshot
from async_research_workflow.resources import schema_path
from async_research_workflow.scripts import check_schema_versions, task_lock, validate_transition
from async_research_workflow.scripts.aggregate_reviews import (
    CLAIM_STRENGTH_ORDER,
    REVIEWER_ROLES,
    current_claim_strength,
    read_review,
    required_reviewers,
    review_tier,
    validate_review,
)
from async_research_workflow.scripts.schema_diagnostics import status_schema_diagnostics
from async_research_workflow.scripts.validate_json_artifact import load_json, validate
from async_research_workflow.scripts.validate_result_acceptance import cap_claim_strength, load_result_summary


SUCCESS = 0
VALIDATION_FAILED = 2
INVALID_STATE = 4
READINESS_WARNINGS = 2
REVIEWABLE_STATUSES = {"awaiting_review", "single_review", "panel_review"}
STATUS_SCHEMA = schema_path("task_status.schema.json")


@dataclass(frozen=True)
class WorkflowStep:
    name: str
    command: list[str]
    module_name: str | None
    argv: list[str]
    mutates: bool
    runs_in_dry_run: bool = True
    warning_only_exit_codes: frozenset[int] = frozenset()


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def module_main(module_name: str, argv: Sequence[str]) -> int:
    module = importlib.import_module(f"async_research_workflow.scripts.{module_name}")
    return int(module.main(list(argv)))


def run_module_json(module_name: str, argv: Sequence[str]) -> tuple[int, Any, str | None, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = module_main(module_name, argv)
    text = stdout.getvalue().strip()
    parsed: Any = {}
    raw_output: str | None = None
    if text:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = {}
            raw_output = text
    return code, parsed, raw_output, stderr.getvalue().strip()


def command_text(command: Sequence[str]) -> str:
    return " ".join(shlex.quote(part) for part in command)


def command_hint(label: str, argv: Sequence[str], reason: str, priority: int = 1) -> dict[str, Any]:
    return {
        "label": label,
        "command": command_text(argv),
        "reason": reason,
        "priority": priority,
    }


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise


def iso_after_minutes(minutes: float) -> str:
    seconds = max(1, int(minutes * 60))
    return (task_lock.utc_now() + timedelta(seconds=seconds)).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def task_lock_owner_arg(lock_state: dict[str, Any]) -> list[str]:
    owner = lock_state.get("owner")
    owner_name = owner.get("owner") if isinstance(owner, dict) else None
    return ["--owner", owner_name] if isinstance(owner_name, str) and owner_name else []


def transitioned_status(status: dict[str, Any], next_status: str, reason: str, **updates: Any) -> dict[str, Any]:
    updated = dict(status)
    updated.update(
        {
            "previous_status": status.get("status"),
            "status": next_status,
            "last_transition_reason": reason,
            "updated_at": task_lock.iso_now(),
        }
    )
    updated.update(updates)
    return updated


def worker_started_status(status: dict[str, Any], owner: str, stale_minutes: float) -> dict[str, Any]:
    return transitioned_status(
        status,
        "in_progress",
        "workflow_worker_started",
        lock_owner=owner,
        lock_expires_at=iso_after_minutes(stale_minutes),
    )


def worker_completed_status(status: dict[str, Any]) -> dict[str, Any]:
    return transitioned_status(
        status,
        "awaiting_review",
        "workflow_worker_completed_output",
        lock_owner=None,
        lock_expires_at=None,
    )


def inferred_ops_dir_for_task(task_dir: Path) -> Path | None:
    if task_dir.parent.name == "tasks":
        return task_dir.parent.parent
    return None


def normalized_path(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def task_workspace_error(
    task_dir: Path,
    ops_dir: Path | None,
    reason: str,
    action: str = "workflow_advance_refused",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": False,
        "action": action,
        "reason": reason,
        "task_dir": str(task_dir),
        "next_step": "pass a task directory directly under the matching research_ops/tasks/ folder",
    }
    if ops_dir is not None:
        payload["ops_dir"] = str(ops_dir)
    return payload


def resolve_task_ops_dir(
    task_dir: Path,
    explicit_ops_dir: Path | None = None,
    action: str = "workflow_advance_refused",
) -> tuple[Path | None, dict[str, Any] | None]:
    inferred_ops_dir = inferred_ops_dir_for_task(task_dir)
    if explicit_ops_dir is None:
        if inferred_ops_dir is None:
            return None, task_workspace_error(task_dir, None, "task_dir_not_under_tasks", action)
        return inferred_ops_dir, None
    if inferred_ops_dir is None:
        return None, task_workspace_error(task_dir, explicit_ops_dir, "task_dir_not_under_tasks", action)
    if normalized_path(inferred_ops_dir) != normalized_path(explicit_ops_dir):
        return None, task_workspace_error(task_dir, explicit_ops_dir, "task_dir_ops_mismatch", action)
    return explicit_ops_dir, None


def load_status_for_report(task_dir: Path) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    status_path = task_dir / "status.json"
    base = {
        "path": str(status_path),
        "valid": False,
        "reason": "valid",
        "issues": [],
    }
    try:
        payload = json.loads(status_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, {**base, "reason": "status_missing", "issues": [{"path": str(status_path), "message": "status.json is missing"}]}
    except json.JSONDecodeError as exc:
        return None, {**base, "reason": "status_malformed", "issues": [{"path": str(status_path), "message": str(exc)}]}
    except OSError as exc:
        return None, {**base, "reason": "status_read_failed", "issues": [{"path": str(status_path), "message": str(exc)}]}

    if not isinstance(payload, dict):
        return None, {**base, "reason": "status_not_object", "issues": [{"path": str(status_path), "message": "status.json must be an object"}]}

    schema = load_json(STATUS_SCHEMA)
    if not isinstance(schema, dict):
        return payload, {**base, "reason": "status_schema_malformed", "issues": [{"path": str(STATUS_SCHEMA), "message": "schema is not an object"}]}
    errors = [error.to_dict() for error in validate(payload, schema)]
    if errors:
        diagnostics = status_schema_diagnostics(payload, errors)
        return payload, {**base, "reason": "status_schema_validation_failed", "issues": errors, "diagnostics": diagnostics}
    return payload, {**base, "valid": True}


def transition_report(status: dict[str, Any] | None, status_path: Path) -> dict[str, Any]:
    if status is None:
        return {
            "valid": False,
            "exit_code": INVALID_STATE,
            "reason": "status_unavailable",
            "previous_status": None,
            "status": None,
            "allowed_next_statuses": [],
        }
    decisions_path = validate_transition.infer_decisions_path(status_path)
    code, result = validate_transition.validate_payload(status, decisions_path=decisions_path)
    current_status = status.get("status")
    return {
        "valid": code == validate_transition.SUCCESS,
        "exit_code": code,
        "reason": result.get("reason"),
        "previous_status": status.get("previous_status"),
        "status": current_status,
        "allowed_next_statuses": sorted(validate_transition.ALLOWED.get(current_status, set())) if isinstance(current_status, str) else [],
        "details": result,
    }


def validate_status_for_write(status_path: Path, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    schema = load_json(STATUS_SCHEMA)
    if not isinstance(schema, dict):
        return INVALID_STATE, {
            "valid": False,
            "reason": "status_schema_malformed",
            "issues": [{"path": str(STATUS_SCHEMA), "message": "schema is not an object"}],
        }
    errors = [error.to_dict() for error in validate(payload, schema)]
    if errors:
        return INVALID_STATE, {
            "valid": False,
            "reason": "status_schema_validation_failed",
            "issues": errors,
        }

    decisions_path = validate_transition.infer_decisions_path(status_path)
    code, result = validate_transition.validate_payload(payload, decisions_path=decisions_path)
    if code != validate_transition.SUCCESS:
        return INVALID_STATE, {
            "valid": False,
            "reason": result.get("reason") or "status_transition_validation_failed",
            "transition": result,
        }
    return SUCCESS, {
        "valid": True,
        "reason": "valid",
        "transition": result,
    }


def worker_output_report(task_dir: Path) -> dict[str, Any]:
    path = task_dir / "worker_output.md"
    report: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "is_file": path.is_file(),
        "readable": False,
        "size_bytes": None,
        "non_empty": False,
        "ready_for_review": False,
    }
    if not path.exists() or not path.is_file():
        return report
    try:
        text = path.read_text(encoding="utf-8")
        report["size_bytes"] = path.stat().st_size
    except (OSError, UnicodeDecodeError) as exc:
        report["read_error"] = str(exc)
        return report
    report["readable"] = True
    report["non_empty"] = bool(text.strip())
    report["ready_for_review"] = bool(report["non_empty"])
    return report


def lock_report(task_dir: Path, stale_minutes: float) -> dict[str, Any]:
    stale_seconds = max(1, int(stale_minutes * 60))
    path = task_lock.lock_dir(task_dir)
    locked = path.exists()
    age_seconds = task_lock.lock_age_seconds(task_dir) if locked else None
    stale = task_lock.is_stale(task_dir, stale_seconds) if locked else False
    hint = None
    if locked and stale:
        hint = "lock is stale; inspect the owner before retrying or clearing it"
    elif locked:
        hint = "task is locked; wait for the owner or inspect active work before mutating"
    return {
        "locked": locked,
        "is_directory": path.is_dir() if locked else False,
        "stale": stale,
        "stale_after_minutes": stale_minutes,
        "age_seconds": age_seconds,
        "age_minutes": round(age_seconds / 60, 2) if age_seconds is not None else None,
        "owner": task_lock.load_owner(task_dir) if locked else None,
        "lock_dir": str(path),
        "stale_hint": hint,
    }


def review_files_report(task_dir: Path, status: dict[str, Any] | None) -> dict[str, Any]:
    reviews_dir = task_dir / "reviews"
    tier = review_tier(status or {}) if status is not None else 1
    required = required_reviewers(status or {}, tier) if status is not None else ["primary"]
    by_role: dict[str, dict[str, Any]] = {}
    invalid_reviews: list[dict[str, Any]] = []
    roles = set(REVIEWER_ROLES) | set(required)
    for role in sorted(roles):
        path = reviews_dir / f"{role}.md"
        by_role[role] = {
            "role": role,
            "path": str(path),
            "required": role in required,
            "exists": path.exists(),
            "valid": None,
        }

    for path in sorted(reviews_dir.glob("*.md")) if reviews_dir.exists() else []:
        role = path.stem
        entry = by_role.setdefault(
            role,
            {
                "role": role,
                "path": str(path),
                "required": role in required,
                "exists": True,
                "valid": None,
            },
        )
        entry["exists"] = True
        entry["path"] = str(path)
        try:
            payload = read_review(path)
        except ValueError as exc:
            entry["valid"] = False
            entry["errors"] = [str(exc)]
            invalid_reviews.append({"role": role, "path": str(path), "errors": [str(exc)]})
            continue
        review_role = payload.get("reviewer_role")
        if isinstance(review_role, str) and review_role != role:
            entry.update(
                {
                    "valid": False,
                    "role_mismatch": True,
                    "declared_role": review_role,
                    "message": f"file declares reviewer_role {review_role!r}, so it does not satisfy role {role!r}",
                }
            )
            role = review_role
            entry = by_role.setdefault(
                role,
                {
                    "role": role,
                    "path": str(path),
                    "required": role in required,
                    "exists": True,
                    "valid": None,
                },
            )
        errors = validate_review(path, payload)
        entry.update(
            {
                "role": role,
                "path": str(path),
                "exists": True,
                "valid": not errors,
                "decision": payload.get("decision"),
                "claim_strength": payload.get("claim_strength"),
                "confidence": payload.get("confidence"),
            }
        )
        if errors:
            entry["errors"] = errors
            invalid_reviews.append({"role": role, "path": str(path), "errors": errors})

    missing_required = [role for role in required if by_role.get(role, {}).get("valid") is not True]
    valid_required = [
        role
        for role in required
        if by_role.get(role, {}).get("exists") is True and by_role.get(role, {}).get("valid") is True
    ]
    return {
        "reviews_dir": str(reviews_dir),
        "review_tier": tier,
        "required_reviewers": required,
        "by_role": {role: by_role[role] for role in sorted(by_role)},
        "missing_required_reviews": missing_required,
        "invalid_reviews": invalid_reviews,
        "ready_to_aggregate": not missing_required and not invalid_reviews and len(valid_required) == len(required),
        "aggregate": {
            "markdown_path": str(task_dir / "review_panel" / "aggregate.md"),
            "markdown_exists": (task_dir / "review_panel" / "aggregate.md").exists(),
            "json_path": str(task_dir / "review_panel" / "aggregate.json"),
            "json_exists": (task_dir / "review_panel" / "aggregate.json").exists(),
        },
    }


def human_gate_report(status: dict[str, Any] | None) -> dict[str, Any]:
    if status is None:
        return {"requires_human": False, "reason": None, "opened_at": None, "gate": None}
    gate = status.get("human_gate") if isinstance(status.get("human_gate"), dict) else None
    reason = status.get("human_gate_reason")
    if not reason and gate is not None:
        reason = gate.get("reason") or gate.get("trigger")
    return {
        "requires_human": bool(status.get("requires_human")),
        "reason": reason,
        "opened_at": status.get("human_gate_opened_at"),
        "gate": gate,
    }


def revision_report(status: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "revision_count": None if status is None else status.get("revision_count"),
        "max_revisions": None if status is None else status.get("max_revisions"),
        "revision_limit_hit": False if status is None else status.get("revision_limit_hit"),
    }


def result_report(status: dict[str, Any] | None) -> dict[str, Any]:
    result = status.get("result") if status is not None and isinstance(status.get("result"), dict) else {}
    return {
        "recommendation": result.get("recommendation"),
        "claim_strength": result.get("claim_strength"),
        "claim_strength_stale": result.get("claim_strength_stale"),
        "claim_strength_revalidation_required": result.get("claim_strength_revalidation_required"),
        "claim_strength_revalidation_reason": result.get("claim_strength_revalidation_reason"),
        "claim_strength_revalidated_at": result.get("claim_strength_revalidated_at"),
        "claim_strength_policy": result.get("claim_strength_policy"),
        "revalidation_status": result.get("revalidation_status"),
        "next_recheck_date": result.get("next_recheck_date"),
    }


def claim_strength_preflight_report(
    task_dir: Path,
    status: dict[str, Any] | None,
    reviews: dict[str, Any] | None = None,
    requested_claim_strength: str | None = None,
) -> dict[str, Any]:
    if status is None:
        return {
            "available": False,
            "reason": "status_unavailable",
            "warnings": [],
        }
    summary = load_result_summary(task_dir)
    cap, reasons = cap_claim_strength(summary, None, str(status.get("type") or ""))
    submitted: list[dict[str, Any]] = []
    if requested_claim_strength:
        submitted.append({"role": "requested", "claim_strength": requested_claim_strength})
    elif isinstance(reviews, dict):
        by_role = reviews.get("by_role") if isinstance(reviews.get("by_role"), dict) else {}
        for role, review in by_role.items():
            if isinstance(review, dict) and review.get("valid") is True and review.get("claim_strength") in CLAIM_STRENGTH_ORDER:
                submitted.append({"role": role, "claim_strength": review["claim_strength"]})
    submitted_strengths = [
        str(item["claim_strength"])
        for item in submitted
        if item.get("claim_strength") in CLAIM_STRENGTH_ORDER
    ]
    aggregate_claim_strength = current_claim_strength([{"claim_strength": value} for value in submitted_strengths]) if submitted_strengths else None
    warnings = [
        {
            "role": item["role"],
            "requested_claim_strength": item["claim_strength"],
            "max_claim_strength": cap,
            "reason": "claim_strength_exceeds_cap",
            "message": (
                f"requested claim strength {item['claim_strength']} exceeds current cap {cap}; "
                "lower the review claim strength or add structured/reproducible result artifacts"
            ),
        }
        for item in submitted
        if item.get("claim_strength") in CLAIM_STRENGTH_ORDER
        and CLAIM_STRENGTH_ORDER.index(str(item["claim_strength"])) > CLAIM_STRENGTH_ORDER.index(cap)
    ]
    return {
        "available": True,
        "structured_result_summary_present": summary is not None,
        "max_claim_strength": cap,
        "cap_reasons": reasons,
        "submitted_reviews": submitted,
        "aggregate_claim_strength": aggregate_claim_strength,
        "warnings": warnings,
        "ok": not warnings,
        "next_step": (
            "claim strength is within the current task/artifact cap"
            if not warnings
            else "lower submitted review claim strength or add structured result summary/analysis claim gates before aggregation"
        ),
    }


def next_legal_commands(
    task_dir: Path,
    ops_dir: Path,
    status: dict[str, Any] | None,
    status_validation: dict[str, Any],
    transition: dict[str, Any],
    lock_state: dict[str, Any],
    worker_output: dict[str, Any],
    reviews: dict[str, Any],
) -> list[dict[str, Any]]:
    if status is None or not status_validation.get("valid") or not transition.get("valid"):
        return [
            command_hint(
                "Validate workspace schema",
                ["async-research", "schema-check", str(ops_dir)],
                "status.json is missing, malformed, schema-invalid, or has an invalid transition",
            ),
            command_hint(
                "Run workflow check",
                ["async-research", "workflow", "check", str(ops_dir)],
                "collect the read-only workspace checks before mutating task state",
                priority=2,
            ),
        ]

    current_status = status.get("status")
    if current_status == "in_progress":
        if worker_output.get("ready_for_review"):
            owner_arg = task_lock_owner_arg(lock_state)
            return [
                command_hint(
                    "Dry-run worker completion",
                    ["async-research", "workflow", "worker-complete", str(task_dir), *owner_arg, "--dry-run"],
                    "worker_output.md is ready; validate the in_progress -> awaiting_review transition before writing it",
                ),
                command_hint(
                    "Complete worker task",
                    ["async-research", "workflow", "worker-complete", str(task_dir), *owner_arg],
                    "move the task to awaiting_review and release the task-local lock when present",
                    priority=2,
                ),
            ]
        if lock_state.get("locked") and not lock_state.get("stale"):
            return [
                command_hint(
                    "Run workflow check",
                    ["async-research", "workflow", "check", str(ops_dir)],
                    "task is actively locked and worker_output.md is not ready; wait for the owner before mutating task state",
                )
            ]
        return [
            command_hint(
                "Run workflow check",
                ["async-research", "workflow", "check", str(ops_dir)],
                "worker_output.md must exist and be non-empty before completing worker execution",
            )
        ]

    if lock_state.get("locked") and not lock_state.get("stale"):
        return [
            command_hint(
                "Run workflow check",
                ["async-research", "workflow", "check", str(ops_dir)],
                "task is actively locked; wait for the owner before running mutating task commands",
            )
        ]

    commands: list[dict[str, Any]] = []
    if current_status == "needs_human" or status.get("requires_human") is True:
        commands.append(
            command_hint(
                "Preview human resolution",
                [
                    "async-research",
                    "decision",
                    "resolve-task",
                    str(ops_dir),
                    str(task_dir),
                    "--decision",
                    "resume",
                    "--reason",
                    "<why>",
                    "--approver",
                    "<name>",
                    "--dry-run",
                ],
                "resolve the structured human gate through decisions.md before continuing",
            )
        )
        commands.append(
            command_hint(
                "Resolve human gate",
                [
                    "async-research",
                    "decision",
                    "resolve-task",
                    str(ops_dir),
                    str(task_dir),
                    "--decision",
                    "resume",
                    "--reason",
                    "<why>",
                    "--approver",
                    "<name>",
                ],
                "write the audited decision and move the task to the selected allowed status",
                priority=2,
            )
        )
        return commands

    if current_status in REVIEWABLE_STATUSES:
        if not worker_output.get("ready_for_review"):
            return [
                command_hint(
                    "Run workflow check",
                    ["async-research", "workflow", "check", str(ops_dir)],
                    "worker_output.md must exist and be non-empty before review writes or aggregation",
                )
            ]
        if reviews.get("invalid_reviews"):
            return [
                command_hint(
                    "Run aggregate dry-run",
                    ["async-research", "review", "aggregate", str(task_dir), "--record-review-start", "--dry-run"],
                    "review files are present but at least one is invalid; dry-run aggregation reports the validation errors",
                )
            ]
        missing = reviews.get("missing_required_reviews") or []
        if missing:
            for role in missing:
                commands.append(
                    command_hint(
                        f"Submit {role} review",
                        [
                            "async-research",
                            "review",
                            "submit",
                            str(task_dir),
                            "--role",
                            role,
                            "--decision",
                            "<decision>",
                            "--claim-strength",
                            "<strength>",
                            "--confidence",
                            "<0-1>",
                        ],
                        "write the missing required review with explicit reviewer metadata",
                    )
                )
                commands.append(
                    command_hint(
                        f"Draft {role} review scaffold",
                        ["async-research", "review", "draft", str(task_dir), "--role", role, "--write"],
                        "create a conservative needs_human scaffold when a reviewer needs a safe starting point",
                        priority=2,
                    )
                )
            return commands
        return [
            command_hint(
                "Dry-run workflow advance",
                ["async-research", "workflow", "advance", str(task_dir), "--dry-run"],
                "all required reviews are present; inspect the aggregate and follow-on plan first",
            ),
            command_hint(
                "Advance workflow",
                ["async-research", "workflow", "advance", str(task_dir)],
                "write aggregate/status changes and refresh accepted memory, surfaces, and health",
                priority=2,
            ),
        ]

    if current_status == "needs_revision":
        return [
            command_hint(
                "Inspect revision state",
                ["async-research", "revision", "inspect", str(task_dir)],
                "check the bounded revision counters before sending the task back to workers",
            ),
            command_hint(
                "Request bounded revision",
                ["async-research", "revision", "request", str(task_dir), "--reviewer", "primary"],
                "route the task back to ready_for_worker without hand-editing status.json",
                priority=2,
            ),
        ]

    if current_status == "ready_for_worker":
        return [
            command_hint(
                "Dry-run worker start",
                ["async-research", "workflow", "worker-start", str(task_dir), "--dry-run"],
                "validate the ready_for_worker -> in_progress transition and lock claim before writing it",
            ),
            command_hint(
                "Start worker task",
                ["async-research", "workflow", "worker-start", str(task_dir)],
                "claim the task-local lock and move the task to in_progress before writing worker output",
                priority=2,
            )
        ]

    if current_status == "accepted":
        return [
            command_hint(
                "Refresh derived outcome surfaces",
                ["async-research", "outcomes", "refresh", str(ops_dir)],
                "writes derived delivered-project outcome files for accepted work; task state is unchanged",
            )
        ]

    if current_status == "rejected":
        return [
            command_hint(
                "Inspect rejected outcomes",
                ["async-research", "workflow", "check", str(ops_dir)],
                "rejected tasks are terminal; continue with workspace-level checks and the next task",
            )
        ]

    return [
        command_hint(
            "Run workflow check",
            ["async-research", "workflow", "check", str(ops_dir)],
            "inspect workspace readiness before choosing the next task transition",
        )
    ]


def status_headline(status: dict[str, Any] | None, worker_output: dict[str, Any], reviews: dict[str, Any], lock_state: dict[str, Any]) -> str:
    if status is None:
        return "task status unavailable"
    lock_label = "stale lock" if lock_state.get("stale") else "locked" if lock_state.get("locked") else "unlocked"
    worker_label = "worker output ready" if worker_output.get("ready_for_review") else "worker output missing or empty"
    missing = reviews.get("missing_required_reviews") or []
    review_label = "required reviews present" if not missing else f"missing reviews: {', '.join(missing)}"
    return f"{status.get('id', 'unknown task')} is {status.get('status')} ({lock_label}; {worker_label}; {review_label})"


def workspace_action(
    category: str,
    label: str,
    argv: Sequence[str],
    reason: str,
    priority: int,
    *,
    task: dict[str, Any] | None = None,
    details: dict[str, Any] | None = None,
    mutates: bool = False,
) -> dict[str, Any]:
    action = command_hint(label, argv, reason, priority)
    action.update(
        {
            "category": category,
            "mutates": mutates,
        }
    )
    if task is not None:
        action["task"] = task
    if details is not None:
        action["details"] = details
    return action


def workspace_action_from_command(
    category: str,
    command: dict[str, Any],
    priority: int,
    *,
    task: dict[str, Any] | None = None,
    details: dict[str, Any] | None = None,
    mutates: bool | None = None,
) -> dict[str, Any]:
    action = dict(command)
    action["category"] = category
    action["priority"] = priority
    action["mutates"] = inferred_command_mutates(str(command.get("command", ""))) if mutates is None else mutates
    if task is not None:
        action["task"] = task
    if details is not None:
        action["details"] = details
    return action


def inferred_command_mutates(command: str) -> bool:
    try:
        parts = shlex.split(command)
    except ValueError:
        parts = command.split()
    if "--dry-run" in parts:
        return False
    mutating_prefixes = (
        ("async-research", "review", "submit"),
        ("async-research", "workflow", "advance"),
        ("async-research", "workflow", "worker-start"),
        ("async-research", "workflow", "worker-complete"),
        ("async-research", "decision", "resolve-task"),
        ("async-research", "revision", "request"),
        ("async-research", "accepted", "revalidation"),
        ("async-research", "surface", "update"),
        ("async-research", "outcomes", "refresh"),
    )
    if parts[:3] == ["async-research", "review", "draft"]:
        return "--write" in parts
    return any(tuple(parts[: len(prefix)]) == prefix for prefix in mutating_prefixes)


def task_identity(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": row.get("task_id"),
        "title": row.get("title"),
        "status": row.get("status"),
        "task_dir": row.get("task_dir"),
        "status_path": row.get("status_path"),
    }


def first_task(rows: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [row for row in rows if isinstance(row, dict)]
    if not candidates:
        return None
    return sorted(candidates, key=lambda row: (str(row.get("task_id") or ""), str(row.get("task_dir") or "")))[0]


def task_status_report_for_row(row: dict[str, Any], ops_dir: Path, stale_minutes: float) -> dict[str, Any] | None:
    task_dir_value = row.get("task_dir")
    if not isinstance(task_dir_value, str) or not task_dir_value.strip():
        return None
    task_dir = Path(task_dir_value)
    if not task_dir.exists() or not task_dir.is_dir():
        return None
    return build_status_report(task_dir, ops_dir, stale_minutes)


def lock_state_for_row(row: dict[str, Any], stale_minutes: float) -> dict[str, Any] | None:
    task_dir_value = row.get("task_dir")
    if not isinstance(task_dir_value, str) or not task_dir_value.strip():
        return None
    task_dir = Path(task_dir_value)
    if not task_dir.exists() or not task_dir.is_dir():
        return None
    return lock_report(task_dir, stale_minutes)


def first_status_command(report: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(report, dict):
        return None
    commands = report.get("next_legal_commands")
    if not isinstance(commands, list) or not commands:
        return None
    first = commands[0]
    return first if isinstance(first, dict) else None


def dashboard_warning_count(group: Any) -> int:
    if not isinstance(group, dict):
        return 0
    warnings = group.get("warnings")
    count = len(warnings) if isinstance(warnings, list) else 0
    summary = group.get("summary") if isinstance(group.get("summary"), dict) else {}
    for key in (
        "error_count",
        "warning_count",
        "findings_count",
        "blocked_source_count",
        "stale_source_count",
        "candidate_source_count",
        "needs_review_source_count",
        "governance_error_count",
        "governance_warning_count",
    ):
        value = summary.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            count += max(0, value)
    if group.get("ok") is False or group.get("available") is False:
        count += 1
    return count


def workflow_next_actions(ops_dir: Path, snapshot: dict[str, Any], schema_report: dict[str, Any], stale_minutes: float) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    tasks = snapshot.get("tasks") if isinstance(snapshot.get("tasks"), dict) else {}

    schema_errors = schema_report.get("errors") if isinstance(schema_report.get("errors"), list) else []
    malformed_statuses = tasks.get("malformed_statuses") if isinstance(tasks.get("malformed_statuses"), list) else []
    if schema_errors or malformed_statuses:
        actions.append(
            workspace_action(
                "malformed_state",
                "Validate schema versions",
                ["async-research", "schema-check", str(ops_dir)],
                "repair malformed or schema-invalid workflow state before choosing task work",
                10,
                details={
                    "schema_error_count": len(schema_errors),
                    "malformed_status_count": len(malformed_statuses),
                    "first_schema_error": schema_errors[0] if schema_errors else None,
                    "first_malformed_status": malformed_statuses[0] if malformed_statuses else None,
                },
            )
        )

    human_task = first_task(tasks.get("human", []) if isinstance(tasks.get("human"), list) else [])
    if human_task is not None:
        report = task_status_report_for_row(human_task, ops_dir, stale_minutes)
        command = first_status_command(report)
        if command is not None:
            actions.append(
                workspace_action_from_command(
                    "needs_human",
                    command,
                    20,
                    task=task_identity(human_task),
                    details={"human_gate": report.get("human_gate") if isinstance(report, dict) else None},
                )
            )
        else:
            actions.append(
                workspace_action(
                    "needs_human",
                    "Inspect human-gated task",
                    ["async-research", "workflow", "status", str(human_task.get("task_dir"))],
                    "resolve the highest-priority human gate before starting lower-priority work",
                    20,
                    task=task_identity(human_task),
                )
            )

    all_tasks = tasks.get("all", []) if isinstance(tasks.get("all"), list) else []
    active_lock_tasks = []
    stale_lock_tasks = []
    lock_state_by_task_dir: dict[str, dict[str, Any]] = {}
    for row in all_tasks:
        lock_state = lock_state_for_row(row, stale_minutes)
        if lock_state is None or lock_state.get("locked") is not True:
            continue
        task_dir_key = str(row.get("task_dir") or "")
        lock_state_by_task_dir[task_dir_key] = lock_state
        if lock_state.get("stale") is True:
            stale_lock_tasks.append(row)
        else:
            active_lock_tasks.append(row)
    active_lock = first_task(active_lock_tasks)
    if active_lock is not None:
        lock_state = lock_state_by_task_dir.get(str(active_lock.get("task_dir") or ""), active_lock.get("lock_state"))
        actions.append(
            workspace_action(
                "active_lock",
                "Inspect active task lock",
                ["async-research", "workflow", "status", str(active_lock.get("task_dir"))],
                "an active task lock is present; inspect it before running mutating task commands",
                30,
                task=task_identity(active_lock),
                details={"lock_state": lock_state},
            )
        )

    stale_lock = first_task(stale_lock_tasks)
    if stale_lock is not None:
        lock_state = lock_state_by_task_dir.get(str(stale_lock.get("task_dir") or ""), stale_lock.get("lock_state"))
        actions.append(
            workspace_action(
                "stale_lock",
                "Inspect stale task lock",
                ["async-research", "workflow", "status", str(stale_lock.get("task_dir"))],
                "a stale task lock may block future work; inspect owner and task state before continuing",
                31,
                task=task_identity(stale_lock),
                details={"lock_state": lock_state},
            )
        )

    completion_tasks = [row for row in all_tasks if row.get("status") == "in_progress"]
    for row in sorted(completion_tasks, key=lambda item: (str(item.get("task_id") or ""), str(item.get("task_dir") or ""))):
        report = task_status_report_for_row(row, ops_dir, stale_minutes)
        if not isinstance(report, dict):
            continue
        worker_ready = bool(report.get("worker_output", {}).get("ready_for_review"))
        if not worker_ready:
            continue
        command = first_status_command(report)
        if command is None:
            continue
        actions.append(
            workspace_action_from_command(
                "worker_completion",
                command,
                35,
                task=task_identity(row),
                details={
                    "lock_state": report.get("lock_state"),
                    "worker_output": report.get("worker_output"),
                },
            )
        )
        break

    review_tasks = [row for row in all_tasks if row.get("status") in REVIEWABLE_STATUSES]
    for row in sorted(review_tasks, key=lambda item: (str(item.get("task_id") or ""), str(item.get("task_dir") or ""))):
        report = task_status_report_for_row(row, ops_dir, stale_minutes)
        if not isinstance(report, dict):
            continue
        worker_ready = bool(report.get("worker_output", {}).get("ready_for_review"))
        if not worker_ready:
            continue
        command = first_status_command(report)
        if command is None:
            continue
        actions.append(
            workspace_action_from_command(
                "ready_for_review",
                command,
                40,
                task=task_identity(row),
                details={
                    "missing_required_reviews": report.get("reviews", {}).get("missing_required_reviews"),
                    "ready_to_aggregate": report.get("reviews", {}).get("ready_to_aggregate"),
                    "aggregate": report.get("reviews", {}).get("aggregate"),
                },
            )
        )
        break

    worker_task = first_task([row for row in all_tasks if row.get("status") == "ready_for_worker"])
    if worker_task is not None:
        report = task_status_report_for_row(worker_task, ops_dir, stale_minutes)
        command = first_status_command(report)
        if command is not None:
            actions.append(
                workspace_action_from_command(
                    "ready_for_worker",
                    command,
                    50,
                    task=task_identity(worker_task),
                    details={"lock_state": report.get("lock_state") if isinstance(report, dict) else None},
                )
            )
        else:
            actions.append(
                workspace_action(
                    "ready_for_worker",
                    "Inspect ready worker task",
                    ["async-research", "workflow", "status", str(worker_task.get("task_dir"))],
                    "a task is ready for worker execution; inspect it before assigning work",
                    50,
                    task=task_identity(worker_task),
                )
            )

    accepted_outputs = snapshot.get("accepted_outputs") if isinstance(snapshot.get("accepted_outputs"), dict) else {}
    memory_decay = accepted_outputs.get("memory_decay") if isinstance(accepted_outputs.get("memory_decay"), dict) else {}
    due_count = memory_decay.get("due_count") if isinstance(memory_decay.get("due_count"), int) else 0
    stale_count = memory_decay.get("stale_count") if isinstance(memory_decay.get("stale_count"), int) else 0
    if due_count or stale_count:
        actions.append(
            workspace_action(
                "accepted_memory_revalidation",
                "Write accepted-memory revalidation schedule",
                ["async-research", "accepted", "revalidation", str(ops_dir), "--write-schedule"],
                "accepted memory has due or stale entries; this writes the derived revalidation schedule",
                60,
                details={"due_count": due_count, "stale_count": stale_count},
                mutates=True,
            )
        )

    foundation_counts = {
        "source": dashboard_warning_count(snapshot.get("sources")),
        "data": dashboard_warning_count(snapshot.get("data")),
        "library": dashboard_warning_count(snapshot.get("library")),
    }
    foundation_total = sum(foundation_counts.values())
    if foundation_total:
        actions.append(
            workspace_action(
                "foundation_attention",
                "Run workflow check",
                ["async-research", "workflow", "check", str(ops_dir)],
                "source, data, or library read models report warnings that need operator attention",
                70,
                details=foundation_counts,
            )
        )

    actions.append(
        workspace_action(
            "maintenance",
            "Update operator surfaces",
            ["async-research", "surface", "update", str(ops_dir)],
            "no higher-priority task action was found; refresh derived operator surfaces",
            80,
            mutates=True,
        )
    )
    return sorted(actions, key=lambda item: (int(item.get("priority", 999)), str(item.get("command", ""))))


def workflow_next_summary(snapshot: dict[str, Any], schema_report: dict[str, Any]) -> dict[str, Any]:
    tasks = snapshot.get("tasks") if isinstance(snapshot.get("tasks"), dict) else {}
    accepted_outputs = snapshot.get("accepted_outputs") if isinstance(snapshot.get("accepted_outputs"), dict) else {}
    memory_decay = accepted_outputs.get("memory_decay") if isinstance(accepted_outputs.get("memory_decay"), dict) else {}
    return {
        "schema_error_count": schema_report.get("error_count", 0),
        "task_total": tasks.get("total", 0),
        "malformed_status_count": len(tasks.get("malformed_statuses", []) if isinstance(tasks.get("malformed_statuses"), list) else []),
        "human_task_count": len(tasks.get("human", []) if isinstance(tasks.get("human"), list) else []),
        "review_task_count": len(tasks.get("review", []) if isinstance(tasks.get("review"), list) else []),
        "active_task_count": len(tasks.get("active", []) if isinstance(tasks.get("active"), list) else []),
        "accepted_memory_due_count": memory_decay.get("due_count", 0),
        "accepted_memory_stale_count": memory_decay.get("stale_count", 0),
    }


def plan_summary(steps: Sequence[WorkflowStep], dry_run: bool) -> list[dict[str, Any]]:
    plan = []
    for step in steps:
        will_run = step.runs_in_dry_run or not dry_run
        dry_run_behavior = "run"
        if not will_run:
            dry_run_behavior = "skip_mutation" if step.mutates else "skip_dry_run_dependency"
        plan.append(
            {
                "name": step.name,
                "command": command_text(step.command),
                "mutates": step.mutates,
                "will_run": will_run,
                "dry_run_behavior": dry_run_behavior,
            }
        )
    return plan


def step_next_step(step: WorkflowStep, code: int, stdout_json: Any) -> str:
    if isinstance(stdout_json, dict) and isinstance(stdout_json.get("next_step"), str):
        return stdout_json["next_step"]
    if code in step.warning_only_exit_codes:
        return "continue; this step is warning-only for workflow orchestration"
    if code == SUCCESS:
        return "continue"
    return "fix this subcommand result, then rerun the workflow command"


def run_steps(steps: Sequence[WorkflowStep], dry_run: bool) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    results: list[dict[str, Any]] = []
    failed: dict[str, Any] | None = None
    for step in steps:
        if dry_run and not step.runs_in_dry_run:
            status = "skipped_mutation" if step.mutates else "skipped_dry_run_dependency"
            next_step = (
                "rerun without --dry-run to execute this mutating step"
                if step.mutates
                else "rerun without --dry-run after the preceding mutating step has refreshed its artifacts"
            )
            results.append(
                {
                    "name": step.name,
                    "command": command_text(step.command),
                    "mutates": step.mutates,
                    "status": status,
                    "exit_code": None,
                    "ok": True,
                    "next_step": next_step,
                }
            )
            continue

        if step.module_name is None:
            code, stdout_json, raw_output, stderr = SUCCESS, {}, None, ""
        else:
            code, stdout_json, raw_output, stderr = run_module_json(step.module_name, step.argv)
        ok = code == SUCCESS or code in step.warning_only_exit_codes
        status = "ok" if code == SUCCESS else "warning" if ok else "failed"
        result: dict[str, Any] = {
            "name": step.name,
            "command": command_text(step.command),
            "mutates": step.mutates,
            "status": status,
            "exit_code": code,
            "ok": ok,
            "stdout_json": stdout_json,
            "stderr": stderr,
            "next_step": step_next_step(step, code, stdout_json),
        }
        if raw_output is not None:
            result["stdout_text"] = raw_output
        results.append(result)
        if not ok:
            failed = result
            break
    return results, failed


def aggregate_decision_from(results: Sequence[dict[str, Any]]) -> str | None:
    for result in results:
        if result.get("name") != "review_aggregate":
            continue
        stdout_json = result.get("stdout_json")
        if isinstance(stdout_json, dict) and isinstance(stdout_json.get("aggregate_decision"), str):
            return stdout_json["aggregate_decision"]
    return None


def partial_mutation_occurred(results: Sequence[dict[str, Any]]) -> bool:
    return any(result.get("mutates") is True and result.get("status") == "ok" for result in results)


def route_next_step(decision: str | None, dry_run: bool, stopped: bool) -> str:
    if stopped:
        return "fix the failed subcommand, then rerun the workflow command"
    if dry_run:
        return "rerun without --dry-run to write aggregate/status changes and refresh operator surfaces"
    if decision == "accepted":
        return "accepted memory, revalidation schedule, surfaces, and health are refreshed"
    if decision == "needs_revision":
        return "send the task back through the bounded revision loop before aggregating again"
    if decision == "needs_human":
        return "resolve the structured human gate with async-research decision resolve-task before continuing"
    if decision == "rejected":
        return "inspect rejected_results.md and continue with the next readiness-gated task"
    return "workflow sequence completed"


def check_steps(ops_dir: Path) -> list[WorkflowStep]:
    return [
        WorkflowStep(
            name="schema_check",
            command=["async-research", "schema-check", str(ops_dir)],
            module_name="check_schema_versions",
            argv=[str(ops_dir)],
            mutates=False,
        ),
        WorkflowStep(
            name="readiness_dry_run",
            command=["async-research", "readiness", str(ops_dir), "--dry-run"],
            module_name="autonomy_readiness_gate",
            argv=[str(ops_dir), "--dry-run"],
            mutates=False,
            warning_only_exit_codes=frozenset({READINESS_WARNINGS}),
        ),
        WorkflowStep(
            name="surface_validate",
            command=["async-research", "surface", "validate", str(ops_dir)],
            module_name="human_review_surface",
            argv=["validate", str(ops_dir)],
            mutates=False,
        ),
        WorkflowStep(
            name="health_dry_run",
            command=["async-research", "health", str(ops_dir), "--dry-run"],
            module_name="health_check",
            argv=[str(ops_dir), "--dry-run"],
            mutates=False,
        ),
    ]


def advance_steps(task_dir: Path, ops_dir: Path, dry_run: bool) -> list[WorkflowStep]:
    review_aggregate_argv = [str(task_dir), "--record-review-start"]
    review_aggregate_command = ["async-research", "review", "aggregate", str(task_dir), "--record-review-start"]
    health_argv = [str(ops_dir)]
    health_command = ["async-research", "health", str(ops_dir)]
    if dry_run:
        review_aggregate_argv.append("--dry-run")
        review_aggregate_command.append("--dry-run")
        health_argv.append("--dry-run")
        health_command.append("--dry-run")
    return [
        WorkflowStep(
            name="schema_check",
            command=["async-research", "schema-check", str(ops_dir)],
            module_name="check_schema_versions",
            argv=[str(ops_dir)],
            mutates=False,
        ),
        WorkflowStep(
            name="readiness_dry_run",
            command=["async-research", "readiness", str(ops_dir), "--dry-run"],
            module_name="autonomy_readiness_gate",
            argv=[str(ops_dir), "--dry-run"],
            mutates=False,
            warning_only_exit_codes=frozenset({READINESS_WARNINGS}),
        ),
        WorkflowStep(
            name="review_aggregate",
            command=review_aggregate_command,
            module_name="aggregate_reviews",
            argv=review_aggregate_argv,
            mutates=not dry_run,
        ),
        WorkflowStep(
            name="accepted_update",
            command=["async-research", "accepted", "update", str(ops_dir)],
            module_name="update_accepted_outputs_index",
            argv=["update", str(ops_dir)],
            mutates=True,
            runs_in_dry_run=False,
        ),
        WorkflowStep(
            name="accepted_revalidation",
            command=["async-research", "accepted", "revalidation", str(ops_dir), "--write-schedule"],
            module_name="update_accepted_outputs_index",
            argv=["revalidation-report", str(ops_dir), "--write-schedule"],
            mutates=True,
            runs_in_dry_run=False,
        ),
        WorkflowStep(
            name="surface_update",
            command=["async-research", "surface", "update", str(ops_dir)],
            module_name="human_review_surface",
            argv=["update", str(ops_dir)],
            mutates=True,
            runs_in_dry_run=False,
        ),
        WorkflowStep(
            name="surface_validate",
            command=["async-research", "surface", "validate", str(ops_dir)],
            module_name="human_review_surface",
            argv=["validate", str(ops_dir)],
            mutates=False,
            runs_in_dry_run=False,
        ),
        WorkflowStep(
            name="health",
            command=health_command,
            module_name="health_check",
            argv=health_argv,
            mutates=not dry_run,
        ),
    ]


def build_status_report(task_dir: Path, ops_dir: Path, stale_minutes: float) -> dict[str, Any]:
    status, status_validation = load_status_for_report(task_dir)
    status_path = task_dir / "status.json"
    transition = transition_report(status, status_path)
    worker_output = worker_output_report(task_dir)
    lock_state = lock_report(task_dir, stale_minutes)
    reviews = review_files_report(task_dir, status)
    human_gate = human_gate_report(status)
    revisions = revision_report(status)
    result = result_report(status)
    claim_strength_preflight = claim_strength_preflight_report(task_dir, status, reviews)
    commands = next_legal_commands(
        task_dir,
        ops_dir,
        status,
        status_validation,
        transition,
        lock_state,
        worker_output,
        reviews,
    )
    ok = bool(status_validation.get("valid")) and bool(transition.get("valid"))
    return {
        "ok": ok,
        "action": "workflow_status_reported",
        "ops_dir": str(ops_dir),
        "task_dir": str(task_dir),
        "status_path": str(status_path),
        "task_id": status.get("id") if status is not None else task_dir.name,
        "title": status.get("title") if status is not None else None,
        "status": status.get("status") if status is not None else None,
        "previous_status": status.get("previous_status") if status is not None else None,
        "type": status.get("type") if status is not None else None,
        "review_tier": reviews["review_tier"],
        "status_validation": status_validation,
        "transition_validation": transition,
        "lock_state": lock_state,
        "worker_output": worker_output,
        "reviews": reviews,
        "human_gate": human_gate,
        "revisions": revisions,
        "result": result,
        "claim_strength_preflight": claim_strength_preflight,
        "next_legal_commands": commands,
        "next_step": commands[0]["command"] if commands else "no safe task-level command is available",
        "summary": {
            "headline": status_headline(status, worker_output, reviews, lock_state),
            "primary_next_command": commands[0]["command"] if commands else None,
        },
    }


def run_status(args: argparse.Namespace) -> int:
    task_dir = args.task_dir
    if not task_dir.exists() or not task_dir.is_dir():
        ops_dir = args.ops_dir or inferred_ops_dir_for_task(task_dir)
        payload: dict[str, Any] = {
            "ok": False,
            "action": "workflow_status_refused",
            "reason": "task_dir_missing",
            "task_dir": str(task_dir),
            "next_step": "choose an existing research_ops/tasks/<TASK-ID> directory",
        }
        if ops_dir is not None:
            payload["ops_dir"] = str(ops_dir)
        print_json(payload)
        return INVALID_STATE

    ops_dir, workspace_error = resolve_task_ops_dir(task_dir, args.ops_dir, action="workflow_status_refused")
    if workspace_error is not None:
        print_json(workspace_error)
        return INVALID_STATE
    assert ops_dir is not None

    report = build_status_report(task_dir, ops_dir, args.stale_minutes)
    print_json(report)
    return SUCCESS if report["ok"] else INVALID_STATE


def build_next_report(ops_dir: Path, stale_minutes: float) -> dict[str, Any]:
    schema_report = check_schema_versions.scan_schema_versions(ops_dir)
    snapshot = console_snapshot.snapshot(ops_dir)
    actions = workflow_next_actions(ops_dir, snapshot, schema_report, stale_minutes)
    recommendation = actions[0] if actions else None
    return {
        "ok": True,
        "action": "workflow_next_reported",
        "ops_dir": str(ops_dir),
        "read_only": True,
        "changed": False,
        "priority_order": [
            "malformed_state",
            "needs_human",
            "active_lock",
            "stale_lock",
            "worker_completion",
            "ready_for_review",
            "ready_for_worker",
            "accepted_memory_revalidation",
            "foundation_attention",
            "maintenance",
        ],
        "recommendation": recommendation,
        "alternatives": actions[1:],
        "candidate_count": len(actions),
        "summary": workflow_next_summary(snapshot, schema_report),
        "snapshot": {
            "schema_version": snapshot.get("schema_version"),
            "generated_at": snapshot.get("generated_at"),
            "readiness": snapshot.get("readiness", {}).get("next_step") if isinstance(snapshot.get("readiness"), dict) else None,
            "health": snapshot.get("health", {}).get("next_step") if isinstance(snapshot.get("health"), dict) else None,
        },
        "next_step": recommendation.get("command") if isinstance(recommendation, dict) else "no recommended command available",
    }


def run_next(args: argparse.Namespace) -> int:
    ops_dir = args.ops_dir
    if not ops_dir.exists() or not ops_dir.is_dir():
        print_json(
            {
                "ok": False,
                "action": "workflow_next_refused",
                "reason": "ops_dir_missing",
                "ops_dir": str(ops_dir),
                "read_only": True,
                "changed": False,
                "next_step": f"initialize a workspace with async-research init {shlex.quote(str(ops_dir))}",
            }
        )
        return INVALID_STATE
    print_json(build_next_report(ops_dir, args.stale_minutes))
    return SUCCESS


def load_valid_task_status(task_dir: Path, action: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    status, status_validation = load_status_for_report(task_dir)
    status_path = task_dir / "status.json"
    transition = transition_report(status, status_path)
    if status is None or not status_validation.get("valid") or not transition.get("valid"):
        return None, {
            "ok": False,
            "action": action,
            "reason": "status_invalid",
            "task_dir": str(task_dir),
            "status_path": str(status_path),
            "status_validation": status_validation,
            "transition_validation": transition,
            "changed": False,
            "next_step": "repair status.json before running workflow worker transition commands",
        }
    return status, None


def validate_transition_candidate(status_path: Path, payload: dict[str, Any], action: str, task_dir: Path) -> dict[str, Any] | None:
    code, validation = validate_status_for_write(status_path, payload)
    if code == SUCCESS:
        return None
    return {
        "ok": False,
        "action": action,
        "reason": "transition_validation_failed",
        "task_dir": str(task_dir),
        "status_path": str(status_path),
        "validation": validation,
        "changed": False,
        "next_step": "inspect the task status transition before retrying the worker wrapper",
    }


def run_worker_start(args: argparse.Namespace) -> int:
    task_dir = args.task_dir
    action = "workflow_worker_start_refused"
    if not task_dir.exists() or not task_dir.is_dir():
        ops_dir = args.ops_dir or inferred_ops_dir_for_task(task_dir)
        payload: dict[str, Any] = {
            "ok": False,
            "action": action,
            "reason": "task_dir_missing",
            "task_dir": str(task_dir),
            "changed": False,
            "next_step": "choose an existing research_ops/tasks/<TASK-ID> directory",
        }
        if ops_dir is not None:
            payload["ops_dir"] = str(ops_dir)
        print_json(payload)
        return INVALID_STATE

    ops_dir, workspace_error = resolve_task_ops_dir(task_dir, args.ops_dir, action=action)
    if workspace_error is not None:
        workspace_error["changed"] = False
        print_json(workspace_error)
        return INVALID_STATE
    assert ops_dir is not None

    status, error = load_valid_task_status(task_dir, action)
    if error is not None:
        error["ops_dir"] = str(ops_dir)
        print_json(error)
        return INVALID_STATE
    assert status is not None

    if status.get("status") != "ready_for_worker":
        print_json(
            {
                "ok": False,
                "action": action,
                "reason": "task_not_ready_for_worker",
                "ops_dir": str(ops_dir),
                "task_dir": str(task_dir),
                "current_status": status.get("status"),
                "required_status": "ready_for_worker",
                "changed": False,
                "next_step": f"run async-research workflow status {shlex.quote(str(task_dir))}",
            }
        )
        return INVALID_STATE

    updated = worker_started_status(status, args.owner, args.stale_minutes)
    status_path = task_dir / "status.json"
    validation_error = validate_transition_candidate(status_path, updated, action, task_dir)
    if validation_error is not None:
        validation_error["ops_dir"] = str(ops_dir)
        print_json(validation_error)
        return INVALID_STATE

    lock_state = lock_report(task_dir, args.stale_minutes)
    if lock_state.get("locked") and not lock_state.get("stale"):
        print_json(
            {
                "ok": False,
                "action": action,
                "reason": "lock_acquire_failed",
                "ops_dir": str(ops_dir),
                "task_dir": str(task_dir),
                "owner": args.owner,
                "lock_state": lock_state,
                "dry_run": args.dry_run,
                "changed": False,
                "next_step": "wait for the lock owner, inspect stale locks, or retry after the lock becomes stale",
            }
        )
        return task_lock.LOCKED

    if args.dry_run:
        print_json(
            {
                "ok": True,
                "action": "workflow_worker_start_dry_run",
                "ops_dir": str(ops_dir),
                "task_dir": str(task_dir),
                "status_path": str(status_path),
                "dry_run": True,
                "changed": False,
                "current_status": status.get("status"),
                "next_status": "in_progress",
                "owner": args.owner,
                "lock_state": lock_state,
                "would_acquire_lock": True,
                "would_write_status": True,
                "next_step": f"rerun without --dry-run to claim the task, then write {shlex.quote(str(task_dir / 'worker_output.md'))}",
            }
        )
        return SUCCESS

    acquire_code, acquire_json, raw_output, stderr = run_module_json(
        "task_lock",
        ["acquire", str(task_dir), "--owner", args.owner, "--stale-minutes", str(args.stale_minutes)],
    )
    if acquire_code != SUCCESS:
        print_json(
            {
                "ok": False,
                "action": action,
                "reason": "lock_acquire_failed",
                "ops_dir": str(ops_dir),
                "task_dir": str(task_dir),
                "owner": args.owner,
                "lock_result": acquire_json,
                "stdout_text": raw_output,
                "stderr": stderr,
                "changed": False,
                "next_step": "wait for the lock owner, inspect stale locks, or retry with a stale threshold after review",
            }
        )
        return int(acquire_code)

    latest_status, latest_error = load_valid_task_status(task_dir, action)
    if latest_error is not None or latest_status is None or latest_status.get("status") != "ready_for_worker":
        release_code, release_json, release_raw, release_stderr = run_module_json(
            "task_lock",
            ["release", str(task_dir), "--owner", args.owner],
        )
        print_json(
            {
                "ok": False,
                "action": action,
                "reason": "status_changed_after_lock",
                "ops_dir": str(ops_dir),
                "task_dir": str(task_dir),
                "current_status": latest_status.get("status") if latest_status is not None else None,
                "status_error": latest_error,
                "lock_result": acquire_json,
                "release_result": release_json,
                "release_stdout_text": release_raw,
                "release_stderr": release_stderr,
                "changed": release_code == SUCCESS,
                "next_step": "inspect the current task state before retrying worker-start",
            }
        )
        return INVALID_STATE

    updated = worker_started_status(latest_status, args.owner, args.stale_minutes)
    validation_error = validate_transition_candidate(status_path, updated, action, task_dir)
    if validation_error is not None:
        release_code, release_json, release_raw, release_stderr = run_module_json(
            "task_lock",
            ["release", str(task_dir), "--owner", args.owner],
        )
        validation_error.update(
            {
                "ops_dir": str(ops_dir),
                "lock_result": acquire_json,
                "release_result": release_json,
                "release_stdout_text": release_raw,
                "release_stderr": release_stderr,
                "changed": release_code == SUCCESS,
            }
        )
        print_json(validation_error)
        return INVALID_STATE

    try:
        atomic_write_json(status_path, updated)
    except OSError as exc:
        release_code, release_json, release_raw, release_stderr = run_module_json(
            "task_lock",
            ["release", str(task_dir), "--owner", args.owner],
        )
        print_json(
            {
                "ok": False,
                "action": action,
                "reason": "status_write_failed",
                "ops_dir": str(ops_dir),
                "task_dir": str(task_dir),
                "status_path": str(status_path),
                "error": str(exc),
                "lock_result": acquire_json,
                "release_result": release_json,
                "release_stdout_text": release_raw,
                "release_stderr": release_stderr,
                "changed": release_code == SUCCESS,
                "next_step": "fix the filesystem error, then rerun worker-start",
            }
        )
        return INVALID_STATE

    print_json(
        {
            "ok": True,
            "action": "workflow_worker_started",
            "ops_dir": str(ops_dir),
            "task_dir": str(task_dir),
            "status_path": str(status_path),
            "dry_run": False,
            "changed": True,
            "previous_status": latest_status.get("status"),
            "status": "in_progress",
            "owner": args.owner,
            "lock_result": acquire_json,
            "next_step": f"write {shlex.quote(str(task_dir / 'worker_output.md'))}, then run async-research workflow worker-complete {shlex.quote(str(task_dir))} --owner {shlex.quote(args.owner)} --dry-run",
        }
    )
    return SUCCESS


def run_worker_complete(args: argparse.Namespace) -> int:
    task_dir = args.task_dir
    action = "workflow_worker_complete_refused"
    if not task_dir.exists() or not task_dir.is_dir():
        ops_dir = args.ops_dir or inferred_ops_dir_for_task(task_dir)
        payload: dict[str, Any] = {
            "ok": False,
            "action": action,
            "reason": "task_dir_missing",
            "task_dir": str(task_dir),
            "changed": False,
            "next_step": "choose an existing research_ops/tasks/<TASK-ID> directory",
        }
        if ops_dir is not None:
            payload["ops_dir"] = str(ops_dir)
        print_json(payload)
        return INVALID_STATE

    ops_dir, workspace_error = resolve_task_ops_dir(task_dir, args.ops_dir, action=action)
    if workspace_error is not None:
        workspace_error["changed"] = False
        print_json(workspace_error)
        return INVALID_STATE
    assert ops_dir is not None

    status, error = load_valid_task_status(task_dir, action)
    if error is not None:
        error["ops_dir"] = str(ops_dir)
        print_json(error)
        return INVALID_STATE
    assert status is not None

    if status.get("status") != "in_progress":
        print_json(
            {
                "ok": False,
                "action": action,
                "reason": "task_not_in_progress",
                "ops_dir": str(ops_dir),
                "task_dir": str(task_dir),
                "current_status": status.get("status"),
                "required_status": "in_progress",
                "changed": False,
                "next_step": f"run async-research workflow status {shlex.quote(str(task_dir))}",
            }
        )
        return INVALID_STATE

    worker_output = worker_output_report(task_dir)
    if not worker_output.get("ready_for_review"):
        print_json(
            {
                "ok": False,
                "action": action,
                "reason": "worker_output_not_ready",
                "ops_dir": str(ops_dir),
                "task_dir": str(task_dir),
                "worker_output": worker_output,
                "changed": False,
                "next_step": f"write a non-empty {shlex.quote(str(task_dir / 'worker_output.md'))} before completing the worker task",
            }
        )
        return INVALID_STATE

    claim_strength_preflight = claim_strength_preflight_report(task_dir, status)
    lock_state = lock_report(task_dir, args.stale_minutes)
    lock_owner = None
    if lock_state.get("locked"):
        owner_payload = lock_state.get("owner")
        lock_owner = owner_payload.get("owner") if isinstance(owner_payload, dict) else None
        if lock_owner and lock_owner != args.owner and not args.force_release:
            print_json(
                {
                    "ok": False,
                    "action": action,
                    "reason": "lock_owner_mismatch",
                    "ops_dir": str(ops_dir),
                    "task_dir": str(task_dir),
                    "expected_owner": lock_owner,
                    "requested_owner": args.owner,
                    "lock_state": lock_state,
                    "changed": False,
                    "next_step": "rerun with the lock owner or use --force-release only after confirming the owner is inactive",
                }
            )
            return task_lock.RELEASE_DENIED

    updated = worker_completed_status(status)
    status_path = task_dir / "status.json"
    validation_error = validate_transition_candidate(status_path, updated, action, task_dir)
    if validation_error is not None:
        validation_error["ops_dir"] = str(ops_dir)
        print_json(validation_error)
        return INVALID_STATE

    if args.dry_run:
        print_json(
            {
                "ok": True,
                "action": "workflow_worker_complete_dry_run",
                "ops_dir": str(ops_dir),
                "task_dir": str(task_dir),
                "status_path": str(status_path),
                "dry_run": True,
                "changed": False,
                "current_status": status.get("status"),
                "next_status": "awaiting_review",
                "owner": args.owner,
                "lock_state": lock_state,
                "worker_output": worker_output,
                "claim_strength_preflight": claim_strength_preflight,
                "would_release_lock": bool(lock_state.get("locked")),
                "would_write_status": True,
                "next_step": "rerun without --dry-run to move the task to awaiting_review and release the lock",
            }
        )
        return SUCCESS

    latest_status, latest_error = load_valid_task_status(task_dir, action)
    if latest_error is not None or latest_status is None or latest_status.get("status") != "in_progress":
        print_json(
            {
                "ok": False,
                "action": action,
                "reason": "status_changed_before_write",
                "ops_dir": str(ops_dir),
                "task_dir": str(task_dir),
                "current_status": latest_status.get("status") if latest_status is not None else None,
                "status_error": latest_error,
                "changed": False,
                "next_step": "inspect the current task state before retrying worker-complete",
            }
        )
        return INVALID_STATE

    worker_output = worker_output_report(task_dir)
    if not worker_output.get("ready_for_review"):
        print_json(
            {
                "ok": False,
                "action": action,
                "reason": "worker_output_changed_before_write",
                "ops_dir": str(ops_dir),
                "task_dir": str(task_dir),
                "worker_output": worker_output,
                "changed": False,
                "next_step": f"restore a non-empty {shlex.quote(str(task_dir / 'worker_output.md'))} before completing the worker task",
            }
        )
        return INVALID_STATE

    claim_strength_preflight = claim_strength_preflight_report(task_dir, latest_status)
    lock_state = lock_report(task_dir, args.stale_minutes)
    if lock_state.get("locked"):
        owner_payload = lock_state.get("owner")
        lock_owner = owner_payload.get("owner") if isinstance(owner_payload, dict) else None
        if lock_owner and lock_owner != args.owner and not args.force_release:
            print_json(
                {
                    "ok": False,
                    "action": action,
                    "reason": "lock_owner_mismatch",
                    "ops_dir": str(ops_dir),
                    "task_dir": str(task_dir),
                    "expected_owner": lock_owner,
                    "requested_owner": args.owner,
                    "lock_state": lock_state,
                    "changed": False,
                    "next_step": "rerun with the lock owner or use --force-release only after confirming the owner is inactive",
                }
            )
            return task_lock.RELEASE_DENIED

    updated = worker_completed_status(latest_status)
    validation_error = validate_transition_candidate(status_path, updated, action, task_dir)
    if validation_error is not None:
        validation_error["ops_dir"] = str(ops_dir)
        print_json(validation_error)
        return INVALID_STATE

    try:
        atomic_write_json(status_path, updated)
    except OSError as exc:
        print_json(
            {
                "ok": False,
                "action": action,
                "reason": "status_write_failed",
                "ops_dir": str(ops_dir),
                "task_dir": str(task_dir),
                "status_path": str(status_path),
                "error": str(exc),
                "changed": False,
                "next_step": "fix the filesystem error, then rerun worker-complete",
            }
        )
        return INVALID_STATE

    release_argv = ["release", str(task_dir), "--owner", args.owner]
    if args.force_release:
        release_argv.append("--force")
    release_code, release_json, raw_output, stderr = run_module_json("task_lock", release_argv)
    if release_code != SUCCESS:
        print_json(
            {
                "ok": False,
                "action": action,
                "reason": "lock_release_failed_after_status_write",
                "ops_dir": str(ops_dir),
                "task_dir": str(task_dir),
                "status_path": str(status_path),
                "owner": args.owner,
                "release_result": release_json,
                "stdout_text": raw_output,
                "stderr": stderr,
                "changed": True,
                "partial_mutation": True,
                "next_step": "inspect and release the task-local lock before continuing review work",
            }
        )
        return int(release_code)

    print_json(
        {
            "ok": True,
            "action": "workflow_worker_completed",
            "ops_dir": str(ops_dir),
            "task_dir": str(task_dir),
            "status_path": str(status_path),
            "dry_run": False,
            "changed": True,
            "previous_status": latest_status.get("status"),
            "status": "awaiting_review",
            "owner": args.owner,
            "lock_missing": not bool(lock_state.get("locked")),
            "release_result": release_json,
            "claim_strength_preflight": claim_strength_preflight,
            "next_step": f"run async-research workflow status {shlex.quote(str(task_dir))} or submit reviews before workflow advance",
        }
    )
    return SUCCESS


def run_check(args: argparse.Namespace) -> int:
    ops_dir = args.ops_dir
    steps = check_steps(ops_dir)
    results, failed = run_steps(steps, dry_run=False)
    ok = failed is None
    print_json(
        {
            "ok": ok,
            "action": "workflow_checked",
            "ops_dir": str(ops_dir),
            "dry_run": False,
            "plan": plan_summary(steps, dry_run=False),
            "steps": results,
            "stopped": failed is not None,
            "failed_step": None if failed is None else failed["name"],
            "next_step": "fix the failed subcommand, then rerun workflow check" if failed else "workspace checks passed",
        }
    )
    return SUCCESS if failed is None else int(failed["exit_code"] or VALIDATION_FAILED)


def run_advance(args: argparse.Namespace) -> int:
    task_dir = args.task_dir
    if not task_dir.exists():
        ops_dir = args.ops_dir or inferred_ops_dir_for_task(task_dir)
        payload: dict[str, Any] = {
            "ok": False,
            "action": "workflow_advance_refused",
            "reason": "task_dir_missing",
            "task_dir": str(task_dir),
            "next_step": "choose an existing research_ops/tasks/<TASK-ID> directory",
        }
        if ops_dir is not None:
            payload["ops_dir"] = str(ops_dir)
        print_json(payload)
        return INVALID_STATE
    ops_dir, workspace_error = resolve_task_ops_dir(task_dir, args.ops_dir)
    if workspace_error is not None:
        print_json(workspace_error)
        return INVALID_STATE
    assert ops_dir is not None
    status, _status_validation = load_status_for_report(task_dir)
    preflight_reviews = review_files_report(task_dir, status)
    claim_strength_preflight = claim_strength_preflight_report(task_dir, status, preflight_reviews)
    steps = advance_steps(task_dir, ops_dir, args.dry_run)
    results, failed = run_steps(steps, dry_run=args.dry_run)
    decision = aggregate_decision_from(results)
    ok = failed is None
    partial_mutation = failed is not None and partial_mutation_occurred(results)
    print_json(
        {
            "ok": ok,
            "action": "workflow_advance_dry_run" if args.dry_run else "workflow_advanced",
            "ops_dir": str(ops_dir),
            "task_dir": str(task_dir),
            "dry_run": args.dry_run,
            "plan": plan_summary(steps, dry_run=args.dry_run),
            "steps": results,
            "stopped": failed is not None,
            "failed_step": None if failed is None else failed["name"],
            "partial_mutation": partial_mutation,
            "aggregate_decision": decision,
            "claim_strength_preflight": claim_strength_preflight,
            "next_step": route_next_step(decision, args.dry_run, failed is not None),
        }
    )
    return SUCCESS if failed is None else int(failed["exit_code"] or VALIDATION_FAILED)


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run or dry-run safe async research workflow sequences.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("check", help="Run read-only workspace workflow checks.")
    check.add_argument("ops_dir", nargs="?", type=Path, default=Path("research_ops"))
    check.set_defaults(func=run_check)

    status = subparsers.add_parser("status", help="Report read-only task status and next legal commands.")
    status.add_argument("task_dir", type=Path)
    status.add_argument("--ops-dir", type=Path, help="Override the research_ops directory inferred from the task path.")
    status.add_argument("--stale-minutes", type=float, default=60.0, help="Lock age threshold for stale-lock reporting.")
    status.set_defaults(func=run_status)

    next_cmd = subparsers.add_parser("next", help="Recommend the next safe workspace action.")
    next_cmd.add_argument("ops_dir", nargs="?", type=Path, default=Path("research_ops"))
    next_cmd.add_argument("--stale-minutes", type=float, default=60.0, help="Lock age threshold for stale-lock reporting.")
    next_cmd.set_defaults(func=run_next)

    worker_start = subparsers.add_parser("worker-start", help="Claim a ready task and move it to in_progress.")
    worker_start.add_argument("task_dir", type=Path)
    worker_start.add_argument("--ops-dir", type=Path, help="Override the research_ops directory inferred from the task path.")
    worker_start.add_argument("--owner", default=task_lock.default_owner(), help="Worker owner written to LOCK/owner.json.")
    worker_start.add_argument("--stale-minutes", type=float, default=60.0, help="Lock age threshold for stale-lock takeover.")
    worker_start.add_argument("--dry-run", action="store_true", help="Validate the claim and transition without writing status.json or LOCK/.")
    worker_start.set_defaults(func=run_worker_start)

    worker_complete = subparsers.add_parser("worker-complete", help="Move an in-progress task with worker output to awaiting_review.")
    worker_complete.add_argument("task_dir", type=Path)
    worker_complete.add_argument("--ops-dir", type=Path, help="Override the research_ops directory inferred from the task path.")
    worker_complete.add_argument("--owner", default=task_lock.default_owner(), help="Worker owner expected in LOCK/owner.json.")
    worker_complete.add_argument("--stale-minutes", type=float, default=60.0, help="Lock age threshold for lock-state reporting.")
    worker_complete.add_argument("--force-release", action="store_true", help="Release a mismatched lock owner after external confirmation.")
    worker_complete.add_argument("--dry-run", action="store_true", help="Validate output and transition without writing status.json or releasing LOCK/.")
    worker_complete.set_defaults(func=run_worker_complete)

    advance = subparsers.add_parser("advance", help="Run the canonical post-worker task workflow.")
    advance.add_argument("task_dir", type=Path)
    advance.add_argument("--ops-dir", type=Path, help="Override the research_ops directory inferred from the task path.")
    advance.add_argument("--dry-run", action="store_true", help="Print the plan and run only read-only checks.")
    advance.set_defaults(func=run_advance)
    return parser.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
