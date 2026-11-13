# =============================================================================
# HYDRA-UMC-OS - Simulation bench: the real agent against a simulated CM5
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The real agent code reads its health from a simulated Compute Module 5.

The twin below stands in for everything the agent touches on a device: the thermal
sensor, the free space, the network interfaces, `vcgencmd get_throttled` and
`systemctl is-active`. Scenarios (a warm-up, a brown-out, a disk that fills, a cable
that is pulled, a service that dies, tools that are missing or hang) drive the agent
through its states, and a seeded random timeline checks the rules that must always
hold. It proves the logic and the failure paths of the agent; it says nothing about a
real board, a real sensor or real timing.
"""

import copy
import json
import random
import subprocess
import unittest

from hydra_umc_os import agent
from hydra_umc_os.agent import DEFAULT_CONFIG, ReportGate, health

GIB = 1024**3
SEVERITY = {"PASS": 0, "WARN": 1, "FAIL": 2}


class SimulatedCM5:
    """A device whose readings are set by the scenario, and the two tools the agent may start."""

    def __init__(self):
        self.temperature = 45.0  # None = the sensor is gone
        self.free_bytes = 20 * GIB
        self.interfaces = ["eth0", "wlan0"]
        self.throttled = 0x0  # the bits of vcgencmd get_throttled
        self.units = {"hydra-umc-agent.service": "active", "mosquitto.service": "active"}
        self.missing_tools = set()
        self.hanging_tools = set()
        self.started = []

    def run(self, argv, **kwargs):
        self.started.append(list(argv))
        tool = argv[0]
        if tool in self.hanging_tools:
            raise subprocess.TimeoutExpired(tool, kwargs["timeout"])
        if tool in self.missing_tools:
            raise FileNotFoundError(tool)
        if tool == "vcgencmd" and argv[1:] == ["get_throttled"]:
            return subprocess.CompletedProcess(argv, 0, stdout=f"throttled=0x{self.throttled:x}\n", stderr="")
        if tool == "systemctl" and argv[1] == "is-active":
            word = self.units.get(argv[2], "inactive")
            return subprocess.CompletedProcess(argv, 0 if word == "active" else 3, stdout=word + "\n", stderr="")
        raise AssertionError(f"the agent started something it should not: {argv}")

    def observe(self, config):
        return health(
            config,
            free_bytes=self.free_bytes,
            interfaces=list(self.interfaces),
            temperature_celsius=self.temperature,
            probe_run=self.run,
        )


def config_for_bench(**probes):
    config = copy.deepcopy(DEFAULT_CONFIG)
    config["diagnostics"]["probes"] = {"enabled": True, "units": ["hydra-umc-agent.service", "mosquitto.service"], **probes}
    return config


class WarmUpTests(unittest.TestCase):
    def test_a_slow_warm_up_walks_ready_then_fault_exactly_at_the_limit(self):
        board = SimulatedCM5()
        config = config_for_bench()
        states = []
        for tenth in range(400, 1001, 5):  # 40.0 C to 100.0 C
            board.temperature = tenth / 10
            states.append((board.temperature, board.observe(config).state))
        for temperature, state in states:
            self.assertEqual(state, "FAULT" if temperature >= 80.0 else "READY", temperature)

    def test_a_cool_down_recovers_without_a_restart(self):
        board = SimulatedCM5()
        config = config_for_bench()
        board.temperature = 85.0
        self.assertEqual(board.observe(config).state, "FAULT")
        board.temperature = 60.0
        self.assertEqual(board.observe(config).state, "READY")

    def test_a_dead_sensor_degrades_and_is_never_reported_as_ready(self):
        board = SimulatedCM5()
        board.temperature = None
        report = board.observe(config_for_bench())
        self.assertEqual(report.state, "DEGRADED")
        self.assertEqual(report.checks["temperature"]["state"], "WARN")


class BrownOutTests(unittest.TestCase):
    def test_a_brown_out_faults_now_and_leaves_a_warning_after_the_boot_flag_is_all_that_remains(self):
        board = SimulatedCM5()
        config = config_for_bench()
        self.assertEqual(board.observe(config).checks["throttling"]["state"], "PASS")
        board.throttled = 0x50005  # under-voltage and throttled, now and since the boot
        report = board.observe(config)
        self.assertEqual(report.state, "FAULT")
        self.assertEqual(sorted(report.checks["throttling"]["now"]), ["throttled", "under-voltage"])
        board.throttled = 0x50000  # the supply recovered; the flags since the boot stay
        report = board.observe(config)
        self.assertEqual(report.state, "DEGRADED")
        self.assertEqual(report.checks["throttling"]["now"], [])

    def test_a_frequency_cap_alone_is_a_warning(self):
        board = SimulatedCM5()
        board.throttled = 0x2
        self.assertEqual(board.observe(config_for_bench()).state, "DEGRADED")


class StorageAndNetworkTests(unittest.TestCase):
    def test_a_filling_disk_faults_exactly_when_it_crosses_the_minimum(self):
        board = SimulatedCM5()
        config = config_for_bench()
        minimum = config["diagnostics"]["minimum_free_bytes"]
        seen = []
        for free in range(3 * GIB, 0, -256 * 1024 * 1024):
            board.free_bytes = free
            seen.append((free, board.observe(config).state))
        for free, state in seen:
            self.assertEqual(state, "READY" if free >= minimum else "FAULT", free)

    def test_a_pulled_cable_and_a_lost_wifi_degrade_then_the_return_recovers(self):
        board = SimulatedCM5()
        config = config_for_bench()
        board.interfaces = ["wlan0"]
        self.assertEqual(board.observe(config).state, "READY")
        board.interfaces = []
        self.assertEqual(board.observe(config).state, "DEGRADED")
        board.interfaces = ["eth0"]
        self.assertEqual(board.observe(config).state, "READY")


class ServiceTests(unittest.TestCase):
    def test_a_dead_unit_faults_and_an_inactive_one_warns(self):
        board = SimulatedCM5()
        config = config_for_bench()
        board.units["mosquitto.service"] = "failed"
        report = board.observe(config)
        self.assertEqual(report.state, "FAULT")
        self.assertEqual(report.checks["unit:mosquitto.service"]["state"], "FAIL")
        board.units["mosquitto.service"] = "inactive"
        report = board.observe(config)
        self.assertEqual(report.state, "DEGRADED")
        board.units["mosquitto.service"] = "active"
        self.assertEqual(board.observe(config).state, "READY")

    def test_an_unknown_unit_is_a_warning_not_a_pass(self):
        board = SimulatedCM5()
        config = config_for_bench(units=["nothing.service"])
        self.assertEqual(board.observe(config).checks["unit:nothing.service"]["state"], "WARN")

    def test_missing_and_hanging_tools_degrade_and_name_the_reason(self):
        board = SimulatedCM5()
        config = config_for_bench(timeout_seconds=3)
        board.missing_tools = {"vcgencmd"}
        board.hanging_tools = {"systemctl"}
        report = board.observe(config)
        self.assertEqual(report.state, "DEGRADED")
        self.assertIn("not installed", report.checks["throttling"]["reason"])
        self.assertIn("did not answer in 3 s", report.checks["unit:hydra-umc-agent.service"]["reason"])

    def test_the_agent_only_ever_starts_the_two_read_only_queries(self):
        board = SimulatedCM5()
        config = config_for_bench()
        for step in range(30):
            board.temperature = 30 + step * 2
            board.observe(config)
        allowed = {("vcgencmd", "get_throttled"), ("systemctl", "is-active")}
        self.assertTrue(board.started)
        for argv in board.started:
            self.assertIn((argv[0], argv[1]), allowed)

    def test_probes_stay_off_unless_the_operator_turns_them_on(self):
        board = SimulatedCM5()
        config = copy.deepcopy(DEFAULT_CONFIG)
        config["diagnostics"]["probes"] = {"enabled": False, "units": ["x.service"]}
        report = board.observe(config)
        self.assertEqual(board.started, [])
        self.assertNotIn("throttling", report.checks)


class JournalQuietTests(unittest.TestCase):
    def test_a_quiet_day_writes_the_heartbeat_only_and_a_fault_is_written_at_once(self):
        board = SimulatedCM5()
        config = config_for_bench()
        gate = ReportGate(True, 300.0)
        written = []
        for second in range(0, 1200, 30):
            if second == 600:
                board.free_bytes = 100 * 1024 * 1024
            if second == 900:
                board.free_bytes = 20 * GIB
            report = board.observe(config)
            if gate.should_emit(report, float(second)):
                written.append((second, report.state))
        self.assertEqual(written, [(0, "READY"), (300, "READY"), (600, "FAULT"), (900, "READY")])
        # 40 reports were produced; far fewer reached the journal


class RandomTimelineTests(unittest.TestCase):
    """Whatever the device does, the rules of the agent hold on every step."""

    def test_the_overall_state_is_always_the_worst_check_and_the_report_is_plain_json(self):
        rng = random.Random(20261113)
        board = SimulatedCM5()
        config = config_for_bench()
        previous_session = None
        for _ in range(600):
            board.temperature = rng.choice([None, rng.uniform(-10, 120)])
            board.free_bytes = rng.choice([0, rng.randrange(0, 4 * GIB), 50 * GIB])
            board.interfaces = rng.choice([[], ["eth0"], ["eth0", "wlan0", "can0"]])
            board.throttled = rng.choice([0x0, 0x1, 0x2, 0x4, 0x8, 0x50000, 0x50005, 0x80008, rng.randrange(0, 1 << 20)])
            board.units["mosquitto.service"] = rng.choice(["active", "failed", "inactive", "activating"])
            board.missing_tools = set(rng.sample(["vcgencmd", "systemctl"], rng.randint(0, 2)))
            board.hanging_tools = set(rng.sample(["vcgencmd", "systemctl"], rng.randint(0, 1)))
            report = board.observe(config)
            worst = max(SEVERITY[check["state"]] for check in report.checks.values())
            self.assertEqual(report.state, {0: "READY", 1: "DEGRADED", 2: "FAULT"}[worst])
            for check in report.checks.values():
                self.assertIn(check["state"], SEVERITY)
            json.dumps(agent.asdict(report))
            if previous_session is not None:
                self.assertEqual(report.boot_session_id, previous_session)
            previous_session = report.boot_session_id

    def test_a_missing_tool_is_never_reported_as_a_pass(self):
        rng = random.Random(5)
        board = SimulatedCM5()
        config = config_for_bench()
        for _ in range(100):
            board.missing_tools = {"vcgencmd", "systemctl"}
            board.throttled = rng.randrange(0, 1 << 20)
            report = board.observe(config)
            self.assertEqual(report.checks["throttling"]["state"], "WARN")
            for name, check in report.checks.items():
                if name.startswith("unit:"):
                    self.assertEqual(check["state"], "WARN")


if __name__ == "__main__":
    unittest.main()
