"""Regression tests for structured evidence memory and targeted reflection."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from async_research_workflow import cli


NOW = "2026-05-20T09:00:00Z"


def run_cli_json(argv: list[str | Path]) -> tuple[int, dict]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = cli.main([str(arg) for arg in argv])
    text = stream.getvalue().strip()
    return code, json.loads(text) if text else {}


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def sha256_text(text: str) -> str:
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def write_task(ops_dir: Path, task_id: str, title: str, *, status: str = "accepted") -> Path:
    task_dir = ops_dir / "tasks" / f"{task_id}-{title.lower().replace(' ', '-')}"
    write_json(
        task_dir / "status.json",
        {
            "schema_version": "1.0",
            "id": task_id,
            "title": title,
            "type": "literature_extract",
            "status": status,
            "previous_status": "awaiting_review",
            "last_transition_reason": "fixture",
            "priority": 2,
            "revision_count": 0,
            "max_revisions": 1,
            "revision_limit_hit": False,
            "allowed_paths": [f"research_ops/tasks/{task_dir.name}/**"],
            "max_minutes": 10,
            "requires_human": False,
            "budget": {"max_api_usd": 0.0, "max_compute_usd": 0.0},
            "human_gate_reason": None,
            "updated_at": NOW,
        },
    )
    return task_dir


def write_accepted_index(ops_dir: Path) -> None:
    (ops_dir / "accepted_outputs_index.md").write_text(
        "\n".join(
            [
                "| accepted_date | task_id | title | key_finding | claim_type | freshness_window_days | next_recheck_date | revalidation_status | source_ids | claim_strength | caveats | followups | supersedes | superseded_by | evidence_link |",
                "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
                "| 2026-01-01 | TASK-9001 | Coffee source quality memory | Coffee sourcing claim needs stronger provenance | descriptive | 30 | 2026-02-01 | stale | DS-9001 | moderate | none | none | none | none | tasks/TASK-9001-coffee-source-quality-memory/worker_output.md |",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def write_runtime_evidence(ops_dir: Path) -> None:
    snapshot_text = "Coffee claim is contradicted by the reviewed source.\n"
    snapshot_path = ops_dir / "runtime" / "snapshots" / "EVID-900001.txt"
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(snapshot_text, encoding="utf-8")
    write_jsonl(
        ops_dir / "runtime" / "evidence_objects.jsonl",
        [
            {
                "schema_version": "1.0",
                "framework_version": "runtime_evidence_object_v1.0",
                "evidence_id": "EVID-900001",
                "task_id": "TASK-9001",
                "adapter_type": "file_fetch",
                "source_uri": "fixture://coffee/source-quality",
                "source_title": "Coffee source quality fixture",
                "retrieved_at": NOW,
                "content_hash": sha256_text(snapshot_text),
                "snapshot_path": "research_ops/runtime/snapshots/EVID-900001.txt",
                "span_refs": [
                    {
                        "span_id": "SPAN-9001",
                        "span_type": "text",
                        "selector": "line:1",
                        "content_hash": sha256_text(snapshot_text),
                    }
                ],
                "license_or_use_policy": "fixture-only",
                "freshness_status": {"status": "stale", "checked_at": NOW, "basis": "offline fixture"},
                "cost": {"api_usd": 0.0, "compute_usd": 0.0, "tokens": 0, "basis": "offline fixture"},
                "permission_basis": {"type": "fixture", "reference": "research_ops/tasks/TASK-9001-coffee-source-quality-memory/status.json", "capability": "file_fetch"},
            }
        ],
    )


class EvidenceMemoryTests(unittest.TestCase):
    def init_ops(self, root: Path) -> Path:
        ops_dir = root / "research_ops"
        code, payload = run_cli_json(["init", ops_dir, "--template", "generic", "--force"])
        self.assertEqual(cli.SUCCESS, code, payload)
        return ops_dir

    def test_update_query_and_console_surface_stale_contradicted_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = write_task(ops_dir, "TASK-9001", "Coffee Source Quality Memory")
            write_accepted_index(ops_dir)
            write_runtime_evidence(ops_dir)
            write_json(
                task_dir / "artifacts" / "claim_verification.json",
                {
                    "claims": [
                        {
                            "claim_id": "CLM-9001",
                            "text": "Coffee fixture sources support the public quality claim.",
                            "claim_type": "descriptive",
                            "strength": "moderate",
                            "required_support_level": "direct",
                            "evidence_refs": [{"evidence_id": "EVID-900001"}],
                            "citation_refs": [{"evidence_id": "EVID-900001"}],
                            "verification_status": "contradicted",
                            "failure_reason": "reviewed source says the opposite",
                        }
                    ]
                },
            )
            write_json(
                ops_dir / "deliverables" / "deliverable_manifest.json",
                {
                    "schema_version": "1.0",
                    "framework_version": "deliverable_maturity_v1.0",
                    "deliverables": [
                        {
                            "deliverable_id": "DELIV-9001",
                            "title": "Coffee quality memo",
                            "target_maturity": "shareable_memo",
                            "source_task_ids": ["TASK-9001"],
                        }
                    ],
                },
            )

            code, payload = run_cli_json(["evidence-memory", "update", ops_dir, "--now", NOW])
            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertTrue((ops_dir / "memory" / "evidence_memory_index.json").exists())
            self.assertEqual(1, payload["entry_count"])
            self.assertEqual(1, payload["contradiction_count"])
            self.assertEqual(1, payload["stale_evidence_count"])
            entry = payload["entries"][0]
            self.assertEqual("contradicted", entry["freshness_status"])
            self.assertEqual(["CLM-9001"], entry["claim_ids"])
            self.assertEqual(["EVID-900001"], entry["evidence_ids"])
            self.assertEqual("DELIV-9001", entry["deliverable_links"][0]["deliverable_id"])

            query_code, query = run_cli_json(["evidence-memory", "query", ops_dir, "--contradictions-only", "--now", NOW])
            self.assertEqual(cli.SUCCESS, query_code, query)
            self.assertEqual(1, query["match_count"])
            self.assertEqual("TASK-9001", query["matches"][0]["task_id"])

            snapshot_code, snapshot = run_cli_json(["console", "snapshot", ops_dir, "--json", "--now", NOW])
            self.assertEqual(cli.SUCCESS, snapshot_code, snapshot)
            self.assertEqual(1, snapshot["evidence_memory"]["entry_count"])
            self.assertEqual(1, snapshot["evidence_memory"]["contradiction_count"])
            self.assertEqual(1, snapshot["evidence_memory"]["stale_evidence_count"])

    def test_reflection_record_injects_only_relevant_planner_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            coffee_task = write_task(ops_dir, "TASK-9101", "Coffee Source Review", status="rejected")
            housing_task = write_task(ops_dir, "TASK-9102", "Housing Rent Review", status="rejected")
            write_json(coffee_task / "review_panel" / "aggregate.json", {"decision": "rejected", "reason": "source quality"})
            write_json(housing_task / "review_panel" / "aggregate.json", {"decision": "rejected", "reason": "irrelevant"})

            coffee_code, coffee = run_cli_json(
                [
                    "reflection",
                    "record",
                    coffee_task,
                    "--failure-class",
                    "source_quality",
                    "--trigger-condition",
                    "coffee source quality used a general web source for a public claim",
                    "--affected-stage",
                    "planner",
                    "--mitigation",
                    "require official coffee datasets or reviewed sources before drafting",
                    "--anti-context",
                    "Do not use general web pages for coffee source quality claims.",
                    "--review-evidence",
                    "review_panel/aggregate.json",
                    "--now",
                    NOW,
                ]
            )
            self.assertEqual(cli.SUCCESS, coffee_code, coffee)
            housing_code, housing = run_cli_json(
                [
                    "reflection",
                    "record",
                    housing_task,
                    "--failure-class",
                    "scope_ambiguity",
                    "--trigger-condition",
                    "housing rent geography was ambiguous",
                    "--affected-stage",
                    "clarifier",
                    "--mitigation",
                    "ask for market geography before planning",
                    "--anti-context",
                    "Ask for rent market geography before planning.",
                    "--review-evidence",
                    "review_panel/aggregate.json",
                    "--now",
                    NOW,
                ]
            )
            self.assertEqual(cli.SUCCESS, housing_code, housing)

            anti_code, anti = run_cli_json(
                [
                    "anti-context",
                    "build",
                    ops_dir,
                    "--title",
                    "coffee source quality public claim plan",
                    "--threshold",
                    "0.12",
                ]
            )
            self.assertEqual(cli.SUCCESS, anti_code, anti)
            markdown = anti["markdown"]
            self.assertIn("### Targeted Reflections", markdown)
            self.assertIn("Do not use general web pages for coffee source quality claims.", markdown)
            self.assertNotIn("Ask for rent market geography before planning.", markdown)

            query_code, query = run_cli_json(
                [
                    "evidence-memory",
                    "query",
                    ops_dir,
                    "--query",
                    "coffee source quality",
                    "--failure-class",
                    "source_quality",
                    "--reflection-threshold",
                    "0.12",
                    "--now",
                    NOW,
                ]
            )
            self.assertEqual(cli.SUCCESS, query_code, query)
            self.assertEqual(1, query["targeted_reflection_count"])
            self.assertEqual("source_quality", query["targeted_reflections"][0]["failure_class"])


if __name__ == "__main__":
    unittest.main()
