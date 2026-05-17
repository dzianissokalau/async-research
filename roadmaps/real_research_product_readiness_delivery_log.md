# Real Research Product Readiness Delivery Log

Status: Phase 0 delivered; ready for Phase 1
Roadmap: `roadmaps/in_progress_real_research_product_readiness_roadmap.md`
Automation template: `roadmaps/codex_phase_gated_delivery_automation_template.md`
State file: `roadmaps/real_research_product_readiness_delivery_state.json`
Review directory: `roadmaps/reviews`
Cadence: hourly
Model: GPT-5.5
Reasoning: xhigh

## Operating Policy

- Deliver one phase per branch: `codex/real-research-product-readiness-phase-<n>`.
- Work only on the current phase.
- Run a fresh review before marking a phase delivered.
- Auto-advance to the next phase only after a `delivered` review verdict.
- Stop after 3 review/fix iterations if the phase is still not delivered.
- Create one local commit when each phase is delivered.
- Keep all work local until explicitly told to push.
- Use the current local workspace and existing `.venv`.
- For Phase 0, render Markdown artifacts as formatted Markdown with raw/download fallback.

## Phase 0 - 2026-05-17

Status: not_started
Branch: `codex/real-research-product-readiness-phase-0`

### Scope

- Dashboard artifact viewer.
- Dashboard human-decision action path normalization.
- Human decision evidence cards.
- Source blocker action guidance.
- Decision action regression tests.

### Tests And Verification

- `.venv/bin/python -m unittest tests.test_doc_references`: not run
- `.venv/bin/python -m unittest discover -s tests`: not run
- `.venv/bin/async-research acceptance-suite`: not run
- Targeted dashboard snapshot/action/server/browser checks: not run

### Review

- Review file: pending
- Verdict: pending

### Residual Risks

- None recorded yet.

### Next Action

- Start Phase 0 delivery.

## Phase 0 - 2026-05-17 - Delivery Pass 1

Status: delivered
Branch: `codex/real-research-product-readiness-phase-0`

### Scope

- Dashboard artifact viewer with Markdown rendering and raw/download fallbacks.
- Human decision card evidence links, decision consequences, CLI command preview, and source blocker guidance.
- Human-decision action path normalization for absolute, project-root-relative, ops-relative, and bare task refs.
- Coffee pilot regression coverage for `research_ops/tasks/TASK-0001-data-readiness`.

### Changes

- Added a read-only `/artifacts/...` console route with allowlisted workspace paths and traversal rejection.
- Replaced `file://` dashboard links with local artifact viewer URLs.
- Added viewer metadata to task and delivered-project file links.
- Normalized task references before decision/task actions to avoid double-prefixing.
- Added tests for artifact rendering, missing/blocked artifact states, path normalization, static route usage, and automation roadmap doc exceptions.

### Tests And Verification

- `.venv/bin/python -m unittest tests.test_console_server tests.test_console_actions tests.test_console_snapshot tests.test_console_outcomes tests.test_packaged_resources`: passed
- `.venv/bin/python -m unittest tests.test_doc_references`: passed
- `.venv/bin/python -m unittest discover -s tests`: passed, 620 tests
- `.venv/bin/async-research acceptance-suite`: passed, 14 checks

### Review

- Review file: `roadmaps/reviews/real-research-product-readiness-phase-0-review-iteration-1.md`
- Verdict: delivered

### Residual Risks

- Same-context review was used because sub-agent delegation was not explicitly requested.

### Next Action

- Next automation run should start Phase 1 on `codex/real-research-product-readiness-phase-1`.
