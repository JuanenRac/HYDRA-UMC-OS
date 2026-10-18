#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - Gateway .env generation verification
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Proves provisioning/gateway_env.py: the generated .env is accepted by what the gateway and the broker demand of a production start (secret length, password length, an ACL rule
that covers every credential), is private, is never overwritten, and gives each bridge its own identity and namespace."""
from __future__ import annotations

import importlib.util
import json
import os
import stat
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("hydra_umc_os_gateway_env", ROOT / "provisioning" / "gateway_env.py")
assert spec and spec.loader
ge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ge
spec.loader.exec_module(ge)

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


def values(text: str) -> dict[str, str]:
    out = {}
    for line in text.split(chr(10)):
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            out[key] = value
    return out


text, passwords = ge.build_env()
env = values(text)
check("GATEWAY_JWT_SECRET is 64 hex characters (the gateway wants 32+)", len(env["GATEWAY_JWT_SECRET"]), 64)
credentials = json.loads(env["MQTT_AUTH_JSON"])
rules = json.loads(env["MQTT_ACL_JSON"])
check("one credential per bridge", [c["username"] for c in credentials], [f"hydra-umc-bridge-{n}" for n in ge.BRIDGES])
check("every password has 16+ characters (the broker wants 16+)", all(len(c["password"]) >= 16 for c in credentials), True)
check("the passwords differ", len({c["password"] for c in credentials}), len(ge.BRIDGES))
check("each credential's prefix is its own user name", all(c["clientIdPrefix"] == c["username"] for c in credentials), True)
# the broker evaluates the ACL for the credential's own prefix: a rule must exist whose prefix the credential's prefix starts with
check("an ACL rule covers every credential", all(any(c["clientIdPrefix"].startswith(r["clientIdPrefix"]) for r in rules) for c in credentials), True)
check("a bridge may only publish and subscribe inside its own namespace", all(r["publish"] == [f"hydra/bridges/{r['clientIdPrefix'].rsplit('-', 1)[1]}/#"] for r in rules if not r["clientIdPrefix"].endswith("-amr")), True)
check("the AMR bridge gets a credential and a VDA 5050 namespace", [(r["publish"], r["subscribe"]) for r in rules if r["clientIdPrefix"].endswith("-amr")], [(["vda5050/#"], ["vda5050/#"])])
check("no rule matches every client", any(r["clientIdPrefix"] == "" for r in rules), False)
check("the printed passwords are the ones in the file", {n: passwords[n] for n in ge.BRIDGES} == {c["username"].rsplit("-", 1)[1]: c["password"] for c in credentials}, True)

with tempfile.TemporaryDirectory() as directory:
    path = Path(directory) / ".env"
    check("dry run creates nothing", (ge.main([str(path)]), path.exists()), (0, False))
    check("apply creates the file", (ge.main([str(path), "--apply"]), path.exists()), (0, True))
    if os.name != "nt":
        check("the file is private", stat.S_IMODE(os.stat(path).st_mode) & 0o077, 0)
    first = path.read_text(encoding="utf-8")
    check("a second apply never overwrites it", (ge.main([str(path), "--apply"]), path.read_text(encoding="utf-8")), (0, first))

print()
if failures:
    print(f"GATEWAY_ENV_VERIFY=FAIL {failures} mismatches")
    sys.exit(1)
print(f"GATEWAY_ENV_VERIFY=PASS checks={checks}")
