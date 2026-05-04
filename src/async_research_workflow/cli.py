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
from importlib import resources
from pathlib import Path
from typing import Iterable, Sequence

from async_research_workflow import __version__


SUCCESS = 0
INVALID = 4


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
    if template != "real-estate":
        raise ValueError(f"unsupported template: {template}")
    return resources.files("async_research_workflow").joinpath(
        "templates", "research_ops_starter", "research_ops"
    )


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


def run_init(args: argparse.Namespace) -> int:
    target = args.target_dir
    try:
        source = template_root(args.template)
        if target.exists() and any(target.iterdir()) and not args.force:
            print_json({
                "ok": False,
                "reason": "target_exists",
                "target_dir": str(target),
                "next_step": "rerun with --force or choose an empty target directory",
            })
            return INVALID
        copy_resource_tree(source, target, force=args.force)
        metrics_init_code, metrics_init = module_json("metrics_history", ["init", str(target), "--label", "starter_init", "--force"])
        metrics_append_code, metrics_append = module_json("metrics_history", ["append-snapshot", str(target), "--label", "starter_init"])
        if metrics_init_code != SUCCESS or metrics_append_code != SUCCESS:
            print_json({
                "ok": False,
                "reason": "starter_metrics_init_failed",
                "target_dir": str(target),
                "metrics_init": metrics_init,
                "metrics_append": metrics_append,
            })
            return INVALID
    except Exception as exc:
        print_json({"ok": False, "reason": "init_failed", "error": str(exc), "target_dir": str(target)})
        return INVALID
    print_json({"ok": True, "action": "initialized", "target_dir": str(target), "template": args.template})
    return SUCCESS


def run_starter_smoke(args: argparse.Namespace) -> int:
    base = args.work_dir
    ops_dir = base if base.name == "research_ops" else base / "research_ops"
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
        shutil.rmtree(base)
    failures: list[dict] = []
    reports: list[dict] = []

    init_args = argparse.Namespace(target_dir=ops_dir, template="real-estate", force=True)
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
    parser.add_argument("ops_dir", nargs="?", type=Path, default=Path(default))


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="async-research", description="Async research workflow alpha CLI.")
    sub = parser.add_subparsers(dest="command", required=True)

    version = sub.add_parser("version")
    version.set_defaults(func=run_version)

    init = sub.add_parser("init", help="Initialize a research_ops workspace from a starter template.")
    init.add_argument("target_dir", nargs="?", type=Path, default=Path("research_ops"))
    init.add_argument("--template", choices=["real-estate"], default="real-estate")
    init.add_argument("--force", action="store_true")
    init.set_defaults(func=run_init)

    smoke = sub.add_parser("starter-smoke", help="Initialize and validate a starter workspace.")
    smoke.add_argument("work_dir", type=Path)
    smoke.add_argument("--force", action="store_true")
    smoke.set_defaults(func=run_starter_smoke)

    acceptance = sub.add_parser("acceptance-suite")
    acceptance.set_defaults(func=run_acceptance_suite_command)

    readiness = sub.add_parser("readiness")
    add_common_ops(readiness)
    readiness.add_argument("--dry-run", action="store_true")
    readiness.set_defaults(func=lambda a: module_main("autonomy_readiness_gate", [str(a.ops_dir)] + (["--dry-run"] if a.dry_run else [])))

    health = sub.add_parser("health")
    add_common_ops(health)
    health.add_argument("--dry-run", action="store_true")
    health.set_defaults(func=lambda a: module_main("health_check", [str(a.ops_dir)] + (["--dry-run"] if a.dry_run else [])))

    surface = sub.add_parser("surface")
    surface_sub = surface.add_subparsers(dest="surface_command", required=True)
    for name in ("update", "validate"):
        p = surface_sub.add_parser(name)
        add_common_ops(p)
        p.set_defaults(func=lambda a, n=name: module_main("human_review_surface", [n, str(a.ops_dir)]))

    schema = sub.add_parser("schema-check")
    add_common_ops(schema)
    schema.set_defaults(func=lambda a: module_main("check_schema_versions", [str(a.ops_dir)]))

    source = sub.add_parser("source")
    source_sub = source.add_subparsers(dest="source_command", required=True)
    validate = source_sub.add_parser("validate")
    add_common_ops(validate)
    validate.set_defaults(func=lambda a: module_main("data_source_audit", ["validate", str(a.ops_dir)]))
    freshness = source_sub.add_parser("freshness")
    add_common_ops(freshness)
    freshness.set_defaults(func=lambda a: module_main("data_source_audit", ["freshness-report", str(a.ops_dir)]))

    cost = sub.add_parser("cost")
    cost_sub = cost.add_subparsers(dest="cost_command", required=True)
    cost_summary = cost_sub.add_parser("summary")
    add_common_ops(cost_summary)
    cost_summary.set_defaults(func=lambda a: module_main("cost_tracking", ["summary", str(a.ops_dir)]))

    metrics = sub.add_parser("metrics")
    metrics_sub = metrics.add_subparsers(dest="metrics_command", required=True)
    metrics_append = metrics_sub.add_parser("append")
    add_common_ops(metrics_append)
    metrics_append.add_argument("--label", default="manual")
    metrics_append.add_argument("--update-weekly-digest", action="store_true")
    metrics_append.set_defaults(func=lambda a: module_main("metrics_history", ["append-snapshot", str(a.ops_dir), "--label", a.label] + (["--update-weekly-digest"] if a.update_weekly_digest else [])))

    accepted = sub.add_parser("accepted")
    accepted_sub = accepted.add_subparsers(dest="accepted_command", required=True)
    accepted_update = accepted_sub.add_parser("update")
    add_common_ops(accepted_update)
    accepted_update.set_defaults(func=lambda a: module_main("update_accepted_outputs_index", ["update", str(a.ops_dir)]))
    accepted_reval = accepted_sub.add_parser("revalidation")
    add_common_ops(accepted_reval)
    accepted_reval.add_argument("--write-schedule", action="store_true")
    accepted_reval.set_defaults(func=lambda a: module_main("update_accepted_outputs_index", ["revalidation-report", str(a.ops_dir)] + (["--write-schedule"] if a.write_schedule else [])))

    review = sub.add_parser("review")
    review_sub = review.add_subparsers(dest="review_command", required=True)
    aggregate = review_sub.add_parser("aggregate")
    aggregate.add_argument("task_dir", type=Path)
    aggregate.add_argument("--dry-run", action="store_true")
    aggregate.set_defaults(func=lambda a: module_main("aggregate_reviews", [str(a.task_dir)] + (["--dry-run"] if a.dry_run else [])))

    result = sub.add_parser("result-acceptance")
    result.add_argument("task_dir", type=Path)
    result.add_argument("--ops-dir", type=Path)
    result.add_argument("--write", action="store_true")
    result.add_argument("--update-ledgers", action="store_true")
    result.set_defaults(func=lambda a: module_main("validate_result_acceptance", [str(a.task_dir)] + (["--ops-dir", str(a.ops_dir)] if a.ops_dir else []) + (["--write"] if a.write else []) + (["--update-ledgers"] if a.update_ledgers else [])))

    exploration = sub.add_parser("exploration")
    exploration_sub = exploration.add_subparsers(dest="exploration_command", required=True)
    exploration_validate = exploration_sub.add_parser("validate")
    exploration_validate.add_argument("worker_output", type=Path)
    exploration_validate.add_argument("--ops-dir", type=Path, required=True)
    exploration_validate.add_argument("--task-dir", type=Path, required=True)
    exploration_validate.set_defaults(func=lambda a: module_main("validate_exploration_cycle", [str(a.worker_output), "--ops-dir", str(a.ops_dir), "--task-dir", str(a.task_dir)]))

    idea = sub.add_parser("idea")
    idea_sub = idea.add_subparsers(dest="idea_command", required=True)
    idea_score = idea_sub.add_parser("score")
    idea_score.add_argument("idea_json", type=Path)
    idea_score.add_argument("--ops-dir", type=Path, required=True)
    idea_score.add_argument("--budget-mode", choices=["normal", "budget_constrained", "auto"], default="auto")
    idea_score.set_defaults(func=lambda a: module_main("score_idea_candidate", [str(a.idea_json), "--ops-dir", str(a.ops_dir), "--budget-mode", a.budget_mode]))
    idea_validate = idea_sub.add_parser("validate")
    idea_validate.add_argument("idea_json", type=Path)
    idea_validate.add_argument("--ops-dir", type=Path, required=True)
    idea_validate.set_defaults(func=lambda a: module_main("validate_idea_evaluation", [str(a.idea_json), "--ops-dir", str(a.ops_dir)]))

    experiment = sub.add_parser("experiment")
    experiment_sub = experiment.add_subparsers(dest="experiment_command", required=True)
    experiment_validate = experiment_sub.add_parser("validate")
    experiment_validate.add_argument("worker_output", type=Path)
    experiment_validate.add_argument("--ops-dir", type=Path, required=True)
    experiment_validate.add_argument("--task-dir", type=Path, required=True)
    experiment_validate.set_defaults(func=lambda a: module_main("validate_experiment_plan", [str(a.worker_output), "--ops-dir", str(a.ops_dir), "--task-dir", str(a.task_dir)]))

    benchmark = sub.add_parser("benchmark")
    benchmark.set_defaults(func=lambda a: module_main("run_autonomy_benchmark", []))

    simulate = sub.add_parser("simulate-week")
    add_common_ops(simulate)
    simulate.set_defaults(func=lambda a: module_main("simulate_scheduled_week", [str(a.ops_dir)]))

    return parser.parse_args(list(argv))


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
