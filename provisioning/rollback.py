#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - Real system-file backup/rollback mechanism
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Real, host-independent backup/rollback mechanism for system files this
project's installers overwrite (e.g. the systemd unit in
install_local_agent.sh).

Provisioning scripts run as root on a real CM5, which this dev machine
can't do - but the actual backup/restore logic (copy a file aside
before overwriting it; restore-or-delete it later depending on whether
it existed before) is pure file I/O, fully testable against any
writable directory standing in for a real system path.
`tools/verify_rollback.py` proves this exact code path correct without
root or a CM5; a real installer invokes the same `backup`/`restore` CLI
subcommands below against real paths.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path


class RollbackError(Exception):
    """A manifest or backup file is missing or inconsistent - restoring
    would risk doing the wrong thing, so this always aborts loudly
    rather than guessing."""


@dataclass
class RollbackEntry:
    target: str
    existed_before: bool
    backup_path: str | None


@dataclass
class RollbackManifest:
    entries: list[RollbackEntry] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps([entry.__dict__ for entry in self.entries], indent=2)

    @classmethod
    def from_json(cls, text: str) -> "RollbackManifest":
        raw = json.loads(text)
        return cls(entries=[RollbackEntry(**item) for item in raw])


def backup_before_write(target: Path, backup_dir: Path, manifest_path: Path) -> None:
    """Real backup of `target` before an installer overwrites it, and a
    real, append-only record of what happened so `restore_all()` later
    knows exactly what to undo. Repeated backups of the same `target` in
    one session are recorded in order and restored most-recent-first
    (LIFO) - correct for this project's real installers, which each
    write a given system file at most once per run."""
    manifest = (
        RollbackManifest.from_json(manifest_path.read_text(encoding="utf-8"))
        if manifest_path.is_file()
        else RollbackManifest()
    )

    existed = target.is_file()
    backup_path: str | None = None
    if existed:
        backup_dir.mkdir(parents=True, exist_ok=True)
        destination = backup_dir / f"{len(manifest.entries):04d}-{target.name}"
        shutil.copy2(target, destination)
        backup_path = str(destination)

    manifest.entries.append(RollbackEntry(target=str(target), existed_before=existed, backup_path=backup_path))
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(manifest.to_json(), encoding="utf-8")


def restore_all(manifest_path: Path) -> list[str]:
    """Real rollback of every real file recorded in `manifest_path`,
    most-recent first - each target is restored from its real backup if
    it existed before the installer touched it, or deleted if the
    installer created it fresh. Idempotent: restoring twice in a row is
    a real no-op the second time (the file is already back in its
    pre-install state), never an error - safe to re-run."""
    if not manifest_path.is_file():
        raise RollbackError(f"no rollback manifest at {manifest_path} - nothing to restore")
    manifest = RollbackManifest.from_json(manifest_path.read_text(encoding="utf-8"))

    restored: list[str] = []
    for entry in reversed(manifest.entries):
        target = Path(entry.target)
        if entry.existed_before:
            if not entry.backup_path:
                raise RollbackError(f"{entry.target}: recorded as pre-existing but has no backup path")
            backup = Path(entry.backup_path)
            if not backup.is_file():
                raise RollbackError(f"{entry.target}: backup {backup} is missing - cannot restore safely")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup, target)
        else:
            target.unlink(missing_ok=True)
        restored.append(entry.target)
    return restored


def _cmd_backup(args: argparse.Namespace) -> int:
    backup_before_write(args.target, args.backup_dir, args.manifest)
    print(f"ROLLBACK_BACKUP=PASS target={args.target}")
    return 0


def _cmd_restore(args: argparse.Namespace) -> int:
    try:
        restored = restore_all(args.manifest)
    except RollbackError as exc:
        print(f"ROLLBACK_RESTORE=FAIL {exc}", file=sys.stderr)
        return 1
    print(f"ROLLBACK_RESTORE=PASS restored={len(restored)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    backup = subparsers.add_parser("backup", help="Back up one real file before an installer overwrites it.")
    backup.add_argument("target", type=Path)
    backup.add_argument("--backup-dir", type=Path, required=True)
    backup.add_argument("--manifest", type=Path, required=True)
    backup.set_defaults(func=_cmd_backup)

    restore = subparsers.add_parser("restore", help="Restore every real file recorded in a rollback manifest.")
    restore.add_argument("--manifest", type=Path, required=True)
    restore.set_defaults(func=_cmd_restore)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
