#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - build_hooks/node-healing.sh
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Fetches the pinned Go toolchain when it is missing, builds the program and sets up its optional journal.
# Sourced by provisioning/install_node_healing.sh as root, after the service user and $TARGET exist and before the shared copy step;
# never run on its own. Uses $ROOT, $SOURCE, $TARGET, $SVC_USER and $HERE of the installer. Safe to run again.

[[ -f "$SOURCE/go.mod" ]] || { echo "HYDRA-UMC-NODE-HEALING source is incomplete: $SOURCE" >&2; exit 2; }
source "$HERE/go_toolchain.sh"
ensure_go
( cd "$SOURCE" && "$GO_BIN" build -o "$TARGET/hydra-umc-node-healing" . )
chown root:root "$TARGET/hydra-umc-node-healing"
chmod 0755 "$TARGET/hydra-umc-node-healing"
install -d -o root -g root -m 0755 /etc/hydra-umc-node-healing
JOURNAL_ENV=/etc/hydra-umc-node-healing/journal.env
JOURNAL_LINE="HYDRA_UMC_NODE_HEALING_JOURNAL_ARGS=--journal /var/lib/hydra-umc-node-healing/journal.jsonl"
if [[ ! -f "$JOURNAL_ENV" ]]; then
  cat >"$JOURNAL_ENV" <<EOF
# Read by systemd (as root) for hydra-umc-node-healing.service. The journal is ON while the next line is active (it
# is rotated at 5 MiB, 5 files kept). To turn it off put a # in front of it (or install_node_healing.sh --no-journal),
# then: systemctl restart hydra-umc-node-healing
# Check it with: /opt/hydra-umc/node-healing/hydra-umc-node-healing -journal /var/lib/hydra-umc-node-healing/journal.jsonl -journal-verify
# $JOURNAL_LINE
EOF
  chmod 0644 "$JOURNAL_ENV"
fi
if [[ "$JOURNAL" == "on" ]]; then
  # the unit runs as its own account: the state directory it writes the journal in belongs to it (StateDirectory= in the unit also creates it)
  if grep -q '^HYDRA_UMC_NODE_HEALING_JOURNAL_ARGS=' "$JOURNAL_ENV"; then
    echo "The journal setting is already in $JOURNAL_ENV (left as it is)."
  else
    echo "$JOURNAL_LINE" >>"$JOURNAL_ENV"
    echo "Journal ON, rotated at 5 MiB (restart the service for it to take effect)."
  fi
else
  # the operator asked for no journal: take an active line out (a comment saying why stays), and never delete what was recorded
  if grep -q '^HYDRA_UMC_NODE_HEALING_JOURNAL_ARGS=' "$JOURNAL_ENV"; then
    sed -i 's|^\(HYDRA_UMC_NODE_HEALING_JOURNAL_ARGS=.*\)$|# switched off by install_node_healing.sh --no-journal: \1|' "$JOURNAL_ENV"
  fi
  echo "Journal: OFF (--no-journal). To switch it on: rerun without --no-journal, or edit $JOURNAL_ENV. Records already written are kept."
fi

hook_after_install() {
  echo "Not enabled: this binary refuses to run with zero nodes to watch, and no real"
  echo "HealthService-speaking node exists on this CM5 yet. Once one does:"
  echo "  cp $SOURCE/nodes.example.json /etc/hydra-umc-node-healing/nodes.json"
  echo "  \$EDITOR /etc/hydra-umc-node-healing/nodes.json     # point at real node(s)"
  echo "  systemctl enable --now hydra-umc-node-healing"
}
