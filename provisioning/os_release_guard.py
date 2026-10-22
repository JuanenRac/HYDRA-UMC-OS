#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - provisioning/os_release_guard.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Say whether this machine runs the Debian release the installers are written for.

The installers assume Debian trixie (the base image the Rebuilder downloads).
Running them on another release can fail halfway through an apt step, so this
check looks at /etc/os-release before anything is changed.

The mode is chosen by the operator, never by the script:

* ``warn`` (default): print a clear notice and carry on, as before.
* ``enforce``: refuse to continue on an unsupported release (exit code 3).
* ``off``: say nothing.

Choose it with ``--mode`` or ``HYDRA_UMC_OS_GUARD``; the supported releases are
``--supported`` / ``HYDRA_UMC_SUPPORTED_DEBIAN`` (comma separated codenames,
default ``trixie``).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

DEFAULT_SUPPORTED = ("trixie",)
MODES = ("warn", "enforce", "off")


def parse_os_release(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def check(text: str, supported: tuple[str, ...] = DEFAULT_SUPPORTED) -> tuple[bool, str]:
    """(supported, message) for the content of an os-release file."""
    values = parse_os_release(text)
    codename = values.get("VERSION_CODENAME", "").lower()
    ident = values.get("ID", "").lower()
    shown = f"{ident or 'unknown'} {codename or 'unknown'}"
    if ident not in ("debian", "raspbian") or codename not in supported:
        return False, f"this system is {shown}; the installers are written for Debian {'/'.join(supported)}"
    return True, f"this system is {shown}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--os-release", type=Path, default=Path("/etc/os-release"))
    parser.add_argument("--mode", choices=MODES, default=os.environ.get("HYDRA_UMC_OS_GUARD", "warn"))
    parser.add_argument("--supported", default=os.environ.get("HYDRA_UMC_SUPPORTED_DEBIAN", ",".join(DEFAULT_SUPPORTED)))
    args = parser.parse_args(argv)
    if args.mode not in MODES:
        print(f"OS_RELEASE_GUARD=FAIL unknown mode {args.mode!r}", file=sys.stderr)
        return 2
    if args.mode == "off":
        return 0
    supported = tuple(item.strip().lower() for item in args.supported.split(",") if item.strip()) or DEFAULT_SUPPORTED
    try:
        text = args.os_release.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        text = ""
        print(f"OS_RELEASE_GUARD=WARN cannot read {args.os_release}: {exc}", file=sys.stderr)
    ok, message = check(text, supported)
    if ok:
        print(f"OS_RELEASE_GUARD=PASS {message}")
        return 0
    if args.mode == "enforce":
        print(f"OS_RELEASE_GUARD=FAIL {message}", file=sys.stderr)
        return 3
    print(f"OS_RELEASE_GUARD=WARN {message}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
