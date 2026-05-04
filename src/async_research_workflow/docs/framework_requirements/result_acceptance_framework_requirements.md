# Result Acceptance Framework Requirements And Framework v1.0

## Purpose

The result acceptance framework decides whether completed work becomes accepted evidence, needs revision, pauses, or gets rejected.

It protects the research record from weak claims.

This document now defines both the requirements and the executable
`result_acceptance_v1.0` framework used after deterministic review aggregation
and before accepted outputs enter durable evidence memory.

## Core Principle

Acceptance is not the same as success.

A failed or negative result can be accepted if it is reproducible, well-tested, and honestly documented.

## Executable Framework Contract

Result acceptance has three executable artifacts:

```text
async_research_workflow/schemas/result_acceptance.schema.json
async_research_workflow/templates/artifact_templates/result_summary_template.md
async_research_workflow/scripts/validate_result_acceptance.py
```

For `run_analysis` and `evaluate_results` tasks, workers shall include a fenced
JSON result summary in `worker_output.md` using
`result_summary_template.md`. Routine artifacts can still be accepted from
`status.json`, `worker_output.md`, and review aggregation, but their claim
strength is capped conservatively.

After reviews are aggregated, validate acceptance:

```bash
async-research result-acceptance \
  research_ops/tasks/TASK-0004-evaluate-results \
  --ops-dir research_ops \
  --write \
  --update-ledgers
```

`aggregate_reviews.py` runs this validation automatically before writing an
`accepted` or `rejected` status. If validation fails, aggregation fails closed
and the task must be revised, routed to human review, or rejected.

The validator writes:

```text
research_ops/tasks/<task>/review_panel/result_acceptance.json
research_ops/evidence_ledger.md
research_ops/rejected_results.md
```

## Result Acceptance Lifecycle

```text
worker output
-> independent review(s)
-> aggregate_reviews.py
-> result_acceptance_v1.0 validation
-> result_acceptance.json
-> evidence_ledger.md or rejected_results.md
-> accepted_outputs_index.md
```

Accepted outputs should cite `result_acceptance.json` and the evidence ledger,
not only raw worker prose.

## Required Result Acceptance Record

The validator builds a `result_acceptance.json` record with:

- task ID, task type, route, and evaluation timestamp
- recommended decision and accepted claim strength
- maximum claim strength allowed by evidence caps
- hard gate results
- result scorecard across the ten RAF dimensions
- reviewer panel summary
- human gate status
- evidence ledger status
- rejection logging status
- follow-up discipline fields
- review notes

## Executable Hard Gates

`validate_result_acceptance.py` enforces:

- accepted evidence has non-empty `worker_output.md`
- accepted evidence has a deterministic review aggregate
- accepted aggregate decision is `accepted`
- claim strength is current, not stale from an earlier revision
- claim strength does not exceed the evidence cap
- accepted evidence has a key finding and evidence link
- `run_analysis` and `evaluate_results` tasks have a structured result summary
- result summaries include baseline, validation, robustness, leakage,
  limitation, artifact, dataset, and follow-up fields
- result tasks do not hide failed robustness checks
- public/high-stakes outputs and strong claims require human approval
- rejected results are logged to `rejected_results.md`

## Claim Strength Caps

The executable caps are:

- no structured result summary: at most `suggestive`
- no reproducible run manifest or artifact version: `none`
- no baseline comparison: `weak`
- no leakage checks: `weak`
- no robustness checks: `suggestive`
- predictive validation only: at most `moderate`
- causal claim without identification tests: at most `weak`
- reviewer decision disagreement: at most `suggestive`
- public/high-stakes use without human approval: cannot be accepted
- strong claim without human approval: cannot be accepted

Hard gates override reviewer agreement. Reviewers can be unanimously positive
and still fail acceptance if the result record cannot support the claim.

## Functional Requirements

### RAF-FR1: Required Result Summary Fields

Every result summary shall include:

- experiment plan ID
- run ID
- code commit or artifact version
- dataset versions
- primary metric
- baseline results
- candidate results
- validation split results
- robustness results
- leakage check results
- limitations
- claim strength
- recommended decision
- follow-up tasks

### RAF-FR2: Result Routes

Every result shall route to:

```text
accept_as_evidence
accept_negative_result
needs_revision
needs_followup_test
needs_human
pause
reject
```

### RAF-FR3: Claim Strength Rules

Use these labels:

```text
none
weak
suggestive
moderate
strong
```

Maximum claim strength rules:

- no reproducible run manifest: `none`
- no baseline comparison: `weak`
- no leakage check: `weak`
- no robustness check: `suggestive`
- predictive validation only: at most `moderate`
- causal claim without identification tests: at most `weak`
- reviewer disagreement: at most `suggestive` unless resolved
- no human approval for public/high-stakes use: not public-ready

### RAF-FR4: Hard Gates

A result shall not be accepted as evidence if:

- required outputs are missing
- run cannot be traced to code/config/data
- baseline comparison is absent
- leakage checks are absent
- metrics are inconsistent with the approved experiment plan
- result summary hides failed robustness checks
- claim language exceeds evidence

### RAF-FR5: Review Tier Selection

Result review shall use:

- Tier 1 for routine extraction or draft artifacts
- Tier 2 for experiment results and reusable data-readiness outcomes
- Tier 3 for final memos, moderate/strong claims, public claims, or high-stakes decisions

### RAF-FR6: Evidence Ledger Update

Accepted results shall update an evidence ledger with:

- result ID
- claim supported or weakened
- claim strength
- key metrics
- limitations
- reviewer decision
- follow-up tasks

Rejected results shall update a rejection log.

### RAF-FR7: Follow-Up Discipline

Reviewers may propose follow-ups, but only the planner may create execution tasks.

Follow-ups shall include:

- reason
- required artifact
- priority
- whether human approval is needed
- whether the follow-up is required before memo use

## Scoring Dimensions

Score results from 1 to 5 on:

- plan compliance
- reproducibility
- baseline comparison
- metric validity
- validation strength
- robustness strength
- leakage safety
- limitation honesty
- decision usefulness
- claim discipline

## Non-Functional Requirements

### RAF-NFR1: Honesty

Negative, null, or failed results should be accepted when they are useful and reproducible.

### RAF-NFR2: Auditability

Every accepted claim must link to artifacts.

### RAF-NFR3: Conservative Claims

The system should underclaim rather than overclaim.

## Acceptance Criteria

The result acceptance framework is ready when:

- result summaries use a standard template
- claim strength has explicit caps
- hard gates override scores
- accepted evidence updates a ledger
- rejected results are logged
- review panels are triggered at the right gates
- human approval is required for public/high-stakes claims
- `validate_result_acceptance.py` accepts valid reviewed outputs
- `aggregate_reviews.py` fails closed when accepted/rejected outcomes violate
  result acceptance
- the durable acceptance suite covers ledger updates, claim caps, and rejection
  logging

## Failure Modes

Watch for:

- treating metric improvement as truth
- accepting results without robustness checks
- hiding failed tests
- converting predictive results into causal claims
- repeated revision loops instead of pause/reject decisions
- reviewer consensus without artifact evidence

## Recommended First Artifacts

Create:

```text
research_ops/evidence_ledger.md
research_ops/rejected_results.md
research_ops/result_acceptance_policy.md
```

Each accepted memo should cite evidence ledger entries, not raw agent prose.
