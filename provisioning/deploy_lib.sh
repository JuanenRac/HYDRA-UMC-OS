#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - The deployment steps shared by the installers of the programs
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Sourced, never run. An installer that follows the deployment contract (docs/DEPLOY_CONTRACT.md) declares DEPLOY_CONTRACT=1, calls
# `deploy_begin` before it copies anything into its target and `deploy_finish` after its last `systemctl daemon-reload`:
#
#   deploy_begin  NAME TARGET   keeps the program that is installed now (tools/deploy_tree.py begin); nothing in TARGET changes
#   deploy_finish NAME TARGET   keeps the new program as the current release; when the unit runs it is restarted (systemctl try-restart) and
#                               its health route is polled; when it does not come back the earlier program is put back and the script
#                               ends with status 3
#
# NAME is the service of the registry (HYDRA-UMC-SERVER...); the unit, the port and the health route come from provisioning/ports.yaml, the
# component is the last part of TARGET. A unit that is not running is never started or restarted (the operator enables it after review), and
# the folders data, models and workspace of TARGET are never touched. The unit file of the service and its drop-ins (/etc/systemd/system/<unit> and <unit>.d,
# HYDRA_UMC_UNIT_DIR names another folder) are kept by deploy_begin and put back, with a daemon-reload, when the new program does not hold and by `rollback`.
#
# Settings: /opt/hydra-umc/.releases/deploy.json (keep, healthTimeoutS, healthIntervalS, restartCommand, healthCommand, restartOnDeploy,
# rollbackOnFailure; see tools/deploy_tree.py). HYDRA_UMC_DEPLOY=off skips both steps (the installer then behaves as it did before the
# contract). HYDRA_UMC_DEPLOY_ROOT and HYDRA_UMC_DEPLOY_TOOL name another releases folder / tool (the tests use them);
# HYDRA_UMC_DEPLOY_RESULT names a file that receives the JSON of the last step (the `hydra-umc-os deploy` command reads it).

HYDRA_DEPLOY_CONTRACT_SUPPORTED=1
HYDRA_DEPLOY_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HYDRA_DEPLOY_ROOT="${HYDRA_UMC_DEPLOY_ROOT:-/opt/hydra-umc/.releases}"
HYDRA_DEPLOY_TOOL="${HYDRA_UMC_DEPLOY_TOOL:-$HYDRA_DEPLOY_LIB_DIR/../tools/deploy_tree.py}"
HYDRA_DEPLOY_ACTIVE=0

_deploy_enabled() {
  if [[ "${HYDRA_UMC_DEPLOY:-on}" == "off" ]]; then
    echo "Deploy: HYDRA_UMC_DEPLOY=off, the release step is skipped."
    return 1
  fi
  if ! command -v python3 >/dev/null 2>&1 || [[ ! -f "$HYDRA_DEPLOY_TOOL" ]]; then
    echo "Deploy: python3 or $HYDRA_DEPLOY_TOOL is missing, the release step is skipped (the installer still installs)." >&2
    return 1
  fi
  return 0
}

_deploy_contract_ok() {
  if [[ "${DEPLOY_CONTRACT:-}" != "$HYDRA_DEPLOY_CONTRACT_SUPPORTED" ]]; then
    echo "Deploy: this installer declares DEPLOY_CONTRACT='${DEPLOY_CONTRACT:-}' and this lib supports $HYDRA_DEPLOY_CONTRACT_SUPPORTED: refusing before anything is installed." >&2
    return 1
  fi
}

deploy_begin() {
  local name="$1" target="$2" component unit="" args=()
  _deploy_contract_ok || exit 2
  _deploy_enabled || return 0
  component="$(basename "$target")"
  # shellcheck source=service_registry.sh
  source "$HYDRA_DEPLOY_LIB_DIR/service_registry.sh"
  unit="$(service_field "$name" systemd_unit 2>/dev/null || true)"
  [[ -n "$unit" ]] || unit="hydra-umc-$component.service"
  # the unit file and its drop-ins are kept with the program: the installer changes them outside the target, and a rollback must put them back too
  args=(--root "$HYDRA_DEPLOY_ROOT" begin "$component" --target "$target" --unit "$unit")
  python3 "$HYDRA_DEPLOY_TOOL" "${args[@]}" >/dev/null || {
    echo "Deploy: the program installed now could not be kept, so there would be nothing to go back to: nothing was installed." >&2
    exit 1
  }
  HYDRA_DEPLOY_ACTIVE=1
  echo "Deploy: $name - the program installed now is kept in $HYDRA_DEPLOY_ROOT/$component."
}

deploy_finish() {
  local name="$1" target="$2" component unit="" port health url="" status=0 output
  [[ "$HYDRA_DEPLOY_ACTIVE" == "1" ]] || return 0
  component="$(basename "$target")"
  # shellcheck source=service_registry.sh
  source "$HYDRA_DEPLOY_LIB_DIR/service_registry.sh"
  unit="$(service_field "$name" systemd_unit 2>/dev/null || true)"
  if [[ -z "$unit" && -f "/etc/systemd/system/hydra-umc-$component.service" ]]; then
    unit="hydra-umc-$component.service"
  fi
  if port="$(service_field "$name" port 2>/dev/null)" && health="$(service_field "$name" health_path 2>/dev/null)"; then
    url="http://127.0.0.1:${port}${health}"
  fi
  local args=("$HYDRA_DEPLOY_TOOL" --root "$HYDRA_DEPLOY_ROOT" settle "$component" --target "$target")
  [[ -n "$unit" ]] && args+=(--unit "$unit")
  [[ -n "$url" ]] && args+=(--health-url "$url")
  output="$(python3 "${args[@]}")" || status=$?
  HYDRA_DEPLOY_ACTIVE=0
  if [[ "$status" -ne 0 ]]; then
    echo "Deploy: $name did not hold (status $status): the earlier program was put back where there was one. See the line DEPLOY=FAIL above." >&2
    return "$status"
  fi
  output="${output%DEPLOY=PASS*}"
  if [[ -n "${HYDRA_UMC_DEPLOY_RESULT:-}" ]]; then
    printf '%s\n' "$output" >"$HYDRA_UMC_DEPLOY_RESULT"
  fi
  echo "Deploy: $name - $(printf '%s\n' "$output" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("result", "done"))' 2>/dev/null || echo done)."
}

# -----------------------------------------------------------------------------
# npm in the installers
#
# The install scripts of the dependencies (npm lifecycle scripts) are NOT run by default: a dependency that is changed upstream could otherwise run code as root on the device.
# The setting `npm_scripts = on` in /etc/hydra-umc/provisioning.conf (or HYDRA_UMC_NPM_SCRIPTS=on in the environment) lets them run, for a program whose build needs them.
# The build runs as the user who owns the checkout (not as root), so the checkout is not left with files of root that the updater cannot clean.
# -----------------------------------------------------------------------------

# Prints --ignore-scripts unless the scripts were allowed (the setting is off by default).
hydra_npm_install_flags() {
  local value="${HYDRA_UMC_NPM_SCRIPTS:-}" conf="${HYDRA_UMC_PROVISIONING_CONF:-/etc/hydra-umc/provisioning.conf}"
  if [[ -z "$value" && -f "$conf" ]]; then
    value="$(sed -n 's/^[[:space:]]*npm_scripts[[:space:]]*=[[:space:]]*//p' "$conf" | tail -n 1 | tr -d '[:space:]"')"
  fi
  case "${value,,}" in
    on | 1 | true | yes) ;;
    *) printf '%s' "--ignore-scripts" ;;
  esac
}

# hydra_npm_in DIR npm-arguments...   runs npm in DIR as the owner of DIR when this script runs as root and DIR belongs to somebody else.
hydra_npm_in() {
  local dir="$1" owner="" home=""
  shift
  if [[ $EUID -eq 0 ]]; then
    owner="$(stat -c %U "$dir" 2>/dev/null || true)"
  fi
  if [[ -n "$owner" && "$owner" != "root" && "$owner" != "UNKNOWN" ]]; then
    home="$(getent passwd "$owner" | cut -d: -f6)"
    if command -v runuser >/dev/null 2>&1; then
      (cd "$dir" && runuser -u "$owner" -- env "PATH=$PATH" "HOME=${home:-/tmp}" npm "$@")
    else
      (cd "$dir" && sudo -H -u "$owner" env "PATH=$PATH" npm "$@")
    fi
  else
    (cd "$dir" && npm "$@")
  fi
}

# --- the Python SDK for the services whose code imports it ---------------------------------------------------------------------------------
#
# A service that runs from /opt/hydra-umc/<component>/src with PYTHONPATH set to that folder cannot import `hydra_umc_sdk`, which lives in the
# HYDRA-UMC-SDK repository. `provide_sdk_python` copies the package to one folder that every service can read (default /opt/hydra-umc/sdk-python,
# HYDRA_UMC_SDK_PYTHON_DIR names another) and the unit of the service lists that folder in its PYTHONPATH. `verify_sdk_importable MODULE...` then
# imports each module from that folder alone, as the service user when it can, and ends the installer with status 2 when one cannot be imported,
# BEFORE the program is copied, so a missing SDK stops the installation with the earlier program untouched instead of leaving a service that
# starts and dies with ModuleNotFoundError. Both are called by the generated installers of the services named in "needs_sdk" of
# config/installer_generation.json, after the build hook and before the copy; they need $ROOT (and $SVC_USER for the check).
#
# Settings: HYDRA_UMC_SDK_SOURCE (the folder of the package, default $ROOT/HYDRA-UMC-SDK/clients/python/src/hydra_umc_sdk) and
# HYDRA_UMC_SDK_PYTHON_DIR (where it is put), HYDRA_UMC_PYTHON (the interpreter of the check, default python3; the tests use it).
HYDRA_SDK_PYTHON_DIR="${HYDRA_UMC_SDK_PYTHON_DIR:-/opt/hydra-umc/sdk-python}"

provide_sdk_python() {
  local source="${HYDRA_UMC_SDK_SOURCE:-$ROOT/HYDRA-UMC-SDK/clients/python/src/hydra_umc_sdk}"
  if [[ ! -f "$source/__init__.py" ]]; then
    echo "The Python SDK is missing: $source/__init__.py does not exist. Put the HYDRA-UMC-SDK repository next to the others (or set HYDRA_UMC_SDK_SOURCE); nothing was installed." >&2
    exit 2
  fi
  install -d -m 0755 "$HYDRA_SDK_PYTHON_DIR"
  rm -rf "$HYDRA_SDK_PYTHON_DIR/hydra_umc_sdk"
  cp -a "$source" "$HYDRA_SDK_PYTHON_DIR/hydra_umc_sdk"
  find "$HYDRA_SDK_PYTHON_DIR/hydra_umc_sdk" -name __pycache__ -type d -prune -exec rm -rf {} +
  if [[ $EUID -eq 0 ]]; then chown -R root:root "$HYDRA_SDK_PYTHON_DIR/hydra_umc_sdk"; fi
  chmod -R go-w "$HYDRA_SDK_PYTHON_DIR/hydra_umc_sdk"
  chmod -R a+rX "$HYDRA_SDK_PYTHON_DIR/hydra_umc_sdk"
  echo "SDK: the Python SDK is in $HYDRA_SDK_PYTHON_DIR."
}

verify_sdk_importable() {
  local module status=0
  local runner=()
  if [[ $EUID -eq 0 && -n "${SVC_USER:-}" ]] && id -u "$SVC_USER" >/dev/null 2>&1 && command -v runuser >/dev/null 2>&1; then
    runner=(runuser -u "$SVC_USER" --)
  fi
  for module in "$@"; do
    ${runner[@]+"${runner[@]}"} env "PYTHONPATH=$HYDRA_SDK_PYTHON_DIR" "${HYDRA_UMC_PYTHON:-python3}" -I -c "import sys; sys.path.insert(0, sys.argv[2]); __import__(sys.argv[1])" "$module" "$HYDRA_SDK_PYTHON_DIR" >/dev/null 2>&1 || status=$?
    if [[ $status -ne 0 ]]; then
      echo "SDK=FAIL the service user cannot import $module from $HYDRA_SDK_PYTHON_DIR: nothing was installed." >&2
      exit 2
    fi
  done
  echo "SDK=PASS $* can be imported from $HYDRA_SDK_PYTHON_DIR."
}
