#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - Reversible Raspberry Pi OS first-boot provisioning
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
set -euo pipefail

APPLY=false
[[ "${1:-}" == "--apply" ]] && APPLY=true
[[ $EUID -eq 0 ]] || { echo "Run as root with sudo." >&2; exit 2; }

run() {
  if $APPLY; then
    "$@"
  else
    printf '[dry-run] '
    printf '%q ' "$@"
    printf '\n'
  fi
}

HOSTNAME="${HYDRA_UMC_HOSTNAME:-hydra-umc-test}"
ADMIN_USER="${HYDRA_UMC_ADMIN_USER:-hydra-umc}"
SERVICE_USER="hydra-umc-agent"
echo "HYDRA-UMC-OS first boot: hostname=$HOSTNAME admin=$ADMIN_USER mode=$($APPLY && echo apply || echo dry-run)"

run apt-get update
run apt-get install -y --no-install-recommends python3 python3-venv ca-certificates
run hostnamectl set-hostname "$HOSTNAME"

# Real bug found live pairing a Bluetooth gamepad directly to a CM5:
# BlueZ's own default ClassicBondedOnly=true (profiles/input/device.c)
# refuses the HID connection for any device that bonds over LE rather
# than classic BR/EDR on this hardware (Raspberry Pi's own BCM4345C0),
# even after `bluetoothctl pair`/`trust` genuinely succeed - the device
# is left stuck at Paired=yes/Bonded=no forever, and never shows up as a
# real /dev/input js*/event* device. See
# HYDRA-UMC-SERVER's own POST /api/system/bluetooth/pair (Config >
# Bluetooth in STUDIO) for the real pairing flow this setting unblocks.
if [[ -f /etc/bluetooth/input.conf ]]; then
  if $APPLY; then
    cp -n /etc/bluetooth/input.conf /etc/bluetooth/input.conf.orig 2>/dev/null || true
    if grep -q '^ClassicBondedOnly=' /etc/bluetooth/input.conf; then
      sed -i 's/^ClassicBondedOnly=.*/ClassicBondedOnly=false/' /etc/bluetooth/input.conf
    elif grep -q '^#ClassicBondedOnly=true' /etc/bluetooth/input.conf; then
      sed -i 's/^#ClassicBondedOnly=true/ClassicBondedOnly=false/' /etc/bluetooth/input.conf
    else
      printf '\nClassicBondedOnly=false\n' >> /etc/bluetooth/input.conf
    fi
    systemctl restart bluetooth 2>/dev/null || true
  else
    echo "[dry-run] set ClassicBondedOnly=false in /etc/bluetooth/input.conf, restart bluetooth"
  fi
fi
if $APPLY && ! id -u "$ADMIN_USER" >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash --groups sudo "$ADMIN_USER"
elif ! $APPLY; then
  printf '[dry-run] create administrator %s if absent\n' "$ADMIN_USER"
fi
if $APPLY && ! id -u "$SERVICE_USER" >/dev/null 2>&1; then
  useradd --system --home /var/lib/hydra-umc --create-home --shell /usr/sbin/nologin "$SERVICE_USER"
elif ! $APPLY; then
  printf '[dry-run] create service account %s if absent\n' "$SERVICE_USER"
fi
# Configuration may later contain service credentials, so it stays owned by
# root. The restricted service account only owns its mutable runtime state.
run install -d -o root -g "$SERVICE_USER" -m 0750 /etc/hydra-umc
run install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0750 /var/lib/hydra-umc
run install -d -o root -g root -m 0755 /opt/hydra-umc

echo "Provisioning base complete. Install the signed HYDRA-UMC-OS package next."
echo "Set the $ADMIN_USER password locally with passwd; do not place it in scripts or Git."
echo "SSH policy: use authorized keys; disable PasswordAuthentication only after key login succeeds."
