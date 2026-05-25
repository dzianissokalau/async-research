"""Starter workspace smoke orchestration behind the public CLI command."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from async_research_workflow.cli_runner import function_json
from async_research_workflow.cli_runner import module_json
from async_research_workflow.cli_runner import print_json
from async_research_workflow.workspace_install import INVALID
from async_research_workflow.workspace_install import SUCCESS
from async_research_workflow.workspace_install import remove_path


ModuleJson = Callable[[str, Sequence[str]], tuple[int, dict]]
FunctionJson = Callable[[Callable[..., int], object], tuple[int, dict]]
PrintJson = Callable[[dict], None]
RemovePath = Callable[[Path], None]


@dataclass(frozen=True)
class StarterSmokeCheck:
    module_name: str
    argv: tuple[str, ...]

    def report(self, exit_code: int) -> dict:
        return {
            "command": self.module_name,
            "args": list(self.argv),
            "exit_code": exit_code,
            "ok": exit_code == SUCCESS,
        }

    def failure(self, exit_code: int, payload: dict) -> dict:
        return {
            "command": self.module_name,
            "args": list(self.argv),
            "exit_code": exit_code,
            "payload": payload,
        }


@dataclass(frozen=True)
class StarterSmokePlan:
    work_dir: Path
    ops_dir: Path
    template: str

    @classmethod
    def from_args(cls, args) -> "StarterSmokePlan":
        base = args.work_dir
        ops_dir = base if base.name == "research_ops" else base / "research_ops"
        return cls(work_dir=base, ops_dir=ops_dir, template=args.template)

    def init_args(self) -> argparse.Namespace:
        return argparse.Namespace(target_dir=self.ops_dir, template=self.template, force=True)

    def init_result(self, exit_code: int, payload: dict) -> dict:
        return {
            "command": "init",
            "args": [str(self.ops_dir), "--template", self.template, "--force"],
            "exit_code": exit_code,
            "ok": exit_code == SUCCESS and payload.get("ok", True) is not False,
            "payload": payload,
        }

    def checks(self) -> list[StarterSmokeCheck]:
        return [
            StarterSmokeCheck("check_schema_versions", (str(self.ops_dir),)),
            StarterSmokeCheck("autonomy_readiness_gate", (str(self.ops_dir), "--dry-run")),
            StarterSmokeCheck("health_check", (str(self.ops_dir), "--dry-run")),
            StarterSmokeCheck("human_review_surface", ("update", str(self.ops_dir))),
            StarterSmokeCheck("human_review_surface", ("validate", str(self.ops_dir))),
            StarterSmokeCheck("data_source_audit", ("validate", str(self.ops_dir))),
            StarterSmokeCheck("cost_tracking", ("summary", str(self.ops_dir))),
            StarterSmokeCheck("run_autonomy_benchmark", ()),
            StarterSmokeCheck("simulate_scheduled_week", (str(self.ops_dir),)),
        ]

    def envelope(self, ok: bool, init: dict, smoke: dict, checks: list[dict], failures: list[dict]) -> dict:
        return {
            "ok": ok,
            "action": "starter_smoke_checked",
            "work_dir": str(self.work_dir),
            "ops_dir": str(self.ops_dir),
            "template": self.template,
            "init": init,
            "smoke": smoke,
            "checks": checks,
            "failures": failures,
        }


@dataclass(frozen=True)
class StarterSmokeRunner:
    run_init_func: Callable[[object], int]
    module_json_func: ModuleJson = module_json
    function_json_func: FunctionJson = function_json
    print_json_func: PrintJson = print_json
    remove_path_func: RemovePath = remove_path

    def run(self, args) -> int:
        plan = StarterSmokePlan.from_args(args)
        base = plan.work_dir
        if base.exists() and not base.is_dir():
            self.print_json_func({
                "ok": False,
                "reason": "target_is_file",
                "work_dir": str(base),
                "ops_dir": str(plan.ops_dir),
                "next_step": "choose a directory work path",
            })
            return INVALID
        if base.exists() and any(base.iterdir()) and not args.force:
            self.print_json_func({
                "ok": False,
                "reason": "target_exists",
                "work_dir": str(base),
                "ops_dir": str(plan.ops_dir),
                "next_step": "rerun with --force or choose an empty work directory",
            })
            return INVALID
        if base.exists() and args.force:
            self.remove_path_func(base)

        init_code, init_payload = self.function_json_func(self.run_init_func, plan.init_args())
        init_result = plan.init_result(init_code, init_payload)
        if not init_result["ok"]:
            init_failure = {
                "command": "init",
                "args": init_result["args"],
                "exit_code": init_code,
                "payload": init_payload,
            }
            smoke_result = {"ok": False, "checks": [], "failures": [init_failure]}
            self.print_json_func(plan.envelope(
                False,
                init_result,
                smoke_result,
                [],
                [init_failure],
            ))
            return init_code if init_code != SUCCESS else INVALID

        failures: list[dict] = []
        reports: list[dict] = []
        for check in plan.checks():
            code, payload = self.module_json_func(check.module_name, list(check.argv))
            reports.append(check.report(code))
            if code != SUCCESS:
                failures.append(check.failure(code, payload))
        smoke_result = {"ok": not failures, "checks": reports, "failures": failures}
        self.print_json_func(plan.envelope(not failures, init_result, smoke_result, reports, failures))
        return SUCCESS if not failures else 1

