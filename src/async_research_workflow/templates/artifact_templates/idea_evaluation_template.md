# Idea Evaluation Template

Use this template after `score_idea_candidate.py` has scored a candidate. The
validator can derive most fields directly from the candidate JSON, but this
template documents the durable evaluation object written into
`candidate.idea_evaluation`.

```json
{
  "schema_version": "1.0",
  "framework_version": "idea_evaluation_v1.0",
  "candidate_id": "IDEA-0001",
  "evaluated_at": "YYYY-MM-DDTHH:MM:SSZ",
  "route": "promote_to_hypothesis_card",
  "recommended_next_task": "hypothesis_card",
  "mission_policy_version": "real_estate_research_v1.0",
  "scorecard": {
    "decision_impact": 4,
    "novelty": 3,
    "data_availability": 4,
    "feasibility": 4,
    "killability": 4,
    "robustness_risk": 2,
    "cost": 1,
    "reuse_potential": 4,
    "weighted_total": 17.0,
    "promotion_threshold": 14.0,
    "minimum_killability": 3
  },
  "hard_gate_results": [
    {
      "gate": "research_question_present",
      "passed": true,
      "reason": "question is present"
    }
  ],
  "dedupe": {
    "duplicate_status": "new",
    "checked_against": [
      "accepted_outputs_index",
      "discovery_inbox",
      "queue",
      "rejected_ideas"
    ],
    "cluster_id": "cluster-repeat-sales-volatility",
    "representative": true
  },
  "rejection_logging": {
    "required": false,
    "log_path": "research_ops/discovery/rejected_ideas.md",
    "logged": false,
    "rejection_kind": "none",
    "revisit_condition": "none"
  },
  "promotion_readiness": {
    "planner_may_promote": true,
    "promotion_reason": "mission score and hard gates allow a hypothesis-card task",
    "blocked_reasons": []
  },
  "review_notes": [
    "No direct experiment promotion."
  ]
}
```
