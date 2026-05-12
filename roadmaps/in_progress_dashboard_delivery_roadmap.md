# Dashboard Delivery Roadmap

Status: In Progress
Current phase: Slice 6
Last updated: 2026-05-12
Next action: Implement Slice 6 Human Decision Actions
Blocked by: None

Created: 2026-05-05

## Goal

Deliver a usable local dashboard for the async research workflow in fast AI-led
iterations.

The dashboard should become the normal operator surface for:

- initializing `research_ops/`
- running setup and health checks
- seeing active and blocked work
- seeing delivered projects and outcome stats
- resolving human decisions
- editing scheduled prompts
- triggering bounded jobs
- inspecting run logs and costs

The CLI remains the execution engine. The dashboard should call the same Python
helpers that the CLI uses, and the repo remains the source of truth.

## Delivery Expectation

The first useful version should be fast to deliver. A fuller local operator
dashboard should be achievable within a short implementation window if each
slice is kept small and AI workers are given clear ownership.

The May 9, 2026 Manus review moved this from "eventual polish" to a major
adoption lever. The review found the framework's correctness story strong but
said operators still need a gentler way to see queue state, review blockers,
accepted/rejected ledgers, costs, readiness, and human review work without
keeping many docs and JSON outputs open at once.

This roadmap owns the web UI implementation. The
[Operator UX And Workflow Ergonomics Roadmap](./delivered_operator_ux_workflow_ergonomics_roadmap.md)
owns adjacent CLI ergonomics such as review drafting, a one-page quickstart,
workflow orchestration, and operational metrics. Dashboard slices should consume
those public commands and read models rather than reimplementing workflow logic.

Delivery sequence:

```text
1. read-only dashboard plus setup checks
2. delivered projects and human decision actions
3. prompt library draft/edit/activate
4. trigger-now dry run and run history
5. trigger-now execution and cost/source/health polish
6. hardening, tests, acceptance-suite integration, UX cleanup
```

If scope pressure appears, keep the first two sequence groups intact and defer
prompt editing or trigger-now execution.

## MVP Coordination Contract

The Operator UX roadmap selected dashboard slices 1-2 as the near-term visual
operator surface on 2026-05-11. This roadmap is now the implementation home for
that work.

Slices 1-2 are read-only:

- Slice 1 exposes only `async-research console snapshot research_ops --json`.
- Slice 2 serves static assets and `GET /api/snapshot`.
- No POST, PUT, PATCH, DELETE, command-runner, setup, decision, prompt, schedule,
  trigger-now, or task-mutation endpoints exist in slices 1-2.
- Snapshot code may call existing read-only helpers or dry-run read models, but
  it must not write `research_ops/` files.
- Missing optional files and unimplemented downstream summaries render as
  `unavailable`, not as hard page failures.

Required snapshot groups for the MVP:

- `workspace`: ops path, existence, starter-file availability
- `readiness`: readiness verdict, exit code, blockers, next step
- `health`: health verdict, exit code, blockers, next step
- `tasks`: total counts, status counts, active/blocked/review/human slices,
  malformed status warnings, stale locks
- `human_decisions`: open count, blocked task refs, recent decision rows when
  available
- `accepted_outputs`: count, recent rows, stale/revalidation state when
  available
- `rejected_results`: count and recent rows
- `cost`: month/week spend, budget pressure, ledger warnings
- `ideas`: embedded `idea catalog dashboard` summary or `unavailable`
- `data`: embedded `data dashboard` summary or `unavailable`
- `library`: embedded `library dashboard` summary or `unavailable`
- `analysis`: embedded `analysis dashboard` summary or `unavailable`
- `runs`: recent run artifacts or `unavailable`
- `warnings`: parse, schema, missing optional artifact, and malformed-state
  warnings

Slice 3 is the first place setup actions may be implemented. It must make every
mutating action explicit, show the equivalent command, and display stdout,
stderr, exit code, and recovery advice.

## Build Philosophy

Build a control panel, not a platform.

Rules:

- The dashboard is local-only and binds to `127.0.0.1`.
- Use repo files as durable state.
- Start with read-only views before adding mutations.
- Mutations must call existing helpers where possible.
- Every mutation must show the exact command or operation performed.
- Every command result must show stdout, stderr, exit code, and recovery advice.
- Missing optional artifacts should render as `unavailable`, not fail the page.
- AI workers should own narrow modules and avoid broad refactors.

## Recommended Technical Path

Use a dependency-light implementation first:

```text
Python local HTTP server
  -> service modules under async_research_workflow/console/
  -> static HTML/CSS/JS assets packaged with the project
```

Recommended command:

```bash
async-research console research_ops
```

Recommended URL:

```text
http://127.0.0.1:8765
```

Do not introduce a database in v1. Generated reporting files are acceptable when
they are rebuildable from source artifacts.

## Progress

Last updated: 2026-05-12

| Phase | Description | Status |
| ---: | --- | --- |
| Slice 1 | Build the read-only snapshot backend and `async-research console snapshot research_ops --json`, including task counts, blockers, stale locks, costs, downstream dashboard summaries, readiness, health, recent runs, and warnings. | Complete |
| Slice 2 | Serve the local dashboard shell with static assets, left navigation, manual refresh, and read-only `GET /api/snapshot` as the only API endpoint. | Complete |
| Slice 3 | Add guarded setup and health actions for init, schema check, readiness dry run, health dry run, surface update, surface validate, and command-result inspection. | Complete |
| Slice 4 | Add the read-mostly task board with status filters, task detail inspection, status validation, transition validation, and lock inspection. | Complete |
| Slice 5 | Build delivered-project outcome indexes, summary commands, delivered-project table, and detail panel from accepted outputs and related provenance. | Complete |
| Slice 6 | Add human decision inbox actions around existing human-decision helpers, with confirmation, audit feedback, validation, and task-board refresh. | Pending |
| Slice 7 | Add prompt library initialization, draft editing, validation, diffing, activation, version history, and schedule binding visibility. | Pending |
| Slice 8 | Add schedule manifest storage, validation, schedule list, enable/disable intent, prompt binding, max runtime, and concurrency fields. | Pending |
| Slice 9 | Add trigger-now dry run with command preview, readiness check, concurrency check, disabled-job blocking, and run-id preview. | Pending |
| Slice 10 | Add bounded trigger-now execution, process/run artifacts, logs, event capture, usage ingestion where available, and run history. | Pending |
| Slice 11 | Add cost, source, and health detail views with budget pressure, source governance, stale accepted evidence, and recovery commands. | Pending |
| Slice 12 | Harden packaging, fixtures, smoke tests, acceptance-suite hooks, malformed-file handling, static asset inclusion, and dashboard recovery docs. | Pending |

## Product Slices

### Slice 1: Snapshot Backend

Timebox: 2 to 4 hours

Build:

- `async_research_workflow/console/snapshot.py`
- `async-research console snapshot research_ops --json`
- parser for task `status.json` files
- status counts
- stale lock detection
- human decision count
- accepted output count
- rejected result count
- idea/data/library dashboard summaries when available
- cost summary from `cost_ledger.csv`
- readiness and health verdicts with actionable next steps
- recent run artifact discovery

Demo:

```bash
async-research console snapshot research_ops --json
```

Acceptance:

- works on the generic starter template
- works when `research_ops/tasks/` is empty
- includes the MVP snapshot groups from the coordination contract
- malformed task status appears as a warning
- command does not mutate files
- missing optional foundation files render as `unavailable`

### Slice 2: Local Dashboard Shell

Timebox: 3 to 5 hours

Build:

- `async_research_workflow/console/server.py`
- packaged static files:
  - `index.html`
  - `styles.css`
  - `app.js`
- route for `/api/snapshot`
- first dashboard screen
- left navigation
- manual refresh

Dashboard cards:

- readiness state
- health state
- active tasks
- blocked tasks
- human decisions
- delivered projects
- rejected results
- idea, data, and library summary cards
- cost this month/week
- stale locks

Demo:

```bash
async-research console research_ops
```

Acceptance:

- local page opens at `127.0.0.1`
- dashboard shows real snapshot data
- missing optional files do not break rendering
- no mutation endpoints exist yet
- `/api/snapshot` is read-only and the only API endpoint in Slice 2
- state-machine and human-gate blockers are visible without opening raw JSON

### Slice 3: Setup And Health Actions

Timebox: 3 to 5 hours

Build:

- setup checklist view
- guarded `init` action
- schema check action
- readiness dry-run action
- health dry-run action
- surface update action
- surface validate action
- command result drawer

Dashboard actions:

```bash
async-research init research_ops
async-research schema-check research_ops
async-research readiness research_ops --dry-run
async-research health research_ops --dry-run
async-research surface update research_ops
async-research surface validate research_ops
```

Acceptance:

- operator can initialize a missing `research_ops/`
- `init` refuses to overwrite without explicit confirmation
- `surface update` is labeled as a file-mutating action
- each command shows stdout, stderr, exit code, and next step

### Slice 4: Task Board

Timebox: 3 to 5 hours

Build:

- task board view
- task filters by status
- task detail panel
- status validation action
- transition validation action
- lock inspection action

Show per task:

- task id and title
- status
- type
- review tier
- revision count
- lock state
- human gate reason
- last transition reason
- allowed paths
- links to task files

Acceptance:

- operator can inspect every task without opening files
- invalid status files are visible and actionable
- task board is read-only except validation/inspection actions

### Slice 5: Delivered Projects Index

Timebox: 4 to 8 hours

Build:

- `async_research_workflow/console/outcomes.py`
- `async-research outcomes refresh research_ops`
- `async-research outcomes list research_ops --status accepted`
- `async-research outcomes summary research_ops`
- generated files:
  - `research_ops/outcomes/delivered_projects.jsonl`
  - `research_ops/outcomes/delivered_projects_summary.json`
- delivered projects table
- delivered project detail panel

Show when available:

- accepted or synthesized date
- idea score and breakdown
- review scorecard
- review tier
- reviewer count
- disagreement flag
- revision count
- worker run count
- blocker/problem
- elapsed time to acceptance
- cost
- claim strength
- caveats
- source ids
- revalidation status

Acceptance:

- generated outcome files are rebuildable
- missing idea/review score is shown as `unavailable`
- accepted outputs can be inspected as delivered projects
- summary shows acceptance rate and average iterations where data exists

Framework additions likely needed:

- `origin_idea_id` or promotion score snapshot on tasks
- run artifacts linked to `task_id`
- structured blocker category when a human gate is created

### Slice 6: Human Decision Actions

Timebox: 4 to 8 hours

Build:

- human decision inbox
- action endpoints around existing human decision helpers
- confirmation modal
- post-action validation
- decision audit feedback

Actions:

- resume
- pause
- reject
- approve budget
- approve data use
- approve high-stakes claim
- add note

Acceptance:

- `needs_human` task can be resolved from the dashboard
- every action appends to the decision log
- invalid transition is blocked and explained
- task board refreshes after the action

### Slice 7: Prompt Library

Timebox: 4 to 8 hours

Build:

- `research_ops/prompts/` initializer
- prompt list
- prompt editor
- draft vs active diff
- required-section validator
- activate new version
- history log

Acceptance:

- operator can edit the worker prompt as a draft
- invalid prompt cannot be activated without explicit override
- activation records version, timestamp, and reason
- schedule bindings can show which prompt a job uses

### Slice 8: Schedule Manifest

Timebox: 3 to 6 hours

Build:

- `research_ops/schedules.json`
- schedule validator
- schedule list
- enable/disable job intent
- prompt binding selector
- max runtime and concurrency fields

Acceptance:

- operator can see intended recurring jobs
- schedule changes are logged
- dashboard does not need to install cron, launchd, GitHub Actions, or Codex
  automations in v1

### Slice 9: Trigger-Now Dry Run

Timebox: 3 to 6 hours

Build:

- dry-run trigger endpoint
- command preview
- readiness check before trigger
- concurrency check
- run id preview

Acceptance:

- operator can see exactly what would run
- disabled jobs cannot be triggered
- active concurrency group blocks trigger
- no Codex process launches in this slice

### Slice 10: Trigger-Now Execution

Timebox: 6 to 12 hours

Build:

- bounded local process runner
- run artifact writer
- log streaming or polling
- final message capture
- Codex JSON event capture when applicable
- usage ingestion when available
- run history page

Artifacts:

```text
research_ops/run_artifacts/<run-id>/
  run.json
  events.jsonl
  final_message.md
  stdout.log
  stderr.log
```

Acceptance:

- operator can run one worker now
- failed runs are visible and diagnosable
- same-job overlap is blocked
- run artifacts survive dashboard restart

### Slice 11: Cost, Source, And Health Views

Timebox: 4 to 8 hours

Build:

- cost table and summary
- source governance view
- framework health view
- stale accepted evidence section
- links to recovery commands

Acceptance:

- operator can see budget pressure without reading CSV
- stale or blocked sources are visible
- health failures have suggested next actions

### Slice 12: Hardening And Packaging

Timebox: 4 to 8 hours

Build:

- package static assets
- fixture tests
- smoke tests for dashboard server
- acceptance-suite hooks for new schemas
- runbook entry for dashboard recovery

Acceptance:

- `pip install -e .` includes dashboard assets
- dashboard works from an installed package
- malformed files fail closed
- tests cover the critical parser and mutation paths

## Fast MVP

If the goal is the fastest useful dashboard, build only:

1. Snapshot backend
2. Local dashboard shell
3. Setup and health actions
4. Read-only task board
5. Basic delivered projects table from `accepted_outputs_index.md`

MVP demo:

```bash
async-research console research_ops
```

The operator should be able to:

- initialize `research_ops/`
- run setup checks
- inspect task state
- see accepted outputs
- see obvious blockers and stale locks

No prompt editing. No trigger-now execution. No risky mutations except guarded
`init` and explicit `surface update`.

## Expanded Target

The expanded dashboard should support:

- setup and health checklist
- task board
- delivered projects analytics
- human decision resolution
- prompt draft/edit/activate
- schedule manifest editing
- trigger-now dry run
- trigger-now execution for one bounded worker
- run history
- cost/source/health views
- fixture tests and packaged static assets

This is the first version that can mostly replace day-to-day CLI usage.

## AI Work Packet Template

Each AI worker task should include:

```text
Goal:
Build one dashboard slice only.

Owned files:
List exact modules/static files/tests.

Do not touch:
Existing workflow protocols unless explicitly required.
Unrelated scripts.
User-local research_ops state.

Inputs:
Console spec, this roadmap, relevant schemas, starter template.

Acceptance:
List commands to run and UI behavior to verify.

Output:
Changed files, test results, screenshots if UI changed, known gaps.
```

Keep ownership narrow. For example, one worker can own `snapshot.py` and tests,
another can own static dashboard rendering, and another can own outcomes parsing.

## Dependency Decision

Default recommendation: start with standard-library Python server plus static
HTML/CSS/JS.

Reasons:

- fastest to package
- fewer installation failures
- easier for AI workers to edit
- enough for local dashboard v1

Reconsider a frontend/backend framework only after the local dashboard proves
which interactions matter.

## Risk Register

| Risk | Mitigation |
| --- | --- |
| Dashboard writes invalid workflow state | Mutations call existing helpers and run validation after every write. |
| AI workers over-refactor the framework | Give narrow owned files and reject unrelated rewrites. |
| UI becomes pretty but operationally weak | Require CLI-equivalent command output and recovery advice for every action. |
| Outcome stats are misleading | Show `unavailable` when provenance is missing; add provenance fields incrementally. |
| Trigger-now runs overlap scheduled jobs | Use schedule concurrency plus task-local locks before process launch. |
| Prompt editing breaks automation | Draft prompts, validate required sections, activate by version. |

## Framework Changes Needed For Full Stats

The current framework already supports many dashboard stats, but full outcome
analytics needs a few small additions:

- Add `origin_idea_id` and `promotion_score_snapshot` to promoted tasks.
- Add structured status transition history or append-only transition events.
- Link run artifacts to `task_id`, `job_id`, and `prompt_version`.
- Add structured blocker category to human gates.
- Require `review_panel/result_acceptance.json` before moving a task to
  `accepted`, unless a task type is explicitly exempt.
- Add outcome schemas for delivered project rows and summaries.

These changes should be implemented alongside Slice 5 and Slice 10, not before
the dashboard has a useful read-only shell.

## First Three AI Tasks

1. Build `console snapshot`.
2. Build the local dashboard shell consuming the snapshot.
3. Build setup and health actions.

After those land, decide whether the next most useful iteration is delivered
projects analytics or human decision resolution.
