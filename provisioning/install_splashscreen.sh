#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - Install reversible Plymouth splash screen
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
set -euo pipefail
APPLY=false
[[ "${1:-}" == "--apply" ]] && APPLY=true
[[ $EUID -eq 0 ]] || { echo "Run as root with sudo." >&2; exit 2; }
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; THEME=/usr/share/plymouth/themes/hydra-umc-os
run() { if $APPLY; then "$@"; else printf '[dry-run] '; printf '%q ' "$@"; printf '\n'; fi; }
run apt-get update
run apt-get install -y --no-install-recommends plymouth librsvg2-bin
run install -d "$THEME"
run rsvg-convert --width 1920 --height 1080 "$ROOT/images/HYDRA_UMC_SPLASHSCREEN.svg" -o "$THEME/splash.png"
run install -m 0644 "$ROOT/provisioning/plymouth/hydra-umc-os.plymouth" "$THEME/hydra-umc-os.plymouth"
run install -m 0644 "$ROOT/provisioning/plymouth/hydra-umc-os.script" "$THEME/hydra-umc-os.script"
run plymouth-set-default-theme -R hydra-umc-os
echo "Splash installed. Verify one reboot before changing further boot settings."
