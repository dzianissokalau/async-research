#!/usr/bin/env python3
"""Check async research JSON artifacts for schema version drift."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Iterable


SUCCESS = 0
INVALID = 4
DEFAULT_SCHEMA_VERSION = "1.0"


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def artifact_paths(ops_dir: Path) -> list[tuple[Path, str]]:
    paths: list[tuple[Path, str]] = []

    tasks_dir = ops_dir / "tasks"
    if tasks_dir.exists():
        paths.extend((path, "task_status") for path in sorted(tasks_dir.glob("*/status.json")))
        paths.extend(
            (path, "review_panel")
            for path in sorted(tasks_dir.glob("*/review_panel/aggregate.json"))
        )

    discovery_dir = ops_dir / "discovery"
    if discovery_dir.exists():
        paths.extend((path, "idea_candidate") for path in sorted(discovery_dir.glob("IDEA-*.json")))

    batches_dir = ops_dir / "batches"
    if batches_dir.exists():
        paths.extend((path, "batch_manifest") for path in sorted(batches_dir.glob("*/batch_manifest.json")))

    health_report = ops_dir / "health_report.json"
    if health_report.exists():
        paths.append((health_report, "health_report"))

    deliverable_manifest = ops_dir / "deliverables" / "deliverable_manifest.json"
    if deliverable_manifest.exists():
        paths.append((deliverable_manifest, "deliverable_manifest"))

    return paths


def inspect_artifact(path: Path, artifact_type: str, expected_version: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    base = {
        "artifact_type": artifact_type,
        "path": str(path),
        "expected_schema_version": expected_version,
    }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        issue = {
            **base,
            "severity": "error",
            "reason": "malformed_json",
            "actual_schema_version": None,
            "message": str(exc),
        }
        return issue, issue
    except OSError as exc:
        issue = {
            **base,
            "severity": "error",
            "reason": "read_failed",
            "actual_schema_version": None,
            "message": str(exc),
        }
        return issue, issue

    if not isinstance(payload, dict):
        issue = {
            **base,
            "severity": "error",
            "reason": "artifact_not_object",
            "actual_schema_version": None,
            "message": "JSON artifact is not an object",
        }
        return issue, issue

    actual = payload.get("schema_version")
    record = {**base, "actual_schema_version": actual}

    if actual is None:
        issue = {
            **record,
            "severity": "error",
            "reason": "missing_schema_version",
            "message": "Artifact must declare schema_version before workflow agents continue.",
        }
        return record, issue

    if actual != expected_version:
        issue = {
            **record,
            "severity": "error",
            "reason": "schema_version_mismatch",
            "message": f"Expected schema_version {expected_version!r}, found {actual!r}.",
        }
        return record, issue

    return record, None


def scan_schema_versions(ops_dir: Path, expected_version: str = DEFAULT_SCHEMA_VERSION) -> dict[str, Any]:
    artifacts: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for path, artifact_type in artifact_paths(ops_dir):
        record, issue = inspect_artifact(path, artifact_type, expected_version)
        artifacts.append(record)
        if issue is None:
            continue
        if issue.get("severity") == "error":
            errors.append(issue)
        else:
            warnings.append(issue)

    return {
        "expected_schema_version": expected_version,
        "artifact_count": len(artifacts),
        "warning_count": len(warnings),
        "error_count": len(errors),
        "warnings": warnings,
        "errors": errors,
    }


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check schema_version fields on workflow JSON artifacts.")
    parser.add_argument("ops_dir", nargs="?", type=Path, default=Path("research_ops"))
    parser.add_argument("--expected-version", default=DEFAULT_SCHEMA_VERSION)
    return parser.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    if not args.ops_dir.exists():
        print_json(
            {
                "ok": False,
                "reason": "ops_dir_missing",
                "ops_dir": str(args.ops_dir),
            }
        )
        return INVALID

    report = scan_schema_versions(args.ops_dir, args.expected_version)
    ok = report["error_count"] == 0 and report["warning_count"] == 0
    print_json({"ok": ok, "ops_dir": str(args.ops_dir), **report})
    return SUCCESS if ok else INVALID


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
