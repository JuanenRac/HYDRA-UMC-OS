#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - Install HYDRA-UMC-DATALAKE as a local CM5 time-series API
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Real gap found auditing the ecosystem against actual CM5 hardware:
# HYDRA-UMC-DATALAKE is genuinely stdlib-only Python (sqlite3 + a real
# ThreadingHTTPServer, no third-party runtime dependency at all - see its
# own pyproject.toml) with a real, tested HTTP API - never installed
# anywhere. Same simple "copy src/ + PYTHONPATH" shape as
# install_voice_ui.sh (also stdlib-only), no venv/pip needed at runtime.
set -euo pipefail
[[ "${1:-}" == "--apply" ]] || { echo "Dry-run policy: rerun with --apply after review."; exit 0; }
[[ $EUID -eq 0 ]] || { echo "Run as root with sudo." >&2; exit 2; }

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SOURCE="$ROOT/HYDRA-UMC-DATALAKE"
TARGET=/opt/hydra-umc/datalake
DATALAKE_USER="hydra-umc-datalake"

echo " ==============================================================="
echo "  HYDRA-UMC-OS - install_datalake.sh"
echo "  Installs the real sqlite3-backed time-series API (Server's"
echo "  Ecosystem > Telemetry proxy target - HYDRA_UMC_DATALAKE_URL)."
echo "  Copyright (C) 2026 JuanenRac (Electro Hobby 3D)"
echo "  <electrohobby3d@gmail.com> | GPL-3.0-or-later - see LICENSE"
echo " ==============================================================="

[[ -d "$SOURCE/src/hydra_umc_datalake" && -f "$SOURCE/systemd/hydra-umc-datalake.service" ]] || {
  echo "HYDRA-UMC-DATALAKE source or systemd unit is incomplete: $SOURCE" >&2; exit 2;
}
command -v python3 >/dev/null || { echo "HYDRA-UMC-DATALAKE requires python3." >&2; exit 2; }
if ! id -u "$DATALAKE_USER" >/dev/null 2>&1; then
  useradd --system --home "$TARGET" --no-create-home --shell /usr/sbin/nologin "$DATALAKE_USER"
fi
install -d -o root -g root -m 0755 "$TARGET"
rm -rf "$TARGET/src"
cp -a "$SOURCE/src" "$TARGET/"
chown -R root:root "$TARGET/src"
chmod -R go-w "$TARGET/src"
# Real, durable sqlite3 file lives here - the one path ProtectSystem=strict
# (see the unit's own [Service] block) leaves writable for this account.
install -d -o "$DATALAKE_USER" -g "$DATALAKE_USER" -m 0750 "$TARGET/data"
install -m 0644 "$SOURCE/systemd/hydra-umc-datalake.service" /etc/systemd/system/hydra-umc-datalake.service
systemctl daemon-reload
echo "Datalake installed. Enable manually after review: systemctl enable --now hydra-umc-datalake"
echo "Then point Server at it: uncomment HYDRA_UMC_DATALAKE_URL in /etc/hydra-umc/server.env and restart hydra-umc-server."
