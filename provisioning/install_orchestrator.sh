#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - Install HYDRA-UMC-ORCHESTRATOR as a local CM5 API
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Real gap found auditing the ecosystem against actual CM5 hardware:
# HYDRA-UMC-ORCHESTRATOR's real mission state machine (mission.rs) was
# only ever exercised through mission-demo's own fixed, hardcoded
# scenario - server.rs (new, that repo) exposes the same
# MissionRegistry over a real HTTP API. Still purely in-memory
# bookkeeping: no real gRPC wiring to HYDRA-UMC-JOB-DISPATCHER/
# HYDRA-UMC-NODE-HEALING and no real E-STOP-sending code anywhere in
# that repository - this does not grant any new physical authority.
# Compiled release binary, same pattern as install_twin.sh.
set -euo pipefail
[[ "${1:-}" == "--apply" ]] || { echo "Dry-run policy: rerun with --apply after review."; exit 0; }
[[ $EUID -eq 0 ]] || { echo "Run as root with sudo." >&2; exit 2; }

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SOURCE="$ROOT/HYDRA-UMC-ORCHESTRATOR"
TARGET=/opt/hydra-umc/orchestrator
ORCH_USER="hydra-umc-orchestrator"

echo " ==============================================================="
echo "  HYDRA-UMC-OS - install_orchestrator.sh"
echo "  Installs the real mission-registry API (Rust, builds on-device)."
echo "  Copyright (C) 2026 JuanenRac (Electro Hobby 3D)"
echo "  <electrohobby3d@gmail.com> | GPL-3.0-or-later - see LICENSE"
echo " ==============================================================="

[[ -f "$SOURCE/Cargo.toml" && -f "$SOURCE/systemd/hydra-umc-orchestrator.service" ]] || {
  echo "HYDRA-UMC-ORCHESTRATOR source or systemd unit is incomplete: $SOURCE" >&2; exit 2;
}
if ! command -v cargo >/dev/null; then
  apt-get update
  apt-get install -y cargo
fi
command -v cargo >/dev/null || { echo "cargo installed but still not on PATH." >&2; exit 2; }

if ! id -u "$ORCH_USER" >/dev/null 2>&1; then
  useradd --system --home "$TARGET" --no-create-home --shell /usr/sbin/nologin "$ORCH_USER"
fi
install -d -o root -g root -m 0755 "$TARGET"
( cd "$SOURCE" && cargo build --release )
install -m 0755 -o root -g root "$SOURCE/target/release/hydra-umc-orchestrator" "$TARGET/hydra-umc-orchestrator"
install -m 0644 "$SOURCE/systemd/hydra-umc-orchestrator.service" /etc/systemd/system/hydra-umc-orchestrator.service
systemctl daemon-reload
echo "Orchestrator installed. Enable manually after review: systemctl enable --now hydra-umc-orchestrator"
