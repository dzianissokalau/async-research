#!/usr/bin/env python3
"""Read-only startup inspection for async-research operator sessions."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any


SUPPORTED_VERSION = "0.3.0a1"
SUPPORTED_RANGE = f"async-research-workflow=={SUPPORTED_VERSION}"
EXPECTED_TOP_LEVEL_COMMANDS = (
    "version",
    "init",
    "schema-check",
    "readiness",
    "health",
    "workflow",
    "console",
)
EXPECTED_NESTED_COMMANDS = {
    "workflow": ("next",),
    "console": ("snapshot",),
}
READ_ONLY_CHECKS = (
    ("schema_check", ("schema-check", "{ops_dir}")),
    ("readiness_dry_run", ("readiness", "{ops_dir}", "--dry-run")),
    ("health_dry_run", ("health", "{ops_dir}", "--dry-run")),
    ("workflow_next", ("workflow", "next", "{ops_dir}")),
    ("console_snapshot", ("console", "snapshot", "{ops_dir}", "--json")),
)


def json_dump(payload: dict[str, Any], *, indent: int = 2) -> None:
    print(json.dumps(payload, indent=indent, sort_keys=True))


def resolve_path(value: str | Path, base: Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (base / path).resolve()


def command_result(
    args: list[str],
    *,
    cwd: Path,
    timeout_seconds: float,
) -> dict[str, Any]:
    command = [str(arg) for arg in args]
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd) if cwd.exists() else None,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_seconds,
        )
    except FileNotFoundError as exc:
        return {
            "command": command,
            "returncode": None,
            "stdout": "",
            "stderr": str(exc),
            "status": "missing_executable",
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "returncode": None,
            "stdout": text_output(exc.stdout),
            "stderr": text_output(exc.stderr),
            "status": "timeout",
        }

    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "status": "passed" if completed.returncode == 0 else "failed",
    }


def text_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def compact_command_output(result: dict[str, Any]) -> dict[str, Any]:
    compact = {
        "command": result["command"],
        "returncode": result["returncode"],
        "status": result["status"],
    }
    stdout = result.get("stdout") or ""
    stderr = result.get("stderr") or ""
    if stdout.strip():
        compact["stdout_preview"] = stdout.strip()[:2000]
        parsed = parse_json_text(stdout)
        if parsed is not None:
            compact["stdout_json"] = parsed
    if stderr.strip():
        compact["stderr_preview"] = stderr.strip()[:1200]
    return compact


def parse_json_text(value: str) -> Any | None:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def parse_command_group(help_text: str) -> list[str]:
    match = re.search(r"\{([^{}]+)\}", help_text, flags=re.DOTALL)
    if not match:
        return []
    names: list[str] = []
    for raw in match.group(1).replace("\n", "").split(","):
        name = raw.strip()
        if re.fullmatch(r"[a-z][a-z0-9-]*", name):
            names.append(name)
    return sorted(dict.fromkeys(names))


def detected_subcommands(help_text: str, expected_children: tuple[str, ...]) -> list[str]:
    commands = set(parse_command_group(help_text))
    for expected in expected_children:
        if re.search(rf"\b{re.escape(expected)}\b", help_text):
            commands.add(expected)
    return sorted(commands)


def parse_cli_version(stdout: str) -> str | None:
    parsed = parse_json_text(stdout)
    if isinstance(parsed, dict) and isinstance(parsed.get("version"), str):
        return parsed["version"]
    match = re.search(r"\b\d+\.\d+\.\d+(?:[a-z]\d+)?\b", stdout)
    if match:
        return match.group(0)
    return None


def candidate_cli_path(
    workspace: Path,
    repo_root: Path,
    explicit_cli: str | None,
) -> dict[str, Any]:
    if explicit_cli:
        path = resolve_path(explicit_cli, workspace)
        return {
            "path": str(path),
            "source": "explicit",
            "exists": path.is_file(),
            "executable": path.is_file() and os.access(path, os.X_OK),
        }

    active = shutil.which("async-research")
    if active:
        path = Path(active).resolve()
        return {
            "path": str(path),
            "source": "active_shell",
            "exists": path.is_file(),
            "executable": os.access(path, os.X_OK),
        }

    for source, local in (
        ("project_local_venv", workspace / ".venv" / "bin" / "async-research"),
        ("repo_root_venv", repo_root / ".venv" / "bin" / "async-research"),
    ):
        if local.is_file():
            return {
                "path": str(local.resolve()),
                "source": source,
                "exists": True,
                "executable": os.access(local, os.X_OK),
            }

    return {
        "path": None,
        "source": "missing",
        "exists": False,
        "executable": False,
    }


def inspect_cli(
    workspace: Path,
    repo_root: Path,
    explicit_cli: str | None,
    timeout_seconds: float,
) -> dict[str, Any]:
    cli = candidate_cli_path(workspace, repo_root, explicit_cli)
    cli.update(
        {
            "usable": False,
            "supported_range": SUPPORTED_RANGE,
            "version": None,
            "version_status": "missing",
            "top_level_commands": [],
            "nested_commands": {},
            "missing_expected_commands": list(EXPECTED_TOP_LEVEL_COMMANDS),
            "missing_expected_nested_commands": {
                key: list(value) for key, value in EXPECTED_NESTED_COMMANDS.items()
            },
            "diagnostics": [],
        }
    )
    if not cli["path"]:
        cli["diagnostics"].append("async-research CLI was not found.")
        return cli
    if not cli["executable"]:
        cli["diagnostics"].append("CLI candidate exists but is not executable.")
        return cli

    cli_path = str(cli["path"])
    version_result = command_result(
        [cli_path, "version"],
        cwd=workspace,
        timeout_seconds=timeout_seconds,
    )
    help_result = command_result(
        [cli_path, "--help"],
        cwd=workspace,
        timeout_seconds=timeout_seconds,
    )
    cli["version_command"] = compact_command_output(version_result)
    cli["help_command"] = compact_command_output(help_result)
    cli["usable"] = version_result["returncode"] == 0 and help_result["returncode"] == 0
    cli["version"] = parse_cli_version(version_result.get("stdout") or "")
    if cli["version"] == SUPPORTED_VERSION:
        cli["version_status"] = "matches_supported_range"
    elif cli["version"]:
        cli["version_status"] = "version_drift"
        cli["diagnostics"].append(
            f"Detected async-research version {cli['version']} differs from {SUPPORTED_RANGE}."
        )
    else:
        cli["version_status"] = "unknown"
        cli["diagnostics"].append("Could not parse async-research version output.")

    top_level = parse_command_group(help_result.get("stdout") or "")
    cli["top_level_commands"] = top_level
    cli["missing_expected_commands"] = [
        command for command in EXPECTED_TOP_LEVEL_COMMANDS if command not in top_level
    ]
    if cli["missing_expected_commands"]:
        cli["diagnostics"].append(
            "Missing expected top-level commands: "
            + ", ".join(cli["missing_expected_commands"])
        )

    nested: dict[str, list[str]] = {}
    missing_nested: dict[str, list[str]] = {}
    for parent, expected_children in EXPECTED_NESTED_COMMANDS.items():
        if parent not in top_level:
            missing_nested[parent] = list(expected_children)
            continue
        child_result = command_result(
            [cli_path, parent, "--help"],
            cwd=workspace,
            timeout_seconds=timeout_seconds,
        )
        commands = detected_subcommands(
            child_result.get("stdout") or "",
            expected_children,
        )
        nested[parent] = commands
        missing = [command for command in expected_children if command not in commands]
        if missing:
            missing_nested[parent] = missing
    cli["nested_commands"] = nested
    cli["missing_expected_nested_commands"] = missing_nested
    if missing_nested:
        formatted = [
            f"{parent}: {', '.join(children)}" for parent, children in missing_nested.items()
        ]
        cli["diagnostics"].append("Missing expected subcommands: " + "; ".join(formatted))
    return cli


def sanitized_remote_url(url: str) -> str:
    return re.sub(r"(https?://)[^/@]+@", r"\1***@", url)


def inspect_git(workspace: Path, timeout_seconds: float) -> dict[str, Any]:
    inside = command_result(
        ["git", "-C", str(workspace), "rev-parse", "--is-inside-work-tree"],
        cwd=workspace,
        timeout_seconds=timeout_seconds,
    )
    info: dict[str, Any] = {
        "inside_work_tree": None,
        "top_level": None,
        "remotes": [],
        "diagnostics": [],
    }
    if inside["returncode"] != 0:
        info["inside_work_tree"] = False
        message = inside.get("stderr") or inside.get("stdout") or "not inside a git worktree"
        info["diagnostics"].append(message.strip())
        return info

    info["inside_work_tree"] = (inside.get("stdout") or "").strip() == "true"
    top = command_result(
        ["git", "-C", str(workspace), "rev-parse", "--show-toplevel"],
        cwd=workspace,
        timeout_seconds=timeout_seconds,
    )
    if top["returncode"] == 0:
        info["top_level"] = (top.get("stdout") or "").strip()

    remotes = command_result(
        ["git", "-C", str(workspace), "remote", "-v"],
        cwd=workspace,
        timeout_seconds=timeout_seconds,
    )
    seen: set[tuple[str, str]] = set()
    for line in (remotes.get("stdout") or "").splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        name, url = parts[0], sanitized_remote_url(parts[1])
        key = (name, url)
        if key not in seen:
            info["remotes"].append({"name": name, "url": url})
            seen.add(key)
    return info


def project_name(root: Path) -> str | None:
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        return None
    try:
        payload = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return None
    project = payload.get("project")
    if isinstance(project, dict) and isinstance(project.get("name"), str):
        return project["name"]
    return None


def detect_research_ops(
    workspace: Path,
    repo_root: Path,
    explicit_research_ops: str | None,
) -> dict[str, Any]:
    if explicit_research_ops:
        path = resolve_path(explicit_research_ops, workspace)
        return {
            "path": str(path),
            "source": "explicit",
            "exists": path.is_dir(),
            "proposed_path": str(path),
        }

    candidates = []
    for candidate in (workspace / "research_ops", repo_root / "research_ops"):
        resolved = candidate.resolve()
        if resolved not in candidates:
            candidates.append(resolved)
    for candidate in candidates:
        if candidate.is_dir():
            return {
                "path": str(candidate),
                "source": "current_repo",
                "exists": True,
                "proposed_path": str(candidate),
            }
    return {
        "path": None,
        "source": "missing",
        "exists": False,
        "proposed_path": str(candidates[0]),
    }


def classify_repo(repo_root: Path, research_ops: dict[str, Any]) -> str:
    is_framework = (
        project_name(repo_root) == "async-research-workflow"
        or (repo_root / "src" / "async_research_workflow").is_dir()
    )
    has_research_ops = bool(research_ops.get("exists"))
    if is_framework and has_research_ops:
        return "framework_repo_with_research_ops"
    if is_framework:
        return "framework_repo"
    if has_research_ops:
        return "research_workspace"
    return "unknown_repo"


def privacy_boundary(repo_kind: str, git_info: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    if repo_kind.startswith("framework_repo"):
        reasons.append("framework_repo_is_not_a_default_research_state_target")
    if git_info.get("inside_work_tree") is not True:
        reasons.append("repo_visibility_unknown_without_git_metadata")
    for remote in git_info.get("remotes", []):
        url = str(remote.get("url") or "")
        if any(host in url for host in ("github.com", "gitlab.com", "bitbucket.org")):
            reasons.append("hosted_remote_visibility_unknown")
            break

    return {
        "status": "approval_required" if reasons else "no_boundary_flags",
        "requires_approval_before_research_writes": bool(reasons),
        "safe_for_research_state_writes": not reasons,
        "reasons": reasons,
    }


def run_read_only_checks(
    *,
    cli: dict[str, Any],
    research_ops: dict[str, Any],
    workspace: Path,
    timeout_seconds: float,
    requested: bool,
) -> dict[str, Any]:
    if not requested:
        return {"requested": False, "status": "not_requested", "checks": []}
    if not cli.get("path") or not cli.get("executable"):
        return {
            "requested": True,
            "status": "skipped",
            "reason": "missing_cli",
            "checks": [],
        }
    if not research_ops.get("exists"):
        return {
            "requested": True,
            "status": "skipped",
            "reason": "missing_research_ops",
            "checks": [],
        }

    checks = []
    for name, template in READ_ONLY_CHECKS:
        command = [
            str(cli["path"]),
            *[
                str(research_ops["path"]) if part == "{ops_dir}" else part
                for part in template
            ],
        ]
        result = command_result(command, cwd=workspace, timeout_seconds=timeout_seconds)
        compact = compact_command_output(result)
        compact["name"] = name
        checks.append(compact)

    failed = [check["name"] for check in checks if check["status"] != "passed"]
    return {
        "requested": True,
        "status": "failed" if failed else "passed",
        "failed_checks": failed,
        "checks": checks,
    }


def setup_recommendations(
    cli: dict[str, Any],
    research_ops: dict[str, Any],
    privacy: dict[str, Any],
) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []
    if not cli.get("path") or not cli.get("executable"):
        recommendations.append(
            {
                "reason": "missing_cli",
                "action": (
                    "Ask the user to choose a guided setup path: provide an existing "
                    "CLI path, approve a project-local .venv using the checked-out "
                    "framework repo, or explicitly approve a pinned package/release install."
                ),
                "requires_approval": True,
                "must_not_do_automatically": [
                    "create virtual environments",
                    "install packages",
                    "clone or fetch from the network",
                    "modify shell configuration",
                    "perform global installs",
                ],
            }
        )
    if cli.get("version_status") == "version_drift":
        recommendations.append(
            {
                "reason": "version_drift",
                "action": (
                    "Report the detected version drift, probe command capabilities, "
                    "and avoid recipes whose commands are missing."
                ),
                "requires_approval": False,
            }
        )
    if cli.get("missing_expected_commands") or cli.get("missing_expected_nested_commands"):
        recommendations.append(
            {
                "reason": "capability_gap",
                "action": (
                    "Report missing command capabilities and do not invent internal "
                    "replacement actions."
                ),
                "requires_approval": False,
            }
        )
    if not research_ops.get("exists"):
        recommendations.append(
            {
                "reason": "missing_research_ops",
                "action": (
                    f"Ask before running async-research init or creating files at "
                    f"{research_ops.get('proposed_path')}."
                ),
                "requires_approval": True,
            }
        )
    if privacy.get("requires_approval_before_research_writes"):
        recommendations.append(
            {
                "reason": "privacy_boundary",
                "action": (
                    "Confirm the repository is private or explicitly approved before "
                    "creating or writing research state."
                ),
                "requires_approval": True,
                "boundary_reasons": privacy.get("reasons", []),
            }
        )
    return recommendations


def state_summary(
    cli: dict[str, Any],
    research_ops: dict[str, Any],
    privacy: dict[str, Any],
    read_only_checks: dict[str, Any],
) -> dict[str, Any]:
    if not cli.get("path") or not cli.get("executable"):
        cli_status = "missing"
    elif not cli.get("usable"):
        cli_status = "unusable"
    elif cli.get("version_status") == "version_drift":
        cli_status = "usable_with_version_drift"
    else:
        cli_status = "usable"

    return {
        "cli": cli_status,
        "research_ops": "found" if research_ops.get("exists") else "missing",
        "privacy_boundary": privacy["status"],
        "read_only_checks": read_only_checks["status"],
    }


def next_safe_action(
    cli: dict[str, Any],
    research_ops: dict[str, Any],
    privacy: dict[str, Any],
    read_only_checks: dict[str, Any],
) -> str:
    if not cli.get("path") or not cli.get("executable"):
        return "Ask the user to choose a guided CLI setup path; do not install yet."
    if privacy.get("requires_approval_before_research_writes") and not research_ops.get("exists"):
        return "Ask whether this repo is private or approved before initializing research_ops."
    if not research_ops.get("exists"):
        return "Ask before bootstrapping research_ops at the proposed path."
    if cli.get("missing_expected_commands") or cli.get("missing_expected_nested_commands"):
        return "Report missing CLI capabilities and avoid unsupported command recipes."
    if read_only_checks["status"] == "not_requested":
        return "Run this helper with --run-read-only-checks or run the startup read-only commands manually."
    if read_only_checks["status"] == "failed":
        return "Resolve failing read-only checks before operating the workspace."
    return "Use async-research workflow next and the console snapshot to choose the next bounded action."


def help_payload() -> dict[str, Any]:
    return {
        "ok": True,
        "usage": "inspect_workspace.py [--workspace PATH] [--research-ops PATH] [--cli PATH] [--run-read-only-checks]",
        "description": "Emit read-only JSON diagnostics for async-research operator startup.",
        "options": {
            "--workspace": "Directory to inspect; defaults to the current working directory.",
            "--research-ops": "Explicit research_ops path, relative to --workspace when not absolute.",
            "--cli": "Explicit async-research CLI path, relative to --workspace when not absolute.",
            "--run-read-only-checks": "Run schema, readiness, health, workflow next, and console snapshot checks.",
            "--timeout-seconds": "Per-command timeout for CLI and git probes.",
            "--json-indent": "Indentation for emitted JSON.",
            "-h, --help": "Print this JSON help payload.",
        },
    }


def parse_args(argv: list[str]) -> tuple[dict[str, Any] | None, int, Any]:
    import argparse

    class JsonArgumentParser(argparse.ArgumentParser):
        def error(self, message: str) -> None:
            raise ValueError(message)

    parser = JsonArgumentParser(add_help=False)
    parser.add_argument("-h", "--help", action="store_true", dest="show_help")
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--research-ops")
    parser.add_argument("--cli")
    parser.add_argument("--run-read-only-checks", action="store_true")
    parser.add_argument("--timeout-seconds", type=float, default=8.0)
    parser.add_argument("--json-indent", type=int, default=2)
    try:
        args, unknown = parser.parse_known_args(argv)
    except ValueError as exc:
        return {
            "ok": False,
            "error": "invalid_arguments",
            "message": str(exc),
        }, 2, None
    if args.show_help:
        return help_payload(), 0, args
    if unknown:
        return {
            "ok": False,
            "error": "unknown_arguments",
            "unknown_arguments": unknown,
        }, 2, args
    return None, 0, args


def inspect_workspace(args: Any) -> dict[str, Any]:
    workspace = resolve_path(args.workspace, Path.cwd())
    git = inspect_git(workspace, args.timeout_seconds)
    repo_root = Path(git["top_level"]).resolve() if git.get("top_level") else workspace
    research_ops = detect_research_ops(workspace, repo_root, args.research_ops)
    repo_kind = classify_repo(repo_root, research_ops)
    git["repo_kind"] = repo_kind
    privacy = privacy_boundary(repo_kind, git)
    git["privacy_boundary"] = privacy

    cli = inspect_cli(workspace, repo_root, args.cli, args.timeout_seconds)
    read_only = run_read_only_checks(
        cli=cli,
        research_ops=research_ops,
        workspace=workspace,
        timeout_seconds=args.timeout_seconds,
        requested=args.run_read_only_checks,
    )
    summary = state_summary(cli, research_ops, privacy, read_only)
    recommendations = setup_recommendations(cli, research_ops, privacy)

    return {
        "ok": True,
        "mutations_performed": [],
        "supported_range": SUPPORTED_RANGE,
        "workspace": {
            "path": str(workspace),
            "exists": workspace.is_dir(),
        },
        "git": git,
        "cli": cli,
        "research_ops": research_ops,
        "read_only_checks": read_only,
        "state_summary": summary,
        "setup_recommendations": recommendations,
        "next_safe_action": next_safe_action(cli, research_ops, privacy, read_only),
    }


def main(argv: list[str] | None = None) -> int:
    payload, code, args = parse_args(list(argv or []))
    if payload is not None:
        json_dump(payload, indent=getattr(args, "json_indent", 2))
        return code
    result = inspect_workspace(args)
    json_dump(result, indent=args.json_indent)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
