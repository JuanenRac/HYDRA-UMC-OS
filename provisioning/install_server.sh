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
# $ROOT above is deliberately the PARENT of this repo (the sibling-repos
# checkout root, so SOURCE can reach HYDRA-UMC-SERVER next to it) - this
# repo's OWN root (for files that live in it, like the polkit rule below)
# is one level down from that, not $ROOT itself. Real bug found live: the
# polkit install line below originally (wrongly) used $ROOT directly.
OS_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERVER_USER="hydra-umc-server"
[[ -d "$SOURCE/dist" && -d "$SOURCE/public" && -f "$SOURCE/package.json" && -f "$SOURCE/package-lock.json" && -f "$SOURCE/systemd/hydra-umc-server.service" ]] || { echo "HYDRA-UMC-SERVER build or service unit is incomplete: $SOURCE" >&2; exit 2; }
[[ -f /etc/hydra-umc/server.env ]] || { echo "Create /etc/hydra-umc/server.env from provisioning/server.env.example first." >&2; exit 2; }
command -v node >/dev/null || { echo "HYDRA-UMC-SERVER requires Node.js 20 or later." >&2; exit 2; }
command -v npm >/dev/null || { echo "HYDRA-UMC-SERVER requires npm from the same supported Node.js installation." >&2; exit 2; }
NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
[[ "$NODE_MAJOR" =~ ^[0-9]+$ && "$NODE_MAJOR" -ge 20 ]] || { echo "HYDRA-UMC-SERVER requires Node.js 20 or later; found $(node --version)." >&2; exit 2; }
if ! id -u "$SERVER_USER" >/dev/null 2>&1; then
  useradd --system --home "$TARGET/data" --create-home --shell /usr/sbin/nologin "$SERVER_USER"
fi
install -d -o root -g root -m 0755 "$TARGET"
install -d -o "$SERVER_USER" -g "$SERVER_USER" -m 0750 "$TARGET/data"
# Real bug found live on this device's first real --with-server install:
# this only ever chmod'd server.env, never chgrp'd it - so an operator
# following the documented flow (create it as root:root, per
# CM5_DEPLOYMENT_SEQUENCE.md's own example commands) ended with
# root:root:640, while verify_cm5_runtime.sh checks for
# root:hydra-umc-server:640 specifically. chgrp only now that
# $SERVER_USER's own group is guaranteed to exist (useradd above).
chown root:"$SERVER_USER" /etc/hydra-umc/server.env
chmod 0640 /etc/hydra-umc/server.env
cp -a "$SOURCE/dist" "$SOURCE/public" "$SOURCE/package.json" "$SOURCE/package-lock.json" "$TARGET/"
cd "$TARGET"; npm ci --omit=dev
install -m 0644 "$SOURCE/systemd/hydra-umc-server.service" /etc/systemd/system/hydra-umc-server.service
# Lets $SERVER_USER (unprivileged, NoNewPrivileges) call systemctl
# reboot/poweroff via systemd-logind's own polkit-gated D-Bus API -
# server.ts's own POST /api/system/reboot and /api/system/shutdown, loop-
# back-only, back the shutdown/restart buttons on STUDIO's pre-login
# screen (AuthGate.tsx). See the rule file's own header comment for the
# exact, narrow scope (only those 2 actions, only this one account).
install -d -m 0755 /etc/polkit-1/rules.d
install -m 0644 "$OS_ROOT/provisioning/polkit/49-hydra-umc-server-power.rules" /etc/polkit-1/rules.d/49-hydra-umc-server-power.rules
# Lets $SERVER_USER start/stop/restart OTHER hydra-umc-*.service units
# via systemd's own polkit-gated D-Bus API - server.ts's own
# POST /api/ecosystem/service/:unit/:action, admin-only, backs the
# Ecosystem > Services panel's per-project controls. See the rule file's
# own header comment for the exact, narrow scope (never this server's
# own unit, never anything outside the hydra-umc- namespace).
install -m 0644 "$OS_ROOT/provisioning/polkit/50-hydra-umc-server-service-control.rules" /etc/polkit-1/rules.d/50-hydra-umc-server-service-control.rules
systemctl daemon-reload
echo "Server installed. Enable manually after review: systemctl enable --now hydra-umc-server"
