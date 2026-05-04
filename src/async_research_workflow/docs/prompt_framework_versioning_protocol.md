# Prompt And Framework Versioning Protocol

Created: 2026-05-02

This document implements P2-2 prompt and framework versioning for the async research workflow.

## Purpose

Accepted research outputs must be auditable after the fact. A future calibration pass should be able to answer:

- which worker and reviewer prompt versions touched the task
- which scoring, acceptance, and aggregation frameworks were used
- whether output quality changed after a prompt or framework revision

## Required Task Fields

Each new `status.json` should include:

```json
{
  "prompt_versions": {
    "planner": "planner_v1.0",
    "discovery_scout": "discovery_scout_v1.0",
    "worker": "worker_v1.0",
    "primary_reviewer": "primary_reviewer_v1.0",
    "methodology_reviewer": "methodology_reviewer_v1.0",
    "skeptic_reviewer": "skeptic_reviewer_v1.0",
    "review_aggregator": "review_aggregator_v1.0",
    "weekly_synthesizer": "weekly_synthesizer_v1.0",
    "health_monitor": "health_monitor_v1.0"
  },
  "framework_versions": {
    "mission_scoring": "mission_scoring_v1.0",
    "idea_evaluation": "idea_evaluation_v1.0",
    "experimentation": "experimentation_v1.0",
    "exploration": "exploration_v1.0",
    "result_acceptance": "result_acceptance_v1.0",
    "review_aggregation": "review_aggregation_v1.0",
    "accepted_outputs_index": "accepted_outputs_index_v1.0",
    "schema_versioning": "schema_versioning_v1.0",
    "data_source_audit": "data_source_audit_v1.0"
  }
}
```

The schema keeps these fields optional during migration so old task folders stay readable. Helpers that rewrite `status.json` add defaults when the fields are missing.

## Shared Defaults

Workflow helpers use:

```text
async_research_workflow/scripts/version_metadata.py
```

This file is the local source of truth for current prompt and framework version labels. When a prompt or framework changes materially, update this file and add a migration note here.

## Agent Write Rule

Every agent that updates `status.json` must:

1. preserve existing `prompt_versions` and `framework_versions`
2. add its own prompt version if missing
3. preserve framework versions used by prior steps
4. add any framework version it applies during the current step
5. validate `status.json` after the write

Every reviewer must include prompt/framework version metadata in its review JSON block:

```json
{
  "prompt_version": "primary_reviewer_v1.0",
  "framework_versions": {
    "result_acceptance": "result_acceptance_v1.0"
  }
}
```

`aggregate_reviews.py` rejects review files missing this metadata. The task-level `status.json` remains the durable audit record for the full workflow, while review files record the exact reviewer prompt/framework used for that judgement.

## Calibration Report

Run monthly, or before reviewing prompt/framework quality:

```bash
python -m async_research_workflow.scripts.framework_version_calibration \
  research_ops \
  --month 2026-05 \
  --output research_ops/monthly_calibration_framework_versions.md
```

The helper scans accepted task status files and groups accepted outputs by each framework version. Outputs with missing metadata are grouped under `unknown`, which makes migration debt visible without blocking old tasks.

## Acceptance Checks

P2-2 is implemented when:

- an accepted result exposes `prompt_versions` and `framework_versions`
- each review output records `prompt_version` and `framework_versions.result_acceptance`
- accepted outputs can be grouped by framework version for monthly calibration
- status schemas allow the version metadata
- status-writing helpers preserve existing metadata and add defaults when missing

## Migration Notes

### 1.0

Initial prompt/framework version set. Defaults are defined in `version_metadata.py`.
`data_source_audit_v1.0` was added when experiment plans began requiring
explicit `DS-0000` audit references before execution.

For older tasks:

- do not reject a task only because version metadata is missing
- add defaults the next time a helper rewrites `status.json`
- group missing framework metadata as `unknown` in calibration reports

## Future Bumps

For every prompt or framework version bump:

1. Update `version_metadata.py`.
2. Record what changed in this document.
3. Keep old task metadata unchanged for auditability.
4. Use calibration reports to compare accepted outputs before and after the bump.
