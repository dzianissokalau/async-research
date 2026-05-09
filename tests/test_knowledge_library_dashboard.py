"""Regression tests for the read-only knowledge library dashboard."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from async_research_workflow import cli
from async_research_workflow.scripts import knowledge_library


NOW = "2026-05-09T00:00:00Z"
TEMPLATES = dict(knowledge_library.STARTER_FILES)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, payload: dict) -> None:
    write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


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


def file_snapshot(ops_dir: Path) -> dict[str, str]:
    return {
        str(path.relative_to(ops_dir)): path.read_text(encoding="utf-8")
        for path in sorted((ops_dir / "library").glob("*.md"))
    }


def write_active_literature_task(ops_dir: Path) -> None:
    write_json(
        ops_dir / "tasks" / "TASK-7001-literature-extract" / "status.json",
        {
            "id": "TASK-7001",
            "type": "literature_extract",
            "status": "ready_for_worker",
            "title": "Extract fixture source context",
            "catalog_idea_id": "IDEA-7001",
            "updated_at": NOW,
            "proposed_library_update_targets": ["library/source_library.md", "library/claim_map.md"],
        },
    )


def write_idea(ops_dir: Path, idea_id: str, **fields) -> None:
    payload = {
        "schema_version": "1.0",
        "id": idea_id,
        "status": fields.pop("status", "candidate"),
        "title": fields.pop("title", f"Fixture {idea_id}"),
        "question": "Can this fixture be supported?",
        "why_it_might_matter": "It exercises dashboard support gaps.",
        "required_data": [],
        "minimum_viable_test": "Inspect support.",
        "baseline": "Manual baseline.",
        "main_risks": ["fixture risk"],
        "kill_reason": "Reject if unsupported.",
        "recommended_next_task": fields.pop("recommended_next_task", "hypothesis_card"),
        "created_at": NOW,
        "updated_at": NOW,
    }
    payload.update(fields)
    write_json(ops_dir / "ideas" / f"{idea_id}.json", payload)


class KnowledgeLibraryDashboardTests(unittest.TestCase):
    def test_empty_dashboard_renders_required_sections_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            bootstrap_empty_library(ops_dir)
            before = file_snapshot(ops_dir)

            code, payload = run_cli_json(["library", "dashboard", ops_dir, "--now", NOW])
            after = file_snapshot(ops_dir)

        self.assertEqual(knowledge_library.SUCCESS, code, payload)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["read_only"])
        self.assertFalse(payload["changed"])
        self.assertEqual(before, after)
        self.assertEqual("knowledge_library_dashboard_rendered", payload["action"])
        self.assertEqual(0, payload["validation_exit_code"])
        for section in [
            "coverage_by_topic",
            "source_counts",
            "recently_reviewed_sources",
            "stale_sources",
            "stale_claims",
            "risky_claims",
            "open_questions",
            "proposed_library_update_tasks",
            "ideas_with_library_support_gaps",
            "validator_findings",
        ]:
            self.assertIn(section, payload["sections"])

    def test_dashboard_groups_coverage_risk_tasks_and_idea_support_gaps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            bootstrap_empty_library(ops_dir)
            write_rows(
                ops_dir,
                table_file("source_library.md"),
                [
                    ["LIT-0001", "trusted", "primary", "paper", "Trusted source", "Publisher", "https://example.test/a", "2026-05-01", "ready"],
                    ["LIT-0002", "disputed", "weak", "paper", "Old disputed source", "Publisher", "https://example.test/b", "2025-01-01", "disputed context"],
                    ["LIT-0003", "context_only", "background", "post", "Context source", "Author", "https://example.test/c", "2026-04-15", "context only"],
                ],
            )
            write_rows(
                ops_dir,
                table_file("knowledge_index.md"),
                [["Fixture economics", "Known context", "LIT-0001 LIT-0002", "moderate", "requires caveats", "2026-05-09"]],
            )
            write_rows(
                ops_dir,
                table_file("claim_map.md"),
                [["Fixture claim", "LIT-0002", "strong", "disputed", "source is disputed", "2025-01-01"]],
            )
            write_rows(
                ops_dir,
                table_file("open_questions.md"),
                [["OQ-7001", "What remains unknown?", "It informs extraction.", "LIT-0001", "literature_extract", "open"]],
            )
            write_active_literature_task(ops_dir)
            write_idea(ops_dir, "IDEA-7001", status="promote", library_refs=["LIT-9999"])
            write_idea(ops_dir, "IDEA-7002")

            code, payload = run_cli_json(["library", "dashboard", ops_dir, "--now", NOW, "--stale-days", "30"])

        self.assertEqual(knowledge_library.VALIDATION_FINDINGS, code, payload)
        sections = payload["sections"]
        self.assertEqual({"context_only": 1, "disputed": 1, "trusted": 1}, sections["source_counts"]["by_status"])
        self.assertEqual("Fixture economics", sections["coverage_by_topic"][0]["topic"])
        self.assertEqual(2, sections["coverage_by_topic"][0]["source_count"])
        self.assertEqual("LIT-0001", sections["recently_reviewed_sources"][0]["source_id"])
        self.assertEqual(["LIT-0002"], [item["source_id"] for item in sections["stale_sources"]])
        self.assertEqual(["Fixture claim"], [item["claim"] for item in sections["stale_claims"]])
        self.assertEqual({"LIT-0002": "disputed"}, sections["risky_claims"][0]["risky_source_refs"])
        self.assertEqual(["OQ-7001"], [item["question_id"] for item in sections["open_questions"]])
        self.assertEqual(["TASK-7001"], [item["task_id"] for item in sections["proposed_library_update_tasks"]])
        support_by_idea = {
            item["idea_id"]: item["support_status"]
            for item in sections["ideas_with_library_support_gaps"]
        }
        self.assertEqual("unresolved_library_refs", support_by_idea["IDEA-7001"])
        self.assertEqual("thin_evidence", support_by_idea["IDEA-7002"])
        self.assertIn("library_source_review_stale", [item["reason"] for item in sections["validator_findings"]])

    def test_dashboard_returns_malformed_for_validator_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            bootstrap_empty_library(ops_dir)
            write_rows(
                ops_dir,
                table_file("source_library.md"),
                [["LIT-0001", "approved", "tier_1", "paper", "A", "Publisher", "https://example.test/a", "2026-05-09", "bad vocab"]],
            )
            write_idea(ops_dir, "IDEA-7003", status="promote", library_refs=["LIT-0001"])

            code, payload = run_cli_json(["library", "dashboard", ops_dir, "--now", NOW])

        self.assertEqual(knowledge_library.MALFORMED, code, payload)
        self.assertFalse(payload["ok"])
        self.assertEqual(2, payload["summary"]["validator_error_count"])
        self.assertIn("invalid_library_source_status", [item["reason"] for item in payload["sections"]["validator_findings"]])
        self.assertEqual("invalid_library_state", payload["sections"]["ideas_with_library_support_gaps"][0]["support_status"])

    def test_dashboard_rejects_invalid_stale_days(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            bootstrap_empty_library(ops_dir)

            code, payload = run_cli_json(["library", "dashboard", ops_dir, "--stale-days", "-1"])

        self.assertEqual(knowledge_library.INVALID_REQUEST, code, payload)
        self.assertFalse(payload["ok"])
        self.assertEqual("invalid_stale_days", payload["reason"])


if __name__ == "__main__":
    unittest.main()
