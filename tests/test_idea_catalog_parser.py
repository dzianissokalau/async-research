"""Regression tests for the read-only idea catalog parser."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from async_research_workflow.idea_catalog import CATALOG_TEMPLATE
from async_research_workflow.idea_catalog import PRIORITIZATION_TEMPLATE
from async_research_workflow.idea_catalog import read_catalog


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, payload: dict) -> None:
    write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def candidate_payload(candidate_id: str, status: str = "candidate", failed_gate: bool = False) -> dict:
    return {
        "schema_version": "1.0",
        "id": candidate_id,
        "status": status,
        "title": f"Fixture {candidate_id}",
        "score": {
            "hard_gate_results": [
                {
                    "gate": "fixture_gate",
                    "passed": not failed_gate,
                    "reason": "fixture gate",
                }
            ]
        },
    }


def bootstrap_empty_catalog(ops_dir: Path) -> None:
    write_text(ops_dir / "ideas" / "idea_catalog.md", CATALOG_TEMPLATE)
    write_text(ops_dir / "ideas" / "prioritization.md", PRIORITIZATION_TEMPLATE)


def file_snapshot(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


class IdeaCatalogParserTests(unittest.TestCase):
    def test_empty_catalog_returns_zero_ideas_without_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            bootstrap_empty_catalog(ops_dir)

            model = read_catalog(ops_dir)

            self.assertTrue(model["ok"])
            self.assertEqual(0, model["candidate_count"])
            self.assertEqual({}, model["status_counts"])
            self.assertEqual({}, model["derived_label_counts"])
            self.assertEqual([], model["failures"])
            self.assertEqual([], model["warnings"])

    def test_missing_ideas_directory_returns_cold_start_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            ops_dir.mkdir()

            model = read_catalog(ops_dir)

            self.assertTrue(model["ok"])
            self.assertEqual(0, model["candidate_count"])
            self.assertEqual([], model["failures"])
            self.assertEqual(["catalog_cold_start"], [item["reason"] for item in model["warnings"]])

    def test_malformed_json_reports_path_and_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            bootstrap_empty_catalog(ops_dir)
            bad_path = ops_dir / "ideas" / "IDEA-0001.json"
            write_text(bad_path, "{not-json\n")

            model = read_catalog(ops_dir)

            self.assertFalse(model["ok"])
            self.assertEqual(0, model["candidate_count"])
            self.assertEqual("malformed_candidate_json", model["failures"][0]["reason"])
            self.assertEqual(str(bad_path), model["failures"][0]["path"])

    def test_duplicate_ids_and_filename_mismatch_are_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            bootstrap_empty_catalog(ops_dir)
            write_json(ops_dir / "ideas" / "IDEA-0001.json", candidate_payload("IDEA-0001"))
            write_json(ops_dir / "ideas" / "IDEA-0002.json", candidate_payload("IDEA-0001"))

            model = read_catalog(ops_dir)

            self.assertTrue(model["ok"])
            self.assertEqual(2, model["candidate_count"])
            self.assertEqual(["IDEA-0001"], sorted(model["duplicate_idea_ids"]))
            self.assertCountEqual(
                ["duplicate_idea_id", "filename_id_mismatch", "orphaned_json_record"],
                [item["reason"] for item in model["warnings"]],
            )

    def test_stale_markdown_projection_is_reported_as_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            catalog = """# Idea Catalog

<!-- IDEA-CATALOG: AUTO-MAINTAINED - DO NOT EDIT INSIDE THIS BLOCK -->
| idea_id | status | title | weighted_score | next_task | blockers | promoted_task_id | updated_at |
| --- | --- | --- | ---: | --- | --- | --- | --- |
| IDEA-9999 | candidate | Stale row | 1.0 | data_readiness | none |  | 2026-05-06 |
<!-- /IDEA-CATALOG -->

## Notes

Keep this.
"""
            write_text(ops_dir / "ideas" / "idea_catalog.md", catalog)
            write_text(ops_dir / "ideas" / "prioritization.md", PRIORITIZATION_TEMPLATE)
            write_json(ops_dir / "ideas" / "IDEA-0001.json", candidate_payload("IDEA-0001"))

            model = read_catalog(ops_dir)

            self.assertTrue(model["ok"])
            self.assertEqual(
                {
                    "json_ids": ["IDEA-0001"],
                    "catalog_row_ids": ["IDEA-9999"],
                    "duplicate_projection_rows": [],
                    "orphaned_projection_rows": ["IDEA-9999"],
                    "orphaned_json_records": ["IDEA-0001"],
                },
                model["projection_staleness"],
            )
            self.assertCountEqual(
                ["orphaned_projection_row", "orphaned_json_record"],
                [item["reason"] for item in model["warnings"]],
            )

    def test_status_and_derived_label_counts_are_summarized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            bootstrap_empty_catalog(ops_dir)
            write_json(ops_dir / "ideas" / "IDEA-0001.json", candidate_payload("IDEA-0001"))
            write_json(ops_dir / "ideas" / "IDEA-0002.json", candidate_payload("IDEA-0002", failed_gate=True))
            write_json(ops_dir / "ideas" / "IDEA-0003.json", candidate_payload("IDEA-0003", status="park"))

            model = read_catalog(ops_dir)

            self.assertEqual({"candidate": 2, "park": 1}, model["status_counts"])
            self.assertEqual({"blocked": 1, "park": 1, "scored": 1}, model["derived_label_counts"])

    def test_prioritization_generated_blocks_are_parsed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            write_text(ops_dir / "ideas" / "idea_catalog.md", CATALOG_TEMPLATE)
            prioritization = """# Idea Prioritization

<!-- IDEA-PRIORITIZATION: RECOMMENDED-PROMOTIONS AUTO-MAINTAINED -->
<!-- /IDEA-PRIORITIZATION: RECOMMENDED-PROMOTIONS -->

<!-- IDEA-PRIORITIZATION: PARKED AUTO-MAINTAINED -->
| idea_id | reason |
| --- | --- |
| IDEA-0003 | waiting for source |
<!-- /IDEA-PRIORITIZATION: PARKED -->

<!-- IDEA-PRIORITIZATION: REJECTED AUTO-MAINTAINED -->
<!-- /IDEA-PRIORITIZATION: REJECTED -->

<!-- IDEA-PRIORITIZATION: BLOCKERS AUTO-MAINTAINED -->
<!-- /IDEA-PRIORITIZATION: BLOCKERS -->
"""
            write_text(ops_dir / "ideas" / "prioritization.md", prioritization)

            model = read_catalog(ops_dir)

            parked_block = model["prioritization_projection"]["blocks"]["PARKED"]
            self.assertTrue(parked_block["present"])
            self.assertEqual(
                [{"idea_id": "IDEA-0003", "reason": "waiting for source"}],
                parked_block["table"]["rows"],
            )

    def test_parser_does_not_mutate_catalog_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            bootstrap_empty_catalog(ops_dir)
            write_json(ops_dir / "ideas" / "IDEA-0001.json", candidate_payload("IDEA-0001"))
            before = file_snapshot(ops_dir)

            read_catalog(ops_dir)

            self.assertEqual(before, file_snapshot(ops_dir))


if __name__ == "__main__":
    unittest.main()
