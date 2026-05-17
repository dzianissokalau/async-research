# Real Research Product Readiness Review Fixes - Review Iteration 1

Review date: 2026-05-17
Branch: `codex/real-research-product-readiness-review-fixes`
Base: `codex/real-research-product-readiness-review`
Verdict: delivered

## Scope Reviewed

- P1-A artifact viewer executable content-type and missing security headers.
- P1-B source-use intent prose downgrade and first-intent-wins behavior.
- P2-A `source init --force` register-lock coverage.
- P2-C broad task artifact paths producing executable inline responses.
- P2-D project-root-style `research_ops/tasks/TASK-*` path normalization when the actual workspace directory is not named `research_ops`.

## Findings

No blocking findings remain for the mandatory review-fix scope.

## Checks

- Non-Markdown task artifacts now return `application/octet-stream` for default, raw, and download responses. The added regression covers nested HTML and SVG task artifacts and asserts neither `text/html` nor `image/svg+xml` is served.
- Artifact HTTP responses now get `X-Content-Type-Options: nosniff`, a restrictive `Content-Security-Policy`, and `X-Frame-Options: DENY`. Markdown rendering remains available, and the raw/download links still point at the existing routes.
- Source-use intent parsing no longer treats casual prose words such as `context` or `rejected` as non-evidence intent. Untagged prose DS refs default to `used_as_evidence`.
- Explicit Markdown source-use intent tables still mark non-evidence refs. Later non-table evidence mentions can upgrade weaker earlier intent to `used_as_evidence`.
- `source init --force` now fails under the same fresh source-register lock as `source upsert` and preserves the existing register while locked.
- Console task path normalization now treats a literal `research_ops/` prefix as the conventional project-root prefix, even when `ops_dir.name` is different.

## Verification

- `.venv/bin/python -m unittest tests.test_console_server tests.test_console_actions tests.test_cli_audit_surface`: passed, 77 tests.
- `.venv/bin/python -m unittest tests.test_doc_references`: passed, 12 tests.
- `.venv/bin/python -m unittest discover -s tests`: passed, 638 tests.
- `.venv/bin/async-research acceptance-suite`: passed, 14 checks.

## Residual Risks

- P2-B stale-lock rotation and P2-E HEAD-request optimization remain known lower-priority follow-ups. They were not required for this mandatory blocker fix set and were not changed.
- The artifact viewer still displays Markdown generated from untrusted content, but Markdown HTML is escaped and the route-level CSP prevents script execution.

