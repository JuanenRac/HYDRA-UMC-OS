#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - build_hooks/voice-ui.sh
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Checks the source, creates the settings file with its secrets (never printed) and gives the service user read access to it.
# Sourced by provisioning/install_voice_ui.sh as root, after the service user and $TARGET exist and before the shared copy step;
# never run on its own. Uses $ROOT, $SOURCE, $TARGET, $SVC_USER and $HERE of the installer. Safe to run again.

[[ -d "$SOURCE/src/hydra_umc_voice_ui" ]] || { echo "HYDRA-UMC-VOICE-UI source is incomplete: $SOURCE" >&2; exit 2; }
OS_ROOT="$(cd "$HERE/.." && pwd)"
ENV_FILE=/etc/hydra-umc/voice-ui.env
[[ -d /etc/hydra-umc ]] || install -d -o root -g root -m 0750 /etc/hydra-umc
python3 "$OS_ROOT/provisioning/generate_secrets.py" "$ENV_FILE" --create-from "$SOURCE/deploy/voice-ui.env.example" --apply --adopt "HYDRA_UMC_VOICE_UI_TOKEN=/etc/hydra-umc/server.env:HYDRA_UMC_VOICE_UI_TOKEN" --ensure HYDRA_UMC_VOICE_UI_RESULT_KEY --adopt "HYDRA_UMC_VOICE_UI_RESULT_KEY=/etc/hydra-umc/server.env:HYDRA_UMC_VOICE_UI_RESULT_KEY" --ensure HYDRA_UMC_VOICE_UI_REQUIRE_SUBJECT=1
python3 "$OS_ROOT/provisioning/generate_secrets.py" "$ENV_FILE" --check || { echo "Fix $ENV_FILE (no example value) and rerun." >&2; exit 2; }
command -v python3 >/dev/null || { echo "HYDRA-UMC-VOICE-UI requires python3." >&2; exit 2; }
chown root:"$SVC_USER" "$ENV_FILE"
chmod 0640 "$ENV_FILE"

hook_after_install() {
  echo "Enable it after the Server token review: systemctl enable --now hydra-umc-voice-ui"
}
