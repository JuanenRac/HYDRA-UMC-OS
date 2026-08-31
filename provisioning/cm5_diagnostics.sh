#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - Read-only CM5 hardware diagnostics collection
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
set -euo pipefail
echo " ==============================================================="
echo "  HYDRA-UMC-OS - cm5_diagnostics.sh"
echo "  Collects read-only CM5, PCIe, storage, thermal and network data."
echo "  Copyright (C) 2026 JuanenRac (Electro Hobby 3D)"
echo "  <electrohobby3d@gmail.com> | GPL-3.0-or-later - see LICENSE"
echo " ==============================================================="
echo '--- OS ---'; cat /etc/os-release; uname -a
echo '--- storage ---'; df -h /; lsblk
echo '--- thermal ---'; cat /sys/class/thermal/thermal_zone*/temp 2>/dev/null || true
echo '--- network ---'; ip -brief address
echo '--- PCIe ---'; lspci -nn 2>/dev/null || true
echo '--- Hailo ---'; command -v hailortcli >/dev/null && hailortcli fw-control identify || true
echo '--- services ---'; systemctl --no-pager --full status hydra-umc-agent hydra-umc-server 2>/dev/null || true
