# Framework Simplification Strategy Final Deep Review Prompt

Prepared at: 2026-05-25T14:54:20Z
Roadmap: `roadmaps/delivered_framework_simplification_strategy.md`
Branch: `codex/framework-simplification-strategy-phase-7`
Latest delivery commit: `4056e63 Deliver framework simplification phase 7`
Latest completion-check commit: `cc6231e Record framework simplification completion check`

Use this prompt with a fresh LLM/reviewer context before human merge review or
promotion.

## Prompt

Review the completed Framework Simplification Strategy delivery in this
repository.

Take a skeptical code-review and release-readiness stance. Lead with findings,
ordered by severity. Do not summarize first.

Treat these files as the source of truth:

- `roadmaps/delivered_framework_simplification_strategy.md`
- `roadmaps/automation/codex_phase_gated_delivery_automation_template.md`
- `roadmaps/automation/framework_simplification_strategy/delivery_state.json`
- `roadmaps/automation/framework_simplification_strategy/delivery_log.md`
- `roadmaps/automation/framework_simplification_strategy/phase_0_contract_freeze.md`
- `roadmaps/automation/framework_simplification_strategy/phase_4_proposal_engine_mapping.md`
- `roadmaps/automation/framework_simplification_strategy/phase_5_command_normalization_design.md`
- `roadmaps/automation/framework_simplification_strategy/phase_6_dependency_decision_record.md`
- `roadmaps/automation/framework_simplification_strategy/phase_7_test_consolidation.md`
- all files under `roadmaps/automation/framework_simplification_strategy/reviews/`

Review the delivered code and tests for every phase:

- Phase 0 contract freeze
- Phase 1 CLI runner seam
- Phase 2 init and starter-smoke services
- Phase 3 snapshot facets
- Phase 4 proposal engine consolidation
- Phase 5 command normalization design
- Phase 6 dependency decision record
- Phase 7 test consolidation

Inspect the git history and current branch state:

- `git status --short --branch`
- `git log --oneline --decorate --max-count=12`
- `git diff main...HEAD --stat`
- `git diff main...HEAD`

Evaluate:

- whether every roadmap phase acceptance criterion is actually satisfied;
- whether public CLI behavior, aliases, help shape, JSON envelopes, exit codes,
  workspace file formats, task state values, and documented side effects were
  preserved unless explicitly documented;
- whether fail-closed gates remain intact, especially source audit, freshness,
  claim verification, review aggregation, result acceptance, accepted-memory
  freshness, deliverable maturity, readiness, and cost gates;
- whether the HTTP console and public command families were preserved;
- whether no runtime dependency was added without the Phase 6 decision record;
- whether test consolidation in Phase 7 removed only redundant coverage with
  replacement contracts/goldens in place;
- whether delivery state, delivery log, review files, roadmap status, and
  branch history agree;
- whether verification evidence is sufficient for human merge review;
- whether the branch or worktree has promotion risks, unrelated changes, or
  uncommitted work;
- whether any docs or roadmap claims overstate delivery;
- whether any remaining risks should block human merge review.

Use the recorded verification evidence, but do not blindly trust it. If
possible, rerun at least:

- `git diff --check`
- `.venv/bin/python -m unittest tests.test_doc_references`
- `.venv/bin/python -m unittest discover -s tests`
- `.venv/bin/async-research acceptance-suite`

Output:

- Findings ordered by severity with file and line references.
- Missing or weak tests.
- State/log/review consistency issues.
- Verification gaps.
- Branch and promotion risks.
- Explicit unresolved risks.
- Verdict exactly one of:
  - `ready-for-human-merge-review`
  - `needs-fix-before-human-review`
  - `blocked`

Evaluate delivered behavior only. Do not give credit for intent.
