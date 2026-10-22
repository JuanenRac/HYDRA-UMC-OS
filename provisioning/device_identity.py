#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - provisioning/device_identity.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""A name for this device that no other device shares.

Two devices flashed from the same image used to answer to the same host name and to open a setup
Wi-Fi network with the same name. The default names now end with six hexadecimal characters taken
from the device itself: the last six of the Raspberry Pi serial number, or else the last three bytes
of the first network card's MAC address, or else the start of the machine id.

Only the DEFAULT names get the suffix. A host name or a network name the operator chose
(HYDRA_UMC_HOSTNAME, HYDRA_UMC_AP_SSID, --ap-ssid) is used exactly as given. Setting
HYDRA_UMC_DEVICE_SUFFIX=off brings the fixed default names back.

    device_identity.py suffix | hostname | ap-ssid
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

DEFAULT_HOSTNAME = "hydra-umc"
DEFAULT_AP_SSID = "HYDRA-UMC-SETUP"
SUFFIX_LENGTH = 6
_OFF_VALUES = {"off", "0", "false", "no"}
_HEX = re.compile(r"^[0-9a-f]+$")


def per_device_enabled(env: dict[str, str] | None = None) -> bool:
    """True unless HYDRA_UMC_DEVICE_SUFFIX is set to off, 0, false or no."""
    value = (env if env is not None else os.environ).get("HYDRA_UMC_DEVICE_SUFFIX", "")
    return value.strip().lower() not in _OFF_VALUES


def _from_cpuinfo(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for line in text.splitlines():
        key, _, value = line.partition(":")
        if key.strip().lower() == "serial":
            serial = value.strip().lower()
            # a board without a serial reports zeros: every such board would share one name
            if _HEX.match(serial) and len(serial) >= SUFFIX_LENGTH and set(serial) != {"0"}:
                return serial[-SUFFIX_LENGTH:]
    return None


def _from_mac(net_dir: Path) -> str | None:
    try:
        interfaces = sorted(entry for entry in net_dir.iterdir() if entry.name != "lo")
    except OSError:
        return None
    for interface in interfaces:
        try:
            mac = (interface / "address").read_text(encoding="utf-8").strip().lower()
        except OSError:
            continue
        digits = mac.replace(":", "")
        if len(digits) == 12 and _HEX.match(digits) and set(digits) != {"0"}:
            return digits[-SUFFIX_LENGTH:]
    return None


def _from_machine_id(path: Path) -> str | None:
    try:
        value = path.read_text(encoding="utf-8").strip().lower()
    except OSError:
        return None
    return value[:SUFFIX_LENGTH] if _HEX.match(value) and len(value) >= SUFFIX_LENGTH else None


def device_suffix(
    cpuinfo: Path = Path("/proc/cpuinfo"),
    net_dir: Path = Path("/sys/class/net"),
    machine_id: Path = Path("/etc/machine-id"),
) -> str | None:
    """Six lowercase hexadecimal characters that belong to this device, or None when nothing identifies it."""
    return _from_cpuinfo(cpuinfo) or _from_mac(net_dir) or _from_machine_id(machine_id)


def default_hostname(base: str = DEFAULT_HOSTNAME, suffix: str | None = None, env: dict[str, str] | None = None) -> str:
    suffix = suffix if suffix is not None else (device_suffix() if per_device_enabled(env) else None)
    return f"{base}-{suffix}" if suffix else base


def default_ap_ssid(base: str = DEFAULT_AP_SSID, suffix: str | None = None, env: dict[str, str] | None = None) -> str:
    suffix = suffix if suffix is not None else (device_suffix() if per_device_enabled(env) else None)
    return f"{base}-{suffix.upper()}" if suffix else base


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1 or args[0] not in ("suffix", "hostname", "ap-ssid"):
        print("usage: device_identity.py suffix | hostname | ap-ssid", file=sys.stderr)
        return 2
    if args[0] == "suffix":
        print(device_suffix() or "")
    elif args[0] == "hostname":
        print(default_hostname())
    else:
        print(default_ap_ssid())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
