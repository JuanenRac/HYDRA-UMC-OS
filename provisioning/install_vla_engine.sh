#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - Install HYDRA-UMC-VLA-ENGINE as a local CM5 API
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Real gap found auditing the ecosystem against actual CM5 hardware:
# HYDRA-UMC-VLA-ENGINE's real action-tokenization and trajectory-
# integration math (action_tokens.py, trajectory.py) and its honest
# hardware-status check (hardware.py) were only ever reachable as a
# one-shot CLI - api.py (new) now exposes the same functions as a real
# stdlib HTTP API. Same simple "copy src/ + PYTHONPATH" shape as
# install_datalake.sh, no venv/pip needed at runtime.
#
# GET /status needs the same sibling-checkout layout
# check_engine_status() already expects (workspace/HYDRA-UMC-COGNITIVE-NODE/
# models/) - /opt/hydra-umc/vla-engine/workspace is a symlink to $ROOT,
# the same sibling-checkout root every install_*.sh script in this file
# already resolves, rather than a second copy.
set -euo pipefail
[[ "${1:-}" == "--apply" ]] || { echo "Dry-run policy: rerun with --apply after review."; exit 0; }
[[ $EUID -eq 0 ]] || { echo "Run as root with sudo." >&2; exit 2; }

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SOURCE="$ROOT/HYDRA-UMC-VLA-ENGINE"
TARGET=/opt/hydra-umc/vla-engine
ENGINE_USER="hydra-umc-vla-engine"

echo " ==============================================================="
echo "  HYDRA-UMC-OS - install_vla_engine.sh"
echo "  Installs the real action-tokenization/trajectory API."
echo "  Copyright (C) 2026 JuanenRac (Electro Hobby 3D)"
echo "  <electrohobby3d@gmail.com> | GPL-3.0-or-later - see LICENSE"
echo " ==============================================================="

[[ -d "$SOURCE/src/hydra_umc_vla_engine" && -f "$SOURCE/systemd/hydra-umc-vla-engine.service" ]] || {
  echo "HYDRA-UMC-VLA-ENGINE source or systemd unit is incomplete: $SOURCE" >&2; exit 2;
}
command -v python3 >/dev/null || { echo "HYDRA-UMC-VLA-ENGINE requires python3." >&2; exit 2; }
if ! id -u "$ENGINE_USER" >/dev/null 2>&1; then
  useradd --system --home "$TARGET" --no-create-home --shell /usr/sbin/nologin "$ENGINE_USER"
fi
install -d -o root -g root -m 0755 "$TARGET"
rm -rf "$TARGET/src"
cp -a "$SOURCE/src" "$TARGET/"
chown -R root:root "$TARGET/src"
chmod -R go-w "$TARGET/src"
ln -sfn "$ROOT" "$TARGET/workspace"
install -m 0644 "$SOURCE/systemd/hydra-umc-vla-engine.service" /etc/systemd/system/hydra-umc-vla-engine.service
systemctl daemon-reload
echo "VLA-Engine installed. Enable manually after review: systemctl enable --now hydra-umc-vla-engine"
