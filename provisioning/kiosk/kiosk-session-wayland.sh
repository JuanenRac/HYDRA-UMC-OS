#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - Kiosk Wayland session: one fullscreen Chromium under cage
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Started by cage as its one program (see install_kiosk.sh --session wayland and the
# .bash_profile line it writes): "cage -- /opt/hydra-umc/kiosk/kiosk-session-wayland.sh".
# cage is the compositor and shows this program fullscreen, so there is no X server,
# no window manager and no compositing manager (the X11 session needs openbox and
# picom for that). It runs as the same locked account as the X11 session.
set -euo pipefail

CHROMIUM_PROFILE="$HOME/.config/hydra-umc-kiosk-chromium"
mkdir -p "$CHROMIUM_PROFILE"

# Same page, same profile and same silenced dialogs as the X11 session; --ozone-platform=wayland makes
# Chromium talk to cage instead of looking for an X server.
exec chromium \
  --ozone-platform=wayland \
  --kiosk "file:///opt/hydra-umc/kiosk/splash.html" \
  --user-data-dir="$CHROMIUM_PROFILE" \
  --noerrdialogs \
  --disable-infobars \
  --no-first-run \
  --disable-session-crashed-bubble \
  --disable-translate \
  --overscroll-history-navigation=0 \
  --check-for-update-interval=31536000 \
  --autoplay-policy=no-user-gesture-required
