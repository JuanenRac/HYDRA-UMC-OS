#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - Install HYDRA-UMC-SERVER as the CM5 local dashboard
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
set -euo pipefail
[[ "${1:-}" == "--apply" ]] || { echo "Dry-run policy: rerun with --apply after review."; exit 0; }
[[ $EUID -eq 0 ]] || { echo "Run as root with sudo." >&2; exit 2; }
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; SOURCE="$ROOT/HYDRA-UMC-SERVER"; TARGET=/opt/hydra-umc/server
[[ -f /etc/hydra-umc/server.env ]] || { echo "Create /etc/hydra-umc/server.env from provisioning/server.env.example first." >&2; exit 2; }
install -d -o hydra_umc -g hydra_umc "$TARGET" "$TARGET/data"
cp -a "$SOURCE/dist" "$SOURCE/public" "$SOURCE/package.json" "$SOURCE/package-lock.json" "$TARGET/"
cd "$TARGET"; npm ci --omit=dev
install -m 0644 "$SOURCE/systemd/hydra-umc-server.service" /etc/systemd/system/hydra-umc-server.service
systemctl daemon-reload
echo "Server installed. Enable manually after review: systemctl enable --now hydra-umc-server"
