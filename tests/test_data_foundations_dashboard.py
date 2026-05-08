"""Regression tests for the data-foundation dashboard surface."""

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
NOW = "2026-05-08"


def copy_starter(src: Path, tmp: Path) -> Path:
    target = tmp / "research_ops"
    shutil.copytree(src, target)
    return target


def run_cli_json(argv: list[str]) -> tuple[int, dict]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = cli.main(argv)
    return code, json.loads(stream.getvalue())


def workspace_snapshot(ops_dir: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(ops_dir)): path.read_bytes()
        for path in sorted(ops_dir.rglob("*"))
        if path.is_file()
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def audit_row(source_id: str, status: str, reviewed: str = "2026-05-08", freshness: str = "90") -> dict[str, str]:
    return {
        "source_id": source_id,
        "source_name": f"Fixture source {source_id}",
        "url_or_domain": f"https://example.test/{source_id.lower()}",
        "publisher_owner": "Fixture Publisher",
        "source_tier": "tier_1_official",
        "approval_status": status,
        "approved_use_cases": "experiment_planning; accepted_evidence" if status in {"approved", "approved_with_caveats"} else "none",
        "blocked_use_cases": "all" if status in {"blocked", "restricted", "deprecated"} else "none",
        "freshness_window_days": freshness,
        "known_limitations": "fixture limitations",
        "citation_requirements": f"cite {source_id}",
        "last_reviewed": reviewed,
        "approved_by": "tests" if status in {"approved", "approved_with_caveats"} else "none",
        "review_notes": "fixture row",
    }


def write_audit(ops_dir: Path, rows: list[dict[str, str]]) -> None:
    fields = [
        "source_id",
        "source_name",
        "url_or_domain",
        "publisher_owner",
        "source_tier",
        "approval_status",
        "approved_use_cases",
        "blocked_use_cases",
        "freshness_window_days",
        "known_limitations",
        "citation_requirements",
        "last_reviewed",
        "approved_by",
        "review_notes",
    ]
    lines = [
        "# Data Source Audit Register",
        "",
        "Schema version: 1.0",
        "",
        "| " + " | ".join(fields) + " |",
        "| " + " | ".join("---" for _ in fields) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(row.get(field, "") for field in fields) + " |")
    (ops_dir / "data_source_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def append_known_gap(ops_dir: Path, gap_id: str) -> None:
    path = ops_dir / "data" / "known_data_gaps.md"
    text = path.read_text(encoding="utf-8")
    row = f"| {gap_id} | open | IDEA-9001 | fixture dataset | fixture blocker | create data-readiness task |\n"
    path.write_text(text.replace("| --- | --- | --- | --- | --- | --- |\n", "| --- | --- | --- | --- | --- | --- |\n" + row), encoding="utf-8")


def valid_candidate(candidate_id: str, gap_id: str) -> dict:
    return {
        "schema_version": "1.0",
        "id": candidate_id,
        "status": "candidate",
        "title": "Fixture data gap idea",
        "question": f"Can {gap_id} be resolved before experiment planning?",
        "why_it_might_matter": "It proves dashboard gap surfacing.",
        "required_data": [gap_id],
        "minimum_viable_test": "Run a bounded data-readiness check.",
        "baseline": "Compare against current no-data state.",
        "main_risks": ["data gap remains open"],
        "kill_reason": "Reject if fixture data cannot be approved.",
        "recommended_next_task": "data_readiness",
        "created_at": "2026-05-08T00:00:00Z",
        "updated_at": "2026-05-08T00:00:00Z",
    }


class DataFoundationsDashboardTests(unittest.TestCase):
    def test_real_estate_dashboard_renders_required_sections_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir = copy_starter(REAL_ESTATE_STARTER, Path(tmpdir))
            before = workspace_snapshot(ops_dir)

            code, payload = run_cli_json(["data", "dashboard", str(ops_dir), "--now", NOW])

            self.assertEqual(0, code, payload)
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["read_only"])
            self.assertFalse(payload["changed"])
            self.assertEqual(before, workspace_snapshot(ops_dir))
            self.assertEqual(3, payload["summary"]["usable_today_count"])
            self.assertEqual(3, payload["summary"]["approved_source_count"])
            self.assertEqual(3, payload["summary"]["data_gap_count"])
            self.assertEqual(2, payload["summary"]["join_path_count"])
            for section in (
                "usable_today_sources",
                "approved_sources",
                "candidate_sources",
                "blocked_sources",
                "stale_source_reviews",
                "data_gaps",
                "ideas_blocked_by_data",
                "join_paths",
                "join_caveats",
            ):
                self.assertIn(section, payload["sections"])

    def test_dashboard_groups_candidate_blocked_and_stale_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir = copy_starter(GENERIC_STARTER, Path(tmpdir))
            write_audit(
                ops_dir,
                [
                    audit_row("DS-0001", "approved", reviewed="2025-01-01", freshness="30"),
                    audit_row("DS-0002", "candidate"),
                    audit_row("DS-0003", "blocked"),
                ],
            )
            join_path = ops_dir / "data" / "join_map.md"
            join_text = join_path.read_text(encoding="utf-8")
            join_text = join_text.replace(
                "| --- | --- | --- | --- | --- | --- | --- |\n",
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| JOIN-9001 | DS-0001 | DS-0002 | fixture key | fixture grain | plausible_with_caveats | candidate source needs audit |\n",
            )
            join_path.write_text(join_text, encoding="utf-8")

            code, payload = run_cli_json(["data", "dashboard", str(ops_dir), "--now", NOW])

            self.assertEqual(2, code, payload)
            self.assertTrue(payload["ok"])
            self.assertEqual(["DS-0002"], [row["source_id"] for row in payload["sections"]["candidate_sources"]])
            self.assertEqual(["DS-0003"], [row["source_id"] for row in payload["sections"]["blocked_sources"]])
            self.assertEqual(["DS-0001"], [row["source_id"] for row in payload["sections"]["stale_source_reviews"]])
            self.assertEqual(0, payload["summary"]["usable_today_count"])
            self.assertEqual(1, payload["summary"]["join_caveat_count"])

    def test_dashboard_shows_ideas_blocked_by_data_gap_refs_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir = copy_starter(GENERIC_STARTER, Path(tmpdir))
            append_known_gap(ops_dir, "DG-9001")
            write_json(ops_dir / "ideas" / "IDEA-9001.json", valid_candidate("IDEA-9001", "DG-9001"))
            before = workspace_snapshot(ops_dir)

            code, payload = run_cli_json(["data", "dashboard", str(ops_dir), "--now", NOW])

            self.assertEqual(0, code, payload)
            self.assertEqual(before, workspace_snapshot(ops_dir))
            self.assertEqual(["IDEA-9001"], payload["operator_summary"]["blocked_idea_ids"])
            blocked = payload["sections"]["ideas_blocked_by_data"][0]
            self.assertEqual(["DG-9001"], blocked["gap_ids"])
            self.assertIn("active_idea_data_gap_ref", blocked["reasons"])

    def test_dashboard_returns_malformed_exit_for_broken_data_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir = copy_starter(GENERIC_STARTER, Path(tmpdir))
            (ops_dir / "data" / "data_catalog.md").write_text(
                "# Broken Catalog\n\n| one | two |\n| --- | --- |\n| one-cell |\n",
                encoding="utf-8",
            )

            code, payload = run_cli_json(["data", "dashboard", str(ops_dir), "--now", NOW])

            self.assertEqual(4, code, payload)
            self.assertFalse(payload["ok"])
            self.assertEqual(4, payload["validation_exit_code"])
            self.assertTrue(payload["read_only"])
            self.assertIn("validator_findings", payload["sections"])


if __name__ == "__main__":
    unittest.main()
