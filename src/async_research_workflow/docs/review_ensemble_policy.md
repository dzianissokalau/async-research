# Review Ensemble Policy

## Purpose

Add more reviewers where they improve quality, without turning every task into an expensive multi-agent review.

The review system should support high quality and independence while staying cost-aware.

## Core Rule

Use independent first-pass reviews before aggregation.

```text
worker output -> independent reviewers -> aggregate decision -> revision/human/accept
```

Do not let reviewers read each other's notes until their own review is complete. This preserves diversity and avoids premature convergence.

Independence is enforced structurally by role-specific review bundles. See [Structural Reviewer Isolation Protocol](./reviewer_isolation_protocol.md).

## Why Not One Reviewer Everywhere?

One reviewer is good for ordinary task hygiene:

- did the worker answer the task?
- did it stay in scope?
- are required sections present?
- are caveats visible?

One reviewer is not enough for high-stakes research claims:

- methodology can be subtly wrong
- causal language can be too strong
- code can be reproducible but analytically weak
- source support can be thin
- a single model can have stable blind spots

## Why Not Many Reviewers Everywhere?

Multiple reviewers cost more and can slow the queue. They also do not guarantee truth. LLM judges have known biases, and multi-agent debate can become persuasive without being grounded.

Use review panels only at gates.

## Review Tiers

| Tier | Trigger | Reviewers | Default outcome rule |
| --- | --- | --- | --- |
| Tier 0 | formatting, schema, simple extraction | local/cheap checklist | pass/fail |
| Tier 1 | ordinary worker outputs | primary reviewer | primary can accept |
| Tier 2 | experiment plans, result summaries, expensive follow-ups | primary + methodology | both accept or route |
| Tier 3 | final memos, public/policy/investment-sensitive claims, moderate/strong claims | primary + methodology + skeptic + aggregator | no rejects; disagreements route |

## Reviewer Roles

### Primary Reviewer

Best model/tool:

- Codex or OpenAI frontier/standard model

Focus:

- task compliance
- file/path discipline
- reproducibility
- source links
- whether required output exists

### Methodology Reviewer

Best model/tool:

- Claude Sonnet/Opus, GPT-5.4/5.5, or comparable strong reasoning model

Focus:

- research design
- identification assumptions
- statistical validity
- baselines
- robustness checks
- causal overclaiming

### Skeptic Reviewer

Best model/tool:

- Gemini Pro/Flash, Claude, GPT, or another model family

Focus:

- alternative explanations
- factual/source challenge
- omitted data risks
- hidden leakage
- "why this might be wrong"

### Aggregator

Best model/tool:

- cheap or standard model for Tier 1/2
- frontier or human for Tier 3

Focus:

- compare independent reviews
- list agreements and disagreements
- set final route
- avoid inventing new substantive claims

## Review Output Contract

Every reviewer writes a structured review:

```json
{
  "reviewer_role": "methodology",
  "decision": "accept | accept_with_caveats | needs_revision | needs_human | reject",
  "claim_strength": "none | weak | suggestive | moderate | strong",
  "prompt_version": "methodology_reviewer_v1.0",
  "framework_versions": {
    "result_acceptance": "result_acceptance_v1.0"
  },
  "main_concerns": [],
  "required_followups": [],
  "evidence_gaps": [],
  "scope_or_policy_issues": [],
  "escalate_to_tier": null,
  "escalation_reason": null,
  "confidence": 0.0
}
```

## Dynamic Escalation

If the output is not safe to accept at the current tier but does not need immediate human judgment, reviewers should escalate the task instead of accepting it.

Run:

```bash
python -m async_research_workflow.scripts.escalate_review_tier apply \
  research_ops/tasks/TASK-0001 \
  --to-tier 2 \
  --reason "output requires methodology review" \
  --reviewer primary
```

The helper records the escalation fields, updates required reviewers, and moves the task into the correct review state. `aggregate_reviews.py` logs the escalation in the aggregate review and refuses to aggregate a review file that asks for a higher tier before the status has been escalated.

## Aggregation Rules

Use `aggregate_reviews.py` to compute the route before any LLM writes a narrative summary. The LLM may explain the result, but it must not override the deterministic route.

Tier 1:

- accept if primary says `accept` or `accept_with_caveats`
- otherwise route as primary recommends

Tier 2:

- accept only if both reviewers are `accept` or `accept_with_caveats`
- if one reviewer says `needs_revision`, route to revision
- if either says `needs_human` or `reject`, route there

Tier 3:

- accept only if all reviewers are at least `accept_with_caveats`
- any `reject` blocks acceptance
- any `needs_human` routes to human
- any material disagreement routes to revision or human
- no `strong` claim can be accepted without human approval

## Disagreement Policy

Use this order:

1. If disagreement is about missing evidence, create a follow-up task.
2. If disagreement is about interpretation, route to methodology revision.
3. If disagreement is about high-stakes risk, route to human.
4. If disagreement persists after one revision, pause or human-gate the task.

Do not run repeated open-ended debate.

## Model Diversity Policy

Using Claude and Gemini can help because they often fail differently from OpenAI models. Use them for independence, not for majority theater.

Recommended routing:

| Artifact | Reviewer setup |
| --- | --- |
| simple extraction | primary only |
| hypothesis card | primary + optional skeptic for high-priority ideas |
| data readiness | primary + skeptic if data will feed experiment |
| experiment plan | primary + methodology |
| result summary | primary + methodology + skeptic if claim strength is moderate or higher |
| memo | Tier 3 panel |
| public claim | Tier 3 panel + human |

## Cost Controls

- Review only accepted or high-value worker outputs with panels.
- Batch low-priority reviews weekly.
- Use local or cheap models for schema and citation-presence checks.
- Use model diversity only at gates.
- Use `async-research revision request` for every `needs_revision` decision.
- Stop after the task reaches `max_revisions` unless a human approves more.
- Restate `claim_strength` on every review pass.
- Treat prior `status.result.claim_strength` as stale after any revision request.

## Independence Controls

- Same evidence bundle for each reviewer.
- Reviewer outputs are hidden from each other until aggregation by using isolated bundles.
- Each reviewer gets a role-specific rubric.
- Aggregator must cite reviewer findings rather than re-reviewing from scratch.
- Human sees disagreements, not only final consensus.

Reviewer roles should run as separate process/session/API calls. The methodology and skeptic reviewers should not receive `reviews/primary.md` or sibling review files in their working context. The aggregator is the only role that receives all review files.

## Human Role

The human is not a daily bottleneck. The human is an exception handler and claim approver.

Human approval is required for:

- public release
- strong claims
- policy, legal, investment, or valuation recommendations
- expensive experiments
- persistent reviewer disagreement
- use of new private, scraped, or legally sensitive data

Every human approval or resolution must be appended to
`research_ops/decisions.md` using `async-research decision append`. Reviewer or
aggregator acceptance is not a substitute for a human decision row when a task
is public, high-stakes, expensive, or blocked in `needs_human`.

## Recommended Initial Setup

Start with:

```text
Tier 1 primary reviewer for all tasks
Tier 2 panel for experiment plans and result summaries
Tier 3 panel for final memos only
```

Add Claude/Gemini only for Tier 2 and Tier 3 until the accepted-output rate justifies broader review.
