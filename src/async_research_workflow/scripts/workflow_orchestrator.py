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


SUCCESS = 0
VALIDATION_FAILED = 2
INVALID_STATE = 4
READINESS_WARNINGS = 2


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


def inferred_ops_dir_for_task(task_dir: Path) -> Path | None:
    if task_dir.parent.name == "tasks":
        return task_dir.parent.parent
    return None


def normalized_path(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def task_workspace_error(task_dir: Path, ops_dir: Path | None, reason: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": False,
        "action": "workflow_advance_refused",
        "reason": reason,
        "task_dir": str(task_dir),
        "next_step": "pass a task directory directly under the matching research_ops/tasks/ folder",
    }
    if ops_dir is not None:
        payload["ops_dir"] = str(ops_dir)
    return payload


def resolve_task_ops_dir(task_dir: Path, explicit_ops_dir: Path | None = None) -> tuple[Path | None, dict[str, Any] | None]:
    inferred_ops_dir = inferred_ops_dir_for_task(task_dir)
    if explicit_ops_dir is None:
        if inferred_ops_dir is None:
            return None, task_workspace_error(task_dir, None, "task_dir_not_under_tasks")
        return inferred_ops_dir, None
    if inferred_ops_dir is None:
        return None, task_workspace_error(task_dir, explicit_ops_dir, "task_dir_not_under_tasks")
    if normalized_path(inferred_ops_dir) != normalized_path(explicit_ops_dir):
        return None, task_workspace_error(task_dir, explicit_ops_dir, "task_dir_ops_mismatch")
    return explicit_ops_dir, None


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
