# Roles

Use role names to make the current operating mode explicit in reports.

## Initial Role Set

| Role | Allowed Focus | Boundary |
| --- | --- | --- |
| Status reporter | Inspect state and summarize next safe action. | No writes. |
| Planner | Propose tasks or setup steps through public commands. | No worker execution. |
| Worker | Execute one bounded task when authorized. | Cannot accept its own output. |
| Reviewer | Review task output and evidence. | Must disclose weak same-agent independence. |
| Critic | Challenge deliverable maturity. | Cannot claim publication readiness alone. |
| Synthesizer | Assemble accepted evidence. | Cannot bypass acceptance or deliverable gates. |
| Maintainer | Run validation, health, readiness, and surface checks. | No research-content decisions. |

## Autonomy Levels

- `read_only`: inspect and report only.
- `guided`: ask before writes; default for ambiguous operation requests.
- `bounded_autonomous`: run one safe task loop only after explicit request.
- `maintenance`: run validation and bookkeeping without changing research
  substance.

Phase 4 expands allowed files, max writes, and same-agent review limits.
