#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - build_hooks/server.sh
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Checks the build and the Node.js version, creates the settings file with its secrets (never printed), installs the built dashboard with its production dependencies and the polkit rules.
# Sourced by provisioning/install_server.sh as root, after the service user and $TARGET exist and before the shared copy step;
# never run on its own. Uses $ROOT, $SOURCE, $TARGET, $SVC_USER and $HERE of the installer. Safe to run again.

[[ -d "$SOURCE/dist" && -d "$SOURCE/public" && -f "$SOURCE/package.json" && -f "$SOURCE/package-lock.json" ]] || { echo "HYDRA-UMC-SERVER build is incomplete: $SOURCE" >&2; exit 2; }
[[ -n "$(find "$SOURCE/public/models" -iname '*.stl' -print -quit 2>/dev/null)" ]] || { echo "The frontend in $SOURCE/public has no 3D models. Run: node HYDRA-UMC-STUDIO/scripts/mesh_pack.mjs ensure --source auto (offline: copy the package to ~/.cache/hydra-umc/meshes or set HYDRA_UMC_MESH_PACKAGE), then HYDRA-UMC-SERVER/build-frontend.sh, then rerun this." >&2; exit 2; }
OS_ROOT="$(cd "$HERE/.." && pwd)"
[[ -d /etc/hydra-umc ]] || install -d -o root -g root -m 0750 /etc/hydra-umc
python3 "$OS_ROOT/provisioning/generate_secrets.py" /etc/hydra-umc/server.env --create-from "$OS_ROOT/provisioning/server.env.example" --apply --adopt "HYDRA_UMC_VOICE_UI_TOKEN=/etc/hydra-umc/voice-ui.env:HYDRA_UMC_VOICE_UI_TOKEN" --mirror "HYDRA_UMC_VOICE_UI_TOKEN=/etc/hydra-umc/voice-ui.env:HYDRA_UMC_VOICE_UI_TOKEN" --ensure HYDRA_UMC_VOICE_UI_RESULT_KEY --adopt "HYDRA_UMC_VOICE_UI_RESULT_KEY=/etc/hydra-umc/voice-ui.env:HYDRA_UMC_VOICE_UI_RESULT_KEY" --mirror "HYDRA_UMC_VOICE_UI_RESULT_KEY=/etc/hydra-umc/voice-ui.env:HYDRA_UMC_VOICE_UI_RESULT_KEY" --ensure HYDRA_UMC_VOICE_CONFIRM_REQUIRE_SIGNATURE=1
python3 "$OS_ROOT/provisioning/generate_secrets.py" /etc/hydra-umc/server.env --check || { echo "Fix /etc/hydra-umc/server.env (no example value, secrets long enough) and rerun." >&2; exit 2; }
command -v node >/dev/null || { echo "HYDRA-UMC-SERVER requires Node.js 20 or later." >&2; exit 2; }
command -v npm >/dev/null || { echo "HYDRA-UMC-SERVER requires npm from the same supported Node.js installation." >&2; exit 2; }
NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
[[ "$NODE_MAJOR" =~ ^[0-9]+$ && "$NODE_MAJOR" -ge 20 ]] || { echo "HYDRA-UMC-SERVER requires Node.js 20 or later; found $(node --version)." >&2; exit 2; }
chown root:"$SVC_USER" /etc/hydra-umc/server.env
chmod 0640 /etc/hydra-umc/server.env
rm -rf "$TARGET/dist" "$TARGET/public"
cp -a "$SOURCE/dist" "$SOURCE/public" "$SOURCE/package.json" "$SOURCE/package-lock.json" "$TARGET/"
( cd "$TARGET" && npm ci --omit=dev )
install -d -m 0755 /etc/polkit-1/rules.d
install -m 0644 "$OS_ROOT/provisioning/polkit/49-hydra-umc-server-power.rules" /etc/polkit-1/rules.d/49-hydra-umc-server-power.rules
install -m 0644 "$OS_ROOT/provisioning/polkit/50-hydra-umc-server-service-control.rules" /etc/polkit-1/rules.d/50-hydra-umc-server-service-control.rules
