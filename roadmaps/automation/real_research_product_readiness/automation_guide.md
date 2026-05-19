# Codex Automation Guide: Real Research Product Readiness Roadmap

Status: Draft guide
Created: 2026-05-17
Primary roadmap: `roadmaps/delivered_real_research_product_readiness_roadmap.md`

## Purpose

This guide describes how to run Codex as a phase-gated delivery system for the
Real Research Product Readiness Roadmap.

The intended loop is:

```text
deliver one roadmap phase
review the delivered diff in a fresh context
route findings back to the delivery context
fix and verify
repeat until clean or blocked
advance to the next roadmap phase
```

The goal is high autonomy without silent scope expansion. Codex may implement,
test, review, and fix within the current phase, but it must not advance to the
next phase until the current phase meets its exit criteria.

## Recommended Cadence

Use a 30-minute cadence as the default automation interval.

Rationale:

- Typical 5.5 Extra High delivery slices take about 10-15 minutes.
- A 30-minute interval leaves room for implementation, tests, review, and at
  least one fix pass.
- It avoids overly frequent wakeups while still giving the automation enough
  continuity to make steady progress.

Recommended automation type:

- Use a workspace cron automation for detached roadmap delivery.
- Use a heartbeat only when continuing an active interactive thread for a short
  follow-up.

Recommended schedule:

```text
Every 30 minutes while active
```

If the automation repeatedly hits long test runs or review/fix loops, move to
hourly. If each phase is being manually monitored, 30 minutes is still a good
safe default.

## Operating Rules

1. Work exactly one roadmap phase at a time.
2. Do not begin Phase N+1 until Phase N is delivered, reviewed, fixed, verified,
   and recorded.
3. Treat the roadmap phase exit criteria and implementation notes as the source
   of truth.
4. Prefer small implementation slices inside each phase.
5. Add or update regression tests for each behavior changed.
6. Run the full verification plan before declaring a phase delivered.
7. Stop and record a blocker when a product decision, credential, destructive
   operation, or unclear scope decision is required.
8. Do not mark roadmap items delivered unless the behavior exists and tests or
   smoke checks support the claim.

## Branching

Use one branch per phase:

```bash
git switch -c codex/product-readiness-phase-N
```

If the branch already exists, reuse it:

```bash
git switch codex/product-readiness-phase-N
```

Do not mix multiple roadmap phases in one branch unless explicitly instructed by
the human operator.

## State Files

The automation should maintain file-backed state so work can resume safely after
thread restarts.

Recommended files:

```text
roadmaps/automation/real_research_product_readiness/delivery_state.json
roadmaps/automation/real_research_product_readiness/delivery_log.md
roadmaps/automation/real_research_product_readiness/reviews/phase-N-review.md
roadmaps/automation/real_research_product_readiness/reviews/phase-N-review-iteration-M.md
```

Suggested state shape:

```json
{
  "roadmap": "roadmaps/delivered_real_research_product_readiness_roadmap.md",
  "current_phase": 0,
  "branch": "codex/product-readiness-phase-0",
  "status": "delivering",
  "review_iterations": 0,
  "max_review_iterations": 3,
  "last_verification": null,
  "blocked_reason": null
}
```

Suggested statuses:

```text
not_started
delivering
verifying
reviewing
fixing
delivered
blocked
```

## Required Verification

Every phase must run:

```bash
.venv/bin/python -m unittest tests.test_doc_references
.venv/bin/python -m unittest discover -s tests
.venv/bin/async-research acceptance-suite
```

Dashboard phases must also include relevant targeted checks, such as:

```text
targeted console snapshot/action tests
local HTTP route smoke tests
browser or static-resource checks when UI behavior changes
coffee-pilot-inspired regression fixtures for the bug being fixed
```

If verification cannot run, the phase is not delivered. Record the blocker or
test failure in the delivery log.

## Review Loop

Use a fresh review context after the delivery pass. The reviewer should not be
the same context that authored the implementation when avoidable.

Review verdicts:

```text
delivered
needs-fix
blocked
```

Rules:

- `delivered`: no blocking findings, no missing phase acceptance criteria, and
  verification passed.
- `needs-fix`: implementation can proceed within current phase scope.
- `blocked`: human input is needed, scope is unclear, verification cannot run,
  or a product decision is required.

Stop after 3 review/fix iterations and record a blocker if the reviewer still
finds blocking issues.

## Delivery Agent Prompt

Use this prompt for the delivery context:

```text
Deliver Phase N of roadmaps/delivered_real_research_product_readiness_roadmap.md.

Work only on Phase N. Do not start Phase N+1.

Before editing:
- Extract the phase scope, non-goals, and acceptance criteria.
- Identify the implementation slices.
- Identify tests and smoke checks required for this phase.

During delivery:
- Add or update regression tests for each behavior changed.
- Keep changes scoped to the phase.
- Preserve unrelated user changes in the worktree.
- Update roadmaps/automation/real_research_product_readiness/delivery_log.md with slices,
  changed files, test results, and known gaps.

Required verification:
.venv/bin/python -m unittest tests.test_doc_references
.venv/bin/python -m unittest discover -s tests
.venv/bin/async-research acceptance-suite

For dashboard changes, also run targeted dashboard tests and a local smoke test
for changed routes/actions.

At the end:
- Report changed files.
- Report verification results.
- Report remaining risks.
- Do not claim Phase N is delivered until a fresh review verdict says delivered.
```

## Reviewer Prompt

Use this prompt in a fresh context:

```text
Review the delivered Phase N changes against
roadmaps/delivered_real_research_product_readiness_roadmap.md.

Take a skeptical code-review stance. Lead with findings. Do not summarize first.

Treat the Phase N scope, implementation notes, and exit criteria as the source
of truth. Review the git diff, relevant surrounding code, tests, and delivery
log.

Look for:
- missed acceptance criteria
- bugs or regressions
- weak or missing tests
- unsafe path handling
- dashboard workflow dead ends
- source-governance integrity risks
- roadmap or delivery-log claims that overstate what was delivered

Output:
- Findings ordered by severity with file/line references
- Missing tests
- Residual risks
- Verdict: delivered, needs-fix, or blocked

Do not give credit for intent. Evaluate delivered behavior only.
```

## Fix Prompt

Route reviewer findings back to the delivery context with this prompt:

```text
Address the Phase N review findings below.

Stay within Phase N scope. Do not start Phase N+1.

For each finding:
- decide whether it is valid
- implement the fix if valid
- add or update regression coverage where appropriate
- explain if a finding is intentionally not fixed and why

Rerun required verification:
.venv/bin/python -m unittest tests.test_doc_references
.venv/bin/python -m unittest discover -s tests
.venv/bin/async-research acceptance-suite

Update the delivery log with fixes, tests, and verification results.

Review findings:
<paste review findings here>
```

## Orchestrator Prompt

Paste this into the Codex thread that will coordinate the automation. If
sub-agent or multi-thread tools are available, use them because this task is
explicitly intended to run delivery and review in separate contexts.

```text
You are the roadmap delivery orchestrator for:
roadmaps/delivered_real_research_product_readiness_roadmap.md

Use this guide:
roadmaps/automation/real_research_product_readiness/automation_guide.md

Run a phase-gated deliver-review-fix loop.

Default cadence: every 30 minutes when configured as an automation.

For the current phase:
1. Read the roadmap and delivery state file.
2. Create or reuse branch codex/product-readiness-phase-N.
3. Ask a delivery context to implement only Phase N.
4. Require the delivery context to run the full verification plan.
5. Ask a fresh review context to review the delivered diff against the roadmap.
6. If the reviewer verdict is needs-fix, route findings back to the delivery
   context and repeat.
7. Stop after 3 review/fix iterations if not clean.
8. If the reviewer verdict is blocked, record the blocker and stop.
9. If the reviewer verdict is delivered and verification passed, update the
   roadmap, delivery log, and delivery state.
10. Only then advance to Phase N+1.

Do not silently expand scope.
Do not start the next phase until the current phase is delivered.
Do not perform destructive git operations without explicit human approval.
```

## Phase Completion Checklist

A phase is complete only when all of the following are true:

```text
[ ] Phase acceptance criteria are satisfied.
[ ] Roadmap improvement statuses for the phase are updated.
[ ] Delivery log records what changed.
[ ] Tests were added or updated where behavior changed.
[ ] Full verification passed.
[ ] Dashboard smoke checks passed when relevant.
[ ] Fresh reviewer verdict is delivered.
[ ] Residual risks are documented.
[ ] Delivery state advances to the next phase.
```

## Blocker Conditions

Stop and ask the human operator when:

- the implementation requires credentials, network permissions, or external
  service access that is unavailable
- tests cannot run for environmental reasons
- a destructive operation is needed
- reviewer finds a product decision not answered by the roadmap
- the phase would require broad refactoring outside its scope
- review/fix loop reaches 3 iterations without a delivered verdict
- worktree state makes it unsafe to proceed without clarification

## Notes On Bias

Same-context self-review is useful but biased. Prefer a fresh review context.

Bias is lowest when the reviewer receives only:

```text
roadmap phase
git diff
delivery log
test output summary
relevant files
```

The reviewer should evaluate behavior, not implementation intent.

## Suggested First Run

Start with Phase 0 because it has concrete, high-value control-plane issues:

```text
Dashboard artifact viewer
Human-decision action path normalization
Human decision evidence cards
Source blocker action guidance
Decision action regression tests
```

Do not begin Phase 1 until Phase 0 passes review and verification.
