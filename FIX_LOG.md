# Fix Log

This file tracks notable bug fixes and friction-point fixes that come from
workflow simulations, external reviews, and dogfooding. It is separate from
`CHANGELOG.md`: the changelog summarizes release-level changes, while this log
keeps operational context for why a fix was made and how it was verified.

## 2026-05-06 - Manus Workflow Simulation Fixes

Commit: `04dc736` (`Harden accepted memory extraction`)

Source: virtual workflow simulation with Manus.

### Fixed

| Area | Problem | Resolution | Verification |
| --- | --- | --- | --- |
| Accepted-memory `key_finding` extraction | `accepted update` could treat metadata lines such as `prompt_version: worker_v1.0` as the accepted finding when worker output started with metadata. | Accepted-output indexing now prefers structured result summaries and explicit status results, filters metadata-like lines, and falls back to meaningful Markdown content before task title/default text. | Added `test_accepted_update_ignores_worker_metadata_when_extracting_key_finding`; full test and CLI suites passed. |
| Accepted-memory follow-ups | Follow-ups from status JSON, review acceptance JSON, and worker Markdown could be duplicated, keep `TASK:` prefixes, or produce noisy accepted-memory rows. | Follow-ups are now normalized, deduplicated across all extraction sources, placeholder values are ignored, and the index stores cleaner semicolon-separated follow-up text. | Added `test_accepted_update_deduplicates_and_normalizes_followups`; full test and CLI suites passed. |
| Review aggregation state-machine friction | If a task stayed in `awaiting_review` while reviews existed, `review aggregate` failed with `invalid_transition` but did not explain the required intermediate review-start state. | `review aggregate` now keeps strict state validation but returns actionable JSON with `current_status`, `attempted_route`, `suggested_intermediate_status`, and `next_step` when the missing transition is the blocker. | Added `test_review_aggregate_explains_missing_review_state_transition`; full test and CLI suites passed. |

### Verification Run

- `.venv/bin/python -m unittest tests.test_workflow_regressions`
- `.venv/bin/python -m unittest discover -s tests`
- `.venv/bin/async-research acceptance-suite`
- `.venv/bin/async-research benchmark`
- `.venv/bin/async-research starter-smoke /private/tmp/async-research-manus-fix-generic --force`
- `.venv/bin/async-research starter-smoke /private/tmp/async-research-manus-fix-real-estate --template real-estate --force`
- `.venv/bin/python -m compileall src tests`
- `git diff --check`

### Notes

- The strict state machine remains intentional. The fix improves operator and
  agent guidance without weakening fail-closed transition validation.
- Editable install limitations and broader packaging/developer-loop polish were
  not part of this fix set and should be handled as a separate roadmap item if
  they remain painful.

## 2026-05-06 - Simulation UX Hardening

Commit: `Harden simulation workflow UX`

Source: follow-up end-to-end workflow simulation report.

### Fixed

| Area | Problem | Resolution | Verification |
| --- | --- | --- | --- |
| Review bundle scaffolding | `review prepare-context` created an empty expected reviewer output file, so `review install-context` failed until the operator knew to run the internal review template helper. | Reviewer bundles now seed the expected output file with a fenced JSON review scaffold. The scaffold defaults to `needs_human` so accidentally installing it fails closed rather than accepting evidence. | Added CLI regression assertions that prepared reviewer bundles contain the seeded JSON scaffold. |
| Review state-machine documentation | The README worked loop did not make the required `awaiting_review -> single_review/panel_review` review-start transition explicit. | The worked loop now documents the intermediate review-start status and explains the fail-closed aggregation guidance. | Covered by README/help regression checks and full test discovery. |
| Source upsert guidance | New `source upsert` rows could fail validation with generic missing-field errors even though aliases such as `--owner` and `--status` existed. | Public and script help now state the minimum fields for a new row. Validation failures for new rows include `required_for_new_source` and `next_step` while preserving the existing `audit_validation_failed` reason. | Added a public CLI regression for missing new-source fields. |
| Accepted-memory freshness consistency | `result_acceptance.json` could record accepted-memory freshness as `unspecified` while `accepted update` wrote the computed default freshness window to the global index. | Result acceptance now uses the same claim-type normalization, freshness-window defaults, and next-recheck calculation as the accepted-output index. | Added a regression proving data-readiness acceptance writes `source_data_readiness`, `90`, and the computed next recheck date. |
| Simulated-week work directory ergonomics | The public `simulate-week` wrapper did not expose `--work-dir`, and the simulation guard rejected any path containing a `research_ops` segment even when it was isolated from the source workspace. | `async-research simulate-week` now exposes `--work-dir` and `--keep-work-dir`. The isolation guard now rejects actual source/work overlap rather than directory names. | Added a regression proving isolated paths containing `research_ops` are allowed while overlapping paths are still blocked. |

### Verification Run

- `.venv/bin/python -m unittest tests.test_workflow_regressions`
- `.venv/bin/python -m unittest tests.test_cli_audit_surface tests.test_cli_help`
- `.venv/bin/python -m unittest discover -s tests`
- `.venv/bin/async-research acceptance-suite`
- `.venv/bin/async-research benchmark`
- `.venv/bin/async-research starter-smoke /private/tmp/async-research-simulation-ux-generic --force`
- `.venv/bin/async-research starter-smoke /private/tmp/async-research-simulation-ux-real-estate --template real-estate --force`
- `.venv/bin/async-research init /private/tmp/async-research-simulation-source/research_ops --force`
- `.venv/bin/async-research simulate-week /private/tmp/async-research-simulation-source/research_ops --work-dir /private/tmp/async-research-sim-work/research_ops/nested --keep-work-dir`
- `.venv/bin/python -m compileall src tests`
- `git diff --check`

### Notes

- Review aggregation and status transition validation remain strict by design.
  These fixes improve agent/operator ergonomics without allowing direct
  `awaiting_review -> accepted` transitions.
- The source upsert aliases remain backward-compatible. The change adds clearer
  guidance for creating new rows; it does not relax source-governance validation.
