# TASK-0001: Example Task Title

## Objective

State exactly what should be produced.

## Scope

- Work only inside this task folder.
- Use only listed sources unless `allow_browsing` is true.
- Do not create new tasks directly; propose follow-ups.
- Respect the review tier in `status.json`.

## Required Output

Write `worker_output.md` with:

- summary
- evidence or reasoning
- caveats
- recommendation
- proposed follow-ups

For result-bearing `run_analysis` and `evaluate_results` tasks, also include a
fenced JSON result summary from
`async_research_workflow/templates/artifact_templates/result_summary_template.md`.
Do not upgrade `claim_strength` after seeing attractive results; the summary
should request the strongest claim the accepted plan and validation artifacts
can support, and reviewers/claim gates may cap it further.

## Acceptance Criteria

- Output answers the objective.
- Claims are supported.
- Caveats are explicit.
- No files outside `allowed_paths` changed.

## Review Policy

- Default: Tier 1 primary review.
- Escalate to Tier 2 for experiment plans and result summaries.
- Escalate to Tier 3 for final memos, moderate/strong claims, or public/high-stakes use.
- Reviewers escalate with the advanced/internal helper `python -m async_research_workflow.scripts.escalate_review_tier`; do not hand-edit review tiers.

## Escalation Policy

- Read `research_ops/escalation_policy.md` before moving risky work forward.
- Run `async-research escalation evaluate <task-dir> --ops-dir research_ops`.
- If it exits `2`, rerun with `--apply`, stop, and leave the structured
  `human_gate` for a human decision.
- Do not set `needs_human` with a vague reason.

## Context

- Add relevant file paths or source URLs here.

## Data Source Audit

- For `idea_discovery` tasks, include a fenced JSON exploration cycle block or
  `exploration_cycle.json` conforming to
  `async_research_workflow/schemas/exploration_cycle.schema.json`, and pass
  `async-research exploration validate <worker-output> --ops-dir research_ops --task-dir <task-dir>`
  before updating the discovery inbox.
- For scored idea candidates, run the advanced/internal helper
  `python -m async_research_workflow.scripts.validate_mission_policy`,
  `async-research idea score`, and `async-research idea validate` before adding
  candidates to the discovery inbox or planner queue.
- For `experiment_plan` tasks, list audited data source IDs such as `DS-0001`.
- If no audited data source exists yet, route to `data_readiness` before experiment planning.
- For `data_readiness` tasks, produce profile draft/update details,
  recommended audit status, access check results, field/grain coverage, join
  feasibility, known limitations, recommended next task, and a kill reason if
  data is unusable. Any audit/profile recommendation must be traceable to
  `worker_output.md` and should pass `async-research source validate` plus
  `async-research data validate`.
- Source-dependent tasks must follow `data_source_audit_register_protocol.md`:
  Tier 3 sources are context-only, Tier 4 sources are blocked without explicit
  human approval, high-impact claims need Tier 1/2 support, and stale sources
  must be refreshed or routed to `needs_human`.
- Accepted evidence must cite audited `DS-*` source IDs and pass
  `async-research source check-claim`
  when source-dependent.
- If the task uses prior accepted evidence as a current fact, run
  `async-research accepted check-memory-use`
  against the artifact. Stale accepted memory must be revalidated or used only
  as historical context.
- Accepted task results should include `claim_type`, `freshness_window_days`,
  `next_recheck_date`, `revalidation_status`, `source_ids`, `caveats`,
  `supersedes`, and `superseded_by` fields.
- `experiment_plan` outputs must include a fenced JSON block or `experiment_plan.json`
  conforming to `async_research_workflow/schemas/experiment_plan.schema.json`, and must
  pass `async-research experiment validate <worker-output> --ops-dir research_ops --task-dir <task-dir>`
  before review.
- For `run_analysis` tasks, the task context must name the accepted plan:
  `accepted_plan_task_id`, `experiment_plan_id`, `accepted_plan_path`, and
  `accepted_plan_result_acceptance_path`. Run only that accepted plan, or record
  every deviation in the manifest with `reviewer_action_required: true`.
- For `run_analysis` tasks, write every output inside this task folder,
  normally under `artifacts/analysis_run/`. The accepted experiment plan and
  source/data artifacts are inputs, not writable outputs.
- Before analysis starts, write
  `artifacts/analysis_run/run_manifest.json` conforming to
  `async_research_workflow/schemas/analysis_run.schema.json` with
  `run_status: "planned"`, then run
  `async-research analysis preflight <task-dir> --ops-dir research_ops`.
  Blockers or warnings must be resolved or reviewed before execution.
- After execution, update `run_manifest.json` to the actual run status and
  write `metrics.json`, `diagnostics.json`, and `robustness_checks.json` under
  `artifacts/analysis_run/` using the packaged analysis output templates. If a
  result claim is made, write `claim_gates.json` and make the result summary
  cite `artifacts/analysis_run/run_manifest.json`.
- Before review, run
  `async-research analysis validate-run <task-dir> --ops-dir research_ops`.
  If a result summary and `claim_gates.json` are present, also run
  `async-research analysis validate-results <task-dir> --ops-dir research_ops`.
  Do not mark the task `awaiting_review` until blockers are fixed or explicitly
  routed to `needs_human`.
- For `evaluate_results` tasks, do not rerun or silently reinterpret the
  analysis. Evaluate the existing manifest, metrics, diagnostics, robustness,
  claim gates, and reviewer notes. The result summary must cite the upstream
  `artifacts/analysis_run/run_manifest.json`; accepted/rejected review
  aggregates must pass `async-research result-acceptance`.

## Cross-Task Anti-Context

Generated by `async-research anti-context build`. Keep this section when assigning the task to a worker.
