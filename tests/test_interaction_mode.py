"""Regression tests for durable interaction mode config."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from async_research_workflow import cli


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


class InteractionModeTests(unittest.TestCase):
    def init_ops(self, root: Path) -> Path:
        ops_dir = root / "research_ops"
        code, payload = run_cli_json(["init", ops_dir, "--force"])
        self.assertEqual(cli.SUCCESS, code, payload)
        self.assertTrue(payload["ok"])
        return ops_dir

    def test_starter_template_has_supervised_mode_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))

            code, payload = run_cli_json(["mode", "show", ops_dir])

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["config_present"])
            self.assertFalse(payload["defaulted"])
            self.assertEqual("supervised", payload["summary"]["mode"])
            self.assertIn("hard_budget_breach", payload["summary"]["interrupt_only_for"])
            self.assertIn("allow_revision", payload["summary"]["auto_decisions_enabled"])

    def test_missing_mode_config_uses_manual_default_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            (ops_dir / "interaction_mode.json").unlink()
            before = file_snapshot(ops_dir)

            code, payload = run_cli_json(["mode", "validate", ops_dir])

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertFalse(payload["config_present"])
            self.assertTrue(payload["defaulted"])
            self.assertEqual("manual", payload["summary"]["mode"])
            self.assertEqual([], payload["summary"]["auto_decisions_enabled"])
            self.assertTrue(any(item["message"].startswith("interaction_mode.json is missing") for item in payload["warnings"]))
            self.assertEqual(before, file_snapshot(ops_dir))

    def test_invalid_mode_config_fails_closed_with_actionable_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            path = ops_dir / "interaction_mode.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "mode": "autonomous",
                        "risk_tolerance": "conservative",
                        "interrupt_policy": {
                            "allow_interrupts": False,
                            "interrupt_only_for": ["hard_budget_breach"],
                        },
                        "auto_decisions": {
                            "allow_resume": True,
                            "allow_revision": True,
                            "allow_reject": True,
                            "allow_claim_downgrade": True,
                            "allow_source_substitution": True,
                            "allow_idea_prioritization": True,
                        },
                        "audit": {
                            "write_decisions": True,
                            "write_auto_decisions": False,
                            "explain_auto_decisions": True,
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            before = path.read_text(encoding="utf-8")

            code, payload = run_cli_json(["mode", "validate", ops_dir])
            set_code, set_payload = run_cli_json(["mode", "set", ops_dir, "--mode", "supervised"])

            self.assertEqual(cli.INVALID, code, payload)
            self.assertFalse(payload["ok"])
            self.assertEqual("invalid_mode_config", payload["reason"])
            messages = " ".join(item["message"] for item in payload["errors"])
            self.assertIn("interaction modes must allow human interrupts", messages)
            self.assertIn("hard-stop categories are missing", messages)
            self.assertIn("automatic decisions require audit fields", messages)
            self.assertEqual(cli.INVALID, set_code, set_payload)
            self.assertEqual(before, path.read_text(encoding="utf-8"))

    def test_mode_set_writes_json_readable_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))

            code, payload = run_cli_json(["mode", "set", ops_dir, "--mode", "manual"])

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertEqual("manual", payload["mode"])
            self.assertTrue(payload["changed"])
            self.assertEqual([], payload["summary"]["auto_decisions_enabled"])
            self.assertIn("quality_uncertainty", payload["summary"]["interrupt_only_for"])
            saved = json.loads((ops_dir / "interaction_mode.json").read_text(encoding="utf-8"))
            self.assertEqual("manual", saved["mode"])

            validate_code, validate_payload = run_cli_json(["mode", "validate", ops_dir])
            self.assertEqual(cli.SUCCESS, validate_code, validate_payload)
            self.assertTrue(validate_payload["ok"])

    def test_schema_check_includes_mode_config_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))

            code, payload = run_cli_json(["schema-check", ops_dir])

            self.assertEqual(cli.SUCCESS, code, payload)
            artifact_types = {item["artifact_type"] for item in payload["artifacts"]}
            self.assertIn("interaction_mode", artifact_types)


if __name__ == "__main__":
    unittest.main()
