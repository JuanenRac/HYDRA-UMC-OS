#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - Service registry in the installers verification
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The installers and the runtime check read the port, the health route and the systemd unit of a service from
provisioning/ports.yaml (a copy of HYDRA-UMC-SDK/contracts/ports.yaml). Static and dry-run checks only: nothing is
installed, no root is needed, and the runtime check runs against stubs of `systemctl` and `curl`."""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROVISIONING = ROOT / "provisioning"
REGISTRY = PROVISIONING / "ports.yaml"
HELPER = PROVISIONING / "service_registry.sh"
RUNTIME = PROVISIONING / "verify_cm5_runtime.sh"
BASH = shutil.which("bash")

# Installers whose project is not a service of the registry: the base system, the kiosk, the splash, the Wi-Fi setup
# page, the local agent (its own unit, not a project of the family), a command-line tool and a unit template per camera.
NOT_REGISTRY_SERVICES = frozenset({
    "install_cm5_base.sh", "install_kiosk.sh", "install_local_agent.sh", "install_local_technician.sh",
    "install_node_healing.sh", "install_splashscreen.sh", "install_vision_streamer.sh", "install_wifi_provision.sh",
})


def registry() -> dict[str, dict[str, str | None]]:
    services: dict[str, dict[str, str | None]] = {}
    current = ""
    for line in REGISTRY.read_text(encoding="utf-8").splitlines():
        line = line.rstrip()
        if not line or line.startswith("#") or line == "services:":
            continue
        key, _, value = line.strip().lstrip("- ").partition(": ")
        if line.lstrip().startswith("- "):
            current = value
            services[current] = {}
        else:
            services[current][key] = None if value == "null" else value
    return services


def posix(path: Path) -> str:
    """The path as bash writes it: `C:/x` becomes `/c/x` under Git Bash, other systems keep it."""
    return re.sub(r"^([A-Za-z]):", lambda match: "/" + match.group(1).lower(), path.as_posix()) if os.name == "nt" else path.as_posix()


def bash(script: str, env: dict[str, str] | None = None, argv0: Path | None = None) -> subprocess.CompletedProcess[str]:
    command = [BASH, "-c", script] + ([posix(argv0)] if argv0 else [])
    return subprocess.run(command, capture_output=True, text=True, check=False, env={**os.environ, **(env or {})})


@unittest.skipUnless(BASH, "bash is needed")
class RegistryHelperTests(unittest.TestCase):
    def test_the_helper_has_valid_syntax(self) -> None:
        self.assertEqual(subprocess.run([BASH, "-n", HELPER.as_posix()], capture_output=True, text=True).returncode, 0)

    def test_service_field_agrees_with_the_registry_for_every_service(self) -> None:
        for name, fields in registry().items():
            for key, value in fields.items():
                with self.subTest(service=name, field=key):
                    result = bash(f'source "{HELPER.as_posix()}"; service_field {name} {key}')
                    if value is None:
                        self.assertEqual((result.returncode, result.stdout), (1, ""))
                    else:
                        self.assertEqual((result.returncode, result.stdout.strip()), (0, value))

    def test_registry_services_lists_every_service(self) -> None:
        result = bash(f'source "{HELPER.as_posix()}"; registry_services')
        self.assertEqual(result.stdout.split(), list(registry()))

    def test_an_unknown_service_or_a_missing_registry_is_a_quiet_failure(self) -> None:
        self.assertEqual(bash(f'source "{HELPER.as_posix()}"; service_field HYDRA-UMC-NOT-THERE port').returncode, 1)
        missing = bash(f'source "{HELPER.as_posix()}"; service_field HYDRA-UMC-SERVER port', env={"HYDRA_UMC_PORTS_REGISTRY": "/nonexistent/ports.yaml"})
        self.assertEqual(missing.returncode, 1)

    def test_announce_health_says_where_to_look(self) -> None:
        with_health = bash(f'source "{HELPER.as_posix()}"; announce_health HYDRA-UMC-ORCHESTRATOR')
        self.assertEqual(with_health.returncode, 0)
        self.assertIn("curl --fail http://127.0.0.1:8114/health", with_health.stdout)
        without = bash(f'source "{HELPER.as_posix()}"; announce_health HYDRA-UMC-MQTT-BROKER')
        self.assertIn("port 1883", without.stdout)
        self.assertIn("no HTTP route", without.stdout)
        unknown = bash(f'source "{HELPER.as_posix()}"; announce_health HYDRA-UMC-NOT-THERE')
        self.assertEqual(unknown.returncode, 0)
        self.assertIn("not in the service registry", unknown.stderr)


class InstallerTests(unittest.TestCase):
    def installers(self) -> list[Path]:
        return sorted(PROVISIONING.glob("install_*.sh"))

    def test_every_installer_of_a_registry_service_announces_its_health_route(self) -> None:
        names = set(registry())
        for script in self.installers():
            text = script.read_text(encoding="utf-8")
            with self.subTest(script=script.name):
                if script.name in NOT_REGISTRY_SERVICES:
                    self.assertNotIn("announce_health", text, "an installer of something outside the registry names no service")
                    continue
                self.assertIn('source "$(dirname "$0")/service_registry.sh"', text)
                announced = set(re.findall(r"announce_health\s+(HYDRA-UMC-[A-Z0-9-]+)", text))
                if script.name == "install_industrial_gateway.sh":
                    announced = set(re.findall(r"for service in ([A-Z0-9 -]+); do", text)[0].split())
                self.assertTrue(announced, "it names no service")
                self.assertTrue(announced <= names, f"names a service that is not in the registry: {sorted(announced - names)}")

    def test_the_service_each_installer_installs_is_the_one_it_announces(self) -> None:
        for script in self.installers():
            if script.name in NOT_REGISTRY_SERVICES or script.name == "install_industrial_gateway.sh":
                continue
            text = script.read_text(encoding="utf-8")
            source = re.search(r'SOURCE="\$ROOT/(HYDRA-UMC-[A-Z0-9-]+)"', text)
            with self.subTest(script=script.name):
                self.assertIsNotNone(source)
                self.assertIn(f"announce_health {source.group(1)}", text)

    def test_every_unit_an_installer_installs_is_the_unit_of_the_registry(self) -> None:
        services = registry()
        for script in self.installers():
            if script.name in NOT_REGISTRY_SERVICES or script.name == "install_industrial_gateway.sh":
                continue
            text = script.read_text(encoding="utf-8")
            name = re.search(r"announce_health (HYDRA-UMC-[A-Z0-9-]+)", text).group(1)
            unit = services[name]["systemd_unit"]
            with self.subTest(script=script.name):
                if unit is not None:
                    self.assertIn(unit, text, "the installer does not install the unit the registry names")

    def test_the_installers_still_have_valid_syntax(self) -> None:
        if not BASH:
            self.skipTest("bash is needed")
        for script in self.installers():
            with self.subTest(script=script.name):
                self.assertEqual(subprocess.run([BASH, "-n", script.as_posix()], capture_output=True, text=True).returncode, 0)


class RegistryContentTests(unittest.TestCase):
    def test_every_service_that_serves_http_declares_its_route(self) -> None:
        # Only a message broker and a binary protocol server have no HTTP route on the port of the registry.
        without = sorted(name for name, fields in registry().items() if fields["health_path"] is None)
        self.assertEqual(without, ["HYDRA-UMC-MQTT-BROKER", "HYDRA-UMC-OPCUA-SERVER"])

    def test_the_copy_is_the_one_of_the_sdk_when_it_is_checked_out(self) -> None:
        sdk = ROOT.parent / "HYDRA-UMC-SDK" / "contracts" / "ports.yaml"
        if not sdk.is_file():
            self.skipTest("the sibling HYDRA-UMC-SDK checkout is not present")
        self.assertEqual(REGISTRY.read_bytes().replace(b"\r\n", b"\n"), sdk.read_bytes().replace(b"\r\n", b"\n"))


@unittest.skipUnless(BASH, "bash is needed")
class RuntimeCheckTests(unittest.TestCase):
    """verify_cm5_runtime.sh --with-services against stubs of systemctl and curl."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.stubs = Path(self._tmp.name)

    def stub(self, name: str, body: str) -> None:
        path = self.stubs / name
        path.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IEXEC)

    def run_check(self, active: str, failing: str = "") -> subprocess.CompletedProcess[str]:
        # `systemctl is-active --quiet UNIT` succeeds for the units in $ACTIVE; `curl` fails for the URLs in $FAILING
        self.stub("systemctl", 'for unit in $ACTIVE; do [[ "$3" == "$unit" ]] && exit 0; done; exit 3\n')
        self.stub("curl", 'for url in $FAILING; do [[ "${@: -1}" == *"$url" ]] && exit 22; done; echo "{}"; exit 0\n')
        # the other checks of the script need an agent; only the service part is looked at
        script = (
            f'export PATH="{posix(self.stubs)}:$PATH"; export ACTIVE="{active}" FAILING="{failing}"; '
            f'source "{HELPER.as_posix()}"; '
            + RUNTIME.read_text(encoding="utf-8")
            .split("# Every service of the registry that is running answers on its health route.", 1)[1]
            .split("if (( failures > 0 )); then", 1)[0]
            .join(['failures=0\ncheck_test() { if eval "$1"; then echo "RUNTIME_CHECK=PASS $2"; else echo "RUNTIME_CHECK=FAIL $2" >&2; failures=$((failures + 1)); fi; }\nWITH_SERVICES=true\n# ', '\necho "failures=$failures"\n'])
        )
        return bash(script, argv0=RUNTIME)

    def test_the_option_and_its_block_exist_in_the_script(self) -> None:
        text = RUNTIME.read_text(encoding="utf-8")
        self.assertIn("--with-services) WITH_SERVICES=true", text)
        self.assertIn("registry_services", text)
        self.assertEqual(subprocess.run([BASH, "-n", RUNTIME.as_posix()], capture_output=True, text=True).returncode, 0)

    def test_a_running_service_that_answers_passes_and_one_that_does_not_run_is_skipped(self) -> None:
        result = self.run_check(active="hydra-umc-orchestrator.service")
        self.assertIn("RUNTIME_CHECK=PASS HYDRA-UMC-ORCHESTRATOR answers on /health", result.stdout)
        self.assertIn("RUNTIME_CHECK=SKIP HYDRA-UMC-SWARM-SYNC is not running", result.stdout)
        self.assertIn("failures=0", result.stdout)

    def test_a_running_service_that_does_not_answer_fails(self) -> None:
        result = self.run_check(active="hydra-umc-orchestrator.service hydra-umc-twin.service", failing=":8114/health")
        self.assertIn("RUNTIME_CHECK=FAIL HYDRA-UMC-ORCHESTRATOR answers on /health", result.stderr)
        self.assertIn("RUNTIME_CHECK=PASS HYDRA-UMC-TWIN answers on /stats", result.stdout)
        self.assertIn("failures=1", result.stdout)

    def test_a_stack_without_a_unit_and_a_service_without_a_route_are_skipped(self) -> None:
        result = self.run_check(active="")
        self.assertIn("RUNTIME_CHECK=SKIP HYDRA-UMC-MQTT-BROKER has no systemd unit", result.stdout)
        self.assertIn("failures=0", result.stdout)


if __name__ == "__main__":
    unittest.main()
