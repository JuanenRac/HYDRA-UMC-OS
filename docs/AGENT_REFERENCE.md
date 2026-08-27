# hydra-umc-agent CLI reference

Real command/output reference for `agent/src/hydra_umc_os/agent.py`, the
read-only CM5 diagnostics agent `systemd/hydra-umc-agent.service` runs
(see [SERVICE_MODEL.md](SERVICE_MODEL.md) for how it fits the rest of
the boot chain). The agent never commands the MCU, moves machinery, or
alters the OS - every command below only reads local state.

```bash
hydra-umc-agent [--config PATH] [--interval SECONDS] {describe|health|serve}
```

- `--config PATH` - a validated, non-secret JSON configuration (`schema_version: "1.0"`, `node.id`, `node.profile`, `diagnostics.minimum_free_bytes`). Defaults to a built-in `DEFAULT_CONFIG` if omitted.
- `--interval SECONDS` - only used by `serve` (default `30.0`): seconds between reports.

Every command prints one pretty-printed JSON document to stdout and exits `0`. `2` on a configuration error (invalid JSON, missing/wrong-typed fields), `0` on `Ctrl-C` during `serve`.

---

## `describe`

Prints a `DeviceDescriptor` - static identity, read once:

```json
{
  "schema_version": "1.0",
  "node_id": "hydra-umc-node",
  "profile": "base",
  "hostname": "cm5-arm-3",
  "machine": "aarch64",
  "operating_system": "Linux",
  "kernel": "6.6.31+rpt-rpi-2712",
  "interfaces": ["eth0", "wlan0"]
}
```

`node_id`/`profile` come from `--config` (or the defaults above). `hostname`/`machine`/`operating_system`/`kernel` are read live via Python's `socket`/`platform` modules. `interfaces` lists every entry under `/sys/class/net` except `lo` (loopback) - empty on non-Linux hosts or a host with no `/sys/class/net`.

## `health`

Prints a `HealthReport` - a point-in-time, non-invasive health snapshot:

```json
{
  "schema_version": "1.0",
  "state": "READY",
  "timestamp_utc": "2026-01-01T00:00:00Z",
  "checks": {
    "storage": {"state": "PASS", "free_bytes": 42883584000, "minimum_free_bytes": 1073741824},
    "network": {"state": "PASS", "interfaces": ["eth0", "wlan0"]},
    "runtime": {"state": "PASS", "python": "3.11.2", "pid": 1842},
    "temperature": {"state": "PASS", "celsius": 47.3}
  }
}
```

- `checks.storage` - `FAIL` if free disk space (via `shutil.disk_usage`) is below `diagnostics.minimum_free_bytes` (default 1 GiB); otherwise `PASS`.
- `checks.network` - `WARN` if no non-loopback interface is up; otherwise `PASS`.
- `checks.runtime` - always `PASS`; reports the running Python version and this process's PID.
- `checks.temperature` - reads `/sys/class/thermal/thermal_zone0/temp` (millidegrees C, converted to degrees). `WARN` with `celsius: null` when that file doesn't exist or isn't readable (e.g. non-Linux, or a Pi without that thermal zone) - never fabricated.
- `state` - `"FAULT"` if storage failed, else `"DEGRADED"` if network warned, else `"READY"`. Temperature alone never changes `state` (a missing thermal zone is common and not itself a fault).

## `serve`

Runs `health` in a loop, printing one `HealthReport` every `--interval` seconds until interrupted (`Ctrl-C`, exit `0`). This is what `systemd/hydra-umc-agent.service` actually invokes.

---

## Configuration file shape (`--config`)

```json
{
  "schema_version": "1.0",
  "node": {"id": "hydra-umc-node", "profile": "base"},
  "diagnostics": {"minimum_free_bytes": 1073741824}
}
```

`schema_version` must be exactly `"1.0"`; `node.id` must be a non-empty string; `diagnostics.minimum_free_bytes` must be an integer. Any violation raises `ValueError`, printed to stderr as `hydra-umc-agent: <message>`, exit code `2`.
