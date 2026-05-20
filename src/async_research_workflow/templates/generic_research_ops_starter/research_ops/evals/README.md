# Runtime Evals

Trace-driven eval suites and eval run reports live here when explicitly written.

Expected locations:

- `evals/<suite-id>.json`
- `evals/runs/<run-id>.json`

Build and run deterministic offline evals with:

```bash
async-research eval build-from-traces research_ops --write
async-research eval run research_ops/evals/runtime-trace-suite.json --write
```

Eval reports are release gates and dashboard inputs. They do not replace
`research_ops/runtime/`, task status, review, result acceptance, or human
decisions as source-of-truth artifacts.
