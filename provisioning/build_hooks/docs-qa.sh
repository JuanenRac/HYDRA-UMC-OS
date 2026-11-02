#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - build_hooks/docs-qa.sh
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Checks the source and installs the README and CHANGELOG that the retrieval API serves as its demonstration corpus.
# Sourced by provisioning/install_docs_qa.sh as root, after the service user and $TARGET exist and before the shared copy step;
# never run on its own. Uses $ROOT, $SOURCE, $TARGET, $SVC_USER and $HERE of the installer. Safe to run again.

[[ -d "$SOURCE/src/hydra_umc_docs_qa" ]] || { echo "HYDRA-UMC-DOCS-QA source is incomplete: $SOURCE" >&2; exit 2; }
command -v python3 >/dev/null || { echo "HYDRA-UMC-DOCS-QA requires python3." >&2; exit 2; }
install -m 0644 -o root -g root "$SOURCE/README.md" "$SOURCE/CHANGELOG.md" "$TARGET/"

hook_after_install() {
  echo "Serving its own README.md/CHANGELOG.md as a demo corpus."
}
