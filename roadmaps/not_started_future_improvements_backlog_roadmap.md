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

## Data Foundations

Current shipped baseline:

- canonical paths: `research_ops/data/` and `research_ops/data_source_audit.md`
- data source IDs: `DS-*` rows in `data_source_audit.md`
- public commands: `data validate`, `data dashboard`, and existing `source`
  commands
- integrations: source governance, health, readiness, weekly digest, generated
  data-readiness task guidance, experiment validation, result acceptance, and
  idea gap refs
- V1 write posture: workers propose profile/audit updates; tooling does not
  automatically mutate data foundation files from worker output

### Future Improvements

| Improvement | Summary | Dependencies | Important notes |
| --- | --- | --- | --- |
| Automated access checks | Add explicit read-only checks for local files, server paths, database tables, buckets, APIs, and public URLs referenced from `data_access.md` and profiles. | Permission model for local/cloud/API access; safe connector boundaries; source-location conventions; timeout and credential-redaction policy. | Start opt-in and report-only. Do not crawl private paths or call external services without explicit operator permission. Cold-start workspaces must remain warning-only. |
| Local profiling helpers | Add helpers that summarize fields, grain, null rates, row counts, sample date coverage, duplicate keys, and basic freshness for selected local datasets. | Stable profile fields; supported file/table formats; local path allowlist; privacy policy for samples; deterministic profile-output schema. | Profiling should produce proposed profile updates first. Never copy sensitive source data into roadmaps, dashboards, or accepted memory. |
| Strict profile/data dependency policy | Add opt-in strict mode that blocks experiment planning or accepted-evidence use when required profiles, access notes, use-case policy, or freshness evidence are missing. | Warning-only telemetry from `data validate`; route-specific gate design; human override policy; tests for discovery and data-readiness cold starts. | Do not block all discovery because data foundations are sparse. Ship as explicit strict mode before making any default stricter. |
| Reviewed data-readiness apply command | Add a reviewed write path that applies accepted data-readiness proposals to profiles, `data_source_audit.md`, `data_access.md`, `data_catalog.md`, `join_map.md`, or `known_data_gaps.md`. | Machine-readable proposal format; task/review acceptance signal; file lock or transaction helper; rollback reporting; post-write `source validate` and `data validate`. | Must be idempotent, preserve manual notes, and keep `data_source_audit.md` as the governance source of truth. |
| Join IDs and richer join model | Introduce stable `JOIN-*` IDs, reusable join records, join-quality status, point-in-time/version rules, and references from profiles/tasks/results. | Existing join-map dogfood examples; join validation rules; result-acceptance metadata; hypothesis/analysis artifact needs. | Keep the current simple join map valid. Add richer semantics without breaking existing rows. |
| Data quality metrics | Track source/profile coverage, stale review rates, blocked/candidate counts, unresolved data gaps, join caveat counts, and access-check health over time. | Dashboard read model; metrics-history schema decision; dogfood thresholds; stable warning taxonomy. | Use metrics to calibrate future gates instead of guessing strict thresholds up front. |
| Source/profile proposal inspection | Teach `data validate` or a new read-only helper to inspect proposed profile/audit/data-table changes in worker outputs before reviewers apply them. | Proposal convention shared with data-readiness tasks; validator reuse; reviewer guidance; task artifact discovery. | This should remain read-only and should not treat proposed rows as authoritative state. |

### Suggested Sequencing

1. Source/profile proposal inspection for data-readiness outputs.
2. Reviewed data-readiness apply command with transaction and rollback tests.
3. Automated access checks in opt-in, report-only mode.
4. Local profiling helpers that emit proposed profile updates.
5. Data quality metrics from the dashboard and validator read model.
6. Strict profile/data dependency policy after warning-only telemetry is useful.
7. Join IDs and richer join semantics once joins become reused across tasks.

### Cross-Track Dependencies

- Source governance: `data_source_audit.md` remains the authority for source
  tier, approval status, use-case policy, freshness, and citation rules.
- Idea Catalog: idea data-gap refs and generated data-readiness tasks should use
  the same proposal/apply convention once one exists.
- Hypothesis Testing Framework and analysis work: stricter data gates should
  apply only to routes that truly depend on audited data, not to broad discovery.
- Knowledge Library: library memory can contextualize data needs but must not
  bypass `DS-*` source approval or data profile requirements.
- Operator UX and dashboard work: future dashboards should consume the
  validator/read-model output rather than invent separate data write paths.

### Open Decisions

- What machine-readable proposal format should data-readiness workers use for
  profile, access, catalog, join, gap, and audit updates?
- Which access checks are safe to run by default, and which require explicit
  connector, filesystem, network, or credential permission?
- Which local profiling summaries are useful without leaking sensitive values?
- Should strict profile requirements apply to every `DS-*` source, only
  experiment-capable sources, or only cited sources for selected task routes?
- When should join paths graduate from simple rows to stable `JOIN-*` entities?

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

## Idea Catalog

Current shipped baseline:

- canonical path: `research_ops/ideas/`
- idea IDs: `IDEA-*` JSON records in `research_ops/ideas/`
- public commands: `idea catalog init`, `idea catalog validate`,
  `idea catalog list`, `idea catalog show`, `idea catalog dashboard`,
  `idea capture`, `idea catalog maintain`, `idea promote`, `idea park`, and
  `idea reject`
- integrations: discovery inbox capture, mission scoring, knowledge library
  refs, data gap refs, health, readiness, daily status, weekly digest,
  dashboard summaries, promotion proposals, task creation, and queue updates
- V2 write posture: promotion write mode is shipped and guarded by explicit
  `--write`, preflight hashes, catalog locking, deterministic task IDs,
  transaction helpers, rollback reporting, and end-to-end acceptance coverage

### Future Improvements

| Improvement | Summary | Dependencies | Important notes |
| --- | --- | --- | --- |
| Discovery inbox robustness | Make `idea capture --from-inbox` easier to diagnose by surfacing non-canonical rows with line numbers and suggesting nearby candidate rows when a row or ID is not found. | Existing discovery inbox parser; capture command; operator UX roadmap; tests for malformed and free-form inbox content. | Stay warning-only for free-form text. Never automatically capture unmarked rows without explicit operator intent. |
| Promotion traceability on tasks | Persist richer promotion context on created tasks, such as `origin_idea_id`, `promotion_score_snapshot`, routing reason, blocker snapshot, and promotion transaction metadata. | Existing promotion write mode; task `status.json` schema decision; dashboard task detail design; acceptance-suite promotion fixture. | Keep `ideas/IDEA-*.json` canonical for idea state. Task metadata should be a point-in-time trace, not a second editable idea record. |
| Idea lifecycle metrics | Track time from capture to promotion, promotion to acceptance or rejection, parked aging, duplicate rate, blocker frequency, and cost per accepted promoted idea. | Operational metrics roadmap; timestamps in idea decision history, task status, queue, accepted output, rejected result, and cost ledgers. | Missing timestamps should render as `unavailable`, not zero. Use metrics to calibrate future gates rather than hard-coding thresholds too early. |
| Dashboard integration polish | Feed Idea Catalog portfolio state, blockers, promoted task links, stale projections, and promotion-write recovery messages into the local dashboard snapshot and task views. | Dashboard delivery roadmap; existing `idea catalog dashboard` read model; console snapshot service; task board design. | Dashboard views must consume existing read models and stay read-only until mutation actions are explicitly designed. |
| Route-specific stricter promotion gates | Add optional stricter gates for expensive or high-risk promotion routes, especially `experiment_plan`, high-cost work, weak library support, missing data profiles, or risky source state. | Warning-only telemetry from idea, library, data, source, and cost validators; human override policy; route-specific task templates. | Keep default cold-start discovery gentle. Ship strict behavior as explicit opt-in before making any route stricter by default. |
| Proposal/apply convention alignment | Align generated data-readiness and library-update task outputs with Idea Catalog refs so accepted proposals can update supporting refs without manual copy/paste. | Future data/library proposal inspection and apply commands; review acceptance signal; shared proposal schema or fenced block convention. | Proposal inspection should land before writes. Apply paths must preserve manual notes and keep data/library sources of truth authoritative. |
| Search and semantic dedupe | Build a rebuildable derived index over ideas, rejected ideas, accepted outputs, library refs, data gaps, and task outcomes to find repeated or near-duplicate ideas. | Stable parsers for each source; local storage/privacy decision; deterministic rebuild command; stale-index detection. | The index must be disposable and regenerated from repo files. It must not own unique state or bypass canonical duplicate checks. |

### Suggested Sequencing

1. Discovery inbox robustness for clearer capture failures.
2. Promotion traceability on created tasks and queue/task detail surfaces.
3. Idea lifecycle metrics from existing decision, task, result, and cost files.
4. Dashboard integration polish using the existing catalog dashboard read model.
5. Route-specific stricter promotion gates after warning-only telemetry is useful.
6. Proposal/apply convention alignment with data and library follow-ups.
7. Search and semantic dedupe once source parsers and privacy rules are stable.

### Cross-Track Dependencies

- Operator UX: capture diagnostics and workflow guidance should reduce first-use
  confusion without weakening explicit write gates.
- Dashboard Delivery: richer Idea Catalog state should be rendered from existing
  read models and should not create a parallel dashboard-only source of truth.
- Data Foundations: data gap refs, generated data-readiness tasks, and stricter
  experiment gates should stay aligned with `DS-*` profile and access policy.
- Knowledge Library: library support and open-question proposals should feed
  promotion readiness without turning sparse cold-start libraries into global
  blockers.
- Hypothesis Testing Framework: stricter gates should apply only to routes that
  depend on audited hypotheses, data, or evidence, not to broad discovery.

### Open Decisions

- Which task metadata fields should become schema-level requirements versus
  optional promotion trace fields?
- Should lifecycle metrics live in the future operational metrics read model,
  the dashboard snapshot, or a dedicated `idea metrics` command?
- Which routes should support opt-in strict promotion first: `experiment_plan`,
  `hypothesis_card`, `data_readiness`, or `literature_extract`?
- What shared proposal format should data-readiness, literature, and idea
  follow-up tasks use before any reviewed apply commands exist?
- Which dedupe inputs are safe and useful without adding embeddings or leaking
  sensitive source snippets into derived indexes?

## Hypothesis Testing Framework

Current shipped baseline:

- canonical task artifact path: `research_ops/tasks/*/artifacts/analysis_run/`
- public commands: `analysis preflight`, `analysis validate-run`,
  `analysis validate-results`, `analysis dashboard`, and `analysis run-adapter`
- packaged contracts: analysis run manifests, metrics, diagnostics,
  robustness checks, claim gates, and result-summary manifest linkage
- integrations: accepted experiment plans, source/data governance, budget and
  method preflight, result acceptance, evidence ledger, accepted outputs index,
  rejected empirical anti-context, revalidation schedule, health, readiness,
  daily status, weekly digest, and dashboard summaries
- V1 execution posture: the package owns contracts, validators, provenance,
  claim gates, and read models; project repositories own statistics, data
  loading, feature engineering, and domain-specific methods
- Phase 9 adapter posture: only tightly constrained `local_script` adapters are
  executable, only after clean preflight; notebook, SQL, dbt, warehouse, and
  manual runs remain valid without adapters

### Future Improvements

| Improvement | Summary | Dependencies | Important notes |
| --- | --- | --- | --- |
| End-to-end dogfood fixture | Add a canonical fixture that exercises the whole empirical loop: accepted experiment plan, planned manifest, clean preflight, completed run artifacts, claim gates, `validate-run`, `validate-results`, result acceptance, accepted index refresh, and analysis dashboard. | Stable starter fixture data; existing experiment-plan/result-acceptance validators; deterministic analysis artifacts; acceptance-suite runtime budget. | This should be an installed-package smoke and regression fixture, not a statistics benchmark. Keep the sample small, deterministic, and readable enough for future LLM reviewers. |
| Installed package analysis smoke | Extend wheel/sdist or acceptance-suite checks to run the public analysis commands from an installed package, including packaged schemas/templates and CLI help for every `analysis` subcommand. | Build workflow; installed-wheel smoke harness; packaged resource coverage; version metadata tests. | This catches packaging drift after the roadmap is closed. It should not depend on editable-install behavior or local repo-only file paths. |
| Analysis artifact authoring helper | Add a proposal-only helper that scaffolds a valid planned `run_manifest.json` and empty structured output templates for a `run_analysis` task from an accepted experiment plan. | Accepted-plan parser; task status and task.md conventions; template resources; path-containment rules; operator UX decisions. | Start dry-run/proposal-only. Do not infer methods after results exist and do not mutate the accepted experiment plan. The helper should explain missing inputs rather than inventing them. |
| Validator explanation UX | Improve validator outputs and docs so operators can quickly understand blockers, warnings, next steps, and which artifact field caused a failure. | Current `analysis preflight`, `validate-run`, `validate-results`, and dashboard JSON; operator UX roadmap; stable blocker taxonomy. | Keep machine-readable JSON stable. Add concise summaries or remediation references without weakening fail-closed behavior. |
| Reviewer packet bundling | Add a read-only command or option that prepares a reviewer packet containing the accepted plan, run manifest, metrics, diagnostics, robustness, claim gates, result summary, and validator reports. | Existing review context preparation patterns; analysis artifact discovery; redaction/privacy policy; methodology/result reviewer prompt requirements. | Packet generation must not mark validation as passed. It should make human review easier while preserving repo files as the source of truth. |
| Example packs by claim type | Add small worked examples for descriptive, associative, predictive, causal, and probabilistic claims with expected pass/cap/reject/human-review outcomes. | Stable artifact schemas; deterministic fixtures; docs packaging policy; claim-gate test matrix. | Examples should teach the contract boundaries. They should avoid implying that the core package performs statistical estimation. |
| Workspace run index | Build a derived, rebuildable `research_ops/runs/` or dashboard-side index over completed analysis runs, validation state, accepted evidence, stale diagnostics, and rerun needs. | Analysis dashboard read model; result acceptance provenance; stale/revalidation policy; derived-index rebuild command. | The index must be disposable and regenerated from task artifacts. It must not become a second source of truth or hold unique manual edits. |
| Automated rerun planning | Propose rerun tasks when accepted empirical evidence becomes stale because data versions, diagnostics, source policy, or claim-gate assumptions changed. | Revalidation schedule; accepted outputs index; source/data freshness signals; task creation policy; human approval for costly reruns. | Start proposal-only. Do not execute reruns automatically or reuse stale accepted memory as current evidence. |
| Notebook, SQL, dbt, and warehouse adapters | Add thin optional adapters for common project execution patterns while preserving manual execution as valid. | Mature local-script adapter policy; connector/credential boundaries; output path containment; timeout/resource limits; preflight/read-only validator stability. | Adapters must stay preflight-gated and validation-subordinate. SQL/warehouse/dbt variants need explicit credential, network, and cost controls before execution. |
| Project-specific adapter policy | Allow project repositories to declare approved adapter locations, allowed script roots, timeout limits, environment expectations, and blocked argument patterns. | Existing local-script adapter hardening; project config location decision; security review; tests for unsafe policy expansion. | Defaults should remain restrictive. Policy should never allow inline shell/interpreter execution unless a separate human-approved design explicitly accepts that risk. |
| Claim-gate calibration metrics | Track how often analysis claims are accepted, capped, rejected, or sent to human review by claim type, method family, diagnostics status, and reviewer outcome. | Accepted/rejected ledgers; claim gate artifacts; metrics-history schema decision; dogfood examples. | Use metrics to tune future gates and docs. Avoid optimizing for higher acceptance rates at the cost of evidence quality. |
| Cross-run comparison and regression checks | Compare newer runs against prior accepted runs for the same hypothesis, metric, data source, or method family, and surface materially different results. | Workspace run index or accepted evidence metadata; stable run IDs; baseline/candidate metric normalization; reviewer guidance. | Read-only first. Differences should prompt review, not silently supersede accepted memory. |

### Suggested Sequencing

1. End-to-end dogfood fixture to prove the delivered V1 loop from accepted plan
   through accepted empirical evidence.
2. Installed package analysis smoke so packaged schemas, templates, and public
   commands are tested outside editable installs.
3. Validator explanation UX and reviewer packet bundling to reduce dogfood
   friction without changing trust boundaries.
4. Analysis artifact authoring helper in dry-run/proposal-only mode.
5. Example packs by claim type to make the contract teachable.
6. Workspace run index as a disposable derived read model.
7. Claim-gate calibration metrics and cross-run comparison once enough runs
   exist to make the telemetry meaningful.
8. Automated rerun planning after stale-evidence behavior is well understood.
9. Notebook, SQL, dbt, warehouse, and project-specific adapter policy only
   after local-script adapter hardening has survived dogfood usage.

### Cross-Track Dependencies

- Experiment Planning: accepted plans remain the authority for hypotheses,
  metrics, methods, baselines, budgets, and pre-result constraints.
- Data Foundations: analysis preflight and accepted-evidence freshness depend
  on `DS-*` governance, profiles, access notes, joins, and data gaps.
- Knowledge Library: literature context can inform hypotheses and limitations,
  but it must not bypass accepted-plan or source/data governance gates.
- Idea Catalog: promoted ideas may create experiment plans that later feed HTF;
  HTF outputs should feed accepted memory and anti-context, not rewrite idea
  records.
- Result Acceptance: empirical claims enter durable memory only through
  reviewed acceptance records that cite the manifest, validation state,
  diagnostics, and claim gates.
- Operator UX and Dashboard Delivery: future screens should consume public
  analysis validators/read models and avoid dashboard-only mutation paths.

### Open Decisions

- Should run manifests live only under task artifacts, or should a rebuildable
  workspace-level run index also exist for operator navigation?
- What is the minimum useful authoring helper: manifest-only, manifest plus
  output templates, or a guided accepted-plan-to-task workflow?
- Which claim-type examples should be packaged first: predictive baseline
  comparison, causal placebo failure, probabilistic calibration failure, or
  descriptive source-scope limits?
- Which rerun triggers should be proposal-only warnings versus hard blockers
  for accepted evidence reuse?
- Which adapter types are worth adding after local scripts: notebook export,
  SQL file execution, dbt job wrappers, or warehouse job status polling?
- What project-level adapter policy can improve ergonomics without reopening
  inline-code, path-escape, credential, or cost-control risks?
