#!/usr/bin/env python3
"""Prepare and install structurally isolated review bundles.

Reviewer bundles copy task inputs into a separate directory while excluding
sibling reviews. Aggregator bundles intentionally include review files.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys
from datetime import datetime, timezone
from typing import Iterable

from async_research_workflow.scripts import review_template


SUCCESS = 0
INVALID = 4
EXISTS = 5

REVIEWER_ROLES = {"primary", "methodology", "skeptic"}
ALL_ROLES = REVIEWER_ROLES | {"aggregator"}


def seeded_review_template(role: str) -> str:
    """Return a safe reviewer scaffold that routes to human review if installed unchanged."""
    payload = review_template.review_payload(
        argparse.Namespace(
            role=role,
            decision="needs_human",
            claim_strength="none",
            confidence=0.0,
            concern=["TODO: replace this scaffold with the actual isolated review before installing."],
            followup=[],
            evidence_gap=["Review output scaffold has not been completed."],
        )
    )
    return "```json\n" + json.dumps(payload, indent=2, sort_keys=True) + "\n```\n"


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def print_json(payload: dict) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def copy_file_if_exists(src: Path, dst: Path) -> None:
    if src.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def copy_dir_if_exists(src: Path, dst: Path) -> None:
    if src.exists():
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)


def task_id_from_dir(task_dir: Path) -> str:
    status_path = task_dir / "status.json"
    if status_path.exists():
        try:
            payload = json.loads(status_path.read_text(encoding="utf-8"))
            if isinstance(payload.get("id"), str):
                return payload["id"]
        except json.JSONDecodeError:
            pass
    return task_dir.name.split("-", 2)[0] if task_dir.name.startswith("TASK-") else task_dir.name


def infer_ops_dir(task_dir: Path) -> Path | None:
    if task_dir.parent.name == "tasks":
        return task_dir.parent.parent
    for parent in task_dir.parents:
        if parent.name == "research_ops":
            return parent
    return None


def write_manifest(bundle_dir: Path, task_dir: Path, role: str) -> None:
    manifest = {
        "created_at": iso_now(),
        "role": role,
        "source_task_dir": str(task_dir.resolve()),
        "task_id": task_id_from_dir(task_dir),
        "input_dir": "input",
        "output_dir": "output",
        "includes_sibling_reviews": role == "aggregator",
        "expected_output": (
            f"output/reviews/{role}.md" if role in REVIEWER_ROLES else "output/review_panel/aggregate.md"
        ),
    }
    (bundle_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def prepare_bundle(task_dir: Path, role: str, bundle_dir: Path, force: bool) -> int:
    if role not in ALL_ROLES:
        print_json({"ok": False, "reason": "unknown_role", "role": role})
        return INVALID
    if not task_dir.exists() or not task_dir.is_dir():
        print_json({"ok": False, "reason": "task_dir_missing", "task_dir": str(task_dir)})
        return INVALID
    if bundle_dir.exists():
        if not force:
            print_json({"ok": False, "reason": "bundle_exists", "bundle_dir": str(bundle_dir)})
            return EXISTS
        shutil.rmtree(bundle_dir)

    input_dir = bundle_dir / "input"
    output_dir = bundle_dir / "output"
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    for filename in ("task.md", "status.json", "worker_output.md"):
        copy_file_if_exists(task_dir / filename, input_dir / filename)
    ops_dir = infer_ops_dir(task_dir)
    if ops_dir is not None:
        copy_file_if_exists(ops_dir / "escalation_policy.md", input_dir / "escalation_policy.md")
    copy_dir_if_exists(task_dir / "artifacts", input_dir / "artifacts")

    if role == "aggregator":
        copy_dir_if_exists(task_dir / "reviews", input_dir / "reviews")
        copy_dir_if_exists(task_dir / "review_panel", input_dir / "review_panel")
        target = output_dir / "review_panel" / "aggregate.md"
    else:
        target = output_dir / "reviews" / f"{role}.md"

    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        text = seeded_review_template(role) if role in REVIEWER_ROLES else ""
        target.write_text(text, encoding="utf-8")

    write_manifest(bundle_dir, task_dir, role)
    print_json(
        {
            "ok": True,
            "action": "prepared",
            "role": role,
            "bundle_dir": str(bundle_dir),
            "includes_sibling_reviews": role == "aggregator",
            "expected_output": str(target),
        }
    )
    return SUCCESS


def load_manifest(bundle_dir: Path) -> dict:
    path = bundle_dir / "manifest.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"manifest missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"manifest malformed: {path}: {exc}") from exc


def install_output(bundle_dir: Path, force: bool) -> int:
    try:
        manifest = load_manifest(bundle_dir)
    except ValueError as exc:
        print_json({"ok": False, "reason": "manifest_error", "error": str(exc)})
        return INVALID

    role = manifest.get("role")
    task_dir = Path(str(manifest.get("source_task_dir", "")))
    expected_output = Path(str(manifest.get("expected_output", "")))
    src = bundle_dir / expected_output

    if role in REVIEWER_ROLES:
        dst = task_dir / "reviews" / f"{role}.md"
    elif role == "aggregator":
        dst = task_dir / "review_panel" / "aggregate.md"
    else:
        print_json({"ok": False, "reason": "unknown_role", "role": role})
        return INVALID

    if not src.exists() or not src.read_text(encoding="utf-8").strip():
        print_json({"ok": False, "reason": "output_missing_or_empty", "output": str(src)})
        return INVALID
    if dst.exists() and not force:
        print_json({"ok": False, "reason": "target_exists", "target": str(dst)})
        return EXISTS

    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print_json({"ok": True, "action": "installed", "role": role, "source": str(src), "target": str(dst)})
    return SUCCESS


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare or install isolated review context bundles.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("task_dir", type=Path)
    prepare.add_argument("--role", required=True, choices=sorted(ALL_ROLES))
    prepare.add_argument("--bundle-dir", required=True, type=Path)
    prepare.add_argument("--force", action="store_true")

    install = subparsers.add_parser("install")
    install.add_argument("bundle_dir", type=Path)
    install.add_argument("--force", action="store_true")

    return parser.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    if args.command == "prepare":
        return prepare_bundle(args.task_dir, args.role, args.bundle_dir, args.force)
    if args.command == "install":
        return install_output(args.bundle_dir, args.force)
    return INVALID


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
