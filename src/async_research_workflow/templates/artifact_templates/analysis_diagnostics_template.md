# Analysis Diagnostics Template

Use this fenced JSON block as `artifacts/analysis_run/diagnostics.json` for
completed `run_analysis` tasks. It records missingness, join quality, leakage,
segment diagnostics, optional calibration or uncertainty checks, and limitations
in a reviewer-readable structure.

```json
{
  "schema_version": "1.0",
  "framework_version": "analysis_diagnostics_v1.0",
  "generated_at": "2026-05-09T10:35:00Z",
  "run_id": "RUN-0001",
  "experiment_plan_id": "EXP-0001",
  "task_id": "TASK-0004",
  "missingness_checks": [
    {
      "name": "Outcome missingness",
      "scope": "validation split",
      "affected_fields": [
        "target_outcome"
      ],
      "missing_rate": 0.01,
      "threshold": 0.05,
      "status": "pass",
      "evidence": "Validation split target missingness is below the accepted threshold."
    }
  ],
  "join_quality_checks": [
    {
      "name": "Feature-to-outcome join",
      "left_source_id": "DS-0001",
      "right_source_id": "DS-0001",
      "join_keys": [
        "entity_id",
        "effective_month"
      ],
      "unmatched_rate": 0.02,
      "duplicate_key_rate": 0.0,
      "status": "pass",
      "evidence": "Join audit found low unmatched records and no duplicate keys."
    }
  ],
  "leakage_checks": [
    {
      "name": "Point-in-time feature availability",
      "planned_check_ref": "experiment_plan.leakage_checklist.feature_availability_before_prediction_date",
      "leakage_type": "future information",
      "status": "pass",
      "evidence": "All features are timestamped before the prediction date.",
      "reviewer_action_required": false
    }
  ],
  "segment_diagnostics": [
    {
      "segment_name": "geography_group",
      "segment_value": "all",
      "sample_size": 1250,
      "metric_name": "MAE",
      "metric_value": 9.7,
      "status": "pass",
      "notes": "No segment-specific degradation detected in the fixture output."
    }
  ],
  "calibration_checks": [
    {
      "name": "Probability calibration",
      "applicable": false,
      "status": "not_applicable",
      "metric_name": "none",
      "value": "not applicable",
      "evidence": "This run does not make a probability or calibrated-risk claim."
    }
  ],
  "uncertainty_checks": [
    {
      "name": "Uncertainty interval coverage",
      "applicable": false,
      "status": "not_applicable",
      "metric_name": "none",
      "value": "not applicable",
      "evidence": "This run does not make an uncertainty interval claim."
    }
  ],
  "limitations": [
    {
      "limitation": "Diagnostics are illustrative until replaced by project-owned analysis output.",
      "impact": "medium",
      "claim_boundary": "Supports workflow validation only, not a domain claim.",
      "mitigation": "Replace with real project diagnostics before result acceptance."
    }
  ]
}
```
