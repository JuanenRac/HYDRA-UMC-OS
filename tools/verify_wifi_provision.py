#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - WiFi provisioning state-machine verification
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Proves provisioning/wifi_provision.py's real state machine
(ensure_hotspot_if_disconnected/attempt_join) without a real WiFi radio,
root, or NetworkManager - a FakeNetworkManager standing in for
RealNetworkManager (the module's own real nmcli-shelling implementation)
implements the exact same NetworkManagerRunner Protocol, so this proves
the actual logic real callers run, not a reimplementation of it. Same
"real logic against an injected fake" verification boundary this
ecosystem already applies to every real hardware transport (spidev,
gpiod, mavlink, bosdyn-client, ...).
"""
from __future__ import annotations

import importlib.util
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = ROOT / "provisioning" / "wifi_provision.py"


def _import_wifi_provision():
    spec = importlib.util.spec_from_file_location("hydra_umc_os_wifi_provision", MODULE_PATH)
    if spec is None or spec.loader is None:
        print("WIFI_PROVISION_VERIFY=FAIL cannot load provisioning/wifi_provision.py", file=sys.stderr)
        raise SystemExit(1)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


wp = _import_wifi_provision()

failures = 0


def check(label: str, actual: object, expected: object) -> None:
    global failures
    if actual != expected:
        print(f"FAIL {label}: expected {expected!r}, got {actual!r}")
        failures += 1
    else:
        print(f"ok   {label}")


class FakeNetworkManager:
    """In-memory stand-in for RealNetworkManager - real per-call
    behavior (raises wp.NmcliError on a simulated failure, same as a real
    nmcli non-zero exit would), no subprocess/nmcli/root involved."""

    def __init__(self, known_good_password: str = "correct-horse") -> None:
        self._connected_ssid: str | None = None
        self._hotspot_active = False
        self._known_good_password = known_good_password
        self.calls: list[tuple[str, ...]] = []

    def active_wifi_connection(self, ifname: str) -> str | None:
        self.calls.append(("active_wifi_connection", ifname))
        return self._connected_ssid

    def start_hotspot(self, ifname: str, ssid: str, password: str) -> None:
        self.calls.append(("start_hotspot", ifname, ssid, password))
        self._hotspot_active = True

    def stop_hotspot(self, ifname: str) -> None:
        self.calls.append(("stop_hotspot", ifname))
        self._hotspot_active = False

    def connect(self, ifname: str, ssid: str, password: str) -> None:
        self.calls.append(("connect", ifname, ssid, password))
        if password != self._known_good_password:
            raise wp.NmcliError("Error: Secrets were required, but not provided.")
        self._connected_ssid = ssid

    def scan(self, ifname: str) -> list[str]:
        self.calls.append(("scan", ifname))
        return ["HomeNetwork", "Neighbor5G"]


# --- ensure_hotspot_if_disconnected ---------------------------------------

already_connected = FakeNetworkManager()
already_connected._connected_ssid = "HomeNetwork"
started = wp.ensure_hotspot_if_disconnected(already_connected, "wlan0", "HYDRA-UMC-SETUP", "setup-pass")
check("already-connected: no hotspot started", started, False)
check("already-connected: start_hotspot never called", any(c[0] == "start_hotspot" for c in already_connected.calls), False)

disconnected = FakeNetworkManager()
started = wp.ensure_hotspot_if_disconnected(disconnected, "wlan0", "HYDRA-UMC-SETUP", "setup-pass")
check("disconnected: hotspot started", started, True)
check(
    "disconnected: start_hotspot called with the real ssid/password",
    disconnected.calls[-1],
    ("start_hotspot", "wlan0", "HYDRA-UMC-SETUP", "setup-pass"),
)

# --- attempt_join: success path -------------------------------------------

fnm = FakeNetworkManager(known_good_password="s3cr3t")
result = wp.attempt_join(fnm, "wlan0", "HomeNetwork", "s3cr3t")
check("join success: JoinResult.ok", result.ok, True)
check("join success: reason is empty", result.reason, "")
check("join success: interface now reports the real connection", fnm.active_wifi_connection("wlan0"), "HomeNetwork")
check("join success: hotspot was torn down first", fnm.calls[0], ("stop_hotspot", "wlan0"))
check("join success: hotspot NOT restarted afterward", fnm._hotspot_active, False)

# --- attempt_join: wrong password -------------------------------------

fnm = FakeNetworkManager(known_good_password="s3cr3t")
fnm._hotspot_active = True
result = wp.attempt_join(fnm, "wlan0", "HomeNetwork", "wrong-password")
check("join failure (wrong password): JoinResult.ok is False", result.ok, False)
check("join failure: reason carries the real nmcli error text", "Secrets were required" in result.reason, True)
check("join failure: hotspot restarted so the operator isn't stranded", fnm._hotspot_active, True)
check("join failure: interface never shows a connection", fnm.active_wifi_connection("wlan0"), None)

# --- attempt_join: nmcli reports success but the interface never shows connected ---

class _LyingNetworkManager(FakeNetworkManager):
    """connect() succeeds per nmcli's own exit code, but the interface
    itself never actually reports the connection as active - a real,
    if rare, nmcli/driver inconsistency this module must not trust
    blindly."""

    def connect(self, ifname: str, ssid: str, password: str) -> None:
        self.calls.append(("connect", ifname, ssid, password))
        # Deliberately does NOT set self._connected_ssid.


lying = _LyingNetworkManager()
result = wp.attempt_join(lying, "wlan0", "HomeNetwork", "anything")
check("join failure (interface never confirms): JoinResult.ok is False", result.ok, False)
check("join failure (interface never confirms): hotspot restarted", lying._hotspot_active, True)

# --- attempt_join: a failed join must restart the hotspot with THIS
# deployment's real AP credentials, never the module's own
# DEFAULT_AP_PASSWORD placeholder - a real bug found and fixed while
# building this (ap_ssid/ap_password used to not be threaded through at
# all, so a custom-configured deployment would have silently fallen back
# to the shared default password after any failed join attempt). -------

fnm = FakeNetworkManager(known_good_password="s3cr3t")
wp.attempt_join(fnm, "wlan0", "HomeNetwork", "wrong-password", ap_ssid="CustomSetupSSID", ap_password="custom-ap-pass")
restart_call = next(c for c in fnm.calls if c[0] == "start_hotspot")
check("failed-join hotspot restart reuses the real deployment ap_ssid", restart_call[2], "CustomSetupSSID")
check("failed-join hotspot restart reuses the real deployment ap_password, not the module default", restart_call[3], "custom-ap-pass")

# --- serve_until_joined(): the real HTTP handler, over a real (loopback)
# socket - a FakeNetworkManager stands in for nmcli, but the HTTP
# request/response path itself (do_GET '/', do_GET '/networks',
# do_POST '/wifi', ThreadingHTTPServer.handle_request()'s own real
# join-then-exit loop) is exercised for real, not reimplemented. -------

server_fake = FakeNetworkManager(known_good_password="setup-secret")
server_thread = threading.Thread(
    target=wp.serve_until_joined,
    args=(server_fake, "wlan0", "HYDRA-UMC-SETUP", "setup-pass"),
    kwargs={"host": "127.0.0.1", "port": 18765, "poll_interval_s": 0.2},
    daemon=True,
)
server_thread.start()

try:
    root_resp = urllib.request.urlopen("http://127.0.0.1:18765/", timeout=5)
    check("HTTP GET / returns 200 with the real setup form", root_resp.status, 200)
    check("HTTP GET / body contains the real SSID field", b'name="ssid"' in root_resp.read(), True)

    networks_resp = urllib.request.urlopen("http://127.0.0.1:18765/networks", timeout=5)
    import json as _json

    networks_body = _json.loads(networks_resp.read())
    check("HTTP GET /networks returns the real fake scan result", networks_body, {"ssids": ["HomeNetwork", "Neighbor5G"]})

    # A wrong-password attempt must NOT stop the serving loop - the
    # operator is still expected to retry against the same running server.
    bad_body = "ssid=HomeNetwork&password=wrong".encode("ascii")
    bad_req = urllib.request.Request("http://127.0.0.1:18765/wifi", data=bad_body, method="POST")
    bad_resp = urllib.request.urlopen(bad_req, timeout=5)
    check("HTTP POST /wifi with a wrong password still responds 200 (form re-shown)", bad_resp.status, 200)
    check("serve_until_joined loop still running after a failed attempt", server_thread.is_alive(), True)

    good_body = "ssid=HomeNetwork&password=setup-secret".encode("ascii")
    good_req = urllib.request.Request("http://127.0.0.1:18765/wifi", data=good_body, method="POST")
    good_resp = urllib.request.urlopen(good_req, timeout=5)
    check("HTTP POST /wifi with the real correct password responds 200", good_resp.status, 200)

    server_thread.join(timeout=5)
    check("serve_until_joined returns once a real join succeeds", server_thread.is_alive(), False)
    check("the fake NetworkManager itself shows the real joined network", server_fake.active_wifi_connection("wlan0"), "HomeNetwork")
except (urllib.error.URLError, OSError) as exc:
    print(f"FAIL HTTP round-trip against the real local server: {exc}")
    failures += 1

# --- the credentials of THIS device (no password in the source, a one-time code in the form) ---------------------------

import json as _json2
import tempfile

check("the publicly known default AP password is refused", wp.ap_password_problem(wp.DEFAULT_AP_PASSWORD) is not None, True)
check("a short AP password is refused", wp.ap_password_problem("short") is not None, True)
check("a long AP password is acceptable", wp.ap_password_problem("a-long-enough-pass"), None)

with tempfile.TemporaryDirectory() as _state:
    _first = wp.resolve_ap_credentials(Path(_state))
    check("a device without a password generates its own (16 characters)", len(_first[0]), 16)
    check("...and an 8-digit setup code", (len(_first[1]), _first[1].isdigit()), (8, True))
    check("...and says it generated them", _first[2], True)
    _again = wp.resolve_ap_credentials(Path(_state))
    check("a restart keeps the same password and code", (_again[0], _again[1], _again[2]), (_first[0], _first[1], False))
    check("the credentials file holds them", _json2.loads((Path(_state) / "credentials.json").read_text(encoding="utf-8")), {"password": _first[0], "code": _first[1]})
    _refused = wp.resolve_ap_credentials(Path(_state) / "other", wp.DEFAULT_AP_PASSWORD)
    check("the old default is never used, even when it is asked for", _refused[0] != wp.DEFAULT_AP_PASSWORD, True)
    _explicit = wp.resolve_ap_credentials(Path(_state) / "explicit", "an-explicit-password")
    check("an acceptable explicit password is used as given", _explicit[0], "an-explicit-password")

# --- the setup form with a one-time code, a body limit and a window ---------------------------------------------

coded_fake = FakeNetworkManager(known_good_password="setup-secret")
coded_thread = threading.Thread(
    target=wp.serve_until_joined,
    args=(coded_fake, "wlan0", "HYDRA-UMC-SETUP", "setup-pass"),
    kwargs={"host": "127.0.0.1", "port": 18766, "poll_interval_s": 0.2, "setup_code": "12345678"},
    daemon=True,
)
coded_thread.start()


def _post(url: str, body: bytes):
    try:
        return urllib.request.urlopen(urllib.request.Request(url, data=body, method="POST"), timeout=5).status
    except urllib.error.HTTPError as error:
        return error.code


try:
    check("the form asks for the setup code", b'name="code"' in urllib.request.urlopen("http://127.0.0.1:18766/", timeout=5).read(), True)
    check("a wrong code is refused (403)", _post("http://127.0.0.1:18766/wifi", b"ssid=HomeNetwork&password=setup-secret&code=00000000"), 403)
    check("a missing code is refused (403)", _post("http://127.0.0.1:18766/wifi", b"ssid=HomeNetwork&password=setup-secret"), 403)
    check("nothing was joined with a wrong code", coded_fake.active_wifi_connection("wlan0"), None)
    check("a body over the limit is refused (413)", _post("http://127.0.0.1:18766/wifi", b"ssid=" + b"a" * (wp.MAX_BODY_BYTES + 10)), 413)
    check("the right code joins", _post("http://127.0.0.1:18766/wifi", b"ssid=HomeNetwork&password=setup-secret&code=12345678"), 200)
    coded_thread.join(timeout=5)
    check("the loop ends after the join", coded_thread.is_alive(), False)
except (urllib.error.URLError, OSError) as exc:
    print(f"FAIL HTTP round-trip against the coded server: {exc}")
    failures += 1

lockout_fake = FakeNetworkManager()
lockout_thread = threading.Thread(
    target=wp.serve_until_joined,
    args=(lockout_fake, "wlan0", "HYDRA-UMC-SETUP", "setup-pass"),
    kwargs={"host": "127.0.0.1", "port": 18767, "poll_interval_s": 0.2, "setup_code": "12345678", "window_s": 3},
    daemon=True,
)
lockout_thread.start()
try:
    statuses = [_post("http://127.0.0.1:18767/wifi", b"ssid=HomeNetwork&password=x&code=11111111") for _ in range(wp.MAX_CODE_FAILURES)]
    check("five wrong codes in a row are refused", statuses, [403] * wp.MAX_CODE_FAILURES)
    check("the sixth try is locked out (429), even with the right code", _post("http://127.0.0.1:18767/wifi", b"ssid=HomeNetwork&password=x&code=12345678"), 429)
except (urllib.error.URLError, OSError) as exc:
    print(f"FAIL HTTP round-trip against the lockout server: {exc}")
    failures += 1
lockout_thread.join(timeout=10)
check("nobody set the device up within the window: the loop ends", lockout_thread.is_alive(), False)
check("...and the setup network is switched off", lockout_fake._hotspot_active, False)

print()
if failures:
    print(f"WIFI_PROVISION_VERIFY=FAIL {failures} mismatches")
    sys.exit(1)
print("WIFI_PROVISION_VERIFY=PASS checks=46")
