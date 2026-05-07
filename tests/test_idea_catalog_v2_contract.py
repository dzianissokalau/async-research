"""Regression tests for V2.1 idea catalog promotion write contract docs."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROADMAP = ROOT / "roadmaps" / "idea_catalog_roadmap.md"
CONTRACT = ROOT / "src" / "async_research_workflow" / "docs" / "idea_catalog_contract.md"


def normalized(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


class IdeaCatalogV2ContractTests(unittest.TestCase):
    def assert_doc_contains(self, path: Path, snippets: list[str]) -> None:
        text = normalized(path)
        for snippet in snippets:
            self.assertIn(" ".join(snippet.split()), text, f"missing {snippet!r} from {path}")

    def test_roadmap_marks_v21_contract_complete_before_write_slices(self) -> None:
        self.assert_doc_contains(
            ROADMAP,
            [
                "| V2 | Promotion write mode | In progress | V2.1 contract/preflight shipped; proposal and task write implementations remain deferred until transactional tests exist. |",
                "| V2.1 | Contract and preflight design | Complete |",
                "| V2.2 | Proposal write mode | Planned |",
                "| V2.6 | Task creation write mode | Planned |",
            ],
        )

    def test_contract_keeps_v21_design_only(self) -> None:
        self.assert_doc_contains(
            CONTRACT,
            [
                "V2.1 is a design and test-preflight slice. It does not enable promotion write mode.",
                "Until V2.2 ships, `async-research idea promote ... --write` continues to refuse mutation",
                "`--dry-run` remains the only executable promotion behavior",
                "Promotion write mode is outside v1. In V2.1 it is still design-only",
            ],
        )

    def test_contract_defines_proposal_and_task_mutation_boundaries(self) -> None:
        self.assert_doc_contains(
            CONTRACT,
            [
                "Proposal write mode | `research_ops/inbox.md`, the selected `ideas/IDEA-*.json` proposal reference fields, generated idea projections, and `decision_history`",
                "Proposal write mode | `research_ops/inbox.md`",
                "`queue.md`, `tasks/`, accepted-output ledgers, source audit rows, and unrelated idea records.",
                "Task creation write mode | One new `tasks/TASK-*/` folder, one `queue.md` row, the selected idea's `promoted_task_id`",
                "More than one task, unrelated queue rows, unrelated ideas, source audit state, accepted-output ledgers",
            ],
        )

    def test_contract_defines_lock_order_idempotency_and_changed_candidate_rule(self) -> None:
        self.assert_doc_contains(
            CONTRACT,
            [
                "Acquire `research_ops/ideas/LOCK` before re-reading the selected idea for any write-mode promotion slice.",
                "Re-read the idea, recompute the promotion preflight hash, and rerun catalog validation while the catalog lock is held.",
                "Append `queue.md` only after staged task files validate.",
                "Update the idea's `promoted_task_id` only after the task folder and queue row are both finalized.",
                "catalog_idea_id + task_type + promotion_preflight_hash",
                "If any of those fields change between dry-run and write, the write must refuse with `reason=promotion_preflight_changed`",
            ],
        )

    def test_contract_defines_rollback_and_required_preflight_cases(self) -> None:
        self.assert_doc_contains(
            CONTRACT,
            [
                "Proposal write mode must not leave an inbox proposal without a matching idea proposal reference",
                "Task creation write mode must remove staged task files if queue append fails.",
                "If final validation fails after queue append, the helper must roll back the task folder and queue row together",
                "If rollback itself fails, the helper must stop, return `needs_human`",
                "duplicate retry",
                "stale `research_ops/ideas/LOCK`",
                "changed candidate between dry-run and write",
                "partial inbox proposal without idea reference",
                "partial task folder without queue row",
                "queue row without task folder",
                "stale `promoted_task_id`",
                "rollback failure reporting",
            ],
        )

    def test_contract_defines_human_override_rules(self) -> None:
        self.assert_doc_contains(
            CONTRACT,
            [
                "Human override is required before a write when any of these are true:",
                "`--allow-duplicate` is needed for a duplicate or near-duplicate idea.",
                "the dry-run proposal routes to `experiment_plan`.",
                "the proposal has `review_tier >= 2`, `max_minutes > 75`, or projected spend that fails `async-research cost budget-check`.",
                "catalog validation returns failures or blocking promotion reasons.",
                "an existing task, queue row, or proposal appears related but does not match the current idempotency key.",
            ],
        )


if __name__ == "__main__":
    unittest.main()
