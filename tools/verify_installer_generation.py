#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - Installer generation verification
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Prove provisioning/generate_installers.py: every installer it generates reads back as its row of the table and follows the
deployment contract, nothing existing is overwritten, and writing into provisioning/ is refused while the option is off.
The generated scripts are never executed."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROVISIONING = ROOT / "provisioning"
spec = importlib.util.spec_from_file_location("generate_installers", PROVISIONING / "generate_installers.py")
assert spec and spec.loader
gen = importlib.util.module_from_spec(spec)
sys.modules["generate_installers"] = gen
spec.loader.exec_module(gen)


class GenerateInstallersTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = gen._load_plan_module()
        self.config = gen.load_config()

    def test_every_generated_script_reads_back_as_its_row(self) -> None:
        self.assertEqual(gen.check(self.plan, self.config), [])
        made, skipped = gen.build_all(self.plan, self.config)
        self.assertGreaterEqual(len(made), 20)
        self.assertIn("install_twin.sh", made)
        self.assertTrue(all(name not in made for name in skipped))

    def test_the_shape_has_the_guards_and_the_contract(self) -> None:
        text = gen.build_all(self.plan, self.config, "twin")[0]["install_twin.sh"]
        for fragment in ('--apply', "EUID -eq 0", "DEPLOY_CONTRACT=1", "deploy_begin HYDRA-UMC-TWIN", "deploy_finish HYDRA-UMC-TWIN",
                         "hydra-umc.project.json", "announce_health"):
            self.assertIn(fragment, text)
        self.assertLess(text.index("systemctl daemon-reload"), text.index("deploy_finish"))
        self.assertNotIn("enable --now hydra", text.split("echo ")[0])

    def test_the_hand_written_scripts_that_build_on_the_device_are_marked_as_needing_a_hook(self) -> None:
        rows = {r["script"]: r for r in self.plan.build(PROVISIONING, self.plan.registry())["installers"]}
        self.assertTrue(gen.needs_hook(rows["install_twin.sh"]))

    def test_nothing_is_overwritten_and_the_provisioning_folder_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(gen.main(["--out", tmp, "--only", "twin"]), 0)
            self.assertTrue((Path(tmp) / "install_twin.sh").is_file())
            self.assertEqual(gen.main(["--out", tmp, "--only", "twin"]), 2)
        self.assertFalse(self.config["allow_replace_existing"])
        self.assertEqual(gen.main(["--out", str(PROVISIONING)]), 2)

    def test_show_and_check_commands(self) -> None:
        self.assertEqual(gen.main(["--show", "twin"]), 0)
        self.assertEqual(gen.main(["--show", "nothing"]), 2)


if __name__ == "__main__":
    unittest.main()
