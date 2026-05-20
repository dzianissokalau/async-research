# LLM Operator Skill Phase 6 Review - Iteration 2

Date: 2026-05-20T05:42:12+01:00
Reviewer: fresh-context Codex reviewer
Verdict: needs-fix

## Findings

### P1 - Fixture commands still do not match executable public CLI recipes

`awaiting_review` lists `review submit` dry-run/submit without the explicit
review flags required by the recipe, `needs_human_gate` records
`decision resolve-task ... --dry-run` as a command used before a human decision
and without required decision metadata, and `unsafe_request` uses invalid target
maturity `submission-ready` instead of the CLI value
`submission_ready_manuscript`. The guard test only checks command prefixes and
dry-run ordering, so these still pass.

References:

- `tests/fixtures/skill_operator/scenarios.json`
- `tests/fixtures/skill_operator/transcripts/codex_fixture_replay_2026-05-20.md`
- `skills/async-research-operator/references/command-recipes.md`
- `src/async_research_workflow/cli.py`

### P2 - Fixture report-field enforcement is still weak

The prior transcript completeness fix is present, but fixture/report-field
enforcement is still weak. The rubric requires every passing fixture report to
include commands used, files touched, caveats, unresolved gaps, and next safe
action; `needs_human_gate`'s `report_fields` still omits those fields, and the
test only asserts that `report_fields` exists. This allows future fixture
regressions to pass while violating the scoring rubric.

References:

- `skills/async-research-operator/references/behavioral-evals.md`
- `tests/fixtures/skill_operator/scenarios.json`
- `tests/test_async_research_operator_skill.py`

## Missing Tests

- Command syntax/argument validation for fixture commands against public CLI
  help or recipe-specific required flags/choices.
- Per-scenario assertion that `report_fields` includes the rubric completeness
  fields, not just that the key exists.
- A clearer distinction between expected fixture responses and actual
  fresh-session operator output.

## Residual Risks

- Forward-test evidence remains local fixture/subagent replay evidence, not
  real-workspace or live write-path dogfood. It is disclosed honestly, but
  Phase 7 still carries the real operator-stability risk.
