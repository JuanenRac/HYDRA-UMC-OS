#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - Fleet update check
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Prove tools/fleet_update.py on a simulated device (temporary folders, no systemd, no network, no sudo): the plan, the order, the happy way, an installer that fails, a health
check that fails, an import error in the journal, the SDK that the unit cannot import, a tag that is not the commit GitHub gives, a disk that is too small, a tag that does not
verify, the unit files after a rollback, a run that is cut and taken up again, the progress of the build of the server, and the refusal to restart the machine."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("fleet_update", HERE / "fleet_update.py")
assert _spec and _spec.loader
fu = importlib.util.module_from_spec(_spec)
sys.modules["fleet_update"] = fu
_spec.loader.exec_module(fu)

SHA = {"v0.2.0": "a" * 40, "v0.3.0": "b" * 40, "v1.0.0": "c" * 40}
INSTALLERS = [
    {"script": "install_datalake.sh", "source": "HYDRA-UMC-DATALAKE", "target": "/opt/hydra-umc/datalake", "unit": "hydra-umc-datalake.service", "port": 8100, "health_path": "/health"},
    {"script": "install_semantic_planner.sh", "source": "HYDRA-UMC-SEMANTIC-PLANNER", "target": "/opt/hydra-umc/semantic-planner", "unit": "hydra-umc-semantic-planner.service", "port": 8101, "health_path": "/health"},
]


class Device:
    """A device in a folder: the checkouts, the installed programs, the units and the commands that touch them."""

    def __init__(self, base: Path) -> None:
        self.base = base
        self.workspace, self.root, self.backups, self.units = base / "ws", base / "opt", base / "bak", base / "units"
        for folder in (self.workspace, self.root, self.backups, self.units):
            folder.mkdir(parents=True)
        provisioning = self.workspace / "HYDRA-UMC-OS" / "provisioning"
        provisioning.mkdir(parents=True)
        (provisioning / "install_plan.json").write_text(json.dumps({"installers": INSTALLERS}), encoding="utf-8")
        self.versions = {"datalake": "0.1.0", "semantic-planner": "0.1.0", "server": "0.9.0"}
        for repo in ("HYDRA-UMC-OS", "HYDRA-UMC-SDK", "HYDRA-UMC-DATALAKE", "HYDRA-UMC-SEMANTIC-PLANNER", "HYDRA-UMC-SERVER", "HYDRA-UMC-STUDIO"):
            (self.workspace / repo / ".git").mkdir(parents=True)
        for name, version in self.versions.items():
            self.write_version(name, version)
            (self.units / f"hydra-umc-{name}.service").write_text(f"[Service]\nExecStart=/opt/hydra-umc/{name}/run\n", encoding="utf-8")
        self.active = {f"hydra-umc-{n}.service": "active" for n in self.versions}
        self.releases = {"HYDRA-UMC-OS": "v0.6.0", "HYDRA-UMC-SDK": "v0.6.0", "HYDRA-UMC-DATALAKE": "v0.2.0", "HYDRA-UMC-SEMANTIC-PLANNER": "v0.2.0",
                         "HYDRA-UMC-SERVER": "v0.9.0", "HYDRA-UMC-STUDIO": "v0.9.0"}
        self.calls: list[list[str]] = []
        self.fail_install: set[str] = set()
        self.health_code = 200
        self.journal = ""
        self.sdk_ok = True
        self.verify_tag_ok = True
        self.bad_commit: set[str] = set()
        self.drop_in_on_install: set[str] = set()
        self.damage_unit_on_install: set[str] = set()
        self.restore_units = True
        self.build_fails = False
        self.free = 100000

    def write_version(self, name: str, version: str) -> None:
        folder = self.root / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "hydra-umc.project.json").write_text(json.dumps({"version": version}), encoding="utf-8")

    # ---- the commands ---------------------------------------------------------------------------------------------------------------------------------
    def sh(self, argv: list[str], timeout: int = 0, on_line: Any = None) -> tuple[int, str]:
        if argv[:2] == ["sudo", "-n"]:
            argv = argv[2:]
        self.calls.append(argv)
        if argv[0] == "git":
            repo = Path(argv[2]).name
            verb = argv[3]
            if verb == "describe":
                return 0, {"HYDRA-UMC-OS": "v0.6.0", "HYDRA-UMC-SDK": "v0.6.0", "HYDRA-UMC-DATALAKE": "v0.1.0", "HYDRA-UMC-SEMANTIC-PLANNER": "v0.1.0", "HYDRA-UMC-SERVER": "v0.9.0", "HYDRA-UMC-STUDIO": "v0.9.0"}[repo] + "\n"
            if verb in ("rev-parse",) and argv[4] == "HEAD":
                return 0, "f" * 40 + "\n"
            if verb == "rev-parse":
                tag = argv[4].split("^")[0]
                return 0, ("d" * 40 if repo in self.bad_commit else SHA.get(tag, "e" * 40)) + "\n"
            if verb == "symbolic-ref":
                return 0, "main\n"
            if verb == "status":
                return 0, ""
            if verb == "verify-tag":
                return (0 if self.verify_tag_ok else 1), ""
            return 0, ""
        if argv[0] == "systemctl":
            if argv[1] == "is-active":
                return 0, self.active.get(argv[2], "inactive") + "\n"
            if argv[1] == "show":
                return 0, "Environment=PYTHONPATH=/opt/hydra-umc/sdk\n"
            return 0, ""
        if argv[0] == "tar" and argv[1] == "czf":
            Path(argv[2]).write_text("tar", encoding="utf-8")
            return 0, ""
        if argv[0] == "tar" and argv[1] == "xzf":
            self.restored = argv[2]
            if self.restore_units:
                for unit in self.units.glob("*.service"):
                    unit.write_text(f"[Service]\nExecStart=/opt/hydra-umc/{unit.stem.removeprefix('hydra-umc-')}/run\n", encoding="utf-8")
            name = Path(argv[2]).name.split(".bak_")[0]
            self.write_version(name, self.versions[name])
            return 0, ""
        if argv[0] == "rm":
            import shutil
            for path in argv[2:]:
                shutil.rmtree(path, ignore_errors=True)
            return 0, ""
        if argv[0] == "mkdir":
            return 0, ""
        if argv[0] == "journalctl":
            return 0, self.journal
        if argv[0] == "env":
            return (0 if self.sdk_ok else 1), ""
        if argv[0] == "bash" and argv[1].endswith(".sh"):
            name = Path(argv[1]).name.removeprefix("install_").removesuffix(".sh").replace("_", "-")
            if on_line:
                on_line("compiling")
            if name in self.fail_install:
                return 3, "DEPLOY=FAIL %s did not pass the health check; the release in use is %s\n" % (name, self.versions[name])
            repo = {"datalake": "HYDRA-UMC-DATALAKE", "semantic-planner": "HYDRA-UMC-SEMANTIC-PLANNER", "server": "HYDRA-UMC-SERVER"}[name]
            self.write_version(name, self.releases[repo].lstrip("v"))
            unit = self.units / f"hydra-umc-{name}.service"
            if name in self.drop_in_on_install:
                (self.units / f"{unit.name}.d").mkdir(exist_ok=True)
                (self.units / f"{unit.name}.d" / "10-new.conf").write_text("[Service]\n", encoding="utf-8")
            if name in self.damage_unit_on_install:
                unit.write_text("[Service]\nExecStart=/changed\n", encoding="utf-8")
            return 0, "install rc=0\n"
        if argv[0] == "bash" and argv[1] == "-c":
            for line in ("step 1", "step 2"):
                if on_line:
                    on_line(line)
            return (1 if self.build_fails else 0), "boom\n" if self.build_fails else ""
        return 0, ""

    def http(self, url: str) -> Any:
        repo = url.split("/repos/JuanenRac/")[1].split("/")[0]
        if "/releases/latest" in url:
            return {"tag_name": self.releases[repo], "assets": []}
        return {"sha": SHA.get(url.rsplit("/", 1)[1], "e" * 40)}

    def env(self, **config: Any) -> Any:
        settings = dict(fu.DEFAULTS)
        settings.update(workspace=str(self.workspace), root=str(self.root), backups=str(self.backups), **config)
        clock = [1_900_000_000.0]
        environment = fu.Env(self.base / "state" / "fleet.json", settings, sh=self.sh, http=self.http, health=lambda _u: self.health_code, now=lambda: clock[0],
                             sleep=lambda s: clock.__setitem__(0, clock[0] + s), log=lambda _m: None, free_mb=lambda _p: self.free)
        environment.unit_dir = self.units
        environment.clock = clock  # type: ignore[attr-defined]
        return environment


class FleetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.device = Device(Path(self.tmp.name))

    def planned(self, **config: Any):
        environment = self.device.env(**config)
        environment.state = fu.make_plan(environment)
        environment.save()
        return environment

    def row(self, environment, name: str) -> dict:
        return next(r for r in environment.state["services"] if r["name"] == name)

    def go(self, environment, names=None) -> int:
        environment.state = fu.load_state(environment)
        return fu.run_plan(environment, names)

    # ---- the plan -------------------------------------------------------------------------------------------------------------------------------------
    def test_the_plan_sets_the_installed_against_the_newest_and_writes_nothing_else(self) -> None:
        environment = self.planned()
        actions = {r["name"]: (r["installed"], r["latest"], r["action"], r["reason"]) for r in environment.state["services"]}
        self.assertEqual(actions["datalake"], ("0.1.0", "v0.2.0", "update", ""))
        self.assertEqual(actions["semantic-planner"], ("0.1.0", "v0.2.0", "update", ""))
        self.assertEqual(actions["server"][2], "current")
        self.assertEqual(actions["os-tools"][2], "current")
        self.assertEqual([r["name"] for r in environment.state["services"]], ["os-tools", "sdk", "datalake", "semantic-planner", "server", "studio"])
        self.assertEqual(environment.state["state"], "planned")
        self.assertFalse([c for c in self.device.calls if c[0] == "tar" or (c[0] == "bash")])

    def test_what_cannot_or_should_not_be_updated_is_said_with_its_reason(self) -> None:
        self.device.active["hydra-umc-datalake.service"] = "inactive"
        self.device.releases["HYDRA-UMC-SEMANTIC-PLANNER"] = "v0.0.5"
        environment = self.planned()
        self.assertEqual((self.row(environment, "datalake")["action"], self.row(environment, "datalake")["reason"]), ("skip", "unit_inactive"))
        self.assertEqual((self.row(environment, "semantic-planner")["action"], self.row(environment, "semantic-planner")["reason"]), ("review", "installed_newer"))
        environment = self.device.env()
        environment.state = fu.make_plan(environment, include_inactive=True)
        self.assertEqual(self.row(environment, "datalake")["action"], "update")
        environment.state = fu.make_plan(environment, only={"datalake"})
        self.assertEqual(self.row(environment, "semantic-planner")["reason"], "not_asked" if self.row(environment, "semantic-planner")["action"] == "skip" else "installed_newer")

    # ---- the way in -----------------------------------------------------------------------------------------------------------------------------------
    def test_every_program_is_updated_in_order_with_its_steps_and_the_run_ends_done(self) -> None:
        self.device.releases["HYDRA-UMC-SERVER"] = "v1.0.0"
        self.device.releases["HYDRA-UMC-STUDIO"] = "v1.0.0"
        environment = self.planned()
        self.assertEqual(self.go(environment), 0)
        state = environment.state
        self.assertEqual(state["state"], "done")
        self.assertEqual({r["name"]: r["state"] for r in state["services"] if r["action"] == "update"}, {"datalake": "done", "semantic-planner": "done", "studio": "done", "server": "done"})
        installs = [c[1] for c in self.device.calls if c[0] == "bash" and c[1].endswith(".sh")]
        self.assertEqual([Path(i).name for i in installs], ["install_datalake.sh", "install_semantic_planner.sh", "install_server.sh"])
        self.assertEqual(json.loads((self.device.root / "datalake" / "hydra-umc.project.json").read_text())["version"], "0.2.0")
        saved = json.loads(environment.state_path.read_text())
        self.assertEqual(saved["schema"], fu.SCHEMA)
        self.assertTrue(environment.heartbeat_path.is_file())
        datalake = self.row(environment, "datalake")
        self.assertEqual(datalake["step"], "done")
        seen = [e["text"] for e in datalake["log"]]
        self.assertLess(next(i for i, t in enumerate(seen) if "backup" in t), next(i for i, t in enumerate(seen) if "installing" in t))
        self.assertTrue(datalake["backup"].endswith(".tgz"))

    def test_the_server_is_built_in_steps_with_its_frontend_and_comes_last(self) -> None:
        self.device.releases["HYDRA-UMC-SERVER"] = "v1.0.0"
        self.device.releases["HYDRA-UMC-STUDIO"] = "v1.0.0"
        environment = self.planned()
        self.go(environment, {"server", "studio"})
        server = self.row(environment, "server")
        self.assertEqual(server["state"], "done")
        self.assertEqual(server["substeps"], 3)
        builds = [e["text"] for e in server["log"] if "building" in e["text"]]
        self.assertEqual(len(builds), 3)
        self.assertIn("npm ci (1/3)", builds[0])
        self.assertIn("frontend (3/3)", builds[2])
        checkouts = [c for c in self.device.calls if c[0] == "git" and c[3] == "checkout"]
        self.assertTrue(any("HYDRA-UMC-STUDIO" in c[2] for c in checkouts))
        self.assertIn("minutes", builds[0])

    def test_nothing_is_applied_without_the_yes_and_a_resume_names_its_program(self) -> None:
        environment = self.planned()
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(fu.main(["run", "--state", str(environment.state_path)], environment), 64)
            self.assertEqual(fu.main(["resume", "--state", str(environment.state_path), "--yes"], environment), 64)
        self.assertIn("FLEET=REFUSED", err.getvalue())
        self.assertFalse([c for c in self.device.calls if c[0] == "tar"])

    # ---- the failures ---------------------------------------------------------------------------------------------------------------------------------
    def test_an_installer_that_fails_is_rolled_back_and_the_run_stops_there(self) -> None:
        self.device.fail_install.add("datalake")
        environment = self.planned()
        self.assertEqual(self.go(environment), fu.EXIT_FAILED)
        datalake, planner = self.row(environment, "datalake"), self.row(environment, "semantic-planner")
        self.assertEqual((datalake["state"], datalake["error"]), ("rolled_back", "installer_failed"))
        self.assertIn("DEPLOY=FAIL", datalake["detail"])
        self.assertEqual(planner["state"], "skipped")
        self.assertEqual(environment.state["state"], "failed")
        self.assertEqual(environment.state["stoppedAt"], "datalake")
        self.assertEqual(self.device.restored, datalake["backup"])
        self.assertEqual(json.loads((self.device.root / "datalake" / "hydra-umc.project.json").read_text())["version"], "0.1.0")
        self.assertFalse([c for c in self.device.calls if c[0] == "bash" and "semantic_planner" in c[1]])

    def test_a_health_check_that_fails_puts_the_earlier_program_back(self) -> None:
        self.device.health_code = 503
        environment = self.planned()
        self.assertEqual(self.go(environment, {"datalake"}), fu.EXIT_FAILED)
        row = self.row(environment, "datalake")
        self.assertEqual((row["state"], row["error"]), ("rolled_back", "not_healthy"))
        self.assertTrue(any(c[:2] == ["systemctl", "restart"] for c in self.device.calls))

    def test_an_import_error_in_the_journal_or_an_sdk_off_the_path_is_a_failure(self) -> None:
        self.device.journal = "Nov 13 python[1]: ModuleNotFoundError: No module named 'hydra_umc_sdk'\n"
        environment = self.planned()
        self.go(environment, {"semantic-planner"})
        row = self.row(environment, "semantic-planner")
        self.assertEqual((row["state"], row["error"]), ("rolled_back", "journal_errors"))
        self.assertIn("ModuleNotFoundError", row["detail"])
        self.device.journal = ""
        self.device.sdk_ok = False
        (self.device.root / "datalake").mkdir(exist_ok=True)
        (self.device.root / "datalake" / "app.py").write_text("import hydra_umc_sdk\n", encoding="utf-8")
        environment = self.planned()
        self.go(environment, {"datalake"})
        self.assertEqual(self.row(environment, "datalake")["error"], "sdk_not_importable")

    def test_a_tag_that_is_not_the_commit_github_gives_stops_before_anything_is_touched(self) -> None:
        self.device.bad_commit.add("HYDRA-UMC-DATALAKE")
        environment = self.planned()
        self.assertEqual(self.go(environment, {"datalake"}), fu.EXIT_FAILED)
        row = self.row(environment, "datalake")
        self.assertEqual((row["state"], row["error"]), ("failed", "tag_mismatch"))
        self.assertFalse([c for c in self.device.calls if c[0] == "tar"])

    def test_a_tag_that_does_not_verify_is_refused_only_when_signed_tags_are_required(self) -> None:
        self.device.verify_tag_ok = False
        environment = self.planned()
        self.go(environment, {"datalake"})
        self.assertEqual(self.row(environment, "datalake")["state"], "done")
        self.device = Device(Path(self.tmp.name) / "second")
        self.device.verify_tag_ok = False
        environment = self.planned(requireSignedTags=True)
        self.go(environment, {"datalake"})
        self.assertEqual(self.row(environment, "datalake")["error"], "tag_unsigned")

    def test_too_little_disk_blocks_the_run_before_any_change(self) -> None:
        self.device.free = 300
        environment = self.planned()
        self.assertEqual(self.go(environment), fu.EXIT_BLOCKED)
        row = self.row(environment, "datalake")
        self.assertEqual((row["state"], row["error"]), ("blocked", "low_disk"))
        self.assertEqual((row["freeMb"], row["needMb"]), (300, 800))
        self.assertEqual(environment.state["state"], "blocked")
        self.assertFalse([c for c in self.device.calls if c[0] == "tar"])
        self.device.free = 2000
        self.device.releases["HYDRA-UMC-SERVER"] = "v1.0.0"
        self.device.releases["HYDRA-UMC-STUDIO"] = "v1.0.0"
        environment = self.planned()
        self.go(environment, {"server", "studio"})
        self.assertEqual(self.row(environment, "server")["needMb"], 2500)
        self.assertEqual(self.row(environment, "server")["error"], "low_disk")

    def test_a_build_that_fails_on_the_device_is_a_failure_with_the_step_named(self) -> None:
        self.device.releases["HYDRA-UMC-SERVER"] = "v1.0.0"
        self.device.releases["HYDRA-UMC-STUDIO"] = "v1.0.0"
        self.device.build_fails = True
        environment = self.planned()
        self.go(environment, {"server", "studio"})
        row = self.row(environment, "server")
        self.assertEqual((row["state"], row["error"]), ("rolled_back", "build_failed"))
        self.assertIn("npm ci", row["detail"])

    # ---- the units after a rollback -------------------------------------------------------------------------------------------------------------------
    def test_the_rollback_removes_the_dropin_the_installer_added_and_says_the_unit_is_as_it_was(self) -> None:
        self.device.fail_install.add("datalake")
        self.device.drop_in_on_install.add("datalake")
        (self.device.units / "hydra-umc-datalake.service.d").mkdir()
        (self.device.units / "hydra-umc-datalake.service.d" / "10-old.conf").write_text("[Service]\n", encoding="utf-8")
        environment = self.planned()
        self.go(environment, {"datalake"})
        row = self.row(environment, "datalake")
        self.assertEqual(row["state"], "rolled_back")
        # the drop-in the installer added is gone; the old one was in the copy, and this machine restores only the unit files, so the file says the unit is not as it was
        self.assertFalse((self.device.units / "hydra-umc-datalake.service.d" / "10-new.conf").exists())
        self.assertFalse(row["unitRestored"])

    def test_a_unit_that_the_rollback_could_not_put_back_is_reported(self) -> None:
        self.device.damage_unit_on_install.add("datalake")
        self.device.health_code = 500
        self.device.restore_units = False
        environment = self.planned()
        self.go(environment, {"datalake"})
        row = self.row(environment, "datalake")
        self.assertEqual(row["state"], "rolled_back")
        self.assertFalse(row["unitRestored"])
        self.assertTrue(any("not as they were" in e["text"] for e in row["log"]))
        self.device.restore_units = True
        self.device = Device(Path(self.tmp.name) / "third")
        self.device.damage_unit_on_install.add("datalake")
        self.device.health_code = 500
        environment = self.planned()
        self.go(environment, {"datalake"})
        self.assertTrue(self.row(environment, "datalake")["unitRestored"])

    # ---- the cut run ----------------------------------------------------------------------------------------------------------------------------------
    def test_a_run_that_was_cut_is_interrupted_and_resume_takes_up_that_program_only(self) -> None:
        environment = self.planned()
        state = environment.state
        state.update(state="running", pid=99999999)
        self.row(environment, "datalake").update(state="running", step="installing")
        environment.save()
        environment.heartbeat_path.write_text(str(environment.now() - 600), encoding="utf-8")
        reread = fu.load_state(environment)
        self.assertEqual(reread["state"], "interrupted")
        row = next(r for r in reread["services"] if r["name"] == "datalake")
        self.assertEqual((row["state"], row["error"]), ("interrupted", "interrupted"))
        self.assertIn("installing", row["detail"])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(fu.main(["resume", "--state", str(environment.state_path), "--only", "datalake", "--yes"], environment), 0)
        self.assertIn("FLEET=PASS", out.getvalue())
        self.assertEqual(self.row(environment, "datalake")["state"], "done")
        self.assertEqual(self.row(environment, "semantic-planner")["state"], "waiting")

    def test_a_run_that_is_alive_is_not_marked_interrupted(self) -> None:
        state = {"state": "running", "services": [{"name": "a", "state": "running"}]}
        self.assertFalse(fu.mark_interrupted(state, 3.0, True))
        self.assertTrue(fu.mark_interrupted(state, 3.0, False))
        self.assertTrue(fu.mark_interrupted({"state": "running", "services": []}, None, True))
        self.assertFalse(fu.mark_interrupted({"state": "done", "services": []}, None, False))

    # ---- the rest -------------------------------------------------------------------------------------------------------------------------------------
    def test_the_machine_is_never_restarted(self) -> None:
        for command in (["sudo", "reboot"], ["systemctl", "poweroff"], ["shutdown", "-h", "now"], ["systemctl", "reboot"]):
            with self.assertRaisesRegex(RuntimeError, "never restarted"):
                fu.default_sh(command)
        self.assertEqual(fu.default_sh([sys.executable, "-c", "print('ok')"])[1].strip(), "ok")

    def test_the_settings_come_from_the_file_and_a_bad_value_falls_back_with_a_warning(self) -> None:
        path = Path(self.tmp.name) / "fleet-update.json"
        path.write_text(json.dumps({"requireSignedTags": True, "minFreeMb": 1200, "minFreeMbServer": "lots", "owner": "Someone", "unknown": 1}), encoding="utf-8")
        warnings: list[str] = []
        settings = fu.load_config(path, warnings.append)
        self.assertEqual((settings["requireSignedTags"], settings["minFreeMb"], settings["minFreeMbServer"], settings["owner"]), (True, 1200, 2500, "Someone"))
        self.assertEqual(len(warnings), 1)
        path.write_text("{bad", encoding="utf-8")
        self.assertEqual(fu.load_config(path, warnings.append), fu.DEFAULTS)
        self.assertEqual(fu.load_config(None), fu.DEFAULTS)
        self.assertFalse(fu.DEFAULTS["requireSignedTags"])

    def test_secrets_are_not_written_to_the_file(self) -> None:
        self.assertEqual(fu.redact("token=abc123 password: hunter2"), "token=*** password: ***")
        environment = self.planned()
        row = self.row(environment, "datalake")
        environment.say(row, "connecting with api_key=SECRETVALUE")
        self.assertNotIn("SECRETVALUE", environment.state_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
