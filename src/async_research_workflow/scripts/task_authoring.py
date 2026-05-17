#!/usr/bin/env python3
"""Public helpers for creating schema-valid task folders."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import re
import sys
from typing import Any, Iterable

from async_research_workflow.resources import schema_path
from async_research_workflow.scripts import validate_transition
from async_research_workflow.scripts.schema_diagnostics import status_schema_diagnostics
from async_research_workflow.scripts.validate_json_artifact import load_json, validate
from async_research_workflow.scripts.version_metadata import apply_default_versions


SUCCESS = 0
VALIDATION_FAILED = 2
INVALID_REQUEST = 3
MALFORMED = 4
TARGET_EXISTS = 5

TASK_TYPES = [
    "literature_extract",
    "idea_discovery",
    "idea_dedupe",
    "idea_scoring",
    "batch_job",
    "batch_ingest",
    "hypothesis_card",
    "data_readiness",
    "experiment_plan",
    "code_patch",
    "run_analysis",
    "evaluate_results",
    "critic_review",
    "memo_section",
    "weekly_synthesis",
    "status_update",
    "admin",
]
TASK_ID_RE = re.compile(r"^TASK-[0-9]{4}$")


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "manual-task"


def existing_task_numbers(ops_dir: Path) -> list[int]:
    tasks_dir = ops_dir / "tasks"
    numbers: list[int] = []
    if not tasks_dir.exists():
        return numbers
    for path in tasks_dir.iterdir():
        match = re.match(r"TASK-([0-9]{4})(?:-|$)", path.name)
        if match:
            numbers.append(int(match.group(1)))
    return numbers


def next_task_id(ops_dir: Path) -> str:
    used = set(existing_task_numbers(ops_dir))
    number = 1
    while number in used:
        number += 1
    return f"TASK-{number:04d}"


def review_policy(tier: int) -> dict[str, Any]:
    reviewers = {
        1: ["primary"],
        2: ["primary", "methodology"],
        3: ["primary", "methodology", "skeptic"],
    }[tier]
    return {
        "tier": tier,
        "required_reviewers": reviewers,
        "panel_required": tier >= 2,
        "human_required_for_acceptance": tier >= 3,
    }


def result_placeholder() -> dict[str, Any]:
    return {
        "recommendation": None,
        "claim_strength": "none",
        "claim_strength_stale": False,
        "claim_strength_revalidation_required": False,
        "claim_strength_revalidation_reason": None,
        "claim_strength_revalidated_at": None,
        "claim_strength_policy": "result_acceptance_v1.0_claim_caps",
        "followup_count": 0,
    }


def task_dir_name(task_id: str, slug: str) -> str:
    return f"{task_id}-{slugify(slug)}"


def default_allowed_paths(task_dir: Path, ops_dir: Path, extra_paths: list[str]) -> list[str]:
    try:
        task_ref = task_dir.relative_to(ops_dir.parent).as_posix()
    except ValueError:
        task_ref = task_dir.as_posix()
    paths = [f"{task_ref}/**"]
    paths.extend(path for path in extra_paths if path.strip())
    return paths


def build_status(args: argparse.Namespace, task_id: str, task_dir: Path) -> dict[str, Any]:
    now = iso_now()
    status = {
        "schema_version": "1.0",
        "id": task_id,
        "title": args.title,
        "type": args.task_type,
        "status": "ready_for_worker",
        "previous_status": None,
        "last_transition_reason": args.transition_reason,
        "priority": args.priority,
        "revision_count": 0,
        "max_revisions": args.max_revisions,
        "revision_limit_hit": False,
        "created_at": now,
        "updated_at": now,
        "lock_owner": None,
        "lock_expires_at": None,
        "allowed_paths": default_allowed_paths(task_dir, args.ops_dir, args.allowed_path or []),
        "allowed_tools": ["repo_read", "markdown_edit"],
        "allow_browsing": bool(args.allow_browsing),
        "allow_code_execution": False,
        "allow_network": bool(args.allow_network),
        "max_minutes": args.max_minutes,
        "max_turns": args.max_turns,
        "model_tier": args.model_tier,
        "review_policy": review_policy(args.review_tier),
        "escalate_to_tier": None,
        "escalation_reason": None,
        "escalation_requested_by": None,
        "escalation_requested_at": None,
        "requires_human": False,
        "data_audit_refs": args.data_audit_ref or [],
        "human_gate_reason": None,
        "budget": {
            "max_api_usd": args.max_api_usd,
            "max_compute_usd": args.max_compute_usd,
        },
        "result": result_placeholder(),
    }
    if args.catalog_idea_id:
        status["catalog_idea_id"] = args.catalog_idea_id
    return apply_default_versions(status)


def task_markdown(args: argparse.Namespace, task_id: str) -> str:
    objective = args.objective or "State exactly what should be produced and how it will be used."
    context_lines = args.context or ["Add relevant workspace files, source IDs, library refs, or accepted outputs here."]
    context = "\n".join(f"- {item}" for item in context_lines)
    data_refs = ", ".join(args.data_audit_ref or []) or "none"
    return f"""# {task_id}: {args.title}

## Objective

{objective}

## Scope

- Work only inside this task folder and the paths listed in `status.json`.
- Do not create new tasks directly; propose follow-ups in `worker_output.md`.
- Respect the review tier and human-escalation policy in `status.json`.

## Required Output

Write `worker_output.md` with:

- summary
- evidence or reasoning
- caveats and source/data limitations
- recommendation
- proposed follow-ups

Generic Markdown or prose-only artifacts are capped at `suggestive` claim
strength. To support stronger claims, include the structured result summary,
analysis run manifest, diagnostics, robustness checks, and claim gates required
by the task type.

## Acceptance Criteria

- Output answers the objective.
- Claims are supported by the listed evidence and allowed source/data use.
- Caveats are explicit.
- No files outside `allowed_paths` changed.
- Validation commands relevant to this task type are reported in `worker_output.md`.

## Review Policy

- Review tier: {args.review_tier}.
- Required reviewers: {", ".join(review_policy(args.review_tier)["required_reviewers"])}.
- Escalate public, high-stakes, or moderate/strong claims before acceptance.

## Context

{context}

## Data Source Audit

- Data audit refs: {data_refs}
- Source-dependent accepted evidence must cite audited `DS-*` source IDs and pass source governance checks.

## Cross-Task Anti-Context

Run `async-research anti-context build` for this task before assigning worker effort when prior accepted or rejected work exists.
"""


def validate_status(status: dict[str, Any], task_dir: Path) -> tuple[bool, list[dict[str, Any]], dict[str, Any]]:
    schema = load_json(schema_path("task_status.schema.json"))
    schema_errors = [error.to_dict() for error in validate(status, schema)]
    decisions_path = task_dir.parent.parent / "decisions.md" if task_dir.parent.name == "tasks" else None
    transition_code, transition = validate_transition.validate_payload(status, decisions_path=decisions_path)
    errors = list(schema_errors)
    if transition_code != validate_transition.SUCCESS:
        errors.append({"path": str(task_dir / "status.json"), "message": "invalid status transition", "transition": transition})
    diagnostics = status_schema_diagnostics(status, schema_errors)
    if diagnostics:
        errors.append({"path": str(task_dir / "status.json"), "message": "status authoring diagnostics", "diagnostics": diagnostics})
    return not errors, errors, transition


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def create_task(args: argparse.Namespace) -> int:
    if args.dry_run and args.write:
        print_json({"ok": False, "reason": "conflicting_flags", "next_step": "use either --dry-run or --write, not both"})
        return INVALID_REQUEST
    if not args.ops_dir.exists() or not args.ops_dir.is_dir():
        print_json({"ok": False, "reason": "ops_dir_missing", "ops_dir": str(args.ops_dir)})
        return MALFORMED
    if not args.title.strip():
        print_json({"ok": False, "reason": "missing_title"})
        return INVALID_REQUEST
    task_id = args.task_id or next_task_id(args.ops_dir)
    if not TASK_ID_RE.match(task_id):
        print_json({"ok": False, "reason": "invalid_task_id", "task_id": task_id, "expected": "TASK-0000"})
        return INVALID_REQUEST
    slug = args.slug or args.title
    task_dir = args.ops_dir / "tasks" / task_dir_name(task_id, slug)
    status = build_status(args, task_id, task_dir)
    markdown = task_markdown(args, task_id)
    valid, errors, transition = validate_status(status, task_dir)
    if not valid:
        print_json({"ok": False, "reason": "generated_task_invalid", "errors": errors, "transition": transition})
        return VALIDATION_FAILED

    payload = {
        "ok": True,
        "action": "task_create_written" if args.write else "task_create_previewed",
        "would_write": not args.write,
        "written": bool(args.write),
        "ops_dir": str(args.ops_dir),
        "task_id": task_id,
        "task_dir": str(task_dir),
        "status_path": str(task_dir / "status.json"),
        "task_markdown_path": str(task_dir / "task.md"),
        "status_json": status,
        "task_markdown": markdown,
        "validation": {"ok": True, "transition": transition},
        "surface_update_command": f"async-research surface update {args.ops_dir}",
        "workflow_check_command": f"async-research workflow check {args.ops_dir}",
        "next_step": f"run async-research surface update {args.ops_dir}, then async-research workflow check {args.ops_dir}",
        "claim_strength_guidance": "Generic Markdown/prose artifacts are capped at suggestive unless structured result evidence supports a stronger claim.",
    }
    if not args.write:
        print_json(payload)
        return SUCCESS
    if task_dir.exists():
        print_json(
            {
                "ok": False,
                "reason": "task_dir_exists",
                "task_dir": str(task_dir),
                "next_step": "choose a different --task-id or --slug; existing task folders are never overwritten",
            }
        )
        return TARGET_EXISTS
    task_dir.mkdir(parents=True)
    atomic_write_json(task_dir / "status.json", status)
    atomic_write_text(task_dir / "task.md", markdown)
    (task_dir / "reviews").mkdir()
    (task_dir / "review_panel").mkdir()
    (task_dir / "artifacts").mkdir()
    print_json(payload)
    return SUCCESS


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create schema-valid async research task templates.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser(
        "create",
        help="Preview or write a minimal valid task folder.",
        description=(
            "Preview or write a minimal valid task folder with non-null status placeholders, "
            "review policy, budget fields, and claim-strength cap guidance. Without --write this is a dry run."
        ),
    )
    create.add_argument("ops_dir", nargs="?", type=Path, default=Path("research_ops"), help="research_ops workspace directory.")
    create.add_argument("--title", required=True, help="Human-readable task title.")
    create.add_argument("--task-id", help="Explicit TASK-0000 id; defaults to the next available id.")
    create.add_argument("--slug", help="Task directory slug; defaults to a slugified title.")
    create.add_argument("--task-type", choices=TASK_TYPES, default="data_readiness", help="Task type for status.json.")
    create.add_argument("--objective", help="Objective paragraph for task.md.")
    create.add_argument("--context", action="append", help="Context path, source, or note. Repeat for multiple entries.")
    create.add_argument("--allowed-path", action="append", default=[], help="Additional allowed path for status.json. Repeat as needed.")
    create.add_argument("--data-audit-ref", action="append", default=[], help="DS-* ref required by this task. Repeat as needed.")
    create.add_argument("--catalog-idea-id", help="Optional IDEA-0000 link for promoted tasks.")
    create.add_argument("--priority", type=int, choices=[1, 2, 3, 4, 5], default=3)
    create.add_argument("--review-tier", type=int, choices=[1, 2, 3], default=1)
    create.add_argument("--max-minutes", type=int, default=45)
    create.add_argument("--max-turns", type=int, default=6)
    create.add_argument("--max-revisions", type=int, choices=[0, 1, 2, 3, 4, 5], default=1)
    create.add_argument("--model-tier", default="codex_standard")
    create.add_argument("--max-api-usd", type=float, default=0.0)
    create.add_argument("--max-compute-usd", type=float, default=0.0)
    create.add_argument("--allow-browsing", action="store_true")
    create.add_argument("--allow-network", action="store_true")
    create.add_argument("--transition-reason", default="manual_task_created_from_template")
    create.add_argument("--dry-run", action="store_true", help="Preview without writing; this is the default.")
    create.add_argument("--write", action="store_true", help="Create the task folder, task.md, status.json, and review/artifact directories.")
    return parser.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    if args.command == "create":
        return create_task(args)
    print_json({"ok": False, "reason": "unknown_command", "command": args.command})
    return MALFORMED


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
