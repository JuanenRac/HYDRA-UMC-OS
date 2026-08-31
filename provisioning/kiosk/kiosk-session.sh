#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - Kiosk X session: one fullscreen Chromium, nothing else
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Run as the X session command by startx (see install_kiosk.sh's
# .bash_profile line): "startx /opt/hydra-umc/kiosk/kiosk-session.sh -- ...".
# Openbox is only here to give Chromium a window manager to reparent into -
# no panel, no desktop, no decorations are ever shown.
set -euo pipefail

xset s off
xset -dpms
xset s noblank

openbox-session &
sleep 1

unclutter --timeout 1 --jitter 5 --ignore-scroll &

CHROMIUM_PROFILE="$HOME/.config/hydra-umc-kiosk-chromium"
mkdir -p "$CHROMIUM_PROFILE"

# --kiosk implies fullscreen with no window chrome. The rest silences the
# dialogs/infobars a fresh Chromium profile would otherwise show on a
# device nobody is present to click through (crash-restore bubble, "set as
# default browser", translate prompts). --user-data-dir is a real,
# dedicated profile so a logged-in STUDIO session (its JWT lives in
# localStorage, see store.tsx) survives across reboots exactly like a
# normal browser tab would, without touching any other account's profile.
exec chromium \
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
