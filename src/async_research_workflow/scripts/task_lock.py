#!/usr/bin/env python3
"""Atomic task lock helper for the async research workflow.

The authoritative claim is a task-local LOCK/ directory created with os.mkdir.
Directory creation is atomic on normal local and CI filesystems, so only one
worker can acquire a given task at a time.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import sys
import time
from datetime import datetime, timezone
from typing import Optional


SUCCESS = 0
LOCKED = 2
RELEASE_DENIED = 3
INVALID = 4


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().replace(microsecond=0).isoformat().replace("+00:00", "Z")


def default_owner() -> str:
    for name in ("RESEARCH_WORKER_OWNER", "GITHUB_RUN_ID", "USER"):
        value = os.environ.get(name)
        if value:
            return value
    return f"pid-{os.getpid()}"


def lock_dir(task_dir: Path) -> Path:
    return task_dir / "LOCK"


def owner_file(task_dir: Path) -> Path:
    return lock_dir(task_dir) / "owner.json"


def load_owner(task_dir: Path) -> dict:
    path = owner_file(task_dir)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def write_owner(task_dir: Path, owner: str, stale_seconds: int) -> None:
    path = owner_file(task_dir)
    payload = {
        "owner": owner,
        "pid": os.getpid(),
        "hostname": socket.gethostname(),
        "acquired_at": iso_now(),
        "task_dir": str(task_dir),
        "stale_after_seconds": stale_seconds,
    }
    tmp = path.with_name(f".owner.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def lock_age_seconds(task_dir: Path) -> Optional[float]:
    path = lock_dir(task_dir)
    try:
        return time.time() - path.stat().st_mtime
    except FileNotFoundError:
        return None


def is_stale(task_dir: Path, stale_seconds: int) -> bool:
    age = lock_age_seconds(task_dir)
    return age is not None and age > stale_seconds


def rename_stale_lock(task_dir: Path) -> bool:
    src = lock_dir(task_dir)
    stamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
    dst = task_dir / f"LOCK.stale.{stamp}.{os.getpid()}"
    try:
        os.rename(src, dst)
        return True
    except FileNotFoundError:
        return True
    except OSError:
        return False


def acquire(task_dir: Path, owner: str, stale_seconds: int) -> int:
    if not task_dir.exists() or not task_dir.is_dir():
        print_json({"ok": False, "reason": "task_dir_missing", "task_dir": str(task_dir)})
        return INVALID

    while True:
        try:
            lock_dir(task_dir).mkdir()
            write_owner(task_dir, owner, stale_seconds)
            print_json({"ok": True, "action": "acquired", "owner": owner, "task_dir": str(task_dir)})
            return SUCCESS
        except FileExistsError:
            if not is_stale(task_dir, stale_seconds):
                print_json(
                    {
                        "ok": False,
                        "reason": "locked",
                        "task_dir": str(task_dir),
                        "owner": load_owner(task_dir),
                        "age_seconds": lock_age_seconds(task_dir),
                    }
                )
                return LOCKED
            if rename_stale_lock(task_dir):
                continue
            print_json({"ok": False, "reason": "stale_lock_rename_failed", "task_dir": str(task_dir)})
            return LOCKED
        except OSError as exc:
            print_json({"ok": False, "reason": "mkdir_failed", "error": str(exc), "task_dir": str(task_dir)})
            return INVALID


def release(task_dir: Path, owner: str, force: bool) -> int:
    path = lock_dir(task_dir)
    if not path.exists():
        print_json({"ok": True, "action": "already_unlocked", "task_dir": str(task_dir)})
        return SUCCESS

    current = load_owner(task_dir).get("owner")
    if current and current != owner and not force:
        print_json(
            {
                "ok": False,
                "reason": "owner_mismatch",
                "expected_owner": current,
                "requested_owner": owner,
                "task_dir": str(task_dir),
            }
        )
        return RELEASE_DENIED

    try:
        shutil.rmtree(path)
    except OSError as exc:
        print_json({"ok": False, "reason": "release_failed", "error": str(exc), "task_dir": str(task_dir)})
        return INVALID

    print_json({"ok": True, "action": "released", "owner": owner, "task_dir": str(task_dir)})
    return SUCCESS


def status(task_dir: Path, stale_seconds: int) -> int:
    path = lock_dir(task_dir)
    payload = {
        "task_dir": str(task_dir),
        "locked": path.exists(),
        "owner": load_owner(task_dir) if path.exists() else None,
        "age_seconds": lock_age_seconds(task_dir) if path.exists() else None,
        "stale": is_stale(task_dir, stale_seconds) if path.exists() else False,
    }
    print_json(payload)
    return SUCCESS


def print_json(payload: dict) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Acquire, release, or inspect a task-local LOCK directory.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument("task_dir", type=Path)
        subparser.add_argument("--stale-minutes", type=float, default=60.0)

    acquire_parser = subparsers.add_parser("acquire")
    add_common(acquire_parser)
    acquire_parser.add_argument("--owner", default=default_owner())

    release_parser = subparsers.add_parser("release")
    add_common(release_parser)
    release_parser.add_argument("--owner", default=default_owner())
    release_parser.add_argument("--force", action="store_true")

    status_parser = subparsers.add_parser("status")
    add_common(status_parser)

    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    stale_seconds = max(1, int(args.stale_minutes * 60))
    task_dir = args.task_dir

    if args.command == "acquire":
        return acquire(task_dir, args.owner, stale_seconds)
    if args.command == "release":
        return release(task_dir, args.owner, args.force)
    if args.command == "status":
        return status(task_dir, stale_seconds)
    return INVALID


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
