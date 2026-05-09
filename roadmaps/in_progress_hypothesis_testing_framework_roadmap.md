# Hypothesis Testing Framework Roadmap

Status: In Progress
Current phase: Phase 2 ready
Last updated: 2026-05-09
Next action: Implement Phase 2 preflight validator
Blocked by: None

Created: 2026-05-07

## Summary

Build a framework for turning accepted hypotheses and experiment plans into
reviewable empirical tests. The feature should standardize analysis runs,
diagnostics, robustness checks, and claim limits without turning
`async-research` into a statistics library.

The core package should own contracts, validation, provenance, and review
gates. Project-specific repositories should own the actual data loading,
regression code, causal inference implementation, model fitting, and
domain-specific diagnostics.

Sequencing note: this remains the next research-capability roadmap after the
foundation stack. The May 9, 2026 Manus review also identified a separate
adoption track, captured in the
[Operator UX And Workflow Ergonomics Roadmap](./not_started_operator_ux_workflow_ergonomics_roadmap.md).
If the goal is smoother dogfooding and first-user success, implement the
operator UX P1s first; if the goal is empirical research capability, start this
roadmap.

## Execution Decisions

V1 should be contract-first, read-only-first, and backward-compatible. The
first execution goal is to make the analysis run manifest and validation path
real without executing project-owned analysis code.

The framework should be called the **Hypothesis Testing Framework** in product
language and the **analysis run framework** in implementation contracts.

### V1 Scope

V1 includes:

- analysis run manifest schema and template
- read-only `analysis preflight`
- structured metrics, diagnostics, robustness, and leakage output contracts
- read-only `analysis validate-run`
- read-only `analysis validate-results`
- claim-type gates for descriptive, associative, predictive, causal, and
  probabilistic claims
- `run_analysis` and `evaluate_results` task guidance
- result acceptance integration that can cap, reject, or route claims to human
  review based on run artifacts
- read-only weekly digest, health, readiness, or dashboard summaries after the
  validators are stable

V1 defers:

- general-purpose statistical modeling
- project-owned data loading or feature engineering
- notebook, SQL, dbt, warehouse, or local script execution adapters
- automatic reruns of stale analyses
- a workspace-level `research_ops/runs/` cache
- strict causal inference reference implementations
- any mutation of accepted experiment plans from a `run_analysis` task

### Authority Model

Keep five separate authorities:

| Artifact | Authority |
| --- | --- |
| accepted `experiment_plan` | what was approved before results were known |
| `artifacts/analysis_run/run_manifest.json` | what actually ran |
| structured run outputs | what was measured and diagnosed |
| result summary | what claim is being made |
| result acceptance record | what evidence is allowed into durable memory |

The accepted experiment plan remains immutable from the analysis task. The run
manifest records deviations, but does not approve them. The result summary may
describe a claim, but validators and reviewers decide whether that claim is
supported, capped, rejected, or routed to a human.

If these authorities disagree, validation fails closed or caps the claim. The
framework must not choose the most favorable story after seeing results.

### Accepted Plan Requirement

An analysis run is eligible only when it references an accepted experiment plan.
In V1, an accepted plan can be recognized by:

- an `experiment_plan` task `status.json` with `status: accepted`
- the same task listed in `accepted_outputs_index.md`
- a valid experiment-plan JSON artifact that still passes
  `async-research experiment validate`

If the task status, accepted output index, and plan artifact disagree,
preflight fails. If the accepted plan cannot be found, preflight fails. Direct
discovery-to-analysis execution remains blocked.

### Claim Policy

Claim gates are different by claim class:

- descriptive claims require source governance, data versions, limitations, and
  clear scope.
- associative claims require baseline or comparison context, leakage checks, and
  caveats that avoid causal language.
- predictive claims require out-of-sample validation, baseline comparison, and
  leakage checks.
- causal claims require an identification strategy, identification tests, and
  appropriate falsification, placebo, or sensitivity checks.
- probabilistic or calibrated-risk claims require calibration or uncertainty
  diagnostics.

Public, high-stakes, or strong claims require human approval even when machine
validation passes.

### Validator Contract

Add read-only commands:

```bash
async-research analysis preflight <task-dir> --ops-dir research_ops
async-research analysis validate-run <task-dir> --ops-dir research_ops
async-research analysis validate-results <task-dir> --ops-dir research_ops
```

Exit codes:

- `0` when validation passes cleanly
- `2` when validation finds warnings or blockers that are representable in JSON
- `3` when the request is invalid, such as a missing required argument
- `4` when task state or artifacts are malformed enough that the validator
  cannot reason about them

Warning-only validation may return exit `2` with `ok: true`,
`warning_count > 0`, and no hard gate failures. Hard gate failures return exit
`2` with `ok: false`. Malformed JSON, unsafe paths, or unreadable required
artifacts return exit `4`.

Validator JSON should include:

- `ok`
- `action`
- `task_dir`
- `ops_dir`
- `run_id`
- `experiment_plan_id`
- `accepted_plan_task_id`
- `hard_gate_failures`
- `warnings`
- `claim_gate_results`
- `next_step`

### Backward Compatibility

Implementation must preserve:

- existing `async-research init` behavior unless optional artifact templates are
  added
- existing `async-research experiment validate`
- existing `async-research result-acceptance`
- existing `async-research source` and `async-research data` gates
- existing acceptance of non-result routine task artifacts
- existing starter smoke, acceptance suite, and benchmark expectations

`run_analysis` and `evaluate_results` are already valid task types. V1 should
make those task types safer; it should not change unrelated task lifecycles.

Cold-start workspaces remain valid. Missing analysis artifacts should block only
analysis validation or accepted empirical claims, not discovery, catalog, data
readiness, or literature work.

### First Test Matrix

Minimum tests for the first implementation slices:

- packaged resources include the analysis run schema and template
- valid analysis run manifest passes schema validation
- malformed manifest fails with path-specific schema errors
- task type other than `run_analysis` fails preflight
- missing accepted experiment plan fails preflight
- unaccepted experiment plan fails preflight
- experiment plan artifact that no longer validates fails preflight
- manifest `experiment_plan_id` mismatch fails preflight
- manifest primary metric mismatch fails preflight
- manifest method family not allowed by the plan fails preflight
- data refs that are blocked, stale, or not approved for experiment planning
  fail or warn consistently with existing source/data gates
- budget above the accepted plan fails preflight
- output paths outside the task folder fail validation
- missing baseline metrics fail run validation
- missing robustness or leakage outputs fail run validation
- unplanned metric changes fail or require human decision
- causal claim without identification tests is capped or rejected
- probability claim without calibration or uncertainty diagnostics is capped or
  rejected
- result acceptance for non-result task types remains unchanged
- CLI architecture and help tests include the new `analysis` command group

## What It Does

The hypothesis testing framework supports this pipeline:

```text
catalog idea
  -> data_readiness
  -> hypothesis_card
  -> experiment_plan
  -> accepted experiment plan
  -> run_analysis
  -> evaluate_results
  -> result acceptance
```

The existing experimentation framework validates whether a plan is safe and
well specified before results are known. The hypothesis testing framework
validates whether the analysis run followed that plan and whether the output can
support the claimed evidence.

It should answer:

- what accepted plan the analysis executed
- which data versions and code version were used
- which method family and baseline actually ran
- whether planned metrics and outputs were produced
- whether deviations from the plan were explicit
- whether diagnostics, robustness checks, leakage checks, and limitations are
  sufficient for the requested claim
- whether the result can enter durable accepted evidence memory

## Delivery Strategy

Build this as a sequence of small, deterministic slices. Do not start with
runner adapters, dashboards, or statistical helper implementations. Those should
consume stable contracts and validators rather than inventing their own read
path.

Recommended sequence:

1. Lock execution decisions, authority model, compatibility rules, and test
   matrix.
2. Add the analysis run manifest schema and artifact template.
3. Add read-only preflight against accepted experiment plans.
4. Add structured output contracts for metrics, diagnostics, robustness, and
   leakage checks.
5. Add read-only run and result validators.
6. Add claim gates and clear machine-readable cap/reject reasons.
7. Harden task templates, task contracts, and planner/reviewer prompts.
8. Integrate result acceptance and durable evidence records.
9. Add read-only health, readiness, weekly digest, and dashboard surfaces.
10. Consider optional runner adapters only after validation works without them.

Each phase should leave the package usable. Each strict blocker should ship
after a warning or read-only version has focused tests.

Delivery boundary:

- MVP: Phases 0 through 6. This is the manifest contract, read-only preflight,
  output contracts, validation CLI, claim gates, and task guidance.
- V1 post-MVP: Phases 7 through 8. This adds result acceptance integration and
  read-only operational surfaces.
- V2: Phase 9 optional runner adapters, workspace-level run indexes, automated
  reruns, and stricter project-specific execution helpers.

## Progress

Last updated: 2026-05-09

| Phase | Step | Status | Description | Evidence / Notes |
| ---: | --- | --- | --- | --- |
| 0 | Lock execution decisions | Complete | Capture V1 scope, authority model, accepted plan requirement, validator contract, compatibility rules, and first test matrix before package implementation starts. | This roadmap now defines contract-first execution and keeps the core package out of project-owned statistics code. |
| 1 | Analysis run contract | Complete | Add `analysis_run.schema.json`, a manifest template, packaged resource tests, and docs for the canonical `artifacts/analysis_run/` layout. | Adds the Phase 1 schema/template contract, worker guidance, task contract docs, framework docs, and focused schema/resource tests. |
| 2 | Preflight validator | Not Started | Add read-only `async-research analysis preflight` against task status, accepted experiment plan, source/data governance, budget, metric, method, and path safety. | Should fail closed before analysis starts. |
| 3 | Output contracts | Not Started | Add structured metrics, diagnostics, robustness, and leakage schemas that are generic across regression, matching, forecasting, classification, and causal designs. | Keep project-specific diagnostics in project repos. |
| 4 | Claim gates | Not Started | Add claim-type and claim-strength gate logic for descriptive, associative, predictive, causal, and probabilistic claims. | Strong, public, and high-stakes claims require human approval. |
| 5 | Analysis validation CLI | Not Started | Add `analysis validate-run` and `analysis validate-results` with machine-readable blockers and warnings. | Commands are read-only in V1. |
| 6 | Task templates and prompts | Not Started | Update `run_analysis`, `evaluate_results`, methodology reviewer, and result reviewer guidance so workers emit the required artifacts. | Completes the MVP usability loop. |
| 7 | Result acceptance integration | Not Started | Extend result acceptance, evidence ledger, accepted outputs index, and revalidation schedule to consume run artifacts. | Accepted empirical evidence should cite manifest, data versions, diagnostics, and claim gates. |
| 8 | Read-only surfaces | Not Started | Surface analysis status, blockers, diagnostics, stale runs, and empirical evidence in weekly digest, health, readiness, and dashboard views. | Build only after validators are stable. |
| 9 | Optional runner adapters | Not Started | Consider thin local script, notebook, SQL, dbt, warehouse, or Python entrypoint wrappers. | Adapters remain optional and cannot bypass preflight or validation. |

## Framework Integration

Existing artifacts:

```text
research_ops/tasks/*/status.json
research_ops/tasks/*/worker_output.md
research_ops/data_source_audit.md
research_ops/data/
research_ops/evidence_ledger.md
research_ops/accepted_outputs_index.md
research_ops/rejected_results.md
research_ops/revalidation_schedule.md
src/async_research_workflow/schemas/experiment_plan.schema.json
src/async_research_workflow/schemas/result_acceptance.schema.json
src/async_research_workflow/templates/artifact_templates/experiment_plan_template.md
src/async_research_workflow/templates/artifact_templates/result_summary_template.md
src/async_research_workflow/scripts/validate_experiment_plan.py
src/async_research_workflow/scripts/validate_result_acceptance.py
```

New package artifacts:

```text
src/async_research_workflow/schemas/analysis_run.schema.json
src/async_research_workflow/schemas/analysis_metrics.schema.json
src/async_research_workflow/schemas/analysis_diagnostics.schema.json
src/async_research_workflow/schemas/analysis_robustness_checks.schema.json
src/async_research_workflow/templates/artifact_templates/analysis_run_manifest_template.md
```

Recommended run artifact layout:

```text
research_ops/tasks/TASK-0004-run-analysis/
  task.md
  status.json
  worker_output.md
  artifacts/
    analysis_run/
      run_manifest.json
      analysis_config.json
      data_versions.json
      metrics.json
      diagnostics.json
      diagnostics.md
      robustness_checks.json
      leakage_checks.json
      model_outputs/
      tables/
      figures/
      logs/
```

The canonical narrative result still lands in `worker_output.md`, but structured
run state should live under `artifacts/analysis_run/`.

## Non-Goals

- Do not build a general stats engine.
- Do not depend on one modeling library in the core package.
- Do not let agents choose methods after seeing results.
- Do not let `run_analysis` rewrite the accepted experiment plan.
- Do not accept causal claims without explicit identification tests.
- Do not require every lightweight research note to run a full statistical
  framework.
- Do not create runner adapters before validation works without adapters.

## What The Framework Owns

Core-owned contracts:

- analysis run manifest
- preflight checks against the accepted experiment plan
- data/source/version provenance
- method-family declaration
- baseline execution evidence
- diagnostics and robustness output shape
- claim-strength and claim-type gates
- result-summary compatibility
- reproducibility and rerun metadata

Project-owned implementation:

- SQL, notebooks, scripts, or pipelines
- regression and model code
- causal inference estimators
- data transformations
- feature engineering
- domain-specific diagnostics
- visualization artifacts

## Phase 0: Lock Product Invariants

Purpose: prevent empirical tests from becoming post-hoc storytelling.

Decisions to record before implementation:

- An accepted `experiment_plan` is required before `run_analysis`.
- The accepted experiment plan is canonical for what was approved before
  results were known.
- The run manifest is canonical for what actually ran.
- The result summary is canonical for what claim is being made.
- The result acceptance record is canonical for what evidence is accepted.
- Analysis workers may not silently change hypotheses, data windows, metrics,
  baselines, or claim limits.
- All deviations from the accepted plan must be explicit and reviewed.
- Predictive, descriptive, associative, causal, and probabilistic claims have
  different gates.
- Human approval is required for high-stakes, public, or strong causal claims.

Implementation steps:

1. Capture V1 scope and deferrals.
2. Capture the authority model.
3. Define the accepted plan requirement.
4. Define validator exit codes and JSON output expectations.
5. Define compatibility rules.
6. Define the first test matrix.

Acceptance:

- roadmap and docs state the difference between experiment planning, analysis
  execution, result evaluation, and accepted evidence
- no workflow path allows direct discovery-to-analysis execution
- result reviewers compare outputs to the accepted plan, not to a new story
- implementation can begin with Phase 1 without another planning pass

## Phase 1: Analysis Run Contract

Purpose: make the run manifest the canonical record of what actually ran.

Add a standard run manifest contract:

```text
src/async_research_workflow/schemas/analysis_run.schema.json
src/async_research_workflow/templates/artifact_templates/analysis_run_manifest_template.md
```

Required fields:

- `schema_version`
- `framework_version`
- `run_id`
- `task_id`
- `task_type`
- `experiment_plan_id`
- `accepted_plan_task_id`
- `accepted_plan_path`
- `accepted_plan_result_acceptance_path`
- `analysis_config_path`
- `data_versions`
- `code_version`
- `runner`
- `method_family`
- `candidate_method`
- `baseline_refs`
- `primary_metric`
- `planned_outputs`
- `output_paths`
- `started_at`
- `completed_at`
- `runtime_minutes`
- `cost`
- `deviations_from_plan`
- `reproducibility`

Schema decisions:

- `schema_version` starts at `1.0`.
- `framework_version` starts at `analysis_run_v1.0`.
- `run_id` uses a stable `RUN-0000` style pattern.
- `task_id` must match the analysis task status.
- `task_type` must be `run_analysis` for preflight.
- paths must be workspace-relative and must not escape the task folder unless
  they reference accepted input artifacts.
- deviations are an array of explicit objects, not free-form prose only.
- `runner` is descriptive in V1, such as `manual`, `local_script`, `notebook`,
  `sql`, `dbt`, `warehouse_job`, or `other`; the core package does not execute
  it.

Implementation steps:

1. Add `analysis_run.schema.json`.
2. Add the manifest template.
3. Package the new resources.
4. Add schema/resource tests.
5. Update task contracts and packaged docs to mention the manifest.

Acceptance:

- a `run_analysis` task can declare exactly what will run
- manifest references an accepted experiment plan
- manifest records data and code versions
- manifest records method family, baseline refs, metric, planned outputs, and
  output paths
- deviations are explicit, not hidden in prose

## Phase 2: Preflight Validator

Purpose: fail unsafe analysis tasks before results exist.

Add a read-only preflight validator:

```bash
async-research analysis preflight <task-dir> --ops-dir research_ops
```

The validator should check:

- task type is `run_analysis`
- `status.json` passes the task status schema
- manifest exists and passes `analysis_run.schema.json`
- accepted experiment plan is referenced
- accepted experiment plan task exists and is accepted
- accepted plan artifact still passes `async-research experiment validate`
- manifest `experiment_plan_id` matches the accepted plan
- source/data refs still pass freshness and use-case gates
- planned method family is allowed by the experiment plan
- primary metric matches the plan
- baseline outputs are required
- budget is within the accepted plan
- output paths are inside the task folder
- no known stale accepted memory is being reused as current evidence

Implementation steps:

1. Add `analysis_runs.py` read helpers.
2. Load task status, manifest, accepted plan, and source/data reports.
3. Reuse existing experiment, source, data, and accepted-memory logic where
   possible.
4. Wire `async-research analysis preflight`.
5. Add CLI architecture and help tests.
6. Add focused preflight tests for missing plan, stale data, budget overrun,
   metric mismatch, method mismatch, and unsafe paths.

Acceptance:

- preflight is read-only
- unsafe runs fail closed before analysis starts
- warnings are explicit and reviewable
- preflight output identifies the next corrective action

## Phase 3: Output Contracts

Purpose: let reviewers inspect completed runs without reading all project code.

Define structured outputs for completed runs:

```text
src/async_research_workflow/schemas/analysis_metrics.schema.json
src/async_research_workflow/schemas/analysis_diagnostics.schema.json
src/async_research_workflow/schemas/analysis_robustness_checks.schema.json
```

Minimum output families:

- baseline metrics
- candidate metrics
- validation split metrics
- segment diagnostics
- missingness and join-quality diagnostics
- leakage check results
- robustness checks
- uncertainty or calibration checks when relevant
- run limitations

Implementation steps:

1. Add metrics schema with metric role, value, unit, split, segment, and source.
2. Add diagnostics schema for missingness, joins, leakage, calibration, and
   limitations.
3. Add robustness schema for planned checks, results, pass/fail status, and
   limitation text.
4. Add templates or examples under artifact templates.
5. Package resources and add schema tests.

Acceptance:

- result reviewers can inspect the run without reading all code
- missing baseline or robustness outputs fail validation
- output contracts are generic enough for regression, matching, forecasting,
  classification, and causal designs
- output schemas do not require a specific modeling library

## Phase 4: Claim Gates

Purpose: connect analysis outputs to the maximum claim that can be accepted.

Claim classes:

- descriptive
- associative
- predictive
- causal
- probabilistic or calibrated-risk

Gate examples:

- predictive claims require out-of-sample validation and baseline comparison
- causal claims require identification strategy, placebo or falsification tests
  where appropriate, and explicit assumptions
- probability claims require calibration or uncertainty diagnostics
- public/high-stakes claims require human approval
- strong claims require methodology review and clear robustness evidence

Implementation steps:

1. Define claim gate result objects.
2. Map missing outputs to claim caps.
3. Add causal-language and probability-claim checks.
4. Add human approval requirements for public, high-stakes, and strong claims.
5. Add tests for cap, reject, and human-review routes.

Acceptance:

- causal language is blocked without identification tests
- probability claims are blocked without calibration or uncertainty checks
- claim strength is capped when diagnostics are weak
- result acceptance can explain why a claim was accepted, capped, or rejected

## Phase 5: Analysis Validation CLI

Purpose: validate completed analysis artifacts before result acceptance relies
on them.

Add validation commands:

```bash
async-research analysis validate-run <task-dir> --ops-dir research_ops
async-research analysis validate-results <task-dir> --ops-dir research_ops
```

`validate-run` should compare the manifest and artifacts to the accepted plan.
`validate-results` should compare the structured outputs to the result summary
and claim gates.

Implementation steps:

1. Share read helpers with preflight.
2. Validate manifest and structured output schemas.
3. Compare manifest, outputs, and result summary against the accepted plan.
4. Emit machine-readable blockers and warnings.
5. Add CLI tests for valid artifacts, missing manifest, missing baseline,
   unplanned metric changes, and claim gate failures.

Acceptance:

- valid run artifacts pass
- missing manifest fails
- missing baseline fails
- unplanned metric changes fail or require human decision
- claim gates produce machine-readable blockers and warnings

## Phase 6: Task Templates And Prompts

Purpose: make worker and reviewer expectations clear enough for Codex or
another agent to execute.

Add or update templates for:

- `run_analysis`
- `evaluate_results`
- methodology reviewer
- result reviewer

Worker rules:

- run only the accepted plan or record a deviation
- write all outputs inside the task folder
- include run manifest and structured metrics
- include result summary using the existing template
- do not upgrade claim strength after seeing attractive results

Implementation steps:

1. Update `task_template.md`.
2. Update `result_summary_template.md` to point at
   `artifacts/analysis_run/run_manifest.json`.
3. Update `task_contracts.md`.
4. Update scheduler and reviewer prompts.
5. Add docs/reference tests where command names are mentioned.

Acceptance:

- planner can create a bounded `run_analysis` task from an accepted plan
- worker instructions are clear enough for Codex or another agent
- reviewers have a checklist tied to machine-readable artifacts
- docs use the public CLI commands rather than internal helper paths

## Phase 7: Result Acceptance Integration

Purpose: keep unsupported empirical claims out of durable evidence memory.

Extend result acceptance to consume analysis-run artifacts.

Integration points:

- `result_summary_template.md`
- `validate_result_acceptance.py`
- `evidence_ledger.md`
- `accepted_outputs_index.md`
- `revalidation_schedule.md`

Implementation steps:

1. Load and validate run artifacts during result acceptance for `run_analysis`
   and `evaluate_results`.
2. Apply claim caps from analysis validators.
3. Record run manifest, data versions, diagnostics, and claim gates in
   `result_acceptance.json`.
4. Update evidence ledger rows with claim type, claim strength, and
   revalidation triggers.
5. Preserve rejected empirical results as reusable anti-context.

Acceptance:

- accepted empirical results cite run manifest, data versions, and diagnostics
- rejected results preserve reusable anti-context
- stale data or stale diagnostics trigger revalidation
- accepted evidence records claim type and claim strength

## Phase 8: Read-Only Surfaces

Purpose: make analysis state visible without creating another execution queue.

Add read-only surface summaries for:

- active `run_analysis` tasks
- preflight blockers
- completed runs missing validation
- accepted empirical evidence
- stale data or diagnostics requiring revalidation
- claim caps and human-review requirements

Implementation steps:

1. Feed health/readiness from analysis validator output.
2. Add weekly digest analysis summary.
3. Add dashboard read model after the validator stabilizes.
4. Keep surfaces read-only in V1.

Acceptance:

- operator can see which analyses are safe to run
- operator can see why an empirical claim is blocked or capped
- dashboard and weekly digest do not mutate task artifacts

## Phase 9: Optional Runner Adapters

Purpose: reduce repetitive glue after contracts are stable.

Only after contracts are stable, consider optional helpers for common execution
patterns.

Possible adapters:

- local script runner
- notebook-to-artifact wrapper
- SQL query runner
- dbt or warehouse job wrapper
- Python function entrypoint

These should remain thin. They execute project-owned code and write artifacts
that the core framework validates.

Acceptance:

- adapters are optional
- validation works without adapters
- adapters cannot bypass preflight or result validation

## MVP Definition

The MVP is complete when:

- analysis run manifest schema exists
- analysis run manifest template exists
- `analysis preflight` exists and is read-only
- `analysis validate-run` exists
- `analysis validate-results` exists
- result outputs have minimum structured metrics, diagnostics, robustness, and
  leakage contracts
- claim gates can cap or reject unsupported descriptive, predictive, causal, and
  probability claims
- `run_analysis` and `evaluate_results` task templates are clear
- tests cover missing plan, missing baseline, stale data, unplanned deviation,
  causal claim without identification tests, and probability claim without
  calibration checks

## V1 Definition

The V1 feature is complete when:

- accepted experiment plans can produce validated analysis runs
- completed analysis runs can produce validated result summaries
- claim gates are enforced for descriptive, associative, predictive, causal, and
  probability claims
- accepted empirical evidence is reproducible enough to rerun or audit
- result acceptance records run manifest, data versions, diagnostics, claim
  gates, and revalidation triggers
- dashboard and weekly digest can surface analysis status, blockers,
  diagnostics, and accepted empirical results

## Open Questions

- Should run manifests live only under task artifacts, or also be indexed under
  a workspace-level `research_ops/runs/` cache after V1?
- Should the core package define method families only, or also provide small
  reference implementations for common diagnostics after contracts stabilize?
- Should probability calibration be mandatory only for probability claims, or
  also for ranking/risk-score outputs?
- How strict should deviation handling be for exploratory analysis tasks that
  are explicitly not meant to produce accepted evidence?
- Should `evaluate_results` have a separate result-evaluation manifest, or is
  the result summary plus run manifest enough?
