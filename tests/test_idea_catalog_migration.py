"""Regression tests for idempotent idea catalog initialization."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from async_research_workflow import cli
from async_research_workflow.scripts import idea_catalog


def run_cli_json(argv: list[str]) -> tuple[int, dict]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = cli.main(argv)
    return code, json.loads(stream.getvalue())


class IdeaCatalogMigrationTests(unittest.TestCase):
    def test_dry_run_reports_missing_files_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            ops_dir.mkdir()

            code, payload = run_cli_json(["idea", "catalog", "init", str(ops_dir), "--dry-run"])

            self.assertEqual(cli.SUCCESS, code)
            self.assertEqual("idea_catalog_init_planned", payload["action"])
            self.assertTrue(payload["changed"])
            self.assertEqual(
                ["ideas/idea_catalog.md", "ideas/prioritization.md"],
                [change["relative_path"] for change in payload["would_write"]],
            )
            self.assertFalse((ops_dir / "ideas").exists())

    def test_write_adds_missing_files_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            ops_dir.mkdir()

            code, payload = run_cli_json(["idea", "catalog", "init", str(ops_dir), "--write"])

            self.assertEqual(cli.SUCCESS, code)
            self.assertEqual("idea_catalog_initialized", payload["action"])
            self.assertTrue(payload["changed"])
            self.assertEqual(
                ["ideas/idea_catalog.md", "ideas/prioritization.md"],
                [change["relative_path"] for change in payload["files_added"]],
            )
            self.assertEqual(
                idea_catalog.CATALOG_TEMPLATE,
                (ops_dir / "ideas" / "idea_catalog.md").read_text(encoding="utf-8"),
            )
            self.assertEqual(
                idea_catalog.PRIORITIZATION_TEMPLATE,
                (ops_dir / "ideas" / "prioritization.md").read_text(encoding="utf-8"),
            )

            second_code, second_payload = run_cli_json(["idea", "catalog", "init", str(ops_dir), "--write"])

            self.assertEqual(cli.SUCCESS, second_code)
            self.assertFalse(second_payload["changed"])
            self.assertEqual([], second_payload["files_added"])

    def test_write_preserves_existing_catalog_notes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            ideas_dir = ops_dir / "ideas"
            ideas_dir.mkdir(parents=True)
            existing_catalog = ideas_dir / "idea_catalog.md"
            existing_text = "# Idea Catalog\n\n## Notes\n\nKeep this human note.\n"
            existing_catalog.write_text(existing_text, encoding="utf-8")

            code, payload = run_cli_json(["idea", "catalog", "init", str(ops_dir), "--write"])

            self.assertEqual(cli.SUCCESS, code)
            self.assertEqual(existing_text, existing_catalog.read_text(encoding="utf-8"))
            self.assertEqual(
                ["ideas/prioritization.md"],
                [change["relative_path"] for change in payload["files_added"]],
            )
            self.assertEqual(
                ["ideas/idea_catalog.md"],
                [item["relative_path"] for item in payload["existing_files"]],
            )

    def test_write_refuses_existing_catalog_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            lock_dir = ops_dir / "ideas" / "LOCK"
            lock_dir.mkdir(parents=True)

            code, payload = run_cli_json(["idea", "catalog", "init", str(ops_dir), "--write"])

            self.assertEqual(idea_catalog.VALIDATION_FAILED, code)
            self.assertEqual("catalog_locked", payload["reason"])
            self.assertFalse((ops_dir / "ideas" / "idea_catalog.md").exists())

    def test_conflicting_dry_run_and_write_flags_are_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            ops_dir.mkdir()

            code, payload = run_cli_json(["idea", "catalog", "init", str(ops_dir), "--dry-run", "--write"])

            self.assertEqual(idea_catalog.INVALID_REQUEST, code)
            self.assertEqual("conflicting_flags", payload["reason"])


if __name__ == "__main__":
    unittest.main()
