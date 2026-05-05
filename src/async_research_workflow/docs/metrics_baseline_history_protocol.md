# Metrics Baseline And History Protocol

Created: 2026-05-02

This document implements P2-4 metrics baseline and history for the async research workflow.

## Purpose

The async workflow should improve over time. To know whether it is improving, it needs a baseline and append-only metric snapshots that can be compared during weekly and monthly calibration.

## Required Files

```text
research_ops/metrics_baseline.json
research_ops/metrics_history.jsonl
```

`metrics_baseline.json` stores the initial reference point.

`metrics_history.jsonl` stores one JSON object per snapshot. Do not rewrite old lines; append a new snapshot instead.

## Required Helper

Use:

```text
async_research_workflow/scripts/metrics_history.py
```

Initialize the baseline:

```bash
python -m async_research_workflow.scripts.metrics_history init \
  research_ops \
  --label initial_baseline
```

Append the weekly digest snapshot:

```bash
python -m async_research_workflow.scripts.metrics_history append-snapshot \
  research_ops \
  --period weekly \
  --label weekly_digest
```

Summarize monthly trends:

```bash
async-research metrics summarize \
  research_ops \
  --month 2026-05 \
  --output research_ops/monthly_metrics_trends.md
```

## Metrics

The helper records:

| Metric | Source |
| --- | --- |
| `tasks_created` | `research_ops/tasks/*/status.json` |
| `tasks_accepted` | task status count |
| `tasks_rejected` | task status count |
| `ideas_generated` | discovery inbox, rejected ideas, and `discovery/IDEA-*.json` |
| `ideas_promoted` | promoted discovery rows and promoted idea JSON |
| `ideas_rejected` | rejected discovery rows and rejected idea JSON |
| `human_minutes` | explicit flag, cost ledger minutes, or estimated decision count |
| `estimated_cost_usd` | `research_ops/cost_ledger.csv` amount columns |
| `panel_reviews` | review panel aggregates or panel-required task statuses |
| `revision_loops` | sum of `revision_count` across task statuses |

`human_minutes` is an estimate unless supplied explicitly:

```bash
python -m async_research_workflow.scripts.metrics_history append-snapshot \
  research_ops \
  --period weekly \
  --label weekly_digest \
  --human-minutes 25
```

If `--human-minutes` is omitted, the helper first looks for human-minute columns in `cost_ledger.csv`. If none exist, it estimates five minutes per row in `decisions.md`.

## Snapshot Shape

Each JSONL line contains:

```json
{
  "schema_version": "1.0",
  "generated_at": "2026-05-02T10:00:00Z",
  "period": "weekly",
  "label": "weekly_digest",
  "metrics": {
    "tasks_created": 12,
    "tasks_accepted": 4,
    "tasks_rejected": 2,
    "ideas_generated": 20,
    "ideas_promoted": 5,
    "ideas_rejected": 10,
    "human_minutes": 30,
    "estimated_cost_usd": 12.5,
    "panel_reviews": 3,
    "revision_loops": 2
  }
}
```

## Acceptance Checks

P2-4 is implemented when:

- the weekly digest cadence appends exactly one metrics snapshot
- baseline creation is deterministic and does not overwrite history
- monthly calibration can summarize trends from `metrics_history.jsonl`
- metrics include task, idea, human-time, cost, panel-review, and revision-loop counts
