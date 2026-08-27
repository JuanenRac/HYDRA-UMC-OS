# =============================================================================
# HYDRA-UMC-OS - Device agent unit tests
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================

import json
import tempfile
import unittest
from pathlib import Path

from hydra_umc_os.agent import DEFAULT_CONFIG, describe, health, load_config, load_profile, main, read_temperature_celsius


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

    def test_fault_when_temperature_reaches_configured_limit(self):
        report = health(
            DEFAULT_CONFIG,
            free_bytes=2_000_000_000,
            interfaces=["eth0"],
            temperature_celsius=80.0,
        )
        self.assertEqual(report.state, "FAULT")
        self.assertEqual(report.checks["temperature"]["state"], "FAIL")

    def test_rejects_incomplete_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "node.json"
            config.write_text(json.dumps({"schema_version": "1.0", "node": {}}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_config(config)

    def test_rejects_unsafe_diagnostics_thresholds(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "node.json"
            config.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "node": {"id": "cm5-01", "profile": "base"},
                        "diagnostics": {
                            "minimum_free_bytes": -1,
                            "maximum_temperature_celsius": 80,
                        },
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                load_config(config)

            config.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "node": {"id": "cm5-01", "profile": "base"},
                        "diagnostics": {
                            "minimum_free_bytes": 0,
                            "maximum_temperature_celsius": 0,
                        },
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                load_config(config)

    def test_existing_v1_configuration_receives_safe_temperature_default(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "node.json"
            config.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "node": {"id": "cm5-01", "profile": "base"},
                        "diagnostics": {"minimum_free_bytes": 0},
                    }
                ),
                encoding="utf-8",
            )
            loaded = load_config(config)
            self.assertEqual(loaded["diagnostics"]["maximum_temperature_celsius"], 80.0)

    def test_loads_opt_in_control_profile_without_starting_services(self):
        profile = load_profile(Path(__file__).resolve().parents[2] / "config" / "profiles" / "control.json")
        self.assertEqual(profile["profile"], "control")
        self.assertIn("cm5_mcu_adapter", profile["requires"])

    def test_rejects_invalid_or_duplicate_profile_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            profile_path = Path(directory) / "profile.json"
            profile_path.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "profile": "base",
                        "enabled_services": ["hydra-umc-agent", "hydra-umc-agent"],
                        "requires": ["camera", 1],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                load_profile(profile_path)

    def test_reads_linux_temperature_millidegrees(self):
        with tempfile.TemporaryDirectory() as directory:
            sensor = Path(directory) / "temp"; sensor.write_text("42500", encoding="utf-8")
            self.assertEqual(read_temperature_celsius(sensor), 42.5)

    def test_serve_rejects_non_positive_or_non_finite_intervals(self):
        self.assertEqual(main(["--interval", "0", "serve"]), 2)
        self.assertEqual(main(["--interval", "nan", "serve"]), 2)


if __name__ == "__main__":
    unittest.main()
