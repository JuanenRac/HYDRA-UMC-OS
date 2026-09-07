#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - Install HYDRA-UMC-SEMANTIC-PLANNER as a local CM5 API
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Real gap found auditing the ecosystem against actual CM5 hardware:
# HYDRA-UMC-SEMANTIC-PLANNER's real rule-based task decomposition and
# semantic recovery (decompose.py, recovery.py) were only ever reachable
# as a one-shot CLI - api.py (new) now exposes the same functions as a
# real stdlib HTTP API. Same simple "copy src/ + PYTHONPATH" shape as
# install_datalake.sh, no venv/pip needed at runtime.
set -euo pipefail
[[ "${1:-}" == "--apply" ]] || { echo "Dry-run policy: rerun with --apply after review."; exit 0; }
[[ $EUID -eq 0 ]] || { echo "Run as root with sudo." >&2; exit 2; }

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SOURCE="$ROOT/HYDRA-UMC-SEMANTIC-PLANNER"
TARGET=/opt/hydra-umc/semantic-planner
PLANNER_USER="hydra-umc-semantic-planner"

echo " ==============================================================="
echo "  HYDRA-UMC-OS - install_semantic_planner.sh"
echo "  Installs the real goal-decomposition/recovery API."
echo "  Copyright (C) 2026 JuanenRac (Electro Hobby 3D)"
echo "  <electrohobby3d@gmail.com> | GPL-3.0-or-later - see LICENSE"
echo " ==============================================================="

[[ -d "$SOURCE/src/hydra_umc_semantic_planner" && -f "$SOURCE/systemd/hydra-umc-semantic-planner.service" ]] || {
  echo "HYDRA-UMC-SEMANTIC-PLANNER source or systemd unit is incomplete: $SOURCE" >&2; exit 2;
}
command -v python3 >/dev/null || { echo "HYDRA-UMC-SEMANTIC-PLANNER requires python3." >&2; exit 2; }
if ! id -u "$PLANNER_USER" >/dev/null 2>&1; then
  useradd --system --home "$TARGET" --no-create-home --shell /usr/sbin/nologin "$PLANNER_USER"
fi
install -d -o root -g root -m 0755 "$TARGET"
rm -rf "$TARGET/src"
cp -a "$SOURCE/src" "$TARGET/"
chown -R root:root "$TARGET/src"
chmod -R go-w "$TARGET/src"
install -m 0644 "$SOURCE/systemd/hydra-umc-semantic-planner.service" /etc/systemd/system/hydra-umc-semantic-planner.service
systemctl daemon-reload
echo "Semantic-Planner installed. Enable manually after review: systemctl enable --now hydra-umc-semantic-planner"
