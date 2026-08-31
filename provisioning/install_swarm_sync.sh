#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - Install HYDRA-UMC-SWARM-SYNC as a local CM5 API
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Real gap found auditing the ecosystem against actual CM5 hardware:
# HYDRA-UMC-SWARM-SYNC's real CRDT reconciliation (reconcile(), split
# out of main.rs into reconcile.rs) was only ever reachable as a
# one-shot CLI over a local scenario file - server.rs (new, that repo)
# now exposes the same function as a real HTTP API. Compiled release
# binary, same pattern as install_twin.sh.
set -euo pipefail
[[ "${1:-}" == "--apply" ]] || { echo "Dry-run policy: rerun with --apply after review."; exit 0; }
[[ $EUID -eq 0 ]] || { echo "Run as root with sudo." >&2; exit 2; }

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SOURCE="$ROOT/HYDRA-UMC-SWARM-SYNC"
TARGET=/opt/hydra-umc/swarm-sync
SYNC_USER="hydra-umc-swarm-sync"

echo " ==============================================================="
echo "  HYDRA-UMC-OS - install_swarm_sync.sh"
echo "  Installs the real CRDT-reconciliation API (Rust, builds"
echo "  on-device)."
echo "  Copyright (C) 2026 JuanenRac (Electro Hobby 3D)"
echo "  <electrohobby3d@gmail.com> | GPL-3.0-or-later - see LICENSE"
echo " ==============================================================="

[[ -f "$SOURCE/Cargo.toml" && -f "$SOURCE/systemd/hydra-umc-swarm-sync.service" ]] || {
  echo "HYDRA-UMC-SWARM-SYNC source or systemd unit is incomplete: $SOURCE" >&2; exit 2;
}
if ! command -v cargo >/dev/null; then
  apt-get update
  apt-get install -y cargo
fi
command -v cargo >/dev/null || { echo "cargo installed but still not on PATH." >&2; exit 2; }

if ! id -u "$SYNC_USER" >/dev/null 2>&1; then
  useradd --system --home "$TARGET" --no-create-home --shell /usr/sbin/nologin "$SYNC_USER"
fi
install -d -o root -g root -m 0755 "$TARGET"
( cd "$SOURCE" && cargo build --release )
install -m 0755 -o root -g root "$SOURCE/target/release/hydra-umc-swarm-sync" "$TARGET/hydra-umc-swarm-sync"
install -m 0644 "$SOURCE/systemd/hydra-umc-swarm-sync.service" /etc/systemd/system/hydra-umc-swarm-sync.service
systemctl daemon-reload
echo "Swarm-Sync installed. Enable manually after review: systemctl enable --now hydra-umc-swarm-sync"
