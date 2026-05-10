# Framework Requirements

Created: 2026-05-02

This folder defines the formal framework requirements that make the async research workflow more independent, higher quality, and cheaper to operate.

The frameworks are intended to be used as decision gates. They should not become paperwork for its own sake.

## Frameworks

1. [Mission Scoring Framework Requirements](./mission_scoring_framework_requirements.md)
2. [Idea Evaluation Framework Requirements](./idea_evaluation_framework_requirements.md)
3. [Exploration Framework Requirements](./exploration_framework_requirements.md)
4. [Experimentation Framework Requirements](./experimentation_framework_requirements.md)
5. [Result Acceptance Framework Requirements](./result_acceptance_framework_requirements.md)

## Operating Principle

The system should optimize for:

```text
accepted, reproducible, evidence-backed research outputs
per dollar, per human minute, and per data-risk unit
```

The global priority order remains:

```text
quality > independence > low cost > speed
```

## Decision Flow

```text
mission scoring policy
  -> exploration policy
  -> idea evaluation
  -> data readiness
  -> experiment planning
  -> result acceptance
  -> portfolio decision
```

## Scoring Rule

Use this order for every important decision:

```text
1. hard gates
2. weighted score
3. reviewer judgement
4. human approval only for high-stakes or expensive transitions
```

Agents may propose changes to scoring rubrics, but they must not silently change mission weights, hard gates, or acceptance rules.

## Implementation Guidance

Start with Markdown scorecards. Add JSON Schema or Pydantic models only after
the rubrics are stable. The mission scoring, exploration, idea evaluation,
experimentation, and result acceptance frameworks have reached this point:

- `mission_scoring_v1.0` is backed by
  `async_research_workflow/schemas/mission_policy.schema.json`,
  `async_research_workflow/scripts/validate_mission_policy.py`, and
  `async_research_workflow/scripts/score_idea_candidate.py`
- `exploration_v1.0` is backed by
  `async_research_workflow/schemas/exploration_cycle.schema.json` and
  `async_research_workflow/scripts/validate_exploration_cycle.py`
- `idea_evaluation_v1.0` is backed by
  `async_research_workflow/schemas/idea_evaluation.schema.json` and
  `async_research_workflow/scripts/validate_idea_evaluation.py`
- `experimentation_v1.0` is backed by
  `async_research_workflow/schemas/experiment_plan.schema.json` and
  `async_research_workflow/scripts/validate_experiment_plan.py`
- `analysis_run_v1.0` is backed by
  `async_research_workflow/schemas/analysis_run.schema.json` and the packaged
  `async_research_workflow/templates/artifact_templates/analysis_run_manifest_template.md`;
  read-only preflight is implemented in
  `async_research_workflow/scripts/analysis_runs.py`
- `analysis_metrics_v1.0`, `analysis_diagnostics_v1.0`, and
  `analysis_robustness_v1.0` are backed by
  `async_research_workflow/schemas/analysis_metrics.schema.json`,
  `async_research_workflow/schemas/analysis_diagnostics.schema.json`, and
  `async_research_workflow/schemas/analysis_robustness_checks.schema.json`,
  with packaged artifact templates under
  `async_research_workflow/templates/artifact_templates/`
- `analysis_claim_gates_v1.0` is backed by
  `async_research_workflow/schemas/analysis_claim_gates.schema.json`, the
  packaged `async_research_workflow/templates/artifact_templates/analysis_claim_gates_template.md`,
  and reusable claim gate evaluation in
  `async_research_workflow/scripts/analysis_claim_gates.py`
- Completed analysis runs are checked by
  `async_research_workflow/scripts/analysis_validation.py`, exposed through
  `async-research analysis validate-run` and
  `async-research analysis validate-results`
- `result_acceptance_v1.0` is backed by
  `async_research_workflow/schemas/result_acceptance.schema.json` and
  `async_research_workflow/scripts/validate_result_acceptance.py`

Recommended first implementation:

- Add framework references to task templates.
- Add `scorecard` and `hard_gate_results` fields to `status.json`.
- Require reviewer notes to cite the relevant framework.
- Track whether high-scoring ideas actually produce accepted outputs.
- Recalibrate weights monthly, not continuously.

## Required Shared Concepts

All frameworks should use the same 1 to 5 anchored scale:

```text
1 = absent, invalid, or unsafe
2 = weak; major gaps remain
3 = acceptable with explicit caveats
4 = strong and reusable
5 = excellent; should become a reference example
```

All framework decisions should use the same route vocabulary:

```text
accept
accept_with_caveats
needs_revision
needs_human
pause
reject
```

## Hard Gate Philosophy

Hard gates override scores.

Examples:

- no baseline means an experiment plan cannot be approved
- no leakage check means a result cannot be accepted above weak claim strength
- no reproducible run manifest means a result cannot become memo-ready
- public, policy, investment, legal, or valuation claims require human approval

This prevents the system from gaming a composite score.
