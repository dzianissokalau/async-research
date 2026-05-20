#!/usr/bin/env python3
"""Draft, validate, and dry-run apply bounded research briefs."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from async_research_workflow.resources import schema_path
from async_research_workflow.scripts.validate_json_artifact import load_json, validate


SUCCESS = 0
VALIDATION_FAILED = 2
INVALID_REQUEST = 3
MALFORMED = 4

SCHEMA_VERSION = "1.0"
DEFAULT_BRIEF_RELATIVE_PATH = Path("briefs") / "research_brief.json"
SOURCE_CLASSES = (
    "workspace_files",
    "accepted_memory",
    "knowledge_library",
    "open_web",
    "structured_api",
    "private_data",
    "mcp_private_data",
    "code_execution",
    "paid_services",
    "external_credentials",
)
OUTPUT_MATURITIES = (
    "unspecified",
    "internal_note",
    "internal_draft",
    "shareable_memo",
    "working_paper",
    "submission_ready",
)
PRIVATE_DATA_POLICIES = ("none", "workspace_only", "requires_human_gate", "blocked")
PUBLIC_CLAIM_POLICIES = ("none", "internal_only", "requires_human_gate")
BRIEF_STATUSES = ("ready", "needs_clarification", "needs_human_gate", "blocked")


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso_timestamp(now: datetime | None = None) -> str:
    return (now or utc_now()).isoformat().replace("+00:00", "Z")


def filename_timestamp(now: datetime | None = None) -> str:
    return (now or utc_now()).strftime("%Y%m%dT%H%M%SZ")


def normalize_text(value: Any) -> str:
    return str(value if value is not None else "").strip()


def list_text(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return [str(item).strip() for item in values if str(item).strip()]


def default_brief_path(ops_dir: Path) -> Path:
    return ops_dir / DEFAULT_BRIEF_RELATIVE_PATH


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def resolve_existing_brief_path(ops_dir: Path, brief_path: Path | None) -> tuple[Path | None, dict[str, Any] | None]:
    if brief_path is None:
        candidate = default_brief_path(ops_dir)
        if not candidate.exists():
            return None, None
    else:
        candidate = brief_path if brief_path.is_absolute() else brief_path
        if not candidate.exists():
            relative_candidate = ops_dir / brief_path
            if relative_candidate.exists():
                candidate = relative_candidate
    if not is_relative_to(candidate, ops_dir):
        return None, {
            "ok": False,
            "reason": "brief_path_outside_research_ops",
            "brief_path": str(candidate),
            "ops_dir": str(ops_dir),
            "message": "research brief paths used for planning must stay inside research_ops/",
        }
    if not candidate.exists():
        return None, {
            "ok": False,
            "reason": "brief_path_missing",
            "brief_path": str(candidate),
        }
    return candidate, None


def resolve_output_path(ops_dir: Path, output: Path | None) -> tuple[Path, dict[str, Any] | None]:
    candidate = output or default_brief_path(ops_dir)
    if not candidate.is_absolute() and candidate.parts[:1] == ("briefs",):
        candidate = ops_dir / candidate
    if not is_relative_to(candidate, ops_dir):
        return candidate, {
            "ok": False,
            "reason": "brief_output_outside_research_ops",
            "output": str(candidate),
            "ops_dir": str(ops_dir),
        }
    return candidate, None


def expected_human_gates(brief: dict[str, Any]) -> list[dict[str, str]]:
    permissions = brief.get("permissions") if isinstance(brief.get("permissions"), dict) else {}
    budget = brief.get("budget") if isinstance(brief.get("budget"), dict) else {}
    gates: list[dict[str, str]] = []
    if permissions.get("credentials"):
        gates.append(
            {
                "gate": "credentials",
                "reason": "external credentials require explicit human approval",
                "required_before": "planning",
            }
        )
    if permissions.get("paid_services"):
        gates.append(
            {
                "gate": "paid_services",
                "reason": "paid services require explicit budget approval",
                "required_before": "planning",
            }
        )
    if brief.get("private_data_policy") == "requires_human_gate":
        gates.append(
            {
                "gate": "private_data",
                "reason": "private data use requires a human approval boundary",
                "required_before": "planning",
            }
        )
    if brief.get("public_claims_policy") == "requires_human_gate":
        gates.append(
            {
                "gate": "public_claims",
                "reason": "public-facing claims require human approval and stricter citation gates",
                "required_before": "synthesis",
            }
        )
    if isinstance(budget.get("max_api_usd"), (int, float)) and not isinstance(budget.get("max_api_usd"), bool):
        if float(budget["max_api_usd"]) > 0 and permissions.get("paid_services"):
            gates.append(
                {
                    "gate": "budget",
                    "reason": "nonzero paid API budget requires approval before spending",
                    "required_before": "runtime",
                }
            )
    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for gate in gates:
        name = gate["gate"]
        if name in seen:
            continue
        seen.add(name)
        deduped.append(gate)
    return deduped


def semantic_findings(brief: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []

    if not normalize_text(brief.get("user_question")) or normalize_text(brief.get("user_question")).startswith("TODO"):
        blockers.append({"field": "user_question", "reason": "user_question_required"})
    if not normalize_text(brief.get("clarified_objective")) or normalize_text(brief.get("clarified_objective")).startswith("TODO"):
        blockers.append({"field": "clarified_objective", "reason": "clarified_objective_required"})
    if normalize_text(brief.get("intended_output_maturity")) in {"", "unspecified"}:
        blockers.append({"field": "intended_output_maturity", "reason": "output_target_required"})
    if normalize_text(brief.get("target_audience")).lower() in {"", "unspecified", "unknown", "todo"}:
        blockers.append({"field": "target_audience", "reason": "target_audience_required"})
    status = normalize_text(brief.get("status"))
    if status != "ready":
        blockers.append({"field": "status", "reason": "brief_status_not_ready", "status": status})
    if brief.get("private_data_policy") == "blocked":
        blockers.append({"field": "private_data_policy", "reason": "private_data_policy_blocked"})

    unresolved = list_text(brief.get("unresolved_questions"))
    if unresolved:
        blockers.append(
            {
                "field": "unresolved_questions",
                "reason": "clarifying_questions_unresolved",
                "questions": unresolved,
            }
        )

    expected = expected_human_gates(brief)
    existing_gate_names = {str(item.get("gate") or "") for item in brief.get("human_gates", []) if isinstance(item, dict)}
    for gate in expected:
        if gate["gate"] not in existing_gate_names:
            errors.append({"field": "human_gates", "reason": "required_human_gate_missing", "gate": gate})

    gates = [item for item in brief.get("human_gates", []) if isinstance(item, dict)]
    if gates or expected:
        blockers.append(
            {
                "field": "human_gates",
                "reason": "human_gate_required_before_planning",
                "gates": gates or expected,
            }
        )

    allowed = set(list_text(brief.get("allowed_source_classes")))
    forbidden = set(list_text(brief.get("forbidden_source_classes")))
    overlap = sorted(allowed & forbidden)
    if overlap:
        errors.append({"field": "source_classes", "reason": "source_class_allowed_and_forbidden", "values": overlap})
    if "open_web" in allowed and not brief.get("permissions", {}).get("browsing"):
        warnings.append({"field": "permissions.browsing", "reason": "open_web_allowed_without_browsing_permission"})
    if "structured_api" in allowed and not brief.get("permissions", {}).get("api"):
        warnings.append({"field": "permissions.api", "reason": "structured_api_allowed_without_api_permission"})
    if "private_data" in allowed and brief.get("private_data_policy") == "none":
        warnings.append({"field": "private_data_policy", "reason": "private_data_allowed_without_policy"})

    if status == "ready" and blockers:
        warnings.append({"field": "status", "reason": "status_ready_but_planning_blockers_present"})
    return {"errors": errors, "warnings": warnings, "blockers": blockers}


def brief_summary(brief: dict[str, Any], brief_path: Path | None = None) -> dict[str, Any]:
    permissions = brief.get("permissions") if isinstance(brief.get("permissions"), dict) else {}
    budget = brief.get("budget") if isinstance(brief.get("budget"), dict) else {}
    summary = {
        "brief_id": brief.get("brief_id"),
        "brief_path": str(brief_path) if brief_path is not None else brief.get("brief_path"),
        "user_question": brief.get("user_question"),
        "clarified_objective": brief.get("clarified_objective"),
        "intended_output_maturity": brief.get("intended_output_maturity"),
        "target_audience": brief.get("target_audience"),
        "target_venue": brief.get("target_venue"),
        "allowed_source_classes": list_text(brief.get("allowed_source_classes")),
        "forbidden_source_classes": list_text(brief.get("forbidden_source_classes")),
        "private_data_policy": brief.get("private_data_policy"),
        "public_claims_policy": brief.get("public_claims_policy"),
        "permissions": {
            "browsing": bool(permissions.get("browsing")),
            "api": bool(permissions.get("api")),
            "code_execution": bool(permissions.get("code_execution")),
            "network": bool(permissions.get("network")),
            "credentials": bool(permissions.get("credentials")),
            "paid_services": bool(permissions.get("paid_services")),
        },
        "budget": {
            "max_api_usd": budget.get("max_api_usd"),
            "max_compute_usd": budget.get("max_compute_usd"),
            "max_human_minutes": budget.get("max_human_minutes"),
            "max_runtime_minutes": budget.get("max_runtime_minutes"),
        },
    }
    return summary


def validate_brief_payload(brief: Any, brief_path: Path | None = None) -> dict[str, Any]:
    try:
        schema = load_json(schema_path("research_brief.schema.json"))
    except ValueError as exc:
        return {
            "ok": False,
            "ready_for_planning": False,
            "reason": "schema_unavailable",
            "errors": [{"field": "schema", "reason": str(exc)}],
            "warnings": [],
            "blockers": [],
        }
    if not isinstance(brief, dict):
        return {
            "ok": False,
            "ready_for_planning": False,
            "reason": "brief_must_be_json_object",
            "errors": [{"field": "$", "reason": "expected_json_object"}],
            "warnings": [],
            "blockers": [],
        }
    schema_errors = [error.to_dict() for error in validate(brief, schema)]
    findings = semantic_findings(brief) if not schema_errors else {"errors": [], "warnings": [], "blockers": []}
    errors = schema_errors + findings["errors"]
    blockers = findings["blockers"]
    ready = not errors and not blockers
    return {
        "ok": ready,
        "ready_for_planning": ready,
        "reason": "ready_for_planning" if ready else "brief_not_ready_for_planning",
        "brief_path": str(brief_path) if brief_path is not None else None,
        "summary": brief_summary(brief, brief_path),
        "errors": errors,
        "warnings": findings["warnings"],
        "blockers": blockers,
        "human_gates": brief.get("human_gates", []),
    }


def load_brief(path: Path) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    try:
        payload = load_json(path)
    except ValueError as exc:
        return None, {
            "ok": False,
            "reason": "brief_malformed_or_missing",
            "brief_path": str(path),
            "message": str(exc),
        }
    if not isinstance(payload, dict):
        return None, {
            "ok": False,
            "reason": "brief_must_be_json_object",
            "brief_path": str(path),
        }
    return payload, None


def load_ready_brief_for_ops(ops_dir: Path, brief_path: Path | None = None) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    resolved, path_error = resolve_existing_brief_path(ops_dir, brief_path)
    if path_error is not None:
        return None, path_error
    if resolved is None:
        return None, None
    brief, load_error = load_brief(resolved)
    if load_error is not None or brief is None:
        return None, load_error
    validation = validate_brief_payload(brief, resolved)
    if not validation["ready_for_planning"]:
        return None, {
            "ok": False,
            "reason": "research_brief_not_ready",
            "brief_path": str(resolved),
            "validation": validation,
        }
    return {"path": resolved, "brief": brief, "summary": validation["summary"], "validation": validation}, None


def source_classes_from_args(args: argparse.Namespace) -> tuple[list[str], list[str]]:
    allowed = set(args.allowed_source_class or ["workspace_files", "accepted_memory", "knowledge_library"])
    if args.allow_browsing:
        allowed.add("open_web")
    if args.allow_api:
        allowed.add("structured_api")
    if args.allow_code_execution:
        allowed.add("code_execution")
    if args.private_data_policy in {"workspace_only", "requires_human_gate"}:
        allowed.add("private_data")
    if args.requires_credentials:
        allowed.add("external_credentials")
    if args.allow_paid:
        allowed.add("paid_services")

    forbidden = set(args.forbidden_source_class or [])
    for item, enabled in {
        "open_web": args.allow_browsing,
        "structured_api": args.allow_api,
        "code_execution": args.allow_code_execution,
        "external_credentials": args.requires_credentials,
        "paid_services": args.allow_paid,
    }.items():
        if not enabled and item not in allowed:
            forbidden.add(item)
    return sorted(allowed), sorted(forbidden)


def read_source_question(ops_dir: Path) -> str | None:
    for relative in (Path("briefs") / "source_request.md", Path("briefs") / "source_request.txt"):
        path = ops_dir / relative
        if path.exists():
            text = path.read_text(encoding="utf-8").strip()
            if text:
                return text
    return None


def draft_brief_payload(args: argparse.Namespace) -> dict[str, Any]:
    now_text = args.now or iso_timestamp()
    question = normalize_text(args.question) or read_source_question(args.ops_dir) or "TODO: replace with the research question to clarify."
    objective = normalize_text(args.objective) or (
        f"Answer the bounded research question: {question}" if not question.startswith("TODO") else "TODO: clarify the executable research objective."
    )
    output_maturity = args.output_maturity or "unspecified"
    target_audience = normalize_text(args.audience) or "unspecified"
    target_venue = normalize_text(args.venue) or None
    allowed, forbidden = source_classes_from_args(args)
    permissions = {
        "browsing": bool(args.allow_browsing),
        "api": bool(args.allow_api),
        "code_execution": bool(args.allow_code_execution),
        "network": bool(args.allow_network or args.allow_browsing or args.allow_api),
        "credentials": bool(args.requires_credentials),
        "paid_services": bool(args.allow_paid),
    }
    unresolved = list(args.unresolved_question or [])
    if question.startswith("TODO"):
        unresolved.append("What is the user's research question?")
    if output_maturity == "unspecified":
        unresolved.append("What output maturity is required: internal note, internal draft, shareable memo, working paper, or submission-ready artifact?")
    if target_audience == "unspecified":
        unresolved.append("Who is the target audience or decision owner?")
    if not allowed:
        unresolved.append("Which source classes are allowed for this brief?")
    public_claims_policy = args.public_claims_policy or "none"
    brief = {
        "schema_version": SCHEMA_VERSION,
        "brief_id": args.brief_id or f"BRIEF-{filename_timestamp()}",
        "status": "ready",
        "user_question": question,
        "clarified_objective": objective,
        "intended_output_maturity": output_maturity,
        "target_audience": target_audience,
        "target_venue": target_venue,
        "allowed_source_classes": allowed,
        "forbidden_source_classes": forbidden,
        "private_data_policy": args.private_data_policy,
        "public_claims_policy": public_claims_policy,
        "permissions": permissions,
        "budget": {
            "max_api_usd": args.max_api_usd,
            "max_compute_usd": args.max_compute_usd,
            "max_human_minutes": args.max_human_minutes,
            "max_runtime_minutes": args.max_runtime_minutes,
        },
        "known_assumptions": args.assumption or [],
        "unresolved_questions": unresolved,
        "human_gates": [],
        "created_at": now_text,
        "updated_at": now_text,
    }
    gates = expected_human_gates(brief)
    brief["human_gates"] = gates
    if args.private_data_policy == "blocked":
        brief["status"] = "blocked"
    elif gates:
        brief["status"] = "needs_human_gate"
    elif unresolved:
        brief["status"] = "needs_clarification"
    return brief


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def brief_task_title(brief: dict[str, Any]) -> str:
    objective = normalize_text(brief.get("clarified_objective")) or normalize_text(brief.get("user_question")) or "Research brief task"
    title = objective
    if title.lower().startswith("answer the bounded research question:"):
        title = title.split(":", 1)[1].strip()
    return title[:90].rstrip(" .") or "Research brief task"


def build_apply_plan(ops_dir: Path, brief_path: Path, brief: dict[str, Any], task_type: str) -> dict[str, Any]:
    summary = brief_summary(brief, brief_path)
    objective = normalize_text(brief.get("clarified_objective"))
    title = brief_task_title(brief)
    command = [
        "async-research",
        "workflow",
        "create-task",
        str(ops_dir),
        "--title",
        title,
        "--task-type",
        task_type,
        "--objective",
        objective,
        "--brief",
        str(brief_path),
        "--dry-run",
    ]
    permissions = summary["permissions"]
    return {
        "task_type": task_type,
        "title": title,
        "objective": objective,
        "research_brief": summary,
        "command": " ".join(shlex.quote(part) for part in command),
        "status_overrides": {
            "research_brief_ref": str(brief_path),
            "intended_output_maturity": summary["intended_output_maturity"],
            "target_audience": summary["target_audience"],
            "allow_browsing": permissions["browsing"],
            "allow_network": permissions["network"],
            "allow_code_execution": permissions["code_execution"],
            "budget": summary["budget"],
        },
        "next_step": "inspect the dry-run task proposal before using --write; do not start worker execution until the brief remains valid",
    }


def command_draft(args: argparse.Namespace) -> int:
    if args.write and args.dry_run:
        print_json(
            {
                "ok": False,
                "action": "research_brief_draft_refused",
                "reason": "conflicting_flags",
                "message": "use either --dry-run or --write, not both",
            }
        )
        return INVALID_REQUEST
    if not args.ops_dir.exists() or not args.ops_dir.is_dir():
        print_json({"ok": False, "action": "research_brief_draft_failed", "reason": "ops_dir_missing", "ops_dir": str(args.ops_dir)})
        return MALFORMED
    output, output_error = resolve_output_path(args.ops_dir, args.output)
    if output_error is not None:
        print_json({"action": "research_brief_draft_failed", **output_error})
        return INVALID_REQUEST
    if args.write and output.exists() and not args.force:
        print_json(
            {
                "ok": False,
                "action": "research_brief_draft_refused",
                "reason": "brief_output_exists",
                "output": str(output),
                "next_step": "rerun with --force only after confirming replacement is intended",
            }
        )
        return INVALID_REQUEST
    brief = draft_brief_payload(args)
    validation = validate_brief_payload(brief, output)
    if args.write:
        atomic_write_json(output, brief)
    print_json(
        {
            "ok": True,
            "action": "research_brief_drafted",
            "dry_run": not args.write,
            "read_only": not args.write,
            "written": bool(args.write),
            "output": str(output),
            "brief": brief,
            "validation": validation,
            "ready_for_planning": validation["ready_for_planning"],
            "next_step": (
                f"run async-research brief apply {args.ops_dir} {output} --dry-run"
                if validation["ready_for_planning"]
                else "resolve validation.blockers before applying this brief to planning"
            ),
        }
    )
    return SUCCESS


def command_validate(args: argparse.Namespace) -> int:
    brief, load_error = load_brief(args.brief_path)
    if load_error is not None or brief is None:
        print_json({"action": "research_brief_validation_failed", **(load_error or {})})
        return MALFORMED
    validation = validate_brief_payload(brief, args.brief_path)
    print_json({"action": "research_brief_validated", "read_only": True, "changed": False, **validation})
    return SUCCESS if validation["ready_for_planning"] else VALIDATION_FAILED


def command_apply(args: argparse.Namespace) -> int:
    if not args.dry_run:
        print_json(
            {
                "ok": False,
                "action": "research_brief_apply_refused",
                "reason": "apply_is_dry_run_only",
                "message": "Phase 2 apply previews task planning only; use workflow create-task --brief after inspecting the plan.",
            }
        )
        return INVALID_REQUEST
    if not args.ops_dir.exists() or not args.ops_dir.is_dir():
        print_json({"ok": False, "action": "research_brief_apply_failed", "reason": "ops_dir_missing", "ops_dir": str(args.ops_dir)})
        return MALFORMED
    resolved, path_error = resolve_existing_brief_path(args.ops_dir, args.brief_path)
    if path_error is not None or resolved is None:
        print_json({"action": "research_brief_apply_failed", **(path_error or {})})
        return INVALID_REQUEST
    brief, load_error = load_brief(resolved)
    if load_error is not None or brief is None:
        print_json({"action": "research_brief_apply_failed", **(load_error or {})})
        return MALFORMED
    validation = validate_brief_payload(brief, resolved)
    if not validation["ready_for_planning"]:
        print_json(
            {
                "ok": False,
                "action": "research_brief_apply_blocked",
                "dry_run": True,
                "read_only": True,
                "changed": False,
                "ops_dir": str(args.ops_dir),
                "brief_path": str(resolved),
                "validation": validation,
                "next_step": "answer unresolved questions or record required human gates before planning starts",
            }
        )
        return VALIDATION_FAILED
    plan = build_apply_plan(args.ops_dir, resolved, brief, args.task_type)
    print_json(
        {
            "ok": True,
            "action": "research_brief_apply_planned",
            "dry_run": True,
            "read_only": True,
            "changed": False,
            "ops_dir": str(args.ops_dir),
            "brief_path": str(resolved),
            "validation": validation,
            "plan": plan,
        }
    )
    return SUCCESS


def add_draft_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("ops_dir", nargs="?", type=Path, default=Path("research_ops"), help="research_ops workspace directory.")
    parser.add_argument("--question", help="Raw user question or request to clarify.")
    parser.add_argument("--objective", help="Clarified executable objective.")
    parser.add_argument("--output-maturity", choices=OUTPUT_MATURITIES, help="Intended output maturity.")
    parser.add_argument("--audience", help="Target audience or decision owner.")
    parser.add_argument("--venue", help="Known target venue or channel.")
    parser.add_argument("--allowed-source-class", action="append", choices=SOURCE_CLASSES, help="Allowed source class. Repeat as needed.")
    parser.add_argument("--forbidden-source-class", action="append", choices=SOURCE_CLASSES, help="Forbidden source class. Repeat as needed.")
    parser.add_argument("--private-data-policy", choices=PRIVATE_DATA_POLICIES, default="none")
    parser.add_argument("--public-claims-policy", choices=PUBLIC_CLAIM_POLICIES, default="none")
    parser.add_argument("--allow-browsing", action="store_true")
    parser.add_argument("--allow-api", action="store_true")
    parser.add_argument("--allow-code-execution", action="store_true")
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--requires-credentials", action="store_true")
    parser.add_argument("--allow-paid", action="store_true")
    parser.add_argument("--max-api-usd", type=float, default=0.0)
    parser.add_argument("--max-compute-usd", type=float, default=0.0)
    parser.add_argument("--max-human-minutes", type=int, default=30)
    parser.add_argument("--max-runtime-minutes", type=int, default=45)
    parser.add_argument("--assumption", action="append", default=[], help="Known assumption. Repeat as needed.")
    parser.add_argument("--unresolved-question", action="append", default=[], help="Clarifying question that must be answered before planning.")
    parser.add_argument("--brief-id", help="Explicit BRIEF-* id.")
    parser.add_argument("--output", type=Path, help="Output path inside research_ops; defaults to research_ops/briefs/research_brief.json.")
    parser.add_argument("--now", help="Timestamp override.")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing; this is the default.")
    parser.add_argument("--write", action="store_true", help="Write the drafted brief JSON.")
    parser.add_argument("--force", action="store_true", help="Replace an existing output brief when writing.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Draft, validate, and dry-run apply research brief contracts.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    draft = subparsers.add_parser(
        "draft",
        help="Draft a bounded research_brief.json contract.",
        description="Draft a research brief from explicit flags or research_ops/briefs/source_request.md; unresolved questions stay blocking.",
    )
    add_draft_arguments(draft)
    draft.set_defaults(func=command_draft)

    validate_cmd = subparsers.add_parser(
        "validate",
        help="Validate a research brief before planning.",
        description="Validate schema, output target, audience, source policy, permissions, budget caps, unresolved questions, and human gates.",
    )
    validate_cmd.add_argument("brief_path", type=Path, help="Path to research_brief.json.")
    validate_cmd.set_defaults(func=command_validate)

    apply_cmd = subparsers.add_parser(
        "apply",
        help="Dry-run a validated brief into a task planning command.",
        description="Preview task creation from a validated brief that is ready for planning; Phase 2 apply does not mutate research_ops.",
    )
    apply_cmd.add_argument("ops_dir", type=Path, help="research_ops workspace directory.")
    apply_cmd.add_argument("brief_path", type=Path, help="Path to a brief inside research_ops.")
    apply_cmd.add_argument("--task-type", choices=("literature_extract", "data_readiness", "hypothesis_card", "experiment_plan", "admin"), default="literature_extract")
    apply_cmd.add_argument("--dry-run", action="store_true", help="Required; preview without writing.")
    apply_cmd.set_defaults(func=command_apply)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(sys.argv[1:] if argv is None else argv))
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
