# Changelog

All notable changes to `async-research-workflow` are tracked here.

The project is pre-release. Until tagged releases begin, `main` may contain
alpha hardening work that still reports package version `0.1.0a1`.

## Unreleased

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

## 0.1.0a1 - 2026-05-03

- Initial installable alpha package.
- Added the `async-research` CLI.
- Packaged research operation templates, schemas, benchmark cases, and protocol
  docs.
- Added acceptance, benchmark, starter smoke, readiness, health, review,
  source, cost, metrics, and accepted-memory helper commands.
