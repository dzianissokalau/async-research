# Batch Job Lifecycle Protocol

Created: 2026-05-02

This document implements P3-1 batch job lifecycle for the async research workflow.

## Purpose

Batch work is useful for cheap, slow, high-volume extraction and triage. It is
also dangerous if outputs are treated as accepted research just because a
provider completed the job. Batch output must move through an explicit lifecycle:

```text
draft -> submitted -> completed -> ingested -> reviewed
```

Only `reviewed` batch outputs are trusted for downstream research claims.

## Task Types

Use two first-class task types:

```text
batch_job
batch_ingest
```

`batch_job` tasks prepare and submit a manifest. `batch_ingest` tasks parse
provider outputs into the target workflow folder and prepare them for normal
review.

## Manifest

Each batch lives under:

```text
research_ops/batches/BATCH-0001/batch_manifest.json
```

The manifest validates against:

```text
async_research_workflow/schemas/batch_manifest.schema.json
```

Required core fields:

```json
{
  "schema_version": "1.0",
  "batch_id": "BATCH-0001",
  "lifecycle_status": "draft",
  "input_files": [],
  "prompt_template": "source_extract_v1.0",
  "model": "cheap_or_batch_model",
  "expected_output_schema": "idea_candidate.schema.json",
  "ingest_path": "research_ops/discovery/",
  "output_trust": "untrusted",
  "costs": {
    "estimated_api_usd": 0,
    "estimated_compute_usd": 0,
    "logged": false
  }
}
```

## Required Helper

Use:

```text
async-research batch
```

Create a draft manifest:

```bash
async-research batch init \
  research_ops \
  --batch-id BATCH-0001 \
  --input-file research_ops/batches/BATCH-0001/input.jsonl \
  --prompt-template source_extract_v1.0 \
  --model cheap_or_batch_model \
  --expected-output-schema idea_candidate.schema.json \
  --ingest-path research_ops/discovery/
```

Validate before submission:

```bash
async-research batch validate-manifest \
  research_ops/batches/BATCH-0001/batch_manifest.json
```

Submit and log estimated cost:

```bash
async-research batch submit \
  research_ops/batches/BATCH-0001/batch_manifest.json \
  --provider-batch-id provider-batch-id \
  --api-usd 1.25 \
  --compute-usd 0
```

Record provider outputs while keeping them untrusted:

```bash
async-research batch complete \
  research_ops/batches/BATCH-0001/batch_manifest.json \
  --output-file research_ops/batches/BATCH-0001/provider_output.jsonl
```

Record ingestion while keeping outputs pending review:

```bash
async-research batch ingest \
  research_ops/batches/BATCH-0001/batch_manifest.json \
  --ingest-task-id TASK-0002 \
  --ingested-file research_ops/discovery/IDEA-0007.json
```

Trust outputs only after review:

```bash
async-research batch mark-reviewed \
  research_ops/batches/BATCH-0001/batch_manifest.json \
  --review-task-id TASK-0003
```

## Trust Rule

`output_trust` must be:

| Lifecycle status | Output trust |
| --- | --- |
| `draft` | `untrusted` |
| `validated` | `untrusted` |
| `submitted` | `untrusted` |
| `completed` | `untrusted` |
| `ingested` | `ingested_pending_review` |
| `reviewed` | `reviewed` |

Provider completion is not enough. Batch output is usable for downstream work
only when the manifest is `reviewed`.

Check trust status:

```bash
async-research batch trust-status \
  research_ops/batches/BATCH-0001/batch_manifest.json
```

This exits nonzero until outputs are reviewed.

## Cost Rule

`submit` requires `--api-usd` and `--compute-usd` and appends an estimated row to:

```text
research_ops/cost_ledger.csv
```

The row includes `amount_usd`, `api_usd`, `compute_usd`, and `actual=false`, so
health checks and metrics snapshots can include batch spend. If the provider
later returns usage JSON, ingest it with `async-research cost ingest-usage` so the
ledger also records actual tokens.

## Acceptance Checks

P3-1 is implemented when:

- malformed or incomplete `batch_manifest.json` fails before submission
- submitted batches append cost rows to `cost_ledger.csv`
- completed provider outputs remain `output_trust = "untrusted"`
- ingested outputs remain `output_trust = "ingested_pending_review"`
- only reviewed outputs return trusted status
