# Idea Catalog Roadmap

Created: 2026-05-05

## Summary

Build a durable idea catalog that turns rough ideas into a managed research
portfolio. The catalog should capture, dedupe, score, park, reject, and promote
ideas based on mission fit, novelty, impact, feasibility, data readiness, cost,
robustness risk, reuse potential, and killability.

This feature builds on the existing discovery workflow and mission-weighted
idea scoring. Its job is to make prioritization visible, repeatable, and easy
to inspect.

## What It Does

The idea catalog maintains an idea pipeline:

- rough idea capture
- structured idea candidates
- dedupe and clustering
- evidence seeds from the library, data foundations, and accepted outputs
- mission-weighted scoring
- skeptic notes and kill criteria
- known blockers
- recommended next smallest task
- promotion, parking, and rejection history

The catalog should prioritize useful, killable ideas over interesting but vague
ones. A high-scoring idea should usually become a `library_review`,
`data_readiness`, `hypothesis_card`, or `experiment_plan` task only after
required gates pass.

## Framework Integration

Existing artifacts:

```text
research_ops/discovery_inbox.md
research_ops/discovery/clusters.md
research_ops/discovery/rejected_ideas.md
```

New workspace artifacts:

```text
research_ops/
  ideas/
    idea_catalog.md
    prioritization.md
    IDEA-0001.json
```

Integration points:

- `discovery_inbox.md` remains the short buffer for newly discovered ideas.
- `ideas/idea_catalog.md` becomes the durable portfolio.
- `ideas/IDEA-*.json` holds structured candidate contracts.
- Existing `async-research idea score` remains the scoring engine.
- Planner promotes only candidates with a valid next task and kill reason.
- Library refs, data refs, accepted output refs, and rejected refs improve
  scoring and duplicate detection.
- Accepted outputs and rejected results update duplicate checks and anti-context.
- Dashboard shows top ideas, parked ideas, rejected ideas, blockers, and next
  recommended tasks.

## Implementation Steps

### Slice 1: Starter Files

Add idea catalog files to the generic and real-estate templates.

Acceptance:

- `async-research init research_ops` creates `research_ops/ideas/`
- empty catalog files do not break existing commands
- starter README explains the difference between `discovery_inbox.md` and
  `ideas/idea_catalog.md`

### Slice 2: Catalog Contract

Define lightweight contracts for:

- `ideas/idea_catalog.md`
- `ideas/prioritization.md`
- `ideas/IDEA-*.json`

Suggested catalog fields:

- idea ID
- title
- status
- weighted score
- impact
- novelty
- feasibility
- data readiness
- robustness risk
- cost
- killability
- blockers
- recommended next task
- promoted task ID
- updated date

Acceptance:

- rough ideas can be represented without full scoring
- scored ideas record mission policy version and budget mode
- parked and rejected ideas require a reason

### Slice 3: Candidate Contract Extension

Extend the idea candidate contract with optional refs:

```json
{
  "library_refs": ["LIT-0001"],
  "data_refs": ["DS-0001"],
  "accepted_output_refs": ["TASK-0007"],
  "rejected_refs": ["TASK-0003"]
}
```

Acceptance:

- refs are optional during cold start
- invalid refs warn during discovery
- invalid data refs block direct experiment planning
- duplicate ideas can point to the earlier accepted, parked, or rejected item

### Slice 4: Validator

Add:

```bash
async-research idea catalog validate research_ops
```

Checks:

- duplicate idea IDs
- malformed candidate JSON
- missing required catalog fields
- scored idea missing mission policy version
- promotable idea missing next task or kill reason
- references to missing library, data, accepted, or rejected records
- direct experiment route without data/source gates

Acceptance:

- empty catalog passes or returns warning-only status
- invalid scored candidates fail validation
- direct promotion to expensive experiments remains blocked unless gates pass

### Slice 5: Promotion Helper

Add a planning helper:

```bash
async-research idea promote research_ops IDEA-0001 --dry-run
```

The helper should propose one bounded task folder or queue entry. It should not
bypass planner or human approval.

Acceptance:

- dry run prints proposed task type, title, objective, scope, source refs,
  allowed paths, and kill criteria
- promotion creates or proposes exactly one next task
- expensive experiment routes require audited data refs

### Slice 6: Catalog Maintenance Job

Add a weekly maintenance flow:

```text
dedupe -> cluster -> score -> skeptic filter -> park/reject/promote proposal
```

Acceptance:

- discovery writes new ideas to the inbox first
- maintenance moves durable candidates into `ideas/`
- weekly digest summarizes idea throughput, top blockers, and recommended
  promotions

### Slice 7: Planner Integration

Teach planner prompts and docs to use the catalog.

Planner rules:

- promote few ideas
- prefer cheap killable next tasks
- create `library_review` if evidence is thin
- create `data_readiness` if data path is plausible but unaudited
- avoid direct experiment planning unless gates pass
- record human priority decisions

Acceptance:

- top ideas become bounded queue items
- missing foundations become setup tasks
- planner does not promote duplicate or blocked ideas without a reason

### Slice 8: Dashboard Surface

Add portfolio views.

Show:

- candidate ideas
- parked ideas
- promoted ideas
- rejected ideas
- top blockers
- score dimensions
- next recommended tasks
- idea-to-task links

Acceptance:

- operator can decide what to promote in under a few minutes
- blockers are visible without opening raw files
- dashboard mutation actions remain explicit and logged

## Open Questions

- Should `idea_catalog.md` eventually replace `discovery_inbox.md`, or should
  the inbox remain a short-lived buffer?
- Should idea status values be aligned with task status values, or use a
  separate idea-specific lifecycle?
- Should human priority override scoring, or only adjust a separate priority
  field?
- Should novelty be scored by an agent, a human, or a library-aware reviewer?
