"""Workspace installation and rollback services for starter templates."""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from async_research_workflow.cli_runner import module_json
from async_research_workflow.cli_runner import print_json
from async_research_workflow.resources import template_path


SUCCESS = 0
INVALID = 4
TEMPLATES = {
    "generic": ("generic_research_ops_starter", "research_ops"),
    "real-estate": ("research_ops_starter", "research_ops"),
}


ModuleJson = Callable[[str, list[str]], tuple[int, dict]]
PrintJson = Callable[[dict], None]
CopyTree = Callable[[object, Path, bool], None]
RemovePath = Callable[[Path], None]
RestoreTarget = Callable[[Path, Path | None, bool], None]


def template_root(template: str):
    parts = TEMPLATES.get(template)
    if parts is None:
        raise ValueError(f"unsupported template: {template}")
    return template_path(*parts)


def copy_resource_tree(src, dst: Path, force: bool = False) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        if item.name in {".DS_Store", "__pycache__"}:
            continue
        target = dst / item.name
        if item.is_dir():
            copy_resource_tree(item, target, force=force)
            continue
        if target.exists() and not force:
            raise FileExistsError(f"target file already exists: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(item.read_bytes())


def remove_path(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if path.is_symlink() or path.is_file():
        path.unlink()
        return
    shutil.rmtree(path)


def restore_target(target: Path, backup: Path | None, target_installed: bool) -> None:
    if backup is not None and backup.exists():
        remove_path(target)
        shutil.move(str(backup), str(target))
        return
    if target_installed:
        remove_path(target)


def rollback_target(
    target: Path,
    backup: Path | None,
    target_installed: bool,
    *,
    restore_target_func: RestoreTarget = restore_target,
) -> tuple[bool, str | None]:
    try:
        restore_target_func(target, backup, target_installed)
    except Exception as exc:
        return False, str(exc)
    return True, None


@dataclass(frozen=True)
class WorkspaceInstaller:
    """Install a starter workspace transactionally."""

    module_json_func: ModuleJson = module_json
    print_json_func: PrintJson = print_json
    copy_resource_tree_func: CopyTree = copy_resource_tree
    remove_path_func: RemovePath = remove_path
    restore_target_func: RestoreTarget = restore_target

    def run(self, args) -> int:
        target = args.target_dir
        staging: Path | None = None
        backup_root: Path | None = None
        backup: Path | None = None
        target_installed = False
        preserve_backup_root = False
        try:
            source = template_root(args.template)
            if target.exists() and not target.is_dir() and not args.force:
                self.print_json_func({
                    "ok": False,
                    "reason": "target_exists",
                    "target_dir": str(target),
                    "next_step": "rerun with --force or choose an empty target directory",
                })
                return INVALID
            if target.exists() and target.is_dir() and any(target.iterdir()) and not args.force:
                self.print_json_func({
                    "ok": False,
                    "reason": "target_exists",
                    "target_dir": str(target),
                    "next_step": "rerun with --force or choose an empty target directory",
                })
                return INVALID
            target.parent.mkdir(parents=True, exist_ok=True)
            staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.staging-", dir=target.parent))
            self.copy_resource_tree_func(source, staging, True)
            if target.exists():
                backup_root = Path(tempfile.mkdtemp(prefix=f".{target.name}.backup-", dir=target.parent))
                backup = backup_root / target.name
                shutil.move(str(target), str(backup))
            shutil.move(str(staging), str(target))
            staging = None
            target_installed = True
            metrics_init_code, metrics_init = self.module_json_func(
                "metrics_history",
                ["init", str(target), "--label", "starter_init", "--force"],
            )
            metrics_append_code, metrics_append = self.module_json_func(
                "metrics_history",
                ["append-snapshot", str(target), "--label", "starter_init"],
            )
            if metrics_init_code != SUCCESS or metrics_append_code != SUCCESS:
                rollback_ok, rollback_error = rollback_target(
                    target,
                    backup,
                    target_installed,
                    restore_target_func=self.restore_target_func,
                )
                preserve_backup_root = not rollback_ok
                payload = {
                    "ok": False,
                    "reason": "starter_metrics_init_failed",
                    "target_dir": str(target),
                    "metrics_init": metrics_init,
                    "metrics_append": metrics_append,
                }
                if rollback_error is not None:
                    payload["rollback_error"] = rollback_error
                    if backup_root is not None:
                        payload["backup_dir"] = str(backup_root)
                self.print_json_func(payload)
                return INVALID
        except Exception as exc:
            rollback_ok, rollback_error = rollback_target(
                target,
                backup,
                target_installed,
                restore_target_func=self.restore_target_func,
            )
            preserve_backup_root = not rollback_ok
            payload = {"ok": False, "reason": "init_failed", "error": str(exc), "target_dir": str(target)}
            if rollback_error is not None:
                payload["rollback_error"] = rollback_error
                if backup_root is not None:
                    payload["backup_dir"] = str(backup_root)
            self.print_json_func(payload)
            return INVALID
        finally:
            if staging is not None:
                self.remove_path_func(staging)
            if backup_root is not None and not preserve_backup_root:
                shutil.rmtree(backup_root, ignore_errors=True)
        self.print_json_func({"ok": True, "action": "initialized", "target_dir": str(target), "template": args.template})
        return SUCCESS

