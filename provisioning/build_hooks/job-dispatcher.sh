#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - build_hooks/job-dispatcher.sh
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Fetches the pinned Go toolchain when it is missing and builds the program.
# Sourced by provisioning/install_job_dispatcher.sh as root, after the service user and $TARGET exist and before the shared copy step;
# never run on its own. Uses $ROOT, $SOURCE, $TARGET, $SVC_USER and $HERE of the installer. Safe to run again.

[[ -f "$SOURCE/go.mod" ]] || { echo "HYDRA-UMC-JOB-DISPATCHER source is incomplete: $SOURCE" >&2; exit 2; }
source "$HERE/go_toolchain.sh"
ensure_go
( cd "$SOURCE" && "$GO_BIN" build -o "$TARGET/hydra-umc-job-dispatcher" . )
chown root:root "$TARGET/hydra-umc-job-dispatcher"
chmod 0755 "$TARGET/hydra-umc-job-dispatcher"
