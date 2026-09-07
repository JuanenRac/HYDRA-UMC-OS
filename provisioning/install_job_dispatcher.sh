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
# repo's own CHANGELOG) - but Raspberry Pi OS's own base, Debian 12
# "bookworm", ships golang-go 2:1.19~1 (verified against packages.debian.org),
# one real minor version short. `apt-get install golang-go` alone would
# fail this build on real hardware, not a hypothetical - this installs a
# specific, checksum-verified upstream Go release from go.dev instead of
# depending on whatever Debian happens to package (bookworm-backports has
# a new-enough Go, but isn't guaranteed enabled on every real image this
# runs against, and its own version drifts over time - a pinned, verified
# tarball doesn't). Still a pure-Go binary otherwise: CGO_ENABLED is left
# at its default (no cgo dependency in go.mod), so no C cross-toolchain is
# needed beyond this one real Go toolchain.
set -euo pipefail
[[ "${1:-}" == "--apply" ]] || { echo "Dry-run policy: rerun with --apply after review."; exit 0; }
[[ $EUID -eq 0 ]] || { echo "Run as root with sudo." >&2; exit 2; }

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SOURCE="$ROOT/HYDRA-UMC-JOB-DISPATCHER"
TARGET=/opt/hydra-umc/job-dispatcher
DISPATCHER_USER="hydra-umc-job-dispatcher"
# Pinned, checksum-verified upstream Go release (go.dev/dl) - real values
# captured from that page's own JSON API, not guessed. Bump both together
# if this project's own go.mod ever raises its minimum past this version.
GO_VERSION="1.27.1"
GO_TARBALL="go${GO_VERSION}.linux-arm64.tar.gz"
GO_SHA256="3450b45a3f9ee8568792736a5c5e70a1f2e9b36c35a8f74958c03e51d7d92bec"
GO_ROOT="/usr/local/go-${GO_VERSION}"

echo " ==============================================================="
echo "  HYDRA-UMC-OS - install_job_dispatcher.sh"
echo "  Installs the real priority mission queue (Go, builds on-device)."
echo "  Copyright (C) 2026 JuanenRac (Electro Hobby 3D)"
echo "  <electrohobby3d@gmail.com> | GPL-3.0-or-later - see LICENSE"
echo " ==============================================================="

[[ -f "$SOURCE/go.mod" && -f "$SOURCE/systemd/hydra-umc-job-dispatcher.service" ]] || {
  echo "HYDRA-UMC-JOB-DISPATCHER source or systemd unit is incomplete: $SOURCE" >&2; exit 2;
}

if [[ ! -x "$GO_ROOT/bin/go" ]]; then
  WORKDIR="$(mktemp -d)"
  trap 'rm -rf "$WORKDIR"' EXIT
  curl -fsSL -o "$WORKDIR/$GO_TARBALL" "https://go.dev/dl/$GO_TARBALL"
  echo "$GO_SHA256  $WORKDIR/$GO_TARBALL" | sha256sum -c -
  rm -rf "$GO_ROOT"
  mkdir -p "$GO_ROOT"
  tar -C "$GO_ROOT" --strip-components=1 -xzf "$WORKDIR/$GO_TARBALL"
fi
GO_BIN="$GO_ROOT/bin/go"
[[ -x "$GO_BIN" ]] || { echo "Go toolchain install at $GO_ROOT did not produce a real go binary." >&2; exit 2; }

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
systemctl daemon-reload
echo "Job-Dispatcher installed. Enable manually after review: systemctl enable --now hydra-umc-job-dispatcher"
