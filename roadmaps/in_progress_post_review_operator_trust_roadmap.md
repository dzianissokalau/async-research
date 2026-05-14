# Post-Review Operator Trust And Workflow Roadmap

Status: In Progress
Current phase: Phase 1 - Minimum operator path
Last updated: 2026-05-14
Next action: Add workflow next <ops-dir>
Blocked by: None

Created: 2026-05-13

## Summary

This roadmap turns the May 13, 2026 external workflow reviews into one active
implementation track. The reviewed inputs were:

- Claude end-to-end workflow review
- Deep Research assessment
- Manus dashboard testing report
- Manus framework workflow review

The reviews agree on the same core diagnosis: the framework is much stronger
than a typical alpha in validation, safety gates, packaged starters, dashboard
visibility, and simulation coverage. The remaining risk is not another large
subsystem. It is operator trust and path clarity.

The next work should make the normal workflow hard to misuse:

- audit logs must stay structurally correct
- review commands should refuse premature task states
- operators need direct status and next-step commands
- worker state transitions need a public wrapper
- idea capture and promotion need less manual JSON knowledge
- docs, release signals, and worked examples need to match the quality of the
  implemented safety model

## Review Synthesis

### What Is Working

- `init`, `schema-check`, `readiness`, `health`, `surface update`, and
  `surface validate` form a strong first-run path.
- `workflow check`, dashboard snapshot, local console, outcomes, and generated
  human surfaces give good operational visibility.
- Idea catalog promotion is safe when used correctly: dry-runs produce
  preflight hashes, write mode requires matching hashes, task folders and queue
  rows are created with provenance, and blocked promotions fail closed.
- Source governance, data foundations, knowledge library, accepted memory,
  result acceptance, simulation, benchmark, and acceptance-suite checks are
  credible and useful.
- The dashboard substantially improves operator visibility and validates the
  local-first control-plane direction.

### Main Weaknesses

- `decisions.md` can be written with rows that do not match the starter header,
  causing visible audit-column misalignment.
- `review submit` can write a review before a task is truly reviewable, such as
  when the task is still `ready_for_worker` and `worker_output.md` is absent.
- There is no public command for the normal worker transition path:
  `ready_for_worker -> in_progress -> awaiting_review`.
- There is no direct `workflow status` or `workflow next` command that tells an
  operator where one task or workspace stands and what command to run next.
- `queue` only exposes `discovery-gate`; reviewers expected a simple queue or
  task list.
- Idea capture and promotion are safe but still too implicit for new operators.
  One reviewer completed the path cleanly; another needed manual JSON editing
  after hitting `needs_human`, hard-gate, syntax, and task-id collision
  blockers.
- `starter-smoke` emits two top-level JSON objects, which is awkward for JSON
  consumers.
- `prompts init` lacks `--dry-run`, unlike nearby initializer commands.
- Public release and adoption signals still lag the product ambition: PyPI,
  releases, badges, visible hardening reports, more worked examples, and scaling
  guidance are future adoption work.

## Roadmap Principles

- Fix correctness and trust issues before adding more product breadth.
- Prefer public wrappers around existing validated helpers over hand-editing
  JSON or exposing internal scripts.
- Keep guards fail-closed, but make blockers explain the next legal action.
- Preserve the file-backed source-of-truth model. Dashboards and generated
  indexes remain derived surfaces.
- Treat new write paths as transaction-protected and test them against both
  starter templates.
- Use the existing Future Improvements Backlog for V2 apply paths, but promote
  only focused items into implementation when the operator path is stable.

## Phased Plan

| Phase | Focus | Scope | Exit Criteria |
| ---: | --- | --- | --- |
| 0 | Audit correctness and review guardrails | Fix decision-log writes and add review-submit preflight guards. | Starter decision rows align with headers; premature review submission fails closed or requires explicit override. |
| 1 | Minimum operator path | Add `workflow status`, `workflow next`, public worker transition wrappers, and queue/task listing. | A solo operator can inspect a task/workspace and see the next safe command without opening raw JSON. |
| 2 | Idea lifecycle ergonomics | Add decision-backed idea lifecycle commands and better capture/promote diagnostics. | Common `needs_human` idea states can be resolved without manual JSON edits; blocked promotion messages identify concrete remedies. |
| 3 | JSON/help consistency polish | Normalize `starter-smoke` output, add `prompts init --dry-run`, and sharpen help/examples. | Setup and smoke commands are easier for scripts and LLMs to consume consistently. |
| 4 | Delivered-feature V2 adoption | Add dashboard polish and runnable examples for experiment/analysis paths. | Delivered features have practical examples, not only contracts and dashboard read models. |
| 5 | Public adoption and release trust | Improve release, packaging, docs, worked examples, and scaling guidance. | External users can install, verify, and evaluate the framework with fewer trust gaps. |

## Prioritized Improvements

| Priority | Phase | Improvement | Description | Impact | Status |
| --- | ---: | --- | --- | --- | --- |
| P0 | 0 | Fix `decisions.md` writer/header mismatch | Make decision writes match the existing Markdown table header, or migrate starter templates to the canonical header. Add regression tests for generic and real-estate starters plus append and resolve-task paths. | Protects the durable human decision audit trail and removes the most concrete correctness bug found by external testing. | Complete |
| P1 | 0 | Add review-submit state guard | Make review authoring writes refuse when the task is not reviewable, with no Phase 0B override. Guard at minimum on task status and non-empty `worker_output.md`. | Prevents premature reviews and makes the review lifecycle harder for humans or LLMs to misuse. | Complete |
| P1 | 1 | Add `workflow status <task-dir>` | Print current status, previous status, type, lock state, worker-output presence, review files, human gate, revision count, result state, and next legal task-level commands. | Gives operators and agents a single task truth surface instead of requiring raw `status.json` inspection. | Complete |
| P1 | 1 | Add `workflow next <ops-dir>` | Read the workspace snapshot and recommend the next safe command, such as check health, resolve a human gate, run a review, update surfaces, or inspect a blocked task. | Turns a broad CLI into a guided operating loop and reduces first-user abandonment. | Planned |
| P1 | 1 | Add public worker transition wrapper | Add `workflow worker-start/worker-complete`, `task claim/complete`, or equivalent around existing lock and transition helpers for `ready_for_worker -> in_progress -> awaiting_review`. | Closes the biggest solo-operator gap between planning and review without teaching users internal helpers. | Planned |
| P1 | 2 | Smooth idea lifecycle resolution | Add explicit decision-backed commands for common blocked idea states, such as approving completed capture, updating allowed hard-gate outcomes, or moving a valid idea from `needs_human` to a promotable state. | Makes idea discovery/catalog usable by new operators without manual JSON edits while preserving hard gates. | Planned |
| P2 | 1 | Add `queue list` or equivalent | Add a read-only queue/task listing command, or make `workflow status/next` cover this need clearly. | Resolves a documentation/expectation mismatch and improves visibility into active work. | Planned |
| P2 | 2 | Improve `idea capture` and `idea promote` guidance | Add clearer help text, examples, blocked-promotion `next_step` guidance, and specific task-id collision diagnostics. | Keeps the existing safety model but reduces syntax and blocker confusion. | Planned |
| P2 | 3 | Normalize `starter-smoke` JSON output | Wrap init and smoke results in one JSON envelope rather than emitting two top-level JSON objects. | Makes smoke output easier for CI, shell tools, LLMs, and dashboards to parse. | Planned |
| P2 | 3 | Add `prompts init --dry-run` | Align prompt initialization with `library init`, `idea catalog init`, and `schedules init`. | Reduces setup surprise and keeps initializer command semantics consistent. | Planned |
| P2 | 4 | Dashboard polish | Add optional auto-refresh, improve local-file link handling, and check desktop-first responsive behavior. | Improves the daily operator experience on top of an already useful dashboard. | Backlog |
| P2 | 4 | Add runnable experiment and analysis examples | Add small fixtures that exercise `experiment validate`, `analysis preflight`, `analysis validate-run`, and `analysis validate-results`. | Makes the delivered Hypothesis Testing Framework feel practical end to end, not only contract-complete. | Backlog |
| P3 | 5 | Publish release-trust assets | Prepare PyPI/release flow, badges, visible hardening report, and versioned documentation guidance when the operator path is stable. | Improves external credibility and lowers adoption friction. | Backlog |
| P3 | 5 | Add more vertical worked examples | Add one or two full templates beyond real estate, such as market intelligence, policy scanning, literature review, or due diligence. | Clarifies market fit and helps users evaluate the framework in concrete workflows. | Backlog |
| P3 | 5 | Document scaling boundaries | Explain expected file-backed workspace scale, linear-scan tradeoffs, and when to graduate to heavier orchestration. | Prevents overextension of the local-file model and sets honest expectations. | Backlog |

## Phase 0 Implementation Notes

Phase 0 is a correctness and trust slice. It should be implemented before
broader operator-navigation commands.

### Decision Log Fix

Candidate approaches:

1. Migrate both starters to the canonical 6-column header and keep writer
   output unchanged.
2. Make the writer detect the active header and render rows in that header's
   shape.
3. Combine both: migrate starters for new workspaces and make writer tolerant of
   legacy headers for existing workspaces.

Preferred approach: combine both. New workspaces should use the canonical
header, while existing workspaces should not be corrupted when they still have a
legacy header.

Acceptance:

- `decision append` writes aligned rows for a fresh generic starter.
- `decision resolve-task` writes aligned rows for a fresh real-estate starter.
- existing legacy 7-column logs remain readable and writable without column
  drift.
- existing week-simulation legacy logs remain readable.
- `surface update` and `decision summarize` consume the resulting log
  correctly.

### Review Submit Guard

The review authoring commands should validate task readiness before writing.

Initial guard:

- accepted statuses: `awaiting_review`, `single_review`, `panel_review`
- `worker_output.md` must exist and be non-empty
- existing review file still requires `--force` for replacement
- Phase 0B does not add an override. Premature `review submit` is refused; a
  safety override can be designed later if real operator usage needs it.

Acceptance:

- `review submit` fails closed for `ready_for_worker` without
  `worker_output.md`.
- `review submit --dry-run` returns the same guard result without writing.
- valid `awaiting_review` tasks with non-empty `worker_output.md` still work.
- regression tests cover generic and real-estate task fixtures.

## Phase 1 Implementation Notes

Phase 1 should make the framework easier to drive without weakening its state
machine.

### `workflow status`

Return structured JSON plus concise human-readable fields if the existing CLI
style allows. It should be read-only.

Minimum fields:

- task id and path
- status and previous status
- task type and review tier
- lock state and stale-lock hint
- worker output presence
- review file presence by role
- human gate reason
- revision count and max revisions
- result claim strength and claim-staleness state
- next legal commands

Shipped behavior:

- `async-research workflow status <task-dir>` is read-only and returns JSON.
- The task must live directly under the inferred or explicit matching
  `research_ops/tasks/` folder.
- Missing, malformed, schema-invalid, or transition-invalid status files return
  exit code 4 with schema/workflow-check recovery commands.
- Reviewable tasks report worker-output readiness, required/missing/invalid
  review files, aggregate artifact presence, and safe review/advance commands.
- `needs_human` tasks surface the human gate and suggest
  `decision resolve-task` dry-run/write commands rather than direct status
  edits.

### `workflow next`

Return one recommended next action plus lower-priority alternatives. It should
use existing read models instead of inventing a separate scheduler.

Suggested priority order:

1. malformed state or failed schema check
2. unresolved `needs_human`
3. active locks or stale locks
4. task ready for review but missing review start/aggregation
5. task ready for worker
6. due accepted-memory revalidation
7. source/data/library warnings requiring operator attention
8. safe maintenance actions such as `surface update`

### Worker Transition Wrapper

The wrapper should call existing transition and lock primitives rather than
editing `status.json` directly.

Candidate command names:

```bash
async-research workflow worker-start <task-dir>
async-research workflow worker-complete <task-dir>
```

Open decision: whether this should also write or validate `worker_output.md`,
or only transition state after the worker output is already present.

## Integration With Existing Roadmaps

- Public Alpha Hardening is delivered. This roadmap is its dogfood maintenance
  successor for correctness and trust issues.
- Operator UX And Workflow Ergonomics is delivered. This roadmap adds the next
  generation of operator commands discovered by May 13 reviews.
- Dashboard Delivery is delivered. Dashboard polish remains a later phase here,
  not the immediate critical path.
- Hypothesis Testing Framework is delivered. Runnable experiment/analysis
  examples move to Phase 4 so contract-complete features become easier to
  evaluate.
- Future Improvements Backlog remains the holding area for larger V2 apply
  paths, such as data/library proposal apply commands and richer import helpers.

## Verification Plan

Every implementation slice should run:

```bash
.venv/bin/python -m unittest tests.test_doc_references
.venv/bin/python -m unittest discover -s tests
.venv/bin/async-research acceptance-suite
```

Targeted tests should be added for each phase before marking it complete.

## Open Decisions

- Should the public worker wrapper be `workflow worker-*`, `task claim/complete`,
  or a different command group?
- Should `workflow next` emit only JSON, or support a compact text mode for
  humans?
- Should `queue list` be a real command, or should `workflow next/status` make
  it redundant?
- What is the safest lifecycle command for approving a `needs_human` captured
  idea without letting operators bypass scoring and hard gates too easily?
