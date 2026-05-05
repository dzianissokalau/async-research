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


def add_required_ops(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("ops_dir", type=Path, help="Path to the research_ops workspace.")


def add_command(subparsers, *args, **kwargs) -> argparse.ArgumentParser:
    kwargs.setdefault("formatter_class", HelpFormatter)
    return subparsers.add_parser(*args, **kwargs)


def add_budget_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--monthly-budget-usd", type=float, help="Override or seed the monthly budget in USD.")
    parser.add_argument("--weekly-budget-usd", type=float, help="Override or seed the weekly budget in USD.")


def optional_path(flag: str, value: Path | None) -> list[str]:
    return [flag, str(value)] if value else []


def optional_text(flag: str, value: str | None) -> list[str]:
    return [flag, value] if value else []


def optional_number(flag: str, value: float | None) -> list[str]:
    return [flag, str(value)] if value is not None else []


def budget_option_values(args: argparse.Namespace) -> list[str]:
    return optional_number("--monthly-budget-usd", args.monthly_budget_usd) + optional_number("--weekly-budget-usd", args.weekly_budget_usd)


def run_source_check_experiment_command(args: argparse.Namespace) -> int:
    return module_main(
        "data_source_audit",
        [
            "check-experiment",
            str(args.ops_dir),
            str(args.experiment_plan),
            "--claim-impact",
            args.claim_impact,
        ],
    )


def run_source_check_claim_command(args: argparse.Namespace) -> int:
    return module_main(
        "data_source_audit",
        [
            "check-claim",
            str(args.ops_dir),
            str(args.artifact),
            "--use-case",
            args.use_case,
            "--claim-impact",
            args.claim_impact,
        ]
        + (["--allow-tier4-explicit"] if args.allow_tier4_explicit else []),
    )


def run_cost_summary_command(args: argparse.Namespace) -> int:
    return module_main(
        "cost_tracking",
        ["summary", str(args.ops_dir)]
        + optional_path("--ledger", args.ledger)
        + budget_option_values(args),
    )


def run_cost_ingest_usage_command(args: argparse.Namespace) -> int:
    return module_main(
        "cost_tracking",
        [
            "ingest-usage",
            str(args.ops_dir),
            "--usage-file",
            str(args.usage_file),
            "--item-id",
            args.item_id,
            "--role",
            args.role,
            "--model",
            args.model,
            "--input-usd-per-1m",
            str(args.input_usd_per_1m),
            "--output-usd-per-1m",
            str(args.output_usd_per_1m),
            "--compute-usd",
            str(args.compute_usd),
            "--human-minutes",
            str(args.human_minutes),
            "--status",
            args.status,
        ]
        + optional_number("--api-usd", args.api_usd)
        + optional_text("--notes", args.notes)
        + optional_text("--date", args.date)
        + optional_path("--ledger", args.ledger)
        + (["--dry-run"] if args.dry_run else [])
        + budget_option_values(args),
    )


def run_cost_budget_check_command(args: argparse.Namespace) -> int:
    return module_main(
        "cost_tracking",
        [
            "budget-check",
            str(args.ops_dir),
            "--item-id",
            args.item_id,
            "--action",
            args.action,
            "--proposed-api-usd",
            str(args.proposed_api_usd),
            "--proposed-compute-usd",
            str(args.proposed_compute_usd),
            "--threshold",
            str(args.threshold),
        ]
        + optional_path("--ledger", args.ledger)
        + budget_option_values(args),
    )


def run_metrics_summarize_command(args: argparse.Namespace) -> int:
    return module_main(
        "metrics_history",
        ["summarize", str(args.ops_dir)]
        + optional_text("--month", args.month)
        + optional_path("--output", args.output),
    )


def run_accepted_check_duplicate_command(args: argparse.Namespace) -> int:
    return module_main(
        "update_accepted_outputs_index",
        [
            "check-duplicate",
            str(args.ops_dir),
            "--title",
            args.title,
            "--threshold",
            str(args.threshold),
        ]
        + optional_path("--index", args.index),
    )


def run_accepted_check_memory_use_command(args: argparse.Namespace) -> int:
    return module_main(
        "update_accepted_outputs_index",
        ["check-memory-use", str(args.ops_dir), str(args.artifact)]
        + optional_path("--index", args.index)
        + optional_text("--now", args.now)
        + (["--allow-stale"] if args.allow_stale else []),
    )


def register_package_commands(subparsers) -> None:
    version = add_command(
        subparsers,
        "version",
        help="Print the installed package version as JSON.",
        description="Print the installed async-research package version as JSON.",
    )
    version.set_defaults(func=run_version)

    init = add_command(
        subparsers,
        "init",
        help="Initialize a research_ops workspace from a starter template.",
        description="Create a generic or worked-example research_ops workspace safely.",
        epilog="Without --force, existing non-empty targets are refused with exit code 4.",
    )
    init.add_argument("target_dir", nargs="?", type=Path, default=Path("research_ops"), help="Target research_ops directory to create.")
    init.add_argument("--template", choices=sorted(TEMPLATES), default="generic", help="Starter template to install.")
    init.add_argument("--force", action="store_true", help="Replace an existing target after staging succeeds.")
    init.set_defaults(func=run_init)

    smoke = add_command(
        subparsers,
        "starter-smoke",
        help="Initialize and validate a disposable starter workspace.",
        description="Create a starter workspace, then run schema, readiness, health, surface, source, cost, benchmark, and simulation checks.",
        epilog="Without --force, existing non-empty work directories are refused with exit code 4.",
    )
    smoke.add_argument("work_dir", type=Path, help="Disposable work directory; research_ops is created inside unless this path is already named research_ops.")
    smoke.add_argument("--template", choices=sorted(TEMPLATES), default="generic", help="Starter template to smoke.")
    smoke.add_argument("--force", action="store_true", help="Remove and recreate the disposable work directory.")
    smoke.set_defaults(func=run_starter_smoke)

    acceptance = add_command(
        subparsers,
        "acceptance-suite",
        help="Run isolated package acceptance checks.",
        description="Run the durable package acceptance suite against isolated temporary fixtures.",
        epilog="Exits 0 when all checks pass, 1 when any acceptance check fails.",
    )
    acceptance.set_defaults(func=run_acceptance_suite_command)


def register_status_commands(subparsers) -> None:
    readiness = add_command(
        subparsers,
        "readiness",
        help="Decide whether another autonomous loop is safe.",
        description="Inspect a research_ops workspace and classify whether scheduled or expensive work may continue.",
        epilog=READINESS_EXIT_EPILOG,
    )
    add_common_ops(readiness)
    readiness.add_argument("--dry-run", action="store_true", help="Print the report without writing health_report.json or daily_status.md.")
    readiness.set_defaults(func=lambda a: module_main("autonomy_readiness_gate", [str(a.ops_dir)] + (["--dry-run"] if a.dry_run else [])))

    health = add_command(
        subparsers,
        "health",
        help="Generate operational health status.",
        description="Summarize queue, task, lock, review, source, cost, metric, and accepted-memory health.",
    )
    add_common_ops(health)
    health.add_argument("--dry-run", action="store_true", help="Print the report without writing health_report.json or daily_status.md.")
    health.set_defaults(func=lambda a: module_main("health_check", [str(a.ops_dir)] + (["--dry-run"] if a.dry_run else [])))


def register_surface_commands(subparsers) -> None:
    surface = add_command(
        subparsers,
        "surface",
        aliases=["review-surface"],
        help="Update or validate human-facing review surfaces.",
        description="Manage daily_status.md, human_review_queue.md, and weekly_digest.md.",
    )
    surface_sub = surface.add_subparsers(dest="surface_command", required=True)
    surface_update = add_command(
        surface_sub,
        "update",
        help="Write human-facing status and review queue files.",
        description="Refresh daily_status.md, human_review_queue.md, and the weekly digest surface.",
    )
    add_common_ops(surface_update)
    surface_update.set_defaults(func=lambda a: module_main("human_review_surface", ["update", str(a.ops_dir)]))
    surface_validate = add_command(
        surface_sub,
        "validate",
        help="Validate human-facing status and review queue files.",
        description="Compare rendered human review surfaces with the current workspace state.",
    )
    add_common_ops(surface_validate)
    surface_validate.set_defaults(func=lambda a: module_main("human_review_surface", ["validate", str(a.ops_dir)]))


def register_schema_command(subparsers) -> None:
    schema = add_command(
        subparsers,
        "schema-check",
        help="Validate schema versions for workflow JSON artifacts.",
        description="Check task status and other versioned JSON artifacts for expected schema versions.",
    )
    add_common_ops(schema)
    schema.set_defaults(func=lambda a: module_main("check_schema_versions", [str(a.ops_dir)]))


def register_source_commands(subparsers) -> None:
    source = add_command(
        subparsers,
        "source",
        help="Validate or report source-governance state.",
        description="Inspect data_source_audit.md for validity and source freshness.",
    )
    source_sub = source.add_subparsers(dest="source_command", required=True)
    validate = add_command(
        source_sub,
        "validate",
        help="Validate data_source_audit.md.",
        description="Validate source audit rows, statuses, tiers, and required governance fields.",
    )
    add_common_ops(validate)
    validate.set_defaults(func=lambda a: module_main("data_source_audit", ["validate", str(a.ops_dir)]))
    freshness = add_command(
        source_sub,
        "freshness",
        help="Report stale or due source reviews.",
        description="Report whether source audit entries are stale relative to freshness windows.",
    )
    add_common_ops(freshness)
    freshness.set_defaults(func=lambda a: module_main("data_source_audit", ["freshness-report", str(a.ops_dir)]))
    check_experiment = add_command(
        source_sub,
        "check-experiment",
        help="Verify an experiment plan references ready audited sources.",
        description="Validate that an experiment plan cites source IDs allowed for experiment planning.",
    )
    add_required_ops(check_experiment)
    check_experiment.add_argument("experiment_plan", type=Path, help="Experiment task or artifact to scan for DS-* source references.")
    check_experiment.add_argument("--claim-impact", choices=["low", "medium", "high"], default="medium", help="Impact level used while assessing cited sources.")
    check_experiment.set_defaults(func=run_source_check_experiment_command)
    check_claim = add_command(
        source_sub,
        "check-claim",
        help="Verify an artifact cites sources allowed for its claim use.",
        description="Validate that an artifact's cited DS-* sources are allowed for the selected use case and impact.",
    )
    add_required_ops(check_claim)
    check_claim.add_argument("artifact", type=Path, help="Artifact to scan for DS-* source references.")
    check_claim.add_argument("--use-case", choices=["discovery", "experiment_planning", "accepted_evidence", "context"], default="accepted_evidence", help="Source use case to validate.")
    check_claim.add_argument("--claim-impact", choices=["low", "medium", "high"], default="medium", help="Claim impact level to validate.")
    check_claim.add_argument("--allow-tier4-explicit", action="store_true", help="Allow explicitly cited tier-4 sources when policy permits.")
    check_claim.set_defaults(func=run_source_check_claim_command)


def register_cost_commands(subparsers) -> None:
    cost = add_command(
        subparsers,
        "cost",
        help="Summarize cost and budget state.",
        description="Inspect cost_ledger.csv for spend, usage, and budget pressure.",
    )
    cost_sub = cost.add_subparsers(dest="cost_command", required=True)
    cost_summary = add_command(
        cost_sub,
        "summary",
        help="Summarize the cost ledger.",
        description="Print aggregate spend, usage, and budget information from cost_ledger.csv.",
    )
    add_common_ops(cost_summary)
    cost_summary.add_argument("--ledger", type=Path, help="Override the default research_ops/cost_ledger.csv path.")
    add_budget_options(cost_summary)
    cost_summary.set_defaults(func=run_cost_summary_command)
    ingest = add_command(
        cost_sub,
        "ingest-usage",
        help="Append actual API usage to cost_ledger.csv.",
        description="Aggregate token usage from a JSON/JSONL response artifact and append a cost ledger row.",
    )
    add_common_ops(ingest)
    ingest.add_argument("--usage-file", type=Path, required=True, help="JSON or JSONL usage artifact to aggregate.")
    ingest.add_argument("--item-id", required=True, help="Task, idea, batch, or decision identifier for the ledger row.")
    ingest.add_argument("--role", required=True, help="Actor or workflow role responsible for the usage.")
    ingest.add_argument("--model", required=True, help="Model or tool name responsible for the usage.")
    ingest.add_argument("--input-usd-per-1m", type=float, default=0.0, help="Input-token price per 1M tokens.")
    ingest.add_argument("--output-usd-per-1m", type=float, default=0.0, help="Output-token price per 1M tokens.")
    ingest.add_argument("--api-usd", type=float, help="Explicit API cost override in USD.")
    ingest.add_argument("--compute-usd", type=float, default=0.0, help="Additional compute cost in USD.")
    ingest.add_argument("--human-minutes", type=float, default=0.0, help="Human time associated with the usage.")
    ingest.add_argument("--status", default="completed", help="Status stored on the ledger row.")
    ingest.add_argument("--notes", help="Notes stored on the ledger row.")
    ingest.add_argument("--date", help="ISO date/time stored on the ledger row.")
    ingest.add_argument("--ledger", type=Path, help="Override the default research_ops/cost_ledger.csv path.")
    ingest.add_argument("--dry-run", action="store_true", help="Print the row without writing cost_ledger.csv.")
    add_budget_options(ingest)
    ingest.set_defaults(func=run_cost_ingest_usage_command)
    budget = add_command(
        cost_sub,
        "budget-check",
        help="Exit nonzero when projected spend crosses a threshold.",
        description="Project a proposed cost against monthly and weekly budgets before promotion or expensive work.",
    )
    add_common_ops(budget)
    budget.add_argument("--item-id", required=True, help="Task, idea, batch, or decision identifier being checked.")
    budget.add_argument("--action", default="expensive_task", help="Action being gated.")
    budget.add_argument("--proposed-api-usd", type=float, default=0.0, help="Proposed API cost in USD.")
    budget.add_argument("--proposed-compute-usd", type=float, default=0.0, help="Proposed compute cost in USD.")
    budget.add_argument("--threshold", type=float, default=0.8, help="Budget usage ratio at or above which work is halted.")
    budget.add_argument("--ledger", type=Path, help="Override the default research_ops/cost_ledger.csv path.")
    add_budget_options(budget)
    budget.set_defaults(func=run_cost_budget_check_command)


def register_metrics_commands(subparsers) -> None:
    metrics = add_command(
        subparsers,
        "metrics",
        help="Append or inspect autonomy metrics.",
        description="Maintain metrics_baseline.json and metrics_history.jsonl snapshots.",
    )
    metrics_sub = metrics.add_subparsers(dest="metrics_command", required=True)
    metrics_append = add_command(
        metrics_sub,
        "append",
        help="Append an autonomy metrics snapshot.",
        description="Append a metrics_history.jsonl snapshot for the current workspace state.",
    )
    add_common_ops(metrics_append)
    metrics_append.add_argument("--label", default="manual", help="Label stored with the snapshot.")
    metrics_append.add_argument("--update-weekly-digest", action="store_true", help="Refresh the autonomy metrics section in weekly_digest.md.")
    metrics_append.set_defaults(func=lambda a: module_main("metrics_history", ["append-snapshot", str(a.ops_dir), "--label", a.label] + (["--update-weekly-digest"] if a.update_weekly_digest else [])))
    metrics_summarize = add_command(
        metrics_sub,
        "summarize",
        help="Summarize metric trends from history.",
        description="Summarize baseline and metrics_history.jsonl trends, optionally writing a Markdown report.",
    )
    add_common_ops(metrics_summarize)
    metrics_summarize.add_argument("--month", help="Limit or label the summary month.")
    metrics_summarize.add_argument("--output", type=Path, help="Write a Markdown summary to this path.")
    metrics_summarize.set_defaults(func=run_metrics_summarize_command)


def register_accepted_commands(subparsers) -> None:
    accepted = add_command(
        subparsers,
        "accepted",
        help="Maintain accepted-output memory and revalidation state.",
        description="Update accepted_outputs_index.md and accepted-memory revalidation schedules.",
    )
    accepted_sub = accepted.add_subparsers(dest="accepted_command", required=True)
    accepted_update = add_command(
        accepted_sub,
        "update",
        help="Refresh accepted_outputs_index.md.",
        description="Upsert accepted task rows into accepted_outputs_index.md.",
    )
    add_common_ops(accepted_update)
    accepted_update.set_defaults(func=lambda a: module_main("update_accepted_outputs_index", ["update", str(a.ops_dir)]))
    accepted_duplicate = add_command(
        accepted_sub,
        "check-duplicate",
        help="Check whether a proposed title overlaps accepted memory.",
        description="Report duplicate risk against accepted_outputs_index.md while preserving advisory exit-code behavior.",
    )
    add_common_ops(accepted_duplicate)
    accepted_duplicate.add_argument("--title", required=True, help="Proposed title to compare with accepted outputs.")
    accepted_duplicate.add_argument("--index", type=Path, help="Override the default accepted_outputs_index.md path.")
    accepted_duplicate.add_argument("--threshold", type=float, default=0.35, help="Similarity threshold used to report duplicate risk.")
    accepted_duplicate.set_defaults(func=run_accepted_check_duplicate_command)
    accepted_reval = add_command(
        accepted_sub,
        "revalidation",
        aliases=["revalidate"],
        help="Report due or stale accepted memory.",
        description="Print an accepted-memory freshness report and optionally write revalidation_schedule.md.",
    )
    add_common_ops(accepted_reval)
    accepted_reval.add_argument("--write-schedule", action="store_true", help="Write research_ops/revalidation_schedule.md.")
    accepted_reval.set_defaults(func=lambda a: module_main("update_accepted_outputs_index", ["revalidation-report", str(a.ops_dir)] + (["--write-schedule"] if a.write_schedule else [])))
    accepted_memory = add_command(
        accepted_sub,
        "check-memory-use",
        help="Fail if an artifact cites stale accepted memory.",
        description="Scan an artifact for TASK-* references and block reuse of stale accepted memory.",
    )
    add_required_ops(accepted_memory)
    accepted_memory.add_argument("artifact", type=Path, help="Artifact to scan for accepted-memory task references.")
    accepted_memory.add_argument("--index", type=Path, help="Override the default accepted_outputs_index.md path.")
    accepted_memory.add_argument("--now", help="Override current time for deterministic freshness checks, ISO-8601.")
    accepted_memory.add_argument("--allow-stale", action="store_true", help="Report stale refs without failing the gate.")
    accepted_memory.set_defaults(func=run_accepted_check_memory_use_command)


def register_review_commands(subparsers) -> None:
    review = add_command(
        subparsers,
        "review",
        help="Aggregate isolated reviewer notes.",
        description="Route reviewed tasks based on independent review files and policy.",
    )
    review_sub = review.add_subparsers(dest="review_command", required=True)
    aggregate = add_command(
        review_sub,
        "aggregate",
        help="Aggregate review decisions for one task.",
        description="Read reviews/*.md, compute a deterministic aggregate, and optionally update task state and result ledgers.",
    )
    aggregate.add_argument("task_dir", type=Path, help="Task directory containing status.json and reviews/.")
    aggregate.add_argument("--dry-run", action="store_true", help="Validate and preview routing without writing aggregate/status files.")
    aggregate.set_defaults(func=lambda a: module_main("aggregate_reviews", [str(a.task_dir)] + (["--dry-run"] if a.dry_run else [])))


def register_result_command(subparsers) -> None:
    result = add_command(
        subparsers,
        "result-acceptance",
        help="Validate final result acceptance gates for one task.",
        description="Validate reviewed task output against result-acceptance gates and optionally write result_acceptance.json and ledgers.",
    )
    result.add_argument("task_dir", type=Path, help="Task directory to validate.")
    result.add_argument("--ops-dir", type=Path, help="research_ops directory; inferred from task_dir when omitted.")
    result.add_argument("--write", action="store_true", help="Write review_panel/result_acceptance.json when gates pass.")
    result.add_argument("--update-ledgers", action="store_true", help="Update evidence_ledger.md or rejected_results.md when gates pass.")
    result.set_defaults(func=lambda a: module_main("validate_result_acceptance", [str(a.task_dir)] + (["--ops-dir", str(a.ops_dir)] if a.ops_dir else []) + (["--write"] if a.write else []) + (["--update-ledgers"] if a.update_ledgers else [])))


def register_artifact_commands(subparsers) -> None:
    exploration = add_command(
        subparsers,
        "exploration",
        help="Validate exploration-cycle artifacts.",
        description="Validate worker outputs for idea discovery and exploration-cycle tasks.",
    )
    exploration_sub = exploration.add_subparsers(dest="exploration_command", required=True)
    exploration_validate = add_command(
        exploration_sub,
        "validate",
        help="Validate an exploration worker output.",
        description="Validate one exploration-cycle worker output against schemas, task state, and accepted-memory rules.",
    )
    exploration_validate.add_argument("worker_output", type=Path, help="Worker output artifact to validate.")
    exploration_validate.add_argument("--ops-dir", type=Path, required=True, help="research_ops directory.")
    exploration_validate.add_argument("--task-dir", type=Path, required=True, help="Task directory associated with the worker output.")
    exploration_validate.set_defaults(func=lambda a: module_main("validate_exploration_cycle", [str(a.worker_output), "--ops-dir", str(a.ops_dir), "--task-dir", str(a.task_dir)]))

    idea = add_command(
        subparsers,
        "idea",
        help="Score or validate idea artifacts.",
        description="Score idea candidates and validate idea-evaluation JSON artifacts.",
    )
    idea_sub = idea.add_subparsers(dest="idea_command", required=True)
    idea_score = add_command(
        idea_sub,
        "score",
        help="Score an idea candidate.",
        description="Score an idea JSON file against mission policy, cost posture, and accepted-memory context.",
    )
    idea_score.add_argument("idea_json", type=Path, help="Idea candidate JSON file.")
    idea_score.add_argument("--ops-dir", type=Path, required=True, help="research_ops directory.")
    idea_score.add_argument("--budget-mode", choices=["normal", "budget_constrained", "auto"], default="auto", help="Budget posture to apply while scoring.")
    idea_score.set_defaults(func=lambda a: module_main("score_idea_candidate", [str(a.idea_json), "--ops-dir", str(a.ops_dir), "--budget-mode", a.budget_mode]))
    idea_validate = add_command(
        idea_sub,
        "validate",
        help="Validate an idea-evaluation artifact.",
        description="Validate an idea-evaluation JSON file against schemas and workflow gates.",
    )
    idea_validate.add_argument("idea_json", type=Path, help="Idea-evaluation JSON file.")
    idea_validate.add_argument("--ops-dir", type=Path, required=True, help="research_ops directory.")
    idea_validate.set_defaults(func=lambda a: module_main("validate_idea_evaluation", [str(a.idea_json), "--ops-dir", str(a.ops_dir)]))

    experiment = add_command(
        subparsers,
        "experiment",
        help="Validate experiment-plan artifacts.",
        description="Validate experiment worker outputs against source readiness, schemas, and task constraints.",
    )
    experiment_sub = experiment.add_subparsers(dest="experiment_command", required=True)
    experiment_validate = add_command(
        experiment_sub,
        "validate",
        help="Validate an experiment worker output.",
        description="Validate one experiment-plan worker output against schemas, task state, and source governance.",
    )
    experiment_validate.add_argument("worker_output", type=Path, help="Worker output artifact to validate.")
    experiment_validate.add_argument("--ops-dir", type=Path, required=True, help="research_ops directory.")
    experiment_validate.add_argument("--task-dir", type=Path, required=True, help="Task directory associated with the worker output.")
    experiment_validate.set_defaults(func=lambda a: module_main("validate_experiment_plan", [str(a.worker_output), "--ops-dir", str(a.ops_dir), "--task-dir", str(a.task_dir)]))


def register_benchmark_commands(subparsers) -> None:
    benchmark = add_command(
        subparsers,
        "benchmark",
        help="Run packaged autonomy benchmark cases.",
        description="Run known-good and known-bad benchmark cases against isolated temporary fixtures.",
        epilog="Exits 0 when all cases satisfy acceptance criteria, 1 when the benchmark fails.",
    )
    benchmark.set_defaults(func=lambda a: module_main("run_autonomy_benchmark", []))

    simulate = add_command(
        subparsers,
        "simulate-week",
        help="Simulate one scheduled week against an isolated workspace copy.",
        description="Drive readiness, discovery, review, result acceptance, metrics, and surface helpers with fixture outputs.",
        epilog="Exits 0 when the simulated week satisfies all checks, 1 when the simulation fails.",
    )
    add_common_ops(simulate)
    simulate.set_defaults(func=lambda a: module_main("simulate_scheduled_week", [str(a.ops_dir)]))


COMMAND_REGISTRARS = (
    register_package_commands,
    register_status_commands,
    register_surface_commands,
    register_schema_command,
    register_source_commands,
    register_cost_commands,
    register_metrics_commands,
    register_accepted_commands,
    register_review_commands,
    register_result_command,
    register_artifact_commands,
    register_benchmark_commands,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="async-research",
        description="Async research workflow alpha CLI for file-backed research_ops workspaces.",
        epilog=COMMON_EXIT_EPILOG,
        formatter_class=HelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for register in COMMAND_REGISTRARS:
        register(subparsers)
    return parser


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    return build_parser().parse_args(list(argv))


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
