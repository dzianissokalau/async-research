# Research Runtime Contract

Created: 2026-05-20

This contract defines the boundary for an integrated async-research runtime. It
is intentionally a Phase 0 contract: it names the adapter classes, permission
rules, evidence object fields, trace fields, and human gates that later phases
must implement. It does not add adapters, dependencies, network access, or new
task-state transitions.

## Runtime Boundary

Runtime adapters may:

- fetch, search, parse, compute, and summarize within an explicit task contract;
- emit runtime traces and evidence objects under `research_ops/`;
- produce worker-facing artifacts for review;
- report dry-run plans before performing any external or costly action.

Runtime adapters must not:

- move tasks between lifecycle states;
- mark evidence accepted;
- update result-acceptance, review, deliverable maturity, or accepted-memory
  ledgers directly;
- treat retrieved material as validated evidence merely because it was fetched;
- hide network calls, credential use, paid calls, or publication-sensitive
  decisions inside adapter defaults.

Workflow commands own task transitions. Review and result-acceptance commands
own acceptance decisions. Deliverable maturity commands own publication-readiness
gates. The dashboard and console remain visibility surfaces, not sources of
truth. Durable truth stays in repository files, with `research_ops/` artifacts
outranking chat history or model memory.

## Adapter Classes

The Phase 0 adapter taxonomy is stable enough for later schema and CLI work:

| Adapter type | Purpose | Default capability |
| --- | --- | --- |
| `web_search` | Query an allowed search provider or search endpoint. | Disabled unless network and source-class permissions are present. |
| `web_open` | Retrieve or snapshot a specific allowed web page. | Disabled unless network and domain/source permissions are present. |
| `file_search` | Search approved local files or package fixtures. | Read-only, bounded to allowed paths. |
| `file_fetch` | Read and snapshot approved local files. | Read-only, bounded to allowed paths. |
| `mcp_search` | Query an approved MCP/private-data index. | Disabled unless the task permits that connector and data boundary. |
| `mcp_fetch` | Fetch a specific approved MCP/private-data record. | Disabled unless the task permits that connector and record class. |
| `api_query` | Query a structured API or downloadable data endpoint. | Disabled unless the API, method, budget, and source policy are allowed. |
| `code_execute` | Run deterministic local analysis code over approved inputs. | Disabled unless command, cwd, inputs, outputs, and runtime limits are allowed. |

Phase 3 may add concrete adapters only inside this taxonomy unless a roadmap
update explicitly extends the contract.

## Phase 1 Runtime Artifact Locations

Phase 1 adds machine-readable ledgers and schemas without implementing live
adapters:

- `research_ops/runtime/traces.jsonl`
- `research_ops/runtime/evidence_objects.jsonl`
- `research_ops/runtime/snapshots/`
- `schemas/runtime_trace.schema.json`
- `schemas/runtime_evidence_object.schema.json`

Validate and inspect them with:

```bash
async-research runtime validate research_ops
async-research runtime summary research_ops
async-research runtime inspect-evidence research_ops EVID-000001
```

The validator checks required fields, task links, `research_ops/` path
boundaries, snapshot hashes, freshness metadata, costs, and permission basis.
Missing license or use-policy metadata produces a warning; malformed paths,
missing task links, and hash mismatches fail closed.

## Default Permission Posture

The runtime is read-only by default. Capability must be granted by the task
contract or by a human gate before execution.

Required defaults:

- Network access is disabled unless the task contract allows it.
- Credentials require an explicit human gate and must not be inferred from the
  environment.
- Paid calls require a budget, approval policy, and cost trace.
- Public claims require citation and claim-verification gates before acceptance.
- Unsafe, unclear, private, or restricted source use requires a human gate.
- Write access is limited to declared runtime artifacts under `research_ops/`.
- External actions must support dry-run reporting before execution where
  practical.
- Missing permission data fails closed.

Allowed runtime outputs do not bypass review. A worker may use runtime evidence
objects in draft output, but result acceptance still decides whether that output
becomes accepted memory.

## Evidence Object Contract

Every source, span, computed result, or retrieved artifact that may support a
claim must become an evidence object before it can be cited by later phases.
Phase 1 owns machine-readable schemas and validators; this section defines the
minimum fields those schemas must preserve.

| Field | Required meaning |
| --- | --- |
| `evidence_id` | Stable identifier unique within the workspace, such as `EVID-000001`. |
| `task_id` | Task that requested or produced the evidence. |
| `adapter_type` | One adapter type from the Phase 0 taxonomy. |
| `source_uri` | Canonical URI, path, API endpoint, fixture URI, or computation URI. |
| `source_title` | Human-readable source title or computed-artifact title. |
| `retrieved_at` | ISO-8601 timestamp for retrieval or computation. |
| `content_hash` | Hash of the snapshot or normalized content when available. |
| `snapshot_path` | Path under `research_ops/` for the immutable snapshot or artifact. |
| `span_refs` | Structured spans, rows, pages, sections, or computed-output ranges. |
| `license_or_use_policy` | License, usage policy, access terms, or explicit `unknown` warning state. |
| `freshness_status` | Freshness label and supporting timestamp/policy basis. |
| `cost` | Monetary, token, compute, or `0`/`unknown` cost record. |
| `permission_basis` | Task-contract field, source policy, or human decision that allowed retrieval. |

Evidence objects are not accepted evidence by themselves. They are normalized
inputs for claim verification, review, result acceptance, and eval construction.

## Runtime Trace Contract

Every adapter attempt must produce a trace row, including failed or blocked
attempts when an action was planned or requested. Phase 1 owns the ledger
locations and validators; this minimum trace shape is fixed for implementation.

| Field | Required meaning |
| --- | --- |
| `trace_id` | Stable identifier unique within the workspace, such as `TRACE-000001`. |
| `task_id` | Task that requested the action. |
| `tool_name` | Concrete adapter/tool implementation name. |
| `input_summary` | Redacted summary of request inputs and permission checks. |
| `output_summary` | Summary of returned data, blocked reason, or failure state. |
| `artifact_paths` | Snapshot, evidence, log, or computed-output paths under `research_ops/`. |
| `return_code` | Deterministic status code or symbolic status for blocked actions. |
| `duration_ms` | Runtime duration in milliseconds when measured. |
| `token_usage` | Token usage by model role/provider, or `null` when not applicable. |
| `cost` | Cost estimate or final cost for the action. |
| `error` | Structured error or `null`; must include fail-closed permission blockers. |

Trace rows are an audit ledger and an eval source. They are not a hidden state
machine and must not be the only place where a human decision is stored.

## Human Gates

The runtime must stop for a human decision when a requested action involves:

- credentials, private connectors, or unclear private/public data boundaries;
- paid services without an explicit budget and approval policy;
- live external services that are not allowed by the task contract;
- unsafe, prohibited, or ambiguous source-use terms;
- public or publication-oriented claims that lack citation/claim verification;
- target-venue, legal, compliance, medical, financial, or strategic product
  judgment beyond the roadmap contract;
- destructive file operations, broad refactors, or writes outside allowed paths.

Human decisions must be recorded in existing decision/human-gate surfaces rather
than in runtime traces alone.

## Dependency Posture

The core package remains standard-library first. Phase 0 chooses this posture:

- schemas, validators, CLI summaries, and fixture tests should use the Python
  standard library unless a later phase explicitly chooses an optional boundary;
- external provider SDKs belong in optional runtime extras or plugin adapter
  packages, not the core required install;
- adapters must provide offline fixture or mock paths for tests;
- default tests must not require network, credentials, paid APIs, or live model
  calls.

This keeps the governance kernel installable and auditable while leaving room
for richer adapter packages once the evidence and trace contracts are proven.
