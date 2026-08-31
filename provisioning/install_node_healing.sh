#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - Install HYDRA-UMC-NODE-HEALING as a local CM5 watchdog
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Real gap found auditing the ecosystem against actual CM5 hardware:
# HYDRA-UMC-NODE-HEALING already has a real watchdog loop (src/watchdog,
# src/config - see its own main.go) - never built or installed anywhere.
# Starts watching an intentionally EMPTY node registry
# (/etc/hydra-umc/node-healing/nodes.json = []) rather than this repo's
# own nodes.example.json, which lists HealthService gRPC endpoints for
# HYDRA-UMC-ORCHESTRATOR/VISION-NODE/COGNITIVE-NODE - none of which run as
# real services on this CM5 yet (real, separate future work). Watching
# zero nodes is an honest starting state; add real entries by hand as
# those nodes come online.
set -euo pipefail
[[ "${1:-}" == "--apply" ]] || { echo "Dry-run policy: rerun with --apply after review."; exit 0; }
[[ $EUID -eq 0 ]] || { echo "Run as root with sudo." >&2; exit 2; }

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SOURCE="$ROOT/HYDRA-UMC-NODE-HEALING"
TARGET=/opt/hydra-umc/node-healing
HEALING_USER="hydra-umc-node-healing"

echo " ==============================================================="
echo "  HYDRA-UMC-OS - install_node_healing.sh"
echo "  Installs the real HydraNode watchdog (Go, builds on-device)."
echo "  Copyright (C) 2026 JuanenRac (Electro Hobby 3D)"
echo "  <electrohobby3d@gmail.com> | GPL-3.0-or-later - see LICENSE"
echo " ==============================================================="

[[ -f "$SOURCE/go.mod" && -f "$SOURCE/systemd/hydra-umc-node-healing.service" ]] || {
  echo "HYDRA-UMC-NODE-HEALING source or systemd unit is incomplete: $SOURCE" >&2; exit 2;
}
if ! command -v go >/dev/null; then
  apt-get update
  apt-get install -y golang-go
fi
command -v go >/dev/null || { echo "golang-go installed but 'go' still not on PATH." >&2; exit 2; }

if ! id -u "$HEALING_USER" >/dev/null 2>&1; then
  useradd --system --home "$TARGET" --no-create-home --shell /usr/sbin/nologin "$HEALING_USER"
fi
install -d -o root -g root -m 0755 "$TARGET"
( cd "$SOURCE" && go build -o "$TARGET/hydra-umc-node-healing" . )
chown root:root "$TARGET/hydra-umc-node-healing"
chmod 0755 "$TARGET/hydra-umc-node-healing"
install -d -o root -g root -m 0755 /etc/hydra-umc/node-healing
[[ -f /etc/hydra-umc/node-healing/nodes.json ]] || echo "[]" > /etc/hydra-umc/node-healing/nodes.json
install -m 0644 "$SOURCE/systemd/hydra-umc-node-healing.service" /etc/systemd/system/hydra-umc-node-healing.service
systemctl daemon-reload
echo "Node-Healing installed, watching zero nodes (see this script's own header)."
echo "Enable manually after review: systemctl enable --now hydra-umc-node-healing"
echo "Add real targets to /etc/hydra-umc/node-healing/nodes.json as they come online."
