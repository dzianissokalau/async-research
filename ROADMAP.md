# Async Research Roadmap

Status: public alpha hardening roadmap

Last reviewed: 2026-05-04

## Project Summary

`async-research` is an alpha Python CLI and starter workspace for low-cost
asynchronous research workflows. It uses repo files as durable shared memory:
queue, task state, source governance, review gates, accepted evidence, cost
tracking, metrics, decisions, and human review surfaces.

The package is currently usable for careful dogfooding. Core checks are green,
the benchmark routes known-bad cases safely, and runtime dependencies remain
standard-library-only. It is not ready for broad promotion yet because public
package hygiene still needs work: command/documentation drift, a domain-specific
starter, duplicated runtime assets, and thin Python-level tests.

## North Star

Build `async-research` into an installable, safe, generic async research
workflow for solo operators and small teams.

The desired product shape:

- One blessed user interface: the `async-research` CLI.
- A generic starter workspace that works outside the original real-estate
  dogfood domain.
- Worked examples that remain useful without looking like hidden live state.
- Durable, inspectable repo files for queue, task state, source governance,
  review, evidence, cost, metrics, decisions, and human review.
- Fail-closed gates for malformed state, invalid transitions, stale sources,
  stale accepted memory, missing reviewer metadata, budget pressure, and human
  escalation.
- Low operating cost and high-quality output prioritized above speed.
- Clear docs that an LLM worker can follow without inventing missing process.

## Review Synthesis

Three reviews now agree on the core diagnosis:

- The governance design is unusually mature for an alpha.
- The core smoke checks are meaningful and currently green.
- The project still looks partly like owner dogfooding wrapped into a package.
- CLI/docs drift is a real trust problem.
- The real-estate-only starter conflicts with the reusable package claim.
- Duplicated schemas and duplicated mission/benchmark assets risk future drift.
- Direct Python test coverage is too thin for a safety-oriented workflow.
- CI should validate packaged artifacts, not only editable installs.

The reviews also contain some recommendations that are valid but should be
sequenced carefully:

- Refactoring all script imports away from `sys.path` hacks is important, but
  it should happen after the immediate user-facing safety and docs drift fixes.
- Splitting the CLI into a command registry may become useful, but it is not
  a P0 for a 288-line alpha CLI.
- Removing packaged docs from the wheel is not urgent. The protocol docs are
  useful context for agents and operators; wheel size should be revisited only
  after the CLI and docs have a stable public shape.
- Broad command renames should be avoided until there is user feedback. Add
  help text and aliases before breaking names.

The most severe concern from the reviews is valid: `starter-smoke` is
destructive by default because `--force` is effectively always true. That should
be fixed before encouraging anyone to run commands on directories they care
about.

## Progress Table

| Date | Area | Status | What was done | How it was done | Evidence |
| --- | --- | --- | --- | --- | --- |
| 2026-05-03 | Phase 0: Roadmap | Done | Established the public alpha hardening roadmap. | Added this root `ROADMAP.md` with current state, north star, priorities, phases, concerns, and LLM operating rules. | Commit `d37abc3`. |
| 2026-05-04 | P0: Safety defaults | Done | Made `starter-smoke` non-destructive by default. | Changed `--force` from implicit to explicit, returned structured `target_exists` JSON for existing non-empty work dirs, and added marker-preservation tests. | Commit `68283a0`; `.venv/bin/python -m unittest tests.test_cli_safety`; `async-research starter-smoke /tmp/async-research-starter --force`. |
| 2026-05-04 | P0: Transactional init | Done | Made `init` transactional for bootstrap failures. | Staged template copy, backed up existing targets on forced replacement, restored old targets or removed new partial targets when metrics bootstrap failed, and added rollback tests. | Commit `fcb5ea0`; acceptance-suite, starter-smoke, benchmark, simulate-week, and compileall passed. |
| 2026-05-04 | P0: Rollback hardening | Done | Closed verification edge cases found after the first transactional init patch. | Prevented rollback from deleting an untouched target when copy fails before backup, returned JSON for file-valued `starter-smoke` paths, made path removal symlink-safe, and preserved backup details if restore fails. | Commit `f07999e`; 11 safety tests, acceptance-suite, starter-smoke, benchmark, simulate-week, and compileall passed. |
| 2026-05-04 | P0: Interface and resource drift | Done | Made `async-research` the blessed documented interface where wrappers exist and added drift guards. | Replaced stale public examples-script references in operator docs, scheduler prompts, starter templates, and examples with `async-research` commands or explicit `python -m async_research_workflow.scripts.<module>` advanced forms. Added tests for stale/nonexistent example references, duplicated schema/policy drift, and importlib resource access. | This change; `.venv/bin/python -m unittest tests.test_doc_references tests.test_packaged_resources`. |
| 2026-05-04 | P0: Internal docs drift | Done | Cleaned the remaining internal protocol references to removed examples-script and example schema/template paths. | Expanded doc-reference tests across all packaged docs, templates, and examples; migrated internal protocol command snippets to `async-research` where wrappers exist and to `python -m async_research_workflow.scripts.<module>` for advanced helpers. | This change; `.venv/bin/python -m unittest tests.test_doc_references`; stale-reference scan returned no matches. |
| 2026-05-04 | P1: Generic starter | Done | Added a domain-neutral default starter while keeping real-estate as a worked example. | Introduced a generic empty `research_ops` template, made it the default for `init` and `starter-smoke`, kept real-estate under `--template real-estate`, and added resource/CLI tests for both templates. | This change; targeted template tests, default and real-estate init/smoke checks, acceptance-suite, benchmark, and compileall passed. |
| 2026-05-04 | P1: Runtime resource canonicalization | Done | De-duplicated schema, benchmark, and example policy resources behind canonical loaders. | Kept schemas under `schemas/`, default mission policy at package root, and benchmark cases under `benchmarks/`; routed runtime defaults through `async_research_workflow.resources`; removed duplicate packaged resource copies and added guards against reintroducing them. | This change; packaged-resource/doc tests, acceptance-suite, benchmark, starter-smoke, and compileall passed. |

## Prioritized Roadmap

### P0: Safety And Trust

P0 work is required before recommending the package beyond careful alpha users.

1. Fix destructive smoke behavior.
   - Make `starter-smoke` non-destructive by default.
   - Require explicit `--force` or a temp/default work directory for deletion.
   - Add a regression test proving an existing directory is not removed unless
     force is explicit.
   - Acceptance: running `starter-smoke` against an existing non-empty directory
     exits safely and leaves existing files untouched.

2. Make `init` safer.
   - Make init transactional: prepare in a temp directory, run bootstrap
     metrics/schema steps there, then move into place.
   - On failure, avoid leaving a partially initialized workspace.
   - Keep `--force` for deliberate overwrite behavior only.
   - Acceptance: forced and non-forced init paths have tests for existing,
     empty, non-empty, and failed-bootstrap cases.

3. Make `async-research` the blessed user interface.
   - Replace user-facing docs and starter task instructions that point to
     removed examples-script paths when an equivalent CLI command exists.
   - For operations not yet exposed by the CLI, either add a CLI wrapper or
     document the `python -m async_research_workflow.scripts.<module>` form as
     internal/advanced.
   - Acceptance: a repo scan has no stale references to removed examples-script
     paths in README, starter templates, or operator docs.

4. Add drift detection tests.
   - Add tests that fail when docs reference nonexistent packaged files.
   - Add tests that detect duplicate schema basenames or mismatched schema
     hashes until canonicalization is complete.
   - Add tests for packaged resource access through installed-package APIs.
   - Acceptance: CI catches schema/resource/docs drift before release.

### P1: Public Alpha Readiness

P1 work makes the package credible for external alpha users.

1. Add a generic default template.
   - Make `async-research init` default to a generic template.
   - Keep the current real-estate starter as `--template real-estate`.
   - The generic starter should have empty or clearly placeholder queue/source
     files, no live accepted outputs, no live health report pretending to be a
     completed check, and domain-neutral mission guidance.
   - Acceptance: `starter-smoke` runs against both generic and real-estate
     templates.

2. Canonicalize runtime resources.
   - Choose one schema location, preferably `schemas/`.
   - Load schemas and package data through one resource helper layer.
   - Remove or generate duplicate root-level schema/policy/benchmark copies.
   - Acceptance: no duplicated schema files are shipped unless generated and
     verified; all scripts load canonical resources.

3. Expand Python-level regression tests.
   - Cover malformed `status.json`, missing `schema_version`, invalid
     transitions, stale accepted memory, stale source freshness, missing review
     metadata, lock contention, budget blocks, and result acceptance ledger
     writes.
   - Use isolated temp workspaces.
   - Keep acceptance-suite and benchmark as integration gates.
   - Acceptance: targeted failures identify the failing contract without
     relying only on the full acceptance suite.

4. Make CI packaging-aware.
   - Add Python 3.13 to the matrix while the classifier advertises 3.13.
   - Run pytest.
   - Build wheel and sdist.
   - Install from the built wheel and run a small CLI/resource smoke test.
   - Acceptance: CI verifies the way users install the package, not only
     editable installs.

### P2: Usability And Contributor Clarity

P2 work improves adoption and maintainability after the safety foundation lands.

1. Rewrite the root README for first-time users.
   - Explain the research loop in plain English.
   - Add a lifecycle diagram from inbox through accepted/rejected/needs-human.
   - Show one worked task loop from init to accepted output.
   - Document what each command reads and writes.
   - Include the Python 3.11+ requirement explicitly in setup.
   - Acceptance: a new user can understand the purpose before reading protocol
     docs.

2. Document exit codes and CLI behavior.
   - Centralize exit-code constants or document command-specific codes clearly.
   - Add help text for every top-level and nested subcommand.
   - Keep existing command names stable unless there is a very strong reason.
   - Acceptance: `async-research --help` and subcommand help are useful without
     reading source.

3. Clean script imports.
   - Replace sibling-script `sys.path.insert` patterns with package imports.
   - Ensure scripts still work through the CLI and `python -m`.
   - Avoid changing behavior while doing this refactor.
   - Acceptance: acceptance-suite, starter-smoke, benchmark, simulate-week,
     compileall, and import tests all pass after the import cleanup.

4. Improve benchmark and simulation packaging behavior.
   - Remove assumptions that installed code lives near a repo root.
   - Prefer in-process module invocation where practical.
   - Keep live-workspace isolation guards based on explicit user paths, not
     inferred package layout.
   - Acceptance: benchmark works from editable install and wheel install.

### P3: Release Polish

P3 work is useful but should not distract from P0/P1.

1. Package metadata and repo hygiene.
   - Add `[project.urls]`, keywords, explicit license metadata, changelog, and
     contributor guidance.
   - Add issue and PR templates when external contributors appear.
   - Keep Apache-2.0.

2. Optional command naming cleanup.
   - Consider aliases such as `accepted revalidate` or `review-surface`.
   - Avoid breaking existing command names during alpha hardening.
   - Prefer aliases and docs first.

3. Optional CLI architecture refactor.
   - Defer splitting `cli.py` until command count or review pain justifies it.
   - If refactored, preserve command behavior and JSON output contracts.

4. Optional docs packaging review.
   - Keep protocol docs packaged while they are useful to operators and agents.
   - Revisit wheel size only after docs have a stable public/private split.

## Implementation Phases

### Phase 0: Roadmap And Baseline

- Commit this roadmap.
- Keep current checks green as the baseline.
- Do not make broad architecture changes before P0 safety work.

### Phase 1: Safety Defaults

- Fix `starter-smoke` force behavior.
- Make `init` transactional.
- Add focused tests for destructive and partial-init cases.
- Run acceptance-suite, starter-smoke, benchmark, simulate-week, and compileall.

### Phase 2: Interface And Docs Drift

- Decide which operational scripts need CLI wrappers now.
- Replace stale examples-script references in public docs and starter tasks.
- Add doc-resource drift tests.
- Update the example GitHub worker to use the blessed invocation forms.

### Phase 3: Generic Template

- Add a generic starter template and make it the default.
- Keep real-estate as an explicit worked example.
- Ensure no generic starter file contains private paths, live accepted outputs,
  or domain-specific claims.
- Smoke-test both templates.

### Phase 4: Resource Canonicalization

- Move schema loading behind one resource helper.
- De-duplicate schemas, mission policy, and benchmark data.
- Add tests that prove the installed package can load every runtime resource.

### Phase 5: Test And CI Hardening

- Expand pytest coverage for negative paths.
- Add Python 3.13, wheel/sdist build, and wheel-install smoke checks to CI.
- Keep integration checks as the final gate.

### Phase 6: Public Documentation

- Rewrite README around task lifecycle and operator workflow.
- Add command map, exit-code contract, and worked example.
- Add contribution and release notes after the package shape stabilizes.

## Concerns And Replies

### Concern: "This is not ready as public alpha."

Reply: It is acceptable as a visible alpha for careful users, because the core
checks are green and the package is honest about alpha status. It is not ready
for broad promotion, tutorials, or claims of general usability until P0 and the
core P1 items are complete.

### Concern: "The real-estate starter makes the package look non-generic."

Reply: Correct. Keep the real-estate starter as a worked example, but add a
generic default template before asking outside users to adopt the package.

### Concern: "Delete packaged docs to reduce wheel bloat."

Reply: Not now. The docs are useful context for operators and LLM workers. The
more urgent issue is separating first-user guidance from internal protocol
material. Revisit packaging size later with data.

### Concern: "Split the CLI into a command package immediately."

Reply: Defer. The CLI is currently manageable. The immediate risks are safety
defaults, docs drift, and tests. A CLI architecture refactor should happen only
when it reduces real maintenance pain.

### Concern: "Rename confusing commands now."

Reply: Avoid breaking names during alpha hardening. Add help text, docs, and
possibly aliases first. Rename only after observing actual user confusion.

### Concern: "Add dependencies for testing and developer tooling."

Reply: Runtime should remain standard-library-only for v0.1. Dev-only
dependencies such as pytest or ruff are acceptable under optional development
extras if they do not affect the installed runtime dependency contract.

### Concern: "The schema validator is intentionally limited."

Reply: Keep fail-closed behavior. Either document the supported schema keyword
subset clearly or expand support with tests. Do not silently accept unsupported
keywords.

## Operating Rules For LLM Implementers

- Treat this roadmap as priority order. Do not start P2/P3 polish while P0
  safety or trust issues remain.
- Keep v0.1 runtime dependencies standard-library-only unless a maintainer
  explicitly changes that policy.
- Preserve fail-closed behavior for malformed state, invalid transitions,
  missing reviewer metadata, stale sources, stale accepted memory, and budget
  pressure.
- Do not assume access to private repos, local absolute paths, or dogfood state.
- Prefer isolated fixture tests over tests that require a live research
  workspace.
- Keep documentation and starter templates free of stale paths.
- Before committing behavior changes, run:
  - `async-research acceptance-suite`
  - `async-research starter-smoke /tmp/async-research-starter`
  - `async-research benchmark`
  - `async-research simulate-week <fixture-research-ops>`
  - `python -m compileall src tests`
- For docs-only changes, at minimum run `git diff --check` and a targeted scan
  for the touched roadmap/docs anchors.

## Release Gate

Before promoting beyond alpha dogfooding, the package should satisfy:

- P0 complete.
- Generic template available and documented.
- CLI/docs drift tests in CI.
- Built-wheel install smoke test in CI.
- README explains the full task lifecycle.
- No public docs point to nonexistent package paths.
- Core checks green on Python 3.11, 3.12, and 3.13.
