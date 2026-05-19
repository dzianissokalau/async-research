# Codex Phase-Gated Delivery Automation Template

Status: Template
Created: 2026-05-17

## Purpose

Use this template to run Codex against any phased roadmap with a controlled
deliver-review-fix loop.

The automation should:

```text
read the selected roadmap
deliver exactly one phase
verify the result
review the delivered diff in a fresh context
route review findings back for fixes
repeat until clean or blocked
advance to the next phase only after a clean phase gate
```

This template is intentionally generic. Replace the placeholders before use.

## Placeholders

```text
ROADMAP_PATH=<path to the roadmap markdown file>
ROADMAP_SLUG=<short lowercase name, e.g. product_readiness>
PHASE_N=<current phase number or label>
BRANCH_PREFIX=codex/
BRANCH_NAME=codex/<roadmap-slug>-phase-<phase-n>
STATE_FILE=roadmaps/automation/<roadmap-slug>/delivery_state.json
DELIVERY_LOG=roadmaps/automation/<roadmap-slug>/delivery_log.md
REVIEW_DIR=roadmaps/automation/<roadmap-slug>/reviews
MAX_REVIEW_ITERATIONS=3
CADENCE=30 minutes
```

For roadmaps outside `roadmaps/`, adjust the state, log, and review paths to
fit the project.

## When To Use

Use this process when a roadmap has:

- clear phases or milestones
- implementation work that Codex can perform in the repo
- tests or verification commands
- reviewable acceptance criteria
- enough scope to benefit from separate delivery and review contexts

Do not use this as a blind autopilot for work that primarily requires product
strategy, external credentials, destructive operations, legal/compliance
judgment, or broad architectural choices not captured in the roadmap.

## Recommended Cadence

Default to a 30-minute cadence for recurring automation.

This is a safe starting point when a typical model work slice takes 10-15
minutes. It leaves room for implementation, tests, review, and one fix pass.

Adjust as follows:

- Use 15 minutes for small, fast, low-risk phases.
- Use 30 minutes for normal implementation phases.
- Use 60 minutes for long test suites, large refactors, or review-heavy phases.
- Use manual/on-demand runs when each phase needs close human inspection.

Recommended automation type:

- Use a workspace cron automation for detached roadmap delivery.
- Use a heartbeat only for short follow-ups in an already active thread.

## Core Rule

Codex may implement, test, review, and fix within the current phase.

Codex must not advance to the next phase unless all of these are true:

```text
[ ] current phase acceptance criteria are satisfied
[ ] required verification passed
[ ] fresh reviewer verdict is delivered
[ ] roadmap status is updated
[ ] delivery log is updated
[ ] delivery state is updated
```

## Branching

Use one branch per phase:

```bash
git switch -c codex/<roadmap-slug>-phase-<phase-n>
```

If the branch already exists:

```bash
git switch codex/<roadmap-slug>-phase-<phase-n>
```

Do not mix multiple phases in one branch unless the human operator explicitly
asks for that.

## State Files

Maintain file-backed state so automation can resume after thread or process
interruptions.

Recommended files:

```text
roadmaps/automation/<roadmap-slug>/delivery_state.json
roadmaps/automation/<roadmap-slug>/delivery_log.md
roadmaps/automation/<roadmap-slug>/reviews/<roadmap-slug>-phase-<phase-n>-review.md
roadmaps/automation/<roadmap-slug>/reviews/<roadmap-slug>-phase-<phase-n>-review-iteration-<m>.md
```

Suggested state:

```json
{
  "roadmap": "ROADMAP_PATH",
  "roadmap_slug": "ROADMAP_SLUG",
  "current_phase": "PHASE_N",
  "branch": "BRANCH_NAME",
  "status": "not_started",
  "review_iterations": 0,
  "max_review_iterations": 3,
  "last_verification": null,
  "blocked_reason": null,
  "updated_at": null
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

## Delivery Log

The delivery log should be concise and append-only.

Suggested entry format:

```markdown
## Phase PHASE_N - YYYY-MM-DD

Status: delivering | reviewing | fixing | delivered | blocked
Branch: BRANCH_NAME

### Scope

- ...

### Changes

- ...

### Tests And Verification

- `command`: passed | failed | not run

### Review

- Review file: `roadmaps/automation/.../reviews/...`
- Verdict: delivered | needs-fix | blocked

### Residual Risks

- ...

### Next Action

- ...
```

## Verification

Each roadmap should define its own verification commands. Use the roadmap's
verification section when present.

Default repository verification placeholder:

```bash
<DOC_REFERENCE_TEST_COMMAND>
<UNIT_TEST_COMMAND>
<ACCEPTANCE_TEST_COMMAND>
```

For UI work, add targeted checks such as:

```text
component or snapshot tests
route/action smoke tests
browser verification for changed user flows
visual or layout checks for responsive behavior
```

For data, workflow, or governance work, add targeted checks such as:

```text
regression fixtures
concurrency or locking tests
schema validation tests
CLI command smoke tests
round-trip read/write tests
```

If verification cannot run, the phase is not delivered. Record the blocker.

## Review Verdicts

Use exactly one of these verdicts:

```text
delivered
needs-fix
blocked
```

Definitions:

- `delivered`: acceptance criteria are met, verification passed, and no blocking
  review findings remain.
- `needs-fix`: findings are actionable within the current phase scope.
- `blocked`: human input, credentials, environment fixes, destructive action, or
  scope decisions are required.

Stop after `MAX_REVIEW_ITERATIONS` review/fix loops if the verdict is still not
`delivered`.

## Delivery Agent Prompt

```text
Deliver Phase PHASE_N of ROADMAP_PATH.

Use this phase-gated delivery template:
roadmaps/automation/codex_phase_gated_delivery_automation_template.md

Work only on Phase PHASE_N. Do not start the next phase.

Before editing:
- Extract the phase scope.
- Extract acceptance criteria.
- Identify non-goals.
- Identify implementation slices.
- Identify required tests and verification commands.

During delivery:
- Keep changes scoped to this phase.
- Preserve unrelated user changes in the worktree.
- Add or update tests for each behavior changed.
- Update DELIVERY_LOG with scope, changes, tests, known gaps, and next action.

Verification:
- Run the roadmap's required verification commands.
- Run targeted tests for the behavior changed.
- If verification cannot run, record why and stop as blocked.

At the end:
- Report changed files.
- Report verification results.
- Report known risks.
- Do not claim the phase is delivered until a fresh review verdict is delivered.
```

## Reviewer Prompt

Run this in a fresh context whenever possible:

```text
Review the delivered Phase PHASE_N changes against ROADMAP_PATH.

Use this phase-gated delivery template:
roadmaps/automation/codex_phase_gated_delivery_automation_template.md

Take a skeptical code-review stance. Lead with findings. Do not summarize first.

Treat the roadmap phase scope, implementation notes, and exit criteria as the
source of truth. Review:
- git diff
- relevant surrounding code
- tests
- delivery log
- verification output summary

Look for:
- missed acceptance criteria
- bugs or regressions
- weak or missing tests
- unsafe behavior
- unclear user workflows
- data integrity risks
- security or path-handling risks
- docs or roadmap claims that overstate delivery
- scope creep into later phases

Output:
- Findings ordered by severity with file/line references
- Missing tests
- Residual risks
- Verdict: delivered, needs-fix, or blocked

Evaluate delivered behavior only. Do not give credit for intent.
```

## Fix Prompt

Route review findings back to the delivery context:

```text
Address the Phase PHASE_N review findings below.

Stay within Phase PHASE_N scope. Do not start the next phase.

For each finding:
- decide whether it is valid
- implement the fix if valid
- add or update regression coverage where appropriate
- explain if a finding is intentionally not fixed and why

Rerun required verification and targeted tests.

Update DELIVERY_LOG with:
- fixes made
- tests added or updated
- verification results
- residual risks

Review findings:
<paste review findings here>
```

## Orchestrator Prompt

Use this in the thread or automation that coordinates the work:

```text
You are the roadmap delivery orchestrator for ROADMAP_PATH.

Use this template:
roadmaps/automation/codex_phase_gated_delivery_automation_template.md

Run a phase-gated deliver-review-fix loop.

Configuration:
- ROADMAP_PATH: ROADMAP_PATH
- ROADMAP_SLUG: ROADMAP_SLUG
- Current phase: PHASE_N
- Branch: BRANCH_NAME
- State file: STATE_FILE
- Delivery log: DELIVERY_LOG
- Review directory: REVIEW_DIR
- Max review iterations: MAX_REVIEW_ITERATIONS
- Cadence when automated: CADENCE

For the current phase:
1. Read the roadmap and delivery state.
2. Create or reuse the phase branch.
3. Ask a delivery context to implement only the current phase.
4. Require verification.
5. Ask a fresh review context to review the delivered diff.
6. If the reviewer verdict is needs-fix, route findings back to delivery and
   repeat.
7. If the reviewer verdict is blocked, record the blocker and stop.
8. Stop after MAX_REVIEW_ITERATIONS review/fix loops if still not delivered.
9. If delivered, update the roadmap, delivery log, and delivery state.
10. Only then advance to the next phase.

Do not silently expand scope.
Do not perform destructive git operations without explicit human approval.
Do not claim delivery without passing verification and fresh review.
```

## Phase Completion Checklist

```text
[ ] phase scope implemented
[ ] acceptance criteria satisfied
[ ] non-goals preserved
[ ] tests added or updated
[ ] full verification passed
[ ] targeted smoke checks passed when relevant
[ ] fresh review completed
[ ] reviewer verdict is delivered
[ ] roadmap updated
[ ] delivery log updated
[ ] delivery state updated
[ ] next phase identified
```

## Blocker Conditions

Stop and ask the human operator when:

- credentials or external service access are required
- tests cannot run for environmental reasons
- destructive operations are needed
- product decisions are not answered by the roadmap
- implementation requires broad refactoring outside the current phase
- worktree state makes it unsafe to proceed
- review/fix loop reaches the maximum iteration count
- the reviewer and delivery context disagree on scope or acceptance criteria

## Notes On Review Bias

Same-context self-review is useful but biased. Prefer a fresh review context.

For the lowest practical bias, give the reviewer only:

```text
roadmap phase
git diff
delivery log
test output summary
relevant files
```

The reviewer should evaluate delivered behavior, not intent or explanation.

## Adapting This Template

Before using this template for a specific roadmap:

1. Replace all placeholders.
2. Add roadmap-specific verification commands.
3. Add roadmap-specific risk checks.
4. Decide the current phase.
5. Decide whether the automation should pause after each phase for human review.
6. Create the initial state file and delivery log if they do not exist.

For high-risk phases, prefer pausing after review even when the verdict is
`delivered`.
