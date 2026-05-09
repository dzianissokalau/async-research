"""Regression tests for idempotent knowledge library initialization."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from async_research_workflow import cli
from async_research_workflow.scripts import knowledge_library


def run_cli_json(argv: list[str | Path]) -> tuple[int, dict]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = cli.main([str(arg) for arg in argv])
    return code, json.loads(stream.getvalue())


class KnowledgeLibraryMigrationTests(unittest.TestCase):
    def test_bare_invocation_defaults_to_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            ops_dir.mkdir()

            code, payload = run_cli_json(["library", "init", ops_dir])

            self.assertEqual(cli.SUCCESS, code)
            self.assertEqual("library_init_planned", payload["action"])
            self.assertTrue(payload["dry_run"])
            self.assertFalse((ops_dir / "library").exists())

    def test_dry_run_reports_missing_files_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            ops_dir.mkdir()

            code, payload = run_cli_json(["library", "init", ops_dir, "--dry-run"])

            self.assertEqual(cli.SUCCESS, code)
            self.assertEqual("library_init_planned", payload["action"])
            self.assertTrue(payload["changed"])
            self.assertEqual(
                [str(relative) for relative, _ in knowledge_library.STARTER_FILES],
                [change["relative_path"] for change in payload["would_write"]],
            )
            self.assertFalse((ops_dir / "library").exists())

    def test_write_adds_missing_files_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            ops_dir.mkdir()

            code, payload = run_cli_json(["library", "init", ops_dir, "--write"])

            self.assertEqual(cli.SUCCESS, code)
            self.assertEqual("library_initialized", payload["action"])
            self.assertTrue(payload["changed"])
            self.assertEqual(
                [str(relative) for relative, _ in knowledge_library.STARTER_FILES],
                [change["relative_path"] for change in payload["files_added"]],
            )
            for relative, template in knowledge_library.STARTER_FILES:
                self.assertEqual(template, (ops_dir / relative).read_text(encoding="utf-8"))

            second_code, second_payload = run_cli_json(["library", "init", ops_dir, "--write"])

            self.assertEqual(cli.SUCCESS, second_code)
            self.assertFalse(second_payload["changed"])
            self.assertEqual([], second_payload["files_added"])

    def test_write_preserves_existing_library_notes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            source_library = ops_dir / "library" / "source_library.md"
            existing_text = "# Source Library\n\n## Notes\n\nKeep this human note.\n"
            source_library.parent.mkdir(parents=True)
            source_library.write_text(existing_text, encoding="utf-8")

            code, payload = run_cli_json(["library", "init", ops_dir, "--write"])

            self.assertEqual(cli.SUCCESS, code)
            self.assertEqual(existing_text, source_library.read_text(encoding="utf-8"))
            self.assertNotIn(
                "library/source_library.md",
                [change["relative_path"] for change in payload["files_added"]],
            )
            self.assertIn(
                "library/source_library.md",
                [item["relative_path"] for item in payload["existing_files"]],
            )

    def test_conflicting_dry_run_and_write_flags_are_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            ops_dir.mkdir()

            code, payload = run_cli_json(["library", "init", ops_dir, "--dry-run", "--write"])

            self.assertEqual(knowledge_library.INVALID_REQUEST, code)
            self.assertEqual("conflicting_flags", payload["reason"])

    def test_missing_ops_dir_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "missing" / "research_ops"

            code, payload = run_cli_json(["library", "init", ops_dir])

            self.assertEqual(knowledge_library.MALFORMED, code)
            self.assertEqual("library_init_failed", payload["action"])
            self.assertEqual("ops_dir_missing", payload["failures"][0]["reason"])

    def test_library_path_as_file_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            ops_dir.mkdir()
            (ops_dir / "library").write_text("not a directory\n", encoding="utf-8")

            code, payload = run_cli_json(["library", "init", ops_dir, "--write"])

            self.assertEqual(knowledge_library.MALFORMED, code)
            self.assertEqual("library_path_not_directory", payload["failures"][0]["reason"])

    def test_library_file_path_as_directory_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            (ops_dir / "library" / "source_library.md").mkdir(parents=True)

            code, payload = run_cli_json(["library", "init", ops_dir, "--write"])

            self.assertEqual(knowledge_library.MALFORMED, code)
            self.assertEqual("library_file_path_not_file", payload["failures"][0]["reason"])


if __name__ == "__main__":
    unittest.main()
