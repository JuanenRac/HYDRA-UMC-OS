#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - Pinned Go toolchain verification
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The Go services are built with one pinned, checksum-verified toolchain (provisioning/go_toolchain.sh), not the golang-go of the
Debian archive, which is older than their go.mod asks for. No root, no network: a stand-in `curl` hands over a tarball made here, and
the helper is run with it (a good one, a corrupted one, and a toolchain that is already installed). When the sibling projects are
checked out, their go.mod minimum is compared with the pinned version."""

from __future__ import annotations

import hashlib
import io
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROVISIONING = ROOT / "provisioning"
HELPER = PROVISIONING / "go_toolchain.sh"
GO_INSTALLERS = ("install_job_dispatcher.sh", "install_node_healing.sh", "install_telemetry_collector.sh")
BASH = shutil.which("bash")


def pinned() -> tuple[str, str, str]:
    text = HELPER.read_text(encoding="utf-8")
    version = re.search(r'^GO_VERSION="([^"]+)"', text, re.M)
    tarball = re.search(r'^GO_TARBALL="([^"]+)"', text, re.M)
    digest = re.search(r'^GO_SHA256="([^"]+)"', text, re.M)
    assert version and tarball and digest
    return version.group(1), tarball.group(1), digest.group(1)


def version_tuple(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", text)[:3])


def fake_toolchain() -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, content, mode in (("go/bin/go", b"#!/bin/sh\necho fake go\n", 0o755), ("go/VERSION", b"go-fake\n", 0o644)):
            info = tarfile.TarInfo(name)
            info.size = len(content)
            info.mode = mode
            archive.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


@unittest.skipUnless(BASH, "bash is needed")
class GoToolchainTests(unittest.TestCase):
    def test_the_pinned_values_are_consistent(self) -> None:
        version, tarball, digest = pinned()
        self.assertRegex(version, r"^\d+\.\d+(\.\d+)?$")
        self.assertEqual(tarball, "go${GO_VERSION}.linux-arm64.tar.gz")
        self.assertTrue(tarball.endswith(".linux-arm64.tar.gz"))
        self.assertRegex(digest, r"^[0-9a-f]{64}$")
        self.assertEqual(subprocess.run([BASH, "-n", HELPER.as_posix()], capture_output=True).returncode, 0)

    def test_every_go_installer_uses_it_and_none_installs_the_packaged_go(self) -> None:
        for name in GO_INSTALLERS:
            text = (PROVISIONING / name).read_text(encoding="utf-8")
            self.assertNotIn("golang-go", text.replace("golang-go archive", ""), name)
            self.assertIn('source "$HERE/go_toolchain.sh"', text, name)
            self.assertIn("ensure_go", text, name)
            self.assertIn('"$GO_BIN" build', text, name)
            self.assertNotRegex(text, r"(?m)^\s*\(\s*cd [^)]*&&\s*go build", name)
            self.assertRegex(text, r'(?m)^HERE=', name)
            self.assertEqual(subprocess.run([BASH, "-n", (PROVISIONING / name).as_posix()], capture_output=True).returncode, 0, name)
        self.assertNotIn("GO_SHA256=", (PROVISIONING / "install_job_dispatcher.sh").read_text(encoding="utf-8"), "the pin lives in one place")

    def run_helper(self, tarball: bytes, sha: str, root: Path, bin_dir: Path, calls: Path) -> subprocess.CompletedProcess[str]:
        payload = bin_dir / "payload.tgz"
        payload.write_bytes(tarball)
        (bin_dir / "curl").write_text(f'#!/bin/sh\necho curl >> "{calls.as_posix()}"\nout=""\nwhile [ $# -gt 0 ]; do if [ "$1" = "-o" ]; then out="$2"; fi; shift; done\ncp "{payload.as_posix()}" "$out"\n', encoding="utf-8")
        (bin_dir / "curl").chmod(0o755)
        script = f'set -euo pipefail\nsource "{HELPER.as_posix()}"\nGO_SHA256="{sha}"\nensure_go\necho "GO_BIN=$GO_BIN"\n'
        environment = {**os.environ, "PATH": f"{bin_dir.as_posix()}{os.pathsep}{os.environ['PATH']}", "HYDRA_UMC_GO_ROOT": root.as_posix()}
        return subprocess.run([BASH, "-c", script], capture_output=True, text=True, env=environment)

    def test_a_good_tarball_is_installed_and_a_corrupted_one_is_refused(self) -> None:
        good = fake_toolchain()
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "go-root"
            bins = base / "bin"
            bins.mkdir()
            calls = base / "calls.txt"
            ok = self.run_helper(good, hashlib.sha256(good).hexdigest(), root, bins, calls)
            self.assertEqual(ok.returncode, 0, ok.stderr)
            self.assertIn(f"GO_BIN={root.as_posix()}/bin/go", ok.stdout)
            self.assertTrue((root / "bin" / "go").is_file())
            self.assertEqual(calls.read_text().count("curl"), 1)
            # already installed: nothing is downloaded again
            again = self.run_helper(good, hashlib.sha256(good).hexdigest(), root, bins, calls)
            self.assertEqual(again.returncode, 0, again.stderr)
            self.assertEqual(calls.read_text().count("curl"), 1)

            # a tarball whose digest is not the pinned one is not unpacked
            other_root = base / "other-root"
            bad = self.run_helper(good + b"tampered", hashlib.sha256(good).hexdigest(), other_root, bins, calls)
            self.assertEqual(bad.returncode, 2, bad.stderr)
            self.assertIn("does not match the pinned value", bad.stderr)
            self.assertFalse(other_root.exists())

    def test_the_pinned_go_is_not_older_than_what_the_services_ask_for(self) -> None:
        version, _, _ = pinned()
        wanted = {
            "HYDRA-UMC-JOB-DISPATCHER": "go.mod",
            "HYDRA-UMC-NODE-HEALING": "go.mod",
            "HYDRA-UMC-TELEMETRY-COLLECTOR": "src/go.mod",
        }
        checked = 0
        for project, relative in wanted.items():
            path = ROOT.parent / project / relative
            if not path.is_file():
                continue
            minimum = re.search(r"(?m)^go\s+([\d.]+)", path.read_text(encoding="utf-8"))
            self.assertIsNotNone(minimum, path)
            self.assertLessEqual(version_tuple(minimum.group(1)), version_tuple(version), f"{project} needs Go {minimum.group(1)}, the pin is {version}")
            checked += 1
        if checked == 0:
            self.skipTest("the sibling Go projects are not checked out")


if __name__ == "__main__":
    unittest.main(verbosity=2)
