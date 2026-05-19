# Release Checklist

Use this checklist before tagging or publishing an alpha release. It is designed
to verify the source tree, built artifacts, installed CLI, and packaged runtime
resources from a clean environment.

Local verification is necessary but not sufficient for publication. Do not
publish to PyPI, create a GitHub release, tag a release, or announce public
readiness until a human owner explicitly chooses the version, timing, and
release notes.

## Preconditions

- Work from a clean branch intended for release.
- Confirm runtime dependencies remain standard-library-only unless a roadmap
  item explicitly changed that policy.
- Use Python 3.13 for the packaging smoke when available, because CI already
  covers Python 3.11, 3.12, and 3.13.

## Source Checks

```bash
.venv/bin/python -m unittest discover -s tests
.venv/bin/async-research acceptance-suite
.venv/bin/async-research benchmark
.venv/bin/async-research starter-smoke /tmp/async-research-release-generic --force
.venv/bin/async-research starter-smoke /tmp/async-research-release-real-estate --template real-estate --force
.venv/bin/python -m compileall src tests
git diff --check
git status --short --branch
```

## Build Artifacts

```bash
rm -rf /tmp/async-research-dist
.venv/bin/python -m build --sdist --wheel --no-isolation --outdir /tmp/async-research-dist
```

Inspect the artifact contents:

```bash
python -m zipfile --list /tmp/async-research-dist/*.whl
tar -tzf /tmp/async-research-dist/*.tar.gz
```

Optional PyPI metadata check, only when `twine` is already available in the
environment:

```bash
python -m twine check /tmp/async-research-dist/*
```

Do not add `twine` as a runtime dependency.

## Installed Wheel Smoke

```bash
rm -rf /tmp/async-research-wheel-venv
.venv/bin/python -m venv /tmp/async-research-wheel-venv
/tmp/async-research-wheel-venv/bin/python -m pip install /tmp/async-research-dist/*.whl
/tmp/async-research-wheel-venv/bin/async-research --help
/tmp/async-research-wheel-venv/bin/async-research version
/tmp/async-research-wheel-venv/bin/async-research acceptance-suite
/tmp/async-research-wheel-venv/bin/async-research benchmark
/tmp/async-research-wheel-venv/bin/async-research starter-smoke /tmp/async-research-wheel-generic --force
/tmp/async-research-wheel-venv/bin/async-research starter-smoke /tmp/async-research-wheel-real-estate --template real-estate --force
```

## Packaged Resource Smoke

Verify key packaged resources are available through `importlib.resources` from
the installed wheel:

```bash
/tmp/async-research-wheel-venv/bin/python - <<'PY'
from importlib import resources

root = resources.files("async_research_workflow")
required = [
    ("mission_policy.json",),
    ("schemas", "task_status.schema.json"),
    ("benchmarks", "autonomy_benchmark_cases.json"),
    ("templates", "generic_research_ops_starter", "research_ops", "README.md"),
    ("templates", "research_ops_starter", "research_ops", "README.md"),
    ("docs", "operational_readiness_runbook.md"),
    ("docs", "scheduler_and_prompts.md"),
]
missing = ["/".join(parts) for parts in required if not root.joinpath(*parts).is_file()]
if missing:
    raise SystemExit(f"missing packaged resources: {missing}")
print("packaged resources ok")
PY
```

## Release Hygiene

- Update `CHANGELOG.md`.
- Review the packaged release-trust docs:
  `src/async_research_workflow/docs/release_trust_hardening_report.md`,
  `src/async_research_workflow/docs/scaling_guidance.md`, and
  `src/async_research_workflow/docs/worked_examples_index.md`.
- Confirm `roadmaps/delivered_public_alpha_hardening_roadmap.md` reflects the release state.
- Confirm GitHub description, topics, and release notes are ready.
- Tag only after the source checks, build checks, installed-wheel smokes, and
  packaged-resource smoke pass.
