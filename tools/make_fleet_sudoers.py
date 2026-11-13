#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - tools/make_fleet_sudoers.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Write the rule of sudo that lets the account of the server run exactly the commands of tools/fleet_update.py, and nothing else.

    python tools/make_fleet_sudoers.py --user hydra-umc --install-plan provisioning/install_plan.json > hydra-umc-fleet
    sudo visudo -cf hydra-umc-fleet && sudo install -m 0440 -o root -g root hydra-umc-fleet /etc/sudoers.d/hydra-umc-fleet

One line per command, with the exact words the tool passes and no wildcard: the copy of each program has an exact name (`<name>.bak.tgz`), the installers are the ones of
this repository's `provisioning/`, the unit of each program is named, the journal is read with fixed words. A command the tool does not issue is refused by sudo. The rule is
only as strong as the files it names: the checkout of this repository must belong to root, or to an account that is trusted as much as root, because the installers run as
root. `tools/verify_fleet_update.py` runs the tool on a simulated device and checks that every command it passes to sudo is a line of this output.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("fleet_update_for_sudoers", HERE / "fleet_update.py")
assert _spec and _spec.loader
fu = importlib.util.module_from_spec(_spec)
sys.modules["fleet_update_for_sudoers"] = fu
_spec.loader.exec_module(fu)

BINARIES = {"bash": "/usr/bin/bash", "tar": "/usr/bin/tar", "rm": "/usr/bin/rm", "mkdir": "/usr/bin/mkdir", "systemctl": "/usr/bin/systemctl", "journalctl": "/usr/bin/journalctl"}


def commands(installers: list[dict], workspace: str, root: str, backups: str, unit_dir: str) -> list[list[str]]:
    """Every command (without `sudo -n`) that fleet_update.py passes to sudo, for the programs of the plan of installers."""
    out: list[list[str]] = [["mkdir", "-p", backups], ["systemctl", "daemon-reload"]]
    for svc in fu.build_services(installers):
        name, unit = svc["name"], svc["unit"]
        archive = f"{backups}/{name}.bak.tgz"
        members = [f"{root}/{name}".lstrip("/"), f"{unit_dir}/{unit}".lstrip("/"), f"{unit_dir}/{unit}.d".lstrip("/")]
        out += [
            ["tar", "czf", archive, "--ignore-failed-read", "-C", "/", *members],
            ["tar", "xzf", archive, "-C", "/"],
            ["rm", "-rf", f"{unit_dir}/{unit}.d", f"{root}/{name}.tmp"],
            ["systemctl", "restart", unit],
            ["journalctl", "-u", unit, "-n", "40", "--no-pager", "--since", "-2min"],
            ["bash", f"{workspace}/HYDRA-UMC-OS/provisioning/install_{svc['script']}.sh", "--apply"],
        ]
    seen: set[tuple[str, ...]] = set()
    unique = []
    for command in out:
        if tuple(command) not in seen:
            seen.add(tuple(command))
            unique.append(command)
    return unique


def escape(word: str) -> str:
    """The characters that sudoers reads as syntax are written with a backslash; a word with a wildcard is refused."""
    if any(c in word for c in "*?[]"):
        raise ValueError(f"a wildcard in a command is not allowed: {word}")
    return "".join("\\" + c if c in ",:=\\ " else c for c in word)


def render(user: str, installers: list[dict], workspace: str, root: str, backups: str, unit_dir: str) -> str:
    lines = [f"# Written by tools/make_fleet_sudoers.py: exactly the commands of tools/fleet_update.py for {user}, no wildcard.", "Cmnd_Alias HYDRA_FLEET = \\"]
    commands_ = commands(installers, workspace, root, backups, unit_dir)
    for index, command in enumerate(commands_):
        binary = BINARIES[command[0]]
        text = " ".join([binary, *(escape(w) for w in command[1:])])
        tail = ", \\" if index < len(commands_) - 1 else ""
        lines.append("    " + text + tail)
    lines += ["", f"{user} ALL=(root) NOPASSWD: HYDRA_FLEET", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--user", required=True)
    parser.add_argument("--install-plan", type=Path, required=True)
    parser.add_argument("--workspace", default="/home/hydra-umc/hydra-umc")
    parser.add_argument("--root", default="/opt/hydra-umc")
    parser.add_argument("--backups", default="/opt/hydra-umc-backups")
    parser.add_argument("--unit-dir", default="/etc/systemd/system")
    args = parser.parse_args(argv)
    if not args.user.replace("-", "").replace("_", "").isalnum():
        print("the account name is not valid", file=sys.stderr)
        return 64
    installers = json.loads(args.install_plan.read_text(encoding="utf-8"))["installers"]
    sys.stdout.write(render(args.user, installers, args.workspace, args.root, args.backups, args.unit_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
