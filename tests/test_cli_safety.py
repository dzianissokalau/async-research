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


if __name__ == "__main__":
    unittest.main()
