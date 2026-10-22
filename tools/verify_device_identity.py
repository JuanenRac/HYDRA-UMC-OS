#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - tools/verify_device_identity.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Check that every device gets a name of its own and that a name chosen by the operator is kept."""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROVISIONING = ROOT / "provisioning"

failures: list[str] = []


def expect(condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


identity = load("hydra_device_identity", PROVISIONING / "device_identity.py")


def fake_device(base: Path, serial: str | None = None, macs: dict[str, str] | None = None, machine_id: str | None = None):
    cpuinfo = base / "cpuinfo"
    cpuinfo.write_text("processor\t: 0\n" + (f"Serial\t\t: {serial}\n" if serial is not None else "") + "Model\t\t: Raspberry Pi\n", encoding="utf-8")
    net = base / "net"
    net.mkdir()
    (net / "lo").mkdir()
    (net / "lo" / "address").write_text("00:00:00:00:00:00\n", encoding="utf-8")
    for name, mac in (macs or {}).items():
        (net / name).mkdir()
        (net / name / "address").write_text(mac + "\n", encoding="utf-8")
    mid = base / "machine-id"
    if machine_id is not None:
        mid.write_text(machine_id + "\n", encoding="utf-8")
    return cpuinfo, net, mid


def check_suffix_sources() -> None:
    with tempfile.TemporaryDirectory() as directory:
        base = Path(directory)
        cpuinfo, net, mid = fake_device(base, serial="10000000a1b2c3d4", macs={"eth0": "d8:3a:dd:11:22:33"}, machine_id="0123456789abcdef")
        expect(identity.device_suffix(cpuinfo, net, mid) == "b2c3d4", "the Raspberry Pi serial must come first")
    with tempfile.TemporaryDirectory() as directory:
        base = Path(directory)
        cpuinfo, net, mid = fake_device(base, serial="0000000000000000", macs={"eth0": "d8:3a:dd:11:22:33", "wlan0": "d8:3a:dd:44:55:66"}, machine_id="0123456789abcdef")
        expect(identity.device_suffix(cpuinfo, net, mid) == "112233", "a serial of zeros must be ignored and the first card's MAC used")
    with tempfile.TemporaryDirectory() as directory:
        base = Path(directory)
        cpuinfo, net, mid = fake_device(base, macs={"eth0": "00:00:00:00:00:00"}, machine_id="0123456789abcdef")
        expect(identity.device_suffix(cpuinfo, net, mid) == "012345", "the machine id is the last resort")
    with tempfile.TemporaryDirectory() as directory:
        base = Path(directory)
        cpuinfo, net, mid = fake_device(base)
        expect(identity.device_suffix(cpuinfo, net, mid) is None, "a device that cannot be told apart gets no suffix")
    expect(identity.device_suffix(Path("/nonexistent/a"), Path("/nonexistent/b"), Path("/nonexistent/c")) is None, "missing system files give no suffix")


def check_names() -> None:
    expect(identity.default_hostname(suffix="b2c3d4") == "hydra-umc-b2c3d4", "the host name ends with the suffix")
    expect(identity.default_ap_ssid(suffix="b2c3d4") == "HYDRA-UMC-SETUP-B2C3D4", "the setup network name ends with the suffix in capitals")
    expect(len(identity.default_ap_ssid(suffix="b2c3d4")) <= 32, "a Wi-Fi network name has at most 32 bytes")
    expect(identity.default_hostname(suffix=None, env={"HYDRA_UMC_DEVICE_SUFFIX": "off"}) == "hydra-umc", "off keeps the fixed host name")
    expect(identity.default_ap_ssid(suffix=None, env={"HYDRA_UMC_DEVICE_SUFFIX": "off"}) == "HYDRA-UMC-SETUP", "off keeps the fixed setup network name")
    for value in ("off", "OFF", "0", "false", "no"):
        expect(not identity.per_device_enabled({"HYDRA_UMC_DEVICE_SUFFIX": value}), f"{value!r} must switch the suffix off")
    for value in ("", "on", "1", "yes"):
        expect(identity.per_device_enabled({"HYDRA_UMC_DEVICE_SUFFIX": value}), f"{value!r} must leave the suffix on")


def check_wifi_provision_default() -> None:
    wifi = load("hydra_wifi_provision_identity", PROVISIONING / "wifi_provision.py")
    previous = os.environ.get("HYDRA_UMC_DEVICE_SUFFIX")
    try:
        os.environ["HYDRA_UMC_DEVICE_SUFFIX"] = "off"
        expect(wifi.device_default_ap_ssid() == "HYDRA-UMC-SETUP", "with the suffix off the setup network keeps its fixed name")
        os.environ["HYDRA_UMC_DEVICE_SUFFIX"] = "on"
        name = wifi.device_default_ap_ssid()
        expect(name == "HYDRA-UMC-SETUP" or name.startswith("HYDRA-UMC-SETUP-"), f"unexpected setup network name {name!r}")
    finally:
        if previous is None:
            os.environ.pop("HYDRA_UMC_DEVICE_SUFFIX", None)
        else:
            os.environ["HYDRA_UMC_DEVICE_SUFFIX"] = previous


def check_deployment_files() -> None:
    unit = (ROOT / "systemd" / "hydra-umc-wifi-provision.service").read_text(encoding="utf-8")
    expect("--ap-ssid" not in unit, "the unit must not fix the setup network name, or the per-device name would never apply")
    installer = (PROVISIONING / "install_wifi_provision.sh").read_text(encoding="utf-8")
    expect("device_identity.py" in installer, "the installer must put device_identity.py next to wifi_provision.py")
    first_boot = (PROVISIONING / "first_boot.sh").read_text(encoding="utf-8")
    expect("HYDRA_UMC_HOSTNAME:-" in first_boot and "device_identity.py" in first_boot, "first_boot.sh must keep an explicit host name and default to the per-device one")
    result = subprocess.run([sys.executable, str(PROVISIONING / "device_identity.py"), "hostname"], capture_output=True, text=True, env={**os.environ, "HYDRA_UMC_DEVICE_SUFFIX": "off"})
    expect(result.returncode == 0 and result.stdout.strip() == "hydra-umc", "the command line must print the host name")
    result = subprocess.run([sys.executable, str(PROVISIONING / "device_identity.py"), "nonsense"], capture_output=True, text=True)
    expect(result.returncode == 2, "an unknown command must be refused")


def main() -> int:
    check_suffix_sources()
    check_names()
    check_wifi_provision_default()
    check_deployment_files()
    if failures:
        for message in failures:
            print(f"DEVICE_IDENTITY=FAIL {message}", file=sys.stderr)
        return 1
    print("DEVICE_IDENTITY=PASS suffix sources, names, switch, deployment files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
