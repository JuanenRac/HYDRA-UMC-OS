# =============================================================================
# HYDRA-UMC-OS - Device agent probes tests
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The optional probes of the agent (diagnostics.probes): the firmware throttling bits, the Hailo device, the state of some units.

The first group drives the functions with a runner that answers by itself. The second group starts real programs: stand-ins written as shell scripts in a
temporary folder that print what `vcgencmd` and `systemctl` print, so the real `subprocess` path (no shell, a time limit, a missing program, a non-zero
exit) is exercised on a Linux machine.
"""
import copy
import json
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from hydra_umc_os.agent import DEFAULT_CONFIG, health, load_config, main, probe_checks, throttle_check, unit_check, validate_probes


def done(stdout: str = "", code: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], code, stdout=stdout, stderr="")


def runner(table: dict):
    calls = []

    def run(argv, **kwargs):
        calls.append((list(argv), kwargs))
        answer = table.get(tuple(argv))
        if isinstance(answer, BaseException):
            raise answer
        return answer if answer is not None else done("", 1)

    run.calls = calls  # type: ignore[attr-defined]
    return run


class ThrottleTests(unittest.TestCase):
    def test_a_clean_answer_is_a_pass(self):
        self.assertEqual(throttle_check("throttled=0x0", None)["state"], "PASS")

    def test_under_voltage_or_throttling_now_is_a_fail(self):
        for text, names in (("throttled=0x1", ["under-voltage"]), ("throttled=0x4", ["throttled"]), ("throttled=0x5", ["under-voltage", "throttled"])):
            result = throttle_check(text, None)
            self.assertEqual((result["state"], result["now"]), ("FAIL", names), text)

    def test_a_cap_or_a_soft_limit_now_and_anything_since_the_boot_is_a_warn(self):
        self.assertEqual(throttle_check("throttled=0x2", None)["state"], "WARN")
        self.assertEqual(throttle_check("throttled=0x8", None)["state"], "WARN")
        past = throttle_check("throttled=0x50000", None)
        self.assertEqual((past["state"], past["now"], past["since_boot"]), ("WARN", [], ["under-voltage", "throttled"]))

    def test_an_answer_that_cannot_be_read_is_a_warn_with_the_reason_never_a_pass(self):
        for text in ("", "throttled=", "throttled=0xZZ", "temp=45.0'C", "throttled=0x123456789", None):
            self.assertEqual(throttle_check(text, None)["state"], "WARN", text)
        self.assertIn("not installed", throttle_check(None, "vcgencmd is not installed")["reason"])
        self.assertEqual(throttle_check("throttled=0x0", "vcgencmd exited with status 1")["state"], "WARN")

    def test_the_hex_digits_may_be_in_either_case(self):
        self.assertEqual(throttle_check("throttled=0xA", None)["state"], "WARN")
        self.assertEqual(throttle_check("throttled=0xa", None)["state"], "WARN")


class UnitTests(unittest.TestCase):
    def test_active_is_a_pass_and_failed_a_fail_and_everything_else_a_warn(self):
        self.assertEqual(unit_check("active\n", None)["state"], "PASS")
        self.assertEqual(unit_check("failed", None)["state"], "FAIL")
        for word in ("inactive", "activating", "deactivating", "unknown", "", None):
            self.assertEqual(unit_check(word, None)["state"], "WARN", word)

    def test_the_reason_is_kept_for_a_warn(self):
        self.assertEqual(unit_check(None, "systemctl is not installed")["reason"], "systemctl is not installed")


class ProbeChecksTests(unittest.TestCase):
    def test_nothing_runs_unless_enabled_is_exactly_true(self):
        for probes in (None, {}, {"enabled": False}, {"enabled": 1}, {"enabled": "true"}, {"units": ["a"]}):
            run = runner({})
            self.assertEqual(probe_checks(probes, run=run), {})
            self.assertEqual(run.calls, [])

    def test_the_throttling_the_device_and_each_unit_are_checked_without_a_shell(self):
        run = runner(
            {
                ("vcgencmd", "get_throttled"): done("throttled=0x0\n"),
                ("systemctl", "is-active", "hydra-umc-server"): done("active\n"),
                ("systemctl", "is-active", "hydra-umc-voice-ui"): done("inactive\n", 3),
            }
        )
        checks = probe_checks(
            {"enabled": True, "hailo_device": "/dev/hailo0", "units": ["hydra-umc-server", "hydra-umc-voice-ui"]}, run=run, exists=lambda path: path == "/dev/hailo0"
        )
        self.assertEqual(checks["throttling"]["state"], "PASS")
        self.assertEqual(checks["hailo"], {"state": "PASS", "device": "/dev/hailo0", "present": True})
        self.assertEqual(checks["unit:hydra-umc-server"]["state"], "PASS")
        self.assertEqual(checks["unit:hydra-umc-voice-ui"]["state"], "WARN")
        for argv, kwargs in run.calls:
            self.assertIsInstance(argv, list)
            self.assertNotIn("shell", kwargs)
            self.assertEqual(kwargs["timeout"], 5.0)

    def test_a_device_that_is_not_there_is_a_warn_not_a_fail(self):
        checks = probe_checks({"enabled": True, "hailo_device": "/dev/hailo0"}, run=runner({}), exists=lambda path: False)
        self.assertEqual(checks["hailo"]["state"], "WARN")

    def test_a_missing_program_a_timeout_and_a_failure_to_start_are_warns_with_their_reason(self):
        table = {
            ("vcgencmd", "get_throttled"): FileNotFoundError(),
            ("systemctl", "is-active", "a"): subprocess.TimeoutExpired("systemctl", 5),
            ("systemctl", "is-active", "b"): PermissionError(13, "Permission denied"),
        }
        checks = probe_checks({"enabled": True, "units": ["a", "b"]}, run=runner(table))
        self.assertIn("not installed", checks["throttling"]["reason"])
        self.assertIn("did not answer", checks["unit:a"]["reason"])
        self.assertIn("could not be started", checks["unit:b"]["reason"])
        self.assertEqual({check["state"] for check in checks.values()}, {"WARN"})

    def test_the_names_of_the_programs_and_the_time_limit_come_from_the_configuration(self):
        run = runner({("/usr/bin/vcgencmd", "get_throttled"): done("throttled=0x0"), ("/bin/systemctl", "is-active", "x"): done("active")})
        checks = probe_checks({"enabled": True, "vcgencmd": "/usr/bin/vcgencmd", "systemctl": "/bin/systemctl", "units": ["x"], "timeout_seconds": 2.5}, run=run)
        self.assertEqual(checks["throttling"]["state"], "PASS")
        self.assertEqual(checks["unit:x"]["state"], "PASS")
        self.assertEqual({kwargs["timeout"] for _argv, kwargs in run.calls}, {2.5})


class ValidationTests(unittest.TestCase):
    def test_a_good_block_and_no_block_pass(self):
        validate_probes(None)
        validate_probes({})
        validate_probes({"enabled": True, "vcgencmd": "vcgencmd", "systemctl": "/usr/bin/systemctl", "hailo_device": "/dev/hailo0", "units": ["hydra-umc-server", "getty@tty1"], "timeout_seconds": 30})

    def test_every_bad_value_is_refused_with_the_name_of_the_key(self):
        bad = [
            ([], "diagnostics.probes must be an object"),
            ({"enabled": "yes"}, "probes.enabled"),
            ({"colour": 1}, "unknown keys"),
            ({"vcgencmd": "vcgencmd; reboot"}, "probes.vcgencmd"),
            ({"vcgencmd": 5}, "probes.vcgencmd"),
            ({"systemctl": "a b"}, "probes.systemctl"),
            ({"systemctl": ""}, "probes.systemctl"),
            ({"hailo_device": "dev/hailo0"}, "probes.hailo_device"),
            ({"hailo_device": "/dev/hailo0 "}, "probes.hailo_device"),
            ({"units": "hydra-umc-server"}, "probes.units"),
            ({"units": ["Upper"]}, "probes.units"),
            ({"units": ["a b"]}, "probes.units"),
            ({"units": ["a;b"]}, "probes.units"),
            ({"units": [5]}, "probes.units"),
            ({"units": ["u"] * 33}, "probes.units"),
            ({"timeout_seconds": 0}, "timeout_seconds"),
            ({"timeout_seconds": 31}, "timeout_seconds"),
            ({"timeout_seconds": float("nan")}, "timeout_seconds"),
            ({"timeout_seconds": True}, "timeout_seconds"),
            ({"timeout_seconds": "5"}, "timeout_seconds"),
        ]
        for block, message in bad:
            with self.assertRaisesRegex(ValueError, message):
                validate_probes(block)

    def test_the_default_configuration_has_no_probes_so_a_default_install_runs_nothing_extra(self):
        self.assertNotIn("probes", DEFAULT_CONFIG["diagnostics"])
        report = health(DEFAULT_CONFIG, free_bytes=2_000_000_000, interfaces=["eth0"], temperature_celsius=40.0, probe_run=runner({}))
        self.assertEqual(set(report.checks), {"storage", "network", "runtime", "temperature"})

    def test_a_configuration_file_with_a_bad_block_is_refused_when_it_is_loaded(self):
        with tempfile.TemporaryDirectory() as folder:
            config = copy.deepcopy(DEFAULT_CONFIG)
            config["diagnostics"]["probes"] = {"enabled": True, "units": ["bad unit"]}
            path = Path(folder) / "agent.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "probes.units"):
                load_config(path)
            self.assertEqual(main(["--config", str(path), "health"]), 2)


class HealthWithProbesTests(unittest.TestCase):
    def config(self, **probes):
        config = copy.deepcopy(DEFAULT_CONFIG)
        config["diagnostics"]["probes"] = {"enabled": True, **probes}
        return config

    def test_a_probe_that_fails_makes_the_whole_report_a_fault_and_a_warn_makes_it_degraded(self):
        kwargs = {"free_bytes": 2_000_000_000, "interfaces": ["eth0"], "temperature_celsius": 40.0}
        failing = health(self.config(), probe_run=runner({("vcgencmd", "get_throttled"): done("throttled=0x1")}), **kwargs)
        self.assertEqual((failing.state, failing.checks["throttling"]["state"]), ("FAULT", "FAIL"))
        warning = health(self.config(), probe_run=runner({}), **kwargs)
        self.assertEqual(warning.state, "DEGRADED")
        clean = health(self.config(), probe_run=runner({("vcgencmd", "get_throttled"): done("throttled=0x0")}), **kwargs)
        self.assertEqual(clean.state, "READY")


@unittest.skipIf(sys.platform == "win32", "the stand-ins are shell scripts")
class RealProgramTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name)

    def script(self, name: str, body: str) -> str:
        target = self.path / name
        target.write_text("#!/bin/sh\n" + body + "\n", encoding="utf-8")
        target.chmod(target.stat().st_mode | stat.S_IXUSR)
        return str(target)

    def test_real_programs_are_started_and_read(self):
        vcgencmd = self.script("vcgencmd", 'echo "throttled=0x50000"')
        systemctl = self.script("systemctl", 'if [ "$2" = ok ]; then echo active; else echo failed; exit 3; fi')
        checks = probe_checks({"enabled": True, "vcgencmd": vcgencmd, "systemctl": systemctl, "units": ["ok", "broken"]})
        self.assertEqual(checks["throttling"]["state"], "WARN")
        self.assertEqual(checks["unit:ok"]["state"], "PASS")
        self.assertEqual(checks["unit:broken"]["state"], "FAIL")

    def test_a_program_that_does_not_exist_is_a_warn(self):
        checks = probe_checks({"enabled": True, "vcgencmd": str(self.path / "absent")})
        self.assertEqual(checks["throttling"]["state"], "WARN")
        self.assertIn("not installed", checks["throttling"]["reason"])

    def test_a_program_that_hangs_is_cut_off(self):
        vcgencmd = self.script("vcgencmd", "exec sleep 30")
        checks = probe_checks({"enabled": True, "vcgencmd": vcgencmd, "timeout_seconds": 0.5})
        self.assertEqual(checks["throttling"]["state"], "WARN")
        self.assertIn("did not answer", checks["throttling"]["reason"])

    def test_a_program_that_exits_with_an_error_is_a_warn_even_if_it_printed_a_clean_answer(self):
        vcgencmd = self.script("vcgencmd", 'echo "throttled=0x0"; exit 1')
        checks = probe_checks({"enabled": True, "vcgencmd": vcgencmd})
        self.assertEqual(checks["throttling"]["state"], "WARN")

    def test_the_agent_command_line_reports_the_probes(self):
        vcgencmd = self.script("vcgencmd", 'echo "throttled=0x0"')
        config = copy.deepcopy(DEFAULT_CONFIG)
        config["diagnostics"]["probes"] = {"enabled": True, "vcgencmd": vcgencmd}
        path = self.path / "agent.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        done_ = subprocess.run([sys.executable, "-m", "hydra_umc_os.agent", "--config", str(path), "health"], capture_output=True, text=True, timeout=60, check=False)
        self.assertEqual(done_.returncode, 0, done_.stderr)
        report = json.loads(done_.stdout)
        self.assertEqual(report["checks"]["throttling"]["state"], "PASS")


if __name__ == "__main__":
    unittest.main()
