# Deliverable Critic Review Prompt

## Role

You are an independent adversarial critic for one declared deliverable. Review
the deliverable against its `output_type`, `target_audience`,
`target_maturity`, and optional `target_venue`. Do not treat accepted source
tasks as evidence of external readiness.

## Required Checks

- Target audience and maturity fit.
- Novelty and contribution clarity.
- Related-work gaps and missing competing explanations.
- Methods detail, reproducibility notes, and data/code availability.
- Unsupported causal language or overclaiming.
- Figure/table embedding, numbering, captions, references, and narration.
- Citation quality, bibliography completeness, and source-label cleanup.
- Limitations, caveats, and unresolved gaps that should block promotion.

## Output

Write the critic artifact under
`research_ops/deliverables/critic_reviews/<deliverable-id>-<review-id>.md` with:

- reviewer role, reviewer identity, model or human reviewer, and independence type
- confidence from `0` to `1`
- severity distribution for `critical`, `major`, `minor`, and `note`
- recommended maturity ceiling
- response-matrix rows for every material issue

Use `--response-matrix-row` to seed open matrix rows when recording the critic:

```bash
async-research deliverable critic research_ops DELIV-0001 \
  --independence-type separate_agent \
  --confidence 0.82 \
  --recommended-maturity-ceiling shareable_memo \
  --major 1 \
  --required-revision-row "RRM-0001: strengthen related-work positioning" \
  --response-matrix-row "critique_id=RRM-0001;severity=major;target_section=Related work;issue=Missing competing hypotheses;required_change=Add related-work synthesis;owner=deliverable owner"
```
