#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - What cm5_recovery.sh saves and restores
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The scope of the backup of cm5_recovery.sh, computed from what is installed instead of a fixed list.

The scope is every HYDRA-UMC piece of state found under a root (`/` on a device; a temporary folder in the tests):

  - the configuration folders `etc/hydra-umc` and `etc/hydra-umc-*` (the detection model registry, the node healing nodes, the technician settings...)
  - the state folders `var/lib/hydra-umc` and `var/lib/hydra-umc-*` (Wi-Fi credentials, rollback copies, journals)
  - the data folder of every installed program, `opt/hydra-umc/<program>/data` (the server, the data lake, the job dispatcher...)
  - the unit files `etc/systemd/system/hydra-umc-*.service` (and their `.d` folders)
  - the polkit rules `etc/polkit-1/rules.d/*hydra-umc*.rules`

SQLite databases are not copied while the program that owns them may be writing: `snapshot` makes a consistent copy of each one with the SQLite backup API
(the same as `sqlite3 .backup`, without needing the command line tool), and `live-db-files` names the live files (the database and its -wal / -shm) so the
archive leaves them out and holds the consistent copies instead.

Commands (all take --root, default /):
  list                     the top-level paths to archive, relative to the root, one per line
  live-db-files            the live database files (with their -wal/-shm) to leave out of the archive
  snapshot --stage DIR     write a consistent copy of every database to DIR, with the same relative path
  check-members            read an archive listing on standard input; exit 1 with the reason when a path is unsafe or outside the scope
  drop-sidecars            read an archive listing on standard input and remove the -wal/-shm files that belong to databases about to be restored
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from pathlib import Path

DB_SUFFIXES = (".db", ".sqlite", ".sqlite3")
SQLITE_MAGIC = b"SQLite format 3\x00"

# one source for the scope: the same patterns select what is saved (relative to the root) and what a restore accepts
ALLOWED_MEMBER = re.compile(
    r"^(?:"
    r"etc/hydra-umc(?:-[A-Za-z0-9._-]+)?"
    r"|var/lib/hydra-umc(?:-[A-Za-z0-9._-]+)?"
    r"|opt/hydra-umc/[A-Za-z0-9._-]+/data"
    r"|etc/systemd/system/hydra-umc-[A-Za-z0-9._-]+\.service(?:\.d)?"
    r"|etc/polkit-1/rules\.d/[A-Za-z0-9._-]*hydra-umc[A-Za-z0-9._-]*\.rules"
    r")(?:/.*)?$"
)


def member_problem(name: str) -> str | None:
    """Why an archive member must be refused (None when it is inside the scope)."""
    cleaned = name[2:] if name.startswith("./") else name
    cleaned = cleaned.rstrip("/")
    if not cleaned or cleaned == ".":
        return None  # the root entry of an archive made with -C
    if cleaned.startswith("/") or any(part == ".." for part in cleaned.split("/")):
        return f"unsafe path: {name}"
    if ALLOWED_MEMBER.match(cleaned) is None:
        return f"outside the HYDRA-UMC recovery scope: {name}"
    return None


def top_level_paths(root: Path) -> list[str]:
    found: list[str] = []
    for pattern in ("etc/hydra-umc", "etc/hydra-umc-*", "var/lib/hydra-umc", "var/lib/hydra-umc-*", "opt/hydra-umc/*/data",
                    "etc/systemd/system/hydra-umc-*.service", "etc/systemd/system/hydra-umc-*.service.d", "etc/polkit-1/rules.d/*hydra-umc*.rules"):
        for path in sorted(root.glob(pattern)):
            relative = path.relative_to(root).as_posix()
            if (path.exists() or path.is_symlink()) and ALLOWED_MEMBER.match(relative) and relative not in found:
                found.append(relative)
    return found


def is_sqlite(path: Path) -> bool:
    if path.suffix not in DB_SUFFIXES or not path.is_file() or path.is_symlink():
        return False
    try:
        with path.open("rb") as handle:
            return handle.read(len(SQLITE_MAGIC)) == SQLITE_MAGIC
    except OSError:
        return False


def databases(root: Path) -> list[Path]:
    found: list[Path] = []
    for top in top_level_paths(root):
        base = root / top
        candidates = [base] if base.is_file() else [p for p in sorted(base.rglob("*")) if p.is_file()] if base.is_dir() else []
        found.extend(p for p in candidates if is_sqlite(p))
    return found


def live_db_files(root: Path) -> list[str]:
    names: list[str] = []
    for database in databases(root):
        relative = database.relative_to(root).as_posix()
        names.append(relative)
        for sidecar in ("-wal", "-shm", "-journal"):
            if (root / (relative + sidecar)).exists():
                names.append(relative + sidecar)
    return names


def snapshot(root: Path, stage: Path) -> list[str]:
    copied: list[str] = []
    for database in databases(root):
        relative = database.relative_to(root)
        target = stage / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        source = sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True, timeout=30)
        destination = sqlite3.connect(str(target))
        try:
            source.backup(destination)
        finally:
            destination.close()
            source.close()
        try:
            target.chmod(database.stat().st_mode & 0o777)
        except OSError:
            pass
        copied.append(relative.as_posix())
    return copied


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("list", "live-db-files", "snapshot", "check-members", "drop-sidecars"))
    parser.add_argument("--root", type=Path, default=Path("/"))
    parser.add_argument("--stage", type=Path)
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(newline=chr(10))  # the shell reads one path per line: no carriage returns, whatever the system
    if args.command == "list":
        print("\n".join(top_level_paths(args.root)))
    elif args.command == "live-db-files":
        print("\n".join(live_db_files(args.root)))
    elif args.command == "snapshot":
        if args.stage is None:
            print("snapshot needs --stage DIR", file=sys.stderr)
            return 2
        for name in snapshot(args.root, args.stage):
            print(name)
    else:
        members = [line.rstrip("\n") for line in sys.stdin if line.strip()]
        if args.command == "check-members":
            for member in members:
                problem = member_problem(member)
                if problem:
                    print(problem, file=sys.stderr)
                    return 1
            if not members:
                print("the archive is empty", file=sys.stderr)
                return 1
        else:
            for member in members:
                cleaned = member[2:] if member.startswith("./") else member
                if member_problem(member) is None and cleaned.endswith(DB_SUFFIXES):
                    for sidecar in ("-wal", "-shm", "-journal"):
                        (args.root / (cleaned + sidecar)).unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
