# Phase 5 Command Normalization Design

Status: delivered
Roadmap: `roadmaps/in_progress_framework_simplification_strategy.md`
Date: 2026-05-25

## Phase Contract

Phase 5 classifies the public command surface without removing or renaming any
operator command. It is a migration design and documentation slice only. Public
CLI behavior, aliases, help shape, JSON envelopes, exit codes, workspace file
formats, and documented side effects remain unchanged.

## Non-Goals

- Do not remove any public command, subcommand, alias, or documented command
  family.
- Do not turn the HTTP console or any fail-closed gate into an internal-only
  surface.
- Do not add runtime dependencies.
- Do not emit deprecation warnings until a later implementation slice updates
  README examples and tests in the same change.
- Do not rename `research_ops/` files or task state values.

## Classification Rules

| Classification | Meaning | Phase 5 action |
| --- | --- | --- |
| Keep | Canonical public operator command. | Preserve command and examples. |
| Alias | Supported public spelling that routes to a canonical command. | Preserve alias; prefer canonical spelling in new examples. |
| Deprecate | Public command scheduled for removal or behavior narrowing after a warning period. | None active in Phase 5. A future slice must print a replacement or rationale. |
| Internal | Advanced helper entrypoint, not the public operator interface. | Keep out of promoted docs unless explicitly labeled advanced/internal. |

## Migration Table

| Current surface | Phase 5 status | Canonical replacement | Operator action |
| --- | --- | --- | --- |
| Public command deprecations | None active | Not applicable | No command changes are required. |
| `async-research review-surface` | Alias | `async-research surface` | Existing usage remains supported; new examples should prefer `surface`. |
| `async-research review-surface update` | Alias | `async-research surface update` | Existing usage remains supported; new examples should prefer `surface update`. |
| `async-research review-surface validate` | Alias | `async-research surface validate` | Existing usage remains supported; new examples should prefer `surface validate`. |
| `async-research accepted revalidate` | Alias | `async-research accepted revalidation` | Existing usage remains supported; new examples should prefer `accepted revalidation`. |
| Direct `python -m async_research_workflow.scripts.<module>` calls | Internal | Public `async-research ...` commands | Use only in advanced/internal docs with that label. |

## Deprecation Requirements For Future Slices

Any later command deprecation must ship all of these in the same slice:

1. The old command remains callable for a deprecation period.
2. The old command prints or returns a specific replacement or rationale.
3. README examples and command-map rows are updated in the same change.
4. CLI help tests assert the warning and replacement text.
5. Documentation-reference tests prevent promoted docs from using the old
   command after migration.

## Public Command Classification

All rows below are generated from the Phase 5 parser surface and Phase 0
contract. `console snapshot` is included because it is a documented public mode
of the `console` command even though it is dispatched inside the console runner.

| Command family | Classification | Commands covered |
| --- | --- | --- |
| Version and workspace setup | Keep | `async-research version`; `async-research init`; `async-research starter-smoke`; `async-research acceptance-suite` |
| Operational gates | Keep | `async-research readiness`; `async-research health`; `async-research schema-check`; `async-research mode`; `async-research mode show`; `async-research mode set`; `async-research mode validate` |
| Human review surface | Keep plus supported alias | `async-research surface`; `async-research surface update`; `async-research surface validate`; alias `async-research review-surface`; alias `async-research review-surface update`; alias `async-research review-surface validate` |
| HTTP console | Keep | `async-research console`; `async-research console snapshot` |
| Workflow orchestration | Keep | `async-research workflow`; `async-research workflow check`; `async-research workflow status`; `async-research workflow next`; `async-research workflow create-task`; `async-research workflow worker-start`; `async-research workflow worker-complete`; `async-research workflow advance` |
| Queue controls | Keep | `async-research queue`; `async-research queue discovery-gate`; `async-research queue list` |
| Prompt library | Keep | `async-research prompts`; `async-research prompts init`; `async-research prompts list`; `async-research prompts validate`; `async-research prompts draft`; `async-research prompts activate`; `async-research prompts diff` |
| Schedule intent | Keep | `async-research schedules`; `async-research schedules init`; `async-research schedules list`; `async-research schedules validate`; `async-research schedules upsert`; `async-research schedules set-status`; `async-research schedules trigger-dry-run`; `async-research schedules trigger-now` |
| Human decisions | Keep | `async-research decision`; `async-research decision append`; `async-research decision check`; `async-research decision resolve-task`; `async-research decision auto-resolve-task`; `async-research decision summarize` |
| Escalation policy | Keep | `async-research escalation`; `async-research escalation list`; `async-research escalation scan-needs-human`; `async-research escalation evaluate` |
| Source governance | Keep | `async-research source`; `async-research source init`; `async-research source upsert`; `async-research source validate`; `async-research source freshness`; `async-research source check-experiment`; `async-research source check-claim`; `async-research source explain` |
| Data foundations | Keep | `async-research data`; `async-research data validate`; `async-research data dashboard`; `async-research data inspect-proposals`; `async-research data apply-proposals` |
| Knowledge library | Keep | `async-research library`; `async-research library init`; `async-research library validate`; `async-research library dashboard`; `async-research library inspect-proposals`; `async-research library apply-proposals` |
| Runtime evidence | Keep | `async-research runtime`; `async-research runtime validate`; `async-research runtime summary`; `async-research runtime inspect-evidence`; `async-research runtime dry-run`; `async-research runtime execute` |
| Evaluation flywheel | Keep | `async-research eval`; `async-research eval build-from-traces`; `async-research eval run`; `async-research eval compare` |
| Evidence memory and reflection | Keep | `async-research evidence-memory`; `async-research evidence-memory update`; `async-research evidence-memory query`; `async-research reflection`; `async-research reflection record` |
| Model routing | Keep | `async-research model-routing`; `async-research model-routing init`; `async-research model-routing validate`; `async-research model-routing select`; `async-research model-routing eval-check` |
| Scaling assessment | Keep | `async-research scaling`; `async-research scaling assess` |
| Research briefs | Keep | `async-research brief`; `async-research brief draft`; `async-research brief validate`; `async-research brief apply` |
| Cost gates | Keep | `async-research cost`; `async-research cost summary`; `async-research cost ingest-usage`; `async-research cost budget-check` |
| Batch lifecycle | Keep | `async-research batch`; `async-research batch init`; `async-research batch validate-manifest`; `async-research batch submit`; `async-research batch complete`; `async-research batch ingest`; `async-research batch mark-reviewed`; `async-research batch trust-status` |
| Metrics | Keep | `async-research metrics`; `async-research metrics append`; `async-research metrics summarize`; `async-research metrics operational` |
| Accepted memory | Keep plus supported alias | `async-research accepted`; `async-research accepted update`; `async-research accepted check-duplicate`; `async-research accepted check-memory-use`; `async-research accepted revalidation`; alias `async-research accepted revalidate` |
| Outcomes | Keep | `async-research outcomes`; `async-research outcomes refresh`; `async-research outcomes list`; `async-research outcomes summary` |
| Deliverable maturity | Keep | `async-research deliverable`; `async-research deliverable init`; `async-research deliverable target`; `async-research deliverable critic`; `async-research deliverable response`; `async-research deliverable check` |
| Anti-context | Keep | `async-research anti-context`; `async-research anti-context build` |
| Review authoring and aggregation | Keep | `async-research review`; `async-research review draft`; `async-research review submit`; `async-research review prepare-context`; `async-research review install-context`; `async-research review aggregate` |
| Revision limits | Keep | `async-research revision`; `async-research revision defaults`; `async-research revision request`; `async-research revision inspect`; `async-research revision scan-limits` |
| Result acceptance | Keep | `async-research result-acceptance` |
| Analysis workflows | Keep | `async-research analysis`; `async-research analysis dashboard`; `async-research analysis reviewer-packet`; `async-research analysis run-adapter`; `async-research analysis preflight`; `async-research analysis validate-run`; `async-research analysis validate-results` |
| Exploration and experiments | Keep | `async-research exploration`; `async-research exploration validate`; `async-research experiment`; `async-research experiment validate` |
| Idea lifecycle | Keep | `async-research idea`; `async-research idea score`; `async-research idea validate`; `async-research idea capture`; `async-research idea promote`; `async-research idea metrics`; `async-research idea trace`; `async-research idea resolve`; `async-research idea park`; `async-research idea reject` |
| Idea catalog | Keep | `async-research idea catalog`; `async-research idea catalog init`; `async-research idea catalog validate`; `async-research idea catalog list`; `async-research idea catalog dashboard`; `async-research idea catalog show`; `async-research idea catalog maintain` |
| Benchmark and simulation | Keep | `async-research benchmark`; `async-research simulate-week` |

## Internal Helper Boundary

No public `async-research` command is reclassified as internal in Phase 5.
Internal classification applies only to advanced/internal helper entrypoints such
as `python -m async_research_workflow.scripts.task_lock` or
`python -m async_research_workflow.scripts.metrics_history init`. Promoted docs
should route operators through public command families unless a helper call is
explicitly marked advanced/internal.

## Deferred Candidates

The following are candidates for future command normalization, not active
deprecations:

- Prefer canonical spelling in new examples: `surface` over `review-surface`
  and `accepted revalidation` over `accepted revalidate`.
- Consider grouping low-level proposal inspection/apply examples under data and
  library runbooks after dogfood shows the current wording is confusing.
- Consider hiding more direct script-module references from promoted docs while
  keeping advanced/internal runbooks for maintainers.
- Revisit command deprecation only after usage evidence, warning UX, and README
  example migrations are ready.
