#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - Install HYDRA-UMC-TELEMETRY-COLLECTOR as a local CM5 API
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Real gap found auditing the ecosystem against actual CM5 hardware:
# HYDRA-UMC-TELEMETRY-COLLECTOR already has a real bounded ingestion
# pipeline (telemetry/, buffer/, collector/, sink/ - see its own
# src/main.go) that can deliver to a real HYDRA-UMC-DATALAKE instance -
# never built or installed anywhere. go.mod lives in src/, not the repo
# root - the one build-shape difference from install_job_dispatcher.sh/
# install_node_healing.sh.
set -euo pipefail
[[ "${1:-}" == "--apply" ]] || { echo "Dry-run policy: rerun with --apply after review."; exit 0; }
[[ $EUID -eq 0 ]] || { echo "Run as root with sudo." >&2; exit 2; }

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SOURCE="$ROOT/HYDRA-UMC-TELEMETRY-COLLECTOR"
TARGET=/opt/hydra-umc/telemetry-collector
COLLECTOR_USER="hydra-umc-telemetry-collector"

echo " ==============================================================="
echo "  HYDRA-UMC-OS - install_telemetry_collector.sh"
echo "  Installs the real CAN/WebSocket ingestion node (Go, builds"
echo "  on-device), feeding HYDRA-UMC-DATALAKE."
echo "  Copyright (C) 2026 JuanenRac (Electro Hobby 3D)"
echo "  <electrohobby3d@gmail.com> | GPL-3.0-or-later - see LICENSE"
echo " ==============================================================="

[[ -f "$SOURCE/src/go.mod" && -f "$SOURCE/systemd/hydra-umc-telemetry-collector.service" ]] || {
  echo "HYDRA-UMC-TELEMETRY-COLLECTOR source or systemd unit is incomplete: $SOURCE" >&2; exit 2;
}
if ! command -v go >/dev/null; then
  apt-get update
  apt-get install -y golang-go
fi
command -v go >/dev/null || { echo "golang-go installed but 'go' still not on PATH." >&2; exit 2; }

if ! id -u "$COLLECTOR_USER" >/dev/null 2>&1; then
  useradd --system --home "$TARGET" --no-create-home --shell /usr/sbin/nologin "$COLLECTOR_USER"
fi
install -d -o root -g root -m 0755 "$TARGET"
( cd "$SOURCE/src" && go build -o "$TARGET/telemetry-collector" . )
chown root:root "$TARGET/telemetry-collector"
chmod 0755 "$TARGET/telemetry-collector"
install -m 0644 "$SOURCE/systemd/hydra-umc-telemetry-collector.service" /etc/systemd/system/hydra-umc-telemetry-collector.service
systemctl daemon-reload
echo "Telemetry-Collector installed. Enable manually after review: systemctl enable --now hydra-umc-telemetry-collector"
echo "Depends on HYDRA-UMC-DATALAKE already running for -datalake-url to actually deliver samples."
