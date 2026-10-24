#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - Optional journals of the installers verification
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The local technician's audit journal and the node watchdog's journal are ON unless the installer is
told otherwise (`--no-audit`, `--no-journal`, or the documented settings file is edited). Static and dry-run
checks only: nothing is installed, no root is needed. When the sibling projects are checked out, the
names the installers write are compared with the ones the projects read."""

from __future__ import annotations

import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TECHNICIAN = ROOT / "provisioning" / "install_local_technician.sh"
HEALING = ROOT / "provisioning" / "install_node_healing.sh"
BASH = shutil.which("bash")


def run(script: Path, *arguments: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    import os

    return subprocess.run([BASH, script.as_posix(), *arguments], capture_output=True, text=True, check=False, env={**os.environ, **(env or {})})


@unittest.skipUnless(BASH, "bash is needed")
class OptionalJournalTests(unittest.TestCase):
    def test_the_scripts_have_valid_syntax(self) -> None:
        for script in (TECHNICIAN, HEALING):
            self.assertEqual(subprocess.run([BASH, "-n", script.as_posix()], capture_output=True, text=True).returncode, 0, script)

    def test_a_dry_run_changes_nothing_and_names_the_option(self) -> None:
        for script, option in ((TECHNICIAN, "--no-audit"), (HEALING, "--no-journal")):
            result = run(script)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Dry-run policy", result.stdout)
            self.assertIn(option, result.stdout)

    def test_an_unknown_option_or_a_bad_value_is_refused(self) -> None:
        for script, variable in ((TECHNICIAN, "HYDRA_UMC_LOCAL_TECHNICIAN_AUDIT"), (HEALING, "HYDRA_UMC_NODE_HEALING_JOURNAL")):
            self.assertEqual(run(script, "--apply", "--nonsense").returncode, 2)
            self.assertEqual(run(script, env={variable: "maybe"}).returncode, 2)

    def test_both_default_to_on_and_can_be_switched_off(self) -> None:
        self.assertIn('AUDIT="${HYDRA_UMC_LOCAL_TECHNICIAN_AUDIT:-on}"', TECHNICIAN.read_text(encoding="utf-8"))
        self.assertIn('JOURNAL="${HYDRA_UMC_NODE_HEALING_JOURNAL:-on}"', HEALING.read_text(encoding="utf-8"))
        for script, option in ((TECHNICIAN, "--no-audit"), (HEALING, "--no-journal")):
            self.assertIn(f"{option})", script.read_text(encoding="utf-8"))

    def test_the_settings_file_is_documented_and_the_line_is_active_unless_switched_off(self) -> None:
        text = TECHNICIAN.read_text(encoding="utf-8")
        self.assertIn("$AUDIT_LINE", text)
        self.assertIn("/etc/hydra-umc-local-technician/local-technician.env", text)
        self.assertIn('echo "$AUDIT_LINE" >>"$SETTINGS_FILE"', text)
        healing = HEALING.read_text(encoding="utf-8")
        self.assertIn("$JOURNAL_LINE", healing)
        self.assertIn("/etc/hydra-umc-node-healing/journal.env", healing)
        self.assertIn('echo "$JOURNAL_LINE" >>"$JOURNAL_ENV"', healing)

    def test_switching_it_off_takes_the_active_line_out_and_keeps_what_was_recorded(self) -> None:
        # the rewrite is a sed that comments the line; it never removes the journal file or its directory
        for script in (TECHNICIAN, HEALING):
            text = script.read_text(encoding="utf-8")
            self.assertIn("sed -i", text)
            self.assertIn("Records already written are kept", text)
            self.assertNotIn("rm -rf /var/lib", text)

    def test_the_names_match_the_projects_when_they_are_checked_out(self) -> None:
        technician = ROOT.parent / "HYDRA-UMC-LOCAL-TECHNICIAN" / "src" / "hydra_umc_local_technician" / "orchestrator" / "audit.py"
        if technician.is_file():
            self.assertIn('"HYDRA_UMC_LOCAL_TECHNICIAN_AUDIT_LOG"', technician.read_text(encoding="utf-8"))
        unit = ROOT.parent / "HYDRA-UMC-NODE-HEALING" / "systemd" / "hydra-umc-node-healing.service"
        if unit.is_file():
            text = unit.read_text(encoding="utf-8")
            self.assertIn("$HYDRA_UMC_NODE_HEALING_JOURNAL_ARGS", text)
            self.assertIn("EnvironmentFile=-/etc/hydra-umc-node-healing/journal.env", text)
            exec_lines = [line for line in text.splitlines() if line.startswith("ExecStart=")]
            self.assertEqual(len(exec_lines), 1)
            self.assertNotIn("--journal /var", exec_lines[0], "the journal must not be hard-wired into the unit")


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=1).result
    if result.wasSuccessful():
        print("OPTIONAL_JOURNALS=PASS")
    sys.exit(0 if result.wasSuccessful() else 1)
