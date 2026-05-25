import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from async_research_workflow import cli
from async_research_workflow.starter_smoke import StarterSmokePlan


class JsonPayloadFromOutputTests(unittest.TestCase):
    def test_json_payload_from_output_returns_json_objects(self):
        payload = cli.json_payload_from_output(cli.SUCCESS, '{"ok": true, "value": 1}\n')

        self.assertEqual(payload, {"ok": True, "value": 1})

    def test_json_payload_from_output_wraps_non_object_json(self):
        payload = cli.json_payload_from_output(cli.SUCCESS, '["a", "b"]\n')

        self.assertEqual(payload, {"ok": True, "value": ["a", "b"]})

    def test_json_payload_from_output_wraps_raw_output(self):
        payload = cli.json_payload_from_output(1, "not-json\n")

        self.assertEqual(payload, {"ok": False, "raw_output": "not-json"})


class StarterSmokeSafetyTests(unittest.TestCase):
    def run_cli_json(self, argv):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = cli.main(argv)
        payload = json.loads(stream.getvalue())
        return code, payload

    def test_starter_smoke_refuses_existing_non_empty_dir_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp) / "smoke"
            work_dir.mkdir()
            marker = work_dir / "keep.txt"
            marker.write_text("do not remove\n", encoding="utf-8")

            code, payload = self.run_cli_json(["starter-smoke", str(work_dir)])

            self.assertEqual(code, cli.INVALID)
            self.assertEqual(payload["reason"], "target_exists")
            self.assertEqual(payload["work_dir"], str(work_dir))
            self.assertEqual(payload["ops_dir"], str(work_dir / "research_ops"))
            self.assertTrue(marker.exists())
            self.assertEqual(marker.read_text(encoding="utf-8"), "do not remove\n")

    def test_starter_smoke_force_allows_existing_dir_replacement(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp) / "smoke"
            work_dir.mkdir()
            marker = work_dir / "remove-me.txt"
            marker.write_text("old contents\n", encoding="utf-8")

            with mock.patch.object(cli, "run_init", return_value=cli.SUCCESS) as run_init:
                with mock.patch.object(cli, "module_json", return_value=(cli.SUCCESS, {"ok": True})):
                    code, payload = self.run_cli_json(["starter-smoke", str(work_dir), "--force"])

            self.assertEqual(code, cli.SUCCESS)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["template"], "generic")
            self.assertFalse(marker.exists())
            init_args = run_init.call_args.args[0]
            self.assertEqual(init_args.target_dir, work_dir / "research_ops")
            self.assertEqual(init_args.template, "generic")
            self.assertTrue(init_args.force)

    def test_starter_smoke_real_estate_template_is_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp) / "smoke"

            with mock.patch.object(cli, "run_init", return_value=cli.SUCCESS) as run_init:
                with mock.patch.object(cli, "module_json", return_value=(cli.SUCCESS, {"ok": True})):
                    code, payload = self.run_cli_json([
                        "starter-smoke",
                        str(work_dir),
                        "--template",
                        "real-estate",
                    ])

            self.assertEqual(code, cli.SUCCESS)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["template"], "real-estate")
            init_args = run_init.call_args.args[0]
            self.assertEqual(init_args.target_dir, work_dir / "research_ops")
            self.assertEqual(init_args.template, "real-estate")
            self.assertTrue(init_args.force)

    def test_starter_smoke_wraps_init_output_in_single_json_envelope(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp) / "smoke"

            def fake_run_init(init_args):
                cli.print_json({
                    "ok": True,
                    "action": "initialized",
                    "target_dir": str(init_args.target_dir),
                    "template": init_args.template,
                })
                return cli.SUCCESS

            with mock.patch.object(cli, "run_init", side_effect=fake_run_init):
                with mock.patch.object(cli, "module_json", return_value=(cli.SUCCESS, {"ok": True})):
                    code, payload = self.run_cli_json(["starter-smoke", str(work_dir)])

            self.assertEqual(code, cli.SUCCESS)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["action"], "starter_smoke_checked")
            self.assertEqual(payload["init"]["exit_code"], cli.SUCCESS)
            self.assertEqual(payload["init"]["payload"]["action"], "initialized")
            self.assertEqual(payload["smoke"]["checks"], payload["checks"])
            self.assertEqual(payload["smoke"]["failures"], payload["failures"])
            self.assertEqual(len(payload["checks"]), 9)

    def test_starter_smoke_wraps_init_failure_without_running_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp) / "smoke"

            def fake_run_init(init_args):
                cli.print_json({
                    "ok": False,
                    "reason": "init_failed",
                    "target_dir": str(init_args.target_dir),
                })
                return cli.INVALID

            with mock.patch.object(cli, "run_init", side_effect=fake_run_init):
                with mock.patch.object(cli, "module_json") as module_json:
                    code, payload = self.run_cli_json(["starter-smoke", str(work_dir)])

            self.assertEqual(code, cli.INVALID)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["init"]["exit_code"], cli.INVALID)
            self.assertEqual(payload["init"]["payload"]["reason"], "init_failed")
            self.assertEqual(payload["failures"][0]["command"], "init")
            self.assertEqual(payload["smoke"]["checks"], [])
            module_json.assert_not_called()

    def test_starter_smoke_treats_init_success_code_with_not_ok_payload_as_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp) / "smoke"

            def fake_run_init(init_args):
                cli.print_json({
                    "ok": False,
                    "reason": "init_reported_not_ok",
                    "target_dir": str(init_args.target_dir),
                })
                return cli.SUCCESS

            with mock.patch.object(cli, "run_init", side_effect=fake_run_init):
                with mock.patch.object(cli, "module_json") as module_json:
                    code, payload = self.run_cli_json(["starter-smoke", str(work_dir)])

            self.assertEqual(code, cli.INVALID)
            self.assertFalse(payload["ok"])
            self.assertFalse(payload["init"]["ok"])
            self.assertEqual(payload["init"]["exit_code"], cli.SUCCESS)
            self.assertEqual(payload["init"]["payload"]["reason"], "init_reported_not_ok")
            self.assertEqual(payload["failures"][0]["command"], "init")
            self.assertEqual(payload["smoke"]["checks"], [])
            module_json.assert_not_called()

    def test_starter_smoke_real_generic_run_is_single_json_envelope(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp) / "smoke"

            code, payload = self.run_cli_json(["starter-smoke", str(work_dir)])

            self.assertEqual(code, cli.SUCCESS)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["action"], "starter_smoke_checked")
            self.assertEqual(payload["work_dir"], str(work_dir))
            self.assertEqual(payload["ops_dir"], str(work_dir / "research_ops"))
            self.assertEqual(payload["init"]["command"], "init")
            self.assertEqual(payload["init"]["exit_code"], cli.SUCCESS)
            self.assertTrue(payload["init"]["ok"])
            self.assertEqual(payload["init"]["payload"]["template"], "generic")
            self.assertEqual(payload["smoke"]["checks"], payload["checks"])
            self.assertEqual(payload["smoke"]["failures"], payload["failures"])
            self.assertEqual(payload["failures"], [])

    def test_starter_smoke_refuses_file_work_dir_with_json_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_file = Path(tmp) / "smoke-file"
            work_file.write_text("not a directory\n", encoding="utf-8")

            code, payload = self.run_cli_json(["starter-smoke", str(work_file)])

            self.assertEqual(code, cli.INVALID)
            self.assertEqual(payload["reason"], "target_is_file")
            self.assertEqual(payload["work_dir"], str(work_file))
            self.assertEqual(work_file.read_text(encoding="utf-8"), "not a directory\n")

    def test_starter_smoke_refuses_file_work_dir_even_with_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_file = Path(tmp) / "smoke-file"
            work_file.write_text("not a directory\n", encoding="utf-8")

            code, payload = self.run_cli_json(["starter-smoke", str(work_file), "--force"])

            self.assertEqual(code, cli.INVALID)
            self.assertEqual(payload["reason"], "target_is_file")
            self.assertTrue(work_file.exists())
            self.assertEqual(work_file.read_text(encoding="utf-8"), "not a directory\n")

    def test_starter_smoke_allows_empty_existing_dir_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp) / "smoke"
            work_dir.mkdir()

            with mock.patch.object(cli, "run_init", return_value=cli.SUCCESS):
                with mock.patch.object(cli, "module_json", return_value=(cli.SUCCESS, {"ok": True})):
                    code, payload = self.run_cli_json(["starter-smoke", str(work_dir)])

            self.assertEqual(code, cli.SUCCESS)
            self.assertTrue(payload["ok"])

    def test_starter_smoke_plan_preserves_check_order(self):
        work_dir = Path("/tmp/arw-smoke-order")
        ops_dir = work_dir / "research_ops"
        plan = StarterSmokePlan(work_dir=work_dir, ops_dir=ops_dir, template="generic")

        checks = [(check.module_name, list(check.argv)) for check in plan.checks()]

        self.assertEqual(
            checks,
            [
                ("check_schema_versions", [str(ops_dir)]),
                ("autonomy_readiness_gate", [str(ops_dir), "--dry-run"]),
                ("health_check", [str(ops_dir), "--dry-run"]),
                ("human_review_surface", ["update", str(ops_dir)]),
                ("human_review_surface", ["validate", str(ops_dir)]),
                ("data_source_audit", ["validate", str(ops_dir)]),
                ("cost_tracking", ["summary", str(ops_dir)]),
                ("run_autonomy_benchmark", []),
                ("simulate_scheduled_week", [str(ops_dir)]),
            ],
        )

    def test_remove_path_unlinks_directory_symlink_without_removing_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            real_dir = Path(tmp) / "real"
            real_dir.mkdir()
            marker = real_dir / "keep.txt"
            marker.write_text("target data\n", encoding="utf-8")
            link = Path(tmp) / "link"
            try:
                link.symlink_to(real_dir, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"symlinks unavailable: {exc}")

            cli.remove_path(link)

            self.assertFalse(link.exists())
            self.assertTrue(real_dir.exists())
            self.assertEqual(marker.read_text(encoding="utf-8"), "target data\n")


class InitSafetyTests(unittest.TestCase):
    def run_cli_json(self, argv):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = cli.main(argv)
        payload = json.loads(stream.getvalue())
        return code, payload

    def test_init_metrics_failure_for_new_target_removes_partial_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "research_ops"

            with mock.patch.object(
                cli,
                "module_json",
                side_effect=[
                    (cli.INVALID, {"ok": False, "reason": "boom"}),
                    (cli.SUCCESS, {"ok": True}),
                ],
            ):
                code, payload = self.run_cli_json(["init", str(target)])

            self.assertEqual(code, cli.INVALID)
            self.assertEqual(payload["reason"], "starter_metrics_init_failed")
            self.assertFalse(target.exists())

    def test_init_force_metrics_failure_restores_existing_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "research_ops"
            target.mkdir()
            marker = target / "keep.txt"
            marker.write_text("previous workspace\n", encoding="utf-8")

            with mock.patch.object(
                cli,
                "module_json",
                side_effect=[
                    (cli.INVALID, {"ok": False, "reason": "boom"}),
                    (cli.SUCCESS, {"ok": True}),
                ],
            ):
                code, payload = self.run_cli_json(["init", str(target), "--force"])

            self.assertEqual(code, cli.INVALID)
            self.assertEqual(payload["reason"], "starter_metrics_init_failed")
            self.assertTrue(marker.exists())
            self.assertEqual(marker.read_text(encoding="utf-8"), "previous workspace\n")
            self.assertFalse((target / "queue.md").exists())

    def test_init_force_copy_failure_preserves_existing_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "research_ops"
            target.mkdir()
            marker = target / "keep.txt"
            marker.write_text("original\n", encoding="utf-8")

            with mock.patch.object(cli, "copy_resource_tree", side_effect=OSError("permission denied")):
                code, payload = self.run_cli_json(["init", str(target), "--force"])

            self.assertEqual(code, cli.INVALID)
            self.assertEqual(payload["reason"], "init_failed")
            self.assertIn("permission denied", payload["error"])
            self.assertTrue(marker.exists())
            self.assertEqual(marker.read_text(encoding="utf-8"), "original\n")

    def test_init_force_metrics_failure_restores_existing_file_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "research_ops"
            target.write_text("previous file\n", encoding="utf-8")

            with mock.patch.object(
                cli,
                "module_json",
                side_effect=[
                    (cli.INVALID, {"ok": False, "reason": "boom"}),
                    (cli.SUCCESS, {"ok": True}),
                ],
            ):
                code, payload = self.run_cli_json(["init", str(target), "--force"])

            self.assertEqual(code, cli.INVALID)
            self.assertEqual(payload["reason"], "starter_metrics_init_failed")
            self.assertTrue(target.is_file())
            self.assertEqual(target.read_text(encoding="utf-8"), "previous file\n")

    def test_init_force_rollback_failure_reports_backup_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "research_ops"
            target.mkdir()
            marker = target / "keep.txt"
            marker.write_text("previous workspace\n", encoding="utf-8")

            with mock.patch.object(cli, "module_json", return_value=(cli.INVALID, {"ok": False, "reason": "boom"})):
                with mock.patch.object(cli, "restore_target", side_effect=OSError("restore failed")):
                    code, payload = self.run_cli_json(["init", str(target), "--force"])

            self.assertEqual(code, cli.INVALID)
            self.assertEqual(payload["reason"], "starter_metrics_init_failed")
            self.assertEqual(payload["rollback_error"], "restore failed")
            self.assertIn("backup_dir", payload)
            backup_dir = Path(payload["backup_dir"])
            self.assertTrue(backup_dir.exists())
            self.assertTrue((backup_dir / target.name / "keep.txt").exists())

    def test_init_success_creates_usable_starter_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "research_ops"

            code, payload = self.run_cli_json(["init", str(target)])

            self.assertEqual(code, cli.SUCCESS)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["template"], "generic")
            self.assertEqual(payload["target_dir"], str(target))
            self.assertTrue((target / "queue.md").exists())
            self.assertTrue((target / "ideas" / "idea_catalog.md").exists())
            self.assertTrue((target / "ideas" / "prioritization.md").exists())
            self.assertTrue((target / "data" / "data_catalog.md").exists())
            self.assertTrue((target / "data" / "data_access.md").exists())
            self.assertTrue((target / "data" / "join_map.md").exists())
            self.assertTrue((target / "data" / "known_data_gaps.md").exists())
            self.assertTrue((target / "data" / "profiles" / "README.md").exists())
            self.assertTrue((target / "metrics_baseline.json").exists())
            self.assertTrue((target / "metrics_history.jsonl").exists())
            self.assertTrue((target / "tasks" / ".gitkeep").exists())
            self.assertFalse((target / "health_report.json").exists())
            self.assertEqual(list((target / "tasks").glob("*/status.json")), [])
            leftovers = [
                path.name
                for path in target.parent.iterdir()
                if path.name.startswith(f".{target.name}.staging-")
                or path.name.startswith(f".{target.name}.backup-")
            ]
            self.assertEqual(leftovers, [])

    def test_init_real_estate_template_remains_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "research_ops"

            code, payload = self.run_cli_json(["init", str(target), "--template", "real-estate"])

            self.assertEqual(code, cli.SUCCESS)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["template"], "real-estate")
            self.assertTrue((target / "tasks" / "TASK-0001-data-readiness" / "status.json").exists())
            self.assertTrue((target / "ideas" / "idea_catalog.md").exists())
            self.assertTrue((target / "ideas" / "prioritization.md").exists())
            self.assertTrue((target / "data" / "data_catalog.md").exists())
            self.assertTrue((target / "data" / "profiles" / "DS-0001.md").exists())
            self.assertTrue((target / "data" / "profiles" / "DS-0002.md").exists())
            self.assertTrue((target / "data" / "profiles" / "DS-0003.md").exists())
            self.assertTrue((target / "health_report.json").exists())


if __name__ == "__main__":
    unittest.main()
