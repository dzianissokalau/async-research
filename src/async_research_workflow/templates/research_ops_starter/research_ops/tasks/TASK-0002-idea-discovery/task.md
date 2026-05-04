# TASK-0002: Generate First Real-Estate Research Candidates

## Objective

Generate a small set of high-quality real-estate market research candidates
that can be advanced by the async workflow without constant human steering.

## Scope

- Read `accepted_outputs_index.md` before proposing ideas.
- Read `discovery/source_register.md` and use only registered source refs in the
  exploration cycle.
- Read `data_source_audit.md` and avoid ideas that require unavailable data.
- Prefer ideas that are high quality, independent, low cost, and killable.
- Do not create experiment plans directly.

## Required Output

Write `worker_output.md` with:

- a fenced JSON exploration cycle block conforming to `exploration_cycle.schema.json`
- 5 to 8 candidate ideas
- a mission-weighted score explanation for each candidate
- an `idea_evaluation` record for every candidate added to
  `discovery_inbox.md`
- exploration category, registered source refs, duplicate status, candidate
  rank, and revisit condition for each candidate
- data dependencies and current audit status
- minimum viable next task for each candidate
- rejection notes for ideas that are attractive but not killable or too costly

Before updating `discovery_inbox.md` or marking the task ready for review, run:

```bash
async-research exploration validate \
  research_ops/tasks/TASK-0002-idea-discovery/worker_output.md \
  --ops-dir research_ops \
  --task-dir research_ops/tasks/TASK-0002-idea-discovery
```

For every candidate JSON that may be promoted or added to the discovery inbox,
run:

```bash
python -m async_research_workflow.scripts.validate_mission_policy \
  async_research_workflow/mission_policy.json

async-research idea score \
  research_ops/discovery/IDEA-0001.json \
  --budget-mode auto \
  --ops-dir research_ops

async-research idea validate \
  research_ops/discovery/IDEA-0001.json \
  --ops-dir research_ops
```

If a candidate is strong enough to promote, append a row to
`research_ops/discovery_inbox.md` and recommend a bounded next task.

## Acceptance Criteria

- Each candidate has decision impact, data availability, killability,
  feasibility, reuse potential, novelty, robustness risk, and cost rationale.
- The exploration cycle passes `validate_exploration_cycle.py`.
- The active mission policy passes `validate_mission_policy.py`.
- Every promoted or inbox-added candidate passes `validate_idea_evaluation.py`.
- Novelty does not dominate weak data or weak killability.
- Candidates that need unaudited data route to `data_readiness` first.
- The output avoids duplicating accepted work.

## Review Policy

Tier 1 primary review. Escalate to Tier 2 if the worker recommends direct
experiment planning for a candidate with unresolved data or methodology risk.

## Context

- `research_ops/accepted_outputs_index.md`
- `research_ops/discovery/source_register.md`
- `research_ops/discovery/rejected_ideas.md`
- `research_ops/data_source_audit.md`
- `research_ops/discovery_inbox.md`
- `async_research_workflow/framework_requirements/mission_scoring_framework_requirements.md`
- `async_research_workflow/framework_requirements/exploration_framework_requirements.md`
- `async_research_workflow/framework_requirements/idea_evaluation_framework_requirements.md`
- `async_research_workflow/exploration_cycle.schema.json`
- `async_research_workflow/templates/artifact_templates/exploration_cycle_template.md`
- `async_research_workflow/scripts/validate_exploration_cycle.py`
- `async_research_workflow/idea_evaluation.schema.json`
- `async_research_workflow/templates/artifact_templates/idea_evaluation_template.md`
- `async_research_workflow/scripts/validate_idea_evaluation.py`
- `async_research_workflow/mission_weighted_idea_scoring_protocol.md`
- `async_research_workflow/mission_policy.json`
- `async_research_workflow/mission_policy.schema.json`
- `async_research_workflow/templates/artifact_templates/mission_score_template.md`
- `async_research_workflow/scripts/validate_mission_policy.py`
- `async_research_workflow/scripts/score_idea_candidate.py`
- `async_research_workflow/scripts/cost_tracking.py`
- `async_research_workflow/scripts/validate_json_artifact.py`
- `async_research_workflow/idea_discovery_workflow.md`

## Data Source Audit

Use current `DS-*` statuses as constraints. Candidate ideas may cite data
source IDs, but unaudited sources must not be treated as ready.

## Cross-Task Anti-Context

`TASK-0001` must be completed or explicitly accepted before this task treats DS-* sources as ready for downstream planning. Until then, use `data_source_audit.md` as a candidate source list and route uncertain ideas to data_readiness first.
