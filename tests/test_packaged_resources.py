"""Regression tests for packaged schemas, policies, and starter resources."""

from __future__ import annotations

import re
import unittest
from importlib import resources as importlib_resources
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "src" / "async_research_workflow"
RUNTIME_CODE = [PACKAGE_ROOT / "cli.py", *sorted((PACKAGE_ROOT / "scripts").glob("*.py"))]
LIBRARY_STARTER_FILES = [
    "source_library.md",
    "knowledge_index.md",
    "claim_map.md",
    "method_index.md",
    "open_questions.md",
    "library_update_log.md",
]


def text_files(root: Path) -> list[Path]:
    suffixes = {".csv", ".json", ".jsonl", ".md"}
    return sorted(path for path in root.rglob("*") if path.is_file() and path.suffix in suffixes)


class PackagedResourceTests(unittest.TestCase):
    def test_duplicate_runtime_resources_are_not_packaged(self) -> None:
        forbidden = [
            *sorted(PACKAGE_ROOT.glob("*.schema.json")),
            PACKAGE_ROOT / "examples" / "mission_policy.json",
            PACKAGE_ROOT / "examples" / "benchmarks" / "autonomy_benchmark_cases.json",
        ]
        present = [str(path.relative_to(PACKAGE_ROOT)) for path in forbidden if path.exists()]

        self.assertEqual([], present)

    def test_runtime_code_uses_canonical_resource_helpers(self) -> None:
        patterns = [
            re.compile(r"Path\(__file__\)\.resolve\(\)\.parents\[1\]\s*/\s*[\"'][^\"']+\.schema\.json[\"']"),
            re.compile(r"Path\(__file__\)\.resolve\(\)\.parents\[1\]\s*/\s*[\"']mission_policy\.json[\"']"),
            re.compile(r"resources\.files\([\"']async_research_workflow[\"']\)"),
            re.compile(r"EXAMPLES_DIR\s*/\s*[\"']benchmarks[\"']"),
            re.compile(r"EXAMPLES_DIR\s*/\s*[\"']mission_policy\.json[\"']"),
        ]
        hits: list[str] = []
        for path in RUNTIME_CODE:
            if path.name == "resources.py":
                continue
            text = path.read_text(encoding="utf-8")
            for pattern in patterns:
                if pattern.search(text):
                    hits.append(f"{path.relative_to(PACKAGE_ROOT)} matches {pattern.pattern!r}")

        self.assertEqual([], hits)

    def test_key_resources_are_available_via_importlib_resources(self) -> None:
        package = importlib_resources.files("async_research_workflow")
        required = [
            ("schemas", "task_status.schema.json"),
            ("schemas", "experiment_plan.schema.json"),
            ("schemas", "analysis_run.schema.json"),
            ("schemas", "analysis_metrics.schema.json"),
            ("schemas", "analysis_diagnostics.schema.json"),
            ("schemas", "analysis_robustness_checks.schema.json"),
            ("schemas", "analysis_claim_gates.schema.json"),
            ("schemas", "delivered_project.schema.json"),
            ("schemas", "delivered_projects_summary.schema.json"),
            ("benchmarks", "autonomy_benchmark_cases.json"),
            ("console", "static", "index.html"),
            ("console", "static", "styles.css"),
            ("console", "static", "app.js"),
            ("templates", "artifact_templates", "task_template.md"),
            ("templates", "artifact_templates", "analysis_run_manifest_template.md"),
            ("templates", "artifact_templates", "analysis_metrics_template.md"),
            ("templates", "artifact_templates", "analysis_diagnostics_template.md"),
            ("templates", "artifact_templates", "analysis_robustness_checks_template.md"),
            ("templates", "artifact_templates", "analysis_claim_gates_template.md"),
            ("templates", "generic_research_ops_starter", "research_ops", "README.md"),
            ("templates", "generic_research_ops_starter", "research_ops", "ideas", "idea_catalog.md"),
            ("templates", "generic_research_ops_starter", "research_ops", "ideas", "prioritization.md"),
            ("templates", "generic_research_ops_starter", "research_ops", "data", "data_catalog.md"),
            ("templates", "generic_research_ops_starter", "research_ops", "data", "profiles", "README.md"),
            ("templates", "generic_research_ops_starter", "research_ops", "tasks", ".gitkeep"),
            ("templates", "research_ops_starter", "research_ops", "README.md"),
            ("templates", "research_ops_starter", "research_ops", "ideas", "idea_catalog.md"),
            ("templates", "research_ops_starter", "research_ops", "ideas", "prioritization.md"),
            ("templates", "research_ops_starter", "research_ops", "data", "data_catalog.md"),
            ("templates", "research_ops_starter", "research_ops", "data", "profiles", "README.md"),
            ("templates", "research_ops_starter", "research_ops", "data", "profiles", "DS-0001.md"),
            ("templates", "research_ops_starter", "research_ops", "tasks", "TASK-0001-data-readiness", "status.json"),
            ("docs", "idea_catalog_contract.md"),
            ("docs", "knowledge_library_contract.md"),
            ("examples", "github_actions_codex_worker.yml"),
            ("mission_policy.json",),
        ]
        required.extend(
            ("templates", template, "research_ops", "library", filename)
            for template in ("generic_research_ops_starter", "research_ops_starter")
            for filename in LIBRARY_STARTER_FILES
        )

        missing = [
            "/".join(parts)
            for parts in required
            if not package.joinpath(*parts).is_file()
        ]
        self.assertEqual([], missing)

    def test_console_static_outcomes_preserves_rejected_ledger_visibility(self) -> None:
        static_dir = PACKAGE_ROOT / "console" / "static"
        html = (static_dir / "index.html").read_text(encoding="utf-8")
        app = (static_dir / "app.js").read_text(encoding="utf-8")

        self.assertIn('id="rejected-ledger"', html)
        self.assertIn('id="rejected-ledger-total"', html)
        self.assertIn('id="prompts"', html)
        self.assertIn('id="schedules"', html)
        self.assertIn('id="schedule-init"', html)
        self.assertIn('"prompt-editor"', app)
        self.assertIn("function renderRejectedLedger", app)
        self.assertIn("function renderPrompts", app)
        self.assertIn("function runPromptActivate", app)
        self.assertIn("function renderSchedules", app)
        self.assertIn("function runScheduleSave", app)
        self.assertIn("function runScheduleTriggerDryRun", app)
        self.assertIn("Preview Trigger", app)
        self.assertIn("function validationIssueText", app)
        self.assertIn("Validation Details", app)
        self.assertIn("snapshot.rejected_results", app)
        self.assertIn("snapshot.prompts", app)
        self.assertIn("snapshot.schedules", app)
        self.assertIn('renderList("rejected-ledger"', app)
        self.assertIn('value.join(", ")', app)

    def test_generic_starter_is_domain_neutral_and_empty(self) -> None:
        starter = PACKAGE_ROOT / "templates" / "generic_research_ops_starter" / "research_ops"
        forbidden = [
            "real-estate",
            "real estate",
            "hm land registry",
            "bank of england",
            "office for national statistics",
            "mortgage",
            "property",
            "housing",
            "house price",
        ]
        forbidden_patterns = [re.compile(r"\bons\b")]
        hits: list[str] = []
        for path in text_files(starter):
            text = path.read_text(encoding="utf-8").lower()
            for term in forbidden:
                if term in text:
                    hits.append(f"{path.relative_to(PACKAGE_ROOT)} contains {term!r}")
            for pattern in forbidden_patterns:
                if pattern.search(text):
                    hits.append(f"{path.relative_to(PACKAGE_ROOT)} matches {pattern.pattern!r}")

        self.assertEqual([], hits)
        self.assertFalse((starter / "health_report.json").exists())
        self.assertEqual([], list((starter / "tasks").glob("*/status.json")))

    def test_real_estate_starter_remains_explicit_worked_example(self) -> None:
        starter = PACKAGE_ROOT / "templates" / "research_ops_starter" / "research_ops"

        self.assertTrue((starter / "tasks" / "TASK-0001-data-readiness" / "status.json").exists())
        self.assertTrue((starter / "health_report.json").exists())
        text = (starter / "README.md").read_text(encoding="utf-8").lower()
        self.assertIn("real-estate", text)


if __name__ == "__main__":
    unittest.main()
