#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - build_hooks/safety-zones.sh
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Checks the source and the interpreter, then proves that the account of the service can read its zones file (second half), before the copy.
# Sourced by provisioning/install_safety_zones.sh as root, after the service user and $TARGET exist and before the shared copy step;
# never run on its own. Uses $ROOT, $SOURCE, $TARGET, $SVC_USER and $HERE of the installer. Safe to run again.

[[ -d "$SOURCE/src/hydra_umc_safety_zones" ]] || { echo "HYDRA-UMC-SAFETY-ZONES source is incomplete: $SOURCE" >&2; exit 2; }
command -v python3 >/dev/null || { echo "HYDRA-UMC-SAFETY-ZONES requires python3." >&2; exit 2; }

# --- the zones file: the service reads it from a folder of its own, and the installer proves that its account can ------------------------------------
#
# The unit asks systemd for /etc/hydra-umc-safety-zones (ConfigurationDirectory=); the shared /etc/hydra-umc is never changed, because its account cannot
# enter it. Before anything is copied and before the running service is touched, this step (1) creates that folder if it is not there, (2) copies the zones
# file (and its signature) of the earlier place into it once, as root, never overwriting and never deleting, and (3) runs `check-access` of the program that
# is about to be installed AS THE SERVICE ACCOUNT. When the account cannot read the file the installer ends with status 2 and the program that runs now stays
# exactly as it is (fail closed). The one case that does not stop it: there is no zones file at all and the unit is not running, which is a first
# installation (the zones come from a risk assessment and the service does not start without them, which is the safe state; it is said in the output).
# Settings, for the tests: HYDRA_UMC_SAFETY_ZONES_CONFIG_DIR, HYDRA_UMC_SAFETY_ZONES_LEGACY_FILE, HYDRA_UMC_PYTHON, HYDRA_UMC_SYSTEMCTL.
SZ_CONFIG_DIR="${HYDRA_UMC_SAFETY_ZONES_CONFIG_DIR:-/etc/hydra-umc-safety-zones}"
SZ_ZONES_FILE="$SZ_CONFIG_DIR/zones.json"
SZ_LEGACY_FILE="${HYDRA_UMC_SAFETY_ZONES_LEGACY_FILE:-/etc/hydra-umc/safety-zones.zones.json}"
SZ_PYTHON="${HYDRA_UMC_PYTHON:-python3}"
# a folder that the service account can enter, made by the interpreter itself (tempfile refuses a name that exists and works the same on every system)
SZ_STAGE="$("$SZ_PYTHON" -c 'import os, tempfile; d = tempfile.mkdtemp(prefix="hydra-safety-zones-"); os.chmod(d, 0o755); print(d)')"
cp -a "$SOURCE/src" "$SZ_STAGE/src"
chmod -R a+rX "$SZ_STAGE/src"

if [[ ! -d "$SZ_CONFIG_DIR" ]]; then
  mkdir -p "$SZ_CONFIG_DIR"
  chmod 0750 "$SZ_CONFIG_DIR"
  if [[ $EUID -eq 0 ]]; then chown "root:$SVC_USER" "$SZ_CONFIG_DIR"; fi
  echo "Safety zones: created $SZ_CONFIG_DIR (mode 0750)."
fi

(cd "$SZ_STAGE" && env "PYTHONPATH=$SZ_STAGE/src" "$SZ_PYTHON" -m hydra_umc_safety_zones.main prepare-config --zones-file "$SZ_ZONES_FILE" --legacy-file "$SZ_LEGACY_FILE" --group "$SVC_USER") || {
  rm -rf "$SZ_STAGE"
  echo "SAFETY_ZONES=REFUSED the zones file could not be prepared in $SZ_CONFIG_DIR: nothing was installed and the program that runs now was not touched." >&2
  exit 2
}

SZ_RUNNER=()
if [[ $EUID -eq 0 ]] && id -u "$SVC_USER" >/dev/null 2>&1 && command -v runuser >/dev/null 2>&1; then
  SZ_RUNNER=(runuser -u "$SVC_USER" --)
fi
SZ_STATUS=0
SZ_MESSAGE="$(cd "$SZ_STAGE" && ${SZ_RUNNER[@]+"${SZ_RUNNER[@]}"} env "PYTHONPATH=$SZ_STAGE/src" "$SZ_PYTHON" -m hydra_umc_safety_zones.main check-access --zones-file "$SZ_ZONES_FILE" 2>&1)" || SZ_STATUS=$?
rm -rf "$SZ_STAGE"
if [[ $SZ_STATUS -eq 0 ]]; then
  echo "SAFETY_ZONES=PASS the account $SVC_USER can read $SZ_ZONES_FILE."
else
  SZ_RUNNING=0
  if "${HYDRA_UMC_SYSTEMCTL:-systemctl}" is-active --quiet hydra-umc-safety-zones.service 2>/dev/null; then SZ_RUNNING=1; fi
  if [[ ! -e "$SZ_ZONES_FILE" && $SZ_RUNNING -eq 0 ]]; then
    echo "SAFETY_ZONES=WAIT there is no zones file yet in $SZ_CONFIG_DIR and the service is not running: the program is installed, and the service will not start until a readable zones file is put there." >&2
  else
    printf '%s\n' "$SZ_MESSAGE" >&2
    echo "SAFETY_ZONES=REFUSED the account $SVC_USER cannot read $SZ_ZONES_FILE: nothing was installed and the program that runs now was not touched. Fix the file or its folder (owner root, group $SVC_USER, modes 0750 and 0640) and run the installer again." >&2
    exit 2
  fi
fi
