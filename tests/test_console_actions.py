"""Regression tests for guarded console setup actions."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from async_research_workflow.console import actions


def file_snapshot(root: Path) -> dict[str, bytes]:
    if not root.exists():
        return {}
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


class ConsoleActionTests(unittest.TestCase):
    def test_catalog_marks_missing_workspace_and_known_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            catalog = actions.action_catalog(ops_dir)

        self.assertTrue(catalog["ok"])
        self.assertFalse(catalog["workspace"]["exists"])
        by_id = {item["id"]: item for item in catalog["actions"]}
        self.assertEqual("available", by_id["init"]["status"])
        self.assertEqual("blocked_missing_workspace", by_id["schema_check"]["status"])
        self.assertIn("async-research init", by_id["init"]["command"])
        self.assertIn("async-research surface update", by_id["surface_update"]["command"])
        self.assertTrue(by_id["surface_update"]["mutates"])
        self.assertFalse(by_id["surface_validate"]["mutates"])

    def test_init_requires_confirmation_then_creates_missing_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            status, blocked = actions.run_action("init", ops_dir, {"template": "generic"})
            self.assertEqual(409, status)
            self.assertEqual("confirmation_required", blocked["reason"])
            self.assertFalse(ops_dir.exists())

            status, result = actions.run_action(
                "init",
                ops_dir,
                {
                    "template": "generic",
                    "confirm": actions.init_confirmation_token(ops_dir, "generic"),
                },
            )

            self.assertEqual(200, status)
            self.assertTrue(result["ok"], result)
            self.assertTrue(result["changed"])
            self.assertTrue(result["mutates"])
            self.assertEqual(0, result["exit_code"])
            self.assertEqual("success", result["status"])
            self.assertIn("async-research init", result["command"])
            self.assertIn('"action": "initialized"', result["stdout"])
            self.assertEqual("", result["stderr"])
            self.assertTrue((ops_dir / "README.md").exists())

    def test_init_refuses_existing_workspace_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            ops_dir.mkdir()
            sentinel = ops_dir / "sentinel.txt"
            sentinel.write_text("keep me", encoding="utf-8")
            before = file_snapshot(ops_dir)

            status, result = actions.run_action(
                "init",
                ops_dir,
                {
                    "template": "generic",
                    "confirm": actions.init_confirmation_token(ops_dir, "generic"),
                },
            )

            self.assertEqual(200, status)
            self.assertFalse(result["ok"])
            self.assertFalse(result["changed"])
            self.assertEqual(4, result["exit_code"])
            self.assertIn("target_exists", result["stdout"])
            self.assertEqual(before, file_snapshot(ops_dir))

    def test_init_rejects_force_and_unknown_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            status, result = actions.run_action("init", ops_dir, {"template": "generic", "force": True})
            self.assertEqual(400, status)
            self.assertEqual("force_not_supported", result["reason"])

            status, result = actions.run_action("init", ops_dir, {"template": "unknown"})
            self.assertEqual(400, status)
            self.assertEqual("unsupported_template", result["reason"])

    def test_setup_checks_return_command_result_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            _, init_result = actions.run_action(
                "init",
                ops_dir,
                {
                    "template": "generic",
                    "confirm": actions.init_confirmation_token(ops_dir, "generic"),
                },
            )
            self.assertTrue(init_result["ok"], init_result)

            for action_id in ("schema_check", "readiness_dry_run", "health_dry_run", "surface_update", "surface_validate"):
                status, result = actions.run_action(action_id, ops_dir, {})
                self.assertEqual(200, status, result)
                self.assertIn("async-research", result["command"])
                self.assertIsInstance(result["stdout"], str)
                self.assertIsInstance(result["stderr"], str)
                self.assertIsInstance(result["exit_code"], int)
                self.assertIn(result["status"], {"success", "warning", "failed"})
                self.assertIn("next_step", result)
                if result["stdout"].strip():
                    try:
                        json.loads(result["stdout"])
                    except json.JSONDecodeError:
                        self.fail(f"{action_id} stdout should be JSON: {result['stdout']}")

    def test_non_init_action_requires_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            status, result = actions.run_action("schema_check", ops_dir, {})
        self.assertEqual(409, status)
        self.assertEqual("ops_dir_missing", result["reason"])
        self.assertTrue(result["read_only"])
        self.assertFalse(result["changed"])

    def test_unknown_action_is_structured_404(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            status, result = actions.run_action("nope", Path(tmp) / "research_ops", {})
        self.assertEqual(404, status)
        self.assertEqual("unknown_console_action", result["reason"])


if __name__ == "__main__":
    unittest.main()
