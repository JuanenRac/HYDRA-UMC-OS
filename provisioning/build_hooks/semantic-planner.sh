#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - build_hooks/semantic-planner.sh
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Checks the source and the interpreter.
# Sourced by provisioning/install_semantic_planner.sh as root, after the service user and $TARGET exist and before the shared copy step;
# never run on its own. Uses $ROOT, $SOURCE, $TARGET, $SVC_USER and $HERE of the installer. Safe to run again.

[[ -d "$SOURCE/src/hydra_umc_semantic_planner" ]] || { echo "HYDRA-UMC-SEMANTIC-PLANNER source is incomplete: $SOURCE" >&2; exit 2; }
command -v python3 >/dev/null || { echo "HYDRA-UMC-SEMANTIC-PLANNER requires python3." >&2; exit 2; }
