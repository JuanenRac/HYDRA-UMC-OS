#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - Install the HDMI kiosk: animated splash, then STUDIO fullscreen
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Plymouth (install_splashscreen.sh) cannot play this project's real splash
# animation - it only renders static raster frames or its own tiny scripting
# language, never inline SVG/CSS/SMIL. HYDRA_UMC_SPLASHSCREEN.svg's motion
# (its own <animate>/<animateTransform> elements and @keyframes) only plays
# back faithfully inside a real browser engine. So this script boots a
# minimal X11 session running exactly one thing - Chromium in kiosk mode -
# that shows the actual SVG file first (untouched, not re-implemented) and
# then hands off to HYDRA-UMC-SERVER's own STUDIO UI once it responds, both
# in the same fullscreen window. Deliberately not the future hmi_qt6 native
# path (see HYDRA-UMC/src/cm5_host/hmi_qt6) - that needs its own Qt6
# validation gate; this is the real, working HDMI-out kiosk in the meantime.
set -euo pipefail
APPLY=false
[[ "${1:-}" == "--apply" ]] && APPLY=true
[[ $EUID -eq 0 ]] || { echo "Run as root with sudo." >&2; exit 2; }
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KIOSK_USER="${SUDO_USER:-hydra-umc}"
KIOSK_HOME="$(getent passwd "$KIOSK_USER" | cut -d: -f6)"
[[ -n "$KIOSK_HOME" && -d "$KIOSK_HOME" ]] || { echo "Cannot resolve a home directory for $KIOSK_USER" >&2; exit 2; }
STUDIO_URL="${HYDRA_UMC_STUDIO_URL:-http://localhost:3000/}"
KIOSK_DIR=/opt/hydra-umc/kiosk
BOOT_CONFIG=/boot/firmware/config.txt
run() { if $APPLY; then "$@"; else printf '[dry-run] '; printf '%q ' "$@"; printf '\n'; fi; }

echo " ==============================================================="
echo "  HYDRA-UMC-OS - install_kiosk.sh"
echo "  HDMI kiosk: HYDRA_UMC_SPLASHSCREEN.svg, then STUDIO fullscreen."
echo "  Copyright (C) 2026 JuanenRac (Electro Hobby 3D)"
echo "  <electrohobby3d@gmail.com> | GPL-3.0-or-later - see LICENSE"
echo " ==============================================================="
echo "kiosk user: $KIOSK_USER   studio url: $STUDIO_URL"

run apt-get update
run apt-get install -y --no-install-recommends \
  xserver-xorg x11-xserver-utils xinit openbox chromium unclutter

# GPU memory split: harmless to set, but real testing on this device showed
# it is not the relevant knob here - this image already ships
# dtoverlay=vc4-kms-v3d (full KMS), which sources GPU memory from a CMA
# reservation rather than the legacy VideoCore split gpu_mem= controls, so
# vcgencmd get_mem gpu staying low is expected and not a problem by itself.
# Idempotent: only appends if no gpu_mem line exists yet, never edits an
# operator's own existing value.
if $APPLY; then
  if [[ -f "$BOOT_CONFIG" ]] && ! grep -q '^gpu_mem=' "$BOOT_CONFIG"; then
    printf '\n# HYDRA-UMC-OS kiosk: GPU memory for the Chromium kiosk session\ngpu_mem=128\n' >> "$BOOT_CONFIG"
    echo "gpu_mem=128 appended to $BOOT_CONFIG (takes effect on next reboot)"
  fi
else
  echo "[dry-run] append gpu_mem=128 to $BOOT_CONFIG unless a gpu_mem= line already exists"
fi

# Real bugs found live on this device's first boot into the kiosk, in order:
# (1) with both the modern KMS "modesetting" driver and the legacy "fbdev"
# driver available (xserver-xorg-video-all, pulled in by the xserver-xorg
# metapackage), X's driver auto-probe tried fbdev after modesetting and
# died with "Cannot run in framebuffer mode. Please specify busIDs for all
# framebuffer devices". (2) pinning bare "Driver modesetting" alone still
# failed with "No devices detected"/"no screens found" even with a real
# monitor confirmed connected (/sys/class/drm/card1-HDMI-A-1/status ==
# connected): the CM5 exposes 2 DRM nodes under vc4-kms-v3d - card0 is
# v3d (3D/compute only, no display output) and card1 is vc4 (the real
# display controller) - and modesetting's own autodetection did not
# reliably resolve to card1 on its own. Pinning kmsdev explicitly is the
# documented fix for this dual-node situation.
run install -d -m 0755 /etc/X11/xorg.conf.d
if $APPLY; then
  cat > /etc/X11/xorg.conf.d/20-hydra-umc-modesetting.conf <<'EOF'
Section "Device"
    Identifier "HYDRA-UMC-KMS"
    Driver "modesetting"
    Option "kmsdev" "/dev/dri/card1"
EndSection
EOF
else
  echo "[dry-run] write /etc/X11/xorg.conf.d/20-hydra-umc-modesetting.conf (pin Driver \"modesetting\", kmsdev /dev/dri/card1)"
fi

run install -d -o root -g root -m 0755 "$KIOSK_DIR"
run install -m 0644 "$ROOT/images/HYDRA_UMC_SPLASHSCREEN.svg" "$KIOSK_DIR/HYDRA_UMC_SPLASHSCREEN.svg"
run install -m 0644 "$ROOT/provisioning/kiosk/splash.html" "$KIOSK_DIR/splash.html"
run install -m 0755 "$ROOT/provisioning/kiosk/kiosk-session.sh" "$KIOSK_DIR/kiosk-session.sh"

# Autologin on the physical console (tty1) - the standard, minimal way to
# reach a graphical kiosk session on a Lite install with no display manager.
run install -d -m 0755 /etc/systemd/system/getty@tty1.service.d
if $APPLY; then
  cat > /etc/systemd/system/getty@tty1.service.d/hydra-umc-autologin.conf <<EOF
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin $KIOSK_USER --noclear %I \$TERM
EOF
else
  echo "[dry-run] write /etc/systemd/system/getty@tty1.service.d/hydra-umc-autologin.conf (autologin: $KIOSK_USER)"
fi
run systemctl daemon-reload

# .bash_profile starts X only for an interactive login on the physical
# console (tty1), never for an SSH session - an SSH login has no controlling
# tty1 and $DISPLAY stays unset there, so this never fights an
# administrator's own SSH work on the same account.
PROFILE_LINE='[ -z "$DISPLAY" ] && [ "$(tty)" = "/dev/tty1" ] && exec startx /opt/hydra-umc/kiosk/kiosk-session.sh -- -nocursor'
if $APPLY; then
  touch "$KIOSK_HOME/.bash_profile"
  grep -qxF "$PROFILE_LINE" "$KIOSK_HOME/.bash_profile" || echo "$PROFILE_LINE" >> "$KIOSK_HOME/.bash_profile"
  chown "$KIOSK_USER":"$KIOSK_USER" "$KIOSK_HOME/.bash_profile"
else
  echo "[dry-run] ensure $KIOSK_HOME/.bash_profile starts the kiosk session on tty1 only"
fi

echo "Kiosk installed. Reboot to see it on HDMI, or on this console: sudo systemctl restart getty@tty1"
echo "Splash source stays HYDRA_UMC_SPLASHSCREEN.svg unmodified; edit provisioning/kiosk/splash.html to change hand-off timing."
