#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - tools/verify_package_install.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Prove the root helper without root, systemd or a network: real packages made with the real packer and signed with a key made here, installed into a temporary
folder by tools/package_install.py and driven by tools/root_helper.py. The commands of the system are recorded by a stand-in. Needs a host that can make links."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("root_helper_under_test", HERE / "root_helper.py")
assert spec and spec.loader
rh = importlib.util.module_from_spec(spec)
sys.modules["root_helper_under_test"] = rh
spec.loader.exec_module(rh)
pi, pc, dr = rh.pi, rh.pc, rh.dr


def can_link() -> bool:
    with tempfile.TemporaryDirectory() as folder:
        try:
            os.symlink(folder, Path(folder) / "link", target_is_directory=True)
        except (OSError, NotImplementedError):
            return False
    return True


class System:
    """The machine as the helper sees it: units that run or not, accounts, packages, journal and health."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.active: set[str] = set()
        self.accounts: set[str] = set()
        self.packages: set[str] = set()
        self.health_code = 200
        self.journal = ""

    def sh(self, argv: list[str], timeout: int = 300) -> tuple[int, str]:
        self.calls.append(list(argv))
        if argv[0] == "id":
            return (0 if argv[-1] in self.accounts else 1), ""
        if argv[0] == "useradd":
            self.accounts.add(argv[-1])
            return 0, ""
        if argv[0] == "dpkg":
            return (0 if argv[-1] in self.packages else 1), ""
        if argv[0] == "journalctl":
            return 0, self.journal
        if argv[:2] == ["systemctl", "is-active"]:
            return (0, "active\n") if argv[2] in self.active else (3, "inactive\n")
        if argv[:2] == ["systemctl", "list-units"]:
            prefix = argv[-1].split("*")[0]
            return 0, "".join(f"{u} loaded active running x\n" for u in sorted(self.active) if u.startswith(prefix))
        return 0, ""

    def ran(self, *words: str) -> list[list[str]]:
        return [c for c in self.calls if c[: len(words)] == list(words)]


@unittest.skipUnless(can_link(), "this host cannot make links")
class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.seed = os.urandom(32)
        self.trust = self.root / "release_key.pub"
        self.trust.write_text(pc.ed25519_public_key(self.seed).hex() + "\n", encoding="ascii")
        self.system = System()
        self.said: list[str] = []
        self.device = pi.Device(self.root / "fs", sh=self.system.sh, health=lambda url: self.system.health_code, sleep=lambda s: None, chown=lambda p, u: None,
                                trusted_key=pc.ed25519_public_key(self.seed).hex(), python_version="3.13", health_timeout_s=4, say=self.said.append)
        self.device.root.mkdir(parents=True)

    def package(self, component: str, version: str, unit_text: str = "", extra: dict[str, str] | None = None, spec_change=None) -> Path:
        repo = self.root / "src" / f"{component}-{version}" / pc.LAYOUT[component][0]
        install = pc.install_spec(component, version)
        files = {"hydra-umc.project.json": json.dumps({"version": version}), "src/hydra_umc_" + component.replace("-", "_") + "/main.py": f"VERSION = '{version}'\n"}
        for source, _target in pc.LAYOUT[component][1]:
            if source.startswith("systemd/"):
                files[source] = unit_text or f"[Service]\nDescription={component} {version}\n"
            elif source.startswith("package/") and component in ("hil-bridge", "orchestrator"):
                files[source] = version
        files.update(extra or {})
        for relative, content in files.items():
            target = repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        for source in pc.LAYOUT[component][2]:
            if not (repo / source).exists():
                (repo / source).mkdir(parents=True)
        if spec_change:
            changed = dict(install)
            spec_change(changed)
            with mock.patch.object(pc, "spec_bytes", lambda *_a: json.dumps(changed).encode()):
                built = pc.build(component, repo, self.root / "out" / version)[0]
        else:
            built = pc.build(component, repo, self.root / "out" / version)[0]
        pc.sign_package(built, self.seed, self.trust)
        return built

    def old_install(self, component: str, version: str) -> Path:
        """A program as the installers left it: a plain folder with its data, and its unit."""
        folder = self.device.root / component
        (folder / "src").mkdir(parents=True)
        (folder / "data").mkdir()
        (folder / "data" / "keep.txt").write_text("mine", encoding="utf-8")
        (folder / "hydra-umc.project.json").write_text(json.dumps({"version": version}), encoding="utf-8")
        self.device.unit_dir.mkdir(parents=True, exist_ok=True)
        (self.device.unit_dir / f"hydra-umc-{component}.service").write_text("[Service]\nDescription=old\n", encoding="utf-8")
        return folder

    def unit(self, name: str) -> str:
        return (self.device.unit_dir / name).read_text(encoding="utf-8")

    def version(self, component: str) -> str:
        return json.loads((self.device.root / component / "hydra-umc.project.json").read_text(encoding="utf-8"))["version"]


class InstallTests(Base):
    def test_a_program_installed_the_old_way_is_moved_updated_and_its_running_unit_restarted(self) -> None:
        self.old_install("datalake", "0.2.6")
        self.system.active.add("hydra-umc-datalake.service")
        done = pi.install(self.package("datalake", "0.2.7"), self.device)
        self.assertEqual((done["mode"], done["version"], done["previous"], done["restarted"]), ("migrated", "0.2.7", "0.2.6", ["hydra-umc-datalake.service"]))
        self.assertEqual(self.version("datalake"), "0.2.7")
        self.assertEqual((self.device.root / "datalake" / "data" / "keep.txt").read_text(encoding="utf-8"), "mine")
        self.assertTrue((self.device.root / "datalake.premigration").is_dir())
        self.assertIn("datalake 0.2.7", self.unit("hydra-umc-datalake.service"))
        self.assertIn("HEALTH_OPEN=1", self.unit("hydra-umc-datalake.service.d/10-health-open.conf"))
        self.assertTrue(self.system.ran("systemctl", "daemon-reload"))
        self.assertEqual(self.system.ran("systemctl", "enable"), [])

    def test_a_stopped_service_is_updated_and_stays_stopped(self) -> None:
        self.old_install("datalake", "0.2.6")
        done = pi.install(self.package("datalake", "0.2.7"), self.device)
        self.assertEqual(done["restarted"], [])
        self.assertEqual(self.version("datalake"), "0.2.7")
        self.assertEqual(self.system.ran("systemctl", "restart"), [])
        self.assertEqual(self.system.ran("systemctl", "start"), [])

    def test_a_failed_health_check_puts_the_program_and_the_units_back(self) -> None:
        self.old_install("datalake", "0.2.6")
        self.system.active.add("hydra-umc-datalake.service")
        self.system.health_code = 500
        with self.assertRaises(pi.InstallError) as caught:
            pi.install(self.package("datalake", "0.2.7"), self.device)
        self.assertEqual((caught.exception.code, caught.exception.rolled_back), ("not_healthy", True))
        self.assertEqual(self.version("datalake"), "0.2.6")
        self.assertIn("Description=old", self.unit("hydra-umc-datalake.service"))
        self.assertFalse((self.device.unit_dir / "hydra-umc-datalake.service.d" / "10-health-open.conf").exists())

    def test_an_import_error_in_the_journal_goes_back(self) -> None:
        self.old_install("datalake", "0.2.6")
        self.system.active.add("hydra-umc-datalake.service")
        self.system.journal = "python3: ModuleNotFoundError: No module named 'x'\n"
        with self.assertRaises(pi.InstallError) as caught:
            pi.install(self.package("datalake", "0.2.7"), self.device)
        self.assertEqual(caught.exception.code, "journal_errors")
        self.assertEqual(self.version("datalake"), "0.2.6")

    def test_an_older_or_the_same_version_is_never_installed(self) -> None:
        self.old_install("datalake", "0.2.7")
        for version in ("0.2.7", "0.2.6"):
            with self.assertRaises(pi.InstallError) as caught:
                pi.install(self.package("datalake", version), self.device)
            self.assertEqual(caught.exception.code, "not_newer")

    def test_a_first_installation_is_off_unless_asked_and_then_makes_account_data_and_unit(self) -> None:
        package = self.package("datalake", "0.2.7")
        with self.assertRaises(pi.InstallError) as caught:
            pi.install(package, self.device)
        self.assertEqual(caught.exception.code, "first_install_off")
        done = pi.install(package, self.device, allow_first_install=True)
        self.assertEqual((done["mode"], done["restarted"]), ("first", []))
        self.assertEqual(self.system.accounts, {"hydra-umc-datalake"})
        self.assertEqual(self.version("datalake"), "0.2.7")
        self.assertTrue((self.device.root / "datalake" / "data").is_dir())
        self.assertTrue((self.device.unit_dir / "hydra-umc-datalake-retention.timer").is_file())

    def test_a_first_installation_that_needs_a_setup_or_a_system_package_says_so(self) -> None:
        with self.assertRaises(pi.InstallError) as caught:
            pi.install(self.package("voice-ui", "0.3.0"), self.device, allow_first_install=True)
        self.assertEqual(caught.exception.code, "needs_first_setup")
        with self.assertRaises(pi.InstallError) as caught:
            pi.install(self.package("vision-streamer", "0.3.0"), self.device, allow_first_install=True)
        self.assertEqual(caught.exception.code, "missing_system_package")

    def test_the_helper_installs_itself_with_the_key_it_trusts_beside_its_tools(self) -> None:
        repo = pc.LAYOUT["helper"][0]
        files = {source: "x\n" for source, _target in pc.LAYOUT["helper"][1] if source != "hydra-umc.project.json"}
        for relative, content in {**files, "hydra-umc.project.json": json.dumps({"version": "0.6.5"})}.items():
            target = self.root / "src" / "helper" / repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        package = pc.build("helper", self.root / "src" / "helper" / repo, self.root / "out" / "helper")[0]
        pc.sign_package(package, self.seed, self.trust)
        done = pi.install(package, self.device, allow_first_install=True)
        self.assertEqual((done["mode"], done["restarted"]), ("first", []))
        installed = self.device.root / "helper"
        self.assertTrue((installed / "tools" / "root_helper.py").is_file())
        self.assertTrue((installed / "config" / "release_key.pub").is_file())
        self.assertTrue((self.device.unit_dir / "hydra-umc-helper.path").is_file())
        self.assertEqual(self.system.ran("systemctl", "enable"), [])

    def test_libraries_for_another_python_are_refused_before_anything_changes(self) -> None:
        self.old_install("anomaly-detector", "0.2.6")
        self.device.python_version = "3.11"
        with self.assertRaises(pi.InstallError) as caught:
            pi.install(self.package("anomaly-detector", "0.2.7"), self.device)
        self.assertEqual(caught.exception.code, "wrong_python")
        self.assertFalse((self.device.root / "anomaly-detector").is_symlink())

    def test_a_package_signed_by_another_key_is_refused(self) -> None:
        self.old_install("datalake", "0.2.6")
        package = self.package("datalake", "0.2.7")
        self.device.trusted_key = pc.ed25519_public_key(os.urandom(32)).hex()
        with self.assertRaises(pi.InstallError) as caught:
            pi.install(package, self.device)
        self.assertEqual(caught.exception.code, "signature_invalid")

    def test_a_signed_description_cannot_name_anything_outside_the_program(self) -> None:
        self.old_install("datalake", "0.2.6")
        changes = [lambda s: s.update(units=["sshd.service"], mainUnit=None), lambda s: s.update(dropins={"ssh.service.d/10-x.conf": "x"}),
                   lambda s: s.update(wrappers=[{"path": "/usr/bin/python3", "content": "x"}]), lambda s: s.update(createIfMissing=[{"path": "/etc/passwd", "content": "x", "mode": "0644"}]),
                   lambda s: s.update(user="root"), lambda s: s.update(stateDirs=["../etc"])]
        for number, change in enumerate(changes):
            with self.subTest(change=number):
                with self.assertRaises(pi.InstallError) as caught:
                    pi.install(self.package("datalake", f"0.3.{number}", spec_change=change), self.device)
                self.assertEqual(caught.exception.code, "bad_package")
                self.assertEqual(self.system.calls, [])

    def test_rollback_by_hand_brings_back_the_release_and_the_units(self) -> None:
        self.old_install("datalake", "0.2.6")
        self.system.active.add("hydra-umc-datalake.service")
        pi.install(self.package("datalake", "0.2.7"), self.device)
        done = pi.rollback("datalake", self.device)
        self.assertEqual((done["version"], self.version("datalake")), ("0.2.6", "0.2.6"))
        self.assertIn("Description=old", self.unit("hydra-umc-datalake.service"))


class HelperTests(Base):
    def setUp(self) -> None:
        super().setUp()
        self.clock = [1_000_000.0]
        self.releases: dict[str, str] = {}
        self.files: dict[str, bytes] = {}
        self.signed = True
        self.state = self.root / "server-data" / "fleet-update" / "state.json"
        self.private = self.root / "private"
        self.secret_file = self.root / "helper.totp"
        self.secret = rh.totp_enroll(self.secret_file)
        self.door = rh.Door(self.private, self.secret_file, now=lambda: self.clock[0])
        self.settings = dict(rh.DEFAULTS, enabled=True, minFreeMb=1)
        self.helper = rh.Helper(self.state, self.device, self.settings, self.door, self.private / "downloads", http=self.http, fetch=self.fetch, now=lambda: self.clock[0],
                                free_mb=lambda: 10_000)

    def publish(self, component: str, version: str) -> None:
        package = self.package(component, version)
        self.releases[pc.LAYOUT[component][0]] = version
        for name in rh.package_files(component, version):
            self.files[name] = (package.parent / name).read_bytes()

    def http(self, url: str):
        repository = url.split("/repos/JuanenRac/")[1].split("/")[0]
        version = self.releases[repository]
        component = repository.removeprefix("HYDRA-UMC-").lower()
        assets = [{"name": n} for n in rh.package_files(component, version)] if self.signed else []
        return {"tag_name": "v" + version, "assets": assets}

    def fetch(self, url: str, destination: Path) -> None:
        self.assertTrue(url.startswith("https://github.com/JuanenRac/HYDRA-UMC-"))
        destination.write_bytes(self.files[url.rsplit("/", 1)[1]])

    def report(self) -> dict:
        return json.loads(self.state.read_text(encoding="utf-8"))

    def code(self) -> str:
        return rh.totp_code(self.secret, int(self.clock[0] // 30))

    def request(self, command: str, **fields) -> int:
        self.state.parent.mkdir(parents=True, exist_ok=True)
        (self.state.parent / "request.json").write_text(json.dumps({"v": 1, "id": "abc1", "command": command, "names": [], **fields}), encoding="utf-8")
        code = self.helper.handle("request.json")
        self.assertFalse((self.state.parent / "request.json").exists())
        self.assertEqual(json.loads((self.state.parent / "state.json.done").read_text(encoding="utf-8")), {"id": "abc1", "command": command, "exit": code})
        return code

    def prepare(self) -> str:
        self.old_install("datalake", "0.2.6")
        self.publish("datalake", "0.2.7")
        self.assertEqual(self.request("plan"), 0)
        return self.report()["planId"]

    def test_plan_lists_the_installed_programs_and_what_has_no_signed_package(self) -> None:
        self.old_install("datalake", "0.2.6")
        self.releases["HYDRA-UMC-DATALAKE"] = "0.2.7"
        self.signed = False
        self.request("plan")
        rows = self.report()["services"]
        self.assertEqual([(r["name"], r["installed"], r["latest"], r["action"], r["reason"]) for r in rows], [("datalake", "0.2.6", "v0.2.7", "skip", "no_signed_package")])

    def test_two_steps_and_a_code_then_the_update_runs(self) -> None:
        plan_id = self.prepare()
        self.assertEqual(self.request("run", planId=plan_id, code=self.code()), 0)
        report = self.report()
        self.assertEqual((report["state"], report["services"][0]["state"], report["services"][0]["installed"]), ("done", "done", "0.2.7"))
        self.assertEqual(self.version("datalake"), "0.2.7")

    def test_without_the_identifier_of_the_look_nothing_is_applied(self) -> None:
        self.prepare()
        self.assertEqual(self.request("run", code=self.code()), 3)
        self.assertEqual(self.report()["error"], "confirmation_needed")
        self.assertEqual(self.version("datalake"), "0.2.6")

    def test_a_wrong_code_is_refused_locks_after_five_and_a_code_works_once(self) -> None:
        plan_id = self.prepare()
        for _attempt in range(5):
            self.assertEqual(self.request("run", planId=plan_id, code="000000" if self.code() != "000000" else "111111"), 3)
            self.assertEqual(self.report()["error"], "totp_invalid")
            plan_id = self.report()["planId"]
        self.request("run", planId=plan_id, code=self.code())
        self.assertEqual(self.report()["error"], "totp_locked")
        self.clock[0] += 3600
        used = self.code()
        self.assertEqual(self.door.check_code(used), "")
        self.assertEqual(self.door.check_code(used), "totp_invalid")
        self.assertEqual(self.version("datalake"), "0.2.6")

    def test_an_old_look_or_a_release_that_changed_stops_the_run(self) -> None:
        plan_id = self.prepare()
        self.clock[0] += 16 * 60
        self.request("run", planId=plan_id, code=self.code())
        self.assertEqual(self.report()["error"], "plan_old")
        plan_id = self.report()["planId"]
        self.publish("datalake", "0.2.8")
        self.clock[0] += 60
        self.request("run", planId=plan_id, code=self.code())
        self.assertEqual(self.report()["error"], "plan_changed")
        self.assertEqual(self.version("datalake"), "0.2.6")

    def test_rollback_needs_the_same_two_steps(self) -> None:
        plan_id = self.prepare()
        self.request("run", planId=plan_id, code=self.code())
        self.clock[0] += 60
        self.request("plan")
        plan_id = self.report()["planId"]
        self.request("rollback", names=["datalake"], code=self.code())
        self.assertEqual(self.version("datalake"), "0.2.7")
        self.clock[0] += 60
        self.request("plan")
        self.assertEqual(self.request("rollback", names=["datalake"], planId=self.report()["planId"], code=self.code()), 0)
        self.assertEqual(self.version("datalake"), "0.2.6")

    def test_the_server_is_last_and_the_first_failure_stops_the_run(self) -> None:
        self.assertEqual(rh.ORDER[-1], "server")
        self.old_install("datalake", "0.2.6")
        self.old_install("detection-hef", "0.2.0")
        self.publish("datalake", "0.2.7")
        self.publish("detection-hef", "0.2.1")
        self.files["hydra-datalake-0.2.7.tgz"] = b"changed on the way"
        self.request("plan")
        self.assertEqual(self.request("run", planId=self.report()["planId"], code=self.code()), 2)
        rows = {r["name"]: r for r in self.report()["services"]}
        self.assertEqual((rows["datalake"]["state"], rows["datalake"]["error"], rows["detection-hef"]["state"]), ("failed", "signature_invalid", "waiting"))

    def test_a_request_is_cut_down_to_its_fields(self) -> None:
        self.assertEqual(rh.parse_request(b"x" * 5000)[1], "too long")
        self.assertEqual(rh.parse_request(b'{"v":1,"id":"a","command":"shell"}')[1], "bad command")
        self.assertEqual(rh.parse_request(b'{"v":1,"id":"a","command":"run","names":["a;b"]}')[1], "bad names")
        body = rh.parse_request(b'{"v":1,"id":"a","command":"plan","planId":"../x","code":"12","extra":1}')[0]
        self.assertEqual((body["planId"], body["code"], "extra" in body), ("", "", False))


class SwitchTests(unittest.TestCase):
    def test_everything_is_off_until_root_says_otherwise(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            self.assertFalse(rh.load_settings(Path(folder) / "helper.json")["enabled"])
            (Path(folder) / "helper.json").write_text("{not json", encoding="utf-8")
            settings = rh.load_settings(Path(folder) / "helper.json")
            self.assertEqual((settings["enabled"], settings["requireTotp"], settings["allowFirstInstall"]), (False, True, False))

    def test_the_one_time_code_is_the_one_of_rfc_6238(self) -> None:
        # the SHA-1 test secret of RFC 6238 appendix B, six digits of its eight
        self.assertEqual(rh.totp_code("GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ", 59 // 30), "287082")


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=1).result
    print(f"PACKAGE_INSTALL_VERIFY={'PASS' if result.wasSuccessful() else 'FAIL'} tests={result.testsRun} skipped={len(result.skipped)}")
    sys.exit(0 if result.wasSuccessful() else 1)
