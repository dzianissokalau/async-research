#!/usr/bin/env python3
"""Run package-level async research workflow acceptance checks."""

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
from typing import Iterable

SUCCESS = 0
FAILED = 1


def print_json(payload: dict) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def run_module(module_name: str, argv: list[str]) -> tuple[int, dict]:
    module = importlib.import_module(f"async_research_workflow.scripts.{module_name}")
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = int(module.main(argv))
    text = stream.getvalue().strip()
    payload = {}
    if text:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = {"raw_output": text}
    return code, payload


def run_cli(argv: list[str]) -> tuple[int, dict]:
    from async_research_workflow.cli import main as cli_main
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = int(cli_main(argv))
    text = stream.getvalue().strip()
    payload = {}
    if text:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = {"raw_output": text}
    return code, payload


def check(name: str, code: int, payload: dict, failures: list[dict], checks: list[dict]) -> None:
    ok = code == SUCCESS and payload.get("ok", True) is not False
    checks.append({"name": name, "ok": ok})
    if not ok:
        failures.append({"name": name, "exit_code": code, "payload": payload})


def default_work_dir() -> Path:
    return Path(tempfile.gettempdir()) / "async_research_workflow_acceptance"


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run package-level async research workflow acceptance checks.")
    parser.add_argument("--work-dir", type=Path, default=default_work_dir())
    parser.add_argument("--keep-work-dir", action="store_true")
    return parser.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    if args.work_dir.exists():
        shutil.rmtree(args.work_dir)
    args.work_dir.mkdir(parents=True, exist_ok=True)

    failures: list[dict] = []
    checks: list[dict] = []

    code, payload = run_cli(["version"])
    check("CLI version", code, payload, failures, checks)

    policy = resources.files("async_research_workflow").joinpath("mission_policy.json")
    code, payload = run_module("validate_mission_policy", [str(policy)])
    check("Mission policy validates", code, payload, failures, checks)

    ops_dir = args.work_dir / "research_ops"
    code, payload = run_cli(["init", str(ops_dir), "--force"])
    check("Starter template initializes", code, payload, failures, checks)

    starter_checks = [
        ("Starter schema check", ["schema-check", str(ops_dir)]),
        ("Starter readiness gate", ["readiness", str(ops_dir), "--dry-run"]),
        ("Starter health check", ["health", str(ops_dir), "--dry-run"]),
        ("Starter surface update", ["surface", "update", str(ops_dir)]),
        ("Starter surface validate", ["surface", "validate", str(ops_dir)]),
        ("Starter source validate", ["source", "validate", str(ops_dir)]),
        ("Starter cost summary", ["cost", "summary", str(ops_dir)]),
    ]
    for name, command in starter_checks:
        code, payload = run_cli(command)
        check(name, code, payload, failures, checks)

    code, payload = run_module("run_autonomy_benchmark", [])
    check("Autonomy benchmark", code, payload, failures, checks)

    code, payload = run_module("simulate_scheduled_week", [str(ops_dir)])
    check("Scheduled week simulation", code, payload, failures, checks)

    if not args.keep_work_dir:
        shutil.rmtree(args.work_dir, ignore_errors=True)

    print_json({
        "ok": not failures,
        "work_dir": str(args.work_dir),
        "work_dir_kept": args.keep_work_dir,
        "check_count": len(checks),
        "checks": checks,
        "failures": failures,
    })
    return SUCCESS if not failures else FAILED


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
