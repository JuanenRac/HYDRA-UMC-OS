#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - safety zones installer check
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Prove, in temporary folders and with no root, that the installer of HYDRA-UMC-SAFETY-ZONES asks the account of the service whether it can read its zones file BEFORE it
copies anything or touches the running service, and ends with status 2 and a clear message when it cannot (the program that runs now stays as it is).

The hook `provisioning/build_hooks/safety-zones.sh` is run in a shell with a stand-in for the program (only `prepare-config` and `check-access`), a stand-in for
`systemctl` that records what it is asked, and folders in a temporary directory; when HYDRA-UMC-SAFETY-ZONES is next to this repository the same hook is also run
against its real `check-access`."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "provisioning" / "build_hooks" / "safety-zones.sh"
INSTALLER = ROOT / "provisioning" / "install_safety_zones.sh"
BASH = shutil.which("bash")
REAL = ROOT.parent / "HYDRA-UMC-SAFETY-ZONES"

STAND_IN = """\"\"\"Stand-in for hydra_umc_safety_zones.main: the two commands the installer calls.\"\"\"
import os
import shutil
import sys

args = sys.argv[1:]


def option(name):
    return args[args.index(name) + 1]


if args[0] == "prepare-config":
    zones, legacy = option("--zones-file"), option("--legacy-file")
    if not os.path.exists(zones) and os.path.isfile(legacy):
        shutil.copyfile(legacy, zones)
    print("prepare-config done")
    sys.exit(0)
if args[0] == "check-access":
    if os.environ.get("FAKE_ACCOUNT_CANNOT_READ") == "1":
        print("[safety-zones] cannot read the zones file: the directory cannot be entered by this account", file=sys.stderr)
        sys.exit(2)
    try:
        with open(option("--zones-file"), "rb") as handle:
            handle.read(1)
    except OSError as exc:
        print("[safety-zones] cannot read the zones file: %s" % exc, file=sys.stderr)
        sys.exit(2)
    print("readable")
    sys.exit(0)
sys.exit(64)
"""


def posix(path: Path) -> str:
    return path.as_posix()


@unittest.skipUnless(BASH, "bash is not installed")
class HookTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self.source = self.base / "HYDRA-UMC-SAFETY-ZONES"
        package = self.source / "src" / "hydra_umc_safety_zones"
        package.mkdir(parents=True)
        (package / "__init__.py").write_text("", encoding="utf-8")
        (package / "main.py").write_text(STAND_IN, encoding="utf-8")
        self.config_dir = self.base / "etc" / "hydra-umc-safety-zones"
        self.legacy = self.base / "etc" / "hydra-umc" / "safety-zones.zones.json"
        self.legacy.parent.mkdir(parents=True)
        self.calls = self.base / "systemctl.calls"
        self.systemctl = self.base / "systemctl"
        self.set_unit(active=False)

    def set_unit(self, active: bool) -> None:
        code = 0 if active else 3
        self.systemctl.write_text(f'#!/usr/bin/env bash\necho "$*" >> "{posix(self.calls)}"\n[[ "$1" == "is-active" ]] && exit {code}\nexit 0\n', encoding="utf-8", newline="\n")
        self.systemctl.chmod(0o755)

    def run_hook(self, source: Path | None = None, **extra: str) -> subprocess.CompletedProcess[str]:
        environment = dict(os.environ)
        environment.update(
            {
                "HYDRA_UMC_SAFETY_ZONES_CONFIG_DIR": posix(self.config_dir),
                "HYDRA_UMC_SAFETY_ZONES_LEGACY_FILE": posix(self.legacy),
                "HYDRA_UMC_PYTHON": posix(Path(sys.executable)),
                "HYDRA_UMC_SYSTEMCTL": posix(self.systemctl),
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )
        environment.update(extra)
        body = f'set -euo pipefail\nSOURCE="{posix(source or self.source)}"\nSVC_USER=hydra-umc-safety-zones\nsource "{posix(HOOK)}"\necho HOOK_DONE\n'
        return subprocess.run([str(BASH), "-c", body], capture_output=True, text=True, env=environment, check=False)

    def asked_systemctl(self) -> list[str]:
        return self.calls.read_text(encoding="utf-8").splitlines() if self.calls.exists() else []

    def test_the_folder_of_the_service_is_created_when_it_is_not_there(self) -> None:
        self.assertFalse(self.config_dir.exists())
        self.run_hook()
        self.assertTrue(self.config_dir.is_dir())

    def test_a_first_installation_without_zones_goes_on_and_says_the_service_waits_for_them(self) -> None:
        result = self.run_hook()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("HOOK_DONE", result.stdout)
        self.assertIn("SAFETY_ZONES=WAIT", result.stderr)

    def test_a_missing_zones_file_while_the_service_runs_stops_the_installer(self) -> None:
        self.set_unit(active=True)
        result = self.run_hook()
        self.assertEqual(result.returncode, 2)
        self.assertIn("SAFETY_ZONES=REFUSED", result.stderr)
        self.assertNotIn("HOOK_DONE", result.stdout)

    def test_a_zones_file_of_the_earlier_place_is_copied_once_and_kept(self) -> None:
        self.legacy.write_text('{"zones": ["old"]}', encoding="utf-8")
        result = self.run_hook()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("SAFETY_ZONES=PASS", result.stdout)
        self.assertEqual((self.config_dir / "zones.json").read_text(encoding="utf-8"), '{"zones": ["old"]}')
        self.assertTrue(self.legacy.is_file())

    def test_a_zones_file_that_is_already_in_the_folder_is_never_overwritten(self) -> None:
        self.config_dir.mkdir(parents=True)
        (self.config_dir / "zones.json").write_text('{"zones": ["new"]}', encoding="utf-8")
        self.legacy.write_text('{"zones": ["old"]}', encoding="utf-8")
        result = self.run_hook()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.config_dir / "zones.json").read_text(encoding="utf-8"), '{"zones": ["new"]}')

    def test_an_account_that_cannot_read_the_file_stops_the_installer_and_never_touches_the_service(self) -> None:
        self.config_dir.mkdir(parents=True)
        (self.config_dir / "zones.json").write_text("{}", encoding="utf-8")
        self.set_unit(active=True)
        result = self.run_hook(FAKE_ACCOUNT_CANNOT_READ="1")
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("HOOK_DONE", result.stdout)
        self.assertIn("cannot read the zones file", result.stderr)
        self.assertIn("SAFETY_ZONES=REFUSED", result.stderr)
        self.assertIn("was not touched", result.stderr)
        self.assertEqual([c for c in self.asked_systemctl() if not c.startswith("is-active")], [], "the service must not be stopped, restarted or reloaded")

    def test_a_file_that_exists_but_cannot_be_read_stops_the_installer_even_if_the_service_is_not_running(self) -> None:
        self.config_dir.mkdir(parents=True)
        (self.config_dir / "zones.json").write_text("{}", encoding="utf-8")
        result = self.run_hook(FAKE_ACCOUNT_CANNOT_READ="1")
        self.assertEqual(result.returncode, 2)
        self.assertIn("SAFETY_ZONES=REFUSED", result.stderr)

    @unittest.skipIf(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0), "needs a POSIX account that is not root")
    def test_a_real_file_mode_that_the_account_cannot_read_is_refused(self) -> None:
        self.config_dir.mkdir(parents=True)
        zones = self.config_dir / "zones.json"
        zones.write_text("{}", encoding="utf-8")
        zones.chmod(0)
        self.addCleanup(zones.chmod, 0o600)
        result = self.run_hook()
        self.assertEqual(result.returncode, 2)
        self.assertIn("SAFETY_ZONES=REFUSED", result.stderr)

    def test_a_source_without_the_program_is_refused_by_the_first_guard(self) -> None:
        shutil.rmtree(self.source / "src" / "hydra_umc_safety_zones")
        result = self.run_hook()
        self.assertEqual(result.returncode, 2)
        self.assertIn("source is incomplete", result.stderr)

    @unittest.skipUnless((REAL / "src" / "hydra_umc_safety_zones" / "config_access.py").is_file(), "HYDRA-UMC-SAFETY-ZONES with check-access is not next to this repository")
    def test_the_real_program_agrees_with_the_hook(self) -> None:
        self.legacy.write_text('{"zones": []}', encoding="utf-8")
        ok = self.run_hook(source=REAL)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertIn("SAFETY_ZONES=PASS", ok.stdout)
        (self.config_dir / "zones.json").unlink()
        (self.config_dir / "zones.json").mkdir()  # a folder where the file should be: it cannot be read
        self.set_unit(active=True)
        refused = self.run_hook(source=REAL)
        self.assertEqual(refused.returncode, 2)
        self.assertIn("SAFETY_ZONES=REFUSED", refused.stderr)


class InstallerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = INSTALLER.read_text(encoding="utf-8")

    def test_the_hook_runs_before_the_program_is_copied_and_before_the_unit_is_installed_or_the_service_is_restarted(self) -> None:
        hook = self.text.index('source "$HOOK"')
        for later in ('cp -a "$SOURCE/src"', 'install -m 0644 "$SOURCE/systemd/hydra-umc-safety-zones.service"', "systemctl daemon-reload", "deploy_finish HYDRA-UMC-SAFETY-ZONES"):
            self.assertLess(hook, self.text.index(later), later)

    def test_the_hook_asks_the_service_account_and_ends_with_status_two(self) -> None:
        hook = HOOK.read_text(encoding="utf-8")
        self.assertIn('check-access --zones-file "$SZ_ZONES_FILE"', hook)
        self.assertIn('runuser -u "$SVC_USER"', hook)
        self.assertIn("exit 2", hook[hook.index("SAFETY_ZONES=REFUSED the account") :])
        self.assertIn("chmod 0750", hook)
        for forbidden in ("systemctl stop", "systemctl restart", "chmod 0750 /etc/hydra-umc ", "chmod -R /etc/hydra-umc "):
            self.assertNotIn(forbidden, hook)

    @unittest.skipUnless(BASH, "bash is not installed")
    def test_without_apply_nothing_runs(self) -> None:
        result = subprocess.run([str(BASH), str(INSTALLER)], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Dry-run policy", result.stdout)


if __name__ == "__main__":
    unittest.main()
