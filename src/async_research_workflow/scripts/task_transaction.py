#!/usr/bin/env python3
"""Shared helpers for task-folder and queue transactions."""

from __future__ import annotations

from collections.abc import Callable
import json
import os
from pathlib import Path
import re
import shutil
from typing import Any

from async_research_workflow.resources import schema_path
from async_research_workflow.scripts.validate_json_artifact import load_json
from async_research_workflow.scripts.validate_json_artifact import validate
from async_research_workflow.scripts.validate_transition import SUCCESS as TRANSITION_SUCCESS
from async_research_workflow.scripts.validate_transition import validate_payload


SUCCESS = 0
VALIDATION_FAILED = 2
INVALID_REQUEST = 3
MALFORMED = 4
TASK_ID_RE = re.compile(r"\bTASK-[0-9]{4}\b")
QUEUE_TEMPLATE = "# Queue\n\n| task | priority | status | type | next_runner | notes |\n| --- | ---: | --- | --- | --- | --- |\n"
STATUS_SCHEMA = schema_path("task_status.schema.json")


class TaskTransactionError(RuntimeError):
    def __init__(self, payload: dict[str, Any], code: int = MALFORMED):
        super().__init__(str(payload.get("reason", "task_transaction_error")))
        self.payload = payload
        self.code = code


def json_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def atomic_write_bytes(path: Path, content: bytes) -> bool:
    if path.exists() and path.read_bytes() == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    temp_path.write_bytes(content)
    temp_path.replace(path)
    return True


def markdown_cell(value: Any) -> str:
    if value is None:
        return ""
    text = " ".join(str(value).split())
    return text.replace("|", "\\|")


def task_id_from_text(value: Any) -> str | None:
    match = TASK_ID_RE.search(str(value or ""))
    return match.group(0) if match else None


def queue_path(ops_dir: Path) -> Path:
    return ops_dir / "queue.md"


def queue_row_task_id(line: str) -> str | None:
    stripped = line.lstrip()
    if not stripped.startswith("|"):
        return None
    cells = stripped.split("|")
    if len(cells) <= 1:
        return None
    return task_id_from_text(cells[1])


def queue_contains_task(ops_dir: Path, task_id: str) -> bool:
    path = queue_path(ops_dir)
    if not path.exists():
        return False
    try:
        return any(
            queue_row_task_id(line) == task_id
            for line in path.read_text(encoding="utf-8").splitlines()
        )
    except (OSError, UnicodeDecodeError):
        return False


def queue_row_markdown(row: dict[str, Any]) -> str:
    task_id = str(row.get("task_id") or task_id_from_text(row.get("task")) or "").strip()
    task_dir_name = str(row.get("task_dir_name") or "").strip()
    task_cell = str(row.get("task") or "").strip()
    if not task_cell:
        if not task_id or not task_dir_name:
            raise TaskTransactionError(
                {
                    "reason": "queue_row_missing_task_link_fields",
                    "message": "queue row requires task or task_id plus task_dir_name",
                },
                INVALID_REQUEST,
            )
        task_cell = f"[{task_id}](tasks/{task_dir_name}/task.md)"
    values = [
        task_cell,
        row.get("priority"),
        row.get("status"),
        row.get("type"),
        row.get("next_runner"),
        row.get("notes"),
    ]
    return "| " + " | ".join(markdown_cell(value) for value in values) + " |\n"


def append_queue_row_once(ops_dir: Path, row: dict[str, Any]) -> dict[str, Any]:
    task_id = str(row.get("task_id") or task_id_from_text(row.get("task")) or "").strip()
    if not task_id:
        raise TaskTransactionError({"reason": "queue_row_missing_task_id"}, INVALID_REQUEST)
    path = queue_path(ops_dir)
    if queue_contains_task(ops_dir, task_id):
        return {"path": str(path), "action": "queue_row_already_present", "task_id": task_id, "changed": False}
    try:
        content = path.read_bytes() if path.exists() else QUEUE_TEMPLATE.encode("utf-8")
        if content and not content.endswith(b"\n"):
            content += b"\n"
        changed = atomic_write_bytes(path, content + queue_row_markdown(row).encode("utf-8"))
    except OSError as exc:
        raise TaskTransactionError(
            {"reason": "queue_append_failed", "path": str(path), "error": str(exc)},
            MALFORMED,
        ) from exc
    return {"path": str(path), "action": "append_queue_row", "task_id": task_id, "changed": changed}


def remove_queue_row(ops_dir: Path, task_id: str) -> dict[str, Any]:
    path = queue_path(ops_dir)
    if not path.exists():
        return {"path": str(path), "action": "remove_queue_row", "task_id": task_id, "changed": False}
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise TaskTransactionError(
            {"reason": "queue_read_failed", "path": str(path), "error": str(exc)},
            MALFORMED,
        ) from exc
    lines = text.splitlines()
    kept: list[str] = []
    removed = 0
    for line in lines:
        if queue_row_task_id(line) == task_id:
            removed += 1
            continue
        kept.append(line)
    if removed == 0:
        return {"path": str(path), "action": "remove_queue_row", "task_id": task_id, "changed": False}
    new_text = "\n".join(kept) + ("\n" if text.endswith("\n") else "")
    try:
        atomic_write_bytes(path, new_text.encode("utf-8"))
    except OSError as exc:
        raise TaskTransactionError(
            {"reason": "queue_remove_failed", "path": str(path), "error": str(exc)},
            MALFORMED,
        ) from exc
    return {
        "path": str(path),
        "action": "remove_queue_row",
        "task_id": task_id,
        "changed": True,
        "removed_count": removed,
    }


def safe_relative_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise TaskTransactionError(
            {"reason": "unsafe_extra_task_file_path", "path": str(value)},
            INVALID_REQUEST,
        )
    return path


def unique_stage_dir(target_dir: Path) -> Path:
    base = target_dir.parent / f".{target_dir.name}.staging.{os.getpid()}"
    candidate = base
    index = 1
    while candidate.exists():
        candidate = target_dir.parent / f"{base.name}.{index}"
        index += 1
    return candidate


def stage_task_folder(
    ops_dir: Path,
    task_dir_name: str,
    task_markdown: str,
    status_json: dict[str, Any],
    extra_files: dict[str | Path, str | bytes] | None = None,
) -> tuple[Path, Path]:
    target_dir = ops_dir / "tasks" / task_dir_name
    if target_dir.exists():
        raise TaskTransactionError(
            {"reason": "task_folder_exists", "path": str(target_dir), "task_dir_name": task_dir_name},
            INVALID_REQUEST,
        )
    stage_dir = unique_stage_dir(target_dir)
    try:
        stage_dir.mkdir(parents=True)
        atomic_write_bytes(stage_dir / "task.md", task_markdown.encode("utf-8"))
        atomic_write_bytes(stage_dir / "status.json", json_bytes(status_json))
        for relative, content in (extra_files or {}).items():
            output_path = stage_dir / safe_relative_path(relative)
            data = content if isinstance(content, bytes) else content.encode("utf-8")
            atomic_write_bytes(output_path, data)
    except Exception:
        shutil.rmtree(stage_dir, ignore_errors=True)
        raise
    return stage_dir, target_dir


def validate_task_folder(ops_dir: Path, task_dir: Path) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    task_md = task_dir / "task.md"
    status_path = task_dir / "status.json"
    try:
        task_text = task_md.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        failures.append({"reason": "task_markdown_read_failed", "path": str(task_md), "error": str(exc)})
        task_text = None
    if task_text is not None and not task_text.strip():
        failures.append({"reason": "task_markdown_empty", "path": str(task_md)})

    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        failures.append({"reason": "status_json_malformed", "path": str(status_path), "error": str(exc)})
        return failures
    if not isinstance(status, dict):
        failures.append({"reason": "status_json_not_object", "path": str(status_path)})
        return failures

    task_id = task_id_from_text(task_dir.name)
    if task_id and status.get("id") != task_id:
        failures.append(
            {
                "reason": "status_id_mismatch",
                "path": str(status_path),
                "expected": task_id,
                "actual": status.get("id"),
            }
        )

    schema = load_json(STATUS_SCHEMA)
    schema_errors = [error.to_dict() for error in validate(status, schema)]
    if schema_errors:
        failures.append({"reason": "status_schema_invalid", "path": str(status_path), "errors": schema_errors})

    transition_code, transition = validate_payload(status, decisions_path=ops_dir / "decisions.md")
    if transition_code != TRANSITION_SUCCESS:
        failures.append({"reason": "status_transition_invalid", "path": str(status_path), "details": transition})
    return failures


def default_final_validator(ops_dir: Path, task_dir: Path, task_id: str) -> list[dict[str, Any]]:
    failures = validate_task_folder(ops_dir, task_dir)
    if not queue_contains_task(ops_dir, task_id):
        failures.append({"reason": "queue_row_missing_after_write", "path": str(queue_path(ops_dir)), "task_id": task_id})
    return failures


def rollback_task_transaction(
    ops_dir: Path,
    task_id: str,
    target_dir: Path | None = None,
    stage_dir: Path | None = None,
    remove_queue: bool = False,
) -> dict[str, Any]:
    actions: list[dict[str, Any]] = []
    for path, action in ((stage_dir, "remove_staged_task_folder"), (target_dir, "remove_task_folder")):
        if path is not None and path.exists():
            shutil.rmtree(path, ignore_errors=True)
            actions.append({"action": action, "path": str(path), "changed": not path.exists()})
    if remove_queue:
        actions.append(remove_queue_row(ops_dir, task_id))
    return {"task_id": task_id, "actions": actions}


def write_task_transaction(
    ops_dir: Path,
    task_dir_name: str,
    task_markdown: str,
    status_json: dict[str, Any],
    queue_row: dict[str, Any],
    extra_files: dict[str | Path, str | bytes] | None = None,
    append_queue: Callable[[Path, dict[str, Any]], dict[str, Any]] = append_queue_row_once,
    final_validator: Callable[[Path, Path, str], list[dict[str, Any]]] = default_final_validator,
) -> tuple[int, dict[str, Any]]:
    task_id = str(status_json.get("id") or task_id_from_text(task_dir_name) or "").strip()
    if not task_id:
        return INVALID_REQUEST, {"ok": False, "reason": "task_id_missing", "task_dir_name": task_dir_name}

    stage_dir: Path | None = None
    target_dir = ops_dir / "tasks" / task_dir_name
    queue_write: dict[str, Any] | None = None
    try:
        stage_dir, target_dir = stage_task_folder(ops_dir, task_dir_name, task_markdown, status_json, extra_files)
        staged_failures = validate_task_folder(ops_dir, stage_dir)
        if staged_failures:
            rollback = rollback_task_transaction(ops_dir, task_id, stage_dir=stage_dir)
            return VALIDATION_FAILED, {
                "ok": False,
                "reason": "staged_task_validation_failed",
                "failures": staged_failures,
                "rollback": rollback,
            }

        stage_dir.replace(target_dir)
        stage_dir = None
        queue_write = append_queue(ops_dir, {**queue_row, "task_id": task_id, "task_dir_name": task_dir_name})
        final_failures = final_validator(ops_dir, target_dir, task_id)
        if final_failures:
            rollback = rollback_task_transaction(
                ops_dir,
                task_id,
                target_dir=target_dir,
                remove_queue=bool(queue_write.get("changed")),
            )
            return VALIDATION_FAILED, {
                "ok": False,
                "reason": "final_validation_failed",
                "failures": final_failures,
                "queue_write": queue_write,
                "rollback": rollback,
            }

        return SUCCESS, {
            "ok": True,
            "action": "task_transaction_written",
            "task_id": task_id,
            "task_dir": str(target_dir),
            "queue_write": queue_write,
            "files_written": [
                {"path": str(target_dir / "task.md"), "action": "write_task_markdown"},
                {"path": str(target_dir / "status.json"), "action": "write_status_json"},
                queue_write,
            ],
        }
    except TaskTransactionError as exc:
        rollback = rollback_task_transaction(
            ops_dir,
            task_id,
            target_dir=target_dir,
            stage_dir=stage_dir,
            remove_queue=bool(queue_write and queue_write.get("changed")),
        )
        reason = exc.payload.get("reason") or "task_transaction_failed"
        return exc.code, {"ok": False, "reason": reason, "failure": exc.payload, "rollback": rollback}
    except OSError as exc:
        rollback = rollback_task_transaction(
            ops_dir,
            task_id,
            target_dir=target_dir,
            stage_dir=stage_dir,
            remove_queue=bool(queue_write and queue_write.get("changed")),
        )
        return MALFORMED, {
            "ok": False,
            "reason": "task_transaction_io_failed",
            "error": str(exc),
            "rollback": rollback,
        }
