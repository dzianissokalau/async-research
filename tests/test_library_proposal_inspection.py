"""Regression tests for read-only knowledge library proposal inspection."""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from async_research_workflow import cli
from async_research_workflow.scripts import knowledge_library


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "src" / "async_research_workflow"
REAL_ESTATE_STARTER = PACKAGE_ROOT / "templates" / "research_ops_starter" / "research_ops"
TEMPLATES = dict(knowledge_library.STARTER_FILES)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_cli_json(argv: list[str]) -> tuple[int, dict]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = cli.main(argv)
    return int(code), json.loads(stream.getvalue())


def copy_starter(tmp: Path) -> Path:
    target = tmp / "research_ops"
    shutil.copytree(REAL_ESTATE_STARTER, target)
    return target


def file_snapshot(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


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
    (ops_dir / relative).write_text(before + "\n".join(block) + after, encoding="utf-8")


def operation(operation_id: str, name: str, target_path: str, row_id: str, payload: dict) -> dict:
    return {
        "operation_id": operation_id,
        "operation": name,
        "target_path": target_path,
        "row_id": row_id,
        "payload": payload,
        "preserve_manual_notes": True,
    }


def lit_source_payload(source_id: str) -> dict:
    return {
        "source_id": source_id,
        "status": "candidate",
        "trust_tier": "supporting",
        "type": "paper",
        "title": "Fixture Paper",
        "author_or_publisher": "Fixture Publisher",
        "location": "https://example.test/paper",
        "reviewed_date": "2026-05-19",
        "notes": "fixture proposal",
    }


def valid_library_proposal(proposal_id: str = "PROP-0200", source_id: str = "LIT-0200") -> dict:
    return {
        "proposal_version": "foundation_update_proposal_v1",
        "proposal_id": proposal_id,
        "source_task_id": "TASK-0200-literature-extract",
        "target": "library",
        "created_by": "worker",
        "rationale": "Add reviewed fixture library rows.",
        "operations": [
            operation(
                "OP-0001",
                "upsert_lit_source",
                "library/source_library.md",
                source_id,
                lit_source_payload(source_id),
            ),
            operation(
                "OP-0002",
                "upsert_topic_summary",
                "library/knowledge_index.md",
                "TOPIC-0200",
                {
                    "topic": "Fixture market dynamics",
                    "summary": "Fixture summary.",
                    "source_refs": source_id,
                    "confidence": "medium",
                    "caveats": "Synthetic fixture only.",
                    "updated_at": "2026-05-19",
                },
            ),
            operation(
                "OP-0003",
                "upsert_claim",
                "library/claim_map.md",
                "CLAIM-0200",
                {
                    "claim": "Fixture claim",
                    "source_refs": source_id,
                    "claim_strength": "suggestive",
                    "disputed_status": "none",
                    "caveats": "Synthetic fixture only.",
                    "reviewed_date": "2026-05-19",
                },
            ),
            operation(
                "OP-0004",
                "upsert_method",
                "library/method_index.md",
                "METHOD-0200",
                {
                    "method": "Fixture synthesis",
                    "use_case": "context",
                    "assumptions": "Fixture assumptions.",
                    "source_refs": source_id,
                    "risks": "Synthetic fixture only.",
                    "reviewed_date": "2026-05-19",
                },
            ),
            operation(
                "OP-0005",
                "upsert_open_question",
                "library/open_questions.md",
                "OQ-0200",
                {
                    "question_id": "OQ-0200",
                    "question": "What remains unknown?",
                    "why_it_matters": "Fixture gap.",
                    "source_refs": source_id,
                    "next_task": "TASK-0200",
                    "status": "open",
                },
            ),
            operation(
                "OP-0006",
                "append_library_update_log",
                "library/library_update_log.md",
                "LOG-0200",
                {
                    "date": "2026-05-19",
                    "task_id": "TASK-0200",
                    "files_updated": "library/source_library.md; library/claim_map.md",
                    "reviewer_or_approver": "proposal-review",
                    "notes": "fixture proposal",
                },
            ),
        ],
    }


class LibraryProposalInspectionTests(unittest.TestCase):
    def test_inspects_valid_literature_task_proposal_without_mutating_ops(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir = copy_starter(Path(tmpdir))
            task_dir = ops_dir / "tasks" / "TASK-0200-literature-extract"
            write_json(task_dir / "artifacts" / "foundation_update_proposal.json", valid_library_proposal())
            before = file_snapshot(ops_dir)

            code, payload = run_cli_json(["library", "inspect-proposals", str(ops_dir), str(task_dir)])
            after = file_snapshot(ops_dir)

        self.assertEqual(0, code, payload)
        self.assertTrue(payload["ok"], payload)
        self.assertEqual(1, payload["proposals_found"])
        self.assertEqual(1, payload["valid_proposals"])
        self.assertEqual(0, payload["invalid_proposals"])
        self.assertEqual([], payload["warnings"])
        self.assertEqual([], payload["blockers"])
        self.assertTrue(payload["read_only"])
        self.assertFalse(payload["changed"])
        self.assertEqual(before, after)
        self.assertEqual({"valid"}, {item["status"] for item in payload["operations"]})

    def test_existing_lit_source_upsert_is_warning_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir = copy_starter(Path(tmpdir))
            write_rows(
                ops_dir,
                table_file("source_library.md"),
                [["LIT-0001", "trusted", "primary", "paper", "A", "Publisher", "https://example.com/a", "2026-05-01", "ok"]],
            )
            proposal = valid_library_proposal(source_id="LIT-0001")
            proposal["operations"] = [proposal["operations"][0]]
            proposal_path = Path(tmpdir) / "proposal.json"
            write_json(proposal_path, proposal)

            code, payload = run_cli_json(["library", "inspect-proposals", str(ops_dir), str(proposal_path)])

        self.assertEqual(0, code, payload)
        self.assertTrue(payload["ok"], payload)
        self.assertEqual(1, payload["valid_proposals"])
        self.assertEqual(1, len(payload["warnings"]))
        self.assertEqual("existing_row_upsert", payload["warnings"][0]["reason"])
        self.assertEqual("warning", payload["operations"][0]["status"])

    def test_duplicate_lit_source_in_one_proposal_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir = copy_starter(Path(tmpdir))
            proposal = valid_library_proposal(source_id="LIT-0201")
            proposal["operations"] = [
                proposal["operations"][0],
                operation(
                    "OP-0007",
                    "upsert_lit_source",
                    "library/source_library.md",
                    "LIT-0201",
                    lit_source_payload("LIT-0201"),
                ),
            ]
            proposal_path = Path(tmpdir) / "duplicate_proposal.json"
            write_json(proposal_path, proposal)

            code, payload = run_cli_json(["library", "inspect-proposals", str(ops_dir), str(proposal_path)])

        self.assertEqual(4, code, payload)
        self.assertFalse(payload["ok"])
        self.assertEqual(0, payload["valid_proposals"])
        self.assertEqual(1, payload["invalid_proposals"])
        reasons = {item.get("reason") for item in payload["operations"] + payload["blockers"]}
        self.assertIn("duplicate_proposed_row", reasons)

    def test_missing_source_reference_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir = copy_starter(Path(tmpdir))
            proposal = valid_library_proposal()
            proposal["operations"] = [
                operation(
                    "OP-0003",
                    "upsert_claim",
                    "library/claim_map.md",
                    "CLAIM-0201",
                    {
                        "claim": "Unresolved source claim",
                        "source_refs": "LIT-9999",
                        "claim_strength": "weak",
                        "disputed_status": "none",
                        "caveats": "fixture",
                        "reviewed_date": "2026-05-19",
                    },
                )
            ]
            proposal_path = Path(tmpdir) / "missing_source_ref_proposal.json"
            write_json(proposal_path, proposal)

            code, payload = run_cli_json(["library", "inspect-proposals", str(ops_dir), str(proposal_path)])

        self.assertEqual(4, code, payload)
        self.assertFalse(payload["ok"])
        reasons = {item["reason"] for item in payload["blockers"]}
        self.assertIn("unknown_library_source_ref", reasons)

    def test_path_traversal_target_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir = copy_starter(Path(tmpdir))
            proposal = valid_library_proposal(source_id="LIT-0202")
            proposal["operations"][0]["target_path"] = "../library/source_library.md"
            proposal_path = Path(tmpdir) / "path_traversal_proposal.json"
            write_json(proposal_path, proposal)

            code, payload = run_cli_json(["library", "inspect-proposals", str(ops_dir), str(proposal_path)])

        self.assertEqual(4, code, payload)
        self.assertFalse(payload["ok"])
        reasons = {item["reason"] for item in payload["blockers"]}
        self.assertIn("invalid_target_path", reasons)

    def test_wrong_canonical_target_path_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir = copy_starter(Path(tmpdir))
            proposal = valid_library_proposal(source_id="LIT-0204")
            proposal["operations"][0]["target_path"] = "library/claim_map.md"
            proposal_path = Path(tmpdir) / "wrong_target_proposal.json"
            write_json(proposal_path, proposal)

            code, payload = run_cli_json(["library", "inspect-proposals", str(ops_dir), str(proposal_path)])

        self.assertEqual(4, code, payload)
        self.assertFalse(payload["ok"])
        reasons = {item["reason"] for item in payload["blockers"]}
        self.assertIn("unexpected_target_path", reasons)

    def test_unknown_operation_from_parser_blocks_inspection(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir = copy_starter(Path(tmpdir))
            proposal = valid_library_proposal(source_id="LIT-0203")
            proposal["operations"][0]["operation"] = "rewrite_library"
            proposal_path = Path(tmpdir) / "unknown_operation_proposal.json"
            write_json(proposal_path, proposal)

            code, payload = run_cli_json(["library", "inspect-proposals", str(ops_dir), str(proposal_path)])

        self.assertEqual(4, code, payload)
        self.assertFalse(payload["ok"])
        reasons = {item["reason"] for item in payload["blockers"]}
        self.assertIn("unknown_operation", reasons)

    def test_non_library_proposal_target_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir = copy_starter(Path(tmpdir))
            proposal = {
                "proposal_version": "foundation_update_proposal_v1",
                "proposal_id": "PROP-0205",
                "source_task_id": "TASK-0205-data-readiness",
                "target": "data",
                "created_by": "worker",
                "rationale": "Data proposals must use the data inspection command.",
                "operations": [
                    operation(
                        "OP-0001",
                        "upsert_data_source",
                        "data_source_audit.md",
                        "DS-0205",
                        {
                            "source_id": "DS-0205",
                            "source_name": "Fixture Data Source",
                        },
                    )
                ],
            }
            proposal_path = Path(tmpdir) / "data_proposal.json"
            write_json(proposal_path, proposal)

            code, payload = run_cli_json(["library", "inspect-proposals", str(ops_dir), str(proposal_path)])

        self.assertEqual(4, code, payload)
        self.assertFalse(payload["ok"])
        reasons = {item["reason"] for item in payload["blockers"]}
        self.assertIn("non_library_proposal_target", reasons)


if __name__ == "__main__":
    unittest.main()
