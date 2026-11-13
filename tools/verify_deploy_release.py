#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - Release deployment check
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Prove tools/deploy_release.py in temporary folders, with no systemd and no network: a signed package installs as a release, a newer one replaces it and keeps the old one, a package that
is tampered, unsigned, older or equal is refused and changes nothing, a restart or a health check that fails puts the old release back, a rollback goes to the previous one and pruning
never removes the release in use."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


dr = load("deploy_release")
pc = dr.package_component
SEED = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
PUBLIC = "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
PY = f'"{sys.executable}"' if os.name == "nt" else sys.executable


class DeployTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "opt"
        self.root.mkdir()
        self.trust = self.base / "release_key.pub"
        self.trust.write_text(PUBLIC + "\n", encoding="ascii")
        self.repo = self.base / "HYDRA-UMC-SERVER"
        self.settings = dict(dr.DEFAULTS)

    def package(self, version: str, *, sign: bool = True, content: str = "code") -> Path:
        for relative, text in {"dist/server.cjs": f"{content} {version}", "public/index.html": "<html>", "package.json": "{}", "package-lock.json": "{}",
                               "systemd/hydra-umc-server.service": "[Unit]"}.items():
            target = self.repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        (self.repo / "hydra-umc.project.json").write_text(json.dumps({"version": version}), encoding="utf-8")
        package, _version, _digest = pc.build("server", self.repo, self.base / "out")
        if sign:
            pc.sign_package(package, SEED, self.trust)
        return package

    def install(self, package: Path, **kwargs):
        return dr.install(package, self.root, trusted_key=PUBLIC, settings=self.settings, sleep=lambda _s: None, **kwargs)

    def current(self) -> str | None:
        entry = dr.Component(self.root, "server").state()["current"]
        return entry["version"] if entry else None

    # ---- the way in -----------------------------------------------------------------------------------------------------------------

    def test_a_signed_package_becomes_the_current_release(self) -> None:
        state = self.install(self.package("0.8.1.0"))
        self.assertEqual(state["current"]["version"], "0.8.1.0")
        self.assertIsNone(state["previous"])
        release = self.root / "server" / "releases" / state["current"]["release"]
        self.assertEqual((release / "dist" / "server.cjs").read_text(encoding="utf-8"), "code 0.8.1.0")
        self.assertEqual(len(state["current"]["sha256"]), 64)
        self.assertEqual([p.name for p in (self.root / "server" / "releases").iterdir()], [state["current"]["release"]])

    def test_a_newer_package_replaces_it_and_the_old_one_stays_as_previous(self) -> None:
        self.install(self.package("0.8.1.0"))
        state = self.install(self.package("0.8.1.1"))
        self.assertEqual((state["current"]["version"], state["previous"]["version"]), ("0.8.1.1", "0.8.1.0"))
        self.assertEqual(len(list((self.root / "server" / "releases").iterdir())), 2)
        self.assertEqual([item["event"] for item in state["history"]], ["install", "install"])

    def test_the_link_points_at_the_current_release_where_the_host_can_make_links(self) -> None:
        state = self.install(self.package("0.8.1.0"))
        link = self.root / "server" / "current"
        if link.is_symlink():
            self.assertEqual(Path(os.readlink(link)).name, state["current"]["release"])

    # ---- what is refused and changes nothing ----------------------------------------------------------------------------------------------

    def test_an_unsigned_or_changed_package_is_refused_and_nothing_is_written(self) -> None:
        with self.assertRaisesRegex(dr.DeployError, r"\.sig is missing"):
            self.install(self.package("0.8.1.0", sign=False))
        package = self.package("0.8.1.1")
        data = bytearray(package.read_bytes())
        data[len(data) // 2] ^= 1
        package.write_bytes(bytes(data))
        with self.assertRaisesRegex(dr.DeployError, "hash does not match"):
            self.install(package)
        self.assertFalse((self.root / "server").exists())

    def test_a_signature_by_another_key_is_refused(self) -> None:
        package = self.package("0.8.1.0")
        with self.assertRaisesRegex(dr.DeployError, "signature is not valid"):
            dr.install(package, self.root, trusted_key="3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c", settings=self.settings)
        self.assertFalse((self.root / "server").exists())

    def test_the_same_or_an_older_version_is_refused_unless_asked(self) -> None:
        self.install(self.package("0.8.1.2"))
        for version in ("0.8.1.2", "0.8.1.1", "0.8.0.9"):
            with self.assertRaisesRegex(dr.DeployError, "is not newer"):
                self.install(self.package(version))
        self.assertEqual(self.current(), "0.8.1.2")
        state = self.install(self.package("0.8.1.1"), allow_downgrade=True)
        self.assertEqual(state["current"]["version"], "0.8.1.1")

    def test_versions_compare_as_numbers_not_as_text(self) -> None:
        self.install(self.package("0.8.1.9"))
        self.assertEqual(self.install(self.package("0.8.1.10"))["current"]["version"], "0.8.1.10")

    # ---- restart, health and the way back -------------------------------------------------------------------------------------------------

    def test_a_restart_that_fails_puts_the_old_release_back(self) -> None:
        self.install(self.package("0.8.1.0"))
        self.settings["restartCommand"] = f'{PY} -c "import sys; sys.exit(1)"'
        with self.assertRaises(dr.DeployError) as caught:
            self.install(self.package("0.8.1.1"))
        self.assertEqual(caught.exception.code, dr.EXIT_ROLLED_BACK)
        self.assertEqual(self.current(), "0.8.1.0")
        events = [item["event"] for item in dr.Component(self.root, "server").state()["history"]]
        self.assertEqual(events[-1], "install-failed")

    def test_a_health_check_that_never_passes_puts_the_old_release_back_and_restarts_it(self) -> None:
        log = self.base / "restarts.log"
        self.settings["restartCommand"] = f'{PY} -c "open(r\'{log}\', \'a\').write(\'{{version}}\\n\')"'
        self.install(self.package("0.8.1.0"))
        self.settings["healthCommand"] = f'{PY} -c "import sys; sys.exit(1)"'
        self.settings["healthTimeoutS"] = 1
        self.settings["healthIntervalS"] = 0.1
        with self.assertRaises(dr.DeployError) as caught:
            dr.install(self.package("0.8.1.1"), self.root, trusted_key=PUBLIC, settings=self.settings)
        self.assertEqual(caught.exception.code, dr.EXIT_ROLLED_BACK)
        self.assertEqual(self.current(), "0.8.1.0")
        self.assertEqual(log.read_text(encoding="utf-8").split(), ["0.8.1.0", "0.8.1.1", "0.8.1.0"])

    def test_a_first_release_that_fails_leaves_no_current_release(self) -> None:
        self.settings["restartCommand"] = f'{PY} -c "import sys; sys.exit(1)"'
        with self.assertRaises(dr.DeployError):
            self.install(self.package("0.8.1.0"))
        self.assertIsNone(self.current())
        self.assertFalse((self.root / "server" / "current").is_symlink())

    def test_a_health_check_that_passes_on_the_third_try_is_accepted(self) -> None:
        counter = self.base / "tries"
        script = self.base / "health.py"
        script.write_text("import sys, pathlib\np = pathlib.Path(sys.argv[1])\nn = int(p.read_text()) + 1 if p.exists() else 1\np.write_text(str(n))\nsys.exit(0 if n >= 3 else 1)\n", encoding="utf-8")
        self.settings["healthCommand"] = f'{PY} "{script}" "{counter}"'
        self.settings["healthTimeoutS"] = 60
        state = self.install(self.package("0.8.1.0"))
        self.assertEqual(state["current"]["version"], "0.8.1.0")
        self.assertEqual(counter.read_text(), "3")

    def test_the_commands_know_the_component_the_version_and_the_release(self) -> None:
        out = self.base / "seen.txt"
        self.settings["restartCommand"] = f'{PY} -c "open(r\'{out}\', \'w\').write(\'{{component}}|{{version}}|\' + str(__import__(\'os\').path.isdir(r\'{{release}}\')))"'
        self.install(self.package("0.8.1.0"))
        self.assertEqual(out.read_text(encoding="utf-8"), "server|0.8.1.0|True")

    # ---- rollback and pruning ----------------------------------------------------------------------------------------------------------

    def test_rollback_goes_to_the_previous_release_and_a_second_one_comes_back(self) -> None:
        self.install(self.package("0.8.1.0"))
        self.install(self.package("0.8.1.1"))
        back = dr.rollback(self.root, "server", settings=self.settings, sleep=lambda _s: None)
        self.assertEqual((back["current"]["version"], back["previous"]["version"]), ("0.8.1.0", "0.8.1.1"))
        again = dr.rollback(self.root, "server", settings=self.settings, sleep=lambda _s: None)
        self.assertEqual(again["current"]["version"], "0.8.1.1")

    def test_rollback_with_nothing_before_is_refused(self) -> None:
        self.install(self.package("0.8.1.0"))
        with self.assertRaisesRegex(dr.DeployError, "no earlier release"):
            dr.rollback(self.root, "server", settings=self.settings)
        with self.assertRaisesRegex(dr.DeployError, "no earlier release"):
            dr.rollback(self.root, "studio", settings=self.settings)

    def test_pruning_keeps_the_newest_and_never_the_release_in_use(self) -> None:
        self.settings["keep"] = 2
        for version in ("0.8.1.0", "0.8.1.1", "0.8.1.2", "0.8.1.3"):
            self.install(self.package(version))
        releases = sorted(p.name for p in (self.root / "server" / "releases").iterdir())
        self.assertEqual(releases, ["0.8.1.2-1", "0.8.1.3-1"])
        state = dr.Component(self.root, "server").state()
        self.assertEqual((state["current"]["release"], state["previous"]["release"]), ("0.8.1.3-1", "0.8.1.2-1"))
        self.assertEqual(dr.prune(self.root, "server", 2), [])

    def test_a_component_name_cannot_leave_the_root(self) -> None:
        for name in ("..", "../x", "a/b", "A", ""):
            with self.assertRaises(dr.DeployError):
                dr.Component(self.root, name)

    def test_a_state_file_that_points_outside_the_releases_is_not_followed(self) -> None:
        self.install(self.package("0.8.1.0"))
        component = dr.Component(self.root, "server")
        component.write_state({"current": {"release": "../../etc", "version": "9.9.9"}, "previous": {"release": "../x", "version": "9.9.8"}, "history": []})
        with self.assertRaisesRegex(dr.DeployError, "no earlier release"):
            dr.rollback(self.root, "server", settings=self.settings)

    # ---- the settings and the command line -------------------------------------------------------------------------------------------------

    def test_settings_come_from_deploy_json_and_a_bad_value_falls_back_with_a_warning(self) -> None:
        (self.root / "deploy.json").write_text(json.dumps({"keep": 5, "healthTimeoutS": 9999, "restartCommand": 7, "healthCommand": " ok ", "allowDowngrade": "yes", "healthIntervalS": 2}), encoding="utf-8")
        warnings: list[str] = []
        settings = dr.load_settings(self.root, warnings.append)
        self.assertEqual((settings["keep"], settings["healthTimeoutS"], settings["healthIntervalS"], settings["healthCommand"], settings["restartCommand"], settings["allowDowngrade"]),
                         (5, 30, 2.0, "ok", "", False))
        self.assertEqual(len(warnings), 3)
        (self.root / "deploy.json").write_text("{not json", encoding="utf-8")
        self.assertEqual(dr.load_settings(self.root, warnings.append), dr.DEFAULTS)
        (self.root / "deploy.json").write_text("[]", encoding="utf-8")
        self.assertEqual(dr.load_settings(self.root, warnings.append), dr.DEFAULTS)

    def test_the_command_line_installs_reports_and_returns_the_exit_codes(self) -> None:
        package = self.package("0.8.1.0")
        self.assertEqual(dr.main(["--root", str(self.root), "install", str(package), "--trusted-key", PUBLIC]), 0)
        self.assertEqual(dr.main(["--root", str(self.root), "status"]), 0)
        self.assertEqual(dr.main(["--root", str(self.root), "install", str(package), "--trusted-key", PUBLIC]), dr.EXIT_REFUSED)
        self.assertEqual(dr.main(["--root", str(self.root), "rollback", "server"]), dr.EXIT_REFUSED)
        self.assertEqual(dr.main(["--root", str(self.root), "prune", "server", "--keep", "2"]), 0)
        self.assertEqual(dr.status(self.root)["server"]["current"]["version"], "0.8.1.0")


    # ---- what the server reads when Studio starts an update (HYDRA-UMC-SERVER, src/selfUpdate.ts) -------------------------------------------

    def run_cli(self, module, argv: list[str]) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = module.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_the_end_of_an_install_is_one_marker_line_the_server_can_read(self) -> None:
        package = self.package("0.8.1.0")
        code, out, _err = self.run_cli(dr, ["--root", str(self.root), "install", str(package), "--trusted-key", PUBLIC])
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines()[-1], "DEPLOY=PASS")
        # a newer one whose restart fails: the old release is back, the status is 3 and the failure line says it did not hold
        (self.root / "deploy.json").write_text(json.dumps({"restartCommand": f'{PY} -c "import sys; sys.exit(1)"'}), encoding="utf-8")
        code, out, err = self.run_cli(dr, ["--root", str(self.root), "install", str(self.package("0.8.2.0")), "--trusted-key", PUBLIC])
        self.assertEqual(code, dr.EXIT_ROLLED_BACK)
        self.assertNotIn("DEPLOY=PASS", out)
        failure = [line for line in err.splitlines() if line.startswith("DEPLOY=FAIL")]
        self.assertEqual(len(failure), 1)
        self.assertRegex(failure[0], r"did not|rolled|put back|earlier release")
        self.assertEqual(self.current(), "0.8.1.0")
        # a refusal (the same version) is a failure line too, and it is not one of the "went back" kind
        code, _out, err = self.run_cli(dr, ["--root", str(self.root), "install", str(package), "--trusted-key", PUBLIC])
        self.assertEqual(code, dr.EXIT_REFUSED)
        self.assertRegex(err, r"(?m)^DEPLOY=FAIL refused")

    def test_the_check_of_a_package_says_component_version_and_hash_on_one_line(self) -> None:
        package = self.package("0.8.1.0")
        code, out, _err = self.verify_cli(package)
        self.assertEqual(code, 0)
        self.assertRegex(out, r"(?m)^PACKAGE=OK server 0\.8\.1\.0 [0-9a-f]{64}$")
        unsigned = self.package("0.8.2.0", sign=False)
        code, out, err = self.verify_cli(unsigned)
        self.assertEqual(code, 1)
        self.assertNotIn("PACKAGE=OK", out)
        self.assertRegex(err, r"(?m)^PACKAGE=REFUSED ")

    def verify_cli(self, package: Path) -> tuple[int, str, str]:
        # `verify` checks against the key the repository trusts; the case runs it against the key of the RFC test vector, as the rest of this file does
        original = pc.TRUST_FILE
        pc.TRUST_FILE = self.trust
        try:
            return self.run_cli(pc, ["verify", str(package)])
        finally:
            pc.TRUST_FILE = original


if __name__ == "__main__":
    unittest.main()
