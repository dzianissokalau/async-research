"""Read-only artifact links and Markdown rendering for the local console."""

from __future__ import annotations

import html
import re
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote, unquote


ARTIFACT_ROUTE_PREFIX = "/artifacts/"
MARKDOWN_SUFFIXES = {".md", ".markdown"}
TASK_ROOT_FILES = {
    "task.md",
    "status.json",
    "worker_output.md",
}
TASK_REVIEW_DIRS = {"reviews", "review_panel"}
TASK_ARTIFACT_DIRS = {"artifacts"}
ROOT_MARKDOWN_FILES = {
    "README.md",
    "accepted_outputs_index.md",
    "accepted_memory.md",
    "data_source_audit.md",
    "decisions.md",
    "daily_status.md",
    "human_review_queue.md",
    "weekly_digest.md",
    "research_roadmap.md",
}
ROOT_MARKDOWN_PREFIXES = ("roadmap", "research_roadmap", "accepted", "source")
TOP_LEVEL_MARKDOWN_DIRS = {
    "accepted",
    "accepted_memory",
    "data",
    "idea",
    "ideas",
    "library",
    "roadmap",
    "roadmaps",
    "source",
    "sources",
}


def canonical_ops_dir(ops_dir: Path) -> Path:
    """Return a stable absolute workspace path without requiring it to exist."""
    return Path(ops_dir).expanduser().resolve(strict=False)


def is_markdown_path(path: Path) -> bool:
    return path.suffix.lower() in MARKDOWN_SUFFIXES


def is_task_artifact(parts: tuple[str, ...]) -> bool:
    if len(parts) < 3 or parts[0] != "tasks":
        return False
    task_tail = parts[2:]
    if len(task_tail) == 1 and task_tail[0] in TASK_ROOT_FILES:
        return True
    if task_tail[0] in TASK_REVIEW_DIRS and len(task_tail) == 2:
        suffix = Path(task_tail[-1]).suffix.lower()
        return suffix in {".md", ".json"}
    if task_tail[0] in TASK_ARTIFACT_DIRS and len(task_tail) >= 2:
        return True
    return False


def is_workspace_markdown(parts: tuple[str, ...]) -> bool:
    name = parts[-1] if parts else ""
    path = Path(name)
    if path.suffix.lower() not in MARKDOWN_SUFFIXES:
        return False
    if len(parts) == 1:
        return name in ROOT_MARKDOWN_FILES or name.startswith(ROOT_MARKDOWN_PREFIXES)
    return parts[0] in TOP_LEVEL_MARKDOWN_DIRS


def allowed_artifact_relative(ops_dir: Path, path: Path) -> tuple[bool, str]:
    ops_root = canonical_ops_dir(ops_dir)
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = ops_root / candidate
    resolved = candidate.resolve(strict=False)
    try:
        relative = resolved.relative_to(ops_root)
    except ValueError:
        return False, ""
    parts = relative.parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        return False, ""
    if is_task_artifact(parts) or is_workspace_markdown(parts):
        return True, relative.as_posix()
    return False, ""


def artifact_url(relative_path: str, *, mode: str = "view") -> str:
    encoded = quote(relative_path, safe="/")
    if mode == "raw":
        return f"{ARTIFACT_ROUTE_PREFIX}{encoded}?raw=1"
    if mode == "download":
        return f"{ARTIFACT_ROUTE_PREFIX}{encoded}?download=1"
    return f"{ARTIFACT_ROUTE_PREFIX}{encoded}"


def artifact_link(ops_dir: Path, label: str, path: Path) -> dict[str, Any]:
    ops_root = canonical_ops_dir(ops_dir)
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = ops_root / candidate
    resolved = candidate.resolve(strict=False)
    allowed, relative = allowed_artifact_relative(ops_root, resolved)
    link = {
        "label": label,
        "path": str(resolved),
        "relative_path": relative if allowed else str(path),
        "exists": resolved.exists(),
        "viewer_allowed": allowed,
    }
    if allowed:
        link.update(
            {
                "viewer_url": artifact_url(relative),
                "raw_url": artifact_url(relative, mode="raw"),
                "download_url": artifact_url(relative, mode="download"),
                "is_markdown": is_markdown_path(resolved),
            }
        )
    return link


def resolve_artifact_request(ops_dir: Path, route_path: str) -> tuple[Path | None, dict[str, Any] | None]:
    raw = unquote(route_path).strip()
    if not raw or "\x00" in raw:
        return None, {
            "reason": "artifact_path_missing",
            "message": "Artifact route requires a workspace-relative path.",
            "read_only": True,
            "changed": False,
        }
    pure = PurePosixPath(raw)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        return None, {
            "reason": "artifact_path_not_allowed",
            "message": "Artifact paths must stay inside the selected research_ops workspace.",
            "read_only": True,
            "changed": False,
        }
    candidate = canonical_ops_dir(ops_dir).joinpath(*pure.parts).resolve(strict=False)
    allowed, relative = allowed_artifact_relative(ops_dir, candidate)
    if not allowed:
        return None, {
            "reason": "artifact_path_not_allowed",
            "message": "Artifact viewer is limited to allowlisted read-only research_ops files.",
            "path": relative or raw,
            "read_only": True,
            "changed": False,
        }
    if not candidate.exists():
        return None, {
            "reason": "artifact_missing",
            "message": f"Artifact does not exist: {relative}",
            "path": relative,
            "read_only": True,
            "changed": False,
        }
    if not candidate.is_file():
        return None, {
            "reason": "artifact_not_file",
            "message": f"Artifact is not a file: {relative}",
            "path": relative,
            "read_only": True,
            "changed": False,
        }
    return candidate, None


def render_inline(text: str) -> str:
    escaped = html.escape(text, quote=False)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", escaped)
    return escaped


def split_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def is_table_separator(line: str) -> bool:
    cells = split_table_row(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells)


def render_table(lines: list[str], start: int) -> tuple[str, int]:
    headers = split_table_row(lines[start])
    rows: list[list[str]] = []
    index = start + 2
    while index < len(lines) and "|" in lines[index] and lines[index].strip():
        rows.append(split_table_row(lines[index]))
        index += 1
    header_html = "".join(f"<th>{render_inline(cell)}</th>" for cell in headers)
    row_html = []
    for row in rows:
        cells = row + [""] * max(0, len(headers) - len(row))
        row_html.append("<tr>" + "".join(f"<td>{render_inline(cell)}</td>" for cell in cells[: len(headers)]) + "</tr>")
    return f"<table><thead><tr>{header_html}</tr></thead><tbody>{''.join(row_html)}</tbody></table>", index


def markdown_to_html(markdown: str) -> str:
    lines = markdown.splitlines()
    rendered: list[str] = []
    paragraph: list[str] = []
    list_tag: str | None = None
    in_code = False
    code_lines: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            rendered.append(f"<p>{render_inline(' '.join(paragraph))}</p>")
            paragraph = []

    def close_list() -> None:
        nonlocal list_tag
        if list_tag:
            rendered.append(f"</{list_tag}>")
            list_tag = None

    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_code:
                rendered.append(f"<pre><code>{html.escape(chr(10).join(code_lines))}</code></pre>")
                code_lines = []
                in_code = False
            else:
                flush_paragraph()
                close_list()
                in_code = True
            index += 1
            continue
        if in_code:
            code_lines.append(line)
            index += 1
            continue
        if not stripped:
            flush_paragraph()
            close_list()
            index += 1
            continue
        if index + 1 < len(lines) and "|" in line and is_table_separator(lines[index + 1]):
            flush_paragraph()
            close_list()
            table_html, index = render_table(lines, index)
            rendered.append(table_html)
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading:
            flush_paragraph()
            close_list()
            level = len(heading.group(1))
            rendered.append(f"<h{level}>{render_inline(heading.group(2))}</h{level}>")
            index += 1
            continue
        unordered = re.match(r"^[-*]\s+(.+)$", stripped)
        ordered = re.match(r"^\d+[.)]\s+(.+)$", stripped)
        if unordered or ordered:
            flush_paragraph()
            tag = "ul" if unordered else "ol"
            if list_tag != tag:
                close_list()
                rendered.append(f"<{tag}>")
                list_tag = tag
            item = unordered.group(1) if unordered else ordered.group(1)
            rendered.append(f"<li>{render_inline(item)}</li>")
            index += 1
            continue
        if stripped.startswith(">"):
            flush_paragraph()
            close_list()
            rendered.append(f"<blockquote>{render_inline(stripped.lstrip('>').strip())}</blockquote>")
            index += 1
            continue
        paragraph.append(stripped)
        index += 1

    if in_code:
        rendered.append(f"<pre><code>{html.escape(chr(10).join(code_lines))}</code></pre>")
    flush_paragraph()
    close_list()
    return "\n".join(rendered)


def artifact_view_html(path: Path, ops_dir: Path) -> str:
    allowed, relative = allowed_artifact_relative(ops_dir, path)
    title = relative if allowed else path.name
    try:
        markdown = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        markdown = path.read_text(encoding="utf-8", errors="replace")
    body = markdown_to_html(markdown)
    raw = artifact_url(relative, mode="raw") if allowed else ""
    download = artifact_url(relative, mode="download") if allowed else ""
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{ color-scheme: light; --text: #17212b; --muted: #64717d; --line: #dbe2e8; --bg: #f7f9fb; --panel: #ffffff; --accent: #0f6b78; }}
    body {{ margin: 0; background: var(--bg); color: var(--text); font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; line-height: 1.55; }}
    header {{ position: sticky; top: 0; display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 12px 18px; border-bottom: 1px solid var(--line); background: rgba(255,255,255,0.96); }}
    main {{ max-width: 980px; margin: 0 auto; padding: 24px 18px 48px; }}
    .path {{ min-width: 0; color: var(--muted); font-size: 13px; overflow-wrap: anywhere; }}
    .actions {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    a {{ color: var(--accent); }}
    .actions a {{ padding: 6px 9px; border: 1px solid var(--line); border-radius: 6px; background: var(--panel); text-decoration: none; }}
    h1, h2, h3, h4, h5, h6 {{ line-height: 1.2; margin: 1.2em 0 0.45em; }}
    p, ul, ol, blockquote, pre, table {{ margin: 0 0 1em; }}
    pre {{ overflow: auto; padding: 12px; border: 1px solid var(--line); border-radius: 6px; background: #f2f5f7; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace; font-size: 0.92em; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
    th, td {{ padding: 7px 9px; border: 1px solid var(--line); text-align: left; vertical-align: top; }}
    th {{ background: #eef3f5; }}
    blockquote {{ padding-left: 12px; border-left: 3px solid var(--line); color: var(--muted); }}
  </style>
</head>
<body>
  <header>
    <div class="path">{html.escape(title)}</div>
    <nav class="actions" aria-label="Artifact actions">
      <a href="{html.escape(raw)}" target="_blank" rel="noopener noreferrer">Raw</a>
      <a href="{html.escape(download)}" download>Download</a>
    </nav>
  </header>
  <main>{body}</main>
</body>
</html>
"""


def artifact_error_html(status: int, payload: dict[str, Any]) -> str:
    reason = html.escape(str(payload.get("reason") or "artifact_error"))
    message = html.escape(str(payload.get("message") or "Artifact could not be opened."))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{reason}</title>
  <style>
    body {{ margin: 0; padding: 32px; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #17212b; background: #f7f9fb; }}
    main {{ max-width: 760px; }}
    code {{ overflow-wrap: anywhere; }}
  </style>
</head>
<body>
  <main>
    <h1>{status} {reason}</h1>
    <p>{message}</p>
  </main>
</body>
</html>
"""
