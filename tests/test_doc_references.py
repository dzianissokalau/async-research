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
        r"(?:python -m\s+async_research_workflow\.scripts\.human_decision_log\s+\\?\s*|human_decision_log\.py\s+)(?:append|check|resolve-task|auto-resolve-task|summarize)\b|async_research_workflow/scripts/human_decision_log\.py|human_decision_log\.py\b"
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
ROADMAP_OPERATIONAL_FILES: set[str] = set()
ROADMAP_INDEX_ROW_RE = re.compile(
    r"^\| \[(?P<name>[^\]]+)\]\((?P<target>\./[^)]+)\) \| "
    r"(?P<status>[^|]+) \| (?P<current_phase>[^|]+) \| "
    r"(?P<last_updated>[^|]+) \| (?P<next_action>[^|]+) \| "
    r"(?P<blocked_by>[^|]+) \|$"
)
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\((?P<target>[^)]+)\)")
HISTORICAL_ROADMAP_LABELS = (
    "historical",
    "history",
    "stale",
    "obsolete",
    "renamed",
    "previous",
    "former",
    "legacy",
    "old lifecycle",
    "lifecycle rename",
)


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


def roadmap_index_rows() -> list[dict[str, str]]:
    index = ROOT / "roadmaps" / "README.md"
    rows: list[dict[str, str]] = []
    for line in index.read_text(encoding="utf-8").splitlines():
        match = ROADMAP_INDEX_ROW_RE.match(line)
        if match:
            rows.append(match.groupdict())
    return rows


def roadmap_index_path_map() -> dict[str, Path]:
    return {
        row["name"]: ROOT / "roadmaps" / row["target"].removeprefix("./")
        for row in roadmap_index_rows()
    }


def stale_roadmap_filename_replacements() -> dict[str, str]:
    replacements: dict[str, str] = {}
    for path in roadmap_index_path_map().values():
        current_name = path.name
        matched_prefix = next(
            (prefix for prefix in ROADMAP_STATUS_PREFIXES if current_name.startswith(prefix)),
            None,
        )
        if matched_prefix is None:
            continue
        slug = current_name.removeprefix(matched_prefix)
        for prefix in ROADMAP_STATUS_PREFIXES:
            stale_name = f"{prefix}{slug}"
            if stale_name != current_name:
                replacements[stale_name] = current_name
    return replacements


def line_number_for_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def line_context_for_offset(text: str, offset: int) -> str:
    lines = text.splitlines()
    line_index = line_number_for_offset(text, offset) - 1
    if line_index < 0 or line_index >= len(lines):
        return ""

    context_lines = [lines[line_index]]
    cursor = line_index - 1
    while cursor >= 0 and lines[cursor].strip():
        previous = lines[cursor]
        stripped = previous.lstrip()
        if (
            previous.startswith(" ")
            or stripped.startswith(("- ", "* ", "+ "))
            or re.match(r"\d+[.)]\s", stripped)
        ):
            context_lines.insert(0, previous)
            if stripped.startswith(("- ", "* ", "+ ")) or re.match(r"\d+[.)]\s", stripped):
                break
            cursor -= 1
            continue
        break

    return " ".join(context_lines)


def has_historical_roadmap_label(context: str) -> bool:
    normalized = context.lower()
    return any(label in normalized for label in HISTORICAL_ROADMAP_LABELS)


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

    def test_integrated_runtime_phase0_contract_is_documented(self) -> None:
        runtime_contract = PACKAGE_ROOT / "docs" / "research_runtime_contract.md"
        runtime_artifacts = PACKAGE_ROOT / "docs" / "runtime_artifacts.md"
        runtime_adapters = PACKAGE_ROOT / "docs" / "runtime_adapters.md"
        research_brief = PACKAGE_ROOT / "docs" / "research_brief_contract.md"
        eval_contract = PACKAGE_ROOT / "docs" / "evaluation_flywheel.md"
        evidence_memory = PACKAGE_ROOT / "docs" / "structured_evidence_memory.md"
        bounded_parallel = PACKAGE_ROOT / "docs" / "bounded_parallel_research.md"
        docs_index = (PACKAGE_ROOT / "docs" / "README.md").read_text(encoding="utf-8")
        runtime_text = runtime_contract.read_text(encoding="utf-8")
        artifact_text = runtime_artifacts.read_text(encoding="utf-8")
        adapter_text = runtime_adapters.read_text(encoding="utf-8")
        brief_text = research_brief.read_text(encoding="utf-8")
        eval_text = eval_contract.read_text(encoding="utf-8")
        evidence_memory_text = evidence_memory.read_text(encoding="utf-8")
        bounded_parallel_text = bounded_parallel.read_text(encoding="utf-8")
        runtime_normalized = " ".join(runtime_text.split())
        artifact_normalized = " ".join(artifact_text.split())
        adapter_normalized = " ".join(adapter_text.split())
        brief_normalized = " ".join(brief_text.split())
        eval_normalized = " ".join(eval_text.split())
        evidence_memory_normalized = " ".join(evidence_memory_text.split())
        bounded_parallel_normalized = " ".join(bounded_parallel_text.split())
        failures: list[str] = []

        for snippet in [
            "[Research Runtime Contract](./research_runtime_contract.md)",
            "[Research Brief Contract](./research_brief_contract.md)",
            "[Runtime Artifacts](./runtime_artifacts.md)",
            "[Runtime Adapters](./runtime_adapters.md)",
            "[Evaluation Flywheel](./evaluation_flywheel.md)",
            "[Structured Evidence Memory And Targeted Reflection](./structured_evidence_memory.md)",
            "[Bounded Parallel Research Threads](./bounded_parallel_research.md)",
        ]:
            if snippet not in docs_index:
                failures.append(f"docs/README.md missing {snippet}")

        for snippet in [
            "Workflow commands own task transitions",
            "Review and result-acceptance commands own acceptance decisions",
            "The runtime is read-only by default",
            "Missing permission data fails closed",
            "The core package remains standard-library first",
        ]:
            if " ".join(snippet.split()) not in runtime_normalized:
                failures.append(f"research_runtime_contract.md missing {snippet}")

        for adapter_type in [
            "web_search",
            "web_open",
            "file_search",
            "file_fetch",
            "mcp_search",
            "mcp_fetch",
            "api_query",
            "code_execute",
        ]:
            if f"`{adapter_type}`" not in runtime_text:
                failures.append(f"research_runtime_contract.md missing adapter {adapter_type}")

        for field in [
            "evidence_id",
            "task_id",
            "adapter_type",
            "source_uri",
            "source_title",
            "retrieved_at",
            "content_hash",
            "snapshot_path",
            "span_refs",
            "license_or_use_policy",
            "freshness_status",
            "cost",
            "permission_basis",
            "trace_id",
            "tool_name",
            "input_summary",
            "output_summary",
            "artifact_paths",
            "return_code",
            "duration_ms",
            "token_usage",
            "error",
        ]:
            if f"`{field}`" not in runtime_text:
                failures.append(f"research_runtime_contract.md missing field {field}")

        for snippet in [
            "research_ops/briefs/research_brief.json",
            "schemas/research_brief.schema.json",
            "async-research brief draft research_ops",
            "async-research brief validate research_ops/briefs/research_brief.json",
            "async-research brief apply research_ops research_ops/briefs/research_brief.json --dry-run",
            "The planner must not start broad research from those prompts",
            "credentials",
            "paid_services",
            "private_data",
            "public_claims",
            "workflow create-task --brief",
            "idea promote --brief",
        ]:
            if " ".join(snippet.split()) not in brief_normalized:
                failures.append(f"research_brief_contract.md missing {snippet}")

        for snippet in [
            "research_ops/runtime/traces.jsonl",
            "research_ops/runtime/evidence_objects.jsonl",
            "research_ops/runtime/snapshots/",
            "schemas/runtime_trace.schema.json",
            "schemas/runtime_evidence_object.schema.json",
            "async-research runtime validate research_ops",
            "async-research runtime inspect-evidence research_ops EVID-000001",
            "content_hash does not match the snapshot bytes",
            "not accepted evidence until existing review and result-acceptance gates say so",
        ]:
            if " ".join(snippet.split()) not in artifact_normalized and " ".join(snippet.split()) not in runtime_normalized:
                failures.append(f"runtime artifact docs missing {snippet}")

        for snippet in [
            "async-research runtime dry-run research_ops --request runtime_request.json",
            "async-research runtime execute research_ops --request runtime_request.json",
            "Missing permission data fails closed",
            "runtime_permissions.max_calls",
            "runtime_permissions.allowed_api_names",
            "mocked-only in Phase 3",
            "does not perform live network, credentialed, or paid calls",
            "without changing task state",
            "mode: \"parallel_research\"",
            "parallel_branch",
            "research_ops/runtime/parallel_merges/",
        ]:
            if " ".join(snippet.split()) not in adapter_normalized:
                failures.append(f"runtime_adapters.md missing {snippet}")

        for snippet in [
            "Expert preference win rate",
            "Grounded claim rate",
            "Unsupported claim rate",
            "Task success rate",
            "Accepted-output rate",
            "Cost per accepted report",
            "Median latency to accepted report",
            "Freshness failure rate",
            "Reviewer disagreement rate",
            "Reproducibility pass rate",
            "One domain pack cannot justify broad superiority claims",
        ]:
            if " ".join(snippet.split()) not in eval_normalized:
                failures.append(f"evaluation_flywheel.md missing {snippet}")

        for snippet in [
            "research_ops/memory/evidence_memory_index.json",
            "research_ops/reflections/targeted_reflections.jsonl",
            "async-research evidence-memory update research_ops",
            "async-research evidence-memory query research_ops --contradictions-only",
            "async-research reflection record research_ops/tasks/TASK-0001-example",
            "Targeted Reflections",
            "Expired, suppressed, superseded, or irrelevant rows are not injected",
        ]:
            if " ".join(snippet.split()) not in evidence_memory_normalized:
                failures.append(f"structured_evidence_memory.md missing {snippet}")

        for snippet in [
            "runtime_permissions.parallel_research",
            "max_parallel_branches",
            "per_branch_max_calls",
            "require_task_lock",
            "parallel_plan",
            "branch_id",
            "research_ops/runtime/parallel_merges/",
            "bounded_parallelism",
            "Branches do not own task state",
        ]:
            if " ".join(snippet.split()) not in bounded_parallel_normalized and " ".join(snippet.split()) not in runtime_normalized:
                failures.append(f"bounded parallel docs missing {snippet}")

        self.assertEqual([], failures)

    def test_interaction_mode_phase0_contract_is_documented(self) -> None:
        contract_path = PACKAGE_ROOT / "docs" / "interaction_mode_contract.md"
        docs_index = (PACKAGE_ROOT / "docs" / "README.md").read_text(encoding="utf-8")
        contract = contract_path.read_text(encoding="utf-8")
        normalized = " ".join(contract.split())
        failures: list[str] = []

        if "[Interaction Mode Contract](./interaction_mode_contract.md)" not in docs_index:
            failures.append("docs/README.md missing Interaction Mode Contract link")

        for mode in [
            "`manual`",
            "`guided`",
            "`supervised`",
            "`autonomous`",
            "`publication_guarded`",
        ]:
            if mode not in contract:
                failures.append(f"interaction_mode_contract.md missing mode {mode}")

        for category in [
            "quality uncertainty",
            "source freshness or approval problem",
            "review disagreement",
            "revision limit reached",
            "idea prioritization ambiguity",
            "budget warning",
            "hard budget breach",
            "missing credentials or inaccessible data",
            "destructive file or system operation",
            "private or sensitive data use",
            "external or publication claim approval",
        ]:
            if category not in contract:
                failures.append(f"interaction_mode_contract.md missing category {category}")

        for snippet in [
            "New starter workspaces default to `supervised` through a checked-in `interaction_mode.json`.",
            "Existing workspaces without an interaction-mode config keep manual-compatible behavior for mutating commands.",
            "Autonomous mode has no path that skips result acceptance, source governance, or deliverable maturity gates.",
            "Every framework-made mutating decision must write a durable audit row.",
            "Task status changes must still validate through the existing transition rules.",
            "Human approval required; pause or stop.",
            "Defer publication claims until explicit approval exists.",
            "never silently approve a new source",
            "publication readiness cannot be claimed after an exhausted revision loop",
        ]:
            if " ".join(snippet.split()) not in normalized:
                failures.append(f"interaction_mode_contract.md missing {snippet}")

        self.assertEqual([], failures)

    def test_interaction_mode_phase7_default_migration_docs(self) -> None:
        docs = {
            "README.md": ROOT / "README.md",
            "CHANGELOG.md": ROOT / "CHANGELOG.md",
            "LLM_SETUP_GUIDE.md": ROOT / "LLM_SETUP_GUIDE.md",
            "first_success_quickstart.md": PACKAGE_ROOT / "docs" / "first_success_quickstart.md",
            "interaction_mode_contract.md": PACKAGE_ROOT / "docs" / "interaction_mode_contract.md",
            "operational_readiness_runbook.md": PACKAGE_ROOT / "docs" / "operational_readiness_runbook.md",
            "generic starter README": PACKAGE_ROOT
            / "templates"
            / "generic_research_ops_starter"
            / "research_ops"
            / "README.md",
            "real-estate starter README": PACKAGE_ROOT
            / "templates"
            / "research_ops_starter"
            / "research_ops"
            / "README.md",
        }
        required = {
            "README.md": [
                "New starter workspaces include `interaction_mode.json` in `supervised` mode",
                "Existing workspaces without `interaction_mode.json` keep manual-compatible behavior",
                "async-research mode show research_ops",
                "interaction_mode.json",
            ],
            "CHANGELOG.md": [
                "## Unreleased",
                "new starter workspaces use `supervised`",
                "existing workspaces without `interaction_mode.json` keep manual-compatible behavior",
            ],
            "LLM_SETUP_GUIDE.md": [
                "async-research mode show research_ops",
                "async-research mode validate research_ops",
                "Before mutating workflow state, read the mode",
                "Existing workspaces without `interaction_mode.json` stay manual-compatible",
            ],
            "first_success_quickstart.md": [
                "How autonomous should this run be?",
                "New workspaces start in `supervised` mode",
                "async-research mode show research_ops",
                "async-research mode validate research_ops",
                "explicit mode set succeeds",
            ],
            "interaction_mode_contract.md": [
                "Status: Active contract",
                "routine, reversible gates may continue only when policy, transition validation, and audit logging allow them",
                "Existing workspaces without an interaction-mode config keep manual-compatible behavior",
                "These gates are never bypassed by interaction mode",
                "`publication_guarded` uses the same internal research routing as `autonomous`",
            ],
            "operational_readiness_runbook.md": [
                "## Unexpectedly Frequent Interrupts",
                "New starter workspaces should report `supervised`",
                "auto-decision audit row can be written",
                "Missing source governance, result acceptance, deliverable maturity, or publication approval",
            ],
            "generic starter README": [
                "How autonomous should this run be?",
                "This starter includes `interaction_mode.json` in `supervised` mode",
                "explain whether an interrupt is required by mode policy, a hard stop, or a missing gate",
            ],
            "real-estate starter README": [
                "How autonomous should this run be?",
                "This starter includes `interaction_mode.json` in `supervised` mode",
                "explain whether an interrupt is required by mode policy, a hard stop, or a missing gate",
            ],
        }
        failures: list[str] = []

        for label, snippets in required.items():
            normalized = " ".join(docs[label].read_text(encoding="utf-8").split())
            for snippet in snippets:
                if " ".join(snippet.split()) not in normalized:
                    failures.append(f"{label} missing {snippet}")

        self.assertEqual([], failures)

    def test_first_success_quickstart_stays_short_and_public(self) -> None:
        quickstart = PACKAGE_ROOT / "docs" / "first_success_quickstart.md"
        text = quickstart.read_text(encoding="utf-8")
        normalized = " ".join(text.split())
        commands: list[str] = []
        for block in re.findall(r"```bash\n(.*?)```", text, re.DOTALL):
            current = ""
            for raw_line in block.splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                current = f"{current} {line}".strip() if current else line
                if current.endswith("\\"):
                    current = current[:-1].strip()
                    continue
                commands.append(" ".join(current.split()))
                current = ""
            if current:
                commands.append(" ".join(current.split()))

        self.assertLessEqual(len(text.splitlines()), 100)
        self.assertNotIn("python -m", text)
        self.assertNotIn("review_template", text)
        self.assertNotIn("## Command Map", text)
        for command in commands:
            if command.startswith("TASK="):
                continue
            self.assertTrue(command.startswith("async-research "), command)

        for snippet in [
            "# First Success Quickstart",
            "async-research init research_ops",
            "async-research mode show research_ops",
            "async-research mode validate research_ops",
            "How autonomous should this run be?",
            "async-research readiness research_ops --dry-run",
            'async-research review draft "$TASK" --role primary',
            'async-research review submit "$TASK"',
            'async-research review aggregate "$TASK" --dry-run',
            'async-research review aggregate "$TASK" --record-review-start',
            "async-research accepted update research_ops",
            "async-research accepted revalidation research_ops --write-schedule",
            "async-research surface update research_ops",
            "async-research surface validate research_ops",
            "[README](../../../README.md)",
            "[Task Contracts](./task_contracts.md)",
            "[Structural Reviewer Isolation Protocol](./reviewer_isolation_protocol.md)",
            "[Algorithmic Review Aggregation Protocol](./algorithmic_review_aggregation_protocol.md)",
            "[Operational Readiness Runbook](./operational_readiness_runbook.md)",
        ]:
            self.assertIn(" ".join(snippet.split()), normalized)

        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        docs_index = (PACKAGE_ROOT / "docs" / "README.md").read_text(encoding="utf-8")
        self.assertIn("First Success Quickstart", readme)
        self.assertIn("[First Success Quickstart](./first_success_quickstart.md)", docs_index)
        dry_run_index = commands.index('async-research review aggregate "$TASK" --dry-run')
        write_index = commands.index('async-research review aggregate "$TASK" --record-review-start')
        accepted_update_index = commands.index("async-research accepted update research_ops")
        self.assertLess(dry_run_index, write_index)
        self.assertLess(write_index, accepted_update_index)

    def test_knowledge_library_roadmap_tracks_row_level_ref_hardening(self) -> None:
        roadmap = (ROOT / "roadmaps" / "delivered_knowledge_library_roadmap.md").read_text(encoding="utf-8")
        normalized = " ".join(roadmap.split())
        for snippet in [
            "structured library parser/validator source rows, not generic text presence in `source_library.md`",
            "row-level source IDs from the generated `source_library.md` block",
            "surfaces consume validator output rather than reparsing tables separately or resolving `LIT-*` refs through ad hoc text search",
            "library-dependent routes resolve `library_refs` from structured `source_library.md` generated rows, not generic text presence",
        ]:
            self.assertIn(" ".join(snippet.split()), normalized)

    def test_knowledge_library_phase5_task_guidance_is_documented(self) -> None:
        docs = {
            "knowledge_library_contract.md": PACKAGE_ROOT / "docs" / "knowledge_library_contract.md",
            "task_contracts.md": PACKAGE_ROOT / "docs" / "task_contracts.md",
            "idea_catalog_contract.md": PACKAGE_ROOT / "docs" / "idea_catalog_contract.md",
        }
        required_snippets = [
            "`literature_extract`",
            "allowed source list",
            "source status and trust tier",
            "claim-strength rules",
            "anti-context and dead ends",
            "async-research library validate research_ops",
            "source_library.md",
            "library_update_log.md",
            "High-stakes claims and any proposed `strong` claim require human approval",
        ]
        failures: list[str] = []

        for label, path in docs.items():
            normalized = " ".join(path.read_text(encoding="utf-8").split())
            for snippet in required_snippets:
                if " ".join(snippet.split()) not in normalized:
                    failures.append(f"{label} missing {snippet}")

        for path in [
            PACKAGE_ROOT / "templates" / "generic_research_ops_starter" / "research_ops" / "README.md",
            PACKAGE_ROOT / "templates" / "research_ops_starter" / "research_ops" / "README.md",
        ]:
            normalized = " ".join(path.read_text(encoding="utf-8").split())
            for snippet in [
                "`literature_extract` tasks can propose library updates without writing outside their task folder",
                "proposed generated-table rows",
                "`library_update_log.md` provenance row",
            ]:
                if " ".join(snippet.split()) not in normalized:
                    failures.append(f"{path.relative_to(ROOT)} missing {snippet}")

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

    def test_tier_zero_is_hidden_from_normal_operator_guidance(self) -> None:
        public_guidance = {
            "algorithmic_review_aggregation_protocol.md": PACKAGE_ROOT / "docs" / "algorithmic_review_aggregation_protocol.md",
            "revision_counter_protocol.md": PACKAGE_ROOT / "docs" / "revision_counter_protocol.md",
            "task_contracts.md": PACKAGE_ROOT / "docs" / "task_contracts.md",
            "review_ensemble_policy.md": PACKAGE_ROOT / "docs" / "review_ensemble_policy.md",
            "workflow_blueprint.md": PACKAGE_ROOT / "docs" / "workflow_blueprint.md",
            "scheduler_and_prompts.md": PACKAGE_ROOT / "docs" / "scheduler_and_prompts.md",
            "cost_controls.md": PACKAGE_ROOT / "docs" / "cost_controls.md",
        }
        forbidden_snippets = [
            "| `0` |",
            "| Tier 0 |",
            "tier is 0 or 1",
            "Tier 0/1",
            "`idea_discovery` | 0",
            "`idea_dedupe` | 0",
            "`batch_job` | 0",
            "| 0 | 1 |",
            "| 0 | none |",
            "planners should use defaults including Tier 0",
        ]
        failures: list[str] = []
        for label, path in public_guidance.items():
            text = path.read_text(encoding="utf-8")
            for snippet in forbidden_snippets:
                if snippet in text:
                    failures.append(f"{label} still contains normal Tier 0 guidance: {snippet}")

        boundary = (PACKAGE_ROOT / "docs" / "internal_helper_boundary.md").read_text(encoding="utf-8")
        boundary_normalized = " ".join(boundary.split())
        for snippet in [
            "Public task authoring, review prompts, and operator docs use review tiers 1 through 3.",
            "Tier 0 is reserved for internal recovery and benchmark fixtures",
            "Do not create normal queued work with `review_policy.tier = 0`.",
        ]:
            self.assertIn(" ".join(snippet.split()), boundary_normalized)

        self.assertEqual([], failures)

    def test_roadmap_files_include_status_in_filename_header_and_index(self) -> None:
        failures: list[str] = []
        roadmaps_dir = ROOT / "roadmaps"
        index_text = (roadmaps_dir / "README.md").read_text(encoding="utf-8")
        for path in sorted(roadmaps_dir.glob("*.md")):
            if path.name == "README.md" or path.name in ROADMAP_OPERATIONAL_FILES:
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

    def test_roadmap_index_maps_display_names_to_current_paths(self) -> None:
        rows = roadmap_index_rows()
        failures: list[str] = []
        seen_names: set[str] = set()

        if not rows:
            failures.append("roadmaps/README.md has no parseable roadmap index rows")

        for row in rows:
            name = row["name"]
            target = row["target"]
            status = row["status"].strip()
            path = ROOT / "roadmaps" / target.removeprefix("./")

            if name in seen_names:
                failures.append(f"roadmaps/README.md has duplicate roadmap display name: {name}")
            seen_names.add(name)

            if not target.startswith("./"):
                failures.append(f"{name} uses non-relative roadmap target: {target}")
            if "/" in target.removeprefix("./"):
                failures.append(f"{name} points outside the roadmap root: {target}")
            if not path.is_file():
                failures.append(f"{name} points to missing roadmap: {target}")
                continue

            matched_status = None
            for prefix, expected_status in ROADMAP_STATUS_PREFIXES.items():
                if path.name.startswith(prefix):
                    matched_status = expected_status
                    break
            if matched_status is None:
                failures.append(f"{name} target lacks lifecycle prefix: {target}")
            elif status != matched_status:
                failures.append(
                    f"{name} row status {status!r} does not match current path {target} "
                    f"({matched_status})"
                )

        self.assertEqual([], failures)

    def test_docs_reject_stale_roadmap_lifecycle_links(self) -> None:
        replacements = stale_roadmap_filename_replacements()
        failures: list[str] = []

        for path in iter_documentation_files():
            text = path.read_text(encoding="utf-8")
            relative_path = path.relative_to(ROOT)
            markdown_link_spans = [
                (link.start(), link.end())
                for link in MARKDOWN_LINK_RE.finditer(text)
            ]

            for link in MARKDOWN_LINK_RE.finditer(text):
                target = clean_reference(link.group("target"))
                target_name = Path(target.split("#", 1)[0]).name
                if target_name in replacements:
                    line = line_number_for_offset(text, link.start("target"))
                    failures.append(
                        f"{relative_path}:{line} links to stale roadmap {target_name}; "
                        f"use {replacements[target_name]}"
                    )

            for stale_name, replacement in replacements.items():
                for match in re.finditer(re.escape(stale_name), text):
                    if any(start <= match.start() < end for start, end in markdown_link_spans):
                        continue
                    context = line_context_for_offset(text, match.start())
                    if not has_historical_roadmap_label(context):
                        line = line_number_for_offset(text, match.start())
                        failures.append(
                            f"{relative_path}:{line} mentions stale roadmap {stale_name} "
                            f"without a historical/stale label; current path is {replacement}"
                        )

        self.assertEqual([], failures)

    def test_roadmap_closeout_checklist_covers_lifecycle_hygiene(self) -> None:
        checklist = ROOT / "roadmaps" / "automation" / "roadmap_closeout_checklist.md"
        text = checklist.read_text(encoding="utf-8")
        normalized = " ".join(text.split())
        for snippet in [
            "Update the roadmap header",
            "Rename the roadmap file to the lifecycle prefix",
            "Update `roadmaps/README.md`",
            "Update inbound links",
            "Move or repoint automation artifacts under `roadmaps/automation/<roadmap_slug>/`",
            "Run the stale-link scan",
            ".venv/bin/python -m unittest tests.test_doc_references",
            "Record backlog follow-ups",
        ]:
            self.assertIn(" ".join(snippet.split()), normalized)

    def test_dashboard_mvp_coordination_contract_is_locked(self) -> None:
        dashboard_path = ROOT / "roadmaps" / "delivered_dashboard_delivery_roadmap.md"
        operator_path = ROOT / "roadmaps" / "delivered_operator_ux_workflow_ergonomics_roadmap.md"
        dashboard = dashboard_path.read_text(encoding="utf-8")
        operator = operator_path.read_text(encoding="utf-8")
        dashboard_normalized = " ".join(dashboard.split())
        operator_normalized = " ".join(operator.split())

        self.assertIn("Status: Delivered", dashboard.splitlines()[:8])
        self.assertIn("## MVP Coordination Contract", dashboard)
        self.assertIn("| 3 | Dashboard MVP coordination | Complete |", operator_normalized)
        self.assertIn("Dashboard roadmap is now `In Progress`", operator_normalized)

        for snippet in [
            "Slices 1-2 are read-only:",
            "Slice 1 exposes only `async-research console snapshot research_ops --json`.",
            "Slice 2 serves static assets and `GET /api/snapshot`.",
            "No POST, PUT, PATCH, DELETE, command-runner, setup, decision, prompt, schedule, trigger-now, or task-mutation endpoints exist in slices 1-2.",
            "Snapshot code may call existing read-only helpers or dry-run read models, but it must not write `research_ops/` files.",
            "Slice 3 is the first place setup actions may be implemented.",
            "includes the MVP snapshot groups from the coordination contract",
            "`/api/snapshot` is read-only and the only API endpoint in Slice 2",
        ]:
            self.assertIn(" ".join(snippet.split()), dashboard_normalized)

        for group in [
            "workspace",
            "readiness",
            "health",
            "tasks",
            "human_decisions",
            "accepted_outputs",
            "rejected_results",
            "cost",
            "ideas",
            "data",
            "library",
            "analysis",
            "runs",
            "warnings",
        ]:
            self.assertRegex(dashboard, rf"- `{re.escape(group)}`:")

        for path in iter_documentation_files():
            self.assertNotIn(
                "not_started_dashboard_delivery_roadmap.md",
                path.read_text(encoding="utf-8"),
                f"stale dashboard roadmap link in {path.relative_to(ROOT)}",
            )
            self.assertNotIn(
                "in_progress_dashboard_delivery_roadmap.md",
                path.read_text(encoding="utf-8"),
                f"stale dashboard roadmap link in {path.relative_to(ROOT)}",
            )

        docs_index = (PACKAGE_ROOT / "docs" / "README.md").read_text(encoding="utf-8")
        console_spec = (PACKAGE_ROOT / "docs" / "async_research_console_spec.md").read_text(encoding="utf-8")
        roadmap_index = (ROOT / "roadmaps" / "README.md").read_text(encoding="utf-8")
        for text in [docs_index, console_spec, roadmap_index]:
            self.assertIn("delivered_dashboard_delivery_roadmap.md", text)


if __name__ == "__main__":
    unittest.main()
