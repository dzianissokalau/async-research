# Phase 0 Contract Freeze

Status: delivered
Roadmap: `roadmaps/not_started_framework_simplification_strategy.md`
Date: 2026-05-25

## Phase Contract

Phase 0 freezes the behavior that the first simplification wave must preserve.
It is intentionally documentation and regression coverage only. It does not
move code out of `cli.py`, change parser registration, alter snapshot payloads,
or change starter workspace files.

## Non-Goals

- Do not remove the HTTP console or any public command family.
- Do not change `argparse` behavior, aliases, help output, JSON envelopes, exit
  codes, workspace file names, or task state values.
- Do not add runtime dependencies.
- Do not weaken source, freshness, claim, review, result-acceptance,
  accepted-memory, deliverable-maturity, readiness, or cost gates.
- Do not prune tests before replacement behavior contracts or golden fixtures
  exist.

## Public Parser Surface

The current parser order is load-bearing. `tests.test_cli_architecture` freezes
this top-level order:

```text
version
init
starter-smoke
acceptance-suite
readiness
health
surface
review-surface
console
schema-check
mode
workflow
queue
prompts
schedules
decision
escalation
source
data
library
runtime
eval
evidence-memory
model-routing
scaling
brief
cost
batch
metrics
accepted
outcomes
deliverable
anti-context
reflection
review
revision
result-acceptance
analysis
exploration
idea
experiment
benchmark
simulate-week
```

Nested public subcommands are also frozen by `tests.test_cli_architecture`:

| Command family | Public subcommands |
| --- | --- |
| `surface` | `update`, `validate` |
| `review-surface` | `update`, `validate` |
| `mode` | `show`, `set`, `validate` |
| `workflow` | `check`, `status`, `next`, `create-task`, `worker-start`, `worker-complete`, `advance` |
| `queue` | `discovery-gate`, `list` |
| `prompts` | `init`, `list`, `validate`, `draft`, `activate`, `diff` |
| `schedules` | `init`, `list`, `validate`, `upsert`, `set-status`, `trigger-dry-run`, `trigger-now` |
| `decision` | `append`, `check`, `resolve-task`, `auto-resolve-task`, `summarize` |
| `escalation` | `list`, `scan-needs-human`, `evaluate` |
| `source` | `init`, `upsert`, `validate`, `freshness`, `check-experiment`, `check-claim`, `explain` |
| `data` | `validate`, `dashboard`, `inspect-proposals`, `apply-proposals` |
| `library` | `init`, `validate`, `dashboard`, `inspect-proposals`, `apply-proposals` |
| `runtime` | `validate`, `summary`, `inspect-evidence`, `dry-run`, `execute` |
| `eval` | `build-from-traces`, `run`, `compare` |
| `evidence-memory` | `update`, `query` |
| `model-routing` | `init`, `validate`, `select`, `eval-check` |
| `scaling` | `assess` |
| `brief` | `draft`, `validate`, `apply` |
| `cost` | `summary`, `ingest-usage`, `budget-check` |
| `batch` | `init`, `validate-manifest`, `submit`, `complete`, `ingest`, `mark-reviewed`, `trust-status` |
| `metrics` | `append`, `summarize`, `operational` |
| `accepted` | `update`, `check-duplicate`, `check-memory-use`, `revalidation`, `revalidate` |
| `outcomes` | `refresh`, `list`, `summary` |
| `deliverable` | `init`, `target`, `critic`, `response`, `check` |
| `anti-context` | `build` |
| `reflection` | `record` |
| `review` | `draft`, `submit`, `prepare-context`, `install-context`, `aggregate` |
| `revision` | `defaults`, `request`, `inspect`, `scan-limits` |
| `analysis` | `dashboard`, `reviewer-packet`, `run-adapter`, `preflight`, `validate-run`, `validate-results` |
| `idea` | `score`, `validate`, `capture`, `promote`, `metrics`, `trace`, `resolve`, `park`, `reject`, `catalog` |
| `idea catalog` | `init`, `validate`, `list`, `dashboard`, `show`, `maintain` |

Aliases are contractual:

- `review-surface` is the same parser object as `surface`.
- `accepted revalidate` is the same parser object as `accepted revalidation`.
- `console snapshot` is accepted through the public `console` command and routes
  to the snapshot module without exposing a separate top-level command.

## Dispatch Target Inventory

This table records the current script module or CLI runner target at command
family granularity. Exact argv ordering is frozen by focused wrapper tests
before a family is moved.

| Public command or family | Current target |
| --- | --- |
| `version` | `run_version` in `cli.py` |
| `init` | `run_init` in `cli.py`; seeds metrics through `metrics_history append-snapshot` |
| `starter-smoke` | `run_starter_smoke` in `cli.py`; orchestrates schema, readiness, health, surface, source, cost, benchmark, and simulation checks |
| `acceptance-suite` | `run_acceptance_suite` script |
| `readiness` | `autonomy_readiness_gate` script |
| `health` | `health_check` script |
| `surface`, `review-surface` | `human_review_surface` script |
| `console` | `console.server`; `console snapshot` routes to `console.snapshot` |
| `schema-check` | `check_schema_versions` script |
| `mode` | `interaction_mode` script |
| `workflow` | `workflow_orchestrator` script, except `create-task` routes to `task_authoring` |
| `queue` | `queue_capacity` script |
| `prompts` | `prompt_library` script |
| `schedules` | `schedule_manifest` script |
| `decision` | `human_decision_log` script |
| `escalation` | `escalation_policy` script |
| `source` | `data_source_audit` script |
| `data` | `data_foundations`, `data_proposal_inspection`, and `data_proposal_apply` scripts |
| `library` | `knowledge_library`, `library_proposal_inspection`, and `library_proposal_apply` scripts |
| `runtime` | `runtime_artifacts` and `runtime_adapters` scripts |
| `eval` | `runtime_evals` script |
| `evidence-memory`, `reflection` | `evidence_memory` script |
| `model-routing` | `model_routing` script |
| `scaling` | `scaling_state` script |
| `brief` | `research_brief` script |
| `cost` | `cost_tracking` script |
| `batch` | `batch_lifecycle` script |
| `metrics` | `metrics_history` script |
| `accepted` | `update_accepted_outputs_index` script |
| `outcomes` | outcome refresh/list/summary runner in `cli.py` |
| `deliverable` | `deliverable_maturity` script |
| `anti-context` | `generate_anti_context` script |
| `review` | `review_authoring`, `prepare_review_context`, and `aggregate_reviews` scripts |
| `revision` | `revision_counter` script |
| `result-acceptance` | `validate_result_acceptance` script |
| `analysis` | `analysis_surface`, `analysis_adapters`, `analysis_runs`, and `analysis_validation` scripts |
| `exploration` | `validate_exploration_cycle` script |
| `idea` | `score_idea_candidate`, `validate_idea_evaluation`, and `idea_catalog` scripts |
| `experiment` | `validate_experiment_plan` script |
| `benchmark` | `run_autonomy_benchmark` script |
| `simulate-week` | `simulate_week` script |

## Exit Codes And JSON Envelopes

The global help epilog and README command-specific exit table are the frozen
contract. The common public meanings are:

| Code | Meaning |
| ---: | --- |
| 0 | success |
| 1 | suite or smoke failure |
| 2 | validation failed, warning, lock contention, budget threshold, or skip depending on command |
| 3 | missing required input, invalid request, stale preflight, or skip loop depending on command |
| 4 | malformed input, invalid state, write failure, or safe refusal |
| 5 | human action required |

Runtime command output is JSON unless the command is help or usage output.
Non-OK JSON payloads must keep structured failure fields such as `ok`,
`reason`, `errors`, `failures`, or command-specific warning rows.

Phase 1 through Phase 3 must preserve these envelopes in particular:

| Surface | Envelope contract |
| --- | --- |
| `init` | JSON result with `ok`, target/template details, `changed`, and failure details on safe refusal or rollback. |
| `starter-smoke` | One JSON envelope containing `init` and `smoke` results. |
| `console snapshot --json` | Top-level `console_snapshot_v1.0` payload; invalid `--now` returns code 3 with structured JSON. |
| `cost` | Backing `cost_tracking` JSON is passed through by the wrapper. |
| `accepted` | Backing `update_accepted_outputs_index` JSON is passed through by the wrapper. |
| `scaling` | Backing `scaling_state` JSON is passed through by the wrapper. |

## Reads, Writes, And Dry-Run Contracts

The README command map remains the broad operator contract for reads and writes.
The first simplification wave must preserve these high-value write boundaries:

| Area | Read/write contract |
| --- | --- |
| Workspace truth | `research_ops/` remains file-backed source of truth; no hidden database state. |
| `init` | Writes the target workspace and seeded metrics files; refuses existing non-empty targets unless forced. |
| `starter-smoke` | Writes only the requested disposable smoke target; forced runs may replace that target. |
| `console snapshot` | Read-only; never mutates `research_ops/`. |
| `workflow` read commands | `check`, `status`, and `next` are read-only JSON reports. |
| `workflow advance` | Dry-run is read-only; non-dry-run may write review panels, ledgers, accepted-memory files, surfaces, and health outputs through existing backing commands. |
| `cost summary` | Read-only JSON report. |
| `cost ingest-usage` | `--dry-run` is read-only; without it appends to `cost_ledger.csv` or an override ledger. |
| `cost budget-check` | Read-only gate; exits nonzero when projected spend crosses threshold. |
| `accepted update` | Rebuilds `accepted_outputs_index.md`. |
| `accepted revalidation` | Read-only unless `--write-schedule` writes `revalidation_schedule.md`. |
| Proposal apply commands | Dry-run is default; writes require accepted proof and matching preflight hash. |

## First CLI Runner Slice

Phase 1 should migrate `cost` first unless new evidence changes the choice. It
is low-risk because it is a small command family that delegates to one backing
script module and uses common option builders.

The frozen module target is `async_research_workflow.scripts.cost_tracking`.
The wrapper argv contracts are now covered by
`CliArchitectureTests.test_cost_command_family_routes_to_public_helper_contract`:

| Public command | Backing module argv contract |
| --- | --- |
| `cost summary` | `["summary", ops_dir, optional --ledger, optional budgets]` |
| `cost ingest-usage` | `["ingest-usage", ops_dir, required usage/item/role/model/pricing fields, optional api/notes/date/ledger, optional --dry-run, optional budgets]` |
| `cost budget-check` | `["budget-check", ops_dir, item/action/proposed-cost/threshold fields, optional --ledger, optional budgets]` |

## Snapshot Contract

`tests.test_console_snapshot.SNAPSHOT_GROUPS` freezes the required top-level
snapshot groups:

```text
workspace, readiness, health, tasks, human_decisions, accepted_outputs,
delivered_projects, deliverables, interaction_mode, auto_decisions,
rejected_results, cost, sources, prompts, schedules, ideas, data, library,
analysis, lifecycle, runs, runtime, evals, warnings
```

Known snapshot fixtures before Phase 3:

| Fixture | Test coverage |
| --- | --- |
| Fresh starter | `test_snapshot_renders_generic_starter_without_mutating_files` |
| Task awaiting review | `test_snapshot_contract_covers_awaiting_review_fixture_without_mutating_files` |
| Needs-human task | `test_snapshot_uses_consistent_task_shape_for_human_items` and mode-policy tests |
| Accepted evidence | `test_lifecycle_maps_coffee_pilot_style_path`, `test_task_detail_surfaces_coffee_style_explainability_and_qa`, stale accepted-memory tests |
| Missing or malformed optional groups | malformed task, missing foundations, missing workspace, invalid interaction mode, and invalid `--now` tests |

Phase 3 may split collectors, but the top-level payload shape, read-only
behavior, and fail-closed warning model must stay stable.

## Init And Starter-Smoke Contract

Phase 2 must preserve:

- `init` target safety checks, forced replacement behavior, template names, JSON
  result shape, metrics seeding, and rollback reporting.
- `starter-smoke` check ordering and JSON envelope containing initializer and
  smoke results.
- Packaged resource names and copied `research_ops/` file names.

Existing contract tests before Phase 2:

- `tests.test_packaged_resources`
- `tests.test_cli_safety`
- `tests.test_console_snapshot.ConsoleSnapshotTests.init_ops`

## Out Of Scope For First Wave

- Command deprecation or removal belongs to Phase 5.
- Typer, jsonschema, and filelock decisions belong to Phase 6.
- Test pruning belongs to Phase 7.
- Proposal engine consolidation belongs to Phase 4 and requires at least two
  proven concrete flows before extracting a shared engine.
