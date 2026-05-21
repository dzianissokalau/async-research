# Guided Setup

Use guided setup only when the framework CLI or `research_ops/` workspace is
missing or unusable. Guided setup means diagnose, explain options, ask for the
specific approval, then verify after the approved action. Diagnosis is allowed;
environment or workspace mutation is not automatic.

## Setup Boundaries

Ask before any action that:

- creates files or directories
- creates or modifies virtual environments
- installs packages
- uses network access
- clones, fetches, or pulls code
- modifies shell configuration
- initializes `research_ops/`
- writes outside the current workspace

Global installs are not a default path. Prefer project-local setup because it is
easier to inspect, undo, and keep scoped to one workspace.

## Setup Source Order

Prefer setup sources in this order:

1. Checked-out framework repository and project-local `.venv`.
2. Existing CLI path already present on the machine.
3. Pinned package or release only after explicit approval.

If the current checkout is the async-research framework repo, say so explicitly
and treat `research_ops/` creation as a privacy-boundary decision. A framework
tool repo is not a default target for private research state.

## Missing CLI Flow

When `async-research` is unavailable:

1. Report that the CLI was not found in the active shell or project-local
   `.venv`.
2. State the setup sources in preference order.
3. Ask the user to choose and approve one option before running any command that
   creates files, installs packages, or uses the network.
4. After approved setup, restart startup discovery from CLI detection.
5. Run `async-research version` and `async-research --help`.
6. Probe recipe-critical capabilities before continuing.

Safe options to present:

- "Use an existing CLI path you provide."
- "Use the checked-out framework repo with a project-local `.venv`; this may
  require approval to create the environment and install locally."
- "Install a pinned package or release only if you explicitly approve network or
  package-manager use."

Do not present global installation as the default recommendation. If the user
asks for it, restate the scope and risks before proceeding.

## Version And Capability Drift

The skill is authored against `async-research-workflow==0.3.0a1`. A different
detected version is not an automatic refusal, but it must be surfaced before
operation.

When drift is detected:

- report the detected version and supported range
- run `async-research --help`
- probe subcommand help for `workflow next` and `console snapshot`
- avoid recipes whose commands are missing
- ask for guidance if a required public command is absent and no documented
  fallback exists

Do not call private Python modules to compensate for missing public commands.
Phase 3 may label advanced routes if a public command truly does not exist.

## Missing Workspace Flow

When no `research_ops/` exists:

1. Identify the proposed path.
2. Explain that initialization creates file-backed research state.
3. Check whether the target is a private research repo, a framework/tool repo,
   or a repo with unknown visibility.
4. Stop and ask before running `async-research init` or creating files.
5. After approved initialization, run startup validation checks immediately:
   `schema-check`, `readiness --dry-run`, `health --dry-run`, `workflow next`,
   and `console snapshot --json`.

If the repo is public, is probably public, or is the framework repo, ask for an
explicit private/approved target before writing research state. If the user
intends a separate private workspace, ask for that path and restart discovery.

## Approval Request Shape

Use this shape for setup approvals:

```text
Decision needed: <CLI setup | workspace initialization | network/package use>
Current state: <what was detected>
Proposed target: <path or command family>
Why approval is needed: <writes/network/privacy boundary>
Safe default: do nothing until approved
Options:
1. <read-only/status option>
2. <approved local setup option>
3. <provide another path or defer>
```

Do not combine multiple setup approvals into one broad request. For example,
creating `.venv`, installing a package, and initializing `research_ops/` are
separate decisions unless the user already gave explicit permission for the
whole bounded setup sequence.

## Optional Helper Use

The startup helper can support guided setup diagnosis:

```bash
.venv/bin/python skills/async-research-operator/scripts/inspect_workspace.py
```

The helper is read-only. It emits JSON setup recommendations, version/capability
diagnostics, privacy-boundary warnings, and the next safe action. It does not
create the environment, install packages, clone repositories, initialize
`research_ops/`, or edit files.

## Stop Conditions During Setup

Stop and ask when setup encounters:

- missing approval for file writes, package installs, network use, cloning, or
  shell configuration changes
- credentials, external accounts, paid APIs, paid data, or cloud spend
- destructive cleanup or replacement of existing files
- unclear target workspace path
- public/private boundary ambiguity
- missing required public commands after setup
- failed validation checks after initialization
