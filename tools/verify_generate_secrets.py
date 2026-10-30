#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - Secret generation verification
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Proves provisioning/generate_secrets.py: no example value of a deployment template survives, the operator's own values are left alone, a shared token is mirrored, and --check
refuses what a server would refuse."""
from __future__ import annotations

import importlib.util
import os
import stat
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("hydra_umc_os_generate_secrets", ROOT / "provisioning" / "generate_secrets.py")
assert spec and spec.loader
gs = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = gs
spec.loader.exec_module(gs)

failures = 0
checks = 0


def check(label: str, actual: object, expected: object) -> None:
    global failures, checks
    checks += 1
    if actual != expected:
        print(f"FAIL {label}: expected {expected!r}, got {actual!r}")
        failures += 1
    else:
        print(f"ok   {label}")


TEMPLATE = (ROOT / "provisioning" / "server.env.example").read_text(encoding="utf-8")
check("the real template carries example values", len(gs.problems(TEMPLATE)) >= 3, True)

filled, generated = gs.fill(TEMPLATE)
check("every placeholder is replaced", gs.problems(filled), [])
check("the JWT secret is 64 hex characters", len(generated["JWT_SECRET"]), 64)
check("the bootstrap password is 24 characters", len(generated[gs.ADMIN_PASSWORD_KEY]), 24)
check("two runs never give the same secret", gs.fill(TEMPLATE)[1]["JWT_SECRET"] != generated["JWT_SECRET"], True)
check("comments and other variables are untouched", "NODE_ENV=production" in filled and "HYDRA_UMC_SERVER_PORT=3000" in filled and "#HYDRA_UMC_DATALAKE_URL" in filled, True)

own = "JWT_SECRET=" + "f3a9c07b" * 8 + "\nHYDRA_UMC_BOOTSTRAP_ADMIN_PASSWORD=a-password-of-my-own-1\n"
check("a value the operator chose is left alone", gs.fill(own)[1], {})
check("...and accepted by the check", gs.problems(own), [])
check("an empty JWT secret is refused", gs.problems("JWT_SECRET=" + chr(10)), ["JWT_SECRET is empty"])
check("a short JWT secret is refused", gs.problems("JWT_SECRET=short\n"), ["JWT_SECRET has fewer than 32 characters"])
check("a short password is refused", gs.problems("HYDRA_UMC_BOOTSTRAP_ADMIN_PASSWORD=short\n"), ["HYDRA_UMC_BOOTSTRAP_ADMIN_PASSWORD has fewer than 12 characters"])

with tempfile.TemporaryDirectory() as directory:
    base = Path(directory)
    server_env = base / "server.env"
    voice_env = base / "voice-ui.env"
    voice_env.write_text("HYDRA_UMC_VOICE_UI_TOKEN=SET_LOCALLY_TO_A_LONG_RANDOM_VALUE\n", encoding="utf-8")
    template = ROOT / "provisioning" / "server.env.example"
    mirror = f"HYDRA_UMC_VOICE_UI_TOKEN={voice_env}:HYDRA_UMC_VOICE_UI_TOKEN"

    check("dry run changes nothing", gs.main([str(server_env), "--create-from", str(template)]), 0)
    check("...and creates no file", server_env.exists(), False)
    check("apply creates the file", gs.main([str(server_env), "--create-from", str(template), "--apply", "--mirror", mirror]), 0)
    check("the file passes the check", gs.main([str(server_env), "--check"]), 0)
    mode = stat.S_IMODE(os.stat(server_env).st_mode)
    check("the file is private (no group or other access)", mode & 0o077, 0) if os.name != "nt" else check("(mode not checked on Windows)", True, True)
    server_token = next(v for _, k, v in gs.parse(server_env.read_text(encoding="utf-8")) if k == "HYDRA_UMC_VOICE_UI_TOKEN")
    voice_token = next(v for _, k, v in gs.parse(voice_env.read_text(encoding="utf-8")) if k == "HYDRA_UMC_VOICE_UI_TOKEN")
    check("the voice relay token is the same in both files", server_token == voice_token and len(server_token) == 64, True)
    before = server_env.read_text(encoding="utf-8")
    check("a second apply changes nothing", gs.main([str(server_env), "--apply"]), 0)
    check("...the file is identical", server_env.read_text(encoding="utf-8"), before)
    adopt_env = base / "adopt.env"
    other = base / "other.env"
    other.write_text("HYDRA_UMC_VOICE_UI_TOKEN=" + "ab" * 32 + chr(10), encoding="utf-8")
    check("adopt creates a file", gs.main([str(adopt_env), "--create-from", str(template), "--apply", "--adopt", f"HYDRA_UMC_VOICE_UI_TOKEN={other}:HYDRA_UMC_VOICE_UI_TOKEN"]), 0)
    adopted_token = next(v for _, k, v in gs.parse(adopt_env.read_text(encoding="utf-8")) if k == "HYDRA_UMC_VOICE_UI_TOKEN")
    check("an adopted value is the one the other file already had", adopted_token, "ab" * 32)
    bad = base / "bad.env"
    bad.write_text(TEMPLATE, encoding="utf-8")
    check("the check refuses a copy of the template", gs.main([str(bad), "--check"]), 1)
    check("the check refuses a missing file", gs.main([str(base / "missing.env"), "--check"]), 1)

print()
if failures:
    print(f"GENERATE_SECRETS_VERIFY=FAIL {failures} mismatches")
    sys.exit(1)
print(f"GENERATE_SECRETS_VERIFY=PASS checks={checks}")
