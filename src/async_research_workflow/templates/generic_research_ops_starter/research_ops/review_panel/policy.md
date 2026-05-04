# Review Panel Policy

This file records the active review policy for a generic `research_ops`
workspace. Detailed rules live in
`async_research_workflow/review_ensemble_policy.md` and
`async_research_workflow/algorithmic_review_aggregation_protocol.md`.

## Default Tiers

| tier | reviewers | use when |
| ---: | --- | --- |
| 0 | deterministic validators only | low-risk discovery structure checks |
| 1 | primary | data-readiness notes, hypothesis cards, low-risk memo sections |
| 2 | primary, methodology | experiment plans, methodology-sensitive outputs |
| 3 | primary, methodology, skeptic | public-facing, high-stakes, or disputed conclusions |

## Rules

- Required reviewer files must include `prompt_version` and
  `framework_versions.result_acceptance`.
- Methodology and skeptic reviewers must use isolated bundles from
  `prepare_review_context.py`.
- `aggregate_reviews.py` computes deterministic review routes.
- Strong, public, high-stakes, expensive, or sensitive-data claims require a
  human gate before acceptance.
