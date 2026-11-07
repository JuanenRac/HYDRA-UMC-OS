#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - tools/apt_packages_check.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The Debian packages the installers ask for, and whether the release of the image has them.

    python3 tools/apt_packages_check.py --list        # the packages of every installer, as JSON (needs nothing)
    python3 tools/apt_packages_check.py --simulate    # `apt-get install --simulate` of each installer's packages (needs apt, run in a Debian trixie container)

The installers install their packages with `apt-get install`; whether every name exists in the release of the image (trixie) and can be installed together
could only be seen on an image. `--simulate` asks apt to plan the installation of each installer's packages, one installer at a time, without installing
anything: a name that does not exist, or a conflict, is reported with the installer that asked for it. A name written with a shell variable is not a package
name and is left out of the list (and is reported by `--list`).
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROVISIONING = ROOT / "provisioning"
PACKAGE = re.compile(r"^[a-z0-9][a-z0-9+.\-]*$")
STOP = {"&&", "||", ";", "|", ">", ">>", "2>", "&>", "<"}


def join_continuations(text: str) -> list[str]:
    lines: list[str] = []
    buffer = ""
    for raw in text.splitlines():
        stripped = raw.rstrip()
        if stripped.endswith("\\"):
            buffer += stripped[:-1] + " "
            continue
        lines.append(buffer + stripped)
        buffer = ""
    if buffer:
        lines.append(buffer)
    return lines


def packages_in(text: str) -> tuple[list[str], list[str]]:
    """(package names, tokens that are not plain package names) asked for by the `apt-get install` commands of a script, in order, without repeats."""
    names: list[str] = []
    odd: list[str] = []
    for line in join_continuations(text):
        code = line.split(" #", 1)[0] if " #" in line else line
        if code.lstrip().startswith("#"):
            continue
        found = re.search(r"\bapt(?:-get)?\s+install\b(.*)$", code)
        if not found:
            continue
        for token in found.group(1).split():
            if token in STOP or token.startswith(("|", ";", "&", ">", "<", "2>")):
                break
            if token.startswith("-"):
                continue
            token = token.strip("'\"")
            if PACKAGE.match(token):
                if token not in names:
                    names.append(token)
            elif token not in odd:
                odd.append(token)
    return names, odd


def packages_by_script(directory: Path = PROVISIONING) -> dict[str, dict[str, list[str]]]:
    result: dict[str, dict[str, list[str]]] = {}
    for script in sorted(directory.glob("*.sh")):
        names, odd = packages_in(script.read_text(encoding="utf-8", errors="replace"))
        if names or odd:
            result[script.name] = {"packages": names, "not_plain": odd}
    return result


def simulate(by_script: dict[str, dict[str, list[str]]]) -> int:
    if not shutil.which("apt-get"):
        print("FAIL  apt-get is not installed here (run this in a Debian container)")
        return 1
    failed = 0
    for script, entry in by_script.items():
        names = entry["packages"]
        if not names:
            continue
        done = subprocess.run(["apt-get", "install", "--simulate", "--no-install-recommends", "-y", *names], capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL)
        if done.returncode == 0:
            print(f"PASS  {script}: {len(names)} packages can be installed")
        else:
            failed = 1
            lines = [line for line in (done.stdout + done.stderr).splitlines() if line.startswith(("E:", "The following packages have unmet", "  "))]
            print(f"FAIL  {script}: apt cannot plan {' '.join(names)}")
            for line in lines[:8]:
                print(f"      {line.strip()}")
    return failed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--simulate", action="store_true")
    args = parser.parse_args(argv)
    by_script = packages_by_script()
    if args.simulate:
        return simulate(by_script)
    print(json.dumps(by_script, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
