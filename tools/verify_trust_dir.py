#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - Trust directory step verification
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Proves provisioning/ensure_trust_dir.py: it calls the function of HYDRA-UMC-DEV-SERVER (a stand-in package here, so the check needs no checkout of that
program), says only what it would do without --apply, passes a refusal of the function on as status 2, ends with status 3 when the program is not found,
and that the installer runs it. When the sibling checkout of HYDRA-UMC-DEV-SERVER is present, the real function is run too, on a temporary directory,
as the account that runs the check: root creates the directory with mode 0700, anyone else is refused."""
from __future__ import annotations

import io
import os
import re
import stat
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "provisioning"))
import ensure_trust_dir as step  # noqa: E402

STAND_IN = '''
from pathlib import Path
TRUST_DIR = Path("/etc/hydra-umc/trust")
CALLS = []
def ensure_trust_dir(path=TRUST_DIR):
    if path.name == "refuse":
        raise RuntimeError("the trust directory is created by root")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    (path / "created-by-stand-in").write_text("yes")
'''


def run(argv, environ=None):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = step.main(argv, environ if environ is not None else {})
    return code, out.getvalue(), err.getvalue()


class TrustDirStep(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        package = self.base / "src" / "hydra_umc_dev_server"
        package.mkdir(parents=True)
        (package / "__init__.py").write_text("")
        (package / "trust_rotation.py").write_text(STAND_IN)
        self.src = self.base / "src"
        sys.modules.pop("hydra_umc_dev_server", None)
        sys.modules.pop("hydra_umc_dev_server.trust_rotation", None)

    def test_apply_calls_the_function_of_dev_server_on_the_directory(self):
        target = self.base / "trust"
        code, out, _ = run(["--apply", "--dev-server-src", str(self.src), "--dir", str(target)])
        self.assertEqual(code, 0)
        self.assertTrue((target / "created-by-stand-in").is_file())
        self.assertIn("Trust directory ready", out)

    def test_without_apply_nothing_is_created(self):
        target = self.base / "trust"
        code, out, _ = run(["--dev-server-src", str(self.src), "--dir", str(target)])
        self.assertEqual(code, 0)
        self.assertFalse(target.exists())
        self.assertIn("Dry run", out)

    def test_the_default_directory_is_the_one_dev_server_fixes(self):
        code, out, _ = run(["--dev-server-src", str(self.src)])
        self.assertEqual(code, 0)
        self.assertIn("/etc/hydra-umc/trust", out.replace("\\", "/"))

    def test_a_refusal_of_the_function_is_status_2_and_creates_nothing(self):
        target = self.base / "refuse"
        code, _, err = run(["--apply", "--dev-server-src", str(self.src), "--dir", str(target)])
        self.assertEqual(code, 2)
        self.assertIn("not created", err)
        self.assertFalse(target.exists())

    def test_without_dev_server_the_status_is_3_and_nothing_is_created(self):
        target = self.base / "trust"
        original = step.DEFAULT_SOURCES
        step.DEFAULT_SOURCES = ()
        self.addCleanup(setattr, step, "DEFAULT_SOURCES", original)
        code, _, err = run(["--apply", "--dir", str(target)])
        self.assertEqual(code, step.NOT_FOUND)
        self.assertIn("was not found", err)
        self.assertFalse(target.exists())

    def test_the_environment_names_the_place_of_dev_server(self):
        target = self.base / "trust"
        code, _, _ = run(["--apply", "--dir", str(target)], {"HYDRA_UMC_DEV_SERVER_SRC": str(self.src)})
        self.assertEqual(code, 0)
        self.assertTrue(target.is_dir())

    def test_a_folder_without_the_module_is_skipped_for_the_next_one(self):
        empty = self.base / "empty"
        empty.mkdir()
        found = step.load_ensure_trust_dir([empty, self.src])
        self.assertIsNotNone(found)
        self.assertEqual(found[2], self.src)
        self.assertIsNone(step.load_ensure_trust_dir([empty]))

    def test_the_installer_runs_the_step_and_does_not_stop_when_dev_server_is_missing(self):
        text = (ROOT / "provisioning" / "install_cm5_base.sh").read_text(encoding="utf-8")
        self.assertRegex(text, r"python3 provisioning/ensure_trust_dir\.py --apply")
        line = next(item for item in text.splitlines() if "ensure_trust_dir.py --apply" in item)
        self.assertIn("||", line, "status 3 (DEV-SERVER not found) must not stop the installer")


@unittest.skipUnless((ROOT.parent / "HYDRA-UMC-DEV-SERVER" / "src" / "hydra_umc_dev_server" / "trust_rotation.py").is_file(), "the sibling HYDRA-UMC-DEV-SERVER checkout is not present")
class RealFunction(unittest.TestCase):
    def test_the_real_function_makes_a_root_only_directory_or_refuses_a_user(self):
        sys.modules.pop("hydra_umc_dev_server", None)
        sys.modules.pop("hydra_umc_dev_server.trust_rotation", None)
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "trust"
            code, _, err = run(["--apply", "--dev-server-src", str(ROOT.parent / "HYDRA-UMC-DEV-SERVER" / "src"), "--dir", str(target)])
            geteuid = getattr(os, "geteuid", None)
            if geteuid is not None and geteuid() == 0:
                self.assertEqual(code, 0)
                self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o700)
            else:
                self.assertEqual(code, 2)
                self.assertTrue(re.search(r"root", err))
                self.assertFalse(target.exists())


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=0).result
    if result.wasSuccessful():
        print("TRUST_DIR_VERIFY=PASS")
        raise SystemExit(0)
    print("TRUST_DIR_VERIFY=FAIL", file=sys.stderr)
    raise SystemExit(1)
