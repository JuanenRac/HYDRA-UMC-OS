#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - Install HYDRA-UMC-LOCAL-TECHNICIAN on the CM5
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Real gap found live: HYDRA-UMC-LOCAL-TECHNICIAN (family "Cognitive AI
# Node", parent HYDRA-UMC-COGNITIVE-NODE) has a real, tested CLI
# (`hydra-umc-local-technician`, see its own pyproject.toml
# [project.scripts]) but was never installed anywhere on this device,
# so it never showed up in STUDIO's own AI Family panel at all - not
# stale, genuinely invisible. Unlike every other project this repo
# installs, it declares no `service` block in its own manifest and has
# no systemd unit of its own (Fase 0 of six - a bounded, policy-gated
# CLI technician, not a standing daemon yet, see its own README
# Roadmap) - this script only ever drops its real source + manifest at
# a real host path, the same one every other project's manifest lives
# at, so GET /api/ecosystem/status's own discovery picks it up and
# reports it honestly as "not a service" (live: null), matching the
# same convention every other CLI/library-shaped project here already
# gets.
set -euo pipefail
[[ "${1:-}" == "--apply" ]] || { echo "Dry-run policy: rerun with --apply after review."; exit 0; }
[[ $EUID -eq 0 ]] || { echo "Run as root with sudo." >&2; exit 2; }

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SOURCE="$ROOT/HYDRA-UMC-LOCAL-TECHNICIAN"
TARGET=/opt/hydra-umc/local-technician

echo " ==============================================================="
echo "  HYDRA-UMC-OS - install_local_technician.sh"
echo "  Installs the real, policy-gated local AI technician CLI."
echo "  Copyright (C) 2026 JuanenRac (Electro Hobby 3D)"
echo "  <electrohobby3d@gmail.com> | GPL-3.0-or-later - see LICENSE"
echo " ==============================================================="

[[ -d "$SOURCE/src/hydra_umc_local_technician" ]] || {
  echo "HYDRA-UMC-LOCAL-TECHNICIAN source is incomplete: $SOURCE" >&2; exit 2;
}
command -v python3 >/dev/null || { echo "HYDRA-UMC-LOCAL-TECHNICIAN requires python3." >&2; exit 2; }

install -d -o root -g root -m 0755 "$TARGET"
rm -rf "$TARGET/src" "$TARGET/contracts"
cp -a "$SOURCE/src" "$TARGET/"
cp -a "$SOURCE/contracts" "$TARGET/"
chown -R root:root "$TARGET/src" "$TARGET/contracts"
chmod -R go-w "$TARGET/src" "$TARGET/contracts"
cat >/usr/local/bin/hydra-umc-local-technician <<'EOF'
#!/usr/bin/env sh
export PYTHONPATH=/opt/hydra-umc/local-technician/src
exec /usr/bin/python3 -m hydra_umc_local_technician.cli "$@"
EOF
chmod 0755 /usr/local/bin/hydra-umc-local-technician
install -m 0644 "$SOURCE/hydra-umc.project.json" "$TARGET/hydra-umc.project.json"
echo "Local-Technician installed - a real CLI (hydra-umc-local-technician), no standing service yet."
echo "Try: hydra-umc-local-technician --help"
