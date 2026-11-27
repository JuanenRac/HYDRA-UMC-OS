#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - tools/fleet_update.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Bring the programs installed on the device to the newest published release, one program at a time, with the progress in a file.

    python tools/fleet_update.py plan   --state /var/lib/hydra-umc/fleet-update.json      look only: what is installed against the newest release
    python tools/fleet_update.py run    --state ... --yes [--only datalake,twin]          apply the plan, in the order of the dependencies; stops at the first failure
    python tools/fleet_update.py resume --state ... --yes --only twin                      take up a program whose step was cut again
    python tools/fleet_update.py status --state ...                                        the file, with a cut run marked as interrupted

The order is the one of the dependencies: the operating system tools and the SDK (a checkout, nothing installed), then the services from the leaves to the orchestration, and
the server last (its frontend, Studio, goes with it). For each program: the disk is checked; the tag of the release is fetched and its commit must be the one GitHub gives
(and the signature of the tag when `requireSignedTags` is on); the program in use is kept as a `.tgz` together with its systemd unit and drop-ins and a hash of each; the
installer of this repository (`provisioning/install_<name>.sh --apply`) puts the new one in place and restarts that unit only; then it is checked: unit active, health route
answering, version the one of the release, no import error or missing file in the journal, and the SDK importable by the unit when the program uses it. When anything fails the
`.tgz` is put back, the unit files too (the ones the installer added are removed) and the file says whether the unit is as it was; the run stops there and the programs after
it are not touched. Nothing here restarts the machine: a command that would is refused.

The file (`hydra-fleet-update/1`) is written atomically at every step and a heartbeat file next to it is touched while the tool runs, so a reader can tell a run that was cut
(the machine, the network or the server restarted) from one that is still going: that program is `interrupted` and `resume` takes it up from its first step.

A program that runs from `<components>/<name>/current` (see `component_links.py`) is not touched by its installer, which would write into the release in use: with `usePackages` on (off by
default) it is updated with the signed package of its release (`hydra-<name>-<version>.tgz`, its `.sha256` and its `.sig` from the same release; `package_component.py verify` checks hash and signature,
`deploy_release.py install` keeps the release in use as `previous`, switches, restarts and goes back by itself); with it off, or when its release carries no package, it is left alone and said so.

Settings, all optional, in `<state folder>/fleet-update.json` or `--config`: `signedTags` (the names of the programs whose release tag must verify with `git verify-tag`: the server and the critical services; the rest are trusted by "the tag is the commit GitHub gives" over TLS), `requireSignedTags` (false; true asks it of every program), `minFreeMb` (800), `minFreeMbServer` (2500), `workspace` (~/hydra-umc),
`root` (/opt/hydra-umc), `backups` (/opt/hydra-umc-backups), `owner` (JuanenRac), `allowedSigners` (/etc/hydra-umc/allowed_signers: the public keys that `git verify-tag` trusts;
when the file exists it is passed to git for the check, so the result does not depend on the git configuration of the account that runs the tool). Standard library only.

`request` is the way in for a server that cannot run the tool itself (the unit of HYDRA-UMC-SERVER has no privilege, no sudo and no view of /home): the server leaves one small
file (`{"v":1,"id":..,"command":"plan"|"run"|"resume","names":[..]}`) in its data folder, a path unit of the device (`systemd/hydra-umc-fleet.path`) starts
`systemd/hydra-umc-fleet.service` under the account that owns the checkout and the rule of sudo, and that unit runs `fleet_update.py request --state S --request R --config C`.
The request is read without following a link, is taken away at once, is cut down to those fields (a name must match the pattern of a program, `run` and `resume` are
applied as with `--yes` because the server asks for them only after its own confirmation, `resume` names exactly one program), and the answer `{"id","command","exit"}` is written to `<state>.done`. The settings of a request come from
`--config` (a file that belongs to root) and never from the folder of the server, because a request must not be able to relax the signature check.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import shlex
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

SCHEMA = "hydra-fleet-update/1"
OWNER = "JuanenRac"
FORBIDDEN = re.compile(r"\b(reboot|shutdown|poweroff|halt|init\s+6|systemctl\s+(reboot|poweroff|halt))\b")
SECRET = re.compile(r"(?i)((?:secret|token|passw(?:or)?d|passphrase|jwt|api[_-]?key)\w*\s*[=:]\s*)\S+")
HEARTBEAT_SECONDS = 5
STALE_SECONDS = 60
EXIT_FAILED = 2
EXIT_BLOCKED = 3
DEFAULTS: dict[str, Any] = {
    "signedTags": ["os-tools", "os-agent", "server", "studio", "orchestrator", "safety-zones", "job-dispatcher"], "requireSignedTags": False, "verifyInstallerCheckout": True, "minFreeMb": 800, "minFreeMbServer": 2500, "workspace": "~/hydra-umc", "root": "/opt/hydra-umc",
    "backups": "/opt/hydra-umc-backups", "owner": OWNER, "usePackages": False, "allowedSigners": "/etc/hydra-umc/allowed_signers", "components": "/opt/hydra-umc/.components", "python": "python3",
}
ORDER = ["datalake", "twin", "swarm-sync", "telemetry-collector", "anomaly-detector", "detection-hef", "vision-node", "vision-streamer",
         "visual-servoing-api", "vla-engine", "semantic-planner", "safety-zones", "cognitive-node", "docs-qa", "hil-bridge", "production-reports",
         "node-healing", "local-technician", "job-dispatcher", "orchestrator", "voice-ui", "dashboard-ai", "os-agent", "server"]
EXTRA = {
    "server": dict(script="server", repo="HYDRA-UMC-SERVER", unit="hydra-umc-server.service", port=18200, health="/api/hydra-info"),
    "os-agent": dict(script="local_agent", repo="HYDRA-UMC-OS", unit="hydra-umc-agent.service", port=None, health=None),
}
PACKAGE_COMPONENTS = {"server", "studio", "os-agent"}      # the components that have a signed package (tools/package_component.py LAYOUT)
MAX_PACKAGE_BYTES = 300 * 1024 * 1024
SKIP_NAMES = {"kiosk", "wifi-provision", "splashscreen", "cm5_base", "gateway-industrial", "mqtt-broker", "mtconnect-adapter", "opcua-server"}
# the install scripts of the dependencies are added only when allowed (see server_build_command)
SERVER_BUILD = [("npm ci", "npm ci --no-audit --no-fund"), ("npm run build", "npm run build"), ("frontend", "bash build-frontend.sh")]
JOURNAL_BAD = re.compile(r"ModuleNotFoundError|ImportError|No such file or directory|FileNotFoundError|cannot find module", re.I)
STEPS = ["disk", "fetching", "backup", "building", "installing", "verifying"]
Sh = Callable[..., "tuple[int, str]"]


def write_atomically(target: Path, text: str) -> None:
    """Writes `target` whole through a new temporary file of an unpredictable name that is created exclusively and without following a link (`O_EXCL | O_NOFOLLOW`), then renames it over the target.
    The folders of the progress files are shared with the account of the server, which can create links in them: a link left under the name of the temporary file, or in place of the target,
    is never written through (the rename replaces the link itself)."""
    temporary = target.with_name(f"{target.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0), 0o666)
    try:
        with os.fdopen(descriptor, "wb") as out:
            out.write(text.encode("utf-8"))
        os.replace(temporary, target)
    except BaseException:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise


def redact(text: str) -> str:
    return SECRET.sub(r"\1***", text)


def vtuple(version: Any) -> tuple[int, ...] | None:
    try:
        return tuple(int(x) for x in str(version).lstrip("v").split("."))
    except ValueError:
        return None


def load_config(path: Path | None, warn: Callable[[str], None] = lambda m: print(m, file=sys.stderr)) -> dict[str, Any]:
    settings = dict(DEFAULTS)
    if path is None or not path.is_file():
        return settings
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        warn(f"{path} is not valid JSON; the defaults are used")
        return settings
    if not isinstance(raw, dict):
        warn(f"{path} must hold an object; the defaults are used")
        return settings
    for key, default in DEFAULTS.items():
        if key not in raw:
            continue
        value = raw[key]
        if isinstance(default, bool):
            if isinstance(value, bool):
                settings[key] = value
            else:
                warn(f"{path}: {key} must be true or false; {default} is used")
        elif isinstance(default, list):
            if isinstance(value, list) and len(value) <= 60 and all(isinstance(v, str) and re.fullmatch(r"[a-z][a-z0-9-]{0,40}", v) for v in value):
                settings[key] = list(value)
            else:
                warn(f"{path}: {key} must be a list of names of programs; the default list is used")
        elif isinstance(default, int):
            if isinstance(value, int) and not isinstance(value, bool) and 50 <= value <= 100000:
                settings[key] = value
            else:
                warn(f"{path}: {key} must be a whole number from 50 to 100000; {default} is used")
        elif isinstance(value, str) and value.strip() and "\0" not in value:
            settings[key] = value.strip()
        else:
            warn(f"{path}: {key} must be text; {default} is used")
    return settings


def default_download(url: str, destination: Path, max_bytes: int = MAX_PACKAGE_BYTES) -> None:
    """Fetches one file of a release from github.com (and nowhere else) to `destination`, through a temporary name; a file past the limit or an answer that is not 200 leaves nothing."""
    if not re.fullmatch(r"https://github\.com/[A-Za-z0-9-]{1,39}/HYDRA-UMC-[A-Z0-9-]{1,60}/releases/download/v?[0-9.]{1,20}/[A-Za-z0-9._-]{1,120}", url):
        raise OSError("not the address of a file of a release")
    partial = destination.with_name(destination.name + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "hydra-umc-os-fleet-update"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response, partial.open("wb") as out:  # nosec - https://github.com only (checked above)
            size = 0
            while chunk := response.read(1 << 20):
                size += len(chunk)
                if size > max_bytes:
                    raise OSError("the file is larger than the limit")
                out.write(chunk)
        os.replace(partial, destination)
    finally:
        partial.unlink(missing_ok=True)


def default_sh(argv: list[str], timeout: int = 1800, on_line: Callable[[str], None] | None = None) -> tuple[int, str]:
    """Runs one command without a shell; every line it prints goes to `on_line` as it comes. A command that would restart the machine is refused."""
    text = " ".join(argv)
    if FORBIDDEN.search(text):
        raise RuntimeError("refused: the device is never restarted by this tool: " + text)
    process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL)
    lines: list[str] = []
    timer = threading.Timer(timeout, process.kill)
    timer.start()
    try:
        assert process.stdout is not None
        for line in process.stdout:
            lines.append(line)
            if on_line:
                on_line(line.rstrip("\n"))
        process.wait()
    finally:
        timer.cancel()
    return process.returncode, "".join(lines)


def http_json(url: str, timeout: int = 20) -> Any:
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "hydra-umc-os-fleet-update", "X-GitHub-Api-Version": "2022-11-28"})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec - https://api.github.com only (see latest_release)
        return json.loads(response.read().decode("utf-8"))


def http_status(url: str, timeout: int = 5) -> int:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # nosec - loopback health route of a service of this device
            return int(response.status)
    except urllib.error.HTTPError as error:
        return int(error.code)
    except (urllib.error.URLError, OSError, ValueError):
        return 0


class Env:
    """Everything that touches the device, in one place, so that a test replaces it."""

    def __init__(self, state: Path, config: dict[str, Any] | None = None, sh: Sh = default_sh, http: Callable[[str], Any] = http_json,
                 health: Callable[[str], int] = http_status, now: Callable[[], float] = time.time, sleep: Callable[[float], None] = time.sleep,
                 log: Callable[[str], None] | None = None, free_mb: Callable[[str], int] | None = None, download: Callable[[str, Path], None] = default_download) -> None:
        self.state_path = state
        self.config = config or dict(DEFAULTS)
        self.sh, self.http, self.health, self.now, self.sleep = sh, http, health, now, sleep
        self.log = log or (lambda m: print(redact(m), flush=True))
        self.free_mb = free_mb or self._free_mb
        self.download = download
        self.components = Path(str(self.config['components']))
        self.tools = Path(__file__).resolve().parent
        self.workspace = Path(os.path.expanduser(str(self.config["workspace"])))
        self.root = Path(str(self.config["root"]))
        self.backups = Path(str(self.config["backups"]))
        self.unit_dir = Path("/etc/systemd/system")
        self.state: dict[str, Any] = {}

    @staticmethod
    def _free_mb(path: str) -> int:
        probe = path
        while probe and not os.path.exists(probe):
            probe = os.path.dirname(probe)
        usage = os.statvfs(probe or "/") if hasattr(os, "statvfs") else None
        return int(usage.f_bavail * usage.f_frsize / 1048576) if usage else 10**9

    # ---- the state file ---------------------------------------------------------------------------------------------------------------------------------
    @property
    def heartbeat_path(self) -> Path:
        return self.state_path.with_name(self.state_path.name + ".hb")

    def save(self) -> None:
        self.state["updatedAt"] = iso(self.now())
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        write_atomically(self.state_path, json.dumps(self.state, indent=1))

    def beat(self) -> None:
        try:
            write_atomically(self.heartbeat_path, str(self.now()))
        except OSError:
            pass

    def say(self, service: dict[str, Any] | None, text: str) -> None:
        self.log(text)
        if service is not None:
            service.setdefault("log", []).append({"at": iso(self.now()), "text": redact(text)[:300]})
            service["log"] = service["log"][-60:]
            service["detail"] = redact(text)[:200]
            self.beat()
            self.save()


def iso(seconds: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(seconds))


def sudo(argv: list[str]) -> list[str]:
    return argv if hasattr(os, "geteuid") and os.geteuid() == 0 else ["sudo", "-n", *argv]


# ---- the table of programs -------------------------------------------------------------------------------------------------------------------------------
def build_services(installers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    services: dict[str, dict[str, Any]] = {}
    for item in installers:
        target = item.get("target")
        if not target:
            continue
        name = Path(target).name
        services[name] = dict(name=name, script=item["script"][len("install_"):-len(".sh")], repo=item.get("source"), unit=item.get("unit") or f"hydra-umc-{name}.service",
                              port=item.get("port"), health=item.get("health_path"))
    for name, extra in EXTRA.items():
        services[name] = dict(name=name, **extra)
    rank = {name: index for index, name in enumerate(ORDER)}
    return [services[name] for name in sorted(services, key=lambda n: (rank.get(n, len(ORDER)), n))]


def inventory(env: Env) -> dict[str, Any]:
    """Reads the device: the plan of installers, the checkouts, the installed versions and units, the free space."""
    plan_file = env.workspace / "HYDRA-UMC-OS" / "provisioning" / "install_plan.json"
    installers = json.loads(plan_file.read_text(encoding="utf-8"))["installers"]
    repos: dict[str, Any] = {}
    if env.workspace.is_dir():
        for folder in sorted(env.workspace.iterdir()):
            if folder.name.startswith("HYDRA-UMC-") and (folder / ".git").exists():
                def git(*args: str, where: Path = folder) -> str:
                    return env.sh(["git", "-C", str(where), *args], 60)[1].strip()
                repos[folder.name] = {"describe": git("describe", "--tags", "--always"), "head": git("rev-parse", "HEAD"),
                                      "branch": git("symbolic-ref", "-q", "--short", "HEAD"),
                                      "dirty": len([ln for ln in git("status", "--porcelain").splitlines() if ln.strip()])}
    installed: dict[str, Any] = {}
    if env.root.is_dir():
        for folder in sorted(env.root.iterdir()):
            if not folder.is_dir() or folder.name.startswith("."):
                continue
            try:
                version = json.loads((folder / "hydra-umc.project.json").read_text(encoding="utf-8")).get("version")
            except (OSError, ValueError):
                version = None
            installed[folder.name] = {"version": version, "units": {}}
    return {"installers": installers, "repos": repos, "installed": installed}


def latest_release(env: Env, repo: str) -> dict[str, Any] | None:
    owner = str(env.config["owner"])
    try:
        data = env.http(f"https://api.github.com/repos/{owner}/{repo}/releases/latest")
        if not isinstance(data, dict) or not data.get("tag_name") or data.get("draft") or data.get("prerelease"):
            return None
        tag = str(data["tag_name"])
        if not re.fullmatch(r"v?\d+(\.\d+){1,4}", tag):
            return None
        commit = env.http(f"https://api.github.com/repos/{owner}/{repo}/commits/{tag}")
        sha = commit.get("sha") if isinstance(commit, dict) else None
        return {"tag": tag, "sha": sha if isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{40}", sha) else None, "assets": [a.get("name", "") for a in data.get("assets", []) if isinstance(a, dict)]}
    except (OSError, ValueError, urllib.error.URLError):
        return None


def classify(row: dict[str, Any], repo_state: dict[str, Any] | None, release: dict[str, Any] | None, include_inactive: bool) -> tuple[str, str]:
    installed = vtuple(row["installed"])
    if row["name"] in SKIP_NAMES:
        return "skip", "special_stack"
    if release is None:
        return "skip", "no_release"
    latest = vtuple(release["tag"])
    if installed is None or latest is None:
        return "review", "version_unreadable"
    if installed > latest:
        return "review", "installed_newer"
    if installed == latest:
        return "current", ""
    if not row["active"] and not include_inactive:
        return "skip", "unit_inactive"
    if repo_state and repo_state.get("dirty"):
        return "skip", "repo_dirty"
    return "update", ""


def is_wired(env: Env, name: str) -> bool:
    """The program runs from `<components>/<name>/current` (the unit still points at `<root>/<name>`, which is a link)."""
    link = env.root / name
    return link.is_symlink() and os.path.realpath(link) == os.path.realpath(env.components / name / "current")


def unit_state(env: Env, unit: str) -> str:
    rc, out = env.sh(["systemctl", "is-active", unit], 30)
    return out.strip().splitlines()[-1] if out.strip() else "unknown"


def make_plan(env: Env, include_inactive: bool = False, only: set[str] | None = None) -> dict[str, Any]:
    inv = inventory(env)
    cache: dict[str, Any] = {}

    def release(repo: str) -> dict[str, Any] | None:
        if repo not in cache:
            cache[repo] = latest_release(env, repo)
        return cache[repo]
    rows: list[dict[str, Any]] = []
    for repo, name in (("HYDRA-UMC-OS", "os-tools"), ("HYDRA-UMC-SDK", "sdk")):
        rs, rel = inv["repos"].get(repo), release(repo)
        describe = (rs or {}).get("describe", "")
        tag_now = describe.split("-")[0] if describe else None
        action, reason = ("skip", "no_release") if rel is None else ("current", "") if tag_now == rel["tag"] else ("skip", "repo_dirty") if rs and rs.get("dirty") else ("update", "") if rs else ("skip", "no_checkout")
        rows.append(dict(name=name, kind="repo", repo=repo, unit="", script="", port=None, health=None, installed=tag_now, latest=rel and rel["tag"], action=action, reason=reason,
                         state="waiting", step="", detail="", log=[], active=False))
    for svc in build_services(inv["installers"]):
        current = inv["installed"].get(svc["name"])
        if current is None:
            continue
        active = unit_state(env, svc["unit"]) == "active"
        rs = inv["repos"].get(svc["repo"]) if svc["repo"] else None
        rel = release(svc["repo"]) if svc["repo"] else None
        row = dict(name=svc["name"], kind="svc", repo=svc["repo"], unit=svc["unit"], script=svc["script"], port=svc["port"], health=svc["health"],
                   installed=current["version"], latest=rel and rel["tag"], active=active, state="waiting", step="", detail="", log=[])
        row["action"], row["reason"] = classify(row, rs, rel, include_inactive)
        row["wired"] = is_wired(env, svc["name"])
        if row["wired"] and row["action"] == "update":
            row["mode"] = "package"
            if not env.config["usePackages"]:
                row["action"], row["reason"] = "skip", "migrated_needs_packages"
            elif svc["name"] not in PACKAGE_COMPONENTS:
                row["action"], row["reason"] = "skip", "migrated_no_package"
        rows.append(row)
        if svc["name"] == "server":     # the frontend travels with the server: it is built from its newest release before the installer runs
            srel = release("HYDRA-UMC-STUDIO")
            rs2 = inv["repos"].get("HYDRA-UMC-STUDIO")
            tag_now = (rs2 or {}).get("describe", "").split("-")[0] or None
            rows.append(dict(name="studio", kind="frontend", repo="HYDRA-UMC-STUDIO", unit="", script="", port=None, health=None, installed=tag_now, latest=srel and srel["tag"],
                             action="skip" if row.get("mode") == "package" else row["action"] if row["action"] == "update" and srel else ("current" if srel and tag_now == srel["tag"] else "skip"),
                             reason="own_package" if row.get("mode") == "package" else "goes_with_server" if row["action"] == "update" else ("no_release" if srel is None else ""), state="waiting", step="", detail="", log=[], active=False))
    if only:
        for row in rows:
            if row["name"] not in only and row["action"] == "update":
                row["action"], row["reason"] = "skip", "not_asked"
    rank = {name: index for index, name in enumerate(["os-tools", "sdk", *ORDER, "studio"])}
    rows.sort(key=lambda r: (rank.get(r["name"], len(rank) - 2), r["name"]))
    for index, row in enumerate(rows):
        row["order"] = index
    releases = {repo: rel for repo, rel in cache.items() if rel}
    return {"schema": SCHEMA, "id": f"{int(env.now())}", "mode": "plan", "state": "planned", "startedAt": iso(env.now()), "updatedAt": iso(env.now()), "pid": os.getpid(),
            "disk": {"rootFreeMb": env.free_mb(str(env.root)), "workspaceFreeMb": env.free_mb(str(env.workspace))},
            "requireSignedTags": bool(env.config["requireSignedTags"]), "services": rows, "releases": releases, "error": "", "stoppedAt": ""}


# ---- applying ---------------------------------------------------------------------------------------------------------------------------------------------
class StepFailed(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


def step(env: Env, row: dict[str, Any], name: str, detail: str = "") -> None:
    row["step"] = name
    row["stepStartedAt"] = iso(env.now())
    env.say(row, f"{row['name']}: {name}{' - ' + detail if detail else ''}")


def unit_files(env: Env, unit: str) -> dict[str, str]:
    """The hash of the unit file and of every drop-in, as the machine has them now."""
    out: dict[str, str] = {}
    base = env.unit_dir
    candidates = [base / unit]
    folder = base / f"{unit}.d"
    if folder.is_dir():
        candidates += sorted(folder.glob("*"))
    for path in candidates:
        try:
            out[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            continue
    return out


def installed_version(env: Env, name: str) -> str | None:
    try:
        return json.loads((env.root / name / "hydra-umc.project.json").read_text(encoding="utf-8")).get("version")
    except (OSError, ValueError):
        return None


def check_disk(env: Env, row: dict[str, Any]) -> None:
    need = int(env.config["minFreeMbServer" if row["name"] == "server" else "minFreeMb"])
    free = min(env.free_mb(str(env.root)), env.free_mb(str(env.workspace)))
    row["freeMb"], row["needMb"] = free, need
    if free < need:
        raise StepFailed("low_disk", f"{free} MB free, {need} MB needed")


def needs_signed_tag(env: Env, row: dict[str, Any]) -> bool:
    """The tag must verify for the programs of the list `signedTags` (the server carries its Studio) and for all of them when `requireSignedTags` is on."""
    return bool(env.config["requireSignedTags"]) or row["name"] in env.config["signedTags"]


def signer_options(env: Env) -> list[str]:
    """The public keys the check of a tag trusts: the file of the device when it is there (the same for whichever account runs the tool), else the git configuration of that account."""
    signers = str(env.config.get("allowedSigners") or "")
    if signers and os.path.isfile(signers):
        return ["-c", "gpg.format=ssh", "-c", f"gpg.ssh.allowedSignersFile={signers}"]
    return []


def fetch_tag(env: Env, row: dict[str, Any], repo: str, release: dict[str, Any]) -> str:
    path = str(env.workspace / repo)
    previous = env.sh(["git", "-C", path, "symbolic-ref", "-q", "--short", "HEAD"], 30)[1].strip() or env.sh(["git", "-C", path, "rev-parse", "HEAD"], 30)[1].strip()
    if env.sh(["git", "-C", path, "fetch", "--tags", "--force", "-q", "origin"], 600)[0] != 0:
        raise StepFailed("fetch_failed", f"git fetch in {repo}")
    rc, out = env.sh(["git", "-C", path, "rev-parse", f"{release['tag']}^{{commit}}"], 30)
    commit = out.strip().splitlines()[-1] if out.strip() else ""
    if rc != 0 or not release.get("sha") or commit != release["sha"]:
        raise StepFailed("tag_mismatch", f"the tag {release['tag']} of {repo} is not the commit GitHub gives for it")
    if needs_signed_tag(env, row):
        if env.sh(["git", "-C", path, *signer_options(env), "verify-tag", release["tag"]], 60)[0] != 0:
            raise StepFailed("tag_unsigned", f"the tag {release['tag']} of {repo} does not verify")
    if env.sh(["git", "-C", path, "checkout", "-q", "--detach", release["tag"]], 120)[0] != 0:
        raise StepFailed("checkout_failed", f"git checkout in {repo}")
    return previous


INSTALLER_TAG = re.compile(r"v?\d+(\.\d+){1,4}")


def verify_installer_checkout(env: Env) -> str:
    """The installers run as root from the checkout of this repository, so before any of them runs that checkout must be exactly at a release tag that verifies with `git verify-tag`,
    with no tracked file changed. This does not depend on `signedTags` (a program may be trusted by the commit GitHub gives, the code that installs it as root may not). Off only with
    `verifyInstallerCheckout` false in the settings file of root. Returns the tag."""
    if not env.config.get("verifyInstallerCheckout", True):
        return ""
    path = str(env.workspace / "HYDRA-UMC-OS")
    rc, out = env.sh(["git", "-C", path, "describe", "--exact-match", "--tags", "HEAD"], 30)
    tags = [t for t in out.split() if INSTALLER_TAG.fullmatch(t)]
    if rc != 0 or not tags:
        raise StepFailed("installer_checkout_untagged", "the checkout of HYDRA-UMC-OS that holds the installers is not at a release tag")
    changed = [ln for ln in env.sh(["git", "-C", path, "status", "--porcelain", "--untracked-files=no"], 60)[1].splitlines() if ln.strip()]
    if changed:
        raise StepFailed("installer_checkout_dirty", "the checkout of HYDRA-UMC-OS that holds the installers has changed files")
    if env.sh(["git", "-C", path, *signer_options(env), "verify-tag", tags[0]], 60)[0] != 0:
        raise StepFailed("tag_unsigned", f"the tag {tags[0]} of the checkout of HYDRA-UMC-OS that holds the installers does not verify")
    return tags[0]


def backup(env: Env, row: dict[str, Any]) -> str:
    """One copy per program under an exact name (`<name>.bak.tgz`: the rule of sudo needs no wildcard): the program, its unit and its drop-ins. A program that was cut in the
    middle keeps the copy it already had, because what is installed now may be half of the new one."""
    name = row["name"]
    out = env.backups / f"{name}.bak.tgz"
    if row.get("backup") == str(out) and row.get("resumedFrom") == "interrupted" and out.exists():
        row["unitFilesBefore"] = row.get("unitFilesBefore") or unit_files(env, row["unit"])
        env.say(row, f"{name}: the copy made before the cut is kept")
        return str(out)
    unit = row["unit"]
    members = [str(env.root / name).lstrip("/"), str(env.unit_dir / unit).lstrip("/"), str(env.unit_dir / f"{unit}.d").lstrip("/")]
    env.sh(sudo(["mkdir", "-p", str(env.backups)]), 60)
    rc, text = env.sh(sudo(["tar", "czf", str(out), "--ignore-failed-read", "-C", "/", *members]), 900)
    if rc != 0:
        raise StepFailed("backup_failed", text.strip()[-200:])
    row["backup"] = str(out)
    row["unitFilesBefore"] = unit_files(env, unit)
    return str(out)


def npm_scripts_allowed(environ: Any = None) -> bool:
    """The same setting the installers read (`hydra_npm_install_flags` of provisioning/deploy_lib.sh): HYDRA_UMC_NPM_SCRIPTS, else
    `npm_scripts = on` of /etc/hydra-umc/provisioning.conf. Off unless it says so."""
    source = os.environ if environ is None else environ
    value = source.get("HYDRA_UMC_NPM_SCRIPTS", "")
    if not value:
        conf = Path(source.get("HYDRA_UMC_PROVISIONING_CONF", "/etc/hydra-umc/provisioning.conf"))
        try:
            found = re.findall(r"^\s*npm_scripts\s*=\s*(.*)$", conf.read_text(encoding="utf-8"), re.M)
        except (OSError, UnicodeDecodeError):
            found = []
        value = re.sub(r"[\s\"]", "", found[-1]) if found else ""
    return value.lower() in {"on", "1", "true", "yes"}


def server_build_command(command: str, environ: Any = None) -> str:
    if command.startswith("npm ci") and not npm_scripts_allowed(environ):
        return f"{command} --ignore-scripts"
    return command


def build_server(env: Env, row: dict[str, Any], release: dict[str, Any], studio: dict[str, Any] | None) -> None:
    if studio:
        fetch_tag(env, row, "HYDRA-UMC-STUDIO", studio)
    path = str(env.workspace / "HYDRA-UMC-SERVER")
    for index, (label, command) in enumerate(SERVER_BUILD, 1):
        row["substep"], row["substeps"] = label, len(SERVER_BUILD)
        step(env, row, "building", f"{label} ({index}/{len(SERVER_BUILD)}) - this takes minutes on the device")
        rc, text = env.sh(["bash", "-c", f"cd {shlex.quote(path)} && {server_build_command(command)} < /dev/null"], 3000, lambda line: (row.update(detail=redact(line)[:200]), env.beat()))
        if rc != 0:
            raise StepFailed("build_failed", f"{label}: {text.strip()[-160:]}")


def install(env: Env, row: dict[str, Any]) -> None:
    row["installersTag"] = verify_installer_checkout(env)
    script = env.workspace / "HYDRA-UMC-OS" / "provisioning" / f"install_{row['script']}.sh"
    step(env, row, "installing", "the installer compiles and restarts the unit; this can take minutes")
    started = env.now()

    def on_line(line: str) -> None:
        row["detail"] = redact(line)[:200]
        row["elapsedS"] = int(env.now() - started)
        env.beat()
    rc, text = env.sh(sudo(["bash", str(script), "--apply"]), 3000, on_line)
    row["installerStatus"] = rc
    if rc != 0:
        marker = [ln for ln in text.splitlines() if ln.startswith("DEPLOY=FAIL")]
        raise StepFailed("installer_failed", (marker[-1] if marker else text.strip()[-200:]))


def verify(env: Env, row: dict[str, Any], want: str) -> None:
    step(env, row, "verifying")
    name, unit = row["name"], row["unit"]
    for _attempt in range(12):
        try:
            version = json.loads((env.root / name / "hydra-umc.project.json").read_text(encoding="utf-8")).get("version")
        except (OSError, ValueError):
            version = None
        if version != want.lstrip("v"):
            raise StepFailed("version_mismatch", f"installed {version}, release {want}")
        if not row["active"]:
            return
        if unit_state(env, unit) == "active":
            ok = True
            if row.get("port") and row.get("health"):
                code = env.health(f"http://127.0.0.1:{row['port']}{row['health']}")
                ok = 200 <= code < 400
            if ok:
                break
        env.sleep(5)
    else:
        raise StepFailed("not_healthy", "the unit does not come back active and answering")
    rc, journal = env.sh(sudo(["journalctl", "-u", unit, "-n", "40", "--no-pager", "--since", "-2min"]), 60)
    bad = [ln for ln in journal.splitlines() if JOURNAL_BAD.search(ln)]
    if bad:
        raise StepFailed("journal_errors", redact(bad[-1])[:200])
    if uses_sdk(env, name):
        environment = env.sh(["systemctl", "show", "-p", "Environment", unit], 30)[1]
        match = re.search(r"PYTHONPATH=([^\s\"]+)", environment)
        code = env.sh(["env", f"PYTHONPATH={match.group(1) if match else ''}", "python3", "-c", "import hydra_umc_sdk"], 60)[0]
        if code != 0:
            raise StepFailed("sdk_not_importable", "the Python SDK is not on the PYTHONPATH of the unit")


def uses_sdk(env: Env, name: str) -> bool:
    folder = env.root / name
    if not folder.is_dir():
        return False
    try:
        for path in list(folder.rglob("*.py"))[:400]:
            if "hydra_umc_sdk" in path.read_text(encoding="utf-8", errors="ignore"):
                return True
    except OSError:
        return False
    return False


def roll_back(env: Env, row: dict[str, Any], previous: str | None) -> None:
    name, unit = row["name"], row["unit"]
    env.say(row, f"{name}: putting the earlier program back")
    if row.get("backup"):
        env.sh(sudo(["rm", "-rf", str(env.unit_dir / f"{unit}.d"), f"{env.root}/{name}.tmp"]), 120)
        # A step that fails is not "put back": the state stays failed and the line says by hand (a half-extracted copy is a mixed tree).
        code, text = env.sh(sudo(["tar", "xzf", row["backup"], "-C", "/"]), 900)
        if code != 0:
            raise RuntimeError(f"the copy could not be restored (tar status {code}): {text.strip()[-100:]}")
        env.sh(sudo(["systemctl", "daemon-reload"]), 60)
        if row.get("active"):
            code, text = env.sh(sudo(["systemctl", "restart", unit]), 120)
            if code != 0:
                raise RuntimeError(f"the unit did not start after the restore (status {code})")
        after = unit_files(env, unit)
        before = row.get("unitFilesBefore") or {}
        row["unitRestored"] = after == before
        if not row["unitRestored"]:
            env.say(row, f"{name}: the unit files are not as they were before the update; look at {unit} and its drop-ins")
    if previous:
        env.sh(["git", "-C", str(env.workspace / (row["repo"] or "")), "checkout", "-q", previous], 120)


def package_files(env: Env, row: dict[str, Any], release: dict[str, Any]) -> list[tuple[str, str]]:
    version = release["tag"].lstrip("v")
    package = f"hydra-{row['name']}-{version}.tgz"
    base = f"https://github.com/{env.config['owner']}/{row['repo']}/releases/download/{release['tag']}"
    return [(f"{base}/{package}{suffix}", f"{package}{suffix}") for suffix in ("", ".sha256", ".sig")]


def install_package(env: Env, row: dict[str, Any], release: dict[str, Any]) -> None:
    """A program that runs from its link: the signed package of its release, checked by the check of the family, installed by the deploy tool, which keeps the release in use and goes back by itself."""
    python = str(env.config["python"])
    work = env.state_path.parent / "packages"
    work.mkdir(parents=True, exist_ok=True)
    files = package_files(env, row, release)
    step(env, row, "fetching", f"the signed package {files[0][1]}")
    try:
        for url, name in files:
            (work / name).unlink(missing_ok=True)
            env.download(url, work / name)
    except (OSError, ValueError) as error:
        raise StepFailed("download_failed", redact(str(error))[:200]) from error
    package = work / files[0][1]
    row["mode"] = "package"
    rc, text = env.sh([python, str(env.tools / "package_component.py"), "verify", str(package)], 600)
    match = re.search(r"^PACKAGE=OK (\S+) (\S+) ([0-9a-f]{64})\s*$", text, re.M)
    if rc != 0 or not match or match.group(1) != row["name"] or match.group(2) != release["tag"].lstrip("v"):
        for _url, name in files:
            (work / name).unlink(missing_ok=True)
        raise StepFailed("signature_invalid", (text.strip().splitlines() or ["the package was refused"])[-1][:200])
    step(env, row, "installing", "the deploy tool keeps the release in use and goes back by itself")
    rc, text = env.sh([python, str(env.tools / "deploy_release.py"), "--root", str(env.components), "install", str(package)], 3000, lambda line: (row.update(detail=redact(line)[:200]), env.beat()))
    row["installerStatus"] = rc
    if rc != 0:
        marker = [ln for ln in text.splitlines() if ln.startswith("DEPLOY=FAIL")]
        raise StepFailed("installer_failed", marker[-1] if marker else text.strip()[-200:])
    try:
        verify(env, row, release["tag"])
    except StepFailed:
        env.say(row, f"{row['name']}: the checks failed; going back to the release that was in use")
        env.sh([python, str(env.tools / "deploy_release.py"), "--root", str(env.components), "rollback", row["name"]], 900)
        raise


def update_one(env: Env, row: dict[str, Any], releases: dict[str, Any]) -> bool:
    release = releases[row["repo"]]
    if row.get("mode") == "package":
        return update_one_by_package(env, row, release)
    row["state"], row["startedAt"], row["error"] = "running", iso(env.now()), ""
    previous: str | None = None
    try:
        step(env, row, "disk")
        if row["kind"] != "repo":
            check_disk(env, row)
        if row["kind"] == "svc" and row.get("resumedFrom") == "interrupted" and installed_version(env, row["name"]) == release["tag"].lstrip("v"):
            # The installer had finished when the run was cut (the usual case of the server, whose installer restarts the unit that runs this tool): only the checks are left.
            env.say(row, f"{row['name']}: {release['tag']} is already installed; only the checks are left")
            verify(env, row, release["tag"])
            row["state"], row["step"], row["finishedAt"] = "done", "done", iso(env.now())
            env.say(row, f"{row['name']}: {release['tag']} is in use")
            return True
        step(env, row, "fetching", f"{row['installed']} -> {release['tag']}")
        previous = fetch_tag(env, row, row["repo"], release)
        if row["kind"] == "repo":
            row["state"] = "done"
            env.say(row, f"{row['name']}: checkout done")
            return True
        row["installersTag"] = verify_installer_checkout(env)
        step(env, row, "backup")
        backup(env, row)
        if row["name"] == "server":
            build_server(env, row, release, releases.get("HYDRA-UMC-STUDIO"))
        install(env, row)
        verify(env, row, release["tag"])
        row["state"], row["step"] = "done", "done"
        row["finishedAt"] = iso(env.now())
        env.say(row, f"{row['name']}: {release['tag']} is in use")
        return True
    except StepFailed as failure:
        row["error"], row["detail"] = failure.code, failure.detail[:200]
        row["state"] = "blocked" if failure.code == "low_disk" else "failed"
    except Exception as failure:  # the rollback also needs this path
        row["error"], row["detail"], row["state"] = "unexpected", redact(str(failure))[:200], "failed"
    reason = row["detail"]
    env.say(row, f"{row['name']}: FAILED ({row['error']}) {reason}")
    if row["state"] == "failed" and row["kind"] == "svc" and row.get("backup"):
        try:
            roll_back(env, row, previous)
            row["state"] = "rolled_back"
        except Exception as problem:
            env.say(row, f"{row['name']}: THE ROLLBACK FAILED ({redact(str(problem))[:120]}); the copy is {row.get('backup', '-')}; intervene by hand")
    elif previous and row["repo"]:
        env.sh(["git", "-C", str(env.workspace / row["repo"]), "checkout", "-q", previous], 120)
    row["detail"] = reason
    row["finishedAt"] = iso(env.now())
    return False


def update_one_by_package(env: Env, row: dict[str, Any], release: dict[str, Any]) -> bool:
    row["state"], row["startedAt"], row["error"] = "running", iso(env.now()), ""
    try:
        step(env, row, "disk")
        check_disk(env, row)
        install_package(env, row, release)
        row["state"], row["step"], row["finishedAt"] = "done", "done", iso(env.now())
        env.say(row, f"{row['name']}: {release['tag']} is in use")
        return True
    except StepFailed as failure:
        row["error"], row["detail"] = failure.code, failure.detail[:200]
        row["state"] = "blocked" if failure.code == "low_disk" else "rolled_back" if failure.code in ("installer_failed", "not_healthy", "journal_errors", "version_mismatch", "sdk_not_importable") else "failed"
    except Exception as failure:
        row["error"], row["detail"], row["state"] = "unexpected", redact(str(failure))[:200], "failed"
    reason = row["detail"]
    env.say(row, f"{row['name']}: FAILED ({row['error']}) {reason}")
    row["detail"] = reason
    row["finishedAt"] = iso(env.now())
    return False


def heartbeat_thread(env: Env, stop: threading.Event) -> threading.Thread:
    def loop() -> None:
        while not stop.wait(HEARTBEAT_SECONDS):
            env.beat()
    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    return thread


def run_plan(env: Env, names: set[str] | None = None) -> int:
    """Applies the rows of the file marked `update` (the ones named, when some are), in order; stops at the first that fails."""
    state = env.state
    rows = [r for r in state["services"] if r["action"] == "update" and r["state"] in ("waiting", "interrupted", "failed", "rolled_back", "blocked", "skipped") and (not names or r["name"] in names)]
    if not rows:
        env.say(None, "nothing to update")
        state["mode"], state["state"] = "run", "done"
        env.save()
        return 0
    # The progress file lives in a folder that the account of the server can write, so nothing in it is trusted to say WHAT to install: the rows and the releases are taken from a plan
    # made now (the inventory of the device and the newest releases of GitHub, with the same rules as `plan`), and the file only says which of them to apply and how far they got.
    fresh = make_plan(env, include_inactive=True)
    by_name = {item["name"]: item for item in fresh["services"]}
    for row in rows:
        now_row = by_name.get(row["name"])
        interrupted = row["state"] == "interrupted"
        if now_row is None or now_row["action"] not in (("update", "current") if interrupted else ("update",)) or any(now_row.get(key) != row.get(key) for key in ("kind", "repo", "script", "unit")):
            state.update(mode="run", state="failed", error=row["name"], stoppedAt=row["name"])
            row.update(state="failed", error="plan_changed", detail="the saved plan does not match what the device and the releases say now; run plan again")
            env.say(None, f"{row['name']}: the saved plan does not match the device; nothing was applied")
            env.save()
            return EXIT_FAILED
    for row in rows:
        now_row = by_name[row["name"]]
        for key in ("port", "health", "mode", "wired", "installed", "latest", "action"):
            if key in now_row:
                row[key] = now_row[key]
            else:
                row.pop(key, None)
        if row.get("backup") != str(env.backups / f"{row['name']}.bak.tgz"):
            row.pop("backup", None)      # only the exact copy this tool makes is ever put back
    state["releases"] = dict(fresh["releases"])
    state.update(mode="run", state="running", pid=os.getpid(), startedAt=iso(env.now()), error="")
    for row in state["services"]:
        if row in rows:
            row["resumedFrom"] = row["state"]
            row.update(state="waiting", error="", step="", detail="")
    releases = dict(state["releases"])
    stop = threading.Event()
    env.beat()
    heartbeat_thread(env, stop)
    env.save()
    try:
        for row in rows:
            if row["name"] == "studio":      # it is built with the server, which came before it in the order
                row["state"], row["detail"] = "done", "built with the server"
                continue
            if not update_one(env, row, releases):
                state["state"], state["error"], state["stoppedAt"] = ("blocked" if row["state"] == "blocked" else "failed"), row["name"], row["name"]
                for rest in rows:
                    if rest["state"] == "waiting":
                        rest["state"], rest["detail"] = "skipped", f"stopped after {row['name']}"
                env.save()
                return EXIT_BLOCKED if row["state"] == "blocked" else EXIT_FAILED
            env.save()
        state["state"] = "done"
        env.say(None, "everything is updated")
        env.save()
        return 0
    finally:
        stop.set()


def mark_interrupted(state: dict[str, Any], heartbeat_age: float | None, alive: bool) -> bool:
    """A file that says running while the process is gone or silent: the program that was in its steps is `interrupted`."""
    if state.get("state") != "running":
        return False
    if alive and heartbeat_age is not None and heartbeat_age < STALE_SECONDS:
        return False
    for row in state.get("services", []):
        if row.get("state") == "running":
            row["state"], row["error"] = "interrupted", "interrupted"
            row["detail"] = f"cut at the step {row.get('step', '?')}"
    state["state"], state["error"] = "interrupted", "interrupted"
    return True


def pid_alive(pid: Any) -> bool:
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError, TypeError):
        return False


def load_state(env: Env) -> dict[str, Any]:
    try:
        state = json.loads(env.state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise SystemExit(f"no usable file at {env.state_path}: run plan first ({error})") from error
    if state.get("schema") != SCHEMA:
        raise SystemExit("the file is not a plan of this tool")
    try:
        age = env.now() - float(env.heartbeat_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        age = None
    if mark_interrupted(state, age, pid_alive(state.get("pid")) and state.get("pid") != os.getpid()):
        env.state = state
        env.save()
    return state


REQUEST_MAX_BYTES = 4096
REQUEST_ID = re.compile(r"[a-z0-9]{1,40}")
REQUEST_NAME = re.compile(r"[a-z][a-z0-9-]{0,40}")
REQUEST_COMMANDS = ("plan", "run", "resume")


def read_request(path: Path) -> tuple[dict[str, Any] | None, str]:
    """The request left by the server, cut down to its fields, and why it is refused when it is. The file is opened without following a link, must be a plain small file, and is taken away."""
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        return None, "missing"
    try:
        import stat as stat_module

        if not stat_module.S_ISREG(os.fstat(descriptor).st_mode):
            return None, "not a plain file"
        raw = os.read(descriptor, REQUEST_MAX_BYTES + 1)
    finally:
        os.close(descriptor)
        try:
            path.unlink()
        except OSError:
            pass
    if len(raw) > REQUEST_MAX_BYTES:
        return None, "too long"
    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None, "not JSON"
    if not isinstance(body, dict) or body.get("v") != 1:
        return None, "not a request of this tool"
    ident, command, names = body.get("id"), body.get("command"), body.get("names", [])
    if not isinstance(ident, str) or not REQUEST_ID.fullmatch(ident):
        return None, "bad id"
    if command not in REQUEST_COMMANDS:
        return {"id": ident}, "bad command"
    if not isinstance(names, list) or len(names) > 60 or not all(isinstance(n, str) and REQUEST_NAME.fullmatch(n) for n in names):
        return {"id": ident}, "bad names"
    if command == "resume" and len(names) != 1:
        return {"id": ident}, "resume names one program"
    return {"id": ident, "command": command, "names": list(dict.fromkeys(names))}, ""


def answer_request(env: Env, ident: str, command: str, code: int) -> None:
    """The answer the server waits for: written whole (a reader sees all of it or none of it), next to the progress file."""
    target = env.state_path.with_name(env.state_path.name + ".done")
    write_atomically(target, json.dumps({"id": ident, "command": command, "exit": code}))


def handle_request(request: Path, state: Path, config: Path | None, env: Env | None) -> int:
    """Runs what a request asks (`plan`, `run --yes` or `resume --yes`) through the same code as the command line, then leaves the answer. No request: nothing to do."""
    if env is None:
        env = Env(state, load_config(config))      # never the file beside the progress file: the folder of the server must not be able to change the settings
    body, why = read_request(request)
    if body is None and why == "missing":
        return 0
    if why or body is None or "command" not in body:
        print(f"FLEET=REFUSED the request is {why}", file=sys.stderr)
        if body and body.get("id"):
            answer_request(env, body["id"], "", 64)
        return 64
    argv = [body["command"], "--state", str(state)]
    if config is not None:
        argv += ["--config", str(config)]
    if body["names"] and body["command"] != "plan":
        argv += ["--only", ",".join(body["names"])]
    if body["command"] != "plan":
        argv.append("--yes")
    code = main(argv, env)
    answer_request(env, body["id"], body["command"], code)
    return code


def main(argv: list[str] | None = None, env: Env | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=["plan", "run", "resume", "status", "request"])
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--request", type=Path, help="request: the file the server leaves")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--only", help="names separated by commas")
    parser.add_argument("--include-inactive", action="store_true")
    parser.add_argument("--yes", action="store_true", help="really apply (without it run and resume only say what they would do)")
    args = parser.parse_args(argv)
    if args.command == "request":
        if args.request is None:
            print("FLEET=FAIL request needs --request <file>", file=sys.stderr)
            return 64
        return handle_request(args.request, args.state, args.config, env)
    names = {n.strip() for n in (args.only or "").split(",") if n.strip()} or None
    if env is None:
        env = Env(args.state, load_config(args.config or args.state.with_name("fleet-update.json")))
    if args.command == "plan":
        env.state = make_plan(env, args.include_inactive, names)
        env.save()
        print(json.dumps({"state": env.state["state"], "services": [(r["name"], r["installed"], r["latest"], r["action"], r["reason"]) for r in env.state["services"]]}))
        print("FLEET=PLANNED")
        return 0
    env.state = load_state(env)
    if args.command == "status":
        print(json.dumps(env.state))
        return 0
    if args.command == "resume" and not names:
        print("FLEET=FAIL resume needs --only <program>", file=sys.stderr)
        return 64
    if not args.yes:
        print("FLEET=REFUSED nothing is applied without --yes", file=sys.stderr)
        return 64
    code = run_plan(env, names)
    print("FLEET=PASS" if code == 0 else f"FLEET=FAIL {env.state.get('error', '')}", file=sys.stdout if code == 0 else sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
