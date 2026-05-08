"""Regression tests for data foundation validation."""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from async_research_workflow import cli


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "src" / "async_research_workflow"
GENERIC_STARTER = PACKAGE_ROOT / "templates" / "generic_research_ops_starter" / "research_ops"
REAL_ESTATE_STARTER = PACKAGE_ROOT / "templates" / "research_ops_starter" / "research_ops"


def copy_starter(src: Path, tmp: Path) -> Path:
    target = tmp / "research_ops"
    shutil.copytree(src, target)
    return target


def run_cli_json(argv: list[str]) -> tuple[int, dict]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = cli.main(argv)
    return code, json.loads(stream.getvalue())


class DataFoundationValidatorTests(unittest.TestCase):
    def test_generic_starter_passes_with_empty_data_tables(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir = copy_starter(GENERIC_STARTER, Path(tmpdir))

            code, payload = run_cli_json(["data", "validate", str(ops_dir), "--now", "2026-05-08"])

        self.assertEqual(0, code)
        self.assertTrue(payload["ok"])
        self.assertEqual(0, payload["warning_count"])
        self.assertEqual(0, payload["error_count"])
        self.assertEqual(0, payload["profile_count"])

    def test_real_estate_starter_profiles_pass_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir = copy_starter(REAL_ESTATE_STARTER, Path(tmpdir))

            code, payload = run_cli_json(["data", "validate", str(ops_dir), "--now", "2026-05-08"])

        self.assertEqual(0, code)
        self.assertTrue(payload["ok"])
        self.assertEqual(0, payload["warning_count"])
        self.assertEqual(0, payload["error_count"])
        self.assertEqual(3, payload["profile_count"])

    def test_missing_data_dir_is_warning_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir = copy_starter(GENERIC_STARTER, Path(tmpdir))
            shutil.rmtree(ops_dir / "data")

            code, payload = run_cli_json(["data", "validate", str(ops_dir), "--now", "2026-05-08"])

        self.assertEqual(2, code)
        self.assertTrue(payload["ok"])
        self.assertEqual(1, payload["warning_count"])
        self.assertEqual({"data_dir_missing"}, {item["reason"] for item in payload["warnings"]})

    def test_missing_experiment_ready_profile_is_warning_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir = copy_starter(REAL_ESTATE_STARTER, Path(tmpdir))
            (ops_dir / "data" / "profiles" / "DS-0001.md").unlink()

            code, payload = run_cli_json(["data", "validate", str(ops_dir), "--now", "2026-05-08"])

        self.assertEqual(2, code)
        self.assertTrue(payload["ok"])
        warning_reasons = {item["reason"] for item in payload["warnings"]}
        self.assertIn("missing_experiment_ready_profile", warning_reasons)

    def test_profile_identity_error_fails_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir = copy_starter(REAL_ESTATE_STARTER, Path(tmpdir))
            path = ops_dir / "data" / "profiles" / "DS-0001.md"
            text = path.read_text(encoding="utf-8").replace("source_id: DS-0001", "source_id: DS-9999")
            path.write_text(text, encoding="utf-8")

            code, payload = run_cli_json(["data", "validate", str(ops_dir), "--now", "2026-05-08"])

        self.assertEqual(4, code)
        self.assertFalse(payload["ok"])
        error_reasons = {item["reason"] for item in payload["errors"]}
        self.assertIn("profile_source_id_mismatch", error_reasons)
        self.assertIn("profile_without_audit_row", error_reasons)

    def test_duplicate_profile_id_is_flagged_even_with_noncanonical_filename(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir = copy_starter(REAL_ESTATE_STARTER, Path(tmpdir))
            original = ops_dir / "data" / "profiles" / "DS-0001.md"
            duplicate = ops_dir / "data" / "profiles" / "DS-0001-copy.md"
            duplicate.write_text(original.read_text(encoding="utf-8"), encoding="utf-8")

            code, payload = run_cli_json(["data", "validate", str(ops_dir), "--now", "2026-05-08"])

        self.assertEqual(4, code)
        self.assertFalse(payload["ok"])
        error_reasons = {item["reason"] for item in payload["errors"]}
        self.assertIn("invalid_profile_filename", error_reasons)
        self.assertIn("duplicate_profile_id", error_reasons)

    def test_profile_projection_drift_warns_without_audit_schema_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir = copy_starter(REAL_ESTATE_STARTER, Path(tmpdir))
            path = ops_dir / "data" / "profiles" / "DS-0001.md"
            text = path.read_text(encoding="utf-8").replace(
                "source_name: HM Land Registry Price Paid Data",
                "source_name: Drifted Local Name",
            )
            path.write_text(text, encoding="utf-8")

            code, payload = run_cli_json(["data", "validate", str(ops_dir), "--now", "2026-05-08"])

        self.assertEqual(2, code)
        self.assertTrue(payload["ok"])
        warning_reasons = {item["reason"] for item in payload["warnings"]}
        self.assertIn("profile_audit_projection_drift", warning_reasons)

    def test_template_profile_is_ignored_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir = copy_starter(GENERIC_STARTER, Path(tmpdir))
            template = ops_dir / "data" / "profiles" / "DS-0000.md"
            template.write_text("source_id: DS-0000\n", encoding="utf-8")

            code, payload = run_cli_json(["data", "validate", str(ops_dir), "--now", "2026-05-08"])

        self.assertEqual(0, code)
        self.assertTrue(payload["ok"])
        self.assertEqual([str(template)], payload["ignored_templates"])

    def test_active_idea_unknown_data_gap_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir = copy_starter(GENERIC_STARTER, Path(tmpdir))
            idea_path = ops_dir / "ideas" / "IDEA-0001.json"
            idea_path.write_text(
                json.dumps({"id": "IDEA-0001", "status": "candidate", "data_gaps": ["DG-9999"]}),
                encoding="utf-8",
            )

            code, payload = run_cli_json(["data", "validate", str(ops_dir), "--now", "2026-05-08"])

        self.assertEqual(2, code)
        self.assertTrue(payload["ok"])
        warning_reasons = {item["reason"] for item in payload["warnings"]}
        self.assertIn("active_idea_unknown_data_gap", warning_reasons)


if __name__ == "__main__":
    unittest.main()
