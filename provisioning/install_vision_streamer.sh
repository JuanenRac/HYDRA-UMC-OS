#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - Install HYDRA-UMC-VISION-STREAMER as the CM5 camera capture
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Closes the real gap left after wiring HYDRA-UMC-SERVER's camera-stream
# proxy and HYDRA-UMC-STUDIO's live <img> rendering: neither of those makes
# a USB camera show up in the robot A1 view by itself - something on the
# CM5 still has to actually run `hydra-umc-vision-streamer stream serve`
# against a real /dev/videoN. This installs that piece: a templated
# systemd unit (one instance per admin-assigned camera slot, 1-8) plus the
# real python3-opencv apt package that module's own mjpeg_server.py lazily
# imports (see that repo's own pyproject.toml comment for why apt, not pip
# - no source build on ARM64, matches python3-numpy's precedent here).
#
# This installs the CAPABILITY only - it does not itself enable any camera
# slot, because that needs a person to decide which physical /dev/videoN
# is which slot (see systemd/cameras.env.example in that repo for the
# real reason an automatic guess isn't attempted). Follow the printed
# instructions at the end to enable a slot once a camera is connected.
set -euo pipefail
[[ "${1:-}" == "--apply" ]] || { echo "Dry-run policy: rerun with --apply after review."; exit 0; }
[[ $EUID -eq 0 ]] || { echo "Run as root with sudo." >&2; exit 2; }

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SOURCE="$ROOT/HYDRA-UMC-VISION-STREAMER"
TARGET=/opt/hydra-umc/vision-streamer
STREAMER_USER="hydra-umc-vision-streamer"

echo " ==============================================================="
echo "  HYDRA-UMC-OS - install_vision_streamer.sh"
echo "  Installs the real OpenCV-backed MJPEG camera capture+serve"
echo "  (Server's own GET /api/camera/:id/stream proxy target)."
echo "  Copyright (C) 2026 JuanenRac (Electro Hobby 3D)"
echo "  <electrohobby3d@gmail.com> | GPL-3.0-or-later - see LICENSE"
echo " ==============================================================="

[[ -d "$SOURCE/src/hydra_umc_vision_streamer" && -f "$SOURCE/systemd/hydra-umc-vision-streamer@.service" ]] || {
  echo "HYDRA-UMC-VISION-STREAMER source or systemd unit is incomplete: $SOURCE" >&2; exit 2;
}
command -v python3 >/dev/null || { echo "HYDRA-UMC-VISION-STREAMER requires python3." >&2; exit 2; }

apt-get update
apt-get install -y python3-opencv v4l-utils

if ! id -u "$STREAMER_USER" >/dev/null 2>&1; then
  useradd --system --home "$TARGET" --no-create-home --shell /usr/sbin/nologin "$STREAMER_USER"
fi
install -d -o root -g root -m 0755 "$TARGET"
rm -rf "$TARGET/src"
cp -a "$SOURCE/src" "$TARGET/"
chown -R root:root "$TARGET/src"
chmod -R go-w "$TARGET/src"
install -d -o root -g root -m 0755 /etc/hydra-umc/cameras
install -m 0644 "$SOURCE/systemd/hydra-umc-vision-streamer@.service" /etc/systemd/system/hydra-umc-vision-streamer@.service
systemctl daemon-reload

echo "Vision-Streamer capability installed (no camera slot enabled yet)."
echo "To bring up a physical USB camera as slot N (1-8, matching the cameraId"
echo "already assigned to it in HYDRA-UMC-STUDIO's admin panel):"
echo "  v4l2-ctl --list-devices                 # find its real /dev/videoN"
echo "  install -d /etc/hydra-umc/cameras"
echo "  cp $SOURCE/systemd/cameras.env.example /etc/hydra-umc/cameras/N.env"
echo "  \$EDITOR /etc/hydra-umc/cameras/N.env     # set DEVICE=/dev/videoN"
echo "  systemctl enable --now hydra-umc-vision-streamer@N"
