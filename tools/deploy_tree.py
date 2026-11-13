#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - tools/deploy_tree.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Numbered releases, a restart, a health check and the way back for the installers of the programs of the CM5.

`deploy_release.py` installs a signed package as `<root>/<component>/releases/<version>-<n>` and moves a `current` link. The `install_*.sh` scripts do something else: they copy a
program into `/opt/hydra-umc/<component>`, where the unit expects it, and the folder also holds what the program writes (`data`, `models`, `workspace`). This tool gives them the same
guarantees without moving anything the units point at:

    python tools/deploy_tree.py --root /opt/hydra-umc/.releases begin   server --target /opt/hydra-umc/server
    ... the installer copies the new program into the target ...
    python tools/deploy_tree.py --root /opt/hydra-umc/.releases settle  server --target /opt/hydra-umc/server --unit hydra-umc-server.service --health-url http://127.0.0.1:8080/health
    python tools/deploy_tree.py --root /opt/hydra-umc/.releases rollback server

* `begin` keeps a copy of the program that is installed now (everything in the target except the folders that hold state) as the release that is in use, unless an identical one is
  already kept. Nothing in the target changes.
* `settle` keeps a copy of what the installer left as the new current release. If the program is the same one, nothing else happens (`unchanged`). If its unit is not running, the unit
  is left alone (`installed`: the operator has not enabled it, and a deployment never starts what nobody asked to run). If it runs, `systemctl try-restart` and the health check are run;
  when the restart fails or the health check does not pass within the time, the copy kept by `begin` is put back, the unit is restarted on it, and the exit status is 3.
* `rollback` puts the previous release back (restart and health check as above).

The folders `data`, `models` and `workspace` are never copied, replaced or removed: a program keeps its state across releases. Releases are kept under `--root` (the lib puts them in
`/opt/hydra-umc/.releases`, outside every target). The settings are those of `<root>/deploy.json` (see deploy_release.py): `keep`, `healthTimeoutS`, `healthIntervalS`, `restartCommand`
(by default `systemctl try-restart {unit}`), `healthCommand`, and here also `restartOnDeploy` (true) and `rollbackOnFailure` (true); the command line wins.

Standard library only; nothing here needs systemd to be tested (the restart, the unit state and the health check are replaceable).
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("hydra_deploy_release", HERE / "deploy_release.py")
assert _spec and _spec.loader
dr = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("hydra_deploy_release", dr)
_spec.loader.exec_module(dr)

DeployError = dr.DeployError
EXIT_REFUSED = dr.EXIT_REFUSED
EXIT_ROLLED_BACK = dr.EXIT_ROLLED_BACK
STATE_DIRS = ("data", "models", "workspace")
DEFAULT_RESTART = "systemctl try-restart {unit}"
DEFAULT_RELOAD = "systemctl daemon-reload"
DEFAULT_UNIT_DIR = "/etc/systemd/system"
UNITS_FOLDER = "units"
PENDING_UNITS = "pending"
TREE_DEFAULTS: dict[str, Any] = {"restartOnDeploy": True, "rollbackOnFailure": True}
TREE_KEEP = 2


def load_settings(root: Path, warn: Callable[[str], None] = lambda message: print(message, file=sys.stderr)) -> dict[str, Any]:
    """The settings of deploy_release plus the two switches of this tool; a value that is not true or false is replaced by the default and said."""
    settings = dr.load_settings(root, warn)
    settings.update(TREE_DEFAULTS)
    path = root / "deploy.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except (OSError, ValueError):
        raw = {}
    if not (isinstance(raw, dict) and "keep" in raw):
        settings["keep"] = TREE_KEEP  # a program can be large (node_modules): the one in use and the previous one
    for key, default in TREE_DEFAULTS.items():
        if isinstance(raw, dict) and key in raw:
            if isinstance(raw[key], bool):
                settings[key] = raw[key]
            else:
                warn(f"{path}: {key} must be true or false; {str(default).lower()} is used")
    settings["reloadCommand"] = raw["reloadCommand"] if isinstance(raw, dict) and isinstance(raw.get("reloadCommand"), str) else DEFAULT_RELOAD
    return settings


def payload(target: Path, state_dirs: tuple[str, ...]) -> list[Path]:
    """The top-level entries of the target that belong to a release: everything but the state folders."""
    if not target.is_dir():
        return []
    return sorted((entry for entry in target.iterdir() if entry.name not in state_dirs), key=lambda entry: entry.name)


def tree_digest(entries: list[Path]) -> str:
    """One hash over the names, the kind and the content of the entries (a link counts by where it points), independent of dates and of the host."""
    digest = hashlib.sha256()
    for entry in entries:
        for path in [entry, *sorted(entry.rglob("*"))] if entry.is_dir() and not entry.is_symlink() else [entry]:
            relative = path.relative_to(entry.parent).as_posix()
            if path.is_symlink():
                digest.update(f"L {relative} -> {os.readlink(path)}\n".encode())
            elif path.is_dir():
                digest.update(f"D {relative}\n".encode())
            else:
                digest.update(f"F {relative} {path.stat().st_mode & 0o111 != 0}\n".encode())
                with path.open("rb") as handle:
                    for block in iter(lambda: handle.read(1 << 20), b""):
                        digest.update(block)
    return digest.hexdigest()


def tree_version(target: Path) -> str:
    """The version in the manifest of the program that is in the target, or `0` when there is none."""
    try:
        text = json.loads((target / "hydra-umc.project.json").read_text(encoding="utf-8")).get("version")
    except (OSError, ValueError, AttributeError):
        return "0"
    return text if isinstance(text, str) and all(part.isdigit() for part in text.split(".")) else "0"


def copy_entries(entries: list[Path], destination: Path) -> None:
    destination.mkdir(parents=True)
    for entry in entries:
        if entry.is_dir() and not entry.is_symlink():
            shutil.copytree(entry, destination / entry.name, symlinks=True)
        else:
            shutil.copy2(entry, destination / entry.name, follow_symlinks=False)


def keep_copy(component: Any, target: Path, state_dirs: tuple[str, ...], digest: str, version: str) -> dict[str, Any]:
    """Keep a copy of the payload of the target as a numbered release folder (complete or not there) and return its entry."""
    component.releases.mkdir(parents=True, exist_ok=True)
    name = dr.next_release_name(component, version)
    staging = Path(tempfile.mkdtemp(prefix=".incoming-", dir=component.releases))
    try:
        copy_entries(payload(target, state_dirs), staging / "tree")
        os.replace(staging / "tree", component.releases / name)
    except OSError as error:
        raise DeployError(f"the program in {target} could not be kept: {error}") from error
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return {"release": name, "version": version, "sha256": digest, "installedAt": dr.now_text(), "mode": "tree", "target": str(target)}


def restore(release: Path, target: Path, state_dirs: tuple[str, ...]) -> None:
    """Put the payload of a kept release in the target. What is in the target now moves aside first and comes back if the copy fails; the state folders are not touched."""
    aside = Path(tempfile.mkdtemp(prefix=".restore-", dir=target))
    moved: list[Path] = []
    try:
        for entry in payload(target, state_dirs):
            if entry == aside:
                continue
            os.replace(entry, aside / entry.name)
            moved.append(entry)
        for entry in sorted(release.iterdir(), key=lambda item: item.name):
            if entry.is_dir() and not entry.is_symlink():
                shutil.copytree(entry, target / entry.name, symlinks=True)
            else:
                shutil.copy2(entry, target / entry.name, follow_symlinks=False)
    except OSError as error:
        for entry in sorted(release.iterdir(), key=lambda item: item.name):
            path = target / entry.name
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path, ignore_errors=True)
            elif path.exists() or path.is_symlink():
                path.unlink()
        for entry in moved:
            os.replace(aside / entry.name, entry)
        raise DeployError(f"the earlier release could not be put back: {error}") from error
    finally:
        shutil.rmtree(aside, ignore_errors=True)


def snapshot_units(unit_dir: Path, units: list[str], destination: Path) -> None:
    """Keep the unit files and the drop-in folders (`<unit>.d`) of `units` as they are now, and which of them do not exist, so that `restore_units` can put them back exactly."""
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    entries: dict[str, str] = {}
    for unit in units:
        for relative in (unit, unit + ".d"):
            source = unit_dir / relative
            if source.is_dir() and not source.is_symlink():
                shutil.copytree(source, destination / relative, symlinks=True)
                entries[relative] = "dir"
            elif source.is_file() or source.is_symlink():
                shutil.copy2(source, destination / relative, follow_symlinks=False)
                entries[relative] = "file"
            else:
                entries[relative] = "absent"
    (destination / "manifest.json").write_text(json.dumps({"unitDir": str(unit_dir), "entries": entries}, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def restore_units(snapshot: Path) -> list[str]:
    """Put the unit files and drop-in folders of a snapshot back: what the snapshot has replaces what is there now, and what it says did not exist is removed. Returns the names that were put back or removed."""
    try:
        manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
        unit_dir = Path(manifest["unitDir"])
        entries = manifest["entries"]
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise DeployError(f"the kept units in {snapshot} cannot be read: {error}") from error
    changed: list[str] = []
    for relative, kind in sorted(entries.items()):
        if "/" in relative or "\\" in relative or relative in ("", ".", ".."):
            continue
        current = unit_dir / relative
        if current.is_dir() and not current.is_symlink():
            shutil.rmtree(current)
        elif current.exists() or current.is_symlink():
            current.unlink()
        if kind == "dir":
            shutil.copytree(snapshot / relative, current, symlinks=True)
        elif kind == "file":
            shutil.copy2(snapshot / relative, current, follow_symlinks=False)
        changed.append(relative)
    return changed


def begin(root: Path, name: str, target: Path, *, state_dirs: tuple[str, ...] = STATE_DIRS, units: list[str] | None = None, unit_dir: Path | None = None) -> dict[str, Any]:
    """Remember the program that is installed now, so that `settle` can put it back. Returns the state.

    With `units` the unit files and drop-in folders of those units (in `unit_dir`, /etc/systemd/system by default) are kept too: the installer changes them outside the target,
    and a program that is put back with a unit that no longer fits it does not start."""
    component = dr.Component(root, name)
    if units:
        snapshot_units(unit_dir or Path(DEFAULT_UNIT_DIR), units, component.base / UNITS_FOLDER / PENDING_UNITS)
    else:
        shutil.rmtree(component.base / UNITS_FOLDER / PENDING_UNITS, ignore_errors=True)
    state = component.state()
    entries = payload(target, state_dirs)
    if not entries:
        state["pending"] = None
    else:
        digest = tree_digest(entries)
        current = state["current"]
        if current and current.get("sha256") == digest and (component.release_path(current) or Path("/nonexistent")).is_dir():
            state["pending"] = current
        else:
            state["pending"] = keep_copy(component, target, state_dirs, digest, tree_version(target))
    component.write_state(state)
    return state


def promote_units(component: Any, release: str) -> None:
    """The units kept by `begin` are what the PREVIOUS program needs: keep them as `before-<release>` of the release that was just installed, and drop the ones of releases no longer kept."""
    folder = component.base / UNITS_FOLDER
    pending = folder / PENDING_UNITS
    if pending.is_dir():
        destination = folder / f"before-{release}"
        shutil.rmtree(destination, ignore_errors=True)
        os.replace(pending, destination)
    state = component.state()
    wanted = {f"before-{entry['release']}" for entry in (state["current"], state["previous"]) if entry and isinstance(entry.get("release"), str)}
    for old in folder.glob("before-*") if folder.is_dir() else []:
        if old.name not in wanted:
            shutil.rmtree(old, ignore_errors=True)


def put_back_units(snapshot: Path, settings: dict[str, Any], values: dict[str, str]) -> None:
    """Restore the kept unit files and drop-ins and make systemd read them again."""
    restore_units(snapshot)
    dr.run_command(settings.get("reloadCommand") or DEFAULT_RELOAD, values)


def systemd_is_active(unit: str) -> bool:
    try:
        return subprocess.run(["systemctl", "is-active", "--quiet", unit], check=False, timeout=30).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def http_ok(url: str, timeout: float = 5.0) -> bool:
    """Whether the route answers with a 2xx within the time. Nothing else counts: a refused connection, a 5xx and a redirect to somewhere else are not healthy."""
    if not url.startswith(("http://127.0.0.1", "http://localhost", "http://[::1]")):
        return False
    request = urllib.request.Request(url, method="GET")

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args: Any, **kwargs: Any) -> None:  # type: ignore[override]
            return None

    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=timeout) as answer:
            return 200 <= answer.status < 300
    except urllib.error.HTTPError as answer:
        answer.close()
        return False
    except (urllib.error.URLError, OSError, ValueError):
        return False


def healthy(settings: dict[str, Any], values: dict[str, str], *, unit: str | None, health_url: str | None, sleep: Callable[[float], None],
            is_active: Callable[[str], bool], probe: Callable[[str], bool]) -> bool:
    """The command of the settings if there is one, else the route of the registry, else only that the unit runs; repeated until the time of the settings passes."""
    def once() -> bool:
        if settings["healthCommand"]:
            return dr.run_command(settings["healthCommand"], values, timeout=max(1.0, min(30.0, float(settings["healthTimeoutS"]))))
        if health_url:
            return probe(health_url)
        return bool(unit) and is_active(str(unit))

    end = time.monotonic() + float(settings["healthTimeoutS"])
    while True:
        if once():
            return True
        if time.monotonic() >= end:
            return False
        sleep(float(settings["healthIntervalS"]))


def settle(root: Path, name: str, target: Path, *, unit: str | None = None, health_url: str | None = None, settings: dict[str, Any] | None = None,
           state_dirs: tuple[str, ...] = STATE_DIRS, sleep: Callable[[float], None] = time.sleep,
           is_active: Callable[[str], bool] = systemd_is_active, probe: Callable[[str], bool] = http_ok) -> dict[str, Any]:
    """Keep what the installer left as the current release, restart the unit if it runs, check it, and go back when it does not hold. Returns the state and a `result`."""
    settings = settings if settings is not None else load_settings(root)
    component = dr.Component(root, name)
    state = component.state()
    pending = state.get("pending") if isinstance(state.get("pending"), dict) else None
    entries = payload(target, state_dirs)
    if not entries:
        raise DeployError(f"refused: {target} holds no program to keep")
    digest = tree_digest(entries)
    if pending and pending.get("sha256") == digest:
        state["pending"] = None
        component.write_state(state)
        return {**component.state(), "result": "unchanged"}
    version = tree_version(target)
    entry = keep_copy(component, target, state_dirs, digest, version)
    history = [*state["history"], {"event": "install", "version": version, "at": entry["installedAt"]}][-dr.HISTORY_LIMIT:]
    in_use = pending if pending else state["current"]
    component.write_state({"current": entry, "previous": in_use, "history": history, "pending": None})
    pending_units = component.base / UNITS_FOLDER / PENDING_UNITS
    values = {"component": name, "version": version, "release": str(component.releases / entry["release"]), "root": str(root), "unit": unit or "", "target": str(target)}
    running = bool(unit) and is_active(str(unit))
    if not running or not settings["restartOnDeploy"]:
        promote_units(component, entry["release"])
        dr.prune(root, name, int(settings["keep"]))
        return {**component.state(), "result": "installed" if not running else "installed-not-restarted"}
    restart = settings["restartCommand"] or DEFAULT_RESTART
    started = dr.run_command(restart, values)
    ok = started and healthy(settings, values, unit=unit, health_url=health_url, sleep=sleep, is_active=is_active, probe=probe)
    if ok:
        promote_units(component, entry["release"])
        dr.prune(root, name, int(settings["keep"]))
        return {**component.state(), "result": "deployed"}
    reason = "restart" if not started else "health"
    if not settings["rollbackOnFailure"] or not in_use:
        component.write_state({**component.state(), "history": [*component.state()["history"], {"event": "install-failed", "version": version, "at": dr.now_text(), "reason": reason}][-dr.HISTORY_LIMIT:]})
        raise DeployError(f"{name} {version} did not {'restart' if not started else 'pass the health check'}; "
                          f"{'rollbackOnFailure is off' if in_use else 'there was no earlier release to go back to'}", EXIT_ROLLED_BACK)
    old_path = component.release_path(in_use)
    if not old_path or not old_path.is_dir():
        raise DeployError(f"{name} {version} did not {'restart' if not started else 'pass the health check'} and the earlier release is not kept any more", EXIT_ROLLED_BACK)
    restore(old_path, target, state_dirs)
    if pending_units.is_dir():
        put_back_units(pending_units, settings, values)  # the unit files and drop-ins the installer changed go back with the program
    failed = [*state["history"], {"event": "install-failed", "version": version, "at": dr.now_text(), "reason": reason}]
    component.write_state({"current": in_use, "previous": state["previous"], "history": failed[-dr.HISTORY_LIMIT:], "pending": None})
    back = {**values, "version": str(in_use.get("version", "")), "release": str(old_path)}
    dr.run_command(restart, back)
    raise DeployError(f"{name} {version} did not {'restart' if not started else 'pass the health check'}; the release in use is {in_use.get('version')}", EXIT_ROLLED_BACK)


def rollback(root: Path, name: str, *, unit: str | None = None, health_url: str | None = None, settings: dict[str, Any] | None = None,
             state_dirs: tuple[str, ...] = STATE_DIRS, sleep: Callable[[float], None] = time.sleep,
             is_active: Callable[[str], bool] = systemd_is_active, probe: Callable[[str], bool] = http_ok) -> dict[str, Any]:
    settings = settings if settings is not None else load_settings(root)
    component = dr.Component(root, name)
    state = component.state()
    previous = state["previous"]
    path = component.release_path(previous)
    if not previous or previous.get("mode") != "tree" or not path or not path.is_dir() or not isinstance(previous.get("target"), str):
        raise DeployError(f"refused: {name} has no earlier installed program to go back to")
    target = Path(previous["target"])
    restore(path, target, state_dirs)
    current_entry = state["current"] if isinstance(state.get("current"), dict) else None
    kept_units = component.base / UNITS_FOLDER / f"before-{current_entry['release']}" if current_entry and isinstance(current_entry.get("release"), str) else None
    if kept_units is not None and kept_units.is_dir():
        put_back_units(kept_units, settings, {"component": name, "version": str(previous.get("version", "")), "release": str(path), "root": str(root), "unit": unit or "", "target": str(target)})
    history = [*state["history"], {"event": "rollback", "version": previous.get("version"), "at": dr.now_text()}][-dr.HISTORY_LIMIT:]
    component.write_state({"current": previous, "previous": state["current"], "history": history, "pending": None})
    if unit and is_active(unit) and settings["restartOnDeploy"]:
        values = {"component": name, "version": str(previous.get("version", "")), "release": str(path), "root": str(root), "unit": unit, "target": str(target)}
        if not (dr.run_command(settings["restartCommand"] or DEFAULT_RESTART, values)
                and healthy(settings, values, unit=unit, health_url=health_url, sleep=sleep, is_active=is_active, probe=probe)):
            raise DeployError(f"{name} went back to {previous.get('version')} but did not pass the health check; look at the unit", EXIT_ROLLED_BACK)
    return {**component.state(), "result": "rolled-back"}


def state_dirs_of(text: str | None) -> tuple[str, ...]:
    names = tuple(part for part in (text or ",".join(STATE_DIRS)).split(",") if part)
    if any("/" in part or "\\" in part or part in (".", "..") for part in names):
        raise DeployError("refused: a state folder is a plain name")
    return names


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, required=True, help="where the releases are kept (/opt/hydra-umc/.releases on the device)")
    commands = parser.add_subparsers(dest="command", required=True)
    for word in ("begin", "settle", "rollback"):
        sub = commands.add_parser(word)
        sub.add_argument("component")
        sub.add_argument("--state-dirs", help="comma separated folders that hold state and are never touched (default: data,models,workspace)")
        if word != "rollback":
            sub.add_argument("--target", type=Path, required=True)
        if word == "begin":
            sub.add_argument("--unit", action="append", default=[], help="a unit whose file and drop-ins are kept with the program and put back with it (repeatable)")
            sub.add_argument("--unit-dir", type=Path, default=None, help="where the unit files are (default /etc/systemd/system, or HYDRA_UMC_UNIT_DIR)")
        if word != "begin":
            sub.add_argument("--unit")
            sub.add_argument("--health-url")
    commands.add_parser("status").add_argument("component", nargs="?")
    args = parser.parse_args(argv)
    try:
        if args.command == "status":
            result: dict[str, Any] = dr.status(args.root, args.component)
        else:
            dirs = state_dirs_of(args.state_dirs)
            if args.command == "begin":
                unit_dir = args.unit_dir or (Path(os.environ["HYDRA_UMC_UNIT_DIR"]) if os.environ.get("HYDRA_UMC_UNIT_DIR") else None)
                result = begin(args.root, args.component, args.target, state_dirs=dirs, units=list(args.unit), unit_dir=unit_dir)
            elif args.command == "settle":
                result = settle(args.root, args.component, args.target, unit=args.unit, health_url=args.health_url, state_dirs=dirs)
            else:
                result = rollback(args.root, args.component, unit=args.unit, health_url=args.health_url, state_dirs=dirs)
    except DeployError as error:
        print(f"DEPLOY=FAIL {error}", file=sys.stderr)
        return error.code
    print(json.dumps(result, indent=2, sort_keys=True))
    print("DEPLOY=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
