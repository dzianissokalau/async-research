# Structural Reviewer Isolation Protocol

Created: 2026-05-02

This document implements the P0 structural reviewer isolation requirement from the feedback hardening plan.

## Purpose

Preserve independent first-pass reviews by enforcing isolation structurally, not only through prompt instructions.

Reviewers should not see other reviewers' notes before writing their own. The aggregator is the only role that should see all review files.

## Core Rule

Use role-specific review bundles.

```text
task folder -> isolated reviewer bundle -> reviewer writes output -> output installed back to task folder
```

Specialist reviewer bundles include:

- `task.md`
- `status.json`
- `worker_output.md`
- `artifacts/`
- an empty role-specific output path

They exclude:

- `reviews/primary.md`
- `reviews/methodology.md`
- `reviews/skeptic.md`
- `review_panel/aggregate.md`

Aggregator bundles include all reviews.

## Helper Script

Use:

```text
async_research_workflow/examples/scripts/prepare_review_context.py
```

Prepare a methodology reviewer bundle:

```bash
python3 async_research_workflow/examples/scripts/prepare_review_context.py prepare \
  research_ops/tasks/TASK-0001 \
  --role methodology \
  --bundle-dir /tmp/review-TASK-0001-methodology \
  --force
```

Run the reviewer against the bundle:

```text
Repository root: /tmp/review-TASK-0001-methodology
Read input/task.md, input/status.json, input/worker_output.md, and input/artifacts/.
Write output/reviews/methodology.md.
```

Install the completed review:

```bash
python3 async_research_workflow/examples/scripts/prepare_review_context.py install \
  /tmp/review-TASK-0001-methodology \
  --force
```

Prepare an aggregator bundle:

```bash
python3 async_research_workflow/examples/scripts/prepare_review_context.py prepare \
  research_ops/tasks/TASK-0001 \
  --role aggregator \
  --bundle-dir /tmp/review-TASK-0001-aggregator \
  --force
```

Aggregator bundles include `input/reviews/` and write `output/review_panel/aggregate.md`.

## Bundle Layout

Reviewer bundle:

```text
/tmp/review-TASK-0001-methodology/
  manifest.json
  input/
    task.md
    status.json
    worker_output.md
    artifacts/
  output/
    reviews/
      methodology.md
```

Aggregator bundle:

```text
/tmp/review-TASK-0001-aggregator/
  manifest.json
  input/
    task.md
    status.json
    worker_output.md
    artifacts/
    reviews/
      primary.md
      methodology.md
      skeptic.md
  output/
    review_panel/
      aggregate.md
```

## Role Visibility Matrix

| Role | Sees task input | Sees artifacts | Sees sibling reviews | Writes |
| --- | --- | --- | --- | --- |
| Primary | yes | yes | no | `reviews/primary.md` |
| Methodology | yes | yes | no | `reviews/methodology.md` |
| Skeptic | yes | yes | no | `reviews/skeptic.md` |
| Aggregator | yes | yes | yes | `review_panel/aggregate.md` |

## Scheduler Rule

Each reviewer role should run in a separate process/session/API call.

The scheduler should:

1. prepare the bundle for exactly one reviewer role
2. run that reviewer with the bundle as the working context
3. install only that reviewer's output file
4. repeat separately for other reviewer roles
5. prepare the aggregator bundle only after required reviews exist

Do not run primary, methodology, skeptic, and aggregator in a single long agent session.

## Acceptance Tests

Structural reviewer isolation is considered implemented when:

- methodology bundle contains no `reviews/primary.md`
- skeptic bundle contains no `reviews/methodology.md`
- primary bundle contains no sibling review files
- aggregator bundle contains all available review files
- install copies only the role's output file back to the task folder
- install refuses to overwrite an existing review unless `--force` is passed

## Relationship To Review Policy

The review ensemble policy defines when reviewers are needed.

This protocol defines how to keep their context separate.

Use this protocol for Tier 2 and Tier 3 reviews. Tier 1 primary-only reviews may also use it for consistency.
