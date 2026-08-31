#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - WiFi first-contact provisioning installer
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Installs provisioning/wifi_provision.py to /opt/hydra-umc/wifi-provision/
# (same real install-root convention as install_local_agent.sh's own
# /opt/hydra-umc/os-agent) and the hydra-umc-wifi-provision.service unit.
# Does NOT enable/start it - same "review config, then enable manually"
# posture install_local_agent.sh already uses, doubly warranted here
# since this unit can bring up a real, over-the-air-reachable access
# point with the module's own placeholder password unless
# /etc/hydra-umc/wifi-provision.env is created first (see below).
set -euo pipefail

APPLY=false
[[ "${1:-}" == "--apply" ]] && APPLY=true
[[ $EUID -eq 0 ]] || { echo "Run as root with sudo." >&2; exit 2; }
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET=/opt/hydra-umc/wifi-provision

run() { if $APPLY; then "$@"; else printf '[dry-run] '; printf '%q ' "$@"; printf '\n'; fi; }

run install -d -o root -g root -m 0755 "$TARGET"
run install -m 0755 "$ROOT/provisioning/wifi_provision.py" "$TARGET/wifi_provision.py"
run python3 "$ROOT/provisioning/rollback.py" backup /etc/systemd/system/hydra-umc-wifi-provision.service \
  --backup-dir /var/lib/hydra-umc/rollback --manifest /var/lib/hydra-umc/rollback/manifest.json
run install -m 0644 "$ROOT/systemd/hydra-umc-wifi-provision.service" /etc/systemd/system/hydra-umc-wifi-provision.service
run systemctl daemon-reload

echo "WiFi provisioning installed."
echo "Before enabling it for real, set a real AP password:"
echo "  install -m 0600 -o root -g root /dev/null /etc/hydra-umc/wifi-provision.env"
echo "  echo 'HYDRA_UMC_AP_PASSWORD=<a real, per-device password>' >> /etc/hydra-umc/wifi-provision.env"
echo "Then: systemctl enable --now hydra-umc-wifi-provision"
