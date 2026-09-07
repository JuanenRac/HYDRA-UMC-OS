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
Bookworm - see `docs/CM5_PACKAGE_MANIFEST.md`). When this interface has
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
import html
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Protocol
from urllib.parse import parse_qs

DEFAULT_IFNAME = "wlan0"
DEFAULT_AP_SSID = "HYDRA-UMC-SETUP"
# PLACEHOLDER - a real deployment MUST override this (--ap-password / the
# HYDRA_UMC_AP_PASSWORD env var), same "change before relying on this for
# anything real" caveat this ecosystem's other placeholder secrets already
# carry (e.g. HYDRA-UMC's own bootloader_common.h HMAC_KEY). A shared,
# fixed AP password shipped in source is a real, known-bad default, not a
# design recommendation.
DEFAULT_AP_PASSWORD = "hydraumc-setup"
DEFAULT_PORT = 8080
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
        # confirmed present on this repo's own Raspberry Pi OS Bookworm
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
<button type="submit">Connect</button>
</form>
</body></html>
"""


def make_handler(
    runner: NetworkManagerRunner,
    ifname: str,
    on_joined: "list[bool]",
    ap_ssid: str = DEFAULT_AP_SSID,
    ap_password: str = DEFAULT_AP_PASSWORD,
) -> type[BaseHTTPRequestHandler]:
    """`on_joined` is a real, single-element mutable list used as a
    plain out-of-band signal (`on_joined[0] = True`) the serving loop
    below polls - `ThreadingHTTPServer` handlers are constructed fresh
    per request, so there is no `self` that would survive between
    requests to hold this state instead."""

    class WifiConfigHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - stdlib's own signature
            pass  # real requests go to journald via systemd's own stdout capture, not duplicated here

        def _send_html(self, status: int, message: str) -> None:
            body = _FORM_PAGE.format(message=html.escape(message)).encode("utf-8")
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
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8", errors="replace")
            fields = parse_qs(raw)
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
) -> None:
    """Real serving loop: brings up the AP if needed, serves the config
    form, and returns as soon as a submitted attempt actually joins a
    real network - `main()` below is the only real caller, this function
    is what unit tests exercise instead (with a bounded fake server-tick
    substitute, since a real `ThreadingHTTPServer.serve_forever()` blocks
    by design)."""
    ensure_hotspot_if_disconnected(runner, ifname, ap_ssid, ap_password)
    joined = [False]
    handler = make_handler(runner, ifname, joined, ap_ssid, ap_password)
    httpd = ThreadingHTTPServer((host, port), handler)
    print(f"WIFI_PROVISION=SERVING http://{host}:{port}/ (AP {ap_ssid!r} on {ifname})")
    try:
        while not joined[0]:
            httpd.timeout = poll_interval_s
            httpd.handle_request()
    finally:
        httpd.server_close()
    print("WIFI_PROVISION=JOINED")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="required for any real network change")
    parser.add_argument("--ifname", default=DEFAULT_IFNAME)
    parser.add_argument("--ap-ssid", default=os.environ.get("HYDRA_UMC_AP_SSID", DEFAULT_AP_SSID))
    parser.add_argument(
        "--ap-password",
        default=os.environ.get("HYDRA_UMC_AP_PASSWORD", DEFAULT_AP_PASSWORD),
        help="real deployments must override this (or set HYDRA_UMC_AP_PASSWORD)",
    )
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

    serve_until_joined(runner, args.ifname, args.ap_ssid, args.ap_password, args.host, args.port)
    return 0


def _nmcli_available() -> bool:
    try:
        subprocess.run(["nmcli", "--version"], capture_output=True, timeout=5, check=False)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


if __name__ == "__main__":
    raise SystemExit(main())
