#!/usr/bin/env python3
"""Optional thin runner adapters for analysis tasks."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time
from typing import Any, Iterable, Optional

from async_research_workflow.scripts import analysis_runs
from async_research_workflow.scripts.analysis_runs import MANIFEST_RELATIVE_PATH, PreflightMalformed


SUCCESS = 0
VALIDATION_FINDINGS = 2
INVALID_REQUEST = 3
MALFORMED = 4

SUPPORTED_EXECUTION_RUNNERS = {"local_script"}
KNOWN_RUNNER_TYPES = {
    "manual",
    "local_script",
    "notebook",
    "sql",
    "dbt",
    "warehouse_job",
    "python_function",
    "other",
}
MAX_CAPTURE_CHARS = 4000


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def resolved(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def is_relative_to(path: Path, base: Path) -> bool:
    try:
        resolved(path).relative_to(resolved(base))
        return True
    except ValueError:
        return False


def workspace_root(ops_dir: Path) -> Path:
    return resolved(ops_dir.parent if ops_dir.name == "research_ops" else ops_dir.parent)


def path_text(path: Path, base: Path) -> str:
    try:
        return resolved(path).relative_to(resolved(base)).as_posix()
    except ValueError:
        return path.as_posix()


def run_json(entrypoint, argv: list[str | Path]) -> tuple[int, dict[str, Any]]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = entrypoint.main([str(arg) for arg in argv])
    text = stream.getvalue().strip()
    if not text:
        return code, {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return code, {"ok": code == SUCCESS, "raw_output": text}
    return code, payload if isinstance(payload, dict) else {"ok": False, "payload": payload}


def load_manifest(task_dir: Path) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    try:
        payload = analysis_runs.read_json_object(task_dir / MANIFEST_RELATIVE_PATH)
    except PreflightMalformed as exc:
        return None, str(exc)
    return payload, None


def output_tail(value: str) -> str:
    if len(value) <= MAX_CAPTURE_CHARS:
        return value
    return value[-MAX_CAPTURE_CHARS:]


def command_tokens(entrypoint: Any) -> tuple[list[str], Optional[str]]:
    if not isinstance(entrypoint, str) or not entrypoint.strip():
        return [], "runner.entrypoint must be a non-empty command string"
    try:
        tokens = shlex.split(entrypoint)
    except ValueError as exc:
        return [], f"runner.entrypoint cannot be parsed as a command: {exc}"
    if not tokens:
        return [], "runner.entrypoint produced an empty command"
    return tokens, None


def token_looks_like_path(token: str) -> bool:
    if not token or token.startswith("-") or "://" in token:
        return False
    return "/" in token or token.startswith(".")


def command_path_issues(command: list[str], cwd: Path, root: Path) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for index, token in enumerate(command):
        if not token_looks_like_path(token):
            continue
        path = Path(token)
        candidate = path if path.is_absolute() else cwd / path
        resolved_candidate = resolved(candidate)
        if not is_relative_to(resolved_candidate, root):
            issues.append(
                {
                    "token_index": index,
                    "token": token,
                    "reason": "path_outside_workspace",
                    "workspace_root": str(root),
                    "resolved_path": str(resolved_candidate),
                }
            )
    return issues


def validation_commands(task_dir: Path, ops_dir: Path) -> list[str]:
    return [
        f"async-research analysis validate-run {task_dir.as_posix()} --ops-dir {ops_dir.as_posix()}",
        f"async-research analysis validate-results {task_dir.as_posix()} --ops-dir {ops_dir.as_posix()}",
    ]


def preflight_gate(task_dir: Path, ops_dir: Path, now: Optional[str]) -> tuple[int, dict[str, Any]]:
    argv: list[str | Path] = ["preflight", task_dir, "--ops-dir", ops_dir]
    if now:
        argv.extend(["--now", now])
    return run_json(analysis_runs, argv)


def preflight_exit_code(code: int) -> int:
    if code == MALFORMED:
        return MALFORMED
    if code == analysis_runs.INVALID_REQUEST:
        return INVALID_REQUEST
    return VALIDATION_FINDINGS


def command_cwd(args: argparse.Namespace, root: Path) -> tuple[Optional[Path], Optional[dict[str, Any]]]:
    cwd = resolved(args.cwd) if args.cwd is not None else root
    if not is_relative_to(cwd, root):
        return None, {
            "reason": "cwd_outside_workspace",
            "cwd": str(cwd),
            "workspace_root": str(root),
        }
    return cwd, None


def adapter_plan(task_dir: Path, ops_dir: Path, manifest: dict[str, Any], cwd: Path) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]]]:
    runner = manifest.get("runner") if isinstance(manifest.get("runner"), dict) else {}
    runner_type = str(runner.get("type") or "").strip()
    if runner_type not in KNOWN_RUNNER_TYPES:
        return None, {
            "reason": "unknown_runner_type",
            "runner_type": runner_type,
            "supported_execution_runners": sorted(SUPPORTED_EXECUTION_RUNNERS),
        }
    if runner_type not in SUPPORTED_EXECUTION_RUNNERS:
        return None, {
            "reason": "runner_adapter_not_available",
            "runner_type": runner_type,
            "supported_execution_runners": sorted(SUPPORTED_EXECUTION_RUNNERS),
            "message": "validation works without adapters; run the analysis manually and then use validate-run / validate-results",
        }
    command, parse_error = command_tokens(runner.get("entrypoint"))
    if parse_error is not None:
        return None, {"reason": "runner_entrypoint_invalid", "message": parse_error}
    root = workspace_root(ops_dir)
    path_issues = command_path_issues(command, cwd, root)
    if path_issues:
        return None, {"reason": "runner_command_path_unsafe", "issues": path_issues}
    return (
        {
            "runner_type": runner_type,
            "command": command,
            "command_display": " ".join(shlex.quote(part) for part in command),
            "cwd": str(cwd),
            "task_dir": str(task_dir),
            "manifest_path": str(task_dir / MANIFEST_RELATIVE_PATH),
            "parameters_ref": runner.get("parameters_ref", "none"),
            "execution_environment": runner.get("execution_environment"),
        },
        None,
    )


def execute_command(plan: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            plan["command"],
            cwd=plan["cwd"],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError as exc:
        return {
            "ok": False,
            "reason": "runner_command_not_found",
            "error": str(exc),
            "duration_seconds": round(time.monotonic() - started, 3),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "reason": "runner_command_timeout",
            "timeout_seconds": timeout_seconds,
            "stdout_tail": output_tail(exc.stdout or ""),
            "stderr_tail": output_tail(exc.stderr or ""),
            "duration_seconds": round(time.monotonic() - started, 3),
        }
    return {
        "ok": completed.returncode == 0,
        "exit_code": completed.returncode,
        "stdout_tail": output_tail(completed.stdout or ""),
        "stderr_tail": output_tail(completed.stderr or ""),
        "duration_seconds": round(time.monotonic() - started, 3),
    }


def run_adapter(args: argparse.Namespace) -> int:
    task_dir = args.task_dir
    ops_dir = args.ops_dir
    root = workspace_root(ops_dir)
    cwd, cwd_error = command_cwd(args, root)
    if cwd_error is not None:
        print_json({"ok": False, "action": "analysis_adapter_invalid", **cwd_error})
        return INVALID_REQUEST

    preflight_code, preflight = preflight_gate(task_dir, ops_dir, args.now)
    base: dict[str, Any] = {
        "ok": False,
        "action": "analysis_adapter_planned" if not args.execute else "analysis_adapter_execute_requested",
        "task_dir": str(task_dir),
        "ops_dir": str(ops_dir),
        "workspace_root": str(root),
        "execute_requested": args.execute,
        "executed": False,
        "preflight_exit_code": preflight_code,
        "preflight": preflight,
        "validation_required": True,
        "validation_commands": validation_commands(task_dir, ops_dir),
    }
    if preflight_code != SUCCESS or preflight.get("ok") is not True:
        base.update(
            {
                "reason": "analysis_preflight_not_clean",
                "next_step": preflight.get("next_step", "resolve analysis preflight before using runner adapters"),
            }
        )
        print_json(base)
        return preflight_exit_code(preflight_code)

    manifest, manifest_error = load_manifest(task_dir)
    if manifest is None:
        base.update({"reason": "manifest_malformed", "error": manifest_error})
        print_json(base)
        return MALFORMED

    plan, plan_error = adapter_plan(task_dir, ops_dir, manifest, cwd)
    if plan_error is not None:
        base.update(plan_error)
        print_json(base)
        return INVALID_REQUEST
    base["adapter"] = plan
    if not args.execute:
        base.update(
            {
                "ok": True,
                "next_step": "rerun with --execute to run the local adapter, then run validation commands",
            }
        )
        print_json(base)
        return SUCCESS

    execution = execute_command(plan, args.timeout_seconds)
    base.update(
        {
            "action": "analysis_adapter_executed" if execution.get("ok") else "analysis_adapter_failed",
            "ok": execution.get("ok") is True,
            "executed": True,
            "execution": execution,
            "next_step": "run analysis validate-run and validate-results before result acceptance"
            if execution.get("ok")
            else "fix the adapter command or task artifacts, then rerun preflight before another attempt",
        }
    )
    print_json(base)
    return SUCCESS if execution.get("ok") else VALIDATION_FINDINGS


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run optional thin adapters for analysis tasks.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser(
        "run-adapter",
        help="Plan or execute a preflight-gated local analysis adapter.",
        description=(
            "Optional adapter runner for run_analysis tasks. It executes only local_script runner.entrypoint "
            "commands after clean analysis preflight and never replaces validate-run or validate-results."
        ),
    )
    run.add_argument("task_dir", type=Path, help="run_analysis task directory.")
    run.add_argument("--ops-dir", type=Path, required=True, help="research_ops directory.")
    run.add_argument("--execute", action="store_true", help="Actually execute the adapter command; omitted means dry-run plan only.")
    run.add_argument("--timeout-seconds", type=float, default=900.0, help="Maximum adapter execution time.")
    run.add_argument("--cwd", type=Path, help="Command working directory; defaults to the workspace root.")
    run.add_argument("--now", help="Override current time for deterministic preflight checks.")
    run.set_defaults(func=run_adapter)
    return parser.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    if args.command == "run-adapter":
        return run_adapter(args)
    print_json({"ok": False, "reason": "unknown_command", "command": args.command})
    return INVALID_REQUEST


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
