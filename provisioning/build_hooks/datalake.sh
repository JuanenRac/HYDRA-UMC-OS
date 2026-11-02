#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - build_hooks/datalake.sh
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Checks the source and installs the optional downsampling script and its notes.
# Sourced by provisioning/install_datalake.sh as root, after the service user and $TARGET exist and before the shared copy step;
# never run on its own. Uses $ROOT, $SOURCE, $TARGET, $SVC_USER and $HERE of the installer. Safe to run again.

[[ -d "$SOURCE/src/hydra_umc_datalake" ]] || { echo "HYDRA-UMC-DATALAKE source is incomplete: $SOURCE" >&2; exit 2; }
command -v python3 >/dev/null || { echo "HYDRA-UMC-DATALAKE requires python3." >&2; exit 2; }
if [[ -f "$SOURCE/systemd/hydra-umc-datalake-downsample.sh" ]]; then
  install -d -o root -g root -m 0755 "$TARGET/bin"
  install -m 0755 "$SOURCE/systemd/hydra-umc-datalake-downsample.sh" "$TARGET/bin/downsample.sh"
fi

hook_after_install() {
  echo "Then point Server at it: uncomment HYDRA_UMC_DATALAKE_URL in /etc/hydra-umc/server.env and restart hydra-umc-server."
  echo "Optional: if any series has a real retention policy configured, also enable the daily apply timer:"
  echo "  systemctl enable --now hydra-umc-datalake-retention.timer"
  echo "Optional: periodic downsampling (needs the service started with --enable-downsampling; a DRY RUN until"
  echo "  HYDRA_UMC_DATALAKE_DOWNSAMPLE_DRY_RUN=false is set in /etc/hydra-umc/datalake.env):"
  echo "  systemctl enable --now hydra-umc-datalake-downsample.timer"
}
