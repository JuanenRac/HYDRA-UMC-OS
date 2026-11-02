#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - build_hooks/node-healing.preflight.sh
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Reads and checks the options of install_node_healing.sh before the dry-run policy and the root check, so that a wrong option is refused
# even in a dry run. Sourced by the installer with its arguments; sets JOURNAL (on or off) and DRY_RUN_NOTE.

JOURNAL="${HYDRA_UMC_NODE_HEALING_JOURNAL:-on}"
for arg in "$@"; do
  case "$arg" in
    --apply) ;;
    --journal) JOURNAL=on ;;
    --no-journal) JOURNAL=off ;;
    *) echo "Unknown option: $arg (use --apply and, optionally, --no-journal)" >&2; exit 2 ;;
  esac
done
[[ "$JOURNAL" == "on" || "$JOURNAL" == "off" ]] || { echo "HYDRA_UMC_NODE_HEALING_JOURNAL must be on or off." >&2; exit 2; }
DRY_RUN_NOTE=" (the journal is switched ON unless you add --no-journal)"
