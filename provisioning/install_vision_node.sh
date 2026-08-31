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
# anything but "all missing" - rather than copying those repos a second
# time, /opt/hydra-umc/vision-node/workspace is a symlink to $ROOT, the
# same sibling-checkout root every install_*.sh script in this file
# already resolves. Whichever of the 4 children (VISION-STREAMER,
# DETECTION-HEF, SAFETY-ZONES, VISUAL-SERVOING-API) are actually checked
# out there - some already are, from earlier installs this session -
# show up as present automatically; the rest honestly report NOT FOUND
# until they are.
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
ln -sfn "$ROOT" "$TARGET/workspace"
install -m 0644 "$SOURCE/systemd/hydra-umc-vision-node.service" /etc/systemd/system/hydra-umc-vision-node.service
systemctl daemon-reload
echo "Vision-Node installed. Enable manually after review: systemctl enable --now hydra-umc-vision-node"
