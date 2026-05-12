"""Guarded setup and health actions for the local console."""

from __future__ import annotations

import contextlib
import importlib
import io
import json
import shlex
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from async_research_workflow import cli
from async_research_workflow.console.snapshot import workspace_snapshot
from async_research_workflow.resources import schema_path
from async_research_workflow.scripts.decision_log import has_decision
from async_research_workflow.scripts.decision_log import read_decisions


COMMAND_LOCK = threading.Lock()


@dataclass(frozen=True)
class ActionSpec:
    action_id: str
    label: str
    description: str
    command: tuple[str, ...]
    mutates: bool
    command_prefix: tuple[str, ...] = ("async-research",)
    ok_exit_codes: tuple[int, ...] = (0,)
    requires_confirmation: bool = False
    recovery_advice: str = "Review stdout and stderr, repair the reported issue, then rerun the command."
    success_next_step: str = "Refresh the dashboard snapshot."


@dataclass(frozen=True)
class DecisionActionSpec:
    action_id: str
    label: str
    description: str
    decision: str
    target_status: str | None
    append_only: bool = False
    recovery_advice: str = "Review the decision command result, then repair the task state or decision log before retrying."
    success_next_step: str = "Decision recorded. Refresh the task board and operator surfaces."


ACTION_SPECS: dict[str, ActionSpec] = {
    "schema_check": ActionSpec(
        action_id="schema_check",
        label="Schema Check",
        description="Validate schema versions for workflow JSON artifacts.",
        command=("schema-check", "{ops_dir}"),
        mutates=False,
        recovery_advice="Repair missing, malformed, mismatched, or unreadable versioned artifacts, then rerun schema-check.",
        success_next_step="Run readiness and health dry runs.",
    ),
    "readiness_dry_run": ActionSpec(
        action_id="readiness_dry_run",
        label="Readiness Dry Run",
        description="Classify whether scheduled or expensive work may continue without writing status files.",
        command=("readiness", "{ops_dir}", "--dry-run"),
        mutates=False,
        ok_exit_codes=(0, 2),
        recovery_advice="Resolve readiness blockers or review warnings before starting expensive workers.",
        success_next_step="Run health dry run or update the operator surface.",
    ),
    "health_dry_run": ActionSpec(
        action_id="health_dry_run",
        label="Health Dry Run",
        description="Summarize operational health without writing health_report.json or daily_status.md.",
        command=("health", "{ops_dir}", "--dry-run"),
        mutates=False,
        recovery_advice="Repair malformed workspace state or health errors, then rerun health dry run.",
        success_next_step="Run surface update when the generated operator files should be refreshed.",
    ),
    "surface_update": ActionSpec(
        action_id="surface_update",
        label="Surface Update",
        description="Refresh daily_status.md, human_review_queue.md, and weekly_digest.md.",
        command=("surface", "update", "{ops_dir}"),
        mutates=True,
        recovery_advice="Repair malformed workspace state or missing required files, then rerun surface update.",
        success_next_step="Run surface validate to confirm generated files match the workspace.",
    ),
    "surface_validate": ActionSpec(
        action_id="surface_validate",
        label="Surface Validate",
        description="Compare generated operator surfaces with current workspace state.",
        command=("surface", "validate", "{ops_dir}"),
        mutates=False,
        recovery_advice="Run surface update when surfaces drift; repair malformed workspace state if validation cannot read files.",
        success_next_step="Refresh the dashboard snapshot.",
    ),
    "outcomes_refresh": ActionSpec(
        action_id="outcomes_refresh",
        label="Refresh Outcomes",
        description="Rebuild delivered-project outcome JSONL and summary files from accepted outputs and task provenance.",
        command=("outcomes", "refresh", "{ops_dir}"),
        mutates=True,
        recovery_advice="Repair malformed accepted outputs, task status, review, idea, or cost files, then rerun outcomes refresh.",
        success_next_step="Refresh the delivered projects table.",
    ),
}


DECISION_ACTION_SPECS: dict[str, DecisionActionSpec] = {
    "decision_resume": DecisionActionSpec(
        action_id="decision_resume",
        label="Resume",
        description="Record a resume decision and move the needs_human task back to ready_for_worker.",
        decision="resume",
        target_status="ready_for_worker",
    ),
    "decision_pause": DecisionActionSpec(
        action_id="decision_pause",
        label="Pause",
        description="Record a pause decision and move the needs_human task to paused.",
        decision="pause",
        target_status="paused",
    ),
    "decision_reject": DecisionActionSpec(
        action_id="decision_reject",
        label="Reject",
        description="Record a rejection decision and move the needs_human task to rejected.",
        decision="reject",
        target_status="rejected",
    ),
    "decision_approve_budget": DecisionActionSpec(
        action_id="decision_approve_budget",
        label="Approve Budget",
        description="Record budget approval and resume the task.",
        decision="approve_budget",
        target_status="ready_for_worker",
    ),
    "decision_approve_data_use": DecisionActionSpec(
        action_id="decision_approve_data_use",
        label="Approve Data Use",
        description="Record data-use approval and resume the task.",
        decision="approve_data_use",
        target_status="ready_for_worker",
    ),
    "decision_approve_high_stakes": DecisionActionSpec(
        action_id="decision_approve_high_stakes",
        label="Approve High-Stakes",
        description="Record high-stakes approval and resume the task.",
        decision="approve_high_stakes",
        target_status="ready_for_worker",
    ),
    "decision_add_note": DecisionActionSpec(
        action_id="decision_add_note",
        label="Add Note",
        description="Append an acknowledgement note to decisions.md without changing task status.",
        decision="acknowledge",
        target_status=None,
        append_only=True,
        success_next_step="Decision note recorded. Refresh the dashboard snapshot.",
    ),
}


TASK_ACTION_SPECS: dict[str, ActionSpec] = {
    "task_status_validate": ActionSpec(
        action_id="task_status_validate",
        label="Validate Status",
        description="Validate one task status.json against the packaged task status schema.",
        command=("async_research_workflow.scripts.validate_json_artifact", "{status_path}", "--schema", "{schema_path}"),
        command_prefix=("python", "-m"),
        mutates=False,
        recovery_advice="Repair the task status.json schema errors, then rerun status validation.",
        success_next_step="Run transition validation or inspect the task lock.",
    ),
    "task_transition_validate": ActionSpec(
        action_id="task_transition_validate",
        label="Validate Transition",
        description="Validate the task previous_status -> status state-machine transition.",
        command=("async_research_workflow.scripts.validate_transition", "{task_dir}"),
        command_prefix=("python", "-m"),
        mutates=False,
        recovery_advice="Repair previous_status, status, last_transition_reason, or required human-decision evidence.",
        success_next_step="Inspect the lock state when preparing worker execution.",
    ),
    "task_lock_status": ActionSpec(
        action_id="task_lock_status",
        label="Inspect Lock",
        description="Inspect the task-local LOCK directory without acquiring or releasing it.",
        command=("async_research_workflow.scripts.task_lock", "status", "{task_dir}"),
        command_prefix=("python", "-m"),
        mutates=False,
        recovery_advice="Review the lock owner and stale state before deciding whether recovery is needed.",
        success_next_step="Refresh the task board when lock state changes.",
    ),
}


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def init_confirmation_token(ops_dir: Path, template: str) -> str:
    return f"init:{ops_dir}:{template}"


def decision_confirmation_token(action_id: str) -> str:
    return f"decision:{action_id}"


def action_command(spec: ActionSpec, ops_dir: Path) -> list[str]:
    return [part.format(ops_dir=str(ops_dir)) for part in spec.command]


def task_action_command(spec: ActionSpec, task_dir: Path) -> list[str]:
    return [
        part.format(
            task_dir=str(task_dir),
            status_path=str(task_dir / "status.json"),
            schema_path=str(schema_path("task_status.schema.json")),
        )
        for part in spec.command
    ]


def command_string(argv: list[str], prefix: tuple[str, ...] = ("async-research",)) -> str:
    return shlex.join([*prefix, *argv])


def parse_stdout_json(stdout: str) -> dict[str, Any] | None:
    text = stdout.strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def exit_status(exit_code: int, ok_exit_codes: tuple[int, ...]) -> str:
    if exit_code == 0:
        return "success"
    if exit_code in ok_exit_codes:
        return "warning"
    return "failed"


def recovery_advice(spec: ActionSpec, exit_code: int, parsed_stdout: dict[str, Any] | None) -> str:
    if exit_code in spec.ok_exit_codes:
        return spec.success_next_step
    if parsed_stdout:
        next_step = parsed_stdout.get("next_step")
        if isinstance(next_step, str) and next_step:
            return next_step
        reason = parsed_stdout.get("reason")
        if isinstance(reason, str) and reason:
            return f"{spec.recovery_advice} Reported reason: {reason}."
    return spec.recovery_advice


def run_cli_command(argv: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    # CLI helpers print to process-wide stdout/stderr, so action runs must be
    # serialized even though the HTTP server can handle concurrent requests.
    with COMMAND_LOCK:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                code = cli.main(argv)
            except SystemExit as exc:
                code = exc.code if isinstance(exc.code, int) else 1
            except Exception as exc:
                print(f"unexpected console action failure: {exc}", file=sys.stderr)
                code = 1
    return int(code), stdout.getvalue(), stderr.getvalue()


def run_module_command(module_name: str, argv: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with COMMAND_LOCK:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                module = importlib.import_module(module_name)
                code = module.main(argv)
            except SystemExit as exc:
                code = exc.code if isinstance(exc.code, int) else 1
            except Exception as exc:
                print(f"unexpected console task action failure: {exc}", file=sys.stderr)
                code = 1
    return int(code), stdout.getvalue(), stderr.getvalue()


def command_result(spec: ActionSpec, ops_dir: Path, argv: list[str], started_at: str, elapsed_ms: int, exit_code: int, stdout: str, stderr: str) -> dict[str, Any]:
    parsed_stdout = parse_stdout_json(stdout)
    status = exit_status(exit_code, spec.ok_exit_codes)
    return {
        "ok": status != "failed",
        "status": status,
        "action": spec.action_id,
        "label": spec.label,
        "mutates": spec.mutates,
        "command": command_string(argv, spec.command_prefix),
        "argv": [*spec.command_prefix, *argv],
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "parsed_stdout": parsed_stdout,
        "started_at": started_at,
        "finished_at": utc_timestamp(),
        "elapsed_ms": elapsed_ms,
        "next_step": recovery_advice(spec, exit_code, parsed_stdout),
    }


def task_action_catalog() -> list[dict[str, Any]]:
    return [
        {
            "id": spec.action_id,
            "label": spec.label,
            "description": spec.description,
            "command_template": command_string(list(spec.command), spec.command_prefix),
            "mutates": spec.mutates,
            "requires_confirmation": spec.requires_confirmation,
            "requires_task": True,
            "status": "available",
        }
        for spec in TASK_ACTION_SPECS.values()
    ]


def decision_action_command_template(spec: DecisionActionSpec, ops_dir: Path) -> str:
    if spec.append_only:
        argv = [
            "decision",
            "append",
            str(ops_dir),
            "--item-id",
            "<task_id>",
            "--decision",
            spec.decision,
            "--reason",
            "<reason>",
            "--approver",
            "<approver>",
            "--related-artifact",
            "<status_path>",
        ]
    else:
        argv = [
            "decision",
            "resolve-task",
            str(ops_dir),
            "<task_dir>",
            "--decision",
            spec.decision,
            "--reason",
            "<reason>",
            "--approver",
            "<approver>",
        ]
        if spec.target_status:
            argv.extend(["--status", spec.target_status])
    return command_string(argv)


def decision_action_catalog(ops_dir: Path) -> list[dict[str, Any]]:
    return [
        {
            "id": spec.action_id,
            "label": spec.label,
            "description": spec.description,
            "decision": spec.decision,
            "target_status": spec.target_status,
            "append_only": spec.append_only,
            "command_template": decision_action_command_template(spec, ops_dir),
            "mutates": True,
            "requires_confirmation": True,
            "confirmation_token": decision_confirmation_token(spec.action_id),
            "requires_task": True,
            "status": "available",
        }
        for spec in DECISION_ACTION_SPECS.values()
    ]


def init_spec(template: str) -> ActionSpec:
    command = ("init", "{ops_dir}") if template == "generic" else ("init", "{ops_dir}", "--template", template)
    return ActionSpec(
        action_id="init",
        label="Initialize Workspace",
        description="Create a starter research_ops workspace. Existing non-empty targets are refused by default.",
        command=command,
        mutates=True,
        requires_confirmation=True,
        recovery_advice="Choose a missing or empty target directory. Existing operational folders are not overwritten from the dashboard.",
        success_next_step="Run schema-check, readiness, health, surface update, and surface validate.",
    )


def action_catalog(ops_dir: Path) -> dict[str, Any]:
    workspace = workspace_snapshot(ops_dir)
    actions = [
        {
            "id": "init",
            "label": "Initialize Workspace",
            "description": "Create a starter research_ops workspace. Existing non-empty targets are refused by default.",
            "command": command_string(action_command(init_spec("generic"), ops_dir)),
            "mutates": True,
            "requires_confirmation": True,
            "templates": sorted(cli.TEMPLATES),
            "template_commands": {
                template: command_string(action_command(init_spec(template), ops_dir))
                for template in sorted(cli.TEMPLATES)
            },
            "confirmation_tokens": {
                template: init_confirmation_token(ops_dir, template)
                for template in sorted(cli.TEMPLATES)
            },
            "confirmation_token": init_confirmation_token(ops_dir, "generic"),
            "status": "available" if not workspace["exists"] else "guarded_existing_target",
        }
    ]
    for spec in ACTION_SPECS.values():
        actions.append(
            {
                "id": spec.action_id,
                "label": spec.label,
                "description": spec.description,
                "command": command_string(action_command(spec, ops_dir)),
                "mutates": spec.mutates,
                "requires_confirmation": spec.requires_confirmation,
                "status": "available" if workspace["exists"] else "blocked_missing_workspace",
            }
        )
    return {
        "ok": True,
        "action": "console_actions_catalog",
        "ops_dir": str(ops_dir),
        "workspace": workspace,
        "actions": actions,
        "task_actions": task_action_catalog(),
        "decision_actions": decision_action_catalog(ops_dir),
    }


def resolve_task_dir(ops_dir: Path, request: dict[str, Any]) -> tuple[Path | None, dict[str, Any] | None]:
    if not ops_dir.is_dir():
        return None, {
            "ok": False,
            "reason": "ops_dir_missing",
            "message": "Initialize research_ops before running task inspection actions.",
            "read_only": True,
            "changed": False,
        }
    task_ref = request.get("task_dir") or request.get("status_path") or request.get("task_id")
    if not isinstance(task_ref, str) or not task_ref.strip():
        return None, {
            "ok": False,
            "reason": "missing_task",
            "message": "Task inspection actions require task_id, task_dir, or status_path.",
            "read_only": True,
            "changed": False,
        }
    tasks_root = (ops_dir / "tasks").resolve()
    ref = task_ref.strip()

    for status_path in sorted((ops_dir / "tasks").glob("*/status.json")):
        task_dir = status_path.parent
        try:
            resolved_task_dir = task_dir.resolve()
            resolved_task_dir.relative_to(tasks_root)
        except (OSError, ValueError):
            continue
        if ref in {task_dir.name, str(task_dir), str(status_path)}:
            return resolved_task_dir, None
        try:
            payload = json.loads(status_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = None
        if isinstance(payload, dict) and ref == str(payload.get("id") or ""):
            return resolved_task_dir, None

    candidate = Path(ref)
    if not candidate.is_absolute():
        candidate = ops_dir / "tasks" / ref
    candidate = candidate.resolve()
    if candidate.name == "status.json":
        candidate = candidate.parent
    try:
        candidate.relative_to(tasks_root)
    except ValueError:
        return None, {
            "ok": False,
            "reason": "task_outside_workspace",
            "message": "Task inspection is limited to task folders under research_ops/tasks.",
            "read_only": True,
            "changed": False,
        }
    if not candidate.is_dir():
        return None, {
            "ok": False,
            "reason": "task_missing",
            "message": f"Task folder does not exist: {candidate}",
            "read_only": True,
            "changed": False,
        }
    return candidate, None


def run_task_action(spec: ActionSpec, ops_dir: Path, request: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    task_dir, error = resolve_task_dir(ops_dir, request)
    if error is not None or task_dir is None:
        return 409 if error and error.get("reason") == "ops_dir_missing" else 400, error or {}
    argv = task_action_command(spec, task_dir)
    module_name, module_argv = argv[0], argv[1:]
    started_at = utc_timestamp()
    start = time.monotonic()
    exit_code, stdout, stderr = run_module_command(module_name, module_argv)
    elapsed_ms = int((time.monotonic() - start) * 1000)
    result = command_result(spec, ops_dir, argv, started_at, elapsed_ms, exit_code, stdout, stderr)
    result["task_dir"] = str(task_dir)
    result["status_path"] = str(task_dir / "status.json")
    result["read_only"] = True
    result["changed"] = False
    return 200, result


def clean_required_text(request: dict[str, Any], key: str) -> str:
    value = request.get(key)
    return value.strip() if isinstance(value, str) else ""


def load_task_status(task_dir: Path) -> dict[str, Any]:
    try:
        payload = json.loads((task_dir / "status.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def resolved_task_id(task_dir: Path) -> str:
    status = load_task_status(task_dir)
    task_id = status.get("id")
    return str(task_id).strip() if isinstance(task_id, str) and task_id.strip() else task_dir.name


def optional_date_args(request: dict[str, Any]) -> list[str]:
    date = clean_required_text(request, "date")
    return ["--date", date] if date else []


def decision_action_command(
    spec: DecisionActionSpec,
    ops_dir: Path,
    task_dir: Path,
    reason: str,
    approver: str,
    request: dict[str, Any],
) -> list[str]:
    task_id = resolved_task_id(task_dir)
    related_artifact = str(task_dir / "status.json")
    if spec.append_only:
        return [
            "decision",
            "append",
            str(ops_dir),
            "--item-id",
            task_id,
            "--decision",
            spec.decision,
            "--reason",
            reason,
            "--approver",
            approver,
            "--related-artifact",
            related_artifact,
            *optional_date_args(request),
        ]
    argv = [
        "decision",
        "resolve-task",
        str(ops_dir),
        str(task_dir),
        "--decision",
        spec.decision,
        "--reason",
        reason,
        "--approver",
        approver,
        "--related-artifact",
        related_artifact,
        *optional_date_args(request),
    ]
    if spec.target_status:
        argv.extend(["--status", spec.target_status])
    return argv


def latest_decision_row(decisions_path: Path, task_id: str, decision: str) -> dict[str, str] | None:
    for row in reversed(read_decisions(decisions_path)):
        if row.get("item_id") == task_id and row.get("decision") == decision:
            return row
    return None


def decision_audit(spec: DecisionActionSpec, ops_dir: Path, task_dir: Path) -> dict[str, Any]:
    decisions_path = ops_dir / "decisions.md"
    task_id = resolved_task_id(task_dir)
    status = load_task_status(task_dir)
    logged = has_decision(decisions_path, task_id, [spec.decision])
    current_status = status.get("status", "unavailable")
    status_matches = True if spec.append_only else current_status == spec.target_status
    return {
        "decisions": str(decisions_path),
        "task_id": task_id,
        "decision": spec.decision,
        "decision_logged": logged,
        "latest_row": latest_decision_row(decisions_path, task_id, spec.decision),
        "task_status": current_status,
        "expected_status": spec.target_status,
        "status_matches": status_matches,
        "validated": bool(logged and status_matches),
    }


def run_decision_action(spec: DecisionActionSpec, ops_dir: Path, request: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    task_dir, error = resolve_task_dir(ops_dir, request)
    if error is not None or task_dir is None:
        return 409 if error and error.get("reason") == "ops_dir_missing" else 400, error or {}
    reason = clean_required_text(request, "reason")
    approver = clean_required_text(request, "approver")
    if not reason or not approver:
        return 400, {
            "ok": False,
            "reason": "reason_and_approver_required",
            "message": "Decision actions require non-empty reason and approver fields.",
            "read_only": True,
            "changed": False,
        }
    argv = decision_action_command(spec, ops_dir, task_dir, reason, approver, request)
    token = decision_confirmation_token(spec.action_id)
    if request.get("confirm") != token:
        return 409, {
            "ok": False,
            "reason": "confirmation_required",
            "message": "Confirm the human decision before writing decisions.md or task status.",
            "confirmation_token": token,
            "command": command_string(argv),
            "read_only": True,
            "changed": False,
        }

    started_at = utc_timestamp()
    start = time.monotonic()
    exit_code, stdout, stderr = run_cli_command(argv)
    elapsed_ms = int((time.monotonic() - start) * 1000)
    parsed_stdout = parse_stdout_json(stdout)
    status = exit_status(exit_code, (0,))
    result = {
        "ok": status != "failed",
        "status": status,
        "action": spec.action_id,
        "label": spec.label,
        "mutates": True,
        "command": command_string(argv),
        "argv": ["async-research", *argv],
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "parsed_stdout": parsed_stdout,
        "started_at": started_at,
        "finished_at": utc_timestamp(),
        "elapsed_ms": elapsed_ms,
        "next_step": spec.success_next_step if exit_code == 0 else recovery_advice(
            ActionSpec(
                action_id=spec.action_id,
                label=spec.label,
                description=spec.description,
                command=tuple(argv),
                mutates=True,
                recovery_advice=spec.recovery_advice,
                success_next_step=spec.success_next_step,
            ),
            exit_code,
            parsed_stdout,
        ),
        "task_dir": str(task_dir),
        "status_path": str(task_dir / "status.json"),
        "read_only": False,
        "changed": exit_code == 0,
    }
    if exit_code == 0:
        result["decision_audit"] = decision_audit(spec, ops_dir, task_dir)
    return 200, result


def run_action(action_id: str, ops_dir: Path, payload: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    request = payload or {}
    task_spec = TASK_ACTION_SPECS.get(action_id)
    if task_spec is not None:
        return run_task_action(task_spec, ops_dir, request)
    decision_spec = DECISION_ACTION_SPECS.get(action_id)
    if decision_spec is not None:
        return run_decision_action(decision_spec, ops_dir, request)
    if action_id == "init":
        template = str(request.get("template") or "generic")
        if template not in cli.TEMPLATES:
            return 400, {
                "ok": False,
                "reason": "unsupported_template",
                "message": f"Unsupported template: {template}",
                "allowed_templates": sorted(cli.TEMPLATES),
                "read_only": True,
                "changed": False,
            }
        if request.get("force"):
            return 400, {
                "ok": False,
                "reason": "force_not_supported",
                "message": "Dashboard init never overwrites an existing operational folder. Use the CLI with --force if you intend to replace it.",
                "read_only": True,
                "changed": False,
            }
        token = init_confirmation_token(ops_dir, template)
        if request.get("confirm") != token:
            return 409, {
                "ok": False,
                "reason": "confirmation_required",
                "message": "Confirm the target folder and starter template before initializing.",
                "confirmation_token": token,
                "command": command_string(action_command(init_spec(template), ops_dir)),
                "read_only": True,
                "changed": False,
            }
        spec = init_spec(template)
    else:
        spec = ACTION_SPECS.get(action_id)
        if spec is None:
            return 404, {
                "ok": False,
                "reason": "unknown_console_action",
                "message": f"Unknown console action: {action_id}",
                "read_only": True,
                "changed": False,
            }
        if not ops_dir.is_dir():
            return 409, {
                "ok": False,
                "reason": "ops_dir_missing",
                "message": "Initialize research_ops before running setup checks.",
                "command": command_string(action_command(spec, ops_dir)),
                "read_only": True,
                "changed": False,
            }

    argv = action_command(spec, ops_dir)
    started_at = utc_timestamp()
    start = time.monotonic()
    exit_code, stdout, stderr = run_cli_command(argv)
    elapsed_ms = int((time.monotonic() - start) * 1000)
    result = command_result(spec, ops_dir, argv, started_at, elapsed_ms, exit_code, stdout, stderr)
    result["read_only"] = not spec.mutates
    result["changed"] = bool(spec.mutates and exit_code in spec.ok_exit_codes)
    return 200, result
