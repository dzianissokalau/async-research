#!/usr/bin/env python3
"""Initialize knowledge library workspace files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile
from typing import Any


SUCCESS = 0
INVALID_REQUEST = 3
MALFORMED = 4

LIBRARY_DIR = "library"
SOURCE_LIBRARY_FILE = "source_library.md"
KNOWLEDGE_INDEX_FILE = "knowledge_index.md"
CLAIM_MAP_FILE = "claim_map.md"
METHOD_INDEX_FILE = "method_index.md"
OPEN_QUESTIONS_FILE = "open_questions.md"
UPDATE_LOG_FILE = "library_update_log.md"

SOURCE_LIBRARY_TEMPLATE = """# Source Library

<!-- LIBRARY-SOURCES: schema_version=1.0 -->
| source_id | status | trust_tier | type | title | author_or_publisher | location | reviewed_date | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
<!-- /LIBRARY-SOURCES -->

## Notes

Empty library state is valid during cold start. Keep manual notes outside the
generated block.
"""

KNOWLEDGE_INDEX_TEMPLATE = """# Knowledge Index

<!-- LIBRARY-KNOWLEDGE: schema_version=1.0 -->
| topic | summary | source_refs | confidence | caveats | updated_at |
| --- | --- | --- | --- | --- | --- |
<!-- /LIBRARY-KNOWLEDGE -->

## Notes

Empty library state is valid during cold start. Keep manual notes outside the
generated block.
"""

CLAIM_MAP_TEMPLATE = """# Claim Map

<!-- LIBRARY-CLAIMS: schema_version=1.0 -->
| claim | source_refs | claim_strength | disputed_status | caveats | reviewed_date |
| --- | --- | --- | --- | --- | --- |
<!-- /LIBRARY-CLAIMS -->

## Notes

Empty library state is valid during cold start. Keep manual notes outside the
generated block.
"""

METHOD_INDEX_TEMPLATE = """# Method Index

<!-- LIBRARY-METHODS: schema_version=1.0 -->
| method | use_case | assumptions | source_refs | risks | reviewed_date |
| --- | --- | --- | --- | --- | --- |
<!-- /LIBRARY-METHODS -->

## Notes

Empty library state is valid during cold start. Keep manual notes outside the
generated block.
"""

OPEN_QUESTIONS_TEMPLATE = """# Open Questions

<!-- LIBRARY-OPEN-QUESTIONS: schema_version=1.0 -->
| question_id | question | why_it_matters | source_refs | next_task | status |
| --- | --- | --- | --- | --- | --- |
<!-- /LIBRARY-OPEN-QUESTIONS -->

## Notes

Empty library state is valid during cold start. Keep manual notes outside the
generated block.
"""

UPDATE_LOG_TEMPLATE = """# Library Update Log

<!-- LIBRARY-UPDATE-LOG: schema_version=1.0 -->
| date | task_id | files_updated | reviewer_or_approver | notes |
| --- | --- | --- | --- | --- |
<!-- /LIBRARY-UPDATE-LOG -->

## Notes

Empty library state is valid during cold start. Keep manual notes outside the
generated block.
"""

STARTER_FILES = (
    (Path(LIBRARY_DIR) / SOURCE_LIBRARY_FILE, SOURCE_LIBRARY_TEMPLATE),
    (Path(LIBRARY_DIR) / KNOWLEDGE_INDEX_FILE, KNOWLEDGE_INDEX_TEMPLATE),
    (Path(LIBRARY_DIR) / CLAIM_MAP_FILE, CLAIM_MAP_TEMPLATE),
    (Path(LIBRARY_DIR) / METHOD_INDEX_FILE, METHOD_INDEX_TEMPLATE),
    (Path(LIBRARY_DIR) / OPEN_QUESTIONS_FILE, OPEN_QUESTIONS_TEMPLATE),
    (Path(LIBRARY_DIR) / UPDATE_LOG_FILE, UPDATE_LOG_TEMPLATE),
)


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def atomic_write_text(path: Path, text: str) -> bool:
    existing = path.read_text(encoding="utf-8") if path.exists() else None
    if existing == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(text)
        temp_path = Path(handle.name)
    temp_path.replace(path)
    return True


def init_plan(ops_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    failures: list[dict[str, Any]] = []
    if not ops_dir.exists():
        failures.append(
            {
                "reason": "ops_dir_missing",
                "path": str(ops_dir),
                "message": "research_ops directory does not exist",
            }
        )
        return [], [], failures
    if not ops_dir.is_dir():
        failures.append(
            {
                "reason": "ops_dir_not_directory",
                "path": str(ops_dir),
                "message": "research_ops path must be a directory",
            }
        )
        return [], [], failures

    library_dir = ops_dir / LIBRARY_DIR
    if library_dir.exists() and not library_dir.is_dir():
        failures.append(
            {
                "reason": "library_path_not_directory",
                "path": str(library_dir),
                "message": "research_ops/library must be a directory",
            }
        )
        return [], [], failures

    missing: list[dict[str, Any]] = []
    existing: list[dict[str, Any]] = []
    for relative, template in STARTER_FILES:
        path = ops_dir / relative
        item = {
            "relative_path": str(relative),
            "path": str(path),
            "bytes": len(template.encode("utf-8")),
        }
        if path.exists() and not path.is_file():
            failures.append(
                {
                    "reason": "library_file_path_not_file",
                    "path": str(path),
                    "message": "library starter path must be a file",
                }
            )
            continue
        if path.exists():
            existing.append(item)
        else:
            missing.append(item)
    return missing, existing, failures


def command_init(args: argparse.Namespace) -> int:
    if args.dry_run and args.write:
        print_json(
            {
                "ok": False,
                "action": "library_init_failed",
                "reason": "conflicting_flags",
                "message": "use either --dry-run or --write, not both",
            }
        )
        return INVALID_REQUEST

    dry_run = not args.write
    missing, existing, failures = init_plan(args.ops_dir)
    if failures:
        print_json(
            {
                "ok": False,
                "action": "library_init_failed",
                "dry_run": dry_run,
                "changed": False,
                "failures": failures,
            }
        )
        return MALFORMED

    if dry_run:
        print_json(
            {
                "ok": True,
                "action": "library_init_planned",
                "dry_run": True,
                "changed": bool(missing),
                "would_write": missing,
                "existing_files": existing,
                "next_step": "rerun with --write to add missing library starter files",
            }
        )
        return SUCCESS

    files_added: list[dict[str, Any]] = []
    try:
        for relative, template in STARTER_FILES:
            path = args.ops_dir / relative
            if path.exists():
                continue
            atomic_write_text(path, template)
            files_added.append(
                {
                    "relative_path": str(relative),
                    "path": str(path),
                    "bytes": len(template.encode("utf-8")),
                }
            )
    except OSError as exc:
        print_json(
            {
                "ok": False,
                "action": "library_init_failed",
                "dry_run": False,
                "changed": bool(files_added),
                "files_added": files_added,
                "reason": "write_failed",
                "error": str(exc),
            }
        )
        return MALFORMED

    _, existing_after, _ = init_plan(args.ops_dir)
    print_json(
        {
            "ok": True,
            "action": "library_initialized",
            "dry_run": False,
            "changed": bool(files_added),
            "files_added": files_added,
            "existing_files": [
                item for item in existing_after
                if item["relative_path"] not in {added["relative_path"] for added in files_added}
            ],
        }
    )
    return SUCCESS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Initialize knowledge library workspace files.")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser(
        "init",
        help="Add missing knowledge library starter files.",
        description="Preview or add missing research_ops/library starter files without overwriting existing files.",
    )
    init.add_argument("ops_dir", type=Path, help="Path to research_ops workspace.")
    init.add_argument("--dry-run", action="store_true", help="Report missing library files without writing. This is the default.")
    init.add_argument("--write", action="store_true", help="Create only missing library files.")
    init.set_defaults(func=command_init)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
