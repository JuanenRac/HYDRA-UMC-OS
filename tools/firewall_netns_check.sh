#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - The host firewall loaded for real into network namespaces
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
#
# provisioning/hydra_firewall.sh prints nftables rules; tools/verify_firewall.py proves the text. This script loads those rules into the kernel of a Linux machine
# (a CI runner), inside a network namespace that plays the CM5, and connects to its ports from three other namespaces that play the field network, the clients'
# network and an outsider. It shows what the rules do to real packets. It changes nothing outside the namespaces it creates and removes them at the end.
#
# Needs root (ip netns, nft, python3). Nothing here has run on a CM5: it proves the rules in a kernel's nftables, not the CM5's own network or its Docker.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$HERE/../provisioning/hydra_firewall.sh"
[[ "$(id -u)" == "0" ]] || { echo "firewall_netns_check: run it as root" >&2; exit 2; }
for tool in ip nft python3 bash; do command -v "$tool" >/dev/null 2>&1 || { echo "firewall_netns_check: $tool is not installed" >&2; exit 2; }; done

HOST=hy_host; FIELD=hy_field; CLIENT=hy_client; OUTSIDER=hy_out
PIDS=()
FAILURES=0

cleanup() {
  local pid
  for pid in "${PIDS[@]+"${PIDS[@]}"}"; do kill "$pid" 2>/dev/null || true; done
  local ns
  for ns in "$HOST" "$FIELD" "$CLIENT" "$OUTSIDER"; do ip netns del "$ns" 2>/dev/null || true; done
}
trap cleanup EXIT

for ns in "$HOST" "$FIELD" "$CLIENT" "$OUTSIDER"; do ip netns del "$ns" 2>/dev/null || true; ip netns add "$ns"; ip -n "$ns" link set lo up; done

# link <short> <peer namespace> <network prefix>: the host reaches the peer over <prefix>.0/24; host side .1, peer side .2
link() {
  local short="$1" peer="$2" prefix="$3"
  ip link add "v${short}h" type veth peer name "v${short}p"
  ip link set "v${short}h" netns "$HOST"
  ip link set "v${short}p" netns "$peer"
  ip -n "$HOST" addr add "${prefix}.1/24" dev "v${short}h"
  ip -n "$peer" addr add "${prefix}.2/24" dev "v${short}p"
  ip -n "$HOST" link set "v${short}h" up
  ip -n "$peer" link set "v${short}p" up
}
link f "$FIELD" 192.168.0
link c "$CLIENT" 192.168.10
link o "$OUTSIDER" 172.16.0

# a listener on every port the table talks about, and on one it does not (the stand-in for SSH)
LISTENER='import socket, sys
servers = []
for port in map(int, sys.argv[1:]):
    s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); s.bind(("0.0.0.0", port)); s.listen(16); servers.append(s)
import selectors
sel = selectors.DefaultSelector()
for s in servers: sel.register(s, selectors.EVENT_READ)
while True:
    for key, _ in sel.select():
        conn, _ = key.fileobj.accept(); conn.close()'
ip netns exec "$HOST" python3 -c "$LISTENER" 1883 8883 3000 2222 3100 11883 18883 &
PIDS+=("$!")
sleep 1

# reach <namespace> <address> <port>: prints open or blocked
reach() {
  ip netns exec "$1" python3 -c '
import socket, sys
s = socket.socket(); s.settimeout(1.5)
try:
    s.connect((sys.argv[1], int(sys.argv[2]))); print("open")
except Exception:
    print("blocked")' "$2" "$3"
}

# expect <label> <namespace> <address> <port> <open|blocked>
expect() {
  local got
  got="$(reach "$2" "$3" "$4")"
  if [[ "$got" == "$5" ]]; then echo "PASS  $1: $5"; else echo "FAIL  $1: expected $5, got $got"; FAILURES=$((FAILURES + 1)); fi
}

load() { ip netns exec "$HOST" nft delete table inet hydra_core 2>/dev/null || true; bash "$SCRIPT" print "$@" | ip netns exec "$HOST" nft -f -; }

echo "== before any rule: everything answers"
expect "outsider reaches the broker" "$OUTSIDER" 172.16.0.1 1883 open
expect "clients reach the server" "$CLIENT" 192.168.10.1 3000 open

echo "== --field 192.168.0.0/24 --clients 192.168.10.0/24"
load --field 192.168.0.0/24 --clients 192.168.10.0/24
expect "field reaches the broker" "$FIELD" 192.168.0.1 1883 open
expect "field reaches the broker over TLS" "$FIELD" 192.168.0.1 8883 open
expect "clients do not reach the broker" "$CLIENT" 192.168.10.1 1883 blocked
expect "clients do not reach the broker over TLS" "$CLIENT" 192.168.10.1 8883 blocked
expect "outsider does not reach the broker" "$OUTSIDER" 172.16.0.1 1883 blocked
expect "clients reach the server" "$CLIENT" 192.168.10.1 3000 open
expect "field does not reach the server" "$FIELD" 192.168.0.1 3000 blocked
expect "outsider does not reach the server" "$OUTSIDER" 172.16.0.1 3000 blocked
expect "a port the table never mentions stays open to the outsider" "$OUTSIDER" 172.16.0.1 2222 open
expect "the machine itself reaches the broker" "$HOST" 127.0.0.1 1883 open

echo "== --field only: the server keeps the openness it had"
load --field 192.168.0.0/24
expect "outsider still reaches the server" "$OUTSIDER" 172.16.0.1 3000 open
expect "outsider does not reach the broker" "$OUTSIDER" 172.16.0.1 1883 blocked

echo "== other ports"
load --field 192.168.0.0/24 --clients 192.168.10.0/24 --mqtt-port 11883 --mqtt-tls-port 18883 --server-port 3100
expect "the default broker port is no longer ruled" "$OUTSIDER" 172.16.0.1 1883 open
expect "the server on its own port is closed to the field" "$FIELD" 192.168.0.1 3100 blocked

echo "== removing the table gives everything back"
ip netns exec "$HOST" nft delete table inet hydra_core
expect "outsider reaches the broker again" "$OUTSIDER" 172.16.0.1 1883 open
expect "field reaches the server again" "$FIELD" 192.168.0.1 3000 open

if (( FAILURES > 0 )); then echo "FIREWALL_NETNS=FAIL failures=$FAILURES"; exit 1; fi
echo "FIREWALL_NETNS=PASS"
