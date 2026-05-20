# LLM Operator Skill Phase 6 Review - Iteration 1

Date: 2026-05-20T05:35:41+01:00
Reviewer: fresh-context Codex reviewer
Verdict: needs-fix

## Findings

### P1 - `needs_human_gate` replay misses required report fields

The `needs_human_gate` replay is marked `pass` while missing required
report-completeness fields. The rubric requires each passing fixture to include
commands used, files touched, caveats, unresolved gaps, and next safe action,
but this scenario only records evidence, files touched, stop condition, and
next safe action. The current test only checks those phrases globally across the
whole transcript, so this regression would pass.

References:

- `skills/async-research-operator/references/behavioral-evals.md`
- `tests/fixtures/skill_operator/transcripts/codex_fixture_replay_2026-05-20.md`
- `tests/test_async_research_operator_skill.py`

### P2 - `awaiting_review` fixture skips review-submit dry-run

The `awaiting_review` fixture omits the required dry-run before the
write-capable review submit path. The scenario lists
`async-research review submit <task>` directly, while the command recipe
requires `review submit ... --dry-run` before submit. The guard test only
requires human approval for write-capable commands, so it does not enforce
"dry-run before writes whenever supported."

References:

- `tests/fixtures/skill_operator/scenarios.json`
- `skills/async-research-operator/references/command-recipes.md`
- `tests/test_async_research_operator_skill.py`

## Missing Tests

- Per-scenario transcript scoring for all four behavioral gates instead of
  global substring checks.
- Fixture command-sequence validation against the recipes, including
  dry-run-before-write ordering.
- A clearer replay/eval artifact that distinguishes expected responses from
  actual fresh-session operator output.

## Residual Risks

- Forward-test evidence remains fixture/subagent replay evidence, not live LLM
  or real-workspace execution. It is honestly disclosed, but Phase 7 dogfood
  still carries the real operator-stability risk.
- JSON fixtures describe simulated states; they do not yet exercise full
  `research_ops/` directory fixtures end to end.
