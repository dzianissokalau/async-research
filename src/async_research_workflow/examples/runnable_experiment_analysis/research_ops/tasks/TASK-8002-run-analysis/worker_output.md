Planned fixture analysis only.

This task intentionally stops at `run_status: "planned"` so the fixture can
exercise `async-research analysis preflight` and `async-research analysis
run-adapter` without implying that this task already produced empirical
evidence. The completed accepted empirical result lives in
`research_ops/tasks/TASK-8003-completed-analysis/`.
