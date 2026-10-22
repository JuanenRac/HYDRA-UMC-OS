#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - Certificate authority script verification
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Prove provisioning/hydra_mqtt_tls.sh with real OpenSSL and real TLS handshakes: the certificates it makes are accepted by a server that demands a client certificate, and a
certificate from another authority, no certificate or a wrong host name is refused. Skipped (and said so) when bash or openssl is missing."""

from __future__ import annotations

import hashlib
import os
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "provisioning" / "hydra_mqtt_tls.sh"
BASH = shutil.which("bash")
OPENSSL = shutil.which("openssl")


def environment(directory: Path) -> dict[str, str]:
    env = dict(os.environ, HYDRA_TLS_DIR=str(directory))
    if env.get("OPENSSL_CONF") and not Path(env["OPENSSL_CONF"]).is_file():
        env.pop("OPENSSL_CONF")
    return env


def run(directory: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    script = SCRIPT.as_posix()
    return subprocess.run([BASH, script, *arguments], env=environment(directory), capture_output=True, text=True, check=False)


def serve_once(server_context: ssl.SSLContext) -> tuple[socket.socket, list[object], threading.Thread]:
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    outcome: list[object] = []

    def accept() -> None:
        connection, _address = listener.accept()
        try:
            with server_context.wrap_socket(connection, server_side=True) as tls:
                outcome.append(tls.getpeercert())
                tls.sendall(b"ok")
        except (ssl.SSLError, OSError) as error:
            outcome.append(error)

    thread = threading.Thread(target=accept, daemon=True)
    thread.start()
    return listener, outcome, thread


@unittest.skipUnless(BASH and OPENSSL, "bash and openssl are needed")
class TlsScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls.tmp.name) / "tls"
        result = run(cls.dir, "init", "--name", "hydra-umc", "--ip", "192.168.0.180")
        assert result.returncode == 0, result.stderr
        result = run(cls.dir, "client", "bridge-cnc")
        assert result.returncode == 0, result.stderr

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def handshake(self, client_context: ssl.SSLContext, hostname: str = "localhost") -> tuple[object, object]:
        server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_context.load_cert_chain(self.dir / "server.pem", self.dir / "server.key")
        server_context.load_verify_locations(self.dir / "ca.pem")
        server_context.verify_mode = ssl.CERT_REQUIRED
        listener, outcome, thread = serve_once(server_context)
        reply: object = None
        try:
            with socket.create_connection(listener.getsockname(), timeout=5) as raw:
                with client_context.wrap_socket(raw, server_hostname=hostname) as tls:
                    reply = tls.recv(2)
        except (ssl.SSLError, OSError) as error:
            reply = error
        finally:
            thread.join(5)
            listener.close()
        return reply, outcome[0] if outcome else None

    def client_context(self, certificate: str | None, key: str | None, authority: Path | None = None) -> ssl.SSLContext:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(authority or self.dir / "ca.pem")
        if certificate:
            context.load_cert_chain(self.dir / certificate, self.dir / key)  # type: ignore[arg-type]
        return context

    def test_a_bridge_certificate_is_accepted_by_a_server_that_demands_one(self) -> None:
        reply, peer = self.handshake(self.client_context("client-bridge-cnc.pem", "client-bridge-cnc.key"))
        self.assertEqual(reply, b"ok")
        subject = dict(item[0] for item in peer["subject"])  # type: ignore[index]
        self.assertEqual(subject["commonName"], "bridge-cnc")

    def test_no_client_certificate_is_refused(self) -> None:
        reply, peer = self.handshake(self.client_context(None, None))
        self.assertIsInstance(peer, ssl.SSLError)
        self.assertNotEqual(reply, b"ok")

    def test_a_certificate_from_another_authority_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as other:
            other_dir = Path(other) / "tls"
            self.assertEqual(run(other_dir, "init").returncode, 0)
            self.assertEqual(run(other_dir, "client", "bridge-cnc").returncode, 0)
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.load_verify_locations(self.dir / "ca.pem")
            context.load_cert_chain(other_dir / "client-bridge-cnc.pem", other_dir / "client-bridge-cnc.key")
            reply, peer = self.handshake(context)
            self.assertIsInstance(peer, ssl.SSLError)
            self.assertNotEqual(reply, b"ok")

    def test_a_server_that_is_not_ours_is_refused_by_the_client(self) -> None:
        with tempfile.TemporaryDirectory() as other:
            other_dir = Path(other) / "tls"
            self.assertEqual(run(other_dir, "init").returncode, 0)
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.load_verify_locations(other_dir / "ca.pem")  # trusts only a different authority
            context.load_cert_chain(self.dir / "client-bridge-cnc.pem", self.dir / "client-bridge-cnc.key")
            reply, _peer = self.handshake(context)
            self.assertIsInstance(reply, ssl.SSLError)

    def test_the_certificate_vouches_for_the_names_and_not_for_others(self) -> None:
        context = self.client_context("client-bridge-cnc.pem", "client-bridge-cnc.key")
        reply, _peer = self.handshake(context, hostname="hydra-umc")
        self.assertEqual(reply, b"ok")
        reply, _peer = self.handshake(context, hostname="evil.example")
        self.assertIsInstance(reply, ssl.SSLError)
        sans = subprocess.run(["openssl", "x509", "-in", str(self.dir / "server.pem"), "-noout", "-ext", "subjectAltName"], env=environment(self.dir), capture_output=True, text=True, check=True).stdout
        for expected in ("DNS:localhost", "IP Address:127.0.0.1", "DNS:hydra-umc", "IP Address:192.168.0.180"):
            self.assertIn(expected, sans)

    def test_the_certificate_of_a_bridge_cannot_act_as_a_server(self) -> None:
        text = subprocess.run(["openssl", "x509", "-in", str(self.dir / "client-bridge-cnc.pem"), "-noout", "-ext", "extendedKeyUsage,basicConstraints"], env=environment(self.dir), capture_output=True, text=True, check=True).stdout
        self.assertIn("TLS Web Client Authentication", text)
        self.assertNotIn("TLS Web Server Authentication", text)
        self.assertIn("CA:FALSE", text)

    def test_init_keeps_the_authority_and_renew_changes_only_the_broker_certificate(self) -> None:
        digest = lambda name: hashlib.sha256((self.dir / name).read_bytes()).hexdigest()  # noqa: E731
        before = {name: digest(name) for name in ("ca.pem", "ca.key", "server.pem", "client-bridge-cnc.pem")}
        again = run(self.dir, "init")
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual({name: digest(name) for name in before}, before)
        renewed = run(self.dir, "renew", "--name", "hydra-umc", "--ip", "192.168.0.180")
        self.assertEqual(renewed.returncode, 0, renewed.stderr)
        self.assertEqual(digest("ca.pem"), before["ca.pem"])
        self.assertEqual(digest("client-bridge-cnc.pem"), before["client-bridge-cnc.pem"])
        self.assertNotEqual(digest("server.pem"), before["server.pem"])
        self.assertEqual(run(self.dir, "verify").returncode, 0)

    def test_verify_fails_for_a_certificate_the_authority_did_not_sign(self) -> None:
        with tempfile.TemporaryDirectory() as work:
            copy = Path(work) / "tls"
            shutil.copytree(self.dir, copy)
            with tempfile.TemporaryDirectory() as other:
                other_dir = Path(other) / "tls"
                self.assertEqual(run(other_dir, "init").returncode, 0)
                shutil.copy(other_dir / "server.pem", copy / "server.pem")
            result = run(copy, "verify")
            self.assertEqual(result.returncode, 1)
            self.assertIn("server.pem: NOT signed by this authority", result.stderr)

    def test_the_env_lines_name_the_files_and_demand_a_client_certificate(self) -> None:
        result = run(self.dir, "env", "--client", "bridge-cnc")
        self.assertEqual(result.returncode, 0, result.stderr)
        for expected in ("MQTT_TLS_REQUIRE_CLIENT_CERT=1", "MQTT_TLS_CERT=", "HYDRA_MQTT_TLS_CERT=/etc/hydra-umc/tls/client-bridge-cnc.pem"):
            self.assertIn(expected, result.stdout)
        self.assertNotIn("ca.key", result.stdout)
        self.assertEqual(run(self.dir, "env", "--client", "nobody").returncode, 2)

    def test_the_key_of_the_authority_never_leaves_the_directory(self) -> None:
        exported = run(self.dir, "export-ca")
        self.assertIn("BEGIN CERTIFICATE", exported.stdout)
        self.assertNotIn("PRIVATE KEY", exported.stdout + exported.stderr)
        if os.name != "nt":
            self.assertEqual(oct((self.dir / "ca.key").stat().st_mode & 0o777), "0o600")
            self.assertEqual(oct(self.dir.stat().st_mode & 0o777), "0o700")
            self.assertEqual(oct((self.dir / "server.key").stat().st_mode & 0o777), "0o600")

    def test_plan_changes_nothing_and_bad_input_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as work:
            empty = Path(work) / "tls"
            plan = run(empty, "plan", "--name", "hydra-umc")
            self.assertEqual(plan.returncode, 0, plan.stderr)
            self.assertFalse(empty.exists())
        for arguments in (("init", "--name", "bad name"), ("init", "--ip", "999.1.1.1"), ("init", "--name", "x; rm -rf /"), ("client", "../escape"), ("client", ""), ("frobnicate",), ("init", "--unknown"), ()):
            with self.subTest(arguments=arguments):
                with tempfile.TemporaryDirectory() as work:
                    self.assertEqual(run(Path(work) / "tls", *arguments).returncode, 2)

    def test_client_certificates_need_an_authority_and_are_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as work:
            empty = Path(work) / "tls"
            empty.mkdir()
            self.assertEqual(run(empty, "client", "bridge-x").returncode, 2)
        again = run(self.dir, "client", "bridge-cnc")
        self.assertEqual(again.returncode, 2)
        self.assertIn("already exists", again.stderr)


def main() -> int:
    if not (BASH and OPENSSL):
        print("MQTT_TLS_VERIFY=SKIPPED bash or openssl is not available on this host")
        return 0
    result = unittest.main(module=__name__, exit=False, verbosity=1).result
    if result.wasSuccessful():
        print(f"MQTT_TLS_VERIFY=PASS tests={result.testsRun}")
        return 0
    print("MQTT_TLS_VERIFY=FAIL", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
