# Real Research Product Readiness Roadmap

Status: In Progress
Current phase: Phase 3 - Source governance semantics
Last updated: 2026-05-17
Next action: Lock or concurrency-protect source upserts and clarify source-use/check-claim semantics
Blocked by: None

Created: 2026-05-16

## Summary

This roadmap turns real dogfood evidence from the coffee-and-climate research
pilot into a product-readiness plan.

Source logs:

- `/Users/dzianissokalau/Documents/projects/open-researches/coffee/coffee-and-climate/FRAMEWORK_USAGE_ISSUES.md`
- `/Users/dzianissokalau/Documents/projects/open-researches/coffee/coffee-and-climate/HUMAN_FRAMEWORK_INTERACTION_LOG.md`
- `/Users/dzianissokalau/Documents/projects/open-researches/coffee/coffee-and-climate/LLM_FRAMEWORK_END_TO_END_LOG.md`

This is different from the post-review operator-trust roadmap. The earlier
roadmap handled external review findings and CLI ergonomics. This roadmap is
about what happened when a real human tried to use the framework and dashboard
to run an actual research project.

The underlying research engine is promising. The coffee pilot reached useful
outputs:

- data readiness and source governance for coffee country concentration
- accepted country concentration memo and reproducible dataset
- populated knowledge library and open questions
- climate exposure overlay
- price volatility source foundation, dataset, and event linkage
- firm concentration proxy track
- paper outline, evidence sections, figures, caveat audit, and internal paper
  draft

But the product did not yet feel ready. The framework carried the work, while
the human-facing experience still needed too much chat explanation, manual path
workaround, raw file inspection, and interpretation of hidden framework rules.

North star: a human should be able to use the dashboard as the primary control
surface for a real research project. They should understand where the research
is, why each task exists, where to inspect evidence, what was reviewed, what it
cost, what is blocked, and what should happen next.

## Core Diagnosis

The coffee pilot showed three layers of maturity:

1. Core workflow: strong enough to produce real research artifacts.
2. CLI guardrails: much better after the post-review roadmap, but still with
   source-governance and task-authoring sharp edges.
3. Product surface: not ready. The dashboard and generated surfaces do not yet
   explain the research journey, evidence, review quality, costs, and human
   choices clearly enough.

The next work should therefore prioritize product readiness over new research
subsystems.

## Main Weaknesses

- The dashboard did not give the human a clear research lifecycle map from
  topic to idea, task, evidence, synthesis, paper draft, and final polish.
- Human decision cards did not point clearly to the evidence artifact,
  aggregate review, source/data blockers, or exact decision vocabulary.
- Dashboard artifact links were fragile. Relative console paths produced bad
  `file://` URLs, and the Codex in-app browser blocked local-file navigation.
- A dashboard Resume action failed by duplicating the task path, so the intended
  human-control surface required a CLI workaround.
- The dashboard did not make idea-catalog and knowledge-library contents
  discoverable enough, even though the underlying files and CLI dashboards
  existed.
- Task rows did not explain why a task exists, what it contains, what it
  unblocks, or which input/output artifacts matter.
- Review and quality assurance were present in files, but not visible enough in
  the dashboard for the human to trust accepted outputs.
- Cost status was too unclear for the human to see what had been spent, what was
  estimated, and whether external/paid services were involved.
- `source upsert` can lose updates under parallel writes to the same Markdown
  register.
- Source gates treat every `DS-*` mention as accepted-evidence use, even when a
  task mentions a source only to reject it or mark it as context-only.
- `source check-claim` path semantics were inconsistent with other commands and
  confusing for paths relative to `research_ops`.
- `source check-claim` gave an unhelpful failure for LIT-only artifacts instead
  of explaining that DS source governance was not applicable and library
  validation was the right check.
- Manual task creation exposed schema sharp edges: `result: null` and
  `last_transition_reason: null` felt natural but failed validation.
- Generic artifacts have a suggestive claim-strength cap, but the cap was only
  discovered after review aggregation failed.
- Accepted final-paper workflow output did not guarantee publication-quality
  manuscript readiness. The framework needs a separate deliverable-maturity and
  editorial QA layer so `accepted` is not confused with `submission-ready`.

## Product Readiness Phases

| Phase | Focus | Scope | Exit Criteria |
| ---: | --- | --- | --- |
| 0 | Dashboard control-plane repair | Artifact viewer, robust path normalization, human-decision cards, source-blocker explanations, and decision action regression tests. | A human can inspect evidence and resolve a human gate from the dashboard without `file://` links or CLI path workarounds. |
| 1 | Research lifecycle map | Project-level roadmap/subway-map view, current phase, completed outputs, active task, next task, final deliverables, and station detail panels. | Complete - The dashboard answers where the research is, what is done, what is missing, and what happens next. |
| 2 | Task explainability and QA visibility | Task rationale, inputs, outputs, unblocks, review chain, claim strength, caveats, validation checks, and reviewer confidence. | Complete - Accepted tasks no longer look like unchecked agent output. |
| 3 | Source governance semantics | Register write locking, source-use intent, check-claim path normalization, LIT-only behavior, and source-blocker action guidance. | Source governance blocks are precise, explainable, and safe under concurrent operator actions. |
| 4 | Foundations and cost drilldowns | Idea catalog/library drilldowns, cost panels, budget/source/network indicators, and foundation contents. | Humans can inspect ideas, library contents, and task economics from the dashboard. |
| 5 | Task authoring and claim-strength guardrails | Minimal valid task templates, task creation helper, schema diagnostics, promoted-task preparation, and claim-cap warnings. | Manual or LLM-created tasks validate on first try, and claim-strength caps are visible before aggregation. |

## Prioritized Improvements

| Priority | Phase | Improvement | Description | Impact | Status |
| --- | ---: | --- | --- | --- | --- |
| P0 | 0 | Dashboard artifact viewer | Serve allowed workspace artifacts through local HTTP routes or an embedded viewer instead of relying on `file://` links. Resolve `ops_dir` to an absolute path before creating any artifact reference. | Lets humans inspect `worker_output.md`, reviews, data/library files, and outputs directly from the dashboard. Removes the most visible "dashboard looks usable but is not" failure. | Complete |
| P0 | 0 | Dashboard human-decision action path normalization | Normalize task refs once for decision actions. Accept absolute paths, project-root-relative paths, and `research_ops/tasks/TASK-*` refs without double-prefixing. Add a regression fixture for the coffee failure path. | Makes the dashboard a real human gate surface instead of forcing CLI workarounds. | Complete |
| P0 | 3 | Lock or concurrency-protect `source upsert` | Add register-level locking or optimistic read-version checks around `data_source_audit.md` writes. Report retry guidance when a concurrent write is detected. | Prevents silent loss of source-governance updates, a core data-integrity risk for file-backed state. | Open |
| P1 | 0 | Human decision evidence cards | Each human decision should show links/viewers for worker output, aggregate review, result acceptance, relevant source/data/library dashboards, exact decision options, target statuses, and consequence of each option. | The human can approve, pause, reject, or resume from evidence rather than from an opaque gate label. | Complete |
| P1 | 1 | Research lifecycle map | Add a project-level lifecycle view with stations for topic, discovery, idea, source/data readiness, literature, datasets, analysis, synthesis, draft, review, and final polish. | Makes the full research path legible and prevents accepted tasks from being mistaken for finished research. | Complete |
| P1 | 2 | Task rationale and contents panel | For each task, surface why it exists, what it contains, input artifacts, output artifacts, dependency chain, what it unblocks, and next recommended task. | Reduces the need for chat explanations about why tasks were created and how they fit together. | Complete |
| P1 | 2 | Review and QA visibility panel | Show reviewer role, decision, confidence, claim strength, caveats, evidence gaps, source-gate status, reproducibility checks, validation commands, and whether review was independent, same-agent, panel-based, or human-approved. | Makes quality assurance visible; improves trust in accepted outputs. | Complete |
| P1 | 3 | Source-use intent in claim gates | Distinguish `used_as_evidence`, `context_only`, `rejected_source`, `restricted_optional`, and similar source intents instead of treating every `DS-*` mention as accepted evidence. | Prevents useful source-audit discussion from blocking acceptance just because it mentions restricted sources. | Open |
| P1 | 3 | Normalize `source check-claim` artifact paths | Accept absolute, project-root-relative, and ops-relative artifact paths. Return resolved path diagnostics when missing. | Removes confusing false failures when operators pass paths the way other framework commands accept them. | Open |
| P1 | 3 | Clarify LIT-only source checks | When no `DS-*` refs are present but `LIT-*` refs are, explain that source-governance check is not applicable and recommend `library validate` or a library/source review path. | Avoids turning expected literature-only artifacts into scary source-governance failures. | Open |
| P2 | 4 | Idea and library dashboard drilldowns | Render idea catalog and library read models inside the web dashboard, including idea status, prioritization, source rows, topic coverage, claims, methods, open questions, risky/context-only sources, and validator findings. | Makes foundational research memory visible without raw file inspection. | Open |
| P2 | 4 | Cost and external-service panel | Show per-task estimated budget, actual spend, model/API/data costs, network/API use, and whether any paid or external service requires approval. | Lets humans understand task economics before approving or continuing work. | Open |
| P2 | 5 | Minimal valid task templates and task creation helper | Provide a helper or template for manual/LLM task creation with valid `status.json` placeholders, including non-null `result` and `last_transition_reason`. | Avoids schema failures for natural but invalid `null` values during task creation. | Open |
| P2 | 5 | Claim-strength cap preflight | Warn in `review submit`, `workflow worker-complete`, or `workflow advance --dry-run` when task type/artifact structure caps acceptable claim strength below the submitted review. | Makes claim-strength policy visible before aggregation fails. | Open |
| P2 | 0 | Source blocker action guidance | When source governance blocks acceptance, show which sources blocked, why, and available actions: approve source, accept for planning only, continue with caveats, or revise source audit. | Turns a good guardrail into an actionable workflow instead of a dead end. | Complete |
| P3 | 1 | Research roadmap artifact contract | Standardize an optional `research_ops/research_roadmap.md` or JSON read model so project-level roadmap state is not an ad hoc external file. | Lets dashboards and agents share a durable current-phase/current-task view. | Backlog |
| P3 | 4 | Dashboard vocabulary cleanup | Rename outcome columns from `PROJECT` to `TASK`, `OUTPUT`, or `ACCEPTED OUTPUT`, reserving project for the whole workspace. | Reduces conceptual confusion between workspace, idea, task, output, and paper. | Backlog |

## Phase 0 Implementation Notes

Phase 0 repairs the dashboard as a human control plane.

### Artifact Viewer

The dashboard should not rely on local `file://` links for core review
artifacts. Add an allowlisted local HTTP route that can render or download files
inside the selected `research_ops/` workspace.

Initial scope:

- `task.md`
- `status.json`
- `worker_output.md`
- `reviews/*.md`
- `review_panel/*.md`
- `review_panel/*.json`
- `artifacts/*`
- idea, data, source, library, accepted-memory, and roadmap Markdown files

Safety requirements:

- resolve `ops_dir` to an absolute canonical path at server startup
- reject path traversal and files outside the workspace
- show clear missing-file states
- preserve raw download/open-in-new-tab behavior for non-Markdown artifacts
- do not add write capability through the viewer

### Human Decision Cards

Human decision cards should be evidence-first.

Each card should show:

- task id and title
- reason human input is required
- worker output viewer link
- aggregate review viewer link when present
- result acceptance viewer link when present
- source/data/library blocker summaries when relevant
- exact available decision buttons
- target status for each decision
- one-line consequence of each choice
- equivalent CLI command for auditability

### Dashboard Action Path Normalization

Decision actions must normalize task references exactly once. The coffee pilot
failure path was:

```text
research_ops/tasks/research_ops/tasks/TASK-0001-data-readiness
```

Tests should cover:

- absolute task directory path
- project-root-relative `research_ops/tasks/TASK-*`
- ops-relative `tasks/TASK-*`
- bare task directory name when unambiguous
- malformed or escaping paths fail closed

## Phase 1 Implementation Notes

The dashboard needs a research lifecycle view, not just task status.

Minimum lifecycle stations:

- topic / research objective
- discovery inbox
- idea catalog
- source and data readiness
- knowledge library / literature
- dataset or evidence build
- analysis / hypothesis testing
- synthesis / memo
- draft
- final review and polish

Each station should show:

- objective
- status
- linked accepted outputs
- active task
- blockers
- next recommended task or command
- owner/runner
- artifact links

The UI can start as a dense vertical timeline before becoming a subway-map
visual. The important product requirement is legibility, not decoration.

## Phase 2 Implementation Notes

Tasks should explain themselves.

The task detail view should expose:

- why this task exists
- what question it answers
- what accepted output or idea triggered it
- input artifacts
- output artifacts
- what it unblocks
- source/data/library dependencies
- review status
- validation commands already run
- next recommended task

The review/QA panel should make acceptance evidence obvious:

- reviewer role
- decision
- confidence
- claim strength
- caveats
- evidence gaps
- source-gate result
- reproducibility checks
- result-acceptance scorecard
- whether review was independent, panel-based, same-agent, or human-approved

## Phase 3 Implementation Notes

Source governance needs to be both safer and more semantically precise.

Work items:

- lock or optimistic-concurrency protection for `source upsert`
- source-use intent metadata for claim checks
- artifact path normalization for `source check-claim`
- clearer LIT-only behavior
- source-blocker action guidance in CLI and dashboard surfaces

Acceptance:

- parallel source upserts cannot silently lose updates
- artifacts can mention restricted sources as rejected/context-only without
  automatically blocking accepted evidence
- ops-relative artifact paths resolve consistently
- LIT-only artifacts recommend library validation instead of looking like
  broken source-governance state

## Phase 4 Implementation Notes

Foundation dashboards should expose contents, not only counts.

Add dashboard drilldowns for:

- idea catalog records, prioritization, blockers, and promoted task links
- library sources, topic coverage, claims, methods, open questions, risky or
  context-only sources, and validator findings
- cost summary by task, role, model/provider when available, external API/data
  costs, and explicit approval requirements

## Phase 5 Implementation Notes

Manual and LLM-created tasks should validate without hidden schema knowledge.

Work items:

- task creation helper or minimal valid status template
- better schema diagnostics for common null-field mistakes
- promoted-task preparation action if any gap remains after idea promotion
- claim-strength cap preflight before review aggregation

Acceptance:

- a new task can be created from a public template/helper and pass
  `workflow check` on first try
- review claim strength is warned/capped before aggregation fails
- task templates explain generic-artifact claim caps

## Integration With Existing Roadmaps

- [Post-Review Operator Trust And Workflow Roadmap](./delivered_post_review_operator_trust_roadmap.md)
  delivered most CLI ergonomics that external reviews requested. This roadmap
  takes over the active product-readiness work from real dogfood.
- [Dashboard Delivery Roadmap](./delivered_dashboard_delivery_roadmap.md)
  delivered the initial local console. This roadmap hardens it into a primary
  human control plane.
- [Deliverable Maturity And Editorial QA Roadmap](./not_started_deliverable_maturity_editorial_qa_roadmap.md)
  owns the semantic distinction between task acceptance, internal draft
  acceptance, shareable readiness, working-paper readiness, and
  submission-ready manuscript quality.
- [Future Improvements Backlog](./not_started_future_improvements_backlog_roadmap.md)
  remains the place for broader V2 apply paths that are not directly blocking
  real research usability.
- Release-trust work should wait until Phases 0-5 remove the early-alpha feel
  observed in the coffee pilot.

## Verification Plan

Every implementation slice should run:

```bash
.venv/bin/python -m unittest tests.test_doc_references
.venv/bin/python -m unittest discover -s tests
.venv/bin/async-research acceptance-suite
```

Dashboard slices should also include:

- targeted console snapshot/action tests
- local HTTP smoke test when server behavior changes
- browser or static-resource checks when the UI changes
- at least one coffee-pilot-inspired fixture for the bug being fixed

## Open Decisions

- Should the artifact viewer render Markdown directly or show raw text first?
- Should the research lifecycle map be derived entirely from task state, or
  should it have a durable `research_roadmap` artifact?
- What is the minimum source-use intent schema that avoids overfitting to the
  coffee pilot?
- Should cost visibility start as planned/actual ledger surfacing, or should it
  require richer model/API usage ingestion first?
- Should task creation be a public command, a template generator, or both?
