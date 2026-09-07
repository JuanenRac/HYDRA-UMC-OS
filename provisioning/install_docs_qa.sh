#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - Install HYDRA-UMC-DOCS-QA as a local CM5 API
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Real gap found auditing the ecosystem against actual CM5 hardware:
# HYDRA-UMC-DOCS-QA's real TF-IDF retrieval (index.py, ingest.py) was
# only ever reachable as a one-shot CLI that re-ingests and re-indexes
# its corpus on EVERY invocation - fine for a single command, wasteful
# for a service. api.py (new) builds the real TfidfIndex ONCE at server
# startup and reuses it for every query. Same simple "copy src/ +
# PYTHONPATH" shape as install_datalake.sh, no venv/pip needed at
# runtime - plus this repo's own README.md/CHANGELOG.md, the default
# corpus main.py's own _DEFAULT_DOCS points at.
set -euo pipefail
[[ "${1:-}" == "--apply" ]] || { echo "Dry-run policy: rerun with --apply after review."; exit 0; }
[[ $EUID -eq 0 ]] || { echo "Run as root with sudo." >&2; exit 2; }

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SOURCE="$ROOT/HYDRA-UMC-DOCS-QA"
TARGET=/opt/hydra-umc/docs-qa
QA_USER="hydra-umc-docs-qa"

echo " ==============================================================="
echo "  HYDRA-UMC-OS - install_docs_qa.sh"
echo "  Installs the real TF-IDF documentation-retrieval API."
echo "  Copyright (C) 2026 JuanenRac (Electro Hobby 3D)"
echo "  <electrohobby3d@gmail.com> | GPL-3.0-or-later - see LICENSE"
echo " ==============================================================="

[[ -d "$SOURCE/src/hydra_umc_docs_qa" && -f "$SOURCE/systemd/hydra-umc-docs-qa.service" ]] || {
  echo "HYDRA-UMC-DOCS-QA source or systemd unit is incomplete: $SOURCE" >&2; exit 2;
}
command -v python3 >/dev/null || { echo "HYDRA-UMC-DOCS-QA requires python3." >&2; exit 2; }
if ! id -u "$QA_USER" >/dev/null 2>&1; then
  useradd --system --home "$TARGET" --no-create-home --shell /usr/sbin/nologin "$QA_USER"
fi
install -d -o root -g root -m 0755 "$TARGET"
rm -rf "$TARGET/src"
cp -a "$SOURCE/src" "$TARGET/"
# main.py's own _DEFAULT_DOCS (used when the unit's ExecStart passes no
# --docs) resolves to this repo's own README.md/CHANGELOG.md two levels
# above src/ - copy those two files alongside src/ so that default
# actually resolves to something real once deployed, not a missing path.
install -m 0644 "$SOURCE/README.md" "$SOURCE/CHANGELOG.md" "$TARGET/"
chown -R root:root "$TARGET/src" "$TARGET/README.md" "$TARGET/CHANGELOG.md"
chmod -R go-w "$TARGET/src"
install -m 0644 "$SOURCE/systemd/hydra-umc-docs-qa.service" /etc/systemd/system/hydra-umc-docs-qa.service
systemctl daemon-reload
echo "Docs-QA installed, serving its own README.md/CHANGELOG.md as a demo corpus."
echo "Enable manually after review: systemctl enable --now hydra-umc-docs-qa"
