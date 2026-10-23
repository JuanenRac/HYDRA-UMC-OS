#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - Install HYDRA-UMC-NODE-HEALING as a local CM5 watchdog
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Real gap found auditing the ecosystem against actual CM5 hardware:
# HYDRA-UMC-NODE-HEALING already has a real watchdog loop (src/watchdog,
# src/config - see its own main.go) - never built or installed anywhere.
#
# Installs the CAPABILITY only, same as install_vision_streamer.sh - does
# NOT create a registry or enable/start the service. Real, live-verified
# constraint: config.LoadNodes() itself refuses an empty registry
# ("node registry ... is empty - nothing to watch"), so "watch zero
# nodes" (this script's own first, wrong attempt) is not a state this
# binary can actually run in - and this repo's own nodes.example.json
# names HealthService gRPC endpoints for HYDRA-UMC-ORCHESTRATOR/
# VISION-NODE/COGNITIVE-NODE, none of which run as a real service on this
# CM5 yet (real, separate future work), so seeding the real example file
# would only ever report every node UNREACHABLE. There is genuinely
# nothing for this watchdog to watch yet - see the printed instructions
# below for what to do once that changes.
#
# The registry belongs OUTSIDE the shared /etc/hydra-umc/ tree: that tree
# is 0750 root:hydra-umc-agent (see install_local_agent.sh), and this
# service's own unprivileged account is a member of neither, so it could
# never actually traverse into it to open its own config file - real bug
# found live on this device's first install (systemd's own
# EnvironmentFile= directive, used by other services under
# /etc/hydra-umc/, is read by systemd itself as root before it drops
# privileges; a plain os.Open() by this service's own process is not).
set -euo pipefail
# The journal (an append-only, hash-chained record of every transition and recovery request) is OFF by default.
# `--journal` (or HYDRA_UMC_NODE_HEALING_JOURNAL=on) switches it on; so does putting
#   HYDRA_UMC_NODE_HEALING_JOURNAL_ARGS=--journal /var/lib/hydra-umc-node-healing/journal.jsonl
# in /etc/hydra-umc-node-healing/journal.env by hand, and restarting the service.
APPLY=0
JOURNAL="${HYDRA_UMC_NODE_HEALING_JOURNAL:-off}"
for arg in "$@"; do
  case "$arg" in
    --apply) APPLY=1 ;;
    --journal) JOURNAL=on ;;
    *) echo "Unknown option: $arg (use --apply and, optionally, --journal)" >&2; exit 2 ;;
  esac
done
[[ "$JOURNAL" == "on" || "$JOURNAL" == "off" ]] || { echo "HYDRA_UMC_NODE_HEALING_JOURNAL must be on or off." >&2; exit 2; }
[[ $APPLY -eq 1 ]] || { echo "Dry-run policy: rerun with --apply after review (add --journal to switch the journal on)."; exit 0; }
[[ $EUID -eq 0 ]] || { echo "Run as root with sudo." >&2; exit 2; }

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SOURCE="$ROOT/HYDRA-UMC-NODE-HEALING"
TARGET=/opt/hydra-umc/node-healing
HEALING_USER="hydra-umc-node-healing"

echo " ==============================================================="
echo "  HYDRA-UMC-OS - install_node_healing.sh"
echo "  Installs the real HydraNode watchdog (Go, builds on-device)."
echo "  Copyright (C) 2026 JuanenRac (Electro Hobby 3D)"
echo "  <electrohobby3d@gmail.com> | GPL-3.0-or-later - see LICENSE"
echo " ==============================================================="

[[ -f "$SOURCE/go.mod" && -f "$SOURCE/systemd/hydra-umc-node-healing.service" ]] || {
  echo "HYDRA-UMC-NODE-HEALING source or systemd unit is incomplete: $SOURCE" >&2; exit 2;
}
if ! command -v go >/dev/null; then
  apt-get update
  apt-get install -y golang-go
fi
command -v go >/dev/null || { echo "golang-go installed but 'go' still not on PATH." >&2; exit 2; }

if ! id -u "$HEALING_USER" >/dev/null 2>&1; then
  useradd --system --home "$TARGET" --no-create-home --shell /usr/sbin/nologin "$HEALING_USER"
fi
install -d -o root -g root -m 0755 "$TARGET"
( cd "$SOURCE" && go build -o "$TARGET/hydra-umc-node-healing" . )
chown root:root "$TARGET/hydra-umc-node-healing"
chmod 0755 "$TARGET/hydra-umc-node-healing"
install -d -o root -g root -m 0755 /etc/hydra-umc-node-healing
JOURNAL_ENV=/etc/hydra-umc-node-healing/journal.env
JOURNAL_LINE="HYDRA_UMC_NODE_HEALING_JOURNAL_ARGS=--journal /var/lib/hydra-umc-node-healing/journal.jsonl"
if [[ ! -f "$JOURNAL_ENV" ]]; then
  cat >"$JOURNAL_ENV" <<EOF
# Read by systemd (as root) for hydra-umc-node-healing.service. The journal is OFF while the next line is a comment
# or this file is empty. To switch it on remove the #, then: systemctl restart hydra-umc-node-healing
# Check it with: /opt/hydra-umc/node-healing/hydra-umc-node-healing -journal /var/lib/hydra-umc-node-healing/journal.jsonl -journal-verify
# $JOURNAL_LINE
EOF
  chmod 0644 "$JOURNAL_ENV"
fi
if [[ "$JOURNAL" == "on" ]]; then
  if grep -q '^HYDRA_UMC_NODE_HEALING_JOURNAL_ARGS=' "$JOURNAL_ENV"; then
    echo "The journal setting is already in $JOURNAL_ENV (left as it is)."
  else
    echo "$JOURNAL_LINE" >>"$JOURNAL_ENV"
    echo "Journal switched ON (restart the service for it to take effect)."
  fi
else
  echo "Journal: off (default). To switch it on later: rerun with --journal, or edit $JOURNAL_ENV."
fi
install -m 0644 "$SOURCE/systemd/hydra-umc-node-healing.service" /etc/systemd/system/hydra-umc-node-healing.service
# Real bug found live: every install_*.sh here updated the deployed
# build/binary but never this project's OWN hydra-umc.project.json -
# GET /api/ecosystem/status (STUDIO's own Services/AI Family panels)
# reads THIS file for name/version/maturity/family, so every one of
# them kept reporting whatever version happened to be here from the
# very first install, forever, no matter how many real updates
# followed. Copied last, right before the reload, so it always
# reflects the exact SOURCE that was actually just installed.
install -m 0644 "$SOURCE/hydra-umc.project.json" "$TARGET/hydra-umc.project.json"
systemctl daemon-reload
echo "Node-Healing capability installed (not enabled - see this script's own header)."
echo "This binary refuses to run with zero nodes to watch, and no real"
echo "HealthService-speaking node exists on this CM5 yet. Once one does:"
echo "  cp $SOURCE/nodes.example.json /etc/hydra-umc-node-healing/nodes.json"
echo "  \$EDITOR /etc/hydra-umc-node-healing/nodes.json     # point at real node(s)"
echo "  systemctl enable --now hydra-umc-node-healing"
