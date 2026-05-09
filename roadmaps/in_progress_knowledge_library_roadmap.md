# Knowledge Library Roadmap

Status: In Progress
Current phase: Phase 2
Last updated: 2026-05-09
Next action: Add read-only parser and validator
Blocked by: None

Created: 2026-05-05

## Summary

Build a trusted knowledge library before, during, and after research task
execution. The library should collect durable background context from books,
papers, articles, posts, user notes, and previously accepted evidence.

The goal is not to create an exhaustive literature review by default. The goal
is to create enough trusted context for the current research mission: key
concepts, claims, methods, debates, source quality, caveats, and open
questions.

The library complements `accepted_outputs_index.md`; it does not replace it.
Accepted outputs are reviewed task results. The library is background context
and claim memory that helps choose, bound, and review future work.

## Execution Decisions

V1 should be contract-first and backward-compatible. The first execution goal is
to make the library file structure, source namespace, and validation contract
real without changing task execution semantics or silently mutating research
state.

### V1 Scope

V1 includes:

- starter `research_ops/library/` files in both templates
- documented Markdown table contracts for the library files
- idempotent `async-research library init research_ops --dry-run`
- explicit `async-research library init research_ops --write`
- read-only `async-research library validate research_ops`
- `library_refs` resolution against the canonical library path
- task guidance for reviewed library extraction and update proposals
- warning-only health, readiness, and weekly digest signals

V1 defers:

- import helpers for PDFs, browser bookmarks, citation managers, or note apps
- semantic truth verification beyond structural and provenance checks
- automatic crawling, embedding, RAG, or background source ingestion
- automatic library mutation from accepted outputs
- strict planning blocks for missing library coverage
- dashboard views until the parser and validator are stable

### Source Of Truth

The canonical library path is:

```text
research_ops/library/
```

Do not introduce a parallel `research_ops/knowledge/` namespace. Earlier
placeholder references to `research_ops/knowledge/knowledge_index.md` were a
pre-V1 compatibility bug and should not reappear in code or tests.

Markdown library tables are canonical in V1. There is no JSON canonical store in
the first version. If generated dashboard or digest projections appear later,
they must be rebuilt from the Markdown tables and must not own unique state.

Canonical ownership matrix:

| Surface | Owns | Must not own |
| --- | --- | --- |
| `library/source_library.md` | `LIT-*` source identity, source metadata, trust tier, status, location, provenance | final task claims, accepted-output status |
| `library/knowledge_index.md` | topic summaries, source refs, confidence, caveats | source identity or final citations |
| `library/claim_map.md` | durable claim memory, claim strength, disputed/stale status, caveats | publication approval or task acceptance |
| `library/method_index.md` | methods, assumptions, use cases, source refs, risks | experiment results or data readiness |
| `library/open_questions.md` | unresolved questions, gaps, next-task suggestions | execution queue state |
| `library/library_update_log.md` | reviewed library update provenance | full task result history |
| `accepted_outputs_index.md` | accepted task outputs and result links | durable background source inventory |
| `ideas/IDEA-*.json` | optional `library_refs` to `LIT-*` IDs | library source metadata |
| `queue.md` and `tasks/` | execution state | automatic library writes in V1 |

### Identifier And Status Model

`LIT-*` IDs are unique within one workspace library.

Recommended source namespace:

```text
LIT-0001
LIT-0002
LIT-0003
```

Source statuses:

```text
candidate
trusted
context_only
disputed
deprecated
```

Trust tiers:

```text
primary
supporting
background
weak
unknown
```

Use existing task-contract claim strength labels in `claim_map.md`:

```text
none
weak
suggestive
moderate
strong
```

Only a human can approve `strong` claims for publication or high-stakes use.
Library claim strength is memory for reviewers and planners, not final approval
for a new output.

User-provided notes are valid library sources when their provenance is explicit.
They should usually start as `type=user_note`, `trust_tier=background`, and
`status=context_only` until a reviewer promotes or caveats them.

### Update Authority

Workers may propose library updates from a task, but V1 workers must not write
directly to `research_ops/library/` unless a task explicitly grants that path and
the workflow records the reviewed update in `library_update_log.md`.

Accepted outputs may seed proposed library updates, but the update itself must
remain traceable to a reviewed task ID and reviewer/approver.

Mutating library commands must require explicit `--write`. Without `--write`,
commands are read-only or dry-run by default and must describe exact files that
would change.

### Validator Contract

Add:

```bash
async-research library validate research_ops
```

The command is read-only. It checks structure, provenance, and internal
references; it does not decide whether a scientific or market claim is true.

Exit codes:

- `0` when library contracts are valid
- `2` when warnings are present but the library shape is usable
- `4` when malformed library state prevents reliable parsing or reference checks

Warning-only validation should return exit `2` with `ok: true`,
`warning_count > 0`, and no error-level findings. This keeps cold-start gaps
visible without treating a new workspace as broken.

Cold-start behavior:

- missing `research_ops/library/` in an existing workspace warns, not fails
- empty starter library files pass or return warning-only status
- missing library coverage must not block discovery, idea scoring, or data
  readiness in V1
- malformed populated library files may block library-dependent promotion or
  reviewer checks

### Backward Compatibility

Implementation must preserve:

- existing `async-research init` behavior except for adding starter library files
- existing `async-research source`, `data`, `idea`, `readiness`, `health`, and
  `surface` commands
- existing idea candidates with optional `library_refs`
- existing workspaces that do not yet have `research_ops/library/`
- existing starter smoke, acceptance suite, and benchmark expectations

### Phase 0 Pre-Requirements

Before implementation starts, fix or decide the following:

1. **Canonical path mismatch.** The roadmap uses `research_ops/library/`, while
   early idea catalog unresolved-ref warnings pointed at
   `research_ops/knowledge/knowledge_index.md`. Align all code, docs, and tests
   on `research_ops/library/`. `library_refs` should resolve against
   `library/source_library.md` because `LIT-*` identifies sources.
2. **Task type vocabulary.** The roadmap proposes `library_review`, but the
   current controlled task vocabulary already has `literature_extract` and does
   not yet list `library_review`. Decide and document one path before adding a
   task template:
   - add `library_review` to task schemas, task contracts, review-tier defaults,
     and promotion/task-generation helpers; or
   - keep `literature_extract` as the V1 task type and add a library-update
     output contract.
3. **Library status vocabulary.** Adopt the V1 source statuses and trust tiers
   above so template files, validators, and review prompts do not drift.
4. **Update authority.** Document that worker outputs propose updates and that
   accepted, traceable writes require explicit write paths and an update log.
5. **Validator exit codes.** Match the `data validate` style: valid empty state
   is OK or warning-only; malformed populated state exits `4`.
6. **Reference semantics.** `LIT-*` refs are background/library refs. Final
   claims in accepted results still require source-level citation, not only a
   `LIT-*` pointer.
7. **Template safety.** Empty library files are valid cold-start state and must
   not cause `schema-check`, `readiness`, `health`, or `surface update` failures.

### First Test Matrix

Minimum tests for the first implementation phases:

- `async-research init research_ops` creates `research_ops/library/`
- generic and real-estate starter resources include all library files
- starter READMEs explain that an empty library is valid cold-start state
- existing `schema-check`, `readiness`, `health`, `surface update`, and
  `surface validate` still pass with empty library files
- `async-research library init research_ops --dry-run` reports missing files
- `async-research library init research_ops --write` adds only missing files and
  never overwrites existing notes
- `async-research library validate research_ops` accepts empty starter files
- missing `library/` in an existing workspace is warning-only
- duplicate `LIT-*` IDs fail validation
- malformed Markdown table rows are surfaced with file and row context
- claim rows without source refs are flagged
- disputed or deprecated sources and claims without caveats are flagged
- idea catalog `library_refs` resolve against `library/source_library.md`
- unresolved `library_refs` remain warning-level until the library feature is
  required by a specific task route

## What It Does

The library feature gives the framework reusable research memory:

- source inventory with stable library source IDs
- key claims and caveats linked to sources
- important methods, assumptions, and definitions
- open questions and unresolved disagreements
- known weak sources, dead ends, and anti-context
- gaps that should become future tasks

It supports multiple starting points:

- user provides a curated reading list
- user provides rough notes or local documents
- accepted outputs already exist and can seed proposed library updates
- no library exists yet, so the planner creates a small library extraction task

The library should make future work cheaper and safer without making early
discovery heavyweight. A missing library is a cold-start warning. A malformed or
misused library is a review concern.

## Delivery Strategy

Build this as a sequence of small, deterministic slices. Do not start with the
dashboard, import helpers, or strict planning gates. Those should consume a
stable Markdown contract and validator rather than inventing their own read
path.

Recommended sequence:

1. Lock Phase 0 decisions and compatibility fixes.
2. Add starter files, Markdown contracts, and safe init.
3. Add read-only parser, validator, and CLI.
4. Align idea catalog `library_refs` resolution with the new library path.
5. Add library extraction/update task guidance.
6. Feed health, readiness, weekly digest, and planner guidance from validator
   output.
7. Add read-only dashboard views.

Each phase should leave the package usable. Any strict blocking behavior should
ship only after a warning-only version has real test coverage.

Delivery boundary:

- MVP: Phases 0 through 3. This is decisions, starter state, contracts,
  idempotent init, and read-only validation.
- V1 post-MVP: Phases 4 through 6. This adds idea-catalog ref alignment, task
  guidance, and operational surfaces.
- V2: Phase 7 dashboard views, import helpers, automated extraction, semantic
  freshness policies, and stricter library-dependency gates.

## Progress

Last updated: 2026-05-09

| Phase | Step | Status | Description | Evidence / Notes |
| ---: | --- | --- | --- | --- |
| 0 | Pre-requirements and product decisions | Complete | Lock canonical path, task type choice, status vocabulary, update authority, validator contract, and compatibility rules before implementation starts. | Canonical `library_refs` resolution now targets `research_ops/library/source_library.md`; V1 keeps `literature_extract` as the executable task type and documents library-update proposal expectations, status vocabulary, update authority, validator exit codes, and cold-start safety. |
| 1 | Starter files, contracts, and safe init | Complete | Add `research_ops/library/` starter files to generic and real-estate templates, document table contracts, and add idempotent `library init`. | Adds library starter files, starter README guidance, public `async-research library init` dry-run/write behavior, packaged-resource coverage, safe migration tests, and a legacy `research_ops/knowledge/` regression guard. |
| 2 | Library parser and validator | Not started | Add read-only parsing and `async-research library validate research_ops` with cold-start warnings, duplicate ID checks, row-shape checks, provenance checks, and source-ref checks. | Reuse the data-foundations validator style where possible. |
| 3 | CLI, README, and docs integration | Not started | Wire public CLI help, README command tables, exit-code docs, starter README guidance, and package resource tests. | Completes MVP when validation is available and documented. |
| 4 | Idea catalog reference alignment | Partially complete | Resolve `library_refs` against `research_ops/library/source_library.md` and keep unresolved refs warning-level unless a route explicitly requires them. | The canonical target fix shipped with Phase 0; route-specific promotion explanation remains future work. |
| 5 | Library extraction task guidance | Not started | Add the chosen task contract for library extraction/update proposals and clarify allowed paths, required caveats, claim-strength rules, and update-log provenance. | Depends on Phase 0 task type decision. |
| 6 | Health, readiness, and weekly surfaces | Not started | Surface missing, stale, disputed, unsupported, and open-question library state without blocking all cold-start work. | Should consume validator output, not reparsed Markdown. |
| 7 | Dashboard surface | Not started | Add read-only dashboard views for source coverage, reviewed sources, stale/disputed claims, open questions, and proposed update tasks. | Deferred until parser/validator behavior is stable. |

## Framework Integration

Existing artifacts:

```text
research_ops/accepted_outputs_index.md
research_ops/discovery_inbox.md
research_ops/discovery/source_register.md
research_ops/ideas/IDEA-*.json
research_ops/queue.md
research_ops/tasks/
src/async_research_workflow/schemas/idea_candidate.schema.json
src/async_research_workflow/schemas/task_status.schema.json
```

New workspace artifacts:

```text
research_ops/
  library/
    source_library.md
    knowledge_index.md
    claim_map.md
    method_index.md
    open_questions.md
    library_update_log.md
```

Integration points:

- Discovery reads `library/` before browsing.
- Planner uses `open_questions.md` and `claim_map.md` to create bounded tasks.
- Idea scoring can reference library support and knowledge gaps.
- Idea catalog candidates may include `library_refs` with `LIT-*` source IDs.
- Workers may cite `LIT-*` IDs as background, but final claims still need
  source-level citation.
- Reviewers check whether outputs overstate claims already marked weak,
  disputed, stale, deprecated, or context-only.
- Accepted outputs can trigger reviewed library update proposals.

## Phase 0: Pre-Requirements And Product Decisions

Purpose: prevent the library from becoming a second ungoverned evidence system
or a brittle hidden dependency for discovery.

Decisions to record in docs before implementation:

- `research_ops/library/` is the canonical path.
- `research_ops/knowledge/` is not part of V1.
- `library/source_library.md` is authoritative for `LIT-*` identity.
- `library_refs` point to source IDs, not claim IDs.
- Markdown tables are canonical in V1.
- Empty library files are valid cold-start state.
- Existing workspaces without `library/` are valid partial-bootstrap state.
- Structural validation is read-only.
- Missing coverage warns; malformed populated state can fail.
- Workers propose library updates unless a task explicitly grants library write
  paths.
- Final accepted claims still require source-level citation.
- `library_review` versus `literature_extract` is decided before task template
  work starts.

Acceptance:

- roadmap and docs state the canonical library path clearly
- code and tests no longer point `library_refs` at `research_ops/knowledge/`
- task type decision is captured in `task_contracts.md` and schemas if needed
- validator exit-code contract is documented before CLI implementation
- no implementation step lets library maintenance edit `queue.md` or task
  folders

## Phase 1: Starter Files, Contracts, And Safe Init

Purpose: make the library visible in every new workspace without changing
runtime behavior.

Files to add to both starter templates:

```text
research_ops/library/source_library.md
research_ops/library/knowledge_index.md
research_ops/library/claim_map.md
research_ops/library/method_index.md
research_ops/library/open_questions.md
research_ops/library/library_update_log.md
```

`source_library.md` contract:

```markdown
# Source Library

<!-- LIBRARY-SOURCES: schema_version=1.0 -->
| source_id | status | trust_tier | type | title | author_or_publisher | location | reviewed_date | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
<!-- /LIBRARY-SOURCES -->

## Notes

Free-form notes. Tooling must not edit this section.
```

`knowledge_index.md` contract:

```markdown
# Knowledge Index

<!-- LIBRARY-KNOWLEDGE: schema_version=1.0 -->
| topic | summary | source_refs | confidence | caveats | updated_at |
| --- | --- | --- | --- | --- | --- |
<!-- /LIBRARY-KNOWLEDGE -->

## Notes

Free-form notes. Tooling must not edit this section.
```

`claim_map.md` contract:

```markdown
# Claim Map

<!-- LIBRARY-CLAIMS: schema_version=1.0 -->
| claim | source_refs | claim_strength | disputed_status | caveats | reviewed_date |
| --- | --- | --- | --- | --- | --- |
<!-- /LIBRARY-CLAIMS -->

## Notes

Free-form notes. Tooling must not edit this section.
```

`method_index.md` contract:

```markdown
# Method Index

<!-- LIBRARY-METHODS: schema_version=1.0 -->
| method | use_case | assumptions | source_refs | risks | reviewed_date |
| --- | --- | --- | --- | --- | --- |
<!-- /LIBRARY-METHODS -->

## Notes

Free-form notes. Tooling must not edit this section.
```

`open_questions.md` contract:

```markdown
# Open Questions

<!-- LIBRARY-OPEN-QUESTIONS: schema_version=1.0 -->
| question_id | question | why_it_matters | source_refs | next_task | status |
| --- | --- | --- | --- | --- | --- |
<!-- /LIBRARY-OPEN-QUESTIONS -->

## Notes

Free-form notes. Tooling must not edit this section.
```

`library_update_log.md` contract:

```markdown
# Library Update Log

<!-- LIBRARY-UPDATE-LOG: schema_version=1.0 -->
| date | task_id | files_updated | reviewer_or_approver | notes |
| --- | --- | --- | --- | --- |
<!-- /LIBRARY-UPDATE-LOG -->

## Notes

Free-form notes. Tooling must not edit this section.
```

Add:

```bash
async-research library init research_ops --dry-run
async-research library init research_ops --write
```

Migration safety:

- existing workspaces may not have `research_ops/library/`
- dry-run reports the exact missing files it would add
- write mode adds only missing starter files
- write mode must not overwrite existing files or free-form notes
- `async-research init` must not become an overwrite mechanism for live
  workspaces

Acceptance:

- `async-research init research_ops` creates `research_ops/library/`
- existing workspaces can safely add missing library files
- empty library files are valid cold-start state
- generated blocks are explicit and manual notes are outside them
- generic and real-estate starter READMEs explain library purpose and cold-start
  behavior

## Phase 2: Library Parser And Validator

Purpose: make the library inspectable before any operational surface consumes it.

Add:

```bash
async-research library validate research_ops
```

Checks:

- missing library directory in existing workspace is warning-only
- missing starter files are warning-level unless a populated library depends on
  them
- duplicate `LIT-*` IDs fail validation
- malformed generated blocks fail validation
- malformed table rows report file and row context
- missing source location or provenance is flagged
- missing source status or trust tier is flagged
- invalid source status or trust tier is flagged
- `knowledge_index.md`, `claim_map.md`, `method_index.md`, and
  `open_questions.md` source refs must point to `source_library.md`
- claim rows without source refs are flagged
- `moderate` or `strong` claims without caveats are flagged
- disputed, deprecated, or context-only sources used without caveats are flagged
- stale reviewed dates warn where configured
- update log rows must include task ID or reviewer/approver provenance

Acceptance:

- valid empty library passes or returns warning-only status
- duplicate IDs fail validation
- malformed claim rows are surfaced with file and row context
- unresolved source refs are reported deterministically
- warning-only findings return exit `2` with `ok: true`
- malformed generated blocks return exit `4`

## Phase 3: CLI, README, And Docs Integration

Purpose: make the library contract discoverable to operators and tests.

Update:

- root README command table
- root README exit-code table
- generic starter README
- real-estate starter README
- package resource tests
- CLI help tests
- doc reference tests

Acceptance:

- `async-research library --help` exposes `init` and `validate`
- root README documents the commands and exit codes
- starter READMEs explain how the library differs from accepted outputs
- packaged resources include every library starter file
- existing package-level docs/tests keep passing

## Phase 4: Idea Catalog Reference Alignment

Purpose: make existing `library_refs` useful without making the library required
for all idea work.

Change `library_refs` resolution so it targets:

```text
research_ops/library/source_library.md
```

Rules:

- `library_refs` remain optional on idea candidates
- missing `research_ops/library/` keeps unresolved library refs warning-level in
  normal catalog validation
- invalid `LIT-*` format remains a schema failure
- a route that explicitly requires library support may treat unresolved refs as
  blockers
- final task claims still need source-level citation even when an idea has
  library refs

Acceptance:

- an idea candidate with `library_refs=["LIT-0001"]` validates when
  `source_library.md` contains `LIT-0001`
- unresolved library refs warn against `library/source_library.md`, not
  `knowledge/knowledge_index.md`
- catalog validation remains usable in cold-start workspaces
- promotion dry-run can explain thin evidence versus missing library support

## Phase 5: Library Extraction Task Guidance

Purpose: give workers a bounded way to create or improve library state.

Depending on the Phase 0 task-type decision, either add a dedicated
`library_review` task type or harden `literature_extract` with a library-update
output contract.

The task should specify:

- topic or source set
- allowed source list
- whether browsing is allowed
- extraction fields
- source status and trust tier rules
- claim-strength rules
- required caveats
- anti-context and dead ends
- proposed output update targets
- validation commands to run

Output should include:

- proposed `source_library.md` rows
- proposed `knowledge_index.md` rows
- proposed `claim_map.md` rows
- proposed `method_index.md` rows where relevant
- proposed `open_questions.md` rows
- reviewer notes for weak, disputed, deprecated, or context-only sources
- exact files that would be updated

Acceptance:

- a worker can complete one library extraction task without writing outside the
  task folder unless explicitly granted library write paths
- reviewer can accept, revise, reject, or route to human
- accepted library updates are traceable to a reviewed task
- task guidance says to run `async-research library validate research_ops`
- high-stakes or `strong` claims route to human approval before publication use

## Phase 6: Health, Readiness, And Weekly Surfaces

Purpose: make library state visible without making cold-start discovery brittle.

Signals:

- missing library: warning only
- malformed populated library: blocker for library-dependent work
- stale high-priority topic: warning
- unresolved `library_refs` on active ideas: warning or route-specific blocker
- unsupported claim used by an active task: reviewer concern
- disputed/deprecated source used without caveat: reviewer concern
- new open questions: weekly digest summary

Acceptance:

- `health` and `readiness` explain library warnings without blocking all work
- `weekly_digest.md` can summarize library coverage and open questions
- surfaces consume validator output rather than reparsing tables separately
- source-dependent experiment and result gates continue to rely on source/data
  governance, not library memory alone

## Phase 7: Dashboard Surface

Purpose: make the library inspectable without opening raw Markdown files.

Add read-only dashboard views after the parser and validator are stable.

Show:

- library coverage by topic
- source counts by status and trust tier
- recently reviewed sources
- stale sources or claims
- disputed/deprecated/context-only claims
- open questions
- proposed library update tasks
- ideas with unresolved or thin library support

Acceptance:

- operator can understand library state without opening raw Markdown files
- dashboard reports warnings from the validator
- dashboard does not mutate library files in the first version

## AI Implementation Pattern

Use narrow AI work packets. Each packet should specify:

- owned files
- files to avoid
- expected command output
- exact tests to run
- whether writes are allowed

Recommended packet sequence:

1. Phase 0 docs and compatibility worker:
   - owns roadmap, task-type decision docs, and path decision docs
   - fixes references from `knowledge/` to `library/` only after tests describe
     expected behavior

2. Template and init worker:
   - owns starter template files, starter READMEs, package resource tests, and
     `library init`
   - avoids validator semantics beyond file presence

3. Parser and validator worker:
   - owns library read model and validator tests
   - does not touch operational surfaces

4. CLI/docs worker:
   - owns CLI wiring, help tests, README command tables, and exit-code docs
   - consumes validator behavior without changing it

5. Idea catalog integration worker:
   - owns `library_refs` resolution and catalog regression tests
   - avoids unrelated catalog lifecycle changes

6. Task guidance worker:
   - owns task contracts, schemas if needed, and worker/reviewer guidance
   - avoids dashboard or surface behavior

7. Surface worker:
   - owns health, readiness, and weekly digest integrations
   - consumes validator output

8. Dashboard worker:
   - owns read-only dashboard views after backend state is stable

Do not assign two workers to the same CLI, schema, or validator files in
parallel unless write scopes are explicitly separated.

## Test Strategy

Minimum checks per implementation slice:

```bash
.venv/bin/python -m unittest tests.test_doc_references
.venv/bin/python -m unittest tests.test_cli_architecture tests.test_cli_help
.venv/bin/python -m unittest tests.test_packaged_resources
```

Feature-specific tests to add:

- `tests.test_knowledge_library_templates`
- `tests.test_knowledge_library_migration`
- `tests.test_knowledge_library_parser`
- `tests.test_knowledge_library_validator`
- `tests.test_knowledge_library_cli`
- `tests.test_knowledge_library_idea_refs`
- `tests.test_knowledge_library_surfaces`
- `tests.test_knowledge_library_dashboard`

Regression scenarios:

- empty starter library
- missing `library/` directory
- partial library files
- generated block missing or malformed
- duplicate `LIT-*` ID
- invalid source status
- invalid trust tier
- source row missing location
- source row missing reviewed date
- source row with `context_only` and no notes
- claim row without source refs
- claim row pointing to missing `LIT-*`
- disputed claim without caveats
- deprecated source referenced by a current claim without caveats
- stale reviewed date
- open question without next task or status
- update log row without task ID or approver
- idea candidate `library_refs` resolved against `library/source_library.md`
- unresolved idea candidate `library_refs` warning-only in cold start
- old `knowledge/knowledge_index.md` path does not reappear in warning targets
- `library init --write` preserves existing manual notes

Package-level checks before merging the feature:

```bash
.venv/bin/python -m unittest discover tests
.venv/bin/async-research acceptance-suite
.venv/bin/async-research benchmark
.venv/bin/async-research starter-smoke /tmp/async-research-starter-generic --force
.venv/bin/async-research starter-smoke /tmp/async-research-starter-real-estate --template real-estate --force
.venv/bin/python -m compileall src tests
```

## MVP Definition

The MVP is complete when:

- new workspaces include `research_ops/library/`
- existing workspaces can safely add missing library files
- Markdown library tables are canonical
- empty library files are valid
- `source_library.md` owns `LIT-*` identity
- `async-research library init research_ops --dry-run` exists
- `async-research library init research_ops --write` exists
- `async-research library validate research_ops` exists
- duplicate source IDs, malformed rows, missing provenance, and unresolved
  source refs are reported clearly
- idea catalog `library_refs` point to `library/source_library.md`
- docs explain the difference between library memory, accepted outputs, and
  final source-level citation

## V1 Full Feature Definition

The v1 feature is complete when:

- library extraction/update task guidance is available
- workers can propose library updates without mutating library files by default
- reviewed updates are traceable in `library_update_log.md`
- idea scoring and promotion can use library refs as warning-level support
- health, readiness, and weekly digest expose library coverage and risks
- reviewers can see stale, disputed, deprecated, and context-only claim memory
- dashboard remains deferred or read-only

## Resolved Decisions

- `research_ops/library/` is the canonical V1 path.
- `research_ops/knowledge/` should not be introduced for this feature.
- `LIT-*` IDs identify library sources and are unique within a workspace.
- Markdown tables are canonical in V1.
- User-provided notes can be library sources when provenance is explicit.
- Missing library coverage is warning-only during cold start.
- `LIT-*` refs are background memory; final accepted claims still need
  source-level citation.
- Import helpers and automatic library mutation are deferred until after the
  parser and validator are stable.
