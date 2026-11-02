#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - build_hooks/detection-hef.sh
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Checks the source and lays out the models folder and the registry of compiled models (empty at first).
# Sourced by provisioning/install_detection_hef.sh as root, after the service user and $TARGET exist and before the shared copy step;
# never run on its own. Uses $ROOT, $SOURCE, $TARGET, $SVC_USER and $HERE of the installer. Safe to run again.

[[ -d "$SOURCE/src/hydra_umc_detection_hef" ]] || { echo "HYDRA-UMC-DETECTION-HEF source is incomplete: $SOURCE" >&2; exit 2; }
command -v python3 >/dev/null || { echo "HYDRA-UMC-DETECTION-HEF requires python3." >&2; exit 2; }
install -d -o root -g root -m 0755 "$TARGET/models"
install -d -o root -g root -m 0755 /etc/hydra-umc-detection-hef
[[ -f /etc/hydra-umc-detection-hef/registry.json ]] || echo "[]" > /etc/hydra-umc-detection-hef/registry.json
chmod 0644 /etc/hydra-umc-detection-hef/registry.json

hook_after_install() {
  echo "Serving an empty registry. Add real entries to /etc/hydra-umc-detection-hef/registry.json and .hef files to $TARGET/models as they exist."
}
