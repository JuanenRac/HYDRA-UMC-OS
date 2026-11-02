#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - provisioning/hydra_umc_os.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""`hydra-umc-os`: deploy one program of the CM5 the way its installer says, from the table of installers.

    hydra-umc-os plan   [PROJECT]            what the table says (the installer, the unit, the port, the health route, the contract)
    hydra-umc-os deploy PROJECT [--apply]    run the installer of the project: without --apply it only says what it would run
    hydra-umc-os rollback PROJECT            put the previous program back (restart and health check when the unit runs)
    hydra-umc-os status [PROJECT]            the releases kept, the one in use and the history

PROJECT is the repository (HYDRA-UMC-SERVER), its short name (server) or the script (install_server.sh). Only an installer that follows the deployment
contract this tool supports (docs/DEPLOY_CONTRACT.md) is run; any other is refused before anything changes. `deploy --apply` is what the
updater runs after it has promoted a project: the installer keeps the program in use, installs the new one, restarts the unit if it runs, polls its health
route and puts the old program back if it does not come back.

Exit status: 0 deployed (or installed, unit not running, or unchanged); 3 the unit did not hold and the earlier program was put back; 2 refused (unknown project, no
contract, a contract this tool does not support); anything else is the status of the installer. The last line on the standard output is one JSON object.

Standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
RELEASES_ROOT = Path(os.environ.get("HYDRA_UMC_DEPLOY_ROOT", "/opt/hydra-umc/.releases"))
EXIT_REFUSED = 2
EXIT_ROLLED_BACK = 3


class Refused(Exception):
    pass


def load_plan(directory: Path) -> dict[str, Any]:
    path = directory / "install_plan.json"
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise Refused(f"the table of installers {path} cannot be read: {error}") from error
    if not isinstance(plan, dict) or not isinstance(plan.get("installers"), list) or not isinstance(plan.get("supported_contract"), int):
        raise Refused(f"{path} is not a table of installers this tool understands")
    return plan


def find(plan: dict[str, Any], project: str) -> dict[str, Any]:
    wanted = project.strip().lower()
    for row in plan["installers"]:
        names = {str(row.get("script", "")).lower(), str(row.get("source") or "").lower(), str(row.get("script", "")).lower().removeprefix("install_").removesuffix(".sh").replace("_", "-"),
                 str(row.get("target") or "").rsplit("/", 1)[-1].lower()}
        if wanted in names and row.get("source"):
            return row
    raise Refused(f"{project!r} is not a project of the table (try: hydra-umc-os plan)")


def deployable(plan: dict[str, Any], row: dict[str, Any]) -> None:
    if row.get("contract") is None:
        reason = row.get("deploy_exempt")
        raise Refused(f"{row['script']} does not follow the deployment contract" + (f" ({reason})" if reason else ""))
    if row["contract"] != plan["supported_contract"]:
        raise Refused(f"{row['script']} follows the deployment contract {row['contract']} and this tool supports {plan['supported_contract']}")


def summary(row: dict[str, Any]) -> dict[str, Any]:
    keys = ("script", "source", "target", "user", "unit", "port", "health_path", "contract", "deploy_exempt")
    return {key: row.get(key) for key in keys}


def deploy(directory: Path, project: str, *, apply: bool, runner: Any = subprocess.run) -> tuple[int, dict[str, Any]]:
    plan = load_plan(directory)
    row = find(plan, project)
    deployable(plan, row)
    script = directory / str(row["script"])
    if not script.is_file():
        raise Refused(f"{script} is not there")
    report: dict[str, Any] = {**summary(row), "apply": apply}
    if not apply:
        report["would_run"] = ["bash", str(script), "--apply"]
        report["result"] = "dry-run"
        return 0, report
    with tempfile.TemporaryDirectory(prefix="hydra-deploy-") as scratch:
        result_file = Path(scratch) / "result.json"
        environment = {**os.environ, "HYDRA_UMC_DEPLOY_RESULT": str(result_file)}
        done = runner(["bash", str(script), "--apply"], env=environment, check=False)
        report["installer_exit"] = done.returncode
        try:
            report["deploy"] = json.loads(result_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            report["deploy"] = None
    report["result"] = ((report["deploy"] or {}).get("result") or "done") if done.returncode == 0 else ("rolled-back" if done.returncode == EXIT_ROLLED_BACK else "failed")
    return done.returncode, report


def tool_command(arguments: list[str]) -> list[str]:
    return [sys.executable, str(HERE.parent / "tools" / "deploy_tree.py"), "--root", str(RELEASES_ROOT), *arguments]


def main(argv: list[str] | None = None, *, runner: Any = subprocess.run) -> int:
    parser = argparse.ArgumentParser(prog="hydra-umc-os", description=__doc__.splitlines()[0])
    parser.add_argument("--provisioning-dir", type=Path, default=HERE, help="the folder with install_plan.json and the installers (this one by default)")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("plan").add_argument("project", nargs="?")
    one = commands.add_parser("deploy")
    one.add_argument("project")
    one.add_argument("--apply", action="store_true", help="run the installer (as root); without it only say what would run")
    commands.add_parser("rollback").add_argument("project")
    commands.add_parser("status").add_argument("project", nargs="?")
    args = parser.parse_args(argv)
    try:
        plan = load_plan(args.provisioning_dir)
        if args.command == "plan":
            rows = [find(plan, args.project)] if args.project else [row for row in plan["installers"] if row.get("source")]
            print(json.dumps({"supported_contract": plan["supported_contract"], "projects": [summary(row) for row in rows]}, indent=2, sort_keys=True))
            return 0
        if args.command == "deploy":
            code, report = deploy(args.provisioning_dir, args.project, apply=args.apply, runner=runner)
            print(json.dumps(report, sort_keys=True))
            return code
        row = find(plan, args.project) if args.project else None
        component = str(row["target"]).rsplit("/", 1)[-1] if row else None
        if args.command == "status":
            done = runner(tool_command(["status", *([component] if component else [])]), check=False)
            return int(done.returncode)
        assert row is not None
        deployable(plan, row)
        extra = ["--unit", str(row["unit"])] if row.get("unit") else []
        if row.get("port") and row.get("health_path"):
            extra += ["--health-url", f"http://127.0.0.1:{row['port']}{row['health_path']}"]
        done = runner(tool_command(["rollback", str(component), *extra]), check=False)
        return int(done.returncode)
    except Refused as error:
        print(json.dumps({"result": "refused", "reason": str(error)}, sort_keys=True))
        print(f"HYDRA_UMC_OS=REFUSED {error}", file=sys.stderr)
        return EXIT_REFUSED


if __name__ == "__main__":
    raise SystemExit(main())
