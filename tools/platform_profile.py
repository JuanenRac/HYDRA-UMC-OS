#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - tools/platform_profile.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The platform of the device as data: which base image, packages and units a kind of module needs (`cm5`, `jetson`, `rk3588`).

    python tools/platform_profile.py                 list the platforms and say which one this machine would use
    python tools/platform_profile.py --show jetson   print the plan of one platform (--json for a program)
    python tools/platform_profile.py --check         fail when a file of config/platforms is not valid

A platform is a declaration in `config/platforms/<name>.json` (format `hydra-platform/1`): the base image the system is built on, the extra packages and the units to enable, and the
build backends that can build it. The platform `cm5` is what the images of this project are built on today and adds nothing; `jetson` and `rk3588` are prepared in simulation (the
`rk3588` one is generic: no module or carrier board is chosen). Which platform a machine uses: `HYDRA_UMC_PLATFORM`, else the first word of `/etc/hydra-umc/platform`, else `cm5`. A name that
is not a platform is an error, never a quiet fall back to another one. This tool reads and prints; it installs nothing. The image builder (HYDRA-UMC-OS-REBUILDER) reads the same
declarations through its `platform` option. Evidence: simulator. Standard library only."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
PLATFORMS_DIR = ROOT / "config" / "platforms"
FORMAT = "hydra-platform/1"
DEFAULT_PLATFORM = "cm5"
ENV_NAME = "HYDRA_UMC_PLATFORM"
MACHINE_FILE = Path("/etc/hydra-umc/platform")
BACKENDS = ("chroot", "nspawn", "pigen")
ARCHES = ("arm64",)
_NAME = re.compile(r"[a-z][a-z0-9_]{1,31}")
_PACKAGE = re.compile(r"[a-z0-9][a-z0-9+.\-]{1,63}")
_UNIT = re.compile(r"[A-Za-z0-9:_.\\@-]{1,100}\.(service|timer|socket|path)")
_KEYS = {"format", "platform", "label", "arch", "generic", "base_image", "packages", "remove_packages", "units", "build_backends", "status", "evidence"}
_BASE_KEYS = {"kind", "variant", "release", "source", "note"}


class PlatformError(ValueError):
    """A platform that does not exist or whose file cannot be used."""


def check_profile(data: object, stem: str | None = None) -> list[str]:
    """What is wrong in one declaration, in words; empty when it can be used."""
    if not isinstance(data, dict):
        return ["the file is not a JSON object"]
    found: list[str] = []
    unknown = sorted(set(data) - _KEYS)
    missing = sorted(_KEYS - set(data))
    if unknown:
        found.append(f"unknown key(s): {unknown}")
    if missing:
        found.append(f"missing key(s): {missing}")
        return found
    if data["format"] != FORMAT:
        found.append(f"format must be {FORMAT}")
    name = data["platform"]
    if not isinstance(name, str) or not _NAME.fullmatch(name):
        found.append("platform must be a lower-case name")
    elif stem is not None and name != stem:
        found.append(f"the file is {stem}.json but names the platform {name!r}")
    if data["arch"] not in ARCHES:
        found.append(f"arch must be one of {ARCHES}")
    for key in ("label", "status"):
        if not isinstance(data[key], str) or not data[key].strip():
            found.append(f"{key} must be a text")
    if data["evidence"] not in ("bench", "simulator"):
        found.append("evidence must be bench or simulator")
    if not isinstance(data["generic"], bool):
        found.append("generic must be true or false")
    base = data["base_image"]
    if not isinstance(base, dict) or set(base) != _BASE_KEYS or not all(isinstance(v, str) and v.strip() for v in base.values()):
        found.append(f"base_image must hold exactly {sorted(_BASE_KEYS)} as texts")
    for key in ("packages", "remove_packages"):
        value = data[key]
        if not isinstance(value, list) or not all(isinstance(p, str) and _PACKAGE.fullmatch(p) for p in value) or len(set(value)) != len(value):
            found.append(f"{key} must be a list of distinct package names")
    if isinstance(data["packages"], list) and isinstance(data["remove_packages"], list) and set(data["packages"]) & set(data["remove_packages"]):
        found.append("a package is both installed and removed")
    units = data["units"]
    if not isinstance(units, list) or not all(isinstance(u, dict) and set(u) == {"name", "enable"} and isinstance(u["name"], str) and _UNIT.fullmatch(u["name"]) and isinstance(u["enable"], bool) for u in units):
        found.append("units must be a list of {name, enable} with a unit name")
    elif len({u["name"] for u in units}) != len(units):
        found.append("a unit is listed twice")
    backends = data["build_backends"]
    if not isinstance(backends, list) or not backends or not all(b in BACKENDS for b in backends) or len(set(backends)) != len(backends):
        found.append(f"build_backends must be a non-empty list of distinct names from {BACKENDS}")
    elif "pigen" in backends and name != "cm5":
        found.append("pi-gen builds Raspberry Pi images only: pigen is allowed for cm5 alone")
    return found


def load_all(directory: Path = PLATFORMS_DIR) -> dict[str, dict[str, Any]]:
    """Every declaration of the folder by name. A file that cannot be used is an error naming it."""
    profiles: dict[str, dict[str, Any]] = {}
    for path in sorted(directory.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise PlatformError(f"{path.name}: cannot be read: {error}") from error
        problems = check_profile(data, path.stem)
        if problems:
            raise PlatformError(f"{path.name}: " + "; ".join(problems))
        profiles[path.stem] = data
    if DEFAULT_PLATFORM not in profiles:
        raise PlatformError(f"the platform {DEFAULT_PLATFORM} is missing from {directory}")
    return profiles


def configured_name(environment: dict[str, str] | None = None, machine_file: Path = MACHINE_FILE) -> str:
    """The platform this machine uses: the variable, else the first word of the machine file, else cm5."""
    env = os.environ if environment is None else environment
    value = env.get(ENV_NAME, "").strip()
    if value:
        return value
    try:
        words = machine_file.read_text(encoding="utf-8").split()
    except OSError:
        return DEFAULT_PLATFORM
    return words[0] if words else DEFAULT_PLATFORM


def select(name: str | None = None, directory: Path = PLATFORMS_DIR, **kwargs: Any) -> dict[str, Any]:
    """The declaration of a platform (the one this machine uses when no name is given); an unknown name is an error."""
    profiles = load_all(directory)
    chosen = name if name else configured_name(**kwargs)
    if chosen not in profiles:
        raise PlatformError(f"{chosen!r} is not a platform; the platforms are {', '.join(sorted(profiles))}")
    return profiles[chosen]


def plan(profile: dict[str, Any]) -> dict[str, Any]:
    """What the platform asks of the build, with the commands written out (nothing is run)."""
    commands: list[list[str]] = []
    if profile["packages"]:
        commands.append(["apt-get", "install", "-y", "--no-install-recommends", *profile["packages"]])
    if profile["remove_packages"]:
        commands.append(["apt-get", "remove", "-y", *profile["remove_packages"]])
    for unit in profile["units"]:
        commands.append(["systemctl", "enable" if unit["enable"] else "disable", unit["name"]])
    return {
        "platform": profile["platform"], "label": profile["label"], "arch": profile["arch"], "generic": profile["generic"], "base_image": dict(profile["base_image"]),
        "packages": list(profile["packages"]), "remove_packages": list(profile["remove_packages"]), "units": [dict(u) for u in profile["units"]],
        "build_backends": list(profile["build_backends"]), "commands": commands, "evidence": profile["evidence"], "status": profile["status"], "runs_anything": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--show", metavar="NAME", help="print the plan of this platform ('this' for the one the machine uses)")
    parser.add_argument("--check", action="store_true", help="exit 1 when a file of config/platforms is not valid")
    parser.add_argument("--json", action="store_true", help="print JSON")
    args = parser.parse_args(argv)
    try:
        profiles = load_all()
    except PlatformError as error:
        print(f"PLATFORM_PROFILES=FAIL {error}", file=sys.stderr)
        return 1
    if args.check:
        print(f"PLATFORM_PROFILES=PASS platforms={len(profiles)}")
        return 0
    try:
        if args.show:
            chosen = plan(select(None if args.show == "this" else args.show))
            print(json.dumps(chosen, indent=2, sort_keys=True) if args.json else f"{chosen['platform']}: {chosen['label']} ({chosen['arch']}); base {chosen['base_image']['kind']} {chosen['base_image']['release']}; packages {', '.join(chosen['packages']) or '-'}; units {', '.join(u['name'] for u in chosen['units']) or '-'}")
            return 0
        current = select()["platform"]
    except PlatformError as error:
        print(f"PLATFORM_FAILED {error}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({"platforms": sorted(profiles), "current": current}))
    else:
        for name, data in profiles.items():
            print(f"{name}{' (this machine)' if name == current else ''}: {data['label']} [{data['evidence']}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
