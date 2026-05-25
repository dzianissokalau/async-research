# Framework Simplification Strategy

Status: In Progress
Current phase: Phase 4 - Proposal engine discovery and consolidation
Last updated: 2026-05-25
Next action: Start proposal flow mapping before extracting shared mechanics
Blocked by: None

Created: 2026-05-22

## Summary

The framework is overloaded, but the safest simplification path is not a
large-scale redraw of the product surface. The best near-term strategy is to
shrink the internal orchestration layer while preserving the contracts that make
the tool useful for dogfooding: public CLI behavior, JSON envelopes, exit codes,
workspace file formats, and fail-closed quality gates.

This strategy reviews two proposals:

- `async-research-simplification-roadmap.md` argues for an aggressive cut:
  remove the HTTP console, add CLI/schema/lock dependencies, reduce the command
  surface, create generic surfaces, and consolidate modules.
- `dr-async-research-simplification.md` argues for a safer refactor-first path:
  preserve the public CLI and standard-library posture, extract the `cli.py`
  runner patterns, split `console/snapshot.py`, and only consider larger command
  or dependency changes after parity is locked.

The recommended strategy is a hybrid, but it leans conservative. The aggressive
proposal correctly identifies real accretion, especially repeated proposal
flows, oversized command wiring, and roadmap-driven surface growth. I push back
on its order of operations: deleting the console first, switching to Typer early,
and cutting the test suite before behavioral parity is frozen would create more
risk than leverage.

## Current Evidence

Repository facts checked on 2026-05-22:

| Area | Current observation | Strategy implication |
| --- | ---: | --- |
| Runtime dependencies | `pyproject.toml` has `dependencies = []`; README says runtime dependencies are standard-library-only. | Treat new dependencies as a product decision, not a cleanup default. |
| Main CLI file | `src/async_research_workflow/cli.py` is 4,062 lines. | Highest leverage internal simplification target. |
| Console snapshot | `src/async_research_workflow/console/snapshot.py` is 2,438 lines. | Second highest leverage target, especially as a read-model hub. |
| Console actions | `src/async_research_workflow/console/actions.py` is 1,417 lines. | Keep in scope after snapshot is split, not before. |
| Idea catalog implementation | `idea_catalog.py` plus `scripts/idea_catalog.py` is 6,652 lines. | Likely a later surface-normalization target, not the first cut. |
| Script modules | 68 script modules. | Internal API is broad and string-dispatched from the CLI. |
| Schemas | 28 schema JSON files. | Schema reduction needs contract review before deletion. |
| Tests | 78 top-level test files and 811 `def test_` functions. | Tests are a safety net and a maintenance cost; prune after contract parity exists. |
| Templates | 142 packaged template files. | Template cuts are product cuts; defer until command and workspace contracts are clear. |

## Position

Yes, the framework is too large for the core product promise. The overload is
mostly in orchestration and surfaces, not in the research-quality gates. That is
good news: we can simplify substantially without weakening the outcome model.

The core product should remain:

- file-backed `research_ops/` state;
- bounded task lifecycle from idea to accepted, rejected, revision, or human
  decision;
- source, data, library, claim, review, result-acceptance, readiness, and cost
  gates;
- durable Markdown/JSON artifacts that humans and Codex jobs can both inspect;
- public CLI commands as the stable operator interface.

The code that wires those pieces together can get much smaller.

## Non-Goals

- Do not remove fail-closed gates to make the framework feel simpler.
- Do not delete the console or public command families as the first move.
- Do not replace `argparse` with Typer until public help, aliases, and error
  behavior have golden coverage.
- Do not add `jsonschema` or `filelock` until the standard-library-only posture
  is explicitly revisited.
- Do not prune tests just because commands feel excessive.
- Do not change existing `research_ops/` file names or task state values during
  simplification.

## Load-Bearing Contracts

These contracts must stay stable through the first simplification wave:

| Contract | Must preserve |
| --- | --- |
| Workspace truth | `research_ops/` remains the source of truth; no database or hidden state. |
| Task lifecycle | `ready_for_worker`, `in_progress`, `awaiting_review`, `accepted`, `rejected`, `needs_revision`, and `needs_human` behavior. |
| Exit codes | Scheduler-facing meanings for success, warning, skip, invalid, and human-required states. |
| Public CLI | Existing commands, aliases, help shape, JSON envelopes, and documented side effects until a deprecation plan exists. |
| Quality gates | Source audit, freshness, claim verification, review aggregation, result acceptance, accepted-memory freshness, and deliverable maturity checks. |
| Console snapshot | Current `console snapshot` JSON envelope until facet parity tests are in place. |
| Templates | Existing starter workspaces continue to initialize and validate. |

## Target Internal Shape

The first target is not a new user-visible product shape. It is a smaller
internal shape behind the existing surface:

```text
src/async_research_workflow/
  cli.py                         # public argparse parser and command registration
  cli_runner.py                  # typed ScriptCall, JSON capture, option builders
  workspace_install.py           # init staging, backup, rollback, metrics seeding
  starter_smoke.py               # smoke check plan and JSON envelope assembly

  console/
    snapshot.py                  # top-level envelope assembly only
    facets/
      base.py                    # facet result helpers
      tasks.py                   # workspace and task board collectors
      readiness.py               # readiness, health, and recovery commands
      outcomes.py                # human decisions, accepted outputs, auto decisions, rejected results
      costs.py
      foundations.py
      lifecycle.py
      mode.py
      runtime.py
      deliverables.py

  proposals/
    engine.py                    # preflight hash, lock, apply, rollback protocol
    surfaces.py                  # surface hooks after real duplication is mapped
```

This shape deliberately keeps the existing public CLI and script modules alive
while reducing the two biggest dependency hubs.

## Phased Plan

| Phase | Status | Priority | Focus | Scope | Exit Criteria |
| ---: | --- | --- | --- | --- | --- |
| 0 | Delivered | P0 | Contract freeze | Inventory public commands, JSON envelopes, exit codes, file writes, and high-value tests for touched areas. | A reviewer can tell which behavior must not change before each refactor PR. |
| 1 | Delivered | P0 | CLI runner seam | Extract script dispatch, JSON capture, and option builders from `cli.py`; migrate one low-risk command family first. | Public parser output and wrapper argv tests stay identical. |
| 2 | Delivered | P0 | Init and starter smoke services | Move workspace installation, rollback, and smoke orchestration out of `cli.py`. | `init` and `starter-smoke` JSON envelopes and side effects are unchanged. |
| 3 | Delivered | P0 | Snapshot facets | Split `console/snapshot.py` into facet collectors behind the same top-level payload. | `console snapshot` golden fixtures match before and after, ignoring timestamps. |
| 4 | Not Started | P1 | Proposal engine discovery and consolidation | Map data, library, foundation, and idea proposal flows; extract only the common preflight/hash/lock/rollback spine. | At least two proposal families use one shared engine without losing surface-specific validation. |
| 5 | Not Started | P1 | Command normalization design | Classify commands as keep, alias, deprecate, or internal; no removal yet. | A migration table exists and deprecated commands have explicit replacements. |
| 6 | Not Started | P1 | Dependency decision record | Decide whether standard-library-only remains a release promise or becomes a core/minimal extra. | Typer, jsonschema, and filelock each have an explicit keep/defer/adopt decision. |
| 7 | Not Started | P2 | Test consolidation | Delete or rewrite tests only after replacement contracts and goldens exist. | The remaining suite catches behavior regressions rather than obsolete command-shape drift. |

## Phase 0 - Contract Freeze

### Objective

Make future refactors reviewable by separating load-bearing behavior from
incidental implementation detail.

### Scope

- command map with command name, aliases, module target, exit codes, JSON
  envelope, reads, writes, and dry-run behavior;
- snapshot top-level keys and known fixture outputs;
- `init` and `starter-smoke` side effects and rollback behavior;
- first-pass test labels for tests touched by Phase 1 through Phase 3.

### Implementation Steps

1. Create a local command-contract table from the current parser and README.
2. Add focused equivalence tests for the first CLI wrapper family to be moved.
3. Add or identify snapshot golden fixtures that cover a fresh starter, a task
   in review, a needs-human task, and accepted evidence.
4. Record the commands and files intentionally out of scope for the first wave.

### Acceptance Criteria

- No public command behavior is changed.
- The first implementation slice has explicit before/after parity checks.
- Existing dirty worktree changes unrelated to simplification are not modified.

### Verification

- `git diff --check`
- `.venv/bin/python -m unittest tests.test_cli_architecture tests.test_console_snapshot`

## Phase 1 - CLI Runner Seam

### Objective

Reduce `cli.py` coupling without changing the parser, public command names, or
script modules.

### Scope

- Move `module_main`, `module_json`, JSON output parsing, and common option
  helpers into a small internal runner module.
- Add typed call objects so wrapper tests can assert exact script module and
  argv output.
- Migrate command families incrementally, starting with a low-risk group such as
  `cost`, `scaling`, or `accepted`.

### Acceptance Criteria

- Public command registration order stays unchanged.
- Existing CLI architecture tests pass.
- Moved wrappers have exact argv-equivalence tests.
- `cli.py` gets smaller without losing readable parser definitions.

### Verification

- `.venv/bin/python -m unittest tests.test_cli_architecture tests.test_cli_aliases tests.test_cli_help`
- `.venv/bin/python -m unittest tests.test_cli_safety`

## Phase 2 - Init And Starter Smoke Services

### Objective

Move transactional workspace installation and starter validation orchestration
out of the main CLI file.

### Scope

- `WorkspaceInstaller` or equivalent for staging, backup, rollback, and metrics
  seeding.
- `StarterSmokePlan` or equivalent for check ordering and envelope assembly.
- Focused rollback and failure-reporting tests.

### Acceptance Criteria

- `async-research init` output and file writes are unchanged.
- `async-research starter-smoke` check ordering and JSON envelope are unchanged.
- Rollback failures still report backup paths.

### Verification

- `.venv/bin/python -m unittest tests.test_packaged_resources tests.test_cli_safety`
- `.venv/bin/async-research starter-smoke /tmp/arw-simplification-smoke --force`

## Phase 3 - Snapshot Facets

### Objective

Turn `console/snapshot.py` from one large read-model hub into a small envelope
builder plus isolated facet collectors.

### Scope

- Extract facets in dependency order:
  - workspace and task board;
  - readiness and health;
  - human decisions, accepted outputs, rejected results;
  - cost and foundations;
  - deliverables, runtime, evals, and lifecycle.
- Keep `/api/snapshot` and `console snapshot --json` behavior stable.
- Avoid changing the browser dashboard UI during this phase.

### Acceptance Criteria

- Snapshot top-level keys stay stable.
- Fresh-starter and populated-fixture snapshots match before and after, aside
  from timestamp fields.
- Facet failures stay fail-closed and visible as warnings or unavailable groups.

### Verification

- `.venv/bin/python -m unittest tests.test_console_snapshot tests.test_console_server tests.test_console_actions tests.test_console_outcomes`

## Phase 4 - Proposal Engine Consolidation

### Objective

Remove real duplicated proposal mechanics without forcing every surface into a
premature abstract base class.

### Scope

- Map common behavior across data, library, foundation, and idea proposal flows:
  preflight hash, accepted-task proof, lock acquisition, write plan, rollback,
  post-write validation, and JSON reporting.
- Extract shared mechanics after two concrete flows prove the shape.
- Leave surface-specific parsing and validation near the surface until the
  common API is obvious.

### Acceptance Criteria

- At least two proposal families share the same engine.
- Dry-run and write modes remain explicit.
- Post-write validation and rollback semantics are unchanged.
- Manual notes in Markdown files are preserved.

### Verification

- `.venv/bin/python -m unittest tests.test_foundation_proposals tests.test_foundation_proposal_apply`
- `.venv/bin/python -m unittest tests.test_data_proposal_inspection tests.test_library_proposal_inspection`
- `.venv/bin/python -m unittest tests.test_idea_catalog_v2_proposal_write`

## Phase 5 - Command Normalization Design

### Objective

Reduce the public surface only after the internal code has safer seams and the
team agrees which commands are product concepts versus implementation detail.

### Scope

- Classify every command as keep, alias, deprecate, or internal.
- Prefer aliasing before removal.
- Keep lifecycle, review, acceptance, source governance, runtime, eval, and
  deliverable maturity commands explicit until actual dogfood proves they are
  confusing.
- Produce a user-facing migration table.

### Acceptance Criteria

- Every deprecated command prints a specific replacement or rationale.
- No command disappears without a deprecation period.
- README command examples are updated in the same slice as any public
  deprecation.

### Verification

- `.venv/bin/python -m unittest tests.test_cli_help tests.test_doc_references`

## Phase 6 - Dependency Decision Record

### Objective

Make dependency adoption intentional.

### Current Recommendation

- Defer Typer. `argparse` is verbose but stable, and help/error parity matters.
- Defer `jsonschema` until schema contracts are mapped. The internal helper is
  small and fail-closed, even if incomplete.
- Defer `filelock` for task-local locks. The current lock uses atomic directory
  creation and encodes owner metadata; replacing it changes more than syntax.

### Possible Future Decision

If the product moves from "standard-library-only runtime" to "minimal core plus
optional operator extras", adopt dependencies as extras rather than default
runtime requirements:

```toml
[project.optional-dependencies]
operator = ["typer", "jsonschema", "filelock"]
```

This keeps scheduler and embedded use cases lightweight while allowing a richer
operator CLI later.

## Phase 7 - Test Consolidation

### Objective

Shrink tests after the code has safer contracts, not before.

### Scope

- Keep core invariant tests for lifecycle, review, result acceptance, source
  gates, claim verification, readiness, locking, and workspace writes.
- Keep schema regression tests for stable artifacts.
- Replace brittle surface-contract tests with smaller command-golden tests only
  when commands are intentionally aliased or deprecated.
- Remove tests only when the behavior they pinned has a replacement contract or
  is intentionally deleted with a migration note.

### Acceptance Criteria

- Test count reduction follows code and command simplification.
- Failing tests point to meaningful product regressions.
- Acceptance suite and starter-smoke still cover the first-success path.

## First Implementation Slice

When this roadmap is activated, start with a small, reversible PR:

1. Add `src/async_research_workflow/cli_runner.py`.
2. Move JSON capture and common option helpers from `cli.py`.
3. Migrate one low-risk command family, preferably `cost` or `accepted`.
4. Add argv-equivalence tests for that family.
5. Run targeted CLI tests plus `git diff --check`.

This proves the simplification style without touching public commands,
dependencies, schemas, templates, or the console.

## Success Criteria

Short-term success for the first wave:

- `cli.py` is meaningfully smaller and easier to review.
- `console/snapshot.py` is split by facet without dashboard contract drift.
- `init` and `starter-smoke` logic are testable outside the parser.
- No existing workspace migration is required.
- No scheduler-facing exit code changes.
- No quality gate is removed or weakened.

Longer-term success:

- public commands are reduced only where aliases and dogfood show a simpler
  shape is better;
- proposal apply logic has one hardened transaction path;
- tests are fewer but more contract-focused;
- new features add small surface modules instead of another broad CLI or
  snapshot growth patch.

## Open Decisions

- Is the local HTTP console a core product surface, or should it become an
  optional operator extra after snapshot facets exist?
- Is standard-library-only a hard release promise or a current implementation
  preference?
- How long should public command deprecations live during alpha dogfooding?
- Should command normalization wait until the Codex plugin product boundary is
  decided?
- Should simplification implementation pause until the active interaction-mode
  roadmap is delivered, or can Phase 1 start in parallel because it is internal?

## Relationship To The Input Proposals

Accepted from the aggressive roadmap:

- The framework is too large relative to the solo-researcher promise.
- Repeated proposal workflows should share one engine.
- `cli.py` and surface command growth are central causes of complexity.
- Tests should eventually become smaller and more invariant-focused.

Rejected or deferred from the aggressive roadmap:

- Delete the HTTP console first.
- Add Typer, jsonschema, and filelock in the first implementation wave.
- Reduce from roughly 132 commands to 25-30 commands before deprecation data.
- Delete most CLI/surface tests before behavioral goldens exist.
- Promise a fixed 18k LoC target before measuring what simplification preserves.

Accepted from the conservative assessment:

- Preserve public CLI behavior first.
- Extract a typed internal command runner and argument builders from `cli.py`.
- Split `console/snapshot.py` into facet collectors.
- Encapsulate workspace installation and starter-smoke orchestration.
- Add equivalence tests before changing parser shape.

Adjustment to the conservative assessment:

- Do not stop at refactoring the two hotspots. After seams are in place, pursue
  the proposal-engine consolidation and command normalization work, because the
  overload is also conceptual, not only file-size related.
