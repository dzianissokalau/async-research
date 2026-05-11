# Feedback Hardening Plan

Created: 2026-05-02

This plan turns Claude and Gemini review feedback into an implementation roadmap for hardening the async research workflow before real autonomous scheduling.

## Executive View

The reviews agree on the same core point:

```text
the strategy is sound, but autonomy needs enforceable state, validation,
review isolation, observability, and cost controls.
```

The next phase should not add more intelligence. It should make the workflow harder to corrupt.

## Priority Policy

Keep the operating priority:

```text
quality > independence > low cost > speed
```

Therefore:

- correctness and auditability come before convenience
- slow daily or weekly loops are acceptable
- autonomous jobs must fail closed
- hard gates must be enforceable by scripts where practical
- agents may propose actions, but state transitions must be validated

## Summary Of Feedback Themes

| Theme | Main concern | Source |
| --- | --- | --- |
| State integrity | race conditions, illegal transitions, malformed JSON | Claude, Gemini |
| Review reliability | reviewer independence is prompt-only, false consensus risk | Claude, Gemini |
| Cost and loop control | revision loops, manual cost ledger, discovery overload | Claude, Gemini |
| Observability | health conditions exist but are not monitored | Claude |
| Context and memory | stale digests, cross-task contradictions, rejected-result reuse | Claude, Gemini |
| Versioning | schema, prompt, rubric versions missing | Claude |
| Batch operations | Batch API mentioned but not designed as first-class workflow | Claude |

## Priority Roadmap

### P0: Safety Before Scheduling

Implement before running recurring autonomous workers.

| ID | Work item | Why | Artifacts |
| --- | --- | --- | --- |
| P0-1 | Atomic task locking | prevent two workers claiming same task | `LOCK` file protocol, local `flock`, GitHub concurrency |
| P0-2 | State transition validator | prevent illegal task states | `validate_transition.py`, transition table |
| P0-3 | JSON/schema validation | catch malformed agent writes | `validate_task_state.py`, schemas |
| P0-4 | Structural reviewer isolation | preserve independent reviews | role-specific allowed paths, separate invocations |
| P0-5 | Remove hardcoded repo paths | make local/GitHub runs portable | `$RESEARCH_REPO_ROOT` convention |

Exit criteria:

- two workers cannot claim the same task
- invalid status transitions fail closed
- malformed `status.json` routes to `needs_human`
- methodology and skeptic reviewers cannot read sibling review files
- prompts no longer depend on a local absolute path

### P1: Autonomy Guardrails

Implement before scaling beyond manual or once-daily runs.

| ID | Work item | Why | Artifacts |
| --- | --- | --- | --- |
| P1-1 | Revision counters | prevent infinite revision loops | `revision_count`, `max_revisions` |
| P1-2 | Algorithmic review aggregation | prevent LLM aggregator rule drift | `aggregate_reviews.py` |
| P1-3 | Health monitor | surface problems without daily babysitting | `health_check.py`, `health_report.json` |
| P1-4 | Dynamic tier escalation | let low-tier tasks escalate when output warrants | `escalate_to_tier` field |
| P1-5 | Mission-weight-aligned idea scoring | stop novelty from overpowering quality | scoring formula tied to mission policy |
| P1-6 | Accepted outputs index | reduce duplicate discovery and stale context | `accepted_outputs_index.md` |

Exit criteria:

- tasks auto-route to `needs_human` after revision limit
- Tier 2/3 decisions are routed by deterministic rules
- stale locks, queue overload, cost warnings, and excess `needs_human` are reported
- primary reviewers can escalate tasks to Tier 2/3
- discovery scoring reflects mission weights
- discovery scout reads a current accepted-output index

### P2: Auditability And Calibration

Implement once the workflow has processed seed tasks.

| ID | Work item | Why | Artifacts |
| --- | --- | --- | --- |
| P2-1 | Schema versioning | prevent old tasks from breaking new agents | `schema_version`, migration notes |
| P2-2 | Prompt and framework versioning | make accepted results auditable | `prompt_version`, `framework_version` |
| P2-3 | Human decision log | structure approvals and rejections | `decisions.md` schema |
| P2-4 | Metrics baseline and history | measure whether workflow improves | `metrics_baseline.json`, `metrics_history.jsonl` |
| P2-5 | Claim-strength re-evaluation | prevent drift after revisions | review validation rule |
| P2-6 | Cross-task anti-context injection | avoid repeating known failures | rejected/accepted index lookup in planner |

Exit criteria:

- every task has schema version
- reviewer outputs record prompt and framework versions
- human approvals are append-only and structured
- weekly digest writes metrics snapshot
- revised tasks must restate claim strength
- planner warns workers about similar rejected approaches

### P3: Cost Optimization And Scale

Implement after P0-P2 are stable.

| ID | Work item | Why | Artifacts |
| --- | --- | --- | --- |
| P3-1 | Batch job lifecycle | make Batch API a first-class workflow | `batch_job`, `batch_ingest`, `batch_manifest.json` |
| P3-2 | Programmatic cost tracking | replace manual estimated ledger where possible | API wrapper, token usage ingestion |
| P3-3 | Dynamic killability thresholds | tighten promotion when budget is constrained | budget-aware planner policy |
| P3-4 | Data source audit register | link ideas to verified data dependencies | `data_source_audit.md` |

Exit criteria:

- batch jobs have manifests and ingest tasks
- cost ledger includes actual usage where available
- planner raises promotion thresholds near budget limits
- ideas cite audited data sources before promotion to experiment planning

## Detailed Work Items

### P0-1: Atomic Task Locking

Problem:

- `lock_owner` inside `status.json` is not atomic.

Requirement:

- workers shall claim tasks by creating a task-local `LOCK` file or directory using atomic filesystem semantics.

Implementation status:

- documented in `async_research_workflow/atomic_locking_protocol.md`
- helper script added at `async_research_workflow/scripts/task_lock.py`
- worker prompt and GitHub Actions example updated to require task-local lock acquisition

Recommended local implementation:

```text
research_ops/tasks/TASK-0001/LOCK/
```

Claim process:

1. Attempt atomic `mkdir LOCK`.
2. If it succeeds, worker owns the task.
3. If it fails and lock is fresh, skip task.
4. If it fails and lock is stale, move stale lock to `LOCK.stale.<timestamp>` and retry.
5. Delete `LOCK` only after final status is written and validated.

Acceptance tests:

- two simultaneous workers result in one successful lock
- stale lock is detected and reported
- worker failure leaves enough metadata for recovery

### P0-2: State Transition Validator

Requirement:

- all status transitions shall be checked against an allowlist.

Implementation status:

- documented in `async_research_workflow/state_transition_validation_protocol.md`
- helper script added at `async_research_workflow/scripts/validate_transition.py`
- task status schema updated with `previous_status` and `last_transition_reason`
- worker/reviewer prompts and GitHub Actions example updated to require transition validation

Required fields:

```json
{
  "previous_status": "ready_for_worker",
  "status": "in_progress",
  "last_transition_reason": "worker_claimed"
}
```

Invalid transitions shall:

- fail the job
- write an error to health report
- set or recommend `needs_human` where safe

Initial transition allowlist:

```text
ready_for_worker -> in_progress
in_progress -> awaiting_review
in_progress -> needs_human
in_progress -> paused
awaiting_review -> single_review
awaiting_review -> panel_review
single_review -> accepted | needs_revision | needs_human | paused | rejected
panel_review -> accepted | needs_revision | needs_human | paused | rejected
needs_revision -> ready_for_worker
needs_human -> ready_for_worker | paused | rejected
accepted -> synthesized
```

Acceptance tests:

- worker cannot mark `accepted`
- rejected task cannot return to `in_progress`
- missing `previous_status` fails validation after migration deadline

### P0-3: Schema Validation

Requirement:

- validate all JSON artifacts after agent writes.

Implementation status:

- documented in `async_research_workflow/schema_validation_protocol.md`
- helper script added at `async_research_workflow/scripts/validate_json_artifact.py`
- recovery script added at `async_research_workflow/scripts/recover_status_json.py`
- worker/reviewer prompts and GitHub Actions example updated to validate `status.json`

Scope:

- `status.json`
- idea candidates
- review panel outputs
- future batch manifests

Acceptance tests:

- malformed JSON fails
- missing required fields fail
- invalid enum values fail
- schema failures route to `needs_human` or stop branch
- malformed `status.json` is quarantined and replaced with a valid `needs_human` status

### P0-4: Structural Reviewer Isolation

Requirement:

- review independence shall be enforced by execution context, not only prompt text.

Implementation status:

- documented in `async_research_workflow/reviewer_isolation_protocol.md`
- isolated review context is now exposed through `async-research review prepare-context`
- specialist reviewer prompts updated to run inside isolated bundles
- aggregator prompt updated to run inside an aggregator bundle that includes all reviews

Implementation rule:

- each reviewer runs in a separate process/session/API call
- each reviewer gets only:
  - `task.md`
  - `status.json`
  - `worker_output.md`
  - `artifacts/`
  - its own target review file
- only aggregator sees all reviews

Acceptance tests:

- methodology reviewer cannot read `reviews/primary.md`
- skeptic reviewer cannot read `reviews/methodology.md`
- aggregator waits until required reviews exist

### P0-5: Portable Repository Root

Requirement:

- prompts and scripts shall use `$RESEARCH_REPO_ROOT`, not a hardcoded path.

Local setup:

```bash
export RESEARCH_REPO_ROOT="$(git rev-parse --show-toplevel)"
```

GitHub Actions setup:

```yaml
env:
  RESEARCH_REPO_ROOT: ${{ github.workspace }}
```

Acceptance tests:

- workflow prompt works in local repo
- workflow prompt works in GitHub Actions
- no user-specific absolute repo path remains in active prompt templates

### P1-1: Revision Counters

Requirement:

- tasks shall track revision attempts.

Fields:

```json
{
  "revision_count": 0,
  "max_revisions": 1,
  "revision_limit_hit": false
}
```

Default:

- Tier 1: `max_revisions = 1`
- Tier 2: `max_revisions = 2`
- Tier 3: `max_revisions = 1`, then human gate

Tier 0 is reserved for internal recovery and benchmark fixtures, not normal
operator-authored tasks.

Implementation status:

- task status schema updated with `revision_count`, `max_revisions`, and `revision_limit_hit`
- revision counter is now exposed through `async-research revision`
- documented in `async_research_workflow/revision_counter_protocol.md`
- reviewer and weekly synthesizer prompts updated to use revision counters

Acceptance tests:

- task exceeding max revisions routes to `needs_human`
- reviewer cannot request infinite revisions
- weekly digest reports tasks that hit revision limits

### P1-2: Algorithmic Review Aggregation

Requirement:

- Tier 2/3 routing shall be computed by deterministic rules.

Implementation:

1. parse structured review fields
2. apply tier rule
3. write routing decision
4. optional LLM writes narrative summary after rule-based routing

Implementation status:

- helper script added at `async_research_workflow/scripts/aggregate_reviews.py`
- aggregate schema updated at `async_research_workflow/schemas/review_panel.schema.json`
- documented in `async_research_workflow/algorithmic_review_aggregation_protocol.md`
- aggregator prompt updated so narrative summaries cannot override deterministic routing

Tier 3 rule:

- any `reject` blocks acceptance
- any `needs_human` routes to human
- all reviewers must be `accept` or `accept_with_caveats`
- any public/high-stakes task routes to human before final acceptance

Acceptance tests:

- mixed `accept` + `reject` cannot aggregate to accepted
- missing required review blocks aggregation
- non-standard decision enum fails validation

### P1-3: Health Monitor

Requirement:

- run a daily health check independent of worker/reviewer jobs.

Inputs:

- `queue.md`
- task `status.json` files
- `cost_ledger.csv`
- `discovery_inbox.md`
- lock files

Outputs:

```text
research_ops/health_report.json
research_ops/daily_status.md
```

Checks:

- stale locks
- queue depth
- too many `needs_human`
- too many `in_progress`
- revision limit breaches
- discovery inbox overload
- weekly/monthly budget threshold
- malformed status files
- tasks stuck in same status too long

Implementation status:

- helper script added at `async_research_workflow/scripts/health_check.py`
- documented in `async_research_workflow/health_monitor_protocol.md`
- scheduler prompt added for independent daily health monitoring
- health check writes `research_ops/health_report.json` and appends `research_ops/daily_status.md`

Acceptance tests:

- stale lock appears in health report
- budget warning triggers at 80 percent
- more than 3 `needs_human` tasks triggers alert

### P1-4: Dynamic Tier Escalation

Requirement:

- reviewers may request higher-tier review without human intervention.

Implementation status:

- status schema updated with `escalate_to_tier`, `escalation_reason`, `escalation_requested_by`, and `escalation_requested_at`
- helper script added at `async_research_workflow/scripts/escalate_review_tier.py`
- documented in `async_research_workflow/dynamic_tier_escalation_protocol.md`
- aggregation logs applied escalation metadata and blocks unresolved review-file escalation requests

Field:

```json
{
  "escalate_to_tier": 2,
  "escalation_reason": "worker output needs methodology review before acceptance"
}
```

Acceptance tests:

- Tier 1 task can route to Tier 2 before acceptance
- escalation updates required reviewers
- escalation is logged in aggregate review

### P1-5: Mission-Weighted Idea Scoring

Requirement:

- idea scoring shall reflect mission weights.

Implementation status:

- mission policy added at `async_research_workflow/mission_policy.json`
- helper script added at `async_research_workflow/scripts/score_idea_candidate.py`
- idea candidate schema updated with mission policy version, weighted total, reuse potential, hard gate results, and budget mode
- documented in `async_research_workflow/mission_weighted_idea_scoring_protocol.md`

Replace equal-weight discovery formula with mission-aligned formula.

Initial recommendation:

```text
score =
  2.0 * decision_impact
+ 1.5 * data_availability
+ 1.5 * killability
+ 1.0 * feasibility
+ 1.0 * reuse_potential
+ 0.5 * novelty
- 2.0 * robustness_risk
- 1.0 * cost
```

Acceptance tests:

- idea score references mission policy version
- high novelty cannot dominate weak data and high risk
- budget-constrained mode raises killability threshold

### P1-6: Accepted Outputs Index

Requirement:

- maintain a current index for accepted outputs, separate from weekly narrative digest.

Implementation status:

- accepted-output helper commands added under `async-research accepted`
- documented in `async_research_workflow/accepted_outputs_index_protocol.md`
- planner, discovery scout, and synthesizer prompts updated to refresh/read the index
- duplicate-check command added for planner warnings before promotion

File:

```text
research_ops/accepted_outputs_index.md
```

Columns:

```text
date | task_id | title | key_finding | claim_strength | evidence_link | followups
```

Acceptance tests:

- accepted task appends an index row
- discovery scout reads index
- planner uses index to warn about duplicates

### P2-1: Schema Versioning

Requirement:

- all JSON artifacts shall include `schema_version`.

Fields:

```json
{
  "schema_version": "1.0"
}
```

Migration:

- add migration notes for each schema bump
- provide defaults for new fields
- old tasks must be explicitly migrated or recovered before scheduled agents continue

Acceptance tests:

- missing schema version fails validation or schema-version checks
- schema version mismatch is visible in health report and fails schema-version checks

Implementation status:

- schemas require `schema_version = "1.0"` for task status artifacts
- new helper added at `async_research_workflow/scripts/check_schema_versions.py`
- health monitor reports missing or mismatched versions in `checks.schema_version_warnings`
- schema-version checks fail closed when known JSON artifacts omit or mismatch the expected version
- status recovery, review aggregation, revision counter, tier escalation, and idea scoring helpers write the default version
- migration notes documented in `async_research_workflow/schema_versioning_protocol.md`

### P2-2: Prompt And Framework Versioning

Requirement:

- every task records prompt and framework versions used.

Fields:

```json
{
  "prompt_versions": {
    "worker": "worker_v1.0",
    "primary_reviewer": "primary_reviewer_v1.0"
  },
  "framework_versions": {
    "mission_scoring": "mission_scoring_v1.0",
    "result_acceptance": "result_acceptance_v1.0"
  }
}
```

Acceptance tests:

- accepted result can identify rubrics used
- monthly calibration groups outputs by framework version

Implementation status:

- task status schema allows `prompt_versions` and `framework_versions`
- shared defaults live in `async_research_workflow/scripts/version_metadata.py`
- status-writing helpers preserve existing versions and add defaults when missing
- deterministic review aggregation copies version metadata into `review_panel/aggregate.json`
- monthly calibration helper added at `async_research_workflow/scripts/framework_version_calibration.py`
- prompt/framework versioning protocol documented in `async_research_workflow/prompt_framework_versioning_protocol.md`

### P2-3: Human Decision Log

Requirement:

- human decisions shall be append-only and structured.

File:

```text
research_ops/decisions.md
```

Columns:

```text
date | item_id | decision | reason | approver | related_artifacts
```

Acceptance tests:

- resolving `needs_human` requires decision row
- public/high-stakes approval has decision row
- monthly calibration can summarize human gate reasons

Implementation status:

- append-only decision helper commands added under `async-research decision`
- shared decision log parser added at `async_research_workflow/scripts/decision_log.py`
- `validate_transition.py` now fails `needs_human` exits without a matching decision row
- human decision summaries can be written for monthly calibration
- protocol documented in `async_research_workflow/human_decision_log_protocol.md`

### P2-4: Metrics Baseline And History

Requirement:

- create baseline and append metrics snapshots.

Files:

```text
research_ops/metrics_baseline.json
research_ops/metrics_history.jsonl
```

Metrics:

- tasks created
- tasks accepted
- tasks rejected
- ideas generated
- ideas promoted
- ideas rejected
- human minutes
- estimated cost
- panel reviews
- revision loops

Acceptance tests:

- weekly digest appends one metrics snapshot
- monthly calibration can compute trends

Implementation status:

- metrics helper added with public monthly summary through `async-research metrics summarize`
- baseline file `metrics_baseline.json` is created by init or the first snapshot append
- append-only history file `metrics_history.jsonl` stores weekly snapshots
- weekly synthesizer prompt appends one snapshot per digest run
- monthly calibration prompt writes `monthly_metrics_trends.md`
- protocol documented in `async_research_workflow/metrics_baseline_history_protocol.md`

### P2-5: Claim-Strength Re-Evaluation

Requirement:

- every review pass shall restate claim strength.

Acceptance tests:

- review without `claim_strength` fails validation
- revised task cannot inherit old claim strength silently

Implementation status:

- `aggregate_reviews.py` rejects reviews missing `claim_strength`
- `aggregate_reviews.py` writes `aggregate_claim_strength` from the current review pass
- `async-research revision` and revision aggregation routes clear stale `result.claim_strength`
- accepted outputs prefer current `aggregate_claim_strength`
- protocol documented in `async_research_workflow/claim_strength_re_evaluation_protocol.md`

### P2-6: Cross-Task Anti-Context Injection

Requirement:

- planner shall check prior rejected and accepted outputs for similar tasks.

Context bundle should include:

```text
similar accepted findings
similar rejected approaches
known failure modes
do-not-repeat warnings
```

Acceptance tests:

- task plan references similar prior work when present
- worker receives a concise anti-context section

Implementation status:

- anti-context generation is now exposed through `async-research anti-context build`
- planner prompt runs the helper for each promoted task
- worker prompt reads `anti_context.md` and must address do-not-repeat warnings
- task template includes a Cross-Task Anti-Context section
- protocol documented in `async_research_workflow/cross_task_anti_context_protocol.md`

### P3-1: Batch Job Lifecycle

Requirement:

- batch work shall become first-class.

New task types:

```text
batch_job
batch_ingest
```

Manifest:

```json
{
  "schema_version": "1.0",
  "batch_id": "BATCH-0001",
  "lifecycle_status": "draft",
  "input_files": [],
  "prompt_template": "source_extract_v1.0",
  "model": "cheap_or_batch_model",
  "expected_output_schema": "idea_candidate.schema.json",
  "ingest_path": "research_ops/discovery/",
  "output_trust": "untrusted",
  "costs": {
    "estimated_api_usd": 0,
    "estimated_compute_usd": 0,
    "logged": false
  }
}
```

Acceptance tests:

- batch outputs are not trusted until ingested and reviewed
- batch costs are logged
- batch manifest validates before submission

Implementation status:

- task status schema includes `batch_job` and `batch_ingest`
- batch manifest schema added at `async_research_workflow/schemas/batch_manifest.schema.json`
- batch lifecycle is now exposed through `async-research batch`
- schema-version checks scan `research_ops/batches/*/batch_manifest.json`
- protocol documented in `async_research_workflow/batch_job_lifecycle_protocol.md`

### P3-2: Programmatic Cost Tracking

Requirement:

- where APIs return token usage, write usage programmatically rather than by agent prose.

Acceptance tests:

- cost ledger records actual input/output tokens for API jobs
- health check aggregates costs
- budget thresholds can halt promotion or expensive tasks

Implementation status:

- usage ingestion helper added under `async-research cost ingest-usage`
- cost ledger rows can record `input_tokens`, `output_tokens`, `total_tokens`, and `actual=true`
- health monitor aggregates actual usage token totals from the ledger
- deterministic budget gate exits nonzero when projected spend crosses threshold
- protocol documented in `async_research_workflow/programmatic_cost_tracking_protocol.md`

### P3-3: Dynamic Killability Thresholds

Requirement:

- planner shall tighten promotion requirements when budget is constrained.

Example:

```text
if monthly_budget_used >= 80%:
  minimum_killability = 5
  max_promotions_per_week = 1
```

Acceptance tests:

- budget-constrained mode changes promotion behavior
- daily status notes constrained mode

Implementation status:

- mission policy defines budget-pressure thresholds and per-mode promotion caps
- idea scoring supports `--budget-mode auto --ops-dir research_ops`
- constrained mode raises minimum killability and lowers weekly promotion capacity
- discovery and scheduler prompts score against the current cost ledger before promotion
- discovery prompt records constrained-mode events in `daily_status.md`
- protocol documented in `async_research_workflow/dynamic_killability_thresholds_protocol.md`

### P3-4: Data Source Audit Register

Requirement:

- maintain data source audit status separately from discovery ideas.

File:

```text
research_ops/data_source_audit.md
```

Statuses:

```text
unknown
candidate
available
usable_with_caveats
blocked
restricted
deprecated
```

Rule:

- ideas can enter discovery with plausible data paths
- experiments require audited data readiness

Acceptance tests:

- experiment plan references data audit entries

Implementation status:

- data source audit protocol documented in `async_research_workflow/data_source_audit_register_protocol.md`
- markdown register authoring is now exposed through `async-research source`
- task status schema allows `data_audit_refs`
- planner, worker, and reviewer prompts require audit checks for `experiment_plan` tasks
- discovery may use plausible data paths but experiments require ready audited sources
- blocked/restricted data triggers human gate

## Implementation Sequence

### Step 1: Document Hardening Rules

Update docs and schemas for:

- `LOCK` protocol
- transition validation
- revision counters
- repo root variable
- reviewer isolation
- schema version

### Step 2: Add Validation Scripts

Add:

```text
async_research_workflow/scripts/validate_json_artifact.py
async_research_workflow/scripts/validate_transition.py
async_research_workflow/scripts/aggregate_reviews.py
async_research_workflow/scripts/health_check.py
```

Keep them as packaged helper scripts until each operation has a stable CLI
wrapper.

### Step 3: Update Schemas

Update schemas for:

- `schema_version`
- `previous_status`
- `revision_count`
- `max_revisions`
- `prompt_versions`
- `framework_versions`
- `escalate_to_tier`
- structured decisions

### Step 4: Update Prompts

Update prompts to:

- use `$RESEARCH_REPO_ROOT`
- mention validator scripts
- prohibit direct status writes outside valid transitions
- require claim-strength re-evaluation
- require review-tier escalation when needed

### Step 5: Add Health And Metrics Artifacts

Define:

```text
health_report.json
accepted_outputs_index.md
metrics_baseline.json
metrics_history.jsonl
decisions.md
data_source_audit.md
```

### Step 6: Run Manual Simulation

Before scheduling:

1. create 2 sample tasks
2. run worker manually
3. run primary review manually
4. run Tier 2 review manually
5. intentionally create invalid transition and confirm validation fails
6. intentionally create malformed JSON and confirm recovery routes to `needs_human`
7. intentionally exceed revision limit and confirm `needs_human`

For regression coverage, run the durable acceptance suite:

```bash
async-research acceptance-suite
```

The suite builds temporary fixtures and checks representative P0-P3 and
framework contracts:
atomic locking, transition validation, status recovery, reviewer isolation,
revision limits, tier escalation, review aggregation, health reporting,
mission policy validation, mission scoring, accepted output indexing, audit metadata, metrics snapshots,
anti-context, batch lifecycle, programmatic cost tracking, dynamic budget
thresholds, data-source audit gating, operational readiness documentation,
exploration validation, idea-evaluation validation, experimentation validation,
and result-acceptance validation.

A representative full-loop workflow simulation was also run and documented in
`async_research_workflow/end_to_end_workflow_simulation_report.md`.

### Step 7: Enable Low-Cadence Automation

Only after P0 acceptance:

```text
worker: once daily
reviewer: once daily
health_check: daily
discovery: weekly
synthesizer: weekly
```

## Implementation Backlog

| Priority | Item | Status |
| --- | --- | --- |
| P0 | atomic locking protocol | implemented in docs/examples |
| P0 | state transition validator | implemented in docs/examples |
| P0 | schema validation after writes | implemented in docs/examples |
| P0 | structural reviewer isolation | implemented in docs/examples |
| P0 | portable repo root variable | implemented in docs/examples |
| P1 | revision counters | implemented in docs/examples |
| P1 | algorithmic review aggregation | implemented in docs/examples |
| P1 | health monitor | implemented in docs/examples |
| P1 | dynamic tier escalation | implemented in docs/examples |
| P1 | mission-weighted idea scoring | implemented in docs/examples |
| P1 | accepted outputs index | implemented in docs/examples |
| P2 | schema versioning | implemented in docs/examples |
| P2 | prompt/framework versioning | implemented in docs/examples |
| P2 | human decision log | implemented in docs/examples |
| P2 | metrics baseline/history | implemented in docs/examples |
| P2 | claim-strength re-evaluation | implemented in docs/examples |
| P2 | cross-task anti-context injection | implemented in docs/examples |
| P3 | batch job lifecycle | implemented in docs/examples |
| P3 | programmatic cost tracking | implemented in docs/examples |
| P3 | dynamic killability thresholds | implemented in docs/examples |
| P3 | data source audit register | implemented in docs/examples |

## What Not To Change

Keep:

- repo-as-memory
- discovery inbox before execution queue
- hard gates over composite scores
- slow cadence
- bounded worker tasks
- independent first-pass reviews
- human approval for public/high-stakes claims

The feedback does not require replacing the architecture. It requires enforcing it.
