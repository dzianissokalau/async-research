"""Regression tests for read-only data foundation proposal inspection."""

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
REAL_ESTATE_STARTER = PACKAGE_ROOT / "templates" / "research_ops_starter" / "research_ops"


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


def operation(operation_id: str, name: str, target_path: str, row_id: str, payload: dict) -> dict:
    return {
        "operation_id": operation_id,
        "operation": name,
        "target_path": target_path,
        "row_id": row_id,
        "payload": payload,
        "preserve_manual_notes": True,
    }


def valid_new_source_proposal(proposal_id: str = "PROP-0100", source_id: str = "DS-0100") -> dict:
    return {
        "proposal_version": "foundation_update_proposal_v1",
        "proposal_id": proposal_id,
        "source_task_id": "TASK-0100-data-readiness",
        "target": "data",
        "created_by": "worker",
        "rationale": "Add a reviewed fixture data source proposal.",
        "operations": [
            operation(
                "OP-0001",
                "upsert_data_source",
                "data_source_audit.md",
                source_id,
                {
                    "source_id": source_id,
                    "source_name": "Fixture Data Source",
                    "url_or_domain": "https://example.test/data.csv",
                    "publisher_owner": "Fixture Publisher",
                    "approval_status": "candidate",
                },
            ),
            operation(
                "OP-0002",
                "upsert_data_profile",
                f"data/profiles/{source_id}.md",
                source_id,
                {
                    "source_id": source_id,
                    "approved_use_cases": "context",
                    "blocked_use_cases": "accepted_evidence",
                },
            ),
            operation(
                "OP-0003",
                "upsert_data_catalog_row",
                "data/data_catalog.md",
                source_id,
                {
                    "source_id": source_id,
                    "source_name": "Fixture Data Source",
                    "profile_path": f"data/profiles/{source_id}.md",
                },
            ),
            operation(
                "OP-0004",
                "upsert_data_access_row",
                "data/data_access.md",
                source_id,
                {
                    "source_id": source_id,
                    "access_method": "public download",
                    "location": "https://example.test/data.csv",
                },
            ),
        ],
    }


class DataProposalInspectionTests(unittest.TestCase):
    def test_inspects_valid_task_directory_proposal_without_mutating_ops(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir = copy_starter(Path(tmpdir))
            task_dir = ops_dir / "tasks" / "TASK-0100-data-readiness"
            write_json(task_dir / "artifacts" / "foundation_update_proposal.json", valid_new_source_proposal())
            before = file_snapshot(ops_dir)

            code, payload = run_cli_json(["data", "inspect-proposals", str(ops_dir), str(task_dir)])
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

    def test_existing_row_upsert_is_warning_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir = copy_starter(Path(tmpdir))
            proposal = valid_new_source_proposal(source_id="DS-0001")
            proposal["operations"] = [proposal["operations"][0]]
            proposal_path = Path(tmpdir) / "proposal.json"
            write_json(proposal_path, proposal)

            code, payload = run_cli_json(["data", "inspect-proposals", str(ops_dir), str(proposal_path)])

        self.assertEqual(0, code, payload)
        self.assertTrue(payload["ok"], payload)
        self.assertEqual(1, payload["valid_proposals"])
        self.assertEqual(1, len(payload["warnings"]))
        self.assertEqual("existing_row_upsert", payload["warnings"][0]["reason"])
        self.assertEqual("warning", payload["operations"][0]["status"])

    def test_duplicate_data_row_in_one_proposal_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir = copy_starter(Path(tmpdir))
            proposal = valid_new_source_proposal(source_id="DS-0101")
            proposal["operations"] = [
                proposal["operations"][0],
                operation(
                    "OP-0002",
                    "upsert_data_source",
                    "data_source_audit.md",
                    "DS-0101",
                    {
                        "source_id": "DS-0101",
                        "source_name": "Duplicate Fixture Source",
                    },
                ),
            ]
            proposal_path = Path(tmpdir) / "duplicate_proposal.json"
            write_json(proposal_path, proposal)

            code, payload = run_cli_json(["data", "inspect-proposals", str(ops_dir), str(proposal_path)])

        self.assertEqual(4, code, payload)
        self.assertFalse(payload["ok"])
        self.assertEqual(0, payload["valid_proposals"])
        self.assertEqual(1, payload["invalid_proposals"])
        reasons = {item.get("reason") for item in payload["operations"] + payload["blockers"]}
        self.assertIn("duplicate_proposed_row", reasons)

    def test_path_traversal_target_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir = copy_starter(Path(tmpdir))
            proposal = valid_new_source_proposal(source_id="DS-0102")
            proposal["operations"][0]["target_path"] = "../data_source_audit.md"
            proposal_path = Path(tmpdir) / "path_traversal_proposal.json"
            write_json(proposal_path, proposal)

            code, payload = run_cli_json(["data", "inspect-proposals", str(ops_dir), str(proposal_path)])

        self.assertEqual(4, code, payload)
        self.assertFalse(payload["ok"])
        reasons = {item["reason"] for item in payload["blockers"]}
        self.assertIn("invalid_target_path", reasons)

    def test_wrong_canonical_target_path_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir = copy_starter(Path(tmpdir))
            proposal = valid_new_source_proposal(source_id="DS-0104")
            proposal["operations"][0]["target_path"] = "data/data_catalog.md"
            proposal_path = Path(tmpdir) / "wrong_target_proposal.json"
            write_json(proposal_path, proposal)

            code, payload = run_cli_json(["data", "inspect-proposals", str(ops_dir), str(proposal_path)])

        self.assertEqual(4, code, payload)
        self.assertFalse(payload["ok"])
        reasons = {item["reason"] for item in payload["blockers"]}
        self.assertIn("unexpected_target_path", reasons)

    def test_unknown_operation_from_parser_blocks_inspection(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir = copy_starter(Path(tmpdir))
            proposal = valid_new_source_proposal(source_id="DS-0103")
            proposal["operations"][0]["operation"] = "rewrite_data_foundations"
            proposal_path = Path(tmpdir) / "unknown_operation_proposal.json"
            write_json(proposal_path, proposal)

            code, payload = run_cli_json(["data", "inspect-proposals", str(ops_dir), str(proposal_path)])

        self.assertEqual(4, code, payload)
        self.assertFalse(payload["ok"])
        reasons = {item["reason"] for item in payload["blockers"]}
        self.assertIn("unknown_operation", reasons)


if __name__ == "__main__":
    unittest.main()
