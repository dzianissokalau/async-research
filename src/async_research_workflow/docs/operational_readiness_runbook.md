# Operational Readiness Runbook

Created: 2026-05-03

Use this when scheduled jobs stop, route to `needs_human`, hit budget pressure,
produce batch outputs, or need new data-source approval.

This runbook is deliberately short. Deeper rules live in the linked protocols;
this file is the first place to look during operations.

## First Triage

Start every manual intervention with read-only checks:

```bash
async-research schema-check research_ops
async-research readiness research_ops --dry-run
async-research surface update research_ops
async-research surface validate research_ops
python -m async_research_workflow.scripts.escalation_policy scan-needs-human research_ops
async-research source freshness research_ops
async-research health research_ops --dry-run
async-research cost summary research_ops
```

Then inspect:

```text
research_ops/daily_status.md
research_ops/human_review_queue.md
research_ops/queue.md
research_ops/decisions.md
research_ops/cost_ledger.csv
research_ops/tasks/<TASK-ID>/status.json
research_ops/tasks/<TASK-ID>/worker_output.md
research_ops/tasks/<TASK-ID>/review_panel/
```

Do not hand-edit `status.json` unless a protocol explicitly says to do so.

## Human Review Surface

Refresh the light-supervision files before manual review:

```bash
async-research surface update research_ops
async-research surface validate research_ops
```

Start with `research_ops/daily_status.md`, then inspect
`research_ops/human_review_queue.md` only when it reports open decisions. Each
queue row gives the decision id, task id, decision needed, available options,
recommended command, consequence of ignoring, urgency, owner, and required
update path. Resolve rows with
`async-research decision resolve-task`; do
not delete queue rows by hand.

## Escalation Policy

When a task may require human judgment, run:

```bash
python -m async_research_workflow.scripts.escalation_policy evaluate \
  research_ops/tasks/TASK-0001-data-readiness \
  --ops-dir research_ops
```

If it exits `2`, do not continue automated work. Apply the stop state with:

```bash
python -m async_research_workflow.scripts.escalation_policy evaluate \
  research_ops/tasks/TASK-0001-data-readiness \
  --ops-dir research_ops \
  --apply
```

Every `needs_human` task must include a structured `human_gate` with trigger,
available decisions, default safe action, retry behavior, and ledger update
behavior. Validate that invariant with:

```bash
python -m async_research_workflow.scripts.escalation_policy scan-needs-human research_ops
```

## Back Up Before Automation

Before enabling or changing unattended jobs, create a cheap rollback point:

```bash
git status --short
git branch backup/async-research-before-automation
```

If the working tree is dirty, inspect the changes first:

```bash
git diff -- research_ops async_research_workflow
```

Do not start scheduled workers when task files, `queue.md`, or helper scripts
have unexplained local edits. Commit intentional workflow state first, or pause
automation until the owner decides whether those edits are safe.

## Recover Broken Status Files

Use this only when `status.json` is malformed or cannot be parsed:

```bash
python -m async_research_workflow.scripts.recover_status_json \
  research_ops/tasks/TASK-0001-data-readiness
```

The recovery wrapper:

- quarantines the broken file as `status.invalid.*.json`
- writes a valid replacement `status.json`
- routes the task to `needs_human`
- sets `last_transition_reason = status_json_recovery`

After recovery:

```bash
python -m async_research_workflow.scripts.validate_json_artifact \
  research_ops/tasks/TASK-0001-data-readiness/status.json \
  --schema async_research_workflow/schemas/task_status.schema.json

python -m async_research_workflow.scripts.validate_transition \
  research_ops/tasks/TASK-0001-data-readiness
```

Human decision: inspect the quarantined file, decide whether to resume, pause,
or reject the task, and record the decision with
`async-research decision append` or `async-research decision resolve-task`.

## Recover Local Crashes

Use this when a local Codex app, cron, launchd, or CLI worker is killed before
it can release a task lock or commit its outputs.

First inspect the repo and task lock without changing anything:

```bash
git status --short
python -m async_research_workflow.scripts.task_lock status \
  research_ops/tasks/TASK-0001-data-readiness
async-research health research_ops --dry-run
```

Then decide:

| Situation | Action |
| --- | --- |
| output is complete and validations pass | commit the task files, then release the lock with the recorded owner |
| output is partial but useful | move the task to `needs_human` with a human decision note |
| `status.json` is malformed | run `recover_status_json.py` and inspect the quarantined file |
| lock is stale and no worker is alive | acquire with `task_lock.py acquire --stale-minutes <N>` or release with `--force` only after human review |
| uncommitted edits are unrelated or unsafe | preserve them with `git diff > /tmp/async-research-crash.patch` before any cleanup |

Do not run destructive git cleanup commands until the patch or branch is saved
and the owner has decided what should be discarded.

## Resolve `needs_human`

Never move a task out of `needs_human` by editing `status.json` directly. Use:

```bash
async-research decision resolve-task \
  research_ops \
  research_ops/tasks/TASK-0001-data-readiness \
  --decision resume \
  --status ready_for_worker \
  --reason "human reviewed blocker and approved another worker pass" \
  --approver "<human-name>"
```

Common decisions:

| Situation | Decision | Status |
| --- | --- | --- |
| worker can continue safely | `resume` | `ready_for_worker` |
| task should wait | `pause` | `paused` |
| task should stop | `reject` | `rejected` |
| budget approved | `approve_budget` | `ready_for_worker` |
| data use approved | `approve_data_use` | `ready_for_worker` |
| public/high-stakes claim approved | `approve_public` or `approve_high_stakes` | `ready_for_worker` |

Then verify:

```bash
python -m async_research_workflow.scripts.validate_transition \
  research_ops/tasks/TASK-0001-data-readiness
```

## Inspect Budget Pressure

Use summary first:

```bash
async-research cost summary \
  research_ops \
  --monthly-budget-usd 50 \
  --weekly-budget-usd 15
```

Before any paid promotion, batch, API call, or cloud run:

```bash
async-research cost budget-check \
  research_ops \
  --item-id TASK-0001 \
  --action "planned paid run" \
  --proposed-api-usd 2 \
  --proposed-compute-usd 0 \
  --monthly-budget-usd 50 \
  --weekly-budget-usd 15
```

If `budget-check` exits nonzero:

- do not spend
- route the task to `needs_human` or `paused`
- approve with `async-research decision resolve-task --decision approve_budget`
  only if the spend is intentional

Discovery scoring also reacts to budget pressure through:

```bash
async-research idea score \
  research_ops/discovery/IDEA-0001.json \
  --budget-mode auto \
  --ops-dir research_ops
```

If it returns `budget_constrained`, respect `score.max_promotions_per_week`.

## Capture Codex CLI Usage

For `codex exec` local runs, prefer JSON event output and store it under the
task artifacts before final status validation:

```bash
codex exec --json --cd "$RESEARCH_REPO_ROOT" \
  --output-last-message /tmp/codex-last-message.md \
  "<bounded prompt>" \
  > research_ops/tasks/TASK-0001-data-readiness/artifacts/codex_events.jsonl
```

If the event stream contains token usage fields, ingest them:

```bash
async-research cost ingest-usage \
  research_ops \
  --usage-file research_ops/tasks/TASK-0001-data-readiness/artifacts/codex_events.jsonl \
  --item-id TASK-0001 \
  --role worker \
  --model codex-cli \
  --status awaiting_review
```

If the product surface does not expose usage metadata, keep an estimated ledger
row with `actual=false`; the budget gate still protects against planned spend.

## Pre-Loop Readiness Gate

Every scheduled loop should start with:

```bash
async-research readiness research_ops
```

Use `--dry-run` for manual inspection. Without `--dry-run`, the command writes
the readiness result to `research_ops/health_report.json` and appends a compact
summary to `research_ops/daily_status.md`.

Exit codes:

| Code | Meaning | Scheduler behavior |
| ---: | --- | --- |
| 0 | safe to run | continue workers |
| 2 | safe with warnings | continue, but surface warnings in status |
| 3 | skip loop | treat as intentional no-work; do not start expensive workers |
| 4 | invalid ops state | fail the wrapper and notify the owner |
| 5 | human decision required | pause workers until `needs_human` items are resolved |

The gate checks schema validity, malformed statuses, stale locks, unresolved
`needs_human`, queue depth, reviewer capacity, budget pressure, failed previous
runs, duplicate active tasks, source audit readiness, accepted evidence
freshness, required ops files, and metrics snapshot freshness.

## Control Discovery Capacity

Before discovery writes candidates, run:

```bash
async-research queue discovery-gate \
  research_ops \
  --max-active 10
```

If it returns `action=discovery_skipped`, do not scan sources or update
`discovery_inbox.md`. Append a short `daily_status.md` note with the active task
count and let reviewer/worker capacity catch up first.

Exit codes:

| Code | Meaning | Shell wrapper behavior |
| ---: | --- | --- |
| 0 | capacity available | continue discovery |
| 2 | intentional skip | treat as success-with-no-work, not a failed job |
| 4 | invalid invocation | fail the wrapper and notify the owner |

Shell-safe pattern for `set -e` wrappers:

```bash
set +e
gate_json="$(async-research queue discovery-gate research_ops --max-active 10)"
gate_rc=$?
set -e

if [ "$gate_rc" -eq 2 ]; then
  printf '%s\n' "$gate_json"
  exit 0
fi
if [ "$gate_rc" -ne 0 ]; then
  printf '%s\n' "$gate_json"
  exit "$gate_rc"
fi
```

## Trust Batch Outputs

Batch outputs are untrusted until review marks them trusted.

Check a manifest:

```bash
python -m async_research_workflow.scripts.batch_lifecycle trust-status \
  research_ops/batches/BATCH-0001/batch_manifest.json
```

Normal lifecycle:

```bash
python -m async_research_workflow.scripts.batch_lifecycle validate-manifest \
  research_ops/batches/BATCH-0001/batch_manifest.json

python -m async_research_workflow.scripts.batch_lifecycle ingest \
  research_ops/batches/BATCH-0001/batch_manifest.json \
  --ingest-task-id TASK-0302 \
  --ingested-file artifacts/ingested.jsonl
```

After a reviewer accepts the ingest task:

```bash
python -m async_research_workflow.scripts.batch_lifecycle mark-reviewed \
  research_ops/batches/BATCH-0001/batch_manifest.json \
  --review-task-id TASK-0303
```

Rule: do not cite batch outputs in accepted evidence, experiment plans, or memos
until `trust-status` reports trusted, unless the task explicitly says it is
auditing untrusted output.

## Approve Data Sources

Initialize or validate the register:

```bash
python -m async_research_workflow.scripts.data_source_audit init research_ops
async-research source validate research_ops
```

Approve or update a source:

```bash
python -m async_research_workflow.scripts.data_source_audit upsert \
  research_ops \
  --source-id DS-0001 \
  --approval-status approved_with_caveats \
  --name "HM Land Registry Price Paid Data" \
  --location "https://www.gov.uk/government/statistical-data-sets/price-paid-data-downloads" \
  --owner "HM Land Registry" \
  --source-tier tier_1_official \
  --approved-use-cases "experiment_planning; accepted_evidence" \
  --blocked-use-cases "borrower-level mortgage terms" \
  --freshness-window-days 45 \
  --known-limitations "registration lag and address normalization caveats apply" \
  --citation-requirements "cite DS-0001, URL, extract date, and caveats" \
  --last-reviewed "2026-05-03" \
  --approved-by "<human-or-task-id>" \
  --review-notes "Official transaction data; lag and address normalization caveats apply."
```

Before creating or accepting an experiment plan:

```bash
async-research source check-experiment \
  research_ops \
  research_ops/tasks/TASK-0003-repeat-sales-experiment-plan/task.md
```

Allowed experiment-planning statuses are `approved` and
`approved_with_caveats`. `candidate`, `unknown`, `restricted`, `blocked`,
`deprecated`, stale, Tier 3-only, Tier 4, or missing sources route to
`data_readiness` or `needs_human`.

## Accept Or Reject Evidence

After required reviews are written:

```bash
async-research review aggregate \
  research_ops/tasks/TASK-0001-data-readiness
```

The aggregator now validates result acceptance for accepted/rejected routes and
writes:

```text
research_ops/tasks/<TASK-ID>/review_panel/result_acceptance.json
research_ops/evidence_ledger.md
research_ops/rejected_results.md
```

Rerun acceptance validation manually with:

```bash
async-research result-acceptance \
  research_ops/tasks/TASK-0001-data-readiness \
  --ops-dir research_ops
```

Refresh reusable accepted-output memory:

```bash
async-research accepted update research_ops
```

Check accepted-memory freshness and write the revalidation schedule:

```bash
async-research accepted revalidation research_ops --write-schedule
```

The schedule is written to `research_ops/revalidation_schedule.md`. Treat rows
with `revalidation_status` `stale` as historical context only until a
revalidation task or human decision refreshes them.

Before a worker, planner, or discovery scout relies on a prior accepted task as
a current fact, check the artifact:

```bash
async-research accepted check-memory-use research_ops <artifact-path>
```

If it fails with `stale_accepted_memory_reuse`, create a bounded revalidation
task or route the item to `needs_human`.

If result acceptance fails:

- lower claim strength if the evidence cap is exceeded
- request a bounded revision with `revision_counter.py request`
- route to `needs_human` for public/high-stakes or strong claims
- reject if required artifacts are missing and cannot be recovered

## Archive Old Tasks

Archive only terminal tasks: `accepted`, `rejected`, `paused`, or `synthesized`.
Keep active tasks under `research_ops/tasks/`.

Recommended cadence: after 20 to 50 terminal tasks, move old terminal task
folders into:

```text
research_ops/archive/YYYY-MM/
```

Before moving anything:

```bash
async-research accepted update research_ops
async-research health research_ops --dry-run
git status --short
```

After archiving, update `queue.md`, `weekly_digest.md`, and
`accepted_outputs_index.md` so active work remains easy to scan.

## Daily Ready Check

Before enabling unattended scheduled jobs, this should pass:

```bash
async-research acceptance-suite
async-research simulate-week research_ops
async-research surface update research_ops
async-research surface validate research_ops
async-research schema-check research_ops
async-research readiness research_ops --dry-run
python -m async_research_workflow.scripts.escalation_policy scan-needs-human research_ops
async-research source freshness research_ops
async-research accepted revalidation research_ops --write-schedule
async-research queue discovery-gate research_ops --max-active 10
async-research health research_ops --dry-run
```

If any command fails, do not run autonomous jobs until the failure is resolved or
intentionally paused with a human decision row.

`simulate_scheduled_week.py` is a no-op rehearsal: it creates a temporary ops
copy, uses fixture/model-free outputs, and should report `external_api_calls=0`.
Use `--keep-work-dir` only when debugging the simulated artifacts.
