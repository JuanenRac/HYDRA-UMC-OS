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
[[ $EUID -eq 0 ]] || { echo "Run as root with sudo." >&2; exit 2; }

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

if [[ "$ACTION" == backup ]]; then
  install -d -m 0700 "$(dirname "$ARCHIVE")"
  tar --create --gzip --file "$ARCHIVE" --numeric-owner --ignore-failed-read -C / \
    etc/hydra-umc var/lib/hydra-umc opt/hydra-umc/server/data \
    etc/systemd/system/hydra-umc-agent.service etc/systemd/system/hydra-umc-server.service
  chmod 0600 "$ARCHIVE"
  echo "CM5_RECOVERY=PASS action=backup archive=$ARCHIVE"
  exit 0
fi

[[ -f "$ARCHIVE" ]] || { echo "Archive not found: $ARCHIVE" >&2; exit 2; }
if tar --list --gzip --file "$ARCHIVE" | grep -Eq '(^/|(^|/)\.\.(/|$))'; then
  echo "Refusing archive with unsafe paths." >&2
  exit 2
fi
if tar --list --gzip --file "$ARCHIVE" | grep -Ev '^(etc/hydra-umc|var/lib/hydra-umc|opt/hydra-umc/server/data|etc/systemd/system/hydra-umc-(agent|server)\.service)(/|$)' | grep -q .; then
  echo "Refusing archive with paths outside HYDRA-UMC recovery scope." >&2
  exit 2
fi
systemctl stop hydra-umc-server hydra-umc-agent 2>/dev/null || true
tar --extract --gzip --file "$ARCHIVE" --numeric-owner -C /
systemctl daemon-reload
echo "CM5_RECOVERY=PASS action=restore archive=$ARCHIVE services=stopped"
echo "Review configuration, then enable services manually and run verify_cm5_runtime.sh."
