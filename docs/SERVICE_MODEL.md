# Service model

HYDRA-UMC services run as dedicated least-privilege users where practical.
They receive configuration from `/etc/hydra-umc/`, persist non-secret state
under `/var/lib/hydra-umc/`, and report through structured logs and health
contracts.

Every future unit must declare dependencies, restart policy, writable paths,
and a readiness/health mechanism. The reference ordering is:

```text
network-online -> hydra-umc-agent -> adapter/collector -> server -> UI
```

Optional services must not prevent a control profile from reporting the real
state of its MCU. A crashed dashboard is not a safety fault; a failed MCU
handshake is.

## The service registry and the health route

`provisioning/ports.yaml` is the registry of the services of the family: the port, the health route and the
systemd unit of each. It is a copy of `HYDRA-UMC-SDK/contracts/ports.yaml`, which is generated from the `service`
block of each project manifest and kept identical in this repository by the SDK (`python tools/sync_repo_tools.py`).
Nothing here edits it by hand.

* Every installer of a service sources `provisioning/service_registry.sh` and ends by saying where to look once the
  service runs (`announce_health`): `curl --fail http://127.0.0.1:<port><health route>`. A service with no HTTP route
  on its port (the MQTT broker and the OPC-UA server) says so instead.
* `verify_cm5_runtime.sh --with-services` goes through the registry, skips what is not running, and fails for a
  running service whose health route does not answer. It stays read-only.
* Every service that speaks HTTP declares its health route in its own manifest. A service that has a status route
  (`/stats`) and no `/health` declares the status route; the page of the dashboard is its own health route (`/`). A new
  service declares `GET /health` in its manifest and in its code, answering 200 with a small JSON document.
* `tools/verify_service_registry.py` checks the helper, that each installer announces the service it installs, that
  the unit each installer copies is the one the registry names, that the copy is the one of the SDK, and the
  runtime check against stubs of `systemctl` and `curl`.

## Implemented base agent

`systemd/hydra-umc-agent.service` launches `hydra-umc-agent` as the dedicated
non-login `hydra-umc-agent` user. The executable code and configuration remain
root-owned; only `/var/lib/hydra-umc/` is writable by the service. It has no
privilege escalation, capabilities, personality changes, private temporary
storage, and a read-only system view except for that designated state
directory. The agent currently emits `DeviceDescriptor` and `HealthReport`
JSON documents. It does not open an MCU, CAN, motion, or update control path. See
[AGENT_REFERENCE.md](AGENT_REFERENCE.md) for the full CLI/JSON reference.
