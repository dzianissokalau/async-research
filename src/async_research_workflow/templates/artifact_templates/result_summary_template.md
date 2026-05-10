# Result Summary Template

Use this fenced JSON block in `worker_output.md` for `run_analysis` and
`evaluate_results` tasks before review. The result acceptance validator can
derive routine artifact acceptance from `status.json`, `worker_output.md`, and
review aggregation, but result-bearing tasks need this structured summary for
claim caps and evidence ledger updates.

For `run_analysis`, `run_manifest_path` must point at the same task's canonical
`artifacts/analysis_run/run_manifest.json`. For `evaluate_results`, it must
point at the upstream analysis run being evaluated. Keep `primary_metric`,
`baseline_results`, `candidate_results`, and `validation_split_results`
consistent with the structured `metrics.json`; do not use this summary to
upgrade the accepted plan's claim strength after seeing favorable results.

```json
{
  "schema_version": "1.0",
  "framework_version": "result_acceptance_v1.0",
  "result_id": "RESULT-0001",
  "experiment_plan_id": "EXP-0001",
  "run_id": "RUN-0001",
  "task_id": "TASK-0004",
  "run_manifest_path": "research_ops/tasks/TASK-0004-run-analysis/artifacts/analysis_run/run_manifest.json",
  "artifact_version": "git:e55ec7a",
  "dataset_versions": [
    {
      "source_id": "DS-0001",
      "version": "2026-05-03 export"
    }
  ],
  "primary_metric": "Out-of-sample MAE reduction versus baseline",
  "baseline_results": "Prior-period baseline MAE: 1.00",
  "candidate_results": "Candidate MAE: 0.95",
  "validation_split_results": "Train 2018-2022, validation 2023, test 2024-2025",
  "robustness_results": [
    "Stable by property type and region"
  ],
  "leakage_check_results": [
    "All target aggregates fit on train windows only"
  ],
  "limitations": [
    "Suggestive predictive result only; not causal"
  ],
  "claim": "The candidate feature improves predictive accuracy in this bounded backtest.",
  "claim_type": "predictive",
  "claim_strength": "moderate",
  "recommended_decision": "accept_as_evidence",
  "public_or_high_stakes": false,
  "human_approval_present": false,
  "follow_up_tasks": [
    {
      "reason": "Check stability on latest release",
      "required_artifact": "updated metrics table",
      "priority": 3,
      "human_approval_needed": false,
      "required_before_memo_use": false
    }
  ]
}
```
