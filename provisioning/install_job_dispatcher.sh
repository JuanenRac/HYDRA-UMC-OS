#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - Install HYDRA-UMC-JOB-DISPATCHER as a local CM5 API
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Real gap found auditing the ecosystem against actual CM5 hardware:
# HYDRA-UMC-JOB-DISPATCHER already has a real priority mission queue and a
# real HTTP API (src/api, src/dispatcher - see its own main.go) - never
# built or installed anywhere. First Go service installed on this CM5, so
# this also provisions the (real, apt-packaged) Go toolchain the on-device
# build needs - a pure-Go binary with CGO_ENABLED left at its default (no
# cgo dependency in go.mod), so no C toolchain is required beyond that.
set -euo pipefail
[[ "${1:-}" == "--apply" ]] || { echo "Dry-run policy: rerun with --apply after review."; exit 0; }
[[ $EUID -eq 0 ]] || { echo "Run as root with sudo." >&2; exit 2; }

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SOURCE="$ROOT/HYDRA-UMC-JOB-DISPATCHER"
TARGET=/opt/hydra-umc/job-dispatcher
DISPATCHER_USER="hydra-umc-job-dispatcher"

echo " ==============================================================="
echo "  HYDRA-UMC-OS - install_job_dispatcher.sh"
echo "  Installs the real priority mission queue (Go, builds on-device)."
echo "  Copyright (C) 2026 JuanenRac (Electro Hobby 3D)"
echo "  <electrohobby3d@gmail.com> | GPL-3.0-or-later - see LICENSE"
echo " ==============================================================="

[[ -f "$SOURCE/go.mod" && -f "$SOURCE/systemd/hydra-umc-job-dispatcher.service" ]] || {
  echo "HYDRA-UMC-JOB-DISPATCHER source or systemd unit is incomplete: $SOURCE" >&2; exit 2;
}
if ! command -v go >/dev/null; then
  apt-get update
  apt-get install -y golang-go
fi
command -v go >/dev/null || { echo "golang-go installed but 'go' still not on PATH." >&2; exit 2; }

if ! id -u "$DISPATCHER_USER" >/dev/null 2>&1; then
  useradd --system --home "$TARGET" --no-create-home --shell /usr/sbin/nologin "$DISPATCHER_USER"
fi
install -d -o root -g root -m 0755 "$TARGET"
( cd "$SOURCE" && go build -o "$TARGET/hydra-umc-job-dispatcher" . )
chown root:root "$TARGET/hydra-umc-job-dispatcher"
chmod 0755 "$TARGET/hydra-umc-job-dispatcher"
install -m 0644 "$SOURCE/systemd/hydra-umc-job-dispatcher.service" /etc/systemd/system/hydra-umc-job-dispatcher.service
systemctl daemon-reload
echo "Job-Dispatcher installed. Enable manually after review: systemctl enable --now hydra-umc-job-dispatcher"
