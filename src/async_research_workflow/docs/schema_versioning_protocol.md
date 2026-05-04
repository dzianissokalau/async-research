# Schema Versioning Protocol

Created: 2026-05-02

This document implements P2-1 schema versioning for the async research workflow.

## Purpose

Every machine-readable workflow JSON artifact should declare the schema contract it was written against. Versioning makes slow asynchronous jobs safer because a worker can tell whether an artifact is current, pre-migration, or ahead of the code it is running.

## Current Version

The current workflow JSON schema version is:

```json
{
  "schema_version": "1.0"
}
```

The field applies to:

- `research_ops/tasks/*/status.json`
- `research_ops/tasks/*/review_panel/aggregate.json`
- `research_ops/discovery/IDEA-*.json`
- `research_ops/batches/*/batch_manifest.json`
- `research_ops/health_report.json`

Schemas require `schema_version` for task status artifacts. Missing or mismatched versions fail validation so scheduled agents do not continue against an unknown contract.

## Write Rule

Any agent or helper that writes a workflow JSON artifact must include:

```json
{
  "schema_version": "1.0"
}
```

Status-writing helpers also add the default when they update an older task. This gives the workflow opportunistic migration without a disruptive all-at-once rewrite.

## Version Check

Run:

```bash
async-research schema-check research_ops
```

The checker scans known workflow JSON artifacts and reports:

- `missing_schema_version`: artifact must be repaired or migrated before agents continue
- `schema_version_mismatch`: artifact was written against a different schema version
- `malformed_json`: artifact cannot be inspected and needs repair or quarantine

Missing, mismatched, malformed, or unreadable artifacts return a nonzero exit code.

## Health Monitor Integration

`health_check.py` embeds the schema-version scan in `health_report.json`:

```text
checks.schema_version_warnings
```

If any known JSON artifact is missing a version or uses a mismatched version, the report includes a `schema_version_warnings` alert with artifact paths, artifact types, expected version, actual version, and migration reason. The alert name is retained for compatibility, but these issues are hard failures for worker/reviewer validation.

## Migration Notes

### 1.0

Initial explicit schema version. Defaults:

| Artifact | Default |
| --- | --- |
| `status.json` | `"schema_version": "1.0"` |
| idea candidate JSON | `"schema_version": "1.0"` |
| review panel aggregate JSON | `"schema_version": "1.0"` |
| batch manifest JSON | `"schema_version": "1.0"` |
| health report JSON | `"schema_version": "1.0"` |

For pre-1.0 artifacts:

- migrate or repair the artifact before scheduled agents continue
- use `recover_status_json.py` for task status files that cannot be safely migrated
- keep the original invalid artifact beside the repaired file for auditability
- do not treat a task as routable until schema validation and schema-version checks pass

## Future Bumps

For every future schema version:

1. Add a migration note here.
2. Document new fields and defaults.
3. Update the relevant schema files.
4. Update all helper scripts that write the artifact.
5. Keep old artifacts readable where possible.
6. Decide whether the old version remains readable; if not, fail closed and document the migration helper.
