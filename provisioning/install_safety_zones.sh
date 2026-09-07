#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - Install HYDRA-UMC-SAFETY-ZONES as a local CM5 API
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Real gap found auditing the ecosystem against actual CM5 hardware:
# HYDRA-UMC-SAFETY-ZONES's real zone-breach checking and E-STOP-request
# logic (breach.py, safety_state.py, estop.py) was only ever reachable
# as a one-shot CLI - api.py (new) now exposes the same functions as a
# real stdlib HTTP API. Same simple "copy src/ + PYTHONPATH" shape as
# install_datalake.sh, no venv/pip needed at runtime.
set -euo pipefail
[[ "${1:-}" == "--apply" ]] || { echo "Dry-run policy: rerun with --apply after review."; exit 0; }
[[ $EUID -eq 0 ]] || { echo "Run as root with sudo." >&2; exit 2; }

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SOURCE="$ROOT/HYDRA-UMC-SAFETY-ZONES"
TARGET=/opt/hydra-umc/safety-zones
ZONES_USER="hydra-umc-safety-zones"

echo " ==============================================================="
echo "  HYDRA-UMC-OS - install_safety_zones.sh"
echo "  Installs the real intrusion-detection/E-STOP-request API."
echo "  Copyright (C) 2026 JuanenRac (Electro Hobby 3D)"
echo "  <electrohobby3d@gmail.com> | GPL-3.0-or-later - see LICENSE"
echo " ==============================================================="

[[ -d "$SOURCE/src/hydra_umc_safety_zones" && -f "$SOURCE/systemd/hydra-umc-safety-zones.service" ]] || {
  echo "HYDRA-UMC-SAFETY-ZONES source or systemd unit is incomplete: $SOURCE" >&2; exit 2;
}
command -v python3 >/dev/null || { echo "HYDRA-UMC-SAFETY-ZONES requires python3." >&2; exit 2; }
if ! id -u "$ZONES_USER" >/dev/null 2>&1; then
  useradd --system --home "$TARGET" --no-create-home --shell /usr/sbin/nologin "$ZONES_USER"
fi
install -d -o root -g root -m 0755 "$TARGET"
rm -rf "$TARGET/src"
cp -a "$SOURCE/src" "$TARGET/"
chown -R root:root "$TARGET/src"
chmod -R go-w "$TARGET/src"
install -m 0644 "$SOURCE/systemd/hydra-umc-safety-zones.service" /etc/systemd/system/hydra-umc-safety-zones.service
systemctl daemon-reload
echo "Safety-Zones installed. Enable manually after review: systemctl enable --now hydra-umc-safety-zones"
