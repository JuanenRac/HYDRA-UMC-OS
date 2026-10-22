#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - Version increment
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Increment the version with the one rule of the ecosystem.

The rule (decimal odometer, three components up to 0.7.9 and four from 0.8.0) lives in
bump_manifest_version.py and is shared by every repository; this script no longer has a copy of it.
It runs that utility, which moves the native version (agent/pyproject.toml), the manifest and the
changelog together, and then carries the agent's own ``__version__`` along, because the agent
reports it and a test pins it to the manifest.
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "hydra-umc.project.json"
AGENT_INIT = ROOT / "agent" / "src" / "hydra_umc_os" / "__init__.py"


def load_shared():
    spec = importlib.util.spec_from_file_location("_hydra_shared_bump", ROOT / "bump_manifest_version.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def sync_agent_version(version: str, path: Path = AGENT_INIT) -> bool:
    """Write `version` into the agent's ``__version__`` line; True when the file changed."""
    text = path.read_text(encoding="utf-8")
    line = re.compile(r'(?m)^(__version__\s*=\s*")[^"]*(")')
    if not line.search(text):
        raise SystemExit(f"{path} has no __version__ line")
    new = line.sub(lambda m: m.group(1) + version + m.group(2), text, count=1)
    if new == text:
        return False
    path.write_text(new, encoding="utf-8")
    return True


def main() -> int:
    shared = load_shared()
    code = shared.main()
    if code != 0:
        return code
    version = json.loads(MANIFEST.read_text(encoding="utf-8"))["version"]
    sync_agent_version(version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
