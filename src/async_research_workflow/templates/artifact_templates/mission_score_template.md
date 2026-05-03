# Mission Score Template

Use this score object inside an idea candidate before running
`score_idea_candidate.py`. The scorer validates the mission policy, computes
derived fields, applies hard gates, and writes the full score object back into
the candidate.

```json
{
  "schema_version": "1.0",
  "id": "IDEA-0001",
  "title": "Repeat-sales volatility after rate shocks",
  "question": "Can repeat-sales volatility reveal rate-shock sensitivity?",
  "why_it_might_matter": "It could prioritize a bounded analysis task.",
  "required_data": [
    "DS-0001",
    "DS-0002"
  ],
  "minimum_viable_test": "Create a hypothesis card and data-readiness probe.",
  "baseline": "Prior-period local volatility.",
  "main_risks": [
    "address matching",
    "rate timing"
  ],
  "kill_reason": "Reject if repeat-sales matching quality is too weak.",
  "recommended_next_task": "hypothesis_card",
  "score": {
    "decision_impact": 5,
    "data_availability": 5,
    "killability": 5,
    "feasibility": 4,
    "reuse_potential": 4,
    "novelty": 3,
    "robustness_risk": 1,
    "cost": 1
  }
}
```

After scoring, `score` must include:

```json
{
  "mission_policy_version": "real_estate_research_v1.0",
  "budget_mode": "normal",
  "weighted_total": 18.5,
  "promotion_threshold": 14.0,
  "minimum_killability": 3,
  "max_promotions_per_week": 3,
  "budget_pressure_threshold": 0.8,
  "budget_mode_reason": "auto_budget_available",
  "budget_usage": {
    "monthly_usage_ratio": 0.0,
    "weekly_usage_ratio": 0.0,
    "monthly_cost_usd": 0.0,
    "weekly_cost_usd": 0.0,
    "monthly_budget_usd": null,
    "weekly_budget_usd": null
  },
  "hard_gate_results": [
    {
      "gate": "research_question_present",
      "passed": true,
      "reason": "question is present"
    }
  ],
  "score_explanation": "Mission policy real_estate_research_v1.0 in normal mode gives weighted_total=18.50; route=promote because mission-weighted score and hard gates allow it."
}
```
