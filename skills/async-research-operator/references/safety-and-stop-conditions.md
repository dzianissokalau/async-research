# Safety And Stop Conditions

Use this reference whenever deciding whether to continue autonomously.

## Source-Of-Truth Hierarchy

1. `research_ops/` files.
2. Public `async-research` CLI JSON output.
3. Dashboard or console snapshot.
4. User messages.
5. Model memory.

When sources disagree, prefer the higher source and report the discrepancy. Do
not silently choose between conflicting acceptance, readiness, or dashboard
states.

## Mandatory Stops

- Destructive file or git operations.
- Public/private boundary ambiguity.
- Publishing, submission, release, or publication-readiness claims.
- Credentials, external accounts, paid API/cloud/data use, network installs,
  cloning, or fetching without approval.
- Human decision gates, source governance approval, missing target audience,
  deliverable maturity choice, target venue choice, or product direction.
- Required tests or validators cannot run.
- Required public CLI commands are missing.
- Task acceptance sources disagree.
- Dashboard state conflicts with file-backed state.
- Deliverable readiness checks fail, have not run, or disagree with reported
  maturity.

## Default Behavior

In `guided` mode, stop before writes and present the exact command that would be
run. In `bounded_autonomous` mode, still stop at every mandatory stop condition.
