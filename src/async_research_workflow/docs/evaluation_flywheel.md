# Evaluation Flywheel

Created: 2026-05-20

This contract defines how runtime traces and evidence objects become repeatable
evals. Phase 5 implements the first deterministic eval surface in
[Runtime Evals](./runtime_evals.md).

## Evaluation Boundary

The eval flywheel measures whether runtime-backed research is improving without
turning anecdotes into product claims.

It may:

- build fixture eval cases from runtime traces, evidence objects, worker output,
  reviews, result-acceptance artifacts, and deliverable gates;
- run deterministic validators over schemas, paths, hashes, permissions,
  citations, and claim support;
- compare baseline and candidate outputs with explicit metric deltas;
- mark human-calibrated rubrics separately from automated checks.

It must not:

- require paid live model calls in the default test path;
- optimize prompts or routes automatically without review;
- claim broad superiority over general-purpose Deep Research-style products
  without benchmark evidence and explicit limits;
- move core truth out of `research_ops/` artifacts.

## Success Metrics

Phase 5 evals should expose these metrics with documented denominators,
fixtures, and known limits:

| Metric | Direction | Measurement intent |
| --- | --- | --- |
| Expert preference win rate | Higher is better | Share of paired reviews preferring the candidate output for a bounded domain/task. |
| Grounded claim rate | Higher is better | Material claims mapped to supporting evidence spans or computation artifacts. |
| Unsupported claim rate | Lower is better | Material claims with missing, stale, contradicted, or insufficient support. |
| Task success rate | Higher is better | Tasks that satisfy their brief, source policy, and stop conditions. |
| Accepted-output rate | Higher is better with guardrails | Reviewed outputs accepted without hiding caveats, caps, or follow-ups. |
| Cost per accepted report | Lower is better | Total runtime/model/tool cost divided by accepted reports. |
| Median latency to accepted report | Lower is better | Median wall-clock time from accepted brief to accepted output. |
| Freshness failure rate | Lower is better | Evidence or accepted-memory reuse that violates freshness policy. |
| Reviewer disagreement rate | Lower is not always better | Share of cases where independent reviewers disagree materially. |
| Reproducibility pass rate | Higher is better | Cases that rerun from fixtures/traces with matching validator outcomes. |

Metric reporting must include the suite, fixture version, runtime policy,
model-routing policy, and whether human review was simulated or real.

## Eval Dataset Inputs

The future eval dataset should be rebuildable from repository artifacts:

- clarified brief or task contract;
- runtime trace rows;
- evidence objects and snapshots;
- worker output or deliverable draft;
- claim and citation verification artifacts;
- review aggregates and result-acceptance decisions;
- cost, latency, and token-use summaries;
- known limitations and human-gate records.

If an eval case relies on private reviewer notes or private sources, the public
fixture must store only a redacted summary plus enough provenance for a reviewer
to understand what was withheld.

## Release Policy

Runtime, prompt, model-routing, adapter, and claim-verification changes should
not be marked as quality improvements merely because they are newer.

Phase 5 should enforce this release posture:

- compare candidate behavior against a named baseline;
- report pass/fail, metric deltas, and residual risks;
- fail closed when schema, path, hash, permission, or citation-support
  validators fail;
- require explicit human calibration for subjective rubrics;
- preserve old prompt/runtime variants as baselines until the candidate matches
  or improves groundedness, task success, and cost within documented limits.

Implemented commands:

```bash
async-research eval build-from-traces research_ops --write
async-research eval run research_ops/evals/runtime-trace-suite.json --write
async-research eval compare research_ops/evals/runs/baseline.json research_ops/evals/runs/candidate.json
```

The console snapshot exposes read-only eval suite count, run count, latest run
status, quality metrics, and release-policy posture under its `evals` group.

## Honest Benchmarking

Head-to-head comparisons with Deep Research-style products are out of scope
until Phase 10. When they are introduced, reports must state the domain, source
permissions, allowed tools, benchmark cases, judging rubric, and where the
system wins, loses, or remains unproven.

One domain pack cannot justify broad superiority claims. The accepted claim is
narrower: async-research should be evaluated for repeatable, auditable,
domain-specific research programs where private data, reproducibility,
freshness, cost discipline, and review independence matter.
