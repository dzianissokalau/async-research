#!/usr/bin/env python3
"""Manage first-class async research batch job lifecycle manifests."""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import sys
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from validate_json_artifact import load_json, validate
from async_research_workflow.resources import schema_path


SUCCESS = 0
INVALID_REQUEST = 2
MALFORMED = 4

SCHEMA_VERSION = "1.0"
MANIFEST_NAME = "batch_manifest.json"
MANIFEST_SCHEMA = schema_path("batch_manifest.schema.json")
LEDGER_HEADER = [
    "date",
    "item_id",
    "role",
    "model_or_tool",
    "usage_source",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "input_usd",
    "output_usd",
    "api_usd",
    "compute_usd",
    "amount_usd",
    "human_minutes",
    "status",
    "actual",
    "monthly_budget_usd",
    "weekly_budget_usd",
    "notes",
]

TRUSTED_STATUS = "reviewed"
UNTRUSTED_STATUS = "untrusted"
INGESTED_PENDING_REVIEW = "ingested_pending_review"


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"manifest not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"manifest JSON malformed: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"manifest is not an object: {path}")
    return payload


def manifest_path_for(ops_dir: Path, batch_id: str) -> Path:
    return ops_dir / "batches" / batch_id / MANIFEST_NAME


def infer_ops_dir(manifest_path: Path) -> Optional[Path]:
    if manifest_path.name != MANIFEST_NAME:
        return None
    batch_dir = manifest_path.parent
    if batch_dir.parent.name != "batches":
        return None
    return batch_dir.parent.parent


def non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def non_empty_list(value: Any) -> bool:
    return isinstance(value, list) and bool(value)


def lifecycle_errors(payload: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    status = payload.get("lifecycle_status")
    trust = payload.get("output_trust")

    if status in {"draft", "validated"} and trust != UNTRUSTED_STATUS:
        errors.append({"path": "$.output_trust", "message": "draft or validated batch outputs must stay untrusted"})

    if status in {"submitted", "completed", "ingested", "reviewed"}:
        if not non_empty_string(payload.get("provider_batch_id")):
            errors.append({"path": "$.provider_batch_id", "message": "provider_batch_id is required after submission"})
        if not non_empty_string(payload.get("submitted_at")):
            errors.append({"path": "$.submitted_at", "message": "submitted_at is required after submission"})

    if status == "submitted":
        if trust != UNTRUSTED_STATUS:
            errors.append({"path": "$.output_trust", "message": "submitted batch outputs must stay untrusted"})
        costs = payload.get("costs")
        if not isinstance(costs, dict) or costs.get("logged") is not True:
            errors.append({"path": "$.costs.logged", "message": "batch submission cost must be logged"})

    if status == "completed":
        if trust != UNTRUSTED_STATUS:
            errors.append({"path": "$.output_trust", "message": "completed batch outputs must stay untrusted until ingest and review"})
        if not non_empty_string(payload.get("completed_at")):
            errors.append({"path": "$.completed_at", "message": "completed_at is required for completed batches"})
        if not non_empty_list(payload.get("output_files")):
            errors.append({"path": "$.output_files", "message": "output_files is required for completed batches"})

    if status == "ingested":
        if trust != INGESTED_PENDING_REVIEW:
            errors.append({"path": "$.output_trust", "message": "ingested batch outputs must stay pending review"})
        if not non_empty_string(payload.get("ingest_task_id")):
            errors.append({"path": "$.ingest_task_id", "message": "ingest_task_id is required after ingest"})
        if not non_empty_string(payload.get("ingested_at")):
            errors.append({"path": "$.ingested_at", "message": "ingested_at is required after ingest"})
        if not non_empty_list(payload.get("ingested_files")):
            errors.append({"path": "$.ingested_files", "message": "ingested_files is required after ingest"})

    if status == "reviewed":
        if trust != TRUSTED_STATUS:
            errors.append({"path": "$.output_trust", "message": "reviewed batches must set output_trust to reviewed"})
        if not non_empty_string(payload.get("review_task_id")):
            errors.append({"path": "$.review_task_id", "message": "review_task_id is required after review"})
        if not non_empty_string(payload.get("reviewed_at")):
            errors.append({"path": "$.reviewed_at", "message": "reviewed_at is required after review"})
        if not non_empty_string(payload.get("ingest_task_id")):
            errors.append({"path": "$.ingest_task_id", "message": "reviewed batches must have an ingest task"})
        if not non_empty_list(payload.get("ingested_files")):
            errors.append({"path": "$.ingested_files", "message": "reviewed batches must have ingested files"})

    if trust == TRUSTED_STATUS and status != "reviewed":
        errors.append({"path": "$.output_trust", "message": "batch outputs are trusted only after reviewed lifecycle status"})

    return errors


def validate_manifest_payload(payload: dict[str, Any]) -> tuple[int, list[dict[str, str]]]:
    schema = load_json(MANIFEST_SCHEMA)
    if not isinstance(schema, dict):
        return MALFORMED, [{"path": "$", "message": f"schema is not an object: {MANIFEST_SCHEMA}"}]
    errors = [error.to_dict() for error in validate(payload, schema)]
    errors.extend(lifecycle_errors(payload))
    if errors:
        return INVALID_REQUEST, errors
    return SUCCESS, []


def validate_manifest_file(path: Path) -> tuple[int, dict[str, Any], list[dict[str, str]]]:
    try:
        payload = load_json_object(path)
    except ValueError as exc:
        return MALFORMED, {}, [{"path": str(path), "message": str(exc)}]
    code, errors = validate_manifest_payload(payload)
    return code, payload, errors


def append_cost_row(ledger_path: Path, row: dict[str, Any]) -> None:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    needs_header = not ledger_path.exists() or ledger_path.stat().st_size == 0
    fieldnames = LEDGER_HEADER
    existing_rows: list[dict[str, str]] = []
    if not needs_header:
        with ledger_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames:
                fieldnames = list(reader.fieldnames)
            existing_rows = [{str(key): str(value) for key, value in item.items() if key is not None} for item in reader]
        for field in LEDGER_HEADER:
            if field not in fieldnames:
                fieldnames.append(field)
    if not any(field in fieldnames for field in ("amount_usd", "cost_usd", "usd", "total_usd", "api_usd", "compute_usd")):
        raise ValueError(f"cost ledger lacks a recognized amount column: {ledger_path}")

    tmp = ledger_path.with_name(f".{ledger_path.name}.{os.getpid()}.tmp")
    with tmp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for existing in existing_rows:
            writer.writerow({field: existing.get(field, "") for field in fieldnames})
        writer.writerow({field: row.get(field, "") for field in fieldnames})
    os.replace(tmp, ledger_path)


def cost_row(payload: dict[str, Any], api_usd: float, compute_usd: float, status: str, now: str) -> dict[str, Any]:
    total = round(api_usd + compute_usd, 6)
    return {
        "date": now,
        "item_id": payload.get("batch_id"),
        "role": "batch_job",
        "model_or_tool": payload.get("model"),
        "usage_source": "batch_lifecycle_submit_estimate",
        "input_tokens": "",
        "output_tokens": "",
        "total_tokens": "",
        "input_usd": "",
        "output_usd": "",
        "api_usd": api_usd,
        "compute_usd": compute_usd,
        "amount_usd": total,
        "human_minutes": 0,
        "status": status,
        "actual": "false",
        "monthly_budget_usd": "",
        "weekly_budget_usd": "",
        "notes": f"provider_batch_id={payload.get('provider_batch_id') or 'pending'}",
    }


def update_and_validate(path: Path, payload: dict[str, Any], dry_run: bool) -> tuple[int, list[dict[str, str]]]:
    code, errors = validate_manifest_payload(payload)
    if code != SUCCESS:
        return code, errors
    if not dry_run:
        atomic_write_json(path, payload)
    return SUCCESS, []


def run_init(args: argparse.Namespace) -> int:
    now = iso_now()
    manifest_path = args.manifest or manifest_path_for(args.ops_dir, args.batch_id)
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "batch_id": args.batch_id,
        "provider_batch_id": None,
        "source_task_id": args.source_task_id,
        "ingest_task_id": None,
        "review_task_id": None,
        "lifecycle_status": "draft",
        "input_files": args.input_file,
        "output_files": [],
        "ingested_files": [],
        "prompt_template": args.prompt_template,
        "model": args.model,
        "expected_output_schema": args.expected_output_schema,
        "ingest_path": args.ingest_path,
        "output_trust": UNTRUSTED_STATUS,
        "costs": {
            "estimated_api_usd": args.estimated_api_usd,
            "estimated_compute_usd": args.estimated_compute_usd,
            "logged": False,
            "ledger_path": None,
            "logged_at": None,
        },
        "created_at": now,
        "updated_at": now,
        "submitted_at": None,
        "completed_at": None,
        "ingested_at": None,
        "reviewed_at": None,
    }
    code, errors = validate_manifest_payload(payload)
    if code != SUCCESS:
        print_json({"ok": False, "reason": "manifest_invalid", "errors": errors, "manifest": str(manifest_path)})
        return code
    if not args.dry_run:
        atomic_write_json(manifest_path, payload)
    print_json({"ok": True, "action": "dry_run_initialized" if args.dry_run else "initialized", "manifest": str(manifest_path)})
    return SUCCESS


def run_validate(args: argparse.Namespace) -> int:
    code, payload, errors = validate_manifest_file(args.manifest)
    if code != SUCCESS:
        print_json({"ok": False, "reason": "manifest_invalid", "errors": errors, "manifest": str(args.manifest)})
        return code
    print_json({"ok": True, "batch_id": payload.get("batch_id"), "lifecycle_status": payload.get("lifecycle_status"), "manifest": str(args.manifest)})
    return SUCCESS


def run_submit(args: argparse.Namespace) -> int:
    code, payload, errors = validate_manifest_file(args.manifest)
    if code != SUCCESS:
        print_json({"ok": False, "reason": "manifest_invalid_before_submission", "errors": errors, "manifest": str(args.manifest)})
        return code
    if payload.get("lifecycle_status") not in {"draft", "validated"}:
        print_json({"ok": False, "reason": "invalid_lifecycle_for_submission", "lifecycle_status": payload.get("lifecycle_status")})
        return INVALID_REQUEST

    ops_dir = args.ops_dir or infer_ops_dir(args.manifest)
    if ops_dir is None:
        print_json({"ok": False, "reason": "ops_dir_required", "manifest": str(args.manifest)})
        return INVALID_REQUEST

    now = iso_now()
    updated = dict(payload)
    updated["provider_batch_id"] = args.provider_batch_id
    updated["lifecycle_status"] = "submitted"
    updated["output_trust"] = UNTRUSTED_STATUS
    updated["submitted_at"] = now
    updated["updated_at"] = now
    costs = dict(updated.get("costs") or {})
    costs["estimated_api_usd"] = args.api_usd
    costs["estimated_compute_usd"] = args.compute_usd
    costs["logged"] = True
    costs["ledger_path"] = str(ops_dir / "cost_ledger.csv")
    costs["logged_at"] = now
    updated["costs"] = costs

    code, errors = update_and_validate(args.manifest, updated, dry_run=True)
    if code != SUCCESS:
        print_json({"ok": False, "reason": "submitted_manifest_invalid", "errors": errors, "manifest": str(args.manifest)})
        return code

    if not args.dry_run:
        ledger_path = ops_dir / "cost_ledger.csv"
        try:
            append_cost_row(ledger_path, cost_row(updated, args.api_usd, args.compute_usd, "submitted", now))
        except ValueError as exc:
            print_json({"ok": False, "reason": "cost_ledger_invalid", "error": str(exc), "ledger": str(ledger_path)})
            return INVALID_REQUEST
        atomic_write_json(args.manifest, updated)

    print_json(
        {
            "ok": True,
            "action": "dry_run_submitted" if args.dry_run else "submitted",
            "batch_id": updated.get("batch_id"),
            "provider_batch_id": args.provider_batch_id,
            "manifest": str(args.manifest),
            "cost_logged": True,
            "output_trust": updated["output_trust"],
        }
    )
    return SUCCESS


def run_complete(args: argparse.Namespace) -> int:
    code, payload, errors = validate_manifest_file(args.manifest)
    if code != SUCCESS:
        print_json({"ok": False, "reason": "manifest_invalid", "errors": errors, "manifest": str(args.manifest)})
        return code
    if payload.get("lifecycle_status") != "submitted":
        print_json({"ok": False, "reason": "invalid_lifecycle_for_completion", "lifecycle_status": payload.get("lifecycle_status")})
        return INVALID_REQUEST

    updated = dict(payload)
    updated["lifecycle_status"] = "completed"
    updated["output_trust"] = UNTRUSTED_STATUS
    updated["output_files"] = args.output_file
    updated["completed_at"] = iso_now()
    updated["updated_at"] = updated["completed_at"]
    code, errors = update_and_validate(args.manifest, updated, args.dry_run)
    if code != SUCCESS:
        print_json({"ok": False, "reason": "completed_manifest_invalid", "errors": errors, "manifest": str(args.manifest)})
        return code
    print_json({"ok": True, "action": "dry_run_completed" if args.dry_run else "completed", "output_trust": updated["output_trust"], "manifest": str(args.manifest)})
    return SUCCESS


def run_ingest(args: argparse.Namespace) -> int:
    code, payload, errors = validate_manifest_file(args.manifest)
    if code != SUCCESS:
        print_json({"ok": False, "reason": "manifest_invalid", "errors": errors, "manifest": str(args.manifest)})
        return code
    if payload.get("lifecycle_status") != "completed":
        print_json({"ok": False, "reason": "invalid_lifecycle_for_ingest", "lifecycle_status": payload.get("lifecycle_status")})
        return INVALID_REQUEST

    updated = dict(payload)
    updated["lifecycle_status"] = "ingested"
    updated["output_trust"] = INGESTED_PENDING_REVIEW
    updated["ingest_task_id"] = args.ingest_task_id
    updated["ingested_files"] = args.ingested_file
    updated["ingested_at"] = iso_now()
    updated["updated_at"] = updated["ingested_at"]
    code, errors = update_and_validate(args.manifest, updated, args.dry_run)
    if code != SUCCESS:
        print_json({"ok": False, "reason": "ingested_manifest_invalid", "errors": errors, "manifest": str(args.manifest)})
        return code
    print_json({"ok": True, "action": "dry_run_ingested" if args.dry_run else "ingested", "output_trust": updated["output_trust"], "manifest": str(args.manifest)})
    return SUCCESS


def run_mark_reviewed(args: argparse.Namespace) -> int:
    code, payload, errors = validate_manifest_file(args.manifest)
    if code != SUCCESS:
        print_json({"ok": False, "reason": "manifest_invalid", "errors": errors, "manifest": str(args.manifest)})
        return code
    if payload.get("lifecycle_status") != "ingested":
        print_json({"ok": False, "reason": "invalid_lifecycle_for_review", "lifecycle_status": payload.get("lifecycle_status")})
        return INVALID_REQUEST

    updated = dict(payload)
    updated["lifecycle_status"] = "reviewed"
    updated["output_trust"] = TRUSTED_STATUS
    updated["review_task_id"] = args.review_task_id
    updated["reviewed_at"] = iso_now()
    updated["updated_at"] = updated["reviewed_at"]
    code, errors = update_and_validate(args.manifest, updated, args.dry_run)
    if code != SUCCESS:
        print_json({"ok": False, "reason": "reviewed_manifest_invalid", "errors": errors, "manifest": str(args.manifest)})
        return code
    print_json({"ok": True, "action": "dry_run_reviewed" if args.dry_run else "reviewed", "output_trust": updated["output_trust"], "manifest": str(args.manifest)})
    return SUCCESS


def run_trust_status(args: argparse.Namespace) -> int:
    code, payload, errors = validate_manifest_file(args.manifest)
    if code != SUCCESS:
        print_json({"ok": False, "reason": "manifest_invalid", "errors": errors, "manifest": str(args.manifest), "trusted": False})
        return code
    trusted = payload.get("lifecycle_status") == "reviewed" and payload.get("output_trust") == TRUSTED_STATUS
    print_json(
        {
            "ok": True,
            "batch_id": payload.get("batch_id"),
            "lifecycle_status": payload.get("lifecycle_status"),
            "output_trust": payload.get("output_trust"),
            "trusted": trusted,
        }
    )
    return SUCCESS if trusted or args.allow_untrusted else INVALID_REQUEST


def add_common_write_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dry-run", action="store_true")


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage batch_manifest.json lifecycle.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="Create a draft batch manifest.")
    init.add_argument("ops_dir", type=Path)
    init.add_argument("--batch-id", required=True)
    init.add_argument("--input-file", action="append", required=True)
    init.add_argument("--prompt-template", required=True)
    init.add_argument("--model", required=True)
    init.add_argument("--expected-output-schema", required=True)
    init.add_argument("--ingest-path", required=True)
    init.add_argument("--source-task-id")
    init.add_argument("--estimated-api-usd", type=float, default=0.0)
    init.add_argument("--estimated-compute-usd", type=float, default=0.0)
    init.add_argument("--manifest", type=Path)
    add_common_write_args(init)

    validate_parser = subparsers.add_parser("validate-manifest", help="Validate manifest schema and lifecycle invariants.")
    validate_parser.add_argument("manifest", type=Path)

    submit = subparsers.add_parser("submit", help="Validate and mark a batch as submitted, logging estimated cost.")
    submit.add_argument("manifest", type=Path)
    submit.add_argument("--ops-dir", type=Path)
    submit.add_argument("--provider-batch-id", required=True)
    submit.add_argument("--api-usd", type=float, required=True)
    submit.add_argument("--compute-usd", type=float, required=True)
    add_common_write_args(submit)

    complete = subparsers.add_parser("complete", help="Record provider output files while keeping outputs untrusted.")
    complete.add_argument("manifest", type=Path)
    complete.add_argument("--output-file", action="append", required=True)
    add_common_write_args(complete)

    ingest = subparsers.add_parser("ingest", help="Record ingested output files while keeping outputs pending review.")
    ingest.add_argument("manifest", type=Path)
    ingest.add_argument("--ingest-task-id", required=True)
    ingest.add_argument("--ingested-file", action="append", required=True)
    add_common_write_args(ingest)

    reviewed = subparsers.add_parser("mark-reviewed", help="Mark ingested batch outputs as reviewed and trusted.")
    reviewed.add_argument("manifest", type=Path)
    reviewed.add_argument("--review-task-id", required=True)
    add_common_write_args(reviewed)

    trust = subparsers.add_parser("trust-status", help="Report whether batch outputs are trusted.")
    trust.add_argument("manifest", type=Path)
    trust.add_argument("--allow-untrusted", action="store_true")

    return parser.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    if args.command == "init":
        return run_init(args)
    if args.command == "validate-manifest":
        return run_validate(args)
    if args.command == "submit":
        return run_submit(args)
    if args.command == "complete":
        return run_complete(args)
    if args.command == "ingest":
        return run_ingest(args)
    if args.command == "mark-reviewed":
        return run_mark_reviewed(args)
    if args.command == "trust-status":
        return run_trust_status(args)
    print_json({"ok": False, "reason": "unknown_command", "command": args.command})
    return INVALID_REQUEST


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
