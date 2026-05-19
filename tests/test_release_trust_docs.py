"""Regression tests for release-trust documentation."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "src" / "async_research_workflow" / "docs"


def normalized(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


class ReleaseTrustDocsTests(unittest.TestCase):
    def assert_contains(self, path: Path, snippets: list[str]) -> None:
        text = normalized(path)
        for snippet in snippets:
            self.assertIn(" ".join(snippet.split()), text, f"missing {snippet!r} from {path}")

    def test_release_trust_docs_are_linked_from_public_indexes(self) -> None:
        root_readme = normalized(ROOT / "README.md")
        docs_index = normalized(DOCS / "README.md")

        for snippet in [
            "[Release-trust hardening report](src/async_research_workflow/docs/release_trust_hardening_report.md)",
            "[Scaling guidance](src/async_research_workflow/docs/scaling_guidance.md)",
            "[Worked examples index](src/async_research_workflow/docs/worked_examples_index.md)",
        ]:
            self.assertIn(" ".join(snippet.split()), root_readme)

        for snippet in [
            "[Release-Trust Hardening Report](./release_trust_hardening_report.md)",
            "[Scaling Guidance](./scaling_guidance.md)",
            "[Worked Examples Index](./worked_examples_index.md)",
        ]:
            self.assertIn(" ".join(snippet.split()), docs_index)

    def test_hardening_report_distinguishes_local_evidence_from_release_claims(self) -> None:
        self.assert_contains(
            DOCS / "release_trust_hardening_report.md",
            [
                "It is not a PyPI release note, GitHub release note, security audit, or public claim that a release was published.",
                "Treat a capability as current evidence only when the relevant command has passed in the clone or installed environment being evaluated.",
                ".venv/bin/python -m unittest tests.test_doc_references",
                ".venv/bin/python -m unittest tests.test_docs_packaging",
                ".venv/bin/python -m unittest discover -s tests",
                ".venv/bin/async-research acceptance-suite",
                ".venv/bin/python -m build",
                "default dry-run proposal inspection and guarded data/library proposal apply commands with accepted proof, matching preflight hashes, locks, rollback, and post-write validation",
                "dashboard and console snapshot read models that prefer `unavailable` or structured findings over inferred or silently repaired state",
                "Human owners still decide release timing, version numbers, public positioning, license policy changes",
                "Publishing to PyPI, creating GitHub releases, and announcing public readiness remain manual actions outside the CLI.",
            ],
        )

    def test_scaling_guidance_names_file_backed_boundaries(self) -> None:
        self.assert_contains(
            DOCS / "scaling_guidance.md",
            [
                "tens to low hundreds of active or archived task folders",
                "Most read models deliberately scan files on demand.",
                "missing timestamps, links, or cost rows render as `unavailable` rather than being inferred from prose",
                "Split into separate `research_ops/` workspaces when any of these become true",
                "Move beyond the file-backed alpha pattern when local scans and Git review stop being the right control plane.",
                "thousands of active tasks or ideas",
                "slow cadence is a safety feature",
            ],
        )

    def test_worked_examples_index_points_to_runnable_packaged_examples(self) -> None:
        self.assert_contains(
            DOCS / "worked_examples_index.md",
            [
                "Copy examples to a temporary directory before experimenting with write-capable commands.",
                "async_research_workflow/templates/generic_research_ops_starter/research_ops/",
                "async_research_workflow/templates/research_ops_starter/research_ops/",
                "async_research_workflow/examples/runnable_experiment_analysis/",
                "from async_research_workflow.resources import examples_path",
                "async_research_workflow/examples/coffee_pilot_deliverable_maturity/",
                "The expected first check exits nonzero because the fixture is deliberately below working-paper readiness.",
                "async_research_workflow/examples/github_actions_codex_worker.yml",
                "The packaged examples do not prove real-world research validity, publication readiness, external data access, statistical generality, or production scale.",
            ],
        )

    def test_release_checklist_keeps_publishing_human_owned(self) -> None:
        self.assert_contains(
            ROOT / "RELEASE_CHECKLIST.md",
            [
                "Local verification is necessary but not sufficient for publication.",
                "Do not publish to PyPI, create a GitHub release, tag a release, or announce public readiness until a human owner explicitly chooses the version, timing, and release notes.",
                "Review the packaged release-trust docs",
                "release_trust_hardening_report.md",
                "scaling_guidance.md",
                "worked_examples_index.md",
            ],
        )


if __name__ == "__main__":
    unittest.main()
