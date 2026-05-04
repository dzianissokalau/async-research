# Health Monitor Protocol

Created: 2026-05-02

This document implements the P1 health monitor requirement from the feedback hardening plan.

## Purpose

Surface operational problems without relying on daily human babysitting.

The health monitor is independent of worker, reviewer, discovery, and synthesis jobs. It should run daily and report conditions that need human or scheduler attention.

## Required Helper

Use:

```text
async_research_workflow/scripts/health_check.py
```

Run against the operational folder:

```bash
async-research health research_ops
```

The helper writes:

```text
research_ops/health_report.json
research_ops/daily_status.md
```

It appends a compact human-readable entry to `daily_status.md` and writes a machine-readable JSON report to `health_report.json`.

## Inputs

The health monitor reads:

- `research_ops/queue.md`
- `research_ops/discovery_inbox.md`
- `research_ops/cost_ledger.csv`
- `research_ops/tasks/*/status.json`
- `research_ops/tasks/*/LOCK/`

It does not mutate task status. Recovery, lock cleanup, queue triage, and budget decisions are handled by other jobs or by the human.

## Checks

The daily check reports:

- stale task locks
- queue depth
- too many `needs_human` tasks
- too many `in_progress` tasks
- revision limit breaches
- discovery inbox overload
- weekly or monthly budget threshold
- malformed or schema-invalid `status.json` files
- tasks stuck in the same nonterminal status too long

## Budget Ledger

`cost_ledger.csv` should include one cost amount column:

```text
amount_usd
cost_usd
usd
total_usd
api_usd
compute_usd
```

It should include one date column when possible:

```text
date
created_at
timestamp
period_start
```

Rows created by `cost_tracking.py ingest-usage` also include actual usage fields:

```text
input_tokens
output_tokens
total_tokens
actual
```

The health report aggregates these into `checks.cost.input_tokens`,
`checks.cost.output_tokens`, `checks.cost.total_tokens`, and
`checks.cost.actual_usage_rows`.

Budgets can be passed as flags:

```bash
python -m async_research_workflow.scripts.health_check research_ops \
  --monthly-budget-usd 100 \
  --weekly-budget-usd 25
```

Or supplied in ledger columns:

```text
monthly_budget_usd
weekly_budget_usd
```

The default warning threshold is 80 percent.

## Alert Shape

`health_report.json` contains:

```json
{
  "schema_version": "1.0",
  "generated_at": "2026-05-02T10:00:00Z",
  "summary": {
    "task_count": 12,
    "alert_count": 2,
    "highest_severity": "warning"
  },
  "alerts": [
    {
      "severity": "warning",
      "check": "stale_locks",
      "message": "1 stale lock(s) detected"
    }
  ],
  "checks": {
    "status_counts": {},
    "queue_depth": 0,
    "discovery_inbox_count": 0,
    "stale_locks": [],
    "revision_limit_breaches": [],
    "malformed_status_files": [],
    "schema_version_warnings": {},
    "stuck_tasks": [],
    "cost": {}
  }
}
```

`schema_version_warnings` is populated by `check_schema_versions.py`. The alert name is retained for compatibility, but missing or mismatched versions are hard validation failures and must be repaired before scheduled agents continue.

## Default Thresholds

| Check | Default threshold |
| --- | ---: |
| stale lock age | 60 minutes |
| queue depth | 20 items |
| `needs_human` tasks | more than 3 |
| `in_progress` tasks | more than 3 |
| discovery inbox | 20 items |
| budget warning | 80 percent |
| stuck nonterminal task | 7 days |
| stuck `in_progress` task | 24 hours |

## Acceptance Tests

The health monitor is considered implemented when:

- a stale lock appears in `health_report.json`
- budget warning triggers at 80 percent
- more than 3 `needs_human` tasks triggers an alert
- malformed `status.json` appears in `health_report.json`
- `daily_status.md` receives a health-check entry
