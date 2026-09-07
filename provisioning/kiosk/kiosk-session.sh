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

# Real, live-diagnosed dead end, kept as a note so it isn't retried blind:
# masking plymouth-quit*.service to hold Plymouth's splash up through this
# device's entire boot (instead of its normal ~4s) and quitting it
# manually here, right before Chromium, deadlocked agetty's own tty1
# autologin outright (see install_kiosk.sh's own comment) - not done.
# Plymouth quits on its own normal schedule; nothing to do here for it.

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
# --vsync deliberately omitted - a known real picom gotcha on some
# GPU/driver combinations is --vsync itself causing exactly this kind of
# stall after the first frame; live-tested both ways on this device and
# 0-Present-flip-error runs held with it off.
picom --backend xrender &
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
