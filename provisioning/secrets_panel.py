#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - provisioning/secrets_panel.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The secrets and permissions panel of a node, as data for STUDIO and the operations agent.

    python3 secrets_panel.py --json [--root DIR]      the panel as JSON
    python3 secrets_panel.py --lines [--root DIR]     one RUNTIME_CHECK line per file (what verify_cm5_runtime.sh --secrets prints)
    python3 secrets_panel.py --wrap-runtime RC [--panel FILE]   turn the lines of verify_cm5_runtime.sh (stdin) into JSON

It looks at the files of the folder of the secrets (config/secrets_policy.json: the folder, the name patterns, the owner, the
group prefix and the loosest mode allowed) and reports owner, group and mode with a verdict for each. It never opens a file,
so no value of a secret is read or printed. Read-only. Standard library only.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import stat as stat_module
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
POLICY_FILE = HERE.parent / "config" / "secrets_policy.json"
FORMAT = "hydra-secrets-panel/1"
LINE = re.compile(r"^RUNTIME_CHECK=(PASS|FAIL|SKIP) (.*)$")
SUMMARY = re.compile(r"^CM5_RUNTIME=(PASS|FAIL)\b(.*)$")


def load_policy(path: Path = POLICY_FILE) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy.get("format") != "hydra-secrets-policy/1":
        raise ValueError(f"{path} is not a hydra-secrets-policy/1 file")
    int(str(policy["max_mode"]), 8)
    return policy  # type: ignore[no-any-return]


def _names(st: os.stat_result) -> tuple[str, str]:
    try:
        import grp
        import pwd

        return pwd.getpwuid(st.st_uid).pw_name, grp.getgrgid(st.st_gid).gr_name
    except (ImportError, KeyError):
        return str(st.st_uid), str(st.st_gid)


def judge(name: str, owner: str, group: str, mode: int, size: int, policy: dict[str, Any]) -> tuple[str, list[str]]:
    """The verdict ("ok", "warn" or "fail") and the reasons for one file."""
    fail: list[str] = []
    warn: list[str] = []
    allowed = int(str(policy["max_mode"]), 8)
    if mode & ~allowed & 0o777:
        (fail if mode & 0o007 and policy["world_access_is_failure"] else warn).append(f"mode {mode & 0o777:03o} is looser than {policy['max_mode']}")
    if owner != policy["expected_owner"]:
        fail.append(f"owner is {owner}, expected {policy['expected_owner']}")
    if not group.startswith(str(policy["group_prefix"])) and group != policy["expected_owner"]:
        (fail if policy["wrong_group_is_failure"] else warn).append(f"group {group} does not start with {policy['group_prefix']}")
    if size == 0 and policy["empty_file_is_warning"]:
        warn.append("file is empty")
    return ("fail" if fail else "warn" if warn else "ok"), fail + warn


def scan(root: Path | None = None, policy: dict[str, Any] | None = None, *, names: Callable[[os.stat_result], tuple[str, str]] = _names) -> dict[str, Any]:
    policy = policy or load_policy()
    folder = root or Path(str(policy["directory"]))
    files: list[dict[str, Any]] = []
    if folder.is_dir():
        for path in sorted(folder.iterdir()):
            if path.is_symlink() or not path.is_file() or not any(fnmatch.fnmatch(path.name, p) for p in policy["patterns"]):
                continue
            st = path.stat()
            owner, group = names(st)
            mode = stat_module.S_IMODE(st.st_mode)
            status, reasons = judge(path.name, owner, group, mode, st.st_size, policy)
            files.append({"path": str(path), "owner": owner, "group": group, "mode": f"{mode:03o}", "status": status, "problems": reasons})
    counts = {state: sum(1 for f in files if f["status"] == state) for state in ("ok", "warn", "fail")}
    return {"format": FORMAT, "directory": str(folder), "present": folder.is_dir(), "files": files, "summary": counts, "read_only": True}


def lines(panel: dict[str, Any]) -> list[str]:
    out = []
    if not panel["present"]:
        return [f"RUNTIME_CHECK=SKIP secrets folder {panel['directory']} does not exist"]
    for item in panel["files"]:
        word = "FAIL" if item["status"] == "fail" else "PASS"
        detail = f" ({'; '.join(item['problems'])})" if item["problems"] else ""
        out.append(f"RUNTIME_CHECK={word} secret file {item['path']} {item['owner']}:{item['group']}:{item['mode']}{detail}")
    return out


def wrap_runtime(text: str, returncode: int, panel: dict[str, Any] | None) -> dict[str, Any]:
    """The output of verify_cm5_runtime.sh as JSON: every check with its result, the final verdict and, when asked for, the panel."""
    checks = []
    summary = ""
    for raw in text.splitlines():
        found = LINE.match(raw.strip())
        if found:
            checks.append({"result": found.group(1), "check": found.group(2)})
            continue
        final = SUMMARY.match(raw.strip())
        if final:
            summary = raw.strip()
    result = {
        "format": "hydra-runtime-report/1", "ok": returncode == 0 and bool(summary) and summary.startswith("CM5_RUNTIME=PASS"),
        "summary": summary, "checks": checks, "read_only": True,
    }
    if panel is not None:
        result["secrets"] = panel
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--json", action="store_true")
    mode.add_argument("--lines", action="store_true")
    mode.add_argument("--wrap-runtime", metavar="RC", type=int)
    parser.add_argument("--root", type=Path, help="folder to look at instead of the one of the policy (for tests)")
    parser.add_argument("--panel", action="store_true", help="with --wrap-runtime: add the panel of the secrets")
    args = parser.parse_args(argv)
    panel = scan(args.root) if (args.json or args.lines or args.panel) else None
    if args.json:
        print(json.dumps(panel, indent=2, sort_keys=True))
        return 0
    if args.lines:
        print("\n".join(lines(panel or {})))
        return 1 if panel and panel["summary"]["fail"] else 0
    print(json.dumps(wrap_runtime(sys.stdin.read(), args.wrap_runtime, panel), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
