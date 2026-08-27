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

## Implemented base agent

`systemd/hydra-umc-agent.service` launches `hydra-umc-agent` as the dedicated
`hydra-umc` user. It has no privilege escalation, private temporary storage,
and a read-only system view except for its designated state directory. The
agent currently emits `DeviceDescriptor` and `HealthReport` JSON documents.
It does not open an MCU, CAN, motion, or update control path.
