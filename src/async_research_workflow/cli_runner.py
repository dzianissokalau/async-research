"""Internal helpers for dispatching script-backed CLI commands."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
import importlib
import io
import json
from pathlib import Path
from typing import Callable, Sequence


@dataclass(frozen=True)
class ScriptCall:
    """Exact backing script invocation for a public CLI wrapper."""

    module_name: str
    argv: tuple[str, ...]


def script_call(module_name: str, argv: Sequence[str]) -> ScriptCall:
    return ScriptCall(module_name=module_name, argv=tuple(argv))


def print_json(payload: dict) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def json_payload_from_output(code: int, text: str) -> dict:
    text = text.strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {"ok": code == 0, "raw_output": text}
    if isinstance(payload, dict):
        return payload
    return {"ok": code == 0, "value": payload}


def module_main(module_name: str, argv: Sequence[str]) -> int:
    module = importlib.import_module(f"async_research_workflow.scripts.{module_name}")
    return int(module.main(list(argv)))


def run_script_call(call: ScriptCall) -> int:
    return module_main(call.module_name, call.argv)


def module_json(module_name: str, argv: Sequence[str]) -> tuple[int, dict]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = module_main(module_name, argv)
    return code, json_payload_from_output(code, stream.getvalue())


def function_json(function: Callable[..., int], *args) -> tuple[int, dict]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = int(function(*args))
    return code, json_payload_from_output(code, stream.getvalue())


def optional_path(flag: str, value: Path | None) -> list[str]:
    return [flag, str(value)] if value else []


def optional_text(flag: str, value: str | None) -> list[str]:
    return [flag, value] if value else []


def optional_number(flag: str, value: float | None) -> list[str]:
    return [flag, str(value)] if value is not None else []


def repeated_option(flag: str, values: Sequence[str] | None) -> list[str]:
    args: list[str] = []
    for value in values or []:
        args.extend([flag, str(value)])
    return args
