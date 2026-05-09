# Docs Packaging Review

This review records the P3 decision for packaged protocol docs.

## Decision

Keep Markdown protocol and operator docs packaged in `async_research_workflow`
for the alpha line.

The package is intentionally file-backed and agent-facing. Operators and LLM
implementers need the runbooks, scheduler prompts, artifact contracts, framework
requirements, and governance protocols available from an installed wheel, not
only from a source checkout.

## Current Footprint

At review time, the tracked packaged docs under
`src/async_research_workflow/docs/` were comfortably below the 1 MiB packaging
threshold.
That is small compared with the templates, schemas, benchmark cases, and runtime
code, and it does not justify removing useful offline guidance from the wheel.

## Packaging Rules

- Package Markdown docs that are useful to operators, schedulers, reviewers, or
  LLM implementers.
- Do not package screenshots, media, generated exports, local notes, or large
  binary artifacts under `docs/`.
- Keep `pyproject.toml` package-data explicit: `docs/**/*.md` is allowed;
  broad `docs/**/*` style globs are not.
- Keep the packaged docs footprint below 1 MiB unless a future release records a
  new reason and acceptance threshold.
- Keep individual packaged docs below 128 KiB unless there is a measured need.
- Verify key packaged docs through `importlib.resources` so wheel installs and
  editable installs behave the same way.

## Revisit Triggers

Reopen this decision if any of these become true:

- Packaged docs exceed 1 MiB.
- A public/private docs split is introduced.
- Packaged docs start including generated, project-specific, or private content.
- Users report wheel-size, installation, or distribution pain.

Until then, docs packaging changes should be conservative: keep useful protocol
docs available, trim only clearly stale or non-operator material, and preserve
resource access from installed packages.
