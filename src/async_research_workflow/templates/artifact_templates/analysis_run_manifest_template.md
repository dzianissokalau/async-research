# Analysis Run Manifest Template

Use this fenced JSON block as `artifacts/analysis_run/run_manifest.json` for
`run_analysis` tasks. It records what actually ran after an experiment plan was
accepted. Project repositories own the analysis code; this manifest gives
reviewers and validators a stable contract for provenance, planned outputs,
deviations, and reproducibility.

```json
{
  "schema_version": "1.0",
  "framework_version": "analysis_run_v1.0",
  "run_id": "RUN-0001",
  "task_id": "TASK-0004",
  "task_type": "run_analysis",
  "experiment_plan_id": "EXP-0001",
  "accepted_plan_task_id": "TASK-0003",
  "accepted_plan_path": "research_ops/tasks/TASK-0003-experiment-plan/worker_output.md",
  "accepted_plan_result_acceptance_path": "research_ops/tasks/TASK-0003-experiment-plan/review_panel/result_acceptance.json",
  "analysis_config_path": "research_ops/tasks/TASK-0004-run-analysis/artifacts/analysis_run/analysis_config.json",
  "data_versions": [
    {
      "source_id": "DS-0001",
      "version": "2026-05-03 export",
      "accessed_at": "2026-05-09",
      "role": "outcome",
      "artifact_path": "research_ops/tasks/TASK-0004-run-analysis/artifacts/analysis_run/data_versions.json"
    }
  ],
  "code_version": {
    "type": "git",
    "value": "git:e55ec7a",
    "dirty": false,
    "notes": "Project-owned analysis code version used for this run."
  },
  "runner": {
    "type": "local_script",
    "entrypoint": "analysis/run_repeat_sales_backtest.py",
    "parameters_ref": "research_ops/tasks/TASK-0004-run-analysis/artifacts/analysis_run/analysis_config.json",
    "execution_environment": "local Python environment documented by the project repository"
  },
  "method_family": "predictive_model",
  "candidate_method": {
    "name": "Repeat-sales feature backtest",
    "planned_method_ref": "experiment_plan.candidate_methods[0]",
    "implementation_ref": "analysis/run_repeat_sales_backtest.py"
  },
  "baseline_refs": [
    {
      "name": "Local median baseline",
      "planned_baseline_ref": "experiment_plan.baselines[0]",
      "expected_output_path": "research_ops/tasks/TASK-0004-run-analysis/artifacts/analysis_run/metrics.json"
    }
  ],
  "primary_metric": {
    "name": "Out-of-sample MAE reduction versus baseline",
    "direction": "decrease",
    "planned_metric_ref": "experiment_plan.metrics.primary_metric"
  },
  "planned_outputs": [
    {
      "name": "metrics",
      "path": "research_ops/tasks/TASK-0004-run-analysis/artifacts/analysis_run/metrics.json",
      "required_for_acceptance": true
    },
    {
      "name": "diagnostics",
      "path": "research_ops/tasks/TASK-0004-run-analysis/artifacts/analysis_run/diagnostics.md",
      "required_for_acceptance": true
    },
    {
      "name": "robustness checks",
      "path": "research_ops/tasks/TASK-0004-run-analysis/artifacts/analysis_run/robustness_checks.json",
      "required_for_acceptance": true
    },
    {
      "name": "leakage checks",
      "path": "research_ops/tasks/TASK-0004-run-analysis/artifacts/analysis_run/leakage_checks.json",
      "required_for_acceptance": true
    }
  ],
  "output_paths": [
    "research_ops/tasks/TASK-0004-run-analysis/artifacts/analysis_run/run_manifest.json",
    "research_ops/tasks/TASK-0004-run-analysis/artifacts/analysis_run/analysis_config.json",
    "research_ops/tasks/TASK-0004-run-analysis/artifacts/analysis_run/data_versions.json",
    "research_ops/tasks/TASK-0004-run-analysis/artifacts/analysis_run/metrics.json",
    "research_ops/tasks/TASK-0004-run-analysis/artifacts/analysis_run/diagnostics.md",
    "research_ops/tasks/TASK-0004-run-analysis/artifacts/analysis_run/robustness_checks.json",
    "research_ops/tasks/TASK-0004-run-analysis/artifacts/analysis_run/leakage_checks.json"
  ],
  "started_at": "2026-05-09T10:00:00Z",
  "completed_at": "2026-05-09T10:18:00Z",
  "runtime_minutes": 18,
  "cost": {
    "api_usd": 0,
    "compute_usd": 0,
    "total_usd": 0,
    "notes": "No paid cloud or API spend."
  },
  "deviations_from_plan": [],
  "reproducibility": {
    "rerun_possible": true,
    "rerun_command": "python analysis/run_repeat_sales_backtest.py --config research_ops/tasks/TASK-0004-run-analysis/artifacts/analysis_run/analysis_config.json",
    "environment": "Project repository environment documented outside async-research.",
    "random_seed": "42",
    "determinism_notes": "Train, validation, and test windows are fixed by the accepted plan."
  }
}
```
