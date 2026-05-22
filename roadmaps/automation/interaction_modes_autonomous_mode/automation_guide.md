# Codex Automation Guide: Interaction Modes And Autonomous Mode Roadmap

Status: Draft guide
Created: 2026-05-22
Primary roadmap: `roadmaps/delivered_interaction_modes_autonomous_mode_roadmap.md`

## Purpose

This guide describes how to run Codex as a phase-gated delivery system for the
Interaction Modes And Autonomous Mode Roadmap.

The intended loop is:

```text
deliver one roadmap phase
review the delivered diff in a fresh context
route findings back to delivery
fix and verify
repeat until clean or blocked
advance to the next roadmap phase
```

The roadmap addresses a core product pain: the framework currently interrupts
the operator too often. The delivery automation may implement, test, review, and
fix within the current phase, but it must not skip quality gates or weaken
auditability while adding autonomy.

## Recommended Cadence

Use an hourly detached cron automation by default.

Recommended model and reasoning:

```text
Model: GPT-5.5
Reasoning: xhigh
```

The work changes workflow authority, transition behavior, audit logging, and
operator UX, so use the strongest available coding model by default.

## Operating Rules

1. Work exactly one roadmap phase at a time.
2. Do not begin Phase N+1 until Phase N is delivered, reviewed, fixed,
   verified, recorded, and state is advanced.
3. Treat the roadmap phase scope, non-goals, acceptance criteria, and required
   verification as the source of truth.
4. Preserve unrelated user changes in the worktree.
5. Add or update regression tests for every behavior changed.
6. Run the verification listed in the current phase.
7. Stop and record a blocker when credentials, destructive operations, broad
   product decisions, or unclear scope are required.
8. Do not push, promote to `main`, edit Codex app automation config, or run
   destructive git operations without explicit human approval.

## Branching

Use one branch per phase:

```text
codex/interaction-modes-autonomous-mode-phase-<n>
```

If the branch already exists, reuse it. Do not mix multiple roadmap phases in
one branch unless the human operator explicitly asks for it.

## State Files

Maintain these files:

```text
roadmaps/automation/interaction_modes_autonomous_mode/delivery_state.json
roadmaps/automation/interaction_modes_autonomous_mode/delivery_log.md
roadmaps/automation/interaction_modes_autonomous_mode/review_fix_state.json
roadmaps/automation/interaction_modes_autonomous_mode/review_fix_log.md
roadmaps/automation/interaction_modes_autonomous_mode/reviews/
```

## Required Verification

Every phase must run at least:

```bash
git diff --check
.venv/bin/python -m unittest tests.test_doc_references
```

Run `.venv/bin/python -m unittest discover -s tests` whenever implementation
files, tests, fixtures, package resources, schemas, CLI behavior, or dashboard
read models change.

Run `.venv/bin/async-research acceptance-suite` when the phase touches public
CLI behavior, end-to-end workflow behavior, state transitions, review
aggregation, dashboard/read-model behavior, result acceptance, deliverable
gates, or autonomy/readiness behavior.

Dashboard phases must also include targeted console snapshot/action/static
resource tests and a local smoke test when UI behavior changes.

## Review Loop

Use a fresh review context after the delivery pass whenever possible. The
reviewer should take a skeptical code-review stance and compare the delivered
diff against the current phase scope.

Review verdicts:

```text
delivered
needs-fix
blocked
```

Rules:

- `delivered`: no blocking findings, acceptance criteria satisfied, and
  verification passed.
- `needs-fix`: findings can be fixed within current phase scope.
- `blocked`: human input is needed, scope is unclear, verification cannot run,
  or a product decision is required.

Stop after 3 review/fix iterations and record a blocker if the reviewer still
finds blocking issues.

## Phase-Specific Guidance

- Phase 0: define the mode contract and authority model. This is primarily
  docs and product-contract work unless the roadmap explicitly authorizes code.
  Do not change task transitions yet.
- Phase 1: add durable mode config, schema validation, starter defaults, CLI
  visibility, and console snapshot fields.
- Phase 2: make `needs_human` policy-aware. Preserve manual behavior and hard
  stops.
- Phase 3: add auto-decision audit logging. No autonomous mutation may happen
  without an audit row.
- Phase 4: integrate mode policy into readiness, workflow next/advance, review
  aggregation, idea catalog, and deliverable gates.
- Phase 5: expose mode, interrupt policy, auto-decisions, and progression-flow
  effects in the dashboard.
- Phase 6: add contract tests, fixture gates, autonomous simulations, hard-stop
  tests, and audit completeness checks.
- Phase 7: decide default behavior, migration, quickstart copy, LLM operator
  prompt updates, and release notes.

## Output Expectations For Each Run

- Update `roadmaps/automation/interaction_modes_autonomous_mode/delivery_state.json`.
- Append concise progress to
  `roadmaps/automation/interaction_modes_autonomous_mode/delivery_log.md`.
- Write review output under
  `roadmaps/automation/interaction_modes_autonomous_mode/reviews/`.
- Leave a clear status: `delivered`, `blocked`, `fixing`, `reviewing`,
  `ready_for_next_run`, or `not_started`.
- Do not push before explicit human approval.
