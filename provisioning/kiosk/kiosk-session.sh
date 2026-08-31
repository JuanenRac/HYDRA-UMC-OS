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

# install_kiosk.sh masks systemd's own automatic plymouth-quit*.service so
# the Plymouth splash stays up through this device's ENTIRE boot (agent,
# Server, networking - all of it) instead of just its first few seconds -
# see that script's own comment. This is the manual hand-off point: X is
# already up at this point (startx ran it before this script), so quitting
# Plymouth now hands the display straight to X, with only the brief real
# gap until Chromium itself paints (never a scrolling text console).
# "|| true": never let a kiosk boot fail outright just because plymouthd
# already exited on its own (e.g. this script re-run manually for testing,
# with no active Plymouth session to quit).
sudo plymouth quit || true

openbox-session &
sleep 1

# Real, live-diagnosed bug: with no compositing manager, Chromium's own
# GPU process (an X client, via the Present extension) and X itself raced
# directly over CRTC page-flips - Xorg.0.log showed thousands of repeated
# "Present-flip: queue flip during flip on CRTC 2 failed: Invalid
# argument" lines, and the screen simply stopped receiving new frames
# even though every process (Xorg, Chromium, openbox) stayed alive. Two
# xf86-video-modesetting driver options were tried first (see
# install_kiosk.sh's own comment) and neither fixed it - only giving X an
# actual compositor did: picom now arbitrates the same Present requests
# instead of leaving them to race the CRTC directly. Live-verified: 0
# Present-flip errors in Xorg.0.log after adding this, versus ~2900
# before, across an otherwise-identical reboot. --backend xrender (not
# glx) - the simpler, more compatible backend; this kiosk has exactly one
# fullscreen window and never needs picom's fancier compositing effects.
picom --backend xrender --vsync &
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
