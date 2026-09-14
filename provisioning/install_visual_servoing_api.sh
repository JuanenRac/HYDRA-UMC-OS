#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - Install HYDRA-UMC-VISUAL-SERVOING-API as a local CM5 API
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Real gap found auditing the ecosystem against actual CM5 hardware:
# HYDRA-UMC-VISUAL-SERVOING-API's real PBVS correction law and
# authorization gate (pose.py, servo.py, authorization.py) were only ever
# reachable as a one-shot CLI - api.py (new) now exposes the exact same
# functions as a real stdlib HTTP API. Same simple "copy src/ + PYTHONPATH"
# shape as install_datalake.sh, no venv/pip needed at runtime.
set -euo pipefail
[[ "${1:-}" == "--apply" ]] || { echo "Dry-run policy: rerun with --apply after review."; exit 0; }
[[ $EUID -eq 0 ]] || { echo "Run as root with sudo." >&2; exit 2; }

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SOURCE="$ROOT/HYDRA-UMC-VISUAL-SERVOING-API"
TARGET=/opt/hydra-umc/visual-servoing-api
SERVOING_USER="hydra-umc-visual-servoing-api"

echo " ==============================================================="
echo "  HYDRA-UMC-OS - install_visual_servoing_api.sh"
echo "  Installs the real PBVS correction/authorization API."
echo "  Copyright (C) 2026 JuanenRac (Electro Hobby 3D)"
echo "  <electrohobby3d@gmail.com> | GPL-3.0-or-later - see LICENSE"
echo " ==============================================================="

[[ -d "$SOURCE/src/hydra_umc_visual_servoing_api" && -f "$SOURCE/systemd/hydra-umc-visual-servoing-api.service" ]] || {
  echo "HYDRA-UMC-VISUAL-SERVOING-API source or systemd unit is incomplete: $SOURCE" >&2; exit 2;
}
command -v python3 >/dev/null || { echo "HYDRA-UMC-VISUAL-SERVOING-API requires python3." >&2; exit 2; }
if ! id -u "$SERVOING_USER" >/dev/null 2>&1; then
  useradd --system --home "$TARGET" --no-create-home --shell /usr/sbin/nologin "$SERVOING_USER"
fi
install -d -o root -g root -m 0755 "$TARGET"
rm -rf "$TARGET/src"
cp -a "$SOURCE/src" "$TARGET/"
chown -R root:root "$TARGET/src"
chmod -R go-w "$TARGET/src"
install -m 0644 "$SOURCE/systemd/hydra-umc-visual-servoing-api.service" /etc/systemd/system/hydra-umc-visual-servoing-api.service
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
echo "Visual-Servoing-API installed. Enable manually after review: systemctl enable --now hydra-umc-visual-servoing-api"
