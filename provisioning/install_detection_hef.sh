#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - Install HYDRA-UMC-DETECTION-HEF as a local CM5 API
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Real gap found auditing the ecosystem against actual CM5 hardware:
# HYDRA-UMC-DETECTION-HEF's real compiled-model registry (registry.py)
# and safe-load gate (compatibility.py) were only ever reachable as a
# one-shot CLI - api.py (new) now exposes the same functions as a real
# stdlib HTTP API. Same simple "copy src/ + PYTHONPATH" shape as
# install_datalake.sh, no venv/pip needed at runtime.
#
# The registry config lives at /etc/hydra-umc-detection-hef/, NOT under
# the shared /etc/hydra-umc/ tree (0750 root:hydra-umc-agent) - same real
# permission lesson learned installing HYDRA-UMC-NODE-HEALING: this
# service's own unprivileged account cannot traverse into that directory
# to open its own config file. Starts against a real, valid, empty
# registry ([]) - safe to enable/start immediately, no real .hef models
# registered yet.
set -euo pipefail
[[ "${1:-}" == "--apply" ]] || { echo "Dry-run policy: rerun with --apply after review."; exit 0; }
[[ $EUID -eq 0 ]] || { echo "Run as root with sudo." >&2; exit 2; }

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SOURCE="$ROOT/HYDRA-UMC-DETECTION-HEF"
TARGET=/opt/hydra-umc/detection-hef
HEF_USER="hydra-umc-detection-hef"

echo " ==============================================================="
echo "  HYDRA-UMC-OS - install_detection_hef.sh"
echo "  Installs the real compiled-model registry + safe-load API."
echo "  Copyright (C) 2026 JuanenRac (Electro Hobby 3D)"
echo "  <electrohobby3d@gmail.com> | GPL-3.0-or-later - see LICENSE"
echo " ==============================================================="

[[ -d "$SOURCE/src/hydra_umc_detection_hef" && -f "$SOURCE/systemd/hydra-umc-detection-hef.service" ]] || {
  echo "HYDRA-UMC-DETECTION-HEF source or systemd unit is incomplete: $SOURCE" >&2; exit 2;
}
command -v python3 >/dev/null || { echo "HYDRA-UMC-DETECTION-HEF requires python3." >&2; exit 2; }
if ! id -u "$HEF_USER" >/dev/null 2>&1; then
  useradd --system --home "$TARGET" --no-create-home --shell /usr/sbin/nologin "$HEF_USER"
fi
install -d -o root -g root -m 0755 "$TARGET"
rm -rf "$TARGET/src"
cp -a "$SOURCE/src" "$TARGET/"
chown -R root:root "$TARGET/src"
chmod -R go-w "$TARGET/src"
install -d -o root -g root -m 0755 "$TARGET/models"
install -d -o root -g root -m 0755 /etc/hydra-umc-detection-hef
[[ -f /etc/hydra-umc-detection-hef/registry.json ]] || echo "[]" > /etc/hydra-umc-detection-hef/registry.json
chmod 0644 /etc/hydra-umc-detection-hef/registry.json
install -m 0644 "$SOURCE/systemd/hydra-umc-detection-hef.service" /etc/systemd/system/hydra-umc-detection-hef.service
systemctl daemon-reload
echo "Detection-HEF installed, serving an empty registry. Enable manually after review: systemctl enable --now hydra-umc-detection-hef"
echo "Add real entries to /etc/hydra-umc-detection-hef/registry.json and .hef files to $TARGET/models as they exist."
