# Real Research Product Readiness Review Fix Log

Status: Delivered
Roadmap: `roadmaps/delivered_real_research_product_readiness_roadmap.md`
Independent review: `/Users/dzianissokalau/Downloads/async-research-phase-0-5-independent-review.md`
Base branch: `codex/real-research-product-readiness-review`
Fix branch: `codex/real-research-product-readiness-review-fixes`
State file: `roadmaps/automation/real_research_product_readiness/review_fix_state.json`
Review directory: `roadmaps/automation/real_research_product_readiness/reviews`
Cadence: hourly
Model: GPT-5.5
Reasoning: xhigh

## Operating Policy

- Fix the independent review findings only; do not expand roadmap scope.
- Preserve unrelated worktree changes.
- Prioritize the two P1 findings before lower-severity work.
- Add regression tests for every accepted finding.
- Run full roadmap verification before declaring the fix delivered.
- Run a fresh skeptical review after fixes.
- Stop after 3 review/fix iterations if findings remain.
- Create one local commit when the fix set is delivered.
- Keep work local until explicitly told to push.

## Fix Pass 1 - 2026-05-17

Status: delivered
Branch: `codex/real-research-product-readiness-review-fixes`

### Scope

- P1-A: prevent executable same-origin artifact viewer content and add security headers.
- P1-B: prevent prose source-use intent inference from silently weakening source governance.
- P2-A: lock `source init --force`.
- P2-C: ensure broad task artifact allowlist does not produce executable inline responses.
- P2-D: generalize dashboard task path normalization for non-`research_ops` workspace names.
- P2-B, P2-E, and P3 items: fix only if low-risk after the above are complete.

### Changes

- Forced non-Markdown artifact default/raw responses to `application/octet-stream`, including nested task HTML/SVG artifacts.
- Added artifact-route security headers: `X-Content-Type-Options: nosniff`, restrictive `Content-Security-Policy`, and `X-Frame-Options: DENY`.
- Changed source-use prose inference to fail safe: casual prose no longer downgrades `DS-*` refs; explicit tables and inline `source_use_intent:` metadata remain supported.
- Allowed later evidence references to upgrade weaker earlier source-use intent outside explicit table rows.
- Put `source init` writes, including `--force`, under the source-register lock.
- Normalized literal `research_ops/tasks/TASK-*` refs against custom-named workspace directories.
- Classified this review-fix log as a roadmap operational file so doc-reference checks do not require lifecycle roadmap prefixes for automation logs.

### Tests And Verification

- `.venv/bin/python -m unittest tests.test_console_server tests.test_console_actions tests.test_cli_audit_surface`: passed, 77 tests
- `.venv/bin/python -m unittest tests.test_doc_references`: passed, 12 tests
- `.venv/bin/python -m unittest discover -s tests`: passed, 638 tests
- `.venv/bin/async-research acceptance-suite`: passed, 14 checks

### Review

- Review file: `roadmaps/automation/real_research_product_readiness/reviews/real-research-product-readiness-review-fixes-review-iteration-1.md`
- Verdict: delivered

### Residual Risks

- P2-B stale-lock rotation and P2-E HEAD optimization were not changed; both remain lower-risk follow-ups outside the mandatory blocker slice.

### Next Action

- Local delivery commit created; keep the branch local until a human explicitly asks to push.
