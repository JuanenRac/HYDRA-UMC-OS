#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - Real WiFi first-contact provisioning (AP mode + client join)
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Real gap this closes: nothing anywhere in this ecosystem brings a
headless CM5 onto a real WiFi network for the first time, or lets an
operator's phone/laptop hand it real target-network credentials.
`CM5_DEPLOYMENT_SEQUENCE.md`'s own "Configure local Wi-Fi using the
Raspberry Pi supported first-boot method" was a real, honest pointer at
an out-of-band mechanism this repo owns none of - not a design.

Real design: NetworkManager (`nmcli`), the real, already-confirmed
network stack on this repo's own committed base (Raspberry Pi OS
Trixie - see `docs/CM5_PACKAGE_MANIFEST.md`). When this interface has
no active WiFi connection, this module brings up a real NetworkManager
hotspot (`nmcli device wifi hotspot`) an operator's phone/laptop can join
directly, and serves a small real HTTP form (stdlib `http.server`, same
`ThreadingHTTPServer`/handler-factory shape as
`HYDRA-UMC/src/cm5_host/spi_bridge/spi_bridge/http_service.py`) for the
real target SSID/password. A submitted attempt tears the hotspot down
(a single WiFi radio cannot be an AP and a client at once), tries the
real join, and - only on failure - brings the hotspot back up so the
operator can retry, rather than stranding the device with no way back in.

Every `nmcli` invocation lives behind one real, injectable
`NetworkManagerRunner` Protocol (`RealNetworkManager` is the only place
this module actually shells out to `nmcli`), so the real state machine
(`ensure_hotspot_if_disconnected`/`attempt_join`) is fully unit-testable
against an in-memory fake - no real WiFi radio, no root, no
NetworkManager install required to prove the logic is correct. Same
dry-run-by-default, explicit `--apply` convention as every other real,
mutating script in this repo's own `provisioning/` (`first_boot.sh`,
`install_cm5_base.sh`) - this module can genuinely reconfigure a real
network interface, so it never runs a mutating nmcli command without it.
"""
from __future__ import annotations

import argparse
import hmac
import importlib.util
import html
import json
import os
import secrets
import subprocess
import time
from pathlib import Path
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Protocol
from urllib.parse import parse_qs

DEFAULT_IFNAME = "wlan0"
DEFAULT_AP_SSID = "HYDRA-UMC-SETUP"


def device_default_ap_ssid() -> str:
    """The setup network name when none was chosen: the fixed name plus a part taken from this device.

    The part comes from device_identity.py, installed next to this file; without it (or with
    HYDRA_UMC_DEVICE_SUFFIX=off) the fixed name is used, as before.
    """
    path = Path(__file__).with_name("device_identity.py")
    try:
        spec = importlib.util.spec_from_file_location("hydra_umc_device_identity", path)
        if spec is None or spec.loader is None:
            return DEFAULT_AP_SSID
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.default_ap_ssid(DEFAULT_AP_SSID)
    except (OSError, ImportError, AttributeError, SyntaxError):
        return DEFAULT_AP_SSID
# The old, publicly known AP password. It is NEVER used as a fallback any more: a device
# without a configured password generates its own random one (resolve_ap_credentials) and
# an explicit value equal to this one (or a short one) is refused. The constant stays only
# so that a configuration still carrying it can be recognised and replaced.
DEFAULT_AP_PASSWORD = "hydraumc-setup"
MIN_AP_PASSWORD_LENGTH = 12
DEFAULT_PORT = 8080
# The setup network and form exist only for this long after the service starts (a device
# that is not set up by then simply stops offering them until the next boot).
DEFAULT_WINDOW_SECONDS = 1800
MAX_BODY_BYTES = 4096
MAX_CODE_FAILURES = 5
CODE_LOCKOUT_SECONDS = 60
DEFAULT_STATE_DIR = "/var/lib/hydra-umc/wifi-provision"
_PASSWORD_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # no look-alike characters (0/o, 1/l/i)


def ap_password_problem(password: str | None) -> str | None:
    """Why a configured AP password must not be used (None when it is acceptable)."""
    if not password:
        return "no AP password configured"
    if password == DEFAULT_AP_PASSWORD:
        return "the AP password is the publicly known default"
    if len(password) < MIN_AP_PASSWORD_LENGTH:
        return f"the AP password has fewer than {MIN_AP_PASSWORD_LENGTH} characters"
    return None


def resolve_ap_credentials(state_dir: Path, explicit_password: str | None = None) -> tuple[str, str, bool]:
    """The AP password and the one-time setup code of THIS device: (password, code, generated).

    A device must never offer a Wi-Fi network whose password is in the source code. An explicit, acceptable password is used as given; otherwise a random one is generated the first time
    and kept in `state_dir/credentials.json` (0600, root), so a restart keeps the same values and the label or the log line stays valid. The setup code is always generated: the form
    asks for it, so joining the setup network is not enough to hand the device a network.
    """
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / "credentials.json"
    stored: dict[str, str] = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                stored = {key: value for key, value in loaded.items() if isinstance(value, str)}
        except (OSError, ValueError):
            stored = {}
    generated = False
    password = explicit_password if ap_password_problem(explicit_password) is None else None
    if password is None:
        password = stored.get("password") if ap_password_problem(stored.get("password")) is None else None
    if password is None:
        password = "".join(secrets.choice(_PASSWORD_ALPHABET) for _ in range(16))
        generated = True
    code = stored.get("code") if (stored.get("code") or "").isdigit() and len(stored.get("code", "")) == 8 else None
    if code is None:
        code = f"{secrets.randbelow(10 ** 8):08d}"
        generated = True
    if generated or not path.exists():
        path.write_text(json.dumps({"password": password, "code": code}), encoding="utf-8")
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    return password, code, generated
POLL_INTERVAL_S = 5.0
NMCLI_TIMEOUT_S = 30


class NmcliError(RuntimeError):
    """A real `nmcli` invocation failed - message carries its own stderr."""


class NetworkManagerRunner(Protocol):
    """The minimal real NetworkManager surface this module depends on."""

    def active_wifi_connection(self, ifname: str) -> str | None: ...
    def start_hotspot(self, ifname: str, ssid: str, password: str) -> None: ...
    def stop_hotspot(self, ifname: str) -> None: ...
    def connect(self, ifname: str, ssid: str, password: str) -> None: ...
    def scan(self, ifname: str) -> list[str]: ...


class RealNetworkManager:
    """The only place this module shells out to the real `nmcli` binary.
    Every method raises `NmcliError` (carrying nmcli's own real stderr) on
    failure - a caller never has to catch a bare `CalledProcessError` or
    `FileNotFoundError` (nmcli not installed) itself."""

    def _run(self, *args: str) -> str:
        try:
            result = subprocess.run(
                ["nmcli", *args], capture_output=True, text=True, timeout=NMCLI_TIMEOUT_S, check=False
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            raise NmcliError(f"nmcli {' '.join(args)}: {exc}") from exc
        if result.returncode != 0:
            raise NmcliError(f"nmcli {' '.join(args)}: {result.stderr.strip() or result.stdout.strip()}")
        return result.stdout

    def active_wifi_connection(self, ifname: str) -> str | None:
        # -t (terse) -f (fields) - real nmcli scripting convention (man
        # nmcli, "Parseable output"), not a text-scraping guess.
        output = self._run("-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device", "status")
        for line in output.splitlines():
            fields = line.split(":")
            if len(fields) < 4:
                continue
            device, dtype, state, connection = fields[0], fields[1], fields[2], fields[3]
            if device == ifname and dtype == "wifi" and state == "connected":
                return connection or None
        return None

    def start_hotspot(self, ifname: str, ssid: str, password: str) -> None:
        # Real, real one-shot nmcli hotspot command (NetworkManager 1.x,
        # confirmed present on this repo's own Raspberry Pi OS Trixie
        # base) - creates and activates a real connection profile, always
        # named "Hotspot" by nmcli itself, bound to `ifname`.
        self._run("device", "wifi", "hotspot", "ifname", ifname, "ssid", ssid, "password", password)

    def stop_hotspot(self, ifname: str) -> None:
        del ifname  # nmcli's own hotspot profile name is fixed ("Hotspot"), not per-interface
        self._run("connection", "down", "Hotspot")
        self._run("connection", "delete", "Hotspot")

    def connect(self, ifname: str, ssid: str, password: str) -> None:
        self._run("device", "wifi", "connect", ssid, "password", password, "ifname", ifname)

    def scan(self, ifname: str) -> list[str]:
        self._run("device", "wifi", "rescan", "ifname", ifname)
        output = self._run("-t", "-f", "SSID", "device", "wifi", "list", "ifname", ifname)
        seen: list[str] = []
        for line in output.splitlines():
            ssid = line.strip()
            if ssid and ssid not in seen:
                seen.append(ssid)
        return seen


@dataclass(frozen=True)
class JoinResult:
    ok: bool
    reason: str


def ensure_hotspot_if_disconnected(
    runner: NetworkManagerRunner, ifname: str, ap_ssid: str, ap_password: str
) -> bool:
    """Real, idempotent step: does nothing (returns False) if `ifname`
    already has a real active WiFi connection; otherwise brings up the
    real AP (returns True) so an operator's phone/laptop can join it and
    submit real target-network credentials through the config server."""
    if runner.active_wifi_connection(ifname) is not None:
        return False
    runner.start_hotspot(ifname, ap_ssid, ap_password)
    return True


def attempt_join(
    runner: NetworkManagerRunner,
    ifname: str,
    ssid: str,
    password: str,
    ap_ssid: str = DEFAULT_AP_SSID,
    ap_password: str = DEFAULT_AP_PASSWORD,
) -> JoinResult:
    """Real join attempt. Tears the AP down first - a single WiFi radio
    cannot be an access point and a client at the same time - tries the
    real connect, and re-raises the hotspot ONLY on failure, so an
    operator whose next attempt reconnects to it (most phones remember
    and auto-rejoin a recently-used SSID) can retry instead of the device
    being stranded with no way back in. Never re-raises it on success -
    that would undo the very connection this call just made.

    `ap_ssid`/`ap_password` are the real AP credentials THIS RUN was
    configured with (from serve_until_joined's own caller) - the restart
    on failure must reuse them, not the module's own DEFAULT_AP_PASSWORD
    placeholder, or a deployment that overrode the default (as every real
    deployment must - see that constant's own comment) would silently
    fall back to the shared, publicly-known placeholder password the
    moment a join attempt failed."""
    try:
        runner.stop_hotspot(ifname)
    except NmcliError:
        pass  # already down / never started - not fatal, connect() below is the real gate

    try:
        runner.connect(ifname, ssid, password)
    except NmcliError as exc:
        _restart_hotspot_best_effort(runner, ifname, ap_ssid, ap_password)
        return JoinResult(False, str(exc))

    if runner.active_wifi_connection(ifname) is None:
        _restart_hotspot_best_effort(runner, ifname, ap_ssid, ap_password)
        return JoinResult(False, "connect reported success but the interface is not showing an active connection")

    return JoinResult(True, "")


def _restart_hotspot_best_effort(runner: NetworkManagerRunner, ifname: str, ap_ssid: str, ap_password: str) -> None:
    try:
        runner.start_hotspot(ifname, ap_ssid, ap_password)
    except NmcliError:
        pass  # best-effort recovery only - a failure here is reported by the NEXT status poll, not raised here


# -----------------------------------------------------------------------
# Real HTTP config server - same handler-factory shape as spi_bridge's
# own http_service.py (HYDRA-UMC/src/cm5_host/spi_bridge/).
# -----------------------------------------------------------------------

_FORM_PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>HYDRA-UMC Wi-Fi setup</title>
<meta name="viewport" content="width=device-width, initial-scale=1"></head>
<body style="font-family: sans-serif; max-width: 420px; margin: 2rem auto;">
<h1>HYDRA-UMC Wi-Fi setup</h1>
<p>{message}</p>
<form method="POST" action="/wifi">
<label>Network name (SSID)<br><input name="ssid" required style="width:100%"></label><br><br>
<label>Password<br><input name="password" type="password" style="width:100%"></label><br><br>
{code_field}<button type="submit">Connect</button>
</form>
</body></html>
"""


def make_handler(
    runner: NetworkManagerRunner,
    ifname: str,
    on_joined: "list[bool]",
    ap_ssid: str = DEFAULT_AP_SSID,
    ap_password: str = DEFAULT_AP_PASSWORD,
    setup_code: str | None = None,
) -> type[BaseHTTPRequestHandler]:
    """`setup_code` (the one-time code of this device) is required in the form when given: only someone who can read the device's label or log can hand it a network.
    A wrong code five times in a row locks the form for a minute. `on_joined` is a real, single-element mutable list used as a
    plain out-of-band signal (`on_joined[0] = True`) the serving loop
    below polls - `ThreadingHTTPServer` handlers are constructed fresh
    per request, so there is no `self` that would survive between
    requests to hold this state instead."""

    guard = {"failures": 0, "locked_until": 0.0}
    code_field = ('<label>Setup code (printed on the device label)<br><input name="code" inputmode="numeric" autocomplete="off" required style="width:100%"></label><br><br>' + chr(10)) if setup_code else ""

    class WifiConfigHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - stdlib's own signature
            pass  # real requests go to journald via systemd's own stdout capture, not duplicated here

        def _send_html(self, status: int, message: str) -> None:
            body = _FORM_PAGE.format(message=html.escape(message), code_field=code_field).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's own naming convention
            if self.path == "/":
                self._send_html(200, "Enter the Wi-Fi network this device should join.")
            elif self.path == "/networks":
                try:
                    ssids = runner.scan(ifname)
                    body = json.dumps({"ssids": ssids}).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except NmcliError as exc:
                    body = json.dumps({"error": str(exc)}).encode("utf-8")
                    self.send_response(502)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/wifi":
                self.send_response(404)
                self.end_headers()
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = -1
            if length < 0 or length > MAX_BODY_BYTES:
                self._send_html(413, "That request is too large.")
                return
            raw = self.rfile.read(length).decode("utf-8", errors="replace")
            fields = parse_qs(raw)
            if setup_code:
                now = time.monotonic()
                if now < guard["locked_until"]:
                    self._send_html(429, "Too many wrong codes. Wait a minute and try again.")
                    return
                given = (fields.get("code") or [""])[0].strip()
                if not hmac.compare_digest(given.encode("utf-8"), setup_code.encode("utf-8")):
                    guard["failures"] += 1
                    if guard["failures"] >= MAX_CODE_FAILURES:
                        guard["failures"] = 0
                        guard["locked_until"] = now + CODE_LOCKOUT_SECONDS
                    self._send_html(403, "The setup code is wrong.")
                    return
                guard["failures"] = 0
            ssid = (fields.get("ssid") or [""])[0].strip()
            password = (fields.get("password") or [""])[0]
            if not ssid:
                self._send_html(400, "A network name (SSID) is required.")
                return
            result = attempt_join(runner, ifname, ssid, password, ap_ssid, ap_password)
            if result.ok:
                on_joined[0] = True
                self._send_html(200, f"Connected to {ssid!r}. This setup page will stop responding shortly.")
            else:
                self._send_html(200, f"Could not connect to {ssid!r}: {result.reason}. Try again.")

    return WifiConfigHandler


def serve_until_joined(
    runner: NetworkManagerRunner,
    ifname: str,
    ap_ssid: str,
    ap_password: str,
    host: str = "0.0.0.0",
    port: int = DEFAULT_PORT,
    poll_interval_s: float = POLL_INTERVAL_S,
    setup_code: str | None = None,
    window_s: float | None = None,
) -> None:
    """Real serving loop: brings up the AP if needed, serves the config
    form, and returns as soon as a submitted attempt actually joins a
    real network - `main()` below is the only real caller, this function
    is what unit tests exercise instead (with a bounded fake server-tick
    substitute, since a real `ThreadingHTTPServer.serve_forever()` blocks
    by design)."""
    if not ensure_hotspot_if_disconnected(runner, ifname, ap_ssid, ap_password):
        # already on a network (the normal case at every boot): nothing to set up, and the
        # form must not stay open on the production LAN nor hold network-online.target
        print(f"WIFI_PROVISION=ALREADY_CONNECTED {ifname}")
        return
    joined = [False]
    handler = make_handler(runner, ifname, joined, ap_ssid, ap_password, setup_code)
    httpd = ThreadingHTTPServer((host, port), handler)
    print(f"WIFI_PROVISION=SERVING http://{host}:{port}/ (AP {ap_ssid!r} on {ifname})")
    deadline = None if window_s is None else time.monotonic() + window_s
    try:
        while not joined[0] and (deadline is None or time.monotonic() < deadline):
            httpd.timeout = poll_interval_s
            httpd.handle_request()
    finally:
        httpd.server_close()
    if joined[0]:
        print("WIFI_PROVISION=JOINED")
        return
    # nobody set the device up within the window: the setup network does not stay open for ever
    try:
        runner.stop_hotspot(ifname)
    except NmcliError:
        pass
    print("WIFI_PROVISION=WINDOW_CLOSED")


def _window_from_environment() -> float:
    """HYDRA_UMC_AP_WINDOW_S, or the default when it is unset or not a positive number
    (a typo must not make the service crash-loop at start-up)."""
    raw = os.environ.get("HYDRA_UMC_AP_WINDOW_S")
    if raw is None:
        return float(DEFAULT_WINDOW_SECONDS)
    try:
        value = float(raw)
    except ValueError:
        value = 0.0
    if not value > 0 or value == float("inf"):
        print(f"WIFI_PROVISION=WARNING HYDRA_UMC_AP_WINDOW_S={raw!r} is not a positive number: using {DEFAULT_WINDOW_SECONDS}")
        return float(DEFAULT_WINDOW_SECONDS)
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="required for any real network change")
    parser.add_argument("--ifname", default=DEFAULT_IFNAME)
    parser.add_argument("--ap-ssid", default=os.environ.get("HYDRA_UMC_AP_SSID") or device_default_ap_ssid())
    parser.add_argument(
        "--ap-password",
        default=os.environ.get("HYDRA_UMC_AP_PASSWORD"),
        help="optional: a password of at least 12 characters (or HYDRA_UMC_AP_PASSWORD); without one this device generates its own, kept in --state-dir",
    )
    parser.add_argument("--state-dir", default=os.environ.get("HYDRA_UMC_WIFI_STATE_DIR", DEFAULT_STATE_DIR))
    parser.add_argument("--window-seconds", type=float, default=_window_from_environment())
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)

    runner = RealNetworkManager()

    if not args.apply:
        connected = runner.active_wifi_connection(args.ifname) if _nmcli_available() else None
        print(
            f"[dry-run] would ensure a real WiFi connection on {args.ifname!r}, currently "
            f"{'connected as ' + connected if connected else 'not connected'}; "
            f"would serve the setup form on {args.host}:{args.port} if not. Re-run with --apply to act."
        )
        return 0

    problem = ap_password_problem(args.ap_password) if args.ap_password else None
    if problem:
        print(f"WIFI_PROVISION=WARNING {problem}: a password of this device's own is used instead")
    password, code, generated = resolve_ap_credentials(Path(args.state_dir), args.ap_password)
    # Root-only journal: this line is how the person at the device learns the password and the code (also kept in state-dir/credentials.json, 0600).
    if generated:
        print(f"WIFI_PROVISION=CREDENTIALS ssid={args.ap_ssid} password={password} code={code} (generated now)")
    else:
        print(f"WIFI_PROVISION=CREDENTIALS ssid={args.ap_ssid} (password and code are in {Path(args.state_dir) / 'credentials.json'})")
    serve_until_joined(runner, args.ifname, args.ap_ssid, password, args.host, args.port, setup_code=code, window_s=args.window_seconds)
    return 0


def _nmcli_available() -> bool:
    try:
        subprocess.run(["nmcli", "--version"], capture_output=True, timeout=5, check=False)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


if __name__ == "__main__":
    raise SystemExit(main())
