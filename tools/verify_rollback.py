#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - System-file rollback verification
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Prove the real backup/restore rollback mechanism correct without root
or a CM5. A synthetic tmp directory stands in for a real system path,
but every file operation exercised here is the exact same code path
provisioning/rollback.py's `backup`/`restore` CLI runs for real."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
ROLLBACK = ROOT / "provisioning" / "rollback.py"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run((sys.executable, str(ROLLBACK), *args), text=True, capture_output=True, check=False)


def fail(message: str) -> None:
    print(f"ROLLBACK_VERIFY=FAIL {message}", file=sys.stderr)
    raise SystemExit(1)


def expect_pass(name: str, result: subprocess.CompletedProcess[str]) -> None:
    if result.returncode != 0:
        fail(f"{name}: {result.stderr.strip() or result.stdout.strip()}")
    print(f"ROLLBACK_VERIFY=PASS {name}")


def expect_fail(name: str, result: subprocess.CompletedProcess[str]) -> None:
    if result.returncode == 0:
        fail(f"{name} unexpectedly succeeded")
    print(f"ROLLBACK_VERIFY=PASS {name}")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="hydra-umc-rollback-") as temporary:
        root = Path(temporary)
        manifest = root / "manifest.json"
        backups = root / "backups"

        # Case 1: overwriting a real pre-existing file must restore its
        # real original content, not the installer's replacement.
        existing = root / "existing.conf"
        existing.write_text("original content\n", encoding="utf-8")
        expect_pass(
            "backup-existing",
            run("backup", str(existing), "--backup-dir", str(backups), "--manifest", str(manifest)),
        )
        existing.write_text("installer overwrote this\n", encoding="utf-8")
        expect_pass("restore-existing", run("restore", "--manifest", str(manifest)))
        if existing.read_text(encoding="utf-8") != "original content\n":
            fail("restored content does not match the real original")
        print("ROLLBACK_VERIFY=PASS existing-file-content-restored")

        # Case 2: a file the installer creates fresh (didn't exist
        # before) must be deleted on restore, not left behind.
        manifest.unlink()
        fresh = root / "fresh.conf"
        expect_pass(
            "backup-fresh-absent",
            run("backup", str(fresh), "--backup-dir", str(backups), "--manifest", str(manifest)),
        )
        fresh.write_text("installer created this\n", encoding="utf-8")
        expect_pass("restore-fresh", run("restore", "--manifest", str(manifest)))
        if fresh.exists():
            fail("a freshly-created file must be removed on restore, not left behind")
        print("ROLLBACK_VERIFY=PASS fresh-file-removed-on-restore")

        # Case 3: restoring twice in a row must be a real no-op, not an
        # error - proves the mechanism is safe for an operator to re-run.
        expect_pass("restore-idempotent", run("restore", "--manifest", str(manifest)))

        # Case 4: restoring against a missing manifest is a real, honest
        # failure - never a silent no-op that could hide a real mistake.
        expect_fail("restore-missing-manifest", run("restore", "--manifest", str(root / "does-not-exist.json")))

        # Case 5 (OS-01): a manifest whose LAST-restored entry has a real
        # missing backup must abort with ZERO mutations - not restore
        # every earlier entry first and only then discover the problem.
        missing_backup_manifest = root / "missing-backup-manifest.json"
        missing_backups_dir = root / "missing-backups"
        first_target = root / "first.conf"
        second_target = root / "second.conf"
        first_target.write_text("first original\n", encoding="utf-8")
        second_target.write_text("second original\n", encoding="utf-8")
        run("backup", str(first_target), "--backup-dir", str(missing_backups_dir), "--manifest", str(missing_backup_manifest))
        run("backup", str(second_target), "--backup-dir", str(missing_backups_dir), "--manifest", str(missing_backup_manifest))
        # first_target's own real backup is the one restore_all() would
        # reach LAST (most-recent-first order restores second_target
        # before first_target) - deleting it proves the pre-validation
        # pass checks every entry up front, not just the first one it
        # would otherwise process.
        first_backup = missing_backups_dir / "0000-first.conf"
        if not first_backup.is_file():
            fail(f"expected real backup at {first_backup}, setup itself is wrong")
        first_backup.unlink()
        first_target.write_text("first overwritten by installer\n", encoding="utf-8")
        second_target.write_text("second overwritten by installer\n", encoding="utf-8")
        expect_fail("restore-aborts-on-any-missing-backup", run("restore", "--manifest", str(missing_backup_manifest)))
        if second_target.read_text(encoding="utf-8") != "second overwritten by installer\n":
            fail(
                "restore_all() mutated second_target before discovering first_target's missing backup - "
                "a real partial rollback from a manifest problem, not zero mutations"
            )
        print("ROLLBACK_VERIFY=PASS restore-aborts-with-zero-mutations-on-a-missing-backup")

        # Case 6 (OS-01): a real I/O failure that only surfaces DURING the
        # mutating pass (pre-validation cannot catch it - here, a target's
        # own parent path is occupied by a real file, not a directory)
        # must report a real PartialRestoreError naming exactly what was
        # already restored, not an ambiguous, undiagnosed failure.
        partial_manifest = root / "partial-manifest.json"
        partial_backups = root / "partial-backups"
        blocked_parent = root / "blocked"
        will_fail_target = blocked_parent / "deep.conf"
        will_succeed_target = root / "will-succeed.conf"
        blocked_parent.mkdir()
        will_fail_target.write_text("will-fail original\n", encoding="utf-8")
        will_succeed_target.write_text("will-succeed original\n", encoding="utf-8")
        # Submission order: will_fail_target first, will_succeed_target
        # second - restore_all()'s real most-recent-first order then
        # processes will_succeed_target FIRST (a real success worth
        # recording), then will_fail_target (fails).
        run("backup", str(will_fail_target), "--backup-dir", str(partial_backups), "--manifest", str(partial_manifest))
        run("backup", str(will_succeed_target), "--backup-dir", str(partial_backups), "--manifest", str(partial_manifest))
        will_fail_target.write_text("will-fail overwritten\n", encoding="utf-8")
        will_succeed_target.write_text("will-succeed overwritten\n", encoding="utf-8")
        # Real OS-level failure, no permission tricks needed: replace the
        # real directory with a real file of the same name, so a later
        # `target.parent.mkdir(parents=True, exist_ok=True)` for
        # will_fail_target genuinely raises NotADirectoryError.
        shutil.rmtree(blocked_parent)
        blocked_parent.write_text("not a directory anymore\n", encoding="utf-8")
        result = run("restore", "--manifest", str(partial_manifest))
        if result.returncode == 0:
            fail("restore-partial-failure-is-diagnosed unexpectedly succeeded")
        if str(will_succeed_target) not in result.stderr:
            fail(f"expected the real diagnostic to name the successfully-restored target, got: {result.stderr!r}")
        if will_succeed_target.read_text(encoding="utf-8") != "will-succeed original\n":
            fail("will_succeed_target should have been genuinely restored before the later failure")
        print("ROLLBACK_VERIFY=PASS restore-partial-failure-is-diagnosed")

    print("ROLLBACK_VERIFY=PASS checks=8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
