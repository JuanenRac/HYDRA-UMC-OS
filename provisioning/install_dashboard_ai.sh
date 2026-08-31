#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - Install HYDRA-UMC-DASHBOARD-AI as a local CM5 static SPA
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Real gap found auditing the ecosystem against actual CM5 hardware:
# HYDRA-UMC-DASHBOARD-AI builds a real, deployable static SPA (`npm run
# build` -> dist/), but nothing on the CM5 ever served it. Own port/
# service (scripts/serve_static.py, new, that repo - real stdlib
# ThreadingHTTPServer, no Node runtime needed at serve time), NOT folded
# into HYDRA-UMC-SERVER's own public/ the way HYDRA-UMC-STUDIO is - this
# dashboard already talks straight to HYDRA-UMC-DATALAKE/
# HYDRA-UMC-ANOMALY-DETECTOR by their own configured base URLs, so it
# never needed SERVER's own backend, and two independent SPAs sharing
# one origin risks route/asset collisions.
set -euo pipefail
[[ "${1:-}" == "--apply" ]] || { echo "Dry-run policy: rerun with --apply after review."; exit 0; }
[[ $EUID -eq 0 ]] || { echo "Run as root with sudo." >&2; exit 2; }

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SOURCE="$ROOT/HYDRA-UMC-DASHBOARD-AI"
TARGET=/opt/hydra-umc/dashboard-ai
DASH_USER="hydra-umc-dashboard-ai"

echo " ==============================================================="
echo "  HYDRA-UMC-OS - install_dashboard_ai.sh"
echo "  Builds and installs the real static SPA (own port, Python"
echo "  stdlib server - no Node runtime needed once built)."
echo "  Copyright (C) 2026 JuanenRac (Electro Hobby 3D)"
echo "  <electrohobby3d@gmail.com> | GPL-3.0-or-later - see LICENSE"
echo " ==============================================================="

[[ -f "$SOURCE/package.json" && -f "$SOURCE/scripts/serve_static.py" && -f "$SOURCE/systemd/hydra-umc-dashboard-ai.service" ]] || {
  echo "HYDRA-UMC-DASHBOARD-AI source or systemd unit is incomplete: $SOURCE" >&2; exit 2;
}
command -v node >/dev/null || { echo "HYDRA-UMC-DASHBOARD-AI requires Node.js (build-time only)." >&2; exit 2; }
command -v npm >/dev/null || { echo "HYDRA-UMC-DASHBOARD-AI requires npm (build-time only)." >&2; exit 2; }
command -v python3 >/dev/null || { echo "HYDRA-UMC-DASHBOARD-AI's real static server needs python3." >&2; exit 2; }

if ! id -u "$DASH_USER" >/dev/null 2>&1; then
  useradd --system --home "$TARGET" --no-create-home --shell /usr/sbin/nologin "$DASH_USER"
fi

( cd "$SOURCE" && npm ci && npm run build )

install -d -o root -g root -m 0755 "$TARGET"
rm -rf "$TARGET/dist"
cp -a "$SOURCE/dist" "$TARGET/dist"
install -m 0644 "$SOURCE/scripts/serve_static.py" "$TARGET/serve_static.py"
chown -R root:root "$TARGET/dist" "$TARGET/serve_static.py"
chmod -R go-w "$TARGET/dist"

install -m 0644 "$SOURCE/systemd/hydra-umc-dashboard-ai.service" /etc/systemd/system/hydra-umc-dashboard-ai.service
systemctl daemon-reload
echo "Dashboard-AI installed. Enable manually after review: systemctl enable --now hydra-umc-dashboard-ai"
