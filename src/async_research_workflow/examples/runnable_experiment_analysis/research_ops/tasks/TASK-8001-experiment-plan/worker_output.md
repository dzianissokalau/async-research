Accepted fixture plan.

```json
{
  "baselines": [
    {
      "comparison_role": "baseline",
      "family": "naive_local_median",
      "implementation": "fixture median",
      "name": "local median"
    }
  ],
  "budget": {
    "max_api_usd": 1.0,
    "max_compute_usd": 2.0,
    "max_retries": 0,
    "max_runtime_minutes": 30
  },
  "candidate_methods": [
    {
      "method_class": "regression",
      "name": "fixture regression",
      "why_candidate": "simple fixture"
    }
  ],
  "claim_limits": {
    "causal_claim_allowed": false,
    "claim_limit_text": "bounded fixture claim only",
    "public_claim_allowed": false,
    "strongest_supported_claim": "predictive_improvement"
  },
  "data_audit_refs": [
    "DS-0001"
  ],
  "dataset_versions": [
    {
      "accessed_at": "2026-05-09",
      "role": "outcome",
      "source_id": "DS-0001",
      "version": "fixture"
    }
  ],
  "decision_use_case": "Decide whether to run the fixture experiment.",
  "exclusion_rules": [
    "exclude invalid fixture records"
  ],
  "experiment_id": "EXP-8001",
  "failure_criteria": [
    "fails validation"
  ],
  "feature_set": [
    {
      "available_at": "before target",
      "leakage_risk": "low",
      "name": "fixture_feature",
      "source_id": "DS-0001"
    }
  ],
  "framework_version": "experimentation_v1.0",
  "geography": "Fixture geography.",
  "hypothesis_id": "HYP-8001",
  "inclusion_rules": [
    "include fixture records"
  ],
  "leakage_checklist": {
    "duplicate_or_repeat_transactions_handled": "pass",
    "feature_availability_before_prediction_date": "pass",
    "geography_summaries_time_safe": "pass",
    "joins_point_in_time_or_versioned": "pass",
    "publication_lags_modeled": "pass",
    "target_aggregates_train_only": "pass"
  },
  "metrics": {
    "minimum_detectable_improvement": "1%",
    "primary_metric": "MAE lower is better",
    "secondary_metrics": [
      "RMSE"
    ]
  },
  "outputs": {
    "artifact_paths": [
      "metrics.json"
    ],
    "output_dir": "research_ops/tasks/TASK-8002-run-analysis/artifacts/analysis_run/",
    "run_manifest_path": "research_ops/tasks/TASK-8002-run-analysis/artifacts/analysis_run/run_manifest.json"
  },
  "population": "Fixture records.",
  "research_question": "Can the fixture experiment be planned safely?",
  "robustness_checks": [
    "rerun on fixture segment"
  ],
  "schema_version": "1.0",
  "scores": {
    "baseline_strength": 3,
    "claim_disciplined": 3,
    "cost_realism": 3,
    "data_readiness": 3,
    "decision_usefulness": 3,
    "leakage_control": 3,
    "question_clarity": 3,
    "reproducibility": 3,
    "robustness_design": 3,
    "validation_design": 3
  },
  "stop_conditions": {
    "kill_criteria": [
      "kill if data is unusable"
    ],
    "stop_on_budget_exceeded": "stop before budget",
    "stop_on_data_quality_failure": "stop on data quality failure",
    "stop_on_failure": "stop on validation failure"
  },
  "success_criteria": [
    "beats baseline"
  ],
  "target_outcome": "Fixture target.",
  "task_id": "TASK-8001",
  "time_period": {
    "end": "2025-12",
    "exclusion_lag": "none",
    "start": "2025-01"
  },
  "validation_design": {
    "leakage_review": "review fixture feature timing",
    "missingness_and_join_quality_checks": [
      "check joins"
    ],
    "segment_level_error_analysis": [
      "segment"
    ],
    "spatial_holdout_or_blocked_validation": "blocked fixture split",
    "time_split": "train then test"
  }
}
```
