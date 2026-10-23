#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - The service registry, for the installers and the runtime check
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Sourced, never run. It reads the port, the health route and the systemd unit of a
# service from provisioning/ports.yaml, which is a copy of HYDRA-UMC-SDK/contracts/ports.yaml
# kept identical by the SDK (python tools/sync_repo_tools.py); the registry itself is generated from
# the `service` block of each project manifest. HYDRA_UMC_PORTS_REGISTRY names another file
# (a test uses it).
#
#   service_field NAME port|health_path|systemd_unit  prints the value; returns 1 when the service
#                                                     is unknown or the value is null
#   registry_services                                 prints every service name
#   announce_health NAME                              says where to look once the service runs
#
# Nothing here changes the system: every function only reads the registry and prints.

HYDRA_PORTS_REGISTRY="${HYDRA_UMC_PORTS_REGISTRY:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/ports.yaml}"

service_field() {
  local value
  [[ -r "$HYDRA_PORTS_REGISTRY" ]] || return 1
  value="$(awk -v name="$1" -v field="$2" '
    $1 == "-" && $2 == "name:" { current = $3; next }
    current == name && $1 == field ":" { print $2; exit }
  ' "$HYDRA_PORTS_REGISTRY")"
  [[ -n "$value" && "$value" != "null" ]] || return 1
  printf '%s\n' "$value"
}

registry_services() {
  [[ -r "$HYDRA_PORTS_REGISTRY" ]] || return 1
  awk '$1 == "-" && $2 == "name:" { print $3 }' "$HYDRA_PORTS_REGISTRY"
}

announce_health() {
  local name="$1" port health
  if ! port="$(service_field "$name" port)"; then
    echo "Health: $name is not in the service registry ($HYDRA_PORTS_REGISTRY)." >&2
    return 0
  fi
  if health="$(service_field "$name" health_path)"; then
    echo "Health, once enabled: curl --fail http://127.0.0.1:${port}${health}"
  else
    echo "Health: $name listens on port ${port} and has no HTTP route to probe."
  fi
}
