#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - Install HYDRA-UMC-HIL-BRIDGE as a local CM5 API
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Real gap found auditing the ecosystem against actual CM5 hardware:
# HYDRA-UMC-HIL-BRIDGE's real route/mirror bridging logic (bridge.rs,
# interlock.rs) was only ever reachable as a one-shot CLI - server.rs
# (new, that repo) now exposes the same functions as a real HTTP API.
# No real gRPC/WebSocket transport exists yet (see that repo's own
# Cargo.toml) - this closes the CLI-only gap, not that still-deferred
# question. Compiled release binary, same pattern as install_twin.sh.
set -euo pipefail
[[ "${1:-}" == "--apply" ]] || { echo "Dry-run policy: rerun with --apply after review."; exit 0; }
[[ $EUID -eq 0 ]] || { echo "Run as root with sudo." >&2; exit 2; }

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SOURCE="$ROOT/HYDRA-UMC-HIL-BRIDGE"
TARGET=/opt/hydra-umc/hil-bridge
BRIDGE_USER="hydra-umc-hil-bridge"

echo " ==============================================================="
echo "  HYDRA-UMC-OS - install_hil_bridge.sh"
echo "  Installs the real route/mirror-bridging API (Rust, builds"
echo "  on-device)."
echo "  Copyright (C) 2026 JuanenRac (Electro Hobby 3D)"
echo "  <electrohobby3d@gmail.com> | GPL-3.0-or-later - see LICENSE"
echo " ==============================================================="

[[ -f "$SOURCE/Cargo.toml" && -f "$SOURCE/systemd/hydra-umc-hil-bridge.service" ]] || {
  echo "HYDRA-UMC-HIL-BRIDGE source or systemd unit is incomplete: $SOURCE" >&2; exit 2;
}
if ! command -v cargo >/dev/null; then
  apt-get update
  apt-get install -y cargo
fi
command -v cargo >/dev/null || { echo "cargo installed but still not on PATH." >&2; exit 2; }

if ! id -u "$BRIDGE_USER" >/dev/null 2>&1; then
  useradd --system --home "$TARGET" --no-create-home --shell /usr/sbin/nologin "$BRIDGE_USER"
fi
install -d -o root -g root -m 0755 "$TARGET"
( cd "$SOURCE" && cargo build --release )
install -m 0755 -o root -g root "$SOURCE/target/release/hydra-umc-hil-bridge" "$TARGET/hydra-umc-hil-bridge"
install -m 0644 "$SOURCE/systemd/hydra-umc-hil-bridge.service" /etc/systemd/system/hydra-umc-hil-bridge.service
systemctl daemon-reload
echo "HIL-Bridge installed. Enable manually after review: systemctl enable --now hydra-umc-hil-bridge"
