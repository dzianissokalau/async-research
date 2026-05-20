# LLM Operator Remote Gateway Roadmap

Status: Not Started
Current phase: Phase 0 - Gateway safety contract
Last updated: 2026-05-20
Next action: Decide whether a remote/API command gateway is worth building after Codex skill dogfood
Blocked by: Human approval to start remote/API gateway design

Created: 2026-05-20

## Summary

This roadmap is the follow-on track for any write-capable remote command gateway
or MCP surface for the `async-research-operator` skill. It exists because Phase
8 of the LLM Operator Skill roadmap deliberately keeps API wrappers and browser
agents read-only or advisory until a separate safety design exists.

The gateway, if built, must expose a small allowlist over public
`async-research` CLI commands instead of a general shell. It must make
capabilities, path boundaries, dry-run/write behavior, budget/network policy,
human approval gates, and audit logs explicit before any write path is exposed.

## Non-Goals

- Do not build a hosted service before Phase 0 is approved.
- Do not expose arbitrary shell commands through an API.
- Do not let web-only chat clients mutate a workspace through copied context.
- Do not weaken the skill's existing source-of-truth hierarchy or stop
  conditions.

## Phase 0 - Gateway Safety Contract

### Objective

Decide whether the repository should build a remote/API gateway at all, and if
so define the minimum safety contract before implementation.

### Scope

- capability manifest for supported providers and tools
- public CLI command allowlist
- workspace and path allowlists
- dry-run-before-write enforcement
- budget, network, credentials, and paid-service policy
- human approval gates for high-impact actions
- audit log shape and retention expectations
- failure behavior for missing tools, stale state, and acceptance/readiness
  contradictions

### Acceptance Criteria

- The gateway boundary is specific enough that implementation cannot become a
  general command runner by accident.
- Every write-capable action has a dry-run or explicit human-approval path.
- The design preserves `research_ops/` files and public CLI JSON as higher
  authority than model memory or remote chat context.
- The roadmap states which provider contexts are in scope for the first
  gateway slice.

### Verification

- Run `git diff --check`.
- Run `.venv/bin/python -m unittest tests.test_doc_references`.

