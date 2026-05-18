#!/usr/bin/env python3
"""Run package-level async research workflow acceptance checks."""

from __future__ import annotations

import argparse
import contextlib
import importlib
import io
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Iterable

from async_research_workflow.resources import mission_policy_path

SUCCESS = 0
FAILED = 1


def print_json(payload: dict) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def run_module(module_name: str, argv: list[str]) -> tuple[int, dict]:
    module = importlib.import_module(f"async_research_workflow.scripts.{module_name}")
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = int(module.main(argv))
    text = stream.getvalue().strip()
    payload = {}
    if text:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = {"raw_output": text}
    return code, payload


def run_cli(argv: list[str]) -> tuple[int, dict]:
    from async_research_workflow.cli import main as cli_main
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = int(cli_main(argv))
    text = stream.getvalue().strip()
    payload = {}
    if text:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = {"raw_output": text}
    return code, payload


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, payload: dict) -> None:
    write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def file_snapshot(root: Path) -> dict[str, bytes]:
    if not root.exists():
        return {}
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def promotion_write_score() -> dict:
    return {
        "mission_policy_version": "test_policy_v1.0",
        "budget_mode": "normal",
        "decision_impact": 4,
        "novelty": 3,
        "data_availability": 4,
        "feasibility": 4,
        "robustness_risk": 2,
        "cost": 2,
        "killability": 4,
        "reuse_potential": 4,
        "weighted_total": 16.5,
        "promotion_threshold": 14.0,
        "minimum_killability": 3,
        "max_promotions_per_week": 3,
        "budget_pressure_threshold": 0.8,
        "budget_mode_reason": "manual_normal",
        "budget_usage": {
            "monthly_usage_ratio": None,
            "weekly_usage_ratio": None,
            "monthly_cost_usd": 0.0,
            "weekly_cost_usd": 0.0,
            "monthly_budget_usd": None,
            "weekly_budget_usd": None,
        },
        "hard_gate_results": [
            {
                "gate": "research_question_present",
                "passed": True,
                "reason": "question is present",
            }
        ],
        "score_explanation": "Acceptance fixture score for promotion write end-to-end.",
    }


def promotion_write_candidate(idea_id: str) -> dict:
    return {
        "schema_version": "1.0",
        "id": idea_id,
        "status": "promote",
        "title": "Acceptance promotion write idea",
        "question": "Can promotion write mode create one safe task transaction?",
        "why_it_might_matter": "It proves the shipped dry-run/write/dashboard path works end to end.",
        "required_data": ["public fixture data"],
        "minimum_viable_test": "Promote one bounded data-readiness task in a disposable workspace.",
        "baseline": "No task is created before write mode.",
        "main_risks": ["promotion transaction drift"],
        "kill_reason": "Reject if the task, queue row, or promoted_task_id diverge.",
        "score": promotion_write_score(),
        "recommended_next_task": "data_readiness",
        "data_refs": ["DS-0001"],
        "updated_at": "2026-05-08T00:00:00Z",
    }


def write_promotion_acceptance_source(ops_dir: Path) -> None:
    write_text(
        ops_dir / "data_source_audit.md",
        "\n".join(
            [
                "# Data Source Audit",
                "",
                "| source_id | source_name | url_or_domain | publisher_owner | source_tier | approval_status | approved_use_cases | prohibited_use_cases | freshness_window_days | limitations | citation_requirements | last_reviewed_at | approved_by | review_notes |",
                "| --- | --- | --- | --- | --- | --- | --- | --- | ---: | --- | --- | --- | --- | --- |",
                "| DS-0001 | Acceptance fixture source | https://example.test | Fixture | tier_1_official | approved | experiment_planning; accepted_evidence | none | 30 | none | cite fixture | 2026-05-08 | acceptance | ready |",
                "",
            ]
        ),
    )


def run_promotion_write_acceptance(ops_dir: Path) -> tuple[int, dict]:
    idea_id = "IDEA-9901"
    task_id = "TASK-9901"
    task_dir = ops_dir / "tasks" / "TASK-9901-data-readiness"
    steps: list[dict] = []
    failures: list[dict] = []
    written: dict = {}

    def record_step(name: str, code: int, payload: dict) -> None:
        steps.append({"name": name, "exit_code": code, "ok": code == SUCCESS and payload.get("ok", True) is not False})

    code, payload = run_cli(["init", str(ops_dir), "--force"])
    record_step("init", code, payload)
    if code != SUCCESS or payload.get("ok", True) is False:
        failures.append({"reason": "promotion_acceptance_init_failed", "payload": payload})

    if not failures:
        write_promotion_acceptance_source(ops_dir)
        write_json(ops_dir / "ideas" / f"{idea_id}.json", promotion_write_candidate(idea_id))

        code, dry_run = run_cli(["idea", "promote", str(ops_dir), idea_id, "--dry-run"])
        record_step("promotion_dry_run", code, dry_run)
        preflight_hash = dry_run.get("promotion_preflight_hash")
        if code != SUCCESS or dry_run.get("action") != "idea_promotion_planned" or not preflight_hash:
            failures.append({"reason": "promotion_dry_run_failed", "payload": dry_run})

    if not failures:
        code, written = run_cli(
            [
                "idea",
                "promote",
                str(ops_dir),
                idea_id,
                "--write",
                "--preflight-hash",
                str(preflight_hash),
            ]
        )
        record_step("promotion_write", code, written)
        if (
            code != SUCCESS
            or written.get("action") != "idea_promotion_task_written"
            or written.get("task_id") != task_id
        ):
            failures.append({"reason": "promotion_write_failed", "payload": written})

    if not failures:
        code, validation = run_cli(["idea", "catalog", "validate", str(ops_dir)])
        record_step("catalog_validate", code, validation)
        if code != SUCCESS or validation.get("ok") is not True:
            failures.append({"reason": "catalog_validate_failed", "payload": validation})

    if not failures:
        code, dashboard = run_cli(["idea", "catalog", "dashboard", str(ops_dir)])
        record_step("catalog_dashboard", code, dashboard)
        links = dashboard.get("sections", {}).get("idea_to_task_links", [])
        matching_links = [
            item
            for item in links
            if item.get("idea_id") == idea_id
            and item.get("promoted_task_id") == task_id
            and item.get("link_status") == "available"
        ]
        if code != SUCCESS or dashboard.get("ok") is not True or not matching_links:
            failures.append({"reason": "dashboard_link_missing", "payload": dashboard})

    if not failures:
        idea_payload = json.loads((ops_dir / "ideas" / f"{idea_id}.json").read_text(encoding="utf-8"))
        status_payload = json.loads((task_dir / "status.json").read_text(encoding="utf-8"))
        inbox_text = (ops_dir / "inbox.md").read_text(encoding="utf-8")
        queue_text = (ops_dir / "queue.md").read_text(encoding="utf-8")
        proposal_ref = written.get("proposal_ref") if isinstance(written.get("proposal_ref"), dict) else {}
        proposal_id = proposal_ref.get("proposal_id")
        transaction_id = proposal_ref.get("transaction_id")
        idempotency_key = proposal_ref.get("idempotency_key")
        if idea_payload.get("status") != "promoted" or idea_payload.get("promoted_task_id") != task_id:
            failures.append({"reason": "idea_promotion_state_mismatch", "payload": idea_payload})
        if status_payload.get("catalog_idea_id") != idea_id or status_payload.get("id") != task_id:
            failures.append({"reason": "task_status_mismatch", "payload": status_payload})
        if not proposal_id or not transaction_id or not idempotency_key:
            failures.append({"reason": "proposal_ref_metadata_missing", "proposal_ref": proposal_ref})
        elif (
            str(proposal_id) not in inbox_text
            or str(transaction_id) not in inbox_text
            or str(idempotency_key) not in inbox_text
        ):
            failures.append(
                {
                    "reason": "inbox_proposal_ref_missing",
                    "proposal_id": proposal_id,
                    "transaction_id": transaction_id,
                    "idempotency_key": idempotency_key,
                }
            )
        if f"[{task_id}](tasks/TASK-9901-data-readiness/task.md)" not in queue_text:
            failures.append({"reason": "queue_row_missing", "task_id": task_id})
        record_step("artifact_consistency", SUCCESS if not failures else FAILED, {"ok": not failures})

    if failures:
        return FAILED, {
            "ok": False,
            "action": "promotion_write_end_to_end_failed",
            "idea_id": idea_id,
            "task_id": task_id,
            "ops_dir": str(ops_dir),
            "steps": steps,
            "failures": failures,
        }
    return SUCCESS, {
        "ok": True,
        "action": "promotion_write_end_to_end_passed",
        "idea_id": idea_id,
        "task_id": task_id,
        "task_dir": str(task_dir),
        "ops_dir": str(ops_dir),
        "steps": steps,
    }


def run_console_hardening_acceptance(ops_dir: Path) -> tuple[int, dict]:
    from async_research_workflow.console import server
    from async_research_workflow.resources import console_static_path

    now = "2026-05-11T00:00:00Z"
    steps: list[dict] = []
    failures: list[dict] = []

    def record_step(name: str, ok: bool, payload: dict | None = None) -> None:
        steps.append({"name": name, "ok": ok})
        if not ok:
            failures.append({"name": name, "payload": payload or {}})

    code, payload = run_cli(["init", str(ops_dir), "--force"])
    record_step("console_init", code == SUCCESS and payload.get("ok", True) is not False, payload)

    if not failures:
        missing_assets = []
        for name in ("index.html", "styles.css", "app.js"):
            asset = console_static_path(name)
            if not asset.is_file() or not asset.read_bytes():
                missing_assets.append(name)
        record_step("packaged_static_assets", not missing_assets, {"missing_assets": missing_assets})

    if not failures:
        before = file_snapshot(ops_dir)
        checks = [
            ("static_shell", "/", "text/html", b"Async Research Console"),
            ("snapshot_api", f"/api/snapshot?now={now}", "application/json", b"console_snapshot_rendered"),
            ("actions_api", "/api/actions", "application/json", b"console_actions_catalog"),
        ]
        for name, path, expected_media_type, expected_body in checks:
            status, media_type, body = server.response_for_get(path, ops_dir)
            ok = (
                int(status) == 200
                and expected_media_type in media_type
                and expected_body in body
            )
            record_step(
                name,
                ok,
                {
                    "status": int(status),
                    "media_type": media_type,
                    "body": body.decode("utf-8", errors="replace")[:500],
                },
            )
        record_step("console_gets_are_read_only", before == file_snapshot(ops_dir))

    if not failures:
        bad_task = ops_dir / "tasks" / "TASK-ACCEPTANCE-BAD-malformed" / "status.json"
        write_text(bad_task, "{not json")
        before = file_snapshot(ops_dir)
        status, media_type, body = server.response_for_get(f"/api/snapshot?now={now}", ops_dir)
        try:
            snapshot_payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            snapshot_payload = {"raw_output": body.decode("utf-8", errors="replace")}
        malformed_rows = snapshot_payload.get("tasks", {}).get("malformed_statuses", [])
        warnings = snapshot_payload.get("warnings", [])
        ok = (
            int(status) == 200
            and "application/json" in media_type
            and snapshot_payload.get("read_only") is True
            and snapshot_payload.get("changed") is False
            and any(
                "TASK-ACCEPTANCE-BAD-malformed" in str(row.get("status_path", ""))
                for row in malformed_rows
            )
            and any(item.get("reason") == "malformed_task_status" for item in warnings)
            and before == file_snapshot(ops_dir)
        )
        record_step("malformed_status_fails_closed", ok, snapshot_payload)

    if failures:
        return FAILED, {
            "ok": False,
            "action": "console_dashboard_hardening_failed",
            "ops_dir": str(ops_dir),
            "steps": steps,
            "failures": failures,
        }
    return SUCCESS, {
        "ok": True,
        "action": "console_dashboard_hardening_passed",
        "ops_dir": str(ops_dir),
        "steps": steps,
    }


def run_deliverable_maturity_acceptance(ops_dir: Path) -> tuple[int, dict]:
    steps: list[dict] = []
    failures: list[dict] = []

    def record_step(name: str, ok: bool, payload: dict | None = None, exit_code: int = SUCCESS) -> None:
        steps.append({"name": name, "ok": ok, "exit_code": exit_code})
        if not ok:
            failures.append({"name": name, "payload": payload or {}, "exit_code": exit_code})

    code, payload = run_cli(["init", str(ops_dir), "--force"])
    record_step("deliverable_init_workspace", code == SUCCESS and payload.get("ok", True) is not False, payload, code)

    if not failures:
        task_dir = ops_dir / "tasks" / "TASK-9902-internal-draft"
        write_json(
            task_dir / "status.json",
            {
                "schema_version": "1.0",
                "id": "TASK-9902",
                "title": "Accepted internal draft assembly",
                "type": "status_update",
                "status": "accepted",
                "previous_status": "panel_review",
                "last_transition_reason": "acceptance_deliverable_fixture",
                "priority": 3,
                "revision_count": 0,
                "max_revisions": 1,
                "revision_limit_hit": False,
                "allowed_paths": ["research_ops/tasks/TASK-9902-internal-draft/**"],
                "max_minutes": 10,
                "requires_human": False,
                "budget": {"max_api_usd": 0.0, "max_compute_usd": 0.0},
                "human_gate_reason": None,
                "updated_at": "2026-05-18T00:00:00Z",
            },
        )
        code, payload = run_cli(
            [
                "deliverable",
                "init",
                str(ops_dir),
                "--deliverable-id",
                "DELIV-9902",
                "--title",
                "Acceptance internal draft",
                "--output-type",
                "working_paper",
                "--target-maturity",
                "working_paper",
                "--current-maturity",
                "internal_draft",
                "--target-audience",
                "research collaborators",
                "--source-task",
                "TASK-9902",
                "--complete-gate",
                "source_caveat_checks",
                "--complete-gate",
                "claim_strength_review",
                "--complete-gate",
                "task_review",
                "--complete-gate",
                "accepted_evidence_linkage",
                "--complete-gate",
                "caveat_audit",
                "--complete-gate",
                "internal_workflow_disclosure",
                "--complete-gate",
                "draft_completeness_check",
                "--review-independence",
                "same_agent_visible",
                "--now",
                "2026-05-18T00:00:00Z",
            ]
        )
        record_step("deliverable_manifest_write", code == SUCCESS and payload.get("ok") is True, payload, code)

    if not failures:
        code, checked = run_cli(["deliverable", "check", str(ops_dir), "DELIV-9902"])
        reasons = {item.get("reason") for item in checked.get("blockers", [])}
        ok = (
            code == 2
            and checked.get("ok") is False
            and checked.get("source_tasks", [{}])[0].get("accepted") is True
            and "current_maturity_below_target" in reasons
            and "gate_missing" in reasons
            and "review_independence_below_required" in reasons
            and "critic_review_missing" in reasons
        )
        record_step("accepted_task_not_deliverable_ready", ok, checked, code)

        related_work = next((row for row in checked.get("checklist", []) if row.get("gate") == "related_work_synthesis"), {})
        manuscript_ok = (
            checked.get("manuscript_checklist")
            and related_work.get("status") == "missing"
            and related_work.get("satisfied") is False
        )
        record_step("manuscript_quality_gate_blocks_promotion", bool(manuscript_ok), checked, code)

        code, waiver_payload = run_cli(
            [
                "deliverable",
                "target",
                str(ops_dir),
                "DELIV-9902",
                "--manuscript-gate",
                "complete_bibliography=waived_by_human",
            ]
        )
        waiver_reasons = {item.get("reason") for item in waiver_payload.get("errors", [])}
        record_step(
            "manuscript_waiver_requires_rationale",
            code == 3 and "waiver_rationale_required" in waiver_reasons,
            waiver_payload,
            code,
        )

    if not failures:
        code, payload = run_cli(
            [
                "deliverable",
                "init",
                str(ops_dir),
                "--deliverable-id",
                "DELIV-9903",
                "--title",
                "Acceptance critic-reviewed working paper",
                "--output-type",
                "working_paper",
                "--target-maturity",
                "working_paper",
                "--current-maturity",
                "working_paper",
                "--target-audience",
                "research collaborators",
                "--source-task",
                "TASK-9902",
                "--complete-gate",
                "all",
                "--now",
                "2026-05-18T00:00:00Z",
            ]
        )
        record_step("critic_review_fixture_manifest_write", code == SUCCESS and payload.get("ok") is True, payload, code)

    if not failures:
        code, checked = run_cli(["deliverable", "check", str(ops_dir), "DELIV-9903"])
        reasons = {item.get("reason") for item in checked.get("blockers", [])}
        adversarial = next((row for row in checked.get("checklist", []) if row.get("gate") == "adversarial_review"), {})
        record_step(
            "critic_review_required_for_working_paper",
            code == 2 and "critic_review_missing" in reasons and adversarial.get("satisfied") is False,
            checked,
            code,
        )

    if not failures:
        code, critic = run_cli(
            [
                "deliverable",
                "critic",
                str(ops_dir),
                "DELIV-9903",
                "--independence-type",
                "separate_agent",
                "--reviewer",
                "acceptance adversarial critic",
                "--model-or-reviewer",
                "acceptance fixture",
                "--confidence",
                "0.82",
                "--recommended-maturity-ceiling",
                "working_paper",
                "--major",
                "1",
                "--required-revision-row",
                "RRM-ACCEPT-001: address critic finding in response matrix",
                "--response-matrix-row",
                "critique_id=RRM-ACCEPT-001;severity=major;target_section=Related work;issue=Address critic finding in response matrix.;required_change=Close the critic-required revision row.;owner=acceptance owner",
                "--now",
                "2026-05-18T00:00:00Z",
            ]
        )
        critic_ok = (
            code == SUCCESS
            and critic.get("ok") is True
            and critic.get("critic_review", {}).get("satisfied") is True
            and critic.get("critic_review", {}).get("severity_distribution", {}).get("major") == 1
            and critic.get("maturity", {}).get("critic_ceiling") == "working_paper"
        )
        record_step("independent_critic_review_allows_working_paper_ceiling", critic_ok, critic, code)

    if not failures:
        code, checked = run_cli(["deliverable", "check", str(ops_dir), "DELIV-9903"])
        reasons = {item.get("reason") for item in checked.get("blockers", [])}
        record_step(
            "critic_review_seeds_open_response_matrix_rows",
            code == 2
            and checked.get("response_matrix", {}).get("row_count") == 1
            and "response_matrix_open_critical_major" in reasons
            and checked.get("maturity", {}).get("response_matrix_ceiling") == "shareable_memo",
            checked,
            code,
        )

    if not failures:
        code, response = run_cli(
            [
                "deliverable",
                "response",
                str(ops_dir),
                "DELIV-9903",
                "--critique-id",
                "RRM-ACCEPT-001",
                "--source-review",
                "CRITIC-0001",
                "--severity",
                "major",
                "--target-section",
                "Related work",
                "--issue",
                "Address critic finding in response matrix.",
                "--decision",
                "accepted",
                "--required-change",
                "Close the critic-required revision row.",
                "--owner",
                "acceptance owner",
                "--status",
                "closed",
                "--closure-artifact",
                "deliverables/revisions/RRM-ACCEPT-001.md",
                "--now",
                "2026-05-18T00:00:00Z",
            ]
        )
        response_ok = (
            code == SUCCESS
            and response.get("ok") is True
            and response.get("response_matrix", {}).get("status") == "passed"
            and response.get("response_matrix", {}).get("unresolved_critical_major_count") == 0
        )
        record_step("response_matrix_closure_unblocks_promotion", response_ok, response, code)

    if not failures:
        code, checked = run_cli(["deliverable", "check", str(ops_dir), "DELIV-9903"])
        record_step(
            "closed_response_matrix_allows_working_paper",
            code == SUCCESS
            and checked.get("ok") is True
            and checked.get("response_matrix", {}).get("status") == "passed",
            checked,
            code,
        )

    if failures:
        return FAILED, {
            "ok": False,
            "action": "deliverable_maturity_acceptance_failed",
            "ops_dir": str(ops_dir),
            "steps": steps,
            "failures": failures,
        }
    return SUCCESS, {
        "ok": True,
        "action": "deliverable_maturity_acceptance_passed",
        "ops_dir": str(ops_dir),
        "steps": steps,
    }


def check(name: str, code: int, payload: dict, failures: list[dict], checks: list[dict]) -> None:
    ok = code == SUCCESS and payload.get("ok", True) is not False
    checks.append({"name": name, "ok": ok})
    if not ok:
        failures.append({"name": name, "exit_code": code, "payload": payload})


def default_work_dir() -> Path:
    return Path(tempfile.gettempdir()) / "async_research_workflow_acceptance"


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run package-level async research workflow acceptance checks.")
    parser.add_argument("--work-dir", type=Path, default=default_work_dir())
    parser.add_argument("--keep-work-dir", action="store_true")
    return parser.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    if args.work_dir.exists():
        shutil.rmtree(args.work_dir)
    args.work_dir.mkdir(parents=True, exist_ok=True)

    failures: list[dict] = []
    checks: list[dict] = []

    code, payload = run_cli(["version"])
    check("CLI version", code, payload, failures, checks)

    policy = mission_policy_path()
    code, payload = run_module("validate_mission_policy", [str(policy)])
    check("Mission policy validates", code, payload, failures, checks)

    ops_dir = args.work_dir / "research_ops"
    code, payload = run_cli(["init", str(ops_dir), "--force"])
    check("Starter template initializes", code, payload, failures, checks)

    starter_checks = [
        ("Starter schema check", ["schema-check", str(ops_dir)]),
        ("Starter readiness gate", ["readiness", str(ops_dir), "--dry-run"]),
        ("Starter health check", ["health", str(ops_dir), "--dry-run"]),
        ("Starter surface update", ["surface", "update", str(ops_dir)]),
        ("Starter surface validate", ["surface", "validate", str(ops_dir)]),
        ("Starter source validate", ["source", "validate", str(ops_dir)]),
        ("Starter cost summary", ["cost", "summary", str(ops_dir)]),
    ]
    for name, command in starter_checks:
        code, payload = run_cli(command)
        check(name, code, payload, failures, checks)

    code, payload = run_console_hardening_acceptance(args.work_dir / "console-hardening" / "research_ops")
    check("Console dashboard hardening", code, payload, failures, checks)

    code, payload = run_promotion_write_acceptance(args.work_dir / "promotion-write" / "research_ops")
    check("Promotion write end-to-end", code, payload, failures, checks)

    code, payload = run_deliverable_maturity_acceptance(args.work_dir / "deliverable-maturity" / "research_ops")
    check("Deliverable maturity separates acceptance from readiness", code, payload, failures, checks)

    code, payload = run_module("run_autonomy_benchmark", [])
    check("Autonomy benchmark", code, payload, failures, checks)

    code, payload = run_module("simulate_scheduled_week", [str(ops_dir)])
    check("Scheduled week simulation", code, payload, failures, checks)

    if not args.keep_work_dir:
        shutil.rmtree(args.work_dir, ignore_errors=True)

    print_json({
        "ok": not failures,
        "work_dir": str(args.work_dir),
        "work_dir_kept": args.keep_work_dir,
        "check_count": len(checks),
        "checks": checks,
        "failures": failures,
    })
    return SUCCESS if not failures else FAILED


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
