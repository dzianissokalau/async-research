# Changelog

All notable changes to `async-research-workflow` are tracked here.

The project is pre-release. Alpha versions are intended for careful dogfooding
while the public CLI and workflow contracts harden.

## 0.2.0a3 - 2026-05-09

- Added Knowledge Library starter files, Markdown contracts, idempotent
  `library init`, read-only `library validate`, and read-only
  `library dashboard` surfaces.
- Wired Knowledge Library state into idea-catalog `library_refs`, literature
  extraction task guidance, health, readiness, daily status, and weekly digest
  surfaces while preserving cold-start warning behavior.
- Completed the Research Foundations track by marking Knowledge Library, Data
  Foundations, and Idea Catalog roadmaps delivered.

## 0.2.0a2 - 2026-05-09

- Added data-foundation starter files and profile contracts for source
  readiness, access notes, join paths, and known data gaps.
- Added read-only `data validate` and `data dashboard` surfaces with
  profile/source linkage checks, malformed table guards, active idea gap refs,
  catalog read-model findings, and use-case-aware usable-source summaries.
- Wired data-foundation state into health, readiness, experiment validation,
  result acceptance, generated data-readiness task guidance, and operator docs.

## 0.2.0a1 - 2026-05-08

- Added the durable Idea Catalog workspace with candidate intake, indexing,
  review, scoring, and roadmap-tracking surfaces.
- Added accepted-memory promotion write mode with provenance, duplicate guards,
  dry-run/create behavior, and acceptance artifact checks.
- Hardened Idea Catalog acceptance coverage, including artifact consistency and
  direct inbox verification.

## 0.1.0a2 - 2026-05-06

- Hardened `starter-smoke` and `init` safety behavior.
- Added a generic default starter and kept the real-estate starter as an
  explicit worked example.
- Canonicalized packaged runtime resources for schemas, mission policy, and
  benchmark cases.
- Expanded Python-level regression tests and packaging-aware CI checks.
- Rewrote first-user README guidance and documented CLI exit-code behavior.
- Cleaned up script imports and benchmark/simulation installed-package paths.
- Added package metadata, contributor guidance, and GitHub issue/PR templates.
- Added non-breaking CLI aliases for review surfaces and accepted-memory
  revalidation.
- Refactored CLI parser construction into explicit internal registration
  groups without changing public command behavior.
- Recorded docs packaging policy and added footprint/resource regression tests
  for packaged protocol docs.
- Completed CLI Audit 0-7 by promoting public-worthy wrappers, documenting
  permanent internal helpers, and adding regression guards against CLI/doc
  drift.

## 0.1.0a1 - 2026-05-03

- Initial installable alpha package.
- Added the `async-research` CLI.
- Packaged research operation templates, schemas, benchmark cases, and protocol
  docs.
- Added acceptance, benchmark, starter smoke, readiness, health, review,
  source, cost, metrics, and accepted-memory helper commands.
