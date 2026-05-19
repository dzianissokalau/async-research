# Autonomous Delivery Pivot Roadmap

Status: In Progress
Current phase: Phase 9 - Release-Trust Docs And Scaling Guidance
Last updated: 2026-05-19
Next action: Run Phase 9 through the phase-gated delivery template
Blocked by: None

Created: 2026-05-18

## Summary

This roadmap pivots the remaining backlog into work that an LLM can deliver
without waiting for human product decisions, credentials, external publishing,
or live research-domain judgment.

The goal is not to automate everything. The goal is to extract the next
high-leverage implementation slices that are:

- file-backed
- locally testable
- safe to verify with repository fixtures
- clear enough for phase-gated Codex delivery
- useful for real research workflows
- bounded away from human-only judgment

Use the phase-gated automation template for every phase:

- [Codex Phase-Gated Delivery Automation Template](./automation/codex_phase_gated_delivery_automation_template.md)

This roadmap should be delivered one phase at a time. Do not start a later phase
until the current phase is implemented, verified, reviewed in a fresh context,
fixed if needed, and marked delivered.

## Autonomy Contract

The delivery LLM may do the following without human involvement:

- edit repository code, tests, docs, fixtures, schemas, and packaged examples
- add read-only CLI commands, validators, dashboard read models, and local
  smoke tests
- add write-capable commands only when the roadmap specifies dry-run defaults,
  explicit `--write`, preflight hashes, locks, rollback, and post-write
  validation
- use local fixture data and temporary directories
- run local unit tests, acceptance-suite checks, build checks, and package
  resource checks
- update roadmap status, delivery logs, and automation state for the current
  phase

The delivery LLM must stop and mark the phase `blocked` if any of the following
are required:

- external credentials, cloud access, paid APIs, or live network calls
- PyPI publishing, GitHub release publishing, or public package upload
- destructive git operations or deletion of user work
- changing source-of-truth policy beyond this roadmap
- making warning-only validators strict by default without an explicit phase
  instruction
- deciding a new product taxonomy not already specified here
- accepting high-stakes, public-facing, or strong claims without a human gate
- broad refactors that are not necessary for the current phase

## What This Roadmap Excludes

The following work remains outside autonomous delivery:

- publishing packages or releases
- live external data access checks that require credentials or network approval
- notebook, SQL, dbt, or warehouse execution adapters
- embedding/RAG indexes that introduce new storage/privacy decisions
- default-strict policy gates for cold-start workspaces
- publication-readiness judgment for a real manuscript
- choosing target venues, claims, or audiences for user research projects

If an implementation phase discovers that one of these decisions is required,
record the blocker and stop.

## Roadmap Inputs

This roadmap is a curated implementation pivot from:

- [Future Improvements Backlog](./not_started_future_improvements_backlog_roadmap.md)
- [Real Research Product Readiness Roadmap](./delivered_real_research_product_readiness_roadmap.md)
- [Deliverable Maturity And Editorial QA Roadmap](./delivered_deliverable_maturity_editorial_qa_roadmap.md)
- [Post-Review Operator Trust And Workflow Roadmap](./delivered_post_review_operator_trust_roadmap.md)

It intentionally prioritizes work that improves reliability, testability,
handoff, and autonomous framework operation before broader release or connector
ambitions.

## Priority Overview

| Rank | Phase | Priority | Autonomous Work | Why It Comes Here |
| ---: | ---: | --- | --- | --- |
| 1 | 0 | P0 | Roadmap lifecycle and automation hygiene | The roadmap index and lifecycle files must be coherent before another LLM can safely execute more work. |
| 2 | 1 | P0 | Stale-link guard and closeout checklist | Prevents repeated lifecycle/link drift after roadmap renames and delivered closeouts. |
| 3 | 2 | P1 | Shared proposal contract for foundation updates | Data and library apply workflows need one proposal language before inspection or writes. |
| 4 | 3 | P1 | Data foundation proposal inspection | Makes data-readiness worker proposals reviewable without mutating source-of-truth files. |
| 5 | 4 | P1 | Knowledge library proposal inspection | Makes literature/library worker proposals reviewable without manual table copy/paste. |
| 6 | 5 | P1 | Reviewed proposal apply commands | Removes repetitive manual foundation updates while preserving locks, review gates, and rollback. |
| 7 | 6 | P1 | Hypothesis/analysis adoption fixture and installed smoke | Proves the empirical loop works end to end from installed package resources. |
| 8 | 7 | P1/P2 | Analysis validator UX and reviewer packets | Reduces operator friction without weakening validation boundaries. |
| 9 | 8 | P2 | Idea traceability and lifecycle metrics | Improves explainability of how ideas become tasks and accepted outputs. |
| 10 | 9 | P2/P3 | Release-trust docs without publishing | Improves public confidence while avoiding credentials and release authority. |

## Phased Plan

| Phase | Focus | Scope | Exit Criteria |
| ---: | --- | --- | --- |
| 0 | Roadmap lifecycle and automation hygiene | Reconcile roadmap filenames, statuses, index rows, automation locations, and stale links. | Roadmap index, roadmap headers, filenames, and automation paths agree; documentation reference tests pass. |
| 1 | Roadmap and docs guardrails | Add stale-roadmap-link guard, closeout checklist, and packaging diagnostics. | Future lifecycle renames are test-protected and closeout instructions are explicit. |
| 2 | Shared foundation proposal contract | Define one machine-readable proposal format for data and library update proposals. | Worker outputs can carry validated proposals without mutating data/library files. |
| 3 | Data proposal inspection | Add read-only inspection for proposed data/source/profile/catalog/access/join/gap updates. | Reviewers can validate data foundation proposals before any apply path exists. |
| 4 | Library proposal inspection | Add read-only inspection for proposed library source/topic/claim/method/open-question updates. | Reviewers can validate library proposals before any apply path exists. |
| 5 | Reviewed proposal apply commands | Add guarded dry-run/write apply paths for accepted data and library proposals. | Accepted proposals can be applied transactionally with locks, rollback, and validation. |
| 6 | Analysis adoption fixture and installed smoke | Add a canonical empirical-loop fixture and installed-package analysis smoke. | Public analysis commands are proven from installed resources, not only editable repo state. |
| 7 | Analysis validator UX and reviewer packet | Add clearer validator explanations and a read-only reviewer packet command. | Operators and reviewers can understand blockers and review evidence faster. |
| 8 | Idea traceability and metrics | Persist promotion trace metadata and expose lifecycle metrics/read models. | Task origins and idea-to-output flow are inspectable without raw JSON archaeology. |
| 9 | Release-trust docs and scaling guidance | Add hardening report, scaling boundaries, and worked-example guidance without publishing. | External users can evaluate maturity while release authority remains human-owned. |

## Phase 0 - Roadmap Lifecycle And Automation Hygiene

### Objective

Make the roadmap folder internally coherent before new autonomous work starts.
This phase handles only roadmap metadata, filenames, index rows, automation-file
locations, and stale links.

### Inputs

- `roadmaps/README.md`
- all `roadmaps/*_roadmap.md` files
- `roadmaps/automation/`
- `tests.test_doc_references`
- current `git status`

### Owned Files

The delivery LLM may edit:

- `roadmaps/README.md`
- roadmap files whose header status does not match their filename/status row
- links inside roadmap files
- `roadmaps/automation/README.md`
- automation delivery logs/state paths under `roadmaps/automation/`
- documentation-reference tests only if needed to reflect lifecycle policy

### Implementation Steps

1. Read `roadmaps/README.md` and collect every roadmap row.
2. Read the header of every `roadmaps/*_roadmap.md` file.
3. Build a table with `path`, `header status`, `header current phase`,
   `README status`, and `filename lifecycle prefix`.
4. Identify mismatches where the header and filename disagree. Example:
   a file named `in_progress_*_roadmap.md` whose header says `Status:
   Delivered` and `Current phase: Complete`.
5. For each mismatch, prefer the roadmap header as the source of truth if the
   header says delivered and all prioritized improvements in that roadmap are
   marked `Complete` or `Backlog`.
6. Rename lifecycle files to match their status. Use non-destructive moves and
   preserve file contents.
7. Update `roadmaps/README.md` rows to point to the renamed files.
8. Search for stale references to renamed files with `rg`.
9. Update inbound links. Historical prose may mention an old filename only when
   it explicitly says the name is historical; normal roadmap links must point
   to the current file.
10. Confirm automation files live under `roadmaps/automation/<roadmap-slug>/`.
    If duplicate legacy files exist in the root `roadmaps/` folder and the same
    content exists under `roadmaps/automation/`, update references to the
    automation path. Do not delete unique content.
11. Run verification.

### Acceptance Criteria

- Every roadmap row in `roadmaps/README.md` links to an existing file.
- Every linked roadmap file has a lifecycle filename matching its header
  status: `delivered_`, `in_progress_`, `not_started_`, `blocked_`,
  `paused_`, or `superseded_`.
- No normal link points to a stale lifecycle filename.
- Automation state/log/review references point under `roadmaps/automation/`
  when they refer to automation machinery.
- No content is deleted; moved files preserve their contents.
- Documentation reference tests pass.

### Required Verification

```bash
rg -n "in_progress_.*_roadmap|not_started_.*_roadmap|delivered_.*_roadmap" roadmaps
git diff --check
.venv/bin/python -m unittest tests.test_doc_references
```

### Non-Goals

- Do not implement feature behavior.
- Do not alter backlog priorities.
- Do not publish, push, or release.
- Do not delete legacy files unless their content has been confirmed moved and
  the phase reviewer agrees.

### Blockers

Stop if a roadmap's header, filename, and implementation table disagree in a
way that cannot be resolved mechanically.

## Phase 1 - Roadmap And Docs Guardrails

### Objective

Prevent the lifecycle drift fixed in Phase 0 from recurring. Add tests and
operator documentation so future roadmap closeouts are repeatable.

### Inputs

- Phase 0 delivered state
- `tests.test_doc_references`
- existing documentation iteration helpers
- `roadmaps/README.md`
- `roadmaps/automation/codex_phase_gated_delivery_automation_template.md`

### Owned Files

The delivery LLM may edit:

- documentation reference tests
- `roadmaps/README.md`
- `roadmaps/automation/README.md`
- a new or existing roadmap closeout checklist document
- docs packaging tests for diagnostics only

### Implementation Steps

1. Add a test that parses `roadmaps/README.md` and maps each roadmap display
   name to its current path.
2. Add a stale-roadmap-link guard that scans documentation files for links to
   known old lifecycle filenames when a current replacement exists.
3. Allow explicit historical mentions only when they are plain text or when the
   same sentence or bullet clearly labels the old path as historical. Do not
   allow normal Markdown links to stale lifecycle files.
4. Add error messages that name the stale path and the replacement path.
5. Add a short closeout checklist covering: update header, rename file, update
   index, update inbound links, move automation artifacts under
   `roadmaps/automation/`, run stale-link scan, run doc tests, and record
   backlog follow-ups.
6. Improve packaging-threshold diagnostics if this can be done without changing
   packaging policy. Diagnostics should report total docs bytes, largest docs,
   non-Markdown files, and threshold values.
7. Run verification.

### Acceptance Criteria

- A stale roadmap link to a replaced lifecycle filename fails a test with an
  actionable error.
- Valid current roadmap links pass.
- Historical mentions remain possible only when clearly labeled as history.
- A human or LLM can close a roadmap by following a concise checklist.
- Packaging diagnostics are more actionable if packaging tests fail.

### Required Verification

```bash
git diff --check
.venv/bin/python -m unittest tests.test_doc_references
.venv/bin/python -m unittest tests.test_docs_packaging
```

### Non-Goals

- Do not build a full roadmap management CLI.
- Do not change package-data thresholds.
- Do not move non-roadmap docs.

### Blockers

Stop if existing test utilities cannot distinguish current roadmap links from
historical prose without a broad parser rewrite.

## Phase 2 - Shared Foundation Proposal Contract

### Objective

Create one proposal format for data and library foundation updates so workers
can propose durable changes without directly mutating source-of-truth files.

### Inputs

- Data Foundations backlog proposal/apply items
- Knowledge Library backlog proposal/apply items
- current Markdown table contracts under `research_ops/data/`
- current library table contracts under `research_ops/library/`
- source governance rules for `DS-*`
- library rules for `LIT-*`

### Owned Files

The delivery LLM may edit:

- package schemas/resources
- proposal parser/validator modules
- CLI wiring for read-only proposal validation if needed
- tests and fixtures
- docs/templates that teach worker proposal format

### Required Proposal Format

Use this exact v1 envelope for both data and library proposals:

```json
{
  "proposal_version": "foundation_update_proposal_v1",
  "proposal_id": "PROP-0001",
  "source_task_id": "TASK-0001-example",
  "target": "data",
  "created_by": "worker",
  "rationale": "Why these foundation rows should change.",
  "operations": []
}
```

Allowed `target` values:

- `data`
- `library`

Allowed embedding forms:

- standalone JSON artifact under a task `artifacts/` directory
- fenced code block in `worker_output.md` whose info string contains
  `foundation_update_proposal_v1`

The parser must reject ambiguous files that contain multiple proposals with the
same `proposal_id`.

### Data Operation Types

Support these operation names in the schema, even if later phases implement
deeper semantic validation:

- `upsert_data_source`
- `upsert_data_profile`
- `upsert_data_catalog_row`
- `upsert_data_access_row`
- `upsert_join_map_row`
- `upsert_known_data_gap`

Every data operation must include:

- `operation_id`
- `operation`
- `target_path`
- `row_id`
- `payload`
- `preserve_manual_notes`

### Library Operation Types

Support these operation names in the schema:

- `upsert_lit_source`
- `upsert_topic_summary`
- `upsert_claim`
- `upsert_method`
- `upsert_open_question`
- `append_library_update_log`

Every library operation must include:

- `operation_id`
- `operation`
- `target_path`
- `row_id`
- `payload`
- `preserve_manual_notes`

### Implementation Steps

1. Add a schema or typed validator for `foundation_update_proposal_v1`.
2. Add parser helpers that discover proposals in standalone JSON artifacts and
   fenced blocks.
3. Validate envelope fields, target values, unique operation IDs, target paths,
   row IDs, and required payload objects.
4. Ensure proposal parsing is read-only.
5. Add fixtures for valid data proposal, valid library proposal, duplicate
   proposal ID, unknown operation, missing required field, and malformed JSON.
6. Add docs or template snippets showing the exact proposal format.

### Acceptance Criteria

- The shared parser can load proposals from JSON artifacts and fenced
  `worker_output.md` blocks.
- Invalid proposals produce structured diagnostics with path, proposal ID when
  available, operation ID when available, severity, and remediation.
- No source-of-truth data or library file is modified by this phase.
- Data and library phases can reuse the same parser.

### Required Verification

```bash
git diff --check
.venv/bin/python -m unittest tests.test_doc_references
.venv/bin/python -m unittest discover -s tests
```

### Non-Goals

- Do not apply proposals.
- Do not infer proposals from arbitrary prose.
- Do not support external imports yet.
- Do not add embeddings or search indexes.

### Blockers

Stop if current table contracts are too inconsistent to express with the v1
operation list above without changing source-of-truth semantics.

## Phase 3 - Data Foundation Proposal Inspection

### Objective

Add read-only tooling that inspects data foundation proposals and tells a
reviewer whether the proposed rows are valid before any write path exists.

### Inputs

- Phase 2 proposal parser
- `research_ops/data_source_audit.md`
- `research_ops/data/data_catalog.md`
- `research_ops/data/data_access.md`
- `research_ops/data/join_map.md`
- `research_ops/data/known_data_gaps.md`
- `research_ops/data/profiles/*.md`
- existing `data validate` and `source validate` behavior

### Owned Files

The delivery LLM may edit:

- data proposal inspection module
- public CLI wiring
- tests and fixtures
- data foundation docs/templates

### Public Command

Add this read-only command:

```bash
async-research data inspect-proposals <ops-dir> <proposal-source>
```

`<proposal-source>` may be:

- a task directory
- a `worker_output.md` file
- a JSON proposal artifact
- a directory containing proposal artifacts

### Output Contract

Return JSON with these top-level fields:

- `ok`
- `ops_dir`
- `proposal_source`
- `proposals_found`
- `valid_proposals`
- `invalid_proposals`
- `operations`
- `warnings`
- `blockers`
- `next_steps`

Each operation diagnostic must include:

- `proposal_id`
- `operation_id`
- `operation`
- `target_path`
- `row_id`
- `status`
- `message`

### Implementation Steps

1. Reuse Phase 2 parser to discover proposals.
2. Reject proposals whose `target` is not `data`.
3. Validate target paths are inside the selected `research_ops/` workspace and
   match known data/source files.
4. Validate row ID shape: `DS-*` for source rows, profile file references for
   profiles, and stable row IDs where existing tables support them.
5. Detect duplicate row IDs within one proposal.
6. Detect conflicts with existing rows and classify them as warnings when an
   upsert would replace a row, blockers when the operation is malformed.
7. Do not write files.
8. Add fixtures for a valid data-readiness proposal, duplicate `DS-*`, invalid
   target path, path traversal, unknown operation, and existing-row upsert.

### Acceptance Criteria

- Reviewers can inspect a data-readiness worker proposal without manually
  copying rows into Markdown tables.
- The command never mutates `research_ops`.
- Path traversal and outside-workspace targets fail closed.
- Diagnostics are specific enough for a worker to fix the proposal.

### Required Verification

```bash
git diff --check
.venv/bin/python -m unittest tests.test_doc_references
.venv/bin/python -m unittest discover -s tests
.venv/bin/async-research data inspect-proposals <fixture-ops-dir> <fixture-proposal-source>
```

Use a repository fixture or temporary fixture for the command smoke. Do not use
a user's live research workspace.

### Non-Goals

- Do not apply data proposals.
- Do not run live access checks.
- Do not change `data validate` strictness.
- Do not introduce `JOIN-*` entities yet.

### Blockers

Stop if adding this command requires changing existing data/source validation
semantics in a way not specified here.

## Phase 4 - Knowledge Library Proposal Inspection

### Objective

Add read-only tooling that inspects proposed knowledge-library updates and
reports whether generated `LIT-*`, topic, claim, method, and open-question rows
would validate before any write path exists.

### Inputs

- Phase 2 proposal parser
- `research_ops/library/source_library.md`
- `research_ops/library/knowledge_index.md`
- `research_ops/library/claim_map.md`
- `research_ops/library/method_index.md`
- `research_ops/library/open_questions.md`
- `research_ops/library/library_update_log.md`
- existing `library validate` behavior

### Owned Files

The delivery LLM may edit:

- library proposal inspection module
- public CLI wiring
- tests and fixtures
- knowledge library docs/templates

### Public Command

Add this read-only command:

```bash
async-research library inspect-proposals <ops-dir> <proposal-source>
```

`<proposal-source>` may be:

- a task directory
- a `worker_output.md` file
- a JSON proposal artifact
- a directory containing proposal artifacts

### Output Contract

Return JSON with these top-level fields:

- `ok`
- `ops_dir`
- `proposal_source`
- `proposals_found`
- `valid_proposals`
- `invalid_proposals`
- `operations`
- `warnings`
- `blockers`
- `next_steps`

Each operation diagnostic must include:

- `proposal_id`
- `operation_id`
- `operation`
- `target_path`
- `row_id`
- `status`
- `message`

### Implementation Steps

1. Reuse Phase 2 parser to discover proposals.
2. Reject proposals whose `target` is not `library`.
3. Validate target paths are inside the selected `research_ops/library/`
   directory and match known library files.
4. Validate ID shapes: `LIT-*` for sources, `TOPIC-*` or existing topic IDs
   where local contracts use them, `CLAIM-*`, `METHOD-*`, and `OQ-*` when
   applicable.
5. Detect duplicate row IDs within one proposal.
6. Detect missing source references inside claim/method/topic payloads.
7. Detect conflicts with existing rows and classify expected upserts as
   warnings, malformed rows as blockers.
8. Do not write files.
9. Add fixtures for valid literature-extract proposal, duplicate `LIT-*`,
   missing source reference, invalid target path, path traversal, unknown
   operation, and existing-row upsert.

### Acceptance Criteria

- Reviewers can inspect a literature worker proposal without manually copying
  rows into library Markdown tables.
- The command never mutates `research_ops`.
- Path traversal and outside-workspace targets fail closed.
- Diagnostics are specific enough for a worker to fix the proposal.

### Required Verification

```bash
git diff --check
.venv/bin/python -m unittest tests.test_doc_references
.venv/bin/python -m unittest discover -s tests
.venv/bin/async-research library inspect-proposals <fixture-ops-dir> <fixture-proposal-source>
```

Use a repository fixture or temporary fixture for the command smoke. Do not use
a user's live research workspace.

### Non-Goals

- Do not apply library proposals.
- Do not import PDFs, bookmarks, citation managers, or browser data.
- Do not add embeddings or search indexes.
- Do not make library-support gates stricter.

### Blockers

Stop if current library table contracts do not expose enough structure to
validate proposed rows without changing the library source-of-truth model.

## Phase 5 - Reviewed Proposal Apply Commands

### Objective

Add guarded write paths that apply accepted data and library proposals while
preserving manual notes, using locks, supporting rollback, and validating after
write.

### Inputs

- Phase 2 proposal parser
- Phase 3 data proposal inspection
- Phase 4 library proposal inspection
- existing transaction or lock helpers
- review/task acceptance artifacts
- `source validate`, `data validate`, and `library validate`

### Owned Files

The delivery LLM may edit:

- data proposal apply module
- library proposal apply module
- CLI wiring
- transaction/lock helpers if existing helpers are insufficient
- tests and fixtures
- docs/templates

### Public Commands

Add these commands:

```bash
async-research data apply-proposals <ops-dir> <proposal-source> --dry-run
async-research data apply-proposals <ops-dir> <proposal-source> --write --preflight-hash <hash>
async-research library apply-proposals <ops-dir> <proposal-source> --dry-run
async-research library apply-proposals <ops-dir> <proposal-source> --write --preflight-hash <hash>
```

Default behavior must be dry-run if neither `--dry-run` nor `--write` is
provided.

### Write Preconditions

Write mode must require all of the following:

- proposal inspection returns no blockers
- a preflight hash from the dry-run output matches current proposal and target
  file state
- source task status is accepted, or the operator supplies an existing accepted
  review/result acceptance artifact path that validates
- target files are inside `research_ops`
- target foundation lock is acquired
- post-write validation command passes

### Implementation Steps

1. Add dry-run plan output for data and library proposals.
2. Include proposed file edits, preflight hash, warnings, blockers, and exact
   post-write validators in dry-run output.
3. Implement write mode behind explicit `--write`.
4. Acquire a target-specific lock before re-reading proposal and target files.
5. Recompute preflight hash after lock acquisition.
6. Apply operations idempotently. Existing matching rows should not duplicate.
7. Preserve free-form manual notes outside generated table blocks.
8. Write through a transaction helper with rollback on failure.
9. Run post-write validators. For data, run `source validate` if source rows
   changed and `data validate` when data files changed. For library, run
   `library validate`.
10. If post-write validation fails, rollback and report the validation output.
11. Add tests for dry-run, stale preflight hash, lock contention, successful
    write, idempotent second write, rollback on validation failure, and manual
    note preservation.

### Acceptance Criteria

- Dry-run mode is safe and default.
- Write mode cannot run without explicit `--write` and matching preflight hash.
- Apply commands are idempotent.
- Manual notes are preserved.
- Failed writes rollback or report unrecoverable rollback failure clearly.
- Post-write validation passes before success is reported.

### Required Verification

```bash
git diff --check
.venv/bin/python -m unittest tests.test_doc_references
.venv/bin/python -m unittest discover -s tests
.venv/bin/async-research data apply-proposals <fixture-ops-dir> <fixture-proposal-source> --dry-run
.venv/bin/async-research library apply-proposals <fixture-ops-dir> <fixture-proposal-source> --dry-run
```

Write-mode smoke tests must use temporary fixture copies, never a user's live
workspace.

### Non-Goals

- Do not auto-approve proposals.
- Do not treat proposed rows as authoritative before write succeeds.
- Do not bypass source governance or library validation.
- Do not add import automation.

### Blockers

Stop if current Markdown table writers cannot preserve manual notes without a
larger parser rewrite.

## Phase 6 - Analysis Adoption Fixture And Installed Smoke

### Objective

Prove the hypothesis/analysis framework works end to end through installed
package resources and public CLI commands.

### Inputs

- delivered Hypothesis Testing Framework
- current `analysis preflight`, `analysis validate-run`,
  `analysis validate-results`, `analysis dashboard`, and `analysis run-adapter`
- existing experiment/result acceptance validators
- package-data policy

### Owned Files

The delivery LLM may edit:

- packaged examples and fixture files
- tests for installed-package analysis smoke
- docs linking to the fixture
- package-data configuration when needed

### Fixture Requirements

Add one small deterministic fixture that includes:

- accepted experiment plan
- planned analysis run manifest
- completed run manifest
- metrics artifact
- diagnostics artifact
- robustness artifact
- claim-gate artifact
- result summary
- result acceptance record
- accepted index refresh target
- analysis dashboard expected output

The fixture must be tiny, deterministic, and readable. It must not perform
statistical estimation in the framework package; it only exercises contracts.

### Implementation Steps

1. Locate existing example/fixture conventions.
2. Add or update a fixture under the repository's existing package example or
   fixture location.
3. Ensure package-data includes the fixture.
4. Add tests that run public analysis commands against a copied temporary
   fixture.
5. Add an installed-package smoke if local build tooling already exists. The
   smoke must install the built wheel into a temporary environment and run the
   public analysis commands from the installed package.
6. Document the copy-and-run commands.

### Acceptance Criteria

- Fixture exercises the empirical loop from accepted plan through accepted
  empirical evidence.
- Public analysis commands pass against the fixture.
- Packaged resources expose the fixture from an installed package.
- No editable-install-only paths are required.

### Required Verification

```bash
git diff --check
.venv/bin/python -m unittest tests.test_doc_references
.venv/bin/python -m unittest discover -s tests
.venv/bin/python -m build
```

If build tooling is unavailable, record the environmental blocker and do not
mark the phase delivered.

### Non-Goals

- Do not add new statistical methods.
- Do not execute notebooks, SQL, dbt, or warehouse jobs.
- Do not call external APIs.

### Blockers

Stop if installed-package smoke cannot run locally for environmental reasons
after one retry with the documented project build command.

## Phase 7 - Analysis Validator UX And Reviewer Packet

### Objective

Make analysis validation failures easier to understand and create a read-only
reviewer packet that bundles evidence for human or LLM review.

### Inputs

- Phase 6 fixture
- `analysis preflight`
- `analysis validate-run`
- `analysis validate-results`
- `analysis dashboard`
- existing review context patterns

### Owned Files

The delivery LLM may edit:

- analysis validator output helpers
- CLI docs/help
- reviewer packet command implementation
- tests and fixtures
- operator docs

### Public Command

Add a read-only command unless an equivalent public command already exists:

```bash
async-research analysis reviewer-packet <ops-dir> <analysis-run-dir>
```

### Reviewer Packet Contents

The packet must include paths or embedded summaries for:

- accepted experiment plan
- run manifest
- metrics
- diagnostics
- robustness checks
- claim gates
- result summary
- validator outputs
- result acceptance status
- source/data governance status
- recommended reviewer focus

The packet must not mark validation as passed. It only collects review context.

### Validator UX Requirements

For validator failures, add concise remediation fields while keeping existing
machine-readable fields stable:

- `summary`
- `failing_field`
- `why_it_matters`
- `next_step`
- `docs_ref` when available

### Implementation Steps

1. Identify current validator JSON contracts and preserve existing fields.
2. Add remediation fields for common blockers without changing exit semantics.
3. Add reviewer packet command or option as a read-only route.
4. Use the Phase 6 fixture for tests.
5. Add tests for successful packet generation, missing artifact diagnostics,
   and validator remediation fields.

### Acceptance Criteria

- Existing JSON consumers remain compatible.
- Validator blockers include actionable next steps.
- Reviewer packet generation is read-only.
- Missing artifacts produce clear diagnostics.

### Required Verification

```bash
git diff --check
.venv/bin/python -m unittest tests.test_doc_references
.venv/bin/python -m unittest discover -s tests
.venv/bin/async-research analysis reviewer-packet <fixture-ops-dir> <fixture-analysis-run-dir>
```

### Non-Goals

- Do not auto-review empirical results.
- Do not change claim gates.
- Do not mark any packet as accepted evidence.

### Blockers

Stop if adding remediation fields would break documented JSON contracts and no
compatible extension point exists.

## Phase 8 - Idea Traceability And Lifecycle Metrics

### Objective

Make the idea-to-task-to-output path inspectable without opening raw idea JSON,
queue rows, task statuses, and accepted output files by hand.

### Inputs

- Idea Catalog delivered commands
- task status schema
- queue rows
- accepted outputs index
- cost ledger if present
- dashboard read model

### Owned Files

The delivery LLM may edit:

- idea promotion metadata helpers
- task creation metadata fields if optional/backward-compatible
- idea metrics read model
- dashboard snapshot read model
- tests and docs

### Public Commands

Add these commands only if equivalent commands do not already exist:

```bash
async-research idea metrics <ops-dir>
async-research idea trace <ops-dir> <IDEA-ID>
```

### Trace Metadata

When an idea promotion creates or links a task, persist optional point-in-time
metadata:

- `origin_idea_id`
- `promotion_score_snapshot`
- `promotion_route`
- `routing_reason`
- `blocker_snapshot`
- `promotion_preflight_hash`
- `promotion_transaction_id`

This metadata is trace-only. `ideas/IDEA-*.json` remains the canonical idea
record.

### Metrics

Expose these metrics when data exists:

- time from capture to candidate
- time from candidate to promote
- time from promote to task creation
- time from task creation to accepted/rejected output
- parked idea age
- duplicate rate
- blocker frequency
- cost per accepted promoted idea when cost data exists

Missing timestamps must render as `unavailable`, not `0`.

### Implementation Steps

1. Inspect existing idea promotion and dashboard read-model code.
2. Add optional trace metadata without breaking existing task schemas.
3. Add read-only trace and metrics helpers.
4. Feed trace summaries into dashboard read models if there is an existing
   stable dashboard snapshot path.
5. Add fixtures for promoted idea, parked idea, rejected idea, missing
   timestamps, task accepted, and task rejected.

### Acceptance Criteria

- Operators can answer why a task exists and which idea created it.
- Metrics are read-only and deterministic.
- Missing data is explicit.
- Existing idea/task JSON remains valid.

### Required Verification

```bash
git diff --check
.venv/bin/python -m unittest tests.test_doc_references
.venv/bin/python -m unittest discover -s tests
.venv/bin/async-research idea metrics <fixture-ops-dir>
.venv/bin/async-research idea trace <fixture-ops-dir> <fixture-idea-id>
```

### Non-Goals

- Do not add semantic dedupe or embeddings.
- Do not make stricter promotion gates default.
- Do not create tasks from open questions automatically.

### Blockers

Stop if trace metadata would require a breaking task schema migration.

## Phase 9 - Release-Trust Docs And Scaling Guidance

### Objective

Improve external trust without performing any release or public publishing
action.

### Inputs

- delivered roadmap summaries
- package build/test commands
- existing README and docs
- delivered examples and fixtures
- current package metadata

### Owned Files

The delivery LLM may edit:

- README
- docs
- changelog or hardening report
- examples index
- scaling guidance
- package metadata tests only if needed for docs consistency

### Implementation Steps

1. Add or update a hardening report that summarizes delivered safety,
   validation, dashboard, maturity, and proposal/apply capabilities with test
   commands.
2. Add scaling guidance for file-backed workspaces: expected size, linear-scan
   tradeoffs, when to split workspaces, and when to graduate to heavier
   orchestration.
3. Add a worked-examples index that points to packaged runnable examples and
   explains what each proves.
4. Add release-readiness notes that distinguish local verification from actual
   PyPI/GitHub publishing.
5. Ensure badges or release claims do not imply a publish happened unless it
   already happened before this phase.
6. Run documentation and packaging checks.

### Acceptance Criteria

- External readers can understand what is proven, what is alpha, and what is
  intentionally out of scope.
- Docs explain scaling boundaries honestly.
- Docs link to runnable examples and acceptance commands.
- No public release or publishing action is performed.

### Required Verification

```bash
git diff --check
.venv/bin/python -m unittest tests.test_doc_references
.venv/bin/python -m unittest tests.test_docs_packaging
.venv/bin/python -m unittest discover -s tests
```

### Non-Goals

- Do not publish to PyPI.
- Do not create a GitHub release.
- Do not make claims based on tests that were not run.
- Do not add new product features.

### Blockers

Stop if release wording requires a human decision about market positioning,
version number, license policy, or publication timing.

## Automation Configuration

Use these placeholders with the phase-gated template:

```text
ROADMAP_PATH=roadmaps/in_progress_autonomous_delivery_pivot_roadmap.md
ROADMAP_SLUG=autonomous_delivery_pivot
BRANCH_PREFIX=codex/
BRANCH_NAME=codex/autonomous-delivery-pivot-phase-<phase-n>
STATE_FILE=roadmaps/automation/autonomous_delivery_pivot/delivery_state.json
DELIVERY_LOG=roadmaps/automation/autonomous_delivery_pivot/delivery_log.md
REVIEW_DIR=roadmaps/automation/autonomous_delivery_pivot/reviews
MAX_REVIEW_ITERATIONS=3
CADENCE=30 minutes
```

Initial state:

```json
{
  "roadmap": "roadmaps/in_progress_autonomous_delivery_pivot_roadmap.md",
  "roadmap_slug": "autonomous_delivery_pivot",
  "current_phase": "0",
  "branch": "codex/autonomous-delivery-pivot-phase-0",
  "status": "not_started",
  "review_iterations": 0,
  "max_review_iterations": 3,
  "last_verification": null,
  "blocked_reason": null,
  "updated_at": null
}
```

## Global Verification

Run these after every phase unless the phase defines stricter verification:

```bash
git diff --check
.venv/bin/python -m unittest tests.test_doc_references
.venv/bin/python -m unittest discover -s tests
```

Run this when phase changes touch package resources, CLI command coverage, or
end-to-end workflow behavior:

```bash
.venv/bin/async-research acceptance-suite
```

Run this when phase changes touch package-data, examples, or installed-package
behavior:

```bash
.venv/bin/python -m build
```

## Global Stop Conditions

Stop the automation and mark the phase `blocked` when:

- verification cannot run
- a review verdict remains `needs-fix` after three iterations
- a required change would alter user data outside fixtures
- a required change would need external credentials or network access
- a required change would publish or push externally
- the implementation needs product judgment not specified in this roadmap
- the worktree contains conflicting unrelated edits in files the phase must own

## How Another LLM Should Start

1. Read this roadmap.
2. Read the phase-gated automation template.
3. Read `roadmaps/README.md`.
4. Inspect `git status`.
5. Start only Phase 0.
6. Create or reuse `codex/autonomous-delivery-pivot-phase-0`.
7. Create `roadmaps/automation/autonomous_delivery_pivot/delivery_state.json`
   and `delivery_log.md`.
8. Implement only Phase 0.
9. Run required verification.
10. Request a fresh-context review using the reviewer prompt in the automation
    template.
11. Fix review findings within Phase 0 scope.
12. Mark Phase 0 delivered only after the reviewer verdict is `delivered`.
