#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - Agent deployment contract verification
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Verify that first boot, installer and systemd use the same agent identity.

This is a static, host-independent check.  It prevents a successful package
installation from producing a systemd unit that cannot start or a service
account that can modify its own executable code.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
UNIT = ROOT / "systemd" / "hydra-umc-agent.service"
INSTALLER = ROOT / "provisioning" / "install_local_agent.sh"
FIRST_BOOT = ROOT / "provisioning" / "first_boot.sh"
SERVICE_USER = "hydra-umc-agent"
AGENT_COMMAND = "/usr/local/bin/hydra-umc-agent"


def fail(message: str) -> None:
    print(f"AGENT_DEPLOYMENT_CONTRACT=FAIL {message}", file=sys.stderr)
    raise SystemExit(1)


def unit_value(text: str, name: str) -> str:
    match = re.search(rf"(?m)^{re.escape(name)}=(.*)$", text)
    if match is None:
        fail(f"systemd unit missing {name}")
    return match.group(1).strip()


def main() -> int:
    try:
        unit = UNIT.read_text(encoding="utf-8")
        installer = INSTALLER.read_text(encoding="utf-8")
        first_boot = FIRST_BOOT.read_text(encoding="utf-8")
    except OSError as exc:
        fail(f"cannot read deployment files: {exc}")

    if unit_value(unit, "User") != SERVICE_USER or unit_value(unit, "Group") != SERVICE_USER:
        fail("systemd unit must use the non-login hydra-umc-agent account")
    if not unit_value(unit, "ExecStart").startswith(f"{AGENT_COMMAND} "):
        fail("systemd ExecStart must use the command installed by install_local_agent.sh")
    if unit_value(unit, "ReadWritePaths") != "/var/lib/hydra-umc":
        fail("systemd writable state path must be /var/lib/hydra-umc")

    required_unit_values = {
        "NoNewPrivileges": "true",
        "CapabilityBoundingSet": "",
        "LockPersonality": "true",
        "PrivateTmp": "true",
        "ProtectHome": "true",
        "ProtectControlGroups": "true",
        "ProtectKernelModules": "true",
        "ProtectKernelTunables": "true",
        "ProtectSystem": "strict",
        "UMask": "0027",
    }
    for name, expected in required_unit_values.items():
        if unit_value(unit, name) != expected:
            fail(f"systemd {name} must be {expected!r}")

    if f'SERVICE_USER="{SERVICE_USER}"' not in first_boot:
        fail("first_boot service account differs from the systemd unit")
    if f'--shell /usr/sbin/nologin "$SERVICE_USER"' not in first_boot:
        fail("first_boot must create a non-login service account")
    if f'cat >{AGENT_COMMAND} <<' not in installer:
        fail("installer does not create the command used by systemd")
    if 'install -d -o root -g root -m 0755 "$TARGET"' not in installer:
        fail("agent code directory must be root-owned and non-writable by the service")
    if 'chown -R root:root "$TARGET/hydra_umc_os"' not in installer or 'chmod -R go-w "$TARGET/hydra_umc_os"' not in installer:
        fail("installed agent files must be root-owned and not group/world writable")
    if 'install -d -o root -g "$SERVICE_USER" -m 0750 /etc/hydra-umc' not in installer:
        fail("configuration directory must be root-owned and readable only by the service group")
    if 'install -m 0640 -o root -g "$SERVICE_USER"' not in installer:
        fail("configuration file must be root-owned with restricted service-group read access")

    print(f"AGENT_DEPLOYMENT_CONTRACT=PASS user={SERVICE_USER} command={AGENT_COMMAND}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
