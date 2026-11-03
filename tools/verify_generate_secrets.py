#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - Secret generation verification
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Proves provisioning/generate_secrets.py: no example value of a deployment template survives, the operator's own values are left alone, a shared token is mirrored, and --check
refuses what a server would refuse."""
from __future__ import annotations

import contextlib
import importlib.util
import io
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
    adopt_env = base / "adopt" / "adopt.env"
    other = base / "other.env"
    other.write_text("HYDRA_UMC_VOICE_UI_TOKEN=" + "ab" * 32 + chr(10), encoding="utf-8")
    check("adopt creates a file", gs.main([str(adopt_env), "--create-from", str(template), "--apply", "--adopt", f"HYDRA_UMC_VOICE_UI_TOKEN={other}:HYDRA_UMC_VOICE_UI_TOKEN"]), 0)
    adopted_token = next(v for _, k, v in gs.parse(adopt_env.read_text(encoding="utf-8")) if k == "HYDRA_UMC_VOICE_UI_TOKEN")
    check("an adopted value is the one the other file already had", adopted_token, "ab" * 32)
    bad = base / "bad.env"
    bad.write_text(TEMPLATE, encoding="utf-8")
    check("the check refuses a copy of the template", gs.main([str(bad), "--check"]), 1)
    check("the check refuses a missing file", gs.main([str(base / "missing.env"), "--check"]), 1)
    report_io = io.StringIO()
    with contextlib.redirect_stderr(report_io):
        code = gs.main([str(bad), "--check"])
    report = report_io.getvalue()
    check("the report names the line and the reason, not the setting", code == 1 and "line " in report and "is still an example value" in report and "JWT_SECRET" not in report, True)
    check("the codes give the line, the setting and the reason", gs.problem_codes("A=1" + chr(10) + "JWT_SECRET=short" + chr(10)), [(2, "JWT_SECRET", "short_secret")])

# --- the first administrator's password: a root-only file, the path printed, the value not printed unless print_once is on ---------
NO_CONF = {"HYDRA_UMC_PROVISIONING_CONF": "/nonexistent/provisioning.conf"}


def run_main(argv: list[str], environ: dict[str, str]) -> tuple[int, str, str]:
    """main() with the given environment variables only; returns (exit code, stdout, stderr)."""
    saved = dict(os.environ)
    os.environ.clear()
    os.environ.update(environ)
    out, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = gs.main(argv)
    finally:
        os.environ.clear()
        os.environ.update(saved)
    return code, out.getvalue(), err.getvalue()


def admin_password(env_file: Path) -> str:
    return next(v for _, k, v in gs.parse(env_file.read_text(encoding="utf-8")) if k == gs.ADMIN_PASSWORD_KEY)


with tempfile.TemporaryDirectory() as directory:
    base = Path(directory)
    template = ROOT / "provisioning" / "server.env.example"
    env = base / "etc" / "server.env"
    code, printed, _ = run_main([str(env), "--create-from", str(template), "--apply"], NO_CONF)
    creds = base / "etc" / "credentials" / "server-admin.txt"
    password = admin_password(env)
    check("admin: the run succeeds", code, 0)
    check("admin: by default the password is not printed", password in printed, False)
    check("admin: the output names the file and the sudo cat command", (str(creds) in printed, f"sudo cat {creds}" in printed), (True, True))
    check("admin: the file holds the password and the user name", (f"password: {password}" in creds.read_text(encoding="utf-8"), "username: hydra_umc" in creds.read_text(encoding="utf-8")), (True, True))
    if os.name != "nt":
        check("admin: the file is 0600 and its folder 0700", (stat.S_IMODE(os.stat(creds).st_mode), stat.S_IMODE(os.stat(creds.parent).st_mode)), (0o600, 0o700))
    check("admin: the folder holds nothing else (no temporary file left)", [p.name for p in creds.parent.iterdir()], ["server-admin.txt"])
    check("admin: a second run changes nothing and prints no password", (run_main([str(env), "--apply"], NO_CONF)[0], password in run_main([str(env), "--apply"], NO_CONF)[1]), (0, False))
    check("admin: the file is not rewritten", f"password: {password}" in creds.read_text(encoding="utf-8"), True)

    # an existing credentials file is never overwritten and stops the run before the env file is written
    env2 = base / "two" / "server.env"
    other_creds = base / "two" / "credentials" / "server-admin.txt"
    other_creds.parent.mkdir(parents=True)
    other_creds.write_text("old\n", encoding="utf-8")
    code, _, error = run_main([str(env2), "--create-from", str(template), "--apply"], NO_CONF)
    check("admin: an existing credentials file stops the run", (code, env2.exists(), other_creds.read_text(encoding="utf-8")), (1, False, "old\n"))
    check("admin: ...and the reason is said", "never overwritten" in error, True)

    # a symbolic link is refused
    if os.name != "nt":
        env3 = base / "three" / "server.env"
        link = base / "three" / "credentials" / "server-admin.txt"
        link.parent.mkdir(parents=True)
        target = base / "elsewhere.txt"
        link.symlink_to(target)
        code, _, error = run_main([str(env3), "--create-from", str(template), "--apply"], NO_CONF)
        check("admin: a symbolic link is refused", (code, env3.exists(), target.exists(), "symbolic link" in error), (1, False, False, True))

    # the file named with --admin-credentials-file
    env4 = base / "four" / "server.env"
    named = base / "private" / "admin.txt"
    code, printed, _ = run_main([str(env4), "--create-from", str(template), "--apply", "--admin-credentials-file", str(named)], NO_CONF)
    check("admin: --admin-credentials-file is used", (code, named.exists(), str(named) in printed, (env4.parent / "credentials").exists()), (0, True, True, False))

    # print_once: flag, environment and configuration file (the first that is set wins)
    conf = base / "provisioning.conf"
    conf.write_text("print_once = true\n", encoding="utf-8")
    cases = [
        ("--print-once prints the password", ["--print-once"], NO_CONF, True),
        ("HYDRA_UMC_PRINT_ONCE=1 prints the password", [], {**NO_CONF, "HYDRA_UMC_PRINT_ONCE": "1"}, True),
        ("print_once = true in the configuration file prints the password", [], {"HYDRA_UMC_PROVISIONING_CONF": str(conf)}, True),
        ("--no-print-once wins over the environment", ["--no-print-once"], {**NO_CONF, "HYDRA_UMC_PRINT_ONCE": "1"}, False),
        ("the environment wins over the file", [], {"HYDRA_UMC_PROVISIONING_CONF": str(conf), "HYDRA_UMC_PRINT_ONCE": "0"}, False),
    ]
    for number, (label, argv, environ, expected) in enumerate(cases):
        target_env = base / f"po{number}" / "server.env"
        code, printed, _ = run_main([str(target_env), "--create-from", str(template), "--apply", *argv], environ)
        value = admin_password(target_env)
        check("admin: " + label, (code, value in printed, printed.count(value) <= 1), (0, expected, True))
        check("admin: ...and the file has it either way", f"password: {value}" in (target_env.parent / "credentials" / "server-admin.txt").read_text(encoding="utf-8"), True)

    # an operator's own password is never generated, so no file and no output
    env5 = base / "five" / "server.env"
    env5.parent.mkdir()
    env5.write_text(filled.replace(generated[gs.ADMIN_PASSWORD_KEY], "a-password-of-my-own-1"), encoding="utf-8")
    code, printed, _ = run_main([str(env5), "--apply"], NO_CONF)
    check("admin: a chosen password makes no credentials file", (code, (env5.parent / "credentials").exists(), "a-password-of-my-own-1" in printed), (0, False, False))

print()
if failures:
    print(f"GENERATE_SECRETS_VERIFY=FAIL {failures} mismatches")
    sys.exit(1)
print(f"GENERATE_SECRETS_VERIFY=PASS checks={checks}")
