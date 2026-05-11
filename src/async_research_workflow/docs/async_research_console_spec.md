# Async Research Console Specification

Created: 2026-05-05

## Status And Scope

Status: proposed product and contract specification. The console is not yet part
of the implemented CLI surface unless a command is explicitly documented by the
package.

This document defines what the local console should be, what it may read and
write, and what safety rules it must preserve. It is intentionally not the
delivery roadmap.

Use the
[Dashboard Delivery Roadmap](../../../roadmaps/in_progress_dashboard_delivery_roadmap.md) for
implementation sequence, work slices, MVP scope, risk register, and first AI
tasks.

If this specification and the roadmap drift, use this document for product
behavior, data contracts, and safety constraints. Use the roadmap for delivery
order and implementation packets.

## Purpose

The Async Research Console is a local-first control plane for the async research
workflow.

Its job is to make the framework easy to operate:

- see what research is happening now
- understand what happened recently
- spot blocked, stale, expensive, or risky work
- provide human input without hand-editing fragile files
- change scheduled prompts safely
- run bounded jobs immediately when needed
- keep all operational state in the repo

The console is not the source of truth. The repo remains the source of truth.
The console reads and writes the same `research_ops/` files, schemas, ledgers,
locks, and run artifacts used by scheduled jobs and CLI helpers.

## Product Principle

The console should feel like mission control for a slow, careful research
operation, not like a chat UI.

The operator should be able to answer these questions in under five minutes:

```text
What is running?
What is blocked?
What needs my decision?
What changed since I last checked?
What is spending money?
What can I safely trigger now?
Which prompts or schedules are active?
```

The tool should prefer clear controls over clever automation. Every mutation
should be explicit, logged, reversible when practical, and compatible with the
existing command-line workflow.

## Primary Users

### Solo Research Operator

Wants a quick morning or weekly view of the research system. Needs to approve
blocked decisions, inspect outputs, change priorities, and trigger one job
without remembering helper commands.

### Framework Maintainer

Wants to debug the workflow itself. Needs schema errors, stale locks, cost
ledger gaps, failed transitions, and prompt-version drift surfaced clearly.

### AI Builder

An AI coding agent will implement large parts of this console. The specification
must therefore provide stable product boundaries, data contracts, safety rules,
and testable behavior.

## Non-Goals

- Do not replace `research_ops/` with a database as the primary state store.
- Do not require Linear, GitHub Issues, Symphony, or any external tracker.
- Do not create a general multi-agent orchestration platform.
- Do not make long-running freeform chats the main work unit.
- Do not allow arbitrary writes across the repo from the UI.
- Do not start with cloud deployment, authentication, or collaboration features.
- Do not hide validation failures behind optimistic UI states.

## System Shape

Recommended initial command:

```bash
async-research console research_ops
```

Recommended local URL:

```text
http://127.0.0.1:8765
```

Initial architecture:

```text
browser UI
  -> local HTTP server
    -> console service layer
      -> existing async-research helpers
      -> research_ops files
      -> codex exec for trigger-now jobs
```

The first implementation may use only the Python standard library if keeping
the package dependency-free is more important than UI richness. If a dependency
is acceptable, use a minimal FastAPI or Starlette backend plus a small static
frontend.

The product should be useful before it is beautiful. Start read-only, then add
safe mutations, then add job triggering.

## Core Capabilities

### 1. Dashboard

The dashboard is the first screen.

It should show:

- readiness state
- health state
- active task count
- queued task count
- tasks by status
- stale locks
- open human decisions
- delivered projects and accepted outputs
- recent accepted outputs
- recent rejected or paused outputs
- latest scheduler runs
- estimated and actual cost this week/month
- source freshness warnings

Required controls:

- refresh status
- open workspace setup checklist
- run readiness check
- run health check
- update human review surface
- open detailed views for tasks, delivered projects, decisions, costs, prompts,
  and runs

Empty states must be useful. For example, if no `research_ops/` folder exists,
the console should offer a guarded `init` action rather than a blank dashboard.

### 2. Workspace Setup And Maintenance

The console should let the operator run the common setup and maintenance
commands without opening a terminal.

Required dashboard actions:

```bash
async-research init research_ops
async-research schema-check research_ops
async-research readiness research_ops --dry-run
async-research health research_ops --dry-run
async-research surface update research_ops
async-research surface validate research_ops
```

The setup checklist should show:

- whether `research_ops/` exists
- whether required starter files exist
- whether schemas pass
- readiness result
- health result
- whether the human review surface is current
- whether the surface validates
- the last time each check ran
- the exact command used for each check

Controls:

- initialize `research_ops/`
- initialize with the generic template
- initialize with the real-estate worked example template
- run all safe checks
- run one check
- refresh the human review surface
- validate the human review surface
- copy the equivalent CLI command

Safety requirements:

- `init` must require confirmation of the target folder and template.
- `init` must not silently overwrite an existing operational folder.
- dry-run checks should not mutate files.
- `surface update` is allowed to mutate `daily_status.md`,
  `human_review_queue.md`, and related generated surface files.
- every command result should show stdout, stderr, exit code, and recovery advice
  when the command fails.

Recommended first-run flow:

```text
choose ops directory
  -> initialize research_ops
  -> run schema-check
  -> run readiness --dry-run
  -> run health --dry-run
  -> run surface update
  -> run surface validate
  -> open dashboard
```

### 3. Task Board

The task board should make the conveyor belt visible.

Views:

- all active tasks
- ready for worker
- in progress
- awaiting review
- needs revision
- needs human
- paused
- accepted
- rejected

Each task row/card should show:

- task id and slug
- status
- review tier
- last transition reason
- lock state
- age
- revision count if present
- allowed paths
- cost estimate or recorded usage if present
- human gate summary if present
- links to task files and artifacts

Required controls:

- open task details
- copy task path
- validate task status
- validate transition
- inspect lock
- run recovery checks

Safe task mutations:

- pause task
- resume task from `needs_human` or `paused`
- reject task
- request revision
- add human note
- approve budget
- approve data use
- approve high-stakes claim

All task mutations should call existing helper logic where possible. Direct
`status.json` editing should be a last resort and should still run validation.

### 4. Delivered Projects And Outcome Analytics

The console should make completed work visible as a portfolio of delivered
research outputs, not just terminal task folders.

A delivered project is any task or linked task chain that reaches one of these
states:

- `accepted`
- `synthesized`
- `rejected` when shown in the learning archive
- `paused` when explicitly parked as an abandoned project

The default view should focus on accepted and synthesized outputs. Rejected and
paused outputs should be available as separate learning views.

Read from:

```text
research_ops/accepted_outputs_index.md
research_ops/weekly_digest.md
research_ops/metrics_history.jsonl
research_ops/cost_ledger.csv
research_ops/decisions.md
research_ops/tasks/*/status.json
research_ops/tasks/*/task.md
research_ops/tasks/*/worker_output.md
research_ops/tasks/*/reviews/*
research_ops/tasks/*/review_panel/aggregate.json
research_ops/tasks/*/review_panel/result_acceptance.json
research_ops/tasks/*/artifacts/*
```

Each delivered project row should show:

- project id or task id
- title
- delivered status
- accepted or synthesized date
- project type
- original idea id when available
- idea score and score breakdown when available
- result acceptance scorecard when available
- aggregate review decision
- review tier
- reviewer count
- reviewer disagreement flag
- iteration count
- revision count
- worker run count
- blocker count
- main blocker or problem
- human decisions required
- elapsed time from creation to acceptance
- estimated and actual cost
- claim strength
- caveats
- source ids
- freshness or revalidation status
- next recheck date
- links to output, reviews, run artifacts, and accepted memory row

Project detail pages should show:

- timeline of major state transitions
- idea scoring section
- worker output summary
- review score section
- blockers and human gates
- revisions requested and resolved
- final decision and caveats
- cost and usage
- follow-up tasks
- stale evidence and revalidation state

The dashboard should compute these stats conservatively:

- iteration count is `revision_count` plus completed worker reruns when run
  artifacts can be linked to the task.
- idea score comes from the idea candidate or exploration-cycle artifact that
  promoted the task.
- review score comes from `review_panel/result_acceptance.json` scorecard when
  present, otherwise from structured review or aggregate artifacts if available.
- blocker/problem text comes from `human_gate.reason`, `human_gate.details`,
  `human_gate_reason`, `last_transition_reason`, reviewer notes, and failed run
  metadata.
- cost comes from task-specific ledger rows first, then linked run artifacts,
  then planned budget fields when actual usage is unavailable.

Recommended generated index:

```text
research_ops/outcomes/
  delivered_projects.jsonl
  delivered_projects_summary.json
```

The generated index should be rebuildable from source files. It is a cache and
reporting surface, not the source of truth.

Controls:

- refresh delivered project index
- filter by accepted, synthesized, rejected, or paused
- filter by task type, score range, review tier, blocker type, or source
- open project detail
- create follow-up task
- schedule revalidation
- export table as CSV or JSON

Outcome analytics should show:

- accepted output count
- rejected output count
- acceptance rate
- average iterations to acceptance
- median elapsed time to acceptance
- average idea score for accepted vs rejected work
- average review score for accepted vs rejected work
- cost per accepted output
- most common blocker categories
- revision-limit hit count
- reviewer disagreement rate
- stale or due accepted evidence count

### 5. Human Decision Inbox

This view is the operator's highest-value workflow.

It should read from:

```text
research_ops/human_review_queue.md
research_ops/daily_status.md
research_ops/tasks/*/status.json
research_ops/decisions.md
```

Each decision should show:

- decision id
- task id
- reason human input is required
- available decisions
- recommended safe action
- consequence of ignoring
- urgency
- affected files

Required controls:

- resolve as resume
- resolve as pause
- resolve as reject
- approve budget
- approve data use
- approve public or high-stakes claim
- add note only

Every decision resolution must append to the human decision log and run the
appropriate transition validation.

### 6. Prompt Library

Scheduled prompts should become editable operational assets.

Add this folder in a future migration:

```text
research_ops/prompts/
  discovery_scout.md
  planner.md
  worker.md
  primary_reviewer.md
  panel_reviewer.md
  synthesizer.md
  versions.json
  history.jsonl
```

Prompt files should be plain Markdown with front matter:

```yaml
---
prompt_id: worker
version: worker_v1.0
role: worker
status: active
updated_at: 2026-05-05T00:00:00Z
updated_by: human
---
```

The console should support:

- view active prompts
- edit prompt draft
- compare draft to active version
- validate required prompt sections
- activate draft as a new version
- roll back to a previous version
- see which scheduled jobs use each prompt

Prompt validation should check for the required scheduler prompt rules:

- role
- allowed files
- forbidden files
- task selection rule
- max task count
- max time
- output file
- status transition
- revision counter handling when applicable
- stop conditions
- cost and escalation limits
- reference to `research_ops/escalation_policy.md`

Prompt edits should append to `history.jsonl` and `decisions.md`.

### 7. Schedule Manager

Schedules should also become repo-backed assets.

Add:

```text
research_ops/schedules.json
research_ops/schedule_history.jsonl
```

Example schema shape:

```json
{
  "schema_version": "1.0",
  "jobs": [
    {
      "id": "worker",
      "enabled": true,
      "runner": "codex_exec",
      "prompt_id": "worker",
      "cadence": "daily",
      "max_runtime_minutes": 45,
      "max_concurrent": 1,
      "last_run_id": null
    }
  ]
}
```

Initial schedule controls:

- enable or disable a job
- edit cadence metadata
- edit runtime limit
- edit prompt binding
- trigger one run now
- dry-run next job selection

The first version does not need to install cron, launchd, GitHub Actions, or
Codex app automations automatically. It should manage the repo-backed schedule
intent and provide exact commands for the selected scheduler.

### 8. Trigger-Now Runner

The console should be able to launch one bounded local job.

Initial buttons:

- run discovery scout now
- run planner now
- run one worker now
- run one reviewer now
- run weekly synthesizer now
- run acceptance suite
- run simulate week

Runner requirements:

- never run two jobs with the same concurrency group at once
- write run metadata before execution starts
- stream or periodically refresh logs
- capture `codex exec --json` event output when applicable
- capture final message
- ingest usage metadata when available
- run post-job readiness or health checks when useful
- show failed command, exit code, and recovery advice

Suggested run artifact layout:

```text
research_ops/run_artifacts/
  local-20260505-120000-worker/
    run.json
    events.jsonl
    final_message.md
    stdout.log
    stderr.log
```

Suggested `run.json`:

```json
{
  "schema_version": "1.0",
  "run_id": "local-20260505-120000-worker",
  "job_id": "worker",
  "status": "running",
  "started_at": "2026-05-05T12:00:00Z",
  "finished_at": null,
  "command": ["codex", "exec"],
  "cwd": "/repo/root",
  "ops_dir": "research_ops",
  "prompt_id": "worker",
  "prompt_version": "worker_v1.0",
  "exit_code": null
}
```

### 9. Cost And Usage View

The console should make budget pressure visible without requiring spreadsheet
inspection.

Read from:

```text
research_ops/cost_ledger.csv
research_ops/run_artifacts/*/run.json
research_ops/run_artifacts/*/events.jsonl
```

Show:

- weekly actual cost
- weekly planned cost
- monthly actual cost
- monthly planned cost
- cost by role
- cost by task
- cost by model/provider when available
- failed usage ingestion rows
- budget-check failures

Controls:

- run cost summary
- run budget check for a proposed action
- mark a planned row as superseded if a helper supports it

### 10. Source Governance View

Read from:

```text
research_ops/data_source_audit.md
research_ops/discovery/source_register.md
research_ops/revalidation_schedule.md
research_ops/accepted_outputs_index.md
```

Show:

- approved sources
- blocked sources
- sources requiring human approval
- stale accepted evidence
- due revalidation items
- tasks depending on stale or unaudited data

Controls:

- run source freshness check
- add human note for a source
- approve source for a bounded use case
- create a data-readiness task from a stale or unaudited item

### 11. Run History

Run history should help debug automation without opening terminal logs.

Show:

- run id
- job id
- status
- start and end time
- duration
- exit code
- files changed if detectable
- task claimed if detectable
- token and cost usage if available
- final message
- links to event logs

Controls:

- rerun same job with current prompt
- rerun same job with historical prompt only after explicit confirmation
- mark run as inspected

### 12. Framework Health

This view is for maintainers.

Show outputs from:

```bash
async-research schema-check research_ops
async-research readiness research_ops --dry-run
async-research health research_ops --dry-run
async-research surface update research_ops
async-research surface validate research_ops
async-research accepted revalidation research_ops --write-schedule
async-research source freshness research_ops
async-research acceptance-suite
```

The console should separate:

- blocking errors
- warnings
- useful notices
- expensive checks not run yet

## Permissions And Safety

The console starts as local-only:

```text
127.0.0.1 only
no remote access
no auth in v1
```

Safety rules:

- never expose a public HTTP server by default
- never run `danger-full-access`
- never delete task files from the UI in v1
- never edit outside `research_ops/` unless a command explicitly operates on
  package docs or helper code
- never mutate `status.json` without validation
- never trigger paid/API/cloud work when `requires_human=true` is unresolved
- never run a job if readiness reports a blocking condition unless the operator
  explicitly chooses a recovery action
- always record prompt, schedule, and human-decision mutations

## Data Contracts

### Existing Inputs

The console must consume:

- `research_ops/queue.md`
- `research_ops/daily_status.md`
- `research_ops/human_review_queue.md`
- `research_ops/weekly_digest.md`
- `research_ops/decisions.md`
- `research_ops/cost_ledger.csv`
- `research_ops/data_source_audit.md`
- `research_ops/revalidation_schedule.md`
- `research_ops/accepted_outputs_index.md`
- `research_ops/metrics_history.jsonl`
- `research_ops/tasks/*/task.md`
- `research_ops/tasks/*/status.json`
- `research_ops/tasks/*/worker_output.md`
- `research_ops/tasks/*/reviews/*`
- `research_ops/tasks/*/review_panel/*`
- `research_ops/tasks/*/review_panel/aggregate.json`
- `research_ops/tasks/*/review_panel/result_acceptance.json`
- `research_ops/tasks/*/artifacts/*`

### New Files

Add these only when the relevant milestone starts:

```text
research_ops/prompts/*.md
research_ops/prompts/versions.json
research_ops/prompts/history.jsonl
research_ops/schedules.json
research_ops/schedule_history.jsonl
research_ops/outcomes/delivered_projects.jsonl
research_ops/outcomes/delivered_projects_summary.json
research_ops/run_artifacts/*/run.json
research_ops/run_artifacts/*/events.jsonl
research_ops/run_artifacts/*/final_message.md
```

### New Schemas

Recommended package schemas:

```text
async_research_workflow/schemas/prompt_manifest.schema.json
async_research_workflow/schemas/schedule_manifest.schema.json
async_research_workflow/schemas/run_manifest.schema.json
async_research_workflow/schemas/delivered_project.schema.json
async_research_workflow/schemas/delivered_projects_summary.schema.json
```

## Suggested CLI Surface

Add commands incrementally:

```bash
async-research console research_ops
async-research console snapshot research_ops --json
async-research init research_ops
async-research schema-check research_ops
async-research readiness research_ops --dry-run
async-research health research_ops --dry-run
async-research surface update research_ops
async-research surface validate research_ops
async-research outcomes refresh research_ops
async-research outcomes list research_ops --status accepted
async-research outcomes summary research_ops
async-research prompts init research_ops
async-research prompts validate research_ops
async-research prompts activate research_ops worker --message "tighten worker stop rules"
async-research schedules init research_ops
async-research schedules validate research_ops
async-research runs list research_ops
async-research runs trigger research_ops worker --dry-run
async-research runs trigger research_ops worker
```

The UI should call the same service functions as the CLI, not duplicate logic in
JavaScript.

## UI Design Requirements

The interface should be dense, calm, and operational.

Recommended layout:

```text
left navigation:
  Dashboard
  Setup
  Tasks
  Delivered
  Decisions
  Prompts
  Schedules
  Runs
  Costs
  Sources
  Health

top bar:
  ops_dir selector
  readiness badge
  refresh button
  run-now menu
```

Design rules:

- first screen is the dashboard, not a landing page
- use tables for repeated operational records
- use compact detail panels for selected rows
- use status badges sparingly and consistently
- use confirmation modals for mutations
- use diff view for prompt activation
- use disabled controls with reasons when an action is unsafe
- avoid decorative UI that reduces scan speed

## AI-Buildable Implementation Strategy

AI agents should build this in narrow slices. Each slice should have a clear
write scope and should leave the console usable.

### Slice Rules

- One slice should touch one subsystem when possible.
- Every slice should include tests for parser/service logic.
- UI slices should use fixture `research_ops` directories.
- Runner slices should support dry-run before real execution.
- Mutating slices should include rollback or audit-log behavior.
- AI workers should not rewrite existing workflow protocols while building UI.

### Suggested Internal Modules

```text
src/async_research_workflow/console/
  __init__.py
  snapshot.py
  parsers.py
  setup.py
  outcomes.py
  prompts.py
  schedules.py
  runs.py
  server.py
  static/
    index.html
    app.js
    styles.css
```

Keep command orchestration in Python. Keep the browser as a thin operational
client.

## Delivery Boundary

This specification is complete enough to support implementation, but it should
not own the build order. The delivery roadmap owns:

- implementation slices
- MVP scope
- timeboxes
- risk register
- first AI work packets
- sequencing between snapshot, dashboard shell, setup checks, outcomes,
  decision actions, prompt editing, schedules, run triggering, and hardening

Keep the roadmap and this specification linked rather than duplicating their
contents. A future implementation task should reference both documents:

```text
Product contract: src/async_research_workflow/docs/async_research_console_spec.md
Delivery plan: roadmaps/in_progress_dashboard_delivery_roadmap.md
```

## Product Completion Bar

A full console version is complete when:

- `async-research console research_ops` opens a local dashboard
- dashboard shows task status, locks, delivered projects, decisions, costs, and
  recent runs
- operator can initialize and health-check `research_ops/` from the dashboard
- operator can inspect delivered projects with available idea scores, review
  scores, iteration counts, blockers, costs, and caveats
- operator can resolve human decisions safely
- operator can edit and activate scheduled prompts with history
- operator can trigger one worker job now with run artifacts
- all mutations are logged
- all task status mutations are validated
- the repo remains the source of truth

## Quality Bar

The console is useful only if it reduces operator attention cost.

A good version means:

- morning check takes under five minutes
- blocked work is obvious
- delivered research is easy to inspect and compare
- prompt changes are safer than hand-editing
- trigger-now runs are less error-prone than terminal commands
- failures are easier to recover from
- AI workers can add features without destabilizing the framework

## Open Questions

- Should the package stay dependency-free, or is one small web dependency worth
  the implementation speed?
- Should prompt front matter be mandatory for all generated starter prompts?
- Should schedule state be descriptive only, or should the console eventually
  install/update cron, launchd, or Codex automations?
- Should trigger-now execution be enabled by default, or require a launch flag
  such as `--allow-runs`?
- Should run artifacts include redacted environment metadata for debugging?
