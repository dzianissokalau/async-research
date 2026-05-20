# Low-Cost Async Research Workflow

Created: 2026-05-01

This folder contains a researched design for running an autonomous or semi-autonomous research workflow with much lower cost than a full multi-agent always-on system.

The target use case is a solo or small-team research operation where ChatGPT Pro, Codex, scheduled jobs, and light human review are used to advance research tasks over time.

## Core Conclusion

The optimal low-cost pattern is an asynchronous conveyor belt:

```text
idea discovery -> discovery inbox -> planner -> bounded worker job
               -> reviewer gate -> human gate only when needed -> weekly synthesis
```

Use repository files as durable memory. Do not rely on long chat context as the source of truth.

The main cost reduction comes from:

- short scoped jobs instead of long open-ended agent sessions
- single-writer task folders instead of multiple agents editing the same state
- scheduled reviewer and planner jobs instead of agent debate
- cheap/local/batch models for extraction and triage
- frontier models only at decision gates
- hard stop conditions for every automated run
- independent reviewer notes before any reviewer sees another review
- slow cadence by design: daily or weekly loops are acceptable if outputs improve

## Reading Order

1. [First Success Quickstart](./first_success_quickstart.md)
2. [Research Findings](./research_findings.md)
3. [Workflow Blueprint](./workflow_blueprint.md)
4. [Task Contracts](./task_contracts.md)
5. [Research Runtime Contract](./research_runtime_contract.md)
6. [Runtime Artifacts](./runtime_artifacts.md)
7. [Evaluation Flywheel](./evaluation_flywheel.md)
8. [Idea Discovery Workflow](./idea_discovery_workflow.md)
9. [Idea Catalog Contract](./idea_catalog_contract.md)
10. [Review Ensemble Policy](./review_ensemble_policy.md)
11. [Framework Requirements](./framework_requirements/README.md)
12. [Feedback Hardening Plan](./feedback_hardening_plan.md)
13. [Atomic Locking Protocol](./atomic_locking_protocol.md)
14. [State Transition Validation Protocol](./state_transition_validation_protocol.md)
15. [JSON And Schema Validation Protocol](./schema_validation_protocol.md)
16. [Structural Reviewer Isolation Protocol](./reviewer_isolation_protocol.md)
17. [Revision Counter Protocol](./revision_counter_protocol.md)
18. [Algorithmic Review Aggregation Protocol](./algorithmic_review_aggregation_protocol.md)
19. [Health Monitor Protocol](./health_monitor_protocol.md)
20. [Dynamic Tier Escalation Protocol](./dynamic_tier_escalation_protocol.md)
21. [Mission-Weighted Idea Scoring Protocol](./mission_weighted_idea_scoring_protocol.md)
22. [Accepted Outputs Index Protocol](./accepted_outputs_index_protocol.md)
23. [Knowledge Library Contract](./knowledge_library_contract.md)
24. [Schema Versioning Protocol](./schema_versioning_protocol.md)
25. [Prompt And Framework Versioning Protocol](./prompt_framework_versioning_protocol.md)
26. [Human Decision Log Protocol](./human_decision_log_protocol.md)
27. [Metrics Baseline And History Protocol](./metrics_baseline_history_protocol.md)
28. [Claim-Strength Re-Evaluation Protocol](./claim_strength_re_evaluation_protocol.md)
29. [Cross-Task Anti-Context Protocol](./cross_task_anti_context_protocol.md)
30. [Batch Job Lifecycle Protocol](./batch_job_lifecycle_protocol.md)
31. [Programmatic Cost Tracking Protocol](./programmatic_cost_tracking_protocol.md)
32. [Dynamic Killability Thresholds Protocol](./dynamic_killability_thresholds_protocol.md)
33. [Data Source Audit Register Protocol](./data_source_audit_register_protocol.md)
34. [Foundation Update Proposal Contract](./foundation_update_proposal_contract.md)
35. [Escalation Policy Protocol](./escalation_policy_protocol.md)
36. [Operational Readiness Runbook](./operational_readiness_runbook.md)
37. [Scheduler And Prompts](./scheduler_and_prompts.md)
38. [Cost Controls](./cost_controls.md)
39. [Async Research Console Specification](./async_research_console_spec.md)
40. [Internal Helper Boundary](./internal_helper_boundary.md)
41. [Release-Trust Hardening Report](./release_trust_hardening_report.md)
42. [Scaling Guidance](./scaling_guidance.md)
43. [Worked Examples Index](./worked_examples_index.md)
44. [Dashboard Delivery Roadmap](../../../roadmaps/delivered_dashboard_delivery_roadmap.md)
45. [Implementation Plan](./implementation_plan.md)
46. [Sources](./sources.md)

## Package Resources

Use the `async-research` CLI for supported workflow operations. Advanced helpers
remain importable as `python -m async_research_workflow.scripts.<module>` when a
CLI wrapper does not exist yet. See the
[internal helper boundary](./internal_helper_boundary.md) for helpers that
deliberately remain advanced/internal even though they are importable.

Packaged resources:

- [Generic starter template](../templates/generic_research_ops_starter/research_ops/README.md)
- [Real-estate worked example template](../templates/research_ops_starter/research_ops/README.md)
- [Runnable experiment and analysis example](../examples/runnable_experiment_analysis/README.md)
- [Coffee pilot deliverable maturity fixture](../examples/coffee_pilot_deliverable_maturity/README.md)
- [Worked examples index](./worked_examples_index.md)
- [GitHub worker example](../examples/github_actions_codex_worker.yml)
- [Benchmark cases](../benchmarks/autonomy_benchmark_cases.json)
- [Default mission policy](../mission_policy.json)
- [JSON schemas](../schemas/)
- [Artifact templates](../templates/artifact_templates/)

The GitHub workflow is an example only. It is intentionally not placed under
`.github/workflows/`, so it will not run unless copied into an active workflow.

## Acceptance Suite

Run the durable P0-P3 hardening and framework checks with:

```bash
async-research acceptance-suite
```

The suite creates isolated fixtures under the platform temp directory, exercises
the workflow helpers, and exits nonzero if a hardening contract regresses. When
debugging a failed check, keep the fixtures with:

```bash
async-research acceptance-suite --keep-work-dir
```

Before spending model budget on unattended jobs, rehearse one scheduled week
with fixture outputs:

```bash
async-research simulate-week research_ops
```

The simulator writes to a temporary `research_ops` copy by default, drives the
real helper scripts, covers accepted/rejected/needs_human paths, and reports
queue size, ledger updates, readiness skips, metrics history, and simulated
cost.

For light human supervision, generate and validate the markdown control surface:

```bash
async-research surface update research_ops
async-research surface validate research_ops
```

This refreshes `daily_status.md`, `human_review_queue.md`, and the weekly digest
summary so the operator can focus on current state and actionable decisions.

Accepted memory freshness is part of the suite. Use:

```bash
async-research accepted revalidation research_ops --write-schedule
```

to write `research_ops/revalidation_schedule.md` and surface due/stale accepted
evidence before discovery or planning uses it as current context.

Latest full-loop simulation result:
[End-To-End Workflow Simulation Report](./end_to_end_workflow_simulation_report.md).

## Operational Starter Templates

The default `async-research init` template is the
[generic starter](../templates/generic_research_ops_starter/research_ops/README.md).
It includes durable queue, source-governance, data foundation, cost, metric,
decision, review, and evidence files without live tasks or project-specific
sources.

The [real-estate starter](../templates/research_ops_starter/research_ops/README.md)
remains available as a worked example:

```bash
async-research init research_ops --template real-estate
```

For manual operations and recovery, start with the
[Operational Readiness Runbook](./operational_readiness_runbook.md).

Run `async-research data validate research_ops` after editing `data/` files to
check profile/source linkage, access notes, join caveats, and known gap refs
without mutating the workspace.

Run `async-research data dashboard research_ops --use-case experiment_planning`
when you need a read-only view of sources usable for a selected policy use case,
candidate or blocked sources, stale reviews, data gaps, ideas blocked by data
readiness, and join caveats.

Run `async-research data inspect-proposals research_ops <proposal-source>` to
inspect a data-readiness worker's `foundation_update_proposal_v1` artifact
before any write-capable apply workflow exists. The command is read-only and
fails closed for unsafe target paths or non-data proposals.

Run `async-research library inspect-proposals research_ops <proposal-source>` to
inspect a literature-extract worker's `foundation_update_proposal_v1` artifact
before any write-capable apply workflow exists. The command is read-only and
fails closed for unsafe library target paths, non-library proposals, or missing
`LIT-*` source references.

## Recommended First Setup

Create this operational folder in the working research repo:

```text
research_ops/
  discovery_inbox.md
  ideas/
    idea_catalog.md
    prioritization.md
  data/
    data_catalog.md
    data_access.md
    join_map.md
    known_data_gaps.md
    profiles/
      README.md
  inbox.md
  queue.md
  daily_status.md
  weekly_digest.md
  decisions.md
  data_source_audit.md
  metrics_baseline.json
  metrics_history.jsonl
  discovery/source_register.md
  review_panel/
  batches/
  tasks/
```

Run five recurring jobs:

- Idea discovery: weekly by default.
- Planner: daily or 2-3 times per week.
- Worker: daily or 2-4 times per day.
- Reviewer: daily for simple reviews; weekly for deeper panels.
- Weekly synthesizer: weekly.

Keep the human loop exception-based:

- daily check is optional unless `needs_human` appears
- 20 to 30 minutes weekly to choose priorities and approve serious claims
- no human approval is required for low-risk discovery, triage, drafting, or cheap review

## Recommended Tool Split

| Work | Lowest-cost good option |
| --- | --- |
| reminders and light coordination | ChatGPT scheduled tasks |
| repo-changing research work | Codex app automation or Codex CLI non-interactive job |
| GitHub-native automation | GitHub Actions schedule plus a coding agent |
| autonomous idea discovery | local 30B, mini model, or Batch API |
| bulk document extraction | local 30B model or Batch API |
| primary task review | Codex or standard frontier model |
| independent methodology review | Claude/Sonnet/Opus or comparable model |
| independent factual/source challenge | Gemini Pro/Flash or comparable model |
| final methodology critique | frontier model panel or human |
| public/investment/policy claim approval | human |

## Main Warning

Do not create many scheduled ChatGPT tasks as if they were a distributed agent cluster. ChatGPT scheduled tasks have limits, scheduled agent invocations count against usage, and vague agent tasks can burn budget quickly.

Use a small number of recurring jobs that read a queue and process one bounded task at a time.

## Quality Policy

This workflow is tuned for:

```text
1. high quality
2. independence from constant human steering
3. low cost
4. speed only after the first three are satisfied
```

If a full loop takes a day or a week, that is acceptable. The goal is not to maximize agent activity; it is to maximize accepted evidence per dollar and per minute of human attention.
