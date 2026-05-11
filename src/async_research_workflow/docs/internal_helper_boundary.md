# Internal Helper Boundary

Created: 2026-05-06

`async-research` is the public user interface for supported workflow
operations. Direct `python -m async_research_workflow.scripts.<module>` calls
are reserved for advanced/internal helpers when the docs explicitly label that
use.

This boundary keeps the alpha CLI small while preserving low-level tools for
prompts, recovery procedures, and package maintainers.

## Permanent Internal Helpers

| Helper | Public alternative | Why it stays internal |
| --- | --- | --- |
| `validate_json_artifact` | Artifact-specific gates such as `async-research schema-check`, `async-research exploration validate`, `async-research idea validate`, `async-research experiment validate`, and `async-research result-acceptance`. | It is a generic schema primitive, not an operator workflow. |
| `validate_transition` | Workflow commands that move state, such as `async-research decision resolve-task`, `async-research revision request`, and `async-research review aggregate`. | It validates one low-level state-machine rule after a status write. |
| `validate_mission_policy` | `async-research idea score` for normal idea scoring. | Scheduled prompts may validate policy before scoring, but operators should not need a standalone policy command in the common loop. |
| `task_lock` | Worker prompts and scheduler wrappers. | It is an atomic locking primitive for agents, not a human workflow command. |
| `recover_status_json` | The operational readiness runbook recovery path. | Recovery is intentionally explicit and human-supervised because it rewrites broken task state. |
| `review_template` | Public `async-research review draft` and `async-research review submit` wrappers. | It is a low-level template generator; operators should use the public review commands. |
| `framework_version_calibration` | `async-research metrics summarize` and `async-research decision summarize` for public summaries. | Monthly framework calibration is an advanced maintenance report. |
| `escalate_review_tier` | `async-research escalation evaluate` for human-gate escalation checks. | Dynamic review-tier escalation mutates review policy and should remain a reviewer/internal helper until a broader public design exists. |
| `metrics_history init` | `async-research init`. | Workspace initialization already creates metrics baseline/history files transactionally. |
| `metrics_history append-snapshot --period weekly` | `async-research metrics append` for default snapshots. | The weekly-period/internal options are used by scheduled synthesis prompts and are not part of the public alpha contract. |
| `decision_log` | `async-research decision ...`. | Library-only parser module behind the public decision group. |
| `version_metadata` | Public workflow commands that preserve prompt/framework metadata. | Library-only defaults module used by status-writing helpers. |

## Rules For Docs And Agents

- Use `async-research` commands wherever a public wrapper exists.
- Keep direct helper invocations only in advanced/internal protocols, prompts,
  and recovery runbooks.
- Label direct helper invocations as advanced/internal so LLM implementers do
  not promote them by accident.
- Do not add public CLI names for the helpers above unless a later roadmap
  explicitly changes this policy.
- Keep helper behavior fail-closed: malformed state, unsafe transitions, stale
  governance, and lock conflicts should halt or route to human review.
