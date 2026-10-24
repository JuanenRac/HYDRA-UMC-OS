#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - Create the key file that signs the results of a tool (0600, never in a repository)
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""`make_result_key.py FILE` writes 64 random hexadecimal characters to FILE, readable by its owner only, and does nothing when FILE already holds a usable key.

A signing key is made when the device is installed: it is never shipped in an image or a repository, two devices never share one, and a key that already exists (the operator's own,
or the one a previous run made) is never replaced, because every signature made with it would stop verifying. The file is created without ever being readable by anyone else (mode
0600 from the first byte), the key is never printed, and a file that exists but is too short to be a key is an error (it is not overwritten either). Standard library only.
"""
from __future__ import annotations

import argparse
import os
import secrets
import stat
import sys
from pathlib import Path

MIN_KEY_CHARACTERS = 16  # what the readers of the key require


def existing_key(path: Path) -> str | None:
    """The first line of the file when it is a usable key, else None."""
    try:
        line = path.read_text(encoding="utf-8").splitlines()[0].strip()
    except (OSError, IndexError, UnicodeDecodeError):
        return None
    return line if len(line) >= MIN_KEY_CHARACTERS else None


def make(path: Path) -> str:
    """Creates the key file; returns `created` or `kept`. Raises when the file exists and is not a usable key."""
    if path.exists() or path.is_symlink():
        if path.is_symlink():
            raise SystemExit(f"{path} is a symbolic link: a key file is never followed through one")
        if existing_key(path) is None:
            raise SystemExit(f"{path} exists but holds no usable key (at least {MIN_KEY_CHARACTERS} characters on its first line): not overwritten, fix or remove it by hand")
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode & 0o077:
            os.chmod(path, 0o600)  # a key other users could read is closed to them, whoever made it
        return "kept"
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(secrets.token_hex(32) + "\n")
    except BaseException:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise
    os.chmod(path, 0o600)
    return "created"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file")
    parser.add_argument("--owner", help="USER[:GROUP] to give the file to (the installer runs as root)")
    args = parser.parse_args(argv)
    path = Path(args.file)
    outcome = make(path)
    if args.owner and hasattr(os, "chown"):
        import grp
        import pwd

        user, _, group = args.owner.partition(":")
        os.chown(path, pwd.getpwnam(user).pw_uid, grp.getgrnam(group).gr_gid if group else -1)
    print(f"RESULT_KEY={outcome.upper()} {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
