# Startup

Use this reference when entering an unknown repository or resuming a prior
async-research session.

## Goal

Determine where the framework CLI is, where the research workspace is, and what
the next safe action is without trusting chat history as state.

## Initial Discovery

Run the first five checks from `SKILL.md`. Treat failures as diagnostic facts,
not permission to install or mutate anything.

Prefer this order for locating the CLI:

1. Active shell command: `command -v async-research`.
2. Project-local command: `.venv/bin/async-research`.
3. Existing installed command explicitly provided by the user.

Prefer this order for locating the workspace:

1. Explicit user path.
2. Current repository `research_ops/`.
3. A known private workspace path only if the user provided it in this turn.

## Read-Only State Checks

When the CLI and workspace both exist, use read-only commands before reporting:

```bash
async-research schema-check research_ops
async-research readiness research_ops --dry-run
async-research health research_ops --dry-run
async-research workflow next research_ops
async-research console snapshot research_ops --json
```

If a referenced command is unavailable, report version or capability drift and
avoid inventing an internal replacement.

## Phase Ownership

Phase 2 owns the full startup protocol, version comparison, capability probing,
privacy-boundary check, and optional `inspect_workspace.py` helper.
