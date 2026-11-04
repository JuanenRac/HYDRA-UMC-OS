#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - Reversible CM5 state backup and restore utility
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Creates/restores only HYDRA-UMC state. --apply is required for writes.
set -euo pipefail

ACTION="${1:-}"
ARCHIVE="${2:-}"
APPLY="${3:-}"
[[ "$ACTION" == backup || "$ACTION" == restore ]] || { echo "Usage: $0 <backup|restore> <archive.tar.gz> [--apply]" >&2; exit 2; }
[[ -n "$ARCHIVE" ]] || { echo "An archive path is required." >&2; exit 2; }
[[ -z "$APPLY" || "$APPLY" == --apply ]] || { echo "Unknown option: $APPLY" >&2; exit 2; }
[[ $EUID -eq 0 || -n "${HYDRA_UMC_RECOVERY_ROOT:-}" ]] || { echo "Run as root with sudo." >&2; exit 2; }

echo " ==============================================================="
echo "  HYDRA-UMC-OS - cm5_recovery.sh"
echo "  Backs up or restores only HYDRA-UMC configuration and state."
echo "  Copyright (C) 2026 JuanenRac (Electro Hobby 3D)"
echo "  <electrohobby3d@gmail.com> | GPL-3.0-or-later - see LICENSE"
echo " ==============================================================="
if [[ "$APPLY" != --apply ]]; then
  echo "[dry-run] $ACTION $ARCHIVE"
  echo "No files or services will be changed. Re-run with --apply after review."
  exit 0
fi

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCOPE="$HERE/recovery_scope.py"
[[ -f "$SCOPE" ]] || { echo "recovery_scope.py is missing next to this script." >&2; exit 2; }
command -v python3 >/dev/null || { echo "python3 is required (it computes the scope and copies the databases)." >&2; exit 2; }
# HYDRA_UMC_RECOVERY_ROOT names another root (the tests use it); on a device it is /.
RECOVERY_ROOT="${HYDRA_UMC_RECOVERY_ROOT:-/}"

if [[ "$ACTION" == backup ]]; then
  install -d -m 0700 "$(dirname "$ARCHIVE")"
  # The scope is what is installed (configuration, state, the data folder of every program, units, polkit rules), not a fixed list.
  mapfile -t PATHS < <(python3 "$SCOPE" list --root "$RECOVERY_ROOT")
  STAGE="$(mktemp -d)"
  PLAIN="$(mktemp)"
  trap 'rm -rf "$STAGE"; rm -f "$PLAIN"' EXIT
  # SQLite databases: a consistent copy of each one (the backup API), never the live file that a service may be writing.
  mapfile -t STAGED < <(python3 "$SCOPE" snapshot --root "$RECOVERY_ROOT" --stage "$STAGE")
  EXCLUDES=()
  while IFS= read -r live; do [[ -n "$live" ]] && EXCLUDES+=("--exclude=$live"); done < <(python3 "$SCOPE" live-db-files --root "$RECOVERY_ROOT")
  [[ ${#PATHS[@]} -gt 0 && -n "${PATHS[0]}" ]] || { echo "Nothing of HYDRA-UMC is installed under $RECOVERY_ROOT: nothing to back up." >&2; exit 2; }
  tar --create --force-local --file "$PLAIN" --numeric-owner --ignore-failed-read "${EXCLUDES[@]}" -C "$RECOVERY_ROOT" "${PATHS[@]}"
  if [[ ${#STAGED[@]} -gt 0 && -n "${STAGED[0]}" ]]; then
    tar --append --force-local --file "$PLAIN" --numeric-owner -C "$STAGE" "${STAGED[@]}"
  fi
  gzip -c "$PLAIN" >"$ARCHIVE"
  chmod 0600 "$ARCHIVE"
  echo "CM5_RECOVERY=PASS action=backup archive=$ARCHIVE paths=${#PATHS[@]} databases=${#STAGED[@]}"
  exit 0
fi

[[ -f "$ARCHIVE" ]] || { echo "Archive not found: $ARCHIVE" >&2; exit 2; }
LISTING="$(tar --list --force-local --gzip --file "$ARCHIVE")"
if ! printf '%s\n' "$LISTING" | python3 "$SCOPE" check-members; then
  echo "Refusing the archive (see the reason above)." >&2
  exit 2
fi
# Every running HYDRA-UMC service is stopped before its files are replaced (the databases most of all); none is started again here.
if command -v systemctl >/dev/null 2>&1; then
  systemctl list-units 'hydra-umc-*.service' --state=active --no-legend --plain 2>/dev/null | awk '{print $1}' | xargs -r systemctl stop 2>/dev/null || true
fi
# A -wal or -shm file left by the old database would be replayed over the restored one.
printf '%s\n' "$LISTING" | python3 "$SCOPE" drop-sidecars --root "$RECOVERY_ROOT"
tar --extract --force-local --gzip --file "$ARCHIVE" --numeric-owner -C "$RECOVERY_ROOT"
if command -v systemctl >/dev/null 2>&1; then systemctl daemon-reload; fi
echo "CM5_RECOVERY=PASS action=restore archive=$ARCHIVE services=stopped"
echo "Review configuration, then enable services manually and run verify_cm5_runtime.sh."
