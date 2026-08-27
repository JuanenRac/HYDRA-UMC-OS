#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - Read-only installed CM5 runtime verification
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Inspects an installed node; it never starts/stops services or writes files.
set -euo pipefail

WITH_SERVER=false
[[ "${1:-}" == "--with-server" ]] && WITH_SERVER=true
[[ -z "${2:-}" ]] || { echo "Usage: $0 [--with-server]" >&2; exit 2; }
failures=0
check() { if "$@"; then echo "RUNTIME_CHECK=PASS $*"; else echo "RUNTIME_CHECK=FAIL $*" >&2; failures=$((failures + 1)); fi; }
check_test() { if eval "$1"; then echo "RUNTIME_CHECK=PASS $2"; else echo "RUNTIME_CHECK=FAIL $2" >&2; failures=$((failures + 1)); fi; }

echo " ==============================================================="
echo "  HYDRA-UMC-OS - verify_cm5_runtime.sh"
echo "  Read-only service, permission and local API verification."
echo "  Copyright (C) 2026 JuanenRac (Electro Hobby 3D)"
echo "  <electrohobby3d@gmail.com> | GPL-3.0-or-later - see LICENSE"
echo " ==============================================================="
check id hydra-umc-agent
check_test 'test "$(getent passwd hydra-umc-agent | cut -d: -f7)" = /usr/sbin/nologin' 'agent is non-login'
check_test 'test "$(stat -c %U:%G:%a /etc/hydra-umc/config.json 2>/dev/null)" = root:hydra-umc-agent:640' 'restricted agent configuration ownership'
check systemctl is-active --quiet hydra-umc-agent
if agent_json=$(/usr/local/bin/hydra-umc-agent --config /etc/hydra-umc/config.json health 2>/dev/null); then
  if python3 -c 'import json,sys; report=json.load(sys.stdin); sys.exit(0 if report.get("state") in {"READY", "DEGRADED"} else 1)' <<<"$agent_json"; then
    echo "RUNTIME_CHECK=PASS agent health is READY or DEGRADED"
  else
    echo "RUNTIME_CHECK=FAIL agent health is FAULT or malformed" >&2; failures=$((failures + 1))
  fi
else
  echo "RUNTIME_CHECK=FAIL agent health command" >&2; failures=$((failures + 1))
fi

if $WITH_SERVER; then
  check id hydra-umc-server
  check systemctl is-active --quiet hydra-umc-server
  check_test 'test "$(stat -c %U:%G:%a /etc/hydra-umc/server.env 2>/dev/null)" = root:hydra-umc-server:640' 'restricted server environment ownership'
  if server_json=$(curl --fail --silent --show-error --max-time 5 http://127.0.0.1:3000/api/hydra-info); then
    if python3 -c 'import json,sys; value=json.load(sys.stdin); sys.exit(0 if value.get("product") == "server" and value.get("remoteApiVersion", 0) >= 1 else 1)' <<<"$server_json"; then
      echo "RUNTIME_CHECK=PASS local Server discovery endpoint"
    else
      echo "RUNTIME_CHECK=FAIL local Server discovery payload" >&2; failures=$((failures + 1))
    fi
  else
    echo "RUNTIME_CHECK=FAIL local Server discovery endpoint" >&2; failures=$((failures + 1))
  fi
fi

if (( failures > 0 )); then
  echo "CM5_RUNTIME=FAIL failures=$failures" >&2
  exit 1
fi
echo "CM5_RUNTIME=PASS profile=$($WITH_SERVER && printf control || printf base) changes=none"
