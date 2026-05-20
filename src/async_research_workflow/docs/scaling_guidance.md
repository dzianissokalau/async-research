# Scaling Guidance

Created: 2026-05-19

`async-research` is optimized for file-backed solo and small-team research
workspaces. The design favors inspectable Markdown, JSON, CSV, and JSONL files
over a database so humans and LLM operators can review state with ordinary repo
tools.

That tradeoff is intentional, but it has limits.

## Expected Workspace Shape

A healthy alpha workspace is usually small enough that commands can linearly
scan the relevant files:

- tens to low hundreds of active or archived task folders
- hundreds of idea records, accepted-output rows, source rows, or cost rows
- Markdown/JSON artifacts that remain readable in code review
- scheduled jobs that process one bounded task per run

This is a fit for a local Git repo, a private research repo, or a controlled
team workspace where reviewability matters more than throughput.

## Linear-Scan Tradeoffs

Most read models deliberately scan files on demand. This keeps state durable and
easy to audit, but it means command latency grows with workspace size and file
quality:

- malformed task status files can slow or partially degrade dashboard/report
  output
- very large ledgers or generated Markdown tables can make validation slower
- broad `research_ops/tasks/*` scans are simple and transparent, not optimized
  for thousands of concurrent tasks
- missing timestamps, links, or cost rows render as `unavailable` rather than
  being inferred from prose

Use `async-research workflow check research_ops`,
`async-research health research_ops --dry-run`, and
`async-research console snapshot research_ops --json` to spot drift before
increasing cadence.

Use the Phase 11 scaling assessor when deciding whether file-backed state is
still enough:

```bash
async-research scaling assess research_ops
```

The assessor measures task count, runtime ledger size, eval artifact pressure,
task-lock friction, and read-only dashboard snapshot latency. It reports
`repo_files_sufficient` by default for normal alpha workspaces and recommends an
optional rebuildable index cache only when measured thresholds are crossed.

## When To Split Workspaces

Split into separate `research_ops/` workspaces when any of these become true:

- two projects have different source-governance, privacy, audience, or
  publication-review requirements
- the queue mixes unrelated domains and planners repeatedly need to filter
  everything by project
- task folders or ledgers become too large for useful code review
- accepted-memory freshness policies differ by topic or audience
- humans would not want one dashboard to summarize all active work

Prefer split workspaces over adding ad hoc project columns to every table. Keep
cross-project synthesis as a separate accepted task or human-owned process.

## When To Graduate To Heavier Orchestration

Move beyond the file-backed alpha pattern when local scans and Git review stop
being the right control plane. Signals include:

- thousands of active tasks or ideas
- multiple writers that need central concurrency control beyond file locks
- strict service-level objectives for job latency
- credentialed external data access that must be centrally brokered
- organization-wide permission models, audit retention, or private-data policy
  enforcement
- warehouse-scale artifacts, notebooks, SQL/dbt execution, or long-running
  compute pipelines

At that point, use `async-research` as a contract and fixture source, not as the
entire scheduler. Keep the same safety ideas: dry-run before write, explicit
human gates, accepted evidence separate from publication readiness, rollback for
write paths, and deterministic read models.

## Cadence Guidance

For file-backed workspaces, slow cadence is a safety feature:

- daily planning or worker loops are enough for early dogfood
- reviewer loops can be daily for low-risk tasks and weekly for deeper panels
- trigger-now runs should start with `schedules trigger-dry-run`
- recurring jobs should stop on malformed state, `needs_human`, budget pressure,
  missing source approval, or acceptance/readiness disagreement

Increase cadence only after the acceptance suite, dashboard snapshot, health,
surface validation, and project-specific checks are boring.

## Practical Maintenance

Keep large workspaces reviewable by archiving intentionally:

- close or pause stale task folders instead of leaving ambiguous status
- refresh accepted memory and revalidation schedules before discovery/planning
- keep `cost_ledger.csv` append-only and summarize older periods when needed
- preserve source IDs and idea IDs rather than rewriting history
- move private or oversized artifacts out of packaged docs and templates

The goal is not infinite scale. The goal is an honest, inspectable control plane
for bounded research work.

See the [Scalable State Backend Decision](./scalable_state_backend_decision.md)
for the current Phase 11 backend decision and optional-cache boundary.
