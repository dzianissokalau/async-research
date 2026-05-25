"""Command line interface for the async research workflow alpha package."""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Iterable

from async_research_workflow import __version__
from async_research_workflow.cli_runner import ScriptCall
from async_research_workflow.cli_runner import function_json
from async_research_workflow.cli_runner import json_payload_from_output
from async_research_workflow.cli_runner import module_json
from async_research_workflow.cli_runner import module_main
from async_research_workflow.cli_runner import optional_number
from async_research_workflow.cli_runner import optional_path
from async_research_workflow.cli_runner import optional_text
from async_research_workflow.cli_runner import print_json
from async_research_workflow.cli_runner import repeated_option
from async_research_workflow.cli_runner import run_script_call
from async_research_workflow.cli_runner import script_call
from async_research_workflow.idea_catalog import PROMOTION_TASK_TYPES
from async_research_workflow.idea_catalog import STORED_STATUSES
from async_research_workflow.resources import template_path
from async_research_workflow.scripts.deliverable_maturity import CRITIC_REVIEW_STATUS_CHOICES
from async_research_workflow.scripts.deliverable_maturity import CRITIC_REVIEWER_ROLE_CHOICES
from async_research_workflow.scripts.deliverable_maturity import INDEPENDENCE_CHOICES
from async_research_workflow.scripts.deliverable_maturity import MATURITY_CHOICES
from async_research_workflow.scripts.deliverable_maturity import OUTPUT_TYPE_CHOICES
from async_research_workflow.scripts.deliverable_maturity import RESPONSE_MATRIX_DECISION_CHOICES
from async_research_workflow.scripts.deliverable_maturity import RESPONSE_MATRIX_STATUS_CHOICES
from async_research_workflow.scripts.deliverable_maturity import SEVERITY_LEVELS
from async_research_workflow.scripts.evidence_memory import AFFECTED_STAGES
from async_research_workflow.scripts.evidence_memory import FAILURE_CLASSES
from async_research_workflow.scripts.research_brief import OUTPUT_MATURITIES
from async_research_workflow.scripts.research_brief import PRIVATE_DATA_POLICIES
from async_research_workflow.scripts.research_brief import PUBLIC_CLAIM_POLICIES
from async_research_workflow.scripts.research_brief import SOURCE_CLASSES
from async_research_workflow.scripts.task_authoring import TASK_TYPES


SUCCESS = 0
INVALID = 4
TEMPLATES = {
    "generic": ("generic_research_ops_starter", "research_ops"),
    "real-estate": ("research_ops_starter", "research_ops"),
}
DECISION_CHOICES = (
    "acknowledge",
    "approve",
    "approve_budget",
    "approve_data_use",
    "approve_high_stakes",
    "approve_public",
    "override",
    "pause",
    "reject",
    "resume",
)
RESOLUTION_STATUS_CHOICES = ("paused", "ready_for_worker", "rejected")
IDEA_RESOLUTION_STATUS_CHOICES = ("candidate", "promote", "park", "reject")
SOURCE_TIER_CHOICES = (
    "tier_1_official",
    "tier_2_institutional",
    "tier_3_media",
    "tier_4_untrusted",
)
SOURCE_APPROVAL_STATUS_CHOICES = (
    "approved",
    "approved_with_caveats",
    "blocked",
    "candidate",
    "deprecated",
    "explicitly_approved",
    "restricted",
    "unknown",
)
SOURCE_STATUS_CHOICES = SOURCE_APPROVAL_STATUS_CHOICES + ("available", "usable_with_caveats")
SOURCE_USE_CASE_CHOICES = ("discovery", "experiment_planning", "accepted_evidence", "context")
CLAIM_IMPACT_CHOICES = ("low", "medium", "high")
REVIEW_CONTEXT_ROLE_CHOICES = ("aggregator", "methodology", "primary", "skeptic")


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
    init_code, init_payload = function_json(run_init, init_args)
    init_result = {
        "command": "init",
        "args": [str(ops_dir), "--template", args.template, "--force"],
        "exit_code": init_code,
        "ok": init_code == SUCCESS and init_payload.get("ok", True) is not False,
        "payload": init_payload,
    }
    if not init_result["ok"]:
        init_failure = {
            "command": "init",
            "args": init_result["args"],
            "exit_code": init_code,
            "payload": init_payload,
        }
        smoke_result = {"ok": False, "checks": [], "failures": [init_failure]}
        print_json({
            "ok": False,
            "action": "starter_smoke_checked",
            "work_dir": str(base),
            "ops_dir": str(ops_dir),
            "template": args.template,
            "init": init_result,
            "smoke": smoke_result,
            "checks": [],
            "failures": [init_failure],
        })
        return init_code if init_code != SUCCESS else INVALID

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
    smoke_result = {"ok": not failures, "checks": reports, "failures": failures}
    print_json({
        "ok": not failures,
        "action": "starter_smoke_checked",
        "work_dir": str(base),
        "ops_dir": str(ops_dir),
        "template": args.template,
        "init": init_result,
        "smoke": smoke_result,
        "checks": reports,
        "failures": failures,
    })
    return SUCCESS if not failures else 1


def run_acceptance_suite_command(args: argparse.Namespace) -> int:
    argv: list[str] = []
    if args.work_dir:
        argv.extend(["--work-dir", str(args.work_dir)])
    if args.keep_work_dir:
        argv.append("--keep-work-dir")
    return module_main("run_acceptance_suite", argv)


def run_simulate_week_command(args: argparse.Namespace) -> int:
    argv = [str(args.ops_dir)]
    if args.work_dir:
        argv.extend(["--work-dir", str(args.work_dir)])
    if args.keep_work_dir:
        argv.append("--keep-work-dir")
    return module_main("simulate_scheduled_week", argv)


def run_health_command(args: argparse.Namespace) -> int:
    argv = [str(args.ops_dir)]
    if args.dry_run:
        argv.append("--dry-run")
    if args.monthly_budget_usd is not None:
        argv.extend(["--monthly-budget-usd", str(args.monthly_budget_usd)])
    if args.weekly_budget_usd is not None:
        argv.extend(["--weekly-budget-usd", str(args.weekly_budget_usd)])
    return module_main("health_check", argv)


def run_console_snapshot_command(args: argparse.Namespace) -> int:
    from async_research_workflow.console import snapshot

    argv = [str(args.ops_dir)]
    if args.json:
        argv.append("--json")
    if args.now:
        argv.extend(["--now", args.now])
    return snapshot.main(argv)


def run_console_command(args: argparse.Namespace) -> int:
    from async_research_workflow.console import server
    from async_research_workflow.console import snapshot

    console_args = list(args.console_args or [])
    if console_args and console_args[0] == "snapshot":
        argv = console_args[1:] or ["research_ops"]
        if args.json:
            argv.append("--json")
        if args.now:
            argv.extend(["--now", args.now])
        return snapshot.main(argv)
    if console_args and console_args[0] == "serve":
        console_args = console_args[1:]
    if len(console_args) > 1:
        print_json(
            {
                "ok": False,
                "reason": "invalid_console_args",
                "message": "Use async-research console [research_ops] or async-research console snapshot [research_ops] --json.",
            }
        )
        return 3
    ops_dir = Path(console_args[0]) if console_args else Path("research_ops")
    return server.main([str(ops_dir), "--host", args.host, "--port", str(args.port)])


def run_mode_show_command(args: argparse.Namespace) -> int:
    return module_main("interaction_mode", ["show", str(args.ops_dir)])


def run_mode_set_command(args: argparse.Namespace) -> int:
    return module_main("interaction_mode", ["set", str(args.ops_dir), "--mode", args.mode])


def run_mode_validate_command(args: argparse.Namespace) -> int:
    return module_main("interaction_mode", ["validate", str(args.ops_dir)])


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


def budget_option_values(args: argparse.Namespace) -> list[str]:
    return optional_number("--monthly-budget-usd", args.monthly_budget_usd) + optional_number("--weekly-budget-usd", args.weekly_budget_usd)


def source_upsert_options(args: argparse.Namespace) -> list[str]:
    return (
        ["--source-id", args.source_id]
        + optional_text("--status", args.status)
        + optional_text("--approval-status", args.approval_status)
        + optional_text("--source-name", args.source_name)
        + optional_text("--url-or-domain", args.url_or_domain)
        + optional_text("--publisher-owner", args.publisher_owner)
        + optional_text("--source-tier", args.source_tier)
        + optional_text("--approved-use-cases", args.approved_use_cases)
        + optional_text("--blocked-use-cases", args.blocked_use_cases)
        + optional_text("--freshness-window-days", args.freshness_window_days)
        + optional_text("--known-limitations", args.known_limitations)
        + optional_text("--citation-requirements", args.citation_requirements)
        + optional_text("--last-reviewed", args.last_reviewed)
        + optional_text("--approved-by", args.approved_by)
        + optional_text("--review-notes", args.review_notes)
    )


def run_source_init_command(args: argparse.Namespace) -> int:
    return module_main(
        "data_source_audit",
        ["init", str(args.ops_dir)] + (["--force"] if args.force else []),
    )


def run_source_upsert_command(args: argparse.Namespace) -> int:
    return module_main("data_source_audit", ["upsert", str(args.ops_dir)] + source_upsert_options(args))


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


def run_source_explain_command(args: argparse.Namespace) -> int:
    return module_main(
        "data_source_audit",
        [
            "explain",
            str(args.ops_dir),
            args.source_id,
            "--use-case",
            args.use_case,
            "--claim-impact",
            args.claim_impact,
        ]
        + (["--allow-tier4-explicit"] if args.allow_tier4_explicit else []),
    )


def run_data_validate_command(args: argparse.Namespace) -> int:
    argv = ["validate", str(args.ops_dir)]
    if args.now:
        argv.extend(["--now", args.now])
    return module_main("data_foundations", argv)


def run_data_dashboard_command(args: argparse.Namespace) -> int:
    argv = ["dashboard", str(args.ops_dir)]
    if args.now:
        argv.extend(["--now", args.now])
    argv.extend(["--use-case", args.use_case])
    return module_main("data_foundations", argv)


def run_data_inspect_proposals_command(args: argparse.Namespace) -> int:
    return module_main(
        "data_proposal_inspection",
        [str(args.ops_dir), str(args.proposal_source)],
    )


def run_data_apply_proposals_command(args: argparse.Namespace) -> int:
    argv = [str(args.ops_dir), str(args.proposal_source)]
    if args.dry_run:
        argv.append("--dry-run")
    if args.write:
        argv.append("--write")
    if args.preflight_hash:
        argv.extend(["--preflight-hash", args.preflight_hash])
    if args.accepted_artifact:
        argv.extend(["--accepted-artifact", str(args.accepted_artifact)])
    return module_main("data_proposal_apply", argv)


def run_library_init_command(args: argparse.Namespace) -> int:
    argv = ["init", str(args.ops_dir)]
    if args.dry_run:
        argv.append("--dry-run")
    if args.write:
        argv.append("--write")
    return module_main("knowledge_library", argv)


def run_library_validate_command(args: argparse.Namespace) -> int:
    argv = ["validate", str(args.ops_dir)]
    if args.now:
        argv.extend(["--now", args.now])
    if args.stale_days is not None:
        argv.extend(["--stale-days", str(args.stale_days)])
    return module_main("knowledge_library", argv)


def run_library_dashboard_command(args: argparse.Namespace) -> int:
    argv = ["dashboard", str(args.ops_dir)]
    if args.now:
        argv.extend(["--now", args.now])
    if args.stale_days is not None:
        argv.extend(["--stale-days", str(args.stale_days)])
    return module_main("knowledge_library", argv)


def run_library_inspect_proposals_command(args: argparse.Namespace) -> int:
    return module_main(
        "library_proposal_inspection",
        [str(args.ops_dir), str(args.proposal_source)],
    )


def run_library_apply_proposals_command(args: argparse.Namespace) -> int:
    argv = [str(args.ops_dir), str(args.proposal_source)]
    if args.dry_run:
        argv.append("--dry-run")
    if args.write:
        argv.append("--write")
    if args.preflight_hash:
        argv.extend(["--preflight-hash", args.preflight_hash])
    if args.accepted_artifact:
        argv.extend(["--accepted-artifact", str(args.accepted_artifact)])
    return module_main("library_proposal_apply", argv)


def run_runtime_validate_command(args: argparse.Namespace) -> int:
    return module_main("runtime_artifacts", ["validate", str(args.ops_dir)])


def run_runtime_summary_command(args: argparse.Namespace) -> int:
    return module_main("runtime_artifacts", ["summary", str(args.ops_dir)])


def run_runtime_inspect_evidence_command(args: argparse.Namespace) -> int:
    return module_main("runtime_artifacts", ["inspect-evidence", str(args.ops_dir), args.evidence_id])


def run_runtime_adapter_dry_run_command(args: argparse.Namespace) -> int:
    argv = ["dry-run", str(args.ops_dir), "--request", str(args.request)]
    if args.now:
        argv.extend(["--now", args.now])
    return module_main("runtime_adapters", argv)


def run_runtime_adapter_execute_command(args: argparse.Namespace) -> int:
    argv = ["execute", str(args.ops_dir), "--request", str(args.request)]
    if args.now:
        argv.extend(["--now", args.now])
    return module_main("runtime_adapters", argv)


def run_eval_build_from_traces_command(args: argparse.Namespace) -> int:
    argv = ["build-from-traces", str(args.ops_dir), "--suite-id", args.suite_id]
    if args.output:
        argv.extend(["--output", str(args.output)])
    if args.write:
        argv.append("--write")
    if args.now:
        argv.extend(["--now", args.now])
    if args.runtime_policy:
        argv.extend(["--runtime-policy", args.runtime_policy])
    if args.model_routing_policy:
        argv.extend(["--model-routing-policy", args.model_routing_policy])
    return module_main("runtime_evals", argv)


def run_eval_run_command(args: argparse.Namespace) -> int:
    argv = ["run", str(args.eval_suite)]
    if args.run_id:
        argv.extend(["--run-id", args.run_id])
    if args.output:
        argv.extend(["--output", str(args.output)])
    if args.write:
        argv.append("--write")
    if args.now:
        argv.extend(["--now", args.now])
    return module_main("runtime_evals", argv)


def run_eval_compare_command(args: argparse.Namespace) -> int:
    return module_main(
        "runtime_evals",
        [
            "compare",
            str(args.baseline),
            str(args.candidate),
            "--cost-tolerance-usd",
            str(args.cost_tolerance_usd),
        ],
    )


def run_evidence_memory_update_command(args: argparse.Namespace) -> int:
    argv = ["update", str(args.ops_dir)]
    if args.dry_run:
        argv.append("--dry-run")
    if args.output:
        argv.extend(["--output", str(args.output)])
    if args.now:
        argv.extend(["--now", args.now])
    return module_main("evidence_memory", argv)


def run_evidence_memory_query_command(args: argparse.Namespace) -> int:
    argv = ["query", str(args.ops_dir), "--limit", str(args.limit)]
    if args.query:
        argv.extend(["--query", args.query])
    if args.freshness_status:
        argv.extend(["--freshness-status", args.freshness_status])
    if args.source_id:
        argv.extend(["--source-id", args.source_id])
    if args.contradictions_only:
        argv.append("--contradictions-only")
    if args.failure_class:
        argv.extend(["--failure-class", args.failure_class])
    if args.reflection_threshold is not None:
        argv.extend(["--reflection-threshold", str(args.reflection_threshold)])
    if args.now:
        argv.extend(["--now", args.now])
    return module_main("evidence_memory", argv)


def run_reflection_record_command(args: argparse.Namespace) -> int:
    argv = [
        "record-reflection",
        str(args.task_dir),
        "--failure-class",
        args.failure_class,
        "--trigger-condition",
        args.trigger_condition,
        "--affected-stage",
        args.affected_stage,
        "--mitigation",
        args.mitigation,
        "--anti-context",
        args.anti_context,
        "--review-evidence",
        str(args.review_evidence),
        "--status",
        args.status,
    ]
    if args.review_summary:
        argv.extend(["--review-summary", args.review_summary])
    if args.reflection_id:
        argv.extend(["--reflection-id", args.reflection_id])
    if args.expires_at:
        argv.extend(["--expires-at", args.expires_at])
    if args.dry_run:
        argv.append("--dry-run")
    if args.now:
        argv.extend(["--now", args.now])
    return module_main("evidence_memory", argv)


def run_model_routing_init_command(args: argparse.Namespace) -> int:
    argv = ["init", str(args.ops_dir), "--policy-id", args.policy_id]
    if args.output:
        argv.extend(["--output", str(args.output)])
    if args.write:
        argv.append("--write")
    if args.force:
        argv.append("--force")
    if args.now:
        argv.extend(["--now", args.now])
    return module_main("model_routing", argv)


def run_model_routing_validate_command(args: argparse.Namespace) -> int:
    argv = ["validate", str(args.policy)]
    if args.include_policy:
        argv.append("--include-policy")
    return module_main("model_routing", argv)


def run_model_routing_select_command(args: argparse.Namespace) -> int:
    argv = [
        "select",
        str(args.policy),
        "--role",
        args.role,
        "--task-type",
        args.task_type,
    ]
    if args.claim_strength:
        argv.extend(["--claim-strength", args.claim_strength])
    if args.public_claims:
        argv.append("--public-claims")
    return module_main("model_routing", argv)


def run_model_routing_eval_check_command(args: argparse.Namespace) -> int:
    return module_main(
        "model_routing",
        [
            "eval-check",
            str(args.policy),
            "--baseline",
            str(args.baseline),
            "--candidate",
            str(args.candidate),
            "--cost-tolerance-usd",
            str(args.cost_tolerance_usd),
        ],
    )


def run_scaling_assess_command(args: argparse.Namespace) -> int:
    argv = [
        str(args.ops_dir),
        "--max-task-statuses",
        str(args.max_task_statuses),
        "--max-runtime-ledger-bytes",
        str(args.max_runtime_ledger_bytes),
        "--max-eval-cases",
        str(args.max_eval_cases),
        "--max-dashboard-ms",
        str(args.max_dashboard_ms),
        "--max-stale-locks",
        str(args.max_stale_locks),
        "--stale-lock-minutes",
        str(args.stale_lock_minutes),
    ]
    if args.now:
        argv.extend(["--now", args.now])
    if args.skip_dashboard_latency:
        argv.append("--skip-dashboard-latency")
    return module_main("scaling_state", argv)


def run_brief_draft_command(args: argparse.Namespace) -> int:
    return module_main(
        "research_brief",
        ["draft", str(args.ops_dir)]
        + optional_text("--question", args.question)
        + optional_text("--objective", args.objective)
        + optional_text("--output-maturity", args.output_maturity)
        + optional_text("--audience", args.audience)
        + optional_text("--venue", args.venue)
        + repeated_option("--allowed-source-class", args.allowed_source_class)
        + repeated_option("--forbidden-source-class", args.forbidden_source_class)
        + optional_text("--private-data-policy", args.private_data_policy)
        + optional_text("--public-claims-policy", args.public_claims_policy)
        + (["--allow-browsing"] if args.allow_browsing else [])
        + (["--allow-api"] if args.allow_api else [])
        + (["--allow-code-execution"] if args.allow_code_execution else [])
        + (["--allow-network"] if args.allow_network else [])
        + (["--requires-credentials"] if args.requires_credentials else [])
        + (["--allow-paid"] if args.allow_paid else [])
        + optional_number("--max-api-usd", args.max_api_usd)
        + optional_number("--max-compute-usd", args.max_compute_usd)
        + ["--max-human-minutes", str(args.max_human_minutes)]
        + ["--max-runtime-minutes", str(args.max_runtime_minutes)]
        + repeated_option("--assumption", args.assumption)
        + repeated_option("--unresolved-question", args.unresolved_question)
        + optional_text("--brief-id", args.brief_id)
        + optional_path("--output", args.output)
        + optional_text("--now", args.now)
        + (["--dry-run"] if args.dry_run else [])
        + (["--write"] if args.write else [])
        + (["--force"] if args.force else []),
    )


def run_brief_validate_command(args: argparse.Namespace) -> int:
    return module_main("research_brief", ["validate", str(args.brief_path)])


def run_brief_apply_command(args: argparse.Namespace) -> int:
    return module_main(
        "research_brief",
        ["apply", str(args.ops_dir), str(args.brief_path)]
        + optional_text("--task-type", args.task_type)
        + (["--dry-run"] if args.dry_run else []),
    )


def cost_summary_call(args: argparse.Namespace) -> ScriptCall:
    return script_call(
        "cost_tracking",
        ["summary", str(args.ops_dir)]
        + optional_path("--ledger", args.ledger)
        + budget_option_values(args),
    )


def run_cost_summary_command(args: argparse.Namespace) -> int:
    return run_script_call(cost_summary_call(args))


def cost_ingest_usage_call(args: argparse.Namespace) -> ScriptCall:
    return script_call(
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


def run_cost_ingest_usage_command(args: argparse.Namespace) -> int:
    return run_script_call(cost_ingest_usage_call(args))


def cost_budget_check_call(args: argparse.Namespace) -> ScriptCall:
    return script_call(
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


def run_cost_budget_check_command(args: argparse.Namespace) -> int:
    return run_script_call(cost_budget_check_call(args))


def run_metrics_summarize_command(args: argparse.Namespace) -> int:
    return module_main(
        "metrics_history",
        ["summarize", str(args.ops_dir)]
        + optional_text("--month", args.month)
        + optional_path("--output", args.output),
    )


def run_metrics_operational_command(args: argparse.Namespace) -> int:
    return module_main(
        "operational_metrics",
        [str(args.ops_dir)] + optional_text("--now", args.now),
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


def run_outcomes_command(args: argparse.Namespace) -> int:
    from async_research_workflow.console import outcomes

    command_args = [args.outcomes_command, str(args.ops_dir)] + optional_text("--now", args.now)
    if args.outcomes_command == "list":
        command_args.extend(["--status", args.status])
    return outcomes.main(command_args)


def deliverable_update_options(args: argparse.Namespace, *, include_id: bool = False) -> list[str]:
    command_args: list[str] = []
    if include_id and getattr(args, "deliverable_id", None):
        command_args.extend(["--deliverable-id", args.deliverable_id])
    for flag, attr in (
        ("--title", "title"),
        ("--output-type", "output_type"),
        ("--target-maturity", "target_maturity"),
        ("--current-maturity", "current_maturity"),
        ("--target-audience", "target_audience"),
        ("--target-venue", "target_venue"),
        ("--venue-style-profile", "venue_style_profile"),
        ("--primary-artifact", "primary_artifact"),
        ("--owner", "owner"),
        ("--review-independence", "review_independence"),
        ("--reviewer", "reviewer"),
        ("--review-notes", "review_notes"),
        ("--last-reviewed-at", "last_reviewed_at"),
        ("--now", "now"),
    ):
        value = getattr(args, attr, None)
        if value is not None:
            command_args.extend([flag, str(value)])
    for flag, attr in (
        ("--source-task", "source_task"),
        ("--required-gate", "required_gate"),
        ("--complete-gate", "complete_gate"),
        ("--manuscript-gate", "manuscript_gate"),
        ("--gate-rationale", "gate_rationale"),
        ("--waiver-rationale", "waiver_rationale"),
        ("--gate-evidence", "gate_evidence"),
        ("--open-gap", "open_gap"),
    ):
        command_args.extend(repeated_option(flag, getattr(args, attr, None)))
    if getattr(args, "clear_open_gaps", False):
        command_args.append("--clear-open-gaps")
    return command_args


def run_deliverable_init_command(args: argparse.Namespace) -> int:
    return module_main(
        "deliverable_maturity",
        ["init", str(args.ops_dir)] + deliverable_update_options(args, include_id=True),
    )


def run_deliverable_target_command(args: argparse.Namespace) -> int:
    return module_main(
        "deliverable_maturity",
        ["target", str(args.ops_dir), args.deliverable_id] + deliverable_update_options(args),
    )


def run_deliverable_critic_command(args: argparse.Namespace) -> int:
    command_args = ["critic", str(args.ops_dir), args.deliverable_id]
    for flag, attr in (
        ("--review-id", "review_id"),
        ("--reviewer-role", "reviewer_role"),
        ("--independence-type", "independence_type"),
        ("--reviewer", "reviewer"),
        ("--model-or-reviewer", "model_or_reviewer"),
        ("--confidence", "confidence"),
        ("--recommended-maturity-ceiling", "recommended_maturity_ceiling"),
        ("--critical", "critical_findings"),
        ("--major", "major_findings"),
        ("--minor", "minor_findings"),
        ("--note", "note_findings"),
        ("--review-task-id", "review_task_id"),
        ("--artifact-path", "artifact_path"),
        ("--status", "status"),
        ("--notes", "notes"),
        ("--now", "now"),
    ):
        value = getattr(args, attr, None)
        if value is not None:
            command_args.extend([flag, str(value)])
    command_args.extend(repeated_option("--required-revision-row", getattr(args, "required_revision_row", None)))
    command_args.extend(repeated_option("--response-matrix-row", getattr(args, "response_matrix_row", None)))
    return module_main("deliverable_maturity", command_args)


def run_deliverable_response_command(args: argparse.Namespace) -> int:
    command_args = ["response", str(args.ops_dir), args.deliverable_id]
    for flag, attr in (
        ("--critique-id", "critique_id"),
        ("--source-review", "source_review"),
        ("--severity", "severity"),
        ("--target-section", "target_section"),
        ("--issue", "issue"),
        ("--decision", "decision"),
        ("--required-change", "required_change"),
        ("--response-rationale", "response_rationale"),
        ("--owner", "owner"),
        ("--status", "status"),
        ("--closure-artifact", "closure_artifact"),
        ("--now", "now"),
    ):
        value = getattr(args, attr, None)
        if value is not None:
            command_args.extend([flag, str(value)])
    return module_main("deliverable_maturity", command_args)


def run_deliverable_check_command(args: argparse.Namespace) -> int:
    return module_main(
        "deliverable_maturity",
        ["check", str(args.ops_dir), args.deliverable_id]
        + optional_text("--target-maturity", args.target_maturity),
    )


def run_queue_discovery_gate_command(args: argparse.Namespace) -> int:
    return module_main(
        "queue_capacity",
        [
            "discovery-gate",
            str(args.ops_dir),
            "--max-active",
            str(args.max_active),
        ]
        + repeated_option("--active-status", args.active_status),
    )


def run_queue_list_command(args: argparse.Namespace) -> int:
    return module_main(
        "queue_capacity",
        ["list", str(args.ops_dir), "--group", args.group, "--limit", str(args.limit)]
        + repeated_option("--status", args.status)
        + (["--include-files"] if args.include_files else []),
    )


def run_prompts_init_command(args: argparse.Namespace) -> int:
    return module_main(
        "prompt_library",
        ["init", str(args.ops_dir)]
        + (["--force"] if args.force else [])
        + (["--dry-run"] if args.dry_run else [])
        + optional_text("--now", args.now),
    )


def run_prompts_validate_command(args: argparse.Namespace) -> int:
    return module_main(
        "prompt_library",
        ["validate", str(args.ops_dir)]
        + ([args.prompt_id] if args.prompt_id else []),
    )


def run_prompts_list_command(args: argparse.Namespace) -> int:
    return module_main("prompt_library", ["list", str(args.ops_dir)])


def run_prompts_draft_command(args: argparse.Namespace) -> int:
    return module_main(
        "prompt_library",
        [
            "draft",
            str(args.ops_dir),
            args.prompt_id,
            "--content-file",
            str(args.content_file),
            "--message",
            args.message,
            "--author",
            args.author,
        ]
        + optional_text("--now", args.now),
    )


def run_prompts_activate_command(args: argparse.Namespace) -> int:
    return module_main(
        "prompt_library",
        [
            "activate",
            str(args.ops_dir),
            args.prompt_id,
            "--message",
            args.message,
            "--author",
            args.author,
        ]
        + (["--allow-invalid"] if args.allow_invalid else [])
        + optional_text("--now", args.now),
    )


def run_prompts_diff_command(args: argparse.Namespace) -> int:
    return module_main("prompt_library", ["diff", str(args.ops_dir), args.prompt_id])


def run_schedules_init_command(args: argparse.Namespace) -> int:
    return module_main(
        "schedule_manifest",
        ["init", str(args.ops_dir)]
        + (["--force"] if args.force else [])
        + optional_text("--now", args.now),
    )


def run_schedules_list_command(args: argparse.Namespace) -> int:
    return module_main("schedule_manifest", ["list", str(args.ops_dir)])


def run_schedules_validate_command(args: argparse.Namespace) -> int:
    return module_main("schedule_manifest", ["validate", str(args.ops_dir)])


def run_schedules_upsert_command(args: argparse.Namespace) -> int:
    return module_main(
        "schedule_manifest",
        [
            "upsert",
            str(args.ops_dir),
            args.job_id,
            "--description",
            args.description,
            "--cadence",
            args.cadence,
            "--prompt-id",
            args.prompt_id,
            "--max-runtime-minutes",
            str(args.max_runtime_minutes),
            "--concurrency-key",
            args.concurrency_key,
            "--concurrency-limit",
            str(args.concurrency_limit),
            "--status",
            args.status,
            "--message",
            args.message,
            "--author",
            args.author,
        ]
        + optional_text("--prompt-version", args.prompt_version)
        + optional_text("--disabled-reason", args.disabled_reason)
        + optional_text("--now", args.now),
    )


def run_schedules_set_status_command(args: argparse.Namespace) -> int:
    return module_main(
        "schedule_manifest",
        [
            "set-status",
            str(args.ops_dir),
            args.job_id,
            "--status",
            args.status,
            "--message",
            args.message,
            "--author",
            args.author,
        ]
        + optional_text("--disabled-reason", args.disabled_reason)
        + optional_text("--now", args.now),
    )


def run_schedules_trigger_dry_run_command(args: argparse.Namespace) -> int:
    return module_main(
        "schedule_manifest",
        ["trigger-dry-run", str(args.ops_dir), args.job_id] + optional_text("--now", args.now),
    )


def run_schedules_trigger_now_command(args: argparse.Namespace) -> int:
    return module_main(
        "schedule_manifest",
        ["trigger-now", str(args.ops_dir), args.job_id] + optional_text("--now", args.now),
    )


def decision_option_values(args: argparse.Namespace) -> list[str]:
    return (
        [
            "--decision",
            args.decision,
            "--reason",
            args.reason,
            "--approver",
            args.approver,
        ]
        + repeated_option("--related-artifact", args.related_artifact)
        + optional_text("--date", args.date)
    )


def run_decision_append_command(args: argparse.Namespace) -> int:
    return module_main(
        "human_decision_log",
        ["append", str(args.ops_dir), "--item-id", args.item_id]
        + decision_option_values(args)
        + (["--dry-run"] if args.dry_run else []),
    )


def run_decision_check_command(args: argparse.Namespace) -> int:
    return module_main(
        "human_decision_log",
        ["check", str(args.ops_dir), "--item-id", args.item_id]
        + repeated_option("--decision", args.decision),
    )


def run_decision_resolve_task_command(args: argparse.Namespace) -> int:
    return module_main(
        "human_decision_log",
        ["resolve-task", str(args.ops_dir), str(args.task_dir)]
        + decision_option_values(args)
        + optional_text("--status", args.status)
        + (["--dry-run"] if args.dry_run else []),
    )


def run_decision_auto_resolve_task_command(args: argparse.Namespace) -> int:
    return module_main(
        "human_decision_log",
        ["auto-resolve-task", str(args.ops_dir), str(args.task_dir)]
        + repeated_option("--related-artifact", args.related_artifact)
        + optional_text("--date", args.date)
        + (["--dry-run"] if args.dry_run else []),
    )


def run_decision_summarize_command(args: argparse.Namespace) -> int:
    return module_main(
        "human_decision_log",
        ["summarize", str(args.ops_dir)]
        + optional_text("--month", args.month)
        + optional_path("--output", args.output),
    )


def escalation_evaluate_options(args: argparse.Namespace) -> list[str]:
    return (
        optional_path("--ops-dir", args.ops_dir)
        + (["--apply"] if args.apply else [])
        + optional_text("--now", args.now)
        + ["--source-freshness-days", str(args.source_freshness_days)]
        + ["--reviewer-disagreement-threshold", str(args.reviewer_disagreement_threshold)]
        + ["--confidence-threshold", str(args.confidence_threshold)]
    )


def run_escalation_list_command(args: argparse.Namespace) -> int:
    return module_main("escalation_policy", ["list"])


def run_escalation_scan_needs_human_command(args: argparse.Namespace) -> int:
    return module_main("escalation_policy", ["scan-needs-human", str(args.ops_dir)])


def run_escalation_evaluate_command(args: argparse.Namespace) -> int:
    return module_main(
        "escalation_policy",
        ["evaluate", str(args.task_dir)] + escalation_evaluate_options(args),
    )


def batch_common_write_options(args: argparse.Namespace) -> list[str]:
    return ["--dry-run"] if args.dry_run else []


def run_batch_init_command(args: argparse.Namespace) -> int:
    return module_main(
        "batch_lifecycle",
        [
            "init",
            str(args.ops_dir),
            "--batch-id",
            args.batch_id,
            "--prompt-template",
            args.prompt_template,
            "--model",
            args.model,
            "--expected-output-schema",
            args.expected_output_schema,
            "--ingest-path",
            args.ingest_path,
            "--estimated-api-usd",
            str(args.estimated_api_usd),
            "--estimated-compute-usd",
            str(args.estimated_compute_usd),
        ]
        + repeated_option("--input-file", args.input_file)
        + optional_text("--source-task-id", args.source_task_id)
        + optional_path("--manifest", args.manifest)
        + batch_common_write_options(args),
    )


def run_batch_validate_manifest_command(args: argparse.Namespace) -> int:
    return module_main("batch_lifecycle", ["validate-manifest", str(args.manifest)])


def run_batch_submit_command(args: argparse.Namespace) -> int:
    return module_main(
        "batch_lifecycle",
        [
            "submit",
            str(args.manifest),
            "--provider-batch-id",
            args.provider_batch_id,
            "--api-usd",
            str(args.api_usd),
            "--compute-usd",
            str(args.compute_usd),
        ]
        + optional_path("--ops-dir", args.ops_dir)
        + batch_common_write_options(args),
    )


def run_batch_complete_command(args: argparse.Namespace) -> int:
    return module_main(
        "batch_lifecycle",
        ["complete", str(args.manifest)]
        + repeated_option("--output-file", args.output_file)
        + batch_common_write_options(args),
    )


def run_batch_ingest_command(args: argparse.Namespace) -> int:
    return module_main(
        "batch_lifecycle",
        ["ingest", str(args.manifest), "--ingest-task-id", args.ingest_task_id]
        + repeated_option("--ingested-file", args.ingested_file)
        + batch_common_write_options(args),
    )


def run_batch_mark_reviewed_command(args: argparse.Namespace) -> int:
    return module_main(
        "batch_lifecycle",
        ["mark-reviewed", str(args.manifest), "--review-task-id", args.review_task_id]
        + batch_common_write_options(args),
    )


def run_batch_trust_status_command(args: argparse.Namespace) -> int:
    return module_main(
        "batch_lifecycle",
        ["trust-status", str(args.manifest)] + (["--allow-untrusted"] if args.allow_untrusted else []),
    )


def revision_schema_prefix(args: argparse.Namespace) -> list[str]:
    return optional_path("--schema", args.schema)


def run_revision_defaults_command(args: argparse.Namespace) -> int:
    return module_main("revision_counter", ["defaults", "--tier", str(args.tier)])


def run_revision_request_command(args: argparse.Namespace) -> int:
    return module_main(
        "revision_counter",
        revision_schema_prefix(args)
        + ["request", str(args.task_dir), "--reviewer", args.reviewer, "--reason", args.reason]
        + (["--dry-run"] if args.dry_run else []),
    )


def run_revision_inspect_command(args: argparse.Namespace) -> int:
    return module_main("revision_counter", revision_schema_prefix(args) + ["inspect", str(args.task_dir)])


def run_revision_scan_limits_command(args: argparse.Namespace) -> int:
    return module_main(
        "revision_counter",
        ["scan-limits", str(args.tasks_dir)] + (["--markdown"] if args.markdown else []),
    )


def run_anti_context_build_command(args: argparse.Namespace) -> int:
    return module_main(
        "generate_anti_context",
        [
            "build",
            str(args.ops_dir),
            "--title",
            args.title,
            "--threshold",
            str(args.threshold),
            "--max-items",
            str(args.max_items),
        ]
        + optional_path("--task-dir", args.task_dir)
        + optional_path("--output", args.output),
    )


def run_workflow_create_task_command(args: argparse.Namespace) -> int:
    return module_main(
        "task_authoring",
        ["create", str(args.ops_dir), "--title", args.title]
        + optional_text("--task-id", args.task_id)
        + optional_text("--slug", args.slug)
        + optional_text("--task-type", args.task_type)
        + optional_text("--objective", args.objective)
        + repeated_option("--context", args.context)
        + repeated_option("--allowed-path", args.allowed_path)
        + repeated_option("--data-audit-ref", args.data_audit_ref)
        + optional_text("--catalog-idea-id", args.catalog_idea_id)
        + optional_path("--brief", args.brief)
        + ["--priority", str(args.priority)]
        + ["--review-tier", str(args.review_tier)]
        + ["--max-minutes", str(args.max_minutes)]
        + ["--max-turns", str(args.max_turns)]
        + ["--max-revisions", str(args.max_revisions)]
        + optional_text("--model-tier", args.model_tier)
        + ["--max-api-usd", str(args.max_api_usd)]
        + ["--max-compute-usd", str(args.max_compute_usd)]
        + (["--allow-browsing"] if args.allow_browsing else [])
        + (["--allow-code-execution"] if args.allow_code_execution else [])
        + (["--allow-network"] if args.allow_network else [])
        + optional_text("--transition-reason", args.transition_reason)
        + (["--dry-run"] if args.dry_run else [])
        + (["--write"] if args.write else []),
    )


def run_idea_catalog_init_command(args: argparse.Namespace) -> int:
    return module_main(
        "idea_catalog",
        ["init", str(args.ops_dir)]
        + (["--dry-run"] if args.dry_run else [])
        + (["--write"] if args.write else []),
    )


def run_idea_catalog_validate_command(args: argparse.Namespace) -> int:
    return module_main("idea_catalog", ["validate", str(args.ops_dir)])


def run_idea_catalog_list_command(args: argparse.Namespace) -> int:
    return module_main("idea_catalog", ["list", str(args.ops_dir)] + optional_text("--status", args.status))


def run_idea_catalog_dashboard_command(args: argparse.Namespace) -> int:
    return module_main("idea_catalog", ["dashboard", str(args.ops_dir), "--max-blockers", str(args.max_blockers)])


def run_idea_catalog_show_command(args: argparse.Namespace) -> int:
    return module_main("idea_catalog", ["show", str(args.ops_dir), args.idea_id])


def run_idea_metrics_command(args: argparse.Namespace) -> int:
    return module_main("idea_catalog", ["metrics", str(args.ops_dir)] + optional_text("--now", args.now))


def run_idea_trace_command(args: argparse.Namespace) -> int:
    return module_main("idea_catalog", ["trace", str(args.ops_dir), args.idea_id] + optional_text("--now", args.now))


def run_idea_catalog_maintain_command(args: argparse.Namespace) -> int:
    return module_main(
        "idea_catalog",
        ["maintain", str(args.ops_dir)]
        + (["--dry-run"] if args.dry_run else [])
        + (["--write"] if args.write else [])
        + (["--update-existing"] if args.update_existing else []),
    )


def run_idea_capture_command(args: argparse.Namespace) -> int:
    return module_main(
        "idea_catalog",
        ["capture", str(args.ops_dir)]
        + optional_text("--from-inbox", args.from_inbox)
        + optional_text("--id", args.idea_id)
        + optional_text("--title", args.title)
        + (["--dry-run"] if args.dry_run else [])
        + (["--write"] if args.write else [])
        + (["--update-existing"] if args.update_existing else []),
    )


def run_idea_promote_command(args: argparse.Namespace) -> int:
    return module_main(
        "idea_catalog",
        ["promote", str(args.ops_dir), args.idea_id]
        + optional_text("--task-type", args.task_type)
        + optional_path("--brief", args.brief)
        + optional_text("--preflight-hash", args.preflight_hash)
        + (["--allow-duplicate"] if args.allow_duplicate else [])
        + (["--human-override"] if args.human_override else [])
        + (["--dry-run"] if args.dry_run else [])
        + (["--write"] if args.write else []),
    )


def run_idea_resolve_command(args: argparse.Namespace) -> int:
    return module_main(
        "idea_catalog",
        ["resolve", str(args.ops_dir), args.idea_id]
        + optional_text("--status", args.status)
        + optional_text("--reason", args.reason)
        + optional_text("--approver", args.approver)
        + optional_text("--revisit", args.revisit)
        + repeated_option("--related-artifact", args.related_artifact)
        + optional_text("--date", args.date)
        + (["--dry-run"] if args.dry_run else [])
        + (["--write"] if args.write else []),
    )


def run_idea_park_command(args: argparse.Namespace) -> int:
    return module_main(
        "idea_catalog",
        ["park", str(args.ops_dir), args.idea_id]
        + optional_text("--reason", args.reason)
        + optional_text("--revisit", args.revisit)
        + (["--dry-run"] if args.dry_run else [])
        + (["--write"] if args.write else []),
    )


def run_idea_reject_command(args: argparse.Namespace) -> int:
    return module_main(
        "idea_catalog",
        ["reject", str(args.ops_dir), args.idea_id]
        + optional_text("--reason", args.reason)
        + optional_text("--revisit", args.revisit)
        + (["--dry-run"] if args.dry_run else [])
        + (["--write"] if args.write else []),
    )


def run_review_prepare_context_command(args: argparse.Namespace) -> int:
    return module_main(
        "prepare_review_context",
        [
            "prepare",
            str(args.task_dir),
            "--role",
            args.role,
            "--bundle-dir",
            str(args.bundle_dir),
        ]
        + (["--force"] if args.force else []),
    )


def run_review_install_context_command(args: argparse.Namespace) -> int:
    return module_main(
        "prepare_review_context",
        ["install", str(args.bundle_dir)] + (["--force"] if args.force else []),
    )


def review_authoring_options(args: argparse.Namespace) -> list[str]:
    return (
        [str(args.task_dir)]
        + optional_text("--role", args.role)
        + optional_text("--decision", args.decision)
        + optional_text("--claim-strength", args.claim_strength)
        + optional_text("--confidence", args.confidence)
        + repeated_option("--concern", args.concern)
        + repeated_option("--followup", args.followup)
        + repeated_option("--evidence-gap", args.evidence_gap)
        + (["--force"] if args.force else [])
    )


def run_review_draft_command(args: argparse.Namespace) -> int:
    return module_main(
        "review_authoring",
        ["draft"] + review_authoring_options(args) + (["--write"] if args.write else []),
    )


def run_review_submit_command(args: argparse.Namespace) -> int:
    return module_main(
        "review_authoring",
        ["submit"] + review_authoring_options(args) + (["--dry-run"] if args.dry_run else []),
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
        description="Run the durable package acceptance suite against isolated temporary fixtures, including promotion-write end-to-end acceptance.",
        epilog="Exits 0 when all checks pass, 1 when any acceptance check fails.",
    )
    acceptance.add_argument("--work-dir", type=Path, help="Use this fixture directory instead of the default temp path.")
    acceptance.add_argument("--keep-work-dir", action="store_true", help="Keep isolated fixtures for debugging failed checks.")
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
    health.add_argument("--monthly-budget-usd", type=float, help="Override the monthly budget used for health budget-pressure checks.")
    health.add_argument("--weekly-budget-usd", type=float, help="Override the weekly budget used for health budget-pressure checks.")
    health.set_defaults(func=run_health_command)


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


def register_console_commands(subparsers) -> None:
    console = add_command(
        subparsers,
        "console",
        help="Render or serve the local operator console.",
        description=(
            "Serve the local dashboard shell with guarded setup and task inspection actions, or render the Slice 1 "
            "snapshot with `console snapshot research_ops --json`."
        ),
        epilog=(
            "Examples:\n"
            "  async-research console research_ops\n"
            "  async-research console snapshot research_ops --json\n\n"
            "Slice 5 serves static assets, GET /api/snapshot, GET /api/actions, and guarded POST /api/actions/run.\n"
            "Dashboard mutations are limited to explicit init, surface update, and outcomes refresh actions; task validation and lock actions are read-only.\n\n"
            "Exit codes:\n"
            "  console: 0 when the server stops cleanly; 3 for invalid console arguments.\n"
            "  console snapshot: 0 when the snapshot is rendered; 3 for invalid request flags."
        ),
    )
    console.add_argument(
        "console_args",
        nargs="*",
        help="Optional ops_dir, or `snapshot [ops_dir]` for the read-only JSON snapshot.",
    )
    console.add_argument("--host", default="127.0.0.1", help="Host interface to bind for the dashboard server.")
    console.add_argument("--port", type=int, default=8765, help="Port to bind for the dashboard server.")
    console.add_argument("--json", action="store_true", help="Render JSON output when using `console snapshot`.")
    console.add_argument("--now", help="Override current time when using `console snapshot`.")
    console.set_defaults(func=run_console_command)


def register_schema_command(subparsers) -> None:
    schema = add_command(
        subparsers,
        "schema-check",
        help="Validate schema versions for workflow JSON artifacts.",
        description="Check task status and other versioned JSON artifacts for expected schema versions.",
    )
    add_common_ops(schema)
    schema.set_defaults(func=lambda a: module_main("check_schema_versions", [str(a.ops_dir)]))


def register_mode_commands(subparsers) -> None:
    mode = add_command(
        subparsers,
        "mode",
        help="Inspect or set workspace interaction mode.",
        description=(
            "Show, set, or validate research_ops/interaction_mode.json without changing task transitions. "
            "Missing config resolves to a manual-compatible default until an explicit set command writes the file."
        ),
    )
    mode_sub = mode.add_subparsers(dest="mode_command", required=True)

    show = add_command(
        mode_sub,
        "show",
        help="Show the effective interaction mode as JSON.",
        description="Show the effective interaction mode as JSON by reading interaction_mode.json, or report the deterministic manual-compatible default when the file is missing.",
        epilog="Exits 0 when a valid config or missing-config default is available, and 4 when config is invalid or unreadable.",
    )
    add_common_ops(show)
    show.set_defaults(func=run_mode_show_command)

    set_cmd = add_command(
        mode_sub,
        "set",
        help="Write a safe interaction mode config.",
        description="Write research_ops/interaction_mode.json with conservative defaults for the selected mode.",
        epilog="Exits 0 when the config is written, and 4 when the workspace or existing config is invalid.",
    )
    add_common_ops(set_cmd)
    set_cmd.add_argument(
        "--mode",
        required=True,
        choices=("manual", "guided", "supervised", "autonomous", "publication_guarded"),
        help="Interaction mode to write.",
    )
    set_cmd.set_defaults(func=run_mode_set_command)

    validate_cmd = add_command(
        mode_sub,
        "validate",
        help="Validate interaction mode config.",
        description="Validate interaction_mode.json schema and hard-stop safeguards without mutating research_ops.",
        epilog="Exits 0 when the config or missing-config default is valid, and 4 when it fails closed.",
    )
    add_common_ops(validate_cmd)
    validate_cmd.set_defaults(func=run_mode_validate_command)


def register_workflow_commands(subparsers) -> None:
    workflow = add_command(
        subparsers,
        "workflow",
        help="Run or dry-run canonical operator workflow sequences.",
        description="Coordinate schema, readiness, review aggregation, accepted-memory, surface, and health commands without replacing them.",
    )
    workflow_sub = workflow.add_subparsers(dest="workflow_command", required=True)
    check = add_command(
        workflow_sub,
        "check",
        help="Run read-only workspace workflow checks.",
        description="Run read-only workspace workflow checks: schema-check, readiness --dry-run, surface validate, and health --dry-run as one JSON report.",
    )
    add_common_ops(check)
    check.set_defaults(func=lambda a: module_main("workflow_orchestrator", ["check", str(a.ops_dir)]))
    status = add_command(
        workflow_sub,
        "status",
        help="Report read-only task status and next legal commands.",
        description=(
            "Report read-only task status without mutating it: current status, previous status, type, review tier, "
            "lock state, worker output, review files, human gate, revision counters, result state, and next legal commands."
        ),
    )
    status.add_argument("task_dir", type=Path, help="Task directory containing status.json.")
    status.add_argument("--ops-dir", type=Path, help="Override the research_ops directory inferred from the task path.")
    status.add_argument("--stale-minutes", type=float, default=60.0, help="Lock age threshold for stale-lock reporting.")
    status.set_defaults(
        func=lambda a: module_main(
            "workflow_orchestrator",
            ["status", str(a.task_dir)]
            + (["--ops-dir", str(a.ops_dir)] if a.ops_dir else [])
            + (["--stale-minutes", str(a.stale_minutes)] if a.stale_minutes != 60.0 else []),
        )
    )
    next_cmd = add_command(
        workflow_sub,
        "next",
        help="Recommend the next safe workspace action.",
        description=(
            "Read the workspace snapshot and recommend one next safe workspace action, with alternatives, "
            "for malformed state, human gates, locks, review work, worker-ready tasks, accepted-memory revalidation, "
            "foundation warnings, or maintenance."
        ),
    )
    next_cmd.add_argument("ops_dir", nargs="?", type=Path, default=Path("research_ops"), help="research_ops workspace directory.")
    next_cmd.add_argument("--stale-minutes", type=float, default=60.0, help="Lock age threshold for stale-lock recommendations.")
    next_cmd.set_defaults(
        func=lambda a: module_main(
            "workflow_orchestrator",
            ["next", str(a.ops_dir)]
            + (["--stale-minutes", str(a.stale_minutes)] if a.stale_minutes != 60.0 else []),
        )
    )
    create_task = add_command(
        workflow_sub,
        "create-task",
        help="Preview or write a minimal valid task folder.",
        description=(
            "Create a manual or LLM-authored minimal valid task folder from a public helper: status.json uses non-null placeholders, "
            "task.md documents generic-artifact claim caps, and --write creates the task folder without overwriting existing tasks."
        ),
    )
    create_task.add_argument("ops_dir", nargs="?", type=Path, default=Path("research_ops"), help="research_ops workspace directory.")
    create_task.add_argument("--title", required=True, help="Human-readable task title.")
    create_task.add_argument("--task-id", help="Explicit TASK-0000 id; defaults to the next available id.")
    create_task.add_argument("--slug", help="Task directory slug; defaults to a slugified title.")
    create_task.add_argument("--task-type", choices=TASK_TYPES, default="data_readiness", help="Task type for status.json.")
    create_task.add_argument("--objective", help="Objective paragraph for task.md.")
    create_task.add_argument("--context", action="append", default=[], help="Context path, source, or note. Repeat for multiple entries.")
    create_task.add_argument("--allowed-path", action="append", default=[], help="Additional allowed path in status.json. Repeat as needed.")
    create_task.add_argument("--data-audit-ref", action="append", default=[], help="DS-* ref required by this task. Repeat as needed.")
    create_task.add_argument("--catalog-idea-id", help="Optional IDEA-0000 link for promoted tasks.")
    create_task.add_argument("--brief", type=Path, help="Optional research_ops/briefs/research_brief.json path; defaults to the workspace brief when present.")
    create_task.add_argument("--priority", type=int, choices=[1, 2, 3, 4, 5], default=3)
    create_task.add_argument("--review-tier", type=int, choices=[1, 2, 3], default=1)
    create_task.add_argument("--max-minutes", type=int, default=45)
    create_task.add_argument("--max-turns", type=int, default=6)
    create_task.add_argument("--max-revisions", type=int, choices=[0, 1, 2, 3, 4, 5], default=1)
    create_task.add_argument("--model-tier", default="codex_standard")
    create_task.add_argument("--max-api-usd", type=float, default=0.0)
    create_task.add_argument("--max-compute-usd", type=float, default=0.0)
    create_task.add_argument("--allow-browsing", action="store_true")
    create_task.add_argument("--allow-code-execution", action="store_true")
    create_task.add_argument("--allow-network", action="store_true")
    create_task.add_argument("--transition-reason", default="manual_task_created_from_template")
    create_task.add_argument("--dry-run", action="store_true", help="Preview without writing; this is the default.")
    create_task.add_argument("--write", action="store_true", help="Create task.md, status.json, and review/artifact directories.")
    create_task.set_defaults(func=run_workflow_create_task_command)
    worker_start = add_command(
        workflow_sub,
        "worker-start",
        help="Claim a ready task and move it to in_progress.",
        description=(
            "Acquire the task-local LOCK/ and transition one ready task from ready_for_worker to in_progress. "
            "Use --dry-run first to validate the task, workspace, and transition without writing."
        ),
    )
    worker_start.add_argument("task_dir", type=Path, help="Task directory containing status.json.")
    worker_start.add_argument("--ops-dir", type=Path, help="Override the research_ops directory inferred from the task path.")
    worker_start.add_argument("--owner", help="Worker owner written to LOCK/owner.json; defaults to the task-lock owner heuristic.")
    worker_start.add_argument("--stale-minutes", type=float, default=60.0, help="Lock age threshold for stale-lock takeover.")
    worker_start.add_argument("--dry-run", action="store_true", help="Validate the claim and transition without writing status.json or LOCK/.")
    worker_start.set_defaults(
        func=lambda a: module_main(
            "workflow_orchestrator",
            ["worker-start", str(a.task_dir)]
            + (["--ops-dir", str(a.ops_dir)] if a.ops_dir else [])
            + (["--owner", str(a.owner)] if a.owner else [])
            + (["--stale-minutes", str(a.stale_minutes)] if a.stale_minutes != 60.0 else [])
            + (["--dry-run"] if a.dry_run else []),
        )
    )
    worker_complete = add_command(
        workflow_sub,
        "worker-complete",
        help="Move an in-progress task with worker output to awaiting_review.",
        description=(
            "Validate non-empty worker_output.md for an in-progress task, write the in_progress -> awaiting_review transition, "
            "and release the task-local LOCK/ when present."
        ),
    )
    worker_complete.add_argument("task_dir", type=Path, help="Task directory containing status.json and worker_output.md.")
    worker_complete.add_argument("--ops-dir", type=Path, help="Override the research_ops directory inferred from the task path.")
    worker_complete.add_argument("--owner", help="Worker owner expected in LOCK/owner.json; defaults to the task-lock owner heuristic.")
    worker_complete.add_argument("--stale-minutes", type=float, default=60.0, help="Lock age threshold for lock-state reporting.")
    worker_complete.add_argument("--force-release", action="store_true", help="Release a mismatched lock owner after external confirmation.")
    worker_complete.add_argument("--dry-run", action="store_true", help="Validate output and transition without writing status.json or releasing LOCK/.")
    worker_complete.set_defaults(
        func=lambda a: module_main(
            "workflow_orchestrator",
            ["worker-complete", str(a.task_dir)]
            + (["--ops-dir", str(a.ops_dir)] if a.ops_dir else [])
            + (["--owner", str(a.owner)] if a.owner else [])
            + (["--stale-minutes", str(a.stale_minutes)] if a.stale_minutes != 60.0 else [])
            + (["--force-release"] if a.force_release else [])
            + (["--dry-run"] if a.dry_run else []),
        )
    )
    advance = add_command(
        workflow_sub,
        "advance",
        help="Run the canonical post-worker task workflow.",
        description="Run or dry-run the post-worker task workflow for one reviewed task while reporting every subcommand result.",
    )
    advance.add_argument("task_dir", type=Path, help="Task directory containing status.json and reviews/.")
    advance.add_argument("--ops-dir", type=Path, help="Override the research_ops directory inferred from the task path.")
    advance.add_argument("--dry-run", action="store_true", help="Print the plan and run only read-only checks.")
    advance.set_defaults(
        func=lambda a: module_main(
            "workflow_orchestrator",
            ["advance", str(a.task_dir)]
            + (["--ops-dir", str(a.ops_dir)] if a.ops_dir else [])
            + (["--dry-run"] if a.dry_run else []),
        )
    )


def register_queue_commands(subparsers) -> None:
    queue = add_command(
        subparsers,
        "queue",
        help="Inspect queue and task-board state.",
        description="Run read-only queue capacity checks and list task-board state for operators.",
    )
    queue_sub = queue.add_subparsers(dest="queue_command", required=True)
    discovery = add_command(
        queue_sub,
        "discovery-gate",
        help="Skip discovery when active task capacity is full.",
        description="Read task status files and decide whether discovery should run without mutating research_ops.",
        epilog="Exits 0 with action=discovery_allowed, or 2 with action=discovery_skipped.",
    )
    add_common_ops(discovery)
    discovery.add_argument("--max-active", type=int, default=10, help="Maximum active tasks allowed before discovery is skipped.")
    discovery.add_argument(
        "--active-status",
        action="append",
        help="Status counted as active. Repeat to override the default active-status set.",
    )
    discovery.set_defaults(func=run_queue_discovery_gate_command)
    list_cmd = add_command(
        queue_sub,
        "list",
        help="List queue and task-board state.",
        description=(
            "Read the dashboard task snapshot and return filtered task-board state plus queue counts without mutating research_ops."
        ),
    )
    add_common_ops(list_cmd)
    list_cmd.add_argument(
        "--group",
        choices=("all", "active", "ready_for_worker", "in_progress", "review", "human", "blocked", "malformed"),
        default="all",
        help="Task group to return.",
    )
    list_cmd.add_argument("--status", action="append", help="Only include tasks with this status. Repeat to include multiple statuses.")
    list_cmd.add_argument("--limit", type=int, default=50, help="Maximum rows to return; use 0 for no limit.")
    list_cmd.add_argument("--include-files", action="store_true", help="Include task-local file link metadata.")
    list_cmd.set_defaults(func=run_queue_list_command)


def register_prompt_commands(subparsers) -> None:
    prompts = add_command(
        subparsers,
        "prompts",
        help="Initialize, validate, draft, and activate scheduled prompt library files.",
        description="Manage repo-backed prompt library files under research_ops/prompts with validation, history, and activation.",
    )
    prompt_sub = prompts.add_subparsers(dest="prompts_command", required=True)
    init = add_command(
        prompt_sub,
        "init",
        help="Create missing research_ops/prompts files.",
        description="Create default active prompt files, matching drafts, versions.json, and history.jsonl without overwriting existing prompts unless --force is passed.",
    )
    add_common_ops(init)
    init.add_argument("--force", action="store_true", help="Replace existing default prompt files.")
    init.add_argument("--dry-run", action="store_true", help="Preview prompt library files and history rows without writing.")
    init.add_argument("--now", help="Override the initialization timestamp.")
    init.set_defaults(func=run_prompts_init_command)
    list_cmd = add_command(
        prompt_sub,
        "list",
        help="List prompt library state.",
        description="Read active prompts, drafts, validation results, active-vs-draft diffs, history, and schedule bindings.",
    )
    add_common_ops(list_cmd)
    list_cmd.set_defaults(func=run_prompts_list_command)
    validate = add_command(
        prompt_sub,
        "validate",
        help="Validate prompt drafts or active prompt files.",
        description="Validate required front matter, scheduler prompt sections, stop rules, cost/escalation limits, and escalation-policy references.",
    )
    add_common_ops(validate)
    validate.add_argument("prompt_id", nargs="?", help="Optional prompt id such as worker.")
    validate.set_defaults(func=run_prompts_validate_command)
    draft = add_command(
        prompt_sub,
        "draft",
        help="Save a prompt draft from a content file.",
        description="Save a prompt draft under research_ops/prompts/drafts and record prompt history without activating it.",
    )
    add_required_ops(draft)
    draft.add_argument("prompt_id", help="Prompt id such as worker.")
    draft.add_argument("--content-file", type=Path, required=True, help="Markdown file containing the draft prompt.")
    draft.add_argument("--message", required=True, help="Reason for the draft change.")
    draft.add_argument("--author", default="human", help="Operator or agent saving the draft.")
    draft.add_argument("--now", help="Override history timestamp.")
    draft.set_defaults(func=run_prompts_draft_command)
    activate = add_command(
        prompt_sub,
        "activate",
        help="Activate a prompt draft as the next version.",
        description="Validate a prompt draft, write the next active version, update versions.json, append history, and record a decision row.",
    )
    add_required_ops(activate)
    activate.add_argument("prompt_id", help="Prompt id such as worker.")
    activate.add_argument("--message", required=True, help="Reason for activation.")
    activate.add_argument("--author", default="human", help="Operator or agent activating the prompt.")
    activate.add_argument("--allow-invalid", action="store_true", help="Explicitly activate despite validation errors.")
    activate.add_argument("--now", help="Override activation timestamp.")
    activate.set_defaults(func=run_prompts_activate_command)
    diff = add_command(
        prompt_sub,
        "diff",
        help="Render active-vs-draft prompt diff.",
        description="Render a unified diff between the active prompt and its saved draft without mutating files.",
    )
    add_common_ops(diff)
    diff.add_argument("prompt_id", help="Prompt id such as worker.")
    diff.set_defaults(func=run_prompts_diff_command)


def register_schedule_commands(subparsers) -> None:
    schedules = add_command(
        subparsers,
        "schedules",
        help="Manage recurring-job schedule intent manifests.",
        description="Create, validate, list, update, enable, and disable schedule intent in research_ops/schedules.json without installing external automation.",
    )
    schedule_sub = schedules.add_subparsers(dest="schedules_command", required=True)
    init = add_command(
        schedule_sub,
        "init",
        help="Create research_ops/schedules.json.",
        description="Create research_ops/schedules.json with default recurring-job intent rows, prompt bindings, max runtime, and concurrency limits.",
    )
    add_common_ops(init)
    init.add_argument("--force", action="store_true", help="Replace an existing schedule manifest.")
    init.add_argument("--now", help="Override the initialization timestamp.")
    init.set_defaults(func=run_schedules_init_command)
    list_cmd = add_command(
        schedule_sub,
        "list",
        help="List schedule jobs.",
        description="Read schedule jobs, validation state, prompt bindings, max runtime, concurrency, and schedule-change history.",
    )
    add_common_ops(list_cmd)
    list_cmd.set_defaults(func=run_schedules_list_command)
    validate = add_command(
        schedule_sub,
        "validate",
        help="Validate schedule manifest.",
        description="Validate job ids, enabled/disabled status, prompt bindings, max runtime, and concurrency fields.",
    )
    add_common_ops(validate)
    validate.set_defaults(func=run_schedules_validate_command)
    upsert = add_command(
        schedule_sub,
        "upsert",
        help="Create or update one schedule job.",
        description="Write one schedule-intent job row and append schedule history without installing cron, launchd, GitHub Actions, or Codex automations.",
    )
    add_required_ops(upsert)
    upsert.add_argument("job_id", help="Stable job id such as worker-loop.")
    upsert.add_argument("--description", required=True, help="Human-readable job description.")
    upsert.add_argument("--cadence", required=True, help="Schedule intent cadence such as hourly, daily, weekly, or manual.")
    upsert.add_argument("--prompt-id", required=True, help="Prompt id to bind, such as worker.")
    upsert.add_argument("--prompt-version", help="Prompt version to bind; defaults to the active version when omitted.")
    upsert.add_argument("--max-runtime-minutes", type=int, required=True, help="Maximum intended runtime in minutes.")
    upsert.add_argument("--concurrency-key", required=True, help="Concurrency group key used by trigger-now checks.")
    upsert.add_argument("--concurrency-limit", type=int, default=1, help="Maximum concurrent runs for this key.")
    upsert.add_argument("--status", choices=("enabled", "disabled"), default="disabled", help="Stored schedule intent status.")
    upsert.add_argument("--disabled-reason", help="Reason when status is disabled.")
    upsert.add_argument("--message", required=True, help="Reason for the schedule change.")
    upsert.add_argument("--author", default="human", help="Operator or agent changing the schedule.")
    upsert.add_argument("--now", help="Override schedule history timestamp.")
    upsert.set_defaults(func=run_schedules_upsert_command)
    set_status = add_command(
        schedule_sub,
        "set-status",
        help="Enable or disable one schedule job intent.",
        description="Toggle one schedule job's stored enabled/disabled intent and append schedule history.",
    )
    add_required_ops(set_status)
    set_status.add_argument("job_id", help="Stable job id such as worker-loop.")
    set_status.add_argument("--status", choices=("enabled", "disabled"), required=True, help="New schedule intent status.")
    set_status.add_argument("--message", required=True, help="Reason for changing schedule intent.")
    set_status.add_argument("--author", default="human", help="Operator or agent changing the schedule.")
    set_status.add_argument("--disabled-reason", help="Reason when disabling schedule intent.")
    set_status.add_argument("--now", help="Override schedule history timestamp.")
    set_status.set_defaults(func=run_schedules_set_status_command)
    trigger = add_command(
        schedule_sub,
        "trigger-dry-run",
        help="Preview one trigger-now run without launching Codex.",
        description=(
            "Preview a trigger-now run for one schedule job, including command preview, readiness check, "
            "concurrency check, disabled-job blocking, and run id preview. This does not launch Codex."
        ),
    )
    add_required_ops(trigger)
    trigger.add_argument("job_id", help="Stable job id such as worker-loop.")
    trigger.add_argument("--now", help="Override the trigger run id timestamp.")
    trigger.set_defaults(func=run_schedules_trigger_dry_run_command)
    trigger_now = add_command(
        schedule_sub,
        "trigger-now",
        help="Run one enabled schedule job now.",
        description=(
            "Execute one enabled schedule job with a bounded local process runner, write run artifacts, "
            "capture stdout, stderr, JSON events, final message, and ingest usage metadata when available."
        ),
    )
    add_required_ops(trigger_now)
    trigger_now.add_argument("job_id", help="Stable job id such as worker-loop.")
    trigger_now.add_argument("--now", help="Override the trigger run id timestamp.")
    trigger_now.set_defaults(func=run_schedules_trigger_now_command)


def add_decision_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--decision", required=True, choices=DECISION_CHOICES, help="Structured human decision value to record.")
    parser.add_argument("--reason", required=True, help="Reason for the human decision.")
    parser.add_argument("--approver", required=True, help="Human or owner approving the decision.")
    parser.add_argument("--related-artifact", action="append", default=[], help="Related task, artifact, or report path. Repeat for multiple artifacts.")
    parser.add_argument("--date", help="Decision timestamp or date to record; defaults to current UTC time.")


def register_decision_commands(subparsers) -> None:
    decision = add_command(
        subparsers,
        "decision",
        help="Append, check, resolve, auto-resolve, or summarize decisions.",
        description="Manage append-only decisions.md and auto_decisions.md audit trails for human and mode-policy gates.",
    )
    decision_sub = decision.add_subparsers(dest="decision_command", required=True)
    append = add_command(
        decision_sub,
        "append",
        help="Append a structured human decision row.",
        description="Append a decision row to decisions.md, or preview the exact row with --dry-run.",
    )
    add_common_ops(append)
    append.add_argument("--item-id", required=True, help="Task, idea, source, or policy item the decision applies to.")
    add_decision_options(append)
    append.add_argument("--dry-run", action="store_true", help="Print the row that would be appended without writing decisions.md.")
    append.set_defaults(func=run_decision_append_command)
    check = add_command(
        decision_sub,
        "check",
        help="Check whether an item has a matching decision row.",
        description="Read decisions.md and report whether an item has a matching decision row.",
    )
    add_common_ops(check)
    check.add_argument("--item-id", required=True, help="Item identifier to look up in decisions.md.")
    check.add_argument("--decision", action="append", choices=DECISION_CHOICES, help="Accepted decision value. Repeat to allow multiple values.")
    check.set_defaults(func=run_decision_check_command)
    resolve = add_command(
        decision_sub,
        "resolve-task",
        help="Resolve a needs_human task through the decision log.",
        description="Resolve a needs_human task by appending a decision row, updating status.json, and validating the transition.",
    )
    add_required_ops(resolve)
    resolve.add_argument("task_dir", type=Path, help="Task directory or status.json path to resolve.")
    add_decision_options(resolve)
    resolve.add_argument("--status", choices=RESOLUTION_STATUS_CHOICES, help="Target status; defaults from the decision when possible.")
    resolve.add_argument("--dry-run", action="store_true", help="Preview decision and status transition without writing decisions.md or status.json.")
    resolve.set_defaults(func=run_decision_resolve_task_command)
    auto_resolve = add_command(
        decision_sub,
        "auto-resolve-task",
        help="Resolve a needs_human task when mode policy allows it.",
        description=(
            "Evaluate the current interaction mode and structured human_gate, then resolve the task with "
            "framework-policy decisions.md and auto_decisions.md rows only when the route is allowed. "
            "Use --dry-run to explain the policy result without writing."
        ),
    )
    add_required_ops(auto_resolve)
    auto_resolve.add_argument("task_dir", type=Path, help="Task directory or status.json path to evaluate and resolve.")
    auto_resolve.add_argument("--related-artifact", action="append", default=[], help="Related task, artifact, or report path. Repeat for multiple artifacts.")
    auto_resolve.add_argument("--date", help="Decision timestamp or date to record; defaults to current UTC time.")
    auto_resolve.add_argument("--dry-run", action="store_true", help="Explain the mode-policy route without writing decisions.md or status.json.")
    auto_resolve.set_defaults(func=run_decision_auto_resolve_task_command)
    summarize = add_command(
        decision_sub,
        "summarize",
        help="Summarize human and auto decisions for calibration.",
        description="Summarize human and auto-decision rows by decision, reason, actor, mode, and policy, optionally writing Markdown.",
    )
    add_common_ops(summarize)
    summarize.add_argument("--month", help="Only include decision rows whose date starts with YYYY-MM.")
    summarize.add_argument("--output", type=Path, help="Write a Markdown summary to this path.")
    summarize.set_defaults(func=run_decision_summarize_command)


def register_escalation_commands(subparsers) -> None:
    escalation = add_command(
        subparsers,
        "escalation",
        help="Inspect and apply deterministic human escalation gates.",
        description="List escalation policy triggers, validate structured needs_human gates, and evaluate one task.",
    )
    escalation_sub = escalation.add_subparsers(dest="escalation_command", required=True)
    list_cmd = add_command(
        escalation_sub,
        "list",
        help="List escalation policy triggers.",
        description="Print the packaged deterministic escalation policy trigger table as JSON.",
    )
    list_cmd.set_defaults(func=run_escalation_list_command)
    scan = add_command(
        escalation_sub,
        "scan-needs-human",
        help="Validate structured needs_human gates.",
        description="Read task status files and verify structured needs_human gates.",
        epilog="Exits 0 when structured gates are valid, 2 when needs_human gates are incomplete, and 4 when the workspace is missing.",
    )
    add_common_ops(scan)
    scan.set_defaults(func=run_escalation_scan_needs_human_command)
    evaluate = add_command(
        escalation_sub,
        "evaluate",
        help="Evaluate one task against escalation policy.",
        description="Evaluate deterministic escalation triggers for one task; --apply writes a structured needs_human gate when triggers fire.",
        epilog="Exits 0 when no escalation is needed, 2 when escalation is required or applied, 3 when apply/transition validation fails, and 4 for malformed input.",
    )
    evaluate.add_argument("task_dir", type=Path, help="Task directory or status.json path to evaluate.")
    evaluate.add_argument("--ops-dir", type=Path, help="research_ops directory; inferred from task_dir when omitted.")
    evaluate.add_argument("--apply", action="store_true", help="Write status=needs_human and a structured human_gate when escalation is required.")
    evaluate.add_argument("--now", help="Override current time for deterministic source freshness checks.")
    evaluate.add_argument("--source-freshness-days", type=int, default=90, help="Maximum source freshness age before stale-source escalation.")
    evaluate.add_argument("--reviewer-disagreement-threshold", type=int, default=2, help="Claim-strength spread that triggers reviewer-disagreement escalation.")
    evaluate.add_argument("--confidence-threshold", type=float, default=0.85, help="Confidence threshold for high-confidence weak-evidence escalation.")
    evaluate.set_defaults(func=run_escalation_evaluate_command)


def register_source_commands(subparsers) -> None:
    source = add_command(
        subparsers,
        "source",
        help="Author, validate, or report source-governance state.",
        description="Maintain and inspect data_source_audit.md for source approval, allowed use, and freshness.",
    )
    source_sub = source.add_subparsers(dest="source_command", required=True)
    init = add_command(
        source_sub,
        "init",
        help="Create data_source_audit.md if needed.",
        description="Create the canonical source audit register table, preserving an existing file unless --force is passed.",
    )
    add_common_ops(init)
    init.add_argument("--force", action="store_true", help="Replace an existing data_source_audit.md register.")
    init.set_defaults(func=run_source_init_command)
    upsert = add_command(
        source_sub,
        "upsert",
        help="Add or update one source audit row.",
        description=(
            "Write a governed source audit row with tier, approval status, use-case, freshness, citation, and reviewer metadata. "
            "New rows require --source-name, --url-or-domain, and --publisher-owner; omitted governance fields use conservative defaults."
        ),
        epilog="Exits 0 when the row is written, 2 when the register would be invalid, 3 for invalid source ids or dates, and 4 for malformed registers.",
    )
    add_required_ops(upsert)
    upsert.add_argument("--source-id", required=True, help="Stable source id such as DS-0001.")
    upsert.add_argument("--status", choices=sorted(SOURCE_STATUS_CHOICES), help="Deprecated status alias; prefer --approval-status.")
    upsert.add_argument("--approval-status", choices=sorted(SOURCE_APPROVAL_STATUS_CHOICES), help="Governance approval status for this source.")
    upsert.add_argument("--source-name", "--name", dest="source_name", help="Human-readable source name.")
    upsert.add_argument("--url-or-domain", "--location", dest="url_or_domain", help="URL, path, table, API, bucket, or domain.")
    upsert.add_argument("--publisher-owner", "--owner", dest="publisher_owner", help="Publisher, owner, or responsible team.")
    upsert.add_argument("--source-tier", choices=sorted(SOURCE_TIER_CHOICES), help="Governance tier for this source.")
    upsert.add_argument("--approved-use-cases", help="Semicolon- or comma-separated use cases this source may support.")
    upsert.add_argument("--blocked-use-cases", help="Semicolon- or comma-separated use cases this source must not support.")
    upsert.add_argument("--freshness-window-days", help="Positive number of days before the source review is stale.")
    upsert.add_argument("--known-limitations", help="Known caveats or limits.")
    upsert.add_argument("--citation-requirements", help="Required citation details for downstream use.")
    upsert.add_argument("--last-reviewed", "--last-checked", dest="last_reviewed", help="Review date in YYYY-MM-DD format.")
    upsert.add_argument("--approved-by", help="Human, task, or review that approved the row.")
    upsert.add_argument("--review-notes", "--readiness-notes", dest="review_notes", help="Latest governance or readiness notes.")
    upsert.set_defaults(func=run_source_upsert_command)
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
    explain = add_command(
        source_sub,
        "explain",
        help="Explain whether one source is allowed for a use case.",
        description="Explain source approval, tier, freshness, and use-case decisions for one DS-* id.",
    )
    add_required_ops(explain)
    explain.add_argument("source_id", help="Source id to explain, such as DS-0001.")
    explain.add_argument("--use-case", choices=SOURCE_USE_CASE_CHOICES, default="experiment_planning", help="Source use case to explain.")
    explain.add_argument("--claim-impact", choices=CLAIM_IMPACT_CHOICES, default="medium", help="Claim impact level to assess.")
    explain.add_argument("--allow-tier4-explicit", action="store_true", help="Allow explicitly approved tier-4 sources when policy permits.")
    explain.set_defaults(func=run_source_explain_command)


def register_data_commands(subparsers) -> None:
    data = add_command(
        subparsers,
        "data",
        help="Validate data foundation readiness files.",
        description="Validate data foundation readiness by inspecting research_ops/data profiles, access notes, join caveats, and known gaps without mutating files.",
    )
    data_sub = data.add_subparsers(dest="data_command", required=True)
    validate = add_command(
        data_sub,
        "validate",
        help="Validate research_ops/data contracts.",
        description="Read-only validation for research_ops/data profiles, source-profile linkage, access notes, join caveats, and known gap references.",
        epilog="Exits 0 when ready, 2 for warning-only readiness findings, and 4 for malformed tables or identity errors.",
    )
    add_common_ops(validate)
    validate.add_argument("--now", help="Override current time for deterministic profile freshness checks.")
    validate.set_defaults(func=run_data_validate_command)
    dashboard = add_command(
        data_sub,
        "dashboard",
        help="Render a read-only data readiness dashboard.",
        description="Read-only dashboard for approved, candidate, blocked, stale, gap-blocked, and join-caveat data states.",
        epilog="Exits 0 when dashboard data is clean, 2 when warning-only data findings are present, and 4 when malformed data prevents reliable dashboard state.",
    )
    add_common_ops(dashboard)
    dashboard.add_argument("--now", help="Override current time for deterministic source freshness checks.")
    dashboard.add_argument("--use-case", choices=SOURCE_USE_CASE_CHOICES, default="experiment_planning", help="Source use case for usable-today policy.")
    dashboard.set_defaults(func=run_data_dashboard_command)
    inspect_proposals = add_command(
        data_sub,
        "inspect-proposals",
        help="Inspect data foundation update proposals.",
        description=(
            "Read-only inspection for foundation_update_proposal_v1 data proposals. "
            "The proposal source may be a task directory, worker_output.md, JSON proposal artifact, or proposal artifact directory."
        ),
        epilog="Exits 0 when proposals are inspectable, including warning-only existing-row upserts; exits 4 for malformed proposals, unsafe target paths, non-data proposals, or workspace blockers.",
    )
    add_required_ops(inspect_proposals)
    inspect_proposals.add_argument("proposal_source", type=Path, help="Task directory, worker_output.md, JSON proposal artifact, or proposal artifact directory.")
    inspect_proposals.set_defaults(func=run_data_inspect_proposals_command)
    apply_proposals = add_command(
        data_sub,
        "apply-proposals",
        help="Dry-run or apply accepted data foundation update proposals.",
        description=(
            "Guarded apply workflow for accepted foundation_update_proposal_v1 data proposals. "
            "Dry-run is the default and emits the preflight hash required for explicit --write mode."
        ),
        epilog="Exits 0 for clean dry-runs or successful writes, 2 for lock contention or rollback after failed validation, 3 for invalid write requests, and 4 for blocked proposal or acceptance preconditions.",
    )
    add_required_ops(apply_proposals)
    apply_proposals.add_argument("proposal_source", type=Path, help="Task directory, worker_output.md, JSON proposal artifact, or proposal artifact directory.")
    apply_mode = apply_proposals.add_mutually_exclusive_group()
    apply_mode.add_argument("--dry-run", action="store_true", help="Preview proposed edits and preflight hash without writing. This is the default.")
    apply_mode.add_argument("--write", action="store_true", help="Apply proposals only after all write preconditions pass.")
    apply_proposals.add_argument("--preflight-hash", help="Hash from a clean dry-run output; required with --write.")
    apply_proposals.add_argument("--accepted-artifact", "--acceptance-artifact", dest="accepted_artifact", type=Path, help="Accepted review_panel/result_acceptance.json proof inside research_ops when source task status is not accepted.")
    apply_proposals.set_defaults(func=run_data_apply_proposals_command)


def register_library_commands(subparsers) -> None:
    library = add_command(
        subparsers,
        "library",
        help="Initialize and validate knowledge library files.",
        description="Manage research_ops/library files for source memory, claim maps, methods, and open questions.",
    )
    library_sub = library.add_subparsers(dest="library_command", required=True)
    init = add_command(
        library_sub,
        "init",
        help="Add missing knowledge library starter files.",
        description="Preview or add missing research_ops/library starter files without overwriting existing files.",
        epilog="Without --write this command is a dry run. Exits 0 when missing files are reported or created, 3 for conflicting flags, and 4 for malformed workspace paths or write failures.",
    )
    add_common_ops(init)
    init.add_argument("--dry-run", action="store_true", help="Explicitly report missing library files without writing.")
    init.add_argument("--write", action="store_true", help="Create only missing library files.")
    init.set_defaults(func=run_library_init_command)
    validate = add_command(
        library_sub,
        "validate",
        help="Validate knowledge library Markdown contracts.",
        description="Read-only validation for research_ops/library generated blocks, source IDs, source refs, metadata, and update provenance.",
        epilog="Exits 0 when library contracts are clean, 2 for warning-only findings with usable state, 3 for invalid request flags, and 4 for malformed generated blocks, duplicate IDs, or invalid references.",
    )
    add_common_ops(validate)
    validate.add_argument("--now", help="Override current time for deterministic stale review checks.")
    validate.add_argument("--stale-days", type=int, help="Warn when reviewed_date is older than this many days.")
    validate.set_defaults(func=run_library_validate_command)
    dashboard = add_command(
        library_sub,
        "dashboard",
        help="Render a read-only knowledge library dashboard.",
        description="Read-only dashboard for topic coverage, source status/trust counts, reviewed sources, stale reviews, risky claims, open questions, proposed library update tasks, and idea library-support gaps.",
        epilog="Exits 0 when dashboard data is clean, 2 when validator warnings or dashboard read-model warnings are present, 3 for invalid request flags, and 4 when malformed library state prevents reliable dashboard state.",
    )
    add_common_ops(dashboard)
    dashboard.add_argument("--now", help="Override current time for deterministic stale review checks.")
    dashboard.add_argument("--stale-days", type=int, default=180, help="Report sources and claims older than this many days.")
    dashboard.set_defaults(func=run_library_dashboard_command)
    inspect_proposals = add_command(
        library_sub,
        "inspect-proposals",
        help="Inspect knowledge library update proposals.",
        description=(
            "Read-only inspection for foundation_update_proposal_v1 library proposals. "
            "The proposal source may be a task directory, worker_output.md, JSON proposal artifact, or proposal artifact directory."
        ),
        epilog="Exits 0 when proposals are inspectable, including warning-only existing-row upserts; exits 4 for malformed proposals, unsafe target paths, non-library proposals, unresolved source refs, or workspace blockers.",
    )
    add_required_ops(inspect_proposals)
    inspect_proposals.add_argument("proposal_source", type=Path, help="Task directory, worker_output.md, JSON proposal artifact, or proposal artifact directory.")
    inspect_proposals.set_defaults(func=run_library_inspect_proposals_command)
    apply_proposals = add_command(
        library_sub,
        "apply-proposals",
        help="Dry-run or apply accepted knowledge library update proposals.",
        description=(
            "Guarded apply workflow for accepted foundation_update_proposal_v1 library proposals. "
            "Dry-run is the default and emits the preflight hash required for explicit --write mode."
        ),
        epilog="Exits 0 for clean dry-runs or successful writes, 2 for lock contention or rollback after failed validation, 3 for invalid write requests, and 4 for blocked proposal or acceptance preconditions.",
    )
    add_required_ops(apply_proposals)
    apply_proposals.add_argument("proposal_source", type=Path, help="Task directory, worker_output.md, JSON proposal artifact, or proposal artifact directory.")
    apply_mode = apply_proposals.add_mutually_exclusive_group()
    apply_mode.add_argument("--dry-run", action="store_true", help="Preview proposed edits and preflight hash without writing. This is the default.")
    apply_mode.add_argument("--write", action="store_true", help="Apply proposals only after all write preconditions pass.")
    apply_proposals.add_argument("--preflight-hash", help="Hash from a clean dry-run output; required with --write.")
    apply_proposals.add_argument("--accepted-artifact", "--acceptance-artifact", dest="accepted_artifact", type=Path, help="Accepted review_panel/result_acceptance.json proof inside research_ops when source task status is not accepted.")
    apply_proposals.set_defaults(func=run_library_apply_proposals_command)


def register_runtime_commands(subparsers) -> None:
    runtime = add_command(
        subparsers,
        "runtime",
        help="Validate and summarize runtime evidence and trace ledgers.",
        description=(
            "Inspect read-only runtime artifacts under research_ops/runtime: evidence_objects.jsonl, "
            "traces.jsonl, snapshots, hashes, task links, and permission metadata."
        ),
    )
    runtime_sub = runtime.add_subparsers(dest="runtime_command", required=True)

    validate_cmd = add_command(
        runtime_sub,
        "validate",
        help="Validate runtime evidence objects and trace ledgers.",
        description=(
            "Read evidence_objects.jsonl and traces.jsonl, validate schema shape, task links, "
            "research_ops-bounded paths, snapshot hashes, freshness, costs, and permission metadata."
        ),
        epilog="Exits 0 when schemas and hashes are clean, 2 for validation errors, and 4 when the workspace is missing.",
    )
    add_required_ops(validate_cmd)
    validate_cmd.set_defaults(func=run_runtime_validate_command)

    summary_cmd = add_command(
        runtime_sub,
        "summary",
        help="Summarize runtime evidence and trace ledgers.",
        description=(
            "Return runtime trace count, evidence object count, unsupported or stale evidence count, "
            "latest runtime errors, and validation warning/error counts without mutating research_ops."
        ),
        epilog="Exits 0 when runtime ledgers are valid and 2 when malformed runtime artifacts are present.",
    )
    add_required_ops(summary_cmd)
    summary_cmd.set_defaults(func=run_runtime_summary_command)

    inspect_cmd = add_command(
        runtime_sub,
        "inspect-evidence",
        help="Inspect one runtime evidence object.",
        description=(
            "Show one EVID-* object from research_ops/runtime/evidence_objects.jsonl with related traces "
            "and validation findings without treating it as accepted evidence."
        ),
        epilog="Exits 0 when the evidence object is present and valid, 2 for validation errors, and 3 when the id is missing.",
    )
    add_required_ops(inspect_cmd)
    inspect_cmd.add_argument("evidence_id", help="Evidence id such as EVID-000001.")
    inspect_cmd.set_defaults(func=run_runtime_inspect_evidence_command)

    dry_run_cmd = add_command(
        runtime_sub,
        "dry-run",
        help="Preview bounded runtime adapter calls.",
        description=(
            "Read a runtime request JSON file, load the task contract, and report planned local or mocked "
            "adapter calls, including bounded parallel_research requests, without writing traces, evidence "
            "objects, snapshots, merge packets, or task state."
        ),
        epilog="Exits 0 when every requested adapter is permitted, 2 when task-contract policy blocks a call, and 3 or 4 for malformed inputs.",
    )
    add_required_ops(dry_run_cmd)
    dry_run_cmd.add_argument("--request", required=True, type=Path, help="Runtime request JSON file.")
    dry_run_cmd.add_argument("--now", help="Override report timestamp for deterministic output.")
    dry_run_cmd.set_defaults(func=run_runtime_adapter_dry_run_command)

    execute_cmd = add_command(
        runtime_sub,
        "execute",
        help="Execute permitted local or mocked runtime adapter calls.",
        description=(
            "Run standard-library local adapters or explicit mock external adapters, then write runtime "
            "traces, source route decisions, evidence objects, and snapshots under research_ops/runtime "
            "and bounded parallel merge packets when requested, without changing task state."
        ),
        epilog="Exits 0 when all calls execute, 2 when policy blocks a call, and never performs live network or paid calls in the core runtime.",
    )
    add_required_ops(execute_cmd)
    execute_cmd.add_argument("--request", required=True, type=Path, help="Runtime request JSON file.")
    execute_cmd.add_argument("--now", help="Override evidence and trace timestamp for deterministic output.")
    execute_cmd.set_defaults(func=run_runtime_adapter_execute_command)


def register_eval_commands(subparsers) -> None:
    eval_cmd = add_command(
        subparsers,
        "eval",
        help="Build, run, and compare trace-driven runtime eval suites.",
        description=(
            "Build trace-driven runtime eval suites from runtime traces, evidence objects, claim "
            "verification, result acceptance, costs, and review artifacts, then produce offline "
            "release comparison reports."
        ),
    )
    eval_sub = eval_cmd.add_subparsers(dest="eval_command", required=True)

    build = add_command(
        eval_sub,
        "build-from-traces",
        help="Build an eval suite from fixture runtime traces.",
        description=(
            "Read research_ops/runtime traces and evidence objects, collect task acceptance and claim "
            "verification artifacts, and produce a deterministic eval dataset. Without --write this is read-only."
        ),
        epilog="Exits 0 when at least one trace-backed eval case is built, 2 for invalid runtime artifacts, and 3 or 4 for unsafe inputs.",
    )
    add_required_ops(build)
    build.add_argument("--suite-id", default="runtime-trace-suite", help="Stable eval suite id.")
    build.add_argument("--output", type=Path, help="Output JSON path under research_ops/evals.")
    build.add_argument("--write", action="store_true", help="Write the suite JSON under research_ops/evals.")
    build.add_argument("--now", help="Override built_at timestamp for deterministic output.")
    build.add_argument("--runtime-policy", default="runtime_policy_v1.0", help="Runtime policy label recorded in the suite.")
    build.add_argument("--model-routing-policy", default="model_routing_unset", help="Model-routing policy label recorded in the suite.")
    build.set_defaults(func=run_eval_build_from_traces_command)

    run = add_command(
        eval_sub,
        "run",
        help="Run deterministic graders for one eval suite.",
        description=(
            "Run deterministic graders for the eval suite: schema/path/hash, groundedness, "
            "citation-support, task-success, and cost/latency checks without network, credentials, "
            "paid calls, or prompt optimization."
        ),
        epilog="Exits 0 when automated graders pass and 2 when an eval case regresses or cannot reproduce.",
    )
    run.add_argument("eval_suite", type=Path, help="Eval suite JSON file.")
    run.add_argument("--run-id", help="Stable run id for deterministic output.")
    run.add_argument("--output", type=Path, help="Output JSON path under research_ops/evals/runs.")
    run.add_argument("--write", action="store_true", help="Write the eval run JSON under research_ops/evals/runs.")
    run.add_argument("--now", help="Override evaluated_at timestamp for deterministic output.")
    run.set_defaults(func=run_eval_run_command)

    compare = add_command(
        eval_sub,
        "compare",
        help="Compare candidate eval metrics against a baseline run.",
        description=(
            "Compare candidate eval metrics against a baseline run and report pass/fail, metric "
            "deltas, residual risks, and release-policy blockers."
        ),
        epilog="Exits 0 when candidate metrics do not regress and 2 when release-policy checks fail.",
    )
    compare.add_argument("baseline", type=Path, help="Baseline eval run JSON.")
    compare.add_argument("candidate", type=Path, help="Candidate eval run JSON.")
    compare.add_argument("--cost-tolerance-usd", type=float, default=0.0, help="Allowed cost-per-accepted-report increase.")
    compare.set_defaults(func=run_eval_compare_command)


def register_evidence_memory_commands(subparsers) -> None:
    evidence_memory = add_command(
        subparsers,
        "evidence-memory",
        help="Build and query structured accepted-evidence memory.",
        description=(
            "Build structured accepted-evidence memory by deriving research_ops/memory/evidence_memory_index.json "
            "from accepted memory, runtime evidence, claim verification, deliverable links, and targeted "
            "reflections without replacing source files."
        ),
    )
    memory_sub = evidence_memory.add_subparsers(dest="evidence_memory_command", required=True)

    update = add_command(
        memory_sub,
        "update",
        help="Build the structured evidence memory index.",
        description=(
            "Write a structured evidence memory index under research_ops/memory with claim ids, evidence ids, "
            "source ids, contradiction edges, freshness status, task lineage, deliverable links, and reflection "
            "summaries."
        ),
        epilog="Exits 0 when the derived index is valid, 2 for schema issues, 3 for unsafe output paths, and 4 when research_ops is missing.",
    )
    add_required_ops(update)
    update.add_argument("--dry-run", action="store_true", help="Build the index payload without writing it.")
    update.add_argument("--output", type=Path, help="Override output path under research_ops.")
    update.add_argument("--now", help="Override generated_at for deterministic output.")
    update.set_defaults(func=run_evidence_memory_update_command)

    query = add_command(
        memory_sub,
        "query",
        help="Query structured evidence memory and targeted reflections.",
        description=(
            "Search accepted evidence entries and relevant targeted reflections while surfacing stale or "
            "contradicted evidence before reuse."
        ),
        epilog="Exits 0 for a readable index, 2 for malformed derived memory, and 4 when research_ops is missing.",
    )
    add_required_ops(query)
    query.add_argument("--query", help="Text to match against titles, findings, sources, claims, and reflections.")
    query.add_argument("--freshness-status", choices=["current", "due", "stale", "superseded", "contradicted", "unknown"], help="Limit evidence entries by freshness.")
    query.add_argument("--source-id", help="Limit evidence entries to one DS-* source id.")
    query.add_argument("--contradictions-only", action="store_true", help="Return only memory entries with contradiction edges.")
    query.add_argument("--failure-class", choices=FAILURE_CLASSES, help="Limit targeted reflections to one failure class.")
    query.add_argument("--reflection-threshold", type=float, default=0.2, help="Minimum reflection relevance score.")
    query.add_argument("--limit", type=int, default=10, help="Maximum memory and reflection matches to return.")
    query.add_argument("--now", help="Override current time for deterministic reflection expiry.")
    query.set_defaults(func=run_evidence_memory_query_command)


def register_model_routing_commands(subparsers) -> None:
    routing = add_command(
        subparsers,
        "model-routing",
        help="Validate provider-neutral model routing policy.",
        description=(
            "Manage research_ops/prompts/model_routing_policy.json, select role routes, and gate "
            "candidate prompt or routing changes on deterministic eval comparisons."
        ),
    )
    routing_sub = routing.add_subparsers(dest="model_routing_command", required=True)

    init = add_command(
        routing_sub,
        "init",
        help="Create a default routing policy.",
        description=(
            "Render a provider-neutral model routing policy under research_ops/prompts. Without "
            "--write this previews the policy and does not mutate files."
        ),
        epilog="Exits 0 when the policy is valid, 3 for unsafe paths, and 4 if the bundled default policy is malformed.",
    )
    add_common_ops(init)
    init.add_argument("--output", type=Path, help="Output path under research_ops/prompts.")
    init.add_argument("--policy-id", default="repo_first_model_routing_v1", help="Stable policy id recorded in eval runs.")
    init.add_argument("--write", action="store_true", help="Write research_ops/prompts/model_routing_policy.json.")
    init.add_argument("--force", action="store_true", help="Replace an existing policy when writing.")
    init.add_argument("--now", help="Override timestamps for deterministic output.")
    init.set_defaults(func=run_model_routing_init_command)

    validate_cmd = add_command(
        routing_sub,
        "validate",
        help="Validate one routing policy JSON file.",
        description="Validate schema shape, required roles, provider-neutral posture, hard-rule ownership, and adoption gates.",
        epilog="Exits 0 when valid and 2 when schema or semantic validation fails.",
    )
    validate_cmd.add_argument("policy", type=Path, help="Path to model_routing_policy.json.")
    validate_cmd.add_argument("--include-policy", action="store_true", help="Echo the validated policy in the JSON output.")
    validate_cmd.set_defaults(func=run_model_routing_validate_command)

    select = add_command(
        routing_sub,
        "select",
        help="Select the route for one research role.",
        description="Return the configured tier, budget, fallback, and escalation triggers for one role without mutating files.",
    )
    select.add_argument("policy", type=Path, help="Path to model_routing_policy.json.")
    select.add_argument(
        "--role",
        required=True,
        choices=("planner", "worker", "extractor", "methodology_reviewer", "skeptic_reviewer", "synthesizer"),
    )
    select.add_argument("--task-type", default="literature_extract", help="Task type used to report recommended escalations.")
    select.add_argument("--claim-strength", help="Claim strength used to report recommended escalations.")
    select.add_argument("--public-claims", action="store_true", help="Report public-claim escalation guidance.")
    select.set_defaults(func=run_model_routing_select_command)

    eval_check = add_command(
        routing_sub,
        "eval-check",
        help="Gate routing adoption on eval comparison.",
        description=(
            "Validate the policy, compare candidate eval metrics against a baseline run, and require "
            "the candidate run to record the policy_id before adoption is eligible."
        ),
        epilog="Exits 0 when candidate metrics match or improve baseline and 2 when adoption is blocked.",
    )
    eval_check.add_argument("policy", type=Path, help="Path to model_routing_policy.json.")
    eval_check.add_argument("--baseline", type=Path, required=True, help="Baseline eval run JSON.")
    eval_check.add_argument("--candidate", type=Path, required=True, help="Candidate eval run JSON.")
    eval_check.add_argument("--cost-tolerance-usd", type=float, default=0.0, help="Allowed cost-per-accepted-report increase.")
    eval_check.set_defaults(func=run_model_routing_eval_check_command)


def register_scaling_commands(subparsers) -> None:
    scaling = add_command(
        subparsers,
        "scaling",
        help="Assess file-backed scaling friction and backend need.",
        description=(
            "Measure file-backed scaling friction from task count, runtime ledger size, eval artifacts, lock contention, and dashboard "
            "snapshot latency without mutating research_ops, then recommend no backend, an optional "
            "rebuildable index cache, or a human decision for heavier orchestration."
        ),
    )
    scaling_sub = scaling.add_subparsers(dest="scaling_command", required=True)
    assess = add_command(
        scaling_sub,
        "assess",
        help="Measure scaling friction for one research_ops workspace.",
        description=(
            "Read research_ops files and task-local locks, time the read-only console snapshot, and "
            "explain which source files produced each derived metric. The command never moves truth "
            "out of research_ops."
        ),
        epilog="Exits 0 when the assessment is produced and 4 when the workspace path is invalid.",
    )
    add_required_ops(assess)
    assess.add_argument("--now", help="Override assessment timestamp.")
    assess.add_argument("--max-task-statuses", type=int, default=250, help="Task-status count threshold before index-cache findings are reported.")
    assess.add_argument("--max-runtime-ledger-bytes", type=int, default=10_000_000, help="Runtime trace/evidence byte threshold.")
    assess.add_argument("--max-eval-cases", type=int, default=500, help="Eval case threshold before sharding/index findings are reported.")
    assess.add_argument("--max-dashboard-ms", type=float, default=2000.0, help="Dashboard snapshot latency threshold in milliseconds.")
    assess.add_argument("--max-stale-locks", type=int, default=0, help="Allowed stale task lock count before concurrency findings are reported.")
    assess.add_argument("--stale-lock-minutes", type=float, default=60.0, help="Lock age threshold used for stale-lock detection.")
    assess.add_argument("--skip-dashboard-latency", action="store_true", help="Skip timing the console snapshot.")
    assess.set_defaults(func=run_scaling_assess_command)


def register_brief_commands(subparsers) -> None:
    brief = add_command(
        subparsers,
        "brief",
        help="Draft, validate, and dry-run apply research briefs.",
        description=(
            "Manage pre-planning research_brief.json contracts with output target, audience, source policy, "
            "permissions, budget caps, clarifying questions, and human gates."
        ),
    )
    brief_sub = brief.add_subparsers(dest="brief_command", required=True)

    draft = add_command(
        brief_sub,
        "draft",
        help="Draft a bounded research_brief.json contract.",
        description="Draft a research brief from a question or research_ops/briefs/source_request.md; unresolved questions remain blocking.",
    )
    add_common_ops(draft)
    draft.add_argument("--question", help="Raw user question or research request.")
    draft.add_argument("--objective", help="Clarified executable objective.")
    draft.add_argument("--output-maturity", choices=OUTPUT_MATURITIES, help="Intended output maturity.")
    draft.add_argument("--audience", help="Target audience or decision owner.")
    draft.add_argument("--venue", help="Known target venue or channel.")
    draft.add_argument("--allowed-source-class", action="append", choices=SOURCE_CLASSES, help="Allowed source class. Repeat as needed.")
    draft.add_argument("--forbidden-source-class", action="append", choices=SOURCE_CLASSES, help="Forbidden source class. Repeat as needed.")
    draft.add_argument("--private-data-policy", choices=PRIVATE_DATA_POLICIES, default="none")
    draft.add_argument("--public-claims-policy", choices=PUBLIC_CLAIM_POLICIES, default="none")
    draft.add_argument("--allow-browsing", action="store_true")
    draft.add_argument("--allow-api", action="store_true")
    draft.add_argument("--allow-code-execution", action="store_true")
    draft.add_argument("--allow-network", action="store_true")
    draft.add_argument("--requires-credentials", action="store_true")
    draft.add_argument("--allow-paid", action="store_true")
    draft.add_argument("--max-api-usd", type=float, default=0.0)
    draft.add_argument("--max-compute-usd", type=float, default=0.0)
    draft.add_argument("--max-human-minutes", type=int, default=30)
    draft.add_argument("--max-runtime-minutes", type=int, default=45)
    draft.add_argument("--assumption", action="append", default=[], help="Known assumption. Repeat as needed.")
    draft.add_argument("--unresolved-question", action="append", default=[], help="Clarifying question that must be answered before planning.")
    draft.add_argument("--brief-id", help="Explicit BRIEF-* id.")
    draft.add_argument("--output", type=Path, help="Output path inside research_ops; defaults to research_ops/briefs/research_brief.json.")
    draft.add_argument("--now", help="Timestamp override.")
    draft.add_argument("--dry-run", action="store_true", help="Preview without writing; this is the default.")
    draft.add_argument("--write", action="store_true", help="Write the drafted brief JSON.")
    draft.add_argument("--force", action="store_true", help="Replace an existing output brief when writing.")
    draft.set_defaults(func=run_brief_draft_command)

    validate_cmd = add_command(
        brief_sub,
        "validate",
        help="Validate a research brief before planning.",
        description="Validate schema, output target, audience, source policy, permissions, unresolved questions, and human gates.",
        epilog="Exits 0 when the brief is ready for planning and 2 when clarification or human gates block planning.",
    )
    validate_cmd.add_argument("brief_path", type=Path, help="Path to research_brief.json.")
    validate_cmd.set_defaults(func=run_brief_validate_command)

    apply_cmd = add_command(
        brief_sub,
        "apply",
        help="Dry-run a validated brief into a task planning command.",
        description="Preview task creation from a validated brief that is ready for planning; Phase 2 apply does not mutate research_ops.",
        epilog="Exits 0 when a task plan is ready, 2 when the brief is blocked, and 3 when --dry-run is omitted.",
    )
    apply_cmd.add_argument("ops_dir", type=Path, help="research_ops workspace directory.")
    apply_cmd.add_argument("brief_path", type=Path, help="Path to a brief inside research_ops.")
    apply_cmd.add_argument("--task-type", choices=("literature_extract", "data_readiness", "hypothesis_card", "experiment_plan", "admin"), default="literature_extract")
    apply_cmd.add_argument("--dry-run", action="store_true", help="Required; preview without writing.")
    apply_cmd.set_defaults(func=run_brief_apply_command)


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


def add_batch_dry_run(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dry-run", action="store_true", help="Validate and print the action without writing files.")


def register_batch_commands(subparsers) -> None:
    batch = add_command(
        subparsers,
        "batch",
        help="Manage batch_manifest.json lifecycle.",
        description="Manage the batch_manifest.json lifecycle: create, validate, submit, ingest, review, and trust-check first-class batch manifests.",
    )
    batch_sub = batch.add_subparsers(dest="batch_command", required=True)
    init = add_command(
        batch_sub,
        "init",
        help="Create a draft batch manifest.",
        description="Create a draft batch manifest at research_ops/batches/<batch-id>/batch_manifest.json with untrusted output state.",
    )
    add_required_ops(init)
    init.add_argument("--batch-id", required=True, help="Batch id such as BATCH-0001.")
    init.add_argument("--input-file", action="append", required=True, help="Input file for the batch. Repeat for multiple inputs.")
    init.add_argument("--prompt-template", required=True, help="Prompt template or prompt identifier used for the batch.")
    init.add_argument("--model", required=True, help="Model or provider tool for the batch.")
    init.add_argument("--expected-output-schema", required=True, help="Expected output schema name or path.")
    init.add_argument("--ingest-path", required=True, help="Destination path where reviewed output may later be ingested.")
    init.add_argument("--source-task-id", help="Source task that created or requested the batch.")
    init.add_argument("--estimated-api-usd", type=float, default=0.0, help="Estimated API spend in USD.")
    init.add_argument("--estimated-compute-usd", type=float, default=0.0, help="Estimated compute spend in USD.")
    init.add_argument("--manifest", type=Path, help="Override the default manifest path.")
    add_batch_dry_run(init)
    init.set_defaults(func=run_batch_init_command)
    validate = add_command(
        batch_sub,
        "validate-manifest",
        help="Validate batch manifest schema and lifecycle invariants.",
        description="Validate one batch_manifest.json and lifecycle invariants without mutating it.",
    )
    validate.add_argument("manifest", type=Path, help="batch_manifest.json path to validate.")
    validate.set_defaults(func=run_batch_validate_manifest_command)
    submit = add_command(
        batch_sub,
        "submit",
        help="Mark a batch submitted and log estimated cost.",
        description="Move a draft/validated batch to submitted, keep output untrusted, and log estimated cost unless --dry-run is used.",
    )
    submit.add_argument("manifest", type=Path, help="batch_manifest.json path to submit.")
    submit.add_argument("--ops-dir", type=Path, help="research_ops directory; inferred from the manifest path when omitted.")
    submit.add_argument("--provider-batch-id", required=True, help="Provider batch id assigned by the external system.")
    submit.add_argument("--api-usd", type=float, required=True, help="Estimated API cost in USD.")
    submit.add_argument("--compute-usd", type=float, required=True, help="Estimated compute cost in USD.")
    add_batch_dry_run(submit)
    submit.set_defaults(func=run_batch_submit_command)
    complete = add_command(
        batch_sub,
        "complete",
        help="Record provider output files while keeping them untrusted.",
        description="Move a submitted batch to completed with output_trust=untrusted.",
    )
    complete.add_argument("manifest", type=Path, help="batch_manifest.json path to complete.")
    complete.add_argument("--output-file", action="append", required=True, help="Provider output file. Repeat for multiple files.")
    add_batch_dry_run(complete)
    complete.set_defaults(func=run_batch_complete_command)
    ingest = add_command(
        batch_sub,
        "ingest",
        help="Record ingested output files pending review.",
        description="Move a completed batch to ingested with output_trust=ingested_pending_review.",
    )
    ingest.add_argument("manifest", type=Path, help="batch_manifest.json path to ingest.")
    ingest.add_argument("--ingest-task-id", required=True, help="Task id responsible for ingesting outputs.")
    ingest.add_argument("--ingested-file", action="append", required=True, help="Ingested output artifact. Repeat for multiple files.")
    add_batch_dry_run(ingest)
    ingest.set_defaults(func=run_batch_ingest_command)
    reviewed = add_command(
        batch_sub,
        "mark-reviewed",
        help="Mark ingested batch outputs as reviewed and trusted.",
        description="Move an ingested batch to reviewed and trusted with output_trust=reviewed after human/reviewer acceptance.",
    )
    reviewed.add_argument("manifest", type=Path, help="batch_manifest.json path to mark reviewed.")
    reviewed.add_argument("--review-task-id", required=True, help="Task id that reviewed the ingested outputs.")
    add_batch_dry_run(reviewed)
    reviewed.set_defaults(func=run_batch_mark_reviewed_command)
    trust = add_command(
        batch_sub,
        "trust-status",
        help="Report whether batch outputs are trusted.",
        description="Return nonzero until lifecycle_status=reviewed and output_trust=reviewed, unless --allow-untrusted is set.",
        epilog="Exits 0 when outputs are trusted, 2 when outputs are still untrusted, and 4 for malformed manifests.",
    )
    trust.add_argument("manifest", type=Path, help="batch_manifest.json path to check.")
    trust.add_argument("--allow-untrusted", action="store_true", help="Report untrusted state without failing the command.")
    trust.set_defaults(func=run_batch_trust_status_command)


def register_metrics_commands(subparsers) -> None:
    metrics = add_command(
        subparsers,
        "metrics",
        help="Append or inspect autonomy metrics.",
        description="Maintain metrics_baseline.json and metrics_history.jsonl snapshots, and render operational read models.",
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
    metrics_operational = add_command(
        metrics_sub,
        "operational",
        help="Render operational metrics read model.",
        description="Render read-only time-in-state, review latency, human-decision latency, and cost/review trends.",
    )
    add_common_ops(metrics_operational)
    metrics_operational.add_argument("--now", help="Override report time for deterministic checks.")
    metrics_operational.set_defaults(func=run_metrics_operational_command)


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


def register_outcomes_commands(subparsers) -> None:
    outcomes = add_command(
        subparsers,
        "outcomes",
        help="Build delivered-project outcome indexes.",
        description="Refresh and inspect rebuildable delivered-project indexes from accepted outputs and task provenance.",
    )
    outcomes_sub = outcomes.add_subparsers(dest="outcomes_command", required=True)
    refresh = add_command(
        outcomes_sub,
        "refresh",
        help="Refresh generated delivered-project outcome files.",
        description="Write research_ops/outcomes/delivered_projects.jsonl and delivered_projects_summary.json from source artifacts.",
    )
    add_required_ops(refresh)
    refresh.add_argument("--now", help="Override current time for deterministic freshness checks.")
    refresh.set_defaults(func=run_outcomes_command)
    list_cmd = add_command(
        outcomes_sub,
        "list",
        help="List delivered projects.",
        description="List delivered projects from accepted_outputs_index.md plus related task, review, idea, cost, and provenance files.",
    )
    add_required_ops(list_cmd)
    list_cmd.add_argument("--status", choices=["all", "accepted", "synthesized", "rejected", "paused"], default="accepted", help="Delivered status filter.")
    list_cmd.add_argument("--now", help="Override current time for deterministic freshness checks.")
    list_cmd.set_defaults(func=run_outcomes_command)
    summary = add_command(
        outcomes_sub,
        "summary",
        help="Summarize delivered-project outcomes.",
        description="Print acceptance rate, average iterations, cost, claim-strength counts, and revalidation counts.",
    )
    add_required_ops(summary)
    summary.add_argument("--now", help="Override current time for deterministic freshness checks.")
    summary.set_defaults(func=run_outcomes_command)


def add_deliverable_update_arguments(parser: argparse.ArgumentParser, *, init: bool) -> None:
    if init:
        parser.add_argument("--deliverable-id", help="Explicit deliverable id such as DELIV-0001.")
        parser.add_argument("--title", required=True, help="Human-readable deliverable title.")
        parser.add_argument("--output-type", choices=OUTPUT_TYPE_CHOICES, required=True, help="Declared deliverable output type.")
        parser.add_argument("--target-maturity", choices=MATURITY_CHOICES, default="internal_draft", help="Intended deliverable maturity level.")
        parser.add_argument("--current-maturity", choices=MATURITY_CHOICES, default="research_note", help="Current declared maturity level.")
    else:
        parser.add_argument("--title", help="Human-readable deliverable title.")
        parser.add_argument("--output-type", choices=OUTPUT_TYPE_CHOICES, help="Declared deliverable output type.")
        parser.add_argument("--target-maturity", choices=MATURITY_CHOICES, help="Intended deliverable maturity level.")
        parser.add_argument("--current-maturity", choices=MATURITY_CHOICES, help="Current declared maturity level.")
    parser.add_argument("--target-audience", help="Known reader or audience for shareable and external deliverables.")
    parser.add_argument("--target-venue", help="Venue, publication, client, or submission target.")
    parser.add_argument("--venue-style-profile", help="Optional venue or style profile used for submission-readiness checks.")
    parser.add_argument("--source-task", action="append", default=[], help="Accepted source task id to link, such as TASK-0001. Repeatable.")
    parser.add_argument("--primary-artifact", help="Primary artifact path relative to research_ops.")
    parser.add_argument("--owner", help="Human or agent owner for maturity follow-through.")
    parser.add_argument("--required-gate", action="append", default=[], help="Additional gate id to require. Repeatable.")
    parser.add_argument("--complete-gate", action="append", default=[], help="Completed gate id to mark; use `all` to mark all required gates.")
    parser.add_argument("--manuscript-gate", action="append", default=[], metavar="GATE=STATUS", help="Set a manuscript-quality gate status. Repeatable.")
    parser.add_argument("--gate-rationale", action="append", default=[], metavar="GATE=TEXT", help="Attach rationale or caveat text to a manuscript gate.")
    parser.add_argument("--waiver-rationale", action="append", default=[], metavar="GATE=TEXT", help="Required human rationale for a waived manuscript gate.")
    parser.add_argument("--gate-evidence", action="append", default=[], metavar="GATE=TEXT", help="Attach evidence, artifact, or section reference to a manuscript gate.")
    parser.add_argument("--review-independence", choices=INDEPENDENCE_CHOICES, help="Achieved deliverable-review independence.")
    parser.add_argument("--reviewer", help="Reviewer identity or role for the latest maturity review.")
    parser.add_argument("--review-notes", help="Short review-independence note.")
    parser.add_argument("--open-gap", action="append", default=[], help="Open deliverable gap that must remain visible. Repeatable.")
    parser.add_argument("--last-reviewed-at", help="ISO-8601 timestamp for the latest deliverable-level review.")
    parser.add_argument("--now", help="Override current timestamp for deterministic tests.")
    if not init:
        parser.add_argument("--clear-open-gaps", action="store_true", help="Clear open gaps after they are resolved or waived elsewhere.")


def register_deliverable_commands(subparsers) -> None:
    deliverable = add_command(
        subparsers,
        "deliverable",
        help="Manage deliverable maturity separate from task acceptance.",
        description=(
            "Create target manifests and run read-only readiness checks for papers, memos, and reports. "
            "Accepted task outputs are source evidence, not deliverable readiness."
        ),
    )
    deliverable_sub = deliverable.add_subparsers(dest="deliverable_command", required=True)
    init = add_command(
        deliverable_sub,
        "init",
        help="Create a deliverable maturity manifest entry.",
        description="Create or append research_ops/deliverables/deliverable_manifest.json and its human-readable projection.",
    )
    add_required_ops(init)
    add_deliverable_update_arguments(init, init=True)
    init.set_defaults(func=run_deliverable_init_command)

    target = add_command(
        deliverable_sub,
        "target",
        help="Update target metadata and maturity gates.",
        description="Update target audience, venue, maturity, source task links, completed gates, review independence, and open gaps.",
    )
    add_required_ops(target)
    target.add_argument("deliverable_id", help="Deliverable id such as DELIV-0001.")
    add_deliverable_update_arguments(target, init=False)
    target.set_defaults(func=run_deliverable_target_command)

    critic = add_command(
        deliverable_sub,
        "critic",
        help="Record a deliverable-level adversarial critic review.",
        description=(
            "Record an adversarial critic review with critic-specific metadata, independence, severity distribution, "
            "recommended maturity ceiling, and required revision rows for one deliverable."
        ),
    )
    add_required_ops(critic)
    critic.add_argument("deliverable_id", help="Deliverable id such as DELIV-0001.")
    critic.add_argument("--review-id", help="Explicit critic review id such as CRITIC-0001.")
    critic.add_argument("--reviewer-role", choices=CRITIC_REVIEWER_ROLE_CHOICES, default="adversarial_critic", help="Critic role used for this deliverable-level review.")
    critic.add_argument("--independence-type", choices=INDEPENDENCE_CHOICES, required=True, help="Independence level achieved by this critic review.")
    critic.add_argument("--reviewer", help="Reviewer identity or role label.")
    critic.add_argument("--model-or-reviewer", help="Model name, human reviewer, or external reviewer identity when available.")
    critic.add_argument("--confidence", type=float, required=True, help="Reviewer confidence from 0 to 1.")
    critic.add_argument("--recommended-maturity-ceiling", choices=MATURITY_CHOICES, required=True, help="Highest maturity this critic review recommends before further revision.")
    critic.add_argument("--critical", type=int, default=0, dest="critical_findings", help="Number of critical critic findings.")
    critic.add_argument("--major", type=int, default=0, dest="major_findings", help="Number of major critic findings.")
    critic.add_argument("--minor", type=int, default=0, dest="minor_findings", help="Number of minor critic findings.")
    critic.add_argument("--note", type=int, default=0, dest="note_findings", help="Number of note-level critic findings.")
    critic.add_argument("--required-revision-row", action="append", default=[], help="Required revision or future response-matrix row. Repeatable.")
    critic.add_argument(
        "--response-matrix-row",
        action="append",
        default=[],
        metavar="FIELD=VALUE;...",
        help="Seed an open response-matrix row from critic output. Required fields: critique_id, severity, target_section, issue, required_change, owner.",
    )
    critic.add_argument("--review-task-id", help="Optional critic_review task id that produced the review.")
    critic.add_argument("--artifact-path", help="Optional critic review artifact path relative to research_ops.")
    critic.add_argument("--status", choices=CRITIC_REVIEW_STATUS_CHOICES, default="completed", help="Lifecycle status for the critic review.")
    critic.add_argument("--notes", help="Short critic-stage notes.")
    critic.add_argument("--now", help="Override current timestamp for deterministic tests.")
    critic.set_defaults(func=run_deliverable_critic_command)

    response = add_command(
        deliverable_sub,
        "response",
        help="Record a deliverable review-response row.",
        description=(
            "Add or update a formal review-response matrix row with critique id, severity, section, decision, "
            "required change, owner, closure status, and closure artifact."
        ),
    )
    add_required_ops(response)
    response.add_argument("deliverable_id", help="Deliverable id such as DELIV-0001.")
    response.add_argument("--critique-id", help="Explicit response row id such as RRM-0001.")
    response.add_argument("--source-review", help="Source critic review id or artifact that raised the issue.")
    response.add_argument("--severity", choices=SEVERITY_LEVELS, help="Critique severity.")
    response.add_argument("--target-section", help="Deliverable section affected by the critique.")
    response.add_argument("--issue", help="Critique issue being tracked.")
    response.add_argument("--decision", choices=RESPONSE_MATRIX_DECISION_CHOICES, help="Response decision for this critique.")
    response.add_argument("--required-change", help="Required change, rejected rationale target, or waiver scope.")
    response.add_argument("--response-rationale", help="Rationale for modified, rejected, deferred, or human-waived decisions.")
    response.add_argument("--owner", help="Human or agent owner responsible for closure.")
    response.add_argument("--status", choices=RESPONSE_MATRIX_STATUS_CHOICES, help="Closure status for this response row.")
    response.add_argument("--closure-artifact", help="Evidence artifact path relative to research_ops for closed accepted/modified rows.")
    response.add_argument("--now", help="Override current timestamp for deterministic tests.")
    response.set_defaults(func=run_deliverable_response_command)

    check = add_command(
        deliverable_sub,
        "check",
        help="Check deliverable readiness without mutating files.",
        description=(
            "Return maturity, checklist, source-task, review-independence, and open-gap status. "
            "Exits 0 only when the target maturity is actually ready; accepted source tasks alone are insufficient."
        ),
    )
    add_required_ops(check)
    check.add_argument("deliverable_id", help="Deliverable id such as DELIV-0001.")
    check.add_argument("--target-maturity", choices=MATURITY_CHOICES, help="Override the target maturity for this check only.")
    check.set_defaults(func=run_deliverable_check_command)


def register_anti_context_commands(subparsers) -> None:
    anti_context = add_command(
        subparsers,
        "anti-context",
        help="Generate cross-task anti-context for new tasks.",
        description="Build anti_context.md from accepted memory, rejected ideas, and rejected task failure modes.",
    )
    anti_sub = anti_context.add_subparsers(dest="anti_context_command", required=True)
    build = add_command(
        anti_sub,
        "build",
        help="Build anti-context for a proposed task title.",
        description="Build anti-context for a proposed task, printing Markdown as JSON and optionally updating task.md.",
    )
    add_required_ops(build)
    build.add_argument("--title", required=True, help="Proposed task or candidate title to compare with prior memory.")
    build.add_argument("--task-dir", type=Path, help="Task directory to receive anti_context.md and a task.md section.")
    build.add_argument("--output", type=Path, help="Write the anti-context Markdown to this path instead of a task folder.")
    build.add_argument("--threshold", type=float, default=0.2, help="Similarity threshold for accepted/rejected matches.")
    build.add_argument("--max-items", type=int, default=3, help="Maximum accepted and rejected matches to include.")
    build.set_defaults(func=run_anti_context_build_command)


def register_reflection_commands(subparsers) -> None:
    reflection = add_command(
        subparsers,
        "reflection",
        help="Record targeted reflection for future planning context.",
        description=(
            "Write bounded failure-class reflections under research_ops/reflections so anti-context can "
            "inject only relevant mitigation guidance."
        ),
    )
    reflection_sub = reflection.add_subparsers(dest="reflection_command", required=True)
    record = add_command(
        reflection_sub,
        "record",
        help="Record one targeted reflection from a task review artifact.",
        description=(
            "Create a targeted_reflection_v1.0 JSONL row with failure class, trigger condition, affected "
            "stage, mitigation, future anti-context text, and review evidence under research_ops."
        ),
        epilog="Exits 0 when the reflection is recorded, 2 for invalid records or unsafe task paths.",
    )
    record.add_argument("task_dir", type=Path, help="Task directory under research_ops/tasks.")
    record.add_argument("--failure-class", choices=FAILURE_CLASSES, required=True)
    record.add_argument("--trigger-condition", required=True)
    record.add_argument("--affected-stage", choices=AFFECTED_STAGES, required=True)
    record.add_argument("--mitigation", required=True)
    record.add_argument("--anti-context", required=True, help="Future anti-context injection text for relevant planning tasks.")
    record.add_argument("--review-evidence", type=Path, required=True, help="Review artifact path under the task or research_ops.")
    record.add_argument("--review-summary", help="Short review-evidence summary stored with the record.")
    record.add_argument("--reflection-id", help="Explicit reflection id such as REFL-000001.")
    record.add_argument("--status", choices=["active", "suppressed", "superseded"], default="active")
    record.add_argument("--expires-at", help="Optional ISO timestamp after which the record is no longer injected.")
    record.add_argument("--dry-run", action="store_true", help="Validate and print without writing the reflection ledger.")
    record.add_argument("--now", help="Override created_at for deterministic output.")
    record.set_defaults(func=run_reflection_record_command)


def register_review_commands(subparsers) -> None:
    review = add_command(
        subparsers,
        "review",
        help="Draft, submit, prepare, install, or aggregate reviewer notes.",
        description="Draft or submit role-specific reviews, prepare isolated review bundles, install completed outputs, and aggregate review files.",
    )
    review_sub = review.add_subparsers(dest="review_command", required=True)
    draft = add_command(
        review_sub,
        "draft",
        help="Preview or write a conservative role-specific review scaffold.",
        description="Generate a safe needs_human review scaffold for reviews/<role>.md without requiring direct internal helper usage.",
    )
    draft.add_argument("task_dir", type=Path, help="Task directory containing status.json.")
    draft.add_argument("--role", help="Reviewer role: primary, methodology, or skeptic.")
    draft.add_argument("--decision", help="Override the conservative draft decision; defaults to needs_human.")
    draft.add_argument("--claim-strength", help="Override the conservative draft claim strength; defaults to none.")
    draft.add_argument("--confidence", help="Override the conservative draft confidence; defaults to 0.")
    draft.add_argument("--concern", action="append", help="Main concern. Repeat for multiple concerns.")
    draft.add_argument("--followup", action="append", help="Required follow-up. Repeat for multiple follow-ups.")
    draft.add_argument("--evidence-gap", action="append", help="Evidence gap. Repeat for multiple gaps.")
    draft.add_argument("--write", action="store_true", help="Write reviews/<role>.md instead of previewing the scaffold.")
    draft.add_argument("--force", action="store_true", help="Replace an existing role-specific review file.")
    draft.set_defaults(func=run_review_draft_command)
    submit = add_command(
        review_sub,
        "submit",
        help="Write one explicit role-specific review file.",
        description="Validate explicit review flags and write reviews/<role>.md with required version metadata.",
    )
    submit.add_argument("task_dir", type=Path, help="Task directory containing status.json.")
    submit.add_argument("--role", help="Reviewer role: primary, methodology, or skeptic.")
    submit.add_argument("--decision", help="Review decision: accept, accept_with_caveats, needs_revision, needs_human, or reject.")
    submit.add_argument("--claim-strength", help="Claim strength: none, weak, suggestive, moderate, or strong.")
    submit.add_argument("--confidence", help="Reviewer confidence as a number from 0 to 1.")
    submit.add_argument("--concern", action="append", help="Main concern. Repeat for multiple concerns.")
    submit.add_argument("--followup", action="append", help="Required follow-up. Repeat for multiple follow-ups.")
    submit.add_argument("--evidence-gap", action="append", help="Evidence gap. Repeat for multiple gaps.")
    submit.add_argument("--dry-run", action="store_true", help="Validate and print the review without writing reviews/<role>.md.")
    submit.add_argument("--force", action="store_true", help="Replace an existing role-specific review file.")
    submit.set_defaults(func=run_review_submit_command)
    prepare = add_command(
        review_sub,
        "prepare-context",
        help="Prepare an isolated reviewer or aggregator bundle.",
        description="Copy task inputs into an isolated reviewer bundle; reviewer bundles exclude sibling reviews and aggregator bundles include them.",
    )
    prepare.add_argument("task_dir", type=Path, help="Task directory to bundle.")
    prepare.add_argument("--role", required=True, choices=REVIEW_CONTEXT_ROLE_CHOICES, help="Reviewer role for the bundle.")
    prepare.add_argument("--bundle-dir", required=True, type=Path, help="Bundle directory to create.")
    prepare.add_argument("--force", action="store_true", help="Replace an existing bundle directory.")
    prepare.set_defaults(func=run_review_prepare_context_command)
    install = add_command(
        review_sub,
        "install-context",
        help="Install one completed isolated review output.",
        description="Copy only the completed isolated review output from a review bundle back into the source task.",
    )
    install.add_argument("bundle_dir", type=Path, help="Prepared bundle containing manifest.json and output/.")
    install.add_argument("--force", action="store_true", help="Replace an existing target review output.")
    install.set_defaults(func=run_review_install_context_command)
    aggregate = add_command(
        review_sub,
        "aggregate",
        help="Aggregate review decisions for one task.",
        description="Read reviews/*.md, compute a deterministic aggregate, and optionally update task state and result ledgers.",
    )
    aggregate.add_argument("task_dir", type=Path, help="Task directory containing status.json and reviews/.")
    aggregate.add_argument("--dry-run", action="store_true", help="Validate and preview routing without writing aggregate/status files.")
    aggregate.add_argument(
        "--record-review-start",
        action="store_true",
        help="Validate and record a missing awaiting_review -> single_review/panel_review transition before aggregating.",
    )
    aggregate.set_defaults(
        func=lambda a: module_main(
            "aggregate_reviews",
            [str(a.task_dir)]
            + (["--dry-run"] if a.dry_run else [])
            + (["--record-review-start"] if a.record_review_start else []),
        )
    )


def add_revision_schema_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--schema", type=Path, help="Override the canonical task_status schema.")


def register_revision_commands(subparsers) -> None:
    revision = add_command(
        subparsers,
        "revision",
        help="Inspect or apply bounded revision counters.",
        description="Manage bounded revision counters: request revisions, inspect revision state, and report tasks that hit revision limits.",
    )
    revision_sub = revision.add_subparsers(dest="revision_command", required=True)
    defaults = add_command(
        revision_sub,
        "defaults",
        help="Print default max revisions for a review tier.",
        description="Show the default max revisions for a review tier.",
    )
    defaults.add_argument("--tier", type=int, choices=[1, 2, 3], required=True, help="Public review tier to inspect.")
    defaults.set_defaults(func=run_revision_defaults_command)
    request = add_command(
        revision_sub,
        "request",
        help="Request a bounded task revision.",
        description="Request a bounded task revision by incrementing revision_count and routing safely.",
    )
    request.add_argument("task_dir", type=Path, help="Task directory or status.json path.")
    request.add_argument("--reviewer", default="reviewer", help="Reviewer requesting the revision.")
    request.add_argument("--reason", default="reviewer_requested_revision", help="Transition reason recorded on the task.")
    request.add_argument("--dry-run", action="store_true", help="Validate and print the transition without writing status.json.")
    add_revision_schema_option(request)
    request.set_defaults(func=run_revision_request_command)
    inspect = add_command(
        revision_sub,
        "inspect",
        help="Inspect revision fields for one task.",
        description="Validate and print revision fields: revision_count, max_revisions, and revision_limit_hit.",
    )
    inspect.add_argument("task_dir", type=Path, help="Task directory or status.json path.")
    add_revision_schema_option(inspect)
    inspect.set_defaults(func=run_revision_inspect_command)
    scan = add_command(
        revision_sub,
        "scan-limits",
        help="List tasks that hit revision limits.",
        description="Scan task status files for revision-limit hits, printing JSON by default or Markdown with --markdown.",
    )
    scan.add_argument("tasks_dir", type=Path, help="research_ops/tasks directory to scan.")
    scan.add_argument("--markdown", action="store_true", help="Print a Markdown table instead of JSON.")
    scan.set_defaults(func=run_revision_scan_limits_command)


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


def register_analysis_commands(subparsers) -> None:
    analysis = add_command(
        subparsers,
        "analysis",
        help="Preflight, validate, and surface analysis-run tasks.",
        description="Preflight analysis tasks before execution, validate completed run artifacts before result acceptance, and render read-only analysis surfaces.",
    )
    analysis_sub = analysis.add_subparsers(dest="analysis_command", required=True)
    dashboard = add_command(
        analysis_sub,
        "dashboard",
        help="Render a read-only analysis dashboard.",
        description=(
            "Read-only dashboard for active run_analysis preflight state, completed-run validation gaps, "
            "accepted empirical evidence, revalidation triggers, and blocked or capped claims."
        ),
        epilog="Exits 0 when dashboard data is clean, 2 when analysis warnings or blockers are present, and 4 when malformed state prevents reliable dashboard output.",
    )
    add_common_ops(dashboard)
    dashboard.add_argument("--now", help="Override current time for deterministic source/data and accepted-memory checks.")
    dashboard.add_argument("--max-items", type=int, default=10, help="Maximum rows per dashboard section.")
    dashboard.set_defaults(func=lambda a: module_main("analysis_surface", ["dashboard", str(a.ops_dir), "--max-items", str(a.max_items)] + (["--now", a.now] if a.now else [])))

    reviewer_packet = add_command(
        analysis_sub,
        "reviewer-packet",
        help="Render a read-only reviewer packet for one analysis run.",
        description=(
            "Read-only reviewer packet for one run_analysis task: bundles the accepted experiment plan, "
            "run artifacts, validator outputs, result-acceptance state, source/data governance status, "
            "and recommended reviewer focus without accepting evidence."
        ),
        epilog="Exits 0 when packet context is complete, 2 when validators or artifacts have findings, 3 for invalid paths, and 4 when malformed state prevents reliable packet output.",
    )
    reviewer_packet.add_argument("ops_dir", type=Path, help="Path to research_ops.")
    reviewer_packet.add_argument("analysis_run_dir", type=Path, help="run_analysis task directory to package for review.")
    reviewer_packet.add_argument("--now", help="Override current time for deterministic source/data and accepted-memory checks.")
    reviewer_packet.set_defaults(func=lambda a: module_main("analysis_surface", ["reviewer-packet", str(a.ops_dir), str(a.analysis_run_dir)] + (["--now", a.now] if a.now else [])))

    run_adapter = add_command(
        analysis_sub,
        "run-adapter",
        help="Plan or execute a preflight-gated local analysis adapter.",
        description=(
            "Optional thin adapter runner for run_analysis tasks. It supports runner.type=local_script, "
            "runs only after clean analysis preflight, and never replaces validate-run or validate-results."
        ),
        epilog="Exits 0 for a clean dry-run plan or successful adapter execution, 2 for preflight findings or command failure, 3 for unsupported adapters or invalid requests, and 4 for malformed task state.",
    )
    run_adapter.add_argument("task_dir", type=Path, help="run_analysis task directory.")
    run_adapter.add_argument("--ops-dir", type=Path, required=True, help="research_ops directory.")
    run_adapter.add_argument("--execute", action="store_true", help="Actually execute the adapter command; omitted means dry-run plan only.")
    run_adapter.add_argument("--timeout-seconds", type=float, default=900.0, help="Maximum adapter execution time.")
    run_adapter.add_argument("--cwd", type=Path, help="Command working directory; defaults to the workspace root.")
    run_adapter.add_argument("--now", help="Override current time for deterministic preflight checks.")
    run_adapter.set_defaults(
        func=lambda a: module_main(
            "analysis_adapters",
            [
                "run-adapter",
                str(a.task_dir),
                "--ops-dir",
                str(a.ops_dir),
                "--timeout-seconds",
                str(a.timeout_seconds),
            ]
            + (["--execute"] if a.execute else [])
            + (["--cwd", str(a.cwd)] if a.cwd else [])
            + (["--now", a.now] if a.now else []),
        )
    )

    preflight = add_command(
        analysis_sub,
        "preflight",
        help="Run a read-only analysis preflight.",
        description=(
            "Read-only preflight for a run_analysis task: validates status.json, the run manifest, "
            "accepted experiment plan linkage, source/data readiness, budget, method and metric alignment, "
            "output paths, and stale accepted memory before analysis starts."
        ),
        epilog="Exits 0 when clean, 2 for blockers or reviewable warnings, 3 for invalid requests, and 4 for malformed task state.",
    )
    preflight.add_argument("task_dir", type=Path, help="run_analysis task directory to preflight.")
    preflight.add_argument("--ops-dir", type=Path, required=True, help="research_ops directory.")
    preflight.add_argument("--now", help="Override current time for deterministic source/data and accepted-memory checks.")
    preflight.set_defaults(func=lambda a: module_main("analysis_runs", ["preflight", str(a.task_dir), "--ops-dir", str(a.ops_dir)] + (["--now", a.now] if a.now else [])))

    validate_run = add_command(
        analysis_sub,
        "validate-run",
        help="Validate completed analysis-run artifacts.",
        description=(
            "Read-only validation for a completed run_analysis task: validates run_manifest.json, "
            "structured metrics/diagnostics/robustness artifacts, accepted plan alignment, required outputs, "
            "baseline evidence, metric changes, and robustness semantics."
        ),
        epilog="Exits 0 when clean, 2 for blockers or reviewable warnings, 3 for invalid requests, and 4 for malformed task state.",
    )
    validate_run.add_argument("task_dir", type=Path, help="run_analysis task directory to validate.")
    validate_run.add_argument("--ops-dir", type=Path, required=True, help="research_ops directory.")
    validate_run.add_argument("--now", help="Override current time for deterministic source/data and accepted-memory checks.")
    validate_run.set_defaults(func=lambda a: module_main("analysis_validation", ["validate-run", str(a.task_dir), "--ops-dir", str(a.ops_dir)] + (["--now", a.now] if a.now else [])))

    validate_results = add_command(
        analysis_sub,
        "validate-results",
        help="Validate result summary and claim gates.",
        description=(
            "Read-only validation for completed analysis results: compares the result summary and claim_gates.json "
            "with the run manifest, metrics, diagnostics, robustness checks, and accepted experiment plan."
        ),
        epilog="Exits 0 when clean, 2 for blockers or reviewable warnings, 3 for invalid requests, and 4 for malformed task state.",
    )
    validate_results.add_argument("task_dir", type=Path, help="run_analysis task directory to validate.")
    validate_results.add_argument("--ops-dir", type=Path, required=True, help="research_ops directory.")
    validate_results.add_argument("--now", help="Override current time for deterministic source/data and accepted-memory checks.")
    validate_results.set_defaults(func=lambda a: module_main("analysis_validation", ["validate-results", str(a.task_dir), "--ops-dir", str(a.ops_dir)] + (["--now", a.now] if a.now else [])))


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
        help="Score, validate, or manage idea artifacts.",
        description="Score idea candidates, validate idea-evaluation JSON artifacts, and manage the durable idea catalog.",
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
    idea_capture = add_command(
        idea_sub,
        "capture",
        help="Preview or write discovery-to-catalog capture.",
        description="Build or write one canonical IDEA JSON record from discovery_inbox.md or an explicit title.",
        epilog=(
            "Examples:\n"
            "  async-research idea capture research_ops --from-inbox row-7 --id IDEA-0007 --dry-run\n"
            "  async-research idea capture research_ops --from-inbox row-7 --id IDEA-0007 --write\n"
            "  async-research idea capture research_ops --title \"New angle\" --id IDEA-0008 --dry-run\n\n"
            "Write mode uses research_ops/ideas/LOCK and regenerates generated catalog projections without editing queue.md."
        ),
    )
    add_common_ops(idea_capture)
    idea_capture.add_argument("--from-inbox", help="Discovery inbox item id or row-N selector to capture explicitly.")
    idea_capture.add_argument("--id", dest="idea_id", help="Canonical IDEA-0000 id for the proposed catalog record.")
    idea_capture.add_argument("--title", help="Title for an explicit title-only capture proposal.")
    idea_capture.add_argument("--dry-run", action="store_true", help="Preview proposals without writing; this is the default.")
    idea_capture.add_argument("--write", action="store_true", help="Create the canonical IDEA JSON and regenerate projections.")
    idea_capture.add_argument("--update-existing", action="store_true", help="Allow write mode to merge captured metadata into an existing same-ID IDEA JSON record.")
    idea_capture.set_defaults(func=run_idea_capture_command)
    idea_promote = add_command(
        idea_sub,
        "promote",
        help="Preview or write one catalog idea promotion task.",
        description="Produce one bounded promotion task proposal from a canonical catalog idea; write mode creates the reserved task folder and queue row.",
        epilog=(
            "Examples:\n"
            "  async-research idea promote research_ops IDEA-0007 --dry-run\n"
            "  async-research idea promote research_ops IDEA-0007 --write --preflight-hash <hash>\n\n"
            "Dry-run is proposal-only and returns promotion_preflight_hash. A validated research brief is consumed when present. Blocked dry-runs include next_step and "
            "remediation_steps. Write mode requires the matching hash, appends inbox.md, creates one tasks/TASK-*/ "
            "folder, appends one queue.md row, and updates the selected idea's promoted_task_id under the catalog lock."
        ),
    )
    add_common_ops(idea_promote)
    idea_promote.add_argument("idea_id", help="Canonical idea id such as IDEA-0001.")
    idea_promote.add_argument("--task-type", choices=PROMOTION_TASK_TYPES, help="Explicit task type override for the promotion proposal.")
    idea_promote.add_argument("--brief", type=Path, help="Optional research_ops/briefs/research_brief.json path; defaults to the workspace brief when present.")
    idea_promote.add_argument("--allow-duplicate", action="store_true", help="Record a human override allowing duplicate or near-duplicate ideas to produce a proposal.")
    idea_promote.add_argument("--preflight-hash", help="Required with --write; use promotion_preflight_hash from a prior dry run.")
    idea_promote.add_argument("--human-override", action="store_true", help="Confirm a recorded human decision for high-risk promotion task writes.")
    idea_promote.add_argument("--dry-run", action="store_true", help="Preview the task proposal without writing; this is the default.")
    idea_promote.add_argument("--write", action="store_true", help="Create the reserved task folder, append queue.md, append inbox.md, and update the selected idea.")
    idea_promote.set_defaults(func=run_idea_promote_command)
    idea_metrics = add_command(
        idea_sub,
        "metrics",
        help="Render read-only idea lifecycle metrics.",
        description="Read canonical ideas, queue rows, linked task statuses, accepted outputs, and cost ledger rows to report deterministic idea lifecycle metrics without mutating research_ops.",
    )
    add_common_ops(idea_metrics)
    idea_metrics.add_argument("--now", help="Override report time for deterministic parked-age metrics.")
    idea_metrics.set_defaults(func=run_idea_metrics_command)
    idea_trace = add_command(
        idea_sub,
        "trace",
        help="Trace one idea to promoted tasks and outputs.",
        description="Explain why a promoted task exists by reading one canonical idea, queue evidence, linked task status metadata, promotion trace fields, and accepted-output rows without mutating research_ops.",
    )
    add_common_ops(idea_trace)
    idea_trace.add_argument("idea_id", help="Canonical idea id such as IDEA-0001.")
    idea_trace.add_argument("--now", help="Override report time for deterministic parked-age metrics.")
    idea_trace.set_defaults(func=run_idea_trace_command)
    idea_resolve = add_command(
        idea_sub,
        "resolve",
        help="Resolve a needs_human catalog idea.",
        description=(
            "Resolve one needs_human catalog idea to candidate, promote, park, or reject with a decisions.md row, "
            "decision history, regenerated projections, and promotion hard-gate checks."
        ),
        epilog="Dry-run is the default. Write mode uses research_ops/ideas/LOCK, appends decisions.md, never edits queue.md, and refuses unsafe promote targets.",
    )
    add_common_ops(idea_resolve)
    idea_resolve.add_argument("idea_id", help="Canonical idea id such as IDEA-0001.")
    idea_resolve.add_argument("--status", required=True, choices=IDEA_RESOLUTION_STATUS_CHOICES, help="Target lifecycle status.")
    idea_resolve.add_argument("--reason", required=True, help="Human reason for resolving the idea.")
    idea_resolve.add_argument("--approver", required=True, help="Human or agent identity approving the decision.")
    idea_resolve.add_argument("--revisit", help="Concrete revisit condition; required when --status park.")
    idea_resolve.add_argument("--related-artifact", action="append", default=[], help="Additional artifact to link in decisions.md. Repeatable.")
    idea_resolve.add_argument("--date", help="Decision timestamp override in ISO-8601 format.")
    idea_resolve.add_argument("--dry-run", action="store_true", help="Preview the status and decision-log changes without writing; this is the default.")
    idea_resolve.add_argument("--write", action="store_true", help="Apply the resolution under research_ops/ideas/LOCK and append decisions.md.")
    idea_resolve.set_defaults(func=run_idea_resolve_command)
    idea_park = add_command(
        idea_sub,
        "park",
        help="Park one catalog idea.",
        description="Move one canonical catalog idea to park with a reason, revisit condition, decision history, and regenerated projections.",
    )
    add_common_ops(idea_park)
    idea_park.add_argument("idea_id", help="Canonical idea id such as IDEA-0001.")
    idea_park.add_argument("--reason", required=True, help="Reason for parking the idea.")
    idea_park.add_argument("--revisit", required=True, help="Concrete condition for revisiting the idea.")
    idea_park.add_argument("--dry-run", action="store_true", help="Preview the status change without writing; this is the default.")
    idea_park.add_argument("--write", action="store_true", help="Apply the status change under research_ops/ideas/LOCK.")
    idea_park.set_defaults(func=run_idea_park_command)
    idea_reject = add_command(
        idea_sub,
        "reject",
        help="Reject one catalog idea.",
        description="Move one canonical catalog idea to reject with a reason, decision history, and regenerated projections.",
    )
    add_common_ops(idea_reject)
    idea_reject.add_argument("idea_id", help="Canonical idea id such as IDEA-0001.")
    idea_reject.add_argument("--reason", required=True, help="Reason for rejecting the idea.")
    idea_reject.add_argument("--revisit", help="Optional reopen condition; a conservative default is used when omitted.")
    idea_reject.add_argument("--dry-run", action="store_true", help="Preview the status change without writing; this is the default.")
    idea_reject.add_argument("--write", action="store_true", help="Apply the status change under research_ops/ideas/LOCK.")
    idea_reject.set_defaults(func=run_idea_reject_command)
    idea_catalog = add_command(
        idea_sub,
        "catalog",
        help="Initialize or inspect the durable idea catalog.",
        description="Manage the durable idea catalog in research_ops/ideas, separate from discovery_inbox.md and queue.md.",
    )
    idea_catalog_sub = idea_catalog.add_subparsers(dest="idea_catalog_command", required=True)
    idea_catalog_init = add_command(
        idea_catalog_sub,
        "init",
        help="Add missing idea catalog starter files.",
        description="Preview or create missing research_ops/ideas starter files without overwriting existing files.",
        epilog="Without --write, this command is a dry run and reports the exact files it would add.",
    )
    add_common_ops(idea_catalog_init)
    idea_catalog_init.add_argument("--dry-run", action="store_true", help="Preview missing files without writing; this is the default.")
    idea_catalog_init.add_argument("--write", action="store_true", help="Create only missing idea catalog files.")
    idea_catalog_init.set_defaults(func=run_idea_catalog_init_command)
    idea_catalog_validate = add_command(
        idea_catalog_sub,
        "validate",
        help="Validate the durable idea catalog.",
        description="Validate canonical idea JSON, generated projections, lifecycle gates, and references without mutating files.",
    )
    add_common_ops(idea_catalog_validate)
    idea_catalog_validate.set_defaults(func=run_idea_catalog_validate_command)
    idea_catalog_list = add_command(
        idea_catalog_sub,
        "list",
        help="List canonical idea catalog records.",
        description="List canonical research_ops/ideas/IDEA-*.json records with stored status and derived display labels.",
    )
    add_common_ops(idea_catalog_list)
    idea_catalog_list.add_argument("--status", choices=STORED_STATUSES, help="Filter by stored idea status.")
    idea_catalog_list.set_defaults(func=run_idea_catalog_list_command)
    idea_catalog_dashboard = add_command(
        idea_catalog_sub,
        "dashboard",
        help="Render a read-only idea portfolio dashboard.",
        description="Render a read-only portfolio dashboard with candidate, parked, promoted, rejected, blocker, score, task recommendation, and idea-to-task-link views from canonical catalog state.",
    )
    add_common_ops(idea_catalog_dashboard)
    idea_catalog_dashboard.add_argument("--max-blockers", type=int, default=10, help="Maximum validation blockers to include in the top_blockers section.")
    idea_catalog_dashboard.set_defaults(func=run_idea_catalog_dashboard_command)
    idea_catalog_show = add_command(
        idea_catalog_sub,
        "show",
        help="Show one canonical idea catalog record.",
        description="Show one canonical idea JSON record and derived catalog summary without mutating files.",
    )
    add_common_ops(idea_catalog_show)
    idea_catalog_show.add_argument("idea_id", help="Canonical idea id such as IDEA-0001.")
    idea_catalog_show.set_defaults(func=run_idea_catalog_show_command)
    idea_catalog_maintain = add_command(
        idea_catalog_sub,
        "maintain",
        help="Preview or write catalog maintenance proposals.",
        description="Read discovery_inbox.md, accepted/rejected refs, and canonical idea JSON to plan or apply conservative maintenance.",
        epilog="Write mode uses research_ops/ideas/LOCK, regenerates projections, and never edits queue.md or task folders.",
    )
    add_common_ops(idea_catalog_maintain)
    idea_catalog_maintain.add_argument("--dry-run", action="store_true", help="Preview proposals without writing; this is the default.")
    idea_catalog_maintain.add_argument("--write", action="store_true", help="Apply safe maintenance changes and regenerate generated catalog projections.")
    idea_catalog_maintain.add_argument("--update-existing", action="store_true", help="Allow write mode to replace an existing IDEA JSON target if a create plan races with an existing file.")
    idea_catalog_maintain.set_defaults(func=run_idea_catalog_maintain_command)

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
    simulate.add_argument("--work-dir", type=Path, help="Use this isolated simulation directory instead of the default temp path.")
    simulate.add_argument("--keep-work-dir", action="store_true", help="Keep isolated simulation fixtures for debugging.")
    simulate.set_defaults(func=run_simulate_week_command)


COMMAND_REGISTRARS = (
    register_package_commands,
    register_status_commands,
    register_surface_commands,
    register_console_commands,
    register_schema_command,
    register_mode_commands,
    register_workflow_commands,
    register_queue_commands,
    register_prompt_commands,
    register_schedule_commands,
    register_decision_commands,
    register_escalation_commands,
    register_source_commands,
    register_data_commands,
    register_library_commands,
    register_runtime_commands,
    register_eval_commands,
    register_evidence_memory_commands,
    register_model_routing_commands,
    register_scaling_commands,
    register_brief_commands,
    register_cost_commands,
    register_batch_commands,
    register_metrics_commands,
    register_accepted_commands,
    register_outcomes_commands,
    register_deliverable_commands,
    register_anti_context_commands,
    register_reflection_commands,
    register_review_commands,
    register_revision_commands,
    register_result_command,
    register_analysis_commands,
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
