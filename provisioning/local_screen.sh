#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - Which local screen the CM5 drives: hdmi | dsi | none
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Sourced by provisioning/install_kiosk.sh of HYDRA-UMC-OS and by
# kiosk/install_kiosk.sh of HYDRA-UMC-DSI, which each keep an identical copy of
# this file. It is never run on its own.
#
# The HDMI kiosk (X11 + Chromium) and the DSI app (cage + Flutter) both want
# tty1 and the seat of the console, so only one of them may be installed and
# enabled at a time. The choice is one setting:
#
#   HYDRA_LOCAL_SCREEN=hdmi   the HDMI kiosk of this repository (the default)
#   HYDRA_LOCAL_SCREEN=dsi    the app of HYDRA-UMC-DSI on the DSI touch screen
#   HYDRA_LOCAL_SCREEN=none   no local screen: neither of them takes tty1
#
# Where it is read from, first one wins: the environment variable
# HYDRA_LOCAL_SCREEN (this run only), then the line HYDRA_LOCAL_SCREEN=<value>
# of /etc/hydra-umc/local-screen.conf (HYDRA_LOCAL_SCREEN_FILE names another
# file), then hdmi. A value that is none of the three is an error, never a
# guess: nothing is installed.
#
# HONESTY NOTE: written and tested against stubs only; it has not run on a CM5.

HYDRA_LOCAL_SCREEN_FILE="${HYDRA_LOCAL_SCREEN_FILE:-/etc/hydra-umc/local-screen.conf}"

local_screen_valid() {
  case "$1" in
    hdmi | dsi | none) return 0 ;;
    *) return 1 ;;
  esac
}

# Prints the screen that is chosen; returns 2 (and prints nothing) for a value that is not valid.
local_screen_read() {
  local value="${HYDRA_LOCAL_SCREEN:-}"
  if [[ -z "$value" && -r "$HYDRA_LOCAL_SCREEN_FILE" ]]; then
    value="$(sed -n 's/^HYDRA_LOCAL_SCREEN=//p' "$HYDRA_LOCAL_SCREEN_FILE" | tail -n 1 | tr -d '[:space:]"')"
  fi
  value="${value:-hdmi}"
  value="${value,,}"
  if ! local_screen_valid "$value"; then
    echo "HYDRA_LOCAL_SCREEN must be hdmi, dsi or none (got '$value')." >&2
    return 2
  fi
  printf '%s\n' "$value"
}

# Writes the choice so the next run, and the DSI unit, read the same value.
local_screen_write() {
  local value="$1" dir
  local_screen_valid "$value" || { echo "HYDRA_LOCAL_SCREEN must be hdmi, dsi or none (got '$value')." >&2; return 2; }
  dir="$(dirname "$HYDRA_LOCAL_SCREEN_FILE")"
  install -d -m 0755 "$dir"
  printf '# Which local screen the CM5 drives: hdmi | dsi | none (see local_screen.sh)\nHYDRA_LOCAL_SCREEN=%s\n' "$value" > "$HYDRA_LOCAL_SCREEN_FILE.tmp"
  chmod 0644 "$HYDRA_LOCAL_SCREEN_FILE.tmp"
  mv "$HYDRA_LOCAL_SCREEN_FILE.tmp" "$HYDRA_LOCAL_SCREEN_FILE"
}
