# Analysis Metrics Template

Use this fenced JSON block as `artifacts/analysis_run/metrics.json` for
completed `run_analysis` tasks. It records baseline metrics, candidate metrics,
validation split metrics, baseline comparisons, and limitations without
requiring a specific modeling library.

```json
{
  "schema_version": "1.0",
  "framework_version": "analysis_metrics_v1.0",
  "generated_at": "2026-05-09T10:30:00Z",
  "run_id": "RUN-0001",
  "experiment_plan_id": "EXP-0001",
  "task_id": "TASK-0004",
  "primary_metric_name": "Out-of-sample MAE reduction versus baseline",
  "baseline_metrics": [
    {
      "metric_name": "MAE",
      "role": "baseline",
      "value": 10.4,
      "unit": "target units",
      "direction": "decrease",
      "split": "validation",
      "segment": "all",
      "source": "analysis output table",
      "planned_metric_ref": "experiment_plan.metrics.primary_metric",
      "notes": "Naive local median baseline."
    }
  ],
  "candidate_metrics": [
    {
      "metric_name": "MAE",
      "role": "candidate",
      "value": 9.7,
      "unit": "target units",
      "direction": "decrease",
      "split": "validation",
      "segment": "all",
      "source": "analysis output table",
      "planned_metric_ref": "experiment_plan.metrics.primary_metric",
      "notes": "Candidate method from the accepted plan."
    }
  ],
  "validation_metrics": [
    {
      "metric_name": "MAE",
      "role": "validation",
      "value": 9.7,
      "unit": "target units",
      "direction": "decrease",
      "split": "validation",
      "segment": "all",
      "source": "analysis output table",
      "planned_metric_ref": "experiment_plan.metrics.primary_metric",
      "notes": "Primary validation split metric used for result acceptance."
    }
  ],
  "metric_rows": [],
  "baseline_comparisons": [
    {
      "baseline_name": "Local median baseline",
      "candidate_name": "Repeat-sales feature backtest",
      "metric_name": "MAE",
      "baseline_value": 10.4,
      "candidate_value": 9.7,
      "delta": -0.7,
      "comparison_direction": "candidate_lower_better",
      "passed": true,
      "planned_baseline_ref": "experiment_plan.baselines[0]",
      "notes": "Candidate improves validation MAE versus the planned baseline."
    }
  ],
  "validation_splits": [
    {
      "split_name": "2025 holdout",
      "split_role": "validation",
      "time_window": "2025-01 through 2025-12",
      "geography_scope": "accepted plan geography",
      "sample_size": 1250,
      "metric_refs": [
        "baseline_metrics[0]",
        "candidate_metrics[0]",
        "validation_metrics[0]"
      ],
      "notes": "Split follows the accepted experiment plan."
    }
  ],
  "limitations": [
    {
      "limitation": "Fixture values are illustrative until replaced by project-owned analysis output.",
      "impact": "medium",
      "claim_boundary": "Supports workflow validation only, not a domain claim.",
      "mitigation": "Replace with real project metrics before result acceptance."
    }
  ]
}
```
