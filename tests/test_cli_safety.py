import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from async_research_workflow import cli


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
            self.assertFalse(marker.exists())
            init_args = run_init.call_args.args[0]
            self.assertEqual(init_args.target_dir, work_dir / "research_ops")
            self.assertTrue(init_args.force)

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

    def test_init_success_creates_usable_starter_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "research_ops"

            code, payload = self.run_cli_json(["init", str(target)])

            self.assertEqual(code, cli.SUCCESS)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["target_dir"], str(target))
            self.assertTrue((target / "queue.md").exists())
            self.assertTrue((target / "metrics_baseline.json").exists())
            self.assertTrue((target / "metrics_history.jsonl").exists())
            leftovers = [
                path.name
                for path in target.parent.iterdir()
                if path.name.startswith(f".{target.name}.staging-")
                or path.name.startswith(f".{target.name}.backup-")
            ]
            self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
