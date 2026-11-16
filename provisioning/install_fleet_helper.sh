#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - install_fleet_helper.sh (the helper that lets the isolated server update the programs of the device)
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# The server runs in an isolated unit (its own account, NoNewPrivileges, no capabilities, /home hidden): it cannot run tools/fleet_update.py, reach the checkouts or call sudo.
# This installs the other half: a path unit that watches ONE request file in the data folder of the server and a oneshot unit that runs the tool as the account that owns the
# checkouts, with a rule of sudo that names every command (no wildcard). Nothing is started unless --enable is given, and the server only uses it when its configuration says
# "fleetUpdate": { "helper": true } (off by default).
#
#   install_fleet_helper.sh [--user ACCOUNT] [--workspace DIR] [--signers FILE] [--enable] [--apply]
#     --user       the account that owns the checkouts and runs the tool (default hydra-umc; it must exist, it must not be the account of the server)
#     --workspace  its folder of checkouts (default /home/ACCOUNT/hydra-umc; HYDRA-UMC-OS, HYDRA-UMC-SDK and the programs are cloned there)
#     --signers    a file of public keys for `git verify-tag` (allowed_signers format), installed as /etc/hydra-umc/allowed_signers (root-owned, read by every account)
#     --enable     also enable and start the path unit
#   Without --apply it only says what it would do.
set -euo pipefail

APPLY=false
ENABLE=false
HELPER_USER=hydra-umc
WORKSPACE=""
SIGNERS=""
SERVER_USER=hydra-umc-server
DATA=/opt/hydra-umc/server/data
while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) APPLY=true ;;
    --enable) ENABLE=true ;;
    --user) HELPER_USER="${2:?--user needs an account}"; shift ;;
    --workspace) WORKSPACE="${2:?--workspace needs a folder}"; shift ;;
    --signers) SIGNERS="${2:?--signers needs a file}"; shift ;;
    *) echo "Unknown option: $1" >&2; exit 64 ;;
  esac
  shift
done
[[ "$HELPER_USER" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]] || { echo "The account name is not valid." >&2; exit 64; }
[[ -n "$WORKSPACE" ]] || WORKSPACE="/home/$HELPER_USER/hydra-umc"
[[ "$WORKSPACE" =~ ^/[A-Za-z0-9_./-]+$ ]] || { echo "The workspace must be a plain absolute path." >&2; exit 64; }
[[ "$HELPER_USER" != "$SERVER_USER" ]] || { echo "The helper must not run as the account of the server: that is the isolation this installs." >&2; exit 64; }
[[ $EUID -eq 0 ]] || { echo "Run as root with sudo." >&2; exit 2; }

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TOOL="$WORKSPACE/HYDRA-UMC-OS/tools/fleet_update.py"
run() { if $APPLY; then "$@"; else printf '[dry-run] '; printf '%q ' "$@"; printf '\n'; fi; }

if $APPLY; then
  id -u "$HELPER_USER" >/dev/null 2>&1 || { echo "Missing account $HELPER_USER." >&2; exit 2; }
  id -u "$SERVER_USER" >/dev/null 2>&1 || { echo "Missing account $SERVER_USER: install the server first (provisioning/install_server.sh --apply)." >&2; exit 2; }
  [[ -d "$DATA" ]] || { echo "Missing $DATA: install the server first." >&2; exit 2; }
  [[ -f "$TOOL" ]] || { echo "Missing $TOOL: the checkout of HYDRA-UMC-OS of $HELPER_USER is not at $WORKSPACE." >&2; exit 2; }
  [[ -z "$SIGNERS" || -f "$SIGNERS" ]] || { echo "Missing the file of signers: $SIGNERS" >&2; exit 2; }
fi

# The folder shared by the two accounts: owned by the server, its group on every new file, closed to everybody else.
run install -d -o "$SERVER_USER" -g "$SERVER_USER" -m 2770 "$DATA/fleet-update"
run install -d -o root -g root -m 0755 /etc/hydra-umc
if [[ -n "$SIGNERS" ]]; then
  run install -m 0644 -o root -g root "$SIGNERS" /etc/hydra-umc/allowed_signers
fi

# The rule of sudo: one line per command of the tool, written from the install plan of this checkout, checked by visudo before it is put in place.
RULE="$(mktemp)"
SERVICE_TMP="$(mktemp)"
trap 'rm -f "$RULE" "$SERVICE_TMP"' EXIT
python3 "$ROOT/tools/make_fleet_sudoers.py" --user "$HELPER_USER" --install-plan "$ROOT/provisioning/install_plan.json" --workspace "$WORKSPACE" > "$RULE"
if $APPLY; then
  visudo -cf "$RULE" >/dev/null || { echo "visudo refuses the rule; nothing was installed." >&2; exit 2; }
fi
run install -m 0440 -o root -g root "$RULE" /etc/sudoers.d/hydra-umc-fleet

# The two units of this repository, with the account and the folder of the checkouts put in.
sed -e "s|^User=hydra-umc\$|User=$HELPER_USER|" -e "s|/home/hydra-umc/hydra-umc/HYDRA-UMC-OS/tools/fleet_update.py|$TOOL|" "$ROOT/systemd/hydra-umc-fleet.service" > "$SERVICE_TMP"
run install -m 0644 "$SERVICE_TMP" /etc/systemd/system/hydra-umc-fleet.service
run install -m 0644 "$ROOT/systemd/hydra-umc-fleet.path" /etc/systemd/system/hydra-umc-fleet.path
run systemctl daemon-reload
if $ENABLE; then
  run systemctl enable --now hydra-umc-fleet.path
fi
echo "Fleet update helper installed for $HELPER_USER ($WORKSPACE). It does nothing until the server asks: set \"fleetUpdate\": { \"helper\": true } in the server configuration"
echo "and the switches updateCheck.enabled (look) and maintenance.enabled (apply). Start the trigger with: systemctl enable --now hydra-umc-fleet.path"
