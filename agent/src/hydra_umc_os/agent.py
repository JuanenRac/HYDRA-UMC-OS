# =============================================================================
# HYDRA-UMC-OS - Read-only CM5 diagnostics agent
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================

"""Read-only diagnostics agent for a HYDRA-UMC CM5 node.

The agent deliberately reports local state only. It does not command the MCU,
move machinery, alter Raspberry Pi OS, or bypass hardware safety authority.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import shutil
import socket
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


DEFAULT_CONFIG: dict[str, Any] = {
    "schema_version": "1.0",
    "node": {"id": "hydra-umc-node", "profile": "base"},
    "diagnostics": {
        "minimum_free_bytes": 1_073_741_824,
        "maximum_temperature_celsius": 80.0,
    },
}


@dataclass(frozen=True)
class DeviceDescriptor:
    schema_version: str
    node_id: str
    profile: str
    hostname: str
    machine: str
    operating_system: str
    kernel: str
    interfaces: list[str]


@dataclass(frozen=True)
class HealthReport:
    schema_version: str
    state: str
    timestamp_utc: str
    checks: dict[str, dict[str, Any]]


def load_config(path: Path | None) -> dict[str, Any]:
    """Load a non-secret JSON profile and reject an invalid shape early."""
    if path is None:
        return json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        candidate = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"configuration file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"configuration is not valid JSON: {path}") from exc
    if not isinstance(candidate, dict) or candidate.get("schema_version") != "1.0":
        raise ValueError("configuration schema_version must be '1.0'")
    node = candidate.get("node")
    diagnostics = candidate.get("diagnostics")
    if not isinstance(node, dict) or not isinstance(node.get("id"), str) or not node["id"].strip():
        raise ValueError("configuration node.id must be a non-empty string")
    if "profile" in node and (not isinstance(node["profile"], str) or not node["profile"].strip()):
        raise ValueError("configuration node.profile must be a non-empty string when present")
    if not isinstance(diagnostics, dict):
        raise ValueError("configuration diagnostics must be an object")
    minimum_free_bytes = diagnostics.get("minimum_free_bytes")
    if isinstance(minimum_free_bytes, bool) or not isinstance(minimum_free_bytes, int) or minimum_free_bytes < 0:
        raise ValueError("configuration diagnostics.minimum_free_bytes must be a non-negative integer")
    # The threshold is optional for existing v1.0 configurations.  Keeping a
    # safe default preserves compatibility while ensuring heat is never
    # silently reported as healthy on a CM5.
    maximum_temperature = diagnostics.setdefault(
        "maximum_temperature_celsius",
        DEFAULT_CONFIG["diagnostics"]["maximum_temperature_celsius"],
    )
    if (
        isinstance(maximum_temperature, bool)
        or not isinstance(maximum_temperature, (int, float))
        or not math.isfinite(maximum_temperature)
        or maximum_temperature <= 0
    ):
        raise ValueError("configuration diagnostics.maximum_temperature_celsius must be a positive finite number")
    return candidate


def network_interfaces(sys_class_net: Path = Path("/sys/class/net")) -> list[str]:
    if not sys_class_net.is_dir():
        return []
    return sorted(entry.name for entry in sys_class_net.iterdir() if entry.name != "lo")


def read_temperature_celsius(path: Path = Path("/sys/class/thermal/thermal_zone0/temp")) -> float | None:
    """Read the Linux thermal zone when available; never changes device state."""
    try:
        return int(path.read_text(encoding="utf-8").strip()) / 1000.0
    except (OSError, ValueError):
        return None


def load_profile(path: Path) -> dict[str, Any]:
    """Load an opt-in profile declaration; it never starts services itself."""
    try:
        profile = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"profile is not valid JSON: {path}") from exc
    if profile.get("schema_version") != "1.0" or not isinstance(profile.get("profile"), str) or not profile["profile"]:
        raise ValueError("profile requires schema_version '1.0' and a non-empty profile name")
    if not isinstance(profile.get("enabled_services"), list) or not isinstance(profile.get("requires"), list):
        raise ValueError("profile enabled_services and requires must be arrays")
    for field in ("enabled_services", "requires"):
        values = profile[field]
        if not all(isinstance(value, str) and value for value in values):
            raise ValueError(f"profile {field} must contain non-empty strings")
        if len(values) != len(set(values)):
            raise ValueError(f"profile {field} must not contain duplicates")
    return profile


def describe(config: dict[str, Any], interfaces: list[str] | None = None) -> DeviceDescriptor:
    node = config["node"]
    return DeviceDescriptor(
        schema_version="1.0",
        node_id=node["id"],
        profile=node.get("profile", "base"),
        hostname=socket.gethostname(),
        machine=platform.machine(),
        operating_system=platform.system(),
        kernel=platform.release(),
        interfaces=network_interfaces() if interfaces is None else interfaces,
    )


def health(
    config: dict[str, Any],
    *,
    free_bytes: int | None = None,
    interfaces: list[str] | None = None,
    temperature_celsius: float | None = None,
) -> HealthReport:
    """Produce a deterministic health state from non-invasive local checks."""
    available = shutil.disk_usage(Path.cwd()).free if free_bytes is None else free_bytes
    active_interfaces = network_interfaces() if interfaces is None else interfaces
    temperature = read_temperature_celsius() if temperature_celsius is None else temperature_celsius
    diagnostics = config["diagnostics"]
    minimum = diagnostics["minimum_free_bytes"]
    maximum_temperature = diagnostics.get(
        "maximum_temperature_celsius",
        DEFAULT_CONFIG["diagnostics"]["maximum_temperature_celsius"],
    )
    temperature_state = (
        "WARN" if temperature is None
        else "FAIL" if temperature >= maximum_temperature
        else "PASS"
    )
    checks = {
        "storage": {"state": "PASS" if available >= minimum else "FAIL", "free_bytes": available, "minimum_free_bytes": minimum},
        "network": {"state": "PASS" if active_interfaces else "WARN", "interfaces": active_interfaces},
        "runtime": {"state": "PASS", "python": platform.python_version(), "pid": os.getpid()},
        "temperature": {
            "state": temperature_state,
            "celsius": temperature,
            "maximum_celsius": maximum_temperature,
        },
    }
    state = (
        "FAULT" if any(check["state"] == "FAIL" for check in checks.values())
        else "DEGRADED" if checks["network"]["state"] == "WARN"
        else "READY"
    )
    return HealthReport(
        schema_version="1.0",
        state=state,
        timestamp_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        checks=checks,
    )


def emit(value: DeviceDescriptor | HealthReport) -> None:
    print(json.dumps(asdict(value), sort_keys=True, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, help="path to a validated non-secret JSON configuration")
    parser.add_argument("--interval", type=float, default=30.0, help="seconds between reports in serve mode")
    parser.add_argument("command", choices=("describe", "health", "serve"))
    args = parser.parse_args(argv)
    try:
        if args.command == "serve" and (not math.isfinite(args.interval) or args.interval <= 0):
            raise ValueError("serve interval must be a finite number greater than zero")
        config = load_config(args.config)
        if args.command == "describe":
            emit(describe(config))
            return 0
        if args.command == "health":
            emit(health(config))
            return 0
        while True:
            emit(health(config))
            time.sleep(args.interval)
    except (ValueError, OSError) as exc:
        print(f"hydra-umc-agent: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
