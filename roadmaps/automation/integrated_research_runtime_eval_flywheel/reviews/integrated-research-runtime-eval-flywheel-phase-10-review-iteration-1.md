# Integrated Research Runtime Eval Flywheel Phase 10 Review - Iteration 1

Date: 2026-05-20
Branch: `codex/integrated-research-runtime-eval-flywheel-phase-10`
Roadmap: `roadmaps/in_progress_integrated_research_runtime_eval_flywheel_roadmap.md`
Verdict: delivered

## Scope Reviewed

- Climate/coffee economics first domain selection and benchmark boundary.
- Domain pack source policy, preferred source classes, brief template, task
  templates, claim gates, reviewer rubric, eval cases, comparison report, and
  example workspace skeleton.
- Packaged generic baseline and upgraded runtime eval-run artifacts.
- Resource helper and package-data coverage for domain pack resources.
- Documentation updates for domain-pack benchmark honesty and Deep
  Research-style comparison limits.
- Offline tests proving artifact presence, case coverage, runtime eval-run
  schema validity, `async-research eval compare` compatibility, resource
  packaging, and no broad superiority claim.

## Findings

No blocking or needs-fix findings.

## Verification Reviewed

- `git diff --check`: passed
- `.venv/bin/python -m unittest tests.test_doc_references`: passed, 16 tests
- `.venv/bin/python -m unittest tests.test_docs_packaging tests.test_domain_pack_benchmarks tests.test_runtime_evals`: passed, 17 tests
- `.venv/bin/python -m unittest discover -s tests`: passed, 787 tests
- `.venv/bin/async-research acceptance-suite`: passed, 15 checks
- `.venv/bin/python -m build`: passed, sdist and wheel built

## Residual Risks

- The benchmark is a deterministic packaged fixture; live source acquisition,
  paid APIs, credentials, and proprietary Deep Research-style outputs remain
  unproven until separately permissioned and reviewed.
- Expert preference win rate is intentionally not measured because no
  calibrated paired human reviews are bundled.
- Review ran in the orchestration context after rereading scope, delivered
  artifacts, tests, docs, and verification output; no separate reviewer
  sub-agent was used.
