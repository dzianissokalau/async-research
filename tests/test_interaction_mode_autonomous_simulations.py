"""End-to-end interaction mode simulations and gate fixture regressions."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from async_research_workflow import cli
from async_research_workflow.scripts import autonomy_readiness_gate
from async_research_workflow.scripts import decision_log
from async_research_workflow.scripts import deliverable_maturity
from async_research_workflow.scripts import interaction_mode
from async_research_workflow.scripts import needs_human_policy
from async_research_workflow.scripts import validate_transition
from async_research_workflow.scripts.version_metadata import apply_default_versions


ROOT = Path(__file__).resolve().parents[1]
GATE_FIXTURES = ROOT / "tests" / "fixtures" / "interaction_modes" / "needs_human_gate_categories.json"
NOW = "2026-05-22T10:00:00Z"


def run_cli_json(argv: list[str | Path]) -> tuple[int, dict[str, Any]]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = cli.main([str(arg) for arg in argv])
    text = stream.getvalue().strip()
    return code, json.loads(text) if text else {}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_gate_fixtures() -> list[dict[str, Any]]:
    return json.loads(GATE_FIXTURES.read_text(encoding="utf-8"))


def task_name(task_id: str, category: str) -> str:
    return f"{task_id}-{category.replace('_', '-')}-fixture"


def gate_payload(fixture: dict[str, Any]) -> dict[str, Any]:
    category = str(fixture["gate_category"])
    return {
        "policy_version": "phase6_gate_fixture_v1.0",
        "trigger": fixture["trigger"],
        "gate_category": category,
        "gate_categories": [category],
        "triggered_at": NOW,
        "severity": "high" if category in interaction_mode.HARD_STOP_INTERRUPT_CATEGORIES else "medium",
        "reason": f"{category} fixture requires mode policy routing",
        "required_human_decision": "choose the safe route for this fixture",
        "available_decisions": fixture["available_decisions"],
        "default_safe_action": "pause before unsafe progress",
        "retry_behavior": "rerun after policy or human resolution",
        "ledger_update_behavior": "record decisions.md and auto_decisions.md before status mutation",
    }


def write_needs_human_task(ops_dir: Path, task_id: str, fixture: dict[str, Any]) -> Path:
    category = str(fixture["gate_category"])
    task_dir = ops_dir / "tasks" / task_name(task_id, category)
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "task.md").write_text(
        f"# {task_id} {category} fixture\n\nResolve the gate without bypassing policy.\n",
        encoding="utf-8",
    )
    payload = apply_default_versions(
        {
            "schema_version": "1.0",
            "id": task_id,
            "title": f"{category} gate fixture",
            "type": "admin",
            "status": "needs_human",
            "previous_status": "panel_review",
            "last_transition_reason": f"phase6_fixture_{fixture['trigger']}",
            "priority": 2,
            "revision_count": 1 if category == "revision_limit_reached" else 0,
            "max_revisions": 1,
            "revision_limit_hit": category == "revision_limit_reached",
            "created_at": NOW,
            "updated_at": NOW,
            "allowed_paths": [f"research_ops/tasks/{task_dir.name}/**"],
            "allowed_tools": ["read_files", "write_task_files"],
            "allow_browsing": False,
            "allow_code_execution": False,
            "allow_network": False,
            "max_minutes": 10,
            "max_turns": 1,
            "model_tier": "low",
            "review_policy": {
                "tier": 1,
                "required_reviewers": ["primary"],
                "panel_required": False,
                "human_required_for_acceptance": False,
            },
            "requires_human": True,
            "human_gate_reason": f"{category} fixture requires mode policy routing",
            "human_gate": gate_payload(fixture),
            "budget": {"max_api_usd": 0.0, "max_compute_usd": 0.0},
            "result": {
                "recommendation": None,
                "claim_strength": "none",
                "followup_count": 0,
            },
        }
    )
    write_json(task_dir / "status.json", payload)
    return task_dir


def write_accepted_task(ops_dir: Path, task_id: str) -> Path:
    task_dir = ops_dir / "tasks" / f"{task_id}-accepted-source"
    task_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        task_dir / "status.json",
        apply_default_versions(
            {
                "schema_version": "1.0",
                "id": task_id,
                "title": f"{task_id} accepted source fixture",
                "type": "status_update",
                "status": "accepted",
                "previous_status": "panel_review",
                "last_transition_reason": "phase6_deliverable_fixture",
                "priority": 3,
                "revision_count": 0,
                "max_revisions": 1,
                "revision_limit_hit": False,
                "created_at": NOW,
                "updated_at": NOW,
                "allowed_paths": [f"research_ops/tasks/{task_dir.name}/**"],
                "allowed_tools": ["read_files"],
                "allow_browsing": False,
                "allow_code_execution": False,
                "allow_network": False,
                "max_minutes": 10,
                "max_turns": 1,
                "model_tier": "low",
                "requires_human": False,
                "human_gate_reason": None,
                "budget": {"max_api_usd": 0.0, "max_compute_usd": 0.0},
                "result": {
                    "recommendation": "ready",
                    "claim_strength": "suggestive",
                    "followup_count": 0,
                },
            }
        ),
    )
    return task_dir


class InteractionModeAutonomousSimulationTests(unittest.TestCase):
    def init_ops(self, root: Path) -> Path:
        ops_dir = root / "research_ops"
        code, payload = run_cli_json(["init", ops_dir, "--force"])
        self.assertEqual(cli.SUCCESS, code, payload)
        self.assertTrue(payload["ok"])
        return ops_dir

    def set_mode(self, ops_dir: Path, mode: str) -> None:
        code, payload = run_cli_json(["mode", "set", ops_dir, "--mode", mode])
        self.assertEqual(cli.SUCCESS, code, payload)
        self.assertEqual(mode, payload["mode"])

    def fixture_by_category(self, category: str) -> dict[str, Any]:
        return next(item for item in load_gate_fixtures() if item["gate_category"] == category)

    def test_gate_category_fixtures_cover_contract_and_route_by_mode(self) -> None:
        fixtures = load_gate_fixtures()
        fixture_categories = {item["gate_category"] for item in fixtures}
        self.assertEqual(set(interaction_mode.ALL_INTERRUPT_CATEGORIES), fixture_categories)

        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dirs = [
                write_needs_human_task(ops_dir, f"TASK-{9600 + index}", fixture)
                for index, fixture in enumerate(fixtures, start=1)
            ]

            self.set_mode(ops_dir, "manual")
            for fixture, task_dir in zip(fixtures, task_dirs):
                status = read_json(task_dir / "status.json")
                resolution = needs_human_policy.evaluate_policy(ops_dir, task_dir, status)
                self.assertFalse(resolution["can_auto_resolve"], fixture["gate_category"])
                self.assertEqual("manual_mode_requires_explicit_human_decision", resolution["reason"])

            self.set_mode(ops_dir, "autonomous")
            for fixture, task_dir in zip(fixtures, task_dirs):
                expected = fixture["expected_autonomous"]
                status = read_json(task_dir / "status.json")
                resolution = needs_human_policy.evaluate_policy(ops_dir, task_dir, status)
                self.assertEqual(expected["can_auto_resolve"], resolution["can_auto_resolve"], fixture["gate_category"])
                self.assertEqual(fixture["gate_category"], resolution["gate_category"])
                if expected["can_auto_resolve"]:
                    self.assertFalse(resolution["human_required"], fixture["gate_category"])
                    self.assertEqual(expected["target_status"], resolution["target_status"])
                    self.assertEqual(expected["policy_action"], resolution["policy_action"])
                else:
                    self.assertTrue(resolution["human_required"], fixture["gate_category"])
                    self.assertEqual(expected["reason"], resolution["reason"])

    def test_autonomous_workflow_loop_has_zero_human_interrupts_and_complete_audit(self) -> None:
        routine_categories = [
            "quality_uncertainty",
            "source_freshness_or_approval",
            "review_disagreement",
            "idea_prioritization_ambiguity",
            "budget_warning",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            self.set_mode(ops_dir, "autonomous")

            task_dirs: list[Path] = []
            human_interrupt_count = 0
            for index, category in enumerate(routine_categories, start=1):
                task_dir = write_needs_human_task(ops_dir, f"TASK-{9700 + index}", self.fixture_by_category(category))
                task_dirs.append(task_dir)
                code, payload = run_cli_json(["workflow", "advance", task_dir])
                status = read_json(task_dir / "status.json")
                if code != cli.SUCCESS or status.get("requires_human") is True or status.get("status") == "needs_human":
                    human_interrupt_count += 1
                self.assertEqual(cli.SUCCESS, code, payload)
                self.assertEqual("workflow_auto_resolved", payload["action"])
                self.assertEqual("ready_for_worker", status["status"])
                self.assertFalse(status["requires_human"])
                transition_code, transition = validate_transition.validate_payload(
                    status,
                    decisions_path=ops_dir / "decisions.md",
                )
                self.assertEqual(validate_transition.SUCCESS, transition_code, transition)

            self.assertEqual(0, human_interrupt_count)
            auto_rows = decision_log.read_auto_decisions(ops_dir / "auto_decisions.md")
            self.assertEqual(len(routine_categories), len(auto_rows))
            for task_dir, row in zip(task_dirs, auto_rows):
                self.assertEqual("autonomous", row["mode"])
                self.assertEqual("async-research-mode-policy", row["actor"])
                self.assertIn(str(task_dir / "status.json"), row["related_artifacts"])
                self.assertIn(str(ops_dir / "interaction_mode.json"), row["related_artifacts"])
                self.assertIn(str(ops_dir / "decisions.md"), row["related_artifacts"])
                self.assertEqual([], decision_log.auto_decision_row_errors(row))

            code, summary = run_cli_json(["decision", "summarize", ops_dir, "--month", "2026-05"])
            self.assertEqual(cli.SUCCESS, code, summary)
            self.assertEqual(len(routine_categories), summary["auto_decision_count"])
            self.assertEqual(len(routine_categories), summary["framework_policy_decision_count"])
            self.assertTrue(summary["audit_completeness"]["ok"])

    def test_autonomous_workflow_stops_for_hard_blockers_without_audit_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            self.set_mode(ops_dir, "autonomous")
            task_dir = write_needs_human_task(ops_dir, "TASK-9801", self.fixture_by_category("credentials_missing"))

            code, payload = run_cli_json(["workflow", "advance", task_dir])

            self.assertEqual(autonomy_readiness_gate.HUMAN_REQUIRED, code, payload)
            self.assertFalse(payload["ok"])
            self.assertEqual("readiness_dry_run", payload["failed_step"])
            blocker = payload["steps"][1]["stdout_json"]["blockers"][0]
            self.assertEqual("unresolved_needs_human", blocker["check"])
            self.assertEqual("hard_stop_category_requires_human", blocker["details"][0]["policy_reason"])
            status = read_json(task_dir / "status.json")
            self.assertEqual("needs_human", status["status"])
            self.assertTrue(status["requires_human"])
            self.assertEqual([], decision_log.read_auto_decisions(ops_dir / "auto_decisions.md"))

    def test_publication_ready_deliverable_cannot_pass_without_required_gates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            self.set_mode(ops_dir, "autonomous")
            write_accepted_task(ops_dir, "TASK-9901")
            code, payload = run_cli_json(
                [
                    "deliverable",
                    "init",
                    ops_dir,
                    "--deliverable-id",
                    "DELIV-9901",
                    "--title",
                    "Submission-ready autonomy fixture",
                    "--output-type",
                    "manuscript",
                    "--target-maturity",
                    "submission_ready_manuscript",
                    "--current-maturity",
                    "submission_ready_manuscript",
                    "--target-audience",
                    "journal reviewers",
                    "--source-task",
                    "TASK-9901",
                    "--now",
                    NOW,
                ]
            )
            self.assertEqual(cli.SUCCESS, code, payload)

            code, checked = run_cli_json(["deliverable", "check", ops_dir, "DELIV-9901"])

            self.assertEqual(deliverable_maturity.VALIDATION_FAILED, code, checked)
            self.assertFalse(checked["target_ready"])
            self.assertNotEqual("submission_ready_manuscript", checked["maturity"]["verified_ceiling"])
            reasons = {item["reason"] for item in checked["blockers"]}
            self.assertIn("gate_missing", reasons)
            self.assertIn("target_venue_missing", reasons)
            self.assertIn("critic_review_missing", reasons)
            self.assertIn("citation_verification_unresolved", reasons)
            self.assertIn("declared_current_maturity_exceeds_verified_ceiling", {item["reason"] for item in checked["warnings"]})


if __name__ == "__main__":
    unittest.main()
