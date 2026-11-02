#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - provisioning/install_plan.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The installers of the programs of the CM5 as data: what each `install_*.sh` installs, where, as which user and with which units.

    python provisioning/install_plan.py            write provisioning/install_plan.json
    python provisioning/install_plan.py --check    fail when the file is out of date or an installer disagrees with the registry
    python provisioning/install_plan.py --show twin   print the plan of one installer

The scripts follow one shape (a source folder, a target folder below /opt/hydra-umc, a system user, the unit files that are copied, the files of the project that are installed
beside them), but they were written one by one. This reads that shape out of each script into one table, so that the shared installer that will replace the copies has a plan to
start from and so that a copy that drifts from the others is reported:

* `source`: the repository the script installs (`SOURCE="$ROOT/HYDRA-UMC-..."`), `target`: the folder below /opt/hydra-umc, `user`: the system user it creates,
* `units`: the unit files it copies, `clones`: whether it runs `git clone` (it compiles or fetches on the device),
* `port`, `health_path` and `unit` from `ports.yaml` (generated from the manifests), for the services the registry knows.

`--check` also reports, for every script that installs a service of the registry: a unit that the registry does not list, a target folder whose name is not the unit name without
`hydra-umc-` and `.service`, and a script that does not install the `hydra-umc.project.json` of its project (the status route of the server reports whatever was installed first,
forever, otherwise). Standard library only; reads the scripts and writes nothing but the table.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLAN_FILE = HERE / "install_plan.json"
PORTS_FILE = HERE / "ports.yaml"
SOURCE = re.compile(r'^[A-Z_]*SOURCE="\$ROOT/(HYDRA-UMC-[A-Z0-9-]+)"', re.M)
TARGET = re.compile(r"^TARGET=(/opt/hydra-umc/[a-z0-9-]+)", re.M)
USER = re.compile(r'^[A-Z_]*USER="(hydra-umc-[a-z0-9-]+)"', re.M)
UNITS = re.compile(r"systemd/(hydra-umc-[a-z0-9-]+\.(?:service|timer))")
MANIFEST_INSTALLED = re.compile(r'hydra-umc\.project\.json"\s+"\$TARGET/hydra-umc\.project\.json"')


def registry(ports_file: Path = PORTS_FILE) -> dict[str, dict[str, str]]:
    """name -> {port, health_path, systemd_unit} from the generated ports.yaml."""
    services: dict[str, dict[str, str]] = {}
    current: dict[str, str] | None = None
    for line in ports_file.read_text(encoding="utf-8").splitlines() if ports_file.is_file() else []:
        stripped = line.strip()
        if stripped.startswith("- name:"):
            current = {}
            services[stripped[len("- name:"):].strip()] = current
        elif current is not None and ":" in stripped and not stripped.startswith("#"):
            key, _, value = stripped.partition(":")
            current[key.strip()] = "" if value.strip() == "null" else value.strip()
    return services


def read_script(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8", errors="replace")
    source = SOURCE.search(text)
    target = TARGET.search(text)
    user = USER.search(text)
    return {
        "script": path.name,
        "source": source.group(1) if source else None,
        "target": target.group(1) if target else None,
        "user": user.group(1) if user else None,
        "units": sorted(set(UNITS.findall(text))),
        "clones": "git clone" in text,
        "installs_manifest": bool(MANIFEST_INSTALLED.search(text)),
    }


def build(directory: Path = HERE, ports: dict[str, dict[str, str]] | None = None) -> dict[str, object]:
    ports = registry(directory / "ports.yaml") if ports is None else ports
    rows = []
    for path in sorted(directory.glob("install_*.sh")):
        row = read_script(path)
        known = ports.get(str(row["source"]))
        if known:
            row["port"] = int(known["port"]) if known.get("port", "").isdigit() else None
            row["health_path"] = known.get("health_path") or None
            row["unit"] = known.get("systemd_unit") or None
        rows.append(row)
    return {"format": "hydra-install-plan/1", "installers": rows}


def problems(plan: dict[str, object], ports: dict[str, dict[str, str]]) -> list[str]:
    found: list[str] = []
    for row in plan["installers"]:  # type: ignore[union-attr]
        name = str(row["script"])
        unit = row.get("unit")
        if not unit:
            continue
        if unit not in row["units"]:
            found.append(f"{name}: installs no unit file {unit}, which the registry lists for {row['source']}")
        expected = str(unit).removeprefix("hydra-umc-").removesuffix(".service")
        if row["target"] and not str(row["target"]).endswith("/" + expected):
            found.append(f"{name}: the target {row['target']} is not named after the unit {unit}")
        if not row["installs_manifest"]:
            found.append(f"{name}: does not install hydra-umc.project.json beside the program")
    return found


def render(plan: dict[str, object]) -> str:
    return json.dumps(plan, indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--show", metavar="NAME", help="print the plan of install_<name>.sh")
    args = parser.parse_args(argv)
    ports = registry()
    plan = build(HERE, ports)
    if args.show:
        wanted = f"install_{args.show.replace('-', '_')}.sh"
        rows = [row for row in plan["installers"] if row["script"] == wanted]  # type: ignore[union-attr]
        if not rows:
            print(f"no installer named {wanted}", file=sys.stderr)
            return 2
        print(json.dumps(rows[0], indent=2, sort_keys=True))
        return 0
    if args.check:
        failures = problems(plan, ports)
        if not PLAN_FILE.is_file() or PLAN_FILE.read_text(encoding="utf-8").replace("\r\n", "\n") != render(plan):
            failures.insert(0, "install_plan.json is out of date (run python provisioning/install_plan.py)")
        for failure in failures:
            print(f"INSTALL_PLAN=FAIL {failure}", file=sys.stderr)
        if failures:
            return 1
        print(f"INSTALL_PLAN=PASS {len(plan['installers'])} installers match the table")  # type: ignore[arg-type]
        return 0
    PLAN_FILE.write_text(render(plan), encoding="utf-8", newline="\n")
    print(f"wrote {PLAN_FILE.name} ({len(plan['installers'])} installers)")  # type: ignore[arg-type]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
