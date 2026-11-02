#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - Installed-tree deployment check
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Prove tools/deploy_tree.py and provisioning/deploy_lib.sh in temporary folders, with no systemd and no root: the program installed now is kept, a unit that is not running is never
restarted, a restart or a health check that fails puts the earlier program back and leaves the folders that hold state alone, the same program is not kept twice, a rollback goes back,
and the shell steps of an installer do all of that through a fake `systemctl` and a real local HTTP route."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


dt = load("deploy_tree")
dr = dt.dr
_cli_spec = importlib.util.spec_from_file_location("hydra_umc_os_cli", ROOT / "provisioning" / "hydra_umc_os.py")
assert _cli_spec and _cli_spec.loader
cli = importlib.util.module_from_spec(_cli_spec)
sys.modules["hydra_umc_os_cli"] = cli
_cli_spec.loader.exec_module(cli)
PY = f'"{sys.executable}"' if os.name == "nt" else sys.executable


class Answer(BaseHTTPRequestHandler):
    code = 200

    def do_GET(self) -> None:  # noqa: N802 - the name the standard library calls
        if self.path == "/moved":
            self.send_response(302)
            self.send_header("Location", "http://127.0.0.1:1/")
            self.end_headers()
            return
        self.send_response(type(self).code)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *args) -> None:  # silence the test output
        pass


def serve(code: int = 200) -> tuple[HTTPServer, str]:
    handler = type("H", (Answer,), {"code": code})
    server = HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


class TreeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "releases"
        self.target = self.base / "opt" / "server"
        self.log = self.base / "restarts.log"
        self.settings = {**dt.dr.DEFAULTS, **dt.TREE_DEFAULTS, "healthTimeoutS": 0.3, "healthIntervalS": 0.05,
                         "restartCommand": f'{PY} -c "open(r\'{self.log}\', \'a\').write(\'{{version}}\\n\')"'}
        self.running = True
        self.healthy_now = True

    def program(self, version: str, *, extra: str | None = None) -> None:
        """What an installer leaves in the target: the program, its manifest and, kept apart, the state of the service."""
        for name in ("src", "dist"):
            shutil.rmtree(self.target / name, ignore_errors=True)
        (self.target / "src").mkdir(parents=True)
        (self.target / "src" / "main.py").write_text(f"print('{version}')", encoding="utf-8")
        (self.target / "hydra-umc.project.json").write_text(json.dumps({"version": version}), encoding="utf-8")
        if extra:
            (self.target / extra).write_text("only in this release", encoding="utf-8")

    def state_files(self) -> None:
        (self.target / "data").mkdir(exist_ok=True)
        (self.target / "data" / "db.sqlite").write_text("rows", encoding="utf-8")

    def settle(self, *, unit: str | None = "hydra-umc-server.service", url: str | None = "http://127.0.0.1:1/health", **extra):
        return dt.settle(self.root, "server", self.target, unit=unit, health_url=url, settings=self.settings, sleep=lambda _s: None,
                         is_active=lambda _u: self.running, probe=lambda _u: self.healthy_now, **extra)

    def deploy(self, version: str, **kwargs):
        dt.begin(self.root, "server", self.target)
        self.program(version, extra=kwargs.pop("extra", None))
        return self.settle(**kwargs)

    def restarts(self) -> list[str]:
        return self.log.read_text(encoding="utf-8").split() if self.log.exists() else []

    # ---- what is kept ---------------------------------------------------------------------------------------------------------------

    def test_a_first_installation_keeps_the_program_and_has_nothing_before_it(self) -> None:
        self.running = False
        state = self.deploy("0.1.0")
        self.assertEqual((state["result"], state["current"]["version"], state["previous"]), ("installed", "0.1.0", None))
        self.assertEqual(self.restarts(), [])
        kept = self.root / "server" / "releases" / state["current"]["release"]
        self.assertEqual((kept / "src" / "main.py").read_text(encoding="utf-8"), "print('0.1.0')")

    def test_the_state_folders_are_never_kept_or_touched(self) -> None:
        self.program("0.1.0")
        self.state_files()
        state = self.deploy("0.1.1")
        kept = self.root / "server" / "releases" / state["previous"]["release"]
        self.assertFalse((kept / "data").exists())
        self.assertEqual((self.target / "data" / "db.sqlite").read_text(encoding="utf-8"), "rows")

    def test_the_same_program_is_not_kept_twice(self) -> None:
        self.deploy("0.1.0")
        dt.begin(self.root, "server", self.target)
        self.assertEqual(self.settle()["result"], "unchanged")
        self.assertEqual(len(list((self.root / "server" / "releases").iterdir())), 1)

    def test_begin_reuses_the_release_in_use_instead_of_copying_it_again(self) -> None:
        self.deploy("0.1.0")
        state = dt.begin(self.root, "server", self.target)
        self.assertEqual(state["pending"]["release"], state["current"]["release"])
        self.assertEqual(len(list((self.root / "server" / "releases").iterdir())), 1)

    # ---- the unit ---------------------------------------------------------------------------------------------------------------------

    def test_a_unit_that_is_not_running_is_never_restarted(self) -> None:
        self.running = False
        self.deploy("0.1.0")
        self.assertEqual(self.deploy("0.1.1")["result"], "installed")
        self.assertEqual(self.restarts(), [])

    def test_a_running_unit_is_restarted_and_checked(self) -> None:
        self.running = False
        self.deploy("0.1.0")
        self.running = True
        state = self.deploy("0.1.1")
        self.assertEqual((state["result"], state["current"]["version"], state["previous"]["version"]), ("deployed", "0.1.1", "0.1.0"))
        self.assertEqual(self.restarts(), ["0.1.1"])

    def test_restart_can_be_switched_off(self) -> None:
        self.running = False
        self.deploy("0.1.0")
        self.running = True
        self.settings["restartOnDeploy"] = False
        self.assertEqual(self.deploy("0.1.1")["result"], "installed-not-restarted")
        self.assertEqual(self.restarts(), [])

    def test_a_health_check_that_fails_puts_the_earlier_program_back_and_restarts_it(self) -> None:
        self.running = False
        self.deploy("0.1.0")
        self.state_files()
        self.running = True
        self.healthy_now = False
        with self.assertRaises(dr.DeployError) as caught:
            self.deploy("0.1.1", extra="new_only.txt")
        self.assertEqual(caught.exception.code, dr.EXIT_ROLLED_BACK)
        self.assertEqual((self.target / "src" / "main.py").read_text(encoding="utf-8"), "print('0.1.0')")
        self.assertEqual(json.loads((self.target / "hydra-umc.project.json").read_text(encoding="utf-8"))["version"], "0.1.0")
        self.assertFalse((self.target / "new_only.txt").exists(), "a file that only the new release had must go")
        self.assertEqual((self.target / "data" / "db.sqlite").read_text(encoding="utf-8"), "rows")
        self.assertEqual(self.restarts(), ["0.1.1", "0.1.0"])
        state = dr.Component(self.root, "server").state()
        self.assertEqual(state["current"]["version"], "0.1.0")
        self.assertEqual(state["history"][-1]["event"], "install-failed")
        self.assertEqual(list(self.target.glob(".restore-*")), [])

    def test_a_restart_that_fails_puts_the_earlier_program_back(self) -> None:
        self.running = False
        self.deploy("0.1.0")
        self.running = True
        self.settings["restartCommand"] = f'{PY} -c "import sys; sys.exit(1)"'
        with self.assertRaises(dr.DeployError) as caught:
            self.deploy("0.1.1")
        self.assertEqual(caught.exception.code, dr.EXIT_ROLLED_BACK)
        self.assertEqual((self.target / "src" / "main.py").read_text(encoding="utf-8"), "print('0.1.0')")

    def test_a_first_program_that_does_not_hold_stays_because_there_is_nothing_to_go_back_to(self) -> None:
        self.healthy_now = False
        with self.assertRaisesRegex(dr.DeployError, "no earlier release"):
            self.deploy("0.1.0")
        self.assertEqual((self.target / "src" / "main.py").read_text(encoding="utf-8"), "print('0.1.0')")

    def test_going_back_can_be_switched_off(self) -> None:
        self.running = False
        self.deploy("0.1.0")
        self.running = True
        self.healthy_now = False
        self.settings["rollbackOnFailure"] = False
        with self.assertRaisesRegex(dr.DeployError, "rollbackOnFailure is off"):
            self.deploy("0.1.1")
        self.assertEqual((self.target / "src" / "main.py").read_text(encoding="utf-8"), "print('0.1.1')")

    def test_a_health_command_of_the_settings_wins_over_the_route(self) -> None:
        self.running = False
        self.deploy("0.1.0")
        self.running = True
        self.settings["healthCommand"] = f'{PY} -c "import sys; sys.exit(1)"'
        with self.assertRaises(dr.DeployError):
            self.deploy("0.1.1")

    def test_a_unit_without_a_route_is_healthy_when_it_runs(self) -> None:
        self.running = False
        self.deploy("0.1.0")
        self.running = True
        self.assertEqual(self.deploy("0.1.1", url=None)["result"], "deployed")

    # ---- the way back by hand -------------------------------------------------------------------------------------------------------------

    def test_rollback_puts_the_previous_program_back_and_a_second_one_returns(self) -> None:
        self.running = False
        self.deploy("0.1.0")
        self.state_files()
        self.deploy("0.1.1")
        back = dt.rollback(self.root, "server", settings=self.settings, sleep=lambda _s: None, is_active=lambda _u: False)
        self.assertEqual((back["result"], back["current"]["version"], back["previous"]["version"]), ("rolled-back", "0.1.0", "0.1.1"))
        self.assertEqual((self.target / "src" / "main.py").read_text(encoding="utf-8"), "print('0.1.0')")
        self.assertEqual((self.target / "data" / "db.sqlite").read_text(encoding="utf-8"), "rows")
        again = dt.rollback(self.root, "server", settings=self.settings, sleep=lambda _s: None, is_active=lambda _u: False)
        self.assertEqual(again["current"]["version"], "0.1.1")

    def test_rollback_with_nothing_before_is_refused(self) -> None:
        self.running = False
        self.deploy("0.1.0")
        with self.assertRaisesRegex(dr.DeployError, "no earlier installed program"):
            dt.rollback(self.root, "server", settings=self.settings)

    def test_pruning_keeps_the_release_in_use_and_the_previous_one(self) -> None:
        self.running = False
        self.settings["keep"] = 2
        for version in ("0.1.0", "0.1.1", "0.1.2", "0.1.3"):
            self.deploy(version)
        names = sorted(p.name for p in (self.root / "server" / "releases").iterdir())
        self.assertEqual(names, ["0.1.2-1", "0.1.3-1"])

    # ---- the pieces --------------------------------------------------------------------------------------------------------------------

    def test_the_digest_follows_the_content_and_not_the_date(self) -> None:
        self.program("0.1.0")
        first = dt.tree_digest(dt.payload(self.target, dt.STATE_DIRS))
        os.utime(self.target / "src" / "main.py", (1, 1))
        self.assertEqual(dt.tree_digest(dt.payload(self.target, dt.STATE_DIRS)), first)
        (self.target / "src" / "main.py").write_text("print('changed')", encoding="utf-8")
        self.assertNotEqual(dt.tree_digest(dt.payload(self.target, dt.STATE_DIRS)), first)

    def test_a_state_folder_name_cannot_be_a_path(self) -> None:
        for text in ("../x", "a/b", "..", "."):
            with self.assertRaises(dr.DeployError):
                dt.state_dirs_of(text)
        self.assertEqual(dt.state_dirs_of(None), dt.STATE_DIRS)

    def test_the_settings_of_this_tool_are_read_and_a_bad_value_is_said(self) -> None:
        self.root.mkdir()
        (self.root / "deploy.json").write_text(json.dumps({"restartOnDeploy": "no", "rollbackOnFailure": False, "keep": 4}), encoding="utf-8")
        warnings: list[str] = []
        settings = dt.load_settings(self.root, warnings.append)
        self.assertEqual((settings["restartOnDeploy"], settings["rollbackOnFailure"], settings["keep"]), (True, False, 4))
        self.assertEqual(len(warnings), 1)

    def test_the_route_must_answer_with_a_2xx_on_this_machine(self) -> None:
        server, url = serve(200)
        self.addCleanup(server.shutdown)
        self.assertTrue(dt.http_ok(url + "/health"))
        self.assertFalse(dt.http_ok(url + "/moved"), "a redirect is not an answer")
        bad, bad_url = serve(503)
        self.addCleanup(bad.shutdown)
        self.assertFalse(dt.http_ok(bad_url + "/health"))
        self.assertFalse(dt.http_ok("http://127.0.0.1:1/health"))
        self.assertFalse(dt.http_ok("http://example.invalid/health"))

    def test_the_command_line_begins_settles_and_reports(self) -> None:
        self.program("0.2.0")
        base = ["--root", str(self.root)]
        self.assertEqual(dt.main([*base, "begin", "server", "--target", str(self.target)]), 0)
        self.program("0.2.1")
        self.assertEqual(dt.main([*base, "settle", "server", "--target", str(self.target)]), 0)
        self.assertEqual(dt.main([*base, "status"]), 0)
        self.assertEqual(dt.main([*base, "rollback", "server"]), 0)
        self.assertEqual((self.target / "src" / "main.py").read_text(encoding="utf-8"), "print('0.2.0')")
        self.assertEqual(dt.main([*base, "settle", "server", "--target", str(self.base / "empty")]), dr.EXIT_REFUSED)


class CommandTests(unittest.TestCase):
    """`hydra-umc-os`: it resolves a project in the table, refuses what does not follow the contract and reports what the installer did."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        row = {"script": "install_twin.sh", "source": "HYDRA-UMC-TWIN", "target": "/opt/hydra-umc/twin", "user": "hydra-umc-twin", "unit": "hydra-umc-twin.service",
               "port": 8111, "health_path": "/health", "contract": 1, "deploy_exempt": None}
        self.write_plan([row, {**row, "script": "install_wifi_provision.sh", "source": None, "target": "/opt/hydra-umc/wifi-provision", "contract": None,
                               "deploy_exempt": "it comes from this repository"}])
        (self.dir / "install_twin.sh").write_text("exit 0\n", encoding="utf-8")

    def write_plan(self, rows: list[dict], supported: int = 1) -> None:
        (self.dir / "install_plan.json").write_text(json.dumps({"format": "hydra-install-plan/2", "supported_contract": supported, "installers": rows}), encoding="utf-8")

    def run_cli(self, *argv: str, runner=None) -> tuple[int, str]:
        import contextlib
        import io

        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = cli.main(["--provisioning-dir", str(self.dir), *argv], runner=runner or subprocess.run)
        return code, out.getvalue()

    def test_a_project_is_found_by_its_repository_its_short_name_or_its_script(self) -> None:
        for name in ("HYDRA-UMC-TWIN", "twin", "install_twin.sh", "Twin"):
            code, out = self.run_cli("plan", name)
            self.assertEqual(code, 0, name)
            self.assertEqual(json.loads(out)["projects"][0]["unit"], "hydra-umc-twin.service")

    def test_without_apply_it_only_says_what_it_would_run(self) -> None:
        calls: list = []
        code, out = self.run_cli("deploy", "twin", runner=lambda *a, **k: calls.append(a))
        report = json.loads(out)
        self.assertEqual((code, report["result"], calls), (0, "dry-run", []))
        self.assertEqual(report["would_run"][-1], "--apply")

    def test_an_unknown_project_and_one_without_the_contract_are_refused(self) -> None:
        for name in ("nothing", "wifi-provision", "install_wifi_provision.sh"):
            code, out = self.run_cli("deploy", name, "--apply")
            self.assertEqual((code, json.loads(out)["result"]), (cli.EXIT_REFUSED, "refused"), name)

    def test_a_contract_this_tool_does_not_support_is_refused_before_anything_runs(self) -> None:
        self.write_plan([{"script": "install_twin.sh", "source": "HYDRA-UMC-TWIN", "target": "/opt/hydra-umc/twin", "contract": 2, "deploy_exempt": None}])
        calls: list = []
        code, out = self.run_cli("deploy", "twin", "--apply", runner=lambda *a, **k: calls.append(a))
        self.assertEqual((code, calls), (cli.EXIT_REFUSED, []))
        self.assertIn("contract 2", json.loads(out)["reason"])

    def test_a_table_that_cannot_be_read_is_refused(self) -> None:
        (self.dir / "install_plan.json").write_text("{nope", encoding="utf-8")
        self.assertEqual(self.run_cli("plan")[0], cli.EXIT_REFUSED)

    def test_the_installer_is_run_with_apply_and_what_it_reports_is_passed_on(self) -> None:
        seen: dict = {}

        def runner(command, env=None, check=False):
            seen["command"] = command
            Path(env["HYDRA_UMC_DEPLOY_RESULT"]).write_text(json.dumps({"result": "deployed", "current": {"version": "0.1.1"}}), encoding="utf-8")
            return subprocess.CompletedProcess(command, 0)

        code, out = self.run_cli("deploy", "HYDRA-UMC-TWIN", "--apply", runner=runner)
        report = json.loads(out)
        self.assertEqual((code, report["result"], report["deploy"]["current"]["version"]), (0, "deployed", "0.1.1"))
        self.assertEqual(seen["command"][-1], "--apply")
        self.assertTrue(seen["command"][-2].endswith("install_twin.sh"))

    def test_a_unit_that_did_not_hold_is_reported_as_rolled_back_with_status_3(self) -> None:
        code, out = self.run_cli("deploy", "twin", "--apply", runner=lambda command, env=None, check=False: subprocess.CompletedProcess(command, 3))
        self.assertEqual((code, json.loads(out)["result"]), (3, "rolled-back"))

    def test_an_installer_that_fails_keeps_its_own_status(self) -> None:
        code, out = self.run_cli("deploy", "twin", "--apply", runner=lambda command, env=None, check=False: subprocess.CompletedProcess(command, 1))
        self.assertEqual((code, json.loads(out)["result"]), (1, "failed"))

    def test_rollback_and_status_call_the_tool_with_the_unit_and_the_route(self) -> None:
        calls: list[list[str]] = []

        def runner(command, check=False):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0)

        self.assertEqual(self.run_cli("rollback", "twin", runner=runner)[0], 0)
        self.assertEqual(self.run_cli("status", "twin", runner=runner)[0], 0)
        self.assertIn("rollback", calls[0])
        self.assertEqual(calls[0][calls[0].index("--unit") + 1], "hydra-umc-twin.service")
        self.assertEqual(calls[0][calls[0].index("--health-url") + 1], "http://127.0.0.1:8111/health")
        self.assertEqual(calls[1][-2:], ["status", "twin"])


@unittest.skipIf(os.name == "nt" or not shutil.which("bash"), "the shell steps need bash and a posix host")
class LibTests(unittest.TestCase):
    """The installer side: `deploy_begin` and `deploy_finish` of provisioning/deploy_lib.sh, with a fake `systemctl` and a real local route."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.target = self.base / "opt" / "hydra-umc" / "twin"
        self.target.mkdir(parents=True)
        self.bin = self.base / "bin"
        self.bin.mkdir()
        self.calls = self.base / "systemctl.log"
        shim = self.bin / "systemctl"
        shim.write_text(f'#!/bin/sh\necho "$@" >> "{self.calls}"\n[ "$1" = is-active ] && [ -f "{self.base}/running" ] && exit 0\n[ "$1" = is-active ] && exit 3\nexit 0\n', encoding="utf-8")
        shim.chmod(0o755)
        (self.base / "running").write_text("", encoding="utf-8")
        self.server, self.url = serve(200)
        self.addCleanup(self.server.shutdown)
        self.port = self.server.server_address[1]
        self.registry = self.base / "ports.yaml"
        self.registry.write_text(f"services:\n  - name: HYDRA-UMC-TWIN\n    port: {self.port}\n    health_path: /health\n    systemd_unit: hydra-umc-twin.service\n", encoding="utf-8")
        self.result = self.base / "result.json"
        (self.base / "releases").mkdir()
        (self.base / "releases" / "deploy.json").write_text(json.dumps({"healthTimeoutS": 1, "healthIntervalS": 0.1}), encoding="utf-8")

    def write_program(self, version: str) -> None:
        (self.target / "src").mkdir(exist_ok=True)
        (self.target / "src" / "x.py").write_text(version, encoding="utf-8")
        (self.target / "hydra-umc.project.json").write_text(json.dumps({"version": version}), encoding="utf-8")

    def installer(self, version: str, contract: str = "1") -> subprocess.CompletedProcess:
        script = self.base / "install_x.sh"
        script.write_text(
            "set -euo pipefail\n"
            f'DEPLOY_CONTRACT={contract}\nTARGET="{self.target}"\n'
            f'source "{ROOT / "provisioning" / "deploy_lib.sh"}"\n'
            'deploy_begin HYDRA-UMC-TWIN "$TARGET"\n'
            f'mkdir -p "$TARGET/src"; printf %s "{version}" > "$TARGET/src/x.py"; printf \'{{"version": "{version}"}}\' > "$TARGET/hydra-umc.project.json"\n'
            'deploy_finish HYDRA-UMC-TWIN "$TARGET"\n'
            'echo installer-finished\n', encoding="utf-8")
        env = {**os.environ, "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}", "HYDRA_UMC_PORTS_REGISTRY": str(self.registry),
               "HYDRA_UMC_DEPLOY_ROOT": str(self.base / "releases"), "HYDRA_UMC_DEPLOY_TOOL": str(HERE / "deploy_tree.py"), "HYDRA_UMC_DEPLOY_RESULT": str(self.result)}
        return subprocess.run(["bash", str(script)], env=env, capture_output=True, text=True, timeout=120)

    def test_a_deployment_restarts_the_running_unit_and_reports_it(self) -> None:
        self.write_program("0.1.0")
        done = self.installer("0.1.1")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("installer-finished", done.stdout)
        self.assertEqual(json.loads(self.result.read_text(encoding="utf-8"))["result"], "deployed")
        self.assertIn("try-restart hydra-umc-twin.service", self.calls.read_text(encoding="utf-8"))

    def test_a_unit_that_does_not_come_back_stops_the_installer_with_status_3_and_the_old_program_is_back(self) -> None:
        self.write_program("0.1.0")
        self.server.shutdown()
        self.server.server_close()
        done = self.installer("0.1.1")
        self.assertEqual(done.returncode, 3, done.stdout + done.stderr)
        self.assertNotIn("installer-finished", done.stdout)
        self.assertEqual((self.target / "src" / "x.py").read_text(encoding="utf-8"), "0.1.0")
        self.assertIn("DEPLOY=FAIL", done.stderr)

    def test_a_unit_that_is_not_running_is_left_alone(self) -> None:
        (self.base / "running").unlink()
        self.write_program("0.1.0")
        done = self.installer("0.1.1")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(self.result.read_text(encoding="utf-8"))["result"], "installed")
        self.assertNotIn("try-restart", self.calls.read_text(encoding="utf-8"))

    def test_an_installer_that_declares_another_contract_is_refused_before_it_changes_anything(self) -> None:
        self.write_program("0.1.0")
        done = self.installer("0.1.1", contract="2")
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertEqual((self.target / "src" / "x.py").read_text(encoding="utf-8"), "0.1.0")

    def test_the_switch_skips_both_steps(self) -> None:
        self.write_program("0.1.0")
        script = self.base / "install_y.sh"
        script.write_text(f'set -euo pipefail\nDEPLOY_CONTRACT=1\nsource "{ROOT / "provisioning" / "deploy_lib.sh"}"\ndeploy_begin HYDRA-UMC-TWIN "{self.target}"\ndeploy_finish HYDRA-UMC-TWIN "{self.target}"\necho fine\n', encoding="utf-8")
        done = subprocess.run(["bash", str(script)], env={**os.environ, "HYDRA_UMC_DEPLOY": "off", "HYDRA_UMC_DEPLOY_ROOT": str(self.base / "releases")}, capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("fine", done.stdout)
        self.assertFalse((self.base / "releases" / "twin").exists())


if __name__ == "__main__":
    unittest.main()
