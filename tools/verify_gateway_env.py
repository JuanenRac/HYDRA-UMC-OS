#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - Gateway .env generation verification
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Proves provisioning/gateway_env.py, provisioning/secret_output.py and the credentials of provisioning/wifi_provision.py: the passwords go to a root-only file and are not printed unless print_once is on; the generated .env is accepted by what the gateway and the broker demand of a production start (secret length, password length, an ACL rule\nthat covers every credential), is private, is never overwritten, and gives each bridge its own identity and namespace."""
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
spec = importlib.util.spec_from_file_location("hydra_umc_os_gateway_env", ROOT / "provisioning" / "gateway_env.py")
assert spec and spec.loader
ge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ge
spec.loader.exec_module(ge)
so = sys.modules["secret_output"]  # imported by gateway_env.py from its own folder
spec_wifi = importlib.util.spec_from_file_location("hydra_umc_os_wifi_for_secrets", ROOT / "provisioning" / "wifi_provision.py")
assert spec_wifi and spec_wifi.loader
wp = importlib.util.module_from_spec(spec_wifi)
sys.modules[spec_wifi.name] = wp
spec_wifi.loader.exec_module(wp)

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
check("a new file points the broker at the folder of its certificates", env["MQTT_TLS_DIR"], "/etc/hydra-umc/tls")
check("the folder can be chosen", values(ge.build_env("/srv/tls")[0])["MQTT_TLS_DIR"], "/srv/tls")
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
check("the passwords returned are the ones in the file", {n: passwords[n] for n in ge.BRIDGES} == {c["username"].rsplit("-", 1)[1]: c["password"] for c in credentials}, True)

with tempfile.TemporaryDirectory() as directory:
    path = Path(directory) / ".env"
    check("dry run creates nothing", (ge.main([str(path)]), path.exists()), (0, False))
    check("apply creates the file", (ge.main([str(path), "--apply"]), path.exists()), (0, True))
    if os.name != "nt":
        check("the file is private", stat.S_IMODE(os.stat(path).st_mode) & 0o077, 0)
    first = path.read_text(encoding="utf-8")
    check("a second apply never overwrites it", (ge.main([str(path), "--apply"]), path.read_text(encoding="utf-8")), (0, first))
    old = Path(directory) / "old.env"
    old.write_text("GATEWAY_JWT_SECRET=x\n", encoding="utf-8")
    check("an installation that already has a file keeps it as it is (no TLS line added)", (ge.main([str(old), "--apply"]), old.read_text(encoding="utf-8")), (0, "GATEWAY_JWT_SECRET=x\n"))

def run_main(module: object, argv: list[str], environ: dict[str, str]) -> tuple[int, str]:
    """main() with the given environment variables only; returns (exit code, everything it printed)."""
    saved = dict(os.environ)
    os.environ.clear()
    os.environ.update(environ)
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            code = module.main(argv)  # type: ignore[attr-defined]
    finally:
        os.environ.clear()
        os.environ.update(saved)
    return code, out.getvalue()


def mode(path: Path) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


POSIX = os.name != "nt"
NO_CONF = {"HYDRA_UMC_PROVISIONING_CONF": "/nonexistent/provisioning.conf"}

# --- the bridge passwords: a root-only file, the path printed, the values not printed unless print_once is on ---------------
with tempfile.TemporaryDirectory() as directory:
    env_path = Path(directory) / "etc" / "gateway.env"
    creds = Path(directory) / "etc" / "credentials" / "gateway-bridges.txt"
    code, printed = run_main(ge, [str(env_path), "--apply"], NO_CONF)
    secret_values = [c["password"] for c in json.loads(values(env_path.read_text(encoding="utf-8"))["MQTT_AUTH_JSON"])]
    check("by default the creation succeeds", code, 0)
    check("by default no password reaches the output", any(value in printed for value in secret_values), False)
    check("by default the output names the credentials file", str(creds) in printed, True)
    check("the credentials file holds every password", all(value in creds.read_text(encoding="utf-8") for value in secret_values), True)
    if POSIX:
        check("the credentials file is 0600", mode(creds), 0o600)
        check("its folder is 0700", mode(creds.parent), 0o700)
        check("the .env is 0600", mode(env_path), 0o600)
    check("no temporary file is left behind", sorted(p.name for p in creds.parent.iterdir()), ["gateway-bridges.txt"])
    before = creds.read_text(encoding="utf-8")
    run_main(ge, [str(env_path), "--apply"], NO_CONF)
    check("a second apply leaves the credentials file as it was", creds.read_text(encoding="utf-8"), before)
    if POSIX:
        os.chmod(env_path, 0o644)
        code, printed = run_main(ge, [str(env_path), "--apply"], NO_CONF)
        check("an existing .env with lax permissions is corrected to 0600", (code, mode(env_path)), (0, 0o600))
        link = Path(directory) / "link.env"
        link.symlink_to(env_path)
        check("an existing .env that is a link is refused", run_main(ge, [str(link), "--apply"], NO_CONF)[0], 1)

for label, argv, environ, expected in (
    ("--print-once prints the passwords", ["--print-once"], NO_CONF, True),
    ("HYDRA_UMC_PRINT_ONCE=1 prints the passwords", [], {**NO_CONF, "HYDRA_UMC_PRINT_ONCE": "1"}, True),
    ("--no-print-once wins over the environment", ["--no-print-once"], {**NO_CONF, "HYDRA_UMC_PRINT_ONCE": "1"}, False),
    ("a value that is not recognised keeps the conservative default", [], {**NO_CONF, "HYDRA_UMC_PRINT_ONCE": "maybe"}, False),
):
    with tempfile.TemporaryDirectory() as directory:
        env_path = Path(directory) / "gateway.env"
        code, printed = run_main(ge, [str(env_path), "--apply", *argv], environ)
        pw = [c["password"] for c in json.loads(values(env_path.read_text(encoding="utf-8"))["MQTT_AUTH_JSON"])]
        check(label, (code, all(value in printed for value in pw)), (0, expected))
        if expected:
            check(label + " exactly once", all(printed.count(value) == 1 for value in pw), True)

with tempfile.TemporaryDirectory() as directory:
    conf = Path(directory) / "provisioning.conf"
    conf.write_text("# comment\nprint_once = true  # for a device without a screen\n", encoding="utf-8")
    check("print_once = true in the configuration file turns it on", so.print_once_enabled(None, environ={}, conf=conf), True)
    check("the environment overrides the file", so.print_once_enabled(None, environ={"HYDRA_UMC_PRINT_ONCE": "0"}, conf=conf), False)
    check("print_once is off without file and variable", so.print_once_enabled(None, environ={}, conf=Path(directory) / "none"), False)

# --- atomicity ------------------------------------------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as directory:
    target = Path(directory) / "sub" / "secret.txt"
    check("a new file is written", so.write_private_atomic(target, "one"), True)
    check("an existing file is not replaced without overwrite", (so.write_private_atomic(target, "two"), target.read_text(encoding="utf-8")), (False, "one"))
    check("with overwrite it is replaced in one step", (so.write_private_atomic(target, "three", overwrite=True), target.read_text(encoding="utf-8")), (True, "three"))
    check("no temporary file stays", sorted(p.name for p in target.parent.iterdir()), ["secret.txt"])
    original_fsync = os.fsync

    def failing_fsync(descriptor: int) -> None:
        raise OSError("disk full")

    os.fsync = failing_fsync  # type: ignore[assignment]
    try:
        try:
            so.write_private_atomic(target, "partial", overwrite=True)
        except OSError:
            pass
    finally:
        os.fsync = original_fsync
    check("a failed write leaves the old content and no temporary file", (target.read_text(encoding="utf-8"), sorted(p.name for p in target.parent.iterdir())), ("three", ["secret.txt"]))
    if POSIX:
        os.chmod(target, 0o666)
        check("lax permissions of a secret file are corrected", (so.ensure_private_file(target), mode(target)), (True, 0o600))
        os.chmod(target.parent, 0o755)
        so.ensure_private_dir(target.parent)
        check("lax permissions of its folder are corrected", mode(target.parent), 0o700)

# --- the Wi-Fi setup credentials -----------------------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as directory:
    state = Path(directory) / "state"

    def run_wifi(extra: list[str], environ: dict[str, str]) -> tuple[int, str]:
        wp.serve_until_joined = lambda *a, **k: None  # type: ignore[assignment]  # no radio, no server
        return run_main(wp, ["--apply", "--state-dir", str(state), *extra], environ)

    code, printed = run_wifi([], NO_CONF)
    stored = json.loads((state / "credentials.json").read_text(encoding="utf-8"))
    check("Wi-Fi: by default neither the password nor the code is printed", (code, stored["password"] in printed, stored["code"] in printed), (0, False, False))
    check("Wi-Fi: the output names the file and how to read it", (str(state / "credentials.json") in printed, "sudo cat" in printed), (True, True))
    if POSIX:
        check("Wi-Fi: the state folder is 0700 and the file 0600", (mode(state), mode(state / "credentials.json")), (0o700, 0o600))
        os.chmod(state / "credentials.json", 0o644)
        wp.resolve_ap_credentials(state)
        check("Wi-Fi: a lax credentials file is corrected", mode(state / "credentials.json"), 0o600)
    (state / "credentials.json").unlink()
    code, printed = run_wifi(["--print-once"], NO_CONF)
    stored = json.loads((state / "credentials.json").read_text(encoding="utf-8"))
    check("Wi-Fi: print_once prints the password and the code once", (printed.count(stored["password"]), printed.count(stored["code"])), (1, 1))
    code, printed = run_wifi(["--print-once"], NO_CONF)
    check("Wi-Fi: print_once does not print again at the next start", (stored["password"] in printed, stored["code"] in printed), (False, False))

print()
if failures:
    print(f"GATEWAY_ENV_VERIFY=FAIL {failures} mismatches")
    sys.exit(1)
print(f"GATEWAY_ENV_VERIFY=PASS checks={checks}")
