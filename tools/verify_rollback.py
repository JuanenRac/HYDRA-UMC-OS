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

    print("ROLLBACK_VERIFY=PASS checks=6")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
