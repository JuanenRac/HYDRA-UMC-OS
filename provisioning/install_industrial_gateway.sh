#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - Install the Industry 4.0 Gateway stack (Docker Compose)
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Real gap found auditing the ecosystem against actual CM5 hardware:
# HYDRA-UMC-GATEWAY-INDUSTRIAL/docker-compose.yml already brings up all 3
# real protocol bridges (HYDRA-UMC-OPCUA-SERVER, HYDRA-UMC-MQTT-BROKER,
# HYDRA-UMC-MTCONNECT-ADAPTER) plus the Gateway's own aggregation surface
# with a single `docker compose up` - genuinely working, tested code, just
# never installed anywhere. This is the cheapest real gap to close: install
# Docker, then let that existing compose file do the rest.
set -euo pipefail
APPLY=false
[[ "${1:-}" == "--apply" ]] && APPLY=true
[[ $EUID -eq 0 ]] || { echo "Run as root with sudo." >&2; exit 2; }
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
GATEWAY_DIR="$ROOT/HYDRA-UMC-GATEWAY-INDUSTRIAL"
run() { if $APPLY; then "$@"; else printf '[dry-run] '; printf '%q ' "$@"; printf '\n'; fi; }

echo " ==============================================================="
echo "  HYDRA-UMC-OS - install_industrial_gateway.sh"
echo "  Docker + the real OPC-UA/MQTT/MTConnect protocol bridge stack."
echo "  Copyright (C) 2026 JuanenRac (Electro Hobby 3D)"
echo "  <electrohobby3d@gmail.com> | GPL-3.0-or-later - see LICENSE"
echo " ==============================================================="

for sibling in HYDRA-UMC-GATEWAY-INDUSTRIAL HYDRA-UMC-OPCUA-SERVER HYDRA-UMC-MQTT-BROKER HYDRA-UMC-MTCONNECT-ADAPTER; do
  [[ -d "$ROOT/$sibling" && -f "$ROOT/$sibling/Dockerfile" ]] || {
    echo "$sibling (with a Dockerfile) not found next to this checkout: $ROOT/$sibling" >&2
    echo "Clone it as a sibling of HYDRA-UMC-OS first (standard ecosystem checkout layout)." >&2
    exit 2
  }
done
[[ -f "$GATEWAY_DIR/docker-compose.yml" ]] || { echo "docker-compose.yml missing in $GATEWAY_DIR" >&2; exit 2; }

# Debian trixie's own repos ship real Docker packages - no third-party apt
# source/convenience-script needed, matching this repo's own established
# preference (see install_server.sh's Node.js comment for the same
# reasoning applied there). 2 real package-naming surprises found live on
# the first CM5 this ever ran against: (1) Compose v2 is package
# "docker-compose", not "docker-compose-v2" (apt-cache policy confirms
# it's genuinely 2.26.1, providing the "docker compose" plugin syntax
# used below); (2) "docker.io" installs dockerd/docker-proxy/docker-init
# only - the actual `docker` CLI client is the separate "docker-cli"
# package. docker-buildx is the modern build backend `compose ... --build`
# below wants.
run apt-get update
run apt-get install -y --no-install-recommends docker.io docker-cli docker-buildx docker-compose
run systemctl enable --now docker

if $APPLY; then
  echo "Building and starting the Gateway stack (docker compose up -d --build)..."
  (cd "$GATEWAY_DIR" && docker compose up -d --build)
  echo "Gateway stack started. Check status: cd $GATEWAY_DIR && docker compose ps"
  echo "Follow logs: cd $GATEWAY_DIR && docker compose logs -f"
else
  echo "[dry-run] cd $GATEWAY_DIR && docker compose up -d --build"
fi
