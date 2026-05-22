"""Regression tests for mode-aware needs_human policy resolution."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from async_research_workflow import cli
from async_research_workflow.scripts import decision_log
from async_research_workflow.scripts import validate_transition


NOW = "2026-05-22T09:00:00Z"


def run_cli_json(argv: list[str | Path]) -> tuple[int, dict]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = cli.main([str(arg) for arg in argv])
    text = stream.getvalue().strip()
    return code, json.loads(text) if text else {}


def file_snapshot(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def write_needs_human_task(
    ops_dir: Path,
    task_id: str,
    *,
    trigger: str,
    gate_category: str,
    available_decisions: list[str],
) -> Path:
    task_dir = ops_dir / "tasks" / f"{task_id}-fixture"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "task.md").write_text(
        "\n".join(
            [
                f"# {task_id} Fixture",
                "",
                "## Objective",
                "",
                "Resolve one bounded test fixture.",
                "",
                "## Scope",
                "",
                f"- Work only inside `research_ops/tasks/{task_id}-fixture/`.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    payload = {
        "schema_version": "1.0",
        "id": task_id,
        "title": f"{task_id} fixture",
        "type": "admin",
        "status": "needs_human",
        "previous_status": "ready_for_worker",
        "last_transition_reason": f"escalation_policy_{trigger}",
        "priority": 2,
        "revision_count": 0,
        "max_revisions": 1,
        "revision_limit_hit": False,
        "allowed_paths": [f"research_ops/tasks/{task_id}-fixture/**"],
        "max_minutes": 10,
        "requires_human": True,
        "budget": {"max_api_usd": 0.0, "max_compute_usd": 0.0},
        "human_gate_reason": f"{gate_category} fixture needs policy routing",
        "updated_at": "2026-05-22T08:55:00Z",
        "human_gate": {
            "policy_version": "escalation_policy_v1.0",
            "trigger": trigger,
            "gate_category": gate_category,
            "gate_categories": [gate_category],
            "triggered_at": "2026-05-22T08:55:00Z",
            "severity": "medium",
            "reason": f"{gate_category} fixture needs policy routing",
            "required_human_decision": "choose a test resolution",
            "available_decisions": available_decisions,
            "default_safe_action": "pause before unsafe progress",
            "retry_behavior": "rerun after a policy or human decision",
            "ledger_update_behavior": "record the decision in decisions.md",
        },
    }
    (task_dir / "status.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return task_dir


class NeedsHumanPolicyTests(unittest.TestCase):
    def init_ops(self, root: Path) -> Path:
        ops_dir = root / "research_ops"
        code, payload = run_cli_json(["init", ops_dir, "--force"])
        self.assertEqual(cli.SUCCESS, code, payload)
        self.assertTrue(payload["ok"])
        return ops_dir

    def test_manual_mode_auto_resolve_dry_run_preserves_human_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            run_cli_json(["mode", "set", ops_dir, "--mode", "manual"])
            task_dir = write_needs_human_task(
                ops_dir,
                "TASK-9001",
                trigger="high_confidence_weak_evidence",
                gate_category="quality_uncertainty",
                available_decisions=["request_revision", "pause", "reject"],
            )
            before = file_snapshot(ops_dir)

            code, payload = run_cli_json(["decision", "auto-resolve-task", ops_dir, task_dir, "--dry-run"])

            self.assertEqual(2, code, payload)
            self.assertFalse(payload["can_auto_resolve"])
            self.assertEqual("manual_mode_requires_explicit_human_decision", payload["reason"])
            self.assertEqual(before, file_snapshot(ops_dir))

    def test_autonomous_mode_auto_resolves_routine_quality_gate_with_policy_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            run_cli_json(["mode", "set", ops_dir, "--mode", "autonomous"])
            task_dir = write_needs_human_task(
                ops_dir,
                "TASK-9002",
                trigger="high_confidence_weak_evidence",
                gate_category="quality_uncertainty",
                available_decisions=["request_revision", "pause", "reject"],
            )
            before = file_snapshot(ops_dir)

            dry_code, dry = run_cli_json(["decision", "auto-resolve-task", ops_dir, task_dir, "--dry-run", "--date", NOW])
            self.assertEqual(cli.SUCCESS, dry_code, dry)
            self.assertTrue(dry["resolution"]["can_auto_resolve"])
            self.assertEqual("ready_for_worker", dry["status"])
            self.assertEqual(before, file_snapshot(ops_dir))

            code, payload = run_cli_json(["decision", "auto-resolve-task", ops_dir, task_dir, "--date", NOW])

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertEqual("auto_resolved", payload["action"])
            self.assertEqual("async-research-mode-policy", payload["decision"]["approver"])
            self.assertEqual(str(ops_dir / "auto_decisions.md"), payload["auto_decisions"])
            self.assertEqual("autonomous", payload["auto_decision"]["mode"])
            self.assertEqual("mode_needs_human_policy_v1.0", payload["auto_decision"]["policy_version"])
            self.assertEqual("ready_for_worker", payload["auto_decision"]["target_status"])
            self.assertEqual("high", payload["auto_decision"]["confidence"])
            self.assertIn("mode_needs_human_policy_v1.0", payload["decision"]["reason"])
            status = json.loads((task_dir / "status.json").read_text(encoding="utf-8"))
            self.assertEqual("ready_for_worker", status["status"])
            self.assertFalse(status["requires_human"])
            self.assertEqual("mode_policy_auto_bounded_revision", status["last_transition_reason"])
            self.assertEqual("quality_uncertainty", status["auto_resolution"]["gate_category"])
            self.assertEqual("high", status["auto_resolution"]["confidence"])
            auto_rows = decision_log.read_auto_decisions(ops_dir / "auto_decisions.md")
            self.assertEqual(1, len(auto_rows))
            self.assertEqual("TASK-9002", auto_rows[0]["item_id"])
            self.assertEqual("async-research-mode-policy", auto_rows[0]["actor"])
            self.assertIn(str(task_dir / "status.json"), auto_rows[0]["related_artifacts"])
            transition_code, transition = validate_transition.validate_payload(status, decisions_path=ops_dir / "decisions.md")
            self.assertEqual(validate_transition.SUCCESS, transition_code, transition)

            summary_code, summary = run_cli_json(["decision", "summarize", ops_dir, "--month", "2026-05"])
            self.assertEqual(cli.SUCCESS, summary_code, summary)
            self.assertEqual(1, summary["framework_policy_decision_count"])
            self.assertEqual(1, summary["auto_decision_count"])
            self.assertEqual({"autonomous": 1}, summary["by_mode"])
            self.assertTrue(summary["audit_completeness"]["ok"])

    def test_auto_resolution_transition_requires_matching_auto_decision_audit_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            run_cli_json(["mode", "set", ops_dir, "--mode", "autonomous"])
            task_dir = write_needs_human_task(
                ops_dir,
                "TASK-9004",
                trigger="high_confidence_weak_evidence",
                gate_category="quality_uncertainty",
                available_decisions=["request_revision", "pause", "reject"],
            )
            code, payload = run_cli_json(["decision", "auto-resolve-task", ops_dir, task_dir, "--date", NOW])
            self.assertEqual(cli.SUCCESS, code, payload)
            (ops_dir / "auto_decisions.md").unlink()

            status = json.loads((task_dir / "status.json").read_text(encoding="utf-8"))
            transition_code, transition = validate_transition.validate_payload(status, decisions_path=ops_dir / "decisions.md")

            self.assertEqual(validate_transition.INVALID_TRANSITION, transition_code, transition)
            self.assertEqual("missing_auto_decision", transition["reason"])

    def test_autonomous_mode_does_not_auto_resolve_hard_stop_category(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            run_cli_json(["mode", "set", ops_dir, "--mode", "autonomous"])
            task_dir = write_needs_human_task(
                ops_dir,
                "TASK-9003",
                trigger="credentials_missing",
                gate_category="credentials_missing",
                available_decisions=["pause", "reject"],
            )
            before = file_snapshot(ops_dir)

            code, payload = run_cli_json(["decision", "auto-resolve-task", ops_dir, task_dir, "--dry-run"])

            self.assertEqual(2, code, payload)
            self.assertFalse(payload["can_auto_resolve"])
            self.assertEqual("hard_stop_category_requires_human", payload["reason"])
            self.assertEqual(["credentials_missing"], payload["hard_stop_categories"])
            self.assertEqual(before, file_snapshot(ops_dir))


if __name__ == "__main__":
    unittest.main()
