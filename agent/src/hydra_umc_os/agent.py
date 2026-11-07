# =============================================================================
# HYDRA-UMC-OS - Read-only CM5 diagnostics agent
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================

"""Read-only diagnostics agent for a HYDRA-UMC CM5 node.

The agent deliberately reports local state only. It does not command the MCU,
move machinery, alter Raspberry Pi OS, or bypass hardware safety authority.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import re
import shutil
import socket
import stat
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

try:
    from . import __version__
except ImportError:
    # Real bug found while auditing CI: this module has always been run
    # two different ways - as a real installed package
    # (`from hydra_umc_os.agent import ...`, agent/src on sys.path/
    # PYTHONPATH - test_agent.py's own way) AND as a bare standalone
    # script (`python agent.py describe`/`health`, tools/
    # verify_sdk_contracts.py's own real way of invoking it, and
    # provisioning/preflight_cm5.py's own dynamic load). `from . import`
    # needs a real parent package context to resolve against, which
    # neither of those standalone-execution forms has - `__package__` is
    # `None`/empty there, not the "hydra_umc_os" this needs. Falls back
    # to making the package importable the ordinary way (its own parent
    # directory on sys.path) instead of assuming package context that
    # only the first form actually has.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from hydra_umc_os import __version__

# a stable identifier for THIS running agent process, generated once at
# import time - every health() call from the same "serve" loop reports the
# same boot_session_id, and it changes only when the process itself
# restarts. Without this, a caller polling health() over time (HYDRA-UMC-
# UPDATER, a dashboard, ...) had no way to distinguish "the agent has been
# continuously healthy since boot" from "the agent just restarted and
# happens to report READY again" - two very different real situations that
# used to look identical.
BOOT_SESSION_ID = str(uuid.uuid4())


DEFAULT_CONFIG: dict[str, Any] = {
    "schema_version": "1.0",
    "node": {"id": "hydra-umc-node", "profile": "base"},
    "diagnostics": {
        "minimum_free_bytes": 1_073_741_824,
        "maximum_temperature_celsius": 80.0,
    },
}


@dataclass(frozen=True)
class DeviceDescriptor:
    schema_version: str
    node_id: str
    profile: str
    hostname: str
    machine: str
    operating_system: str
    kernel: str
    interfaces: list[str]


@dataclass(frozen=True)
class HealthReport:
    schema_version: str
    state: str
    timestamp_utc: str
    checks: dict[str, dict[str, Any]]
    # previously a HealthReport carried no link to which agent build
    # produced it, nor to which running process instance - a caller
    # polling health() over time (HYDRA-UMC-UPDATER, a dashboard, ...) had
    # no way to distinguish "continuously healthy since boot" from "just
    # restarted and happens to report READY again", or to tell whether an
    # unexpected state change came with an agent upgrade.
    agent_version: str
    boot_session_id: str


def load_config(path: Path | None) -> dict[str, Any]:
    """Load a non-secret JSON profile and reject an invalid shape early."""
    if path is None:
        return json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        candidate = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"configuration file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"configuration is not valid JSON: {path}") from exc
    if not isinstance(candidate, dict) or candidate.get("schema_version") != "1.0":
        raise ValueError("configuration schema_version must be '1.0'")
    node = candidate.get("node")
    diagnostics = candidate.get("diagnostics")
    if not isinstance(node, dict) or not isinstance(node.get("id"), str) or not node["id"].strip():
        raise ValueError("configuration node.id must be a non-empty string")
    if "profile" in node and (not isinstance(node["profile"], str) or not node["profile"].strip()):
        raise ValueError("configuration node.profile must be a non-empty string when present")
    if not isinstance(diagnostics, dict):
        raise ValueError("configuration diagnostics must be an object")
    minimum_free_bytes = diagnostics.get("minimum_free_bytes")
    if isinstance(minimum_free_bytes, bool) or not isinstance(minimum_free_bytes, int) or minimum_free_bytes < 0:
        raise ValueError("configuration diagnostics.minimum_free_bytes must be a non-negative integer")
    # The threshold is optional for existing v1.0 configurations.  Keeping a
    # safe default preserves compatibility while ensuring heat is never
    # silently reported as healthy on a CM5.
    maximum_temperature = diagnostics.setdefault(
        "maximum_temperature_celsius",
        DEFAULT_CONFIG["diagnostics"]["maximum_temperature_celsius"],
    )
    if (
        isinstance(maximum_temperature, bool)
        or not isinstance(maximum_temperature, (int, float))
        or not math.isfinite(maximum_temperature)
        or maximum_temperature <= 0
    ):
        raise ValueError("configuration diagnostics.maximum_temperature_celsius must be a positive finite number")
    # Optional: the folder whose volume the disk check measures (default: the working folder of the process, which the unit sets to the data folder).
    storage_path = diagnostics.get("storage_path")
    if storage_path is not None and (not isinstance(storage_path, str) or not storage_path.strip()):
        raise ValueError("configuration diagnostics.storage_path must be a non-empty string when present")
    validate_probes(diagnostics.get("probes"))
    validate_local_socket(diagnostics.get("local_socket"))
    return candidate


_PROGRAM = re.compile(r"[A-Za-z0-9._/-]{1,120}")
_UNIT = re.compile(r"[a-z0-9][a-z0-9@._-]{0,63}")


def validate_probes(probes: Any) -> None:
    """The optional `diagnostics.probes` block: off unless `enabled` is exactly true, plain names only, no shell anywhere."""
    if probes is None:
        return
    if not isinstance(probes, dict):
        raise ValueError("configuration diagnostics.probes must be an object when present")
    unknown = set(probes) - {"enabled", "vcgencmd", "systemctl", "hailo_device", "units", "timeout_seconds"}
    if unknown:
        raise ValueError(f"configuration diagnostics.probes has unknown keys: {sorted(unknown)}")
    if not isinstance(probes.get("enabled", False), bool):
        raise ValueError("configuration diagnostics.probes.enabled must be true or false")
    for key in ("vcgencmd", "systemctl"):
        value = probes.get(key)
        if value is not None and (not isinstance(value, str) or not _PROGRAM.fullmatch(value)):
            raise ValueError(f"configuration diagnostics.probes.{key} must be a program name or path of plain characters")
    device = probes.get("hailo_device")
    if device is not None and (not isinstance(device, str) or not device.startswith("/") or not _PROGRAM.fullmatch(device)):
        raise ValueError("configuration diagnostics.probes.hailo_device must be an absolute path of plain characters")
    units = probes.get("units", [])
    if not isinstance(units, list) or len(units) > 32 or any(not isinstance(unit, str) or not _UNIT.fullmatch(unit) for unit in units):
        raise ValueError("configuration diagnostics.probes.units must be a list of at most 32 unit names of plain characters")
    timeout = probes.get("timeout_seconds", 5)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not 0 < timeout <= 30:
        raise ValueError("configuration diagnostics.probes.timeout_seconds must be a number above 0 and at most 30")


def validate_local_socket(block: Any) -> None:
    """The optional `diagnostics.local_socket` block: off unless `enabled` is exactly true; an absolute path of plain characters; the mode of the socket file."""
    if block is None:
        return
    if not isinstance(block, dict):
        raise ValueError("configuration diagnostics.local_socket must be an object when present")
    unknown = set(block) - {"enabled", "path", "mode", "cache_seconds"}
    if unknown:
        raise ValueError(f"configuration diagnostics.local_socket has unknown keys: {sorted(unknown)}")
    if not isinstance(block.get("enabled", False), bool):
        raise ValueError("configuration diagnostics.local_socket.enabled must be true or false")
    path = block.get("path", DEFAULT_SOCKET_PATH)
    if not isinstance(path, str) or not path.startswith("/") or not _PROGRAM.fullmatch(path) or ".." in path.split("/") or len(path) > 100:
        raise ValueError("configuration diagnostics.local_socket.path must be an absolute path of plain characters (at most 100)")
    mode = block.get("mode", DEFAULT_SOCKET_MODE)
    if not isinstance(mode, str) or not re.fullmatch(r"0?[0-7]{3}", mode) or int(mode, 8) & 0o007:
        raise ValueError("configuration diagnostics.local_socket.mode must be an octal string such as '0660' that gives nothing to other users")
    cache = block.get("cache_seconds", 2)
    if isinstance(cache, bool) or not isinstance(cache, (int, float)) or not math.isfinite(cache) or not 0 <= cache <= 60:
        raise ValueError("configuration diagnostics.local_socket.cache_seconds must be a number from 0 to 60")


DEFAULT_SOCKET_PATH = "/run/hydra-umc-agent/agent.sock"
DEFAULT_SOCKET_MODE = "0660"
MAX_REQUEST_BYTES = 64


class LocalSocketServer:
    """A read-only endpoint on a UNIX socket: a client sends `describe` or `health` and one line, and gets one line of JSON back.

    Nothing else is understood, nothing is written anywhere and no command reaches the machine. Access is the mode of the socket file (and the
    permissions of its folder). A report is reused for `cache_seconds`, so a client that asks in a loop cannot make the probes run in a loop.
    """

    def __init__(self, config: dict[str, Any], *, path: str, mode: str = DEFAULT_SOCKET_MODE, cache_seconds: float = 2.0, clock: Any = time.monotonic) -> None:
        self.config = config
        self.path = path
        self.mode = int(mode, 8)
        self.cache_seconds = cache_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._cached: tuple[float, str] | None = None
        self._stop = threading.Event()
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "LocalSocketServer | None":
        block = config["diagnostics"].get("local_socket")
        if not block or block.get("enabled") is not True:
            return None
        return cls(config, path=block.get("path", DEFAULT_SOCKET_PATH), mode=block.get("mode", DEFAULT_SOCKET_MODE), cache_seconds=float(block.get("cache_seconds", 2)))

    def _free_the_path(self) -> None:
        """A leftover socket of a dead agent is removed; a live one, or anything that is not a socket, is never touched."""
        try:
            mode = os.lstat(self.path).st_mode
        except FileNotFoundError:
            return
        if not stat.S_ISSOCK(mode):
            raise ValueError(f"{self.path} exists and is not a socket")
        probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        probe.settimeout(1)
        try:
            probe.connect(self.path)
        except (ConnectionRefusedError, FileNotFoundError):
            os.unlink(self.path)
            return
        except OSError:
            raise ValueError(f"{self.path} could not be checked") from None
        finally:
            probe.close()
        raise ValueError(f"{self.path} is in use by another agent")

    def start(self) -> None:
        if not hasattr(socket, "AF_UNIX"):
            raise ValueError("this system has no UNIX sockets")
        if not Path(self.path).parent.is_dir():
            raise ValueError(f"the folder of {self.path} does not exist")
        self._free_the_path()
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        old = os.umask(0o177)  # closed from the first instant; the configured mode is applied right after
        try:
            sock.bind(self.path)
        finally:
            os.umask(old)
        os.chmod(self.path, self.mode)
        sock.listen(8)
        sock.settimeout(0.2)
        self._sock = sock
        self._thread = threading.Thread(target=self._loop, name="hydra-umc-agent-socket", daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        if self._sock is not None:
            self._sock.close()
            self._sock = None
            try:
                os.unlink(self.path)
            except OSError:
                pass

    def _loop(self) -> None:
        assert self._sock is not None
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            with conn:
                try:
                    conn.settimeout(2)
                    conn.sendall(self.answer(self._read_request(conn)).encode("utf-8"))
                except (OSError, ValueError):
                    pass  # a client that stalls, hangs up or sends too much only loses its own answer

    @staticmethod
    def _read_request(conn: socket.socket) -> bytes:
        data = b""
        while b"\n" not in data:
            chunk = conn.recv(MAX_REQUEST_BYTES + 1)
            if not chunk:
                break
            data += chunk
            if len(data) > MAX_REQUEST_BYTES:
                raise ValueError("request too long")
        return data.split(b"\n", 1)[0]

    def answer(self, request: bytes) -> str:
        """One line of JSON for one request; an unknown request is an error line, never a guess."""
        command = request.decode("utf-8", "replace").strip()
        if command not in ("describe", "health"):
            return json.dumps({"error": "unknown command", "commands": ["describe", "health"]}, separators=(",", ":")) + "\n"
        with self._lock:
            now = self._clock()
            if command == "health" and self._cached is not None and self.cache_seconds > 0 and now - self._cached[0] < self.cache_seconds:
                return self._cached[1]
            value = health(self.config) if command == "health" else describe(self.config)
            line = json.dumps(asdict(value), sort_keys=True, separators=(",", ":")) + "\n"
            if command == "health":
                self._cached = (now, line)
            return line


def query_socket(path: str, command: str = "health", timeout: float = 3.0) -> dict[str, Any]:
    """Asks a running agent over its socket and returns the answer (an error line is an error, not a report)."""
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(timeout)
    try:
        client.connect(path)
        client.sendall(command.encode("utf-8") + b"\n")
        data = b""
        while not data.endswith(b"\n"):
            chunk = client.recv(65536)
            if not chunk:
                break
            data += chunk
            if len(data) > 1_000_000:
                raise ValueError("the answer is too long")
    finally:
        client.close()
    answer = json.loads(data.decode("utf-8"))
    if not isinstance(answer, dict) or "error" in answer:
        raise ValueError(f"the agent refused the request: {answer.get('error') if isinstance(answer, dict) else 'unreadable answer'}")
    return answer


# Bits of `vcgencmd get_throttled`: the first four say what is happening now, the same four shifted by 16 say what happened since the boot.
_THROTTLE_NOW = {0x1: "under-voltage", 0x2: "arm-frequency-capped", 0x4: "throttled", 0x8: "soft-temperature-limit"}


def _run_probe(run: Any, argv: list[str], timeout: float) -> tuple[str | None, str | None]:
    """(standard output, why not): the program is never started through a shell and a slow one is cut off."""
    try:
        done = run(argv, capture_output=True, text=True, timeout=timeout, check=False)
    except FileNotFoundError:
        return None, f"{argv[0]} is not installed"
    except subprocess.TimeoutExpired:
        return None, f"{argv[0]} did not answer in {timeout:g} s"
    except OSError as exc:
        return None, f"{argv[0]} could not be started: {exc.strerror or type(exc).__name__}"
    if done.returncode != 0:
        return (done.stdout or "").strip(), f"{argv[0]} exited with status {done.returncode}"
    return (done.stdout or "").strip(), None


def throttle_check(output: str | None, why: str | None) -> dict[str, Any]:
    """FAIL while under-voltage or throttled right now, WARN for a cap, a soft limit, something that happened since the boot or an answer that cannot be read."""
    found = re.fullmatch(r"throttled=0x([0-9a-fA-F]{1,8})", output or "")
    if why is not None or found is None:
        return {"state": "WARN", "reason": why or "the answer of vcgencmd could not be read"}
    value = int(found.group(1), 16)
    now = [name for bit, name in _THROTTLE_NOW.items() if value & bit]
    past = [name for bit, name in _THROTTLE_NOW.items() if value & (bit << 16)]
    state = "FAIL" if value & 0x5 else "WARN" if now or past else "PASS"
    return {"state": state, "raw": f"0x{value:x}", "now": now, "since_boot": past}


def unit_check(output: str | None, why: str | None) -> dict[str, Any]:
    word = (output or "").splitlines()[0].strip() if output else ""
    if word == "active":
        return {"state": "PASS", "active_state": word}
    if word == "failed":
        return {"state": "FAIL", "active_state": word}
    return {"state": "WARN", "active_state": word or "unknown", **({"reason": why} if why else {})}


def probe_checks(probes: dict[str, Any] | None, *, run: Any = subprocess.run, exists: Any = os.path.exists) -> dict[str, dict[str, Any]]:
    """The extra checks of `diagnostics.probes`: none unless it is enabled. A missing tool is a WARN with its reason, never a crash and never a PASS."""
    if not probes or probes.get("enabled") is not True:
        return {}
    timeout = float(probes.get("timeout_seconds", 5))
    checks: dict[str, dict[str, Any]] = {}
    output, why = _run_probe(run, [probes.get("vcgencmd", "vcgencmd"), "get_throttled"], timeout)
    checks["throttling"] = throttle_check(output, why)
    device = probes.get("hailo_device")
    if device is not None:
        present = bool(exists(device))
        checks["hailo"] = {"state": "PASS" if present else "WARN", "device": device, "present": present}
    for unit in probes.get("units", []):
        output, why = _run_probe(run, [probes.get("systemctl", "systemctl"), "is-active", unit], timeout)
        checks[f"unit:{unit}"] = unit_check(output, why)
    return checks


def storage_probe_path(diagnostics: dict[str, Any]) -> Path:
    """The folder whose volume the storage check measures: diagnostics.storage_path when it exists, otherwise the working folder."""
    configured = diagnostics.get("storage_path")
    if isinstance(configured, str) and configured.strip() and Path(configured).is_dir():
        return Path(configured)
    return Path.cwd()


def network_interfaces(sys_class_net: Path = Path("/sys/class/net")) -> list[str]:
    if not sys_class_net.is_dir():
        return []
    return sorted(entry.name for entry in sys_class_net.iterdir() if entry.name != "lo")


def read_temperature_celsius(path: Path = Path("/sys/class/thermal/thermal_zone0/temp")) -> float | None:
    """Read the Linux thermal zone when available; never changes device state."""
    try:
        return int(path.read_text(encoding="utf-8").strip()) / 1000.0
    except (OSError, ValueError):
        return None


def load_profile(path: Path) -> dict[str, Any]:
    """Load an opt-in profile declaration; it never starts services itself."""
    try:
        profile = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"profile is not valid JSON: {path}") from exc
    if profile.get("schema_version") != "1.0" or not isinstance(profile.get("profile"), str) or not profile["profile"]:
        raise ValueError("profile requires schema_version '1.0' and a non-empty profile name")
    if not isinstance(profile.get("enabled_services"), list) or not isinstance(profile.get("requires"), list):
        raise ValueError("profile enabled_services and requires must be arrays")
    for field in ("enabled_services", "requires"):
        values = profile[field]
        if not all(isinstance(value, str) and value for value in values):
            raise ValueError(f"profile {field} must contain non-empty strings")
        if len(values) != len(set(values)):
            raise ValueError(f"profile {field} must not contain duplicates")
    return profile


def describe(config: dict[str, Any], interfaces: list[str] | None = None) -> DeviceDescriptor:
    node = config["node"]
    return DeviceDescriptor(
        schema_version="1.0",
        node_id=node["id"],
        profile=node.get("profile", "base"),
        hostname=socket.gethostname(),
        machine=platform.machine(),
        operating_system=platform.system(),
        kernel=platform.release(),
        interfaces=network_interfaces() if interfaces is None else interfaces,
    )


def health(
    config: dict[str, Any],
    *,
    free_bytes: int | None = None,
    interfaces: list[str] | None = None,
    temperature_celsius: float | None = None,
    probe_run: Any = subprocess.run,
) -> HealthReport:
    """Produce a deterministic health state from non-invasive local checks."""
    diagnostics = config["diagnostics"]
    available = shutil.disk_usage(storage_probe_path(diagnostics)).free if free_bytes is None else free_bytes
    active_interfaces = network_interfaces() if interfaces is None else interfaces
    temperature = read_temperature_celsius() if temperature_celsius is None else temperature_celsius
    minimum = diagnostics["minimum_free_bytes"]
    maximum_temperature = diagnostics.get(
        "maximum_temperature_celsius",
        DEFAULT_CONFIG["diagnostics"]["maximum_temperature_celsius"],
    )
    temperature_state = (
        "WARN" if temperature is None
        else "FAIL" if temperature >= maximum_temperature
        else "PASS"
    )
    checks = {
        "storage": {"state": "PASS" if available >= minimum else "FAIL", "free_bytes": available, "minimum_free_bytes": minimum},
        "network": {"state": "PASS" if active_interfaces else "WARN", "interfaces": active_interfaces},
        "runtime": {"state": "PASS", "python": platform.python_version(), "pid": os.getpid()},
        "temperature": {
            "state": temperature_state,
            "celsius": temperature,
            "maximum_celsius": maximum_temperature,
        },
    }
    checks.update(probe_checks(diagnostics.get("probes"), run=probe_run))
    # Real bug fixed while auditing the code: this used to only fold *network*
    # WARN into the overall DEGRADED state - an unreadable temperature
    # sensor (temperature_state == "WARN" above, e.g. a flaky/missing
    # thermal_zone0 on real hardware) left every other check PASS and was
    # silently reported as overall READY, exactly the kind of sensor
    # failure this agent exists to surface. Any WARN check now degrades
    # the overall state, matching what "WARN" is meant to signal.
    state = (
        "FAULT" if any(check["state"] == "FAIL" for check in checks.values())
        else "DEGRADED" if any(check["state"] == "WARN" for check in checks.values())
        else "READY"
    )
    return HealthReport(
        schema_version="1.0",
        state=state,
        timestamp_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        checks=checks,
        agent_version=__version__,
        boot_session_id=BOOT_SESSION_ID,
    )


def emit(value: DeviceDescriptor | HealthReport, *, compact: bool = False) -> None:
    if compact:
        # one line per report keeps the journal readable and the flash wear low
        print(json.dumps(asdict(value), sort_keys=True, separators=(",", ":")), flush=True)
    else:
        print(json.dumps(asdict(value), sort_keys=True, indent=2))


class ReportGate:
    """Decides whether a periodic report is worth writing to the journal.

    With ``on_change`` off every report is written (the long-standing behaviour).
    With it on, a report is written when the overall state or the state of any
    single check changed since the last written one, and otherwise at most once
    per ``heartbeat_s`` so a quiet device still shows that it is alive. Measured
    values (free bytes, temperature) never count as a change by themselves.
    """

    def __init__(self, on_change: bool = False, heartbeat_s: float = 300.0) -> None:
        self.on_change = on_change
        self.heartbeat_s = heartbeat_s
        self._signature: tuple | None = None
        self._last_written: float | None = None

    def should_emit(self, report: HealthReport, now: float) -> bool:
        if not self.on_change:
            return True
        signature = (report.state, tuple(sorted((name, check["state"]) for name, check in report.checks.items())))
        due = self._last_written is None or now - self._last_written >= self.heartbeat_s
        if signature != self._signature or due:
            self._signature = signature
            self._last_written = now
            return True
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, help="path to a validated non-secret JSON configuration")
    parser.add_argument("--interval", type=float, default=30.0, help="seconds between reports in serve mode")
    parser.add_argument("--report-on-change", action="store_true", help="in serve mode, write a report only when a state changed (plus a heartbeat)")
    parser.add_argument("--heartbeat", type=float, default=300.0, help="seconds between heartbeat reports with --report-on-change")
    parser.add_argument("--socket", dest="socket_path", help="with `query`: the UNIX socket of a running agent (diagnostics.local_socket)")
    parser.add_argument("--what", choices=("describe", "health"), default="health", help="with `query`: what to ask")
    parser.add_argument("command", choices=("describe", "health", "serve", "query"))
    args = parser.parse_args(argv)
    try:
        if args.command == "serve" and (not math.isfinite(args.interval) or args.interval <= 0):
            raise ValueError("serve interval must be a finite number greater than zero")
        if args.command == "query":
            if not args.socket_path:
                raise ValueError("query needs --socket")
            print(json.dumps(query_socket(args.socket_path, args.what), sort_keys=True, indent=2))
            return 0
        config = load_config(args.config)
        if args.command == "describe":
            emit(describe(config))
            return 0
        if args.command == "health":
            emit(health(config))
            return 0
        if args.command == "serve" and (not math.isfinite(args.heartbeat) or args.heartbeat <= 0):
            raise ValueError("serve heartbeat must be a finite number greater than zero")
        gate = ReportGate(args.report_on_change, args.heartbeat)
        local = LocalSocketServer.from_config(config)
        if local is not None:
            local.start()
        try:
            while True:
                report = health(config)
                if gate.should_emit(report, time.monotonic()):
                    emit(report, compact=True)
                time.sleep(args.interval)
        finally:
            if local is not None:
                local.close()
    except (ValueError, OSError) as exc:
        print(f"hydra-umc-agent: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
