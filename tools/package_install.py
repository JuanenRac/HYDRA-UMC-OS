#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - tools/package_install.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Put one signed package of a program on the device, with its systemd units, and go back when it does not hold. Nothing is compiled and nothing is fetched.

`install(package, device)` does, in this order, and undoes what it did when a step fails:

1. the package is verified (hash, signature of this component and version, member paths) and its `hydra-install.json` is checked against a closed set of names and
   folders; a package without that file (the first ones published) only replaces the program;
2. what the device must already have is checked: the Python version of the libraries inside, and, for a first installation, the files and system packages the
   program needs;
3. the account and the folders of the program are made; a program installed the old way (a plain folder) is moved under `<root>/.components/<name>/` with its data
   (`component_links.py`; the old folder is kept as `<name>.premigration`);
4. the release is installed as `releases/<version>-<n>` (`deploy_release.py`), then its units and drop-ins are put in place, the ones that were there being kept;
5. only the units that were running are restarted (a stopped service is updated and stays stopped; the machine is never restarted); they must come back active, the
   health route must answer and the journal must show no import error or missing file.

`rollback(name, device)` goes back to the release and the units that were there before. Standard library only; every command that touches the system goes through
`Device.sh`, so a test needs neither root nor systemd.
"""
from __future__ import annotations

import base64
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent


def _load(name: str) -> Any:
    key = f"hydra_helper_{name}"
    if key in sys.modules:
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, HERE / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module


pc = _load("package_component")
dr = _load("deploy_release")
links = _load("component_links")

UNIT = re.compile(r"^hydra-umc-[a-z0-9-]+@?\.(service|timer|path)$")
DROPIN = re.compile(r"^(hydra-umc-[a-z0-9-]+@?\.(?:service|timer|path))\.d/[0-9]{2}-[a-z0-9-]+\.conf$")
ACCOUNT = re.compile(r"^hydra-umc-[a-z0-9-]{1,20}$")
CONFIG_PATH = re.compile(r"^/etc/hydra-umc(-[a-z0-9-]+)?/[A-Za-z0-9._-]+$")
WRAPPER_PATH = re.compile(r"^/usr/local/bin/hydra-umc-[a-z0-9-]+$")
NEEDED_PATH = re.compile(r"^(/etc/hydra-umc(-[a-z0-9-]+)?/[A-Za-z0-9._-]+|/usr/local/bin/hydra-umc-[a-z0-9-]+)$")
PACKAGE_NAME = re.compile(r"^[a-z0-9][a-z0-9.+-]{1,60}$")
JOURNAL_BAD = re.compile(r"ModuleNotFoundError|ImportError|No such file or directory|FileNotFoundError|cannot find module", re.I)
Sh = Callable[..., "tuple[int, str]"]


class InstallError(Exception):
    """`code` is a short name Studio has a sentence for; `rolled_back` says whether what was there before is back."""

    def __init__(self, code: str, detail: str = "", rolled_back: bool | None = None) -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code, self.detail, self.rolled_back = code, detail, rolled_back


def default_sh(argv: list[str], timeout: int = 300) -> tuple[int, str]:
    if re.search(r"\b(reboot|shutdown|poweroff|halt)\b", " ".join(argv)):
        raise InstallError("refused", "the machine is never restarted by this tool")
    try:
        done = subprocess.run(argv, capture_output=True, text=True, errors="replace", timeout=timeout, check=False, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as error:
        return 127, str(error)
    return done.returncode, done.stdout + done.stderr


def default_health(url: str) -> int:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:  # nosec - loopback health route of a service of this device
            return int(response.status)
    except urllib.error.HTTPError as error:
        return int(error.code)
    except (urllib.error.URLError, OSError, ValueError):
        return 0


def default_chown(path: Path, user: str) -> None:
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        shutil.chown(path, user, user)


class Device:
    """Everything that touches the machine. `fsroot` is prefixed to every absolute path (a test uses a temporary folder)."""

    def __init__(self, fsroot: Path = Path("/"), *, sh: Sh = default_sh, health: Callable[[str], int] = default_health, sleep: Callable[[float], None] = time.sleep,
                 chown: Callable[[Path, str], None] = default_chown, trusted_key: str | None = None, python_version: str | None = None,
                 health_timeout_s: int = 40, say: Callable[[str], None] = lambda text: None) -> None:
        self.fsroot, self.sh, self.health, self.sleep, self.chown, self.say = Path(fsroot), sh, health, sleep, chown, say
        self.trusted_key, self.health_timeout_s = trusted_key, health_timeout_s
        self.python_version = python_version or f"{sys.version_info[0]}.{sys.version_info[1]}"

    def path(self, absolute: str) -> Path:
        return self.fsroot / absolute.lstrip("/")

    @property
    def root(self) -> Path:
        return self.path("/opt/hydra-umc")

    @property
    def components(self) -> Path:
        return self.root / ".components"

    @property
    def unit_dir(self) -> Path:
        return self.path("/etc/systemd/system")


# ---- the description inside the package ------------------------------------------------------------------------------------------------------------------
def check_spec(spec: Any, component: str, version: str) -> dict[str, Any]:
    """A signed package is as trusted as the release key, and it is still held to a closed set of names: a mistake in a package cannot write outside the program."""
    def bad(why: str) -> InstallError:
        return InstallError("bad_package", why)

    if not isinstance(spec, dict) or spec.get("format") != pc.SPEC_FORMAT or spec.get("component") != component or spec.get("version") != version:
        raise bad("the description inside the package is not the one of this package")
    units = spec.get("units", [])
    if not isinstance(units, list) or len(units) > 16 or not all(isinstance(u, str) and UNIT.match(u) for u in units):
        raise bad("a unit name is not one of the family")
    if spec.get("mainUnit") is not None and spec["mainUnit"] not in units:
        raise bad("the main unit is not one of the units")
    dropins = spec.get("dropins", {})
    if not isinstance(dropins, dict) or not all(isinstance(v, str) and len(v) < 4096 and (m := DROPIN.match(k)) and m.group(1) in units for k, v in dropins.items()):
        raise bad("a drop-in is not of a unit of the package")
    if spec.get("user") is not None and not (isinstance(spec["user"], str) and ACCOUNT.match(spec["user"])):
        raise bad("the account is not one of the family")
    for key in ("userDirs", "stateDirs"):
        if not all(isinstance(d, str) and dr.STATE_DIR.match(d) for d in spec.get(key, [])):
            raise bad(f"{key} must be plain folder names")
    for item in spec.get("createIfMissing", []):
        if not (CONFIG_PATH.match(str(item.get("path"))) and isinstance(item.get("content"), str) and item.get("mode") in ("0644", "0640", "0600")):
            raise bad("a configuration file to create is outside the configuration folders")
    for item in spec.get("wrappers", []):
        if not (WRAPPER_PATH.match(str(item.get("path"))) and isinstance(item.get("content"), str)):
            raise bad("a command to write is outside /usr/local/bin/hydra-umc-*")
    if not all(NEEDED_PATH.match(str(p)) for p in spec.get("needsFiles", [])) or not all(PACKAGE_NAME.match(str(p)) for p in spec.get("aptPackages", [])):
        raise bad("a requirement is not a file or package of the family")
    health = spec.get("health")
    if health is not None and not (isinstance(health.get("port"), int) and 0 < health["port"] < 65536 and re.fullmatch(r"/[A-Za-z0-9/_-]*", str(health.get("path")))):
        raise bad("the health route is not a plain local route")
    return spec


def read_spec(data: bytes, component: str, version: str) -> dict[str, Any] | None:
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        try:
            member = tar.extractfile(pc.SPEC_NAME)
        except KeyError:
            return None
        if member is None:
            return None
        try:
            spec = json.loads(member.read(65536).decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as error:
            raise InstallError("bad_package", "the description inside the package is not JSON") from error
    return check_spec(spec, component, version)


def check_requirements(device: Device, spec: dict[str, Any], first: bool) -> None:
    if spec.get("python") and spec["python"] != device.python_version:
        raise InstallError("wrong_python", f"the libraries of the package are for Python {spec['python']}; the device has {device.python_version}")
    missing = [p for p in spec.get("aptPackages", []) if device.sh(["dpkg", "-s", p])[0] != 0]
    if missing:
        raise InstallError("missing_system_package", " ".join(missing))
    if first:
        absent = [p for p in spec.get("needsFiles", []) if not device.path(p).is_file()]
        if absent:
            raise InstallError("needs_first_setup", " ".join(absent))


# ---- units ------------------------------------------------------------------------------------------------------------------------------------------------
def planned_files(device: Device, release: Path, spec: dict[str, Any]) -> dict[str, tuple[bytes, int]]:
    """Every file outside the program that the package wants: units, drop-ins and commands (absolute path -> bytes, mode)."""
    files: dict[str, tuple[bytes, int]] = {}
    for unit in spec.get("units", []):
        source = release / "systemd" / unit
        if not source.is_file():
            raise InstallError("bad_package", f"the package does not carry {unit}")
        files[f"/etc/systemd/system/{unit}"] = (source.read_bytes(), 0o644)
    for name, text in spec.get("dropins", {}).items():
        files[f"/etc/systemd/system/{name}"] = (text.encode("utf-8"), 0o644)
    for item in spec.get("wrappers", []):
        files[item["path"]] = (item["content"].encode("utf-8"), 0o755)
    return files


def write_file(target: Path, content: bytes, mode: int) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.new")
    temporary.write_bytes(content)
    os.chmod(temporary, mode)
    os.replace(temporary, target)


def keep_and_write(device: Device, files: dict[str, tuple[bytes, int]], record: Path) -> bool:
    """Writes the files that differ, after keeping in `record` what was there. Returns whether anything changed."""
    before: dict[str, Any] = {}
    for absolute, (content, _mode) in files.items():
        target = device.path(absolute)
        old = target.read_bytes() if target.is_file() else None
        if old != content:
            before[absolute] = None if old is None else {"content": base64.b64encode(old).decode("ascii"), "mode": target.stat().st_mode & 0o777}
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(json.dumps(before, indent=1, sort_keys=True), encoding="utf-8")
    for absolute in before:
        write_file(device.path(absolute), *files[absolute])
    return bool(before)


def restore(device: Device, record: Path) -> bool:
    if not record.is_file():
        return False
    before = json.loads(record.read_text(encoding="utf-8"))
    for absolute, old in before.items():
        target = device.path(absolute)
        if old is None:
            target.unlink(missing_ok=True)
        else:
            write_file(target, base64.b64decode(old["content"]), old["mode"])
    return bool(before)


def active_units(device: Device, units: list[str]) -> list[str]:
    """The units of the package that are running now, the instances of a template included."""
    found: list[str] = []
    for unit in units:
        if "@." in unit:
            pattern = unit.replace("@.", "@*.")
            rc, out = device.sh(["systemctl", "list-units", "--state=active", "--no-legend", "--plain", pattern])
            found += [line.split()[0] for line in out.splitlines() if rc == 0 and line.split()]
        elif device.sh(["systemctl", "is-active", unit])[1].strip().splitlines()[-1:] == ["active"]:
            found.append(unit)
    return found


def reload_units(device: Device) -> None:
    rc, out = device.sh(["systemctl", "daemon-reload"])
    if rc != 0:
        raise InstallError("units_failed", out.strip()[-200:])


def check_running(device: Device, spec: dict[str, Any], running: list[str], since: float) -> None:
    for unit in running:
        rc, out = device.sh(["systemctl", "restart", unit])
        if rc != 0:
            raise InstallError("restart_failed", f"{unit}: {out.strip()[-160:]}")
    # a oneshot service that was caught while it ran is not asked to stay active
    waiting = [u for u in running if u == spec.get("mainUnit") or u.endswith(".timer") or "@" in u]
    health = spec.get("health") if spec.get("mainUnit") in running else None
    tries = max(1, device.health_timeout_s // 2)
    for attempt in range(tries):
        down = [u for u in waiting if u not in active_units(device, [u])]
        code = device.health(f"http://127.0.0.1:{health['port']}{health['path']}") if health and not down else 200
        if not down and 200 <= code < 400:
            break
        if attempt == tries - 1:
            raise InstallError("not_healthy", f"{', '.join(down)} not active" if down else f"the health route answered {code}")
        device.sleep(2)
    for unit in waiting:
        rc, journal = device.sh(["journalctl", "-u", unit, "-n", "40", "--no-pager", "--since", f"@{int(since)}"])
        bad = [line for line in journal.splitlines() if JOURNAL_BAD.search(line)]
        if rc == 0 and bad:
            raise InstallError("journal_errors", bad[-1][-200:])


# ---- install and go back ---------------------------------------------------------------------------------------------------------------------------------
def make_accounts_and_folders(device: Device, name: str, spec: dict[str, Any]) -> None:
    user = spec.get("user")
    if user and device.sh(["id", "-u", user])[0] != 0:
        home = f"/opt/hydra-umc/{name}" + ("/data" if spec.get("homeInData") else "")
        rc, out = device.sh(["useradd", "--system", "--home", home, "--no-create-home", "--shell", "/usr/sbin/nologin", user])
        if rc != 0:
            raise InstallError("account_failed", out.strip()[-200:])
    for item in spec.get("createIfMissing", []):
        target = device.path(item["path"])
        if not target.exists():
            write_file(target, item["content"].encode("utf-8"), int(item["mode"], 8))


def prepare_layout(device: Device, name: str, spec: dict[str, Any] | None, unit_running: bool) -> str:
    """`wired`, `migrated` (a plain folder was moved under .components) or `first` (nothing installed yet)."""
    program, component = device.root / name, dr.Component(device.components, name)
    if links.wired(device.root, device.components, name):
        return "wired"
    state_dirs = (spec or {}).get("stateDirs", links.DEFAULT_STATE_DIRS)
    if program.is_dir() and not program.is_symlink():
        unit = (spec or {}).get("mainUnit") or ""

        def run(command: str, values: dict[str, str]) -> bool:
            if command in ("stop", "start") and unit_running and unit:
                return device.sh(["systemctl", command, unit])[0] == 0
            return True
        try:
            links.migrate(device.root, device.components, name, apply=True, unit=unit, run=run, say=device.say,
                          settings={"enabled": True, "stateDirs": list(state_dirs), "stopCommand": "stop", "startCommand": "start", "healthCommand": "health"})
        except links.LinkError as error:
            raise InstallError("migration_failed", str(error)) from error
        return "migrated"
    if program.exists() or program.is_symlink():
        raise InstallError("layout_unknown", f"{program} is neither a folder nor the link of a release")
    for folder in state_dirs:
        (component.base / "state" / folder).mkdir(parents=True, exist_ok=True)
        if spec and spec.get("user") and folder in spec.get("userDirs", []):
            device.chown(component.base / "state" / folder, spec["user"])
    return "first"


def record_path(component: Any, release: str) -> Path:
    return component.base / "units" / f"{release}.json"


def install(package: Path, device: Device, *, allow_first_install: bool = False) -> dict[str, Any]:
    try:
        name, version, _digest, data = pc.verify_package_bytes(package, device.trusted_key)
    except pc.PackageRefused as error:
        raise InstallError("signature_invalid", str(error)) from error
    spec = read_spec(data, name, version)
    component = dr.Component(device.components, name)
    first = not (device.root / name).exists() and not (device.root / name).is_symlink()
    if first and (spec is None or not allow_first_install):
        raise InstallError("first_install_off" if spec else "not_installed", f"{name} is not installed on this device")
    installed = links.program_version(device.root / name) if not first else "0.0.0"
    if not first and dr.version_key(version) <= dr.version_key(installed):
        raise InstallError("not_newer", f"{version} is not newer than the {installed} installed")
    if spec:
        check_requirements(device, spec, first)
        make_accounts_and_folders(device, name, spec)
    units = list((spec or {}).get("units", []))
    running = active_units(device, units)
    mode = prepare_layout(device, name, spec, bool(spec and spec.get("mainUnit") in running))
    settings = {**dr.DEFAULTS, "stateDirs": list((spec or {}).get("stateDirs", []))}
    try:
        state = dr.install(package, device.components, trusted_key=device.trusted_key, settings=settings)
    except dr.DeployError as error:
        raise InstallError("deploy_failed", str(error)) from error
    release = state["current"]["release"]
    since = time.time()
    try:
        if spec:
            for folder in spec.get("userDirs", []):
                target = component.base / "state" / folder
                if not target.exists():
                    # a program that never had the folder (a first release over a migrated one): it is made beside the releases and linked in
                    target.mkdir(parents=True)
                    device.chown(target, spec["user"])
                    dr.link_state(component, component.releases / release, [folder])
            if keep_and_write(device, planned_files(device, component.releases / release, spec), record_path(component, release)) and units:
                reload_units(device)
        if mode == "first":
            links.relative_link(component.link, device.root / name)
        if spec:
            device.say(f"{name}: {'restarting ' + ', '.join(running) if running else 'no unit of it is running: updated, left stopped'}")
            check_running(device, spec, running, since)
    except (InstallError, OSError) as failure:
        code = failure.code if isinstance(failure, InstallError) else "write_failed"
        detail = failure.detail if isinstance(failure, InstallError) else str(failure)
        back = go_back(device, name, running, remove_link=mode == "first")
        raise InstallError(code, detail, rolled_back=back) from failure
    return {"name": name, "version": version, "mode": mode, "release": release, "restarted": running, "previous": (state["previous"] or {}).get("version")}


def go_back(device: Device, name: str, running: list[str], *, remove_link: bool = False) -> bool:
    """Puts back the release and the files of before the newest release; returns whether everything came back."""
    component = dr.Component(device.components, name)
    state = component.state()
    current, previous = state["current"], state["previous"]
    ok = True
    try:
        if current and restore(device, record_path(component, current["release"])):
            reload_units(device)
        if previous and component.release_path(previous) and component.release_path(previous).is_dir():
            dr.rollback(device.components, name, settings=dict(dr.DEFAULTS))
        else:
            # nothing to go back to: the failed first release stays on disk, but nothing points at it
            component.write_state({"current": None, "previous": None, "history": [*state["history"], {"event": "removed", "at": dr.now_text()}], "pending": None})
            if remove_link and (device.root / name).is_symlink():
                (device.root / name).unlink()
            if component.link.is_symlink():
                component.link.unlink()
        for unit in running:
            if device.sh(["systemctl", "restart", unit])[0] != 0:
                ok = False
    except (InstallError, dr.DeployError, OSError, ValueError) as error:
        device.say(f"{name}: going back failed: {error}")
        ok = False
    return ok


def rollback(name: str, device: Device) -> dict[str, Any]:
    component = dr.Component(device.components, name)
    state = component.state()
    previous = state["previous"]
    path = component.release_path(previous)
    if not state["current"] or not path or not path.is_dir():
        raise InstallError("no_earlier_release", name)
    spec_file = component.releases / state["current"]["release"] / pc.SPEC_NAME
    units = json.loads(spec_file.read_text(encoding="utf-8")).get("units", []) if spec_file.is_file() else []
    running = active_units(device, [u for u in units if UNIT.match(u)])
    if not go_back(device, name, running):
        raise InstallError("rollback_failed", name, rolled_back=False)
    return {"name": name, "version": previous.get("version"), "restarted": running}
