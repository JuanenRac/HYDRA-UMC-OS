#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - Service identity verification
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Proves provisioning/service_identity.py: nothing is on until asked, the key of the server is distributed with a private mode, an example or short key is refused, the secret is never
printed, and the switch can be turned off again."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import stat
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("hydra_umc_os_service_identity", ROOT / "provisioning" / "service_identity.py")
assert spec and spec.loader
si = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = si
spec.loader.exec_module(si)

failures = 0


def check(label: str, actual: object, expected: object) -> None:
    """Compares and reports the label only: a value compared here may derive from the sample key, which is never printed."""
    global failures
    if actual != expected:
        print(f"FAIL {label}")
        failures += 1
    else:
        print(f"ok   {label}")


def run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = si.main(list(argv))
    return code, out.getvalue(), err.getvalue()


SAMPLE = os.urandom(32).hex()  # a throwaway value made for this run; it lives only in the temporary directory below
config = si.load_config(ROOT / "config" / "service_identity.json")
check("the shipped configuration names at least the three pilot services", {"cognitive-node", "vision-node", "vla-engine"} <= set(config["services"]), True)
check("every service has its own variable", len({e["environment"] for e in config["services"].values()}), len(config["services"]))

with tempfile.TemporaryDirectory() as directory:
    base = Path(directory)
    keys, units, env = base / "etc", base / "systemd", base / "server.env"
    common = ["--directory", str(keys), "--systemd-directory", str(units), "--server-env", str(env)]
    env.write_text(f"NODE_ENV=production\nJWT_SECRET={SAMPLE}\n", encoding="utf-8")

    code, out, _ = run(*common, "--status")
    check("nothing is on by default", (code, "vision-node: off" in out and ": on" not in out), (0, True))

    code, out, _ = run(*common, "--enable", "vision-node")
    check("a dry run writes nothing", (code, keys.exists(), units.exists(), SAMPLE in out), (0, False, False, False))

    code, out, err = run(*common, "--enable", "vision-node", "--apply")
    key_file = keys / "vision-node-identity.key"
    drop_in = units / "hydra-umc-vision-node.service.d" / "20-server-identity.conf"
    check("enabling writes the key and the drop-in", (code, key_file.is_file(), drop_in.is_file()), (0, True, True))
    check("the secret is never printed", SAMPLE in out or SAMPLE in err, False)
    check("the key file holds the signing key", key_file.read_text(encoding="utf-8").strip() == SAMPLE, True)
    if os.name == "posix":
        check("the key file is not readable by others", stat.S_IMODE(key_file.stat().st_mode) & 0o007, 0)
    text = drop_in.read_text(encoding="utf-8")
    check("the drop-in sets the variable of the service to that file", text, f"[Service]\nEnvironment=HYDRA_UMC_VISION_NODE_IDENTITY_KEY_FILE={key_file}\n")
    check("the other services stay off", (units / "hydra-umc-vla-engine.service.d").exists(), False)
    check("status says on for that one", "vision-node: on" in run(*common, "--status")[1], True)

    code, out, _ = run(*common, "--disable", "vision-node", "--apply")
    check("disabling renames the drop-in and keeps the key", (code, drop_in.exists(), drop_in.with_name(drop_in.name + ".off").is_file(), key_file.is_file()), (0, False, True, True))
    check("disabling twice changes nothing", run(*common, "--disable", "vision-node", "--apply")[1].startswith("IDENTITY=UNCHANGED"), True)

    for label, content, fragment in (
        ("an example key", "JWT_SECRET=SET_LOCALLY_TO_A_LONG_RANDOM_VALUE\n", "example value"),
        ("a short key", "JWT_SECRET=short\n", "fewer than 32"),
        ("an empty key", "JWT_SECRET=\n", "is empty"),
        ("a missing key", "NODE_ENV=production\n", "has no JWT_SECRET"),
    ):
        env.write_text(content, encoding="utf-8")
        code, _, err = run(*common, "--enable", "cognitive-node", "--apply")
        check(f"{label} is refused", (code, fragment in err, (keys / "cognitive-node-identity.key").exists()), (1, True, False))
    env.unlink()
    check("a missing server env is refused", run(*common, "--enable", "cognitive-node", "--apply")[0], 1)

    check("an unknown service is refused", run(*common, "--enable", "nowhere")[0], 2)
    check("enable and disable together are refused", run(*common, "--enable", "vla-engine", "--disable", "vla-engine")[0], 2)
    bad = base / "bad.json"
    bad.write_text(json.dumps({"format": "hydra-service-identity/1", "services": {"x": {"unit": "u"}}}), encoding="utf-8")
    check("a service entry without a variable is refused", run("--config", str(bad), "--status")[0], 2)

print(f"SERVICE_IDENTITY={'PASS' if not failures else 'FAIL'}")
raise SystemExit(1 if failures else 0)
