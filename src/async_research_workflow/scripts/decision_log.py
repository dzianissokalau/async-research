"""Shared helpers for the append-only human decision log."""

from __future__ import annotations

from pathlib import Path
import re
from datetime import datetime, timezone
from typing import Any, Iterable, Optional


HEADER = ["date", "item_id", "decision", "reason", "approver", "related_artifacts"]
STARTER_LEGACY_HEADER = [
    "decision_id",
    "item_id",
    "decision",
    "decided_at",
    "decided_by",
    "rationale",
    "follow_up",
]
WEEK_SIMULATION_LEGACY_HEADER = ["date", "item_id", "decision", "approver", "reason", "next_status"]

HEADER_MAPS = {
    tuple(HEADER): {
        "date": "date",
        "item_id": "item_id",
        "decision": "decision",
        "reason": "reason",
        "approver": "approver",
        "related_artifacts": "related_artifacts",
    },
    tuple(STARTER_LEGACY_HEADER): {
        "date": "decided_at",
        "item_id": "item_id",
        "decision": "decision",
        "reason": "rationale",
        "approver": "decided_by",
        "related_artifacts": "follow_up",
    },
    tuple(WEEK_SIMULATION_LEGACY_HEADER): {
        "date": "date",
        "item_id": "item_id",
        "decision": "decision",
        "reason": "reason",
        "approver": "approver",
        "related_artifacts": "next_status",
    },
}

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


def normalize_header(cells: list[str]) -> tuple[str, ...]:
    return tuple(cell.lower().strip().replace(" ", "_") for cell in cells)


def decision_row_from_cells(cells: list[str], active_header: tuple[str, ...] | None) -> dict[str, str] | None:
    header = active_header if active_header is not None and len(cells) == len(active_header) else None
    if header is None:
        if len(cells) == len(HEADER):
            header = tuple(HEADER)
        elif len(cells) == len(STARTER_LEGACY_HEADER):
            header = tuple(STARTER_LEGACY_HEADER)
        else:
            return None
    mapping = HEADER_MAPS.get(header)
    if mapping is None:
        return None
    raw = {key: markdown_unescape(value) for key, value in zip(header, cells)}
    return {key: raw.get(source, "") for key, source in mapping.items()}


def active_decision_header(path: Path) -> tuple[str, ...] | None:
    if not path.exists():
        return None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line.startswith("|") or "---" in line:
            continue
        normalized = normalize_header(split_markdown_row(line))
        if normalized in HEADER_MAPS:
            return normalized
    return None


def render_decision_row(row: dict[str, Any], active_header: tuple[str, ...]) -> str:
    mapping = HEADER_MAPS.get(active_header)
    if mapping is None:
        active_header = tuple(HEADER)
        mapping = HEADER_MAPS[active_header]

    public_values = {key: row.get(key, "") for key in HEADER}
    source_to_public = {source: public for public, source in mapping.items()}
    values: list[Any] = []
    for column in active_header:
        public_key = source_to_public.get(column)
        values.append(public_values.get(public_key, "") if public_key else row.get(column, ""))
    return "| " + " | ".join(markdown_escape(value) for value in values) + " |\n"


def render_decision_header(active_header: tuple[str, ...]) -> str:
    return (
        "| "
        + " | ".join(active_header)
        + " |\n| "
        + " | ".join("---" for _ in active_header)
        + " |\n"
    )


def read_decisions(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    rows: list[dict[str, str]] = []
    active_header: tuple[str, ...] | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line.startswith("|") or "---" in line:
            continue
        cells = split_markdown_row(line)
        normalized = normalize_header(cells)
        if normalized in HEADER_MAPS:
            active_header = normalized
            continue
        row = decision_row_from_cells(cells, active_header)
        if row is None:
            continue
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
    active_header = active_decision_header(path)
    header = active_header or tuple(HEADER)
    needs_header = active_header is None
    prefix = ""
    if path.exists() and path.stat().st_size > 0:
        text = path.read_text(encoding="utf-8")
        if text and not text.endswith("\n"):
            prefix = "\n"

    line = render_decision_row(row, header)
    with path.open("a", encoding="utf-8") as handle:
        if prefix:
            handle.write(prefix)
        if needs_header:
            handle.write(render_decision_header(header))
        handle.write(line)


def normalize_related_artifacts(values: Iterable[str]) -> str:
    artifacts = [str(value).strip() for value in values if str(value).strip()]
    return "; ".join(artifacts) if artifacts else "none"
