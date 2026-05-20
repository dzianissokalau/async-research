# Deep Review Prompt - LLM Operator Skill Delivery

Repository: `/Users/dzianissokalau/Documents/projects/async-research`
Final branch: `codex/llm-operator-skill-delivered`
Roadmap path: `roadmaps/delivered_llm_operator_skill_roadmap.md`
Delivery log: `roadmaps/automation/llm_operator_skill/delivery_log.md`
State file: `roadmaps/automation/llm_operator_skill/delivery_state.json`
Review files: `roadmaps/automation/llm_operator_skill/reviews/`

## Verification Commands That Passed

- `git diff --check`
- `.venv/bin/python -m unittest tests.test_doc_references`
- `.venv/bin/python skills/async-research-operator/scripts/validate_skill_pack.py`
- `.venv/bin/python -m unittest tests.test_async_research_operator_skill`
- `.venv/bin/python -m unittest discover -s tests`
- `.venv/bin/async-research acceptance-suite`

## Review Task

Perform an independent deep review of the completed LLM Operator Skill delivery.
Inspect the final branch diff against the pre-delivery base branch before Phase
0. Review the roadmap, delivery log, state file, all phase review files, skill
package, validation scripts, tests, fixtures, and dogfood evidence.

Focus on whether the delivered `async-research-operator` skill can operate an
async-research workspace safely without overclaiming unsupported environments.
Specifically inspect:

- skill trigger behavior and description quality
- source-of-truth hierarchy for `research_ops/`, public CLI JSON, dashboard
  snapshots, user messages, and model memory
- guided setup safety, including install/network/write approval boundaries
- stop conditions for human gates, credentials, paid services, destructive
  actions, target-venue decisions, publication-readiness claims, broken tooling,
  and acceptance/readiness contradictions
- command recipes and whether they use public CLI commands with dry-run before
  write where supported
- role independence limits, especially same-agent review disclosure
- reporting and dashboard alignment rules
- validation fixtures, trigger evals, behavioral scenarios, and transcript
  evidence
- Codex dogfood evidence and its stated limitations
- provider-scope honesty for Codex, Claude Code, ChatGPT agent tools, web-only
  clients, API wrappers, and remote gateways
- whether remote/API write operation is correctly split into a future roadmap
  rather than implemented or implied inside this skill

## Expected Output

Return findings first, ordered by severity, with concrete file and line
references. Then list missing tests, residual risks, and a final verdict exactly
one of:

- `delivered`
- `needs-fix`
- `blocked`

Do not give credit for intent. Evaluate the delivered repository state.
