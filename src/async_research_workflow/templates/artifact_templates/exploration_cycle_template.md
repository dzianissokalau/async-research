# Exploration Cycle Template

Use this template for `idea_discovery` worker outputs and discovery-scout
cycle reports. The fenced JSON block is the executable contract validated by
`validate_exploration_cycle.py`.

```json
{
  "schema_version": "1.0",
  "exploration_id": "EXPL-0001",
  "task_id": "TASK-0000",
  "framework_version": "exploration_v1.0",
  "cycle_type": "weekly",
  "mission_scope": "Low-cost real-estate market research with auditable public or internal data.",
  "source_register_path": "research_ops/discovery/source_register.md",
  "exploration_budget": {
    "max_sources_scanned": 10,
    "max_raw_candidates": 20,
    "max_kept_candidates": 10,
    "max_discovery_inbox_additions": 5,
    "max_promotions_to_tasks": 3,
    "max_api_usd": 1.0,
    "max_compute_usd": 0.0,
    "max_human_decisions": 1
  },
  "search_modes": [
    "internal_mining",
    "source_register_scanning",
    "dataset_gap_generation"
  ],
  "category_targets": {
    "exploit": 0.7,
    "adjacent": 0.2,
    "speculative": 0.1
  },
  "sources_scanned": [
    "SRC-0001"
  ],
  "raw_candidate_count": 3,
  "kept_candidates": 1,
  "discovery_inbox_additions": 1,
  "promotions_to_tasks": 0,
  "candidates": [
    {
      "id": "IDEA-0001",
      "title": "Candidate title",
      "category": "exploit",
      "source_refs": [
        "SRC-0001"
      ],
      "trigger": "Accepted-output gap or source-register observation.",
      "status": "candidate",
      "idea_score": 14.0,
      "diversity_bonus": 0.5,
      "duplicate_penalty": 0.0,
      "drift_penalty": 0.0,
      "candidate_rank": 14.5,
      "recommended_next_task": "hypothesis_card",
      "duplicate_status": "new",
      "revisit_condition": "none"
    }
  ],
  "stop_rules_triggered": [
    "candidate_limit"
  ],
  "duplicate_summary": {
    "checked_against_accepted_outputs": true,
    "near_duplicate_count": 0,
    "duplicate_count": 0
  },
  "parking_summary": {
    "parked_count": 0,
    "rejected_count": 2,
    "parked_written_to_log": true
  },
  "health_summary": {
    "category_distribution": {
      "exploit": 1,
      "adjacent": 0,
      "speculative": 0
    },
    "limits_respected": true,
    "human_decisions_requested": 0
  }
}
```
