#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - Read-only CM5 installation preflight
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Prove the local BASE or CONTROL deployment plan before a CM5 is changed.

The preflight is deliberately read-only: it validates configuration/profile
contracts, the OS agent deployment contract and (when available) live OS to
SDK schema compatibility. CONTROL also validates the local dashboard service
contract. It never installs software, creates users or invokes systemd.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "config" / "hydra-umc-os.example.json"
DEFAULT_IDENTITY = ROOT / "config" / "identity.example.json"
DEFAULT_SDK_ROOT = ROOT.parent / "HYDRA-UMC-SDK"
DEFAULT_SERVER_ROOT = ROOT.parent / "HYDRA-UMC-SERVER"
AGENT_SOURCE = ROOT / "agent" / "src"
AGENT_CONTRACT = ROOT / "tools" / "verify_agent_deployment_contract.py"
SDK_CONTRACT = ROOT / "tools" / "verify_sdk_contracts.py"


def fail(message: str) -> None:
    print(f"CM5_PREFLIGHT=FAIL {message}", file=sys.stderr)
    raise SystemExit(1)


def run_check(label: str, command: list[str]) -> None:
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit code {result.returncode}"
        fail(f"{label}: {detail}")
    summary = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "PASS"
    summary = summary.removeprefix(f"{label}=PASS ")
    print(f"{label}=PASS {summary}")


def import_agent() -> Any:
    spec = importlib.util.spec_from_file_location(
        "hydra_umc_os_agent_preflight", AGENT_SOURCE / "hydra_umc_os" / "agent.py"
    )
    if spec is None or spec.loader is None:
        fail("cannot load local HYDRA-UMC-OS agent")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_identity(path: Path) -> dict[str, str]:
    try:
        identity = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"identity configuration is invalid: {path}: {exc}")
    expected = {
        "display_name": "HYDRA-UMC-TEST",
        "hostname": "hydra-umc-test",
        "administrator": "hydra-umc",
        "service_account": "hydra-umc-agent",
    }
    if identity != expected:
        fail("identity configuration does not match the reviewed CM5 BASE identity")
    return identity


def validate_server_contract(server_root: Path) -> None:
    try:
        installer = (ROOT / "provisioning" / "install_server.sh").read_text(encoding="utf-8")
        unit = (server_root / "systemd" / "hydra-umc-server.service").read_text(encoding="utf-8")
    except OSError as exc:
        fail(f"cannot read HYDRA-UMC-SERVER deployment files: {exc}")
    account = "hydra-umc-server"
    for key in ("User", "Group"):
        match = re.search(rf"(?m)^{key}=(.*)$", unit)
        if match is None or match.group(1).strip() != account:
            fail(f"HYDRA-UMC-SERVER systemd {key} must be {account}")
    if f'SERVER_USER="{account}"' not in installer:
        fail("install_server.sh and HYDRA-UMC-SERVER systemd identity disagree")
    required = ("dist", "public", "package.json", "package-lock.json")
    missing = [name for name in required if not (server_root / name).exists()]
    if missing:
        fail(f"HYDRA-UMC-SERVER install source is incomplete: {', '.join(missing)}")
    print(f"SERVER_DEPLOYMENT_CONTRACT=PASS user={account} source={server_root.name}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--identity", type=Path, default=DEFAULT_IDENTITY)
    parser.add_argument("--profile", type=Path, default=ROOT / "config" / "profiles" / "base.json")
    parser.add_argument("--sdk-root", type=Path, default=DEFAULT_SDK_ROOT)
    parser.add_argument("--server-root", type=Path, default=DEFAULT_SERVER_ROOT)
    parser.add_argument("--skip-sdk", action="store_true", help="skip sibling SDK integration verification")
    args = parser.parse_args(argv)

    agent = import_agent()
    config = agent.load_config(args.config)
    profile = agent.load_profile(args.profile)
    identity = load_identity(args.identity)
    print(
        "CONFIG_PROFILE=PASS "
        f"node={config['node']['id']} active={config['node'].get('profile', 'base')} "
        f"planned={profile['profile']} identity={identity['hostname']}"
    )
    run_check("AGENT_DEPLOYMENT_CONTRACT", [sys.executable, str(AGENT_CONTRACT)])
    if args.skip_sdk:
        print("SDK_OS_CONTRACT=SKIPPED explicit --skip-sdk")
    else:
        run_check(
            "SDK_OS_CONTRACT",
            [sys.executable, str(SDK_CONTRACT), "--sdk-root", str(args.sdk_root.resolve())],
        )
    if profile["profile"] == "control":
        validate_server_contract(args.server_root)
    print(f"CM5_PREFLIGHT=PASS profile={profile['profile']} changes=none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
