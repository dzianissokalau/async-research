from __future__ import annotations

import ast
import importlib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "src" / "async_research_workflow" / "scripts"


def script_paths() -> list[Path]:
    return sorted(path for path in SCRIPTS_DIR.glob("*.py") if path.name != "__init__.py")


class ScriptImportTests(unittest.TestCase):
    def test_scripts_do_not_mutate_sys_path_for_sibling_imports(self) -> None:
        offenders = []
        for path in script_paths():
            text = path.read_text(encoding="utf-8")
            if "sys.path.insert" in text or "sys.path.append" in text:
                offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual([], offenders)

    def test_scripts_use_package_qualified_sibling_imports(self) -> None:
        script_module_names = {path.stem for path in script_paths()}
        offenders = []
        for path in script_paths():
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    root_module = node.module.split(".", 1)[0]
                    if root_module in script_module_names:
                        offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}: from {node.module} import ...")
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        root_module = alias.name.split(".", 1)[0]
                        if root_module in script_module_names:
                            offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}: import {alias.name}")
        self.assertEqual([], offenders)

    def test_script_modules_import_from_package_namespace(self) -> None:
        failures = []
        for path in script_paths():
            module_name = f"async_research_workflow.scripts.{path.stem}"
            try:
                importlib.import_module(module_name)
            except Exception as exc:  # pragma: no cover - failure message preserves exact import error.
                failures.append(f"{module_name}: {exc!r}")
        self.assertEqual([], failures)


if __name__ == "__main__":
    unittest.main()
