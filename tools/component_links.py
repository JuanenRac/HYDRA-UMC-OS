#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - tools/component_links.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Make a program of the device run from `<components>/<name>/current`, so that the signed packages of `deploy_release.py` can replace it and go back, without changing a path.

    python tools/component_links.py status  datalake --root /opt/hydra-umc
    python tools/component_links.py migrate datalake --root /opt/hydra-umc --apply
    python tools/component_links.py unmigrate datalake --root /opt/hydra-umc --apply

Today a program lives in `<root>/<name>` (the unit points there). After `migrate` `<root>/<name>` is a link to `<components>/<name>/current`, a link to the release in use
(`releases/<version>-<n>`, the layout of `deploy_release.py`), and what the program writes (`data`, `models`, `workspace`, or the folders of `stateDirs`) lives once in
`<components>/<name>/state/` and is linked inside every release: no unit, installer or path changes, and a new release or a way back never touches the data.

OFF BY DEFAULT: nothing is changed unless `<components>/wiring.json` says `"enabled": true` AND the call has `--apply`; without `--apply` it only says what it would do.
Settings of that file: `enabled` (false), `stateDirs` (data, models, workspace), `stopCommand`, `startCommand`, `healthCommand` (empty by default; `{unit}`, `{component}`,
`{root}` are replaced; no shell runs them). `migrate` stops the program, moves its state, copies the program into the first release, puts the links in place, starts it and checks it;
if the start or the check fails everything is put back by itself (status 3). The old folder is KEPT as `<name>.premigration`, never deleted. `unmigrate` is the way back by hand:
what the program wrote since is carried back with it. Standard library only; the commands are replaceable so a test needs no systemd.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("hydra_deploy_release_for_links", HERE / "deploy_release.py")
assert _spec and _spec.loader
dr = importlib.util.module_from_spec(_spec)
sys.modules["hydra_deploy_release_for_links"] = dr
_spec.loader.exec_module(dr)

EXIT_REFUSED = 2
EXIT_UNDONE = 3
NAME = re.compile(r"^[a-z][a-z0-9-]{0,40}$")
DEFAULT_STATE_DIRS = ["data", "models", "workspace"]
Runner = Callable[[str, dict[str, str]], bool]


class LinkError(Exception):
    def __init__(self, message: str, code: int = EXIT_REFUSED) -> None:
        super().__init__(message)
        self.code = code


def load_wiring(components: Path, warn: Callable[[str], None] = lambda m: print(m, file=sys.stderr)) -> dict[str, Any]:
    settings: dict[str, Any] = {"enabled": False, "stateDirs": list(DEFAULT_STATE_DIRS), "stopCommand": "", "startCommand": "", "healthCommand": ""}
    path = components / "wiring.json"
    if not path.is_file():
        return settings
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        warn(f"{path} is not valid JSON; the program stays as it is")
        return settings
    if not isinstance(raw, dict):
        return settings
    if raw.get("enabled") is True:
        settings["enabled"] = True
    dirs = raw.get("stateDirs")
    if isinstance(dirs, list) and len(dirs) <= 16 and all(isinstance(d, str) and dr.STATE_DIR.match(d) for d in dirs):
        settings["stateDirs"] = list(dirs)
    elif "stateDirs" in raw:
        warn(f"{path}: stateDirs must be a list of plain folder names; the default is used")
    for key in ("stopCommand", "startCommand", "healthCommand"):
        if isinstance(raw.get(key), str):
            settings[key] = raw[key].strip()
    return settings


def wired(root: Path, components: Path, name: str) -> bool:
    link = root / name
    return link.is_symlink() and Path(os.path.realpath(link)) == Path(os.path.realpath(components / name / "current"))


def status(root: Path, components: Path, name: str) -> dict[str, Any]:
    component = dr.Component(components, name)
    state = component.state()
    return {"name": name, "wired": wired(root, components, name), "path": "link" if (root / name).is_symlink() else "folder" if (root / name).is_dir() else "absent",
            "current": (state["current"] or {}).get("version"), "previous": (state["previous"] or {}).get("version"),
            "premigration": (root / f"{name}.premigration").is_dir(), "stateDirs": sorted(p.name for p in (component.base / "state").glob("*")) if (component.base / "state").is_dir() else []}


def program_version(folder: Path) -> str:
    try:
        version = str(json.loads((folder / "hydra-umc.project.json").read_text(encoding="utf-8")).get("version", ""))
    except (OSError, ValueError):
        version = ""
    return version if re.fullmatch(r"\d+(\.\d+){1,3}", version) else "0.0.0"


def relative_link(target: Path, link: Path) -> None:
    os.symlink(os.path.relpath(target, link.parent), link, target_is_directory=True)


def replace_link(target: Path, link: Path) -> None:
    temporary = link.with_name(f".{link.name}.new")
    if temporary.is_symlink() or temporary.exists():
        temporary.unlink()
    os.symlink(target, temporary, target_is_directory=True)
    os.replace(temporary, link)


def migrate(root: Path, components: Path, name: str, *, apply: bool, settings: dict[str, Any], unit: str = "", run: Runner = lambda c, v: dr.run_command(c, v),
            say: Callable[[str], None] = print) -> dict[str, Any]:
    if not NAME.match(name):
        raise LinkError(f"{name!r} is not a program name")
    program = root / name
    component = dr.Component(components, name)
    if program.is_symlink():
        raise LinkError(f"refused: {name} is already a link")
    if not program.is_dir():
        raise LinkError(f"refused: {root / name} is not a folder")
    if component.base.exists():
        raise LinkError(f"refused: {component.base} exists already")
    if (root / f"{name}.premigration").exists():
        raise LinkError(f"refused: {root / (name + '.premigration')} exists (a folder kept by an earlier migration)")
    version = program_version(program)
    names = [d for d in settings["stateDirs"] if (program / d).is_dir() and not (program / d).is_symlink()]
    plan = {"name": name, "version": version, "release": f"{version}-1", "stateDirs": names, "applied": False}
    if not apply:
        say(f"would migrate {name} {version}: release {version}-1, state {names or 'none'}, folder kept as {name}.premigration")
        return plan
    if not settings["enabled"]:
        raise LinkError("refused: the wiring is switched off (wiring.json: enabled)")
    values = {"unit": unit, "component": name, "root": str(root)}
    undo: list[Callable[[], None]] = []
    stopped = False
    try:
        stopped = run(settings["stopCommand"], values)
        if not stopped:
            raise LinkError("the program could not be stopped", EXIT_UNDONE)
        release = component.releases / f"{version}-1"
        state = component.base / "state"
        state.mkdir(parents=True)
        undo.append(lambda: shutil.rmtree(component.base, ignore_errors=True))      # only what this call created (nothing of the program was inside yet)
        for d in names:
            shutil.move(str(program / d), str(state / d))
            undo.append(lambda d=d: shutil.move(str(state / d), str(program / d)) if (state / d).exists() else None)
        shutil.copytree(program, release, symlinks=True)
        for d in names:
            relative_link(state / d, release / d)
        entry = {"release": release.name, "version": version, "sha256": "", "installedAt": dr.now_text()}
        component.write_state({"current": entry, "previous": None, "history": [{"event": "migrate", "version": version, "at": entry["installedAt"]}], "pending": None})
        component.point_link(release)
        os.replace(program, root / f"{name}.premigration")
        undo.append(lambda: os.replace(root / f"{name}.premigration", program))
        os.symlink(component.link, program, target_is_directory=True)
        undo.append(lambda: program.unlink() if program.is_symlink() else None)
        started = run(settings["startCommand"], values)
        if not (started and wait_health(settings, values, run)):
            raise LinkError(f"{name} did not {'start' if not started else 'pass the health check'} from its link; everything was put back", EXIT_UNDONE)
        plan["applied"] = True
        say(f"{name} {version} now runs from {component.link}")
        return plan
    except BaseException as failure:
        for step in reversed(undo):
            try:
                step()
            except OSError as problem:
                say(f"could not undo a step ({problem}); look at {root} and {components}")
        if stopped:
            run(settings["startCommand"], values)
        if isinstance(failure, LinkError):
            raise
        raise LinkError(f"{name}: {failure}; everything was put back", EXIT_UNDONE) from failure


def wait_health(settings: dict[str, Any], values: dict[str, str], run: Runner, tries: int = 5, sleep: Callable[[float], None] = time.sleep) -> bool:
    for _ in range(tries):
        if run(settings["healthCommand"], values):
            return True
        sleep(1)
    return False


def unmigrate(root: Path, components: Path, name: str, *, apply: bool, settings: dict[str, Any], unit: str = "", run: Runner = lambda c, v: dr.run_command(c, v),
              say: Callable[[str], None] = print) -> dict[str, Any]:
    if not NAME.match(name):
        raise LinkError(f"{name!r} is not a program name")
    program, kept = root / name, root / f"{name}.premigration"
    component = dr.Component(components, name)
    if not wired(root, components, name):
        raise LinkError(f"refused: {name} does not run from its link")
    if not kept.is_dir():
        raise LinkError(f"refused: {kept} is missing (nothing to go back to)")
    state = component.base / "state"
    names = sorted(p.name for p in state.glob("*") if p.is_dir()) if state.is_dir() else []
    plan = {"name": name, "stateDirs": names, "applied": False}
    if not apply:
        say(f"would put {kept.name} back as {name} with the state it holds now: {names or 'none'}")
        return plan
    if not settings["enabled"]:
        raise LinkError("refused: the wiring is switched off (wiring.json: enabled)")
    values = {"unit": unit, "component": name, "root": str(root)}
    if not run(settings["stopCommand"], values):
        raise LinkError("the program could not be stopped", EXIT_UNDONE)
    try:
        program.unlink()
        for d in names:
            if (kept / d).exists() or (kept / d).is_symlink():
                shutil.move(str(kept / d), str(kept / f"{d}.before_unmigrate_{int(time.time())}"))
            shutil.move(str(state / d), str(kept / d))
        os.replace(kept, program)
        os.replace(component.base, components / f"{name}.unwired_{int(time.time())}")       # kept, never deleted
    finally:
        run(settings["startCommand"], values)
    plan["applied"] = True
    say(f"{name} runs from its own folder again; the releases are kept as {name}.unwired_*")
    return plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=["status", "migrate", "unmigrate"])
    parser.add_argument("name")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--components", type=Path)
    parser.add_argument("--unit", default="")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    components = args.components or args.root / ".components"
    settings = load_wiring(components)
    try:
        if args.command == "status":
            print(json.dumps(status(args.root, components, args.name), indent=2, sort_keys=True))
        elif args.command == "migrate":
            print(json.dumps(migrate(args.root, components, args.name, apply=args.apply, settings=settings, unit=args.unit), sort_keys=True))
        else:
            print(json.dumps(unmigrate(args.root, components, args.name, apply=args.apply, settings=settings, unit=args.unit), sort_keys=True))
    except LinkError as error:
        print(f"LINKS=FAIL {error}", file=sys.stderr)
        return error.code
    print("LINKS=PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
