#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - Install HYDRA-UMC-LOCAL-TECHNICIAN on the CM5
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Real gap found live: HYDRA-UMC-LOCAL-TECHNICIAN (family "Cognitive AI
# Node", parent HYDRA-UMC-COGNITIVE-NODE) has a real, tested CLI
# (`hydra-umc-local-technician`, see its own pyproject.toml
# [project.scripts]) but was never installed anywhere on this device,
# so it never showed up in STUDIO's own AI Family panel at all - not
# stale, genuinely invisible. Unlike every other project this repo
# installs, it declares no `service` block in its own manifest and has
# no systemd unit of its own (Fase 0 of six - a bounded, policy-gated
# CLI technician, not a standing daemon yet, see its own README
# Roadmap) - this script only ever drops its real source + manifest at
# a real host path, the same one every other project's manifest lives
# at, so GET /api/ecosystem/status's own discovery picks it up and
# reports it honestly as "not a service" (live: null), matching the
# same convention every other CLI/library-shaped project here already
# gets.
set -euo pipefail
# The audit journal (an append-only, hash-chained record of every tool request) is OFF by default. It is
# switched on by `--audit` (or HYDRA_UMC_LOCAL_TECHNICIAN_AUDIT=on), or later by hand: put
#   HYDRA_UMC_LOCAL_TECHNICIAN_AUDIT_LOG=/var/lib/hydra-umc-local-technician/audit.jsonl
# in /etc/hydra-umc-local-technician/local-technician.env (the CLI reads that file when it starts).
APPLY=0
AUDIT="${HYDRA_UMC_LOCAL_TECHNICIAN_AUDIT:-off}"
for arg in "$@"; do
  case "$arg" in
    --apply) APPLY=1 ;;
    --audit) AUDIT=on ;;
    *) echo "Unknown option: $arg (use --apply and, optionally, --audit)" >&2; exit 2 ;;
  esac
done
[[ "$AUDIT" == "on" || "$AUDIT" == "off" ]] || { echo "HYDRA_UMC_LOCAL_TECHNICIAN_AUDIT must be on or off." >&2; exit 2; }
[[ $APPLY -eq 1 ]] || { echo "Dry-run policy: rerun with --apply after review (add --audit to switch the audit journal on)."; exit 0; }
[[ $EUID -eq 0 ]] || { echo "Run as root with sudo." >&2; exit 2; }

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SOURCE="$ROOT/HYDRA-UMC-LOCAL-TECHNICIAN"
TARGET=/opt/hydra-umc/local-technician

echo " ==============================================================="
echo "  HYDRA-UMC-OS - install_local_technician.sh"
echo "  Installs the real, policy-gated local AI technician CLI."
echo "  Copyright (C) 2026 JuanenRac (Electro Hobby 3D)"
echo "  <electrohobby3d@gmail.com> | GPL-3.0-or-later - see LICENSE"
echo " ==============================================================="

[[ -d "$SOURCE/src/hydra_umc_local_technician" ]] || {
  echo "HYDRA-UMC-LOCAL-TECHNICIAN source is incomplete: $SOURCE" >&2; exit 2;
}
command -v python3 >/dev/null || { echo "HYDRA-UMC-LOCAL-TECHNICIAN requires python3." >&2; exit 2; }

install -d -o root -g root -m 0755 "$TARGET"
rm -rf "$TARGET/src" "$TARGET/contracts"
cp -a "$SOURCE/src" "$TARGET/"
cp -a "$SOURCE/contracts" "$TARGET/"
chown -R root:root "$TARGET/src" "$TARGET/contracts"
chmod -R go-w "$TARGET/src" "$TARGET/contracts"
cat >/usr/local/bin/hydra-umc-local-technician <<'EOF'
#!/usr/bin/env sh
export PYTHONPATH=/opt/hydra-umc/local-technician/src
# optional settings, one NAME=value per line (see the comments in the file itself)
if [ -r /etc/hydra-umc-local-technician/local-technician.env ]; then
  set -a
  . /etc/hydra-umc-local-technician/local-technician.env
  set +a
fi
exec /usr/bin/python3 -m hydra_umc_local_technician.cli "$@"
EOF
chmod 0755 /usr/local/bin/hydra-umc-local-technician

SETTINGS_DIR=/etc/hydra-umc-local-technician
SETTINGS_FILE="$SETTINGS_DIR/local-technician.env"
AUDIT_DIR=/var/lib/hydra-umc-local-technician
AUDIT_LINE="HYDRA_UMC_LOCAL_TECHNICIAN_AUDIT_LOG=$AUDIT_DIR/audit.jsonl"
install -d -o root -g root -m 0755 "$SETTINGS_DIR"
if [[ ! -f "$SETTINGS_FILE" ]]; then
  cat >"$SETTINGS_FILE" <<EOF
# Settings read by /usr/local/bin/hydra-umc-local-technician (NAME=value, no quotes needed).
#
# Audit journal: an append-only, hash-chained JSONL record of every tool request and its outcome; a request
# that cannot be recorded is not run. OFF by default. To switch it on remove the # from the next line (the
# directory must exist and be writable by whoever runs the CLI; install_local_technician.sh --audit makes it):
# $AUDIT_LINE
# Check it with: hydra-umc-local-technician audit-verify
EOF
  chmod 0644 "$SETTINGS_FILE"
fi
if [[ "$AUDIT" == "on" ]]; then
  # only root (sudo) runs the technician on the CM5 today; widen the group by hand if that changes
  install -d -o root -g root -m 0750 "$AUDIT_DIR"
  if grep -q '^HYDRA_UMC_LOCAL_TECHNICIAN_AUDIT_LOG=' "$SETTINGS_FILE"; then
    echo "The audit journal setting is already in $SETTINGS_FILE (left as it is)."
  else
    echo "$AUDIT_LINE" >>"$SETTINGS_FILE"
    echo "Audit journal switched ON: $AUDIT_DIR/audit.jsonl (verify with: hydra-umc-local-technician audit-verify)."
  fi
else
  echo "Audit journal: off (default). To switch it on later: rerun with --audit, or edit $SETTINGS_FILE."
fi
install -m 0644 "$SOURCE/hydra-umc.project.json" "$TARGET/hydra-umc.project.json"
echo "Local-Technician installed - a real CLI (hydra-umc-local-technician), no standing service yet."
echo "Try: hydra-umc-local-technician --help"
