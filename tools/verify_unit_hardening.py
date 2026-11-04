#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - Hardening of the agent and Wi-Fi units verification
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Static check of the two systemd units: the directives that narrow what each service can do are present, and the ones that would break what it
needs are absent. The real exposure level is measured with `systemd-analyze security` on a device (docs/BENCH_TESTS.md, step 8); this check only
keeps the directives from being lost by an edit."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
failures: list[str] = []


def values(unit: str) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for line in unit.splitlines():
        match = re.match(r"^([A-Za-z]+)=(.*)$", line.strip())
        if match:
            found.setdefault(match.group(1), []).append(match.group(2).strip())
    return found


def expect(condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def check_agent() -> None:
    text = (ROOT / "systemd" / "hydra-umc-agent.service").read_text(encoding="utf-8")
    unit = values(text)
    required = {
        "WorkingDirectory": "/var/lib/hydra-umc", "ProtectProc": "invisible", "PrivateDevices": "true", "ProtectClock": "true", "ProtectKernelLogs": "true",
        "RestrictNamespaces": "true", "RestrictRealtime": "true", "RestrictSUIDSGID": "true", "RestrictAddressFamilies": "AF_UNIX",
        "SystemCallArchitectures": "native",
    }
    for name, wanted in required.items():
        expect(unit.get(name) == [wanted], f"agent unit: {name} must be {wanted!r}, found {unit.get(name)!r}")
    expect("@system-service" in unit.get("SystemCallFilter", [""])[0], "agent unit: SystemCallFilter must start from @system-service")
    # the agent reports the network interfaces it sees: a private network namespace would hide them
    expect("PrivateNetwork" not in unit, "agent unit: PrivateNetwork would hide the interfaces the agent reports")


def check_wifi() -> None:
    text = (ROOT / "systemd" / "hydra-umc-wifi-provision.service").read_text(encoding="utf-8")
    unit = values(text)
    required = {
        "ProtectSystem": "strict", "PrivateTmp": "true", "ProtectKernelTunables": "true", "ProtectKernelLogs": "true", "ProtectClock": "true",
        "ProtectProc": "invisible", "RestrictNamespaces": "true", "RestrictRealtime": "true", "RestrictSUIDSGID": "true",
        "RestrictAddressFamilies": "AF_UNIX AF_INET AF_INET6 AF_NETLINK", "SystemCallArchitectures": "native",
        "StateDirectory": "hydra-umc/wifi-provision",
    }
    for name, wanted in required.items():
        expect(unit.get(name) == [wanted], f"wifi unit: {name} must be {wanted!r}, found {unit.get(name)!r}")
    expect("@system-service" in unit.get("SystemCallFilter", [""])[0], "wifi unit: SystemCallFilter must start from @system-service")
    # the service reconfigures the radio through NetworkManager: a private network or no netlink would stop it
    expect("PrivateNetwork" not in unit, "wifi unit: PrivateNetwork would cut the service off from the radio")


def main() -> int:
    check_agent()
    check_wifi()
    if failures:
        for message in failures:
            print(f"UNIT_HARDENING=FAIL {message}", file=sys.stderr)
        return 1
    print("UNIT_HARDENING=PASS agent and wifi units")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
