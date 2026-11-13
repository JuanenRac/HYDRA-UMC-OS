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

Settings, all optional, in `<state folder>/fleet-update.json` or `--config`: `requireSignedTags` (false), `minFreeMb` (800), `minFreeMbServer` (2500), `workspace` (~/hydra-umc),
`root` (/opt/hydra-umc), `backups` (/opt/hydra-umc-backups), `owner` (JuanenRac). Standard library only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
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
    "requireSignedTags": False, "minFreeMb": 800, "minFreeMbServer": 2500, "workspace": "~/hydra-umc", "root": "/opt/hydra-umc",
    "backups": "/opt/hydra-umc-backups", "owner": OWNER,
}
ORDER = ["datalake", "twin", "swarm-sync", "telemetry-collector", "anomaly-detector", "detection-hef", "vision-node", "vision-streamer",
         "visual-servoing-api", "vla-engine", "semantic-planner", "safety-zones", "cognitive-node", "docs-qa", "hil-bridge", "production-reports",
         "node-healing", "local-technician", "job-dispatcher", "orchestrator", "voice-ui", "dashboard-ai", "os-agent", "server"]
EXTRA = {
    "server": dict(script="server", repo="HYDRA-UMC-SERVER", unit="hydra-umc-server.service", port=18200, health="/api/hydra-info"),
    "os-agent": dict(script="local_agent", repo="HYDRA-UMC-OS", unit="hydra-umc-agent.service", port=None, health=None),
}
SKIP_NAMES = {"kiosk", "wifi-provision", "splashscreen", "cm5_base", "gateway-industrial", "mqtt-broker", "mtconnect-adapter", "opcua-server"}
SERVER_BUILD = [("npm ci", "npm ci --no-audit --no-fund"), ("npm run build", "npm run build"), ("frontend", "bash build-frontend.sh")]
JOURNAL_BAD = re.compile(r"ModuleNotFoundError|ImportError|No such file or directory|FileNotFoundError|cannot find module", re.I)
STEPS = ["disk", "fetching", "backup", "building", "installing", "verifying"]
Sh = Callable[..., "tuple[int, str]"]


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
                 log: Callable[[str], None] | None = None, free_mb: Callable[[str], int] | None = None) -> None:
        self.state_path = state
        self.config = config or dict(DEFAULTS)
        self.sh, self.http, self.health, self.now, self.sleep = sh, http, health, now, sleep
        self.log = log or (lambda m: print(redact(m), flush=True))
        self.free_mb = free_mb or self._free_mb
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
        temporary = self.state_path.with_name(f"{self.state_path.name}.{os.getpid()}.tmp")
        temporary.write_text(json.dumps(self.state, indent=1), encoding="utf-8")
        os.replace(temporary, self.state_path)

    def beat(self) -> None:
        try:
            self.heartbeat_path.write_text(str(self.now()), encoding="utf-8")
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
        rows.append(row)
        if svc["name"] == "server":     # the frontend travels with the server: it is built from its newest release before the installer runs
            srel = release("HYDRA-UMC-STUDIO")
            rs2 = inv["repos"].get("HYDRA-UMC-STUDIO")
            tag_now = (rs2 or {}).get("describe", "").split("-")[0] or None
            rows.append(dict(name="studio", kind="frontend", repo="HYDRA-UMC-STUDIO", unit="", script="", port=None, health=None, installed=tag_now, latest=srel and srel["tag"],
                             action=row["action"] if row["action"] == "update" and srel else ("current" if srel and tag_now == srel["tag"] else "skip"),
                             reason="goes_with_server" if row["action"] == "update" else "", state="waiting", step="", detail="", log=[], active=False))
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


def check_disk(env: Env, row: dict[str, Any]) -> None:
    need = int(env.config["minFreeMbServer" if row["name"] == "server" else "minFreeMb"])
    free = min(env.free_mb(str(env.root)), env.free_mb(str(env.workspace)))
    row["freeMb"], row["needMb"] = free, need
    if free < need:
        raise StepFailed("low_disk", f"{free} MB free, {need} MB needed")


def fetch_tag(env: Env, row: dict[str, Any], repo: str, release: dict[str, Any]) -> str:
    path = str(env.workspace / repo)
    previous = env.sh(["git", "-C", path, "symbolic-ref", "-q", "--short", "HEAD"], 30)[1].strip() or env.sh(["git", "-C", path, "rev-parse", "HEAD"], 30)[1].strip()
    if env.sh(["git", "-C", path, "fetch", "--tags", "--force", "-q", "origin"], 600)[0] != 0:
        raise StepFailed("fetch_failed", f"git fetch in {repo}")
    rc, out = env.sh(["git", "-C", path, "rev-parse", f"{release['tag']}^{{commit}}"], 30)
    commit = out.strip().splitlines()[-1] if out.strip() else ""
    if rc != 0 or not release.get("sha") or commit != release["sha"]:
        raise StepFailed("tag_mismatch", f"the tag {release['tag']} of {repo} is not the commit GitHub gives for it")
    if env.config["requireSignedTags"]:
        if env.sh(["git", "-C", path, "verify-tag", release["tag"]], 60)[0] != 0:
            raise StepFailed("tag_unsigned", f"the tag {release['tag']} of {repo} does not verify")
    if env.sh(["git", "-C", path, "checkout", "-q", "--detach", release["tag"]], 120)[0] != 0:
        raise StepFailed("checkout_failed", f"git checkout in {repo}")
    return previous


def backup(env: Env, row: dict[str, Any]) -> str:
    name = row["name"]
    out = env.backups / f"{name}.bak_{time.strftime('%Y%m%d_%H%M%S', time.gmtime(env.now()))}.tgz"
    unit = row["unit"]
    members = [str(env.root / name).lstrip("/")]
    for candidate in (env.unit_dir / unit, env.unit_dir / f"{unit}.d"):
        if candidate.exists():
            members.append(str(candidate).lstrip("/"))
    rc, text = env.sh(sudo(["mkdir", "-p", str(env.backups)]), 60)
    rc, text = env.sh(sudo(["tar", "czf", str(out), "-C", "/", *members]), 900)
    if rc != 0:
        raise StepFailed("backup_failed", text.strip()[-200:])
    row["backup"] = str(out)
    row["unitFilesBefore"] = unit_files(env, unit)
    return str(out)


def build_server(env: Env, row: dict[str, Any], release: dict[str, Any], studio: dict[str, Any] | None) -> None:
    if studio:
        fetch_tag(env, row, "HYDRA-UMC-STUDIO", studio)
    path = str(env.workspace / "HYDRA-UMC-SERVER")
    for index, (label, command) in enumerate(SERVER_BUILD, 1):
        row["substep"], row["substeps"] = label, len(SERVER_BUILD)
        step(env, row, "building", f"{label} ({index}/{len(SERVER_BUILD)}) - this takes minutes on the device")
        rc, text = env.sh(["bash", "-c", f"cd {shlex.quote(path)} && {command} < /dev/null"], 3000, lambda line: (row.update(detail=redact(line)[:200]), env.beat()))
        if rc != 0:
            raise StepFailed("build_failed", f"{label}: {text.strip()[-160:]}")


def install(env: Env, row: dict[str, Any]) -> None:
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
        env.sh(sudo(["tar", "xzf", row["backup"], "-C", "/"]), 900)
        env.sh(sudo(["systemctl", "daemon-reload"]), 60)
        if row.get("active"):
            env.sh(sudo(["systemctl", "restart", unit]), 120)
        after = unit_files(env, unit)
        before = row.get("unitFilesBefore") or {}
        row["unitRestored"] = after == before
        if not row["unitRestored"]:
            env.say(row, f"{name}: the unit files are not as they were before the update; look at {unit} and its drop-ins")
    if previous:
        env.sh(["git", "-C", str(env.workspace / (row["repo"] or "")), "checkout", "-q", previous], 120)


def update_one(env: Env, row: dict[str, Any], releases: dict[str, Any]) -> bool:
    release = releases[row["repo"]]
    row["state"], row["startedAt"], row["error"] = "running", iso(env.now()), ""
    previous: str | None = None
    try:
        step(env, row, "disk")
        if row["kind"] != "repo":
            check_disk(env, row)
        step(env, row, "fetching", f"{row['installed']} -> {release['tag']}")
        previous = fetch_tag(env, row, row["repo"], release)
        if row["kind"] == "repo":
            row["state"] = "done"
            env.say(row, f"{row['name']}: checkout done")
            return True
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
    rows = [r for r in state["services"] if r["action"] == "update" and r["state"] in ("waiting", "interrupted", "failed", "rolled_back", "blocked") and (not names or r["name"] in names)]
    if not rows:
        env.say(None, "nothing to update")
        state["mode"], state["state"] = "run", "done"
        env.save()
        return 0
    state.update(mode="run", state="running", pid=os.getpid(), startedAt=iso(env.now()), error="")
    for row in state["services"]:
        if row in rows:
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


def main(argv: list[str] | None = None, env: Env | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=["plan", "run", "resume", "status"])
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--only", help="names separated by commas")
    parser.add_argument("--include-inactive", action="store_true")
    parser.add_argument("--yes", action="store_true", help="really apply (without it run and resume only say what they would do)")
    args = parser.parse_args(argv)
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
