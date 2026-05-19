# Release-Trust Hardening Report

Created: 2026-05-19

This report is the external trust summary for the current alpha package. It
explains what local verification is designed to prove, what remains alpha, and
which release actions remain human-owned.

It is not a PyPI release note, GitHub release note, security audit, or public
claim that a release was published.

## Current Trust Posture

`async-research` is a file-backed alpha CLI for careful dogfooding. The package
is designed so humans and LLM operators can inspect durable workspace files,
run public validation commands, route review decisions through explicit gates,
and keep accepted evidence separate from publication-ready deliverables.

The strongest local evidence is regression coverage plus deterministic fixture
smokes. Treat a capability as current evidence only when the relevant command
has passed in the clone or installed environment being evaluated.

## What Local Verification Covers

| Area | Capability | Local evidence to run |
| --- | --- | --- |
| Package docs and references | Packaged Markdown docs, examples, roadmap links, and public command guidance stay internally coherent. | `git diff --check`; `.venv/bin/python -m unittest tests.test_doc_references`; `.venv/bin/python -m unittest tests.test_docs_packaging` |
| Full regression suite | CLI command contracts, validators, dashboard read models, templates, examples, and write guards stay compatible. | `.venv/bin/python -m unittest discover -s tests` |
| Acceptance hardening | P0-P3 safety checks and end-to-end fixture behavior run in isolated temporary workspaces. | `.venv/bin/async-research acceptance-suite` |
| Build and package resources | Wheel and sdist include schemas, templates, docs, examples, console assets, and benchmark resources needed by installed users. | `.venv/bin/python -m build` |
| Starter initialization | Generic and real-estate workspaces initialize and validate without live credentials. | `.venv/bin/async-research starter-smoke /tmp/async-research-starter-generic --force`; `.venv/bin/async-research starter-smoke /tmp/async-research-starter-real-estate --template real-estate --force` |
| Installed examples | Packaged examples can be copied from installed resources and exercised with public commands. | See [Worked Examples Index](./worked_examples_index.md). |

## Delivered Safety And Validation Surfaces

The alpha package includes these trust-building surfaces:

- schema checks for versioned JSON artifacts and task status files
- task-local locks, legal state transitions, and recovery paths for malformed
  `status.json`
- public workflow commands for worker start, worker completion, task advance,
  review drafting, review submission, and review aggregation
- source-governance, data-foundation, and knowledge-library validators that
  render warnings without silently editing the workspace
- default dry-run proposal inspection and guarded data/library proposal apply
  commands with accepted proof, matching preflight hashes, locks, rollback, and
  post-write validation
- dashboard and console snapshot read models that prefer `unavailable` or
  structured findings over inferred or silently repaired state
- result-acceptance gates, accepted-memory freshness checks, and deliverable
  maturity checks that keep accepted task evidence separate from shareable or
  submission-ready output
- analysis preflight, run validation, result validation, and reviewer-packet
  context collection for empirical outputs
- idea traceability and lifecycle metrics that use explicit file-backed links
  and render missing lineage as `unavailable`

## Alpha Boundaries

The package deliberately does not claim:

- autonomous publication readiness
- PyPI publication or GitHub release completion
- external credential, cloud, paid API, warehouse, notebook, SQL, or dbt
  execution coverage
- human approval for public, high-stakes, legal, medical, financial, policy, or
  investment claims
- performance guarantees for very large workspaces
- that warning-only validators are strict release gates

Human owners still decide release timing, version numbers, public positioning,
license policy changes, and whether evidence is appropriate for a real audience
or venue.

## Release-Readiness Notes

Local verification answers "does this checkout or installed wheel satisfy the
documented contracts?" It does not answer "should this package be published?"
or "is this research output ready for public use?"

Before tagging or publishing, use [Release Checklist](../../../RELEASE_CHECKLIST.md)
from a clean release branch. The checklist includes source checks, build
artifact inspection, installed-wheel smoke, packaged-resource smoke, changelog
review, and release hygiene. Publishing to PyPI, creating GitHub releases, and
announcing public readiness remain manual actions outside the CLI.

## Related Reading

- [Scaling Guidance](./scaling_guidance.md)
- [Worked Examples Index](./worked_examples_index.md)
- [Operational Readiness Runbook](./operational_readiness_runbook.md)
- [Internal Helper Boundary](./internal_helper_boundary.md)
- [Foundation Update Proposal Contract](./foundation_update_proposal_contract.md)
