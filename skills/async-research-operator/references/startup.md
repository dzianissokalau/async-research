# Startup

Use this reference when entering an unknown repository or resuming a prior
async-research session.

## Goal

Determine where the framework CLI is, where the research workspace is, whether
the privacy boundary is safe, and what the next safe action is without trusting
chat history as state.

## Startup Protocol

Run these checks in order. Treat failures as diagnostic facts, not permission to
install, initialize, or mutate anything.

1. Run `pwd`.
2. Run `git rev-parse --is-inside-work-tree`.
3. Decide whether the current repo is the framework repo, a research workspace,
   a framework checkout with local research state, or an unknown repo.
4. Locate the CLI in this order:
   - active shell command: `command -v async-research`
   - project-local command: `.venv/bin/async-research`
   - existing installed command path explicitly provided by the user
5. If no usable CLI is found, enter guided setup mode:
   - report that `async-research` is unavailable in the current environment
   - list safe setup options from `setup.md`
   - ask before creating `.venv`, installing packages, cloning or fetching,
     modifying shell config, using the network, or writing outside the workspace
   - avoid global installs by default
   - after approved setup actions, restart CLI detection from step 4
6. Run `async-research version`.
7. Compare the detected version to the supported range
   `async-research-workflow==0.3.0a1`. Report version drift and continue only
   after probing command capabilities.
8. Run `async-research --help` and probe top-level command capabilities. Probe
   nested help for recipe-critical commands such as `workflow next` and
   `console snapshot`.
9. If a recipe references a missing command, report the gap and avoid inventing
   a replacement internal action.
10. Locate the workspace in this order:
    - explicit user path
    - current repository `research_ops/`
    - known private workspace path only if the user provided it in this turn
11. If no `research_ops/` exists, offer guided workspace bootstrap:
    - explain the path where state would be created
    - confirm the repo is private or explicitly approved for research state
    - ask before running `async-research init` or creating files
    - run validation checks immediately after approved initialization
12. Check the privacy boundary. If `research_ops/` would be created or written
    inside a public tool repo, a framework repo, or a repo whose visibility is
    unknown, stop and ask before writing research state.
13. Run read-only checks when the CLI and workspace both exist.
14. Summarize setup actions taken or still needed, capability gaps, version
    drift, privacy status, read-only check results, and the next safe action.

## Read-Only State Checks

When the CLI and workspace both exist, use these commands before broad state
reports:

```bash
async-research schema-check research_ops
async-research readiness research_ops --dry-run
async-research health research_ops --dry-run
async-research workflow next research_ops
async-research console snapshot research_ops --json
```

The first four commands provide object-level status and blocker details. The
console snapshot is a compact dashboard-alignment check, not the sole authority.
If raw CLI output and the snapshot disagree, trust the raw CLI for the specific
object and report the discrepancy.

## Optional Inspection Helper

The optional helper can collect the startup facts without mutating files:

```bash
.venv/bin/python skills/async-research-operator/scripts/inspect_workspace.py
```

Use `--workspace`, `--research-ops`, or `--cli` when the user gives explicit
paths. Add `--run-read-only-checks` only when a CLI and `research_ops/` are
available and the user asked for inspection or status. The helper emits JSON
only and records `mutations_performed: []`.

The helper may:

- detect the candidate CLI path
- detect candidate `research_ops/`
- inspect git worktree and remotes
- flag framework/public/unknown privacy boundaries
- compare the detected framework version to the supported range
- list available top-level and recipe-critical subcommands
- run the read-only state checks when explicitly invoked
- produce setup recommendations

The helper must not create environments, install packages, clone repositories,
initialize workspaces, edit files, or make network calls.

## Startup Report

Keep the first report compact:

```text
Mode: read_only | guided | bounded_autonomous | maintenance
Workspace: <path or missing>
CLI: <path or missing>, version <detected>, supported range <range>
Capabilities: <ok or missing commands>
Privacy: <safe, approval required, or unknown>
Checks: <schema/readiness/health/workflow/console summary>
Next safe action: <one bounded action or approval request>
```

Never describe setup as complete if the CLI is missing, version/capability drift
is unresolved, `research_ops/` is missing, privacy approval is needed, or
read-only checks failed.
