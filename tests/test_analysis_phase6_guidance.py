"""Regression tests for Phase 6 analysis task and prompt guidance."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "src" / "async_research_workflow" / "docs"
TEMPLATES = ROOT / "src" / "async_research_workflow" / "templates" / "artifact_templates"


def normalized(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


class AnalysisPhase6GuidanceTests(unittest.TestCase):
    def assert_contains(self, path: Path, snippets: list[str]) -> None:
        text = normalized(path)
        for snippet in snippets:
            self.assertIn(" ".join(snippet.split()), text, f"missing {snippet!r} from {path}")

    def test_task_template_guides_run_analysis_and_evaluate_results_workers(self) -> None:
        self.assert_contains(
            TEMPLATES / "task_template.md",
            [
                "Do not upgrade `claim_strength` after seeing attractive results",
                "For `run_analysis` tasks, the task context must name the accepted plan: `accepted_plan_task_id`, `experiment_plan_id`, `accepted_plan_path`, and `accepted_plan_result_acceptance_path`.",
                "For `run_analysis` tasks, write every output inside this task folder",
                "write `claim_gates.json` even when `claim_strength` is `none`",
                "`async-research analysis preflight <task-dir> --ops-dir research_ops`",
                "`async-research analysis validate-run <task-dir> --ops-dir research_ops`",
                "`async-research analysis validate-results <task-dir> --ops-dir research_ops`",
                "For `evaluate_results` tasks, do not rerun or silently reinterpret the analysis.",
                "`async-research analysis validate-results <upstream-run-analysis-task-dir> --ops-dir research_ops`",
            ],
        )

    def test_result_summary_template_points_to_manifest_and_metrics(self) -> None:
        self.assert_contains(
            TEMPLATES / "result_summary_template.md",
            [
                "For `run_analysis`, `run_manifest_path` must point at the same task's canonical `artifacts/analysis_run/run_manifest.json`.",
                "For `evaluate_results`, it must point at the upstream analysis run being evaluated.",
                "Keep `primary_metric`, `baseline_results`, `candidate_results`, and `validation_split_results` consistent with the structured `metrics.json`",
                "do not use this summary to upgrade the accepted plan's claim strength after seeing favorable results",
            ],
        )

    def test_scheduler_prompts_cover_planner_worker_and_result_reviewers(self) -> None:
        self.assert_contains(
            DOCS / "scheduler_and_prompts.md",
            [
                "For accepted `experiment_plan` outputs selected for execution, create at most one bounded `run_analysis` task only when the accepted_outputs_index row is current",
                "accepted_plan_task_id, experiment_plan_id, accepted_plan_path, accepted_plan_result_acceptance_path",
                "The `run_analysis` status.json must set type=\"run_analysis\", status=\"ready_for_worker\"",
                "Use Tier 3 when the planned result is causal, probabilistic, public, high-stakes, high-impact, or likely to request moderate/strong claim strength.",
                "Do not create `run_analysis` tasks from discovery, catalog ideas, or hypothesis cards without an accepted `experiment_plan` in between.",
                "For `run_analysis` tasks, read the accepted plan references from task.md/status.json",
                "Always run async-research analysis validate-run <task-dir> --ops-dir research_ops before review",
                "Whenever worker_output.md includes a result summary, write claim_gates.json even for claim_strength=\"none\" and run async-research analysis validate-results <task-dir> --ops-dir research_ops.",
                "Resolve the upstream run_analysis task directory from run_manifest_path, then run async-research analysis validate-run <upstream-run-analysis-task-dir> --ops-dir research_ops and async-research analysis validate-results <upstream-run-analysis-task-dir> --ops-dir research_ops before review",
                "## Result Reviewer Prompt",
                "For `run_analysis` with a result summary, require claim_gates.json and run async-research analysis validate-results <task-dir> --ops-dir research_ops.",
                "Hard gate failures from public CLI validation route to revision, rejection, or needs_human; they are not waived in prose.",
            ],
        )

    def test_task_contracts_define_accepted_plan_to_analysis_review_loop(self) -> None:
        self.assert_contains(
            DOCS / "task_contracts.md",
            [
                "Planner-created `run_analysis` tasks are allowed only from an accepted `experiment_plan` whose result acceptance record is current.",
                "accepted_plan_task_id experiment_plan_id accepted_plan_path accepted_plan_result_acceptance_path source_ids planned candidate/baseline/metric refs planned artifacts/analysis_run/ output paths",
                "If the result may be moderate, strong, public, high-stakes, high-impact, causal, or probabilistic, the planner should require Tier 3 or route to human review.",
                "Do not create `run_analysis` tasks from discovery, idea catalog, or hypothesis-card records without an accepted experiment plan in between.",
                "Workers may only run the accepted plan named by the manifest.",
                "Reviewer checklist for `run_analysis` and `evaluate_results`",
                "`claim_gates.json` matches the current result summary and structured artifacts.",
                "A `run_analysis` result summary always has `claim_gates.json`, including summaries with `claim_strength: \"none\"`, and `analysis validate-results` has been run against the same task directory.",
                "An `evaluate_results` review reruns `analysis validate-run` and `analysis validate-results` against the upstream `run_analysis` task directory cited by `run_manifest_path`.",
            ],
        )

    def test_analysis_prompt_guidance_uses_public_cli_commands(self) -> None:
        combined = "\n".join(
            normalized(path)
            for path in (
                TEMPLATES / "task_template.md",
                TEMPLATES / "result_summary_template.md",
                DOCS / "scheduler_and_prompts.md",
                DOCS / "task_contracts.md",
            )
        )
        for command in [
            "async-research analysis preflight",
            "async-research analysis validate-run",
            "async-research analysis validate-results",
        ]:
            self.assertIn(command, combined)

        for forbidden in [
            "python -m async_research_workflow.scripts.analysis_runs",
            "python -m async_research_workflow.scripts.analysis_validation",
            "async_research_workflow/scripts/analysis_runs.py",
            "async_research_workflow/scripts/analysis_validation.py",
        ]:
            self.assertNotIn(forbidden, combined)

    def test_result_validation_cannot_be_conditionally_skipped(self) -> None:
        combined = "\n".join(
            normalized(path)
            for path in (
                TEMPLATES / "task_template.md",
                DOCS / "scheduler_and_prompts.md",
            )
        )
        for required in [
            "write `claim_gates.json` even when `claim_strength` is `none`",
            "If `worker_output.md` includes a result summary, also run `async-research analysis validate-results <task-dir> --ops-dir research_ops`.",
            "For `run_analysis` with a result summary, require claim_gates.json and run async-research analysis validate-results <task-dir> --ops-dir research_ops.",
        ]:
            self.assertIn(" ".join(required.split()), combined)

        for forbidden in [
            "validate-results <task-dir> --ops-dir research_ops when result summary plus claim_gates.json are present",
            "validate-results <task-dir> --ops-dir research_ops when result summary plus claim_gates.json",
            "with a result summary and claim_gates.json, run async-research analysis validate-results",
            "If a result summary and `claim_gates.json` are present",
            "write claim_gates.json when making a result claim",
            "write `claim_gates.json` when making a result claim",
        ]:
            self.assertNotIn(" ".join(forbidden.split()), combined)


if __name__ == "__main__":
    unittest.main()
