# Experiment Plan Template

Use this template for `experiment_plan` worker outputs. The fenced JSON block is
the executable contract validated by `validate_experiment_plan.py`; prose may be
added above or below it, but reviewers should rely on the JSON block for hard
gates.

```json
{
  "schema_version": "1.0",
  "experiment_id": "EXP-0001",
  "task_id": "TASK-0000",
  "framework_version": "experimentation_v1.0",
  "hypothesis_id": "HYP-0001",
  "research_question": "What bounded question will this experiment answer?",
  "decision_use_case": "What decision becomes easier if the experiment works?",
  "target_outcome": "Define the outcome variable and timing.",
  "population": "Define eligible records.",
  "geography": "Define geography.",
  "time_period": {
    "start": "YYYY-MM",
    "end": "YYYY-MM",
    "exclusion_lag": "Exclude or lag incomplete recent periods."
  },
  "data_audit_refs": [
    "DS-0001"
  ],
  "dataset_versions": [
    {
      "source_id": "DS-0001",
      "version": "Exact source release, table, or file version.",
      "accessed_at": "YYYY-MM-DD",
      "role": "outcome"
    }
  ],
  "inclusion_rules": [
    "Rule for records included in the experiment."
  ],
  "exclusion_rules": [
    "Rule for records excluded before analysis."
  ],
  "feature_set": [
    {
      "name": "feature_name",
      "source_id": "DS-0001",
      "available_at": "Before prediction or event date.",
      "leakage_risk": "low"
    }
  ],
  "baselines": [
    {
      "name": "Local median baseline",
      "family": "naive_local_median",
      "implementation": "Describe exact implementation.",
      "comparison_role": "Must be beaten out of sample."
    }
  ],
  "candidate_methods": [
    {
      "name": "Candidate method",
      "method_class": "regression_or_matching_or_tree_or_other",
      "why_candidate": "Why this method is appropriate."
    }
  ],
  "validation_design": {
    "time_split": "Train/validation/test split with dates.",
    "spatial_holdout_or_blocked_validation": "Geographic or blocked validation design.",
    "segment_level_error_analysis": [
      "Property type",
      "Region"
    ],
    "missingness_and_join_quality_checks": [
      "Measure missingness and join failure rates."
    ],
    "leakage_review": "How leakage will be checked before running."
  },
  "metrics": {
    "primary_metric": "Primary metric and direction.",
    "secondary_metrics": [
      "Secondary metric"
    ],
    "minimum_detectable_improvement": "Smallest improvement worth caring about."
  },
  "leakage_checklist": {
    "feature_availability_before_prediction_date": "pass",
    "target_aggregates_train_only": "pass",
    "geography_summaries_time_safe": "pass",
    "publication_lags_modeled": "pass",
    "joins_point_in_time_or_versioned": "pass",
    "duplicate_or_repeat_transactions_handled": "pass"
  },
  "robustness_checks": [
    "Robustness check."
  ],
  "success_criteria": [
    "Criterion required to continue."
  ],
  "failure_criteria": [
    "Criterion that kills or revises the idea."
  ],
  "budget": {
    "max_runtime_minutes": 60,
    "max_api_usd": 1.0,
    "max_compute_usd": 0.0,
    "max_retries": 1
  },
  "stop_conditions": {
    "stop_on_failure": "Stop on schema, source, join, or metric failure.",
    "stop_on_budget_exceeded": "Stop before exceeding declared budget.",
    "stop_on_data_quality_failure": "Stop if minimum quality criteria fail.",
    "kill_criteria": [
      "Kill if baseline cannot be beaten out of sample."
    ]
  },
  "outputs": {
    "output_dir": "research_ops/tasks/TASK-0000/artifacts/experiment_run/",
    "run_manifest_path": "research_ops/tasks/TASK-0000/artifacts/experiment_run/run_manifest.json",
    "artifact_paths": [
      "metrics.json",
      "diagnostics.md"
    ]
  },
  "claim_limits": {
    "strongest_supported_claim": "predictive_improvement",
    "causal_claim_allowed": false,
    "public_claim_allowed": false,
    "claim_limit_text": "This plan can support only the stated bounded claim."
  },
  "scores": {
    "question_clarity": 3,
    "data_readiness": 3,
    "baseline_strength": 3,
    "validation_design": 3,
    "leakage_control": 3,
    "robustness_design": 3,
    "cost_realism": 3,
    "decision_usefulness": 3,
    "reproducibility": 3,
    "claim_disciplined": 3
  }
}
```
