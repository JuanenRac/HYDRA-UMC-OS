#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - npm in the installers verification
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The installers install npm dependencies without running their install scripts unless the owner allows it (npm_scripts = on in
/etc/hydra-umc/provisioning.conf or HYDRA_UMC_NPM_SCRIPTS=on), and run the build of a checkout as the user who owns it. Static checks of the
hooks plus a run of the helper functions of provisioning/deploy_lib.sh with a stand-in `npm` that records its arguments."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "provisioning" / "deploy_lib.sh"
failures: list[str] = []


def expect(condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def check_hooks() -> None:
    dashboard = (ROOT / "provisioning" / "build_hooks" / "dashboard-ai.sh").read_text(encoding="utf-8")
    server = (ROOT / "provisioning" / "build_hooks" / "server.sh").read_text(encoding="utf-8")
    expect("hydra_npm_in" in dashboard and "hydra_npm_install_flags" in dashboard, "the dashboard hook must install through the helpers")
    expect("npm ci" in server and "hydra_npm_install_flags" in server, "the server hook must install without the install scripts of the dependencies")
    for name, text in (("dashboard-ai", dashboard), ("server", server)):
        expect("npm install" not in text, f"{name}: npm install would ignore the lock file")
    library = LIB.read_text(encoding="utf-8")
    expect("runuser" in library and "stat -c %U" in library, "the helper must run npm as the owner of the checkout")


def check_functions() -> None:
    bash = shutil.which("bash")
    if bash is None:
        print("NPM_INSTALLER=SKIPPED bash is not available")
        return
    with tempfile.TemporaryDirectory() as folder:
        base = Path(folder)
        log = base / "npm.log"
        bin_dir = base / "bin"
        bin_dir.mkdir()
        stand_in = "\n".join(["#!/usr/bin/env bash", 'echo "$@" >>"$NPM_LOG"', ""])
        (bin_dir / "npm").write_bytes(stand_in.encode("utf-8"))
        (bin_dir / "npm").chmod(0o755)  # without the executable bit the real npm of the machine would run instead of the stand-in
        project = base / "project"
        project.mkdir()
        conf = base / "provisioning.conf"

        def run(script: str, extra: dict[str, str] | None = None) -> str:
            environment = {**os.environ, "PATH": bin_dir.as_posix() + os.pathsep + os.environ["PATH"], "NPM_LOG": log.as_posix(),
                           "HYDRA_UMC_PROVISIONING_CONF": conf.as_posix(), **(extra or {})}
            environment.pop("HYDRA_UMC_NPM_SCRIPTS", None) if not extra or "HYDRA_UMC_NPM_SCRIPTS" not in extra else None
            result = subprocess.run([bash, "-c", f'source "{LIB.as_posix()}"; {script}'], capture_output=True, text=True, env=environment, check=False)
            expect(result.returncode == 0, f"{script!r} failed: {result.stderr.strip()[:200]}")
            return result.stdout

        expect(run("hydra_npm_install_flags") == "--ignore-scripts", "by default the install scripts of the dependencies must not run")
        conf.write_text("npm_scripts = on\n", encoding="utf-8")
        expect(run("hydra_npm_install_flags") == "", "npm_scripts = on in the settings file allows them")
        conf.write_text("npm_scripts = off\n", encoding="utf-8")
        expect(run("hydra_npm_install_flags") == "--ignore-scripts", "npm_scripts = off keeps them blocked")
        conf.write_text("# npm_scripts = on\nprint_once = true\n", encoding="utf-8")
        expect(run("hydra_npm_install_flags") == "--ignore-scripts", "a commented setting does not count")
        expect(run("hydra_npm_install_flags", {"HYDRA_UMC_NPM_SCRIPTS": "on"}) == "", "the environment can allow them too")
        expect(run("hydra_npm_install_flags", {"HYDRA_UMC_NPM_SCRIPTS": "banana"}) == "--ignore-scripts", "an unknown value keeps them blocked")
        conf.unlink()
        run('hydra_npm_in "' + project.as_posix() + '" ci $(hydra_npm_install_flags)')
        recorded = log.read_text(encoding="utf-8").split() if log.exists() else []
        expect(recorded == ["ci", "--ignore-scripts"], f"npm ci must receive the flag, got {recorded}")


def main() -> int:
    check_hooks()
    check_functions()
    if failures:
        for message in failures:
            print(f"NPM_INSTALLER=FAIL {message}", file=sys.stderr)
        return 1
    print("NPM_INSTALLER=PASS dependencies installed without install scripts unless allowed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
