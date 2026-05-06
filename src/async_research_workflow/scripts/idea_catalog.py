#!/usr/bin/env python3
"""Initialize and maintain idea catalog workspace files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from async_research_workflow.idea_catalog import CATALOG_FILE
from async_research_workflow.idea_catalog import CATALOG_TEMPLATE
from async_research_workflow.idea_catalog import IDEAS_DIR
from async_research_workflow.idea_catalog import PRIORITIZATION_FILE
from async_research_workflow.idea_catalog import PRIORITIZATION_TEMPLATE


SUCCESS = 0
VALIDATION_FAILED = 2
INVALID_REQUEST = 3
MALFORMED = 4

STARTER_FILES = (
    (Path(IDEAS_DIR) / CATALOG_FILE, CATALOG_TEMPLATE),
    (Path(IDEAS_DIR) / PRIORITIZATION_FILE, PRIORITIZATION_TEMPLATE),
)


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def init_plan(ops_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    planned: list[dict[str, Any]] = []
    existing: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    ideas_dir = ops_dir / IDEAS_DIR

    if not ops_dir.exists():
        failures.append({
            "path": str(ops_dir),
            "reason": "ops_dir_missing",
            "message": "run async-research init first or choose an existing research_ops directory",
        })
        return planned, existing, failures
    if not ops_dir.is_dir():
        failures.append({
            "path": str(ops_dir),
            "reason": "ops_dir_not_directory",
            "message": "catalog initialization requires a research_ops directory",
        })
        return planned, existing, failures
    if ideas_dir.exists() and not ideas_dir.is_dir():
        failures.append({
            "path": str(ideas_dir),
            "reason": "ideas_path_not_directory",
            "message": "research_ops/ideas must be a directory",
        })
        return planned, existing, failures

    for relative_path, content in STARTER_FILES:
        path = ops_dir / relative_path
        entry = {
            "path": str(path),
            "relative_path": relative_path.as_posix(),
        }
        if path.exists():
            if path.is_dir():
                failures.append({
                    **entry,
                    "reason": "catalog_file_path_is_directory",
                    "message": "expected a catalog file but found a directory",
                })
            else:
                existing.append({**entry, "action": "preserve_existing"})
            continue
        planned.append({
            **entry,
            "action": "create",
            "bytes": len(content.encode("utf-8")),
        })

    return planned, existing, failures


def create_missing_files(ops_dir: Path, planned: list[dict[str, Any]]) -> list[dict[str, Any]]:
    added: list[dict[str, Any]] = []
    templates = {relative_path.as_posix(): content for relative_path, content in STARTER_FILES}
    for change in planned:
        relative = str(change["relative_path"])
        path = ops_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as handle:
            handle.write(templates[relative])
        added.append({**change, "action": "created"})
    return added


def run_init(args: argparse.Namespace) -> int:
    if args.write and args.dry_run:
        print_json({
            "ok": False,
            "reason": "conflicting_flags",
            "message": "use either --dry-run or --write, not both",
        })
        return INVALID_REQUEST

    dry_run = not args.write
    ops_dir = args.ops_dir
    planned, existing, failures = init_plan(ops_dir)
    ideas_dir = ops_dir / IDEAS_DIR
    lock_dir = ideas_dir / "LOCK"
    warnings: list[dict[str, Any]] = []

    if failures:
        print_json({
            "ok": False,
            "action": "idea_catalog_init_failed",
            "ops_dir": str(ops_dir),
            "planned_changes": planned,
            "existing_files": existing,
            "failures": failures,
        })
        return MALFORMED

    if args.write and lock_dir.exists():
        print_json({
            "ok": False,
            "action": "idea_catalog_init_refused",
            "reason": "catalog_locked",
            "ops_dir": str(ops_dir),
            "lock_dir": str(lock_dir),
            "planned_changes": planned,
            "existing_files": existing,
        })
        return VALIDATION_FAILED

    if dry_run:
        if lock_dir.exists():
            warnings.append({
                "reason": "catalog_locked",
                "message": "ideas/LOCK exists; --write will be refused until the lock is removed",
                "path": str(lock_dir),
            })
        print_json({
            "ok": True,
            "action": "idea_catalog_init_planned",
            "ops_dir": str(ops_dir),
            "catalog_dir": str(ideas_dir),
            "dry_run": True,
            "would_write": planned,
            "existing_files": existing,
            "warnings": warnings,
            "changed": bool(planned),
        })
        return SUCCESS

    try:
        added = create_missing_files(ops_dir, planned)
    except FileExistsError as exc:
        print_json({
            "ok": False,
            "action": "idea_catalog_init_refused",
            "reason": "catalog_file_created_concurrently",
            "error": str(exc),
            "ops_dir": str(ops_dir),
        })
        return VALIDATION_FAILED
    except OSError as exc:
        print_json({
            "ok": False,
            "action": "idea_catalog_init_failed",
            "reason": "write_failed",
            "error": str(exc),
            "ops_dir": str(ops_dir),
        })
        return MALFORMED

    print_json({
        "ok": True,
        "action": "idea_catalog_initialized",
        "ops_dir": str(ops_dir),
        "catalog_dir": str(ideas_dir),
        "files_added": added,
        "existing_files": existing,
        "changed": bool(added),
    })
    return SUCCESS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Initialize and maintain idea catalog workspace files.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser(
        "init",
        help="Add missing idea catalog starter files.",
        description="Preview or create missing research_ops/ideas starter files without overwriting existing files.",
    )
    init.add_argument("ops_dir", type=Path, help="Path to the research_ops workspace.")
    init.add_argument("--dry-run", action="store_true", help="Preview missing files without writing; this is the default.")
    init.add_argument("--write", action="store_true", help="Create only missing idea catalog files.")
    init.set_defaults(func=run_init)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
