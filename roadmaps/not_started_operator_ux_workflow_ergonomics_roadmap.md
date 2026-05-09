# Operator UX And Workflow Ergonomics Roadmap

Status: Not Started
Current phase: Phase 0
Last updated: 2026-05-09
Next action: Decide sequencing versus Hypothesis Testing Framework, then start Review Authoring UX
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
Hypothesis Testing Framework roadmap. HTF remains the next research-capability
feature. Operator UX work may be delivered before HTF if first-user friction is
the higher priority.

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

## Implementation Phases

### Phase 0: Decisions And Command Shape

Decide exact command names and non-goals before editing code.

Recommended command names:

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
| Hypothesis Testing Framework | Remains the next research-capability feature; this roadmap may precede it if adoption friction is the priority. |
| Public Alpha Hardening | This roadmap is a post-hardening follow-up from external review, not a reopening of P0/P1 safety work. |
| Knowledge Library / Data Foundations / Idea Catalog | These are delivered foundations that should feed dashboard and workflow snapshot views. |

## LLM Implementer Rules

- Preserve fail-closed behavior.
- Prefer public `async-research` wrappers over direct script invocation.
- Keep runtime dependencies standard-library-only unless the user explicitly
  accepts a dependency change.
- Add or update regression tests for every new public command and every docs
  example.
- Do not broaden a phase while implementing it; finish one slice, test it, and
  update this roadmap.
