# Runtime Adapters

Created: 2026-05-20

Runtime adapters are the Phase 3 execution boundary for integrated research
actions. They are optional, task-contract bounded, and subordinate to the
existing workflow, review, and result-acceptance gates.

## Interface

Every adapter follows the same narrow interface:

- `capabilities()`
- `dry_run(request)`
- `execute(request)`
- `to_trace()`
- `to_evidence_objects()`

The public CLI wrappers are:

```bash
async-research runtime dry-run research_ops --request runtime_request.json
async-research runtime execute research_ops --request runtime_request.json
```

`dry-run` is read-only. `execute` writes only under
`research_ops/runtime/` without changing task state, `status.json`, review
files, accepted outputs, or task transitions.

## Task Contract

Runtime requests fail closed unless the task status contract grants explicit
permission:

- `allowed_tools` must include either the adapter type, such as `file_fetch`,
  or the namespaced form, such as `runtime:file_fetch`.
- `allowed_paths` must include `research_ops/runtime/**` before execution can
  write traces, snapshots, or evidence objects.
- `runtime_permissions.max_calls` must bound the request size.
- `budget.max_api_usd`, `budget.max_compute_usd`,
  `runtime_permissions.max_api_usd`, and
  `runtime_permissions.max_compute_usd` bound cost.
- `allow_browsing=true` is required for `web_search` and `web_open`.
- `allow_network=true` is required for network-capable adapters:
  `web_search`, `web_open`, `mcp_search`, `mcp_fetch`, and `api_query`.
- `allow_code_execution=true` is required for `code_execute`.
- `runtime_permissions.allowed_domains` bounds web adapters.
- `runtime_permissions.allowed_api_names` bounds `api_query`.
- `runtime_permissions.allowed_mcp_servers` bounds MCP adapters.
- Credential use requires `runtime_permissions.allow_credentials=true`.
- Paid calls require `runtime_permissions.allow_paid_calls=true` and must stay
  inside the task budget.

Missing permission data fails closed. A blocked execution may write a trace with
`return_code=blocked_by_policy`, but it writes no evidence object.

## Implemented Adapters

The Phase 3 core package remains standard-library first:

- `file_fetch` reads a permitted text file under `research_ops/` and snapshots
  it as a runtime evidence object.
- `file_search` searches permitted text files under `research_ops/` and
  snapshots matching lines.
- `code_execute` runs only deterministic built-in summary operations:
  `word_count`, `line_count`, and `sha256`.
- `web_search`, `web_open`, `mcp_search`, `mcp_fetch`, and `api_query` are
  mocked-only in Phase 3. They require explicit task-contract permission and a
  `mock_response`; the core package does not perform live network,
  credentialed, or paid calls.

## Request Shape

Runtime requests are single-task JSON files:

```json
{
  "mode": "vertical_slice",
  "task_id": "TASK-1001",
  "calls": [
    {
      "adapter_type": "file_fetch",
      "source_path": "research_ops/sources/source.md",
      "license_or_use_policy": "fixture-only"
    },
    {
      "adapter_type": "api_query",
      "api_name": "fixture_stats",
      "mock_response": {
        "source_uri": "mock://fixture_stats/runtime",
        "source_title": "Mock API fixture",
        "content": "metric=42\n"
      }
    }
  ]
}
```

The request is not accepted evidence. It is only an execution instruction that
must produce valid runtime traces and evidence objects before review can use
the results.
