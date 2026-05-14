#!/usr/bin/env python3
"""Public workflow orchestration for the canonical post-worker loop."""

from __future__ import annotations

import argparse
import contextlib
import importlib
import io
import json
import shlex
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any, Iterable, Sequence

from async_research_workflow.resources import schema_path
from async_research_workflow.scripts import task_lock, validate_transition
from async_research_workflow.scripts.aggregate_reviews import (
    REVIEWER_ROLES,
    read_review,
    required_reviewers,
    review_tier,
    validate_review,
)
from async_research_workflow.scripts.validate_json_artifact import load_json, validate


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
        return payload, {**base, "reason": "status_schema_validation_failed", "issues": errors}
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
                "Run workflow check",
                ["async-research", "workflow", "check", str(ops_dir)],
                "confirm workspace readiness before assigning or starting worker execution",
            )
        ]

    if current_status == "accepted":
        return [
            command_hint(
                "Refresh outcomes",
                ["async-research", "outcomes", "refresh", str(ops_dir)],
                "update delivered-project outcome surfaces for accepted work",
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
