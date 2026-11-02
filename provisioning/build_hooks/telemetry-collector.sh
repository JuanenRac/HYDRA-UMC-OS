#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - build_hooks/telemetry-collector.sh
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Fetches the pinned Go toolchain when it is missing and builds the program.
# Sourced by provisioning/install_telemetry_collector.sh as root, after the service user and $TARGET exist and before the shared copy step;
# never run on its own. Uses $ROOT, $SOURCE, $TARGET, $SVC_USER and $HERE of the installer. Safe to run again.

[[ -f "$SOURCE/src/go.mod" ]] || { echo "HYDRA-UMC-TELEMETRY-COLLECTOR source is incomplete: $SOURCE" >&2; exit 2; }
source "$HERE/go_toolchain.sh"
ensure_go
( cd "$SOURCE/src" && "$GO_BIN" build -o "$TARGET/telemetry-collector" . )
chown root:root "$TARGET/telemetry-collector"
chmod 0755 "$TARGET/telemetry-collector"

hook_after_install() {
  echo "Depends on HYDRA-UMC-DATALAKE already running for -datalake-url to actually deliver samples."
}
