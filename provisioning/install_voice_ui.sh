#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - Install HYDRA-UMC-VOICE-UI as a local CM5 gateway
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# The v0 gateway uses only the Python standard library and binds to loopback.
# It is not the future Hailo STT/TTS runtime and never receives raw audio.
set -euo pipefail
[[ "${1:-}" == "--apply" ]] || { echo "Dry-run policy: rerun with --apply after review."; exit 0; }
[[ $EUID -eq 0 ]] || { echo "Run as root with sudo." >&2; exit 2; }

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SOURCE="$ROOT/HYDRA-UMC-VOICE-UI"
TARGET=/opt/hydra-umc/voice-ui
VOICE_USER="hydra-umc-voice-ui"
ENV_FILE=/etc/hydra-umc/voice-ui.env

echo " ==============================================================="
echo "  HYDRA-UMC-OS - install_voice_ui.sh"
echo "  Installs the bounded loopback Voice UI gateway; no STT/TTS model."
echo "  Copyright (C) 2026 JuanenRac (Electro Hobby 3D)"
echo "  <electrohobby3d@gmail.com> | GPL-3.0-or-later - see LICENSE"
echo " ==============================================================="

[[ -d "$SOURCE/src/hydra_umc_voice_ui" && -f "$SOURCE/systemd/hydra-umc-voice-ui.service" ]] || {
  echo "HYDRA-UMC-VOICE-UI source or systemd unit is incomplete: $SOURCE" >&2; exit 2;
}
[[ -f "$ENV_FILE" ]] || {
  echo "Create $ENV_FILE from HYDRA-UMC-VOICE-UI/deploy/voice-ui.env.example first." >&2; exit 2;
}
command -v python3 >/dev/null || { echo "HYDRA-UMC-VOICE-UI requires python3." >&2; exit 2; }
if ! id -u "$VOICE_USER" >/dev/null 2>&1; then
  useradd --system --home "$TARGET" --no-create-home --shell /usr/sbin/nologin "$VOICE_USER"
fi
install -d -o root -g root -m 0755 "$TARGET"
rm -rf "$TARGET/src"
cp -a "$SOURCE/src" "$TARGET/"
chown -R root:root "$TARGET/src"
chmod -R go-w "$TARGET/src"
chown root:"$VOICE_USER" "$ENV_FILE"
chmod 0640 "$ENV_FILE"
install -m 0644 "$SOURCE/systemd/hydra-umc-voice-ui.service" /etc/systemd/system/hydra-umc-voice-ui.service
# Real bug found live: every install_*.sh here updated the deployed
# build/binary but never this project's OWN hydra-umc.project.json -
# GET /api/ecosystem/status (STUDIO's own Services/AI Family panels)
# reads THIS file for name/version/maturity/family, so every one of
# them kept reporting whatever version happened to be here from the
# very first install, forever, no matter how many real updates
# followed. Copied last, right before the reload, so it always
# reflects the exact SOURCE that was actually just installed.
install -m 0644 "$SOURCE/hydra-umc.project.json" "$TARGET/hydra-umc.project.json"
systemctl daemon-reload
echo "Voice UI installed. Enable manually after Server token review: systemctl enable --now hydra-umc-voice-ui"
