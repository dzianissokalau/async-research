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
