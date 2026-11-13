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
import os
import re
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
_spec2 = importlib.util.spec_from_file_location("make_fleet_sudoers", HERE / "make_fleet_sudoers.py")
assert _spec2 and _spec2.loader
ms = importlib.util.module_from_spec(_spec2)
sys.modules["make_fleet_sudoers"] = ms
_spec2.loader.exec_module(ms)

FAKE_DIGEST = "a" * 64
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
        self.components = base / "components"
        self.bad_signature = False
        self.fail_package_install = False
        self.download_fails = False
        self.downloads: list[str] = []
        self.rollbacks: list[str] = []
        self.fail_tar = False
        self.install_noop: set[str] = set()
        self.offline = False
        self.dirty: set[str] = set()

    def write_version(self, name: str, version: str) -> None:
        folder = self.root / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "hydra-umc.project.json").write_text(json.dumps({"version": version}), encoding="utf-8")

    # ---- the commands ---------------------------------------------------------------------------------------------------------------------------------
    def sh(self, argv: list[str], timeout: int = 0, on_line: Any = None) -> tuple[int, str]:
        if argv[:2] == ["sudo", "-n"]:
            argv = argv[2:]
        self.calls.append(argv)
        if argv[0] == "python3" and argv[1].endswith("package_component.py"):
            name = Path(argv[3]).name
            m = re.match(r"hydra-([a-z-]+)-([0-9.]+)\.tgz$", name)
            if self.bad_signature or not m:
                return 1, "PACKAGE=REFUSED the signature does not match the key of the releases\n"
            return 0, f"PACKAGE=OK {m.group(1)} {m.group(2)} {FAKE_DIGEST}\n"
        if argv[0] == "python3" and argv[1].endswith("deploy_release.py"):
            if argv[4] == "rollback":
                self.rollbacks.append(argv[5])
                self.write_version(argv[5], self.versions[argv[5]])
                return 0, "DEPLOY=PASS\n"
            name = re.match(r"hydra-([a-z-]+)-([0-9.]+)\.tgz$", Path(argv[5]).name)
            if self.fail_package_install:
                return 3, f"DEPLOY=FAIL {name.group(1)} did not pass the health check; the release in use is {self.versions[name.group(1)]}\n"
            self.write_version(name.group(1), name.group(2))
            return 0, "DEPLOY=PASS\n"
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
                return 0, " M file.py\n" if repo in self.dirty else ""
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
            if self.fail_tar:
                return 2, "tar: No space left on device\n"
            Path(argv[2]).write_text("tar", encoding="utf-8")
            return 0, ""
        if argv[0] == "tar" and argv[1] == "xzf":
            self.restored = argv[2]
            if self.restore_units:
                for unit in self.units.glob("*.service"):
                    unit.write_text(f"[Service]\nExecStart=/opt/hydra-umc/{unit.stem.removeprefix('hydra-umc-')}/run\n", encoding="utf-8")
            name = Path(argv[2]).name.split(".bak")[0]
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
            if name in self.install_noop:
                return 0, "install rc=0\n"
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
        if self.offline:
            raise OSError("offline")
        repo = url.split("/repos/JuanenRac/")[1].split("/")[0]
        if "/releases/latest" in url:
            return {"tag_name": self.releases[repo], "assets": []}
        return {"sha": SHA.get(url.rsplit("/", 1)[1], "e" * 40)}

    def wire(self, name: str) -> None:
        """The program runs from <components>/<name>/current: its folder under the root becomes a link to it."""
        import shutil
        release = self.components / name / "releases" / f"{self.versions[name]}-1"
        release.parent.mkdir(parents=True)
        shutil.move(str(self.root / name), str(release))
        os.symlink(Path("releases") / release.name, self.components / name / "current", target_is_directory=True)
        os.symlink(self.components / name / "current", self.root / name, target_is_directory=True)

    def download(self, url: str, destination: Path) -> None:
        self.downloads.append(url)
        if self.download_fails:
            raise OSError("connection reset")
        destination.write_text("package", encoding="utf-8")

    def env(self, **config: Any) -> Any:
        settings = dict(fu.DEFAULTS)
        settings.update(workspace=str(self.workspace), root=str(self.root), backups=str(self.backups), components=str(self.components), **config)
        clock = [1_900_000_000.0]
        environment = fu.Env(self.base / "state" / "fleet.json", settings, sh=self.sh, http=self.http, health=lambda _u: self.health_code, now=lambda: clock[0],
                             sleep=lambda s: clock.__setitem__(0, clock[0] + s), log=lambda _m: None, free_mb=lambda _p: self.free, download=self.download)
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


    # ---- more cases of the simulated device -----------------------------------------------------------------------------------------------------------
    def test_after_the_cause_is_fixed_a_failed_program_is_taken_up_and_the_run_goes_on(self) -> None:
        self.device.fail_install.add("datalake")
        environment = self.planned()
        self.assertEqual(self.go(environment), fu.EXIT_FAILED)
        self.assertEqual(self.row(environment, "semantic-planner")["state"], "skipped")
        self.device.fail_install.clear()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(fu.main(["resume", "--state", str(environment.state_path), "--only", "datalake", "--yes"], environment), 0)
        self.assertEqual(self.row(environment, "datalake")["state"], "done")
        with contextlib.redirect_stdout(out):
            self.assertEqual(fu.main(["run", "--state", str(environment.state_path), "--yes"], environment), 0)
        self.assertEqual(self.row(environment, "semantic-planner")["state"], "done")
        self.assertEqual(environment.state["state"], "done")

    def test_a_second_run_after_everything_is_current_has_nothing_to_do(self) -> None:
        environment = self.planned()
        self.assertEqual(self.go(environment), 0)
        environment = self.planned()
        self.assertEqual({r["action"] for r in environment.state["services"]}, {"current"})
        before = len([c for c in self.device.calls if c[0] == "tar"])
        self.assertEqual(self.go(environment), 0)
        self.assertEqual(len([c for c in self.device.calls if c[0] == "tar"]), before)

    def test_an_installer_that_ends_well_but_changes_nothing_is_a_version_failure_and_is_put_back(self) -> None:
        self.device.install_noop.add("datalake")
        environment = self.planned()
        self.go(environment, {"datalake"})
        row = self.row(environment, "datalake")
        self.assertEqual((row["state"], row["error"]), ("rolled_back", "version_mismatch"))

    def test_a_backup_that_cannot_be_made_stops_before_the_installer_runs(self) -> None:
        self.device.fail_tar = True
        environment = self.planned()
        self.assertEqual(self.go(environment), fu.EXIT_FAILED)
        row = self.row(environment, "datalake")
        self.assertEqual((row["state"], row["error"]), ("failed", "backup_failed"))
        self.assertIn("No space left", row["detail"])
        self.assertFalse([c for c in self.device.calls if c[0] == "bash" and c[1].endswith(".sh")])

    def test_a_checkout_of_the_tools_that_does_not_match_stops_before_any_service(self) -> None:
        self.device.releases["HYDRA-UMC-OS"] = "v0.7.0"
        self.device.bad_commit.add("HYDRA-UMC-OS")
        environment = self.planned()
        self.assertEqual(self.row(environment, "os-tools")["action"], "update")
        self.assertEqual(self.go(environment), fu.EXIT_FAILED)
        self.assertEqual(self.row(environment, "os-tools")["error"], "tag_mismatch")
        self.assertEqual(self.row(environment, "datalake")["state"], "skipped")
        self.assertFalse([c for c in self.device.calls if c[0] == "tar"])

    def test_the_studio_tag_that_does_not_match_fails_the_server_before_it_is_built(self) -> None:
        self.device.releases["HYDRA-UMC-SERVER"] = "v1.0.0"
        self.device.releases["HYDRA-UMC-STUDIO"] = "v1.0.0"
        self.device.bad_commit.add("HYDRA-UMC-STUDIO")
        environment = self.planned()
        self.go(environment, {"server", "studio"})
        row = self.row(environment, "server")
        self.assertEqual(row["error"], "tag_mismatch")
        self.assertFalse([c for c in self.device.calls if c[0] == "bash" and c[1] == "-c"])

    def test_an_unreachable_github_is_no_release_and_never_a_failure_or_a_change(self) -> None:
        self.device.offline = True
        environment = self.planned()
        self.assertEqual({r["action"] for r in environment.state["services"]}, {"skip"})
        self.assertEqual({r["reason"] for r in environment.state["services"]}, {"no_release"})
        self.assertEqual(self.go(environment), 0)
        self.assertFalse([c for c in self.device.calls if c[0] == "tar"])

    def test_a_checkout_with_local_changes_is_left_alone(self) -> None:
        self.device.dirty.add("HYDRA-UMC-DATALAKE")
        environment = self.planned()
        self.assertEqual((self.row(environment, "datalake")["action"], self.row(environment, "datalake")["reason"]), ("skip", "repo_dirty"))
        self.go(environment)
        self.assertEqual(self.row(environment, "datalake")["state"], "waiting")
        self.assertEqual(self.row(environment, "semantic-planner")["state"], "done")

    def test_an_inactive_unit_is_updated_only_when_asked_and_is_not_started_or_judged_by_its_health(self) -> None:
        self.device.active["hydra-umc-datalake.service"] = "inactive"
        self.device.health_code = 503
        environment = self.device.env()
        environment.state = fu.make_plan(environment, include_inactive=True)
        environment.save()
        self.go(environment, {"datalake"})
        row = self.row(environment, "datalake")
        self.assertEqual(row["state"], "done")
        self.assertFalse([c for c in self.device.calls if c[:2] == ["systemctl", "restart"]])

    def test_the_log_of_a_program_keeps_the_last_sixty_lines_and_the_file_stays_valid_json(self) -> None:
        environment = self.planned()
        row = self.row(environment, "datalake")
        for index in range(200):
            environment.say(row, f"line {index}")
        self.assertEqual(len(row["log"]), 60)
        saved = json.loads(environment.state_path.read_text(encoding="utf-8"))
        self.assertEqual(next(r for r in saved["services"] if r["name"] == "datalake")["log"][-1]["text"], "line 199")

    def test_a_file_that_is_not_a_plan_is_refused_and_never_applied(self) -> None:
        environment = self.device.env()
        environment.state_path.parent.mkdir(parents=True, exist_ok=True)
        environment.state_path.write_text(json.dumps({"schema": "other/1"}), encoding="utf-8")
        with self.assertRaises(SystemExit):
            fu.load_state(environment)
        environment.state_path.write_text("{bad", encoding="utf-8")
        with self.assertRaises(SystemExit):
            fu.load_state(environment)


    # ---- the signed tags of the critical programs, the cut copy and the rule of sudo -----------------------------------------------------------------
    def test_only_the_programs_of_the_list_need_a_tag_that_verifies(self) -> None:
        self.device.verify_tag_ok = False
        self.device.releases["HYDRA-UMC-SERVER"] = "v1.0.0"
        self.device.releases["HYDRA-UMC-STUDIO"] = "v1.0.0"
        environment = self.planned()
        self.assertEqual(self.go(environment), fu.EXIT_FAILED)
        self.assertEqual(self.row(environment, "datalake")["state"], "done")
        self.assertEqual(self.row(environment, "semantic-planner")["state"], "done")
        server = self.row(environment, "server")
        self.assertEqual((server["state"], server["error"]), ("failed", "tag_unsigned"))
        self.assertFalse([c for c in self.device.calls if c[0] == "bash" and c[1] == "-c"])

    def test_the_list_of_critical_programs_is_a_setting_and_an_empty_one_asks_nothing(self) -> None:
        self.device.verify_tag_ok = False
        self.device.releases["HYDRA-UMC-SERVER"] = "v1.0.0"
        self.device.releases["HYDRA-UMC-STUDIO"] = "v1.0.0"
        environment = self.planned(signedTags=[])
        self.assertEqual(self.go(environment), 0)
        self.assertEqual(self.row(environment, "server")["state"], "done")
        self.assertTrue(fu.needs_signed_tag(self.device.env(signedTags=["datalake"]), {"name": "datalake"}))
        self.assertFalse(fu.needs_signed_tag(self.device.env(signedTags=["datalake"]), {"name": "twin"}))
        warnings: list[str] = []
        path = Path(self.tmp.name) / "list.json"
        path.write_text(json.dumps({"signedTags": ["ok", "Bad Name"]}), encoding="utf-8")
        self.assertEqual(fu.load_config(path, warnings.append)["signedTags"], fu.DEFAULTS["signedTags"])
        self.assertEqual(len(warnings), 1)
        path.write_text(json.dumps({"signedTags": ["server", "orchestrator"]}), encoding="utf-8")
        self.assertEqual(fu.load_config(path, warnings.append)["signedTags"], ["server", "orchestrator"])

    def test_the_copy_of_a_program_has_one_exact_name_and_a_cut_program_keeps_the_copy_it_had(self) -> None:
        environment = self.planned()
        self.go(environment, {"datalake"})
        row = self.row(environment, "datalake")
        self.assertTrue(row["backup"].endswith("datalake.bak.tgz"))
        tars = [c for c in self.device.calls if c[:2] == ["tar", "czf"]]
        self.assertEqual(len(tars), 1)
        self.assertIn("--ignore-failed-read", tars[0])
        # a second program cut in the middle: its copy is not made again over what may be half of the new program
        self.device.releases["HYDRA-UMC-SEMANTIC-PLANNER"] = "v0.3.0"
        environment = self.planned()
        planner = self.row(environment, "semantic-planner")
        planner.update(state="interrupted", backup=str(self.device.backups / "semantic-planner.bak.tgz"), unitFilesBefore={})
        (self.device.backups / "semantic-planner.bak.tgz").write_text("good copy", encoding="utf-8")
        environment.save()
        environment.state["state"] = "interrupted"
        environment.save()
        before = len([c for c in self.device.calls if c[:2] == ["tar", "czf"]])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(fu.main(["resume", "--state", str(environment.state_path), "--only", "semantic-planner", "--yes"], environment), 0)
        self.assertEqual(len([c for c in self.device.calls if c[:2] == ["tar", "czf"]]), before)
        self.assertEqual((self.device.backups / "semantic-planner.bak.tgz").read_text(encoding="utf-8"), "good copy")

    def test_every_command_the_tool_passes_to_sudo_is_a_line_of_the_rule_and_the_rule_has_no_wildcard(self) -> None:
        self.device.fail_install.add("semantic-planner")
        self.device.releases["HYDRA-UMC-SERVER"] = "v1.0.0"
        self.device.releases["HYDRA-UMC-STUDIO"] = "v1.0.0"
        original = fu.sudo
        issued: list[list[str]] = []
        fu.sudo = lambda argv: (issued.append(list(argv)), ["sudo", "-n", *argv])[1]
        try:
            environment = self.planned()
            self.go(environment)
            self.device.fail_install.clear()
            self.go(environment, {"semantic-planner", "server", "studio"})
        finally:
            fu.sudo = original
        self.assertTrue(issued)
        allowed = ms.commands(INSTALLERS, self.device.workspace.as_posix(), self.device.root.as_posix(), self.device.backups.as_posix(), self.device.units.as_posix())
        norm = [[w.replace("\\", "/") for w in c] for c in issued]
        allowed = [[w.replace("\\", "/") for w in c] for c in allowed]
        outside = [c for c in norm if c not in allowed]
        self.assertEqual(outside, [], "commands outside the rule")
        kinds = {c[0] for c in norm}
        self.assertTrue({"mkdir", "tar", "bash", "journalctl", "rm", "systemctl"} <= kinds, kinds)
        text = ms.render("hydra-umc", INSTALLERS, "/home/hydra-umc/hydra-umc", "/opt/hydra-umc", "/opt/hydra-umc-backups", "/etc/systemd/system")
        self.assertNotIn("*", text.replace("# Written", ""))
        self.assertIn("hydra-umc ALL=(root) NOPASSWD: HYDRA_FLEET", text)
        self.assertIn("/usr/bin/bash /home/hydra-umc/hydra-umc/HYDRA-UMC-OS/provisioning/install_server.sh --apply", text)
        self.assertIn("/usr/bin/systemctl restart hydra-umc-datalake.service", text)
        with self.assertRaises(ValueError):
            ms.escape("a*b")


    def test_a_program_cut_after_its_installer_finished_is_taken_up_by_the_checks_alone(self) -> None:
        """The server's installer restarts the unit that runs the tool: the run is cut with the new version in place."""
        self.device.releases["HYDRA-UMC-SERVER"] = "v1.0.0"
        self.device.releases["HYDRA-UMC-STUDIO"] = "v1.0.0"
        environment = self.planned()
        server = self.row(environment, "server")
        server.update(state="running", step="installing", backup=str(self.device.backups / "server.bak.tgz"))
        environment.state.update(state="running", pid=99999999)
        environment.save()
        environment.heartbeat_path.write_text(str(environment.now() - 900), encoding="utf-8")
        self.device.write_version("server", "1.0.0")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(fu.main(["resume", "--state", str(environment.state_path), "--only", "server", "--yes"], environment), 0)
        self.assertEqual(self.row(environment, "server")["state"], "done")
        self.assertFalse([c for c in self.device.calls if c[0] == "tar" or (c[0] == "bash" and c[1] == "-c")])
        self.assertFalse([c for c in self.device.calls if c[0] == "git" and c[3] == "checkout"])
        self.assertTrue(any("only the checks are left" in e["text"] for e in self.row(environment, "server")["log"]))


    # ---- the programs that run from their link are updated with the signed package of their release --------------------------------------------------
    def wired_server(self, **config: Any):
        self.device.releases["HYDRA-UMC-SERVER"] = "v1.0.0"
        self.device.releases["HYDRA-UMC-STUDIO"] = "v1.0.0"
        self.device.wire("server")
        return self.planned(**config)

    def test_a_program_that_runs_from_its_link_is_left_alone_while_the_switch_is_off(self) -> None:
        environment = self.wired_server()
        server = self.row(environment, "server")
        self.assertEqual((server["action"], server["reason"], server["wired"]), ("skip", "migrated_needs_packages", True))
        self.assertEqual(self.row(environment, "studio")["action"], "skip")
        self.go(environment)
        self.assertEqual(self.row(environment, "datalake")["state"], "done")
        self.assertEqual(self.row(environment, "server")["state"], "waiting")
        self.assertFalse([c for c in self.device.calls if c[0] == "python3"])
        self.assertFalse([c for c in self.device.calls if c[0] == "bash" and "install_server" in c[1]])
        self.assertFalse(fu.DEFAULTS["usePackages"])

    def test_with_the_switch_on_the_server_is_updated_by_its_signed_package_and_not_by_its_installer(self) -> None:
        environment = self.wired_server(usePackages=True)
        server = self.row(environment, "server")
        self.assertEqual((server["action"], server["mode"]), ("update", "package"))
        self.assertEqual((self.row(environment, "studio")["action"], self.row(environment, "studio")["reason"]), ("skip", "own_package"))
        self.assertEqual(self.go(environment, {"server"}), 0)
        self.assertEqual(self.row(environment, "server")["state"], "done")
        self.assertEqual(sorted(u.rsplit("/", 1)[1] for u in self.device.downloads), ["hydra-server-1.0.0.tgz", "hydra-server-1.0.0.tgz.sha256", "hydra-server-1.0.0.tgz.sig"])
        self.assertTrue(all(u.startswith("https://github.com/JuanenRac/HYDRA-UMC-SERVER/releases/download/v1.0.0/") for u in self.device.downloads))
        python = [c for c in self.device.calls if c[0] == "python3"]
        self.assertTrue(python[0][1].endswith("package_component.py") and python[0][2] == "verify")
        self.assertTrue(python[1][1].endswith("deploy_release.py") and python[1][4] == "install")
        self.assertFalse([c for c in self.device.calls if c[0] == "bash"])
        self.assertFalse([c for c in self.device.calls if c[0] == "tar" or c[:2] == ["git", "checkout"]])
        self.assertEqual(json.loads((self.device.root / "server" / "hydra-umc.project.json").read_text())["version"], "1.0.0")

    def test_a_program_without_a_package_that_runs_from_its_link_is_never_touched_by_its_installer(self) -> None:
        self.device.wire("datalake")
        environment = self.planned(usePackages=True)
        row = self.row(environment, "datalake")
        self.assertEqual((row["action"], row["reason"]), ("skip", "migrated_no_package"))
        self.go(environment)
        self.assertEqual(row["state"], "waiting")
        self.assertFalse([c for c in self.device.calls if c[0] == "bash" and "install_datalake" in c[1]])

    def test_a_package_whose_signature_does_not_hold_is_discarded_and_nothing_is_installed(self) -> None:
        self.device.bad_signature = True
        environment = self.wired_server(usePackages=True)
        self.assertEqual(self.go(environment, {"server"}), fu.EXIT_FAILED)
        row = self.row(environment, "server")
        self.assertEqual((row["state"], row["error"]), ("failed", "signature_invalid"))
        self.assertIn("signature does not match", row["detail"])
        self.assertFalse([c for c in self.device.calls if c[0] == "python3" and c[1].endswith("deploy_release.py")])
        self.assertEqual(json.loads((self.device.root / "server" / "hydra-umc.project.json").read_text())["version"], "0.9.0")
        self.assertFalse(list((environment.state_path.parent / "packages").glob("hydra-server-*")))

    def test_a_download_that_is_cut_is_a_failure_before_anything_is_checked_or_installed(self) -> None:
        self.device.download_fails = True
        environment = self.wired_server(usePackages=True)
        self.go(environment, {"server"})
        row = self.row(environment, "server")
        self.assertEqual((row["state"], row["error"]), ("failed", "download_failed"))
        self.assertFalse([c for c in self.device.calls if c[0] == "python3"])

    def test_an_install_the_deploy_tool_puts_back_is_reported_as_rolled_back_and_the_run_stops(self) -> None:
        self.device.fail_package_install = True
        environment = self.wired_server(usePackages=True)
        self.assertEqual(self.go(environment, {"server"}), fu.EXIT_FAILED)
        row = self.row(environment, "server")
        self.assertEqual((row["state"], row["error"]), ("rolled_back", "installer_failed"))
        self.assertIn("DEPLOY=FAIL", row["detail"])
        self.assertEqual(self.device.rollbacks, [])        # the tool already went back by itself

    def test_checks_that_fail_after_the_install_make_the_tool_go_back(self) -> None:
        self.device.health_code = 503
        environment = self.wired_server(usePackages=True)
        self.assertEqual(self.go(environment, {"server"}), fu.EXIT_FAILED)
        row = self.row(environment, "server")
        self.assertEqual((row["state"], row["error"]), ("rolled_back", "not_healthy"))
        self.assertEqual(self.device.rollbacks, ["server"])
        self.assertEqual(json.loads((self.device.root / "server" / "hydra-umc.project.json").read_text())["version"], "0.9.0")

    def test_the_address_of_a_download_is_only_a_file_of_a_release_on_github(self) -> None:
        target = Path(self.tmp.name) / "x"
        for bad in ("http://github.com/JuanenRac/HYDRA-UMC-SERVER/releases/download/v1.0.0/a.tgz", "https://evil.example/JuanenRac/HYDRA-UMC-SERVER/releases/download/v1.0.0/a.tgz",
                    "https://github.com/JuanenRac/HYDRA-UMC-SERVER/archive/main.tar.gz", "https://github.com/JuanenRac/OTHER/releases/download/v1.0.0/a.tgz",
                    "https://github.com/JuanenRac/HYDRA-UMC-SERVER/releases/download/v1.0.0/../a.tgz"):
            with self.assertRaises(OSError, msg=bad):
                fu.default_download(bad, target)
        self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
