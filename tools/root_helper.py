#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - tools/root_helper.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The root helper of the device: it brings the programs to their newest signed release, from the request the server leaves, and compiles nothing.

    root_helper.py request --request R --state S      what the path unit runs
    root_helper.py plan --state S                     look only
    root_helper.py totp-enroll                        makes the one-time code secret (printed once)

OFF BY DEFAULT: nothing happens, not even a look, unless `/etc/hydra-umc/helper.json` (owned by root) says `"enabled": true`. The server cannot change that file.

Two steps and a one-time code. `plan` compares what is installed with the newest release of each program and keeps, in a folder only root can read, an identifier of
exactly what it showed. `run`, `resume` and `rollback` must name that identifier (it is good once and for `planValidMinutes`), the releases must still be the same,
and, with `requireTotp` (on), bring a current six-digit code of `/etc/hydra-umc/helper.totp`; a code works once and wrong codes lock the door for longer each time.
So a server that has been taken over can ask to look, and nothing else.

What it applies: only `hydra-<component>-<version>.tgz` with its `.sha256` and `.sig` from the newest release of the repository of the program, fetched from
github.com, verified with the key it was installed with, never an older version. `package_install.py` does the installation and goes back by itself. The programs
that are stopped are updated and left stopped. The programs are taken one at a time, the server last; the first failure stops the run. The machine is never
restarted.

Settings of helper.json (all optional): enabled (false), requireTotp (true), allowFirstInstall (false: only programs already installed), owner (JuanenRac),
planValidMinutes (15), healthTimeoutS (40), minFreeMb (800). The progress is written in the format `hydra-fleet-update/1` that the server and Studio already read.
Standard library only.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import importlib.util
import json
import os
import re
import secrets
import shutil
import stat
import struct
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("hydra_helper_package_install", HERE / "package_install.py")
assert _spec and _spec.loader
pi = importlib.util.module_from_spec(_spec)
sys.modules["hydra_helper_package_install"] = pi
_spec.loader.exec_module(pi)
pc, dr, links = pi.pc, pi.dr, pi.links

SCHEMA = "hydra-fleet-update/1"
MAX_PACKAGE_BYTES = 300 * 1024 * 1024
REQUEST_MAX_BYTES = 4096
NAME = re.compile(r"[a-z][a-z0-9-]{0,40}")
COMMANDS = ("plan", "run", "resume", "rollback")
# the order of a run: what others use first, the helper itself and then the server last
ORDER = ["os-agent", "datalake", "twin", "swarm-sync", "telemetry-collector", "anomaly-detector", "detection-hef", "vision-node", "vision-streamer", "visual-servoing-api",
         "vla-engine", "semantic-planner", "safety-zones", "cognitive-node", "docs-qa", "hil-bridge", "production-reports", "node-healing", "local-technician",
         "job-dispatcher", "orchestrator", "voice-ui", "dashboard-ai", "studio", "helper", "server"]
DEFAULTS: dict[str, Any] = {"enabled": False, "requireTotp": True, "allowFirstInstall": False, "owner": "JuanenRac", "planValidMinutes": 15, "healthTimeoutS": 40, "minFreeMb": 800}
SECRET_TEXT = re.compile(r"(?i)((?:secret|token|passw(?:or)?d|passphrase|jwt|api[_-]?key)\w*\s*[=:]\s*)\S+")


def iso(seconds: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(seconds))


def redact(text: str) -> str:
    return SECRET_TEXT.sub(r"\1***", text)


def load_settings(path: Path) -> dict[str, Any]:
    """The settings of root. A file that is missing, unreadable or not JSON leaves the defaults, and the default is off."""
    settings = dict(DEFAULTS)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return settings
    if not isinstance(raw, dict):
        return settings
    for key, default in DEFAULTS.items():
        value = raw.get(key)
        if isinstance(default, bool) and isinstance(value, bool):
            settings[key] = value
        elif isinstance(default, int) and not isinstance(default, bool) and isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 100000:
            settings[key] = value
        elif key == "owner" and isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9-]{1,39}", value):
            settings[key] = value
    return settings


# ---- files in the folder of the server -------------------------------------------------------------------------------------------------------------------
class SharedFolder:
    """The folder where the server leaves its request and reads the progress. The account of the server can create links in it, so the folder is opened once without
    following a link, every file is opened relative to it without following a link, and a file is written whole under a new name and renamed over the old one."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.fd: int | None = None
        if os.open in os.supports_dir_fd:
            self.fd = os.open(folder, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
        elif folder.is_symlink() or not folder.is_dir():
            raise OSError(f"{folder} is not a plain folder")

    def _at(self, name: str) -> tuple[Any, dict[str, int]]:
        return (name, {"dir_fd": self.fd}) if self.fd is not None else (self.folder / name, {})

    def write(self, name: str, text: str, group: int | None = None) -> None:
        temporary = f"{name}.{secrets.token_hex(6)}.tmp"
        path, at = self._at(temporary)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0), 0o660, **at)
        try:
            with os.fdopen(descriptor, "wb") as out:
                out.write(text.encode("utf-8"))
                if self.fd is not None and hasattr(os, "fchmod"):
                    os.fchmod(out.fileno(), 0o660)
                    if group is not None and os.geteuid() == 0:
                        os.fchown(out.fileno(), -1, group)
            if self.fd is not None:
                os.rename(temporary, name, src_dir_fd=self.fd, dst_dir_fd=self.fd)
            else:
                os.replace(self.folder / temporary, self.folder / name)
        except BaseException:
            try:
                os.unlink(path, **at)
            except OSError:
                pass
            raise

    def take_request(self, name: str) -> tuple[dict[str, Any] | None, str]:
        """The request, cut down to its fields, and why it is refused when it is. A plain small file, opened without following a link, and taken away."""
        path, at = self._at(name)
        try:
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0), **at)
        except OSError:
            return None, "missing"
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                return None, "not a plain file"
            raw = os.read(descriptor, REQUEST_MAX_BYTES + 1)
        finally:
            os.close(descriptor)
            try:
                os.unlink(path, **at)
            except OSError:
                pass
        return parse_request(raw)

    def group(self) -> int | None:
        return os.fstat(self.fd).st_gid if self.fd is not None else None


def parse_request(raw: bytes) -> tuple[dict[str, Any] | None, str]:
    if len(raw) > REQUEST_MAX_BYTES:
        return None, "too long"
    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None, "not JSON"
    if not isinstance(body, dict) or body.get("v") != 1:
        return None, "not a request of this tool"
    ident, command, names = body.get("id"), body.get("command"), body.get("names", [])
    if not isinstance(ident, str) or not re.fullmatch(r"[a-z0-9]{1,40}", ident):
        return None, "bad id"
    if command not in COMMANDS:
        return {"id": ident}, "bad command"
    if not isinstance(names, list) or len(names) > 60 or not all(isinstance(n, str) and NAME.fullmatch(n) for n in names):
        return {"id": ident}, "bad names"
    if command in ("resume", "rollback") and len(names) != 1:
        return {"id": ident}, f"{command} names one program"
    plan_id, code = body.get("planId", ""), body.get("code", "")
    return {"id": ident, "command": command, "names": list(dict.fromkeys(names)),
            "planId": plan_id if isinstance(plan_id, str) and re.fullmatch(r"[0-9a-f]{32}", plan_id) else "",
            "code": code if isinstance(code, str) and re.fullmatch(r"[0-9]{6}", code) else ""}, ""


# ---- the one-time code -----------------------------------------------------------------------------------------------------------------------------------
def totp_code(secret_base32: str, counter: int) -> str:
    key = base64.b32decode(secret_base32.strip().upper() + "=" * (-len(secret_base32.strip()) % 8))
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    return f"{(struct.unpack('>I', digest[offset:offset + 4])[0] & 0x7FFFFFFF) % 1_000_000:06d}"


def totp_enroll(seed_file: Path) -> str:
    """Makes the secret once, in a file only root can read, and returns it; an existing one is never replaced."""
    seed_text = base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")
    seed_file.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(seed_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="ascii") as out:
        out.write(seed_text + "\n")
    return seed_text


class Door:
    """The two steps: what a plan showed, and the one-time code. Its memory is in a folder only root can read."""

    def __init__(self, private: Path, secret_file: Path, now: Callable[[], float] = time.time) -> None:
        self.private, self.secret_file, self.now = private, secret_file, now

    def _read(self, name: str) -> dict[str, Any]:
        try:
            value = json.loads((self.private / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return value if isinstance(value, dict) else {}

    def _write(self, name: str, value: dict[str, Any]) -> None:
        self.private.mkdir(parents=True, exist_ok=True, mode=0o700)
        pi.write_file(self.private / name, json.dumps(value).encode("utf-8"), 0o600)

    def keep_plan(self, rows: list[dict[str, Any]]) -> str:
        plan_id = secrets.token_hex(16)
        self._write("plan.json", {"id": plan_id, "at": self.now(), "updates": {r["name"]: [r["installed"], r["latest"]] for r in rows if r["action"] == "update"},
                                  "previous": {r["name"]: [r["installed"], r["previous"]] for r in rows if r.get("previous")}})
        return plan_id

    def check_code(self, code: str) -> str:
        """"" when the code is good, else why not (`totp_not_set_up`, `totp_locked`, `totp_required`, `totp_invalid`)."""
        try:
            secret = self.secret_file.read_text(encoding="ascii").strip()
        except OSError:
            return "totp_not_set_up"
        memory = self._read("totp.json")
        now = self.now()
        if now < float(memory.get("lockedUntil", 0)):
            return "totp_locked"
        if not code:
            return "totp_required"
        counter = int(now // 30)
        for step in (counter - 1, counter, counter + 1):
            if step > int(memory.get("counter", 0)) and hmac.compare_digest(totp_code(secret, step), code):
                self._write("totp.json", {"counter": step, "failures": 0, "lockedUntil": 0})
                return ""
        failures = int(memory.get("failures", 0)) + 1
        locked = now + min(3600, 30 * 2 ** min(failures - 5, 10)) if failures >= 5 else 0
        self._write("totp.json", {"counter": int(memory.get("counter", 0)), "failures": failures, "lockedUntil": locked})
        return "totp_invalid"

    def open(self, plan_id: str, code: str, settings: dict[str, Any]) -> tuple[dict[str, Any], str]:
        """The plan that `plan_id` names, used up; or why not."""
        plan = self._read("plan.json")
        if not plan_id or not plan.get("id") or not hmac.compare_digest(str(plan["id"]), plan_id):
            return {}, "confirmation_needed"
        if self.now() - float(plan.get("at", 0)) > settings["planValidMinutes"] * 60:
            return {}, "plan_old"
        if settings["requireTotp"]:
            why = self.check_code(code)
            if why:
                return {}, why
        (self.private / "plan.json").unlink(missing_ok=True)
        return plan, ""


# ---- releases -------------------------------------------------------------------------------------------------------------------------------------------
def http_json(url: str) -> Any:
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "hydra-umc-os-helper", "X-GitHub-Api-Version": "2022-11-28"})
    with urllib.request.urlopen(request, timeout=20) as response:  # nosec - https://api.github.com only
        return json.loads(response.read().decode("utf-8"))


def download(url: str, destination: Path) -> None:
    if not re.fullmatch(r"https://github\.com/[A-Za-z0-9-]{1,39}/HYDRA-UMC-[A-Z0-9-]{1,60}/releases/download/v[0-9.]{1,20}/hydra-[A-Za-z0-9._-]{1,100}", url):
        raise OSError("not the address of a file of a release")
    request = urllib.request.Request(url, headers={"User-Agent": "hydra-umc-os-helper"})
    partial = destination.with_name(destination.name + ".part")
    try:
        with urllib.request.urlopen(request, timeout=60) as response, partial.open("wb") as out:  # nosec - https://github.com only
            size = 0
            while chunk := response.read(1 << 20):
                size += len(chunk)
                if size > MAX_PACKAGE_BYTES:
                    raise OSError("the file is larger than the limit")
                out.write(chunk)
        os.replace(partial, destination)
    finally:
        partial.unlink(missing_ok=True)


def latest_release(http: Callable[[str], Any], owner: str, repository: str) -> dict[str, Any] | None:
    try:
        data = http(f"https://api.github.com/repos/{owner}/{repository}/releases/latest")
        tag = str(data["tag_name"])
        if data.get("draft") or data.get("prerelease") or not re.fullmatch(r"v\d+(\.\d+){2,3}", tag):
            return None
        return {"version": tag[1:], "assets": [str(a.get("name", "")) for a in data.get("assets", []) if isinstance(a, dict)]}
    except (OSError, ValueError, KeyError, TypeError, AttributeError, urllib.error.URLError):
        return None


def package_files(component: str, version: str) -> list[str]:
    name = f"hydra-{component}-{version}.tgz"
    return [name, name + ".sha256", name + ".sig"]


# ---- the helper ------------------------------------------------------------------------------------------------------------------------------------------
class Helper:
    def __init__(self, state: Path, device: Any, settings: dict[str, Any], door: Door, downloads: Path, *, http: Callable[[str], Any] = http_json,
                 fetch: Callable[[str, Path], None] = download, now: Callable[[], float] = time.time, free_mb: Callable[[], int] | None = None) -> None:
        self.device, self.settings, self.door, self.downloads = device, settings, door, downloads
        self.http, self.fetch, self.now = http, fetch, now
        self.free_mb = free_mb or (lambda: shutil.disk_usage(device.root if device.root.exists() else device.fsroot).free // 1048576)
        self.name = state.name
        state.parent.mkdir(parents=True, exist_ok=True)
        self.shared = SharedFolder(state.parent)
        self.report: dict[str, Any] = {}

    def save(self) -> None:
        self.report["updatedAt"] = iso(self.now())
        self.shared.write(self.name, json.dumps(self.report, indent=1), self.shared.group())

    def beat(self) -> None:
        try:
            self.shared.write(self.name + ".hb", str(self.now()), self.shared.group())
        except OSError:
            pass

    def say(self, row: dict[str, Any], text: str, step: str = "") -> None:
        print(redact(text), flush=True)
        if step:
            row["step"] = step
        row.setdefault("log", []).append({"at": iso(self.now()), "text": redact(text)[:300]})
        row["log"] = row["log"][-30:]
        row["detail"] = redact(text)[:200]
        self.save()

    def installed(self, component: str) -> str | None:
        folder = self.device.root / component
        if not folder.is_dir():
            return None
        version = links.program_version(folder)
        return version if version != "0.0.0" else None

    def rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for component in sorted(pc.LAYOUT, key=lambda n: ORDER.index(n) if n in ORDER else len(ORDER)):
            installed = self.installed(component)
            present = (self.device.root / component).is_dir()
            if not present and not self.settings["allowFirstInstall"]:
                continue
            release = latest_release(self.http, self.settings["owner"], pc.LAYOUT[component][0])
            latest = release and release["version"]
            action, reason = "skip", "no_release"
            if release:
                complete = set(package_files(component, latest)) <= set(release["assets"])
                if present and installed is None:
                    action, reason = "review", "version_unreadable"
                elif installed and dr.version_key(installed) > dr.version_key(latest):
                    action, reason = "review", "installed_newer"
                elif installed == latest:
                    action, reason = "current", ""
                elif not complete:
                    action, reason = "skip", "no_signed_package"
                else:
                    action, reason = "update", "" if present else "first_install"
            if not present and action != "update":
                continue
            previous = dr.Component(self.device.components, component).state()["previous"]
            rows.append({"name": component, "kind": "frontend" if component == "studio" else "svc", "repo": pc.LAYOUT[component][0], "installed": installed, "latest": latest and f"v{latest}",
                         "previous": (previous or {}).get("version"), "mode": "package", "action": action, "reason": reason, "state": "waiting", "step": "", "detail": "", "error": "",
                         "log": [], "order": len(rows)})
        return rows

    def new_report(self, mode: str, rows: list[dict[str, Any]]) -> None:
        self.report = {"schema": SCHEMA, "id": str(int(self.now())), "mode": mode, "state": "planned" if mode == "plan" else "running", "startedAt": iso(self.now()), "pid": os.getpid(),
                       "disk": {"rootFreeMb": self.free_mb(), "workspaceFreeMb": None}, "requireSignedTags": False, "helper": "root",
                       "totpRequired": self.settings["requireTotp"], "planId": "", "error": "", "stoppedAt": "", "services": rows}

    def plan(self) -> int:
        rows = self.rows()
        self.new_report("plan", rows)
        self.report["planId"] = self.door.keep_plan(rows)
        self.save()
        return 0

    def refuse(self, why: str) -> int:
        """A request that changes nothing: the plan on screen stays, with the reason, and a new look gives a new identifier."""
        rows = self.rows()
        self.new_report("plan", rows)
        self.report["planId"] = self.door.keep_plan(rows)
        self.report["error"] = why
        self.save()
        print(f"HELPER=REFUSED {why}", file=sys.stderr)
        return 3

    def apply(self, command: str, names: list[str], plan_id: str, code: str) -> int:
        plan, why = self.door.open(plan_id, code, self.settings)
        if why:
            return self.refuse(why)
        seen = plan["previous"] if command == "rollback" else plan["updates"]
        wanted = names or list(seen)
        if not wanted or any(n not in seen for n in wanted):
            return self.refuse("plan_changed")
        rows = self.rows()
        by_name = {r["name"]: r for r in rows}
        for name in wanted:
            row = by_name.get(name)
            now = row and ([row["installed"], row["previous"]] if command == "rollback" else [row["installed"], row["latest"]] if row["action"] == "update" else None)
            if now != seen[name]:
                return self.refuse("plan_changed")
        for row in rows:
            if row["name"] not in wanted and row["action"] == "update":
                row["action"], row["reason"] = "skip", "not_asked"
        self.new_report("run", rows)
        self.save()
        stop = threading.Event()

        def keep_beating() -> None:
            while not stop.wait(5):
                self.beat()
        beating = threading.Thread(target=keep_beating, daemon=True)
        self.beat()
        beating.start()
        try:
            for row in [r for r in rows if r["name"] in wanted]:
                if not self.one(command, row):
                    self.report["state"], self.report["error"], self.report["stoppedAt"] = "failed", row["error"], row["name"]
                    self.save()
                    return 2
            self.report["state"] = "done"
            self.save()
            return 0
        finally:
            stop.set()

    def one(self, command: str, row: dict[str, Any]) -> bool:
        name = row["name"]
        row["state"] = "running"
        self.device.say = lambda text: self.say(row, text)
        try:
            if command == "rollback":
                self.say(row, f"{name}: going back to {row['previous']}", "installing")
                pi.rollback(name, self.device)
                row["state"] = "rolled_back"
            else:
                if self.free_mb() < self.settings["minFreeMb"]:
                    raise pi.InstallError("low_disk", f"{self.free_mb()} MB free")
                self.say(row, f"{name}: downloading {row['latest']}", "fetching")
                package = self.get(name, row["latest"].lstrip("v"))
                self.say(row, f"{name}: installing {row['latest']}", "installing")
                done = pi.install(package, self.device, allow_first_install=self.settings["allowFirstInstall"])
                row["installed"], row["previous"], row["state"] = done["version"], done["previous"], "done"
                self.say(row, f"{name}: {done['version']} is in place", "verifying")
        except pi.InstallError as failure:
            row["state"] = "rolled_back" if failure.rolled_back else "failed"
            row["error"], row["unitRestored"] = failure.code, failure.rolled_back
            self.say(row, f"{name}: {failure}")
            return False
        except (OSError, urllib.error.URLError) as failure:
            row["state"], row["error"] = "failed", "download_failed"
            self.say(row, f"{name}: {failure}")
            return False
        self.save()
        return True

    def get(self, component: str, version: str) -> Path:
        """The three files of the package, in a new folder only root can write."""
        folder = self.downloads / f"{component}-{version}"
        shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir(parents=True, mode=0o700)
        base = f"https://github.com/{self.settings['owner']}/{pc.LAYOUT[component][0]}/releases/download/v{version}/"
        for name in package_files(component, version):
            self.fetch(base + name, folder / name)
        # one package of each program is kept, the newest, for the operator to look at
        for other in self.downloads.glob(f"{component}-*"):
            if other != folder:
                shutil.rmtree(other, ignore_errors=True)
        return folder / package_files(component, version)[0]

    def answer(self, ident: str, command: str, code: int) -> None:
        self.shared.write(self.name + ".done", json.dumps({"id": ident, "command": command, "exit": code}), self.shared.group())

    def handle(self, request_name: str) -> int:
        body, why = self.shared.take_request(request_name)
        if body is None and why == "missing":
            return 0
        if why or body is None:
            print(f"HELPER=REFUSED the request is {why}", file=sys.stderr)
            if body:
                self.answer(body["id"], "", 64)
            return 64
        if body["command"] == "plan":
            code = self.plan()
        else:
            code = self.apply(body["command"], body["names"], body["planId"], body["code"])
        self.answer(body["id"], body["command"], code)
        return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=["request", "plan", "totp-enroll"])
    parser.add_argument("--state", type=Path)
    parser.add_argument("--request", type=Path)
    parser.add_argument("--config", type=Path, default=Path("/etc/hydra-umc/helper.json"))
    parser.add_argument("--secret", dest="seed_file", metavar="FILE", type=Path, default=Path("/etc/hydra-umc/helper.totp"))
    parser.add_argument("--private", type=Path, default=Path("/var/lib/hydra-umc-helper"))
    arguments = parser.parse_args(argv)
    if arguments.command == "totp-enroll":
        try:
            seed_text = totp_enroll(arguments.seed_file)
        except FileExistsError:
            print(f"HELPER=REFUSED {arguments.seed_file} exists; move it away to make a new one", file=sys.stderr)
            return 2
        print(f"Add this to an authenticator app, it is not shown again:\n  {seed_text}\n  otpauth://totp/HYDRA-UMC:helper?secret={seed_text}&issuer=HYDRA-UMC")
        return 0
    if arguments.state is None or (arguments.command == "request" and arguments.request is None):
        print("HELPER=FAIL --state (and --request for a request) are needed", file=sys.stderr)
        return 64
    settings = load_settings(arguments.config)
    if not settings["enabled"]:
        print(f"HELPER=OFF {arguments.config} does not say enabled: nothing was looked at or changed", file=sys.stderr)
        if arguments.command == "request" and arguments.request is not None and arguments.request.exists():
            # the request is taken away (or the path unit would start this again and again) and the server is told
            shared = SharedFolder(arguments.request.parent)
            body, _why = shared.take_request(arguments.request.name)
            if body:
                shared.write(arguments.state.name + ".done", json.dumps({"id": body["id"], "command": body.get("command", ""), "exit": 64}), shared.group())
        return 0
    if arguments.request is not None and arguments.request.parent != arguments.state.parent:
        print("HELPER=FAIL the request must be beside the state file", file=sys.stderr)
        return 64
    device = pi.Device(health_timeout_s=settings["healthTimeoutS"])
    helper = Helper(arguments.state, device, settings, Door(arguments.private, arguments.seed_file), arguments.private / "downloads")
    if arguments.command == "plan":
        return helper.plan()
    return helper.handle(arguments.request.name)


if __name__ == "__main__":
    sys.exit(main())
