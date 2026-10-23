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
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" \&\& pwd)"   # absolute, before any cd
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

# docker-compose.yml needs the secrets of a production gateway and broker (GATEWAY_JWT_SECRET, MQTT_AUTH_JSON, MQTT_ACL_JSON): without them
# both refuse to start. They are generated per device (never overwritten) and the credential of each machine bridge is printed once. A bridge
# connects with HYDRA_MQTT_USERNAME / HYDRA_MQTT_PASSWORD of its own credential.
#
# The file lives in /etc/hydra-umc/gateway.env (root only, 0600), outside the checkout of the user: a `git clean -xdf` or a fresh clone cannot
# take it away, and the updater, which works as a normal user in that checkout, has no file of root to trip over. Compose reads it with
# --env-file; the compose file itself does not change. A file left in the checkout by an earlier version is MOVED (not copied: there is
# never a second copy of the secrets).
GATEWAY_ENV="${HYDRA_GATEWAY_ENV:-/etc/hydra-umc/gateway.env}"
LEGACY_ENV="$GATEWAY_DIR/.env"
# --- gateway env begin
if $APPLY; then
  [[ -d "$(dirname "$GATEWAY_ENV")" ]] || install -d -o root -g root -m 0750 "$(dirname "$GATEWAY_ENV")"
  if [[ -f "$LEGACY_ENV" && ! -e "$GATEWAY_ENV" ]]; then
    mv "$LEGACY_ENV" "$GATEWAY_ENV"
    chown root:root "$GATEWAY_ENV"
    chmod 0600 "$GATEWAY_ENV"
    echo "Moved the secrets of the stack from $LEGACY_ENV to $GATEWAY_ENV."
  elif [[ -f "$LEGACY_ENV" ]]; then
    echo "WARNING: $LEGACY_ENV exists next to $GATEWAY_ENV. The stack reads only $GATEWAY_ENV: compare them and remove the old file by hand." >&2
  fi
  python3 "$(dirname "$0")/gateway_env.py" "$GATEWAY_ENV" --apply
else
  [[ -f "$LEGACY_ENV" && ! -e "$GATEWAY_ENV" ]] && echo "[dry-run] mv $LEGACY_ENV $GATEWAY_ENV"
  python3 "$(dirname "$0")/gateway_env.py" "$GATEWAY_ENV"
fi
# --- gateway env end

# every compose command takes the same --env-file: compose resolves ${GATEWAY_JWT_SECRET:?...} when it reads the file, even for `ps` or `logs`
COMPOSE="docker compose --env-file $GATEWAY_ENV"
if $APPLY; then
  echo "Building and starting the Gateway stack ($COMPOSE up -d --build)..."
  (cd "$GATEWAY_DIR" && $COMPOSE up -d --build)
  echo "Gateway stack started. Check status: cd $GATEWAY_DIR && $COMPOSE ps"
  echo "Follow logs: cd $GATEWAY_DIR && $COMPOSE logs -f"
else
  echo "[dry-run] cd $GATEWAY_DIR && $COMPOSE up -d --build"
fi

# Real gap found live, distinct from every other install_*.sh's own
# missing-manifest bug: GET /api/ecosystem/status (STUDIO's own Services/
# AI Family panels) only ever looks under /opt/hydra-umc/<name>/ for a
# real hydra-umc.project.json - a project running purely as a Docker
# container (this whole stack) has no such directory at all, so these 4
# would stay invisible there forever even once the stack above is
# genuinely up and healthy. Drops each one's own real manifest at the
# same real host path every other project's own install script uses, so
# the exact same discovery path picks these up too - the container
# itself never needs to know this directory exists.
for project in HYDRA-UMC-GATEWAY-INDUSTRIAL HYDRA-UMC-OPCUA-SERVER HYDRA-UMC-MQTT-BROKER HYDRA-UMC-MTCONNECT-ADAPTER; do
  target_dir="/opt/hydra-umc/$(echo "$project" | sed 's/^HYDRA-UMC-//' | tr '[:upper:]_' '[:lower:]-')"
  run install -d -o root -g root -m 0755 "$target_dir"
  run install -m 0644 "$ROOT/$project/hydra-umc.project.json" "$target_dir/hydra-umc.project.json"
done

# Where to look once the stack runs: the port and the health route of each part come from the service registry.
source "$HERE/service_registry.sh"
for service in HYDRA-UMC-GATEWAY-INDUSTRIAL HYDRA-UMC-OPCUA-SERVER HYDRA-UMC-MQTT-BROKER HYDRA-UMC-MTCONNECT-ADAPTER; do
  announce_health "$service"
done
