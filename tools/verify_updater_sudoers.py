#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - Updater sudoers rule check
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Proves tools/make_updater_sudoers.py: only projects of the plan, exact words, no wildcard, and the committed file is the generated one."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("make_updater_sudoers", ROOT / "tools" / "make_updater_sudoers.py")
assert spec and spec.loader
maker = importlib.util.module_from_spec(spec)
sys.modules["make_updater_sudoers"] = maker
spec.loader.exec_module(maker)

PLAN = {
    "supported_contract": 1,
    "installers": [
        {"source": "HYDRA-UMC-TWIN", "contract": 1, "deploy_exempt": None},
        {"source": "HYDRA-UMC-SERVER", "contract": 1, "deploy_exempt": None},
        {"source": "HYDRA-UMC-SERVER", "contract": 1, "deploy_exempt": None},
        {"source": "HYDRA-UMC-DSI", "contract": 1, "deploy_exempt": "kiosk"},
        {"source": "HYDRA-UMC-OLD", "contract": 0, "deploy_exempt": None},
        {"source": "HYDRA-UMC-NEWER", "contract": 2, "deploy_exempt": None},
        {"source": None, "contract": 1, "deploy_exempt": None},
        {"source": "hydra-umc-lower", "contract": 1, "deploy_exempt": None},
        {"source": "HYDRA-UMC-X; rm -rf /", "contract": 1, "deploy_exempt": None},
        {"source": "HYDRA-UMC-TWO WORDS", "contract": 1, "deploy_exempt": None},
    ],
}


class UpdaterSudoersTests(unittest.TestCase):
    def test_only_projects_that_follow_the_supported_contract_are_listed_once_and_sorted(self) -> None:
        self.assertEqual(maker.deployable_projects(PLAN), ["HYDRA-UMC-SERVER", "HYDRA-UMC-TWIN"])

    def test_a_name_that_is_not_a_plain_repository_name_never_reaches_the_file(self) -> None:
        text = maker.render(PLAN)
        for bad in ("rm -rf", ";", "TWO WORDS", "lower", "OLD", "NEWER", "DSI"):
            self.assertNotIn(bad, text)

    def test_every_rule_line_is_the_exact_command_without_a_wildcard(self) -> None:
        lines = [line for line in maker.render(PLAN).splitlines() if line and not line.startswith("#") and not line.startswith("Defaults")]
        self.assertEqual(
            lines,
            [
                "hydra-umc-updater ALL=(root) NOPASSWD: /usr/local/bin/hydra-umc-os deploy HYDRA-UMC-SERVER --apply",
                "hydra-umc-updater ALL=(root) NOPASSWD: /usr/local/bin/hydra-umc-os deploy HYDRA-UMC-TWIN --apply",
            ],
        )
        for line in lines:
            self.assertNotRegex(line, r"[*?\[\]\\!]|\bALL\s*$|NOPASSWD:\s*ALL")

    def test_the_rule_is_for_one_account_and_runs_as_root_only(self) -> None:
        text = maker.render(PLAN, "someone")
        self.assertIn("Defaults:someone !requiretty", text)
        for line in text.splitlines():
            if line.startswith("someone "):
                self.assertTrue(line.startswith("someone ALL=(root) NOPASSWD: /usr/local/bin/hydra-umc-os deploy "))

    def test_no_plan_with_a_deployable_project_gives_a_file_without_command_lines(self) -> None:
        text = maker.render({"supported_contract": 1, "installers": []})
        self.assertFalse([line for line in text.splitlines() if "NOPASSWD" in line])

    def test_the_committed_file_is_the_one_the_install_plan_produces(self) -> None:
        plan = json.loads((ROOT / "provisioning" / "install_plan.json").read_text(encoding="utf-8"))
        committed = (ROOT / "provisioning" / "sudoers.d" / "hydra-umc-updater").read_bytes().decode("utf-8").replace("\r\n", "\n")
        self.assertEqual(committed, maker.render(plan))
        self.assertGreater(len(maker.deployable_projects(plan)), 5)
        for project in maker.deployable_projects(plan):
            self.assertRegex(project, re.compile(r"HYDRA-UMC-[A-Z0-9-]+"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
