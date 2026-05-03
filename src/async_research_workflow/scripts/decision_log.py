"""Shared helpers for the append-only human decision log."""

from __future__ import annotations

from pathlib import Path
import re
from datetime import datetime, timezone
from typing import Any, Iterable, Optional


HEADER = ["date", "item_id", "decision", "reason", "approver", "related_artifacts"]

DECISIONS = {
    "approve",
    "resume",
    "pause",
    "reject",
    "approve_public",
    "approve_high_stakes",
    "approve_budget",
    "approve_data_use",
    "override",
    "acknowledge",
}


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def markdown_escape(value: Any) -> str:
    text = str(value if value is not None else "").replace("\n", " ").strip()
    text = re.sub(r"\s+", " ", text)
    return text.replace("|", "\\|") or "none"


def markdown_unescape(value: str) -> str:
    return value.replace("\\|", "|").strip()


def split_markdown_row(line: str) -> list[str]:
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for char in line.strip().strip("|"):
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            current.append(char)
            escaped = True
        elif char == "|":
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    cells.append("".join(current).strip())
    return cells


def read_decisions(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    rows: list[dict[str, str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line.startswith("|") or "---" in line:
            continue
        cells = split_markdown_row(line)
        if [cell.lower() for cell in cells] == HEADER:
            continue
        if len(cells) != len(HEADER):
            continue
        row = {key: markdown_unescape(value) for key, value in zip(HEADER, cells)}
        if row.get("item_id") and row.get("decision"):
            rows.append(row)
    return rows


def has_decision(
    path: Path,
    item_id: str,
    decisions: Optional[Iterable[str]] = None,
) -> bool:
    allowed = set(decisions) if decisions is not None else None
    for row in read_decisions(path):
        if row.get("item_id") != item_id:
            continue
        if allowed is None or row.get("decision") in allowed:
            return True
    return False


def append_decision(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    needs_header = not path.exists() or path.stat().st_size == 0
    prefix = ""
    if path.exists() and path.stat().st_size > 0:
        text = path.read_text(encoding="utf-8")
        if text and not text.endswith("\n"):
            prefix = "\n"

    values = {key: row.get(key, "") for key in HEADER}
    line = "| " + " | ".join(markdown_escape(values[key]) for key in HEADER) + " |\n"
    with path.open("a", encoding="utf-8") as handle:
        if prefix:
            handle.write(prefix)
        if needs_header:
            handle.write("| " + " | ".join(HEADER) + " |\n")
            handle.write("| --- | --- | --- | --- | --- | --- |\n")
        handle.write(line)


def normalize_related_artifacts(values: Iterable[str]) -> str:
    artifacts = [str(value).strip() for value in values if str(value).strip()]
    return "; ".join(artifacts) if artifacts else "none"
