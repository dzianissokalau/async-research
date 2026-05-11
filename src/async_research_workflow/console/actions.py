"""Guarded setup and health actions for the local console."""

from __future__ import annotations

import contextlib
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


COMMAND_LOCK = threading.Lock()


@dataclass(frozen=True)
class ActionSpec:
    action_id: str
    label: str
    description: str
    command: tuple[str, ...]
    mutates: bool
    ok_exit_codes: tuple[int, ...] = (0,)
    requires_confirmation: bool = False
    recovery_advice: str = "Review stdout and stderr, repair the reported issue, then rerun the command."
    success_next_step: str = "Refresh the dashboard snapshot."


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
}


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def init_confirmation_token(ops_dir: Path, template: str) -> str:
    return f"init:{ops_dir}:{template}"


def action_command(spec: ActionSpec, ops_dir: Path) -> list[str]:
    return [part.format(ops_dir=str(ops_dir)) for part in spec.command]


def command_string(argv: list[str]) -> str:
    return shlex.join(["async-research", *argv])


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


def command_result(spec: ActionSpec, ops_dir: Path, argv: list[str], started_at: str, elapsed_ms: int, exit_code: int, stdout: str, stderr: str) -> dict[str, Any]:
    parsed_stdout = parse_stdout_json(stdout)
    status = exit_status(exit_code, spec.ok_exit_codes)
    return {
        "ok": status != "failed",
        "status": status,
        "action": spec.action_id,
        "label": spec.label,
        "mutates": spec.mutates,
        "command": command_string(argv),
        "argv": ["async-research", *argv],
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "parsed_stdout": parsed_stdout,
        "started_at": started_at,
        "finished_at": utc_timestamp(),
        "elapsed_ms": elapsed_ms,
        "next_step": recovery_advice(spec, exit_code, parsed_stdout),
    }


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
    }


def run_action(action_id: str, ops_dir: Path, payload: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    request = payload or {}
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
