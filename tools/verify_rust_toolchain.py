#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - Rust compiler requirement verification
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The Rust programs are built on the device with the compiler of the Debian archive. Their hooks first compare `rust-version` of
Cargo.toml with `rustc --version` (provisioning/rust_toolchain.sh) and stop with a plain message when the compiler is too old.
No root, no network: a stand-in `rustc` answers a chosen version. When the sibling projects are checked out, none of them may ask
for more than the compiler of Debian trixie."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROVISIONING = ROOT / "provisioning"
HELPER = PROVISIONING / "rust_toolchain.sh"
# The rustc of Debian trixie, the system of the CM5.
DEVICE_RUSTC = (1, 85)
RUST_PROGRAMS = {
    "twin": "HYDRA-UMC-TWIN",
    "orchestrator": "HYDRA-UMC-ORCHESTRATOR",
    "hil-bridge": "HYDRA-UMC-HIL-BRIDGE",
    "swarm-sync": "HYDRA-UMC-SWARM-SYNC",
}
BASH = shutil.which("bash")


@unittest.skipUnless(BASH, "bash is needed")
class RustToolchainTests(unittest.TestCase):
    def test_every_rust_hook_checks_the_compiler_before_it_builds(self) -> None:
        for short, project in RUST_PROGRAMS.items():
            text = (PROVISIONING / "build_hooks" / f"{short}.sh").read_text(encoding="utf-8")
            check = f'require_rust "$SOURCE" {project}'
            self.assertIn('source "$HERE/rust_toolchain.sh"', text, short)
            self.assertIn(check, text, short)
            self.assertLess(text.index(check), text.index('hydra_cargo_in "$SOURCE" build'), short)

    def run_helper(self, rust_version: str | None, rustc: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            line = f'rust-version = "{rust_version}"\n' if rust_version else ""
            # a rust-version outside [package] is not the one of the program
            (base / "Cargo.toml").write_text(f'[package]\nname = "x"\n{line}\n[dependencies]\n', encoding="utf-8")
            stand_in = base / "rustc"
            stand_in.write_text(f'#!/bin/sh\necho "rustc {rustc} (abc 2026-01-01)"\n', encoding="utf-8", newline="\n")
            stand_in.chmod(0o755)
            script = f'set -euo pipefail\nsource "{HELPER.as_posix()}"\nrequire_rust "{base.as_posix()}" HYDRA-UMC-X\necho BUILD\n'
            environment = {**os.environ, "PATH": f"{base.as_posix()}{os.pathsep}{os.environ['PATH']}"}
            return subprocess.run([BASH, "-c", script], capture_output=True, text=True, env=environment)

    def test_an_old_compiler_stops_with_a_plain_message(self) -> None:
        result = self.run_helper("1.88", "1.85.1")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertNotIn("BUILD", result.stdout)
        self.assertIn("HYDRA-UMC-X needs rustc 1.88 or newer to build; this device has rustc 1.85.1", result.stderr)

    def test_a_new_enough_compiler_goes_on(self) -> None:
        for wanted, have in (("1.85", "1.85.1"), ("1.85", "1.98.0"), ("1.9", "1.85.0"), (None, "1.70.0"), ("1.88", "1.88.0-nightly")):
            result = self.run_helper(wanted, have)
            self.assertEqual(result.returncode, 0, f"{wanted} {have}: {result.stderr}")
            self.assertIn("BUILD", result.stdout)

    def test_no_sibling_program_asks_for_more_than_the_compiler_of_the_device(self) -> None:
        checked = 0
        for project in RUST_PROGRAMS.values():
            path = ROOT.parent / project / "Cargo.toml"
            if not path.is_file():
                continue
            wanted = re.search(r'(?m)^rust-version\s*=\s*"(\d+)\.(\d+)', path.read_text(encoding="utf-8"))
            self.assertIsNotNone(wanted, f"{project} names no rust-version")
            assert wanted
            self.assertLessEqual((int(wanted.group(1)), int(wanted.group(2))), DEVICE_RUSTC, project)
            checked += 1
        if checked == 0:
            self.skipTest("the sibling Rust projects are not checked out")


if __name__ == "__main__":
    unittest.main(verbosity=2)
