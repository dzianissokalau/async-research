"""Console snapshot facet helpers."""

from __future__ import annotations

import json
import re
import shlex
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from async_research_workflow.scripts import health_check


RECENT_LIMIT = 5

def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

def parse_now(value: str | None) -> datetime:
    if not value:
        return utc_now()
    parsed = health_check.parse_datetime(value)
    if parsed is None:
        raise ValueError(f"invalid --now value: {value}")
    return parsed

def iso_now(now: datetime) -> str:
    return now.replace(microsecond=0).isoformat().replace("+00:00", "Z")

def tail_text(path: Path, limit: int = 1200) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return text[-limit:]

def issue(severity: str, reason: str, message: str, path: Path | str | None = None, details: Any = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "severity": severity,
        "reason": reason,
        "message": message,
    }
    if path is not None:
        payload["path"] = str(path)
    if details is not None:
        payload["details"] = details
    return payload

def unavailable(reason: str, message: str, path: Path | str | None = None, details: Any = None) -> dict[str, Any]:
    payload = {
        "available": False,
        "status": "unavailable",
        "reason": reason,
        "message": message,
        "summary": {},
        "warnings": [issue("warning", reason, message, path, details)],
    }
    if path is not None:
        payload["path"] = str(path)
    return payload

def markdown_table_rows(path: Path) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    warnings: list[dict[str, Any]] = []
    if not path.exists():
        return [], warnings
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        return [], [
            issue(
                "warning",
                "markdown_table_unreadable",
                "markdown table could not be read",
                path,
                str(exc),
            )
        ]
    header: list[str] | None = None
    rows: list[dict[str, str]] = []
    for line_number, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if not cells or all(not cell for cell in cells):
            continue
        if all(cell.replace("-", "").strip() == "" for cell in cells):
            continue
        if header is None:
            header = cells
            continue
        if len(cells) != len(header):
            warnings.append(
                issue(
                    "warning",
                    "malformed_markdown_table_row",
                    "markdown table row has a different number of cells than the header",
                    path,
                    {"line_number": line_number, "cell_count": len(cells), "header_count": len(header)},
                )
            )
            continue
        rows.append(dict(zip(header, cells)))
    return rows, warnings

def recent_markdown_rows(path: Path, limit: int = RECENT_LIMIT) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows, warnings = markdown_table_rows(path)
    return {
        "path": str(path),
        "exists": path.exists(),
        "count": len(rows),
        "recent_rows": rows[-limit:],
    }, warnings

def revalidation_state(rows: list[dict[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        status = str(row.get("revalidation_status") or "unavailable").strip() or "unavailable"
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items()))

def command_hint(label: str, argv: list[str]) -> dict[str, str]:
    return {
        "label": label,
        "command": " ".join(shlex.quote(str(part)) for part in argv),
    }

def limited(rows: list[dict[str, Any]], limit: int = RECENT_LIMIT) -> list[dict[str, Any]]:
    return rows[:limit]

def safe_read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}

def safe_read_embedded_json(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}
    for match in re.finditer(r"```(?:json)?\s*(.*?)```", text, re.IGNORECASE | re.DOTALL):
        try:
            payload = json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            continue
        return payload if isinstance(payload, dict) else {}
    start = text.find("{")
    if start < 0:
        return {}
    decoder = json.JSONDecoder()
    try:
        payload, _index = decoder.raw_decode(text[start:])
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}

def normalize_heading(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")

def markdown_sections(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return {}
    sections: dict[str, list[str]] = {"intro": []}
    current = "intro"
    for raw in lines:
        stripped = raw.strip()
        if stripped.startswith("## "):
            current = normalize_heading(stripped[3:])
            sections.setdefault(current, [])
            continue
        if stripped.startswith("# "):
            continue
        if stripped:
            sections.setdefault(current, []).append(stripped)
    return {key: "\n".join(value).strip() for key, value in sections.items() if "\n".join(value).strip()}

def first_section(sections: dict[str, str], *names: str) -> str:
    for name in names:
        text = sections.get(normalize_heading(name), "").strip()
        if text:
            return text
    return ""

def compact_text(value: Any, fallback: str = "unavailable", limit: int = 900) -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    if not text or text.lower() == "none":
        return fallback
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."

def normalize_list_value(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        rows = value
    elif isinstance(value, tuple):
        rows = list(value)
    elif isinstance(value, dict):
        rows = [f"{key}: {val}" for key, val in value.items()]
    else:
        text = str(value).strip()
        if not text or text.lower() == "none":
            return []
        rows = re.split(r"\s*(?:;|\n)\s*", text)
    output: list[str] = []
    for item in rows:
        text = str(item).strip().strip("-").strip()
        if text and text.lower() != "none" and text not in output:
            output.append(text)
    return output

def markdown_bullets(text: str, limit: int = RECENT_LIMIT) -> list[str]:
    rows: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("-", "*")):
            rows.append(stripped[1:].strip())
        elif stripped and not rows:
            rows.append(stripped)
        if len(rows) >= limit:
            break
    return [row for row in rows if row]

def reference_ids_from_text(*texts: str) -> list[str]:
    refs: list[str] = []
    for text in texts:
        for match in re.findall(r"\b(?:DS|LIT|IDEA|TASK)-[A-Za-z0-9_-]+\b", text):
            if match not in refs:
                refs.append(match)
    return refs

def extract_validation_commands(*paths: Path) -> list[str]:
    commands: list[str] = []
    patterns = [
        re.compile(r"`((?:\.venv/bin/)?async-research\s+[^`]+)`"),
        re.compile(r"((?:\.venv/bin/)?async-research\s+[A-Za-z0-9][^\n]+)"),
    ]
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for pattern in patterns:
            for match in pattern.findall(text):
                command = str(match).strip().rstrip(".")
                if command and command not in commands:
                    commands.append(command)
                if len(commands) >= RECENT_LIMIT:
                    return commands
    return commands

def count_values(rows: Iterable[dict[str, Any]], getter: Callable[[dict[str, Any]], Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(getter(row) or "unavailable")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))

def collect_unavailable_warnings(groups: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    for group in groups:
        if group.get("available") is False:
            warnings.extend(group.get("warnings", []))
    return warnings
