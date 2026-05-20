---
name: async-research-operator
description: Operate async-research workspaces through public CLI commands, dashboard snapshots, and file-backed research_ops state. Use when Codex is asked to inspect, set up, continue, run, review, report on, or find the next safe action for an async-research workflow, including research_ops, async-research dashboard/console, workflow next/status, acceptance, readiness, gates, or operator automation requests. Use for guided setup and bounded operation; do not use for generic research advice, unrelated coding tasks, or non-async-research project status.
---

# Async Research Operator

## Purpose

Operate an async-research workspace safely through public `async-research` CLI
commands, dashboard snapshots, and file-backed `research_ops/` state. Default to
`guided` autonomy unless the user asks only for inspection (`read_only`) or
explicitly asks for one bounded autonomous loop (`bounded_autonomous`).

## First Five Checks

Run these before deciding what to do next. Use the detected CLI path in place of
`async-research` when needed.

```bash
pwd
git rev-parse --is-inside-work-tree
command -v async-research || test -x .venv/bin/async-research
async-research version
async-research workflow next research_ops
```

If `research_ops/` is present and the CLI is usable, also prefer
`async-research console snapshot research_ops --json` before broad status
reports. If any command is missing or unsafe to run, stop and report the gap.

## Operating Rules

- Treat `research_ops/` files as the highest authority, followed by public CLI
  JSON output, dashboard or console snapshots, user messages, then model memory.
- Prefer public `async-research` commands over direct file edits.
- Dry-run before writes whenever the command supports it.
- Operate one bounded task at a time.
- Ask before creating environments, installing packages, using network access,
  cloning or fetching, modifying shell config, initializing `research_ops/`, or
  writing outside the workspace.

## Stop Conditions

Stop and ask the human when the next action involves credentials, paid services,
network setup, destructive file or git operations, publication/submission,
public/private boundary ambiguity, target-venue or product decisions, human
gates, broken required tooling, acceptance/readiness contradictions, dashboard
state that conflicts with file-backed state, or a claim that deliverables are
ready without the required checks.

## Reference Map

- [startup.md](references/startup.md): initial workspace and CLI discovery.
- [setup.md](references/setup.md): guided setup boundaries and approval points.
- [command-recipes.md](references/command-recipes.md): command recipe structure
  and mutation safety rules.
- [roles.md](references/roles.md): role modes and autonomy vocabulary.
- [safety-and-stop-conditions.md](references/safety-and-stop-conditions.md):
  source-of-truth hierarchy and hard stops.
- [reporting.md](references/reporting.md): concise status, blocker, and decision
  request formats.
- [provider-notes.md](references/provider-notes.md): Codex-first scope and
  provider portability limits.
- [trigger-evals.md](references/trigger-evals.md): selected description,
  candidate descriptions, and trigger examples.
- [behavioral-evals.md](references/behavioral-evals.md): fixture scenarios,
  scoring rubric, and forward-test evidence.
- [packaging.md](references/packaging.md): install, update, uninstall, first-use,
  and dogfood rollout instructions.

Load only the reference file needed for the current task.
