#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - Install HYDRA-UMC-ANOMALY-DETECTOR as a local CM5 API
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Real gap found auditing the ecosystem against actual CM5 hardware: this
# is the only one of the 8 real "AI" repos that already runs as a real
# HTTP service (the other 7 are CLIs only, see this session's own audit) -
# real FFT + z-score anomaly detection, tested against a labeled synthetic
# fixture - never installed anywhere. Unlike install_datalake.sh/
# install_voice_ui.sh, this one real dependency (numpy) means "copy src/ +
# PYTHONPATH" alone is not enough - python3-numpy is a real Debian package,
# no venv/pip needed.
set -euo pipefail
APPLY=false
[[ "${1:-}" == "--apply" ]] && APPLY=true
[[ $EUID -eq 0 ]] || { echo "Run as root with sudo." >&2; exit 2; }

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SOURCE="$ROOT/HYDRA-UMC-ANOMALY-DETECTOR"
TARGET=/opt/hydra-umc/anomaly-detector
ANOMALY_USER="hydra-umc-anomaly"
run() { if $APPLY; then "$@"; else printf '[dry-run] '; printf '%q ' "$@"; printf '\n'; fi; }

echo " ==============================================================="
echo "  HYDRA-UMC-OS - install_anomaly_detector.sh"
echo "  Installs the real FFT + z-score anomaly-detection API."
echo "  Copyright (C) 2026 JuanenRac (Electro Hobby 3D)"
echo "  <electrohobby3d@gmail.com> | GPL-3.0-or-later - see LICENSE"
echo " ==============================================================="

[[ -d "$SOURCE/src/hydra_umc_anomaly_detector" && -f "$SOURCE/systemd/hydra-umc-anomaly-detector.service" ]] || {
  echo "HYDRA-UMC-ANOMALY-DETECTOR source or systemd unit is incomplete: $SOURCE" >&2; exit 2;
}
run apt-get update
run apt-get install -y --no-install-recommends python3-numpy
if $APPLY; then
  if ! id -u "$ANOMALY_USER" >/dev/null 2>&1; then
    useradd --system --home "$TARGET" --no-create-home --shell /usr/sbin/nologin "$ANOMALY_USER"
  fi
else
  echo "[dry-run] useradd --system --home $TARGET --no-create-home --shell /usr/sbin/nologin $ANOMALY_USER"
fi
run install -d -o root -g root -m 0755 "$TARGET"
if $APPLY; then
  rm -rf "$TARGET/src"
  cp -a "$SOURCE/src" "$TARGET/"
  chown -R root:root "$TARGET/src"
  chmod -R go-w "$TARGET/src"
else
  echo "[dry-run] copy $SOURCE/src to $TARGET/src (root:root, not group/other-writable)"
fi
run install -m 0644 "$SOURCE/systemd/hydra-umc-anomaly-detector.service" /etc/systemd/system/hydra-umc-anomaly-detector.service
run systemctl daemon-reload
echo "Anomaly-Detector installed. Enable manually after review: systemctl enable --now hydra-umc-anomaly-detector"
