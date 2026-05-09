# Analysis Claim Gates Template

Use this fenced JSON block as `artifacts/analysis_run/claim_gates.json` for
completed `run_analysis` tasks after metrics, diagnostics, and robustness
artifacts are available. It records the claim class, maximum supported claim
strength, human-review requirement, and machine-readable reasons for accepted,
capped, rejected, or human-gated claims.

```json
{
  "schema_version": "1.0",
  "framework_version": "analysis_claim_gates_v1.0",
  "generated_at": "2026-05-09T10:45:00Z",
  "run_id": "RUN-0001",
  "experiment_plan_id": "EXP-0001",
  "task_id": "TASK-0004",
  "claim": "The candidate feature improves predictive accuracy in this bounded backtest.",
  "claim_type": "predictive",
  "requested_claim_strength": "moderate",
  "max_claim_strength": "moderate",
  "claim_decision": "accepted",
  "recommended_route": "accept_as_evidence",
  "cap_reasons": [],
  "human_gate": {
    "required": false,
    "satisfied": true,
    "reason": "not required"
  },
  "claim_gate_results": [
    {
      "gate": "predictive_validation_and_baseline",
      "status": "pass",
      "max_claim_strength": "moderate",
      "reason": "predictive validation and baseline comparison are present; predictive claims remain capped at moderate",
      "evidence": [
        "passed baseline comparisons: 1",
        "out-of-sample splits: 1"
      ]
    },
    {
      "gate": "diagnostic_quality",
      "status": "pass",
      "max_claim_strength": "strong",
      "reason": "diagnostics do not cap the claim",
      "evidence": []
    },
    {
      "gate": "human_approval_required",
      "status": "pass",
      "max_claim_strength": "strong",
      "reason": "human approval is not required",
      "evidence": []
    }
  ],
  "review_notes": [
    "Claim gates accepted the requested claim strength."
  ]
}
```
