# TASK-0003: Plan Repeat-Sales Volatility Experiment

## Objective

After data readiness is accepted, produce a bounded experiment plan for testing
whether mortgage-rate shocks are followed by measurable changes in repeat-sales
price volatility.

## Scope

- Do not run this task while `status.json` is `inbox`.
- Promote only after `DS-0001` and `DS-0002` are available or usable with
  caveats in `data_source_audit.md`.
- Work only inside this task folder unless the planner updates status through
  validated transitions.
- Do not run analysis or write code beyond pseudocode.

## Required Output

Write `worker_output.md` with:

- a fenced JSON plan block conforming to `experiment_plan.schema.json`
- research question
- data sources and exact `DS-*` references
- unit of analysis
- candidate identification strategy
- baseline model
- leakage and confounding risks
- kill criteria
- robustness checks
- expected result format
- claim-strength limits

Before marking this task ready for review, run:

```bash
python3 async_research_workflow/examples/scripts/validate_experiment_plan.py \
  research_ops/tasks/TASK-0003-repeat-sales-experiment-plan/worker_output.md \
  --ops-dir research_ops \
  --task-dir research_ops/tasks/TASK-0003-repeat-sales-experiment-plan
```

## Acceptance Criteria

- The plan cites `DS-0001` and `DS-0002`.
- The plan passes `validate_experiment_plan.py`.
- Claims are limited to planned methodology, not findings.
- Review tier is Tier 2 with primary and methodology reviewers.

## Review Policy

Tier 2 panel review is required. Primary and methodology reviewers must write
isolated reviews before aggregation.

## Context

- `research_ops/data_source_audit.md`
- `research_ops/accepted_outputs_index.md`
- `async_research_workflow/framework_requirements/experimentation_framework_requirements.md`
- `async_research_workflow/examples/experiment_plan.schema.json`
- `async_research_workflow/examples/experiment_plan_template.md`
- `async_research_workflow/examples/scripts/validate_experiment_plan.py`
- `async_research_workflow/data_source_audit_register_protocol.md`

## Data Source Audit

Required audited sources:

- `DS-0001`
- `DS-0002`

## Cross-Task Anti-Context

Do not promote this task because it sounds valuable. Promote it only after the
data source gate is satisfied by `TASK-0001` or a later accepted readiness task.
