# Autonomous Roadmap Delivery Workflow - Skill Development Brief

Status: Draft input for future skill development
Created: 2026-05-19

## Absolute Path Bases

Repository root:

```text
/Users/dzianissokalau/Documents/projects/async-research
```

Codex home:

```text
/Users/dzianissokalau/.codex
```

Unless a path is shown inside a directory tree rooted at one of the absolute
paths above, concrete file paths in this document are written as absolute paths.
Placeholder paths keep angle-bracket variables such as `<roadmap_slug>` but
still include their absolute base directory.

## Purpose

This document describes the current autonomous roadmap delivery workflow used
in this repository so it can be turned into a Codex skill.

The workflow lets Codex deliver a phased roadmap with a controlled loop:

```text
read roadmap
select one current phase
deliver only that phase
run verification
review the delivered diff
fix review findings
repeat until clean or blocked
commit the phase
advance to the next phase
after all phases, push a final branch and write a deep-review prompt
pause the automation
```

The target skill should help Codex set up, operate, inspect, and safely recover
this workflow across roadmaps. It should not replace repository tests, git
history, phase reviews, or human judgment.

## Current Workflow In One Sentence

Autonomous roadmap delivery is a file-backed, phase-gated Codex operating
system for roadmaps: it uses roadmap phase contracts, local verification,
skeptical review, delivery logs, JSON state, per-phase commits, final branch
pushes, and explicit stop conditions to let Codex make progress without silently
expanding scope.

## Source Artifacts In This Repo

Core template:

```text
/Users/dzianissokalau/Documents/projects/async-research/roadmaps/automation/codex_phase_gated_delivery_automation_template.md
```

Automation artifact layout:

```text
/Users/dzianissokalau/Documents/projects/async-research/roadmaps/automation/
  README.md
  roadmap_closeout_checklist.md
  codex_phase_gated_delivery_automation_template.md
  <roadmap_slug>/
    automation_guide.md
    delivery_state.json
    delivery_log.md
    review_fix_state.json
    review_fix_log.md
    reviews/
      <roadmap-slug>-phase-<n>-review-iteration-<m>.md
      <roadmap-slug>-deep-review-prompt.md
```

Examples of delivered or active automation-backed roadmaps:

```text
/Users/dzianissokalau/Documents/projects/async-research/roadmaps/delivered_real_research_product_readiness_roadmap.md
/Users/dzianissokalau/Documents/projects/async-research/roadmaps/delivered_deliverable_maturity_editorial_qa_roadmap.md
/Users/dzianissokalau/Documents/projects/async-research/roadmaps/delivered_autonomous_delivery_pivot_roadmap.md
/Users/dzianissokalau/Documents/projects/async-research/roadmaps/delivered_llm_operator_skill_roadmap.md
```

Example saved Codex app automation configs:

```text
/Users/dzianissokalau/.codex/automations/real-research-product-readiness-delivery/automation.toml
/Users/dzianissokalau/.codex/automations/deliverable-maturity-editorial-qa-delivery/automation.toml
/Users/dzianissokalau/.codex/automations/autonomous-delivery-pivot-delivery/automation.toml
/Users/dzianissokalau/.codex/automations/llm-operator-skill-delivery/automation.toml
```

## Skill Candidate

Recommended skill name:

```text
autonomous-roadmap-delivery
```

Recommended skill description:

```text
Use when operating, creating, inspecting, pausing, resuming, reviewing, or
repairing a phase-gated Codex automation that delivers a repository roadmap one
phase at a time with tests, fresh review, delivery logs, JSON state, per-phase
branches, final branch push, deep-review prompt, and explicit stop conditions.
```

The skill should trigger for requests such as:

- "set up automation for this roadmap"
- "activate/pause the roadmap automation"
- "what is the status of this roadmap delivery?"
- "why did the automation rename this roadmap?"
- "review/fix findings from the deep review"
- "promote delivered roadmap branch to main"
- "turn this roadmap delivery process into a reusable workflow"
- "repair a blocked phase-gated automation"

It should not trigger for:

- ordinary feature implementation unrelated to roadmap automation
- generic project management advice with no repository roadmap
- one-off code review requests unrelated to a delivered roadmap
- creating an unrelated Codex skill unless the delivery workflow itself is the topic

## Desired Skill Layout

Recommended source package:

```text
/Users/dzianissokalau/.codex/skills/autonomous-roadmap-delivery/
  SKILL.md
  agents/
    openai.yaml
  references/
    setup-automation.md
    phase-loop.md
    review-and-fix.md
    state-log-and-branches.md
    finalization-and-promotion.md
    troubleshooting.md
  scripts/
    inspect_delivery_state.py
    validate_delivery_artifacts.py
```

Keep `SKILL.md` concise. Put details and examples in references. The body should
tell Codex what to read next based on the task:

- setup a new automation: read `setup-automation.md`
- deliver a phase manually: read `phase-loop.md`
- handle review findings: read `review-and-fix.md`
- answer status questions: read `state-log-and-branches.md`
- complete/push/promote: read `finalization-and-promotion.md`
- repair a bad state: read `troubleshooting.md`

## Core Entities

### Roadmap

A roadmap is a Markdown file under `/Users/dzianissokalau/Documents/projects/async-research/roadmaps/` with:

```text
Status: Not Started | In Progress | Delivered | Blocked | Paused | Superseded
Current phase: ...
Last updated: YYYY-MM-DD
Next action: ...
Blocked by: ...
```

Roadmap filenames should match lifecycle status:

```text
not_started_*_roadmap.md
in_progress_*_roadmap.md
delivered_*_roadmap.md
blocked_*_roadmap.md
paused_*_roadmap.md
superseded_*_roadmap.md
```

The workflow treats the roadmap as the phase contract. A phase cannot be marked
delivered unless the roadmap scope, acceptance criteria, non-goals, and
verification expectations for that phase are satisfied.

### Phase

A phase is the unit of autonomous work. It should include:

- objective
- owned files
- implementation steps
- acceptance criteria
- required verification
- non-goals
- blockers

Codex must deliver exactly one phase at a time. Later phases are not started
until the current phase is verified, reviewed, fixed, committed, logged, and
advanced in state.

### Automation Config

Codex app automations are saved outside the repo under:

```text
/Users/dzianissokalau/.codex/automations/<automation-id>/automation.toml
```

Important fields:

```toml
id = "..."
kind = "cron"
name = "..."
prompt = "..."
status = "ACTIVE" # or "PAUSED"
rrule = "FREQ=HOURLY;INTERVAL=1"
model = "gpt-5.5"
reasoning_effort = "xhigh"
execution_environment = "local"
cwds = ["/Users/dzianissokalau/Documents/projects/async-research"]
```

Observed behavior: new automations may save as `ACTIVE` even when `PAUSED` was
requested. Always read back the saved config and correct it if needed.

### Cadence

The working assumption from current usage:

- GPT-5.5 Extra High roadmap phases often take 10-15 minutes for one
  deliver-review-fix pass
- 30 minutes would be a reasonable wake-up interval if the automation platform
  supports minute-level detached cron cadence
- the current Codex cron workflow uses hourly cadence:

```text
FREQ=HOURLY;INTERVAL=1
```

Use hourly cadence for detached repository automations unless the platform
explicitly supports safe non-overlapping 30-minute cron runs. A shorter cadence
is only safe if the automation system guarantees that a second run will not
start while the previous run is still delivering or reviewing a phase.

Thread heartbeats can support minute-based wakeups, but they are the wrong
default for this workflow because roadmap delivery should survive thread
closure and operate from durable repo state.

### Delivery State

The state file is JSON:

```text
/Users/dzianissokalau/Documents/projects/async-research/roadmaps/automation/<roadmap_slug>/delivery_state.json
```

Typical shape:

```json
{
  "roadmap": "/Users/dzianissokalau/Documents/projects/async-research/roadmaps/in_progress_example_roadmap.md",
  "roadmap_slug": "example",
  "current_phase": 1,
  "branch": "codex/example-phase-1",
  "status": "not_started",
  "review_iterations": 0,
  "max_review_iterations": 3,
  "last_verification": null,
  "last_review": null,
  "last_delivered_phase": 0,
  "blocked_reason": null,
  "all_phases_complete": false,
  "updated_at": "2026-05-19T07:30:19+01:00"
}
```

Common statuses:

```text
not_started
delivering
verifying
reviewing
fixing
delivered
blocked
completed_pending_pause
```

The state file is the primary checkpoint for automation resumption. It should
be updated after every status transition and after final completion.

### Delivery Log

The log is append-only Markdown:

```text
/Users/dzianissokalau/Documents/projects/async-research/roadmaps/automation/<roadmap_slug>/delivery_log.md
```

Each phase entry should include:

```markdown
## Phase N - YYYY-MM-DD

Status: delivered | blocked | fixing | reviewing
Branch: `codex/<roadmap-slug>-phase-N`

### Scope

- ...

### Changes

- ...

### Tests And Verification

- `command`: passed, details

### Review

- Review file: `/Users/dzianissokalau/Documents/projects/async-research/roadmaps/automation/<slug>/reviews/...`
- Verdict: delivered | needs-fix | blocked

### Residual Risks

- ...

### Next Action

- ...
```

The log should be concise but sufficient for a later Codex session or human to
answer: what changed, how it was verified, what review said, and what comes
next.

### Review Files

Review files live under:

```text
/Users/dzianissokalau/Documents/projects/async-research/roadmaps/automation/<roadmap_slug>/reviews/
```

Naming convention:

```text
<roadmap-slug>-phase-<phase>-review-iteration-<n>.md
```

Review verdicts must be exactly:

```text
delivered
needs-fix
blocked
```

Review posture:

- lead with findings
- use file/line references
- check roadmap acceptance criteria
- check tests and verification
- check security/path handling and data integrity when relevant
- check scope creep
- check overclaiming in roadmap/log/docs
- evaluate delivered behavior, not intent

### Deep Review Prompt

At final completion, write:

```text
/Users/dzianissokalau/Documents/projects/async-research/roadmaps/automation/<roadmap_slug>/reviews/<roadmap-slug>-deep-review-prompt.md
```

It should ask another LLM to review the final branch deeply against the roadmap,
delivery log, state file, review files, and tests. It should request findings
by severity, missing tests, residual risks, and final verdict.

## Branching Model

Default branch prefix:

```text
codex/
```

Typical phase branch:

```text
codex/<roadmap-slug>-phase-<n>
```

Typical final branch:

```text
codex/<roadmap-slug>-delivered
```

Observed variants:

```text
codex/deliverable-maturity-editorial-qa-delivered
codex/autonomous-delivery-pivot-delivered
codex/llm-operator-skill-delivered
```

Rules:

- create or reuse one phase branch per phase
- for later phases, branch from the previous delivered phase commit unless a
  current phase branch already exists
- never rebase, reset, or discard unrelated user changes
- create one local commit per delivered phase
- push only the final delivered branch unless explicitly requested otherwise
- promoting to `main` is not part of normal automation; it requires explicit
  human instruction

## The Phase Loop

### Step 1 - Read And Reconcile State

Codex reads:

- roadmap file
- phase-gated template
- delivery state
- delivery log
- current git branch
- `git status --short`

If the roadmap lifecycle filename changed, update the automation prompt and
state to use the current file before continuing. This happened when
`not_started_*` became `in_progress_*` or `in_progress_*` became `delivered_*`.

### Step 2 - Extract The Phase Contract

Before editing, Codex must extract:

- phase number and focus
- scope
- owned files
- non-goals
- blockers
- acceptance criteria
- required verification commands
- likely targeted tests
- whether broad verification, acceptance suite, or build is needed

If the phase needs a product decision not answered by the roadmap, mark blocked.

### Step 3 - Implement Only The Current Phase

Delivery rules:

- keep edits inside phase scope
- prefer existing repo patterns
- add tests for changed behavior
- do not silently expand into later phases
- preserve unrelated user changes
- use public CLI surfaces when applicable
- use local fixtures and temporary directories for tests
- never mutate live user research workspaces in smoke tests

### Step 4 - Verify

Run the phase-required verification. Common baseline:

```bash
git diff --check
/Users/dzianissokalau/Documents/projects/async-research/.venv/bin/python -m unittest tests.test_doc_references
/Users/dzianissokalau/Documents/projects/async-research/.venv/bin/python -m unittest discover -s /Users/dzianissokalau/Documents/projects/async-research/tests
```

Additional commands used when relevant:

```bash
/Users/dzianissokalau/Documents/projects/async-research/.venv/bin/async-research acceptance-suite
/Users/dzianissokalau/Documents/projects/async-research/.venv/bin/python -m build
/Users/dzianissokalau/Documents/projects/async-research/.venv/bin/python -m unittest tests.test_docs_packaging
/Users/dzianissokalau/Documents/projects/async-research/.venv/bin/python -m unittest tests.test_packaged_resources
```

Feature-specific smoke commands should use repository fixtures or temporary
copies, for example:

```bash
/Users/dzianissokalau/Documents/projects/async-research/.venv/bin/async-research idea metrics /Users/dzianissokalau/Documents/projects/async-research/tests/fixtures/idea_traceability/research_ops
/Users/dzianissokalau/Documents/projects/async-research/.venv/bin/async-research analysis reviewer-packet <fixture-ops-dir> <fixture-analysis-run-dir>
```

If verification cannot run, stop and record a blocker. Do not mark delivered.

### Step 5 - Review

Prefer a fresh context for review. If fresh subagent or separate thread review
is unavailable, explicitly record that limitation in residual risks.

Review should inspect:

- diff
- relevant surrounding code
- tests
- delivery log
- verification output summary
- roadmap scope and exit criteria

Reviewer outputs:

- findings ordered by severity
- missing tests
- residual risks
- verdict

### Step 6 - Fix

If verdict is `needs-fix`:

- route findings back to delivery context
- decide whether each finding is valid
- fix valid findings within current phase scope
- add regression coverage when appropriate
- rerun verification
- update state/log
- repeat review

Stop after `max_review_iterations`, normally 3.

### Step 7 - Commit And Advance

When verdict is `delivered` and verification passed:

- update roadmap phase/status/next action
- update delivery log
- update delivery state
- create one local commit for the delivered phase
- advance `current_phase` in state
- set next phase branch name
- do not push yet unless the roadmap is fully complete and finalization begins

## Finalization

When all phases are delivered:

1. Confirm the roadmap says delivered or complete.
2. Confirm final verification passed.
3. Confirm latest phase review verdict is `delivered`.
4. Update delivery state:

```json
{
  "status": "completed_pending_pause",
  "all_phases_complete": true,
  "completion": {
    "final_branch": "codex/<roadmap-slug>-delivered",
    "final_branch_pushed": true,
    "deep_review_prompt": "/Users/dzianissokalau/Documents/projects/async-research/roadmaps/automation/<roadmap_slug>/reviews/<roadmap-slug>-deep-review-prompt.md",
    "automation_pause": "pending_manual_or_system_pause"
  }
}
```

5. Write the deep-review prompt.
6. Commit final bookkeeping.
7. Create or switch to final branch.
8. Push final branch.
9. Pause the automation.

The automation should contain a hard-stop guard:

```text
If delivery_state.json says completed_pending_pause or all_phases_complete:
true, do not start new delivery work.
```

## Promotion To Main

Promotion to GitHub `main` is a separate human-requested action, not normal
automation.

Safe promotion flow:

1. Ensure final branch contains all intended commits.
2. Ensure verification passed.
3. Ensure `origin/main` is an ancestor of `HEAD`:

```bash
git fetch origin
git merge-base --is-ancestor origin/main HEAD
```

4. Push fast-forward:

```bash
git push origin HEAD:main
```

5. Report exact commit hash.

Do not force-push `main`.

## Automation Prompt Skeleton

The future skill should generate a prompt with this shape. Keep the concrete
roadmap path, slug, state path, log path, review path, and final branch in the
prompt so the automation can recover after context compaction.

```text
You are delivering an absolute roadmap path using the repository's phase-gated
autonomous roadmap workflow.

Set these concrete paths at the top of the prompt:
- REPO_ROOT=/Users/dzianissokalau/Documents/projects/async-research
- ROADMAP_PATH=/Users/dzianissokalau/Documents/projects/async-research/roadmaps/<roadmap-file>.md
- TEMPLATE_PATH=/Users/dzianissokalau/Documents/projects/async-research/roadmaps/automation/codex_phase_gated_delivery_automation_template.md
- STATE_FILE=/Users/dzianissokalau/Documents/projects/async-research/roadmaps/automation/<roadmap_slug>/delivery_state.json
- DELIVERY_LOG=/Users/dzianissokalau/Documents/projects/async-research/roadmaps/automation/<roadmap_slug>/delivery_log.md
- REVIEW_DIR=/Users/dzianissokalau/Documents/projects/async-research/roadmaps/automation/<roadmap_slug>/reviews

Operate from:
- ROADMAP_PATH
- TEMPLATE_PATH
- STATE_FILE
- DELIVERY_LOG
- REVIEW_DIR

Model expectation:
- use GPT-5.5 with Extra High reasoning
- deliver one phase per successful loop
- keep all work file-backed so future runs can resume safely

Hard stop:
- if STATE_FILE says all_phases_complete is true, or status is
  completed_pending_pause, do not start new delivery work
- pause the automation if possible
- report that the roadmap is complete

At the start of every run:
1. Read the roadmap, state file, delivery log, and template.
2. Check git branch and git status.
3. Reconcile lifecycle rename drift. If the roadmap moved from not_started_* to
   in_progress_* or delivered_*, update references before continuing.
4. Identify the current phase from the roadmap and state file.
5. If state and roadmap disagree, stop and report the mismatch.

For the current phase:
1. Extract scope, non-goals, acceptance criteria, owned files, and required
   verification.
2. Create or switch to codex/<roadmap-slug>-phase-<phase>.
3. Implement only the current phase.
4. Add or update tests appropriate to the changed behavior.
5. Run required verification.
6. Update state and delivery log with commands and results.
7. Run or request a fresh review.
8. If the review verdict is needs-fix, fix valid findings and repeat
   verification/review up to max_review_iterations.
9. If the review verdict is blocked, record the blocker and stop.
10. If the review verdict is delivered, update roadmap/state/log and commit the
    phase.

Finalization:
1. When all non-backlog phases are delivered, run final verification.
2. Write REVIEW_DIR/<roadmap-slug>-deep-review-prompt.md.
3. Commit final bookkeeping.
4. Create or switch to codex/<roadmap-slug>-delivered.
5. Push the final delivered branch.
6. Mark state completed_pending_pause.
7. Pause the automation.

Never:
- deliver future phases early
- silently expand scope
- mutate live user research workspaces during smoke tests
- revert unrelated user changes
- force-push main
- promote to main without explicit human instruction
```

## Automation Setup Workflow

To create a new automation:

1. Read the roadmap.
2. Confirm it is suitable for autonomous phase-gated delivery.
3. Pick slug and paths:

```text
ROADMAP_PATH=/Users/dzianissokalau/Documents/projects/async-research/roadmaps/not_started_<name>_roadmap.md
ROADMAP_SLUG=<snake_or_kebab_slug>
STATE_FILE=/Users/dzianissokalau/Documents/projects/async-research/roadmaps/automation/<slug>/delivery_state.json
DELIVERY_LOG=/Users/dzianissokalau/Documents/projects/async-research/roadmaps/automation/<slug>/delivery_log.md
REVIEW_DIR=/Users/dzianissokalau/Documents/projects/async-research/roadmaps/automation/<slug>/reviews
FINAL_BRANCH=codex/<slug-kebab>-delivered
```

4. Create cron automation with:

```text
kind: cron
status: PAUSED initially
rrule: FREQ=HOURLY;INTERVAL=1
model: gpt-5.5
reasoning effort: xhigh
execution environment: local
cwd: /Users/dzianissokalau/Documents/projects/async-research
```

5. Prefer hourly cadence for detached cron automations.
6. Read back the saved config.
7. If it saved as `ACTIVE`, pause it before final response.
8. Activate only when explicitly requested.

Observed operational caveat: status-only updates through the automation API can
be rejected. When that happens, use a full update or directly edit the saved
automation config if approved.

## Status Inspection Workflow

When the human asks for status:

1. Read automation config status.
2. Read delivery state.
3. Read tail of delivery log.
4. Check current branch.
5. List matching branches.
6. Check git status.
7. Check final branch and deep-review prompt if completion may have happened.
8. Be explicit about which roadmap and phase are being discussed.

Important lesson: avoid stale answers after a resume. Roadmaps may be renamed
from `not_started_` to `in_progress_` to `delivered_`, and automations can
advance several phases between user check-ins.

## Roadmap Lifecycle Cleanup

The workflow may rename roadmap files when a phase explicitly owns lifecycle
hygiene. Rename according to header status:

```text
Status: Not Started -> not_started_...
Status: In Progress -> in_progress_...
Status: Delivered -> delivered_...
```

Rules:

- prefer roadmap header/status when it clearly reflects delivered work
- update `/Users/dzianissokalau/Documents/projects/async-research/roadmaps/README.md`
- update inbound links
- move automation artifacts under `/Users/dzianissokalau/Documents/projects/async-research/roadmaps/automation/<slug>/`
- do not delete unique content
- keep historical mentions only when clearly labeled historical

This cleanup can surprise users. Status reports must say which roadmap was
renamed and why.

## Stop Conditions

Stop and ask the human operator when:

- external credentials, cloud access, paid APIs, or live network calls are needed
- tests cannot run for environmental reasons
- destructive git operations are needed
- user work would be overwritten
- product decisions are not answered by the roadmap
- scope would expand beyond current phase
- review/fix loop reaches max iterations
- reviewer and delivery context disagree on acceptance
- a roadmap path disappeared or was renamed and cannot be reconciled
- final promotion to `main` is requested but `origin/main` is not an ancestor
- push/publish/release is required but the roadmap forbids it or lacks explicit
  human approval

## Worktree Safety

Rules:

- never revert unrelated changes
- never stage broad `git add .`
- stage only files owned by the current phase or explicit user request
- use `git status --short` before staging and before final reporting
- when committing review fixes, stage only the files changed for that fix
- if unrelated dirty files are present, mention them and leave them untouched

## Review Bias Policy

Same-context self-review is biased. The workflow prefers fresh context review.

Bias levels:

- same thread self-review: useful but high bias
- fresh Codex context reviewing diff: moderate bias
- different model or human review: lower bias
- final deep-review prompt: broad independent assessment after all phases

If fresh review is unavailable, record that limitation as a residual risk.

## Common Failure Modes And Repairs

### Automation Saved As Active

Symptom:

```text
status = "ACTIVE"
```

after creating automation with requested `PAUSED`.

Repair:

- read back config immediately
- pause with full automation update or approved direct config edit

### Roadmap Renamed But Automation Prompt Still Points To Old Path

Symptom:

- state says roadmap is `/Users/dzianissokalau/Documents/projects/async-research/roadmaps/in_progress_...`
- automation prompt still says `/Users/dzianissokalau/Documents/projects/async-research/roadmaps/not_started_...`

Repair:

- update automation prompt/config to current roadmap filename
- confirm no stale path remains

### Completed State But Automation Still Active

Symptom:

```json
"status": "completed_pending_pause",
"all_phases_complete": true
```

but automation config says:

```toml
status = "ACTIVE"
```

Repair:

- pause automation
- ensure prompt has hard-stop guard

### User Confusion Between Roadmaps

Symptom:

Human asks why a delivered roadmap has queued Phase 1.

Cause:

Status answer mixed up the delivered roadmap with a later pivot roadmap.

Repair:

- identify exact roadmap path
- state which roadmap is delivered
- state which automation, if any, is active
- avoid saying "Phase N" without roadmap name

### Review Finds Medium Gaps After Delivery

Pattern:

- final deep review says delivered but identifies medium hardening gaps

Repair:

- implement focused follow-up patch on final delivered branch
- add regression tests
- rerun full verification
- commit and push final branch
- promote to main only if explicitly requested

## Requirements For The Future Skill

The skill should be able to help Codex:

1. Create a new roadmap delivery automation from a roadmap file.
2. Activate or pause an existing automation.
3. Inspect current status accurately.
4. Repair stale roadmap paths after lifecycle renames.
5. Explain why a roadmap was renamed or marked delivered.
6. Continue a blocked or paused phase if safe.
7. Route review findings into a fix pass.
8. Write or validate final deep-review prompts.
9. Promote final delivered branch to `main` only after explicit human approval.
10. Keep unrelated worktree changes untouched.

## Suggested Skill References

### `setup-automation.md`

Should include:

- when to use cron vs heartbeat
- how to choose slug, branch, state/log/review paths
- complete automation prompt skeleton
- activation/pause readback checklist
- cadence guidance
- model/reasoning defaults

### `phase-loop.md`

Should include:

- phase extraction checklist
- implementation scope rules
- verification selection
- delivery log update format
- commit/advance rules

### `review-and-fix.md`

Should include:

- reviewer prompt
- verdict definitions
- fix prompt
- max iterations
- how to record residual risks

### `state-log-and-branches.md`

Should include:

- delivery state schema
- delivery log schema
- review filename conventions
- branch naming
- status inspection commands

### `finalization-and-promotion.md`

Should include:

- all-phases-complete checklist
- final branch creation
- deep-review prompt requirements
- automation pause procedure
- GitHub branch push
- optional `main` promotion flow

### `troubleshooting.md`

Should include:

- saved ACTIVE despite requested PAUSED
- status-only automation update rejected
- renamed roadmap path mismatch
- completed state but active automation
- dirty worktree with unrelated changes
- final branch push failed
- review finds post-delivery hardening gaps

## Suggested Scripts

### `inspect_delivery_state.py`

Inputs:

```text
--repo-root /Users/dzianissokalau/Documents/projects/async-research
--roadmap-slug
--automation-id
```

Output JSON:

```json
{
  "automation_status": "ACTIVE",
  "roadmap_path": "/Users/dzianissokalau/Documents/projects/async-research/roadmaps/in_progress_example_roadmap.md",
  "state_status": "not_started",
  "current_phase": 1,
  "last_delivered_phase": 0,
  "blocked_reason": null,
  "current_branch": "codex/example-phase-0",
  "matching_branches": [],
  "worktree_dirty": false,
  "deep_review_prompt_exists": false,
  "warnings": []
}
```

Must be read-only.

### `validate_delivery_artifacts.py`

Checks:

- state file exists and is valid JSON
- delivery log exists
- review directory exists
- roadmap path exists
- automation prompt references current roadmap path
- lifecycle filename matches roadmap header
- `current_phase` agrees with roadmap current phase unless all complete
- completion state has deep-review prompt
- completed state has paused automation or hard-stop guard

Must not mutate files.

## Suggested Skill Trigger Evals

Should trigger:

```text
Set up automation for this roadmap using our phase-gated process.
What's the status of the autonomous delivery automation?
Pause the roadmap delivery automation.
Why did this roadmap get renamed to delivered_?
Route this deep review back into fixes.
Push the final delivered branch and promote to main.
Create a deep review prompt for the delivered roadmap.
Repair the automation after the roadmap was renamed.
```

Should not trigger:

```text
Fix this Python bug.
Review this PR.
Write a general product roadmap.
Summarize these research findings.
Create a new Codex skill unrelated to roadmap automation.
Run the test suite.
```

## Acceptance Criteria For The Skill

The future skill is useful only if it can reliably:

- set up a paused automation from a new roadmap
- activate the automation on request
- answer status without stale roadmap paths
- detect delivered/completed state and pause safely
- avoid confusing multiple roadmaps
- preserve unrelated worktree changes
- explain lifecycle renames
- enforce one-phase-at-a-time delivery
- require verification before delivery
- require review before phase advancement
- create final deep-review prompt
- avoid pushing until all phases are complete or until human explicitly requests
  promotion

## Minimal First Version Of The Skill

The first version can be small:

`SKILL.md` should include:

- when to use this skill
- first status inspection commands
- setup/activation/pause safety rules
- one-phase-at-a-time rule
- stop conditions
- reference file map

References should hold:

- full automation prompt skeleton
- state/log schemas
- review/fix prompts
- finalization checklist
- troubleshooting

Scripts can come later, but `inspect_delivery_state.py` would immediately reduce
stale-status mistakes.

## Non-Goals For The Skill

Do not make the skill:

- a general project manager
- a generic CI runner
- a release publisher
- a replacement for code review
- a hidden branch-pushing tool
- a system that mutates roadmaps without explicit phase ownership
- a tool that silently resolves product decisions

## Final Note

The strongest lesson from the current workflow is that autonomy is safe only
when it is boringly file-backed. The skill should continually push Codex back to
the same durable surfaces:

```text
roadmap
delivery_state.json
delivery_log.md
review files
git branch and commit history
verification output
automation.toml
```

If those surfaces disagree, the right behavior is to stop, report the mismatch,
and ask before moving on.
