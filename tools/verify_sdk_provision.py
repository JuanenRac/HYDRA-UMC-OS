#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - Python SDK provision check
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Prove, in temporary folders and with no root, that the installers of the services whose code imports `hydra_umc_sdk` put the package where the service can import it,
and stop BEFORE the program is copied when they cannot: the shell functions `provide_sdk_python` and `verify_sdk_importable` of provisioning/deploy_lib.sh, and the
generated installer of every service named in "needs_sdk" of config/installer_generation.json (it calls both, in that order, before the copy, and no other installer does)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "provisioning" / "deploy_lib.sh"
BASH = shutil.which("bash")


def posix(path: Path) -> str:
    return path.as_posix()


@unittest.skipUnless(BASH, "bash is not installed")
class ProvisionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self.source = self.base / "repos" / "HYDRA-UMC-SDK" / "clients" / "python" / "src" / "hydra_umc_sdk"
        self.source.mkdir(parents=True)
        (self.source / "__init__.py").write_text("VERSION = '0'\n", encoding="utf-8")
        (self.source / "mcu_errors.py").write_text("ERROR_CODES = {1: 'x'}\n", encoding="utf-8")
        self.destination = self.base / "opt" / "sdk-python"

    def run_shell(self, script: str, **extra: str) -> subprocess.CompletedProcess[str]:
        environment = dict(os.environ)
        environment.update({"HYDRA_UMC_SDK_PYTHON_DIR": posix(self.destination), "HYDRA_UMC_PYTHON": posix(Path(sys.executable)), "PYTHONDONTWRITEBYTECODE": "1"})
        environment.update(extra)
        body = f'set -euo pipefail\nROOT="{posix(self.base / "repos")}"\nsource "{posix(LIB)}"\n{script}\n'
        return subprocess.run([str(BASH), "-c", body], capture_output=True, text=True, env=environment, check=False)

    def test_the_package_is_copied_where_the_service_can_read_it(self) -> None:
        result = self.run_shell("provide_sdk_python")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.destination / "hydra_umc_sdk" / "mcu_errors.py").is_file())

    def test_a_second_run_replaces_the_copy_and_leaves_no_stale_file(self) -> None:
        self.run_shell("provide_sdk_python")
        (self.destination / "hydra_umc_sdk" / "stale.py").write_text("x = 1\n", encoding="utf-8")
        (self.source / "mcu_errors.py").write_text("ERROR_CODES = {2: 'y'}\n", encoding="utf-8")
        result = self.run_shell("provide_sdk_python")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.destination / "hydra_umc_sdk" / "stale.py").exists())
        self.assertIn("2: 'y'", (self.destination / "hydra_umc_sdk" / "mcu_errors.py").read_text(encoding="utf-8"))

    def test_a_missing_sdk_stops_with_status_two_and_a_message(self) -> None:
        shutil.rmtree(self.base / "repos" / "HYDRA-UMC-SDK")
        result = self.run_shell("provide_sdk_python")
        self.assertEqual(result.returncode, 2)
        self.assertIn("The Python SDK is missing", result.stderr)
        self.assertFalse(self.destination.exists())

    def test_the_source_can_be_named_by_a_setting(self) -> None:
        elsewhere = self.base / "elsewhere" / "hydra_umc_sdk"
        shutil.copytree(self.source, elsewhere)
        shutil.rmtree(self.base / "repos" / "HYDRA-UMC-SDK")
        result = self.run_shell("provide_sdk_python", HYDRA_UMC_SDK_SOURCE=posix(elsewhere))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_the_check_passes_when_the_module_can_be_imported(self) -> None:
        result = self.run_shell("provide_sdk_python\nverify_sdk_importable hydra_umc_sdk hydra_umc_sdk.mcu_errors")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("SDK=PASS", result.stdout)

    def test_the_check_fails_with_status_two_when_the_package_was_not_put_there(self) -> None:
        result = self.run_shell("verify_sdk_importable hydra_umc_sdk.mcu_errors")
        self.assertEqual(result.returncode, 2)
        self.assertIn("SDK=FAIL", result.stderr)

    def test_the_check_fails_when_the_module_the_service_needs_is_not_in_the_package(self) -> None:
        (self.source / "mcu_errors.py").unlink()
        result = self.run_shell("provide_sdk_python\nverify_sdk_importable hydra_umc_sdk.mcu_errors")
        self.assertEqual(result.returncode, 2)
        self.assertIn("hydra_umc_sdk.mcu_errors", result.stderr)

    def test_the_check_does_not_trust_the_working_folder(self) -> None:
        # a package of the same name in the folder the installer runs from must not make the check pass
        decoy = self.base / "cwd" / "hydra_umc_sdk"
        decoy.mkdir(parents=True)
        (decoy / "__init__.py").write_text("", encoding="utf-8")
        (decoy / "mcu_errors.py").write_text("", encoding="utf-8")
        environment = dict(os.environ, HYDRA_UMC_SDK_PYTHON_DIR=posix(self.destination), HYDRA_UMC_PYTHON=posix(Path(sys.executable)))
        body = f'set -euo pipefail\nROOT="{posix(self.base)}"\nsource "{posix(LIB)}"\nverify_sdk_importable hydra_umc_sdk.mcu_errors'
        result = subprocess.run([str(BASH), "-c", body], capture_output=True, text=True, env=environment, cwd=self.base / "cwd", check=False)
        self.assertEqual(result.returncode, 2)


class InstallerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = json.loads((ROOT / "config" / "installer_generation.json").read_text(encoding="utf-8"))

    def test_the_semantic_planner_needs_the_error_vocabulary_of_the_sdk(self) -> None:
        self.assertEqual(self.config["needs_sdk"]["semantic-planner"], ["hydra_umc_sdk.mcu_errors"])

    def test_the_installers_of_those_services_provide_and_check_the_sdk_before_the_copy(self) -> None:
        for short, modules in self.config["needs_sdk"].items():
            text = (ROOT / "provisioning" / f"install_{short.replace('-', '_')}.sh").read_text(encoding="utf-8")
            provide, verify, copy = text.index("\nprovide_sdk_python\n"), text.index("\nverify_sdk_importable " + " ".join(modules)), text.index('cp -a "$SOURCE/src"')
            self.assertLess(provide, verify, short)
            self.assertLess(verify, copy, short)

    def test_the_folder_of_configuration_the_unit_names_is_copied_and_its_file_is_checked_before_anything_is_installed(self) -> None:
        text = (ROOT / "provisioning" / "install_semantic_planner.sh").read_text(encoding="utf-8")
        self.assertIn('cp -a "$SOURCE/configs" "$TARGET/"', text)
        for required in self.config["required_files"]["semantic-planner"]:
            check = text.index(f'[[ -f "$SOURCE/{required}" ]]')
            self.assertLess(check, text.index("provide_sdk_python"))
            self.assertLess(check, text.index('cp -a "$SOURCE/src"'))
            self.assertIn("exit 2", text[check : check + 220])

    def test_every_path_the_unit_of_the_semantic_planner_names_inside_its_folder_is_installed(self) -> None:
        # the unit is in the repository of the service, which may not be next to this one: the check runs when it is
        unit = ROOT.parent / "HYDRA-UMC-SEMANTIC-PLANNER" / "systemd" / "hydra-umc-semantic-planner.service"
        if not unit.is_file():
            self.skipTest("HYDRA-UMC-SEMANTIC-PLANNER is not next to this repository")
        text = (ROOT / "provisioning" / "install_semantic_planner.sh").read_text(encoding="utf-8")
        copied = {"src"} | set(self.config.get("extra_copy_dirs", {}).get("semantic-planner", []))
        import re

        for folder in re.findall(r"/opt/hydra-umc/semantic-planner/([A-Za-z0-9_.-]+)", unit.read_text(encoding="utf-8")):
            if folder in ("data", "models", "workspace"):
                continue
            self.assertIn(folder, copied, f"the unit names {folder}/ but the installer does not copy it")
            self.assertIn(f'cp -a "$SOURCE/{folder}" "$TARGET/"', text)

    def test_no_other_installer_provides_the_sdk(self) -> None:
        wanted = {f"install_{short.replace('-', '_')}.sh" for short in self.config["needs_sdk"]}
        for path in (ROOT / "provisioning").glob("install_*.sh"):
            if path.name not in wanted:
                self.assertNotIn("provide_sdk_python", path.read_text(encoding="utf-8"), path.name)

    def test_the_generator_reproduces_the_installer_of_the_semantic_planner(self) -> None:
        shown = subprocess.run([sys.executable, str(ROOT / "provisioning" / "generate_installers.py"), "--show", "semantic-planner"], capture_output=True, text=True, check=False)
        self.assertEqual(shown.returncode, 0, shown.stderr)
        committed = (ROOT / "provisioning" / "install_semantic_planner.sh").read_text(encoding="utf-8")
        self.assertEqual(shown.stdout.replace("\r\n", "\n"), committed.replace("\r\n", "\n"))


if __name__ == "__main__":
    unittest.main()
