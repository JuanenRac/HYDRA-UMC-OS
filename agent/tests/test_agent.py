# =============================================================================
# HYDRA-UMC-OS - Device agent unit tests
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================

import json
import tempfile
import unittest
from pathlib import Path

from hydra_umc_os.agent import DEFAULT_CONFIG, describe, health, load_config, load_profile, read_temperature_celsius


class AgentTests(unittest.TestCase):
    def test_default_descriptor_uses_declared_node(self):
        descriptor = describe(DEFAULT_CONFIG, interfaces=["eth0"])
        self.assertEqual(descriptor.node_id, "hydra-umc-node")
        self.assertEqual(descriptor.interfaces, ["eth0"])

    def test_ready_when_storage_and_network_are_available(self):
        report = health(DEFAULT_CONFIG, free_bytes=2_000_000_000, interfaces=["eth0"])
        self.assertEqual(report.state, "READY")

    def test_degraded_without_a_network_interface(self):
        report = health(DEFAULT_CONFIG, free_bytes=2_000_000_000, interfaces=[])
        self.assertEqual(report.state, "DEGRADED")

    def test_fault_when_storage_is_below_profile_minimum(self):
        report = health(DEFAULT_CONFIG, free_bytes=0, interfaces=["eth0"])
        self.assertEqual(report.state, "FAULT")

    def test_rejects_incomplete_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "node.json"
            config.write_text(json.dumps({"schema_version": "1.0", "node": {}}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_config(config)

    def test_loads_opt_in_control_profile_without_starting_services(self):
        profile = load_profile(Path(__file__).resolve().parents[2] / "config" / "profiles" / "control.json")
        self.assertEqual(profile["profile"], "control")
        self.assertIn("cm5_mcu_adapter", profile["requires"])

    def test_reads_linux_temperature_millidegrees(self):
        with tempfile.TemporaryDirectory() as directory:
            sensor = Path(directory) / "temp"; sensor.write_text("42500", encoding="utf-8")
            self.assertEqual(read_temperature_celsius(sensor), 42.5)


if __name__ == "__main__":
    unittest.main()
