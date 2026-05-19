# Guided Setup

Use guided setup only when the framework CLI or `research_ops/` workspace is
missing or unusable.

## Setup Boundaries

Ask before any action that creates files, installs packages, uses the network,
clones or fetches, modifies shell configuration, initializes `research_ops/`, or
writes outside the workspace. Global installs are not a default path.

Prefer setup sources in this order:

1. Checked-out framework repository and project-local `.venv`.
2. Existing CLI path already present on the machine.
3. Pinned package or release only after explicit approval.

## Missing CLI

Report that `async-research` is unavailable, list safe options, and ask which
option to use. Do not create `.venv`, run package installs, or fetch code
without approval.

## Missing Workspace

If no `research_ops/` exists, explain the target path and privacy implications.
Ask before running initialization commands or creating files.

## Phase Ownership

Phase 2 expands this into a complete guided setup flow with version and
capability checks. Phase 3 adds exact write recipes.
