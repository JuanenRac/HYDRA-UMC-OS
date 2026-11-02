#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - build_hooks/vla-engine.sh
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Checks the source and copies the model files of the cognitive node into the workspace.
# Sourced by provisioning/install_vla_engine.sh as root, after the service user and $TARGET exist and before the shared copy step;
# never run on its own. Uses $ROOT, $SOURCE, $TARGET, $SVC_USER and $HERE of the installer. Safe to run again.

[[ -d "$SOURCE/src/hydra_umc_vla_engine" ]] || { echo "HYDRA-UMC-VLA-ENGINE source is incomplete: $SOURCE" >&2; exit 2; }
command -v python3 >/dev/null || { echo "HYDRA-UMC-VLA-ENGINE requires python3." >&2; exit 2; }
install -d -o root -g root -m 0755 "$TARGET/workspace/HYDRA-UMC-COGNITIVE-NODE/models"
if [[ -d "$ROOT/HYDRA-UMC-COGNITIVE-NODE/models" ]]; then
  find "$ROOT/HYDRA-UMC-COGNITIVE-NODE/models" -maxdepth 1 -type f -exec cp -a {} "$TARGET/workspace/HYDRA-UMC-COGNITIVE-NODE/models/" \;
  chown -R root:root "$TARGET/workspace"
fi
