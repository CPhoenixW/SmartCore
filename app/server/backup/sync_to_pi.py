"""Rsync backup archives to Raspberry Pi and prune remote retention."""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path

from app.server.config import Settings, get_settings

Runner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


def _require_pi_settings(settings: Settings) -> None:
    if not settings.pi_user or not settings.pi_host or not settings.pi_backup_dir:
        raise ValueError("PI_USER, PI_HOST, and PI_BACKUP_DIR must be configured")


def build_rsync_command(
    local_backup_dir: Path,
    settings: Settings,
    *,
    dry_run: bool = False,
) -> list[str]:
    _require_pi_settings(settings)
    remote = f"{settings.pi_user}@{settings.pi_host}:{settings.pi_backup_dir}/"
    command = [
        "rsync",
        "-av",
        "--ignore-existing",
        f"{local_backup_dir}/",
        remote,
    ]
    if dry_run:
        command.insert(1, "--dry-run")
    return command


def build_remote_cleanup_command(settings: Settings) -> list[str]:
    _require_pi_settings(settings)
    retention_days = settings.pi_backup_retention_days
    remote_dir = settings.pi_backup_dir
    remote_script = (
        f"find {remote_dir} -maxdepth 1 -type f "
        f"-name 'smartcore-*.sqlite.gz' -mtime +{retention_days} -delete"
    )
    return ["ssh", f"{settings.pi_user}@{settings.pi_host}", remote_script]


def sync_to_pi(
    local_backup_dir: Path | None = None,
    settings: Settings | None = None,
    *,
    dry_run: bool = False,
    runner: Runner | None = None,
) -> subprocess.CompletedProcess[str]:
    cfg = settings or get_settings()
    backup_dir = local_backup_dir or cfg.backup_path
    command = build_rsync_command(backup_dir, cfg, dry_run=dry_run)
    execute = runner or _default_runner
    return execute(command)


def cleanup_remote_backups(
    settings: Settings | None = None,
    *,
    runner: Runner | None = None,
) -> subprocess.CompletedProcess[str]:
    cfg = settings or get_settings()
    command = build_remote_cleanup_command(cfg)
    execute = runner or _default_runner
    return execute(command)


def run_sync(
    settings: Settings | None = None,
    *,
    dry_run: bool = False,
    runner: Runner | None = None,
) -> subprocess.CompletedProcess[str]:
    """Sync local backups to Pi and prune expired remote snapshots."""
    cfg = settings or get_settings()
    result = sync_to_pi(settings=cfg, dry_run=dry_run, runner=runner)
    if not dry_run:
        cleanup_remote_backups(settings=cfg, runner=runner)
    return result


def _default_runner(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        check=True,
        capture_output=True,
        text=True,
    )
