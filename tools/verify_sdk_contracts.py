#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - Local SDK contract integration verification
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Validate live read-only OS agent output against a sibling SDK checkout.

This developer verification intentionally has no runtime dependency on the
SDK. It is run only in a workspace that contains both repositories and proves
that the independently released OS producer still emits SDK v1 contracts.
"""

from __future__ import annotations

import argparse
import importlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SDK_ROOT = ROOT.parent / "HYDRA-UMC-SDK"
AGENT = ROOT / "agent" / "src" / "hydra_umc_os" / "agent.py"


def fail(message: str) -> None:
    print(f"SDK_OS_CONTRACT=FAIL {message}", file=sys.stderr)
    raise SystemExit(1)


def agent_payload(command: str) -> dict[str, Any]:
    result = subprocess.run(
        (sys.executable, str(AGENT), command),
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        fail(f"agent {command} failed: {result.stderr.strip() or result.returncode}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        fail(f"agent {command} emitted invalid JSON: {exc.msg}")
    if not isinstance(payload, dict):
        fail(f"agent {command} payload must be an object")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk-root", type=Path, default=DEFAULT_SDK_ROOT)
    args = parser.parse_args(argv)
    sdk_source = args.sdk_root / "clients" / "python" / "src"
    if not sdk_source.is_dir():
        fail(f"SDK Python client not found: {sdk_source}")
    if not AGENT.is_file():
        fail(f"OS agent not found: {AGENT}")

    sys.path.insert(0, str(sdk_source))
    validation = importlib.import_module("hydra_umc_sdk.validation")
    descriptor = agent_payload("describe")
    report = agent_payload("health")
    validation.validate("DeviceDescriptor", descriptor)
    validation.validate("HealthReport", report)
    if descriptor["schema_version"] != report["schema_version"]:
        fail("agent descriptor and health report use different schema versions")
    print(
        "SDK_OS_CONTRACT=PASS "
        f"schema={descriptor['schema_version']} node={descriptor['node_id']} state={report['state']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
