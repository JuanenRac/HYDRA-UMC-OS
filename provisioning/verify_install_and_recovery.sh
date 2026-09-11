#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - provisioning/verify_install_and_recovery.sh
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Real, --apply-mode verification of install_cm5_base.sh and
# cm5_recovery.sh - closes a real gap found while auditing the code:
# CI only ever ran `bash -n` (syntax-only) against these scripts, and a
# real --apply run + a real backup/wipe/restore cycle had never been
# exercised anywhere except by hand, directly on a real CM5. This script
# is that missing real exercise, safe to run on any real, disposable
# systemd-based Debian/Ubuntu machine (a GitHub Actions ubuntu-latest
# runner, or a real WSL Ubuntu distro a developer is fine mutating) -
# NEVER on a real, in-use CM5 or workstation, since it genuinely creates
# real system users/directories/systemd units.
#
# Requires: root (sudo), systemd, and HYDRA-UMC-SDK checked out as a real
# sibling directory (../HYDRA-UMC-SDK relative to this repo's own root) -
# the same convention preflight_cm5.py's own SDK_OS_CONTRACT check
# already requires for a real, non-degraded pass.
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "Run as root with sudo." >&2; exit 2; }

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo " ==============================================================="
echo "  HYDRA-UMC-OS - verify_install_and_recovery.sh"
echo "  Real --apply install + a real backup/wipe/restore cycle."
echo " ==============================================================="

echo "[1/4] Real install (install_cm5_base.sh --apply)"
bash provisioning/install_cm5_base.sh --apply

echo "[2/4] Verifying the real state install_cm5_base.sh claims to create"
id hydra-umc-agent >/dev/null 2>&1 || { echo "VERIFY_INSTALL=FAIL: hydra-umc-agent user was not created" >&2; exit 1; }
[[ -d /etc/hydra-umc ]] || { echo "VERIFY_INSTALL=FAIL: /etc/hydra-umc was not created" >&2; exit 1; }
[[ -d /var/lib/hydra-umc ]] || { echo "VERIFY_INSTALL=FAIL: /var/lib/hydra-umc was not created" >&2; exit 1; }
[[ -d /opt/hydra-umc ]] || { echo "VERIFY_INSTALL=FAIL: /opt/hydra-umc was not created" >&2; exit 1; }
[[ -f /etc/systemd/system/hydra-umc-agent.service ]] || { echo "VERIFY_INSTALL=FAIL: hydra-umc-agent.service was not installed" >&2; exit 1; }
# Real, current hostnamectl state - not left at whatever the base image
# happened to have before this ran.
[[ "$(hostname)" == "hydra-umc-test" || "$(cat /etc/hostname 2>/dev/null || true)" == "hydra-umc-test" ]] \
  || { echo "VERIFY_INSTALL=FAIL: hostname was not really set to hydra-umc-test" >&2; exit 1; }
echo "VERIFY_INSTALL=PASS"

echo "[3/4] Real backup/wipe/restore cycle (cm5_recovery.sh --apply)"
MARKER_CONTENT="hydra-umc-os-real-recovery-verification-$$"
echo "$MARKER_CONTENT" > /etc/hydra-umc/verify-marker.txt
ARCHIVE="$(mktemp -u /tmp/hydra-umc-recovery-verify-XXXXXX.tar.gz)"
bash provisioning/cm5_recovery.sh backup "$ARCHIVE" --apply
rm -rf /etc/hydra-umc /var/lib/hydra-umc
[[ ! -e /etc/hydra-umc ]] || { echo "VERIFY_RECOVERY=FAIL: /etc/hydra-umc survived the real wipe" >&2; exit 1; }
bash provisioning/cm5_recovery.sh restore "$ARCHIVE" --apply

echo "[4/4] Verifying the real restored state matches what was backed up"
[[ -f /etc/hydra-umc/verify-marker.txt ]] || { echo "VERIFY_RECOVERY=FAIL: verify-marker.txt did not survive restore" >&2; exit 1; }
RESTORED_CONTENT="$(cat /etc/hydra-umc/verify-marker.txt)"
[[ "$RESTORED_CONTENT" == "$MARKER_CONTENT" ]] || {
  echo "VERIFY_RECOVERY=FAIL: restored content ($RESTORED_CONTENT) != backed-up content ($MARKER_CONTENT)" >&2
  exit 1
}
# --numeric-owner in cm5_recovery.sh's own backup/restore must round-trip
# real ownership too, not just file content.
[[ "$(stat -c '%U:%G' /etc/hydra-umc)" == "root:hydra-umc-agent" ]] \
  || { echo "VERIFY_RECOVERY=FAIL: /etc/hydra-umc ownership was not restored correctly" >&2; exit 1; }
rm -f "$ARCHIVE"
echo "VERIFY_RECOVERY=PASS"

echo "CM5_INSTALL_AND_RECOVERY_VERIFICATION=PASS"
