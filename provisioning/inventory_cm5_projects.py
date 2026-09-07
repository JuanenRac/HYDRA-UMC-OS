#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - List locally checked-out projects targeted at CM5 deployment
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
#
# Real bug fixed after a live ecosystem audit: this used to import a static
# `PROJECTS` list from hydra_umc_updater.registry that no longer exists -
# discovery moved to reading each repository's own hydra-umc.project.json
# (see HYDRA-UMC-UPDATER's own detect.py) and the static catalog was
# removed, breaking this script's import outright. Now uses the same
# manifest-based discover_workspace() every other ecosystem tool uses.
# =============================================================================
from __future__ import annotations
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / "HYDRA-UMC-UPDATER" / "src"))
from hydra_umc_updater.detect import discover_workspace  # noqa: E402

discovery = discover_workspace(root)
for error in discovery.errors:
    print(f"warning: {error}", file=sys.stderr)

for status in discovery.projects:
    entry = status.entry
    if entry.deploy == "cm5":
        print(f"{entry.name}\t{entry.role}\t{', '.join(entry.tech)}")
