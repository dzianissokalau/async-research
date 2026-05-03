# Atomic Locking Protocol

Created: 2026-05-02

This document implements the P0 atomic task locking requirement from the feedback hardening plan.

## Purpose

Prevent two autonomous workers from claiming and writing the same task at the same time.

The previous `lock_owner` and `lock_expires_at` fields in `status.json` are useful metadata, but they are not an atomic claim mechanism. They can be read by two workers before either writes an update.

The authoritative worker claim is now:

```text
research_ops/tasks/<TASK-ID>/LOCK/
```

The lock is acquired by atomically creating the `LOCK/` directory. On normal filesystems, only one process can create a directory with a given name. All other workers fail the claim and must skip the task.

## Required Task Folder Shape

```text
research_ops/tasks/TASK-0001-example/
  LOCK/                         # exists only while claimed
    owner.json
  task.md
  status.json
  worker_output.md
  reviews/
  review_panel/
  artifacts/
```

## Lock Metadata

The lock owner writes:

```json
{
  "owner": "worker-20260502-001",
  "pid": 12345,
  "hostname": "runner-or-machine",
  "acquired_at": "2026-05-02T10:00:00Z",
  "task_dir": "research_ops/tasks/TASK-0001-example",
  "stale_after_seconds": 3600
}
```

## Claim Rule

Worker sequence:

1. Read `queue.md` only to identify candidate tasks.
2. Select the oldest task with `status = ready_for_worker`.
3. Attempt to acquire `LOCK/` using the helper script.
4. If lock acquisition fails because the lock is fresh, skip the task and try the next candidate.
5. If lock acquisition succeeds, update `status.json` to `in_progress`.
6. Work only inside the task's allowed paths.
7. Before completion, write outputs and update `status.json`.
8. Release `LOCK/` only after final writes succeed.

The worker must not write `worker_output.md` before acquiring `LOCK/`.

## Stale Locks

A lock is stale when its directory or metadata age exceeds:

```text
max_minutes + 15 minutes
```

If a lock is stale:

1. move `LOCK/` to `LOCK.stale.<timestamp>.<pid>/`
2. attempt to create a fresh `LOCK/`
3. record stale lock recovery in `daily_status.md` or the future health report

Do not delete stale locks immediately. Renaming preserves forensic evidence.

## Helper Script

Use:

```text
async_research_workflow/examples/scripts/task_lock.py
```

Acquire:

```bash
python3 async_research_workflow/examples/scripts/task_lock.py acquire \
  research_ops/tasks/TASK-0001-example \
  --owner "$RESEARCH_WORKER_OWNER" \
  --stale-minutes 60
```

Release:

```bash
python3 async_research_workflow/examples/scripts/task_lock.py release \
  research_ops/tasks/TASK-0001-example \
  --owner "$RESEARCH_WORKER_OWNER"
```

Status:

```bash
python3 async_research_workflow/examples/scripts/task_lock.py status \
  research_ops/tasks/TASK-0001-example
```

Exit codes:

| Code | Meaning |
| ---: | --- |
| 0 | success |
| 2 | lock exists and is fresh |
| 3 | release denied because owner differs |
| 4 | invalid task directory or lock state |

## Local Scheduler Guidance

Use a global process lock as a second layer:

```bash
flock /tmp/async-research-worker.lock \
  codex exec --cd "$RESEARCH_REPO_ROOT" --sandbox workspace-write ...
```

The global process lock prevents overlapping scheduler invocations. The task-local `LOCK/` prevents two independent workers from claiming the same task.

## GitHub Actions Guidance

Use workflow-level concurrency to avoid overlapping worker runs:

```yaml
concurrency:
  group: async-research-worker-${{ github.ref }}
  cancel-in-progress: false
```

Then still use task-local `LOCK/` inside the worker prompt. Workflow-level concurrency is not a replacement for task-local locking, because future workflows may run multiple worker classes or branches.

## Required Prompt Language

Every worker prompt should include:

```text
Before writing any task output, acquire the task-local LOCK/ using
async_research_workflow/examples/scripts/task_lock.py. If lock acquisition fails,
skip that task. Release the lock only after final status and output writes complete.
```

## Acceptance Tests

The locking protocol is considered implemented when:

- two simultaneous acquire attempts on the same task produce one success and one fresh-lock failure
- stale lock recovery renames the old lock instead of deleting it
- release fails when attempted by the wrong owner
- release succeeds for the current owner
- worker prompts require lock acquisition before writing outputs
- the GitHub Actions example mentions both workflow concurrency and task-local locking

## Relationship To `status.json`

`status.json` should still keep these fields for observability:

```json
{
  "lock_owner": "worker-20260502-001",
  "lock_expires_at": "2026-05-02T11:00:00Z"
}
```

But these fields are not the authoritative lock. They are metadata derived from the `LOCK/` claim.
