#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - Install HYDRA-UMC-TWIN as a local CM5 API
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Real gap found auditing the ecosystem against actual CM5 hardware:
# HYDRA-UMC-TWIN's real family-status/family-sync checks (family.rs,
# contract.rs) were only ever reachable as a one-shot CLI - server.rs
# (new, that repo) now exposes the same functions as a real HTTP API
# (tiny_http - the closest Rust equivalent to this ecosystem's other
# services' stdlib ThreadingHTTPServer, no async runtime). First Rust
# service installed as a compiled release binary rather than built
# on-device (unlike the Go services, this repo's own build.sh already
# expects a local `cargo build --release` toolchain - see that script).
#
# --workspace needs a real root:root 0755 tree with this node's real
# children's own hydra-umc.project.json files, NOT a symlink to the real
# sibling-checkout root - same real permission lesson learned installing
# HYDRA-UMC-VISION-NODE (that root lives under the operator's home
# directory, 0700 by Debian's own default, unreadable by this service's
# own unprivileged account).
set -euo pipefail
[[ "${1:-}" == "--apply" ]] || { echo "Dry-run policy: rerun with --apply after review."; exit 0; }
[[ $EUID -eq 0 ]] || { echo "Run as root with sudo." >&2; exit 2; }

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SOURCE="$ROOT/HYDRA-UMC-TWIN"
TARGET=/opt/hydra-umc/twin
TWIN_USER="hydra-umc-twin"

echo " ==============================================================="
echo "  HYDRA-UMC-OS - install_twin.sh"
echo "  Installs the real family-status/family-sync API (Rust, builds"
echo "  on-device)."
echo "  Copyright (C) 2026 JuanenRac (Electro Hobby 3D)"
echo "  <electrohobby3d@gmail.com> | GPL-3.0-or-later - see LICENSE"
echo " ==============================================================="

[[ -f "$SOURCE/Cargo.toml" && -f "$SOURCE/systemd/hydra-umc-twin.service" ]] || {
  echo "HYDRA-UMC-TWIN source or systemd unit is incomplete: $SOURCE" >&2; exit 2;
}
if ! command -v cargo >/dev/null; then
  apt-get update
  apt-get install -y cargo
fi
command -v cargo >/dev/null || { echo "cargo installed but still not on PATH." >&2; exit 2; }

if ! id -u "$TWIN_USER" >/dev/null 2>&1; then
  useradd --system --home "$TARGET" --no-create-home --shell /usr/sbin/nologin "$TWIN_USER"
fi
install -d -o root -g root -m 0755 "$TARGET"
( cd "$SOURCE" && cargo build --release )
install -m 0755 -o root -g root "$SOURCE/target/release/hydra-umc-twin" "$TARGET/hydra-umc-twin"

install -d -o root -g root -m 0755 "$TARGET/workspace"
for child in HYDRA-UMC-PHYSICS-REPLICA HYDRA-UMC-HIL-BRIDGE HYDRA-UMC-SYNTHETIC-DATA-GEN; do
  if [[ -f "$ROOT/$child/hydra-umc.project.json" ]]; then
    install -d -o root -g root -m 0755 "$TARGET/workspace/$child"
    install -m 0644 "$ROOT/$child/hydra-umc.project.json" "$TARGET/workspace/$child/hydra-umc.project.json"
  fi
done

install -m 0644 "$SOURCE/systemd/hydra-umc-twin.service" /etc/systemd/system/hydra-umc-twin.service
systemctl daemon-reload
echo "Twin installed. Enable manually after review: systemctl enable --now hydra-umc-twin"
