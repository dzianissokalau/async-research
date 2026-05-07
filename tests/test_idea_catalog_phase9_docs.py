"""Regression tests for Phase 9 planner promotion guidance."""

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

    def test_planner_prompt_uses_catalog_promotion_dry_run(self) -> None:
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
                "If action is idea_promotion_blocked, do not create a task",
                "using proposal.proposed_task_id and proposal.proposed_task_slug",
                "replacing TASK-PROPOSED in proposal.task_markdown_draft and proposal.status_json_draft",
                "Append queue.md only after task.md, status.json, anti_context.md, source checks, and transition/schema checks are coherent",
                "close the v1 catalog loop so the same idea is not promoted again next run",
                "async-research idea park research_ops <IDEA-ID> --reason \"promoted to <TASK-ID>\"",
                "Do not use `--allow-duplicate` without a recorded human decision or explicit planner note",
                "Do not create a second task from the same catalog idea unless an existing task scan, human decision, or explicit planner note proves the new task is a distinct follow-up",
            ],
        )

    def test_planner_prompt_does_not_make_catalog_a_queue_writer(self) -> None:
        text = normalized(DOCS / "scheduler_and_prompts.md")
        self.assertNotIn("catalog maintain --write queue", text)
        self.assertNotIn("idea promote --write queue", text)
        self.assertNotIn("catalog maintenance creates task folders", text)

    def test_core_docs_explain_discovery_catalog_queue_flow(self) -> None:
        self.assert_doc_contains(
            DOCS / "task_contracts.md",
            [
                "discovery_inbox.md -> async-research idea capture ... --write -> research_ops/ideas/IDEA-0001.json -> async-research idea promote research_ops IDEA-0001 --dry-run -> planner-created TASK folder -> queue.md row",
                "The promotion command is a dry-run proposal in v1",
                "Do not create tasks from blocked proposals",
                "scan `research_ops/tasks/*/status.json` for `catalog_idea_id` matching the candidate idea",
                "use `proposal.proposed_task_id` and `proposal.proposed_task_slug` as the reserved task identity",
                "Append the `queue.md` row only after `task.md`, `status.json`, `anti_context.md`, source checks, and applicable proposal validation commands pass",
                "After appending `queue.md`, close the v1 catalog loop",
                "This is a v1 planner closeout convention, not the V2 promoted-task transaction",
            ],
        )
        self.assert_doc_contains(
            DOCS / "idea_discovery_workflow.md",
            [
                "The planner must not turn a discovery inbox row directly into execution work",
                "async-research idea promote research_ops IDEA-0007 --dry-run",
                "thin evidence -> `literature_extract`",
                "plausible but unaudited data -> `data_readiness`",
                "`experiment_plan` only when audited data refs and hard gates already pass",
            ],
        )
        self.assert_doc_contains(
            DOCS / "workflow_blueprint.md",
            [
                "planner capture -> ideas/IDEA-*.json",
                "idea promote --dry-run -> planner-created task -> queue.md",
                "Run `async-research idea promote research_ops IDEA-0001 --dry-run`",
                "Duplicate, blocked, parked, or rejected catalog ideas do not become execution tasks",
                "Use `proposal.proposed_task_id` and `proposal.proposed_task_slug` as the reserved task identity",
            ],
        )
        self.assert_doc_contains(
            DOCS / "idea_catalog_contract.md",
            [
                "Phase 9 Planner Promotion Behavior",
                "Catalog commands own portfolio state and proposal generation. The planner owns execution task creation.",
                "do not create tasks from blocked proposals",
                "skip ideas that already have a task `status.json` with matching `catalog_idea_id`",
                "append `queue.md` only after task files, anti-context, source checks, and applicable validation commands are coherent",
                "The park closeout is a temporary v1 planner convention to prevent repeat promotion",
            ],
        )

    def test_starter_readmes_include_planner_promotion_commands(self) -> None:
        snippets = [
            "Planner promotion should stay catalog-first",
            "async-research idea catalog validate research_ops",
            "async-research idea catalog list research_ops --status promote",
            "async-research idea promote research_ops IDEA-0001 --dry-run",
            "Create a task folder only from a successful, unblocked promotion proposal",
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
