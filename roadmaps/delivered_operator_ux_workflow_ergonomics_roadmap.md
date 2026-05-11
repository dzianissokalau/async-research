# Operator UX And Workflow Ergonomics Roadmap

Status: Delivered
Current phase: Complete
Last updated: 2026-05-11
Next action: Monitor operator dogfood feedback and patch regressions
Blocked by: None

Created: 2026-05-09

## Summary

This roadmap captures follow-ups from the May 9, 2026 Manus framework review.
The review says the framework's core safety architecture is strong: file-backed
state, strict transitions, reviewer isolation, source governance, accepted
memory, anti-context, exit-code contracts, and `simulate-week` should all stay.

The remaining risk is adoption friction. A careful operator can run the system,
but too much of the happy path still requires knowing internal vocabulary,
opening long docs, or invoking advanced helper commands. This roadmap turns
those findings into focused implementation slices.

This is an adoption and ergonomics roadmap, not a replacement for the
Hypothesis Testing Framework roadmap. HTF was delivered on 2026-05-10, so the
sequencing question is resolved and Operator UX is now the active adoption
track.

Delivered on 2026-05-11. Follow-up dashboard implementation continues in the
Dashboard Delivery roadmap.

## Execution Decisions

P1 stays narrow: make review authoring public without weakening review
isolation, review-start transitions, or deterministic aggregation.

Review authoring command contract:

- `async-research review draft <task-dir> --role primary` previews a
  conservative `needs_human` fenced JSON scaffold by default.
- `review draft --write` writes `reviews/<role>.md`.
- `async-research review submit <task-dir> --role primary --decision <decision>
  --claim-strength <claim_strength> --confidence <0-1>` validates explicit
  flags and writes `reviews/<role>.md`.
- `review submit --dry-run` validates and previews the review without writing.
- both commands protect existing role review files unless `--force` is
  explicit.
- direct `review_template` remains an advanced/internal helper behind the public
  wrappers.

Exit code contract:

- `0`: scaffold previewed/written or review submitted
- `2`: generated review payload failed review validation
- `3`: missing or invalid review flags
- `4`: missing or malformed task/status input
- `5`: target review file exists without `--force`

Non-goals for P1:

- no automatic review-start status transition
- no aggregator behavior change
- no mutation of sibling review files
- no dashboard or workflow orchestration behavior

## Manus Review Synthesis

### Keep

- File-backed `research_ops/` as the source of truth.
- Strict state machine and fail-closed transition validation.
- Structural reviewer isolation.
- Deterministic JSON CLI with documented exit codes.
- Source audit, data foundations, knowledge library, idea catalog, accepted
  memory, anti-context, cost controls, and `simulate-week`.
- Generic starter plus worked example template.

### Incorporate

- First-class public review authoring commands.
- A tiny first-success quickstart.
- A local dashboard path that starts read-only.
- A workflow orchestrator for the canonical post-worker loop.
- Discovery inbox robustness for non-canonical rows.
- Operational metrics for time-in-state and cost/review trends.
- Later policy cleanup for Tier 0 review and docs packaging.

### Do Not Rush

- Do not weaken the explicit `awaiting_review -> single_review/panel_review`
  transition.
- Do not remove the Knowledge Library now that it is delivered and integrated.
  Improve examples and first-user guidance instead.
- Do not split packaged protocol docs out of the wheel until measured install
  footprint or user confusion makes it worth the complexity.

## Priority Plan

| Priority | Item | Why | Acceptance |
| --- | --- | --- | --- |
| P1 | Review authoring UX | Hand-written review files are the highest-friction part of the manual loop. | Public commands generate and validate review scaffolds without requiring direct `python -m ...review_template` use. |
| P1 | One-page quickstart | The README is thorough but too dense for a first successful run. | A short quickstart shows one path from init to readiness, review aggregation, accepted update, and surface update. |
| P1/P2 | Dashboard MVP coordination | Manus identifies observability as the main missing operator surface. | Dashboard roadmap slices 1-2 are explicitly tied to this roadmap and remain read-only first. |
| P2 | Workflow orchestrator | Operators currently copy a multi-command worked loop. | A public command can run or dry-run the canonical safe sequence while preserving individual command contracts. |
| P2 | Discovery inbox robustness | Free-form inbox rows can confuse capture. | Capture and validation explain non-canonical rows and avoid silent `row_not_found` confusion. |
| P2 | Operational metrics | JSONL metrics exist, but operators need trends that answer whether the loop is improving. | Metrics expose time-in-state, review latency, human-decision latency, and cost per accepted output where data exists. |
| P3 | Tier 0 review policy | Tier 0 is conceptually present but weakly surfaced. | Decide whether to hide, remove, or replace Tier 0 with an explicit review-skip decision. |
| P3 | Docs packaging review | Packaged protocol docs are useful but large. | Revisit only with install-size data or repeated user confusion. |

## Delivery Strategy

Deliver ergonomics as small public-command slices. Each slice should preserve
the existing file-backed workflow and leave direct lower-level helpers available
only as advanced/internal building blocks.

Recommended sequence:

1. Resolve command names and safety boundaries.
2. Add public review authoring commands.
3. Add a one-page first-success quickstart using only public commands.
4. Coordinate read-only dashboard MVP slices.
5. Add workflow orchestration only after the manual public path is clear.
6. Harden discovery inbox errors.
7. Add operational metrics read models.
8. Clean up Tier 0 and docs packaging policy after the higher-friction items.

Delivery boundary:

- MVP: Phases 0 through 2. This is command shape, review authoring UX, and a
  one-page quickstart.
- V1 post-MVP: Phases 3 through 6. This adds dashboard coordination, workflow
  orchestration, discovery robustness, and operational metrics.
- V2: Phase 7 policy cleanup and any future mutation-capable dashboard work.

## Progress

Last updated: 2026-05-11

| Phase | Step | Status | Description | Evidence / Notes |
| ---: | --- | --- | --- | --- |
| 0 | Decisions and command shape | Complete | Resolve HTF sequencing, public command names, review authoring write rules, non-goals, and exit codes. | HTF is delivered; this roadmap now defines public `review draft` and `review submit` behavior plus the P1 non-goals. |
| 1 | Review authoring UX | Complete | Add public commands around existing review-template and review-validation logic. | Adds `async-research review draft` and `async-research review submit`, JSON output, schema-validated task status preflight, atomic non-force write protection, docs, help coverage, and regression tests for preview, write, target-exists, missing role, invalid status, role mismatch, race protection, and aggregate use. |
| 2 | One-page quickstart | Complete | Add the first-success quickstart after P1 commands are available. | Adds packaged `first_success_quickstart.md`, links it from the README and docs index, keeps the page short, uses only public `async-research` commands, and adds doc-reference tests for the command path and deep-doc links. |
| 3 | Dashboard MVP coordination | Complete | Tie dashboard slices 1-2 to this adoption roadmap while keeping dashboard read-only first. | Dashboard roadmap is now `In Progress`, owns implementation for slices 1-2, defines the read-only MVP snapshot contract, forbids mutation endpoints before Slice 3 setup actions, and has doc-reference coverage for the coordination boundary. |
| 4 | Workflow orchestrator | Complete | Add a public orchestrator for the canonical post-worker loop without removing individual commands. | Adds `async-research workflow check` and `async-research workflow advance`, dry-run-only read checks, mutating subcommand reporting, warning-only readiness handling, fail-closed stopping, README/prompt docs, and regression tests for accepted, needs_revision, needs_human, dry-run, and invalid-state paths. |
| 5 | Discovery inbox robustness | Complete | Improve capture diagnostics for non-canonical discovery inbox rows. | Adds discovery-inbox-only warnings for non-canonical free-form lines with line numbers, richer `idea capture --from-inbox` not-found JSON with valid selectors and nearby candidate rows, docs, and regression tests proving free-form text is never captured automatically. |
| 6 | Operational metrics | Complete | Add read models for review latency, human-decision latency, and cost/review trends. | Adds `async-research metrics operational`, a read-only JSON read model for time in review/human states, review latency by tier, human-decision latency, promotion-to-terminal latency, cost per accepted/rejected output, revision-loop counts, timestamp preservation for future closed-loop metrics, unavailable timestamp handling, README/protocol docs, and regression tests. |
| 7 | Policy cleanup | Complete | Revisit Tier 0 and docs packaging with usage evidence. | Tier 0 is now hidden from normal operator guidance: public review/protocol docs and scheduler prompts use Tier 1-3, public revision defaults expose only Tier 1-3, escalation-to-Tier-0 is schema/aggregation-invalid, and Tier 0 is documented as internal recovery/benchmark-only. Docs packaging review keeps Markdown protocol docs packaged for alpha after a fresh build measured a 586,416-byte wheel, 589,490-byte sdist, 47 packaged Markdown docs, 427,255 uncompressed docs bytes, and 153,593 compressed docs bytes; recorded support evidence shows operator guidance demand without wheel-size or installation pain. |

## Framework Integration

Existing workspace artifacts:

```text
research_ops/
  tasks/<TASK-ID>/
    status.json
    reviews/
      primary.md
      methodology.md
      skeptic.md
    review_panel/
```

Integration points:

- `reviews/<role>.md` remains the role-specific review file consumed by
  `review aggregate`.
- `review draft` and `review submit` only create or replace the target role
  file.
- `review aggregate` remains the only public command that computes the final
  deterministic route.
- `prepare-context` and `install-context` remain the isolated-review path for
  reviewers who should not see sibling review files.
- task `status.json` review-start transitions remain explicit and validated.

## Implementation Phases

### Phase 0: Decisions And Command Shape

Decide exact command names and non-goals before editing code.

Resolved command names:

```bash
async-research review draft <task-dir> --role primary
async-research review submit <task-dir> --role primary --decision accept --claim-strength suggestive --confidence 0.75
async-research workflow check research_ops
async-research workflow advance <task-dir> --dry-run
```

Acceptance:

- command names do not collide with existing public CLI groups
- direct `review_template` remains advanced/internal
- review-start transition remains explicit and validated
- orchestrator design says exactly which steps are read-only and which mutate

### Phase 1: Review Authoring UX

Add public review authoring commands around the existing review-template and
review-validation logic.

Behavior:

- `review draft` writes or prints a fenced JSON scaffold with conservative
  defaults
- default scaffold routes to `needs_human` if installed unchanged
- `review submit` accepts explicit flags and writes one role-specific review
- both commands protect existing review files unless `--force` is explicit
- both commands return structured JSON and documented exit codes

Acceptance:

- no direct internal helper invocation is required for a normal review
- malformed or incomplete review flags fail closed with actionable JSON
- reviewer isolation still excludes sibling review files
- tests cover dry-run, write, target exists, role mismatch, and aggregate use

### Phase 2: One-Page Quickstart

Add a short operator quickstart focused only on the first successful loop.

Content:

- initialize generic starter
- run readiness
- write or draft one review
- record review-start transition through the public path
- aggregate review
- update accepted memory
- update/validate surface

Acceptance:

- one page, no full command map
- links to README and deep protocol docs for details
- commands are all public `async-research` commands
- doc-reference tests guard against stale internal helper examples

### Phase 3: Dashboard MVP Coordination

Use the dashboard roadmap as the implementation home for the web UI. This
roadmap only defines why the dashboard is now a near-term adoption item.

Acceptance:

- dashboard slices 1-2 remain read-only
- snapshot includes readiness, health, tasks, human decisions, accepted/rejected
  outputs, cost, idea/data/library dashboard summaries where available
- no mutation endpoints exist before setup actions are explicitly designed

### Phase 4: Workflow Orchestrator

Add a public orchestration layer for the canonical worked-loop sequence without
removing individual commands.

Candidate sequence:

```text
schema-check
readiness --dry-run
review aggregate with review-start support
accepted update
accepted revalidation --write-schedule
surface update
surface validate
health
```

Acceptance:

- `--dry-run` prints the plan and runs only read-only checks
- mutating mode reports each subcommand, exit code, stdout JSON, and next step
- nonzero subcommand results stop the sequence unless explicitly marked
  warning-only
- tests cover accepted, needs_revision, needs_human, and invalid-state paths

### Phase 5: Discovery Inbox Robustness

Improve capture errors and validation for discovery inbox content.

Acceptance:

- non-canonical free-form rows are surfaced as warnings with line numbers
- `idea capture --from-inbox` reports nearby candidate rows when an id is not
  found
- no automatic capture from free-form text without explicit user intent

### Phase 6: Operational Metrics

Add metrics that measure how well the workflow is operating.

Candidate metrics:

- time in `awaiting_review`
- time in `needs_human`
- time from promotion to acceptance/rejection
- review latency by tier
- cost per accepted output
- rejection cost and revision-loop count trends

Acceptance:

- metrics are derived from existing files when possible
- missing timestamps render as `unavailable`, not zero
- weekly digest and future dashboard can consume the same read model

### Phase 7: Policy Cleanup

Resolve lower-priority policy questions after the P1/P2 ergonomics work lands.

Acceptance:

- Tier 0 review is either clearly hidden from normal operator guidance, removed
  from user-facing docs, or replaced by a public review-skip decision path
- docs packaging is revisited with measured wheel-size and user-support data

## Roadmap Dependencies

| Related Roadmap | Relationship |
| --- | --- |
| Dashboard Delivery | Implements Phase 3 and the local visual operator surface. |
| Hypothesis Testing Framework | Delivered on 2026-05-10; sequencing is resolved and this roadmap can proceed as the active adoption track. |
| Public Alpha Hardening | This roadmap is a post-hardening follow-up from external review, not a reopening of P0/P1 safety work. |
| Knowledge Library / Data Foundations / Idea Catalog | These are delivered foundations that should feed dashboard and workflow snapshot views. |

## Test Strategy

Minimum checks per implementation slice:

```bash
.venv/bin/python -m unittest tests.test_review_authoring
.venv/bin/python -m unittest tests.test_cli_architecture tests.test_cli_help
.venv/bin/python -m unittest tests.test_doc_references tests.test_packaged_resources
```

P1 regression scenarios:

- `review draft` previews a conservative `needs_human` scaffold without writing
- `review draft --write` writes `reviews/<role>.md`
- draft and submit refuse an existing target without `--force`
- unchanged draft scaffold aggregates to `needs_human`
- `review submit` requires explicit decision, claim strength, and confidence
- `review submit --dry-run` writes nothing
- submitted review files can be consumed by `review aggregate`
- generated payload role must match target review role
- parseable but schema-invalid `status.json` refuses writes
- missing `--role` returns structured JSON rather than argparse usage text
- non-force writes do not replace concurrent target creation or dangling symlinks

Package-level checks before merging a completed slice:

```bash
.venv/bin/python -m unittest discover tests
.venv/bin/async-research acceptance-suite
.venv/bin/python -m compileall src tests
```

## LLM Implementer Rules

- Preserve fail-closed behavior.
- Prefer public `async-research` wrappers over direct script invocation.
- Keep runtime dependencies standard-library-only unless the user explicitly
  accepts a dependency change.
- Add or update regression tests for every new public command and every docs
  example.
- Do not broaden a phase while implementing it; finish one slice, test it, and
  update this roadmap.
