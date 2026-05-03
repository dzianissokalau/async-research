# Mission-Weighted Idea Scoring Protocol

Created: 2026-05-02

This document implements the P1 mission-weighted idea scoring requirement from the feedback hardening plan.

## Purpose

Make idea scoring reflect the mission policy instead of rewarding novelty too heavily.

The system should prefer ideas that are decision-relevant, data-backed, feasible, reusable, and cheap to kill. Novelty helps, but it cannot compensate for weak data, severe robustness risk, or no kill path.

## Required Policy

Use:

```text
async_research_workflow/examples/mission_policy.json
```

Initial version:

```text
real_estate_research_v1.0
```

The policy defines stable weights, hard gates, promotion thresholds, and budget-mode thresholds. Agents may propose policy changes, but they must not silently change these values.

Validate the policy before scheduled scoring:

```bash
python3 async_research_workflow/examples/scripts/validate_mission_policy.py \
  async_research_workflow/examples/mission_policy.json
```

`score_idea_candidate.py` also validates the policy contract at runtime and
fails closed if the policy is malformed, misaligned, or missing required gates.

## Required Helper

Use:

```text
async_research_workflow/examples/scripts/score_idea_candidate.py
```

Example:

```bash
python3 async_research_workflow/examples/scripts/score_idea_candidate.py \
  research_ops/discovery/IDEA-0007.json
```

For automatic budget mode:

```bash
python3 async_research_workflow/examples/scripts/score_idea_candidate.py \
  research_ops/discovery/IDEA-0007.json \
  --budget-mode auto \
  --ops-dir research_ops
```

The helper reads `cost_ledger.csv` and switches to `budget_constrained` when
weekly or monthly spend reaches the configured budget pressure threshold.

For manual constrained budget mode:

```bash
python3 async_research_workflow/examples/scripts/score_idea_candidate.py \
  research_ops/discovery/IDEA-0007.json \
  --budget-mode budget_constrained
```

The helper:

- validates the mission policy against `mission_policy.schema.json`
- loads the candidate JSON
- loads the mission policy
- applies the mission-weighted score
- applies hard gates before promotion
- writes the mission policy version into the score
- raises the killability threshold in budget-constrained mode
- validates the scored candidate against `idea_candidate.schema.json`
- records `max_promotions_per_week` so the planner can reduce promotions when budget is tight

## Formula

```text
score =
  2.0 * decision_impact
+ 1.5 * data_availability
+ 1.5 * killability
+ 1.0 * feasibility
+ 1.0 * reuse_potential
+ 0.5 * novelty
- 2.0 * robustness_risk
- 1.0 * cost
```

Interpretation:

- `decision_impact`, `data_availability`, `killability`, `feasibility`, `reuse_potential`, and `novelty` are positive dimensions.
- `robustness_risk` and `cost` are penalty dimensions where higher values are worse.
- `novelty` has the smallest positive weight, by design.

## Hard Gates

Hard gates override the composite score.

An idea cannot promote if it lacks:

- a research question
- an identifiable data path
- a minimum viable test
- a baseline or comparison
- a kill reason

The helper parks ideas that fail only the killability threshold, because a stronger cheap rejection path may make them viable later.

Direct discovery promotion to `experiment_plan` is blocked. The helper reroutes
otherwise-promotable experiment ideas to `data_readiness` and records the
`direct_experiment_blocked` gate as passed only after the route is safe.

## Budget Modes

| Mode | Promotion threshold | Park threshold | Minimum killability |
| --- | ---: | ---: | ---: |
| `normal` | 14.0 | 9.0 | 3 |
| `budget_constrained` | 16.0 | 11.0 | 5 |

Budget-constrained mode is intentionally stricter: when money or review capacity is tight, the system should only advance ideas that can be killed very cheaply.

Budget-constrained mode also lowers `max_promotions_per_week` from 3 to 1.

## Score Output

The candidate JSON itself is written with top-level `"schema_version": "1.0"`.

The helper writes these fields under `score`:

```json
{
  "mission_policy_version": "real_estate_research_v1.0",
  "budget_mode": "normal",
  "decision_impact": 4,
  "data_availability": 3,
  "killability": 4,
  "feasibility": 3,
  "reuse_potential": 4,
  "novelty": 4,
  "robustness_risk": 3,
  "cost": 2,
  "weighted_total": 19.5,
  "promotion_threshold": 14.0,
  "minimum_killability": 3,
  "max_promotions_per_week": 3,
  "budget_mode_reason": "auto_budget_available",
  "hard_gate_results": [],
  "score_explanation": "..."
}
```

## Acceptance Tests

The scoring layer is considered implemented when:

- every scored candidate records top-level `schema_version = "1.0"` and `score.mission_policy_version`
- high novelty cannot dominate weak data and high robustness risk
- budget-constrained mode raises `minimum_killability`
- automatic budget mode switches scoring policy when budget usage crosses the pressure threshold
- scored candidates expose `max_promotions_per_week`
- scored candidates validate against `idea_candidate.schema.json`
- the active mission policy validates against `mission_policy.schema.json`
- scoring refuses an invalid mission policy
- direct experiment promotion is blocked or rerouted before execution
