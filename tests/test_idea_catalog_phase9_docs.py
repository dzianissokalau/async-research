"""Regression tests for planner promotion guidance."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "src" / "async_research_workflow" / "docs"
TEMPLATES = ROOT / "src" / "async_research_workflow" / "templates"


def normalized(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


class IdeaCatalogPhase9DocsTests(unittest.TestCase):
    def assert_doc_contains(self, path: Path, snippets: list[str]) -> None:
        text = normalized(path)
        for snippet in snippets:
            self.assertIn(" ".join(snippet.split()), text, f"missing {snippet!r} from {path}")

    def test_planner_prompt_uses_catalog_promotion_write_mode(self) -> None:
        self.assert_doc_contains(
            DOCS / "scheduler_and_prompts.md",
            [
                "Run async-research idea catalog validate research_ops",
                "Run async-research idea catalog list research_ops --status promote",
                "For selected ideas, inspect async-research idea catalog show research_ops <IDEA-ID> and respect payload.score.max_promotions_per_week when present",
                "Before running promotion dry-run, scan research_ops/tasks/*/status.json for catalog_idea_id matching the selected IDEA ID",
                "run async-research idea promote research_ops <IDEA-ID> --dry-run",
                "Do not create a task directly from discovery_inbox.md",
                "Treat the promotion dry-run as authoritative",
                "Inspect `evidence_support.status`",
                "`missing_library_support` means unresolved `library_refs` need resolved row-level `LIT-*` source IDs",
                "If action is idea_promotion_blocked, do not write a task",
                "run async-research idea promote research_ops <IDEA-ID> --write --preflight-hash <promotion_preflight_hash>",
                "Do not hand-create task folders, task.md, status.json, or queue.md rows from the dry-run JSON",
                "If write mode returns action=idea_promotion_task_written, record task_id, task_dir, proposal_ref.proposal_id, transaction_id, and idempotency_key",
                "If write mode returns promotion_preflight_changed, rerun --dry-run",
                "Run async-research idea catalog dashboard research_ops",
                "link_status=available",
                "Do not run the former v1 park closeout after a successful or idempotent promotion write",
                "Do not use `async-research idea park` as a post-write promotion closeout",
                "Do not use `--allow-duplicate` without a recorded human decision or explicit planner note",
                "Do not create a second task from the same catalog idea unless an existing task scan, human decision, or explicit planner note proves the new task is a distinct follow-up",
            ],
        )

    def test_planner_prompt_limits_queue_writes_to_promotion_write_mode(self) -> None:
        text = normalized(DOCS / "scheduler_and_prompts.md")
        self.assertNotIn("catalog maintain --write queue", text)
        self.assertNotIn("idea promote --write queue", text)
        self.assertNotIn("catalog maintenance creates task folders", text)
        self.assertNotIn("planner creates task folders and queue rows", text)
        self.assertIn(
            "Keep catalog maintenance separate from task creation: `idea catalog maintain --write` never edits queue.md or tasks, while `idea promote --write` is the only catalog command that creates the reserved task folder and queue row.",
            normalized(DOCS / "scheduler_and_prompts.md"),
        )

    def test_core_docs_explain_discovery_catalog_queue_flow(self) -> None:
        self.assert_doc_contains(
            DOCS / "task_contracts.md",
            [
                "discovery_inbox.md -> async-research idea capture ... --write -> research_ops/ideas/IDEA-0001.json -> async-research idea promote research_ops IDEA-0001 --dry-run -> async-research idea promote research_ops IDEA-0001 --write --preflight-hash <hash> -> reserved TASK folder + queue.md row + promoted_task_id",
                "The promotion command is split into a read-only planning pass and a guarded write pass",
                "`evidence_support.status`",
                "`missing_library_support` means `library_refs` did not resolve against row-level source IDs in the generated `research_ops/library/source_library.md` block",
                "Do not create tasks from blocked proposals",
                "scan `research_ops/tasks/*/status.json` for `catalog_idea_id` matching the candidate idea",
                "Write mode uses `proposal.proposed_task_id` and `proposal.proposed_task_slug` as the reserved task identity",
                "The write transaction stages `task.md` and `status.json`, validates the staged task folder, appends `queue.md`, updates the canonical idea, and rolls back if post-write consistency fails.",
                "The promoted idea should have `status=promoted`, `promoted_task_id=<TASK-ID>`, and a dashboard `sections.idea_to_task_links` row with `link_status=available`.",
                "Do not run the former v1 park closeout after a successful or idempotent promotion write.",
                "`async-research idea park ... --reason \"promoted to <TASK-ID>\" --write` would replace `status=promoted` and break the `promoted_task_id` dashboard link.",
            ],
        )
        self.assert_doc_contains(
            DOCS / "idea_discovery_workflow.md",
            [
                "The planner must not turn a discovery inbox row directly into execution work",
                "async-research idea promote research_ops IDEA-0007 --dry-run",
                "async-research idea promote research_ops IDEA-0007 --write --preflight-hash <hash>",
                "the write must use the returned `promotion_preflight_hash`",
                "thin evidence -> `literature_extract`",
                "missing library support -> resolve `library_refs` against row-level source IDs in the generated `source_library.md` block or run `literature_extract` before library-dependent routes",
                "Promotion dry-run exposes `evidence_support.status`",
                "plausible but unaudited data -> `data_readiness`",
                "`experiment_plan` only when audited data refs and hard gates already pass",
                "`sections.idea_to_task_links` with `link_status=available`",
            ],
        )
        self.assert_doc_contains(
            DOCS / "workflow_blueprint.md",
            [
                "planner capture -> ideas/IDEA-*.json",
                "idea promote --dry-run -> idea promote --write --preflight-hash <hash>",
                "Run `async-research idea promote research_ops IDEA-0001 --dry-run`",
                "Inspect `evidence_support.status`",
                "Run `async-research idea promote research_ops IDEA-0001 --write --preflight-hash <promotion_preflight_hash>`",
                "Duplicate, blocked, parked, or rejected catalog ideas do not become execution tasks",
                "Let write mode create the reserved task folder, append the single `queue.md` row, append the `inbox.md` proposal reference, update `promoted_task_id`, and regenerate catalog projections.",
            ],
        )
        self.assert_doc_contains(
            DOCS / "idea_catalog_contract.md",
            [
                "Current Planner Promotion Behavior",
                "Promotion dry-run reports `evidence_support` separately from route choice",
                "`missing_library_support` means `library_refs` were present but did not resolve against row-level `source_id` values",
                "`idea promote --write` is the one catalog command allowed to create the reserved task folder and queue row.",
                "do not write tasks from blocked proposals",
                "skip ideas that already have a task `status.json` with matching `catalog_idea_id`",
                "do not hand-create task folders, `status.json`, `task.md`, or `queue.md` rows from the dry-run payload",
                "`link_status=available`",
                "do not run the former v1 park closeout after write success",
                "refresh any cached pre-V2.8 planner prompt",
            ],
        )

    def test_starter_readmes_include_planner_promotion_commands(self) -> None:
        snippets = [
            "Planner promotion should stay catalog-first",
            "Promotion write mode is the guarded helper",
            "async-research idea catalog validate research_ops",
            "async-research idea catalog list research_ops --status promote",
            "async-research idea promote research_ops IDEA-0001 --dry-run",
            "async-research idea promote research_ops IDEA-0001 --write --preflight-hash <hash>",
            "async-research idea catalog dashboard research_ops",
            "Let promotion write create the task folder",
            "`link_status=available`",
        ]
        self.assert_doc_contains(
            TEMPLATES / "generic_research_ops_starter" / "research_ops" / "README.md",
            snippets,
        )
        self.assert_doc_contains(
            TEMPLATES / "research_ops_starter" / "research_ops" / "README.md",
            snippets,
        )


if __name__ == "__main__":
    unittest.main()
