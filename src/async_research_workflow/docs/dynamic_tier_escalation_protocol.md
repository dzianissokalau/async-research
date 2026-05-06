# Dynamic Tier Escalation Protocol

Created: 2026-05-02

This document implements the P1 dynamic tier escalation requirement from the feedback hardening plan.

## Purpose

Let a reviewer route a task to a higher review tier without waiting for human intervention.

Escalation is for cases where the worker output is plausible enough to continue, but the current review tier is too weak for the risk in the output.

## Advanced/Internal Helper

Dynamic tier escalation remains an advanced/internal helper. Public escalation
checks use the `async-research escalation` command group.

Use:

```text
async_research_workflow/scripts/escalate_review_tier.py
```

Advanced/internal example:

```bash
python -m async_research_workflow.scripts.escalate_review_tier apply \
  research_ops/tasks/TASK-0001 \
  --to-tier 2 \
  --reason "worker output needs methodology review before acceptance" \
  --reviewer primary
```

The helper:

- loads `status.json`
- verifies that the target tier is higher than the current tier
- updates `review_policy.tier`
- replaces `review_policy.required_reviewers` with the required reviewer set for the target tier
- routes the task to `single_review` for Tier 1 or `panel_review` for Tier 2/3
- records escalation fields in `status.json`
- validates the task status schema and status transition before writing

## Status Fields

Escalated tasks record:

```json
{
  "escalate_to_tier": 2,
  "escalation_reason": "worker output needs methodology review before acceptance",
  "escalation_requested_by": "primary",
  "escalation_requested_at": "2026-05-02T10:00:00Z"
}
```

Unescalated tasks may set these fields to `null`.

## Tier Reviewer Sets

| Target tier | Required reviewers |
| ---: | --- |
| 1 | `primary` |
| 2 | `primary`, `methodology` |
| 3 | `primary`, `methodology`, `skeptic` |

The aggregator is not listed in `required_reviewers` because it is a deterministic wrapper plus optional narrative step after required review files exist.

## Allowed Status Routes

Escalation is allowed only from review states:

```text
awaiting_review -> single_review
awaiting_review -> panel_review
single_review -> panel_review
panel_review -> panel_review
```

The helper fails closed for accepted, rejected, paused, synthesized, worker, or planning states.

## Reviewer Escalation Requests

A reviewer file may include an escalation request in its structured JSON:

```json
{
  "reviewer_role": "primary",
  "decision": "accept_with_caveats",
  "claim_strength": "suggestive",
  "prompt_version": "primary_reviewer_v1.0",
  "framework_versions": {
    "result_acceptance": "result_acceptance_v1.0"
  },
  "main_concerns": ["methodology needs specialist review"],
  "required_followups": [],
  "evidence_gaps": [],
  "escalate_to_tier": 2,
  "escalation_reason": "methodology risk exceeds Tier 1 review",
  "confidence": 0.7
}
```

If `aggregate_reviews.py` sees a review requesting a tier higher than `status.json.review_policy.tier`, it refuses to aggregate and instructs the scheduler to run the escalation helper.

## Aggregate Logging

After escalation and completion of the required reviews, `aggregate_reviews.py` writes escalation metadata into:

```text
review_panel/aggregate.json
review_panel/aggregate.md
```

This preserves the audit trail showing why the task was reviewed at a higher tier before acceptance.

## Human Gates

Tier escalation is not the same as human approval.

Use `--human-required` when the escalation reason itself requires human approval, such as public release, investment advice, policy claims, legal sensitivity, private data, or expensive cloud/API spend.

## Acceptance Tests

The escalation layer is considered implemented when:

- a Tier 1 task can route to Tier 2 before acceptance
- escalation updates `review_policy.required_reviewers`
- the aggregate review logs escalation metadata
- attempts to downgrade or reapply the same tier fail closed
- unresolved review-file escalation requests block aggregation
