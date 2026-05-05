"""Command line interface for the async research workflow alpha package."""

from __future__ import annotations

import argparse
import contextlib
import importlib
import io
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Iterable, Sequence

from async_research_workflow import __version__
from async_research_workflow.resources import template_path


SUCCESS = 0
INVALID = 4
TEMPLATES = {
    "generic": ("generic_research_ops_starter", "research_ops"),
    "real-estate": ("research_ops_starter", "research_ops"),
}


class HelpFormatter(argparse.ArgumentDefaultsHelpFormatter, argparse.RawDescriptionHelpFormatter):
    """Show defaults while preserving short command epilogs."""


COMMON_EXIT_EPILOG = """Exit codes:
  0 success
  1 suite or smoke failure
  2 validation failed, warnings, locked, or skip depending on command
  3 missing required input, invalid request, or skip loop depending on command
  4 malformed input, invalid state, or safe refusal
  5 human action required

See README.md for the command-specific contract.
"""

READINESS_EXIT_EPILOG = """Readiness exit codes:
  0 safe to continue
  2 warnings only; expensive workers are still allowed
  3 skip the loop for now
  4 invalid workspace state
  5 human action required before autonomous work continues
"""


def print_json(payload: dict) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def module_main(module_name: str, argv: Sequence[str]) -> int:
    module = importlib.import_module(f"async_research_workflow.scripts.{module_name}")
    return int(module.main(list(argv)))


def module_json(module_name: str, argv: Sequence[str]) -> tuple[int, dict]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = module_main(module_name, argv)
    text = stream.getvalue().strip()
    if not text:
        return code, {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = {"ok": code == 0, "raw_output": text}
    return code, payload


def template_root(template: str):
    parts = TEMPLATES.get(template)
    if parts is None:
        raise ValueError(f"unsupported template: {template}")
    return template_path(*parts)


def copy_resource_tree(src, dst: Path, force: bool = False) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        if item.name in {".DS_Store", "__pycache__"}:
            continue
        target = dst / item.name
        if item.is_dir():
            copy_resource_tree(item, target, force=force)
            continue
        if target.exists() and not force:
            raise FileExistsError(f"target file already exists: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(item.read_bytes())


def remove_path(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if path.is_symlink() or path.is_file():
        path.unlink()
        return
    shutil.rmtree(path)


def restore_target(target: Path, backup: Path | None, target_installed: bool) -> None:
    if backup is not None and backup.exists():
        remove_path(target)
        shutil.move(str(backup), str(target))
        return
    if target_installed:
        remove_path(target)


def rollback_target(target: Path, backup: Path | None, target_installed: bool) -> tuple[bool, str | None]:
    try:
        restore_target(target, backup, target_installed)
    except Exception as exc:
        return False, str(exc)
    return True, None


def run_init(args: argparse.Namespace) -> int:
    target = args.target_dir
    staging: Path | None = None
    backup_root: Path | None = None
    backup: Path | None = None
    target_installed = False
    preserve_backup_root = False
    try:
        source = template_root(args.template)
        if target.exists() and not target.is_dir() and not args.force:
            print_json({
                "ok": False,
                "reason": "target_exists",
                "target_dir": str(target),
                "next_step": "rerun with --force or choose an empty target directory",
            })
            return INVALID
        if target.exists() and target.is_dir() and any(target.iterdir()) and not args.force:
            print_json({
                "ok": False,
                "reason": "target_exists",
                "target_dir": str(target),
                "next_step": "rerun with --force or choose an empty target directory",
            })
            return INVALID
        target.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.staging-", dir=target.parent))
        copy_resource_tree(source, staging, force=True)
        if target.exists():
            backup_root = Path(tempfile.mkdtemp(prefix=f".{target.name}.backup-", dir=target.parent))
            backup = backup_root / target.name
            shutil.move(str(target), str(backup))
        shutil.move(str(staging), str(target))
        staging = None
        target_installed = True
        metrics_init_code, metrics_init = module_json("metrics_history", ["init", str(target), "--label", "starter_init", "--force"])
        metrics_append_code, metrics_append = module_json("metrics_history", ["append-snapshot", str(target), "--label", "starter_init"])
        if metrics_init_code != SUCCESS or metrics_append_code != SUCCESS:
            rollback_ok, rollback_error = rollback_target(target, backup, target_installed)
            preserve_backup_root = not rollback_ok
            payload = {
                "ok": False,
                "reason": "starter_metrics_init_failed",
                "target_dir": str(target),
                "metrics_init": metrics_init,
                "metrics_append": metrics_append,
            }
            if rollback_error is not None:
                payload["rollback_error"] = rollback_error
                if backup_root is not None:
                    payload["backup_dir"] = str(backup_root)
            print_json(payload)
            return INVALID
    except Exception as exc:
        rollback_ok, rollback_error = rollback_target(target, backup, target_installed)
        preserve_backup_root = not rollback_ok
        payload = {"ok": False, "reason": "init_failed", "error": str(exc), "target_dir": str(target)}
        if rollback_error is not None:
            payload["rollback_error"] = rollback_error
            if backup_root is not None:
                payload["backup_dir"] = str(backup_root)
        print_json(payload)
        return INVALID
    finally:
        if staging is not None:
            remove_path(staging)
        if backup_root is not None and not preserve_backup_root:
            shutil.rmtree(backup_root, ignore_errors=True)
    print_json({"ok": True, "action": "initialized", "target_dir": str(target), "template": args.template})
    return SUCCESS


def run_starter_smoke(args: argparse.Namespace) -> int:
    base = args.work_dir
    ops_dir = base if base.name == "research_ops" else base / "research_ops"
    if base.exists() and not base.is_dir():
        print_json({
            "ok": False,
            "reason": "target_is_file",
            "work_dir": str(base),
            "ops_dir": str(ops_dir),
            "next_step": "choose a directory work path",
        })
        return INVALID
    if base.exists() and any(base.iterdir()) and not args.force:
        print_json({
            "ok": False,
            "reason": "target_exists",
            "work_dir": str(base),
            "ops_dir": str(ops_dir),
            "next_step": "rerun with --force or choose an empty work directory",
        })
        return INVALID
    if base.exists() and args.force:
        remove_path(base)
    failures: list[dict] = []
    reports: list[dict] = []

    init_args = argparse.Namespace(target_dir=ops_dir, template=args.template, force=True)
    init_code = run_init(init_args)
    if init_code != SUCCESS:
        return init_code

    checks = [
        ("check_schema_versions", [str(ops_dir)]),
        ("autonomy_readiness_gate", [str(ops_dir), "--dry-run"]),
        ("health_check", [str(ops_dir), "--dry-run"]),
        ("human_review_surface", ["update", str(ops_dir)]),
        ("human_review_surface", ["validate", str(ops_dir)]),
        ("data_source_audit", ["validate", str(ops_dir)]),
        ("cost_tracking", ["summary", str(ops_dir)]),
        ("run_autonomy_benchmark", []),
        ("simulate_scheduled_week", [str(ops_dir)]),
    ]
    for module_name, argv in checks:
        code, payload = module_json(module_name, argv)
        reports.append({"command": module_name, "args": argv, "exit_code": code, "ok": code == 0})
        if code != 0:
            failures.append({"command": module_name, "args": argv, "exit_code": code, "payload": payload})
    print_json({
        "ok": not failures,
        "action": "starter_smoke_checked",
        "work_dir": str(base),
        "ops_dir": str(ops_dir),
        "template": args.template,
        "checks": reports,
        "failures": failures,
    })
    return SUCCESS if not failures else 1


def run_acceptance_suite_command(args: argparse.Namespace) -> int:
    return module_main("run_acceptance_suite", [])


def run_version(args: argparse.Namespace) -> int:
    print_json({"ok": True, "version": __version__})
    return SUCCESS


def add_common_ops(parser: argparse.ArgumentParser, default: str = "research_ops") -> None:
    parser.add_argument(
        "ops_dir",
        nargs="?",
        type=Path,
        default=Path(default),
        help="Path to the research_ops workspace.",
    )


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="async-research",
        description="Async research workflow alpha CLI for file-backed research_ops workspaces.",
        epilog=COMMON_EXIT_EPILOG,
        formatter_class=HelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    version = sub.add_parser(
        "version",
        help="Print the installed package version as JSON.",
        description="Print the installed async-research package version as JSON.",
        formatter_class=HelpFormatter,
    )
    version.set_defaults(func=run_version)

    init = sub.add_parser(
        "init",
        help="Initialize a research_ops workspace from a starter template.",
        description="Create a generic or worked-example research_ops workspace safely.",
        epilog="Without --force, existing non-empty targets are refused with exit code 4.",
        formatter_class=HelpFormatter,
    )
    init.add_argument("target_dir", nargs="?", type=Path, default=Path("research_ops"), help="Target research_ops directory to create.")
    init.add_argument("--template", choices=sorted(TEMPLATES), default="generic", help="Starter template to install.")
    init.add_argument("--force", action="store_true", help="Replace an existing target after staging succeeds.")
    init.set_defaults(func=run_init)

    smoke = sub.add_parser(
        "starter-smoke",
        help="Initialize and validate a disposable starter workspace.",
        description="Create a starter workspace, then run schema, readiness, health, surface, source, cost, benchmark, and simulation checks.",
        epilog="Without --force, existing non-empty work directories are refused with exit code 4.",
        formatter_class=HelpFormatter,
    )
    smoke.add_argument("work_dir", type=Path, help="Disposable work directory; research_ops is created inside unless this path is already named research_ops.")
    smoke.add_argument("--template", choices=sorted(TEMPLATES), default="generic", help="Starter template to smoke.")
    smoke.add_argument("--force", action="store_true", help="Remove and recreate the disposable work directory.")
    smoke.set_defaults(func=run_starter_smoke)

    acceptance = sub.add_parser(
        "acceptance-suite",
        help="Run isolated package acceptance checks.",
        description="Run the durable package acceptance suite against isolated temporary fixtures.",
        epilog="Exits 0 when all checks pass, 1 when any acceptance check fails.",
        formatter_class=HelpFormatter,
    )
    acceptance.set_defaults(func=run_acceptance_suite_command)

    readiness = sub.add_parser(
        "readiness",
        help="Decide whether another autonomous loop is safe.",
        description="Inspect a research_ops workspace and classify whether scheduled or expensive work may continue.",
        epilog=READINESS_EXIT_EPILOG,
        formatter_class=HelpFormatter,
    )
    add_common_ops(readiness)
    readiness.add_argument("--dry-run", action="store_true", help="Print the report without writing health_report.json or daily_status.md.")
    readiness.set_defaults(func=lambda a: module_main("autonomy_readiness_gate", [str(a.ops_dir)] + (["--dry-run"] if a.dry_run else [])))

    health = sub.add_parser(
        "health",
        help="Generate operational health status.",
        description="Summarize queue, task, lock, review, source, cost, metric, and accepted-memory health.",
        formatter_class=HelpFormatter,
    )
    add_common_ops(health)
    health.add_argument("--dry-run", action="store_true", help="Print the report without writing health_report.json or daily_status.md.")
    health.set_defaults(func=lambda a: module_main("health_check", [str(a.ops_dir)] + (["--dry-run"] if a.dry_run else [])))

    surface = sub.add_parser(
        "surface",
        aliases=["review-surface"],
        help="Update or validate human-facing review surfaces.",
        description="Manage daily_status.md, human_review_queue.md, and weekly_digest.md.",
        formatter_class=HelpFormatter,
    )
    surface_sub = surface.add_subparsers(dest="surface_command", required=True)
    surface_update = surface_sub.add_parser(
        "update",
        help="Write human-facing status and review queue files.",
        description="Refresh daily_status.md, human_review_queue.md, and the weekly digest surface.",
        formatter_class=HelpFormatter,
    )
    add_common_ops(surface_update)
    surface_update.set_defaults(func=lambda a: module_main("human_review_surface", ["update", str(a.ops_dir)]))
    surface_validate = surface_sub.add_parser(
        "validate",
        help="Validate human-facing status and review queue files.",
        description="Compare rendered human review surfaces with the current workspace state.",
        formatter_class=HelpFormatter,
    )
    add_common_ops(surface_validate)
    surface_validate.set_defaults(func=lambda a: module_main("human_review_surface", ["validate", str(a.ops_dir)]))

    schema = sub.add_parser(
        "schema-check",
        help="Validate schema versions for workflow JSON artifacts.",
        description="Check task status and other versioned JSON artifacts for expected schema versions.",
        formatter_class=HelpFormatter,
    )
    add_common_ops(schema)
    schema.set_defaults(func=lambda a: module_main("check_schema_versions", [str(a.ops_dir)]))

    source = sub.add_parser(
        "source",
        help="Validate or report source-governance state.",
        description="Inspect data_source_audit.md for validity and source freshness.",
        formatter_class=HelpFormatter,
    )
    source_sub = source.add_subparsers(dest="source_command", required=True)
    validate = source_sub.add_parser(
        "validate",
        help="Validate data_source_audit.md.",
        description="Validate source audit rows, statuses, tiers, and required governance fields.",
        formatter_class=HelpFormatter,
    )
    add_common_ops(validate)
    validate.set_defaults(func=lambda a: module_main("data_source_audit", ["validate", str(a.ops_dir)]))
    freshness = source_sub.add_parser(
        "freshness",
        help="Report stale or due source reviews.",
        description="Report whether source audit entries are stale relative to freshness windows.",
        formatter_class=HelpFormatter,
    )
    add_common_ops(freshness)
    freshness.set_defaults(func=lambda a: module_main("data_source_audit", ["freshness-report", str(a.ops_dir)]))

    cost = sub.add_parser(
        "cost",
        help="Summarize cost and budget state.",
        description="Inspect cost_ledger.csv for spend, usage, and budget pressure.",
        formatter_class=HelpFormatter,
    )
    cost_sub = cost.add_subparsers(dest="cost_command", required=True)
    cost_summary = cost_sub.add_parser(
        "summary",
        help="Summarize the cost ledger.",
        description="Print aggregate spend, usage, and budget information from cost_ledger.csv.",
        formatter_class=HelpFormatter,
    )
    add_common_ops(cost_summary)
    cost_summary.set_defaults(func=lambda a: module_main("cost_tracking", ["summary", str(a.ops_dir)]))

    metrics = sub.add_parser(
        "metrics",
        help="Append or inspect autonomy metrics.",
        description="Maintain metrics_baseline.json and metrics_history.jsonl snapshots.",
        formatter_class=HelpFormatter,
    )
    metrics_sub = metrics.add_subparsers(dest="metrics_command", required=True)
    metrics_append = metrics_sub.add_parser(
        "append",
        help="Append an autonomy metrics snapshot.",
        description="Append a metrics_history.jsonl snapshot for the current workspace state.",
        formatter_class=HelpFormatter,
    )
    add_common_ops(metrics_append)
    metrics_append.add_argument("--label", default="manual", help="Label stored with the snapshot.")
    metrics_append.add_argument("--update-weekly-digest", action="store_true", help="Refresh the autonomy metrics section in weekly_digest.md.")
    metrics_append.set_defaults(func=lambda a: module_main("metrics_history", ["append-snapshot", str(a.ops_dir), "--label", a.label] + (["--update-weekly-digest"] if a.update_weekly_digest else [])))

    accepted = sub.add_parser(
        "accepted",
        help="Maintain accepted-output memory and revalidation state.",
        description="Update accepted_outputs_index.md and accepted-memory revalidation schedules.",
        formatter_class=HelpFormatter,
    )
    accepted_sub = accepted.add_subparsers(dest="accepted_command", required=True)
    accepted_update = accepted_sub.add_parser(
        "update",
        help="Refresh accepted_outputs_index.md.",
        description="Upsert accepted task rows into accepted_outputs_index.md.",
        formatter_class=HelpFormatter,
    )
    add_common_ops(accepted_update)
    accepted_update.set_defaults(func=lambda a: module_main("update_accepted_outputs_index", ["update", str(a.ops_dir)]))
    accepted_reval = accepted_sub.add_parser(
        "revalidation",
        aliases=["revalidate"],
        help="Report due or stale accepted memory.",
        description="Print an accepted-memory freshness report and optionally write revalidation_schedule.md.",
        formatter_class=HelpFormatter,
    )
    add_common_ops(accepted_reval)
    accepted_reval.add_argument("--write-schedule", action="store_true", help="Write research_ops/revalidation_schedule.md.")
    accepted_reval.set_defaults(func=lambda a: module_main("update_accepted_outputs_index", ["revalidation-report", str(a.ops_dir)] + (["--write-schedule"] if a.write_schedule else [])))

    review = sub.add_parser(
        "review",
        help="Aggregate isolated reviewer notes.",
        description="Route reviewed tasks based on independent review files and policy.",
        formatter_class=HelpFormatter,
    )
    review_sub = review.add_subparsers(dest="review_command", required=True)
    aggregate = review_sub.add_parser(
        "aggregate",
        help="Aggregate review decisions for one task.",
        description="Read reviews/*.md, compute a deterministic aggregate, and optionally update task state and result ledgers.",
        formatter_class=HelpFormatter,
    )
    aggregate.add_argument("task_dir", type=Path, help="Task directory containing status.json and reviews/.")
    aggregate.add_argument("--dry-run", action="store_true", help="Validate and preview routing without writing aggregate/status files.")
    aggregate.set_defaults(func=lambda a: module_main("aggregate_reviews", [str(a.task_dir)] + (["--dry-run"] if a.dry_run else [])))

    result = sub.add_parser(
        "result-acceptance",
        help="Validate final result acceptance gates for one task.",
        description="Validate reviewed task output against result-acceptance gates and optionally write result_acceptance.json and ledgers.",
        formatter_class=HelpFormatter,
    )
    result.add_argument("task_dir", type=Path, help="Task directory to validate.")
    result.add_argument("--ops-dir", type=Path, help="research_ops directory; inferred from task_dir when omitted.")
    result.add_argument("--write", action="store_true", help="Write review_panel/result_acceptance.json when gates pass.")
    result.add_argument("--update-ledgers", action="store_true", help="Update evidence_ledger.md or rejected_results.md when gates pass.")
    result.set_defaults(func=lambda a: module_main("validate_result_acceptance", [str(a.task_dir)] + (["--ops-dir", str(a.ops_dir)] if a.ops_dir else []) + (["--write"] if a.write else []) + (["--update-ledgers"] if a.update_ledgers else [])))

    exploration = sub.add_parser(
        "exploration",
        help="Validate exploration-cycle artifacts.",
        description="Validate worker outputs for idea discovery and exploration-cycle tasks.",
        formatter_class=HelpFormatter,
    )
    exploration_sub = exploration.add_subparsers(dest="exploration_command", required=True)
    exploration_validate = exploration_sub.add_parser(
        "validate",
        help="Validate an exploration worker output.",
        description="Validate one exploration-cycle worker output against schemas, task state, and accepted-memory rules.",
        formatter_class=HelpFormatter,
    )
    exploration_validate.add_argument("worker_output", type=Path, help="Worker output artifact to validate.")
    exploration_validate.add_argument("--ops-dir", type=Path, required=True, help="research_ops directory.")
    exploration_validate.add_argument("--task-dir", type=Path, required=True, help="Task directory associated with the worker output.")
    exploration_validate.set_defaults(func=lambda a: module_main("validate_exploration_cycle", [str(a.worker_output), "--ops-dir", str(a.ops_dir), "--task-dir", str(a.task_dir)]))

    idea = sub.add_parser(
        "idea",
        help="Score or validate idea artifacts.",
        description="Score idea candidates and validate idea-evaluation JSON artifacts.",
        formatter_class=HelpFormatter,
    )
    idea_sub = idea.add_subparsers(dest="idea_command", required=True)
    idea_score = idea_sub.add_parser(
        "score",
        help="Score an idea candidate.",
        description="Score an idea JSON file against mission policy, cost posture, and accepted-memory context.",
        formatter_class=HelpFormatter,
    )
    idea_score.add_argument("idea_json", type=Path, help="Idea candidate JSON file.")
    idea_score.add_argument("--ops-dir", type=Path, required=True, help="research_ops directory.")
    idea_score.add_argument("--budget-mode", choices=["normal", "budget_constrained", "auto"], default="auto", help="Budget posture to apply while scoring.")
    idea_score.set_defaults(func=lambda a: module_main("score_idea_candidate", [str(a.idea_json), "--ops-dir", str(a.ops_dir), "--budget-mode", a.budget_mode]))
    idea_validate = idea_sub.add_parser(
        "validate",
        help="Validate an idea-evaluation artifact.",
        description="Validate an idea-evaluation JSON file against schemas and workflow gates.",
        formatter_class=HelpFormatter,
    )
    idea_validate.add_argument("idea_json", type=Path, help="Idea-evaluation JSON file.")
    idea_validate.add_argument("--ops-dir", type=Path, required=True, help="research_ops directory.")
    idea_validate.set_defaults(func=lambda a: module_main("validate_idea_evaluation", [str(a.idea_json), "--ops-dir", str(a.ops_dir)]))

    experiment = sub.add_parser(
        "experiment",
        help="Validate experiment-plan artifacts.",
        description="Validate experiment worker outputs against source readiness, schemas, and task constraints.",
        formatter_class=HelpFormatter,
    )
    experiment_sub = experiment.add_subparsers(dest="experiment_command", required=True)
    experiment_validate = experiment_sub.add_parser(
        "validate",
        help="Validate an experiment worker output.",
        description="Validate one experiment-plan worker output against schemas, task state, and source governance.",
        formatter_class=HelpFormatter,
    )
    experiment_validate.add_argument("worker_output", type=Path, help="Worker output artifact to validate.")
    experiment_validate.add_argument("--ops-dir", type=Path, required=True, help="research_ops directory.")
    experiment_validate.add_argument("--task-dir", type=Path, required=True, help="Task directory associated with the worker output.")
    experiment_validate.set_defaults(func=lambda a: module_main("validate_experiment_plan", [str(a.worker_output), "--ops-dir", str(a.ops_dir), "--task-dir", str(a.task_dir)]))

    benchmark = sub.add_parser(
        "benchmark",
        help="Run packaged autonomy benchmark cases.",
        description="Run known-good and known-bad benchmark cases against isolated temporary fixtures.",
        epilog="Exits 0 when all cases satisfy acceptance criteria, 1 when the benchmark fails.",
        formatter_class=HelpFormatter,
    )
    benchmark.set_defaults(func=lambda a: module_main("run_autonomy_benchmark", []))

    simulate = sub.add_parser(
        "simulate-week",
        help="Simulate one scheduled week against an isolated workspace copy.",
        description="Drive readiness, discovery, review, result acceptance, metrics, and surface helpers with fixture outputs.",
        epilog="Exits 0 when the simulated week satisfies all checks, 1 when the simulation fails.",
        formatter_class=HelpFormatter,
    )
    add_common_ops(simulate)
    simulate.set_defaults(func=lambda a: module_main("simulate_scheduled_week", [str(a.ops_dir)]))

    return parser.parse_args(list(argv))


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
