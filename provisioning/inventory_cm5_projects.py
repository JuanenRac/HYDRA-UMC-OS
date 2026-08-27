#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - List registry projects targeted at CM5 deployment
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
from __future__ import annotations
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / "HYDRA-UMC-UPDATER" / "src"))
from hydra_umc_updater.registry import PROJECTS  # noqa: E402

for project in PROJECTS:
    if project.deploy == "cm5":
        print(f"{project.name}\t{project.role}\t{', '.join(project.tech)}")
