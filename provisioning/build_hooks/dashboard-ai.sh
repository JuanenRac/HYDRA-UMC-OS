#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - build_hooks/dashboard-ai.sh
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Builds the static single-page app with npm and installs it with its small Python server.
# Sourced by provisioning/install_dashboard_ai.sh as root, after the service user and $TARGET exist and before the shared copy step;
# never run on its own. Uses $ROOT, $SOURCE, $TARGET, $SVC_USER and $HERE of the installer. Safe to run again.

[[ -f "$SOURCE/package.json" && -f "$SOURCE/scripts/serve_static.py" ]] || { echo "HYDRA-UMC-DASHBOARD-AI source is incomplete: $SOURCE" >&2; exit 2; }
command -v node >/dev/null || { echo "HYDRA-UMC-DASHBOARD-AI requires Node.js (build-time only)." >&2; exit 2; }
command -v npm >/dev/null || { echo "HYDRA-UMC-DASHBOARD-AI requires npm (build-time only)." >&2; exit 2; }
command -v python3 >/dev/null || { echo "HYDRA-UMC-DASHBOARD-AI static server needs python3." >&2; exit 2; }
# `npm ci` (versions from the lock file): the dependencies are installed without running their install scripts (npm_scripts = on in /etc/hydra-umc/provisioning.conf allows them) and the build runs as the owner of the checkout.
# shellcheck disable=SC2046
hydra_npm_in "$SOURCE" ci $(hydra_npm_install_flags) && hydra_npm_in "$SOURCE" run build || { echo "The build of HYDRA-UMC-DASHBOARD-AI failed. If a dependency needs its install script, set npm_scripts = on in /etc/hydra-umc/provisioning.conf and rerun." >&2; exit 1; }
rm -rf "$TARGET/dist"
cp -a "$SOURCE/dist" "$TARGET/dist"
install -m 0644 "$SOURCE/scripts/serve_static.py" "$TARGET/serve_static.py"
chown -R root:root "$TARGET/dist" "$TARGET/serve_static.py"
chmod -R go-w "$TARGET/dist"
