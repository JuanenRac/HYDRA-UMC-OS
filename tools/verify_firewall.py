#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - Host firewall rules verification
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Prove the rules provisioning/hydra_firewall.sh prints and what it refuses. Only `print` and `check` are used: nothing is loaded, no root is needed and nothing changes. When `nft`
is installed and usable, it also checks that nftables accepts the rules."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = (ROOT / "provisioning" / "hydra_firewall.sh").as_posix()
BASH = shutil.which("bash")


def firewall(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([BASH, SCRIPT, *arguments], capture_output=True, text=True, check=False)


def rules(*arguments: str) -> str:
    result = firewall("print", *arguments)
    assert result.returncode == 0, result.stderr
    return result.stdout


@unittest.skipUnless(BASH, "bash is needed")
class FirewallTests(unittest.TestCase):
    def test_standard_rules_close_the_broker_to_everything_but_the_field(self) -> None:
        text = rules("--field", "192.168.0.0/24", "--clients", "192.168.10.0/24", "--clients", "10.8.0.0/24")
        for expected in ("table inet hydra_core {", "policy accept;", 'iifname "lo" accept', "ct state established,related accept",
                         "tcp dport { 1883, 8883 } ip saddr { 192.168.0.0/24 } accept", "tcp dport { 1883, 8883 } counter drop",
                         "tcp dport { 3000 } ip saddr { 192.168.10.0/24,10.8.0.0/24 } accept", "tcp dport { 3000 } counter drop"):
            self.assertIn(expected, text)

    def test_it_never_takes_over_the_machine(self) -> None:
        text = rules("--field", "192.168.0.0/24", "--clients", "192.168.10.0/24")
        self.assertNotIn("policy drop", text)
        self.assertNotIn("dport 22", text)
        ports = set()
        for line in text.splitlines():
            if "dport" in line and not line.strip().startswith("#"):
                ports.update(re.findall(r"\d+", re.search(r"dport \{([^}]*)\}", line).group(1)))  # type: ignore[union-attr]
        self.assertEqual(ports, {"1883", "8883", "3000"})
        self.assertEqual(sum(1 for line in text.splitlines() if "dport" in line and not line.strip().startswith("#")), 4)

    def test_without_clients_only_the_broker_is_closed(self) -> None:
        text = rules("--field", "192.168.0.0/24")
        self.assertIn("tcp dport { 1883, 8883 } counter drop", text)
        self.assertNotIn("tcp dport { 3000 }", text)

    def test_other_ports_networks_and_interfaces(self) -> None:
        text = rules("--field", "192.168.0.0/24", "--field", "172.16.5.0/28", "--mqtt-port", "21883", "--mqtt-tls-port", "28883", "--server-port", "23000", "--studio-port", "23001",
                     "--clients", "10.0.0.0/8", "--trust-iface", "docker0")
        for expected in ("tcp dport { 21883, 28883 } ip saddr { 192.168.0.0/24,172.16.5.0/28 } accept", "tcp dport { 23000, 23001 } ip saddr { 10.0.0.0/8 } accept", 'iifname "docker0" accept'):
            self.assertIn(expected, text)
        self.assertNotIn("1883, 8883", text)
        self.assertIn("ip saddr { 192.168.0.50 } accept", rules("--field", "192.168.0.50"))

    def test_bad_input_is_refused_and_nothing_is_printed_as_rules(self) -> None:
        refused = [
            [], ["print"], ["print", "--clients", "192.168.10.0/24"], ["print", "--field", "192.168.0.0/33"], ["print", "--field", "300.1.1.0/24"], ["print", "--field", "192.168.0.0/24/8"],
            ["print", "--field", "192.168.0.0/24; drop"], ["print", "--field", "192.168.0.0/24", "--clients", "not-a-network"], ["print", "--field", "192.168.0.0/24", "--mqtt-port", "0"],
            ["print", "--field", "192.168.0.0/24", "--mqtt-port", "70000"], ["print", "--field", "192.168.0.0/24", "--mqtt-port", "3000"],
            ["print", "--field", "192.168.0.0/24", "--mqtt-tls-port", "1883"], ["print", "--field", "192.168.0.0/24", "--studio-port", "3000"],
            ["print", "--field", "192.168.0.0/24", "--trust-iface", "eth0; flush ruleset"], ["print", "--field", "192.168.0.0/24", "--table", "a b"],
            ["print", "--field", "192.168.0.0/24", "--unknown"], ["frobnicate"], ["apply", "--field", "192.168.0.0/24", "--rollback-after", "3"],
        ]
        for arguments in refused:
            with self.subTest(arguments=arguments):
                result = firewall(*arguments)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertNotIn("table inet", result.stdout)

    def test_nft_accepts_the_rules_when_it_can_check_them(self) -> None:
        result = firewall("check", "--field", "192.168.0.0/24", "--clients", "192.168.10.0/24")
        text = result.stdout + result.stderr
        if "FIREWALL_CHECK=SKIP" in text or re.search(r"operation not permitted|permission denied|must be root|netlink", text, re.I):
            self.skipTest("nft is not installed or not usable here")
        self.assertIn("FIREWALL_CHECK=PASS", text)


def main() -> int:
    if not BASH:
        print("FIREWALL_VERIFY=SKIPPED bash is not available on this host")
        return 0
    result = unittest.main(module=__name__, exit=False, verbosity=1).result
    if result.wasSuccessful():
        print(f"FIREWALL_VERIFY=PASS tests={result.testsRun} skipped={len(result.skipped)}")
        return 0
    print("FIREWALL_VERIFY=FAIL", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
