#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - Component links check
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Prove tools/component_links.py in temporary folders, with no systemd: off by default and a dry run that changes nothing, the migration of a running program to the layout
of deploy_release.py with its data kept once and linked, a signed package installed and gone back from afterwards without touching the data, a start or a health check that
fails putting everything back by itself, the way back by hand carrying the data written since, and every refusal."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


cl = load("component_links")
dr = cl.dr
pc = dr.package_component
SEED = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
PUBLIC = "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"


def can_link() -> bool:
    with tempfile.TemporaryDirectory() as folder:
        try:
            os.symlink(folder, os.path.join(folder, "l"), target_is_directory=True)
            return True
        except (OSError, NotImplementedError):
            return False


@unittest.skipUnless(can_link(), "this host cannot make links")
class LinkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "opt"
        self.components = self.root / ".components"
        self.components.mkdir(parents=True)
        self.program = self.root / "server"
        for relative, text in {"dist/server.cjs": "old code", "package.json": "{}", "hydra-umc.project.json": json.dumps({"version": "0.8.0.0"}),
                               "data/store.db": "records", "workspace/job.txt": "job"}.items():
            target = self.program / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        self.calls: list[str] = []
        self.failing: set[str] = set()
        self.settings = {"enabled": True, "stateDirs": ["data", "models", "workspace"], "stopCommand": "stop", "startCommand": "start", "healthCommand": "health"}
        self.trust = self.base / "release_key.pub"
        self.trust.write_text(PUBLIC + "\n", encoding="ascii")
        self.repo = self.base / "HYDRA-UMC-SERVER"

    def run_command(self, command: str, values: dict) -> bool:
        self.calls.append(command)
        return command not in self.failing

    def migrate(self, apply: bool = True, **kwargs):
        return cl.migrate(self.root, self.components, "server", apply=apply, settings=kwargs.pop("settings", self.settings), unit="u.service", run=self.run_command, say=lambda _m: None, **kwargs)

    def package(self, version: str):
        for relative, text in {"dist/server.cjs": f"new code {version}", "public/index.html": "<html>", "package.json": "{}", "package-lock.json": "{}",
                               "systemd/hydra-umc-server.service": "[Unit]"}.items():
            target = self.repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        (self.repo / "hydra-umc.project.json").write_text(json.dumps({"version": version}), encoding="utf-8")
        package, _v, _d = pc.build("server", self.repo, self.base / "out")
        pc.sign_package(package, SEED, self.trust)
        return package

    # ---- off by default ---------------------------------------------------------------------------------------------------------------------------
    def test_without_the_switch_nothing_is_changed_even_with_apply_and_the_default_file_means_off(self) -> None:
        self.assertFalse(cl.load_wiring(self.components)["enabled"])
        off = dict(self.settings, enabled=False)
        with self.assertRaisesRegex(cl.LinkError, "switched off"):
            self.migrate(settings=off)
        self.assertTrue(self.program.is_dir() and not self.program.is_symlink())
        self.assertEqual(self.calls, [])
        self.assertFalse((self.components / "server").exists())

    def test_a_dry_run_says_what_it_would_do_and_changes_nothing(self) -> None:
        said: list[str] = []
        plan = cl.migrate(self.root, self.components, "server", apply=False, settings=self.settings, run=self.run_command, say=said.append)
        self.assertEqual((plan["release"], plan["stateDirs"], plan["applied"]), ("0.8.0.0-1", ["data", "workspace"], False))
        self.assertIn("would migrate server", said[0])
        self.assertEqual(self.calls, [])
        self.assertFalse((self.components / "server").exists())
        self.assertTrue((self.program / "data" / "store.db").is_file())

    def test_the_settings_file_is_read_defensively(self) -> None:
        path = self.components / "wiring.json"
        warnings: list[str] = []
        path.write_text(json.dumps({"enabled": "yes", "stateDirs": ["../x"], "stopCommand": 5}), encoding="utf-8")
        loaded = cl.load_wiring(self.components, warnings.append)
        self.assertEqual((loaded["enabled"], loaded["stateDirs"], loaded["stopCommand"]), (False, cl.DEFAULT_STATE_DIRS, ""))
        path.write_text(json.dumps({"enabled": True, "stateDirs": ["data", "media"], "healthCommand": " ok "}), encoding="utf-8")
        loaded = cl.load_wiring(self.components, warnings.append)
        self.assertEqual((loaded["enabled"], loaded["stateDirs"], loaded["healthCommand"]), (True, ["data", "media"], "ok"))
        path.write_text("{bad", encoding="utf-8")
        self.assertFalse(cl.load_wiring(self.components, warnings.append)["enabled"])

    # ---- the migration ----------------------------------------------------------------------------------------------------------------------------
    def test_a_program_runs_from_its_link_with_the_same_path_and_its_data_kept_once(self) -> None:
        self.migrate()
        self.assertEqual(self.calls[0], "stop")
        self.assertEqual(self.calls[-1], "health")
        self.assertTrue(self.program.is_symlink())
        self.assertTrue(cl.wired(self.root, self.components, "server"))
        self.assertEqual((self.program / "dist" / "server.cjs").read_text(encoding="utf-8"), "old code")
        self.assertEqual((self.program / "data" / "store.db").read_text(encoding="utf-8"), "records")
        self.assertTrue((self.components / "server" / "state" / "data" / "store.db").is_file())
        self.assertTrue((self.components / "server" / "releases" / "0.8.0.0-1" / "data").is_symlink())
        self.assertTrue((self.root / "server.premigration" / "dist" / "server.cjs").is_file())
        self.assertEqual(dr.Component(self.components, "server").state()["current"]["version"], "0.8.0.0")
        # what the program writes through its path lands in the one place
        (self.program / "data" / "new.db").write_text("later", encoding="utf-8")
        self.assertTrue((self.components / "server" / "state" / "data" / "new.db").is_file())
        info = cl.status(self.root, self.components, "server")
        self.assertEqual((info["wired"], info["path"], info["current"], info["premigration"], info["stateDirs"]), (True, "link", "0.8.0.0", True, ["data", "workspace"]))

    def test_a_signed_package_replaces_the_program_and_goes_back_without_touching_the_data(self) -> None:
        self.migrate()
        settings = dict(dr.DEFAULTS, stateDirs=["data", "workspace"])
        dr.install(self.package("0.9.0.0"), self.components, trusted_key=PUBLIC, settings=settings, sleep=lambda _s: None)
        self.assertEqual((self.program / "dist" / "server.cjs").read_text(encoding="utf-8"), "new code 0.9.0.0")
        self.assertEqual((self.program / "data" / "store.db").read_text(encoding="utf-8"), "records")
        (self.program / "data" / "after.db").write_text("written by the new program", encoding="utf-8")
        dr.rollback(self.components, "server", settings=settings, sleep=lambda _s: None)
        self.assertEqual((self.program / "dist" / "server.cjs").read_text(encoding="utf-8"), "old code")
        self.assertEqual((self.program / "data" / "after.db").read_text(encoding="utf-8"), "written by the new program")
        self.assertEqual(dr.Component(self.components, "server").state()["current"]["version"], "0.8.0.0")

    def test_without_state_dirs_in_the_deploy_settings_a_release_gets_no_links_as_before(self) -> None:
        self.migrate()
        dr.install(self.package("0.9.0.0"), self.components, trusted_key=PUBLIC, settings=dict(dr.DEFAULTS), sleep=lambda _s: None)
        self.assertFalse((self.components / "server" / "releases" / "0.9.0.0-1" / "data").exists())
        warnings: list[str] = []
        (self.components / "deploy.json").write_text(json.dumps({"stateDirs": ["data", "../x"]}), encoding="utf-8")
        self.assertEqual(dr.load_settings(self.components, warnings.append)["stateDirs"], [])
        self.assertEqual(len(warnings), 1)
        (self.components / "deploy.json").write_text(json.dumps({"stateDirs": ["data"]}), encoding="utf-8")
        self.assertEqual(dr.load_settings(self.components, warnings.append)["stateDirs"], ["data"])

    # ---- failures put everything back --------------------------------------------------------------------------------------------------------------
    def check_untouched(self) -> None:
        self.assertTrue(self.program.is_dir() and not self.program.is_symlink())
        self.assertEqual((self.program / "dist" / "server.cjs").read_text(encoding="utf-8"), "old code")
        self.assertEqual((self.program / "data" / "store.db").read_text(encoding="utf-8"), "records")
        self.assertEqual((self.program / "workspace" / "job.txt").read_text(encoding="utf-8"), "job")
        self.assertFalse((self.components / "server").exists())
        self.assertFalse((self.root / "server.premigration").exists())

    def test_a_program_that_does_not_stop_is_not_touched(self) -> None:
        self.failing.add("stop")
        with self.assertRaises(cl.LinkError) as caught:
            self.migrate()
        self.assertEqual(caught.exception.code, cl.EXIT_UNDONE)
        self.check_untouched()

    def test_a_program_that_does_not_start_from_its_link_is_put_back_as_it_was(self) -> None:
        self.failing.add("start")
        with self.assertRaises(cl.LinkError) as caught:
            self.migrate()
        self.assertEqual(caught.exception.code, cl.EXIT_UNDONE)
        self.check_untouched()
        self.assertEqual(self.calls.count("start"), 2)        # once from the link, once again on the old folder

    def test_a_health_check_that_fails_is_put_back_as_it_was(self) -> None:
        self.failing.add("health")
        original = cl.time.sleep
        cl.time.sleep = lambda _s: None
        try:
            with self.assertRaises(cl.LinkError) as caught:
                self.migrate()
        finally:
            cl.time.sleep = original
        self.assertEqual(caught.exception.code, cl.EXIT_UNDONE)
        self.assertIn("health check", str(caught.exception))
        self.check_untouched()

    def test_a_copy_that_fails_in_the_middle_puts_the_state_back(self) -> None:
        original = cl.shutil.copytree
        cl.shutil.copytree = lambda *a, **k: (_ for _ in ()).throw(OSError("disk full"))
        try:
            with self.assertRaises(cl.LinkError):
                self.migrate()
        finally:
            cl.shutil.copytree = original
        self.check_untouched()

    # ---- the way back by hand ---------------------------------------------------------------------------------------------------------------------
    def test_going_back_by_hand_carries_the_data_written_since_and_keeps_the_releases(self) -> None:
        self.migrate()
        (self.program / "data" / "since.db").write_text("written while linked", encoding="utf-8")
        said: list[str] = []
        dry = cl.unmigrate(self.root, self.components, "server", apply=False, settings=self.settings, run=self.run_command, say=said.append)
        self.assertFalse(dry["applied"])
        self.assertTrue(cl.wired(self.root, self.components, "server"))
        cl.unmigrate(self.root, self.components, "server", apply=True, settings=self.settings, run=self.run_command, say=lambda _m: None)
        self.assertTrue(self.program.is_dir() and not self.program.is_symlink())
        self.assertEqual((self.program / "dist" / "server.cjs").read_text(encoding="utf-8"), "old code")
        self.assertEqual((self.program / "data" / "since.db").read_text(encoding="utf-8"), "written while linked")
        self.assertEqual((self.program / "data" / "store.db").read_text(encoding="utf-8"), "records")
        self.assertFalse((self.root / "server.premigration").exists())
        self.assertTrue([p for p in self.components.glob("server.unwired_*")])

    def test_every_refusal_changes_nothing(self) -> None:
        for bad in ("../x", "Server", "", "a b"):
            with self.assertRaises(cl.LinkError):
                cl.migrate(self.root, self.components, bad, apply=True, settings=self.settings, run=self.run_command, say=lambda _m: None)
        with self.assertRaisesRegex(cl.LinkError, "not a folder"):
            cl.migrate(self.root, self.components, "missing", apply=True, settings=self.settings, run=self.run_command, say=lambda _m: None)
        (self.root / "server.premigration").mkdir()
        with self.assertRaisesRegex(cl.LinkError, "premigration"):
            self.migrate()
        (self.root / "server.premigration").rmdir()
        self.migrate()
        with self.assertRaisesRegex(cl.LinkError, "already a link"):
            self.migrate()
        with self.assertRaisesRegex(cl.LinkError, "does not run from its link"):
            cl.unmigrate(self.root, self.components, "datalake", apply=True, settings=self.settings, run=self.run_command, say=lambda _m: None)

    def test_the_command_line_reports_and_returns_the_exit_codes(self) -> None:
        def call(*argv: str) -> tuple[int, str, str]:
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = cl.main([*argv, "--root", str(self.root)])
            return code, out.getvalue(), err.getvalue()
        code, out, _ = call("status", "server")
        self.assertEqual((code, json.loads(out.split("LINKS=")[0])["wired"]), (0, False))
        code, out, _ = call("migrate", "server")
        self.assertEqual(code, 0)
        self.assertIn("LINKS=PASS", out)
        self.assertTrue(self.program.is_dir() and not self.program.is_symlink())
        code, _, err = call("migrate", "server", "--apply")
        self.assertEqual(code, cl.EXIT_REFUSED)
        self.assertIn("LINKS=FAIL", err)
        self.assertIn("switched off", err)


if __name__ == "__main__":
    unittest.main()
