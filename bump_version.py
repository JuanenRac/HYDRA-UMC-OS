#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - Decimal build version odometer
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
from __future__ import annotations
import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TARGETS = (ROOT / "agent/pyproject.toml", ROOT / "agent/src/hydra_umc_os/__init__.py")
MANIFEST = ROOT / "hydra-umc.project.json"

def bump(value: str) -> str:
    major, minor, patch = map(int, value.split(".")); patch += 1
    if patch == 10: minor, patch = minor + 1, 0
    if minor == 10: major, minor = major + 1, 0
    return f"{major}.{minor}.{patch}"

def main() -> None:
    pattern = re.compile(r'(?m)(version\s*=\s*"|__version__\s*=\s*")([0-9]+\.[0-9]+\.[0-9]+)(")')
    first = TARGETS[0].read_text(encoding="utf-8"); match = pattern.search(first)
    if not match: raise SystemExit("Version not found")
    old, new = match.group(2), bump(match.group(2))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("name") != "HYDRA-UMC-OS" or manifest.get("version") != old:
        raise SystemExit("Manifest version must match the native version before a build")
    for target in TARGETS:
        text = target.read_text(encoding="utf-8")
        target.write_text(pattern.sub(lambda m: m.group(1) + new + m.group(3), text), encoding="utf-8")
    changelog = ROOT / "CHANGELOG.md"
    text = changelog.read_text(encoding="utf-8")
    entry = f"## [{new}] - {date.today().isoformat()}\n\n### Changed\n\n- Automated build version increment from {old}.\n\n"
    changelog.write_text(text.replace("# Changelog\n\n", "# Changelog\n\n" + entry, 1), encoding="utf-8")
    manifest["version"] = new
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Version bumped: {old} -> {new}")

if __name__ == "__main__": main()
