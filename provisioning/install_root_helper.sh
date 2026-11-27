#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - install_root_helper.sh (first installation of the root helper, from its signed package)
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# The helper updates the programs of the device from signed release packages, and itself with them. This puts the first one in place, once, from the three files of
# the release of HYDRA-UMC-OS (hydra-helper-<version>.tgz, .sha256, .sig). Nothing is built and nothing is fetched here.
#
#   install_root_helper.sh PACKAGE.tgz [--apply] [--enable-trigger]
#     --apply           really install (without it the package is only verified and the steps are said)
#     --enable-trigger  also enable hydra-umc-helper.path and disable hydra-umc-fleet.path (the earlier helper)
#
# It does not switch the helper on: /etc/hydra-umc/helper.json ("enabled": true) and the one-time code (root_helper.py totp-enroll) are the operator's.
# The trusted key is the one of the checkout this script runs from (config/release_key.pub).
set -euo pipefail

PACKAGE=""
APPLY=false
TRIGGER=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) APPLY=true ;;
    --enable-trigger) TRIGGER=true ;;
    -*) echo "Unknown option: $1" >&2; exit 64 ;;
    *) PACKAGE="$1" ;;
  esac
  shift
done
[[ -n "$PACKAGE" && -f "$PACKAGE" ]] || { echo "Usage: install_root_helper.sh PACKAGE.tgz [--apply] [--enable-trigger]" >&2; exit 64; }
[[ "$(basename "$PACKAGE")" == hydra-helper-*.tgz ]] || { echo "The package of the helper is hydra-helper-<version>.tgz." >&2; exit 64; }
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
python3 "$ROOT/tools/package_component.py" verify "$PACKAGE" || { echo "The package is not the one the project signed: nothing was installed." >&2; exit 2; }
if ! $APPLY; then
  echo "Dry run: with --apply it would install $(basename "$PACKAGE") in /opt/hydra-umc/helper, its units and /etc/hydra-umc/helper.json (switched off)."
  exit 0
fi
[[ $EUID -eq 0 ]] || { echo "Run as root with sudo." >&2; exit 2; }
# shellcheck source=deploy_lib.sh
source "$ROOT/provisioning/deploy_lib.sh"
hydra_etc_dir
PACKAGE_PATH="$(cd "$(dirname "$PACKAGE")" && pwd)/$(basename "$PACKAGE")"
python3 - "$ROOT/tools" "$PACKAGE_PATH" <<'PY'
import importlib.util, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("package_install", Path(sys.argv[1]) / "package_install.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
done = module.install(Path(sys.argv[2]), module.Device(say=print), allow_first_install=True)
print(f"helper {done['version']} installed ({done['mode']})")
PY
if [[ ! -f /etc/hydra-umc/helper.json ]]; then
  printf '{\n  "enabled": false,\n  "requireTotp": true\n}\n' > /etc/hydra-umc/helper.json
  chmod 0644 /etc/hydra-umc/helper.json
fi
install -d -o root -g root -m 0700 /var/lib/hydra-umc-helper
if [[ -d /opt/hydra-umc/server/data ]]; then
  install -d -o hydra-umc-server -g hydra-umc-server -m 2770 /opt/hydra-umc/server/data/fleet-update
fi
if $TRIGGER; then
  systemctl disable --now hydra-umc-fleet.path 2>/dev/null || true
  systemctl enable --now hydra-umc-helper.path
fi
echo "Installed. Still off: set \"enabled\": true in /etc/hydra-umc/helper.json, run /opt/hydra-umc/helper/tools/root_helper.py totp-enroll as root,"
echo "and set \"fleetUpdate\": { \"helper\": true } in the server configuration. Start the trigger: systemctl enable --now hydra-umc-helper.path"
