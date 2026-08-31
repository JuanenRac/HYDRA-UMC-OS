#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - Staged CM5 BASE and local-control installer
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Runs the reviewed installation order. By default it is a dry run; --apply is
# required for any state change and --enable-services is separately explicit.
set -euo pipefail

APPLY=false
WITH_SERVER=false
WITH_VOICE_UI=false
ENABLE_SERVICES=false
for argument in "$@"; do
  case "$argument" in
    --apply) APPLY=true ;;
    --with-server) WITH_SERVER=true ;;
    --with-voice-ui) WITH_VOICE_UI=true ;;
    --enable-services) ENABLE_SERVICES=true ;;
    *) echo "Usage: $0 [--apply] [--with-server] [--with-voice-ui] [--enable-services]" >&2; exit 2 ;;
  esac
done
if $ENABLE_SERVICES && ! $APPLY; then
  echo "--enable-services requires --apply." >&2
  exit 2
fi
if $WITH_VOICE_UI && ! $WITH_SERVER; then
  echo "--with-voice-ui requires --with-server so Server owns the Voice UI token boundary." >&2
  exit 2
fi
[[ $EUID -eq 0 ]] || { echo "Run as root with sudo." >&2; exit 2; }

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
echo " ==============================================================="
echo "  HYDRA-UMC-OS - install_cm5_base.sh"
echo "  Staged BASE installer; Server and service activation are opt-in."
echo "  Copyright (C) 2026 JuanenRac (Electro Hobby 3D)"
echo "  <electrohobby3d@gmail.com> | GPL-3.0-or-later - see LICENSE"
echo " ==============================================================="

python3 provisioning/preflight_cm5.py
if $APPLY; then
  provisioning/first_boot.sh --apply
  provisioning/install_local_agent.sh --apply
  provisioning/install_wifi_provision.sh --apply
  if $WITH_SERVER; then
    provisioning/install_server.sh --apply
  fi
  if $WITH_VOICE_UI; then
    provisioning/install_voice_ui.sh --apply
  fi
  if $ENABLE_SERVICES; then
    systemctl enable --now hydra-umc-agent
    # WiFi provisioning is deliberately NOT auto-enabled even under
    # --enable-services - see install_wifi_provision.sh's own note: it
    # must not start with the module's own placeholder AP password on a
    # real, over-the-air-reachable device. Set
    # /etc/hydra-umc/wifi-provision.env first, then enable it by hand.
    # The bounded Voice UI gateway must be ready before Server accepts
    # authenticated Watch/phone voice turns that it relays locally.
    $WITH_VOICE_UI && systemctl enable --now hydra-umc-voice-ui
    $WITH_SERVER && systemctl enable --now hydra-umc-server
  fi
  echo "Installation complete. Run provisioning/verify_cm5_runtime.sh$($WITH_SERVER && printf ' --with-server')$($WITH_VOICE_UI && printf ' --with-voice-ui') next."
else
  provisioning/first_boot.sh
  provisioning/install_local_agent.sh
  provisioning/install_wifi_provision.sh
  $WITH_SERVER && provisioning/install_server.sh
  $WITH_VOICE_UI && provisioning/install_voice_ui.sh
  echo "Dry run complete. Re-run with --apply only after reviewing every command."
fi
