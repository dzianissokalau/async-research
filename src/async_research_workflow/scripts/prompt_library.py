"""Repo-backed prompt library helpers for the local console and CLI."""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from async_research_workflow.scripts.decision_log import append_decision


SUCCESS = 0
VALIDATION_FAILED = 2
INVALID_REQUEST = 3
MALFORMED = 4
SCHEMA_VERSION = "1.0"

REQUIRED_PROMPT_FIELDS = ("prompt_id", "version", "role", "status", "updated_at", "updated_by")
REQUIRED_PROMPT_SECTIONS = {
    "role": "role",
    "allowed_files": "allowed files",
    "forbidden_files": "forbidden files",
    "task_selection_rule": "task selection rule",
    "max_task_count": "max task count",
    "max_time": "max time",
    "output_file": "output file",
    "status_transition": "status transition",
    "revision_counter_handling": "revision counter",
    "stop_conditions": "stop condition",
    "cost_and_escalation_limits": "cost and escalation",
}
ESCALATION_POLICY_REF = "research_ops/escalation_policy.md"


@dataclass(frozen=True)
class PromptSpec:
    prompt_id: str
    role: str
    version: str
    title: str
    output_file: str
    status_transition: str


DEFAULT_PROMPTS = (
    PromptSpec(
        prompt_id="discovery_scout",
        role="discovery_scout",
        version="discovery_scout_v1.0",
        title="Discovery Scout Prompt",
        output_file="research_ops/discovery_inbox.md",
        status_transition="Record candidate ideas only; do not mutate task status.",
    ),
    PromptSpec(
        prompt_id="planner",
        role="planner",
        version="planner_v1.0",
        title="Planner Prompt",
        output_file="research_ops/tasks/<task-id>/task.md and status.json",
        status_transition="Create ready_for_worker tasks only after promotion checks pass.",
    ),
    PromptSpec(
        prompt_id="worker",
        role="worker",
        version="worker_v1.0",
        title="Worker Prompt",
        output_file="research_ops/tasks/<task-id>/worker_output.md",
        status_transition="Move one task from ready_for_worker to awaiting_review, needs_human, paused, or rejected.",
    ),
    PromptSpec(
        prompt_id="primary_reviewer",
        role="primary_reviewer",
        version="primary_reviewer_v1.0",
        title="Primary Reviewer Prompt",
        output_file="research_ops/tasks/<task-id>/reviews/primary.md",
        status_transition="Write an isolated review; do not update task status directly.",
    ),
    PromptSpec(
        prompt_id="panel_reviewer",
        role="panel_reviewer",
        version="panel_reviewer_v1.0",
        title="Panel Reviewer Prompt",
        output_file="research_ops/tasks/<task-id>/reviews/<role>.md",
        status_transition="Write an isolated specialist review; do not update task status directly.",
    ),
    PromptSpec(
        prompt_id="deliverable_critic",
        role="deliverable_critic",
        version="deliverable_critic_v1.0",
        title="Deliverable Critic Prompt",
        output_file="research_ops/deliverables/critic_reviews/<deliverable-id>-<review-id>.md",
        status_transition="Write the critic artifact and record it with `async-research deliverable critic`; do not treat task acceptance as deliverable readiness.",
    ),
    PromptSpec(
        prompt_id="synthesizer",
        role="synthesizer",
        version="synthesizer_v1.0",
        title="Weekly Synthesizer Prompt",
        output_file="research_ops/weekly_digest.md",
        status_transition="Summarize accepted state; do not change task status.",
    ),
)
DEFAULT_PROMPT_BY_ID = {spec.prompt_id: spec for spec in DEFAULT_PROMPTS}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def prompt_root(ops_dir: Path) -> Path:
    return ops_dir / "prompts"


def manifest_path(ops_dir: Path) -> Path:
    return prompt_root(ops_dir) / "versions.json"


def history_path(ops_dir: Path) -> Path:
    return prompt_root(ops_dir) / "history.jsonl"


def prompt_path(ops_dir: Path, prompt_id: str) -> Path:
    return prompt_root(ops_dir) / f"{prompt_id}.md"


def draft_path(ops_dir: Path, prompt_id: str) -> Path:
    return prompt_root(ops_dir) / "drafts" / f"{prompt_id}.md"


def archived_prompt_path(ops_dir: Path, prompt_id: str, version: str) -> Path:
    safe_version = re.sub(r"[^A-Za-z0-9_.-]+", "_", version)
    return prompt_root(ops_dir) / "versions" / prompt_id / f"{safe_version}.md"


def rel_path(ops_dir: Path, path: Path) -> str:
    try:
        return str(path.relative_to(ops_dir))
    except ValueError:
        return str(path)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def parse_front_matter(text: str) -> tuple[dict[str, str], str, list[str]]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text, ["front_matter_missing"]
    closing_index: int | None = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            closing_index = index
            break
    if closing_index is None:
        return {}, text, ["front_matter_unclosed"]
    metadata: dict[str, str] = {}
    errors: list[str] = []
    for line in lines[1:closing_index]:
        if not line.strip():
            continue
        if ":" not in line:
            errors.append(f"front_matter_malformed:{line.strip()}")
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if key:
            metadata[key] = value.strip().strip('"').strip("'")
    body = "\n".join(lines[closing_index + 1 :]).lstrip("\n")
    if text.endswith("\n"):
        body += "\n" if body and not body.endswith("\n") else ""
    return metadata, body, errors


def render_front_matter(metadata: dict[str, str], body: str) -> str:
    lines = ["---"]
    for key in REQUIRED_PROMPT_FIELDS:
        value = metadata.get(key)
        if value is not None:
            lines.append(f"{key}: {value}")
    for key in sorted(k for k in metadata if k not in REQUIRED_PROMPT_FIELDS):
        lines.append(f"{key}: {metadata[key]}")
    lines.append("---")
    lines.append("")
    lines.append(body.rstrip())
    return "\n".join(lines).rstrip() + "\n"


def default_prompt_text(spec: PromptSpec, now: str) -> str:
    body = f"""# {spec.title}

## Role

You are the `{spec.role}` operator prompt for the async research workflow.

## Allowed Files

Work only inside the target `research_ops/` workspace and the specific task,
review, digest, or discovery files named by the job.

## Forbidden Files

Do not edit package source, unrelated task folders, generated history ledgers,
or files outside the active workspace unless a human explicitly expands scope.

## Task Selection Rule

Select only the oldest eligible item for this role. Skip locked, paused,
needs_human, rejected, malformed, or out-of-scope work.

## Max Task Count

Process at most one task or one scheduled unit of work per run.

## Max Time

Stop before the job's configured max runtime. If no schedule limit is supplied,
stay within 30 minutes.

## Output File

Write or update `{spec.output_file}`.

## Status Transition

{spec.status_transition}

## Revision Counter Handling

Preserve `revision_count`, `max_revisions`, and `revision_limit_hit` unless the
role explicitly owns a revision request.

## Stop Conditions

Stop after writing the required output, when validation fails, when a lock is
fresh, when the task needs a human decision, or when source/cost gates block.

## Cost And Escalation Limits

Respect task budgets, source governance, and the deterministic escalation policy
in `{ESCALATION_POLICY_REF}` before doing expensive or risky work.
"""
    if spec.prompt_id == "planner":
        body += """
## Research Brief Gate

For broad research requests, draft or validate a bounded brief before creating
tasks:

- Run `async-research brief draft research_ops --question "<request>" --dry-run`
  or use an existing `research_ops/briefs/research_brief.json`.
- Run `async-research brief validate research_ops/briefs/research_brief.json`.
- If validation reports unresolved questions, credentials, paid services,
  private-data ambiguity, or public-claim gates, stop for a human decision.
- Run `async-research brief apply research_ops research_ops/briefs/research_brief.json --dry-run`
  before creating a task from the brief.
- Use `async-research workflow create-task ... --brief research_ops/briefs/research_brief.json`
  or `async-research idea promote ... --brief research_ops/briefs/research_brief.json`
  only after the brief is ready for planning.

Tiny maintenance tasks do not require a brief when no brief file is present, but
the planner must not start broad research from ambiguous prompts without one.
"""
    if spec.prompt_id == "deliverable_critic":
        body += """
## Critic Review Rubric

Assess target audience and maturity fit, novelty and contribution clarity,
related-work gaps, methods and reproducibility weaknesses, unsupported causal
language, figure/table integration, citation and bibliography quality, prose
clarity, external-reader readiness, and unresolved caveats that should block
maturity promotion.

## Critic Metadata

Record reviewer role, independence type, model or human reviewer when available,
confidence, severity distribution, recommended maturity ceiling, and required
revision rows before any maturity promotion.

## Response Matrix Expectations

Use `async_research_workflow/templates/artifact_templates/critic_review_prompt_template.md`
for the full critic shape and
`async_research_workflow/templates/artifact_templates/review_response_matrix_template.md`
for required response rows. Each critical or major finding should name a
response-matrix row id such as `RRM-0001`, target section, required change, and
recommended owner. Use `async-research deliverable critic --response-matrix-row`
to seed open rows when the critic finding is recorded. Do not close rows
yourself unless the job explicitly includes revision evidence.

## Readiness Boundary

State plainly when accepted source tasks support an internal draft but do not
support the requested external maturity. Never label the deliverable final,
working-paper ready, or submission-ready unless `async-research deliverable
check` passes for that target maturity.
"""
    return render_front_matter(
        {
            "prompt_id": spec.prompt_id,
            "version": spec.version,
            "role": spec.role,
            "status": "active",
            "updated_at": now,
            "updated_by": "system",
        },
        body,
    )


def prompt_ids(ops_dir: Path) -> list[str]:
    ids = set(DEFAULT_PROMPT_BY_ID)
    root = prompt_root(ops_dir)
    if root.exists():
        ids.update(path.stem for path in root.glob("*.md"))
        drafts = root / "drafts"
        if drafts.exists():
            ids.update(path.stem for path in drafts.glob("*.md"))
    return sorted(ids)


def read_text_if_exists(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def normalize_text(value: Any) -> str:
    return str(value if value is not None else "").strip()


def validate_prompt_text(prompt_id: str, text: str) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    metadata, _body, parse_errors = parse_front_matter(text)
    for item in parse_errors:
        errors.append({"field": "front_matter", "reason": item})
    for field in REQUIRED_PROMPT_FIELDS:
        if not normalize_text(metadata.get(field)):
            errors.append({"field": field, "reason": "required_field_missing"})
    if metadata.get("prompt_id") and metadata.get("prompt_id") != prompt_id:
        errors.append({"field": "prompt_id", "reason": "prompt_id_mismatch"})
    if metadata.get("status") and metadata.get("status") not in {"active", "draft"}:
        errors.append({"field": "status", "reason": "unsupported_status"})

    lowered = text.lower()
    for field, snippet in REQUIRED_PROMPT_SECTIONS.items():
        if snippet not in lowered:
            errors.append({"field": field, "reason": "required_section_missing", "expected": snippet})
    if ESCALATION_POLICY_REF.lower() not in lowered:
        errors.append(
            {
                "field": "escalation_policy",
                "reason": "required_reference_missing",
                "expected": ESCALATION_POLICY_REF,
            }
        )
    if len(text.strip()) < 200:
        warnings.append({"field": "body", "reason": "prompt_is_very_short"})
    return {
        "ok": not errors,
        "prompt_id": prompt_id,
        "errors": errors,
        "warnings": warnings,
        "metadata": metadata,
    }


def update_prompt_metadata(text: str, updates: dict[str, str]) -> str:
    metadata, body, _errors = parse_front_matter(text)
    metadata.update(updates)
    return render_front_matter(metadata, body)


def next_version(current: str, prompt_id: str) -> str:
    match = re.match(r"^(.+_v)(\d+)\.(\d+)$", current)
    if match:
        prefix, major, minor = match.groups()
        return f"{prefix}{major}.{int(minor) + 1}"
    return f"{prompt_id}_v1.1"


def read_history(ops_dir: Path, limit: int | None = None) -> list[dict[str, Any]]:
    path = history_path(ops_dir)
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            rows.append({"ok": False, "reason": "malformed_history_row", "raw": raw})
            continue
        if isinstance(parsed, dict):
            rows.append(parsed)
    return rows[-limit:] if limit is not None else rows


def load_manifest(ops_dir: Path) -> dict[str, Any]:
    path = manifest_path(ops_dir)
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "prompts": {}}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {"schema_version": SCHEMA_VERSION, "prompts": {}}
    return parsed if isinstance(parsed, dict) else {"schema_version": SCHEMA_VERSION, "prompts": {}}


def prompt_manifest_entry(ops_dir: Path, prompt_id: str) -> dict[str, Any]:
    active = prompt_path(ops_dir, prompt_id)
    draft = draft_path(ops_dir, prompt_id)
    active_text = read_text_if_exists(active)
    active_metadata, _body, _errors = parse_front_matter(active_text)
    spec = DEFAULT_PROMPT_BY_ID.get(prompt_id)
    role = active_metadata.get("role") or (spec.role if spec else prompt_id)
    version = active_metadata.get("version") or (spec.version if spec else f"{prompt_id}_v1.0")
    return {
        "prompt_id": prompt_id,
        "role": role,
        "active_version": version,
        "active_path": rel_path(ops_dir, active),
        "draft_path": rel_path(ops_dir, draft),
        "updated_at": active_metadata.get("updated_at", ""),
        "updated_by": active_metadata.get("updated_by", ""),
    }


def write_manifest(ops_dir: Path) -> dict[str, Any]:
    prompts = {prompt_id: prompt_manifest_entry(ops_dir, prompt_id) for prompt_id in prompt_ids(ops_dir)}
    payload = {"schema_version": SCHEMA_VERSION, "prompts": prompts}
    atomic_write_json(manifest_path(ops_dir), payload)
    return payload


def prompt_file_plan_entry(ops_dir: Path, prompt_id: str, target: Path, operation: str, text: str) -> dict[str, Any]:
    return {
        "operation": operation,
        "prompt_id": prompt_id,
        "relative_path": rel_path(ops_dir, target),
        "path": str(target),
        "bytes": len(text.encode("utf-8")),
    }


def init_library_plan(
    ops_dir: Path,
    *,
    force: bool = False,
    now: str | None = None,
) -> dict[str, Any]:
    timestamp = now or utc_now()
    would_create: list[dict[str, Any]] = []
    would_update: list[dict[str, Any]] = []
    existing_files: list[dict[str, Any]] = []
    would_append_history: list[dict[str, Any]] = []

    for spec in DEFAULT_PROMPTS:
        text = default_prompt_text(spec, timestamp)
        prompt_changed = False
        for target in (
            prompt_path(ops_dir, spec.prompt_id),
            draft_path(ops_dir, spec.prompt_id),
            archived_prompt_path(ops_dir, spec.prompt_id, spec.version),
        ):
            if target.exists():
                if force:
                    would_update.append(prompt_file_plan_entry(ops_dir, spec.prompt_id, target, "update", text))
                    prompt_changed = True
                else:
                    existing_files.append(
                        {
                            "operation": "keep",
                            "prompt_id": spec.prompt_id,
                            "relative_path": rel_path(ops_dir, target),
                            "path": str(target),
                        }
                    )
            else:
                would_create.append(prompt_file_plan_entry(ops_dir, spec.prompt_id, target, "create", text))
                prompt_changed = True
        if prompt_changed:
            would_append_history.append(
                {
                    "operation": "append_history",
                    "prompt_id": spec.prompt_id,
                    "version": spec.version,
                    "action": "init",
                    "reason": "prompt library initialized",
                    "author": "system",
                    "relative_path": rel_path(ops_dir, history_path(ops_dir)),
                    "path": str(history_path(ops_dir)),
                }
            )

    would_write_manifest = {
        "operation": "write_manifest",
        "relative_path": rel_path(ops_dir, manifest_path(ops_dir)),
        "path": str(manifest_path(ops_dir)),
    }
    return {
        "timestamp": timestamp,
        "would_create": would_create,
        "would_update": would_update,
        "existing_files": existing_files,
        "would_append_history": would_append_history,
        "would_write_manifest": would_write_manifest,
        "would_write": [*would_create, *would_update, *would_append_history, would_write_manifest],
    }


def append_prompt_decision(ops_dir: Path, prompt_id: str, action: str, reason: str, author: str, artifact: Path) -> None:
    append_decision(
        ops_dir / "decisions.md",
        {
            "date": utc_now(),
            "item_id": f"prompt:{prompt_id}",
            "decision": "acknowledge",
            "reason": f"prompt_{action}: {reason}",
            "approver": author,
            "related_artifacts": rel_path(ops_dir, artifact),
        },
    )


def append_history(
    ops_dir: Path,
    *,
    prompt_id: str,
    action: str,
    version: str,
    reason: str,
    author: str,
    path: Path,
    now: str,
    validation: dict[str, Any] | None = None,
    override: bool = False,
) -> dict[str, Any]:
    row = {
        "timestamp": now,
        "prompt_id": prompt_id,
        "action": action,
        "version": version,
        "reason": reason,
        "author": author,
        "path": rel_path(ops_dir, path),
        "override": override,
        "validation_ok": None if validation is None else bool(validation.get("ok")),
    }
    append_jsonl(history_path(ops_dir), row)
    return row


def init_library(
    ops_dir: Path,
    *,
    force: bool = False,
    now: str | None = None,
    dry_run: bool = False,
) -> tuple[int, dict[str, Any]]:
    if not ops_dir.is_dir():
        return INVALID_REQUEST, {
            "ok": False,
            "reason": "ops_dir_missing",
            "message": "Initialize research_ops before creating the prompt library.",
            "changed": False,
            "read_only": True,
            "dry_run": dry_run,
        }
    timestamp = now or utc_now()
    root = prompt_root(ops_dir)
    if dry_run:
        plan = init_library_plan(ops_dir, force=force, now=timestamp)
        changed = bool(plan["would_create"] or plan["would_update"])
        return SUCCESS, {
            "ok": True,
            "action": "prompt_library_init_planned",
            "changed": changed,
            "read_only": True,
            "dry_run": True,
            "force": force,
            "prompts_dir": str(root),
            "timestamp": plan["timestamp"],
            "would_create": plan["would_create"],
            "would_update": plan["would_update"],
            "existing_files": plan["existing_files"],
            "would_append_history": plan["would_append_history"],
            "would_write_manifest": plan["would_write_manifest"],
            "would_write": plan["would_write"],
            "next_step": (
                "rerun without --dry-run to apply this prompt library initialization plan"
                if changed
                else "prompt library is already initialized; no prompt files would be created or updated"
            ),
        }
    created: list[str] = []
    updated: list[str] = []
    root.mkdir(parents=True, exist_ok=True)
    (root / "drafts").mkdir(parents=True, exist_ok=True)
    (root / "versions").mkdir(parents=True, exist_ok=True)
    for spec in DEFAULT_PROMPTS:
        text = default_prompt_text(spec, timestamp)
        active = prompt_path(ops_dir, spec.prompt_id)
        draft = draft_path(ops_dir, spec.prompt_id)
        archive = archived_prompt_path(ops_dir, spec.prompt_id, spec.version)
        prompt_changed = False
        for target in (active, draft, archive):
            existed = target.exists()
            if existed and not force:
                continue
            atomic_write_text(target, text)
            prompt_changed = True
            (updated if existed else created).append(rel_path(ops_dir, target))
        if prompt_changed and active.exists():
            append_history(
                ops_dir,
                prompt_id=spec.prompt_id,
                action="init",
                version=spec.version,
                reason="prompt library initialized",
                author="system",
                path=active,
                now=timestamp,
            )
    manifest = write_manifest(ops_dir)
    changed = bool(created or updated)
    return SUCCESS, {
        "ok": True,
        "action": "prompt_library_initialized",
        "changed": changed,
        "read_only": False,
        "prompts_dir": str(root),
        "created": created,
        "updated": updated,
        "manifest": manifest,
    }


def unified_diff(active_text: str, draft_text: str, prompt_id: str) -> str:
    return "\n".join(
        difflib.unified_diff(
            active_text.splitlines(),
            draft_text.splitlines(),
            fromfile=f"{prompt_id}.active",
            tofile=f"{prompt_id}.draft",
            lineterm="",
        )
    )


def schedule_bindings(ops_dir: Path) -> dict[str, list[dict[str, Any]]]:
    path = ops_dir / "schedules.json"
    if not path.exists():
        return {}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    raw_jobs: Any
    if isinstance(parsed, dict):
        raw_jobs = parsed.get("jobs") or parsed.get("schedules") or []
    else:
        raw_jobs = parsed
    if not isinstance(raw_jobs, list):
        return {}
    bindings: dict[str, list[dict[str, Any]]] = {}
    for item in raw_jobs:
        if not isinstance(item, dict):
            continue
        prompt_id = normalize_text(item.get("prompt_id") or item.get("prompt"))
        if not prompt_id and isinstance(item.get("prompt_binding"), dict):
            prompt_id = normalize_text(item["prompt_binding"].get("prompt_id"))
        if not prompt_id:
            continue
        binding = {
            "job_id": normalize_text(item.get("job_id") or item.get("id") or item.get("name")) or "unavailable",
            "status": normalize_text(item.get("status")) or "unavailable",
            "prompt_version": normalize_text(item.get("prompt_version"))
            or normalize_text((item.get("prompt_binding") or {}).get("prompt_version"))
            or "unavailable",
        }
        bindings.setdefault(prompt_id, []).append(binding)
    return bindings


def library_snapshot(ops_dir: Path) -> dict[str, Any]:
    root = prompt_root(ops_dir)
    bindings = schedule_bindings(ops_dir)
    manifest = load_manifest(ops_dir)
    rows: list[dict[str, Any]] = []
    for prompt_id in prompt_ids(ops_dir):
        active = prompt_path(ops_dir, prompt_id)
        draft = draft_path(ops_dir, prompt_id)
        active_text = read_text_if_exists(active)
        draft_text = read_text_if_exists(draft)
        active_validation = validate_prompt_text(prompt_id, active_text) if active_text else {"ok": False, "errors": []}
        draft_validation = validate_prompt_text(prompt_id, draft_text) if draft_text else {"ok": False, "errors": []}
        active_metadata = active_validation.get("metadata", {})
        draft_metadata = draft_validation.get("metadata", {})
        diff_text = unified_diff(active_text, draft_text, prompt_id) if active_text or draft_text else ""
        rows.append(
            {
                "prompt_id": prompt_id,
                "role": active_metadata.get("role") or draft_metadata.get("role") or prompt_id,
                "active_version": active_metadata.get("version", ""),
                "draft_version": draft_metadata.get("version", ""),
                "active_status": active_metadata.get("status", ""),
                "draft_status": draft_metadata.get("status", ""),
                "active_path": str(active),
                "draft_path": str(draft),
                "active_exists": active.exists(),
                "draft_exists": draft.exists(),
                "active_text": active_text,
                "draft_text": draft_text,
                "active_validation": active_validation,
                "draft_validation": draft_validation,
                "has_draft_changes": active_text != draft_text,
                "diff": diff_text,
                "schedule_bindings": bindings.get(prompt_id, []),
            }
        )
    return {
        "available": root.is_dir(),
        "status": "available" if root.is_dir() else "unavailable",
        "prompts_dir": str(root),
        "manifest_path": str(manifest_path(ops_dir)),
        "history_path": str(history_path(ops_dir)),
        "manifest": manifest,
        "prompts": rows,
        "prompt_count": len(rows) if root.is_dir() else 0,
        "history": read_history(ops_dir, limit=20),
        "schedule_bindings_path": str(ops_dir / "schedules.json"),
    }


def validate_library(ops_dir: Path, prompt_id: str | None = None) -> tuple[int, dict[str, Any]]:
    if not prompt_root(ops_dir).is_dir():
        return VALIDATION_FAILED, {
            "ok": False,
            "reason": "prompt_library_missing",
            "prompts_dir": str(prompt_root(ops_dir)),
            "changed": False,
            "read_only": True,
            "errors": [{"reason": "prompt_library_missing"}],
        }
    selected = [prompt_id] if prompt_id else prompt_ids(ops_dir)
    results = []
    errors: list[dict[str, Any]] = []
    for item_id in selected:
        path = draft_path(ops_dir, item_id) if draft_path(ops_dir, item_id).exists() else prompt_path(ops_dir, item_id)
        validation = validate_prompt_text(item_id, read_text_if_exists(path))
        validation["path"] = str(path)
        results.append(validation)
        errors.extend({**error, "prompt_id": item_id, "path": str(path)} for error in validation["errors"])
    payload = {
        "ok": not errors,
        "action": "prompt_library_validated",
        "changed": False,
        "read_only": True,
        "prompt_id": prompt_id,
        "results": results,
        "errors": errors,
    }
    return SUCCESS if not errors else VALIDATION_FAILED, payload


def save_draft(
    ops_dir: Path,
    prompt_id: str,
    content: str,
    *,
    reason: str,
    author: str,
    now: str | None = None,
) -> tuple[int, dict[str, Any]]:
    if prompt_id not in prompt_ids(ops_dir):
        return INVALID_REQUEST, {"ok": False, "reason": "unknown_prompt", "prompt_id": prompt_id, "changed": False}
    if not prompt_root(ops_dir).is_dir():
        return INVALID_REQUEST, {"ok": False, "reason": "prompt_library_missing", "changed": False}
    timestamp = now or utc_now()
    target = draft_path(ops_dir, prompt_id)
    atomic_write_text(target, content if content.endswith("\n") else f"{content}\n")
    validation = validate_prompt_text(prompt_id, content)
    _manifest = write_manifest(ops_dir)
    history_row = append_history(
        ops_dir,
        prompt_id=prompt_id,
        action="draft_saved",
        version=validation.get("metadata", {}).get("version", ""),
        reason=reason,
        author=author,
        path=target,
        now=timestamp,
        validation=validation,
    )
    append_prompt_decision(ops_dir, prompt_id, "draft_saved", reason, author, target)
    return SUCCESS, {
        "ok": True,
        "action": "prompt_draft_saved",
        "changed": True,
        "read_only": False,
        "prompt_id": prompt_id,
        "path": str(target),
        "validation": validation,
        "history": history_row,
    }


def activate_prompt(
    ops_dir: Path,
    prompt_id: str,
    *,
    reason: str,
    author: str,
    allow_invalid: bool = False,
    now: str | None = None,
) -> tuple[int, dict[str, Any]]:
    if prompt_id not in prompt_ids(ops_dir):
        return INVALID_REQUEST, {"ok": False, "reason": "unknown_prompt", "prompt_id": prompt_id, "changed": False}
    active = prompt_path(ops_dir, prompt_id)
    draft = draft_path(ops_dir, prompt_id)
    if not draft.exists():
        return INVALID_REQUEST, {"ok": False, "reason": "draft_missing", "prompt_id": prompt_id, "changed": False}
    timestamp = now or utc_now()
    draft_text = draft.read_text(encoding="utf-8")
    validation = validate_prompt_text(prompt_id, draft_text)
    if not validation["ok"] and not allow_invalid:
        return VALIDATION_FAILED, {
            "ok": False,
            "reason": "prompt_validation_failed",
            "message": "Fix the draft or activate with an explicit override.",
            "changed": False,
            "read_only": True,
            "prompt_id": prompt_id,
            "validation": validation,
        }
    override_used = allow_invalid and not validation["ok"]
    active_text = read_text_if_exists(active)
    active_metadata, _body, _errors = parse_front_matter(active_text)
    current_version = active_metadata.get("version") or validation.get("metadata", {}).get("version") or f"{prompt_id}_v1.0"
    new_version = next_version(current_version, prompt_id)
    if active_text:
        archived = archived_prompt_path(ops_dir, prompt_id, current_version)
        if not archived.exists():
            atomic_write_text(archived, active_text)
    role = validation.get("metadata", {}).get("role") or active_metadata.get("role") or prompt_id
    activated = update_prompt_metadata(
        draft_text,
        {
            "prompt_id": prompt_id,
            "version": new_version,
            "role": role,
            "status": "active",
            "updated_at": timestamp,
            "updated_by": author,
            "activation_reason": reason,
        },
    )
    activated_validation = validate_prompt_text(prompt_id, activated)
    atomic_write_text(active, activated)
    atomic_write_text(archived_prompt_path(ops_dir, prompt_id, new_version), activated)
    atomic_write_text(draft, activated)
    manifest = write_manifest(ops_dir)
    history_row = append_history(
        ops_dir,
        prompt_id=prompt_id,
        action="activated",
        version=new_version,
        reason=reason,
        author=author,
        path=active,
        now=timestamp,
        validation=activated_validation,
        override=override_used,
    )
    append_prompt_decision(ops_dir, prompt_id, "activated", reason, author, active)
    return SUCCESS, {
        "ok": True,
        "action": "prompt_activated",
        "changed": True,
        "read_only": False,
        "prompt_id": prompt_id,
        "version": new_version,
        "path": str(active),
        "validation": activated_validation,
        "override": override_used,
        "history": history_row,
        "manifest": manifest,
    }


def diff_prompt(ops_dir: Path, prompt_id: str) -> tuple[int, dict[str, Any]]:
    if prompt_id not in prompt_ids(ops_dir):
        return INVALID_REQUEST, {"ok": False, "reason": "unknown_prompt", "prompt_id": prompt_id}
    active_text = read_text_if_exists(prompt_path(ops_dir, prompt_id))
    draft_text = read_text_if_exists(draft_path(ops_dir, prompt_id))
    return SUCCESS, {
        "ok": True,
        "action": "prompt_diff_rendered",
        "changed": False,
        "read_only": True,
        "prompt_id": prompt_id,
        "diff": unified_diff(active_text, draft_text, prompt_id),
    }


def read_content_file(path: Path | None) -> str:
    if path is None:
        return ""
    return path.read_text(encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage repo-backed prompt library files.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    init = subparsers.add_parser("init", help="Create missing research_ops/prompts files.")
    init.add_argument("ops_dir", type=Path)
    init.add_argument("--force", action="store_true", help="Replace existing default prompt files.")
    init.add_argument("--dry-run", action="store_true", help="Preview prompt library files and history rows without writing.")
    init.add_argument("--now", help="Timestamp for deterministic tests.")
    validate = subparsers.add_parser("validate", help="Validate prompt drafts or active prompt files.")
    validate.add_argument("ops_dir", type=Path)
    validate.add_argument("prompt_id", nargs="?")
    list_cmd = subparsers.add_parser("list", help="List prompt library state.")
    list_cmd.add_argument("ops_dir", type=Path)
    draft = subparsers.add_parser("draft", help="Save a prompt draft from a content file.")
    draft.add_argument("ops_dir", type=Path)
    draft.add_argument("prompt_id")
    draft.add_argument("--content-file", type=Path, required=True)
    draft.add_argument("--message", required=True)
    draft.add_argument("--author", default="human")
    draft.add_argument("--now")
    activate = subparsers.add_parser("activate", help="Activate a prompt draft as the next version.")
    activate.add_argument("ops_dir", type=Path)
    activate.add_argument("prompt_id")
    activate.add_argument("--message", required=True)
    activate.add_argument("--author", default="human")
    activate.add_argument("--allow-invalid", action="store_true")
    activate.add_argument("--now")
    diff = subparsers.add_parser("diff", help="Render active-vs-draft prompt diff.")
    diff.add_argument("ops_dir", type=Path)
    diff.add_argument("prompt_id")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv or []))
    if args.command == "init":
        code, payload = init_library(args.ops_dir, force=args.force, now=args.now, dry_run=args.dry_run)
    elif args.command == "list":
        code, payload = SUCCESS, library_snapshot(args.ops_dir)
        payload.update({"ok": True, "action": "prompt_library_listed", "changed": False, "read_only": True})
    elif args.command == "validate":
        code, payload = validate_library(args.ops_dir, args.prompt_id)
    elif args.command == "draft":
        code, payload = save_draft(
            args.ops_dir,
            args.prompt_id,
            read_content_file(args.content_file),
            reason=args.message,
            author=args.author,
            now=args.now,
        )
    elif args.command == "activate":
        code, payload = activate_prompt(
            args.ops_dir,
            args.prompt_id,
            reason=args.message,
            author=args.author,
            allow_invalid=args.allow_invalid,
            now=args.now,
        )
    elif args.command == "diff":
        code, payload = diff_prompt(args.ops_dir, args.prompt_id)
    else:
        code, payload = INVALID_REQUEST, {"ok": False, "reason": "unknown_command"}
    print_json(payload)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
