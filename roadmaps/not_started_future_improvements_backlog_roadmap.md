# Future Improvements Backlog

Status: Not Started
Current phase: Backlog
Last updated: 2026-05-10
Next action: Select one item and split it into a dedicated roadmap when explicitly requested
Blocked by: None

Created: 2026-05-10

## Summary

This backlog captures post-delivery improvement ideas that are not active
implementation tracks. It should not be used as an execution plan by itself.
Before implementation starts, promote one focused item into a dedicated roadmap
with phases, acceptance tests, owned files, and rollout risks.

Use this file to preserve context after delivered roadmaps close, especially
when a shipped feature has intentional V1 boundaries.

## Selection Rules

- Prefer fixes for dogfood pain, correctness risks, or repeated manual work.
- Keep cold-start behavior warning-only unless a stricter gate has already
  shipped as warning-only with real usage evidence.
- Do not let derived indexes, dashboards, embeddings, or imported artifacts
  become sources of truth. Repo files remain authoritative.
- Any write-capable follow-up needs idempotency, lock/transaction behavior,
  rollback reporting, and tests proving manual notes are preserved.
- High-stakes, public-facing, or `strong` claims should require human approval
  before publication use.

## Knowledge Library

Current shipped baseline:

- canonical path: `research_ops/library/`
- source IDs: `LIT-*` rows in `library/source_library.md`
- public commands: `library init`, `library validate`, and `library dashboard`
- integrations: idea-catalog `library_refs`, `literature_extract` task
  guidance, health, readiness, daily status, and weekly digest
- V1 write posture: workers propose library updates; tooling does not
  automatically mutate library files from worker output

### Future Improvements

| Improvement | Summary | Dependencies | Important notes |
| --- | --- | --- | --- |
| Import helpers | Add dry-run helpers for PDFs, browser bookmarks, citation managers, and local notes that produce proposed `source_library.md`, `knowledge_index.md`, `claim_map.md`, and `library_update_log.md` rows. | Stable Markdown table contracts; source-location conventions; citation/provenance fields; clear file/browsing permissions. | Start proposal-only. Do not crawl or trust imported material automatically. Preserve manual `## Notes` sections. |
| Proposed-row inspection | Teach tooling to inspect proposed generated-table rows from `literature_extract` outputs, especially `worker_output.md`, and report whether they would validate before reviewer application. | A machine-readable proposal convention, such as fenced Markdown blocks or JSON; validator reuse; reviewer guidance. | This addresses the current dashboard residual risk: proposed update tasks are visible by `status.json`, but proposed rows are not deeply inspected yet. Keep this read-only. |
| Reviewed update apply command | Add a reviewed, explicit apply path that moves accepted proposed rows into generated library blocks and appends provenance to `library_update_log.md`. | Proposed-row inspection; task/review acceptance signal; library lock or transaction helper; post-write `library validate`. | Must be idempotent, preserve free-form notes, report rollback failures, and never upgrade trust without reviewer or human approval. |
| Automated extraction pipeline | Create bounded `literature_extract` tasks from selected sources/topics and produce structured library update proposals. | Import helpers or source-selection workflow; cost controls; browsing/network policy; task template hardening. | Automation should propose, not publish. Strong/high-stakes claims still need human approval. |
| Semantic freshness policies | Move beyond simple date staleness toward topic, claim-strength, trust-tier, and source-status freshness policy. | Dashboard telemetry; dogfood examples; configurable policy defaults; validator warning coverage. | Ship as warning-only first. Avoid global blockers for cold-start workspaces. |
| Stricter route-specific gates | Add stricter planning blocks only for routes that truly depend on library support, such as selected hypothesis or experiment paths. | Existing warning-only support-gap data; idea promotion behavior; human override policy; tests for cold-start discovery. | Never block all discovery or data-readiness work because the library is sparse or missing. |
| Evidence crosswalk | Add a crosswalk between `LIT-*` sources, `DS-*` data sources, accepted outputs, and claim/result artifacts. | Source governance contracts; accepted-output index; result acceptance metadata; stable reference fields. | The library remains background memory, not a substitute for audited data sources or final source-level citations. |
| Search or derived index | Build a rebuildable search, embedding, or RAG-friendly derived index over library rows and notes. | Stable parser/read model; local storage/privacy decision; rebuild command; stale-index detection. | Derived indexes must be disposable and regenerated from repo files. They must not own unique state. |
| Open-question task proposals | Turn selected `open_questions.md` rows into idea-catalog candidates or bounded task proposals. | Idea capture/promote workflow; dedupe checks; cost/readiness gates; planner prompt updates. | Proposal-only first. Avoid creating task spam from every open question. |
| Library quality metrics | Track coverage, stale rates, risky-source counts, unresolved refs, and update latency over time. | Dashboard output; metrics-history schema decision; dogfood thresholds. | Use metrics to calibrate future gates instead of guessing thresholds up front. |

### Suggested Sequencing

1. Proposed-row inspection for `literature_extract` outputs.
2. Reviewed update apply command with transaction and rollback tests.
3. Import helpers that produce the same proposal format.
4. Automated extraction pipeline using the proposal/apply contract.
5. Semantic freshness and quality metrics.
6. Stricter route-specific gates only after warning-only telemetry is useful.
7. Search, embeddings, or RAG-derived indexes once the row model is stable.

### Cross-Track Dependencies

- Idea Catalog: future library gates must stay aligned with `library_refs`,
  promotion preflight, duplicate handling, and task creation write mode.
- Data Foundations and source governance: library memory must not bypass
  `DS-*` source audit or result-acceptance citation requirements.
- Operator UX and dashboard work: richer dashboards should consume validator
  read models and should not invent separate write paths.
- Hypothesis Testing Framework: hypothesis and experiment routes may eventually
  consume stricter library support signals, but only after the warning-only
  behavior is proven.

### Open Decisions

- What proposal format should `literature_extract` workers use for generated
  library rows: fenced Markdown tables, JSON, or both?
- Should a future apply command require a human decision row, a reviewed task
  acceptance artifact, or either?
- Which freshness thresholds should vary by trust tier, claim strength, or
  topic criticality?
- Should imports preserve original source files in the repo, link to local
  paths, or only store external locations?
- What is the minimum useful search/index capability before embeddings or RAG
  add more complexity than value?
