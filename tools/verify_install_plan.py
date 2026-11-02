#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - Install plan check
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Prove provisioning/install_plan.py: it reads the shape of an installer, reports a copy that drifts from the registry, and the committed table is the one the scripts produce."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("install_plan", ROOT / "provisioning" / "install_plan.py")
assert spec and spec.loader
plan = importlib.util.module_from_spec(spec)
sys.modules["install_plan"] = plan
spec.loader.exec_module(plan)

GOOD = """#!/usr/bin/env bash
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SOURCE="$ROOT/HYDRA-UMC-TWIN"
TARGET=/opt/hydra-umc/twin
TWIN_USER="hydra-umc-twin"
install -m 0644 "$SOURCE/systemd/hydra-umc-twin.service" /etc/systemd/system/hydra-umc-twin.service
install -m 0644 "$SOURCE/hydra-umc.project.json" "$TARGET/hydra-umc.project.json"
"""
PORTS = {"HYDRA-UMC-TWIN": {"port": "8101", "health_path": "/health", "systemd_unit": "hydra-umc-twin.service"}}


class InstallPlanTests(unittest.TestCase):
    def folder(self, scripts: dict[str, str]) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        for name, text in scripts.items():
            (Path(tmp.name) / name).write_text(text, encoding="utf-8")
        return Path(tmp.name)

    def test_the_shape_of_an_installer_is_read(self) -> None:
        table = plan.build(self.folder({"install_twin.sh": GOOD}), PORTS)
        row = table["installers"][0]
        self.assertEqual((row["source"], row["target"], row["user"], row["units"], row["clones"], row["installs_manifest"]),
                         ("HYDRA-UMC-TWIN", "/opt/hydra-umc/twin", "hydra-umc-twin", ["hydra-umc-twin.service"], False, True))
        self.assertEqual((row["port"], row["health_path"], row["unit"]), (8101, "/health", "hydra-umc-twin.service"))
        self.assertEqual(plan.problems(table, PORTS), [])

    def test_a_script_that_clones_on_the_device_is_marked(self) -> None:
        row = plan.build(self.folder({"install_twin.sh": GOOD + "git clone https://example.invalid/x\n"}), PORTS)["installers"][0]
        self.assertTrue(row["clones"])

    def test_a_drifting_copy_is_reported(self) -> None:
        bad = GOOD.replace("hydra-umc-twin.service", "hydra-umc-twins.service", 2).replace("/opt/hydra-umc/twin", "/opt/hydra-umc/other")
        bad = bad.replace('install -m 0644 "$SOURCE/hydra-umc.project.json" "$TARGET/hydra-umc.project.json"\n', "")
        found = "\n".join(plan.problems(plan.build(self.folder({"install_twin.sh": bad}), PORTS), PORTS))
        self.assertIn("installs no unit file hydra-umc-twin.service", found)
        self.assertIn("not named after the unit", found)
        self.assertIn("does not install hydra-umc.project.json", found)

    def test_a_script_without_a_service_in_the_registry_is_left_alone(self) -> None:
        table = plan.build(self.folder({"install_kiosk.sh": "#!/usr/bin/env bash\necho kiosk\n"}), {})
        self.assertEqual(plan.problems(table, {}), [])
        self.assertIsNone(table["installers"][0]["source"])

    def test_the_registry_treats_null_as_nothing(self) -> None:
        folder = self.folder({"ports.yaml": "services:\n  - name: HYDRA-UMC-A\n    port: 1\n    health_path: null\n    systemd_unit: null\n"})
        self.assertEqual(plan.registry(folder / "ports.yaml")["HYDRA-UMC-A"], {"port": "1", "health_path": "", "systemd_unit": ""})

    def test_the_committed_table_is_what_the_scripts_produce(self) -> None:
        self.assertEqual(plan.main(["--check"]), 0)
        self.assertEqual(plan.main(["--show", "twin"]), 0)
        self.assertEqual(plan.main(["--show", "nothing"]), 2)


if __name__ == "__main__":
    unittest.main()
