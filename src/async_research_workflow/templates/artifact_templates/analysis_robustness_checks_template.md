# Analysis Robustness Checks Template

Use this fenced JSON block as
`artifacts/analysis_run/robustness_checks.json` for completed `run_analysis`
tasks. It records planned robustness checks, pass/warn/fail status, decision
impact, and claim boundaries without requiring a specific analysis library.

```json
{
  "schema_version": "1.0",
  "framework_version": "analysis_robustness_v1.0",
  "generated_at": "2026-05-09T10:40:00Z",
  "run_id": "RUN-0001",
  "experiment_plan_id": "EXP-0001",
  "task_id": "TASK-0004",
  "planned_checks": [
    {
      "name": "Alternative validation window",
      "planned_check_ref": "experiment_plan.robustness_checks[0]",
      "check_family": "holdout",
      "hypothesis": "Candidate result remains directionally similar under an adjacent validation window.",
      "status": "pass",
      "result": "Candidate remains better than the planned baseline in the adjacent window.",
      "metric_refs": [
        "analysis_metrics.candidate_metrics[0]",
        "analysis_metrics.validation_metrics[0]"
      ],
      "decision_impact": "supports_claim",
      "limitation": "One adjacent window does not prove stability across all future periods."
    }
  ],
  "summary": {
    "overall_status": "pass",
    "strongest_supported_claim": "predictive",
    "review_notes": "Fixture robustness supports a bounded predictive-improvement claim only."
  },
  "limitations": [
    {
      "limitation": "Robustness output is illustrative until replaced by project-owned analysis output.",
      "impact": "medium",
      "claim_boundary": "Supports workflow validation only, not a domain claim.",
      "mitigation": "Replace with real project robustness checks before result acceptance."
    }
  ]
}
```
