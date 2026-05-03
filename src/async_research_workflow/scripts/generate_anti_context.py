#!/usr/bin/env python3
"""Generate cross-task anti-context from accepted and rejected workflow memory."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Iterable, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from update_accepted_outputs_index import DEFAULT_INDEX_NAME, read_index_rows, similarity


SUCCESS = 0
INVALID_REQUEST = 2

SECTION_TITLE = "Cross-Task Anti-Context"
DEFAULT_MAX_ITEMS = 3


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def read_json(path: Path) -> Optional[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def markdown_escape(value: Any) -> str:
    text = str(value if value is not None else "").replace("\n", " ").strip()
    text = re.sub(r"\s+", " ", text)
    return text.replace("|", "\\|") or "none"


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
            cells.append("".join(current).strip().replace("\\|", "|"))
            current = []
        else:
            current.append(char)
    cells.append("".join(current).strip().replace("\\|", "|"))
    return cells


def read_markdown_table(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    header: Optional[list[str]] = None
    rows: list[dict[str, str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line.startswith("|"):
            continue
        cells = split_markdown_row(line)
        if all(set(cell) <= {"-", ":", " "} for cell in cells):
            continue
        if header is None:
            header = [cell.lower().strip().replace(" ", "_") for cell in cells]
            continue
        if len(cells) != len(header):
            continue
        row = {key: value for key, value in zip(header, cells)}
        if any(value.strip() for value in row.values()):
            rows.append(row)
    return rows


def first_content_line(path: Path) -> str:
    if not path.exists():
        return ""
    in_code = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code or not line or line.startswith("#") or line.startswith("|"):
            continue
        if set(line) <= {"-", " "}:
            continue
        return re.sub(r"^[-*]\s+", "", line)
    return ""


def row_text(row: dict[str, str], keys: Iterable[str]) -> str:
    return " ".join(str(row.get(key, "")) for key in keys)


def match_record(query: str, row: dict[str, str], keys: Iterable[str], threshold: float) -> Optional[dict[str, Any]]:
    score = similarity(query, {"title": row_text(row, keys), "key_finding": ""})
    if score < threshold:
        return None
    record: dict[str, Any] = dict(row)
    record["similarity"] = round(score, 3)
    return record


def accepted_matches(ops_dir: Path, query: str, threshold: float, max_items: int) -> list[dict[str, Any]]:
    rows = read_index_rows(ops_dir / DEFAULT_INDEX_NAME)
    matches: list[dict[str, Any]] = []
    for row in rows:
        match = match_record(query, row, ("title", "key_finding", "followups"), threshold)
        if match:
            matches.append(match)
    matches.sort(key=lambda item: item["similarity"], reverse=True)
    return matches[:max_items]


def rejected_idea_matches(ops_dir: Path, query: str, threshold: float, max_items: int) -> list[dict[str, Any]]:
    paths = [
        ops_dir / "discovery" / "rejected_ideas.md",
        ops_dir / "rejected_ideas.md",
    ]
    matches: list[dict[str, Any]] = []
    for path in paths:
        for row in read_markdown_table(path):
            match = match_record(query, row, row.keys(), threshold)
            if match:
                match["source"] = str(path)
                match["item_id"] = match.get("id") or match.get("idea_id") or match.get("item_id") or "rejected_idea"
                matches.append(match)
    matches.sort(key=lambda item: item["similarity"], reverse=True)
    return matches[:max_items]


def task_result(status: dict[str, Any], key: str) -> Any:
    result = status.get("result")
    if isinstance(result, dict):
        return result.get(key)
    return None


def rejected_task_matches(ops_dir: Path, query: str, threshold: float, max_items: int) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for status_path in sorted((ops_dir / "tasks").glob("*/status.json")):
        status = read_json(status_path)
        if not status or status.get("status") not in {"rejected", "paused"}:
            continue
        task_dir = status_path.parent
        row = {
            "item_id": str(status.get("id") or task_dir.name),
            "title": str(status.get("title") or task_dir.name),
            "reason": str(status.get("human_gate_reason") or status.get("last_transition_reason") or ""),
            "key_finding": str(task_result(status, "key_finding") or ""),
            "worker_summary": first_content_line(task_dir / "worker_output.md"),
            "source": str(task_dir),
        }
        match = match_record(query, row, ("title", "reason", "key_finding", "worker_summary"), threshold)
        if match:
            matches.append(match)
    matches.sort(key=lambda item: item["similarity"], reverse=True)
    return matches[:max_items]


def failure_mode(item: dict[str, Any]) -> str:
    for key in ("reason", "kill_reason", "rejection_reason", "failure_mode", "worker_summary", "key_finding"):
        value = item.get(key)
        if isinstance(value, str) and value.strip() and value.strip().lower() != "none":
            return value.strip()
    return "similar prior work was rejected or paused"


def accepted_label(item: dict[str, Any]) -> str:
    task_id = item.get("task_id") or item.get("item_id") or "accepted"
    title = item.get("title") or "accepted output"
    finding = item.get("key_finding") or "no key finding recorded"
    return f"{task_id}: {title} - {finding}"


def rejected_label(item: dict[str, Any]) -> str:
    item_id = item.get("item_id") or item.get("id") or item.get("task_id") or "rejected"
    title = item.get("title") or item.get("candidate") or "rejected approach"
    return f"{item_id}: {title} - {failure_mode(item)}"


def build_bundle(ops_dir: Path, title: str, threshold: float, max_items: int) -> dict[str, Any]:
    accepted = accepted_matches(ops_dir, title, threshold, max_items)
    rejected_ideas = rejected_idea_matches(ops_dir, title, threshold, max_items)
    rejected_tasks = rejected_task_matches(ops_dir, title, threshold, max_items)
    rejected = sorted(rejected_ideas + rejected_tasks, key=lambda item: item["similarity"], reverse=True)[:max_items]
    failure_modes = [failure_mode(item) for item in rejected]

    warnings: list[str] = []
    for item in accepted:
        if item.get("revalidation_status") in {"stale", "due"}:
            warnings.append(
                f"Do not use {item.get('task_id', 'an accepted output')} as a current fact until revalidated; status={item.get('revalidation_status')} next_recheck={item.get('next_recheck_date')}."
            )
        warnings.append(
            f"Do not restate {item.get('task_id', 'an accepted output')} unless the task has a new data path, geography, mechanism, or decision use."
        )
    for item in rejected:
        warnings.append(
            f"Do not repeat {item.get('item_id', item.get('task_id', 'a rejected approach'))} without directly addressing: {failure_mode(item)}."
        )
    if not warnings:
        warnings.append("No similar accepted or rejected prior work found; still state novelty and cheap kill criteria explicitly.")

    return {
        "title": title,
        "threshold": threshold,
        "similar_accepted_findings": accepted,
        "similar_rejected_approaches": rejected,
        "known_failure_modes": failure_modes[:max_items],
        "do_not_repeat_warnings": warnings[: max_items * 2],
    }


def bullet_list(items: list[str]) -> list[str]:
    if not items:
        return ["- none found"]
    return [f"- {item}" for item in items]


def render_markdown(bundle: dict[str, Any]) -> str:
    accepted = [accepted_label(item) for item in bundle["similar_accepted_findings"]]
    rejected = [rejected_label(item) for item in bundle["similar_rejected_approaches"]]
    failures = [str(item) for item in bundle["known_failure_modes"] if str(item).strip()]
    warnings = [str(item) for item in bundle["do_not_repeat_warnings"] if str(item).strip()]
    lines = [
        f"## {SECTION_TITLE}",
        "",
        "### Similar Accepted Findings",
        *bullet_list(accepted),
        "",
        "### Similar Rejected Approaches",
        *bullet_list(rejected),
        "",
        "### Known Failure Modes",
        *bullet_list(failures),
        "",
        "### Do-Not-Repeat Warnings",
        *bullet_list(warnings),
    ]
    return "\n".join(lines).rstrip() + "\n"


def replace_section(text: str, section: str) -> str:
    pattern = re.compile(rf"\n?## {re.escape(SECTION_TITLE)}\n.*?(?=\n## |\Z)", re.DOTALL)
    stripped = pattern.sub("", text).rstrip()
    if stripped:
        return stripped + "\n\n" + section
    return section


def write_bundle(task_dir: Path, markdown: str) -> tuple[Path, Path]:
    anti_context_path = task_dir / "anti_context.md"
    task_path = task_dir / "task.md"
    atomic_write_text(anti_context_path, markdown)
    existing = task_path.read_text(encoding="utf-8") if task_path.exists() else f"# {task_dir.name}\n"
    atomic_write_text(task_path, replace_section(existing, markdown))
    return anti_context_path, task_path


def run_build(args: argparse.Namespace) -> int:
    if not args.title.strip():
        print_json({"ok": False, "reason": "title_required"})
        return INVALID_REQUEST
    bundle = build_bundle(args.ops_dir, args.title, args.threshold, args.max_items)
    markdown = render_markdown(bundle)
    output: dict[str, Any] = {
        "ok": True,
        "title": args.title,
        "accepted_match_count": len(bundle["similar_accepted_findings"]),
        "rejected_match_count": len(bundle["similar_rejected_approaches"]),
        "markdown": markdown,
        "bundle": bundle,
    }
    if args.task_dir:
        anti_context_path, task_path = write_bundle(args.task_dir, markdown)
        output["anti_context_path"] = str(anti_context_path)
        output["task_path"] = str(task_path)
    elif args.output:
        atomic_write_text(args.output, markdown)
        output["anti_context_path"] = str(args.output)
    print_json(output)
    return SUCCESS


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate task anti-context from accepted and rejected prior work.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="Build an anti-context bundle for a proposed task title.")
    build.add_argument("ops_dir", type=Path)
    build.add_argument("--title", required=True)
    build.add_argument("--task-dir", type=Path)
    build.add_argument("--output", type=Path)
    build.add_argument("--threshold", type=float, default=0.2)
    build.add_argument("--max-items", type=int, default=DEFAULT_MAX_ITEMS)

    return parser.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    if args.command == "build":
        return run_build(args)
    print_json({"ok": False, "reason": "unknown_command", "command": args.command})
    return INVALID_REQUEST


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
