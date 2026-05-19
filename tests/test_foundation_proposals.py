"""Regression tests for shared foundation update proposal parsing."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from async_research_workflow.scripts import foundation_proposals


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def valid_data_proposal(proposal_id: str = "PROP-0001") -> dict:
    return {
        "proposal_version": "foundation_update_proposal_v1",
        "proposal_id": proposal_id,
        "source_task_id": "TASK-0001-data-readiness",
        "target": "data",
        "created_by": "worker",
        "rationale": "Add reviewed fixture source metadata.",
        "operations": [
            {
                "operation_id": "OP-0001",
                "operation": "upsert_data_source",
                "target_path": "data_source_audit.md",
                "row_id": "DS-0001",
                "payload": {
                    "source_id": "DS-0001",
                    "source_name": "Fixture Source",
                    "approval_status": "candidate",
                },
                "preserve_manual_notes": True,
            },
            {
                "operation_id": "OP-0002",
                "operation": "upsert_data_profile",
                "target_path": "data/profiles/DS-0001.md",
                "row_id": "DS-0001",
                "payload": {
                    "source_id": "DS-0001",
                    "approved_use_cases": "context",
                },
                "preserve_manual_notes": True,
            },
        ],
    }


def valid_library_proposal(proposal_id: str = "PROP-0002") -> dict:
    return {
        "proposal_version": "foundation_update_proposal_v1",
        "proposal_id": proposal_id,
        "source_task_id": "TASK-0002-literature-extract",
        "target": "library",
        "created_by": "worker",
        "rationale": "Add reviewed fixture source to the library.",
        "operations": [
            {
                "operation_id": "OP-0001",
                "operation": "upsert_lit_source",
                "target_path": "library/source_library.md",
                "row_id": "LIT-0001",
                "payload": {
                    "source_id": "LIT-0001",
                    "title": "Fixture Paper",
                    "status": "candidate",
                },
                "preserve_manual_notes": True,
            },
            {
                "operation_id": "OP-0002",
                "operation": "append_library_update_log",
                "target_path": "library/library_update_log.md",
                "row_id": "LOG-0001",
                "payload": {
                    "task_id": "TASK-0002",
                    "files_updated": "library/source_library.md",
                },
                "preserve_manual_notes": True,
            },
        ],
    }


class FoundationProposalParserTests(unittest.TestCase):
    def test_loads_valid_standalone_json_artifact_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp) / "research_ops" / "tasks" / "TASK-0001-data-readiness"
            proposal_path = task_dir / "artifacts" / "data_foundation_proposal.json"
            source_file = task_dir.parents[1] / "data_source_audit.md"
            source_file.parent.mkdir(parents=True, exist_ok=True)
            source_file.write_text("source-of-truth must not change\n", encoding="utf-8")
            write_json(proposal_path, valid_data_proposal())

            result = foundation_proposals.discover_task_proposals(task_dir)

            self.assertTrue(result.ok, result.to_dict())
            self.assertEqual(1, len(result.proposals))
            self.assertEqual("PROP-0001", result.proposals[0].proposal_id)
            self.assertEqual("data", result.proposals[0].target)
            self.assertEqual(2, len(result.proposals[0].operations))
            self.assertEqual("source-of-truth must not change\n", source_file.read_text(encoding="utf-8"))

    def test_loads_valid_worker_output_fenced_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp) / "research_ops" / "tasks" / "TASK-0002-literature-extract"
            worker_output = task_dir / "worker_output.md"
            worker_output.parent.mkdir(parents=True, exist_ok=True)
            worker_output.write_text(
                "Worker summary.\n\n"
                "```json foundation_update_proposal_v1\n"
                f"{json.dumps(valid_library_proposal(), indent=2)}\n"
                "```\n",
                encoding="utf-8",
            )

            result = foundation_proposals.discover_task_proposals(task_dir)

            self.assertTrue(result.ok, result.to_dict())
            self.assertEqual(1, len(result.proposals))
            proposal = result.proposals[0]
            self.assertEqual("worker_output_fence", proposal.source_type)
            self.assertEqual("library", proposal.target)
            self.assertEqual("LIT-0001", proposal.operations[0]["row_id"])

    def test_rejects_duplicate_proposal_ids_across_embedding_forms(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp) / "research_ops" / "tasks" / "TASK-0003-duplicate"
            write_json(task_dir / "artifacts" / "proposal.json", valid_data_proposal("PROP-0007"))
            worker_output = task_dir / "worker_output.md"
            worker_output.write_text(
                "```foundation_update_proposal_v1\n"
                f"{json.dumps(valid_library_proposal('PROP-0007'), indent=2)}\n"
                "```\n",
                encoding="utf-8",
            )

            result = foundation_proposals.discover_task_proposals(task_dir)

            self.assertFalse(result.ok)
            self.assertEqual(0, len(result.proposals))
            reasons = {item["reason"] for item in result.diagnostics}
            self.assertIn("duplicate_proposal_id", reasons)
            duplicate = next(item for item in result.diagnostics if item["reason"] == "duplicate_proposal_id")
            self.assertEqual("PROP-0007", duplicate["proposal_id"])
            self.assertIn("remediation", duplicate)

    def test_rejects_unknown_operation_with_structured_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad_proposal.json"
            payload = valid_data_proposal()
            payload["operations"][0]["operation"] = "rewrite_everything"
            write_json(path, payload)

            result = foundation_proposals.load_proposal_paths([path])

            self.assertFalse(result.ok)
            self.assertEqual(0, len(result.proposals))
            error = next(item for item in result.diagnostics if item["reason"] == "unknown_operation")
            self.assertEqual(str(path), error["path"])
            self.assertEqual("PROP-0001", error["proposal_id"])
            self.assertEqual("OP-0001", error["operation_id"])
            self.assertEqual("error", error["severity"])
            self.assertIn("remediation", error)

    def test_rejects_missing_required_field_with_remediation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "missing_field_proposal.json"
            payload = valid_library_proposal()
            del payload["source_task_id"]
            write_json(path, payload)

            result = foundation_proposals.load_proposal_paths([path])

            self.assertFalse(result.ok)
            reasons = [item["reason"] for item in result.diagnostics]
            self.assertIn("missing_proposal_field", reasons)
            self.assertIn("invalid_source_task_id", reasons)
            missing = next(item for item in result.diagnostics if item["reason"] == "missing_proposal_field")
            self.assertEqual("source_task_id", missing["field"])
            self.assertEqual("PROP-0002", missing["proposal_id"])
            self.assertIn("remediation", missing)

    def test_rejects_malformed_json_in_candidate_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp) / "research_ops" / "tasks" / "TASK-0004-malformed"
            path = task_dir / "artifacts" / "foundation_update_proposal.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('{"proposal_version": "foundation_update_proposal_v1",', encoding="utf-8")

            result = foundation_proposals.discover_task_proposals(task_dir)

            self.assertFalse(result.ok)
            self.assertEqual(0, len(result.proposals))
            error = result.diagnostics[0]
            self.assertEqual("malformed_json", error["reason"])
            self.assertEqual(str(path), error["path"])
            self.assertIn("line", error["location"])
            self.assertIn("remediation", error)

    def test_validates_target_path_row_id_payload_and_manual_notes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad_operation_proposal.json"
            payload = valid_data_proposal()
            payload["operations"][0].update(
                {
                    "target_path": "../data_source_audit.md",
                    "row_id": "SOURCE-1",
                    "payload": [],
                    "preserve_manual_notes": "yes",
                }
            )
            write_json(path, payload)

            result = foundation_proposals.load_proposal_paths([path])

            self.assertFalse(result.ok)
            reasons = {item["reason"] for item in result.diagnostics}
            self.assertIn("invalid_target_path", reasons)
            self.assertIn("invalid_row_id", reasons)
            self.assertIn("invalid_payload", reasons)
            self.assertIn("invalid_preserve_manual_notes", reasons)

    def test_module_main_prints_json_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "proposal.json"
            write_json(path, valid_data_proposal())
            stream = io.StringIO()

            with contextlib.redirect_stdout(stream):
                code = foundation_proposals.main([str(path)])

            payload = json.loads(stream.getvalue())
            self.assertEqual(foundation_proposals.SUCCESS, code)
            self.assertTrue(payload["ok"])
            self.assertEqual(1, payload["proposal_count"])


if __name__ == "__main__":
    unittest.main()
