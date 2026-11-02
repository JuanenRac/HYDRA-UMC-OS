#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - build_hooks/swarm-sync.sh
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Compiles the Rust program on the device and installs the binary.
# Sourced by provisioning/install_swarm_sync.sh as root, after the service user and $TARGET exist and before the shared copy step;
# never run on its own. Uses $ROOT, $SOURCE, $TARGET, $SVC_USER and $HERE of the installer. Safe to run again.

[[ -f "$SOURCE/Cargo.toml" ]] || { echo "HYDRA-UMC-SWARM-SYNC source is incomplete: $SOURCE" >&2; exit 2; }
if ! command -v cargo >/dev/null; then
  apt-get update
  apt-get install -y cargo
fi
command -v cargo >/dev/null || { echo "cargo installed but still not on PATH." >&2; exit 2; }
( cd "$SOURCE" && cargo build --release )
install -m 0755 -o root -g root "$SOURCE/target/release/hydra-umc-swarm-sync" "$TARGET/hydra-umc-swarm-sync"
