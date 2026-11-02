#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - build_hooks/vision-node.sh
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Checks the source and lays out the workspace with the manifests of the family members it reports on.
# Sourced by provisioning/install_vision_node.sh as root, after the service user and $TARGET exist and before the shared copy step;
# never run on its own. Uses $ROOT, $SOURCE, $TARGET, $SVC_USER and $HERE of the installer. Safe to run again.

[[ -d "$SOURCE/src/hydra_umc_vision_node" ]] || { echo "HYDRA-UMC-VISION-NODE source is incomplete: $SOURCE" >&2; exit 2; }
command -v python3 >/dev/null || { echo "HYDRA-UMC-VISION-NODE requires python3." >&2; exit 2; }
install -d -o root -g root -m 0755 "$TARGET/workspace"
for child in HYDRA-UMC-VISION-STREAMER HYDRA-UMC-DETECTION-HEF HYDRA-UMC-SAFETY-ZONES HYDRA-UMC-VISUAL-SERVOING-API; do
  if [[ -f "$ROOT/$child/hydra-umc.project.json" ]]; then
    install -d -o root -g root -m 0755 "$TARGET/workspace/$child"
    install -m 0644 "$ROOT/$child/hydra-umc.project.json" "$TARGET/workspace/$child/hydra-umc.project.json"
  fi
done
