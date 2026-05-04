# Experimentation Framework Requirements And Framework v1.0

## Purpose

The experimentation framework defines what a valid experiment plan must contain before any analysis or model run begins.

Its job is to prevent costly, leaky, or weak experiments from running.

This document now defines both the requirements and the executable
`experimentation_v1.0` framework used by the async workflow.

## Core Principle

Experiments should be approved before results are known.

This reduces p-hacking, weak baselines, and post-hoc storytelling.

## Executable Framework Contract

Every `experiment_plan` worker output shall include either:

- `experiment_plan.json`
- or a fenced JSON block inside `worker_output.md`

The JSON plan must conform to:

```text
async_research_workflow/experiment_plan.schema.json
```

Validate the plan with:

```bash
async-research experiment validate \
  research_ops/tasks/TASK-0003-repeat-sales-experiment-plan/worker_output.md \
  --ops-dir research_ops \
  --task-dir research_ops/tasks/TASK-0003-repeat-sales-experiment-plan
```

The validator fails closed if hard gates fail. A failed experiment plan should
be routed to `needs_revision` or `needs_human`; it must not advance to
`run_analysis`.

## Experiment Lifecycle

```text
hypothesis_card or accepted idea
-> data_readiness if needed
-> experiment_plan
-> framework validation
-> Tier 2 review
-> accepted experiment plan
-> run_analysis
-> evaluate_results
-> result acceptance review
```

Direct promotion from idea discovery to `run_analysis` is forbidden. Direct
promotion from idea discovery to `experiment_plan` is allowed only when audited
data dependencies already exist and the planner can explain why no additional
data-readiness task is needed.

## Required Plan Object

The plan object is the durable pre-registration artifact. It includes:

- identifiers: `experiment_id`, `task_id`, `hypothesis_id`
- scope: `research_question`, `decision_use_case`, `target_outcome`,
  `population`, `geography`, `time_period`
- data contract: `data_audit_refs`, `dataset_versions`, inclusion and
  exclusion rules
- modeling contract: `feature_set`, `baselines`, `candidate_methods`
- validation contract: time split, spatial or blocked holdout, segment analysis,
  missingness and join checks, leakage review
- outcome contract: metrics, success criteria, failure criteria, robustness
  checks
- execution contract: budget, stop conditions, output directory, run manifest
- claim contract: strongest supported claim, causal/public claim limits
- review contract: 1-5 scores on all framework dimensions

The plan should be complete enough that a separate `run_analysis` worker can
execute it without reinterpreting the research goal.

## Hard Gate Enforcement

`validate_experiment_plan.py` enforces:

- schema validity
- at least one audited data source reference
- referenced sources must be `available` or `usable_with_caveats`
- plan `data_audit_refs` must match `status.json` `data_audit_refs` when a task
  directory is provided
- at least one approved simple baseline family
- non-empty time split and spatial or blocked validation
- segment-level error analysis
- missingness and join-quality checks
- leakage checklist answers with no `fail` values
- primary metric, success criteria, and failure criteria
- output directory and run manifest path
- bounded claim limits
- plan budget no larger than the task status budget
- `status.json` records `framework_versions.experimentation =
  "experimentation_v1.0"`

Warnings do not block acceptance, but reviewers must address them. Warnings
include `caveat` or `not_applicable` leakage checklist values, public-claim
intent, and low score summaries.

## Approved Baseline Families

At least one baseline must use one of these families:

- `naive_local_median`
- `prior_period_value`
- `geography_time_fixed_effects`
- `hedonic_regression_core_fields`
- `regularized_regression_benchmark`

Other baselines are allowed, but they cannot be the only baseline.

## Review Integration

Experiment plans require Tier 2 review by default:

- primary reviewer checks usefulness, completeness, cost realism, and
  task-contract fit
- methodology reviewer checks validation design, leakage controls, baselines,
  robustness, and claim limits

Reviewers may not accept an experiment plan unless
`validate_experiment_plan.py` passes. If the validator returns warnings, the
review may still accept with caveats only when the caveats are explicitly
recorded in the review.

## Run-Analysis Dependency

A `run_analysis` task may be created only after:

1. the experiment plan passes `validate_experiment_plan.py`
2. Tier 2 aggregation accepts the plan
3. the accepted experiment plan is indexed or otherwise referenced by the
   `run_analysis` task
4. the `run_analysis` task budget is no larger than the accepted plan budget

The result reviewer later compares analysis outputs against the approved plan,
not against a revised story written after seeing results.

## Functional Requirements

### EXF-FR1: Required Experiment Plan Fields

Every experiment plan shall include:

- hypothesis ID
- research question
- decision use case
- target outcome
- population and geography
- time period
- dataset versions
- inclusion and exclusion rules
- feature set
- baselines
- candidate methods
- validation design
- metrics
- leakage checks
- robustness checks
- success criteria
- failure criteria
- compute/API budget
- claim limits

### EXF-FR2: Baseline Requirements

Every experiment shall include at least one simple baseline.

For real-estate price research, approved baseline families include:

- naive local median
- prior-period value
- geography and time fixed effects
- hedonic regression with core property fields
- regularized regression benchmark

Complex models cannot be accepted unless they beat relevant simple baselines out of sample or deliver clearly better interpretability/decision value.

### EXF-FR3: Validation Requirements

Real-estate experiments shall define:

- time-based split
- spatial holdout or blocked validation
- segment-level error analysis
- missingness and join-quality checks
- leakage review

Optional, when relevant:

- rolling-origin backtest
- property-type holdout
- price-band holdout
- region-level robustness
- uncertainty calibration

### EXF-FR4: Leakage Checklist

Every experiment plan shall answer:

- were all features available before the prediction or sale date?
- are target-derived aggregates computed only from training data?
- are geography-level summaries time-safe?
- are publication lags modeled where relevant?
- are joins using point-in-time or latest geography?
- are duplicate or repeat transactions handled correctly?

### EXF-FR5: Data Readiness Dependency

No experiment plan may be approved unless required datasets have data-readiness notes.

Experiment plans must reference audited `DS-0000` entries from
`research_ops/data_source_audit.md`. Referenced sources must be `available` or
`usable_with_caveats`.

If readiness is incomplete, missing, blocked, restricted, or deprecated, route
to `data_readiness` before approving the experiment plan.

### EXF-FR6: Budget And Stop Conditions

Every plan shall define:

- maximum runtime
- maximum API spend
- maximum warehouse/compute spend
- max retries
- stop-on-failure conditions
- output directory
- run manifest path

### EXF-FR7: Pre-Registered Claim Limits

Each experiment shall state the strongest claim it could support if successful.

Example:

```text
This experiment can support a suggestive predictive improvement claim.
It cannot support a causal claim without additional identification tests.
```

## Scoring Dimensions

Score each experiment plan from 1 to 5 on:

- question clarity
- data readiness
- baseline strength
- validation design
- leakage control
- robustness design
- cost realism
- decision usefulness
- reproducibility
- claim discipline

## Hard Gates

An experiment plan shall not be approved if:

- no baseline exists
- no validation split exists
- no leakage checklist exists
- data readiness is missing
- data audit references are missing or not experiment-ready
- success metric is undefined
- output path and run manifest are undefined
- claim type is not bounded
- cost exceeds budget without human approval

## Non-Functional Requirements

### EXF-NFR1: Reproducibility

Every approved experiment must be runnable from saved config and code.

### EXF-NFR2: Modularity

Experiment plans should be small enough to execute in one bounded worker task or explicitly split into subtasks.

### EXF-NFR3: Reviewability

Plans should be understandable without reading all source code.

## Acceptance Criteria

The experimentation framework is ready when:

- experiment plans use a standard template
- baselines and leakage checks are mandatory
- data readiness is a dependency
- reviewer prompts score the plan against this framework
- no experiment can run directly from idea discovery
- result review can compare outputs against the approved plan
- `validate_experiment_plan.py` passes valid plans and fails malformed or weak
  plans
- the durable acceptance suite covers the validator and its hard gates

## Failure Modes

Watch for:

- baseline too weak
- random split used where time or space split is needed
- target leakage through future aggregates
- causal language in predictive experiments
- underbudgeted compute or warehouse scans
- plan rewritten after seeing results
