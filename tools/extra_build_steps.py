#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - tools/extra_build_steps.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The steps of this repository beyond the shared build test: the agent tests and the deployment checks."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def fail(message: str) -> None:
    print(f"BUILD_TEST=FAIL {message}", file=sys.stderr)
    raise SystemExit(1)


def run(*command: str, cwd: Path = ROOT, env: dict[str, str] | None = None) -> None:
    print("+", " ".join(command))
    try:
        subprocess.run(command, cwd=cwd, env=env, check=True)
    except FileNotFoundError:
        fail(f"required command not found: {command[0]}")
    except subprocess.CalledProcessError as exc:
        fail(f"command failed with exit code {exc.returncode}: {' '.join(command)}")


def run_agent_checks() -> None:
    environment = dict(os.environ)
    agent_source = str(ROOT / "agent" / "src")
    existing_python_path = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = agent_source if not existing_python_path else os.pathsep.join((agent_source, existing_python_path))
    run(sys.executable, "-m", "unittest", "discover", "-s", "agent/tests", "-v", env=environment)
    run(sys.executable, "tools/verify_agent_deployment_contract.py", env=environment)
    if (ROOT.parent / "HYDRA-UMC-VOICE-UI").is_dir():
        run(sys.executable, "tools/verify_voice_gateway_deployment_contract.py", env=environment)
    else:
        print("VOICE_GATEWAY_CONTRACT=SKIPPED the sibling HYDRA-UMC-VOICE-UI checkout is not present")
    run(sys.executable, "tools/verify_preflight_negative.py", env=environment)
    run(sys.executable, "tools/verify_preflight_idempotent.py", env=environment)
    run(sys.executable, "tools/verify_rollback.py", env=environment)
    run(sys.executable, "tools/verify_wifi_provision.py", env=environment)
    run(sys.executable, "tools/verify_generate_secrets.py", env=environment)
    run(sys.executable, "tools/verify_result_keys.py", env=environment)
    run(sys.executable, "tools/verify_gateway_env.py", env=environment)
    run(sys.executable, "tools/verify_gateway_installer.py", env=environment)
    run(sys.executable, "tools/verify_kiosk_installer.py", env=environment)
    run(sys.executable, "tools/verify_package_component.py", env=environment)
    run(sys.executable, "tools/verify_mqtt_tls.py", env=environment)
    run(sys.executable, "tools/verify_firewall.py", env=environment)
    run(sys.executable, "tools/verify_optional_journals.py", env=environment)
    run(sys.executable, "tools/verify_go_toolchain.py", env=environment)
    run(sys.executable, "tools/verify_service_registry.py", env=environment)
    run(sys.executable, "tools/verify_backup_settings.py", env=environment)
    run(sys.executable, "tools/verify_os_guard_and_docs.py", env=environment)
    run(sys.executable, "tools/verify_bump_version.py", env=environment)
    run(sys.executable, "tools/verify_device_identity.py", env=environment)
    run(sys.executable, "tools/verify_deb_package.py", env=environment)
    # CI checks the self-contained BASE plan. A full local preflight also
    # validates a sibling SDK checkout before a real CM5 is changed.
    run(sys.executable, "provisioning/preflight_cm5.py", "--skip-sdk", env=environment)


def main() -> int:
    if (ROOT / "agent" / "tests").is_dir():
        run_agent_checks()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
