# TASK-0001: Audit Real-Estate Data Source Readiness

## Objective

Verify whether the starter real-estate data sources in
`research_ops/data_source_audit.md` and `research_ops/data/` are usable for the
first automated research loop.

## Scope

- Work only inside this task folder, `research_ops/data_source_audit.md`, and
  `research_ops/data/`.
- Use official source pages or existing local documentation.
- Do not run an experiment or make market claims.
- Do not create new tasks directly; propose follow-ups in `worker_output.md`.

## Required Output

Write `worker_output.md` with:

- source-by-source readiness verdict
- profile draft or update for each `DS-*` source, or an explicit no-change rationale
- recommended audit status for each `DS-*` row: `approved`, `approved_with_caveats`, `blocked`, `restricted`, `deprecated`, or `candidate`
- exact `async-research source upsert` fields needed for any audit update, with this task referenced in `approved_by` or `review_notes`
- access check result covering access route, permission requirement, reproducibility notes, and expected update cadence
- field/grain coverage needed for sale price, geography, date, mortgage shock timing, and contextual joins
- join feasibility, join keys, join caveats, and leakage risks
- known limitations, licensing/privacy constraints, missingness risks, and freshness risks
- recommended next task: `experiment_plan`, `hypothesis_card`, another `data_readiness`, `park`, or `reject`
- kill reason if a source is unusable or too risky for downstream planning
- validation results from `async-research source validate research_ops` and `async-research data validate research_ops`

## Acceptance Criteria

- `data_source_audit.md` is updated with accurate statuses.
- Each source is marked `approved`, `approved_with_caveats`, `blocked`,
  `restricted`, `deprecated`, or left as `candidate` with a reason.
- Matching data profiles are drafted or updated when source details change.
- No source is treated as experiment-ready without an access route and caveats.
- Audit/profile changes are traceable to this task's `worker_output.md` and review.
- The output distinguishes verified facts from assumptions.

## Review Policy

Tier 1 primary review. Escalate to Tier 2 if the worker proposes using a source
with major licensing, matching, or methodology uncertainty.

## Context

- `research_ops/data_source_audit.md`
- `research_ops/data/`
- `async_research_workflow/data_source_audit_register_protocol.md`
- `async-research source upsert`

## Data Source Audit

This is a `data_readiness` task. It may update `DS-0001`, `DS-0002`, and
`DS-0003` audit rows and matching data profiles, but it should not create an
experiment plan.

## Cross-Task Anti-Context

No accepted outputs exist yet. Do not assume any data source is ready just
because it appears in the starter register.
