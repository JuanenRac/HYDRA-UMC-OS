# =============================================================================
# HYDRA-UMC-OS - tools/verify_sudoers_rule.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Runs the sudoers rule of the updater for real: `visudo -cf`, then `sudo -n` as the account, with a stand-in for `hydra-umc-os`.

It needs root and sudo on a Linux machine that can be changed (the manual workflow `Polkit rules (manual)` runs it on a runner): it creates the accounts
`hydra-umc-updater` and `hydra-umc-stranger`, puts the generated rule in /etc/sudoers.d, replaces /usr/local/bin/hydra-umc-os by a program that only prints
the user it runs as and its arguments, and compares what sudo does with a fixed table. Prints `SUDOERS_RULE=PASS` or `SUDOERS_RULE=FAIL`.
"""
from __future__ import annotations

import importlib.util
import json
import os
import pwd
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("make_updater_sudoers", ROOT / "tools" / "make_updater_sudoers.py")
assert spec and spec.loader
maker = importlib.util.module_from_spec(spec)
sys.modules["make_updater_sudoers"] = maker
spec.loader.exec_module(maker)

RULE_FILE = Path("/etc/sudoers.d/90-hydra-umc-updater")
STAND_IN = Path("/usr/local/bin/hydra-umc-os")
STRANGER = "hydra-umc-stranger"


def _run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, capture_output=True, text=True, timeout=30, check=False)


def _account(name: str) -> None:
    try:
        pwd.getpwnam(name)
    except KeyError:
        _run(["useradd", "--system", "--no-create-home", "--shell", "/bin/bash", name])


def table(project: str) -> list[tuple[str, str, list[str], bool]]:
    """(name, account, command after sudo, allowed)"""
    ok = [str(STAND_IN), "deploy", project, "--apply"]
    return [
        ("deploys a listed project", maker.ACCOUNT, ok, True),
        ("deploys without --apply", maker.ACCOUNT, [str(STAND_IN), "deploy", project], False),
        ("rolls back", maker.ACCOUNT, [str(STAND_IN), "rollback", project], False),
        ("adds an argument", maker.ACCOUNT, [*ok, "--extra"], False),
        ("adds a second project", maker.ACCOUNT, [str(STAND_IN), "deploy", project, "HYDRA-UMC-SERVER", "--apply"], False),
        ("names a project the plan does not list", maker.ACCOUNT, [str(STAND_IN), "deploy", "HYDRA-UMC-NOT-A-PROJECT", "--apply"], False),
        ("names the project in lower case", maker.ACCOUNT, [str(STAND_IN), "deploy", project.lower(), "--apply"], False),
        ("runs another program", maker.ACCOUNT, ["/bin/true"], False),
        ("runs a shell", maker.ACCOUNT, ["/bin/sh", "-c", "id"], False),
        ("a stranger deploys a listed project", STRANGER, ok, False),
    ]


def main() -> int:
    if os.geteuid() != 0:
        print("SUDOERS_RULE=FAIL needs root")
        return 1
    plan = json.loads((ROOT / "provisioning" / "install_plan.json").read_text(encoding="utf-8"))
    projects = maker.deployable_projects(plan)
    if not projects:
        print("SUDOERS_RULE=FAIL the plan lists no deployable project")
        return 1
    _account(maker.ACCOUNT)
    _account(STRANGER)
    text = (ROOT / "provisioning" / "sudoers.d" / "hydra-umc-updater").read_bytes().decode("utf-8").replace("\r\n", "\n")
    RULE_FILE.write_bytes(text.encode("utf-8"))
    RULE_FILE.chmod(0o440)
    checked = _run(["visudo", "-cf", str(RULE_FILE)])
    print(f"visudo -cf: exit {checked.returncode} {(checked.stdout + checked.stderr).strip()[:200]}")
    if checked.returncode != 0:
        print("SUDOERS_RULE=FAIL the rule is not valid sudoers")
        return 1
    STAND_IN.write_text('#!/bin/sh\necho "ran as $(id -un): $*"\n', encoding="utf-8")
    STAND_IN.chmod(0o755)
    failures = 0
    cases = 0
    for project in (projects[0], projects[-1]):
        for name, account, command, allowed in table(project):
            cases += 1
            done = _run(["runuser", "-u", account, "--", "sudo", "-n", *command])
            good = (done.returncode == 0) == allowed
            if allowed and good:
                good = done.stdout.startswith("ran as root:")
            failures += 0 if good else 1
            print(f"{'ok  ' if good else 'FAIL'} {'ALLOW ' if allowed else 'REFUSE'} {account} {name} [{project}] (exit {done.returncode}: {(done.stdout + done.stderr).strip()[:100]})")
    print(f"SUDOERS_RULE={'PASS' if failures == 0 else 'FAIL'} {cases - failures}/{cases} cases")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
