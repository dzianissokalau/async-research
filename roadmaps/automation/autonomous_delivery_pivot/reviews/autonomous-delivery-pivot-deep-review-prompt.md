# Deep Review Prompt - Autonomous Delivery Pivot

Repository: `dzianissokalau/async-research`
Final branch: `codex/autonomous-delivery-pivot-delivered`
Pre-delivery base commit: `259207d`

Roadmap path:
`roadmaps/delivered_autonomous_delivery_pivot_roadmap.md`

Delivery log path:
`roadmaps/automation/autonomous_delivery_pivot/delivery_log.md`

State file path:
`roadmaps/automation/autonomous_delivery_pivot/delivery_state.json`

Review files path:
`roadmaps/automation/autonomous_delivery_pivot/reviews/`

## Verification Commands Reported Passed

Final Phase 9 verification:

```bash
git diff --check
.venv/bin/python -m unittest tests.test_doc_references
.venv/bin/python -m unittest tests.test_docs_packaging
.venv/bin/python -m unittest tests.test_release_trust_docs
.venv/bin/python -m unittest discover -s tests
.venv/bin/async-research acceptance-suite
.venv/bin/python -m build
```

Earlier phase-specific verification is recorded in the delivery log and phase
review files. Confirm the relevant commands and outputs before trusting any
delivery claim.

## Review Instructions

Inspect the full delivered diff against the pre-delivery base commit:

```bash
git fetch origin
git switch codex/autonomous-delivery-pivot-delivered
git diff --stat 259207d..codex/autonomous-delivery-pivot-delivered
git diff 259207d..codex/autonomous-delivery-pivot-delivered
```

If `259207d` is not present in your checkout, identify the parent of the first
autonomous-delivery-pivot phase commit and use that as the pre-delivery base.

Review whether the delivered system respects the roadmap autonomy contract:

- feature behavior matches the stated phase scopes and does not implement
  excluded product strategy, external access, publishing, or broad refactors
- tests cover changed behavior at appropriate levels
- write-capable proposal commands default to dry-run and require explicit
  `--write`, accepted task/review proof, matching preflight hash, locks,
  rollback, and post-write validation
- transaction and rollback behavior preserves data integrity on validation
  failure or lock contention
- path handling fails closed on path traversal, outside-workspace targets, and
  invalid source/library references
- validators preserve warning-only behavior unless a phase explicitly made a
  check strict
- dashboard/read-model outputs are honest, deterministic, and render missing
  information as `unavailable` rather than inference
- analysis and reviewer-packet surfaces do not auto-review, auto-accept, or
  overstate evidence
- idea traceability and lifecycle metrics use explicit file-backed links only
- release-trust docs avoid implying PyPI publication, GitHub release creation,
  public readiness, external verification, or claims not backed by tests
- roadmap status, delivery log entries, review files, branch state, and final
  completion claims agree

## Expected Output

Return:

- findings by severity with file and line references
- missing or weak tests
- residual risks and human-owned decisions
- whether the final branch should be accepted as delivered
- final verdict exactly one of `delivered`, `needs-fix`, or `blocked`
