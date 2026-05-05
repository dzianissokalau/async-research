# Claim-Strength Re-Evaluation Protocol

Created: 2026-05-02

This document implements P2-5 claim-strength re-evaluation for the async research workflow.

## Purpose

Claim strength is not permanent task metadata. It is a judgement made against a specific worker output at a specific review pass. If a task is revised, the old claim strength must not silently carry forward.

## Review Rule

Every review JSON block must include:

```json
{
  "claim_strength": "none | weak | suggestive | moderate | strong"
}
```

`aggregate_reviews.py` rejects review files that omit `claim_strength`.

## Revision Rule

Whenever a reviewer requests revision, the task result claim strength is marked stale:

```json
{
  "result": {
    "claim_strength": null,
    "claim_strength_stale": true,
    "claim_strength_revalidation_required": true,
    "claim_strength_revalidation_reason": "reviewer_requested_revision",
    "claim_strength_revalidated_at": null
  }
}
```

This is done by:

- `revision_counter.py request`
- `aggregate_reviews.py` when the deterministic route is `needs_revision`
- `aggregate_reviews.py` when a revision request exceeds the limit and routes to `needs_human`

## Aggregation Rule

`aggregate_reviews.py` computes a fresh `aggregate_claim_strength` from the current review pass and writes it to `review_panel/aggregate.json`.

Policy:

```text
weakest_current_review
```

The accepted task cannot claim stronger evidence than the weakest current reviewer judgement. The current aggregate claim strength is also copied into `status.json.result.claim_strength` for accepted, rejected, and human-gated review routes.

## Accepted Output Rule

The accepted-output updater used by `async-research accepted update` prefers
`review_panel/aggregate.json.aggregate_claim_strength` when available. Older
accepted outputs without the field still fall back to review files or status
metadata.

## Acceptance Checks

P2-5 is implemented when:

- review files without `claim_strength` fail deterministic aggregation
- a revision request clears any prior `status.result.claim_strength`
- a revision request sets `claim_strength_revalidation_required = true`
- a subsequent accepted review pass writes a fresh current claim strength
