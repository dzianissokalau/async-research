# Analysis Run Manifest Template

Use this fenced JSON block as `artifacts/analysis_run/run_manifest.json` for
`run_analysis` tasks. It starts as a pre-run declaration with
`run_status: "planned"` and becomes the canonical record of what actually ran
after the worker updates it to `completed` or `failed`. Project repositories own
the analysis code; this manifest gives reviewers and validators a stable
contract for provenance, planned outputs, deviations, and reproducibility.

For manual, notebook, or SQL runs where parameters are embedded in the reviewed
artifact rather than a separate config file, set `analysis_config_path` and
`runner.parameters_ref` to `"none"`.

```json
{
  "schema_version": "1.0",
  "framework_version": "analysis_run_v1.0",
  "manifest_created_at": "2026-05-09T09:55:00Z",
  "run_id": "RUN-0001",
  "run_status": "planned",
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
      "path": "research_ops/tasks/TASK-0004-run-analysis/artifacts/analysis_run/diagnostics.json",
      "required_for_acceptance": true
    },
    {
      "name": "robustness checks",
      "path": "research_ops/tasks/TASK-0004-run-analysis/artifacts/analysis_run/robustness_checks.json",
      "required_for_acceptance": true
    }
  ],
  "output_paths": [
    "research_ops/tasks/TASK-0004-run-analysis/artifacts/analysis_run/run_manifest.json",
    "research_ops/tasks/TASK-0004-run-analysis/artifacts/analysis_run/analysis_config.json",
    "research_ops/tasks/TASK-0004-run-analysis/artifacts/analysis_run/data_versions.json",
    "research_ops/tasks/TASK-0004-run-analysis/artifacts/analysis_run/metrics.json",
    "research_ops/tasks/TASK-0004-run-analysis/artifacts/analysis_run/diagnostics.json",
    "research_ops/tasks/TASK-0004-run-analysis/artifacts/analysis_run/robustness_checks.json"
  ],
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
