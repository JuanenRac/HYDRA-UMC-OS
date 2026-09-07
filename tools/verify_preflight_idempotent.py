#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - Preflight idempotency verification
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Prove provisioning/preflight_cm5.py is idempotent and genuinely
side-effect-free: running it twice in a row, against the same real
inputs, must produce byte-identical output and touch no file under this
repository - a real, checkable property for a preflight that claims to
be read-only, not just an assertion in a docstring."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PREFLIGHT = ROOT / "provisioning" / "preflight_cm5.py"
EXCLUDED_PARTS = {".git", "__pycache__", ".pytest_cache"}


def snapshot(root: Path) -> dict[str, float]:
    """Real mtimes for every real file under `root` - a read-only script
    must never create or modify any of them between two runs."""
    return {
        str(path): path.stat().st_mtime
        for path in root.rglob("*")
        if path.is_file() and not any(part in EXCLUDED_PARTS for part in path.parts)
    }


def main() -> int:
    before = snapshot(ROOT)
    first = subprocess.run(
        (sys.executable, str(PREFLIGHT), "--skip-sdk"), cwd=ROOT, text=True, capture_output=True, check=False
    )
    second = subprocess.run(
        (sys.executable, str(PREFLIGHT), "--skip-sdk"), cwd=ROOT, text=True, capture_output=True, check=False
    )
    after = snapshot(ROOT)

    if first.returncode != 0 or second.returncode != 0:
        print(
            f"PREFLIGHT_IDEMPOTENT=FAIL preflight itself failed: {first.stderr or second.stderr}",
            file=sys.stderr,
        )
        return 1
    if first.stdout != second.stdout:
        print("PREFLIGHT_IDEMPOTENT=FAIL two consecutive runs produced different output", file=sys.stderr)
        return 1
    if before != after:
        changed = sorted(set(before) ^ set(after) | {k for k in before if before.get(k) != after.get(k)})
        print(f"PREFLIGHT_IDEMPOTENT=FAIL preflight touched real files: {changed}", file=sys.stderr)
        return 1

    print("PREFLIGHT_IDEMPOTENT=PASS runs=2 output=identical files=untouched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
