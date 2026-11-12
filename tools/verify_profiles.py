#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - tools/verify_profiles.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Check the profile declarations and the module matrix that docs/CM5_MODULE_MATRIX.md prints from them.

A profile is a declaration, never a switch: it names the services of a kind of node and the capabilities that need
hardware. This check proves, without a Compute Module:

* every profile loads through the agent's own validator;
* every service a profile names is the agent, the Server or a unit that provisioning/install_plan.json installs;
* every profile starts the agent, and a profile never names the same installer twice;
* the profile name is the file name;
* the committed matrix (`docs/CM5_MODULE_MATRIX.md`) is the one this script prints (`--write` rewrites it).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent" / "src"))

from hydra_umc_os.agent import load_profile  # noqa: E402

PROFILES = ROOT / "config" / "profiles"
PLAN = ROOT / "provisioning" / "install_plan.json"
MATRIX = ROOT / "docs" / "CM5_MODULE_MATRIX.md"
ALWAYS = ("hydra-umc-agent", "hydra-umc-server")


def installed_units(plan_file: Path = PLAN) -> dict[str, str]:
    """Map each service name of the install plan to the script that installs it."""
    plan = json.loads(plan_file.read_text(encoding="utf-8"))
    units: dict[str, str] = {}
    for installer in plan["installers"]:
        for unit in installer["units"]:
            if unit.endswith(".service"):
                units[unit[: -len(".service")]] = installer["script"]
    return units


def load_all(directory: Path = PROFILES) -> dict[str, dict[str, object]]:
    return {path.stem: load_profile(path) for path in sorted(directory.glob("*.json"))}


def problems(profiles: dict[str, dict[str, object]], units: dict[str, str]) -> list[str]:
    found: list[str] = []
    for stem, profile in profiles.items():
        if profile["profile"] != stem:
            found.append(f"{stem}.json names the profile {profile['profile']!r}")
        services = profile["enabled_services"]
        assert isinstance(services, list)
        if "hydra-umc-agent" not in services:
            found.append(f"profile {stem} does not start the agent")
        for service in services:
            if service not in ALWAYS and service not in units:
                found.append(f"profile {stem} names {service}, which no installer of the plan installs")
        scripts = [units.get(service, service) for service in services]
        if len(scripts) != len(set(scripts)) and any(scripts.count(s) > 1 and s.endswith(".sh") for s in scripts):
            found.append(f"profile {stem} names two units of the same installer")
    return found


def render(profiles: dict[str, dict[str, object]], units: dict[str, str]) -> str:
    names = list(profiles)
    modules = sorted({service for profile in profiles.values() for service in profile["enabled_services"]})  # type: ignore[union-attr]
    lines = [
        "<!-- Printed by tools/verify_profiles.py --write from config/profiles and provisioning/install_plan.json; do not edit by hand. -->",
        "",
        "# CM5 module matrix",
        "",
        "Which service each profile declares. A profile is a declaration the preflight reads, never a switch: nothing here",
        "installs or starts a service, and a capability under \"Needs\" is checked on the node before the profile is used.",
        "",
        "| Service | Installer | " + " | ".join(names) + " |",
        "|---|---|" + "|".join("---" for _ in names) + "|",
    ]
    for module in modules:
        installer = units.get(module, "install_local_agent.sh" if module == "hydra-umc-agent" else "install_server.sh")
        marks = ["yes" if module in profiles[name]["enabled_services"] else "" for name in names]  # type: ignore[operator]
        lines.append(f"| `{module}` | `{installer}` | " + " | ".join(marks) + " |")
    needs = ["<br>".join(f"`{item}`" for item in profiles[name]["requires"]) or "-" for name in names]  # type: ignore[union-attr]
    lines.append("| **Needs** | | " + " | ".join(needs) + " |")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    profiles = load_all()
    units = installed_units()
    found = problems(profiles, units)
    text = render(profiles, units)
    if "--write" in argv:
        MATRIX.write_text(text, encoding="utf-8", newline="\n")
    elif not MATRIX.is_file() or MATRIX.read_text(encoding="utf-8") != text:
        found.append("docs/CM5_MODULE_MATRIX.md is not the matrix of the profiles (run tools/verify_profiles.py --write)")
    if found:
        for line in found:
            print(f"PROFILES=FAIL {line}", file=sys.stderr)
        return 1
    print(f"PROFILES=PASS {len(profiles)} profiles, {len(units)} services in the plan")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
