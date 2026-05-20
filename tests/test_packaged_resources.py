"""Regression tests for packaged schemas, policies, and starter resources."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
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
DELIVERABLE_TEMPLATE_FILES = [
    "README.md",
    "deliverable_manifest_template.json",
    "manuscript_readiness_checklist.md",
    "critic_review_prompt.md",
    "review_response_matrix.md",
    "internal_draft_assembly_task.md",
    "shareable_memo_polish_task.md",
    "working_paper_revision_task.md",
    "submission_ready_manuscript_cleanup_task.md",
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
            ("schemas", "runtime_evidence_object.schema.json"),
            ("schemas", "runtime_trace.schema.json"),
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
            ("templates", "artifact_templates", "deliverable_manifest_template.json"),
            ("templates", "artifact_templates", "deliverable_manifest_template.md"),
            ("templates", "artifact_templates", "manuscript_readiness_checklist_template.md"),
            ("templates", "artifact_templates", "critic_review_prompt_template.md"),
            ("templates", "artifact_templates", "review_response_matrix_template.md"),
            ("templates", "artifact_templates", "internal_draft_assembly_task_template.md"),
            ("templates", "artifact_templates", "shareable_memo_polish_task_template.md"),
            ("templates", "artifact_templates", "working_paper_revision_task_template.md"),
            ("templates", "artifact_templates", "submission_ready_manuscript_cleanup_task_template.md"),
            ("templates", "generic_research_ops_starter", "research_ops", "README.md"),
            ("templates", "generic_research_ops_starter", "research_ops", "ideas", "idea_catalog.md"),
            ("templates", "generic_research_ops_starter", "research_ops", "ideas", "prioritization.md"),
            ("templates", "generic_research_ops_starter", "research_ops", "data", "data_catalog.md"),
            ("templates", "generic_research_ops_starter", "research_ops", "data", "profiles", "README.md"),
            ("templates", "generic_research_ops_starter", "research_ops", "deliverables", "templates", "README.md"),
            ("templates", "generic_research_ops_starter", "research_ops", "runtime", "README.md"),
            ("templates", "generic_research_ops_starter", "research_ops", "runtime", "snapshots", ".gitkeep"),
            ("templates", "generic_research_ops_starter", "research_ops", "tasks", ".gitkeep"),
            ("templates", "research_ops_starter", "research_ops", "README.md"),
            ("templates", "research_ops_starter", "research_ops", "ideas", "idea_catalog.md"),
            ("templates", "research_ops_starter", "research_ops", "ideas", "prioritization.md"),
            ("templates", "research_ops_starter", "research_ops", "data", "data_catalog.md"),
            ("templates", "research_ops_starter", "research_ops", "data", "profiles", "README.md"),
            ("templates", "research_ops_starter", "research_ops", "data", "profiles", "DS-0001.md"),
            ("templates", "research_ops_starter", "research_ops", "deliverables", "templates", "README.md"),
            ("templates", "research_ops_starter", "research_ops", "runtime", "README.md"),
            ("templates", "research_ops_starter", "research_ops", "runtime", "snapshots", ".gitkeep"),
            ("templates", "research_ops_starter", "research_ops", "tasks", "TASK-0001-data-readiness", "status.json"),
            ("docs", "idea_catalog_contract.md"),
            ("docs", "knowledge_library_contract.md"),
            ("docs", "runtime_artifacts.md"),
            ("examples", "github_actions_codex_worker.yml"),
            ("examples", "runnable_experiment_analysis", "README.md"),
            ("examples", "runnable_experiment_analysis", "analysis_scripts", "write_fixture_marker.py"),
            ("examples", "runnable_experiment_analysis", "expected", "analysis_dashboard.json"),
            ("examples", "runnable_experiment_analysis", "research_ops", "data_source_audit.md"),
            ("examples", "runnable_experiment_analysis", "research_ops", "data", "profiles", "README.md"),
            ("examples", "runnable_experiment_analysis", "research_ops", "tasks", "TASK-8001-experiment-plan", "worker_output.md"),
            (
                "examples",
                "runnable_experiment_analysis",
                "research_ops",
                "tasks",
                "TASK-8002-run-analysis",
                "artifacts",
                "analysis_run",
                "run_manifest.json",
            ),
            (
                "examples",
                "runnable_experiment_analysis",
                "research_ops",
                "tasks",
                "TASK-8003-completed-analysis",
                "artifacts",
                "analysis_run",
                "run_manifest.json",
            ),
            (
                "examples",
                "runnable_experiment_analysis",
                "research_ops",
                "tasks",
                "TASK-8003-completed-analysis",
                "review_panel",
                "result_acceptance.json",
            ),
            ("examples", "coffee_pilot_deliverable_maturity", "README.md"),
            (
                "examples",
                "coffee_pilot_deliverable_maturity",
                "research_ops",
                "deliverables",
                "deliverable_manifest.json",
            ),
            (
                "examples",
                "coffee_pilot_deliverable_maturity",
                "research_ops",
                "tasks",
                "TASK-0015-internal-draft-assembly",
                "status.json",
            ),
            ("mission_policy.json",),
        ]
        required.extend(
            ("templates", template, "research_ops", "library", filename)
            for template in ("generic_research_ops_starter", "research_ops_starter")
            for filename in LIBRARY_STARTER_FILES
        )
        required.extend(
            ("templates", template, "research_ops", "deliverables", "templates", filename)
            for template in ("generic_research_ops_starter", "research_ops_starter")
            for filename in DELIVERABLE_TEMPLATE_FILES
        )

        missing = [
            "/".join(parts)
            for parts in required
            if not package.joinpath(*parts).is_file()
        ]
        self.assertEqual([], missing)

    def test_deliverable_templates_explain_maturity_boundary(self) -> None:
        starter = PACKAGE_ROOT / "templates" / "generic_research_ops_starter" / "research_ops" / "deliverables" / "templates"
        critic = (starter / "critic_review_prompt.md").read_text(encoding="utf-8")
        draft = (starter / "internal_draft_assembly_task.md").read_text(encoding="utf-8")
        matrix = (starter / "review_response_matrix.md").read_text(encoding="utf-8")

        self.assertIn("Do not treat accepted source tasks as evidence of external readiness.", critic)
        self.assertIn("--response-matrix-row", critic)
        self.assertIn("accepted internal draft; external readiness requires deliverable gates", draft)
        self.assertIn("Critical and major rows must be closed", matrix)

    def test_console_static_outcomes_preserves_rejected_ledger_visibility(self) -> None:
        static_dir = PACKAGE_ROOT / "console" / "static"
        html = (static_dir / "index.html").read_text(encoding="utf-8")
        app = (static_dir / "app.js").read_text(encoding="utf-8")
        styles = (static_dir / "styles.css").read_text(encoding="utf-8")

        self.assertIn('id="rejected-ledger"', html)
        self.assertIn('id="rejected-ledger-total"', html)
        self.assertIn('id="prompts"', html)
        self.assertIn('id="schedules"', html)
        self.assertIn('id="schedule-init"', html)
        self.assertIn('id="auto-refresh-toggle"', html)
        self.assertIn('id="auto-refresh-interval"', html)
        self.assertIn('id="refresh-status"', html)
        self.assertIn('id="lifecycle"', html)
        self.assertIn('id="lifecycle-map"', html)
        self.assertIn('id="lifecycle-current"', html)
        self.assertIn('id="deliverables"', html)
        self.assertIn('id="deliverable-list"', html)
        self.assertIn('id="deliverable-attention"', html)
        self.assertIn('id="operations"', html)
        self.assertIn('id="cost-ledger"', html)
        self.assertIn('id="cost-task-drilldown"', html)
        self.assertIn('id="cost-role-drilldown"', html)
        self.assertIn('id="cost-model-drilldown"', html)
        self.assertIn('id="source-attention"', html)
        self.assertIn('id="health-alerts"', html)
        self.assertIn('id="idea-drilldown"', html)
        self.assertIn('id="library-drilldown"', html)
        self.assertIn('id="idea-foundation-links"', html)
        self.assertIn('id="library-foundation-links"', html)
        self.assertIn("asyncResearchAutoRefreshEnabled", app)
        self.assertIn("function scheduleAutoRefresh", app)
        self.assertIn("function artifactHref", app)
        self.assertIn("function renderLifecycle", app)
        self.assertIn("function ideaDrilldownRows", app)
        self.assertIn("function libraryDrilldownRows", app)
        self.assertIn("function taskExplainabilityPanel", app)
        self.assertIn("function taskQaPanel", app)
        self.assertIn("Task Explanation", app)
        self.assertIn("Review And QA", app)
        self.assertIn("reviewer_confidence", app)
        self.assertIn("lifecycle.stations", app)
        self.assertIn("viewer_url", app)
        self.assertNotIn("file://", app)
        self.assertIn('document.createElement("span")', app)
        self.assertIn(".auto-refresh-control", styles)
        self.assertIn(".auto-refresh-interval", styles)
        self.assertIn(".refresh-status", styles)
        self.assertIn(".lifecycle-map", styles)
        self.assertIn(".lifecycle-station", styles)
        self.assertIn(".foundation-detail-grid", styles)
        self.assertIn(".foundation-panel", styles)
        self.assertIn(".task-insight-panel", styles)
        self.assertIn(".insight-list", styles)
        self.assertIn('"prompt-editor"', app)
        self.assertIn("function renderRejectedLedger", app)
        self.assertIn("function renderPrompts", app)
        self.assertIn("function runPromptActivate", app)
        self.assertIn("function renderSchedules", app)
        self.assertIn("function renderOperations", app)
        self.assertIn("function runScheduleSave", app)
        self.assertIn("function runScheduleTriggerDryRun", app)
        self.assertIn("function runScheduleTriggerNow", app)
        self.assertIn("Preview Trigger", app)
        self.assertIn("Run Now", app)
        self.assertIn("function validationIssueText", app)
        self.assertIn("Validation Details", app)
        self.assertIn("snapshot.rejected_results", app)
        self.assertIn("snapshot.prompts", app)
        self.assertIn("snapshot.schedules", app)
        self.assertIn("snapshot.sources", app)
        self.assertIn("snapshot.lifecycle", app)
        self.assertIn('renderList("rejected-ledger"', app)
        self.assertIn('renderList("cost-task-drilldown"', app)
        self.assertIn("snapshot.library", app)
        self.assertIn("snapshot.ideas", app)
        self.assertIn("renderDeliverables(snapshot)", app)
        self.assertIn("accepted source tasks", app)
        self.assertIn('renderList("source-attention"', app)
        self.assertIn("function sourceActionSummary", app)
        self.assertIn("cost.top_spend_rows.length > 0", app)
        self.assertIn('value.join(", ")', app)

    def test_console_artifact_href_helper_prefers_viewer_routes(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not available")

        app_js = PACKAGE_ROOT / "console" / "static" / "app.js"
        cases = [
            [{"viewer_url": "/artifacts/tasks/TASK-1/worker_output.md", "raw_url": "/artifacts/tasks/TASK-1/worker_output.md?raw=1", "download_url": "/artifacts/tasks/TASK-1/worker_output.md?download=1"}, "view", "/artifacts/tasks/TASK-1/worker_output.md"],
            [{"viewer_url": "/artifacts/tasks/TASK-1/worker_output.md", "raw_url": "/artifacts/tasks/TASK-1/worker_output.md?raw=1"}, "raw", "/artifacts/tasks/TASK-1/worker_output.md?raw=1"],
            [{"viewer_url": "/artifacts/tasks/TASK-1/worker_output.md", "download_url": "/artifacts/tasks/TASK-1/worker_output.md?download=1"}, "download", "/artifacts/tasks/TASK-1/worker_output.md?download=1"],
            [{"path": "/tmp/worker_output.md"}, "view", ""],
        ]
        script = """
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync(process.argv[1], "utf8");
const cases = JSON.parse(process.argv[2]);
const context = {
  window: {
    localStorage: {
      getItem() { return null; },
      setItem() {},
    },
    clearTimeout() {},
    setTimeout() { return 0; },
  },
  document: {
    addEventListener() {},
    getElementById() { return null; },
  },
};
vm.runInNewContext(`${source}\\nthis.__artifactHref = artifactHref;`, context);
for (const [input, mode, expected] of cases) {
  const actual = context.__artifactHref(input, mode);
  if (actual !== expected) {
    console.error(`${JSON.stringify(input)}: expected ${expected}, got ${actual}`);
    process.exit(1);
  }
}
"""
        completed = subprocess.run(
            [node, "-e", script, str(app_js), json.dumps(cases)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual("", completed.stderr)
        self.assertEqual(0, completed.returncode, completed.stdout)

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
