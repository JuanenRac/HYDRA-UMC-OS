#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - Run the read-only node diagnostics agent
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
set -euo pipefail
echo " ==============================================================="
echo "  HYDRA-UMC-OS - run.sh"
echo "  Runs the read-only node diagnostics agent."
echo "  Copyright (C) 2026 JuanenRac (Electro Hobby 3D)"
echo "  <electrohobby3d@gmail.com> | GPL-3.0-or-later - see LICENSE"
echo " ==============================================================="
cd "$(dirname "$0")"
trap '[ -t 0 ] && read -r -p "Press Enter to close..." _' EXIT
export PYTHONPATH="$PWD/agent/src"
python3 -m hydra_umc_os.agent --config config/hydra-umc-os.example.json health "$@"
