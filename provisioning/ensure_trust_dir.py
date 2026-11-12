#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - provisioning/ensure_trust_dir.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Creates the directory of the trust store of a CM5 (/etc/hydra-umc/trust: owned by root, mode 0700) with the function of HYDRA-UMC-DEV-SERVER.

The rules of that directory (who owns it, its mode, that it lives outside the data of any program) belong to HYDRA-UMC-DEV-SERVER, which is the only
program that reads the store and applies a signed rotation to it; this script does not repeat them, it loads `ensure_trust_dir` from
`hydra_umc_dev_server.trust_rotation` and calls it. Where that program is looked for, in this order:

    --dev-server-src DIR            a folder that holds the package hydra_umc_dev_server (its `src`)
    HYDRA_UMC_DEV_SERVER_SRC        the same, from the environment
    /opt/hydra-umc/dev-server/src   where a deployment puts it
    ../../HYDRA-UMC-DEV-SERVER/src  a checkout next to this one

Without --apply nothing is created and the script only says what it would do. Exit status: 0 done (or dry run), 2 a refusal (not root, a bad
argument, the function refused), 3 HYDRA-UMC-DEV-SERVER was not found: the installer goes on, because the directory is only needed by the program that
reads the store, which creates it itself when it is deployed by root.
"""
from __future__ import annotations

import argparse
import importlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCES = (Path("/opt/hydra-umc/dev-server/src"), ROOT.parent / "HYDRA-UMC-DEV-SERVER" / "src")
NOT_FOUND = 3


def candidate_sources(explicit: str | None, environ: dict[str, str]) -> list[Path]:
    found: list[Path] = []
    for value in (explicit, environ.get("HYDRA_UMC_DEV_SERVER_SRC")):
        if value:
            found.append(Path(value))
    found.extend(DEFAULT_SOURCES)
    return found


def load_ensure_trust_dir(sources: list[Path]):
    """The function and the folder it came from, or None when no folder holds the package."""
    for source in sources:
        if (source / "hydra_umc_dev_server" / "trust_rotation.py").is_file():
            sys.path.insert(0, str(source))
            try:
                module = importlib.import_module("hydra_umc_dev_server.trust_rotation")
            finally:
                sys.path.remove(str(source))
            return module.ensure_trust_dir, module.TRUST_DIR, source
    return None


def main(argv: list[str] | None = None, environ: dict[str, str] | None = None) -> int:
    environ = dict(os.environ) if environ is None else environ
    parser = argparse.ArgumentParser(description="Create the root-only directory of the trust store with the function of HYDRA-UMC-DEV-SERVER.")
    parser.add_argument("--apply", action="store_true", help="create the directory (without it, only say what would be done)")
    parser.add_argument("--dev-server-src", help="the folder that holds the package hydra_umc_dev_server")
    parser.add_argument("--dir", help="another directory than the one DEV-SERVER fixes (for a test)")
    args = parser.parse_args(argv)
    loaded = load_ensure_trust_dir(candidate_sources(args.dev_server_src, environ))
    if loaded is None:
        print("HYDRA-UMC-DEV-SERVER was not found; the trust directory is not created now (it is created by root when that program is deployed).", file=sys.stderr)
        return NOT_FOUND
    ensure, default_dir, source = loaded
    target = Path(args.dir) if args.dir else Path(default_dir)
    if not args.apply:
        print(f"Dry run: would create {target} (owned by root, mode 0700) with ensure_trust_dir from {source}.")
        return 0
    try:
        ensure(target)
    except Exception as error:  # the function names its own refusal (not root, ...)
        print(f"The trust directory was not created: {error}", file=sys.stderr)
        return 2
    print(f"Trust directory ready: {target} (owned by root, mode 0700).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
