#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - Install HYDRA-UMC-NODE-HEALING as a local CM5 watchdog
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Real gap found auditing the ecosystem against actual CM5 hardware:
# HYDRA-UMC-NODE-HEALING already has a real watchdog loop (src/watchdog,
# src/config - see its own main.go) - never built or installed anywhere.
#
# Installs the CAPABILITY only, same as install_vision_streamer.sh - does
# NOT create a registry or enable/start the service. Real, live-verified
# constraint: config.LoadNodes() itself refuses an empty registry
# ("node registry ... is empty - nothing to watch"), so "watch zero
# nodes" (this script's own first, wrong attempt) is not a state this
# binary can actually run in - and this repo's own nodes.example.json
# names HealthService gRPC endpoints for HYDRA-UMC-ORCHESTRATOR/
# VISION-NODE/COGNITIVE-NODE, none of which run as a real service on this
# CM5 yet (real, separate future work), so seeding the real example file
# would only ever report every node UNREACHABLE. There is genuinely
# nothing for this watchdog to watch yet - see the printed instructions
# below for what to do once that changes.
#
# The registry belongs OUTSIDE the shared /etc/hydra-umc/ tree: that tree
# is 0750 root:hydra-umc-agent (see install_local_agent.sh), and this
# service's own unprivileged account is a member of neither, so it could
# never actually traverse into it to open its own config file - real bug
# found live on this device's first install (systemd's own
# EnvironmentFile= directive, used by other services under
# /etc/hydra-umc/, is read by systemd itself as root before it drops
# privileges; a plain os.Open() by this service's own process is not).
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
install -d -o root -g root -m 0755 /etc/hydra-umc-node-healing
install -m 0644 "$SOURCE/systemd/hydra-umc-node-healing.service" /etc/systemd/system/hydra-umc-node-healing.service
systemctl daemon-reload
echo "Node-Healing capability installed (not enabled - see this script's own header)."
echo "This binary refuses to run with zero nodes to watch, and no real"
echo "HealthService-speaking node exists on this CM5 yet. Once one does:"
echo "  cp $SOURCE/nodes.example.json /etc/hydra-umc-node-healing/nodes.json"
echo "  \$EDITOR /etc/hydra-umc-node-healing/nodes.json     # point at real node(s)"
echo "  systemctl enable --now hydra-umc-node-healing"
