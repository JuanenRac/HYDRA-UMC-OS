#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - Negative CM5 preflight verification
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Ensure unsafe CM5 installation plans fail before they can be applied."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PREFLIGHT = ROOT / "provisioning" / "preflight_cm5.py"


def expect_failure(name: str, *arguments: str) -> None:
    result = subprocess.run(
        (sys.executable, str(PREFLIGHT), *arguments), cwd=ROOT, text=True, capture_output=True, check=False
    )
    if result.returncode == 0:
        raise SystemExit(f"PREFLIGHT_NEGATIVE=FAIL {name} unexpectedly passed")
    print(f"PREFLIGHT_NEGATIVE=PASS {name}")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="hydra-umc-preflight-") as temporary:
        directory = Path(temporary)
        bad_config = directory / "bad-config.json"
        bad_config.write_text("{}", encoding="utf-8")
        expect_failure("invalid-config", "--config", str(bad_config), "--skip-sdk")

        bad_identity = directory / "bad-identity.json"
        identity = json.loads((ROOT / "config" / "identity.example.json").read_text(encoding="utf-8"))
        identity["administrator"] = "wrong-user"
        bad_identity.write_text(json.dumps(identity), encoding="utf-8")
        expect_failure("identity-mismatch", "--identity", str(bad_identity), "--skip-sdk")

        expect_failure("missing-sdk", "--sdk-root", str(directory / "missing-sdk"))
        expect_failure(
            "missing-control-server",
            "--profile", str(ROOT / "config" / "profiles" / "control.json"),
            "--server-root", str(directory / "missing-server"),
            "--skip-sdk",
        )
    print("PREFLIGHT_NEGATIVE=PASS checks=4")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
