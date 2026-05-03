# Human Decision Log Protocol

Created: 2026-05-02

This document implements P2-3 human decision logging for the async research workflow.

## Purpose

The human loop should be light, but when it happens it must leave durable evidence. Human decisions are the audit trail for:

- resolving `needs_human` tasks
- approving public, high-stakes, expensive, private-data, or policy-sensitive work
- overriding an automated route
- monthly calibration of recurring human gate reasons

## Required File

Use:

```text
research_ops/decisions.md
```

Columns:

```text
date | item_id | decision | reason | approver | related_artifacts
```

The file is append-only. Do not edit previous rows to reinterpret history. If a decision changes, append a new row with the new decision and reason.

## Required Helper

Use:

```text
async_research_workflow/examples/scripts/human_decision_log.py
```

Append a decision:

```bash
python3 async_research_workflow/examples/scripts/human_decision_log.py append \
  research_ops \
  --item-id TASK-0001 \
  --decision approve_public \
  --reason "Approved for public memo after Tier 3 review" \
  --approver "human-owner" \
  --related-artifact research_ops/tasks/TASK-0001/worker_output.md
```

Resolve a task blocked in `needs_human`:

```bash
python3 async_research_workflow/examples/scripts/human_decision_log.py resolve-task \
  research_ops \
  research_ops/tasks/TASK-0001 \
  --decision resume \
  --reason "Scope clarified; continue with smaller data-readiness task" \
  --approver "human-owner" \
  --status ready_for_worker
```

The resolver appends a decision row, updates `status.json`, and validates the transition. It is the preferred way to move a task out of `needs_human`.

## Decision Values

Supported decisions:

```text
acknowledge
approve
approve_budget
approve_data_use
approve_high_stakes
approve_public
override
pause
reject
resume
```

Use `resume`, `pause`, or `reject` when resolving `needs_human` tasks. Use the approval-specific decisions for public, high-stakes, budget, or data-use gates.

## Transition Enforcement

`validate_transition.py` now checks `research_ops/decisions.md` when a task moves from `needs_human` to:

```text
ready_for_worker
paused
rejected
```

If no matching decision row exists for the task ID, transition validation fails with `missing_human_decision`.

## Monthly Calibration

Summarize human gate reasons:

```bash
python3 async_research_workflow/examples/scripts/human_decision_log.py summarize \
  research_ops \
  --month 2026-05 \
  --output research_ops/monthly_human_decision_summary.md
```

The summary groups decision rows by decision, reason, and approver. Repeated reasons show where automation needs better prompts, stricter gates, or clearer task definitions.

## Acceptance Checks

P2-3 is implemented when:

- resolving `needs_human` fails transition validation without a matching decision row
- resolving `needs_human` through the helper appends a decision row and validates
- public or high-stakes approval can be recorded as a structured decision row
- monthly calibration can summarize human gate reasons
