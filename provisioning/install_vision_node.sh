#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - Install HYDRA-UMC-VISION-NODE as a local CM5 API
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Real gap found auditing the ecosystem against actual CM5 hardware:
# HYDRA-UMC-VISION-NODE's real family/pipeline-status/frame-validation
# checks (family.py, hardware.py, frame.py) were only ever reachable as a
# one-shot CLI - api.py (new) now exposes the same functions as a real
# stdlib HTTP API. Same simple "copy src/ + PYTHONPATH" shape as
# install_datalake.sh, no venv/pip needed at runtime.
#
# GET /family-status needs a real workspace directory containing this
# node's 4 real children's own hydra-umc.project.json files to report
# anything but "all missing". Real bug found live on this device's first
# install: a symlink straight to $ROOT (this script's first, wrong
# attempt) is unreadable by this service's own unprivileged account no
# matter how ProtectHome is set - $ROOT lives under the operator's own
# home directory, itself 0700 (Debian's own default), which blocks ANY
# other account's traversal regardless of systemd sandboxing. Instead,
# this script (running as root, so real read access to $ROOT is not in
# question here) copies out just the small hydra-umc.project.json file
# for each of the 4 expected children that is actually checked out
# there, into a real root:root 0755 tree this service CAN read. This is
# a point-in-time snapshot, not a live view - rerun this script to
# refresh it after a child's manifest changes (e.g. a maturity bump).
set -euo pipefail
[[ "${1:-}" == "--apply" ]] || { echo "Dry-run policy: rerun with --apply after review."; exit 0; }
[[ $EUID -eq 0 ]] || { echo "Run as root with sudo." >&2; exit 2; }

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SOURCE="$ROOT/HYDRA-UMC-VISION-NODE"
TARGET=/opt/hydra-umc/vision-node
NODE_USER="hydra-umc-vision-node"

echo " ==============================================================="
echo "  HYDRA-UMC-OS - install_vision_node.sh"
echo "  Installs the real family/pipeline-status/frame-validation API."
echo "  Copyright (C) 2026 JuanenRac (Electro Hobby 3D)"
echo "  <electrohobby3d@gmail.com> | GPL-3.0-or-later - see LICENSE"
echo " ==============================================================="

[[ -d "$SOURCE/src/hydra_umc_vision_node" && -f "$SOURCE/systemd/hydra-umc-vision-node.service" ]] || {
  echo "HYDRA-UMC-VISION-NODE source or systemd unit is incomplete: $SOURCE" >&2; exit 2;
}
command -v python3 >/dev/null || { echo "HYDRA-UMC-VISION-NODE requires python3." >&2; exit 2; }
if ! id -u "$NODE_USER" >/dev/null 2>&1; then
  useradd --system --home "$TARGET" --no-create-home --shell /usr/sbin/nologin "$NODE_USER"
fi
install -d -o root -g root -m 0755 "$TARGET"
rm -rf "$TARGET/src"
cp -a "$SOURCE/src" "$TARGET/"
chown -R root:root "$TARGET/src"
chmod -R go-w "$TARGET/src"
install -d -o root -g root -m 0755 "$TARGET/workspace"
for child in HYDRA-UMC-VISION-STREAMER HYDRA-UMC-DETECTION-HEF HYDRA-UMC-SAFETY-ZONES HYDRA-UMC-VISUAL-SERVOING-API; do
  if [[ -f "$ROOT/$child/hydra-umc.project.json" ]]; then
    install -d -o root -g root -m 0755 "$TARGET/workspace/$child"
    install -m 0644 "$ROOT/$child/hydra-umc.project.json" "$TARGET/workspace/$child/hydra-umc.project.json"
  fi
done
install -m 0644 "$SOURCE/systemd/hydra-umc-vision-node.service" /etc/systemd/system/hydra-umc-vision-node.service
systemctl daemon-reload
echo "Vision-Node installed. Enable manually after review: systemctl enable --now hydra-umc-vision-node"
