# =============================================================================
# HYDRA-UMC-OS - Device agent edge cases, failure paths and fuzzing
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Branches of the agent that the happy-path tests do not reach: every refusal of the
configuration and profile readers, the probe verdicts, the report gate, the command line
and a seeded fuzz of the configuration reader. Nothing here needs a socket or a CM5."""

import contextlib
import copy
import io
import json
import math
import random
import subprocess
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from hydra_umc_os import agent
from hydra_umc_os.agent import (
    DEFAULT_CONFIG,
    HealthReport,
    LocalSocketServer,
    ReportGate,
    load_config,
    load_profile,
    main,
    network_interfaces,
    probe_checks,
    read_temperature_celsius,
    storage_probe_path,
    throttle_check,
    unit_check,
    validate_local_socket,
    validate_probes,
)


def valid_config(**diagnostics):
    config = copy.deepcopy(DEFAULT_CONFIG)
    config["diagnostics"].update(diagnostics)
    return config


def write_json(directory, name, value):
    path = Path(directory) / name
    path.write_text(value if isinstance(value, str) else json.dumps(value), encoding="utf-8")
    return path


class ConfigRefusalTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = self._tmp.name

    def refuse(self, config, fragment):
        path = write_json(self.dir, "c.json", config)
        with self.assertRaises(ValueError) as caught:
            load_config(path)
        self.assertIn(fragment, str(caught.exception))

    def test_no_path_returns_an_independent_copy_of_the_defaults(self):
        first = load_config(None)
        first["node"]["id"] = "changed"
        self.assertEqual(load_config(None)["node"]["id"], "hydra-umc-node")

    def test_missing_file_is_a_clear_error(self):
        with self.assertRaises(ValueError) as caught:
            load_config(Path(self.dir) / "absent.json")
        self.assertIn("not found", str(caught.exception))

    def test_invalid_json_is_a_clear_error(self):
        path = write_json(self.dir, "bad.json", "{not json")
        with self.assertRaises(ValueError) as caught:
            load_config(path)
        self.assertIn("not valid JSON", str(caught.exception))

    def test_top_level_must_be_an_object_with_schema_one(self):
        self.refuse([1, 2], "schema_version")
        self.refuse({"schema_version": "2.0"}, "schema_version")
        self.refuse({}, "schema_version")

    def test_node_id_must_be_a_non_blank_string(self):
        for node in (None, [], {}, {"id": 5}, {"id": "   "}, {"id": ""}):
            config = valid_config()
            config["node"] = node
            self.refuse(config, "node.id")

    def test_node_profile_must_be_a_non_blank_string_when_present(self):
        for profile in (3, "", "  ", None):
            config = valid_config()
            config["node"]["profile"] = profile
            self.refuse(config, "node.profile")

    def test_diagnostics_must_be_an_object(self):
        for diagnostics in (None, [], "x", 3):
            config = valid_config()
            config["diagnostics"] = diagnostics
            self.refuse(config, "diagnostics must be an object")

    def test_minimum_free_bytes_rules(self):
        for value in (-1, True, False, "5", 1.5, None):
            self.refuse(valid_config(minimum_free_bytes=value), "minimum_free_bytes")
        # zero is a legal threshold
        path = write_json(self.dir, "zero.json", valid_config(minimum_free_bytes=0))
        self.assertEqual(load_config(path)["diagnostics"]["minimum_free_bytes"], 0)

    def test_maximum_temperature_rules(self):
        for value in (0, -5, True, "80", None, float("inf"), float("nan")):
            config = valid_config(maximum_temperature_celsius=value)
            path = write_json(self.dir, "t.json", json.dumps(config))  # json keeps Infinity/NaN readable
            with self.assertRaises(ValueError, msg=repr(value)) as caught:
                load_config(path)
            self.assertIn("maximum_temperature_celsius", str(caught.exception))

    def test_a_missing_maximum_temperature_gets_the_safe_default(self):
        config = valid_config()
        del config["diagnostics"]["maximum_temperature_celsius"]
        loaded = load_config(write_json(self.dir, "d.json", config))
        self.assertEqual(loaded["diagnostics"]["maximum_temperature_celsius"], 80.0)

    def test_storage_path_must_be_a_non_blank_string_when_present(self):
        for value in (3, "", "  ", []):
            self.refuse(valid_config(storage_path=value), "storage_path")
        loaded = load_config(write_json(self.dir, "s.json", valid_config(storage_path="/var/lib")))
        self.assertEqual(loaded["diagnostics"]["storage_path"], "/var/lib")

    def test_probe_and_socket_blocks_are_validated_through_the_loader(self):
        self.refuse(valid_config(probes=[]), "probes must be an object")
        self.refuse(valid_config(local_socket="x"), "local_socket must be an object")


class ProbeValidationTests(unittest.TestCase):
    def bad(self, block, fragment):
        with self.assertRaises(ValueError) as caught:
            validate_probes(block)
        self.assertIn(fragment, str(caught.exception))

    def test_absent_block_is_fine(self):
        self.assertIsNone(validate_probes(None))

    def test_unknown_keys_are_refused_by_name(self):
        self.bad({"shell": "rm"}, "unknown keys")

    def test_enabled_must_be_a_real_boolean(self):
        for value in (1, "true", None):
            self.bad({"enabled": value}, "enabled")

    def test_program_names_allow_only_plain_characters(self):
        for key in ("vcgencmd", "systemctl"):
            for value in ("a b", "x;y", "$(id)", "", "a" * 121, 5, "`x`", "a|b"):
                self.bad({key: value}, key)
            validate_probes({key: "/usr/bin/" + key})

    def test_hailo_device_must_be_an_absolute_plain_path(self):
        for value in ("hailo0", "/dev/hailo 0", 7, "/dev/h;x"):
            self.bad({"hailo_device": value}, "hailo_device")
        validate_probes({"hailo_device": "/dev/hailo0"})

    def test_units_list_rules(self):
        self.bad({"units": "ssh"}, "units")
        self.bad({"units": [f"u{i}" for i in range(33)]}, "units")
        self.bad({"units": ["Upper"]}, "units")
        self.bad({"units": ["ok", 4]}, "units")
        self.bad({"units": ["a b"]}, "units")
        self.bad({"units": ["-lead"]}, "units")
        validate_probes({"units": [f"u{i}" for i in range(32)]})
        validate_probes({"units": ["ssh.service", "getty@tty1.service"]})

    def test_timeout_bounds(self):
        for value in (0, -1, 31, True, "5", float("nan"), float("inf")):
            self.bad({"timeout_seconds": value}, "timeout_seconds")
        validate_probes({"timeout_seconds": 30})
        validate_probes({"timeout_seconds": 0.5})


class SocketValidationTests(unittest.TestCase):
    def bad(self, block, fragment):
        with self.assertRaises(ValueError) as caught:
            validate_local_socket(block)
        self.assertIn(fragment, str(caught.exception))

    def test_absent_block_is_fine(self):
        self.assertIsNone(validate_local_socket(None))

    def test_unknown_keys_and_wrong_types(self):
        self.bad({"port": 1}, "unknown keys")
        self.bad({"enabled": "yes"}, "enabled")

    def test_path_rules(self):
        for path in ("run/x.sock", "/run/../etc/x", "/run/x y", 5, "/" + "a" * 100):
            self.bad({"path": path}, "path")
        validate_local_socket({"path": "/run/hydra-umc-agent/agent.sock"})

    def test_mode_must_give_nothing_to_other_users(self):
        for mode in ("0666", "0777", "0007", "0664", "999", "660x", 660, ""):
            self.bad({"mode": mode}, "mode")
        for mode in ("0660", "660", "0600", "0770", "0000"):
            validate_local_socket({"mode": mode})

    def test_cache_seconds_bounds(self):
        for value in (-1, 61, True, "2", float("nan")):
            self.bad({"cache_seconds": value}, "cache_seconds")
        validate_local_socket({"cache_seconds": 0})
        validate_local_socket({"cache_seconds": 60})


class ProbeVerdictTests(unittest.TestCase):
    def test_every_current_throttle_bit_is_named(self):
        cases = {0x1: "under-voltage", 0x2: "arm-frequency-capped", 0x4: "throttled", 0x8: "soft-temperature-limit"}
        for bit, name in cases.items():
            result = throttle_check(f"throttled=0x{bit:x}", None)
            self.assertEqual(result["now"], [name])
            self.assertEqual(result["state"], "FAIL" if bit in (0x1, 0x4) else "WARN")

    def test_a_past_event_only_warns_and_is_reported_since_boot(self):
        result = throttle_check("throttled=0x50000", None)
        self.assertEqual(result["state"], "WARN")
        self.assertEqual(result["now"], [])
        self.assertEqual(sorted(result["since_boot"]), ["throttled", "under-voltage"])

    def test_zero_is_a_pass(self):
        self.assertEqual(throttle_check("throttled=0x0", None)["state"], "PASS")

    def test_unreadable_or_failed_answers_are_a_warn_never_a_pass(self):
        for output in (None, "", "garbage", "throttled=0xZZ", "throttled=0x123456789", "throttled=0x"):
            self.assertEqual(throttle_check(output, None)["state"], "WARN", output)
        self.assertEqual(throttle_check("throttled=0x0", "boom")["reason"], "boom")

    def test_unit_states(self):
        self.assertEqual(unit_check("active\n", None)["state"], "PASS")
        self.assertEqual(unit_check("failed", None)["state"], "FAIL")
        inactive = unit_check("inactive", "systemctl exited with status 3")
        self.assertEqual(inactive["state"], "WARN")
        self.assertEqual(inactive["reason"], "systemctl exited with status 3")
        self.assertEqual(unit_check(None, "x is not installed")["active_state"], "unknown")
        self.assertNotIn("reason", unit_check("activating", None))

    def test_probes_are_silent_unless_enabled_with_exactly_true(self):
        def explode(*_a, **_k):
            raise AssertionError("must not run")

        for probes in (None, {}, {"enabled": False}, {"enabled": 1}, {"enabled": "true"}):
            self.assertEqual(probe_checks(probes, run=explode), {})

    def run_stub(self, table):
        calls = []

        def run(argv, **kwargs):
            calls.append((argv, kwargs))
            outcome = table[argv[0]]
            if isinstance(outcome, BaseException):
                raise outcome
            return subprocess.CompletedProcess(argv, outcome[0], stdout=outcome[1], stderr="")

        run.calls = calls
        return run

    def test_probe_runs_without_a_shell_and_with_the_configured_timeout(self):
        run = self.run_stub({"vcgencmd": (0, "throttled=0x0\n"), "systemctl": (0, "active\n")})
        checks = probe_checks({"enabled": True, "units": ["ssh"], "timeout_seconds": 7}, run=run)
        self.assertEqual(checks["throttling"]["state"], "PASS")
        self.assertEqual(checks["unit:ssh"]["state"], "PASS")
        for argv, kwargs in run.calls:
            self.assertIsInstance(argv, list)
            self.assertEqual(kwargs["timeout"], 7.0)
            self.assertFalse(kwargs.get("shell", False))

    def test_a_missing_tool_a_timeout_and_an_os_error_are_warns_with_a_reason(self):
        run = self.run_stub({
            "vcgencmd": FileNotFoundError(),
            "systemctl": subprocess.TimeoutExpired("systemctl", 2),
        })
        checks = probe_checks({"enabled": True, "units": ["ssh"], "timeout_seconds": 2}, run=run)
        self.assertEqual(checks["throttling"]["state"], "WARN")
        self.assertIn("not installed", checks["throttling"]["reason"])
        self.assertEqual(checks["unit:ssh"]["state"], "WARN")
        self.assertIn("did not answer in 2 s", checks["unit:ssh"]["reason"])
        run = self.run_stub({"vcgencmd": PermissionError(13, "Permission denied")})
        checks = probe_checks({"enabled": True}, run=run)
        self.assertIn("could not be started", checks["throttling"]["reason"])

    def test_a_non_zero_exit_keeps_the_output_and_names_the_status(self):
        run = self.run_stub({"vcgencmd": (1, "throttled=0x0"), "systemctl": (3, "inactive\n")})
        checks = probe_checks({"enabled": True, "units": ["x"]}, run=run)
        self.assertIn("status 1", checks["throttling"]["reason"])
        self.assertIn("status 3", checks["unit:x"]["reason"])
        self.assertEqual(checks["unit:x"]["active_state"], "inactive")

    def test_hailo_presence_follows_the_device_path(self):
        run = self.run_stub({"vcgencmd": (0, "throttled=0x0")})
        present = probe_checks({"enabled": True, "hailo_device": "/dev/hailo0"}, run=run, exists=lambda p: True)
        absent = probe_checks({"enabled": True, "hailo_device": "/dev/hailo0"}, run=run, exists=lambda p: False)
        self.assertEqual(present["hailo"], {"state": "PASS", "device": "/dev/hailo0", "present": True})
        self.assertEqual(absent["hailo"]["state"], "WARN")
        self.assertNotIn("hailo", probe_checks({"enabled": True}, run=run))

    def test_a_failing_probe_degrades_or_faults_the_overall_health(self):
        run = self.run_stub({"vcgencmd": (0, "throttled=0x1"), "systemctl": (0, "active")})
        config = valid_config(probes={"enabled": True})
        report = agent.health(config, free_bytes=2**31, interfaces=["eth0"], temperature_celsius=30.0, probe_run=run)
        self.assertEqual(report.state, "FAULT")
        run = self.run_stub({"vcgencmd": FileNotFoundError()})
        report = agent.health(config, free_bytes=2**31, interfaces=["eth0"], temperature_celsius=30.0, probe_run=run)
        self.assertEqual(report.state, "DEGRADED")


class HealthBoundaryTests(unittest.TestCase):
    def state(self, **kw):
        base = dict(free_bytes=2**31, interfaces=["eth0"], temperature_celsius=30.0)
        base.update(kw)
        return agent.health(valid_config(), **base)

    def test_storage_threshold_is_inclusive(self):
        minimum = DEFAULT_CONFIG["diagnostics"]["minimum_free_bytes"]
        self.assertEqual(self.state(free_bytes=minimum).state, "READY")
        report = self.state(free_bytes=minimum - 1)
        self.assertEqual(report.state, "FAULT")
        self.assertEqual(report.checks["storage"]["state"], "FAIL")

    def test_temperature_limit_is_exclusive_of_the_pass_side(self):
        self.assertEqual(self.state(temperature_celsius=79.99).state, "READY")
        self.assertEqual(self.state(temperature_celsius=80.0).state, "FAULT")
        self.assertEqual(self.state(temperature_celsius=-20.0).state, "READY")

    def test_the_configured_limit_wins_over_the_default(self):
        config = valid_config(maximum_temperature_celsius=50.0)
        report = agent.health(config, free_bytes=2**31, interfaces=["eth0"], temperature_celsius=55.0)
        self.assertEqual(report.checks["temperature"]["maximum_celsius"], 50.0)
        self.assertEqual(report.state, "FAULT")

    def test_a_fail_outranks_a_warn(self):
        report = self.state(free_bytes=0, interfaces=[], temperature_celsius=None)
        self.assertEqual(report.state, "FAULT")
        self.assertEqual(report.checks["network"]["state"], "WARN")
        self.assertEqual(report.checks["temperature"]["state"], "WARN")

    def test_report_timestamp_is_utc_iso(self):
        stamp = self.state().timestamp_utc
        self.assertRegex(stamp, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_storage_probe_path_falls_back_to_the_working_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(storage_probe_path({"storage_path": tmp}), Path(tmp))
        self.assertEqual(storage_probe_path({"storage_path": "/no/such/folder/here"}), Path.cwd())
        self.assertEqual(storage_probe_path({"storage_path": "   "}), Path.cwd())
        self.assertEqual(storage_probe_path({}), Path.cwd())


class SystemReaderTests(unittest.TestCase):
    def test_network_interfaces_skips_loopback_and_sorts(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("wlan0", "lo", "eth0", "can0"):
                (Path(tmp) / name).mkdir()
            self.assertEqual(network_interfaces(Path(tmp)), ["can0", "eth0", "wlan0"])
            self.assertEqual(network_interfaces(Path(tmp) / "absent"), [])

    def test_temperature_reader_handles_good_bad_and_missing_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            good = write_json(tmp, "good", "52300\n")
            self.assertAlmostEqual(read_temperature_celsius(good), 52.3)
            self.assertAlmostEqual(read_temperature_celsius(write_json(tmp, "neg", "-5000")), -5.0)
            self.assertIsNone(read_temperature_celsius(write_json(tmp, "bad", "hot")))
            self.assertIsNone(read_temperature_celsius(write_json(tmp, "empty", "")))
            self.assertIsNone(read_temperature_celsius(Path(tmp) / "absent"))


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def refuse(self, profile, fragment):
        path = write_json(self._tmp.name, "p.json", profile)
        with self.assertRaises(ValueError) as caught:
            load_profile(path)
        self.assertIn(fragment, str(caught.exception))

    def good(self, **change):
        profile = {"schema_version": "1.0", "profile": "dsi", "enabled_services": ["a"], "requires": ["b"]}
        profile.update(change)
        return profile

    def test_a_good_profile_loads(self):
        path = write_json(self._tmp.name, "ok.json", self.good())
        self.assertEqual(load_profile(path)["profile"], "dsi")

    def test_unreadable_files_are_one_error(self):
        with self.assertRaises(ValueError):
            load_profile(Path(self._tmp.name) / "absent.json")
        path = write_json(self._tmp.name, "bad.json", "{")
        with self.assertRaises(ValueError):
            load_profile(path)

    def test_schema_and_name_rules(self):
        self.refuse(self.good(schema_version="2.0"), "schema_version")
        self.refuse(self.good(profile=""), "non-empty profile name")
        self.refuse(self.good(profile=4), "non-empty profile name")

    def test_lists_must_be_lists_of_unique_non_empty_strings(self):
        self.refuse(self.good(enabled_services="a"), "arrays")
        self.refuse(self.good(requires=None), "arrays")
        self.refuse(self.good(enabled_services=["a", ""]), "enabled_services must contain")
        self.refuse(self.good(requires=[1]), "requires must contain")
        self.refuse(self.good(enabled_services=["a", "a"]), "duplicates")
        self.refuse(self.good(requires=["b", "b"]), "duplicates")


class ReportGateTests(unittest.TestCase):
    def report(self, state="READY", **checks):
        checks = checks or {"storage": {"state": "PASS", "free_bytes": 1}}
        return HealthReport("1.0", state, "t", checks, "0", "id")

    def test_without_on_change_every_report_is_written(self):
        gate = ReportGate(False)
        self.assertTrue(all(gate.should_emit(self.report(), t) for t in (0, 1, 2)))

    def test_on_change_writes_the_first_report_then_stays_quiet(self):
        gate = ReportGate(True, 300.0)
        self.assertTrue(gate.should_emit(self.report(), 0.0))
        self.assertFalse(gate.should_emit(self.report(), 10.0))
        self.assertFalse(gate.should_emit(self.report(), 299.9))

    def test_the_heartbeat_fires_at_exactly_the_interval(self):
        gate = ReportGate(True, 300.0)
        gate.should_emit(self.report(), 0.0)
        self.assertTrue(gate.should_emit(self.report(), 300.0))
        self.assertFalse(gate.should_emit(self.report(), 599.0))

    def test_a_changed_overall_or_single_check_state_is_written(self):
        gate = ReportGate(True, 300.0)
        gate.should_emit(self.report(), 0.0)
        self.assertTrue(gate.should_emit(self.report("FAULT"), 1.0))
        self.assertTrue(gate.should_emit(self.report("FAULT", storage={"state": "FAIL"}), 2.0))
        self.assertFalse(gate.should_emit(self.report("FAULT", storage={"state": "FAIL"}), 3.0))

    def test_measured_values_alone_never_count_as_a_change(self):
        gate = ReportGate(True, 300.0)
        gate.should_emit(self.report(storage={"state": "PASS", "free_bytes": 5}), 0.0)
        self.assertFalse(gate.should_emit(self.report(storage={"state": "PASS", "free_bytes": 999}), 1.0))

    def test_a_new_check_name_counts_as_a_change(self):
        gate = ReportGate(True, 300.0)
        gate.should_emit(self.report(storage={"state": "PASS"}), 0.0)
        self.assertTrue(gate.should_emit(self.report(storage={"state": "PASS"}, extra={"state": "PASS"}), 1.0))


class CommandLineTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def run_main(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_describe_prints_a_json_descriptor(self):
        code, out, _ = self.run_main("describe")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["node_id"], "hydra-umc-node")

    def test_health_prints_a_json_report_with_the_boot_session(self):
        code, out, _ = self.run_main("health")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["boot_session_id"], agent.BOOT_SESSION_ID)

    def test_a_bad_config_exits_two_with_the_reason_on_stderr(self):
        path = write_json(self._tmp.name, "bad.json", {"schema_version": "9"})
        code, out, err = self.run_main("--config", str(path), "health")
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("hydra-umc-agent:", err)
        self.assertIn("schema_version", err)

    def test_a_missing_config_file_exits_two(self):
        code, _, err = self.run_main("--config", str(Path(self._tmp.name) / "none.json"), "describe")
        self.assertEqual(code, 2)
        self.assertIn("not found", err)

    def test_query_needs_a_socket(self):
        code, _, err = self.run_main("query")
        self.assertEqual(code, 2)
        self.assertIn("--socket", err)

    def test_query_prints_the_answer_and_turns_a_refusal_into_exit_two(self):
        with unittest.mock.patch.object(agent, "query_socket", return_value={"state": "READY"}) as ask:
            code, out, _ = self.run_main("query", "--socket", "/run/x.sock", "--what", "describe")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), {"state": "READY"})
        ask.assert_called_once_with("/run/x.sock", "describe")
        with unittest.mock.patch.object(agent, "query_socket", side_effect=ConnectionRefusedError("nobody")):
            code, _, err = self.run_main("query", "--socket", "/run/x.sock")
        self.assertEqual(code, 2)
        self.assertIn("nobody", err)

    def test_serve_refuses_a_non_positive_or_non_finite_interval(self):
        for value in ("0", "-1", "nan", "inf"):
            code, _, err = self.run_main("serve", "--interval", value)
            self.assertEqual(code, 2, value)
            self.assertIn("interval", err)

    def test_serve_refuses_a_bad_heartbeat(self):
        for value in ("0", "-5", "nan"):
            code, _, err = self.run_main("serve", "--heartbeat", value)
            self.assertEqual(code, 2, value)
            self.assertIn("heartbeat", err)

    def test_an_unknown_command_is_an_argparse_exit(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            main(["reboot"])
        self.assertEqual(caught.exception.code, 2)

    def serve(self, *argv, ticks=3):
        counter = {"n": 0}

        def sleeper(_seconds):
            counter["n"] += 1
            if counter["n"] >= ticks:
                raise KeyboardInterrupt

        with unittest.mock.patch.object(agent.time, "sleep", sleeper), \
                unittest.mock.patch.object(agent.LocalSocketServer, "from_config", return_value=None):
            return self.run_main("serve", *argv)

    def test_serve_writes_one_compact_line_per_tick_and_stops_cleanly_on_interrupt(self):
        code, out, _ = self.serve("--interval", "1")
        self.assertEqual(code, 0)
        lines = out.strip().splitlines()
        self.assertEqual(len(lines), 3)
        for line in lines:
            self.assertEqual(line, json.dumps(json.loads(line), sort_keys=True, separators=(",", ":")))

    def test_serve_with_report_on_change_is_quiet_when_nothing_changes(self):
        fixed = agent.HealthReport("1.0", "READY", "t", {"storage": {"state": "PASS"}}, "0", "id")
        with unittest.mock.patch.object(agent, "health", return_value=fixed):
            code, out, _ = self.serve("--interval", "1", "--report-on-change", "--heartbeat", "1000", ticks=5)
        self.assertEqual(code, 0)
        self.assertEqual(len(out.strip().splitlines()), 1)

    def test_serve_closes_the_local_socket_even_when_stopped(self):
        local = unittest.mock.Mock()
        counter = {"n": 0}

        def sleeper(_seconds):
            counter["n"] += 1
            raise KeyboardInterrupt

        with unittest.mock.patch.object(agent.time, "sleep", sleeper), \
                unittest.mock.patch.object(agent.LocalSocketServer, "from_config", return_value=local):
            code, _, _ = self.run_main("serve")
        self.assertEqual(code, 0)
        local.start.assert_called_once()
        local.close.assert_called_once()

    def test_a_socket_that_cannot_start_is_exit_two_and_nothing_to_close(self):
        local = unittest.mock.Mock()
        local.start.side_effect = ValueError("the folder of /x does not exist")
        with unittest.mock.patch.object(agent.LocalSocketServer, "from_config", return_value=local):
            code, _, err = self.run_main("serve")
        self.assertEqual(code, 2)
        self.assertIn("does not exist", err)
        local.close.assert_not_called()


class SocketLogicTests(unittest.TestCase):
    """The request/answer logic of the socket server, with no socket opened."""

    def server(self, clock=None, cache=2.0):
        config = valid_config()
        kwargs = {"clock": clock} if clock else {}
        return LocalSocketServer(config, path="/run/none.sock", cache_seconds=cache, **kwargs)

    def test_from_config_is_off_unless_enabled_is_exactly_true(self):
        for block in (None, {}, {"enabled": False}, {"enabled": 1}, {"path": "/run/a.sock"}):
            config = valid_config()
            if block is not None:
                config["diagnostics"]["local_socket"] = block
            self.assertIsNone(LocalSocketServer.from_config(config), block)

    def test_from_config_applies_the_documented_defaults(self):
        config = valid_config(local_socket={"enabled": True})
        server = LocalSocketServer.from_config(config)
        self.assertEqual(server.path, agent.DEFAULT_SOCKET_PATH)
        self.assertEqual(server.mode, 0o660)
        self.assertEqual(server.cache_seconds, 2.0)

    def test_an_unknown_command_gets_an_error_line_that_lists_the_commands(self):
        for request in (b"", b"reboot", b"HEALTH", b"health extra", b"\xff\xfe"):
            line = self.server().answer(request)
            self.assertTrue(line.endswith("\n"))
            answer = json.loads(line)
            self.assertEqual(answer["error"], "unknown command")
            self.assertEqual(answer["commands"], ["describe", "health"])

    def test_surrounding_whitespace_is_ignored(self):
        self.assertIn("node_id", json.loads(self.server().answer(b"  describe \r")))

    def test_health_is_cached_for_the_cache_window_only(self):
        now = {"t": 100.0}
        server = self.server(clock=lambda: now["t"], cache=2.0)
        with unittest.mock.patch.object(agent, "health", wraps=agent.health) as probe:
            first = server.answer(b"health")
            now["t"] = 101.9
            self.assertEqual(server.answer(b"health"), first)
            self.assertEqual(probe.call_count, 1)
            now["t"] = 102.0
            server.answer(b"health")
            self.assertEqual(probe.call_count, 2)

    def test_a_zero_cache_never_reuses_a_report(self):
        server = self.server(clock=lambda: 5.0, cache=0)
        with unittest.mock.patch.object(agent, "health", wraps=agent.health) as probe:
            server.answer(b"health")
            server.answer(b"health")
        self.assertEqual(probe.call_count, 2)

    def test_describe_is_never_cached(self):
        server = self.server(clock=lambda: 1.0)
        with unittest.mock.patch.object(agent, "describe", wraps=agent.describe) as ask:
            server.answer(b"describe")
            server.answer(b"describe")
        self.assertEqual(ask.call_count, 2)

    def test_the_answer_is_one_line_of_sorted_compact_json(self):
        line = self.server().answer(b"health")
        self.assertEqual(line.count("\n"), 1)
        self.assertEqual(line.strip(), json.dumps(json.loads(line), sort_keys=True, separators=(",", ":")))

    def test_a_request_is_read_up_to_the_newline_and_no_further(self):
        class Conn:
            def __init__(self, chunks):
                self.chunks = list(chunks)

            def recv(self, _n):
                return self.chunks.pop(0) if self.chunks else b""

        self.assertEqual(LocalSocketServer._read_request(Conn([b"hea", b"lth\nrest"])), b"health")
        self.assertEqual(LocalSocketServer._read_request(Conn([b"half"])), b"half")
        self.assertEqual(LocalSocketServer._read_request(Conn([])), b"")

    def test_a_request_longer_than_the_limit_is_refused(self):
        class Conn:
            def recv(self, _n):
                return b"x" * (agent.MAX_REQUEST_BYTES + 1)

        with self.assertRaises(ValueError):
            LocalSocketServer._read_request(Conn())

    def test_start_refuses_a_missing_folder_and_a_system_without_unix_sockets(self):
        server = LocalSocketServer(valid_config(), path="/no/such/folder/a.sock")
        if hasattr(agent.socket, "AF_UNIX"):
            with self.assertRaises(ValueError) as caught:
                server.start()
            self.assertIn("does not exist", str(caught.exception))
        with unittest.mock.patch.object(agent, "socket", spec=[]):
            with self.assertRaises(ValueError) as caught:
                server.start()
        self.assertIn("no UNIX sockets", str(caught.exception))

    def test_close_without_start_is_harmless(self):
        self.server().close()


class ConfigFuzzTests(unittest.TestCase):
    """Whatever JSON arrives, the loader answers with a config or a ValueError - never another exception."""

    ATOMS = [None, True, False, 0, -1, 1, 1.5, 80, 2**40, float("inf"), float("nan"), "", " ", "0660", "/run/a.sock", "a b", "..", "x" * 130, [], {}, [1], ["ssh"]]

    def random_value(self, rng, depth=0):
        roll = rng.random()
        if depth < 2 and roll < 0.2:
            return {rng.choice(["id", "profile", "enabled", "path", "mode", "units", "timeout_seconds", "junk"]): self.random_value(rng, depth + 1) for _ in range(rng.randint(0, 3))}
        if depth < 2 and roll < 0.3:
            return [self.random_value(rng, depth + 1) for _ in range(rng.randint(0, 3))]
        return rng.choice(self.ATOMS)

    def test_random_mutations_of_a_valid_config_never_raise_anything_but_value_error(self):
        rng = random.Random(20260101)
        survivors = 0
        with tempfile.TemporaryDirectory() as tmp:
            for index in range(400):
                config = valid_config(minimum_free_bytes=1000, probes={"enabled": True, "units": ["ssh"]}, local_socket={"enabled": True, "mode": "0660"})
                config["node"]["id"] = "n1"
                target = rng.choice([config, config["node"], config["diagnostics"], config["diagnostics"]["probes"], config["diagnostics"]["local_socket"]])
                key = rng.choice(list(target) + ["extra", "schema_version", "minimum_free_bytes", "maximum_temperature_celsius"])
                target[key] = self.random_value(rng)
                path = write_json(tmp, f"f{index}.json", json.dumps(config))
                try:
                    loaded = load_config(path)
                except ValueError:
                    continue
                survivors += 1
                self.assertEqual(loaded["schema_version"], "1.0")
                self.assertGreaterEqual(loaded["diagnostics"]["minimum_free_bytes"], 0)
                self.assertTrue(math.isfinite(loaded["diagnostics"]["maximum_temperature_celsius"]))
        self.assertGreater(survivors, 0)

    def test_random_bytes_as_a_config_file_never_crash_the_loader(self):
        rng = random.Random(7)
        with tempfile.TemporaryDirectory() as tmp:
            for index in range(60):
                payload = bytes(rng.randrange(256) for _ in range(rng.randint(0, 80)))
                path = Path(tmp) / f"r{index}.json"
                path.write_bytes(payload)
                try:
                    load_config(path)
                except (ValueError, UnicodeDecodeError):
                    pass


if __name__ == "__main__":
    unittest.main()
