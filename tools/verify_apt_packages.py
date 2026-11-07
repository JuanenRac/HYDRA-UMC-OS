#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - tools/verify_apt_packages.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The reading of the packages the installers ask for (tools/apt_packages_check.py): continuation lines, options, comments, stops at a pipe or an
`&&`, names written with a variable, and a check that every real installer is read."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import apt_packages_check as apt  # noqa: E402


class ReadingTests(unittest.TestCase):
    def test_a_plain_line(self) -> None:
        self.assertEqual(apt.packages_in("apt-get install -y curl git\n"), (["curl", "git"], []))

    def test_run_prefix_options_and_continuations(self) -> None:
        text = chr(10).join(["run apt-get install -y --no-install-recommends " + chr(92), "  cage " + chr(92), "  chromium"]) + chr(10)
        self.assertEqual(apt.packages_in(text), (["cage", "chromium"], []))

    def test_it_stops_at_a_pipe_a_redirect_and_a_command_separator(self) -> None:
        for tail in (" | tee log", " && echo done", " ; echo done", " > /dev/null", " 2>&1", " || true"):
            self.assertEqual(apt.packages_in("apt-get install -y curl" + tail + "\n"), (["curl"], []), tail)

    def test_comments_are_not_read(self) -> None:
        self.assertEqual(apt.packages_in("# apt-get install -y nothing\necho hi # apt-get install -y here\n"), ([], []))

    def test_a_name_with_a_variable_is_not_a_package_name(self) -> None:
        names, odd = apt.packages_in('apt-get install -y curl "$EXTRA" ${MORE}\n')
        self.assertEqual(names, ["curl"])
        self.assertEqual(odd, ["$EXTRA", "${MORE}"][:len(odd)] if odd else odd)
        self.assertTrue(odd)

    def test_repeats_are_dropped_and_the_order_kept(self) -> None:
        self.assertEqual(apt.packages_in("apt-get install -y b a\napt install a c\n")[0], ["b", "a", "c"])

    def test_package_names_with_dots_pluses_and_dashes(self) -> None:
        self.assertEqual(apt.packages_in("apt-get install -y docker.io libstdc++6 python3-venv\n")[0], ["docker.io", "libstdc++6", "python3-venv"])

    def test_a_script_with_no_install_has_no_packages(self) -> None:
        self.assertEqual(apt.packages_in("echo apt-get is mentioned\nset -e\n"), ([], []))


class RealInstallersTests(unittest.TestCase):
    def test_every_installer_that_installs_packages_is_read(self) -> None:
        by_script = apt.packages_by_script()
        for script in ("install_kiosk.sh", "install_splashscreen.sh", "install_industrial_gateway.sh", "install_vision_streamer.sh", "first_boot.sh"):
            self.assertIn(script, by_script, script)
            self.assertTrue(by_script[script]["packages"], script)

    def test_the_kiosk_asks_for_cage_and_for_the_x_pieces(self) -> None:
        names = apt.packages_by_script()["install_kiosk.sh"]["packages"]
        for name in ("cage", "chromium", "xserver-xorg", "openbox", "picom"):
            self.assertIn(name, names)

    def test_every_name_looks_like_a_debian_package(self) -> None:
        for script, entry in apt.packages_by_script().items():
            for name in entry["packages"]:
                self.assertRegex(name, apt.PACKAGE.pattern, script)
            self.assertEqual(entry["not_plain"], [], f"{script} asks for a package with a variable in its name")


if __name__ == "__main__":
    unittest.main()
