# JSON And Schema Validation Protocol

Created: 2026-05-02

This document implements the P0 JSON/schema validation requirement from the feedback hardening plan.

## Purpose

Prevent malformed or schema-invalid JSON artifacts from silently entering the async research workflow.

State transition validation checks whether a status move is legal. Schema validation checks whether the JSON artifact itself is well formed and has the required fields, types, enums, patterns, and bounds.

## Required Validator

Use:

```text
async_research_workflow/scripts/validate_json_artifact.py
```

This is a small stdlib validator for the JSON Schema subset used by the workflow examples. It intentionally avoids third-party dependencies so it can run locally or in GitHub Actions without setup.

Supported schema features:

- `type`
- nullable type lists such as `["string", "null"]`
- `required`
- `properties`
- `items`
- `enum`
- `pattern`
- `minimum`
- `maximum`

It is not a full JSON Schema Draft 2020-12 implementation. Unsupported assertion
keywords such as `anyOf`, `oneOf`, `$ref`, `const`, `minItems`, `maxItems`, and
`additionalProperties` fail closed so future schemas do not silently rely on
constraints this helper does not check. If the workflow later needs advanced
schema features, add validator support first or replace it with a pinned
`jsonschema` dependency.

## Validate Commands

Task status:

```bash
python -m async_research_workflow.scripts.validate_json_artifact \
  --schema async_research_workflow/schemas/task_status.schema.json \
  research_ops/tasks/TASK-0001/status.json
```

Idea candidate:

```bash
python -m async_research_workflow.scripts.validate_json_artifact \
  --schema async_research_workflow/schemas/idea_candidate.schema.json \
  research_ops/discovery/IDEA-0001.json
```

Review panel output:

```bash
python -m async_research_workflow.scripts.validate_json_artifact \
  --schema async_research_workflow/schemas/review_panel.schema.json \
  research_ops/tasks/TASK-0001/review_panel/aggregate.json
```

Exit codes:

| Code | Meaning |
| ---: | --- |
| 0 | valid |
| 2 | schema validation failed |
| 4 | schema or artifact JSON is missing or malformed |

## Agent Write Rule

Any agent writing JSON must:

1. write the JSON artifact
2. run `validate_json_artifact.py` with the matching schema
3. if validation fails, stop and report the error
4. do not route the task as complete until the artifact validates

For `status.json`, agents must run both:

```bash
python -m async_research_workflow.scripts.validate_json_artifact \
  --schema async_research_workflow/schemas/task_status.schema.json \
  <task-dir>/status.json

python -m async_research_workflow.scripts.validate_transition \
  <task-dir>
```

Schema validation should happen first. Transition validation assumes valid JSON.

## Required Artifact Mapping

| Artifact | Schema |
| --- | --- |
| `status.json` | `task_status.schema.json` |
| idea candidate JSON | `idea_candidate.schema.json` |
| review panel aggregate JSON | `review_panel.schema.json` |
| batch manifest JSON | `batch_manifest.schema.json` |

Future schemas should be added for:

- health reports
- cost ledger machine summaries

Human decisions are structured markdown rows in `research_ops/decisions.md`;
validate them with `human_decision_log.py check` and transition validation
rather than a JSON schema.

Metrics snapshots are JSONL records in `research_ops/metrics_history.jsonl`.
Create and summarize them with `metrics_history.py`; do not hand-edit previous
JSONL rows.

Review panel aggregate JSON is written by `aggregate_reviews.py` and must validate against `review_panel.schema.json` before it can route the task.

## Schema Version Checks

Every new workflow JSON artifact should include:

```json
{
  "schema_version": "1.0"
}
```

During the P2-1 migration window, missing versions are warnings rather than hard validation failures so old task folders stay readable. Run:

```bash
async-research schema-check research_ops
```

The health monitor also includes these warnings in `checks.schema_version_warnings`.

Workflow JSON schemas require `schema_version = "1.0"` where a schema exists. `task_status.schema.json` also allows `prompt_versions` and `framework_versions`.
They are optional during migration, but new task status files should include
them so accepted outputs remain auditable.

## Failure Handling

If validation fails:

- the agent must not mark the task accepted or complete
- the failure should be reported in the final response
- the future health check should surface the invalid artifact
- if the invalid file blocks progress, run the status recovery wrapper and route the task to `needs_human`

## Status Recovery Wrapper

Use this wrapper when `status.json` is malformed, missing, schema-invalid, or has
an invalid transition:

```bash
python -m async_research_workflow.scripts.recover_status_json \
  research_ops/tasks/TASK-0001
```

The wrapper:

- preserves the original file as `status.invalid.<timestamp>.<pid>.json`
- writes a minimal valid `status.json` with `status = needs_human`
- sets `requires_human = true`
- sets `last_transition_reason = status_json_recovery`
- validates the recovered file against `task_status.schema.json`
- validates the recovered transition

If the original status cannot be parsed, the recovered file uses
`previous_status = null`. The transition validator allows `null -> needs_human`
only for this recovery reason.

## GitHub Actions Guidance

After Codex writes task artifacts, validate the changed JSON files before opening a pull request.

Example for a known task:

```bash
python -m async_research_workflow.scripts.validate_json_artifact \
  --schema async_research_workflow/schemas/task_status.schema.json \
  research_ops/tasks/TASK-0001/status.json
```

If the worker selects the task dynamically, it should report the task path in its final message. A wrapper can then validate that path.

## Acceptance Tests

The schema validation layer is considered implemented when:

- a valid task status artifact passes
- a task status missing a required field fails
- an invalid enum value fails
- an invalid ID pattern fails
- an out-of-range score fails
- a scored idea missing `mission_policy_version` fails
- unbounded or out-of-range revision counters fail
- malformed JSON fails
- malformed `status.json` can be recovered to a valid `needs_human` state
- worker/reviewer prompts require schema validation after JSON writes

## Relationship To Other P0 Controls

Atomic locking prevents simultaneous writers.

Schema validation prevents malformed JSON state.

State transition validation prevents illegal state moves.

All three are required before recurring autonomous jobs should run.
