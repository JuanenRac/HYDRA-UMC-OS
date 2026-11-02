#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - tools/deploy_release.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Install a signed package as a numbered release, switch to it, check it and go back when it does not hold.

    python tools/deploy_release.py install dist-packages/hydra-server-0.8.1.0.tgz --root /opt/hydra-umc
    python tools/deploy_release.py rollback server --root /opt/hydra-umc
    python tools/deploy_release.py status [server] --root /opt/hydra-umc
    python tools/deploy_release.py prune server --root /opt/hydra-umc --keep 3

Layout under `--root` (a temporary folder in the tests, `/opt/hydra-umc` on the device):

    <root>/<component>/releases/<version>-<n>/     what the package holds, extracted
    <root>/<component>/current                     a link to the release in use (best effort: the truth is state.json)
    <root>/<component>/state.json                  {"current", "previous", "history"}: written atomically
    <root>/deploy.json                             optional settings (below); the command line wins

`install` goes through these steps and stops at the first that fails:

1. the package is verified (`tools/package_component.py verify_package`: hash, Ed25519 signature of the component, the version and the hash, and only paths of the layout);
2. a version lower than the one in use is refused, and the same version is refused too (use `--allow-downgrade` to go back on purpose);
3. the package is extracted next to its final place and renamed, so a release folder is either complete or not there;
4. the state is switched to the new release (the old one is kept as `previous`) and the link is moved;
5. `restartCommand` runs (for example `systemctl try-restart hydra-umc-server`), then `healthCommand` is repeated until it exits 0 or `healthTimeoutS` passes;
6. if the restart or the health check fails, the state goes back to the release that was in use, the restart runs again and the exit status is 3: the failure is visible and the old
   release is the one running;
7. old releases beyond `keep` are removed, never the current one nor the previous one.

`{component}`, `{version}`, `{release}` (the folder of the new release) and `{root}` are replaced in the two commands. Nothing here needs root, systemd or a network: the commands are
whatever the settings say, and they are empty (skipped) by default, so a dry installation on a laptop does not touch anything outside `--root`.

Settings of `<root>/deploy.json`: `keep` (releases to keep, 2 or more, 3 by default), `healthTimeoutS` (1 to 600, 30), `healthIntervalS` (0.1 to 30, 1), `restartCommand` and
`healthCommand` (empty by default), `allowDowngrade` (false). A value that is not valid is replaced by the default and said on the standard error.

Standard library only.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("hydra_package_component", HERE / "package_component.py")
assert _spec and _spec.loader
package_component = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("hydra_package_component", package_component)
_spec.loader.exec_module(package_component)

EXIT_REFUSED = 2
EXIT_ROLLED_BACK = 3
HISTORY_LIMIT = 50
COMPONENT = re.compile(r"^[a-z][a-z0-9-]*$")

DEFAULTS: dict[str, Any] = {"keep": 3, "healthTimeoutS": 30, "healthIntervalS": 1.0, "restartCommand": "", "healthCommand": "", "allowDowngrade": False}


class DeployError(Exception):
    """A deployment that did not happen; `code` is the exit status."""

    def __init__(self, message: str, code: int = EXIT_REFUSED) -> None:
        super().__init__(message)
        self.code = code


def _number(value: Any, fallback: float, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return fallback
    return fallback if not low <= value <= high else float(value)


def load_settings(root: Path, warn: Callable[[str], None] = lambda message: print(message, file=sys.stderr)) -> dict[str, Any]:
    settings = dict(DEFAULTS)
    path = root / "deploy.json"
    if not path.is_file():
        return settings
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        warn(f"{path} is not valid JSON; the defaults are used")
        return settings
    if not isinstance(raw, dict):
        warn(f"{path} must hold an object; the defaults are used")
        return settings
    for key in ("keep", "healthTimeoutS", "healthIntervalS"):
        if key in raw:
            low, high = {"keep": (2, 100), "healthTimeoutS": (1, 600), "healthIntervalS": (0.1, 30)}[key]
            value = _number(raw[key], float(DEFAULTS[key]), low, high)
            if value == float(DEFAULTS[key]) and raw[key] != DEFAULTS[key]:
                warn(f"{path}: {key} is not valid; {DEFAULTS[key]} is used")
            settings[key] = int(value) if key == "keep" else value
    for key in ("restartCommand", "healthCommand"):
        if key in raw:
            if isinstance(raw[key], str):
                settings[key] = raw[key].strip()
            else:
                warn(f"{path}: {key} must be text; it is ignored")
    if "allowDowngrade" in raw:
        if isinstance(raw["allowDowngrade"], bool):
            settings["allowDowngrade"] = raw["allowDowngrade"]
        else:
            warn(f"{path}: allowDowngrade must be true or false; false is used")
    return settings


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


class Component:
    """The folder of one component under the root and its state."""

    def __init__(self, root: Path, name: str) -> None:
        if not COMPONENT.match(name):
            raise DeployError(f"{name!r} is not a component name")
        self.name = name
        self.base = root / name
        self.releases = self.base / "releases"
        self.state_file = self.base / "state.json"
        self.link = self.base / "current"

    def state(self) -> dict[str, Any]:
        try:
            raw = json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"current": None, "previous": None, "history": []}
        if not isinstance(raw, dict):
            return {"current": None, "previous": None, "history": []}
        history = raw.get("history") if isinstance(raw.get("history"), list) else []
        return {"current": raw.get("current") if isinstance(raw.get("current"), dict) else None,
                "previous": raw.get("previous") if isinstance(raw.get("previous"), dict) else None, "history": history[-HISTORY_LIMIT:]}

    def write_state(self, state: dict[str, Any]) -> None:
        self.base.mkdir(parents=True, exist_ok=True)
        temporary = self.state_file.with_name(self.state_file.name + ".tmp")
        temporary.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        os.replace(temporary, self.state_file)

    def point_link(self, release: Path | None) -> None:
        """Move `current` to the release; a host that cannot make links (some Windows set-ups) only has state.json, which is the truth."""
        if release is None:
            return
        temporary = self.base / ".current.new"
        try:
            if temporary.is_symlink() or temporary.exists():
                temporary.unlink()
            os.symlink(release.name if release.parent == self.releases else release, temporary, target_is_directory=True)
            os.replace(temporary, self.link)
        except (OSError, NotImplementedError):
            pass

    def release_path(self, entry: dict[str, Any] | None) -> Path | None:
        if not entry or not isinstance(entry.get("release"), str) or "/" in entry["release"] or "\\" in entry["release"] or entry["release"] in ("", ".", ".."):
            return None
        return self.releases / entry["release"]


def run_command(template: str, values: dict[str, str], timeout: float = 120) -> bool:
    if not template:
        return True
    command = template
    for key, value in values.items():
        command = command.replace("{" + key + "}", value)
    try:
        # Windows parses a command line itself; elsewhere the line is split like a shell would, and no shell runs it.
        done = subprocess.run(command if os.name == "nt" else shlex.split(command), timeout=timeout, check=False, capture_output=True)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return False
    return done.returncode == 0


def wait_healthy(template: str, values: dict[str, str], timeout_s: float, interval_s: float, sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic) -> bool:
    if not template:
        return True
    end = clock() + timeout_s
    while True:
        if run_command(template, values, timeout=max(1.0, min(30.0, timeout_s))):
            return True
        if clock() >= end:
            return False
        sleep(interval_s)


def extract(package: Path, destination: Path) -> None:
    """The members were checked by verify_package (regular files below the layout); extract them with the data filter where the Python has it."""
    with tarfile.open(package, "r:gz") as tar:
        if hasattr(tarfile, "data_filter"):
            tar.extractall(destination, filter="data")
        else:  # pragma: no cover - Python older than 3.12 without the backport
            tar.extractall(destination)


def next_release_name(component: Component, version: str) -> str:
    number = 1
    while (component.releases / f"{version}-{number}").exists():
        number += 1
    return f"{version}-{number}"


def now_text() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def install(package: Path, root: Path, *, trusted_key: str | None = None, allow_downgrade: bool | None = None, settings: dict[str, Any] | None = None,
            sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    settings = settings if settings is not None else load_settings(root)
    try:
        name, version, digest = package_component.verify_package(package, trusted_key)
    except package_component.PackageRefused as error:
        raise DeployError(f"refused: {error}") from error
    component = Component(root, name)
    state = component.state()
    in_use = state["current"]
    if in_use and not (settings["allowDowngrade"] if allow_downgrade is None else allow_downgrade):
        if version_key(version) <= version_key(str(in_use.get("version", "0"))):
            raise DeployError(f"refused: {version} is not newer than the {in_use.get('version')} in use (--allow-downgrade goes back on purpose)")
    component.releases.mkdir(parents=True, exist_ok=True)
    release_name = next_release_name(component, version)
    staging = Path(tempfile.mkdtemp(prefix=".incoming-", dir=component.releases))
    try:
        extract(package, staging)
        final = component.releases / release_name
        os.replace(staging, final)
    except (OSError, tarfile.TarError) as error:
        shutil.rmtree(staging, ignore_errors=True)
        raise DeployError(f"refused: the package could not be extracted: {error}") from error
    entry = {"release": release_name, "version": version, "sha256": digest, "installedAt": now_text()}
    values = {"component": name, "version": version, "release": str(final), "root": str(root)}
    component.write_state({"current": entry, "previous": in_use, "history": [*state["history"], {"event": "install", "version": version, "at": entry["installedAt"]}][-HISTORY_LIMIT:]})
    component.point_link(final)
    started = run_command(settings["restartCommand"], values)
    healthy = started and wait_healthy(settings["healthCommand"], values, settings["healthTimeoutS"], settings["healthIntervalS"], sleep)
    if not healthy:
        failed = state["history"] + [{"event": "install-failed", "version": version, "at": now_text(), "reason": "restart" if not started else "health"}]
        component.write_state({"current": in_use, "previous": state["previous"], "history": failed[-HISTORY_LIMIT:]})
        if in_use:
            component.point_link(component.release_path(in_use))
        elif component.link.is_symlink():
            component.link.unlink()
        back = {**values, "version": str((in_use or {}).get("version", "")), "release": str(component.release_path(in_use) or "")}
        run_command(settings["restartCommand"], back)
        raise DeployError(f"{name} {version} did not {'restart' if not started else 'pass the health check'}; "
                          f"{'the release in use is ' + str(in_use.get('version')) if in_use else 'there was no earlier release'}", EXIT_ROLLED_BACK)
    prune(root, name, int(settings["keep"]))
    return component.state()


def rollback(root: Path, name: str, *, settings: dict[str, Any] | None = None, sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    settings = settings if settings is not None else load_settings(root)
    component = Component(root, name)
    state = component.state()
    target = state["previous"]
    path = component.release_path(target)
    if not path or not path.is_dir():
        raise DeployError(f"refused: {name} has no earlier release to go back to")
    values = {"component": name, "version": str(target.get("version", "")), "release": str(path), "root": str(root)}
    component.write_state({"current": target, "previous": state["current"], "history": [*state["history"], {"event": "rollback", "version": target.get("version"), "at": now_text()}][-HISTORY_LIMIT:]})
    component.point_link(path)
    if not (run_command(settings["restartCommand"], values) and wait_healthy(settings["healthCommand"], values, settings["healthTimeoutS"], settings["healthIntervalS"], sleep)):
        raise DeployError(f"{name} went back to {target.get('version')} but did not pass the health check; look at the unit", EXIT_ROLLED_BACK)
    return component.state()


def prune(root: Path, name: str, keep: int) -> list[str]:
    """Remove the oldest releases beyond `keep`; the current one and the previous one stay whatever the number."""
    component = Component(root, name)
    state = component.state()
    protected = {entry["release"] for entry in (state["current"], state["previous"]) if entry and isinstance(entry.get("release"), str)}
    if not component.releases.is_dir():
        return []
    folders = sorted((p for p in component.releases.iterdir() if p.is_dir() and not p.name.startswith(".")), key=lambda p: p.stat().st_mtime, reverse=True)
    removed: list[str] = []
    for folder in folders[max(keep, len(protected)):]:
        if folder.name not in protected:
            shutil.rmtree(folder, ignore_errors=True)
            removed.append(folder.name)
    return removed


def status(root: Path, name: str | None = None) -> dict[str, Any]:
    names = [name] if name else sorted(p.name for p in root.iterdir() if p.is_dir() and (p / "state.json").is_file()) if root.is_dir() else []
    return {item: Component(root, item).state() for item in names}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, required=True, help="the folder that holds the components (/opt/hydra-umc on the device)")
    commands = parser.add_subparsers(dest="command", required=True)
    one = commands.add_parser("install", help="verify, install, switch, check and go back when it does not hold")
    one.add_argument("package", type=Path)
    one.add_argument("--trusted-key", help="the public key (64 hexadecimal digits) instead of config/release_key.pub")
    one.add_argument("--allow-downgrade", action="store_true", default=None)
    for word in ("rollback", "prune"):
        sub = commands.add_parser(word)
        sub.add_argument("component")
        if word == "prune":
            sub.add_argument("--keep", type=int, default=None)
    show = commands.add_parser("status")
    show.add_argument("component", nargs="?")
    args = parser.parse_args(argv)
    try:
        if args.command == "install":
            result = install(args.package, args.root, trusted_key=args.trusted_key, allow_downgrade=True if args.allow_downgrade else None)
        elif args.command == "rollback":
            result = rollback(args.root, args.component)
        elif args.command == "prune":
            keep = args.keep if args.keep is not None else int(load_settings(args.root)["keep"])
            result = {"removed": prune(args.root, args.component, max(2, keep))}
        else:
            result = status(args.root, args.component)
    except DeployError as error:
        print(f"DEPLOY=FAIL {error}", file=sys.stderr)
        return error.code
    print(json.dumps(result, indent=2, sort_keys=True))
    print("DEPLOY=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
