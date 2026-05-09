"""Regression tests for documentation and starter package references."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "src" / "async_research_workflow"

TOP_LEVEL_DOCS = [
    ROOT / "README.md",
]
DOC_TREES = [
    ROOT / ".github",
    ROOT / "roadmaps",
    PACKAGE_ROOT / "docs",
    PACKAGE_ROOT / "examples",
    PACKAGE_ROOT / "templates",
]
TEXT_SUFFIXES = {".csv", ".json", ".md", ".txt", ".yml", ".yaml"}
FORBIDDEN_SNIPPETS = (
    "async_research_workflow/examples/scripts/",
    "examples/scripts/",
    "blob/main/ROADMAP.md",
)
EXAMPLES_REF_RE = re.compile(r"async_research_workflow/examples/[A-Za-z0-9_./-]+")
RELATIVE_EXAMPLES_REF_RE = re.compile(r"(?<!async_research_workflow/)examples/[A-Za-z0-9_./-]+")
SCRIPT_REF_RE = re.compile(r"async_research_workflow/scripts/[A-Za-z0-9_./-]+\.py")
ROOT_SCHEMA_REF_RE = re.compile(r"async_research_workflow/[A-Za-z0-9_]+\.schema\.json")
REMOVED_EXAMPLE_RESOURCE_RE = re.compile(
    r"async_research_workflow/examples/(?:mission_policy\.json|benchmarks/autonomy_benchmark_cases\.json)"
)
PUBLIC_CLI_ADVANCED_REF_PATTERNS = {
    "cost_tracking": re.compile(
        r"(?:python -m\s+async_research_workflow\.scripts\.cost_tracking\s+\\?\s*|cost_tracking\.py\s+)(?:summary|ingest-usage|budget-check)\b"
    ),
    "cost_tracking_helper_path": re.compile(
        r"(?:async_research_workflow/scripts/cost_tracking\.py|cost_tracking\.py\b)"
    ),
    "update_accepted_outputs_index": re.compile(
        r"(?:python -m\s+async_research_workflow\.scripts\.update_accepted_outputs_index\s+\\?\s*|update_accepted_outputs_index\.py\s+)(?:check-duplicate|check-memory-use)\b"
    ),
    "update_accepted_outputs_index_helper_path": re.compile(
        r"(?:async_research_workflow/scripts/update_accepted_outputs_index\.py|update_accepted_outputs_index\.py\b)"
    ),
    "data_source_audit": re.compile(
        r"(?:python -m\s+async_research_workflow\.scripts\.data_source_audit\s+\\?\s*|data_source_audit\.py\s+)(?:init|upsert|check-experiment|check-claim|explain|freshness-report)\b"
    ),
    "batch_lifecycle": re.compile(
        r"(?:python -m\s+async_research_workflow\.scripts\.batch_lifecycle\s+\\?\s*|batch_lifecycle\.py\s+)(?:init|validate-manifest|submit|complete|ingest|mark-reviewed|trust-status)\b"
    ),
    "revision_counter": re.compile(
        r"(?:python -m\s+async_research_workflow\.scripts\.revision_counter\s+\\?\s*|revision_counter\.py\s+)(?:defaults|request|inspect|scan-limits)\b"
    ),
    "generate_anti_context": re.compile(
        r"(?:python -m\s+async_research_workflow\.scripts\.generate_anti_context\s+\\?\s*|generate_anti_context\.py\s+)build\b"
    ),
    "prepare_review_context": re.compile(
        r"(?:python -m\s+async_research_workflow\.scripts\.prepare_review_context\s+\\?\s*|prepare_review_context\.py\s+)(?:prepare|install)\b"
    ),
    "metrics_history": re.compile(
        r"(?:python -m\s+async_research_workflow\.scripts\.metrics_history\s+\\?\s*|metrics_history\.py\s+)summarize\b"
    ),
    "queue_capacity": re.compile(
        r"(?:python -m\s+async_research_workflow\.scripts\.queue_capacity\s+\\?\s*|queue_capacity\.py\s+)discovery-gate\b"
    ),
    "human_decision_log": re.compile(
        r"(?:python -m\s+async_research_workflow\.scripts\.human_decision_log\s+\\?\s*|human_decision_log\.py\s+)(?:append|check|resolve-task|summarize)\b|async_research_workflow/scripts/human_decision_log\.py|human_decision_log\.py\b"
    ),
    "escalation_policy": re.compile(
        r"(?:python -m\s+async_research_workflow\.scripts\.escalation_policy\s+\\?\s*|escalation_policy\.py\s+)(?:list|scan-needs-human|evaluate)\b|async_research_workflow/scripts/escalation_policy\.py"
    ),
    "health_check": re.compile(
        r"python -m\s+async_research_workflow\.scripts\.health_check\b"
    ),
    "run_acceptance_suite": re.compile(
        r"python -m\s+async_research_workflow\.scripts\.run_acceptance_suite\b"
    ),
}
INTERNAL_HELPER_MODULES = (
    "validate_json_artifact",
    "validate_transition",
    "validate_mission_policy",
    "task_lock",
    "recover_status_json",
    "review_template",
    "framework_version_calibration",
    "escalate_review_tier",
)
INTERNAL_HELPER_DIRECT_INVOCATION_RE = re.compile(
    r"python -m\s+async_research_workflow\.scripts\.(?:"
    + "|".join(re.escape(name) for name in INTERNAL_HELPER_MODULES)
    + r"|metrics_history)\b"
)
INTERNAL_HELPER_LABELS = ("advanced/internal", "internal helper", "advanced helper")
ROADMAP_STATUS_PREFIXES = {
    "delivered_": "Delivered",
    "in_progress_": "In Progress",
    "not_started_": "Not Started",
    "blocked_": "Blocked",
    "paused_": "Paused",
    "superseded_": "Superseded",
}


def iter_documentation_files() -> list[Path]:
    files = list(TOP_LEVEL_DOCS)
    for tree in DOC_TREES:
        files.extend(
            path
            for path in tree.rglob("*")
            if path.is_file() and path.suffix in TEXT_SUFFIXES
        )
    return sorted(set(files))


def clean_reference(raw: str) -> str:
    return raw.rstrip("`'\".,:;)]}")


def has_internal_helper_label(lines: list[str], index: int) -> bool:
    start = max(0, index - 4)
    end = min(len(lines), index + 2)
    context = "\n".join(lines[start:end]).lower()
    return any(label in context for label in INTERNAL_HELPER_LABELS)


class DocumentationReferenceTests(unittest.TestCase):
    def test_docs_do_not_use_removed_or_stale_paths(self) -> None:
        failures: list[str] = []
        for path in iter_documentation_files():
            text = path.read_text(encoding="utf-8")
            for snippet in FORBIDDEN_SNIPPETS:
                if snippet in text:
                    failures.append(f"{path.relative_to(ROOT)} contains {snippet}")

        self.assertEqual([], failures)

    def test_examples_package_references_exist(self) -> None:
        failures: list[str] = []
        for path in iter_documentation_files():
            text = path.read_text(encoding="utf-8")
            for match in EXAMPLES_REF_RE.finditer(text):
                reference = clean_reference(match.group(0))
                package_path = ROOT / "src" / reference
                if not package_path.exists():
                    line = text.count("\n", 0, match.start()) + 1
                    failures.append(f"{path.relative_to(ROOT)}:{line} -> {reference}")
            for match in RELATIVE_EXAMPLES_REF_RE.finditer(text):
                reference = clean_reference(match.group(0))
                package_path = PACKAGE_ROOT / reference
                if not package_path.exists():
                    line = text.count("\n", 0, match.start()) + 1
                    failures.append(f"{path.relative_to(ROOT)}:{line} -> {reference}")
            for match in SCRIPT_REF_RE.finditer(text):
                reference = clean_reference(match.group(0))
                package_path = ROOT / "src" / reference
                if not package_path.exists():
                    line = text.count("\n", 0, match.start()) + 1
                    failures.append(f"{path.relative_to(ROOT)}:{line} -> {reference}")

        self.assertEqual([], failures)

    def test_docs_use_canonical_runtime_resource_paths(self) -> None:
        failures: list[str] = []
        for path in iter_documentation_files():
            text = path.read_text(encoding="utf-8")
            for pattern in (ROOT_SCHEMA_REF_RE, REMOVED_EXAMPLE_RESOURCE_RE):
                for match in pattern.finditer(text):
                    line = text.count("\n", 0, match.start()) + 1
                    failures.append(f"{path.relative_to(ROOT)}:{line} -> {match.group(0)}")

        self.assertEqual([], failures)

    def test_docs_use_public_cli_for_promoted_commands(self) -> None:
        failures: list[str] = []
        for path in iter_documentation_files():
            text = path.read_text(encoding="utf-8")
            for module_name, pattern in PUBLIC_CLI_ADVANCED_REF_PATTERNS.items():
                for match in pattern.finditer(text):
                    line = text.count("\n", 0, match.start()) + 1
                    failures.append(f"{path.relative_to(ROOT)}:{line} -> advanced {module_name} invocation")

        self.assertEqual([], failures)

    def test_knowledge_library_docs_use_canonical_boundary(self) -> None:
        docs = [
            ROOT / "README.md",
            PACKAGE_ROOT / "docs" / "knowledge_library_contract.md",
            PACKAGE_ROOT / "templates" / "generic_research_ops_starter" / "research_ops" / "README.md",
            PACKAGE_ROOT / "templates" / "research_ops_starter" / "research_ops" / "README.md",
        ]
        required_snippets = [
            "research_ops/library/",
            "library/source_library.md",
            "accepted_outputs_index.md",
        ]
        failures: list[str] = []

        for path in docs:
            text = path.read_text(encoding="utf-8")
            normalized = " ".join(text.split())
            for snippet in required_snippets:
                if " ".join(snippet.split()) not in normalized:
                    failures.append(f"{path.relative_to(ROOT)} missing {snippet}")
            if "research_ops/knowledge/knowledge_index.md" in text:
                failures.append(f"{path.relative_to(ROOT)} mentions legacy knowledge namespace")

        docs_index = (PACKAGE_ROOT / "docs" / "README.md").read_text(encoding="utf-8")
        if "[Knowledge Library Contract](./knowledge_library_contract.md)" not in docs_index:
            failures.append("docs/README.md missing Knowledge Library Contract link")

        contract = (PACKAGE_ROOT / "docs" / "knowledge_library_contract.md").read_text(encoding="utf-8")
        normalized_contract = " ".join(contract.split())
        for snippet in [
            "Workers may cite `LIT-*` IDs as background context",
            "Final accepted claims still need source-level citation",
            "Tooling owns only the generated block",
        ]:
            if " ".join(snippet.split()) not in normalized_contract:
                failures.append(f"knowledge_library_contract.md missing {snippet}")

        self.assertEqual([], failures)

    def test_direct_internal_helper_invocations_are_labeled(self) -> None:
        failures: list[str] = []
        for path in iter_documentation_files():
            text = path.read_text(encoding="utf-8")
            lines = text.splitlines()
            for index, line in enumerate(lines):
                if INTERNAL_HELPER_DIRECT_INVOCATION_RE.search(line) and not has_internal_helper_label(lines, index):
                    failures.append(f"{path.relative_to(ROOT)}:{index + 1} -> unlabeled internal helper invocation")

        self.assertEqual([], failures)

    def test_roadmap_files_include_status_in_filename_header_and_index(self) -> None:
        failures: list[str] = []
        roadmaps_dir = ROOT / "roadmaps"
        index_text = (roadmaps_dir / "README.md").read_text(encoding="utf-8")
        for path in sorted(roadmaps_dir.glob("*.md")):
            if path.name == "README.md":
                continue
            matched_status = None
            for prefix, status in ROADMAP_STATUS_PREFIXES.items():
                if path.name.startswith(prefix):
                    matched_status = status
                    break
            if matched_status is None:
                failures.append(f"{path.relative_to(ROOT)} missing lifecycle status filename prefix")
                continue

            header = "\n".join(path.read_text(encoding="utf-8").splitlines()[:10])
            if f"Status: {matched_status}" not in header:
                failures.append(f"{path.relative_to(ROOT)} missing matching header Status: {matched_status}")
            if f"./{path.name}" not in index_text:
                failures.append(f"roadmaps/README.md missing link to {path.name}")
            if f"| {matched_status} |" not in index_text:
                failures.append(f"roadmaps/README.md missing status table entry for {matched_status}")

        self.assertEqual([], failures)


if __name__ == "__main__":
    unittest.main()
