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
                "| V2 | Promotion write mode | In progress | V2.1 contract/preflight, V2.2 proposal write mode, and V2.3 recovery hardening shipped; task creation write mode remains deferred until transactional helpers exist. |",
                "| V2.1 | Contract and preflight design | Complete |",
                "| V2.2 | Proposal write mode | Complete |",
                "| V2.3 | Proposal write recovery tests | Complete |",
                "| V2.6 | Task creation write mode | Planned |",
            ],
        )

    def test_contract_documents_v22_proposal_write_only(self) -> None:
        self.assert_doc_contains(
            CONTRACT,
            [
                "V2.1 was a design and test-preflight slice. V2.2 enables proposal write mode only",
                "operators must run `async-research idea promote ... --dry-run`, copy the returned `promotion_preflight_hash`",
                "--write --preflight-hash <hash>",
                "It does not create task folders, append `queue.md`, set `promoted_task_id`, or mutate source or accepted-output ledgers.",
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

    def test_contract_defines_cli_evolution_for_write_slices(self) -> None:
        self.assert_doc_contains(
            CONTRACT,
            [
                "CLI evolution is staged.",
                "In V2.2, `idea promote --write` performs proposal writes only and does not create task folders or edit `queue.md`.",
                "In V2.6, `idea promote --write` composes proposal write and task creation write in one invocation under one catalog lock acquisition.",
                "If later implementation chooses separate flags instead, this contract and its tests must be updated before runtime code changes.",
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
                "same `catalog_idea_id`, idempotency key, and transaction id.",
                "The transaction id is generated at write time after the idempotency key is computed.",
                "Proposal write mode must persist it in the idea `decision_history` entry and the `inbox.md` proposal metadata.",
                "Task creation write mode must also persist it in task `status.json` and queue row metadata or notes.",
                "Recovery payloads and rollback messages must include both the transaction id and the idempotency key.",
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
                "Human override rules are slice-specific.",
                "For V2.2 proposal write mode, human override is required when any of these are true:",
                "`--allow-duplicate` is needed for a duplicate or near-duplicate idea.",
                "the dry-run proposal routes to `experiment_plan`.",
                "the proposal has `review_tier >= 2` or `max_minutes > 75`.",
                "catalog validation returns failures or blocking promotion reasons.",
                "V2.2 has no projected spend, task creation, or queue mutation, so it does not run `async-research cost budget-check` or fuzzy related task/queue matching inside proposal write mode.",
                "Before V2.6 task creation write mode ships, human override must also be required when any of these are true:",
                "projected spend fails `async-research cost budget-check`.",
                "an existing task, queue row, or proposal appears related but does not match the current idempotency key.",
            ],
        )


if __name__ == "__main__":
    unittest.main()
