#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - Secrets and permissions panel verification
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Prove provisioning/secrets_panel.py: the verdict of a file by owner, group and mode, a folder scan that never opens a file,
the JSON form of the runtime check and the --json / --secrets switches of verify_cm5_runtime.sh."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("secrets_panel", ROOT / "provisioning" / "secrets_panel.py")
assert spec and spec.loader
panel = importlib.util.module_from_spec(spec)
sys.modules["secrets_panel"] = panel
spec.loader.exec_module(panel)

POLICY = panel.load_policy()
RUNTIME = (ROOT / "provisioning" / "verify_cm5_runtime.sh").read_text(encoding="utf-8")


class SecretsPanelTests(unittest.TestCase):
    def test_a_file_is_judged_by_owner_group_and_mode(self) -> None:
        self.assertEqual(panel.judge("server.env", "root", "hydra-umc-server", 0o640, 10, POLICY), ("ok", []))
        self.assertEqual(panel.judge("a.env", "root", "hydra-umc-a", 0o600, 10, POLICY)[0], "ok")
        status, why = panel.judge("a.env", "root", "hydra-umc-a", 0o644, 10, POLICY)
        self.assertEqual(status, "fail")
        self.assertIn("looser", why[0])
        self.assertEqual(panel.judge("a.env", "root", "hydra-umc-a", 0o660, 10, POLICY)[0], "warn")
        self.assertEqual(panel.judge("a.env", "pi", "hydra-umc-a", 0o640, 10, POLICY)[0], "fail")
        self.assertEqual(panel.judge("a.env", "root", "users", 0o640, 10, POLICY)[0], "warn")
        self.assertEqual(panel.judge("a.env", "root", "hydra-umc-a", 0o640, 0, POLICY)[0], "warn")

    def test_the_scan_lists_matching_files_without_opening_them(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "server.env").write_text("TOKEN=do-not-print-me\n", encoding="utf-8")
            (folder / "notes.txt").write_text("not a secret file", encoding="utf-8")
            report = panel.scan(folder, POLICY, names=lambda st: ("root", "hydra-umc-server"))
            self.assertEqual([Path(f["path"]).name for f in report["files"]], ["server.env"])
            self.assertNotIn("do-not-print-me", json.dumps(report))
            self.assertTrue(report["read_only"])
            self.assertEqual(sum(report["summary"].values()), 1)
            missing = panel.scan(folder / "absent", POLICY)
            self.assertFalse(missing["present"])
            self.assertTrue(panel.lines(missing)[0].startswith("RUNTIME_CHECK=SKIP"))

    def test_failures_become_failing_runtime_lines(self) -> None:
        report = {"present": True, "directory": "/x", "files": [{"path": "/x/a.env", "owner": "root", "group": "g", "mode": "644", "status": "fail", "problems": ["mode 644 is looser than 640"]}],
                  "summary": {"ok": 0, "warn": 0, "fail": 1}}
        self.assertTrue(panel.lines(report)[0].startswith("RUNTIME_CHECK=FAIL secret file /x/a.env root:g:644"))

    def test_the_runtime_output_becomes_json(self) -> None:
        text = "RUNTIME_CHECK=PASS id hydra-umc-agent\nRUNTIME_CHECK=SKIP x is not running\nCM5_RUNTIME=PASS profile=base changes=none\n"
        report = panel.wrap_runtime(text, 0, None)
        self.assertTrue(report["ok"])
        self.assertEqual([c["result"] for c in report["checks"]], ["PASS", "SKIP"])
        self.assertNotIn("secrets", report)
        failed = panel.wrap_runtime("RUNTIME_CHECK=FAIL id x\n", 1, {"summary": {}})
        self.assertFalse(failed["ok"])
        self.assertIn("secrets", failed)

    def test_the_runtime_script_has_the_switches_and_stays_read_only(self) -> None:
        for fragment in ("--secrets) WITH_SECRETS=true", "--json) AS_JSON=true", "secrets_panel.py", "--wrap-runtime"):
            self.assertIn(fragment, RUNTIME)
        self.assertNotIn("chmod", RUNTIME)
        self.assertNotIn("chown", RUNTIME)

    def test_the_policy_is_a_file_not_code(self) -> None:
        self.assertEqual(POLICY["directory"], "/etc/hydra-umc")
        self.assertTrue(POLICY["world_access_is_failure"])


if __name__ == "__main__":
    unittest.main()
