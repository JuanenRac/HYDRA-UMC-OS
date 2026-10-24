#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - Install HYDRA-UMC-JOB-DISPATCHER as a local CM5 API
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Real gap found auditing the ecosystem against actual CM5 hardware:
# HYDRA-UMC-JOB-DISPATCHER already has a real priority mission queue and a
# real HTTP API (src/api, src/dispatcher - see its own main.go) - never
# built or installed anywhere. First Go service installed on this CM5.
#
# Real gap found in a later pass, before this ever ran against real
# hardware: go.mod now needs a real Go >= 1.21 (modernc.org/sqlite, the
# pure-Go SQLite driver src/sqlitestore's own persistence uses - see that
# repo's own CHANGELOG). This installs a specific, checksum-verified
# upstream Go release from go.dev instead of depending on whatever Go the
# base's own Debian trixie archive happens to package: that version drifts
# over time, a pinned, verified tarball doesn't. Still a pure-Go binary otherwise: CGO_ENABLED is left
# at its default (no cgo dependency in go.mod), so no C cross-toolchain is
# needed beyond this one real Go toolchain.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # absolute, before any cd
[[ "${1:-}" == "--apply" ]] || { echo "Dry-run policy: rerun with --apply after review."; exit 0; }
[[ $EUID -eq 0 ]] || { echo "Run as root with sudo." >&2; exit 2; }

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SOURCE="$ROOT/HYDRA-UMC-JOB-DISPATCHER"
TARGET=/opt/hydra-umc/job-dispatcher
DISPATCHER_USER="hydra-umc-job-dispatcher"
# The pinned, checksum-verified upstream Go release (go.dev/dl) is in go_toolchain.sh, shared with the other Go services.
source "$HERE/go_toolchain.sh"

echo " ==============================================================="
echo "  HYDRA-UMC-OS - install_job_dispatcher.sh"
echo "  Installs the real priority mission queue (Go, builds on-device)."
echo "  Copyright (C) 2026 JuanenRac (Electro Hobby 3D)"
echo "  <electrohobby3d@gmail.com> | GPL-3.0-or-later - see LICENSE"
echo " ==============================================================="

[[ -f "$SOURCE/go.mod" && -f "$SOURCE/systemd/hydra-umc-job-dispatcher.service" ]] || {
  echo "HYDRA-UMC-JOB-DISPATCHER source or systemd unit is incomplete: $SOURCE" >&2; exit 2;
}

ensure_go

if ! id -u "$DISPATCHER_USER" >/dev/null 2>&1; then
  useradd --system --home "$TARGET" --no-create-home --shell /usr/sbin/nologin "$DISPATCHER_USER"
fi
install -d -o root -g root -m 0755 "$TARGET"
# Real, durable sqlite3 file lives here - the one path ProtectSystem=strict
# (see the unit's own [Service] block) leaves writable for this account.
install -d -o "$DISPATCHER_USER" -g "$DISPATCHER_USER" -m 0750 "$TARGET/data"
( cd "$SOURCE" && "$GO_BIN" build -o "$TARGET/hydra-umc-job-dispatcher" . )
chown root:root "$TARGET/hydra-umc-job-dispatcher"
chmod 0755 "$TARGET/hydra-umc-job-dispatcher"
install -m 0644 "$SOURCE/systemd/hydra-umc-job-dispatcher.service" /etc/systemd/system/hydra-umc-job-dispatcher.service
# Real bug found live: every install_*.sh here updated the deployed
# build/binary but never this project's OWN hydra-umc.project.json -
# GET /api/ecosystem/status (STUDIO's own Services/AI Family panels)
# reads THIS file for name/version/maturity/family, so every one of
# them kept reporting whatever version happened to be here from the
# very first install, forever, no matter how many real updates
# followed. Copied last, right before the reload, so it always
# reflects the exact SOURCE that was actually just installed.
install -m 0644 "$SOURCE/hydra-umc.project.json" "$TARGET/hydra-umc.project.json"
systemctl daemon-reload
echo "Job-Dispatcher installed. Enable manually after review: systemctl enable --now hydra-umc-job-dispatcher"

# Where to look once the service runs: the port and the health route come from the service registry.
source "$HERE/service_registry.sh"
announce_health HYDRA-UMC-JOB-DISPATCHER
