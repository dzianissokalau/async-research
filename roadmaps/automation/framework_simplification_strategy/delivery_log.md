# Framework Simplification Strategy Delivery Log

Status: In Progress
Roadmap: `roadmaps/in_progress_framework_simplification_strategy.md`
Automation template: `roadmaps/automation/codex_phase_gated_delivery_automation_template.md`
State file: `roadmaps/automation/framework_simplification_strategy/delivery_state.json`
Review directory: `roadmaps/automation/framework_simplification_strategy/reviews`
Cadence: hourly
Model: GPT-5.5
Reasoning: xhigh

## Operating Policy

- Deliver one phase per branch: `codex/framework-simplification-strategy-phase-<n>`.
- Work only on the current phase.
- Preserve public CLI behavior, JSON envelopes, exit codes, workspace file formats, and fail-closed quality gates.
- Do not add runtime dependencies without an explicit dependency decision record.
- Run a fresh review before marking a phase delivered.
- Auto-advance only after a `delivered` review verdict.
- Stop after 3 review/fix iterations if the phase is still not delivered.
- Create one local commit when each phase is delivered.
- Keep work local until explicitly told to push.
- Use the current local workspace and existing `.venv`.

## Human Approval

- 2026-05-25: Human approval to begin implementation is recorded from the user request to set up this automation.

## Phase 0 - 2026-05-25

Status: not_started
Branch: `codex/framework-simplification-strategy-phase-0`

### Scope

- Command map with command name, aliases, module target, exit codes, JSON envelope, reads, writes, and dry-run behavior.
- Snapshot top-level keys and known fixture outputs.
- `init` and `starter-smoke` side effects and rollback behavior.
- First-pass test labels for tests touched by Phase 1 through Phase 3.
- Focused equivalence tests for the first CLI wrapper family to be moved.

### Tests And Verification

- `git diff --check`: not run
- `.venv/bin/python -m unittest tests.test_cli_architecture tests.test_console_snapshot`: not run

### Review

- Review file: pending
- Verdict: pending

### Next Action

- Start Phase 0 contract freeze.

## Phase 0 - 2026-05-25 - Delivery Pass 1

Status: delivered
Branch: `codex/framework-simplification-strategy-phase-0`

### Scope

- Inventory public commands, aliases, dispatch targets, exit codes, JSON envelopes, reads/writes, and dry-run behavior for the first simplification wave.
- Add explicit parity coverage before moving the first CLI wrapper family.
- Identify snapshot fixtures needed before Phase 3 collector extraction.

### Changes

- Added `phase_0_contract_freeze.md` with parser surface, alias, dispatch target, exit-code, JSON-envelope, read/write, dry-run, snapshot, init, and starter-smoke contracts.
- Added exact argv parity coverage for the `cost` command family as the Phase 1 first-slice candidate.
- Added an awaiting-review console snapshot fixture that asserts top-level groups, review task shape, artifact links, and read-only behavior.
- Advanced the roadmap and delivery state to Phase 1 for the next run after a clean review.

### Tests And Verification

- `git diff --check`: passed
- `.venv/bin/python -m unittest tests.test_cli_architecture tests.test_console_snapshot`: passed, 43 tests

### Review

- Review file: `roadmaps/automation/framework_simplification_strategy/reviews/framework-simplification-strategy-phase-0-review-iteration-1.md`
- Verdict: delivered

### Finding Disposition

- No findings.

### Residual Risks

- The README command map remains the broad source for detailed per-command reads/writes; the Phase 0 contract records dispatch targets and the write boundaries most relevant to the first simplification wave.

### Next Action

- Next run should start Phase 1 on `codex/framework-simplification-strategy-phase-1` and migrate the `cost` command family through a CLI runner seam while preserving the new argv parity tests.

## Phase 1 - 2026-05-25 - Delivery Pass 1

Status: delivered
Branch: `codex/framework-simplification-strategy-phase-1`

### Scope

- Extract script dispatch, JSON output parsing, and common option-list helpers from `cli.py`.
- Add typed script call objects so migrated wrappers expose exact backing module and argv contracts.
- Migrate one low-risk command family, `cost`, behind the runner seam without changing parser output, help, aliases, JSON envelopes, or exit codes.

### Changes

- Added `src/async_research_workflow/cli_runner.py` with `ScriptCall`, script dispatch, JSON capture, and common optional/repeated option helpers.
- Imported the runner helpers back into `cli.py` so existing `cli.*` helper names remain available while the implementation moves out of the main parser file.
- Migrated `cost summary`, `cost ingest-usage`, and `cost budget-check` to build typed `ScriptCall` values before dispatch.
- Updated the `cost` argv-equivalence test to assert the exact `ScriptCall` module and argv contract.
- Renamed the roadmap from `not_started_framework_simplification_strategy.md` to `in_progress_framework_simplification_strategy.md` after broad verification caught the lifecycle-status mismatch left by starting Phase 0.
- Advanced the roadmap, roadmap index, and delivery state to Phase 2 after the delivered review verdict.

### Tests And Verification

- `.venv/bin/python -m unittest tests.test_cli_architecture tests.test_cli_aliases tests.test_cli_help`: passed, 21 tests
- `.venv/bin/python -m unittest tests.test_cli_safety`: passed, 20 tests
- `git diff --check`: passed
- `.venv/bin/python -m unittest tests.test_doc_references`: passed, 18 tests
- `.venv/bin/python -m unittest discover -s tests`: passed, 829 tests
- `.venv/bin/async-research acceptance-suite`: passed, 15 checks

### Review

- Review file: `roadmaps/automation/framework_simplification_strategy/reviews/framework-simplification-strategy-phase-1-review-iteration-1.md`
- Verdict: delivered

### Finding Disposition

- No findings.

### Residual Risks

- Same-context review was used because sub-agent delegation requires explicit user permission. The review records this limitation.
- Future CLI wrapper migrations should continue one command family at a time using `ScriptCall` builders and exact argv contract tests.

### Next Action

- Next run should start Phase 2 on `codex/framework-simplification-strategy-phase-2` and extract init/starter-smoke orchestration while preserving JSON envelopes and side effects.

## Phase 2 - 2026-05-25 - Delivery Pass 1

Status: delivered
Branch: `codex/framework-simplification-strategy-phase-2`

### Scope

- Extract transactional starter workspace installation, backup, rollback, metrics seeding, and cleanup from `cli.py`.
- Extract starter-smoke work-dir safety checks, init wrapping, smoke check ordering, result aggregation, and JSON envelope assembly from `cli.py`.
- Preserve `init` and `starter-smoke` public parser behavior, JSON envelopes, exit codes, side effects, and rollback reporting.

### Changes

- Added `src/async_research_workflow/workspace_install.py` with `WorkspaceInstaller`, template selection, copy/remove/restore helpers, rollback handling, and metrics seeding.
- Added `src/async_research_workflow/starter_smoke.py` with `StarterSmokePlan`, `StarterSmokeCheck`, and `StarterSmokeRunner`.
- Kept `cli.run_init` and `cli.run_starter_smoke` as thin public wrappers that inject the existing CLI helper names for compatibility with current contract tests.
- Added regression coverage for starter-smoke check ordering and rollback failure backup reporting.
- Advanced the roadmap and delivery state to Phase 3 after a delivered review verdict.

### Tests And Verification

- `.venv/bin/python -m unittest tests.test_cli_safety`: passed, 22 tests
- `.venv/bin/python -m unittest tests.test_packaged_resources tests.test_cli_safety`: passed, 30 tests
- `git diff --check`: passed
- `.venv/bin/async-research starter-smoke /tmp/arw-simplification-smoke --force`: passed, 9 checks
- `.venv/bin/python -m unittest discover -s tests`: passed, 831 tests
- `.venv/bin/async-research acceptance-suite`: passed, 15 checks

### Review

- Review file: `roadmaps/automation/framework_simplification_strategy/reviews/framework-simplification-strategy-phase-2-review-iteration-1.md`
- Verdict: delivered

### Finding Disposition

- No findings.

### Residual Risks

- Same-context review was used because sub-agent delegation was not explicitly authorized. The review records this limitation.
- Phase 3 should start from the now-advanced branch `codex/framework-simplification-strategy-phase-3` and focus only on console snapshot facets.

### Next Action

- Next run should start Phase 3 on `codex/framework-simplification-strategy-phase-3` and split `console/snapshot.py` into facet collectors behind the same top-level payload.

## Phase 3 - 2026-05-25 - Delivery Pass 1

Status: delivered
Branch: `codex/framework-simplification-strategy-phase-3`

### Scope

- Split `console/snapshot.py` into facet collectors behind the same top-level payload.
- Preserve `/api/snapshot` and `console snapshot --json` behavior, including warning aggregation and unavailable groups.
- Avoid dashboard UI changes.

### Changes

- Added `src/async_research_workflow/console/facets/` with base helpers plus task, readiness, outcomes, cost, foundations, deliverables, mode, runtime, and lifecycle collectors.
- Reduced `src/async_research_workflow/console/snapshot.py` to envelope assembly, CLI parsing, compatibility re-exports, and dashboard loader wiring.
- Added an exact top-level snapshot key regression assertion covering the existing `evidence_memory` group.
- Advanced the roadmap and delivery state to Phase 4 after a delivered review verdict.

### Tests And Verification

- `git diff --check`: passed
- `.venv/bin/python -m unittest tests.test_console_snapshot`: passed, 31 tests
- `.venv/bin/python -m unittest tests.test_console_snapshot tests.test_console_server tests.test_console_actions tests.test_console_outcomes`: passed, 77 tests
- `.venv/bin/python -m unittest tests.test_doc_references`: passed, 18 tests
- `.venv/bin/python -m unittest discover -s tests`: passed, 831 tests
- `.venv/bin/async-research acceptance-suite`: passed, 15 checks

### Review

- Review file: `roadmaps/automation/framework_simplification_strategy/reviews/framework-simplification-strategy-phase-3-review-iteration-1.md`
- Verdict: delivered

### Finding Disposition

- No findings.

### Residual Risks

- Same-context review was used because sub-agent delegation requires explicit user permission. The review records this limitation.
- `console.snapshot` keeps compatibility re-exports for moved helpers; future cleanup should narrow that surface only with explicit deprecation coverage.

### Next Action

- Next run should start Phase 4 on `codex/framework-simplification-strategy-phase-4` and map proposal flow mechanics before extracting shared engine code.

## Phase 4 - 2026-05-25 - Delivery Pass 1

Status: delivered
Branch: `codex/framework-simplification-strategy-phase-4`

### Scope

- Map data, library, foundation, and idea proposal flow mechanics before extracting shared behavior.
- Extract only the common preflight/hash/lock/rollback spine after concrete flow evidence.
- Preserve dry-run/write modes, post-write validation, rollback semantics, manual notes, public JSON envelopes, and surface-specific validation.

### Changes

- Added `roadmaps/automation/framework_simplification_strategy/phase_4_proposal_engine_mapping.md` documenting shared mechanics, surface-specific boundaries, preserved contracts, and deferred candidates.
- Added `src/async_research_workflow/proposals/engine.py` with stable JSON hashing, file hashes, directory lock primitives, snapshots, restore helpers, and atomic byte writes.
- Migrated data and library foundation apply to use the shared engine for preflight hashes, foundation lock acquisition/release, target snapshots, and rollback wrappers.
- Migrated idea promotion hash and snapshot/restore wrappers to the shared engine while keeping catalog lock, idempotency recovery, task transaction, and human override behavior in `idea_catalog.py`.
- Added focused regression tests for data/library shared engine lock usage and idea promotion stable preflight hashing.
- Advanced the roadmap and delivery state to Phase 5 after a delivered review verdict.

### Tests And Verification

- `.venv/bin/python -m unittest tests.test_foundation_proposals tests.test_foundation_proposal_apply`: passed, 19 tests
- `.venv/bin/python -m unittest tests.test_data_proposal_inspection tests.test_library_proposal_inspection`: passed, 14 tests
- `.venv/bin/python -m unittest tests.test_idea_catalog_v2_proposal_write`: passed, 20 tests
- `git diff --check`: passed
- `.venv/bin/python -m unittest tests.test_doc_references`: passed, 18 tests
- `.venv/bin/python -m unittest discover -s tests`: passed, 833 tests
- `.venv/bin/async-research acceptance-suite`: passed, 15 checks

### Review

- Review file: `roadmaps/automation/framework_simplification_strategy/reviews/framework-simplification-strategy-phase-4-review-iteration-1.md`
- Verdict: delivered

### Finding Disposition

- No findings.

### Residual Risks

- Same-context review was used because sub-agent delegation requires explicit user permission. The review records this limitation.
- Idea catalog capture, maintenance, status, and resolution writes remain future candidates; Phase 4 only migrated the proven proposal promotion primitives.

### Next Action

- Next run should start Phase 5 on `codex/framework-simplification-strategy-phase-5` and classify commands as keep, alias, deprecate, or internal without removing public behavior.

## Phase 5 - 2026-05-25 - Delivery Pass 1

Status: delivered
Branch: `codex/framework-simplification-strategy-phase-5`

### Scope

- Classify public commands as keep, alias, deprecate, or internal without removing behavior.
- Produce a user-facing migration table.
- Preserve current public commands, aliases, help shape, JSON envelopes, exit codes, and docs examples.

### Changes

- Added `roadmaps/automation/framework_simplification_strategy/phase_5_command_normalization_design.md` with classification rules, a migration table, deprecation requirements, and a complete public command classification.
- Recorded no active public deprecations for Phase 5; `review-surface` and `accepted revalidate` remain supported aliases with canonical replacements documented.
- Added README command-normalization status and internal-helper migration guidance.
- Added regression coverage requiring the design record to include every live public parser path plus `console snapshot`.
- Advanced the roadmap and delivery state to Phase 6 after a delivered review verdict.

### Tests And Verification

- `git diff --check`: passed
- `.venv/bin/python -m unittest tests.test_cli_help`: passed, 9 tests
- `.venv/bin/python -m unittest tests.test_doc_references`: passed, 18 tests
- `.venv/bin/python -m unittest discover -s tests`: passed, 835 tests
- `.venv/bin/async-research acceptance-suite`: passed, 15 checks

### Review

- Review file: `roadmaps/automation/framework_simplification_strategy/reviews/framework-simplification-strategy-phase-5-review-iteration-1.md`
- Verdict: delivered

### Finding Disposition

- No findings.

### Residual Risks

- Same-context review was used because sub-agent delegation requires explicit user permission. The review records this limitation.
- Future command deprecation remains a product decision and must add runtime replacement/rationale messaging in the same slice as README example updates.

### Next Action

- Next run should start Phase 6 on `codex/framework-simplification-strategy-phase-6` and record explicit Typer, jsonschema, and filelock decisions.

## Phase 6 - 2026-05-25 - Delivery Pass 1

Status: delivered
Branch: `codex/framework-simplification-strategy-phase-6`

### Scope

- Decide Typer, jsonschema, and filelock explicitly without adding runtime
  dependencies.
- Preserve the standard-library-only runtime posture, public CLI behavior, JSON
  envelopes, exit codes, schema behavior, workspace file formats, and lock
  semantics.
- Add a focused doc-reference guard for the decision record and runtime
  dependency posture.

### Changes

- Added `phase_6_dependency_decision_record.md` with explicit `defer`
  decisions for Typer, jsonschema, and filelock.
- Linked the README runtime dependency promise to the Phase 6 decision record.
- Added `tests.test_doc_references` coverage requiring the decision record to
  include all three dependency decisions and `pyproject.toml` to keep
  `project.dependencies = []`.
- Advanced the roadmap and delivery state to Phase 7 after a delivered review
  verdict.

### Tests And Verification

- `git diff --check`: passed
- `.venv/bin/python -m unittest tests.test_doc_references`: passed, 19 tests

### Review

- Review file: `roadmaps/automation/framework_simplification_strategy/reviews/framework-simplification-strategy-phase-6-review-iteration-1.md`
- Verdict: delivered

### Finding Disposition

- No findings.

### Residual Risks

- Same-context review was used because sub-agent delegation was not explicitly
  authorized. The review records this limitation.
- Future dependency adoption remains possible, but must be justified by new
  evidence and should prefer optional operator extras over default runtime
  requirements.

### Next Action

- Next run should start Phase 7 on `codex/framework-simplification-strategy-phase-7` and map replacement contracts and goldens before deleting or rewriting tests.
