#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - tools/verify_platform_profile.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Prove tools/platform_profile.py and the declarations of config/platforms: every file is valid, the platform of a machine is chosen by a variable, then a file, then cm5, an unknown name
is an error, the plan names the commands without running anything, and the rules refuse a bad declaration. Evidence: simulator."""
from __future__ import annotations

import copy
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import platform_profile as pp  # noqa: E402


class PlatformProfileTests(unittest.TestCase):
    def test_every_declaration_of_the_folder_is_valid_and_the_three_platforms_exist(self) -> None:
        profiles = pp.load_all()
        self.assertEqual(sorted(profiles), ["cm5", "jetson", "rk3588"])
        for name, data in profiles.items():
            self.assertEqual(pp.check_profile(data, name), [], name)

    def test_cm5_adds_nothing_so_the_images_of_today_do_not_change(self) -> None:
        cm5 = pp.select("cm5")
        self.assertEqual((cm5["packages"], cm5["remove_packages"], cm5["units"]), ([], [], []))
        self.assertEqual(pp.plan(cm5)["commands"], [])
        self.assertIn("pigen", cm5["build_backends"])

    def test_jetson_and_the_generic_rk3588_choose_packages_units_and_a_base_image(self) -> None:
        jetson = pp.plan(pp.select("jetson"))
        self.assertEqual(jetson["commands"], [["apt-get", "install", "-y", "--no-install-recommends", "nvidia-jetpack"], ["systemctl", "enable", "nvpmodel.service"]])
        self.assertEqual(jetson["base_image"]["kind"], "nvidia-l4t-rootfs")
        rk = pp.plan(pp.select("rk3588"))
        self.assertTrue(rk["generic"] and rk["evidence"] == "simulator")
        self.assertEqual(rk["base_image"]["kind"], "generic-arm64-debian")
        self.assertNotIn("pigen", rk["build_backends"])
        self.assertFalse(jetson["runs_anything"] or rk["runs_anything"])

    def test_the_generic_profile_names_no_board(self) -> None:
        text = (ROOT / "config" / "platforms" / "rk3588.json").read_text(encoding="utf-8").lower()
        for model in ("orange", "rock", "radxa", "firefly", "khadas", "friendlyelec", "nanopi", "turing", "rk3588s", "cool pi"):
            self.assertNotIn(model, text)

    def test_the_platform_of_a_machine_is_the_variable_then_the_file_then_cm5(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            machine = Path(tmp) / "platform"
            self.assertEqual(pp.configured_name({}, machine), "cm5")  # no file
            machine.write_text("jetson extra words\n", encoding="utf-8")
            self.assertEqual(pp.configured_name({}, machine), "jetson")
            self.assertEqual(pp.configured_name({"HYDRA_UMC_PLATFORM": "rk3588"}, machine), "rk3588")
            self.assertEqual(pp.configured_name({"HYDRA_UMC_PLATFORM": "  "}, machine), "jetson")
            machine.write_text("\n", encoding="utf-8")
            self.assertEqual(pp.configured_name({}, machine), "cm5")

    def test_an_unknown_platform_is_an_error_and_never_falls_back(self) -> None:
        with self.assertRaises(pp.PlatformError):
            pp.select("orin")
        with self.assertRaises(pp.PlatformError):
            pp.select(None, environment={"HYDRA_UMC_PLATFORM": "typo"}, machine_file=Path("/nonexistent/platform"))

    def test_bad_declarations_are_refused(self) -> None:
        good = pp.select("jetson")

        def broken(**change: object) -> list[str]:
            data = copy.deepcopy(good)
            data.update(change)
            return pp.check_profile(data, "jetson")

        self.assertEqual(pp.check_profile([], None), ["the file is not a JSON object"])
        self.assertTrue(pp.check_profile({"format": pp.FORMAT}, None)[0].startswith("missing"))
        self.assertTrue(any("unknown key" in p for p in broken(extra=1)))
        self.assertTrue(broken(format="other/1"))
        self.assertTrue(broken(platform="Jetson"))
        self.assertTrue(any("names the platform" in p for p in broken(platform="orin")))
        self.assertTrue(broken(arch="x86_64"))
        self.assertTrue(broken(label=""))
        self.assertTrue(broken(evidence="lab"))
        self.assertTrue(broken(generic="yes"))
        self.assertTrue(broken(base_image={"kind": "x"}))
        self.assertTrue(broken(packages=["a b"]))
        self.assertTrue(broken(packages=["curl", "curl"]))
        self.assertTrue(any("both installed and removed" in p for p in broken(packages=["curl"], remove_packages=["curl"])))
        self.assertTrue(broken(units=[{"name": "nvpmodel", "enable": True}]))
        self.assertTrue(broken(units=[{"name": "a.service", "enable": "yes"}]))
        self.assertTrue(any("listed twice" in p for p in broken(units=[{"name": "a.service", "enable": True}, {"name": "a.service", "enable": False}])))
        self.assertTrue(broken(build_backends=[]))
        self.assertTrue(broken(build_backends=["docker"]))
        self.assertTrue(any("pigen is allowed for cm5 alone" in p for p in broken(build_backends=["pigen"])))

    def test_a_folder_with_a_damaged_or_missing_file_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with self.assertRaisesRegex(pp.PlatformError, "cm5 is missing"):
                pp.load_all(folder)
            for name in ("cm5", "jetson"):
                (folder / f"{name}.json").write_text((ROOT / "config" / "platforms" / f"{name}.json").read_text(encoding="utf-8"), encoding="utf-8")
            self.assertEqual(sorted(pp.load_all(folder)), ["cm5", "jetson"])
            (folder / "jetson.json").write_text("{not json", encoding="utf-8")
            with self.assertRaisesRegex(pp.PlatformError, "cannot be read"):
                pp.load_all(folder)
            (folder / "jetson.json").write_text(json.dumps({"format": pp.FORMAT}), encoding="utf-8")
            with self.assertRaisesRegex(pp.PlatformError, "missing key"):
                pp.load_all(folder)

    def run_cli(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = pp.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_the_command_lists_shows_and_checks(self) -> None:
        code, out, _ = self.run_cli()
        self.assertEqual(code, 0)
        self.assertIn("cm5 (this machine)", out)
        code, out, _ = self.run_cli("--json")
        self.assertEqual(json.loads(out)["platforms"], ["cm5", "jetson", "rk3588"])
        code, out, _ = self.run_cli("--show", "rk3588", "--json")
        self.assertEqual((code, json.loads(out)["platform"]), (0, "rk3588"))
        code, out, _ = self.run_cli("--show", "this")
        self.assertEqual(code, 0)
        self.assertIn("cm5:", out)
        code, _, err = self.run_cli("--show", "orin")
        self.assertEqual(code, 1)
        self.assertIn("PLATFORM_FAILED", err)
        code, out, _ = self.run_cli("--check")
        self.assertEqual((code, out.strip()), (0, "PLATFORM_PROFILES=PASS platforms=3"))

    def test_the_command_fails_when_the_folder_is_damaged(self) -> None:
        original = pp.PLATFORMS_DIR
        with tempfile.TemporaryDirectory() as tmp:
            pp.PLATFORMS_DIR = Path(tmp)
            self.addCleanup(setattr, pp, "PLATFORMS_DIR", original)
            original_load = pp.load_all
            pp.load_all = lambda directory=Path(tmp): original_load(directory)  # type: ignore[assignment]
            self.addCleanup(setattr, pp, "load_all", original_load)
            code, _, err = self.run_cli("--check")
        self.assertEqual(code, 1)
        self.assertIn("PLATFORM_PROFILES=FAIL", err)


if __name__ == "__main__":
    unittest.main(verbosity=1)
