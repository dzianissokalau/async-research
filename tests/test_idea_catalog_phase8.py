"""Regression tests for Phase 8 idea catalog promotion dry run."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from async_research_workflow import cli


def run_cli_json(argv: list[str | Path]) -> tuple[int, dict]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = cli.main([str(arg) for arg in argv])
    return code, json.loads(stream.getvalue())


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, payload: dict) -> None:
    write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def write_source_library_rows(ops_dir: Path, rows: list[list[str]], notes: str = "") -> None:
    body = [
        "# Source Library",
        "",
        "<!-- LIBRARY-SOURCES: schema_version=1.0 -->",
        "| source_id | status | trust_tier | type | title | author_or_publisher | location | reviewed_date | notes |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        *["| " + " | ".join(row) + " |" for row in rows],
        "<!-- /LIBRARY-SOURCES -->",
        "",
        "## Notes",
        "",
        "Free-form notes. Tooling must not edit this section.",
    ]
    if notes:
        body.extend(["", notes])
    write_text(ops_dir / "library" / "source_library.md", "\n".join(body) + "\n")


def file_snapshot(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def valid_score() -> dict:
    return {
        "mission_policy_version": "test_policy_v1.0",
        "budget_mode": "normal",
        "decision_impact": 4,
        "novelty": 3,
        "data_availability": 4,
        "feasibility": 4,
        "robustness_risk": 2,
        "cost": 2,
        "killability": 4,
        "reuse_potential": 4,
        "weighted_total": 16.5,
        "promotion_threshold": 14.0,
        "minimum_killability": 3,
        "max_promotions_per_week": 3,
        "budget_pressure_threshold": 0.8,
        "budget_mode_reason": "manual_normal",
        "budget_usage": {
            "monthly_usage_ratio": None,
            "weekly_usage_ratio": None,
            "monthly_cost_usd": 0.0,
            "weekly_cost_usd": 0.0,
            "monthly_budget_usd": None,
            "weekly_budget_usd": None,
        },
        "hard_gate_results": [{"gate": "research_question_present", "passed": True, "reason": "question is present"}],
        "score_explanation": "Fixture score for catalog phase 8 tests.",
    }


def promotable_candidate(candidate_id: str, title: str = "Promotable catalog idea") -> dict:
    return {
        "schema_version": "1.0",
        "id": candidate_id,
        "status": "promote",
        "title": title,
        "question": "Can the fixture idea be validated cheaply?",
        "why_it_might_matter": "It checks catalog promotion behavior.",
        "required_data": ["public fixture data"],
        "minimum_viable_test": "Run a bounded data-readiness check.",
        "baseline": "Compare against a simple baseline.",
        "main_risks": ["fixture risk"],
        "kill_reason": "Reject if fixture data is unavailable.",
        "score": valid_score(),
        "recommended_next_task": "data_readiness",
    }


class IdeaCatalogPhase8Tests(unittest.TestCase):
    def init_ops(self, root: Path) -> Path:
        ops_dir = root / "research_ops"
        code, payload = run_cli_json(["init", ops_dir, "--force"])
        self.assertEqual(cli.SUCCESS, code, payload)
        return ops_dir

    def write_audited_source(self, ops_dir: Path, source_id: str = "DS-0001") -> None:
        write_text(
            ops_dir / "data_source_audit.md",
            "\n".join(
                [
                    "# Data Source Audit",
                    "",
                    "| source_id | source_name | url_or_domain | publisher_owner | source_tier | approval_status | approved_use_cases | prohibited_use_cases | freshness_window_days | limitations | citation_requirements | last_reviewed_at | approved_by | review_notes |",
                    "| --- | --- | --- | --- | --- | --- | --- | --- | ---: | --- | --- | --- | --- | --- |",
                    f"| {source_id} | Fixture source | https://example.test | Fixture | tier_1_official | approved | experiment_planning; accepted_evidence | none | 30 | none | cite fixture | 2026-05-07 | tests | ready |",
                    "",
                ]
            ),
        )

    def test_promote_dry_run_proposes_one_bounded_task_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            self.write_audited_source(ops_dir)
            candidate = promotable_candidate("IDEA-7301", "Audited data idea")
            candidate["data_refs"] = ["DS-0001"]
            write_json(ops_dir / "ideas" / "IDEA-7301.json", candidate)
            before = file_snapshot(ops_dir)

            code, payload = run_cli_json(["idea", "promote", ops_dir, "IDEA-7301", "--dry-run"])

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertEqual("idea_promotion_planned", payload["action"])
            self.assertFalse(payload["changed"])
            proposal = payload["proposal"]
            self.assertEqual("data_readiness", proposal["task_type"])
            self.assertEqual("catalog_recommended_next_task", proposal["route_reason"])
            self.assertEqual("TASK-7301-data-readiness", proposal["proposed_task_slug"])
            self.assertEqual("TASK-7301", proposal["proposed_task_id"])
            self.assertEqual(["DS-0001"], proposal["data_refs"])
            self.assertIn("max_minutes", proposal)
            self.assertIn("max_turns", proposal)
            self.assertIn("async-research source validate research_ops", proposal["validation_commands"])
            self.assertIn("async-research data validate research_ops", proposal["validation_commands"])
            self.assertIn("research_ops/data_source_audit.md", proposal["allowed_paths"])
            self.assertIn("research_ops/data/**", proposal["allowed_paths"])
            self.assertIn("task_markdown_draft", proposal)
            for snippet in [
                "Profile draft or update",
                "Recommended audit status",
                "Access check result",
                "Field/grain coverage",
                "Join feasibility",
                "Known limitations",
                "Recommended next task",
                "Kill reason if data is unusable",
            ]:
                self.assertIn(snippet, proposal["task_markdown_draft"])
            self.assertIn("status_json_draft", proposal)
            blocked_paths = {item["path"] for item in payload["would_not_write"]}
            self.assertIn(str(ops_dir / "queue.md"), blocked_paths)
            self.assertIn(str(ops_dir / "tasks"), blocked_paths)
            self.assertEqual(before, file_snapshot(ops_dir))

    def test_promote_uses_evidence_and_override_routing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            thin = promotable_candidate("IDEA-7302", "Thin evidence idea")
            write_json(ops_dir / "ideas" / "IDEA-7302.json", thin)

            thin_code, thin_payload = run_cli_json(["idea", "promote", ops_dir, "IDEA-7302"])
            self.assertEqual(cli.SUCCESS, thin_code, thin_payload)
            self.assertEqual("literature_extract", thin_payload["proposal"]["task_type"])
            self.assertEqual("evidence_is_thin", thin_payload["proposal"]["route_reason"])
            self.assertEqual("thin_evidence", thin_payload["evidence_support"]["status"])
            self.assertEqual("thin_evidence", thin_payload["proposal"]["evidence_support"]["status"])
            self.assertIn(
                "async-research library validate research_ops",
                thin_payload["proposal"]["validation_commands"],
            )
            self.assertNotIn("research_ops/library/**", thin_payload["proposal"]["allowed_paths"])
            for snippet in [
                "Proposed `source_library.md` rows",
                "Proposed `knowledge_index.md` rows",
                "Proposed `claim_map.md` rows",
                "Proposed `method_index.md` rows",
                "Proposed `open_questions.md` rows",
                "library_update_log.md",
                "Human approval flag for high-stakes claims",
            ]:
                self.assertIn(snippet, thin_payload["proposal"]["task_markdown_draft"])

            override_code, override_payload = run_cli_json(
                ["idea", "promote", ops_dir, "IDEA-7302", "--task-type", "hypothesis_card"]
            )
            self.assertEqual(cli.SUCCESS, override_code, override_payload)
            self.assertEqual("hypothesis_card", override_payload["proposal"]["task_type"])
            self.assertEqual("explicit_task_type_override", override_payload["proposal"]["route_reason"])

    def test_promote_blocks_invalid_status_and_failed_gates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            parked = promotable_candidate("IDEA-7303", "Parked idea")
            parked["status"] = "park"
            parked["status_reason"] = "not now"
            parked["revisit_condition"] = "after data release"
            write_json(ops_dir / "ideas" / "IDEA-7303.json", parked)
            blocked = promotable_candidate("IDEA-7304", "Blocked idea")
            blocked["score"]["hard_gate_results"] = [
                {"gate": "data_readiness", "passed": False, "reason": "source unavailable"}
            ]
            write_json(ops_dir / "ideas" / "IDEA-7304.json", blocked)

            parked_code, parked_payload = run_cli_json(["idea", "promote", ops_dir, "IDEA-7303"])
            self.assertEqual(2, parked_code, parked_payload)
            self.assertEqual("idea_promotion_blocked", parked_payload["action"])
            self.assertEqual("status_not_promotable", parked_payload["blockers"][0]["reason"])
            self.assertIn("idea catalog show", parked_payload["next_step"])
            self.assertEqual("status_not_promotable", parked_payload["remediation_steps"][0]["reason"])
            self.assertIsNone(parked_payload["proposal"])

            blocked_code, blocked_payload = run_cli_json(["idea", "promote", ops_dir, "IDEA-7304"])
            self.assertEqual(2, blocked_code, blocked_payload)
            self.assertTrue(any(item["reason"] == "failed_hard_gates" for item in blocked_payload["blockers"]))
            hard_gate_step = next(item for item in blocked_payload["remediation_steps"] if item["reason"] == "failed_hard_gates")
            self.assertIn("idea resolve", hard_gate_step["next_step"])
            self.assertFalse(
                any(
                    item.get("reason") == "catalog_validation_failure"
                    and item.get("failure_reason") == "promote_failed_hard_gates"
                    for item in blocked_payload["blockers"]
                )
            )

    def test_promote_candidate_status_uses_lifecycle_recommendation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            ready = promotable_candidate("IDEA-7310", "Candidate ready idea")
            ready["status"] = "candidate"
            write_json(ops_dir / "ideas" / "IDEA-7310.json", ready)

            ready_code, ready_payload = run_cli_json(["idea", "promote", ops_dir, "IDEA-7310"])

            self.assertEqual(cli.SUCCESS, ready_code, ready_payload)
            self.assertEqual("idea_promotion_planned", ready_payload["action"])
            self.assertEqual("literature_extract", ready_payload["proposal"]["task_type"])

    def test_promote_candidate_below_threshold_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            below = promotable_candidate("IDEA-7311", "Candidate below threshold")
            below["status"] = "candidate"
            below["score"]["weighted_total"] = 5.0
            write_json(ops_dir / "ideas" / "IDEA-7311.json", below)

            code, payload = run_cli_json(["idea", "promote", ops_dir, "IDEA-7311"])

            self.assertEqual(2, code, payload)
            self.assertTrue(any(item["reason"] == "candidate_not_ready_for_promotion" for item in payload["blockers"]))
            self.assertIn("candidate lifecycle recommendation", payload["remediation_steps"][0]["message"])
            self.assertIsNone(payload["proposal"])

    def test_promote_routes_plausible_unaudited_data_to_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            candidate = promotable_candidate("IDEA-7312", "Unaudited data idea")
            candidate["recommended_next_task"] = "hypothesis_card"
            candidate["library_refs"] = ["LIT-7312"]
            write_json(ops_dir / "ideas" / "IDEA-7312.json", candidate)

            code, payload = run_cli_json(["idea", "promote", ops_dir, "IDEA-7312"])

            self.assertEqual(cli.SUCCESS, code, payload)
            proposal = payload["proposal"]
            self.assertEqual("data_readiness", proposal["task_type"])
            self.assertEqual("data_plausible_but_unaudited", proposal["route_reason"])
            self.assertEqual("missing_library_support", payload["evidence_support"]["status"])
            self.assertEqual(["LIT-7312"], payload["evidence_support"]["library_support"]["unresolved_refs"])
            self.assertEqual("missing_library_support", proposal["evidence_support"]["status"])
            self.assertTrue(
                any(
                    item["reason"] == "non_blocking_catalog_warning"
                    and item["warning_reason"] == "library_ref_unresolved"
                    and item["ref"] == "LIT-7312"
                    and item["target"].endswith("research_ops/library/source_library.md")
                    and item["blocking"] is False
                    for item in payload["blockers"]
                )
            )

    def test_promote_blocks_library_required_route_when_library_ref_is_unresolved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            candidate = promotable_candidate("IDEA-7313", "Missing library support idea")
            candidate["recommended_next_task"] = "hypothesis_card"
            candidate["required_data"] = []
            candidate["library_refs"] = ["LIT-7313"]
            write_json(ops_dir / "ideas" / "IDEA-7313.json", candidate)

            code, payload = run_cli_json(["idea", "promote", ops_dir, "IDEA-7313"])

            self.assertEqual(2, code, payload)
            self.assertEqual("idea_promotion_blocked", payload["action"])
            self.assertEqual("hypothesis_card", payload["selected_task_type"])
            self.assertEqual("missing_library_support", payload["evidence_support"]["status"])
            blocker = next(item for item in payload["blockers"] if item["reason"] == "missing_library_support")
            self.assertEqual(["LIT-7313"], blocker["unresolved_refs"])
            self.assertTrue(blocker["target"].endswith("research_ops/library/source_library.md"))
            step = next(item for item in payload["remediation_steps"] if item["reason"] == "missing_library_support")
            self.assertIn("library validate", step["next_step"])
            self.assertIsNone(payload["proposal"])

    def test_promote_allows_library_required_route_when_library_ref_resolves(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            candidate = promotable_candidate("IDEA-7314", "Resolved library support idea")
            candidate["recommended_next_task"] = "hypothesis_card"
            candidate["required_data"] = []
            candidate["library_refs"] = ["LIT-7314"]
            write_json(ops_dir / "ideas" / "IDEA-7314.json", candidate)
            write_source_library_rows(
                ops_dir,
                [
                    [
                        "LIT-7314",
                        "trusted",
                        "supporting",
                        "article",
                        "Fixture source",
                        "Fixture Publisher",
                        "https://example.test/lit-7314",
                        "2026-05-09",
                        "ready",
                    ]
                ],
            )

            code, payload = run_cli_json(["idea", "promote", ops_dir, "IDEA-7314"])

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertEqual("hypothesis_card", payload["proposal"]["task_type"])
            self.assertEqual("supported", payload["evidence_support"]["status"])
            self.assertEqual(["LIT-7314"], payload["evidence_support"]["library_support"]["resolved_refs"])
            self.assertEqual(
                "source_library_generated_rows",
                payload["evidence_support"]["library_support"]["resolution"],
            )

    def test_promote_does_not_count_notes_text_as_library_source_row_support(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            candidate = promotable_candidate("IDEA-7316", "Notes-only library support idea")
            candidate["recommended_next_task"] = "hypothesis_card"
            candidate["required_data"] = []
            candidate["library_refs"] = ["LIT-7316"]
            write_json(ops_dir / "ideas" / "IDEA-7316.json", candidate)
            write_source_library_rows(ops_dir, [], "This note mentions LIT-7316 but is not a generated source row.")

            code, payload = run_cli_json(["idea", "promote", ops_dir, "IDEA-7316"])

            self.assertEqual(2, code, payload)
            self.assertEqual("idea_promotion_blocked", payload["action"])
            self.assertEqual("missing_library_support", payload["evidence_support"]["status"])
            library_support = payload["evidence_support"]["library_support"]
            self.assertEqual("source_library_generated_rows", library_support["resolution"])
            self.assertEqual([], library_support["resolved_refs"])
            self.assertEqual(["LIT-7316"], library_support["unresolved_refs"])

    def test_promote_blocks_library_required_route_when_source_row_has_validator_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            candidate = promotable_candidate("IDEA-7317", "Invalid library source row idea")
            candidate["recommended_next_task"] = "hypothesis_card"
            candidate["required_data"] = []
            candidate["library_refs"] = ["LIT-7317"]
            write_json(ops_dir / "ideas" / "IDEA-7317.json", candidate)
            write_source_library_rows(
                ops_dir,
                [
                    [
                        "LIT-7317",
                        "approved",
                        "tier_1",
                        "article",
                        "Fixture source",
                        "Fixture Publisher",
                        "https://example.test/lit-7317",
                        "2026-05-09",
                        "invalid vocabulary on purpose",
                    ]
                ],
            )

            code, payload = run_cli_json(["idea", "promote", ops_dir, "IDEA-7317"])

            self.assertEqual(2, code, payload)
            self.assertEqual("idea_promotion_blocked", payload["action"])
            self.assertEqual("invalid_library_support", payload["evidence_support"]["status"])
            library_support = payload["evidence_support"]["library_support"]
            self.assertEqual(["LIT-7317"], library_support["resolved_refs"])
            blocker = next(item for item in payload["blockers"] if item["reason"] == "invalid_library_support")
            error_reasons = {item["reason"] for item in blocker["resolution_errors"]}
            self.assertIn("invalid_library_source_status", error_reasons)
            self.assertIn("invalid_library_trust_tier", error_reasons)
            self.assertIsNone(payload["proposal"])

    def test_promote_keeps_partial_library_support_warning_nonblocking_when_other_evidence_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            candidate = promotable_candidate("IDEA-7315", "Partial library support idea")
            candidate["recommended_next_task"] = "hypothesis_card"
            candidate["required_data"] = []
            candidate["library_refs"] = ["LIT-7315"]
            candidate["accepted_output_refs"] = ["TASK-7315"]
            write_json(ops_dir / "ideas" / "IDEA-7315.json", candidate)
            write_text(ops_dir / "accepted_outputs_index.md", "# Accepted Outputs\n\nTASK-7315\n")

            code, payload = run_cli_json(["idea", "promote", ops_dir, "IDEA-7315"])

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertEqual("hypothesis_card", payload["proposal"]["task_type"])
            self.assertEqual("partial_library_support", payload["evidence_support"]["status"])
            self.assertFalse(any(item["reason"] == "missing_library_support" for item in payload["blockers"]))

    def test_promote_duplicate_requires_explicit_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            self.write_audited_source(ops_dir)
            duplicate = promotable_candidate("IDEA-7305", "Duplicate idea")
            duplicate["data_refs"] = ["DS-0001"]
            duplicate["duplicate_status"] = "near_duplicate"
            write_json(ops_dir / "ideas" / "IDEA-7305.json", duplicate)

            code, payload = run_cli_json(["idea", "promote", ops_dir, "IDEA-7305"])
            self.assertEqual(2, code, payload)
            self.assertTrue(any(item["reason"] == "duplicate_requires_human_override" for item in payload["blockers"]))

            override_code, override_payload = run_cli_json(["idea", "promote", ops_dir, "IDEA-7305", "--allow-duplicate"])
            self.assertEqual(cli.SUCCESS, override_code, override_payload)
            self.assertTrue(override_payload["proposal"]["human_override"]["duplicate_allowed"])

    def test_promote_requires_exact_data_ref_audit_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            self.write_audited_source(ops_dir, "DS-7309")
            candidate = promotable_candidate("IDEA-7308", "Exact audit ref")
            candidate["data_refs"] = ["DS-7308"]
            candidate["recommended_next_task"] = "experiment_plan"
            write_json(ops_dir / "ideas" / "IDEA-7308.json", candidate)

            code, payload = run_cli_json(["idea", "promote", ops_dir, "IDEA-7308", "--task-type", "experiment_plan"])

            self.assertEqual(2, code, payload)
            self.assertTrue(any(item["reason"] == "experiment_plan_gates_not_met" for item in payload["blockers"]))
            step = next(item for item in payload["remediation_steps"] if item["reason"] == "experiment_plan_gates_not_met")
            self.assertIn("--task-type data_readiness", step["next_step"])

    def test_promote_experiment_plan_requires_audited_data_refs_and_passed_gates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            no_audit = promotable_candidate("IDEA-7306", "No audited data")
            write_json(ops_dir / "ideas" / "IDEA-7306.json", no_audit)

            no_audit_code, no_audit_payload = run_cli_json(
                ["idea", "promote", ops_dir, "IDEA-7306", "--task-type", "experiment_plan"]
            )
            self.assertEqual(2, no_audit_code, no_audit_payload)
            self.assertTrue(any(item["reason"] == "experiment_plan_gates_not_met" for item in no_audit_payload["blockers"]))

            self.write_audited_source(ops_dir)
            ready = promotable_candidate("IDEA-7307", "Experiment ready idea")
            ready["data_refs"] = ["DS-0001"]
            write_json(ops_dir / "ideas" / "IDEA-7307.json", ready)

            ready_code, ready_payload = run_cli_json(
                ["idea", "promote", ops_dir, "IDEA-7307", "--task-type", "experiment_plan"]
            )
            self.assertEqual(cli.SUCCESS, ready_code, ready_payload)
            proposal = ready_payload["proposal"]
            self.assertEqual("experiment_plan", proposal["task_type"])
            self.assertEqual(2, proposal["status_json_draft"]["review_policy"]["tier"])
            self.assertTrue(any("source check-experiment" in command for command in proposal["validation_commands"]))


if __name__ == "__main__":
    unittest.main()
