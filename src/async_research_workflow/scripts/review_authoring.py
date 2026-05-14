#!/usr/bin/env python3
"""Public review authoring helpers for role-specific review files."""

from __future__ import annotations

import argparse
import errno
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Iterable

from async_research_workflow.resources import schema_path
from async_research_workflow.scripts import review_template
from async_research_workflow.scripts.aggregate_reviews import (
    CLAIM_STRENGTHS,
    DECISIONS,
    REVIEWER_ROLES,
    validate_review,
)
from async_research_workflow.scripts.validate_json_artifact import load_json, validate


SUCCESS = 0
VALIDATION_FAILED = 2
MISSING_REQUIRED = 3
MALFORMED = 4
TARGET_EXISTS = 5
REVIEWABLE_STATUSES = {"awaiting_review", "single_review", "panel_review"}

DEFAULT_DRAFT_CONCERNS = [
    "Draft scaffold only; a reviewer must replace this before acceptance.",
]
DEFAULT_DRAFT_FOLLOWUPS = [
    "Complete the review or submit an explicit role-specific decision.",
]
DEFAULT_DRAFT_EVIDENCE_GAPS = [
    "No substantive review evidence has been recorded yet.",
]


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def fenced_json(payload: dict[str, Any]) -> str:
    return "```json\n" + json.dumps(payload, indent=2, sort_keys=True) + "\n```\n"


def review_path(task_dir: Path, role: str) -> Path:
    return task_dir / "reviews" / f"{role}.md"


def load_task_status(task_dir: Path) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    status_path = task_dir / "status.json"
    try:
        payload = json.loads(status_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, {"reason": "status_missing", "status_path": str(status_path)}
    except json.JSONDecodeError as exc:
        return None, {"reason": "status_malformed", "status_path": str(status_path), "error": str(exc)}
    if not isinstance(payload, dict):
        return None, {"reason": "status_not_object", "status_path": str(status_path)}
    schema = load_json(schema_path("task_status.schema.json"))
    if not isinstance(schema, dict):
        return None, {"reason": "status_schema_malformed", "status_path": str(status_path)}
    errors = validate(payload, schema)
    if errors:
        return None, {
            "reason": "status_schema_validation_failed",
            "status_path": str(status_path),
            "errors": [error.to_dict() for error in errors],
        }
    return payload, None


def load_valid_task_status(task_dir: Path) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if not task_dir.exists() or not task_dir.is_dir():
        return None, {"reason": "task_dir_missing", "task_dir": str(task_dir)}
    return load_task_status(task_dir)


def validate_task_dir(task_dir: Path) -> dict[str, Any] | None:
    _, error = load_valid_task_status(task_dir)
    return error


def review_readiness_error(task_dir: Path, status: dict[str, Any]) -> dict[str, Any] | None:
    current_status = status.get("status")
    worker_output = task_dir / "worker_output.md"
    next_step = "complete worker output and move the task to awaiting_review before submitting a review"
    if current_status not in REVIEWABLE_STATUSES:
        return {
            "reason": "task_not_reviewable",
            "task_dir": str(task_dir),
            "status": current_status,
            "allowed_statuses": sorted(REVIEWABLE_STATUSES),
            "worker_output_path": str(worker_output),
            "next_step": next_step,
        }
    if not worker_output.exists() or not worker_output.is_file():
        return {
            "reason": "worker_output_missing",
            "task_dir": str(task_dir),
            "status": current_status,
            "worker_output_path": str(worker_output),
            "next_step": next_step,
        }
    if not worker_output.read_text(encoding="utf-8").strip():
        return {
            "reason": "worker_output_empty",
            "task_dir": str(task_dir),
            "status": current_status,
            "worker_output_path": str(worker_output),
            "next_step": next_step,
        }
    return None


def split_repeated(values: list[str] | None) -> list[str]:
    items: list[str] = []
    for value in values or []:
        for part in value.split("\n"):
            stripped = part.strip()
            if stripped:
                items.append(stripped)
    return items


def validate_common_flags(role: str | None, decision: str | None, claim_strength: str | None, confidence_raw: str | None) -> tuple[list[str], float | None]:
    errors: list[str] = []
    confidence: float | None = None
    if role not in REVIEWER_ROLES:
        errors.append(f"role must be one of {sorted(REVIEWER_ROLES)}")
    if decision not in DECISIONS:
        errors.append(f"decision must be one of {sorted(DECISIONS)}")
    if claim_strength not in CLAIM_STRENGTHS:
        errors.append(f"claim_strength must be one of {sorted(CLAIM_STRENGTHS)}")
    if confidence_raw is None:
        errors.append("confidence is required")
    else:
        try:
            confidence = float(confidence_raw)
        except ValueError:
            errors.append("confidence must be a number between 0 and 1")
        else:
            if not 0 <= confidence <= 1:
                errors.append("confidence must be a number between 0 and 1")
    return errors, confidence


def review_payload(
    *,
    role: str,
    decision: str,
    claim_strength: str,
    confidence: float,
    concerns: list[str] | None = None,
    followups: list[str] | None = None,
    evidence_gaps: list[str] | None = None,
) -> dict[str, Any]:
    return review_template.review_payload(
        argparse.Namespace(
            role=role,
            decision=decision,
            claim_strength=claim_strength,
            confidence=confidence,
            concern=concerns or [],
            followup=followups or [],
            evidence_gap=evidence_gaps or [],
        )
    )


def validate_payload_for_role(path: Path, payload: dict[str, Any], role: str) -> list[str]:
    errors = validate_review(path, payload)
    payload_role = payload.get("reviewer_role")
    if payload_role != role:
        errors.append(f"{path}: reviewer_role {payload_role!r} does not match target role {role!r}")
    return errors


def write_review(path: Path, markdown: str, force: bool) -> tuple[bool, dict[str, Any] | None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=f".{os.getpid()}.tmp", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(markdown)
        if force:
            os.replace(tmp, path)
            return True, None
        try:
            os.link(tmp, path)
        except FileExistsError:
            return False, {
                "reason": "target_exists",
                "review_path": str(path),
                "next_step": "rerun with --force after confirming the existing review should be replaced",
            }
        except OSError as exc:
            if exc.errno not in {errno.EPERM, errno.EOPNOTSUPP, errno.ENOTSUP}:
                raise
            try:
                with path.open("x", encoding="utf-8") as target:
                    target.write(markdown)
            except FileExistsError:
                return False, {
                    "reason": "target_exists",
                    "review_path": str(path),
                    "next_step": "rerun with --force after confirming the existing review should be replaced",
                }
        return True, None
    finally:
        tmp.unlink(missing_ok=True)


def success_payload(
    *,
    action: str,
    task_dir: Path,
    path: Path,
    payload: dict[str, Any],
    written: bool,
    would_write: bool,
    include_markdown: bool,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ok": True,
        "action": action,
        "task_dir": str(task_dir),
        "review_path": str(path),
        "reviewer_role": payload["reviewer_role"],
        "decision": payload["decision"],
        "claim_strength": payload["claim_strength"],
        "confidence": payload["confidence"],
        "written": written,
        "would_write": would_write,
        "review": payload,
        "next_step": "run async-research review aggregate <task-dir> --dry-run when required reviews are present",
    }
    if include_markdown:
        result["review_markdown"] = fenced_json(payload)
    return result


def draft_review(args: argparse.Namespace) -> int:
    status, error = load_valid_task_status(args.task_dir)
    if error is not None:
        print_json({"ok": False, **error})
        return MALFORMED

    role = args.role
    if role not in REVIEWER_ROLES:
        print_json({"ok": False, "reason": "invalid_review_flags", "errors": [f"role must be one of {sorted(REVIEWER_ROLES)}"]})
        return MISSING_REQUIRED

    decision = args.decision or "needs_human"
    claim_strength = args.claim_strength or "none"
    confidence_raw = args.confidence if args.confidence is not None else "0"
    errors, confidence = validate_common_flags(role, decision, claim_strength, confidence_raw)
    if errors or confidence is None:
        print_json({"ok": False, "reason": "invalid_review_flags", "errors": errors})
        return MISSING_REQUIRED

    concerns = split_repeated(args.concern) or list(DEFAULT_DRAFT_CONCERNS)
    followups = split_repeated(args.followup) or list(DEFAULT_DRAFT_FOLLOWUPS)
    evidence_gaps = split_repeated(args.evidence_gap) or list(DEFAULT_DRAFT_EVIDENCE_GAPS)
    path = review_path(args.task_dir, role)
    payload = review_payload(
        role=role,
        decision=decision,
        claim_strength=claim_strength,
        confidence=confidence,
        concerns=concerns,
        followups=followups,
        evidence_gaps=evidence_gaps,
    )
    validation_errors = validate_payload_for_role(path, payload, role)
    if validation_errors:
        print_json({"ok": False, "reason": "review_validation_failed", "errors": validation_errors, "review_path": str(path)})
        return VALIDATION_FAILED

    markdown = fenced_json(payload)
    if args.write:
        readiness_error = review_readiness_error(args.task_dir, status or {})
        if readiness_error is not None:
            print_json({"ok": False, **readiness_error})
            return MALFORMED
        ok, write_error = write_review(path, markdown, args.force)
        if not ok:
            print_json({"ok": False, **(write_error or {})})
            return TARGET_EXISTS
        print_json(
            success_payload(
                action="review_draft_written",
                task_dir=args.task_dir,
                path=path,
                payload=payload,
                written=True,
                would_write=False,
                include_markdown=False,
            )
        )
        return SUCCESS

    print_json(
        success_payload(
            action="review_draft_previewed",
            task_dir=args.task_dir,
            path=path,
            payload=payload,
            written=False,
            would_write=True,
            include_markdown=True,
        )
    )
    return SUCCESS


def submit_review(args: argparse.Namespace) -> int:
    status, error = load_valid_task_status(args.task_dir)
    if error is not None:
        print_json({"ok": False, **error})
        return MALFORMED
    readiness_error = review_readiness_error(args.task_dir, status or {})
    if readiness_error is not None:
        print_json({"ok": False, **readiness_error})
        return MALFORMED

    missing = [
        flag
        for flag, value in (
            ("--role", args.role),
            ("--decision", args.decision),
            ("--claim-strength", args.claim_strength),
            ("--confidence", args.confidence),
        )
        if value is None
    ]
    if missing:
        print_json(
            {
                "ok": False,
                "reason": "missing_required_flags",
                "missing_flags": missing,
                "next_step": "provide --decision, --claim-strength, and --confidence explicitly",
            }
        )
        return MISSING_REQUIRED

    errors, confidence = validate_common_flags(args.role, args.decision, args.claim_strength, args.confidence)
    if errors or confidence is None:
        print_json({"ok": False, "reason": "invalid_review_flags", "errors": errors})
        return MISSING_REQUIRED

    role = args.role
    path = review_path(args.task_dir, role)
    payload = review_payload(
        role=role,
        decision=args.decision,
        claim_strength=args.claim_strength,
        confidence=confidence,
        concerns=split_repeated(args.concern),
        followups=split_repeated(args.followup),
        evidence_gaps=split_repeated(args.evidence_gap),
    )
    validation_errors = validate_payload_for_role(path, payload, role)
    if validation_errors:
        print_json({"ok": False, "reason": "review_validation_failed", "errors": validation_errors, "review_path": str(path)})
        return VALIDATION_FAILED

    markdown = fenced_json(payload)
    if args.dry_run:
        print_json(
            success_payload(
                action="review_submit_dry_run",
                task_dir=args.task_dir,
                path=path,
                payload=payload,
                written=False,
                would_write=True,
                include_markdown=True,
            )
        )
        return SUCCESS

    ok, write_error = write_review(path, markdown, args.force)
    if not ok:
        print_json({"ok": False, **(write_error or {})})
        return TARGET_EXISTS
    print_json(
        success_payload(
            action="review_submitted",
            task_dir=args.task_dir,
            path=path,
            payload=payload,
            written=True,
            would_write=False,
            include_markdown=False,
        )
    )
    return SUCCESS


def add_authoring_options(parser: argparse.ArgumentParser, *, submit: bool) -> None:
    parser.add_argument("task_dir", type=Path, help="Task directory containing status.json.")
    parser.add_argument("--role", help=f"Reviewer role: {', '.join(sorted(REVIEWER_ROLES))}.")
    parser.add_argument("--decision", help=f"Review decision: {', '.join(sorted(DECISIONS))}.")
    parser.add_argument("--claim-strength", help=f"Claim strength: {', '.join(sorted(CLAIM_STRENGTHS))}.")
    parser.add_argument("--confidence", help="Reviewer confidence as a number from 0 to 1.")
    parser.add_argument("--concern", action="append", help="Main concern. Repeat for multiple concerns.")
    parser.add_argument("--followup", action="append", help="Required follow-up. Repeat for multiple follow-ups.")
    parser.add_argument("--evidence-gap", action="append", help="Evidence gap. Repeat for multiple gaps.")
    parser.add_argument("--force", action="store_true", help="Replace an existing role-specific review file.")
    if submit:
        parser.add_argument("--dry-run", action="store_true", help="Validate and print the review without writing reviews/<role>.md.")
    else:
        parser.add_argument("--write", action="store_true", help="Write reviews/<role>.md instead of previewing the scaffold.")


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Draft or submit role-specific async-research reviews.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    draft = subparsers.add_parser("draft", help="Preview or write a conservative review scaffold.")
    add_authoring_options(draft, submit=False)
    submit = subparsers.add_parser("submit", help="Validate and write one explicit role-specific review.")
    add_authoring_options(submit, submit=True)
    return parser.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    if args.command == "draft":
        return draft_review(args)
    if args.command == "submit":
        return submit_review(args)
    print_json({"ok": False, "reason": "unknown_command", "command": args.command})
    return MALFORMED


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
