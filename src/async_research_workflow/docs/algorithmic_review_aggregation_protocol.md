# Algorithmic Review Aggregation Protocol

Created: 2026-05-02

This document implements the P1 algorithmic review aggregation requirement from the feedback hardening plan.

## Purpose

Prevent free-form LLM aggregators from drifting away from the review policy.

Reviewers may write narrative comments, but Tier 2 and Tier 3 routing must be computed by deterministic rules from structured review fields.

## Required Helper

Use:

```text
async_research_workflow/scripts/aggregate_reviews.py
```

Run it after all required reviewer files are present:

```bash
async-research review aggregate \
  research_ops/tasks/TASK-0001
```

The helper:

- parses structured JSON review fields from `reviews/*.md`
- checks required reviewers from `status.json.review_policy`
- validates review decisions against the allowed enum
- blocks aggregation if a review file requests a higher tier that has not been applied to `status.json`
- applies the tier routing rules
- writes `review_panel/aggregate.json`
- writes `review_panel/aggregate.md`
- updates `status.json`
- writes `schema_version = "1.0"` to new aggregate JSON and adds it to older status files on update
- preserves and defaults task-level prompt/framework version metadata
- writes `aggregate_claim_strength` from the current review pass
- clears stale `status.result.claim_strength` when routing to revision
- validates the aggregate JSON, task status schema, and status transition before writing

## Structured Review Input

Each reviewer file must contain a JSON object, either as the whole file or inside a fenced `json` block:

```json
{
  "reviewer_role": "methodology",
  "decision": "accept_with_caveats",
  "claim_strength": "suggestive",
  "prompt_version": "methodology_reviewer_v1.0",
  "framework_versions": {
    "result_acceptance": "result_acceptance_v1.0"
  },
  "main_concerns": ["baseline coverage should be expanded"],
  "required_followups": [],
  "evidence_gaps": [],
  "escalate_to_tier": null,
  "escalation_reason": null,
  "confidence": 0.72
}
```

Allowed `decision` values:

```text
accept
accept_with_caveats
needs_revision
needs_human
reject
```

Any other decision value fails validation and blocks aggregation.

`claim_strength` is required on every review pass. Aggregation fails if it is
missing; revised tasks must not inherit an old claim-strength judgement.

`prompt_version` and `framework_versions.result_acceptance` are required on
every review pass. Aggregation fails if reviewer version metadata is missing.

## Required Reviewers

If `status.json.review_policy.required_reviewers` is present, it is authoritative.
Otherwise use:

| Tier | Required reviewers |
| ---: | --- |
| 0 | none |
| 1 | primary |
| 2 | primary, methodology |
| 3 | primary, methodology, skeptic |

Missing required reviews block aggregation. Optional extra reviewer files are allowed, but their decisions still affect the route.

## Escalation Handling

Reviewers may include `escalate_to_tier` and `escalation_reason` in their structured review. If the requested tier is higher than the current task tier, aggregation fails closed with `review_requested_higher_tier`.

The scheduler should then run:

```bash
python -m async_research_workflow.scripts.escalate_review_tier apply \
  research_ops/tasks/TASK-0001 \
  --to-tier 2 \
  --reason "reviewer requested methodology review" \
  --reviewer primary
```

After the required higher-tier reviews exist, `aggregate_reviews.py` logs the escalation in `review_panel/aggregate.json` and `review_panel/aggregate.md`.

## Routing Rules

Tier 1:

- accept if primary says `accept` or `accept_with_caveats`
- otherwise route as primary recommends

Tier 2:

- accept only if all required reviewers say `accept` or `accept_with_caveats`
- any `needs_revision` routes to revision
- any `needs_human` routes to human
- any `reject` routes to rejected

Tier 3:

- accept only if all required reviewers say `accept` or `accept_with_caveats`
- any `reject` blocks acceptance and routes to rejected
- any `needs_human` routes to human
- any `needs_revision` routes to revision, bounded by revision counters
- any strong claim or human-required policy routes to human before final acceptance

Revision routing uses the revision counter fields. If the task already reached `max_revisions`, the aggregate route becomes `needs_human`.

## Human Gate Rules

The helper routes to `needs_human` before final acceptance when:

- `review_policy.human_required_for_acceptance = true`
- `status.requires_human = true`
- any reviewer marks `claim_strength = strong`
- the revision limit is reached

## Narrative Summaries

An LLM may write a narrative summary only after `aggregate_reviews.py` has written `review_panel/aggregate.json`. The narrative must not override the deterministic `aggregate_decision`.

## Acceptance Tests

The aggregation layer is considered implemented when:

- mixed `accept` and `reject` cannot aggregate to accepted
- missing required reviews block aggregation
- non-standard decision enum fails validation
- unresolved escalation requests block aggregation
- aggregate output records applied escalation metadata
- all required accept-like reviews aggregate to accepted
- human-required or strong-claim tasks route to `needs_human`
- revision requests respect `revision_count` and `max_revisions`
