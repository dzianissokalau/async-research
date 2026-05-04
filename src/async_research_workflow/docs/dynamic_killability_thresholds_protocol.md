# Dynamic Killability Thresholds Protocol

Created: 2026-05-02

This document implements P3-3 dynamic killability thresholds for the async
research workflow.

## Purpose

When the workflow is near its weekly or monthly budget, discovery should become
more selective. The system should not keep promoting merely interesting ideas
when only highly killable, cheap-to-reject ideas deserve the next execution slot.

## Policy Source

`async_research_workflow/mission_policy.json` defines:

```json
{
  "promotion": {
    "normal": {
      "promotion_threshold": 14.0,
      "park_threshold": 9.0,
      "minimum_killability": 3,
      "max_promotions_per_week": 3
    },
    "budget_constrained": {
      "promotion_threshold": 16.0,
      "park_threshold": 11.0,
      "minimum_killability": 5,
      "max_promotions_per_week": 1
    }
  },
  "budget_pressure": {
    "threshold": 0.8,
    "default_mode": "normal",
    "constrained_mode": "budget_constrained"
  }
}
```

## Required Helper Behavior

Use automatic budget mode when scoring discovery candidates:

```bash
async-research idea score \
  research_ops/discovery/IDEA-0007.json \
  --budget-mode auto \
  --ops-dir research_ops
```

The helper reads `research_ops/cost_ledger.csv` through the programmatic cost
tracking rules. If weekly or monthly usage is at or above the pressure threshold,
it applies the `budget_constrained` promotion policy.

Scored candidates record:

```json
{
  "score": {
    "budget_mode": "budget_constrained",
    "budget_mode_reason": "auto_budget_threshold_exceeded",
    "minimum_killability": 5,
    "max_promotions_per_week": 1,
    "budget_pressure_threshold": 0.8,
    "budget_usage": {
      "monthly_usage_ratio": 0.82
    }
  }
}
```

## Planner Rule

The planner must respect `score.max_promotions_per_week`. If any top candidate
is in `budget_constrained` mode, the planner should promote at most the lowest
`max_promotions_per_week` among promoted candidates, usually one per week.

When discovery scoring enters `budget_constrained` mode, append a compact note
to `research_ops/daily_status.md` with the budget mode reason and promotion cap.
This keeps the human loop informed without requiring immediate intervention.

Candidates that would have promoted in normal mode but fail the constrained
`minimum_killability` gate should be parked, not rejected. A stronger cheap kill
path can make them viable later.

## Acceptance Checks

P3-3 is implemented when:

- automatic scoring selects `normal` mode below the budget threshold
- automatic scoring selects `budget_constrained` mode at or above the threshold
- budget-constrained mode raises `minimum_killability` to 5
- candidates with killability below the constrained threshold park instead of promote
- scored candidates expose `max_promotions_per_week` for the planner
- constrained discovery runs are noted in `daily_status.md`
