# Bounded Parallel Research Threads

Created: 2026-05-20

Bounded parallel research lets a planner split source gathering or extraction
across a small number of branches while preserving one deterministic task,
runtime ledger, merge packet, review gate, and result-acceptance path.

It is not a many-agent swarm. Branches do not own task state, cannot accept
evidence, and cannot skip claim verification, review, result acceptance, or
human gates.

## Allowed Shapes

Parallelism is planner-controlled and only applies to these task shapes:

- `source_gathering`
- `literature_extraction`
- `market_map_slice`
- `policy_jurisdiction_comparison`
- `data_source_profiling`

Other work should stay single-threaded until a roadmap phase adds a specific
contract and fixture.

## Task Contract

The task `status.json` must explicitly enable the policy under
`runtime_permissions.parallel_research`:

```json
{
  "runtime_permissions": {
    "max_calls": 4,
    "max_api_usd": 0.0,
    "max_compute_usd": 0.0,
    "parallel_research": {
      "enabled": true,
      "max_parallel_branches": 2,
      "per_branch_max_calls": 2,
      "per_branch_max_api_usd": 0.0,
      "per_branch_max_compute_usd": 0.0,
      "allowed_shapes": ["literature_extraction"],
      "merge_required": true,
      "no_direct_acceptance": true,
      "require_task_lock": true,
      "concurrency_key": "runtime-parallel"
    }
  }
}
```

Missing policy data fails closed. The global runtime limits still apply, and
each branch must also stay within its own call count, file path, and budget
limits.

When `require_task_lock` is true, the request coordinator must match the active
task-local `LOCK/owner.json`. This integrates with the existing atomic lock
protocol without letting runtime adapters acquire or release task locks.

## Runtime Request

Parallel requests use `mode: "parallel_research"` and must include a
`parallel_plan`:

```json
{
  "mode": "parallel_research",
  "task_id": "TASK-0001",
  "parallel_plan": {
    "planner_controlled": true,
    "coordinator_id": "planner-20260520",
    "merge_strategy": "deterministic_review_packet",
    "review_packet_required": true,
    "merge_output_path": "research_ops/runtime/parallel_merges/TASK-0001-merge.md",
    "branches": [
      {
        "branch_id": "lit-a",
        "branch_shape": "literature_extraction",
        "branch_title": "Literature slice A",
        "allowed_paths": ["research_ops/sources/lit-a.md"],
        "budget": {"max_api_usd": 0.0, "max_compute_usd": 0.0}
      }
    ]
  },
  "calls": []
}
```

Each call must name its `branch_id` and `branch_shape`. Branch source paths
must stay inside that branch's `allowed_paths`. Runtime adapters add
`parallel_branch` metadata to emitted traces and evidence objects, preserving
the normal `EVID-*` and `TRACE-*` identifiers while making branch lineage
queryable.

## Merge Packet

Successful parallel execution writes one Markdown merge packet under
`research_ops/runtime/parallel_merges/`. The packet includes:

- branch summaries
- evidence coverage by branch
- contradictions
- unresolved gaps
- reviewer instructions

The merge packet is review context only. Review, claim verification,
result-acceptance, deliverable maturity, and human gates remain the only paths
to accepted evidence or publication readiness.

## Eval Coverage

Trace-driven evals record parallel branch counts, parallel trace counts, merge
packet counts, and whether parallelism triggered for the case. The
`bounded_parallelism` grader passes only when a parallel case has at least two
bounded branches and a recorded merge packet under `research_ops/`.

Default evals remain deterministic and offline. They do not create live
parallel workers, use credentials, spend money, browse, or optimize prompts.
