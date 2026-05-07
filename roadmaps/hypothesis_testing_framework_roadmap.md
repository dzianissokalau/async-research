# Hypothesis Testing Framework Roadmap

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

## Product Decision

The framework should be called the **Hypothesis Testing Framework** in product
language and the **analysis run framework** in implementation contracts.

It sits after accepted experiment planning:

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

## Non-Goals

- Do not build a general stats engine.
- Do not depend on one modeling library in the core package.
- Do not let agents choose methods after seeing results.
- Do not let `run_analysis` rewrite the accepted experiment plan.
- Do not accept causal claims without explicit identification tests.
- Do not require every lightweight research note to run a full statistical
  framework.

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

## Workspace Artifacts

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

## Phase 0: Invariants

Lock these decisions before implementation:

- An accepted `experiment_plan` is required before `run_analysis`.
- The run manifest is canonical for what actually ran.
- The result summary is canonical for what claim is being made.
- Analysis workers may not silently change hypotheses, data windows, metrics,
  baselines, or claim limits.
- All deviations from the accepted plan must be explicit and reviewed.
- Predictive, descriptive, and causal claims have different gates.
- Human approval is required for high-stakes, public, or strong causal claims.

Acceptance:

- docs state the difference between experiment planning, analysis execution,
  result evaluation, and accepted evidence
- no workflow path allows direct discovery-to-analysis execution
- result reviewers compare outputs to the accepted plan, not to a new story

## Phase 1: Analysis Run Contract

Add a standard run manifest contract.

Suggested schema:

```text
async_research_workflow/schemas/analysis_run.schema.json
```

Required fields:

- `schema_version`
- `framework_version`
- `run_id`
- `task_id`
- `experiment_plan_id`
- `accepted_plan_path`
- `analysis_config_path`
- `data_versions`
- `code_version`
- `method_family`
- `baseline_refs`
- `primary_metric`
- `planned_outputs`
- `started_at`
- `completed_at`
- `runtime_minutes`
- `cost`
- `deviations_from_plan`

Acceptance:

- a `run_analysis` task can declare exactly what will run
- manifest references an accepted experiment plan
- manifest records data and code versions
- deviations are explicit, not hidden in prose

## Phase 2: Preflight Validator

Add a read-only preflight validator:

```bash
async-research analysis preflight <task-dir> --ops-dir research_ops
```

The validator should check:

- task type is `run_analysis`
- accepted experiment plan is referenced
- source/data refs still pass freshness and use-case gates
- planned method family is allowed by the experiment plan
- primary metric matches the plan
- baseline outputs are required
- budget is within the accepted plan
- output paths are inside the task folder
- no known stale accepted memory is being reused as current evidence

Acceptance:

- preflight is read-only
- unsafe runs fail closed before analysis starts
- warnings are explicit and reviewable

## Phase 3: Output Contracts

Define structured outputs for completed runs.

Suggested schemas:

```text
async_research_workflow/schemas/analysis_metrics.schema.json
async_research_workflow/schemas/analysis_diagnostics.schema.json
async_research_workflow/schemas/robustness_checks.schema.json
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

Acceptance:

- result reviewers can inspect the run without reading all code
- missing baseline or robustness outputs fail validation
- output contracts are generic enough for regression, matching, forecasting,
  classification, and causal designs

## Phase 4: Claim Gates

Add claim-type gates that connect analysis outputs to result acceptance.

Claim classes:

- descriptive
- predictive
- associative
- causal
- probabilistic or calibrated-risk

Gate examples:

- predictive claims require out-of-sample validation and baseline comparison
- causal claims require identification strategy, placebo or falsification tests
  where appropriate, and explicit assumptions
- probability claims require calibration or uncertainty diagnostics
- public/high-stakes claims require human approval
- strong claims require methodology review and clear robustness evidence

Acceptance:

- causal language is blocked without identification tests
- probability claims are blocked without calibration or uncertainty checks
- claim strength is capped when diagnostics are weak
- result acceptance can explain why a claim was accepted, capped, or rejected

## Phase 5: Analysis Validation CLI

Add validation commands:

```bash
async-research analysis validate-run <task-dir> --ops-dir research_ops
async-research analysis validate-results <task-dir> --ops-dir research_ops
```

`validate-run` should compare the manifest and artifacts to the accepted plan.
`validate-results` should compare the structured outputs to the result summary
and claim gates.

Acceptance:

- valid run artifacts pass
- missing manifest fails
- missing baseline fails
- unplanned metric changes fail or require human decision
- claim gates produce machine-readable blockers and warnings

## Phase 6: Task Templates And Prompts

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

Acceptance:

- planner can create a bounded `run_analysis` task from an accepted plan
- worker instructions are clear enough for Codex or another agent
- reviewers have a checklist tied to machine-readable artifacts

## Phase 7: Result Acceptance Integration

Extend result acceptance to consume analysis-run artifacts.

Integration points:

- `result_summary_template.md`
- `validate_result_acceptance.py`
- `evidence_ledger.md`
- `accepted_outputs_index.md`
- `revalidation_schedule.md`

Acceptance:

- accepted empirical results cite run manifest, data versions, and diagnostics
- rejected results preserve reusable anti-context
- stale data or stale diagnostics trigger revalidation
- accepted evidence records claim type and claim strength

## Phase 8: Optional Runner Adapters

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
- `analysis preflight` exists and is read-only
- `analysis validate-run` exists
- result outputs have a minimum structured metrics/diagnostics contract
- result acceptance can cap or reject claims based on missing diagnostics
- `run_analysis` and `evaluate_results` task templates are clear
- tests cover missing plan, missing baseline, stale data, unplanned deviation,
  causal claim without identification tests, and probability claim without
  calibration checks

## V1 Definition

The V1 feature is complete when:

- accepted experiment plans can produce validated analysis runs
- completed analysis runs can produce validated result summaries
- claim gates are enforced for descriptive, predictive, causal, and probability
  claims
- accepted empirical evidence is reproducible enough to rerun or audit
- dashboard and weekly digest can surface analysis status, blockers, diagnostics,
  and accepted empirical results

## Open Questions

- Should run manifests live only under task artifacts, or also be indexed under
  a workspace-level `research_ops/runs/` cache?
- Should the core package define method families only, or also provide small
  reference implementations for common diagnostics?
- Should probability calibration be mandatory only for probability claims, or
  also for ranking/risk-score outputs?
- How strict should deviation handling be for exploratory analysis tasks that
  are explicitly not meant to produce accepted evidence?
