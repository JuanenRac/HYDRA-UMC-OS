#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - tools/verify_os_guard_and_docs.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Check the Debian release guard and a few facts the READMEs state.

* the guard accepts the supported release, warns by default on another one,
  refuses it in enforce mode and stays silent when switched off;
* the installer runs the guard;
* no README names a device state the agent never produces, or promises a
  placeholder access-point password;
* the "Child Projects" block of every README lists only projects whose
  manifest names this repository as the parent (checked when the sibling
  checkouts are present).
"""
from __future__ import annotations

import io
import json
import re
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "provisioning"))

import os_release_guard as guard  # noqa: E402

TRIXIE = 'PRETTY_NAME="Debian GNU/Linux 13 (trixie)"\nID=debian\nVERSION_CODENAME=trixie\n'
BOOKWORM = 'ID=debian\nVERSION_CODENAME=bookworm\n'
READMES = ["README.md"] + [f"README_{code}.md" for code in ("deu", "fra", "ita", "jpn", "por", "spa", "zho")]
failures: list[str] = []


def expect(condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def run_guard(text: str, *args: str) -> tuple[int, str, str]:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "os-release"
        path.write_text(text, encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = guard.main(["--os-release", str(path), *args])
        return code, out.getvalue(), err.getvalue()


def check_guard() -> None:
    code, out, _ = run_guard(TRIXIE, "--mode", "enforce")
    expect(code == 0 and "PASS" in out, "trixie must pass in enforce mode")
    code, _, err = run_guard(BOOKWORM, "--mode", "warn")
    expect(code == 0 and "WARN" in err, "an unsupported release only warns by default")
    code, _, err = run_guard(BOOKWORM, "--mode", "enforce")
    expect(code == 3 and "FAIL" in err, "enforce mode must refuse an unsupported release")
    code, out, err = run_guard(BOOKWORM, "--mode", "off")
    expect(code == 0 and not out and not err, "off mode must be silent")
    code, _, _ = run_guard(BOOKWORM, "--mode", "enforce", "--supported", "bookworm, trixie")
    expect(code == 0, "the supported list must be configurable")
    code, _, _ = run_guard("ID=ubuntu\nVERSION_CODENAME=trixie\n", "--mode", "enforce")
    expect(code == 3, "another distribution with the same codename must be refused")
    code, _, _ = run_guard("", "--mode", "enforce")
    expect(code == 3, "an unreadable release must be refused in enforce mode")
    installer = (ROOT / "provisioning" / "install_cm5_base.sh").read_text(encoding="utf-8")
    expect("os_release_guard.py" in installer, "install_cm5_base.sh must run the release guard")


def check_readmes() -> None:
    for name in READMES:
        text = (ROOT / name).read_text(encoding="utf-8")
        expect("INHIBITED" not in text, f"{name} names a state the agent never produces")
        if name == "README.md":
            expect("placeholder AP password" not in text, f"{name} promises a placeholder access-point password")
        start = text.find("**[HYDRA-UMC-SDK]")
        if start < 0:
            failures.append(f"{name}: related projects block not found")
            continue
        block = []
        for line in text[start:].splitlines():
            if line.startswith("**") and not line.startswith("- **"):
                break
            block.append(line)
        for match in re.finditer(r"\[(HYDRA-UMC-[A-Z0-9-]+)\]", "\n".join(block)):
            manifest = ROOT.parent / match.group(1) / "hydra-umc.project.json"
            if not manifest.is_file():
                continue
            parent = json.loads(manifest.read_text(encoding="utf-8")).get("parent")
            expect(parent == "HYDRA-UMC-OS", f"{name}: {match.group(1)} is listed as a child but its parent is {parent!r}")


def main() -> int:
    check_guard()
    check_readmes()
    if failures:
        for message in failures:
            print(f"OS_GUARD_AND_DOCS=FAIL {message}", file=sys.stderr)
        return 1
    print("OS_GUARD_AND_DOCS=PASS guard modes, installer hook, README facts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
