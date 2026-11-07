# =============================================================================
# HYDRA-UMC-OS - tools/verify_polkit_rules.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Asks a real polkit what the rules of provisioning/polkit/ grant, with `pkcheck`, as the account they name.

The two rules (reboot/power-off and start/stop/restart of the other hydra-umc units) were only read until now. This tool copies them to
/etc/polkit-1/rules.d of a Linux machine that has polkit and systemd (the manual workflow `Polkit rules (manual)` runs it on a runner), creates the
unprivileged account `hydra-umc-server` if it is missing and, for each case of a fixed table, runs `pkcheck` as root about a process of that account (or of another
one) and compares the answer with what the rule is meant to say: granted, or refused. It prints `POLKIT_RULES=PASS` or `POLKIT_RULES=FAIL`, one line per case.
It must run as root, changes the machine it runs on and is never started by the checks of a push. `--table` prints the cases without running anything.
"""
from __future__ import annotations

import argparse
import os
import pwd
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

RULES_DIR = Path(__file__).resolve().parent.parent / "provisioning" / "polkit"
TARGET_DIR = Path("/etc/polkit-1/rules.d")
ACCOUNT = "hydra-umc-server"
OTHER = "hydra-umc-other"


@dataclass(frozen=True)
class Case:
    name: str
    user: str
    action: str
    details: tuple[tuple[str, str], ...]
    granted: bool


def _manage(unit: str, verb: str, user: str = ACCOUNT) -> Case:
    return Case(f"{user} {verb} {unit}", user, "org.freedesktop.systemd1.manage-units", (("unit", unit), ("verb", verb)), False)


def cases() -> list[Case]:
    """The table: every row says whether the rules must grant the action to that account."""
    table = [
        Case("server account reboots", ACCOUNT, "org.freedesktop.login1.reboot", (), True),
        Case("server account powers off", ACCOUNT, "org.freedesktop.login1.power-off", (), True),
        Case("server account reboots with other sessions open", ACCOUNT, "org.freedesktop.login1.reboot-multiple-sessions", (), True),
        Case("server account suspends", ACCOUNT, "org.freedesktop.login1.suspend", (), False),
        Case("server account hibernates", ACCOUNT, "org.freedesktop.login1.hibernate", (), False),
        Case("other account reboots", OTHER, "org.freedesktop.login1.reboot", (), False),
        Case("other account powers off", OTHER, "org.freedesktop.login1.power-off", (), False),
    ]
    for unit in ("hydra-umc-datalake.service", "hydra-umc-vision-node.service", "hydra-umc-voice-ui.service"):
        for verb in ("start", "stop", "restart"):
            table.append(Case(f"server account {verb} {unit}", ACCOUNT, "org.freedesktop.systemd1.manage-units", (("unit", unit), ("verb", verb)), True))
    for unit, verb in (
        ("hydra-umc-server.service", "restart"),
        ("hydra-umc-wifi-provision.service", "start"),
        ("hydra-umc-agent.service", "stop"),
        ("ssh.service", "restart"),
        ("networking.service", "stop"),
        ("hydra-umc-datalake.service", "reload"),
        ("hydra-umc-datalake.service", "kill"),
        ("hydra-umc-.service", "start"),
        ("hydra-umc-Datalake.service", "start"),
        ("hydra-umc-datalake.service.evil", "start"),
    ):
        table.append(_manage(unit, verb))
    table.append(_manage("hydra-umc-datalake.service", "restart", OTHER))
    table.append(Case("server account manage-units without a unit", ACCOUNT, "org.freedesktop.systemd1.manage-units", (("verb", "start"),), False))
    return table


def _run(argv: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)


def _ensure_account(name: str) -> None:
    try:
        pwd.getpwnam(name)
    except KeyError:
        _run(["useradd", "--system", "--no-create-home", "--shell", "/bin/bash", name])
        pwd.getpwnam(name)


def install_rules() -> list[Path]:
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    written = []
    for source in sorted(RULES_DIR.glob("*.rules")):
        target = TARGET_DIR / source.name
        shutil.copyfile(source, target)
        target.chmod(0o644)
        written.append(target)
    return written


def check(case: Case) -> tuple[bool, str]:
    """Runs pkcheck as root about a process of the account of the case (polkit only takes details from a trusted caller); True when the answer is the expected one."""
    info = pwd.getpwnam(case.user)
    holder = subprocess.Popen(["setpriv", f"--reuid={info.pw_uid}", f"--regid={info.pw_gid}", "--clear-groups", "sleep", "30"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(0.2)
        argv = ["pkcheck", "--action-id", case.action, "--process", str(holder.pid)]
        for key, value in case.details:
            argv += ["--detail", key, value]
        done = _run(argv)
    finally:
        holder.kill()
        holder.wait()
    granted = done.returncode == 0
    note = (done.stdout + done.stderr).strip().replace(chr(10), " ")[:160]
    return granted == case.granted, f"pkcheck exit {done.returncode}{': ' + note if note else ''}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--table", action="store_true", help="print the cases and run nothing")
    args = parser.parse_args()
    if args.table:
        for case in cases():
            print(f"{'GRANT ' if case.granted else 'REFUSE'} {case.name}")
        return 0
    if os.geteuid() != 0 or shutil.which("pkcheck") is None:
        print("POLKIT_RULES=FAIL needs root and polkit (pkcheck) on this machine")
        return 1
    _ensure_account(ACCOUNT)
    _ensure_account(OTHER)
    written = install_rules()
    print(f"installed {len(written)} rule files: {', '.join(p.name for p in written)}")
    time.sleep(3)  # polkitd watches the folder and reloads on its own
    failures = 0
    for case in cases():
        good, note = check(case)
        print(f"{'ok  ' if good else 'FAIL'} {'GRANT ' if case.granted else 'REFUSE'} {case.name} ({note})")
        failures += 0 if good else 1
    print(f"POLKIT_RULES={'PASS' if failures == 0 else 'FAIL'} {len(cases()) - failures}/{len(cases())} cases")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
