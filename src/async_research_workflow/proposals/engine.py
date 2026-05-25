"""Shared primitives for guarded proposal write flows."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
from typing import Any, Callable, Iterable


@dataclass(frozen=True)
class DirectoryLock:
    path: Path
    owner: dict[str, Any]


def print_stable_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def stable_json_hash(payload: Any) -> str:
    return hashlib.sha256(print_stable_json(payload).encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError:
        return None


def file_hashes(paths: Iterable[Path]) -> list[dict[str, str | None]]:
    return [{"path": str(path), "sha256": file_sha256(path)} for path in paths]


def read_json_object(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def acquire_directory_lock(
    path: Path,
    owner: dict[str, Any],
    *,
    on_exists: Callable[[Path, dict[str, Any]], Exception],
    on_failure: Callable[[Path, OSError], Exception],
) -> DirectoryLock:
    try:
        path.mkdir()
        (path / "owner.json").write_text(json.dumps(owner, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except FileExistsError as exc:
        raise on_exists(path, read_json_object(path / "owner.json") or {}) from exc
    except OSError as exc:
        shutil.rmtree(path, ignore_errors=True)
        raise on_failure(path, exc) from exc
    return DirectoryLock(path=path, owner=owner)


def release_directory_lock(lock: DirectoryLock | None) -> None:
    if lock is not None:
        shutil.rmtree(lock.path, ignore_errors=True)


def snapshot_files(paths: Iterable[Path], *, missing_on_error: bool = False) -> dict[Path, bytes | None]:
    snapshots: dict[Path, bytes | None] = {}
    for path in paths:
        try:
            snapshots[path] = path.read_bytes() if path.exists() else None
        except OSError:
            if not missing_on_error:
                raise
            snapshots[path] = None
    return snapshots


def restore_file_snapshots(
    snapshots: dict[Path, bytes | None],
    write_bytes: Callable[[Path, bytes], bool],
    *,
    absent_action: str,
    absent_failed_action: str,
    restored_action: str,
    restored_failed_action: str,
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for path, content in snapshots.items():
        if content is None:
            if path.exists():
                try:
                    path.unlink()
                    actions.append({"path": str(path), "action": absent_action, "changed": True})
                except OSError as exc:
                    actions.append(
                        {
                            "path": str(path),
                            "action": absent_failed_action,
                            "changed": False,
                            "error": str(exc),
                        }
                    )
            else:
                actions.append({"path": str(path), "action": absent_action, "changed": False})
            continue
        try:
            changed = write_bytes(path, content)
            actions.append({"path": str(path), "action": restored_action, "changed": changed})
        except OSError as exc:
            actions.append(
                {
                    "path": str(path),
                    "action": restored_failed_action,
                    "changed": False,
                    "error": str(exc),
                }
            )
    return actions


def atomic_write_bytes(path: Path, content: bytes) -> bool:
    existing = path.read_bytes() if path.exists() else None
    if existing == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_bytes(content)
    os.replace(tmp, path)
    return True
