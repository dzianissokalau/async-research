# Codex Dogfood Rollout Evidence - 2026-05-20

Skill source: repository package, not installed into $CODEX_HOME.
Workspace: `/Users/dzianissokalau/Documents/projects/async-research`.
Codex context: roadmap automation session with file and terminal access.
Autonomy: `read_only` for first-use inspection.

## First-Use Prompt

First-use prompt:

```text
Use the async-research-operator skill. Inspect this workspace, report the current state, and recommend the next safe action without writing files.
```

## Commands used:

```bash
pwd
git rev-parse --is-inside-work-tree
.venv/bin/async-research version
.venv/bin/python skills/async-research-operator/scripts/inspect_workspace.py
.venv/bin/python skills/async-research-operator/scripts/inspect_workspace.py --run-read-only-checks
.venv/bin/python skills/async-research-operator/scripts/inspect_workspace.py --workspace src/async_research_workflow/examples/coffee_pilot_deliverable_maturity --research-ops research_ops --run-read-only-checks
```

## Observed State

- CLI source: project-local `.venv/bin/async-research`.
- CLI version: `0.2.0a5`, matching `async-research-workflow==0.2.0a5`.
- Command capability probe: no missing expected top-level, workflow, or console
  snapshot commands.
- privacy_boundary: approval_required.
- Boundary reasons: framework repo is not a default research-state target, and
  hosted remote visibility is unknown.
- research_ops: missing.
- Read-only checks: skipped because `research_ops/` is missing.
- mutations_performed: [].

## Existing Coffee-Style Workspace Status

The existing example workspace at
`src/async_research_workflow/examples/coffee_pilot_deliverable_maturity` was
inspected with explicit `research_ops` and read-only checks.

- CLI source: repo-root `.venv/bin/async-research`.
- CLI version: `0.2.0a5`, matching `async-research-workflow==0.2.0a5`.
- research_ops: found.
- Schema check: passed.
- Readiness dry-run: failed with missing operational files and data source audit
  blockers.
- Health dry-run: passed with error-severity alerts.
- Workflow next and console snapshot: ran read-only.
- privacy_boundary: approval_required.
- mutations_performed: [].
- Next safe action: resolve failing read-only checks before operating the
  workspace.

## Report

Files touched: none.
Caveats: this was a source-package dogfood pass in the roadmap automation
session, not a fresh installed-skill Codex session.
Unresolved gaps: full private-workspace rollout still needs a human-approved
workspace with `research_ops/` so the checklist can exercise a bounded worker
loop, review loop, human gate, deliverable maturity report, and
acceptance/readiness mismatch stop.
Next safe action: ask before initializing research_ops or writing research
state in this framework repository.

## Checklist Items Exercised

- missing `research_ops/` bootstrap diagnosis
- command-capability report
- version report
- privacy-boundary stop
- read-only first-use report
- existing coffee-style workspace status
- readiness-failure stop before operation

Result: pass for read-only first-use and stop behavior.

## Limitations:

- The skill was referenced from the repository source package and was not copied
  into `$CODEX_HOME/skills/async-research-operator/`.
- No write-capable dogfood loop was run; the existing coffee-style example
  workspace was inspected read-only and stopped on readiness blockers.
- No environment creation, package install, network use, workspace
  initialization, or write outside the workspace was attempted.
