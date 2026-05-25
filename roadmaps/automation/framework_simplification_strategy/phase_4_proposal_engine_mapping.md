# Phase 4 Proposal Engine Mapping

Status: Delivered with Phase 4
Created: 2026-05-25

## Scope

This map identifies the proposal mechanics that are common enough to share now,
and the surface-specific behavior that should stay close to each proposal flow.
The goal is a smaller internal write spine without changing public CLI behavior,
JSON envelopes, exit codes, workspace file names, or task states.

## Flow Inventory

| Flow | Public entrypoints | Current shared mechanics | Surface-specific behavior |
| --- | --- | --- | --- |
| Foundation proposal parsing | `foundation-proposals` script family and data/library inspection callers | `foundation_update_proposal_v1` envelope parsing, JSON/Markdown discovery, duplicate proposal diagnostics | Operation vocabulary, target path rules, row id validation |
| Data proposal inspection/apply | `async-research data inspect-proposals`, `async-research data apply-proposals` | Proposal discovery, preflight hash, accepted task/artifact proof, foundation lock, target-file snapshot, rollback, post-write validation, JSON reporting | Data source audit register, data profiles, data foundation Markdown tables, source-register lock |
| Library proposal inspection/apply | `async-research library inspect-proposals`, `async-research library apply-proposals` | Proposal discovery, preflight hash, accepted task/artifact proof, foundation lock, target-file snapshot, rollback, post-write validation, JSON reporting | Knowledge library table specs, source refs, claim/method/open-question validation, library update log append |
| Idea promotion proposal write | `async-research idea promote` | Stable preflight hash, catalog lock, idempotency/recovery checks, file snapshots, rollback, post-write validation, JSON reporting | Task transaction staging, queue/inbox writes, human override policy, task identity reservation, catalog projection rendering |
| Idea catalog capture/maintain/status/resolve writes | `async-research idea capture`, `idea catalog maintain`, status and resolution commands | Catalog lock, file snapshots, rollback or recovery payloads, post-write validation | Command-specific catalog mutations and decision-log behavior |

## Shared Engine Extracted

The new `async_research_workflow.proposals.engine` module owns these common
standard-library-only primitives:

- stable JSON hashing for preflight contracts;
- file SHA-256 helpers for proposal documents and target files;
- directory lock acquisition/release with caller-supplied failure payloads;
- file snapshot capture with optional fail-closed or best-effort read behavior;
- file snapshot restore with caller-supplied action names;
- atomic byte writes for rollback-friendly restore helpers.

## First Migration

The first concrete engine users are:

- data foundation apply, through `foundation_proposal_apply`;
- library foundation apply, through `foundation_proposal_apply`;
- idea promotion preflight and snapshot/restore wrappers, without moving the
  task-transaction-specific write body.

Data and library therefore share one common engine spine for preflight hashing,
foundation lock handling, target snapshots, and rollback while keeping their
surface-specific inspection and validation modules unchanged.

## Preserved Contracts

- `data apply-proposals` remains dry-run by default and still requires
  `--write --preflight-hash` for mutation.
- `library apply-proposals` keeps the same write envelope, warning semantics,
  and post-write validation handling.
- Accepted source-task or accepted-artifact proof remains fail-closed.
- Existing source-register locking for data proposals remains layered on top of
  the foundation apply lock.
- Idea promotion keeps its catalog lock, idempotency recovery, task transaction,
  and human override policy unchanged.
- Manual notes in Markdown tables and catalog files remain preserved by the
  existing surface writers.

## Deferred Boundaries

- Do not force idea capture, maintenance, status, and resolution writes into the
  foundation apply shape; they do not use accepted-task proof and have different
  transaction semantics.
- Do not add runtime dependencies for schema, lock, or CLI behavior.
- Do not collapse data and library inspection validators; their row identity and
  source-reference rules are intentionally different.
