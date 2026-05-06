# Revision Counter Protocol

Created: 2026-05-02

This document implements the P1 revision counter requirement from the feedback hardening plan.

## Purpose

Prevent autonomous reviewer loops where a task is repeatedly sent back for revision without a human decision.

Every task tracks how many reviewer-requested revisions have been used and the maximum number allowed before the task routes to `needs_human`.

## Required Fields

Each `status.json` must include:

```json
{
  "revision_count": 0,
  "max_revisions": 1,
  "revision_limit_hit": false
}
```

Meanings:

- `revision_count`: number of reviewer-approved revision loops already consumed
- `max_revisions`: maximum autonomous revision loops allowed
- `revision_limit_hit`: true when the task has reached or exceeded its revision budget

## Defaults

Use these defaults when a planner creates a task:

| Review tier | Default `max_revisions` |
| ---: | ---: |
| 0 | 1 |
| 1 | 1 |
| 2 | 2 |
| 3 | 1 |

Tier 3 returns to human review after one revision because disagreement between multiple independent reviewers is usually a judgement problem, not a reason for endless worker retries.

## Required Helper

Use:

```text
async-research revision
```

Request a revision:

```bash
async-research revision request \
  research_ops/tasks/TASK-0001 \
  --reviewer primary
```

If `revision_count < max_revisions`, the helper:

- increments `revision_count`
- sets `status = needs_revision`
- sets `last_transition_reason = reviewer_requested_revision`
- sets `revision_limit_hit = true` if the increment reaches the limit
- clears `result.claim_strength`
- sets `result.claim_strength_revalidation_required = true`
- validates schema and transition before writing

If `revision_count >= max_revisions`, the helper:

- sets `status = needs_human`
- sets `last_transition_reason = revision_limit_exceeded`
- sets `requires_human = true`
- sets `revision_limit_hit = true`
- writes a human gate reason
- clears `result.claim_strength`
- sets `result.claim_strength_revalidation_required = true`
- validates schema and transition before writing

Inspect one task:

```bash
async-research revision inspect \
  research_ops/tasks/TASK-0001
```

Report tasks that hit revision limits:

```bash
async-research revision scan-limits \
  research_ops/tasks \
  --markdown
```

## Reviewer Rule

Reviewers must not set `status = needs_revision` by hand.

If a reviewer wants another worker pass, it must use `async-research revision request`. If the helper routes to `needs_human`, the reviewer must not override it.

## Weekly Synthesis Rule

The weekly synthesizer must run `scan-limits` and include a short section for tasks that hit revision limits. If there are no hits, it should say so.

## Acceptance Tests

The revision counter layer is considered implemented when:

- `revision_count` and `max_revisions` are required by the task status schema
- first revision request under the limit routes to `needs_revision`
- revision request at or over the limit routes to `needs_human`
- `max_revisions` cannot be unbounded by schema
- reviewer prompts use `async-research revision request` for revision requests
- weekly synthesizer prompt reports tasks that hit revision limits
