# Docs Packaging Review

This review records the P3 decision for packaged protocol docs.

## Decision

Keep Markdown protocol and operator docs packaged in `async_research_workflow`
for the alpha line. Do not split the docs into an optional extra or external
download for the current alpha package.

The package is intentionally file-backed and agent-facing. Operators and LLM
implementers need the runbooks, scheduler prompts, artifact contracts, framework
requirements, and governance protocols available from an installed wheel, not
only from a source checkout.

## Current Footprint

Reviewed again on 2026-05-11 with a fresh build:

```bash
.venv/bin/python -m build --outdir /private/tmp/arw-docs-packaging-review
```

| Measure | Value |
| --- | ---: |
| Wheel artifact | 586,416 bytes |
| Source distribution artifact | 589,490 bytes |
| Wheel package payload, uncompressed | 1,976,398 bytes |
| Packaged docs files | 47 Markdown files |
| Packaged docs, uncompressed | 427,255 bytes |
| Packaged docs, compressed in wheel | 153,593 bytes |
| Packaged docs share of compressed wheel | 26.2% |

The tracked packaged docs under `src/async_research_workflow/docs/` remain
comfortably below the 1 MiB packaging threshold. The installed-wheel cost is
about 154 KB (150 KiB) compressed, which is not enough to justify removing
useful offline guidance from the wheel.

## Support Signal

The support and review evidence recorded in this repo points toward clearer
operator guidance, shorter quickstarts, public command paths, and better
workflow surfaces. It does not include a user or reviewer report about
wheel-size, installation, or distribution pain caused by packaged Markdown docs.

Recent operator UX work also made the packaged docs more valuable: the first
success quickstart, scheduler prompts, task contracts, review protocols,
dashboard spec, and internal helper boundary are all meant to be reachable from
an installed package. Splitting them out now would add release and support
complexity without a measured user benefit.

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
