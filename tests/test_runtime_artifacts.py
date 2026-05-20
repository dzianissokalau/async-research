"""Regression tests for runtime evidence object and trace ledgers."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from async_research_workflow import cli


NOW = "2026-05-20T09:00:00Z"


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


def write_task(ops_dir: Path, task_id: str = "TASK-0001") -> None:
    task_dir = ops_dir / "tasks" / f"{task_id}-runtime-fixture"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "status.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "id": task_id,
                "title": "Runtime fixture",
                "type": "data_readiness",
                "status": "ready_for_worker",
                "previous_status": None,
                "last_transition_reason": "fixture",
                "priority": 2,
                "revision_count": 0,
                "max_revisions": 1,
                "revision_limit_hit": False,
                "allowed_paths": [f"research_ops/tasks/{task_dir.name}/**", "research_ops/runtime/**"],
                "max_minutes": 10,
                "requires_human": False,
                "budget": {"max_api_usd": 0.0, "max_compute_usd": 0.0},
                "human_gate_reason": None,
                "updated_at": NOW,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def sha256_text(text: str) -> str:
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def base_evidence(content_hash: str) -> dict:
    return {
        "schema_version": "1.0",
        "framework_version": "runtime_evidence_object_v1.0",
        "evidence_id": "EVID-000001",
        "task_id": "TASK-0001",
        "adapter_type": "file_fetch",
        "source_uri": "fixture://runtime/source",
        "source_title": "Runtime fixture source",
        "retrieved_at": NOW,
        "content_hash": content_hash,
        "snapshot_path": "research_ops/runtime/snapshots/EVID-000001.txt",
        "span_refs": [
            {
                "span_id": "SPAN-0001",
                "span_type": "text",
                "selector": "line:1",
                "content_hash": content_hash,
            }
        ],
        "license_or_use_policy": "fixture-only",
        "freshness_status": {
            "status": "current",
            "checked_at": NOW,
            "basis": "offline fixture",
        },
        "cost": {
            "api_usd": 0.0,
            "compute_usd": 0.0,
            "tokens": 0,
            "basis": "offline fixture",
        },
        "permission_basis": {
            "type": "task_contract",
            "reference": "research_ops/tasks/TASK-0001-runtime-fixture/status.json",
            "capability": "file_fetch",
        },
    }


def base_trace() -> dict:
    return {
        "schema_version": "1.0",
        "framework_version": "runtime_trace_v1.0",
        "trace_id": "TRACE-000001",
        "task_id": "TASK-0001",
        "adapter_type": "file_fetch",
        "tool_name": "fixture_file_fetch",
        "input_summary": "Read offline fixture source permitted by task contract.",
        "output_summary": "Wrote one source snapshot and evidence object.",
        "artifact_paths": [
            "research_ops/runtime/snapshots/EVID-000001.txt",
            "research_ops/runtime/evidence_objects.jsonl",
        ],
        "return_code": "success",
        "duration_ms": 3,
        "token_usage": {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "basis": "not_applicable",
        },
        "cost": {
            "api_usd": 0.0,
            "compute_usd": 0.0,
            "basis": "offline fixture",
        },
        "error": None,
    }


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


class RuntimeArtifactsTests(unittest.TestCase):
    def init_ops(self, root: Path) -> Path:
        ops_dir = root / "research_ops"
        code, payload = run_cli_json(["init", ops_dir, "--force"])
        self.assertEqual(cli.SUCCESS, code, payload)
        write_task(ops_dir)
        return ops_dir

    def write_runtime_fixture(self, ops_dir: Path, evidence: dict | None = None, traces: list[dict] | None = None) -> None:
        snapshot_text = "Runtime fixture source.\n"
        snapshot_path = ops_dir / "runtime" / "snapshots" / "EVID-000001.txt"
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(snapshot_text, encoding="utf-8")
        evidence_payload = evidence or base_evidence(sha256_text(snapshot_text))
        write_jsonl(ops_dir / "runtime" / "evidence_objects.jsonl", [evidence_payload])
        write_jsonl(ops_dir / "runtime" / "traces.jsonl", traces if traces is not None else [base_trace()])

    def test_runtime_validate_summary_inspect_and_console_are_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            self.write_runtime_fixture(ops_dir)
            before = file_snapshot(ops_dir)

            code, payload = run_cli_json(["runtime", "validate", ops_dir])
            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertEqual(1, payload["summary"]["evidence_object_count"])
            self.assertEqual(1, payload["summary"]["runtime_trace_count"])
            self.assertEqual([], payload["errors"])

            summary_code, summary = run_cli_json(["runtime", "summary", ops_dir])
            self.assertEqual(cli.SUCCESS, summary_code, summary)
            self.assertEqual(0, summary["summary"]["unsupported_or_stale_evidence_count"])

            inspect_code, inspected = run_cli_json(["runtime", "inspect-evidence", ops_dir, "EVID-000001"])
            self.assertEqual(cli.SUCCESS, inspect_code, inspected)
            self.assertEqual("EVID-000001", inspected["evidence"]["evidence_id"])
            self.assertEqual(1, len(inspected["related_traces"]))

            snapshot_code, snapshot = run_cli_json(["console", "snapshot", ops_dir, "--json", "--now", NOW])
            self.assertEqual(cli.SUCCESS, snapshot_code, snapshot)
            self.assertEqual(1, snapshot["runtime"]["evidence_object_count"])
            self.assertEqual(1, snapshot["runtime"]["trace_count"])
            self.assertEqual(0, snapshot["runtime"]["unsupported_or_stale_evidence_count"])
            self.assertEqual(before, file_snapshot(ops_dir))

    def test_missing_required_evidence_field_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            snapshot_text = "Runtime fixture source.\n"
            evidence = base_evidence(sha256_text(snapshot_text))
            del evidence["source_title"]
            self.write_runtime_fixture(ops_dir, evidence=evidence)

            code, payload = run_cli_json(["runtime", "validate", ops_dir])

            self.assertEqual(2, code, payload)
            reasons = {error["reason"] for error in payload["errors"]}
            self.assertIn("schema_validation_failed", reasons)

            inspect_code, inspected = run_cli_json(["runtime", "inspect-evidence", ops_dir, "EVID-000001"])
            self.assertEqual(2, inspect_code, inspected)
            self.assertFalse(inspected["ok"])

    def test_bad_snapshot_path_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            snapshot_text = "Runtime fixture source.\n"
            evidence = base_evidence(sha256_text(snapshot_text))
            evidence["snapshot_path"] = "research_ops/runtime/snapshots/../../secret.txt"
            self.write_runtime_fixture(ops_dir, evidence=evidence)

            code, payload = run_cli_json(["runtime", "validate", ops_dir])

            self.assertEqual(2, code, payload)
            reasons = {error["reason"] for error in payload["errors"]}
            self.assertIn("path_outside_research_ops", reasons)

    def test_snapshot_hash_mismatch_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            evidence = base_evidence("sha256:" + ("0" * 64))
            self.write_runtime_fixture(ops_dir, evidence=evidence)

            code, payload = run_cli_json(["runtime", "validate", ops_dir])

            self.assertEqual(2, code, payload)
            reasons = {error["reason"] for error in payload["errors"]}
            self.assertIn("content_hash_mismatch", reasons)

    def test_stale_or_unknown_license_evidence_warns_and_summarizes_latest_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            snapshot_text = "Runtime fixture source.\n"
            evidence = base_evidence(sha256_text(snapshot_text))
            evidence["license_or_use_policy"] = "unknown"
            evidence["freshness_status"]["status"] = "stale"
            trace = base_trace()
            trace["trace_id"] = "TRACE-000002"
            trace["return_code"] = "failed"
            trace["error"] = {
                "code": "fixture_failure",
                "message": "offline fixture adapter failed",
                "category": "tool_error",
            }
            self.write_runtime_fixture(ops_dir, evidence=evidence, traces=[trace])

            code, payload = run_cli_json(["runtime", "validate", ops_dir])

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertEqual(1, payload["summary"]["stale_evidence_count"])
            self.assertEqual(1, payload["summary"]["unsupported_evidence_count"])
            self.assertEqual(1, payload["summary"]["unsupported_or_stale_evidence_count"])
            self.assertEqual("TRACE-000002", payload["summary"]["latest_runtime_errors"][0]["trace_id"])
            reasons = {warning["reason"] for warning in payload["warnings"]}
            self.assertIn("license_or_use_policy_missing", reasons)


if __name__ == "__main__":
    unittest.main()
