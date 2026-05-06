# Async Research Public Alpha Hardening Roadmap

Status: public alpha hardening roadmap

Last reviewed: 2026-05-05

## Project Summary

`async-research` is an alpha Python CLI and starter workspace for low-cost
asynchronous research workflows. It uses repo files as durable shared memory:
queue, task state, source governance, review gates, accepted evidence, cost
tracking, metrics, decisions, and human review surfaces.

The package is currently usable for careful dogfooding and visible alpha use.
Core checks are green, the benchmark routes known-bad cases safely, runtime
dependencies remain standard-library-only, and the original P0/P1/P2/P3
hardening work has addressed the most obvious packaging and starter risks. The
next risk frontier is public/internal CLI surface clarity: users should see the
commands they are taught to run in `async-research --help`, while lower-level
runner and maintainer primitives should stay clearly marked as advanced.

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

The initial external reviews agreed on the core diagnosis:

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

The most severe initial concern was valid: `starter-smoke` was destructive by
default because `--force` was effectively always true. That risk has been fixed
and is now covered by safety regression tests.

Most of those initial hardening risks are now closed. The current review signal
has shifted from packaging safety toward CLI surface governance: deciding which
script-backed operations deserve public wrappers, which should remain advanced,
and how docs should migrate only after the public contract exists.

## Progress Table

| Date | Area | Status | What was done | How it was done | Evidence |
| --- | --- | --- | --- | --- | --- |
| 2026-05-03 | Phase 0: Roadmap | Done | Established the public alpha hardening roadmap. | Added the initial roadmap with current state, north star, priorities, phases, concerns, and LLM operating rules. | Commit `d37abc3`. |
| 2026-05-04 | P0: Safety defaults | Done | Made `starter-smoke` non-destructive by default. | Changed `--force` from implicit to explicit, returned structured `target_exists` JSON for existing non-empty work dirs, and added marker-preservation tests. | Commit `68283a0`; `.venv/bin/python -m unittest tests.test_cli_safety`; `async-research starter-smoke /tmp/async-research-starter --force`. |
| 2026-05-04 | P0: Transactional init | Done | Made `init` transactional for bootstrap failures. | Staged template copy, backed up existing targets on forced replacement, restored old targets or removed new partial targets when metrics bootstrap failed, and added rollback tests. | Commit `fcb5ea0`; acceptance-suite, starter-smoke, benchmark, simulate-week, and compileall passed. |
| 2026-05-04 | P0: Rollback hardening | Done | Closed verification edge cases found after the first transactional init patch. | Prevented rollback from deleting an untouched target when copy fails before backup, returned JSON for file-valued `starter-smoke` paths, made path removal symlink-safe, and preserved backup details if restore fails. | Commit `f07999e`; 11 safety tests, acceptance-suite, starter-smoke, benchmark, simulate-week, and compileall passed. |
| 2026-05-04 | P0: Interface and resource drift | Done | Made `async-research` the blessed documented interface where wrappers exist and added drift guards. | Replaced stale public examples-script references in operator docs, scheduler prompts, starter templates, and examples with `async-research` commands or explicit `python -m async_research_workflow.scripts.<module>` advanced forms. Added tests for stale/nonexistent example references, duplicated schema/policy drift, and importlib resource access. | This change; `.venv/bin/python -m unittest tests.test_doc_references tests.test_packaged_resources`. |
| 2026-05-04 | P0: Internal docs drift | Done | Cleaned the remaining internal protocol references to removed examples-script and example schema/template paths. | Expanded doc-reference tests across all packaged docs, templates, and examples; migrated internal protocol command snippets to `async-research` where wrappers exist and to `python -m async_research_workflow.scripts.<module>` for advanced helpers. | This change; `.venv/bin/python -m unittest tests.test_doc_references`; stale-reference scan returned no matches. |
| 2026-05-04 | P1: Generic starter | Done | Added a domain-neutral default starter while keeping real-estate as a worked example. | Introduced a generic empty `research_ops` template, made it the default for `init` and `starter-smoke`, kept real-estate under `--template real-estate`, and added resource/CLI tests for both templates. | This change; targeted template tests, default and real-estate init/smoke checks, acceptance-suite, benchmark, and compileall passed. |
| 2026-05-04 | P1: Runtime resource canonicalization | Done | De-duplicated schema, benchmark, and example policy resources behind canonical loaders. | Kept schemas under `schemas/`, default mission policy at package root, and benchmark cases under `benchmarks/`; routed runtime defaults through `async_research_workflow.resources`; removed duplicate packaged resource copies and added guards against reintroducing them. | This change; packaged-resource/doc tests, acceptance-suite, benchmark, starter-smoke, and compileall passed. |
| 2026-05-04 | P1: Expanded Python regression tests | Done | Added focused contract-level tests for safety gates that were mostly covered by benchmark cases. | Created isolated temp-workspace tests for malformed status recovery, missing schema versions, invalid transitions, missing reviewer metadata, stale source and accepted-memory gates, lock contention, budget pressure, and result acceptance ledger/index writes. | This change; `tests.test_workflow_regressions`, unittest discovery, acceptance-suite, benchmark, starter-smoke, and compileall passed. |
| 2026-05-04 | P1: Packaging-aware CI | Done | Made CI verify supported Python versions and installed package artifacts. | Added Python 3.13 to the editable-install matrix, promoted unittest discovery and benchmark into CI gates, and added a wheel/sdist job that installs the built wheel into a clean venv before running CLI/resource smokes for version, acceptance, benchmark, and both starter templates. | This change; local unittest discovery, acceptance-suite, benchmark, generic and real-estate starter-smoke, compileall, wheel/sdist build, and installed-wheel smokes passed. |
| 2026-05-05 | P2: README rewrite | Done | Rewrote the root README for first-time users. | Added a plain-English project summary, lifecycle diagram, install/setup guidance with Python 3.11+, generic and real-estate starter guidance, worked task loop, command read/write map, maintainer checks, and links into the deeper protocol docs. | This change; documentation reference tests, packaged-resource tests, unittest discovery, acceptance-suite, benchmark, starter-smoke, compileall, and package build checks passed. |
| 2026-05-05 | P2: Exit codes and CLI behavior | Done | Documented exit codes and improved CLI help. | Added top-level and nested `argparse` descriptions, option help, and exit-code epilogs without renaming commands or changing JSON contracts. Added a README exit-code contract covering readiness and command-specific outcomes. | This change; CLI help regression tests, documentation reference tests, unittest discovery, acceptance-suite, benchmark, starter-smoke, compileall, and package build checks passed. |
| 2026-05-05 | P2: Script import cleanup | Done | Refactored sibling-script imports without behavior changes. | Replaced `sys.path.insert` patterns and bare sibling imports with package-qualified imports, then added regression tests for import hygiene and package-namespace importability. | This change; script import tests, unittest discovery, acceptance-suite, benchmark, starter-smoke, simulate-week, compileall, and package build checks passed. |
| 2026-05-05 | P2: Benchmark and simulation packaging | Done | Made benchmark and scheduled-week simulation more robust from installed packages. | Replaced subprocess calls to sibling script files with in-process package module invocation, removed repo-root layout assumptions, and tightened scratch-workdir isolation around explicit user paths. | This change; benchmark packaging tests, unittest discovery, acceptance-suite, benchmark, simulate-week, starter-smoke, compileall, and installed-wheel checks passed. |
| 2026-05-05 | P3: Package metadata and repo hygiene | Done | Polished release metadata and contributor affordances. | Added project URLs, keywords, explicit Apache-2.0 license metadata, changelog, contributor guidance, issue templates, PR template, and metadata regression tests. | This change; project metadata tests, unittest discovery, package build, and installed-wheel version check passed. |
| 2026-05-05 | P3: Optional command naming cleanup | Done | Added clearer aliases without breaking existing commands. | Kept canonical names stable while adding `review-surface` as an alias for `surface` and `accepted revalidate` as an alias for `accepted revalidation`; documented the aliases and added CLI regression coverage. | This change; CLI alias/help tests, unittest discovery, acceptance-suite, benchmark, starter-smoke, compileall, and installed-wheel alias smokes passed. |
| 2026-05-05 | P3: Optional CLI architecture refactor | Done | Split CLI parser wiring into explicit internal registration groups. | Added `build_parser()`, shared parser helpers, and focused command registration functions while keeping command names, aliases, JSON output, and module dispatch unchanged. | This change; CLI architecture/help/alias tests, unittest discovery, acceptance-suite, benchmark, starter-smoke, compileall, and installed-wheel parser smokes passed. |
| 2026-05-05 | P3: Optional docs packaging review | Done | Reviewed packaged protocol docs and kept them in the wheel for alpha. | Recorded `DOCS_PACKAGING_REVIEW.md`, kept `docs/**/*.md` explicit, and added tests for docs package-data, Markdown-only docs, footprint thresholds, and importlib resource access. | This change; docs packaging tests, packaged-resource tests, unittest discovery, acceptance-suite, benchmark, starter-smoke, compileall, package build, and installed-wheel docs smokes passed. |
| 2026-05-05 | CLI surface audit planning | Done | Captured the public/internal CLI audit as the next execution track. | Added an audit results section, decision notes, and a phase-by-phase action table so implementation can proceed one slice at a time. | Roadmap now tracks CLI Audit 0-7 with status, timing, and acceptance criteria. |
| 2026-05-05 | CLI Audit 0: exploration validate doc bug | Done | Replaced the one stale advanced invocation for exploration-cycle validation. | Updated the Discovery Scout prompt to call the public `async-research exploration validate` wrapper and added the previously missing `--task-dir` argument. | This change; doc-reference tests and direct stale-invocation scan passed. |
| 2026-05-05 | CLI Audit 1: existing-group wrappers | Done | Promoted seven low-risk script subcommands into existing public CLI groups. | Added `cost ingest-usage`, `cost budget-check`, `accepted check-duplicate`, `accepted check-memory-use`, `source check-experiment`, `source check-claim`, and `metrics summarize` while preserving backing script JSON and exit-code behavior. | This change; CLI audit surface tests, parser/help tests, README exit-code coverage, full unittest discovery, acceptance-suite, benchmark, starter-smoke, and compileall passed. |
| 2026-05-05 | CLI Audit 2: docs and template migration | Done | Migrated docs and templates for promoted public commands away from advanced script invocations. | Replaced eligible `python -m async_research_workflow.scripts.<module>` examples with `async-research` forms for promoted cost, accepted-memory, source-check, and metrics-summary commands; left internal/deferred helpers as advanced forms. | This change; promoted-command doc-reference guard, targeted scans, doc-reference tests, full unittest discovery, acceptance-suite, benchmark, starter-smoke, and compileall passed. |
| 2026-05-05 | CLI Audit 3: queue discovery gate | Done | Promoted the read-only discovery capacity gate into the public CLI. | Added `async-research queue discovery-gate`, documented its read-only behavior and skip exit code, and migrated scheduler/runbook examples from the advanced queue-capacity script form. | This change; queue wrapper tests, help/architecture tests, doc-reference guard, full unittest discovery, acceptance-suite, benchmark, starter-smoke, and compileall passed. |
| 2026-05-05 | CLI Audit 4: decision commands | Done | Promoted human decision logging and resolution into the public CLI. | Added `async-research decision append/check/resolve-task/summarize`, including append dry-run preview, README exit-code documentation, human-surface copy updates, and docs/templates migration from the advanced helper form. | This change; decision wrapper tests, help/architecture tests, doc-reference guard, full unittest discovery, acceptance-suite, benchmark, starter-smoke, and compileall passed. |
| 2026-05-05 | CLI Audit 5: escalation commands | Done | Promoted deterministic human escalation gates into the public CLI. | Added `async-research escalation list/scan-needs-human/evaluate`, documented escalation-specific exit codes, migrated docs/templates from the advanced helper form, and added public-CLI tests for no-trigger, trigger-without-apply, and `--apply` mutation behavior. | This change; escalation wrapper tests, help/architecture tests, doc-reference guard, full unittest discovery, acceptance-suite, benchmark, starter-smoke, and compileall passed. |
| 2026-05-06 | CLI Audit 6: deferred workflow surfaces | Done | Promoted the remaining deferred helpers that now have clear workflow stories. | Added public wrappers for source authoring/explain, batch lifecycle, anti-context generation, isolated review context preparation/install, and bounded revision counters; migrated docs/templates to public CLI forms and documented exit semantics. | This change; Audit 6 wrapper tests, help/architecture tests, doc-reference guard, full unittest discovery, acceptance-suite, benchmark, starter-smoke, and compileall passed. |
| 2026-05-06 | CLI Audit 7: internal helper boundary | Done | Locked the remaining low-level helpers out of the public CLI contract. | Added an internal-helper boundary doc, documented the split in the README and docs index, labeled intentional direct helper invocations as advanced/internal, and added parser/doc guards for accidental promotion or unlabeled helper usage. | This change; CLI architecture/help/doc-reference tests, full unittest discovery, acceptance-suite, benchmark, starter-smoke, and compileall passed. |

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

## CLI Surface Audit Results

The CLI/script surface audit reviewed `main` at commit `0a0e370` and found that
the package now has a much clearer public contract than it did at the start of
hardening: the public interface is `async-research`, while direct
`python -m async_research_workflow.scripts.<module>` usage should be reserved
for advanced or internal tools that do not have a wrapper yet.

The audit inventory found 34 script modules under
`src/async_research_workflow/scripts/`. Two are library-only modules
(`decision_log.py` and `version_metadata.py`); the other 32 expose an
`argparse`-driven `main(argv)`. The top-level CLI currently exposes 20 public
commands, counting aliases such as `review-surface`.

The main finding is not that every script needs promotion. The useful split is:

- Promote low-risk gaps inside command groups that already exist.
- Promote a few small command groups only where docs/templates already teach
  users to run the underlying script.
- Keep validators, lock/recovery primitives, review-context builders, and
  authoring utilities internal until a broader workflow justifies them.
- Fix documentation drift only after the relevant public wrapper exists, except
  for one current doc bug: `validate_exploration_cycle` already has the public
  wrapper `async-research exploration validate`.

### CLI Audit Execution Table

| Phase | Priority | Action items | When | Status | What was done | Evidence / acceptance |
| --- | --- | --- | --- | --- | --- | --- |
| CLI Audit 0 | P2 | Fix the existing doc bug that teaches `python -m async_research_workflow.scripts.validate_exploration_cycle` where `async-research exploration validate` already exists. | First audit follow-up; no CLI changes needed. | Done | Updated the Discovery Scout prompt to use `async-research exploration validate` and added the required `--task-dir` argument. | Scheduler prompts use the public wrapper; doc-reference tests pass. |
| CLI Audit 1 | P2 | Add subcommands inside existing groups: `cost ingest-usage`, `cost budget-check`, `accepted check-duplicate`, `accepted check-memory-use`, `source check-experiment`, `source check-claim`, and `metrics summarize`. | After the doc bug fix. | Done | Added the seven wrappers inside the existing `cost`, `accepted`, `source`, and `metrics` groups, plus command-map and exit-code documentation. | CLI help lists each command; JSON contracts and exit behavior match backing scripts; focused CLI regression tests pass. |
| CLI Audit 2 | P2 | Migrate docs/templates for the newly promoted subcommands from advanced `python -m ...scripts.<module>` forms to `async-research ...` forms. | Immediately after CLI Audit 1 lands. | Done | Updated operator docs, protocols, templates, and the GitHub worker example to use public `async-research` forms for promoted commands, while preserving advanced forms for internal/deferred helpers. | No public docs/templates teach advanced forms for promoted commands; doc-reference tests pass. |
| CLI Audit 3 | P2 | Add `queue discovery-gate` as a small public command group. | After Audit 1/2 prove the wrapper pattern. | Done | Added the `async-research queue discovery-gate` wrapper around the queue-capacity gate, updated README and scheduler/runbook examples, and added regressions for success, skip, and read-only behavior. | Under-capacity returns success, over-capacity returns the documented skip code, and help documents read-only behavior. |
| CLI Audit 4 | P2 | Add `decision append`, `decision check`, `decision resolve-task`, and `decision summarize`. | After queue wrapper; separate commit because it writes decision state. | Done | Added the `async-research decision` group with append, check, resolve-task, and summarize wrappers; append and resolve dry-runs write nothing; docs/templates and generated human-review guidance now use public commands. | Append/resolve behavior is tested through the public CLI, `--dry-run` writes nothing, and docs/templates use the public commands. |
| CLI Audit 5 | P2/P3 | Add `escalation list`, `escalation scan-needs-human`, and `escalation evaluate`, with an explicit decision on public exit-code semantics. | After decision commands; separate commit because exit-code meaning needs care. | Done | Added the `async-research escalation` group with list, scan-needs-human, and evaluate wrappers; documented exit semantics and migrated escalation docs/templates to public CLI forms. | Help documents escalation-specific exit codes; tests cover no-trigger, trigger-without-apply, and `--apply` mutation behavior. |
| CLI Audit 6 | P3 | Revisit deferred surfaces: `batch_lifecycle`, `revision_counter`, source authoring (`source init`, `source upsert`, `source explain`), `prepare_review_context`, and `generate_anti_context`. | Only after the surrounding workflow becomes public enough to justify the surface. | Done | Promoted the coherent workflow surfaces as `async-research batch`, `async-research revision`, `async-research anti-context build`, `async-research review prepare-context/install-context`, and source authoring/explain subcommands. | Each promoted command has a documented user story, tests, and migration docs; deferred internals remain advanced/internal. |
| CLI Audit 7 | Permanent internal | Keep `validate_json_artifact`, `validate_transition`, `validate_mission_policy`, `task_lock`, `recover_status_json`, `review_template`, `framework_version_calibration`, `escalate_review_tier`, `metrics_history init`, `decision_log`, and `version_metadata` out of the public CLI unless a later design explicitly changes that policy. | Ongoing policy; implemented as the final audit hardening pass. | Done | Added an internal-helper boundary doc, README guidance, docs-index link, direct-helper labels in advanced protocols/prompts/templates, and regression tests that reject accidental public helper commands or unlabeled direct helper invocations. | Public docs call artifact-specific gates where wrappers exist; advanced/internal docs label direct helper use; parser tests keep internal helpers out of the top-level CLI. |

### CLI Audit Decisions

- `accepted check-duplicate` should remain advisory unless deliberately changed:
  duplicate risk is reported in JSON, but the backing script currently exits
  successfully.
- `accepted check-memory-use` is a hard gate and should preserve nonzero exit
  behavior for stale accepted-memory reuse.
- `cost budget-check` should be documented as a budget gate failure when it
  halts, not as malformed CLI input.
- `metrics init` should stay internal because `async-research init` already
  creates the baseline.
- `source init`, `source upsert`, and `source explain` were promoted once the
  public source-authoring workflow could be documented as a coherent group.
- `escalation` needs an explicit wrapper-level exit-code decision before
  promotion because the backing script's current code meanings do not line up
  perfectly with the general CLI epilog.
