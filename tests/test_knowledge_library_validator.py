"""Regression tests for read-only knowledge library validation."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from async_research_workflow import cli
from async_research_workflow.scripts import knowledge_library


TEMPLATES = dict(knowledge_library.STARTER_FILES)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def run_cli_json(argv: list[str | Path]) -> tuple[int, dict]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = cli.main([str(arg) for arg in argv])
    return code, json.loads(stream.getvalue())


def bootstrap_empty_library(ops_dir: Path) -> None:
    for relative, template in knowledge_library.STARTER_FILES:
        write_text(ops_dir / relative, template)


def table_file(relative: str) -> Path:
    return Path(knowledge_library.LIBRARY_DIR) / relative


def write_rows(ops_dir: Path, relative: Path, rows: list[list[str]]) -> None:
    template = TEMPLATES[relative]
    spec = knowledge_library.TABLE_SPECS[relative]
    start = str(spec["start"])
    end = str(spec["end"])
    headers = list(spec["headers"])
    before, rest = template.split(start, 1)
    _old_block, after = rest.split(end, 1)
    block = [
        start,
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _header in headers) + " |",
    ]
    block.extend("| " + " | ".join(row) + " |" for row in rows)
    block.append(end)
    write_text(ops_dir / relative, before + "\n".join(block) + after)


class KnowledgeLibraryValidatorTests(unittest.TestCase):
    def test_empty_starter_library_validates_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            bootstrap_empty_library(ops_dir)

            code, payload = run_cli_json(["library", "validate", ops_dir])

            self.assertEqual(knowledge_library.SUCCESS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertEqual(0, payload["warning_count"])
            self.assertEqual(0, payload["error_count"])
            self.assertEqual(0, payload["source_count"])

    def test_missing_library_is_warning_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            ops_dir.mkdir()

            code, payload = run_cli_json(["library", "validate", ops_dir])

            self.assertEqual(knowledge_library.VALIDATION_FINDINGS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertEqual(["library_dir_missing"], [item["reason"] for item in payload["warnings"]])

    def test_missing_starter_file_is_warning_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            bootstrap_empty_library(ops_dir)
            (ops_dir / "library" / "method_index.md").unlink()

            code, payload = run_cli_json(["library", "validate", ops_dir])

            self.assertEqual(knowledge_library.VALIDATION_FINDINGS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertIn("library_file_missing", [item["reason"] for item in payload["warnings"]])

    def test_duplicate_lit_ids_fail_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            bootstrap_empty_library(ops_dir)
            write_rows(
                ops_dir,
                table_file("source_library.md"),
                [
                    ["LIT-0001", "trusted", "primary", "paper", "A", "Publisher", "https://example.com/a", "2026-05-01", "ok"],
                    ["LIT-0001", "trusted", "primary", "paper", "B", "Publisher", "https://example.com/b", "2026-05-01", "ok"],
                ],
            )

            code, payload = run_cli_json(["library", "validate", ops_dir])

            self.assertEqual(knowledge_library.MALFORMED, code, payload)
            self.assertFalse(payload["ok"])
            self.assertIn("duplicate_library_source_id", [item["reason"] for item in payload["errors"]])

    def test_malformed_generated_row_reports_file_and_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            bootstrap_empty_library(ops_dir)
            path = ops_dir / "library" / "claim_map.md"
            text = path.read_text(encoding="utf-8")
            text = text.replace(
                "<!-- /LIBRARY-CLAIMS -->",
                "| malformed | too few |\n<!-- /LIBRARY-CLAIMS -->",
            )
            write_text(path, text)

            code, payload = run_cli_json(["library", "validate", ops_dir])

            self.assertEqual(knowledge_library.MALFORMED, code, payload)
            errors = [item for item in payload["errors"] if item["reason"] == "malformed_library_table_row"]
            self.assertEqual(1, len(errors))
            self.assertEqual(str(path), errors[0]["path"])
            self.assertIn("line", errors[0])

    def test_missing_source_metadata_is_warning_level(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            bootstrap_empty_library(ops_dir)
            write_rows(
                ops_dir,
                table_file("source_library.md"),
                [["LIT-0001", "", "", "paper", "A", "", "", "", ""]],
            )

            code, payload = run_cli_json(["library", "validate", ops_dir])

            self.assertEqual(knowledge_library.VALIDATION_FINDINGS, code, payload)
            reasons = [item["reason"] for item in payload["warnings"]]
            self.assertIn("library_source_status_missing", reasons)
            self.assertIn("library_source_trust_tier_missing", reasons)
            self.assertIn("library_source_location_missing", reasons)
            self.assertIn("library_source_provenance_missing", reasons)

    def test_invalid_source_status_and_trust_tier_are_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            bootstrap_empty_library(ops_dir)
            write_rows(
                ops_dir,
                table_file("source_library.md"),
                [["LIT-0001", "approved", "tier_1", "paper", "A", "Publisher", "https://example.com/a", "2026-05-01", "ok"]],
            )

            code, payload = run_cli_json(["library", "validate", ops_dir])

            self.assertEqual(knowledge_library.MALFORMED, code, payload)
            reasons = [item["reason"] for item in payload["errors"]]
            self.assertIn("invalid_library_source_status", reasons)
            self.assertIn("invalid_library_trust_tier", reasons)

    def test_source_refs_must_resolve_to_source_library(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            bootstrap_empty_library(ops_dir)
            write_rows(
                ops_dir,
                table_file("claim_map.md"),
                [["Fixture claim", "LIT-9999", "weak", "", "caveat", "2026-05-01"]],
            )

            code, payload = run_cli_json(["library", "validate", ops_dir])

            self.assertEqual(knowledge_library.MALFORMED, code, payload)
            self.assertEqual(["unknown_library_source_ref"], [item["reason"] for item in payload["errors"]])

    def test_claim_caveat_and_update_log_warnings_are_warning_level(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            bootstrap_empty_library(ops_dir)
            write_rows(
                ops_dir,
                table_file("source_library.md"),
                [["LIT-0001", "trusted", "primary", "paper", "A", "Publisher", "https://example.com/a", "2025-01-01", "ok"]],
            )
            write_rows(
                ops_dir,
                table_file("claim_map.md"),
                [["Fixture claim", "LIT-0001", "strong", "disputed", "", "2026-05-01"]],
            )
            write_rows(
                ops_dir,
                table_file("library_update_log.md"),
                [["2026-05-01", "", "claim_map.md", "", "missing provenance"]],
            )

            code, payload = run_cli_json(["library", "validate", ops_dir])

            self.assertEqual(knowledge_library.VALIDATION_FINDINGS, code, payload)
            reasons = [item["reason"] for item in payload["warnings"]]
            self.assertIn("library_claim_without_caveats", reasons)
            self.assertIn("library_update_log_missing_provenance", reasons)

    def test_stale_review_dates_warn_only_when_configured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            bootstrap_empty_library(ops_dir)
            write_rows(
                ops_dir,
                table_file("source_library.md"),
                [["LIT-0001", "trusted", "primary", "paper", "A", "Publisher", "https://example.com/a", "2025-01-01", "ok"]],
            )

            clean_code, clean_payload = run_cli_json(["library", "validate", ops_dir, "--now", "2026-05-09"])
            stale_code, stale_payload = run_cli_json(["library", "validate", ops_dir, "--now", "2026-05-09", "--stale-days", "30"])

            self.assertEqual(knowledge_library.SUCCESS, clean_code, clean_payload)
            self.assertEqual(knowledge_library.VALIDATION_FINDINGS, stale_code, stale_payload)
            self.assertIn("library_source_review_stale", [item["reason"] for item in stale_payload["warnings"]])

    def test_malformed_generated_block_fails_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            bootstrap_empty_library(ops_dir)
            path = ops_dir / "library" / "source_library.md"
            write_text(path, path.read_text(encoding="utf-8").replace("<!-- /LIBRARY-SOURCES -->", ""))

            code, payload = run_cli_json(["library", "validate", ops_dir])

            self.assertEqual(knowledge_library.MALFORMED, code, payload)
            self.assertIn("malformed_library_generated_block", [item["reason"] for item in payload["errors"]])


if __name__ == "__main__":
    unittest.main()
