"""Delivered-project outcome index for the local console.

The generated files are rebuildable reporting artifacts. Source-of-truth state
stays in accepted_outputs_index.md, task folders, review artifacts, and ledgers.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from async_research_workflow.scripts import update_accepted_outputs_index as accepted_index


SUCCESS = 0
INVALID = 2
PROJECT_SCHEMA_VERSION = "delivered_project_v1.0"
SUMMARY_SCHEMA_VERSION = "delivered_projects_summary_v1.0"
OUTCOMES_DIR = "outcomes"
PROJECTS_JSONL = "delivered_projects.jsonl"
SUMMARY_JSON = "delivered_projects_summary.json"
TERMINAL_STATUSES = {"accepted", "synthesized", "rejected", "paused"}
DEFAULT_STATUS = "accepted"
UNAVAILABLE = "unavailable"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def iso_timestamp(now: datetime) -> str:
    return now.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_now(value: str | None) -> datetime | None:
    if not value:
        return utc_now()
    return accepted_index.parse_datetime(value)


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def normalize_text(value: Any, fallback: str = UNAVAILABLE) -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text if text else fallback


def normalize_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        text = value.strip()
        if not text or text.lower() == "none":
            return []
        return [item.strip() for item in text.replace(";", ",").split(",") if item.strip()]
    return []


def numeric_value(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value)
        except ValueError:
            return None
    return None


def relative_path(ops_dir: Path, path: Path) -> str:
    try:
        return path.relative_to(ops_dir).as_posix()
    except ValueError:
        return path.as_posix()


def maybe_file_link(ops_dir: Path, label: str, path: Path) -> dict[str, Any]:
    return {
        "label": label,
        "path": str(path),
        "relative_path": relative_path(ops_dir, path),
        "exists": path.exists(),
    }


def status_entries(ops_dir: Path) -> dict[str, dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    for status_path in sorted((ops_dir / "tasks").glob("*/status.json")):
        payload = read_json(status_path)
        if not payload:
            continue
        task_id = normalize_text(payload.get("id"), status_path.parent.name)
        entries[task_id] = {
            "task_id": task_id,
            "task_dir": status_path.parent,
            "status_path": status_path,
            "status": payload,
        }
    return entries


def accepted_rows_by_task(ops_dir: Path, now: datetime) -> dict[str, dict[str, str]]:
    rows = accepted_index.read_index_rows(ops_dir / accepted_index.DEFAULT_INDEX_NAME, now=now)
    return {row["task_id"]: row for row in rows if row.get("task_id")}


def idea_id_from_status(status: dict[str, Any]) -> str:
    idea_id = normalize_text(status.get("catalog_idea_id"), "")
    if idea_id:
        return idea_id
    promotion = status.get("catalog_promotion")
    if isinstance(promotion, dict):
        return normalize_text(promotion.get("catalog_idea_id"), "")
    return ""


def idea_snapshot(ops_dir: Path, status: dict[str, Any]) -> dict[str, Any]:
    idea_id = idea_id_from_status(status)
    if not idea_id:
        return {"idea_id": UNAVAILABLE, "score": UNAVAILABLE, "score_breakdown": {}, "path": None}
    path = ops_dir / "ideas" / f"{idea_id}.json"
    payload = read_json(path)
    score = payload.get("score") if isinstance(payload.get("score"), dict) else {}
    weighted = (
        score.get("weighted_total")
        if isinstance(score, dict)
        else None
    )
    if weighted is None:
        weighted = payload.get("weighted_score")
    return {
        "idea_id": idea_id,
        "score": weighted if weighted is not None else UNAVAILABLE,
        "score_breakdown": score if isinstance(score, dict) else {},
        "path": str(path) if path.exists() else None,
    }


def aggregate_disagreement(aggregate: dict[str, Any]) -> bool:
    disagreements = aggregate.get("disagreements")
    return isinstance(disagreements, list) and any(str(item).strip().lower() not in {"", "none"} for item in disagreements)


def review_snapshot(status: dict[str, Any], task_dir: Path | None) -> dict[str, Any]:
    aggregate = read_json(task_dir / "review_panel" / "aggregate.json") if task_dir is not None else {}
    acceptance = read_json(task_dir / "review_panel" / "result_acceptance.json") if task_dir is not None else {}
    panel = acceptance.get("reviewer_panel") if isinstance(acceptance.get("reviewer_panel"), dict) else {}
    review_policy = status.get("review_policy") if isinstance(status.get("review_policy"), dict) else {}
    reviews = aggregate.get("reviews") if isinstance(aggregate.get("reviews"), list) else []
    return {
        "aggregate_decision": normalize_text(panel.get("aggregate_decision") or aggregate.get("aggregate_decision")),
        "review_tier": panel.get("tier") if panel.get("tier") is not None else review_policy.get("tier", UNAVAILABLE),
        "reviewer_count": panel.get("reviewer_count") if panel.get("reviewer_count") is not None else len(reviews),
        "disagreement": bool(panel.get("disagreement_present")) or aggregate_disagreement(aggregate),
        "scorecard": acceptance.get("scorecard") if isinstance(acceptance.get("scorecard"), dict) else {},
        "result_acceptance_route": normalize_text(acceptance.get("route")),
        "result_acceptance_decision": normalize_text(acceptance.get("recommended_decision")),
        "acceptance": acceptance,
        "aggregate": aggregate,
    }


def count_worker_runs(task_dir: Path | None, review: dict[str, Any]) -> int:
    run_ids: set[str] = set()
    acceptance = review.get("acceptance") if isinstance(review.get("acceptance"), dict) else {}
    analysis_run = acceptance.get("analysis_run") if isinstance(acceptance.get("analysis_run"), dict) else {}
    if analysis_run.get("run_id"):
        run_ids.add(str(analysis_run["run_id"]))
    if task_dir is not None:
        for path in task_dir.glob("artifacts/**/run_manifest.json"):
            payload = read_json(path)
            run_ids.add(normalize_text(payload.get("run_id"), path.parent.name))
    return len(run_ids)


def cost_by_task(ops_dir: Path) -> dict[str, float]:
    path = ops_dir / "cost_ledger.csv"
    if not path.exists():
        return {}
    totals: dict[str, float] = {}
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                task_id = normalize_text(row.get("item_id"), "")
                if not task_id:
                    continue
                amount = numeric_value(row.get("amount_usd"))
                if amount is None:
                    amount = (numeric_value(row.get("api_usd")) or 0.0) + (numeric_value(row.get("compute_usd")) or 0.0)
                totals[task_id] = round(totals.get(task_id, 0.0) + amount, 6)
    except (OSError, UnicodeDecodeError, csv.Error):
        return {}
    return totals


def estimated_cost(status: dict[str, Any]) -> float | str:
    budget = status.get("budget") if isinstance(status.get("budget"), dict) else {}
    api = numeric_value(budget.get("max_api_usd")) or 0.0
    compute = numeric_value(budget.get("max_compute_usd")) or 0.0
    total = api + compute
    return round(total, 6) if total > 0 else UNAVAILABLE


def elapsed_days(status: dict[str, Any], accepted_date: str) -> float | str:
    created = accepted_index.parse_datetime(status.get("created_at"))
    delivered = accepted_index.parse_datetime(accepted_date or status.get("updated_at"))
    if created is None or delivered is None:
        return UNAVAILABLE
    return round(max(0.0, (delivered - created).total_seconds() / 86400), 2)


def main_problem(status: dict[str, Any], row: dict[str, str]) -> str:
    human_gate = status.get("human_gate") if isinstance(status.get("human_gate"), dict) else {}
    for value in (
        human_gate.get("reason"),
        human_gate.get("details"),
        status.get("human_gate_reason"),
        row.get("caveats"),
        status.get("last_transition_reason"),
    ):
        text = normalize_text(value, "")
        if text and text.lower() != "none":
            return text
    return UNAVAILABLE


def project_links(ops_dir: Path, task_dir: Path | None, row: dict[str, str], idea: dict[str, Any]) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    evidence_link = normalize_text(row.get("evidence_link"), "")
    if evidence_link and evidence_link.lower() != "none":
        path = ops_dir / evidence_link if not Path(evidence_link).is_absolute() else Path(evidence_link)
        links.append(maybe_file_link(ops_dir, "Accepted memory evidence", path))
    if task_dir is not None:
        links.extend(
            [
                maybe_file_link(ops_dir, "Task brief", task_dir / "task.md"),
                maybe_file_link(ops_dir, "Status JSON", task_dir / "status.json"),
                maybe_file_link(ops_dir, "Worker output", task_dir / "worker_output.md"),
                maybe_file_link(ops_dir, "Review aggregate", task_dir / "review_panel" / "aggregate.json"),
                maybe_file_link(ops_dir, "Result acceptance", task_dir / "review_panel" / "result_acceptance.json"),
            ]
        )
    if idea.get("path"):
        links.append(maybe_file_link(ops_dir, "Idea record", Path(str(idea["path"]))))
    return links


def project_from_row(
    ops_dir: Path,
    task_id: str,
    row: dict[str, str],
    entry: dict[str, Any] | None,
    task_costs: dict[str, float],
) -> dict[str, Any]:
    status = entry["status"] if entry else {}
    task_dir = entry["task_dir"] if entry else None
    delivered_status = normalize_text(status.get("status"), "accepted")
    if delivered_status not in TERMINAL_STATUSES:
        delivered_status = "accepted"
    accepted_date = normalize_text(row.get("accepted_date") or status.get("updated_at"), UNAVAILABLE)
    idea = idea_snapshot(ops_dir, status)
    review = review_snapshot(status, task_dir)
    revision_count = status.get("revision_count", UNAVAILABLE)
    worker_runs = count_worker_runs(task_dir, review)
    iteration_count = revision_count + worker_runs if isinstance(revision_count, int) else worker_runs or UNAVAILABLE
    source_ids = normalize_list(row.get("source_ids"))
    actual_cost = task_costs.get(task_id)
    project = {
        "schema_version": PROJECT_SCHEMA_VERSION,
        "project_id": task_id,
        "task_id": task_id,
        "title": normalize_text(row.get("title") or status.get("title"), task_id),
        "delivered_status": delivered_status,
        "accepted_date": accepted_date,
        "synthesized_date": normalize_text(status.get("updated_at"), UNAVAILABLE) if delivered_status == "synthesized" else UNAVAILABLE,
        "project_type": normalize_text(status.get("type")),
        "origin_idea_id": idea["idea_id"],
        "idea_score": idea["score"],
        "idea_score_breakdown": idea["score_breakdown"],
        "review_scorecard": review["scorecard"],
        "aggregate_review_decision": review["aggregate_decision"],
        "review_tier": review["review_tier"],
        "reviewer_count": review["reviewer_count"],
        "reviewer_disagreement": review["disagreement"],
        "iteration_count": iteration_count,
        "revision_count": revision_count,
        "worker_run_count": worker_runs,
        "blocker_count": 1 if status.get("requires_human") else 0,
        "main_blocker": main_problem(status, row),
        "requires_human": bool(status.get("requires_human")),
        "elapsed_days_to_acceptance": elapsed_days(status, accepted_date),
        "estimated_cost_usd": estimated_cost(status),
        "actual_cost_usd": round(actual_cost, 6) if actual_cost is not None else UNAVAILABLE,
        "claim_type": normalize_text(row.get("claim_type")),
        "claim_strength": normalize_text(row.get("claim_strength")),
        "key_finding": normalize_text(row.get("key_finding")),
        "caveats": normalize_text(row.get("caveats")),
        "source_ids": source_ids,
        "revalidation_status": normalize_text(row.get("revalidation_status")),
        "next_recheck_date": normalize_text(row.get("next_recheck_date")),
        "followups": normalize_text(row.get("followups")),
        "evidence_link": normalize_text(row.get("evidence_link")),
        "task_dir": str(task_dir) if task_dir is not None else UNAVAILABLE,
        "links": project_links(ops_dir, task_dir, row, idea),
    }
    return project


def terminal_task_row(status: dict[str, Any], task_dir: Path, now: datetime) -> dict[str, str]:
    accepted_date = accepted_index.iso_date(status.get("updated_at") or status.get("created_at") or iso_timestamp(now))
    result = status.get("result") if isinstance(status.get("result"), dict) else {}
    return accepted_index.canonical_index_row(
        {
            "accepted_date": accepted_date,
            "task_id": normalize_text(status.get("id"), task_dir.name),
            "title": normalize_text(status.get("title"), task_dir.name),
            "key_finding": normalize_text(result.get("key_finding") or status.get("last_transition_reason")),
            "claim_type": accepted_index.normalize_claim_type(result.get("claim_type"), str(status.get("type") or "")),
            "source_ids": accepted_index.join_list(accepted_index.source_ids_for_task(status, task_dir)),
            "claim_strength": normalize_text(result.get("claim_strength"), "none"),
            "caveats": normalize_text(result.get("caveats"), "none"),
            "followups": normalize_text(result.get("followups"), "none"),
            "evidence_link": relative_path(ops_dir=task_dir.parent.parent, path=task_dir),
        },
        now=now,
    )


def build_index(ops_dir: Path, now: datetime | None = None) -> dict[str, Any]:
    current = now or utc_now()
    status_by_task = status_entries(ops_dir)
    accepted_rows = accepted_rows_by_task(ops_dir, current)
    task_costs = cost_by_task(ops_dir)
    projects: dict[str, dict[str, Any]] = {}
    for task_id, row in accepted_rows.items():
        projects[task_id] = project_from_row(ops_dir, task_id, row, status_by_task.get(task_id), task_costs)
    for task_id, entry in status_by_task.items():
        status = entry["status"]
        if status.get("status") not in TERMINAL_STATUSES or task_id in projects:
            continue
        row = terminal_task_row(status, entry["task_dir"], current)
        projects[task_id] = project_from_row(ops_dir, task_id, row, entry, task_costs)
    ordered = sorted(projects.values(), key=lambda item: (str(item.get("accepted_date")), str(item.get("task_id"))), reverse=True)
    summary = summary_for_projects(ops_dir, ordered, current)
    return {
        "ok": True,
        "generated_at": iso_timestamp(current),
        "projects": ordered,
        "summary": summary,
        "paths": {
            "projects_jsonl": str(ops_dir / OUTCOMES_DIR / PROJECTS_JSONL),
            "summary_json": str(ops_dir / OUTCOMES_DIR / SUMMARY_JSON),
        },
    }


def average(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 3)


def summary_for_projects(ops_dir: Path, projects: list[dict[str, Any]], now: datetime) -> dict[str, Any]:
    rejected_count = sum(1 for item in projects if item.get("delivered_status") == "rejected")
    accepted_count = sum(1 for item in projects if item.get("delivered_status") == "accepted")
    synthesized_count = sum(1 for item in projects if item.get("delivered_status") == "synthesized")
    paused_count = sum(1 for item in projects if item.get("delivered_status") == "paused")
    denominator = accepted_count + synthesized_count + rejected_count
    numeric_iterations = [float(item["iteration_count"]) for item in projects if isinstance(item.get("iteration_count"), (int, float))]
    numeric_costs = [float(item["actual_cost_usd"]) for item in projects if isinstance(item.get("actual_cost_usd"), (int, float))]
    revalidation_counts: dict[str, int] = {}
    for project in projects:
        status = normalize_text(project.get("revalidation_status"))
        revalidation_counts[status] = revalidation_counts.get(status, 0) + 1
    return {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "generated_at": iso_timestamp(now),
        "outcomes_dir": str(ops_dir / OUTCOMES_DIR),
        "project_count": len(projects),
        "accepted_count": accepted_count,
        "synthesized_count": synthesized_count,
        "rejected_count": rejected_count,
        "paused_count": paused_count,
        "acceptance_rate": round((accepted_count + synthesized_count) / denominator, 3) if denominator else UNAVAILABLE,
        "average_iterations": average(numeric_iterations) if numeric_iterations else UNAVAILABLE,
        "total_actual_cost_usd": round(sum(numeric_costs), 6) if numeric_costs else UNAVAILABLE,
        "revalidation_counts": dict(sorted(revalidation_counts.items())),
        "claim_strength_counts": count_by_field(projects, "claim_strength"),
    }


def count_by_field(projects: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for project in projects:
        value = normalize_text(project.get(field))
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def write_index(ops_dir: Path, projects: list[dict[str, Any]], summary: dict[str, Any]) -> tuple[Path, Path]:
    outcomes_dir = ops_dir / OUTCOMES_DIR
    projects_path = outcomes_dir / PROJECTS_JSONL
    summary_path = outcomes_dir / SUMMARY_JSON
    jsonl = "".join(json.dumps(project, sort_keys=True) + "\n" for project in projects)
    atomic_write_text(projects_path, jsonl)
    atomic_write_json(summary_path, summary)
    return projects_path, summary_path


def filter_projects(projects: list[dict[str, Any]], status: str) -> list[dict[str, Any]]:
    if status == "all":
        return projects
    return [project for project in projects if project.get("delivered_status") == status]


def run_refresh(args: argparse.Namespace) -> int:
    now = parse_now(args.now)
    if now is None:
        print_json({"ok": False, "reason": "invalid_now", "now": args.now})
        return INVALID
    index = build_index(args.ops_dir, now=now)
    projects_path, summary_path = write_index(args.ops_dir, index["projects"], index["summary"])
    print_json(
        {
            "ok": True,
            "action": "outcomes_refreshed",
            "project_count": len(index["projects"]),
            "projects_jsonl": str(projects_path),
            "summary_json": str(summary_path),
            "summary": index["summary"],
        }
    )
    return SUCCESS


def run_list(args: argparse.Namespace) -> int:
    now = parse_now(args.now)
    if now is None:
        print_json({"ok": False, "reason": "invalid_now", "now": args.now})
        return INVALID
    index = build_index(args.ops_dir, now=now)
    rows = filter_projects(index["projects"], args.status)
    print_json(
        {
            "ok": True,
            "status": args.status,
            "count": len(rows),
            "projects": rows,
        }
    )
    return SUCCESS


def run_summary(args: argparse.Namespace) -> int:
    now = parse_now(args.now)
    if now is None:
        print_json({"ok": False, "reason": "invalid_now", "now": args.now})
        return INVALID
    index = build_index(args.ops_dir, now=now)
    print_json({"ok": True, "summary": index["summary"]})
    return SUCCESS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build delivered-project outcome indexes.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name, help_text, runner in (
        ("refresh", "Refresh generated delivered-project outcome files.", run_refresh),
        ("list", "List delivered projects from source artifacts.", run_list),
        ("summary", "Summarize delivered-project outcome stats.", run_summary),
    ):
        sub = subparsers.add_parser(name, help=help_text)
        sub.add_argument("ops_dir", type=Path, help="research_ops directory.")
        sub.add_argument("--now", help="Override current time for deterministic freshness checks.")
        if name == "list":
            sub.add_argument("--status", choices=["all", *sorted(TERMINAL_STATUSES)], default=DEFAULT_STATUS)
        sub.set_defaults(func=runner)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
