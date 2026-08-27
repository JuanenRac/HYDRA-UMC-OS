#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - Validate and test the read-only platform agent
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
set -euo pipefail
echo " ==============================================================="
echo "  HYDRA-UMC-OS - build.sh"
echo "  Validates and tests the read-only platform agent."
echo "  Copyright (C) 2026 JuanenRac (Electro Hobby 3D)"
echo "  <electrohobby3d@gmail.com> | GPL-3.0-or-later - see LICENSE"
echo " ==============================================================="
cd "$(dirname "$0")"
trap '[ -t 0 ] && read -r -p "Press Enter to close..." _' EXIT
export PYTHONPATH="$PWD/agent/src"
python3 bump_version.py || exit 1
python3 "$(dirname "$0")/bump_manifest_version.py" --sync || exit 1
python3 -m unittest discover -s agent/tests -v
