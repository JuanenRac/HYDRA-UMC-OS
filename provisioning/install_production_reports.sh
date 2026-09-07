#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - Install HYDRA-UMC-PRODUCTION-REPORTS as a local CM5 API
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Real gap found auditing the ecosystem against actual CM5 hardware:
# HYDRA-UMC-PRODUCTION-REPORTS is genuinely stdlib-only Python (a real
# ThreadingHTTPServer over HYDRA-UMC-DATALAKE's own HTTP API - see its own
# pyproject.toml) with a real, tested OEE/availability reporting engine -
# never installed anywhere. Same simple "copy src/ + PYTHONPATH" shape as
# install_datalake.sh, no venv/pip needed at runtime.
set -euo pipefail
[[ "${1:-}" == "--apply" ]] || { echo "Dry-run policy: rerun with --apply after review."; exit 0; }
[[ $EUID -eq 0 ]] || { echo "Run as root with sudo." >&2; exit 2; }

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SOURCE="$ROOT/HYDRA-UMC-PRODUCTION-REPORTS"
TARGET=/opt/hydra-umc/production-reports
REPORTS_USER="hydra-umc-production-reports"

echo " ==============================================================="
echo "  HYDRA-UMC-OS - install_production_reports.sh"
echo "  Installs the real OEE/availability reporting API (reads from"
echo "  HYDRA-UMC-DATALAKE, already installed loopback-only on this CM5)."
echo "  Copyright (C) 2026 JuanenRac (Electro Hobby 3D)"
echo "  <electrohobby3d@gmail.com> | GPL-3.0-or-later - see LICENSE"
echo " ==============================================================="

[[ -d "$SOURCE/src/hydra_umc_production_reports" && -f "$SOURCE/systemd/hydra-umc-production-reports.service" ]] || {
  echo "HYDRA-UMC-PRODUCTION-REPORTS source or systemd unit is incomplete: $SOURCE" >&2; exit 2;
}
command -v python3 >/dev/null || { echo "HYDRA-UMC-PRODUCTION-REPORTS requires python3." >&2; exit 2; }
if ! id -u "$REPORTS_USER" >/dev/null 2>&1; then
  useradd --system --home "$TARGET" --no-create-home --shell /usr/sbin/nologin "$REPORTS_USER"
fi
install -d -o root -g root -m 0755 "$TARGET"
rm -rf "$TARGET/src"
cp -a "$SOURCE/src" "$TARGET/"
chown -R root:root "$TARGET/src"
chmod -R go-w "$TARGET/src"
install -m 0644 "$SOURCE/systemd/hydra-umc-production-reports.service" /etc/systemd/system/hydra-umc-production-reports.service
systemctl daemon-reload
echo "Production-Reports installed. Enable manually after review: systemctl enable --now hydra-umc-production-reports"
