# Runtime Evals

Created: 2026-05-20

Runtime evals turn repository-backed runtime traces into repeatable regression
fixtures. They are deterministic and offline by default; they do not call live
models, browse the web, use credentials, spend money, or change task state.

## Locations

Eval artifacts live under `research_ops/evals/`:

```text
research_ops/evals/
  <suite-id>.json
  runs/
    <run-id>.json
```

The source-of-truth inputs remain the original repository files:

- `research_ops/runtime/traces.jsonl`
- `research_ops/runtime/evidence_objects.jsonl`
- runtime snapshots
- task `status.json`
- review aggregates
- result-acceptance records
- claim-verification reports

## Commands

Build a suite from existing runtime traces:

```bash
async-research eval build-from-traces research_ops --write
```

Run deterministic graders:

```bash
async-research eval run research_ops/evals/runtime-trace-suite.json --write
```

Compare a candidate run against a baseline:

```bash
async-research eval compare \
  research_ops/evals/runs/baseline.json \
  research_ops/evals/runs/candidate.json
```

`build-from-traces` is read-only unless `--write` is provided. `run` writes only
under `research_ops/evals/runs/` when `--write` is provided. `compare` is
read-only.

For prompt or routing policy adoption, use the model-routing gate after the
candidate run has been written:

```bash
async-research model-routing eval-check \
  research_ops/prompts/model_routing_policy.json \
  --baseline research_ops/evals/runs/baseline.json \
  --candidate research_ops/evals/runs/candidate.json
```

The candidate run must record the candidate policy id in `model_routing_policy`.
If groundedness, unsupported-claim rate, task success, accepted-output rate,
freshness, reproducibility, or cost per accepted report regresses, adoption is
blocked.

## Dataset Contract

Each eval case records:

- `case_id`
- `source_trace_ids`
- `input_brief`
- `expected_behavior`
- `gold_or_reference_evidence`
- `grader`
- `metrics`
- `known_limitations`

The suite also records runtime policy, model-routing policy, release policy,
and whether human calibration is included.

## Automated Graders

Default graders are deterministic:

- schema, path, and snapshot-hash reproducibility
- grounded claim rate
- unsupported claim rate
- citation support and freshness
- accepted-output and task-success gates
- cost and latency accounting

Human preference and subjective rubric checks are explicit placeholders until
calibrated reviewer data is attached.

## Release Policy

Candidate runs fail comparison when they regress groundedness, unsupported
claims, task success, accepted-output rate, freshness, reproducibility, or cost
per accepted report beyond the configured tolerance.

The eval surface can support narrow quality claims only when the claim cites the
suite, baseline, candidate, metric deltas, and residual risks. Deep
Research-style head-to-head comparisons remain out of scope until benchmark
cases and source policies are defined for that purpose.
