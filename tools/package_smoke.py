#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - tools/package_smoke.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Show that a built package can run on a machine that builds and downloads nothing.

    python3 tools/package_smoke.py dist-packages/hydra-datalake-0.2.7.tgz [--run]

The package is extracted into a temporary folder. Always: it carries `hydra-install.json`, every unit it names is there, and every file of the program that a unit starts
(`/opt/hydra-umc/<component>/...`) is in the package. With `--run` (on the arm64 runner that built it): the libraries of a Python program are enough to import it with
no site packages, the libraries of the server resolve, and a built program is an arm64 file whose libraries are all found. Nothing of the program is started.
Standard library only.
"""
from __future__ import annotations

import argparse
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("hydra_package_component_smoke", HERE / "package_component.py")
assert _spec and _spec.loader
pc = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("hydra_package_component_smoke", pc)
_spec.loader.exec_module(pc)

# the module a program is started with, when it is not `<package>.main`
ENTRY = {"local-technician": "hydra_umc_local_technician.cli", "os-agent": "hydra_umc_os.agent"}
BINARY = {"twin", "orchestrator", "hil-bridge", "swarm-sync", "job-dispatcher", "node-healing", "telemetry-collector"}
NODE = {"server", "studio", "dashboard-ai"}


def entry_module(component: str) -> str:
    return ENTRY.get(component, "hydra_umc_" + component.replace("-", "_") + ".main")


def static_problems(root: Path, component: str, version: str) -> list[str]:
    """What is wrong with an extracted package, without running anything."""
    problems: list[str] = []
    spec_file = root / pc.SPEC_NAME
    if not spec_file.is_file():
        return [f"{pc.SPEC_NAME} is missing"]
    spec = json.loads(spec_file.read_text(encoding="utf-8"))
    if (spec.get("format"), spec.get("component"), spec.get("version")) != (pc.SPEC_FORMAT, component, version):
        problems.append(f"{pc.SPEC_NAME} describes {spec.get('component')} {spec.get('version')}, not {component} {version}")
    prefix = f"/opt/hydra-umc/{component}/"
    for unit in spec.get("units", []):
        path = root / "systemd" / unit
        if not path.is_file():
            problems.append(f"the unit {unit} is missing")
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.startswith(("ExecStart=", "ExecStartPre=")):
                continue
            for word in re.findall(re.escape(prefix) + r"[A-Za-z0-9._/-]+", line):
                inside = word[len(prefix):]
                # a folder the program writes into is made on the device, not carried
                if inside.split("/")[0] not in spec.get("stateDirs", []) and not (root / inside).exists():
                    problems.append(f"{unit} starts {inside}, which the package does not carry")
    return problems


def run_checks(root: Path, component: str) -> list[list[str]]:
    """The commands that prove the program loads from what the package carries (each must end with status 0)."""
    if component in BINARY:
        program = root / ("telemetry-collector" if component == "telemetry-collector" else f"hydra-umc-{component}")
        # an arm64 ELF (machine 0xB7) whose shared libraries are all on the system
        return [[sys.executable, "-c", "import sys; h=open(sys.argv[1],'rb').read(20); sys.exit(0 if h[:4]==b'\\x7fELF' and h[18]==0xB7 else 1)", str(program)],
                ["sh", "-c", "! ldd \"$1\" 2>&1 | grep -q 'not found'", "sh", str(program)]]
    if component == "server":
        script = "const p=require('./package.json');for(const d of Object.keys(p.dependencies||{})){try{require.resolve(d)}catch(e){require.resolve(d+'/package.json')}}"
        return [["node", "-e", script], ["node", "--check", "dist/server.cjs"]]
    if component == "studio":
        return []
    if component == "dashboard-ai":
        return [[sys.executable, "-S", "-B", "-c", "import ast,sys; ast.parse(open('serve_static.py',encoding='utf-8').read())"]]
    path = [str(root)] if component == "os-agent" else [str(root / "src"), str(root / "pydeps")]
    code = "import importlib,sys; sys.path[:0]=sys.argv[2:]; importlib.import_module(sys.argv[1])"
    # -S: no site packages, so nothing of the machine that built it can stand in for a library the package should carry
    return [[sys.executable, "-S", "-B", "-c", code, entry_module(component), *path]]


def smoke(package: Path, run: bool) -> list[str]:
    match = pc.NAME_PATTERN.match(package.name)
    if not match or match.group(1) not in pc.LAYOUT:
        return [f"{package.name} is not a package of a program"]
    component, version = match.groups()
    data = package.read_bytes()
    try:
        pc.check_members(package, component, data)
    except pc.PackageRefused as error:
        return [str(error)]
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            if hasattr(tarfile, "data_filter"):
                tar.extractall(root, filter="data")
            else:  # pragma: no cover - Python older than 3.12
                tar.extractall(root)
        problems = static_problems(root, component, version)
        if run and not problems:
            for command in run_checks(root, component):
                done = subprocess.run(command, cwd=root, capture_output=True, text=True, check=False, timeout=120, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
                if done.returncode != 0:
                    problems.append(f"{command[0]} said {(done.stderr or done.stdout).strip()[-400:]}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("package", type=Path)
    parser.add_argument("--run", action="store_true", help="also load the program from what the package carries (on the architecture of the device)")
    arguments = parser.parse_args(argv)
    problems = smoke(arguments.package.resolve(), arguments.run)
    for problem in problems:
        print(f"SMOKE=FAIL {problem}", file=sys.stderr)
    if problems:
        return 1
    print(f"SMOKE=PASS {arguments.package.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
