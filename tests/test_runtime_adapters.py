"""Regression tests for bounded runtime adapters."""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from async_research_workflow import cli


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "runtime_vertical_slice"
NOW = "2026-05-20T10:00:00Z"


def run_cli_json(argv: list[str | Path]) -> tuple[int, dict]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = cli.main([str(arg) for arg in argv])
    text = stream.getvalue().strip()
    return code, json.loads(text) if text else {}


def file_snapshot(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def write_runtime_task(ops_dir: Path, *, allow_network: bool = True) -> Path:
    task_dir = ops_dir / "tasks" / "TASK-1001-runtime-vertical-slice"
    task_dir.mkdir(parents=True, exist_ok=True)
    status = {
        "schema_version": "1.0",
        "id": "TASK-1001",
        "title": "Runtime vertical slice",
        "type": "literature_extract",
        "status": "ready_for_worker",
        "previous_status": None,
        "last_transition_reason": "runtime_fixture",
        "priority": 2,
        "revision_count": 0,
        "max_revisions": 1,
        "revision_limit_hit": False,
        "allowed_paths": [
            "research_ops/tasks/TASK-1001-runtime-vertical-slice/**",
            "research_ops/runtime/**",
            "research_ops/sources/**",
        ],
        "allowed_tools": ["runtime:file_fetch", "runtime:api_query"],
        "allow_browsing": False,
        "allow_code_execution": False,
        "allow_network": allow_network,
        "max_minutes": 10,
        "requires_human": False,
        "budget": {"max_api_usd": 0.0, "max_compute_usd": 0.0},
        "human_gate_reason": None,
        "runtime_permissions": {
            "max_calls": 2,
            "max_api_usd": 0.0,
            "max_compute_usd": 0.0,
            "allowed_api_names": ["fixture_stats"],
            "allowed_domains": [],
            "allow_credentials": False,
            "allow_paid_calls": False,
        },
    }
    (task_dir / "status.json").write_text(json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    shutil.copyfile(FIXTURE / "worker_output.md", task_dir / "worker_output.md")
    shutil.copyfile(FIXTURE / "review_packet.md", task_dir / "review_packet.md")
    return task_dir


def init_vertical_slice(root: Path, *, allow_network: bool = True) -> tuple[Path, Path]:
    ops_dir = root / "research_ops"
    code, payload = run_cli_json(["init", ops_dir, "--template", "generic", "--force"])
    if code != cli.SUCCESS:
        raise AssertionError(payload)
    task_dir = write_runtime_task(ops_dir, allow_network=allow_network)
    sources_dir = ops_dir / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(FIXTURE / "source.md", sources_dir / "runtime-source.md")
    briefs_dir = ops_dir / "briefs"
    briefs_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(FIXTURE / "research_brief.json", briefs_dir / "research_brief.json")
    return ops_dir, task_dir


class RuntimeAdapterTests(unittest.TestCase):
    def test_runtime_dry_run_and_execute_vertical_slice_are_auditable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ops_dir, task_dir = init_vertical_slice(root)
            request_path = FIXTURE / "request.json"
            before = file_snapshot(ops_dir)

            dry_code, dry_run = run_cli_json(["runtime", "dry-run", ops_dir, "--request", request_path, "--now", NOW])

            self.assertEqual(cli.SUCCESS, dry_code, dry_run)
            self.assertTrue(dry_run["ok"])
            self.assertFalse(dry_run["changed"])
            self.assertTrue(dry_run["read_only"])
            self.assertEqual(2, dry_run["summary"]["call_count"])
            self.assertEqual("official_api", dry_run["calls"][1]["route_decision"]["selected_source_class"])
            self.assertEqual("mock_statistical_api", dry_run["calls"][1]["tool_name"])
            self.assertEqual(before, file_snapshot(ops_dir))

            execute_code, executed = run_cli_json(["runtime", "execute", ops_dir, "--request", request_path, "--now", NOW])

            self.assertEqual(cli.SUCCESS, execute_code, executed)
            self.assertTrue(executed["ok"])
            self.assertTrue(executed["changed"])
            self.assertEqual(2, executed["summary"]["trace_count"])
            self.assertEqual(2, executed["summary"]["evidence_object_count"])
            self.assertEqual(["EVID-000001"], executed["calls"][0]["evidence_ids"])
            self.assertEqual(["EVID-000002"], executed["calls"][1]["evidence_ids"])
            self.assertEqual("api_query", executed["calls"][1]["route_decision"]["selected_adapter"])
            self.assertEqual(
                "official_page",
                executed["calls"][1]["route_decision"]["rejected_alternatives"][0]["source_class"],
            )

            validate_code, validated = run_cli_json(["runtime", "validate", ops_dir])
            self.assertEqual(cli.SUCCESS, validate_code, validated)
            self.assertEqual(2, validated["summary"]["runtime_trace_count"])
            self.assertEqual(2, validated["summary"]["evidence_object_count"])
            self.assertEqual(2, validated["summary"]["route_decision_count"])
            self.assertEqual(0, validated["summary"]["unsupported_or_stale_evidence_count"])

            snapshot_code, snapshot = run_cli_json(["console", "snapshot", ops_dir, "--json", "--now", NOW])
            self.assertEqual(cli.SUCCESS, snapshot_code, snapshot)
            self.assertEqual(2, snapshot["runtime"]["trace_count"])
            self.assertEqual(2, snapshot["runtime"]["evidence_object_count"])

            status = json.loads((task_dir / "status.json").read_text(encoding="utf-8"))
            self.assertEqual("ready_for_worker", status["status"])
            self.assertTrue((task_dir / "worker_output.md").is_file())
            self.assertTrue((task_dir / "review_packet.md").is_file())

    def test_network_capable_adapter_fails_closed_without_task_permission(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir, _task_dir = init_vertical_slice(Path(tmp), allow_network=False)
            request_path = FIXTURE / "api_only_request.json"

            dry_code, dry_run = run_cli_json(["runtime", "dry-run", ops_dir, "--request", request_path, "--now", NOW])
            self.assertEqual(2, dry_code, dry_run)
            self.assertFalse(dry_run["changed"])
            self.assertEqual("blocked", dry_run["calls"][0]["status"])
            self.assertEqual("network_not_allowed", dry_run["calls"][0]["error"]["code"])

            execute_code, executed = run_cli_json(["runtime", "execute", ops_dir, "--request", request_path, "--now", NOW])
            self.assertEqual(2, execute_code, executed)
            self.assertEqual(1, executed["summary"]["blocked_call_count"])
            self.assertEqual(1, executed["summary"]["trace_count"])
            self.assertEqual(0, executed["summary"]["evidence_object_count"])
            self.assertEqual("network_not_allowed", executed["calls"][0]["error"]["code"])

            validate_code, validated = run_cli_json(["runtime", "validate", ops_dir])
            self.assertEqual(cli.SUCCESS, validate_code, validated)
            self.assertEqual(1, validated["summary"]["runtime_trace_count"])
            self.assertEqual(0, validated["summary"]["evidence_object_count"])
            self.assertEqual("network_not_allowed", validated["summary"]["latest_runtime_errors"][0]["error"]["code"])

    def test_external_adapter_requires_mock_response_in_phase_three(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ops_dir, _task_dir = init_vertical_slice(root, allow_network=True)
            request_path = root / "live_api_request.json"
            request_path.write_text(
                json.dumps(
                    {
                        "mode": "vertical_slice",
                        "task_id": "TASK-1001",
                        "calls": [
                            {
                                "adapter_type": "api_query",
                                "api_name": "fixture_stats",
                                "input_summary": "Attempt a live API call.",
                            }
                        ],
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            dry_code, dry_run = run_cli_json(["runtime", "dry-run", ops_dir, "--request", request_path, "--now", NOW])

            self.assertEqual(2, dry_code, dry_run)
            self.assertFalse(dry_run["changed"])
            self.assertEqual("blocked", dry_run["calls"][0]["status"])
            self.assertEqual("mock_response_required", dry_run["calls"][0]["error"]["code"])

    def test_browser_fallback_requires_reason_and_preserves_governance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ops_dir, _task_dir = init_vertical_slice(root, allow_network=True)
            status_path = ops_dir / "tasks" / "TASK-1001-runtime-vertical-slice" / "status.json"
            status = json.loads(status_path.read_text(encoding="utf-8"))
            status["allowed_tools"] = ["runtime:web_open"]
            status["allow_browsing"] = True
            status["budget"]["max_api_usd"] = 0.01
            status["runtime_permissions"]["max_api_usd"] = 0.01
            status["runtime_permissions"]["allowed_domains"] = ["example.org"]
            status_path.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            request_path = root / "browser_fallback_request.json"
            request = {
                "mode": "vertical_slice",
                "task_id": "TASK-1001",
                "calls": [
                    {
                        "adapter_type": "web_open",
                        "source_uri": "https://example.org/report",
                        "domain": "example.org",
                        "source_class": "official_page",
                        "source_profile": "document_repository",
                        "browser_fallback_reason": "api_incomplete",
                        "route_reason": "The official page supplies narrative context missing from the API.",
                        "route_alternatives": [
                            {
                                "adapter_type": "api_query",
                                "source_class": "official_api",
                                "rejection_reason": "The API omits the narrative context required by the brief.",
                            }
                        ],
                        "estimated_cost": {"api_usd": 0.0, "compute_usd": 0.0, "tokens": 0},
                        "mock_response": {
                            "source_uri": "https://example.org/report",
                            "source_title": "Example official report",
                            "license_or_use_policy": "fixture-only",
                            "content": "official browser fallback snapshot\n",
                        },
                    }
                ],
            }
            request_path.write_text(json.dumps(request, indent=2, sort_keys=True) + "\n", encoding="utf-8")

            dry_code, dry_run = run_cli_json(["runtime", "dry-run", ops_dir, "--request", request_path, "--now", NOW])
            self.assertEqual(cli.SUCCESS, dry_code, dry_run)
            fallback = dry_run["calls"][0]["route_decision"]["browser_fallback"]
            self.assertTrue(fallback["used"])
            self.assertTrue(fallback["allowed_by_task_contract"])
            self.assertTrue(fallback["snapshot_required"])

            execute_code, executed = run_cli_json(["runtime", "execute", ops_dir, "--request", request_path, "--now", NOW])
            self.assertEqual(cli.SUCCESS, execute_code, executed)
            validate_code, validated = run_cli_json(["runtime", "validate", ops_dir])
            self.assertEqual(cli.SUCCESS, validate_code, validated)
            self.assertEqual(1, validated["summary"]["browser_fallback_count"])

            del request["calls"][0]["browser_fallback_reason"]
            request_path.write_text(json.dumps(request, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            blocked_code, blocked_run = run_cli_json(["runtime", "dry-run", ops_dir, "--request", request_path, "--now", NOW])
            self.assertEqual(2, blocked_code, blocked_run)
            self.assertEqual("browser_fallback_reason_missing", blocked_run["calls"][0]["error"]["code"])

    def test_malformed_estimated_cost_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ops_dir, _task_dir = init_vertical_slice(root, allow_network=True)
            request_path = root / "bad_cost_request.json"
            request_path.write_text(
                json.dumps(
                    {
                        "mode": "vertical_slice",
                        "task_id": "TASK-1001",
                        "calls": [
                            {
                                "adapter_type": "file_fetch",
                                "source_path": "research_ops/sources/runtime-source.md",
                                "estimated_cost": {"tokens": "unknown"},
                            }
                        ],
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            dry_code, dry_run = run_cli_json(["runtime", "dry-run", ops_dir, "--request", request_path, "--now", NOW])

            self.assertEqual(2, dry_code, dry_run)
            self.assertFalse(dry_run["changed"])
            self.assertEqual("blocked", dry_run["calls"][0]["status"])
            self.assertEqual("invalid_estimated_cost", dry_run["calls"][0]["error"]["code"])


if __name__ == "__main__":
    unittest.main()
