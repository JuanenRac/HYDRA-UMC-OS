#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - Voice gateway deployment contract verification
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Verify the CM5 loopback Voice UI deployment boundary without hardware.

The check is deliberately static: it ensures the provisioning scripts, unit
and environment templates keep the Voice UI private on the CM5 and make
HYDRA-UMC-SERVER its sole authenticated caller.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
VOICE_UNIT = ROOT.parent / "HYDRA-UMC-VOICE-UI" / "systemd" / "hydra-umc-voice-ui.service"
VOICE_ENV_TEMPLATE = ROOT.parent / "HYDRA-UMC-VOICE-UI" / "deploy" / "voice-ui.env.example"
INSTALLER = ROOT / "provisioning" / "install_voice_ui.sh"
BASE_INSTALLER = ROOT / "provisioning" / "install_cm5_base.sh"
RUNTIME_CHECK = ROOT / "provisioning" / "verify_cm5_runtime.sh"
SERVER_ENV_TEMPLATE = ROOT / "provisioning" / "server.env.example"

VOICE_USER = "hydra-umc-voice-ui"
VOICE_URL = "http://127.0.0.1:8091"
VOICE_ENV = "/etc/hydra-umc/voice-ui.env"


def fail(message: str) -> None:
    print(f"VOICE_GATEWAY_DEPLOYMENT_CONTRACT=FAIL {message}", file=sys.stderr)
    raise SystemExit(1)


def unit_value(text: str, name: str) -> str:
    match = re.search(rf"(?m)^{re.escape(name)}=(.*)$", text)
    if match is None:
        fail(f"Voice UI systemd unit missing {name}")
    return match.group(1).strip()


def require(text: str, fragment: str, description: str) -> None:
    if fragment not in text:
        fail(description)


def main() -> int:
    try:
        unit = VOICE_UNIT.read_text(encoding="utf-8")
        voice_env = VOICE_ENV_TEMPLATE.read_text(encoding="utf-8")
        installer = INSTALLER.read_text(encoding="utf-8")
        base_installer = BASE_INSTALLER.read_text(encoding="utf-8")
        runtime_check = RUNTIME_CHECK.read_text(encoding="utf-8")
        server_env = SERVER_ENV_TEMPLATE.read_text(encoding="utf-8")
    except OSError as exc:
        fail(f"cannot read Voice UI deployment files: {exc}")

    if unit_value(unit, "User") != VOICE_USER or unit_value(unit, "Group") != VOICE_USER:
        fail("Voice UI unit must use the dedicated non-login service account")
    if unit_value(unit, "EnvironmentFile") != VOICE_ENV:
        fail("Voice UI unit must read its token from the restricted environment file")
    if not unit_value(unit, "ExecStart").endswith("--host 127.0.0.1 --port 8091"):
        fail("Voice UI unit must bind only to loopback port 8091")
    for name, expected in {
        "NoNewPrivileges": "true",
        "PrivateTmp": "true",
        "ProtectHome": "true",
        "ProtectSystem": "strict",
    }.items():
        if unit_value(unit, name) != expected:
            fail(f"Voice UI systemd {name} must be {expected!r}")

    require(voice_env, "HYDRA_UMC_VOICE_UI_TOKEN=", "Voice UI environment template lacks its token")
    require(installer, f'VOICE_USER="{VOICE_USER}"', "Voice UI installer uses a different service account")
    require(installer, f"ENV_FILE={VOICE_ENV}", "Voice UI installer uses a different environment file")
    require(installer, 'chmod 0640 "$ENV_FILE"', "Voice UI token file must have restricted permissions")
    require(installer, 'chown root:"$VOICE_USER" "$ENV_FILE"', "Voice UI token must be owned by root and its service group")
    require(base_installer, "--with-voice-ui", "CM5 base installer does not expose the Voice UI stage")
    require(base_installer, "--with-voice-ui requires --with-server", "Voice UI stage must require the Server boundary")
    require(base_installer, "systemctl enable --now hydra-umc-voice-ui", "CM5 base installer does not enable Voice UI")
    require(runtime_check, "check id hydra-umc-voice-ui", "CM5 verifier does not validate the Voice UI account")
    require(runtime_check, "hydra-umc-voice-ui", "CM5 verifier does not validate the Voice UI service")
    require(server_env, f"HYDRA_UMC_VOICE_UI_URL={VOICE_URL}", "Server template must use the loopback Voice UI endpoint")
    require(server_env, "HYDRA_UMC_VOICE_UI_TOKEN=", "Server template lacks the matching relay token")

    print(f"VOICE_GATEWAY_DEPLOYMENT_CONTRACT=PASS user={VOICE_USER} endpoint={VOICE_URL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
