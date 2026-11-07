# =============================================================================
# HYDRA-UMC-OS - Device agent local socket tests
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The optional local socket of the agent (diagnostics.local_socket): read only, off by default, closed to other users, and it only
answers `describe` and `health`. The server tests run on a Linux machine (a UNIX socket in a temporary folder)."""
import contextlib
import copy
import io
import json
import os
import socket
import stat
import tempfile
import unittest
from pathlib import Path

from hydra_umc_os.agent import (
    DEFAULT_CONFIG,
    MAX_REQUEST_BYTES,
    LocalSocketServer,
    load_config,
    main,
    query_socket,
    validate_local_socket,
)

HAS_UNIX = hasattr(socket, "AF_UNIX") and os.name == "posix"


def config_with(block):
    config = copy.deepcopy(DEFAULT_CONFIG)
    config["diagnostics"]["minimum_free_bytes"] = 0
    if block is not None:
        config["diagnostics"]["local_socket"] = block
    return config


class ConfigurationTests(unittest.TestCase):
    def test_no_block_means_no_socket(self):
        self.assertIsNone(LocalSocketServer.from_config(config_with(None)))
        self.assertNotIn("local_socket", DEFAULT_CONFIG["diagnostics"])

    def test_a_block_that_is_not_enabled_means_no_socket(self):
        self.assertIsNone(LocalSocketServer.from_config(config_with({"path": "/run/x/a.sock"})))
        self.assertIsNone(LocalSocketServer.from_config(config_with({"enabled": False})))

    def test_only_a_real_true_turns_it_on(self):
        for value in ("true", 1, "yes", None):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_local_socket({"enabled": value})
        validate_local_socket({"enabled": True})
        validate_local_socket(None)

    def test_the_bad_shapes_are_refused(self):
        bad = [
            "x",
            [],
            {"unknown": 1},
            {"path": "relative.sock"},
            {"path": "/run/../etc/x.sock"},
            {"path": "/run/a b.sock"},
            {"path": "/" + "a" * 120},
            {"path": 7},
            {"mode": "0666"},
            {"mode": "0664"},
            {"mode": "660x"},
            {"mode": 660},
            {"cache_seconds": -1},
            {"cache_seconds": 61},
            {"cache_seconds": "2"},
            {"cache_seconds": True},
            {"cache_seconds": float("inf")},
        ]
        for block in bad:
            with self.subTest(block=block):
                with self.assertRaises(ValueError):
                    validate_local_socket(block)

    def test_the_good_shapes_are_accepted(self):
        for block in ({"enabled": True, "path": "/run/hydra-umc-agent/agent.sock", "mode": "0660", "cache_seconds": 0}, {"mode": "600"}, {"mode": "0750", "cache_seconds": 60}):
            validate_local_socket(block)

    def test_load_config_checks_the_block(self):
        with tempfile.TemporaryDirectory() as folder:
            good = Path(folder) / "good.json"
            good.write_text(json.dumps(config_with({"enabled": True, "mode": "0660"})), encoding="utf-8")
            self.assertTrue(load_config(good)["diagnostics"]["local_socket"]["enabled"])
            bad = Path(folder) / "bad.json"
            bad.write_text(json.dumps(config_with({"enabled": True, "mode": "0666"})), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_config(bad)


class AnswerTests(unittest.TestCase):
    """The answers without any socket: they are the same lines a client reads."""

    def setUp(self):
        self.now = 100.0
        self.server = LocalSocketServer(config_with(None), path="/unused", cache_seconds=2.0, clock=lambda: self.now)

    def test_describe_and_health_are_one_line_of_json(self):
        for command, key in ((b"describe", "node_id"), (b"health", "state")):
            line = self.server.answer(command)
            self.assertTrue(line.endswith("\n"))
            self.assertEqual(line.count("\n"), 1)
            self.assertIn(key, json.loads(line))

    def test_anything_else_is_an_error_line(self):
        for request in (b"", b"reboot", b"HEALTH", b"health extra", b"describe;id", b"\xff\xfe"):
            with self.subTest(request=request):
                answer = json.loads(self.server.answer(request))
                self.assertEqual(answer["error"], "unknown command")
                self.assertEqual(answer["commands"], ["describe", "health"])

    def test_surrounding_blanks_are_ignored(self):
        self.assertIn("state", json.loads(self.server.answer(b"  health \r")))

    def counted(self, server, times):
        import hydra_umc_os.agent as agent

        calls = []
        original = agent.health

        def counting(config, **kwargs):
            calls.append(1)
            return original(config, **kwargs)

        agent.health = counting
        try:
            times()
        finally:
            agent.health = original
        return len(calls)

    def test_a_report_is_reused_for_the_cache_time_only(self):
        def times():
            self.server.answer(b"health")
            self.now += 1.9
            self.server.answer(b"health")
            self.now += 0.2
            self.server.answer(b"health")

        self.assertEqual(self.counted(self.server, times), 2)

    def test_describe_is_never_taken_from_the_cache_of_health(self):
        self.server.answer(b"health")
        self.assertIn("node_id", json.loads(self.server.answer(b"describe")))

    def test_no_cache_when_the_time_is_zero(self):
        server = LocalSocketServer(config_with(None), path="/unused", cache_seconds=0, clock=lambda: self.now)

        def times():
            server.answer(b"health")
            server.answer(b"health")

        self.assertEqual(self.counted(server, times), 2)


@unittest.skipUnless(HAS_UNIX, "needs UNIX sockets (Linux)")
class SocketTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = os.path.join(self.folder.name, "agent.sock")

    def started(self, **kwargs):
        server = LocalSocketServer(config_with(None), path=kwargs.pop("path", self.path), **kwargs)
        server.start()
        self.addCleanup(server.close)
        return server

    def test_a_client_gets_a_report(self):
        self.started()
        report = query_socket(self.path, "health")
        self.assertIn(report["state"], ("READY", "DEGRADED", "FAULT"))
        self.assertIn("storage", report["checks"])
        self.assertEqual(query_socket(self.path, "describe")["schema_version"], "1.0")

    def test_the_socket_file_is_closed_to_other_users(self):
        self.started(mode="0660")
        mode = stat.S_IMODE(os.stat(self.path).st_mode)
        self.assertEqual(mode, 0o660)
        self.assertEqual(mode & 0o007, 0)

    def test_a_stricter_mode_is_applied(self):
        self.started(mode="0600")
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o600)

    def test_closing_removes_the_file(self):
        server = self.started()
        self.assertTrue(os.path.exists(self.path))
        server.close()
        self.assertFalse(os.path.exists(self.path))
        server.close()  # twice is harmless

    def test_an_unknown_command_is_an_error_not_a_report(self):
        self.started()
        with self.assertRaises(ValueError):
            query_socket(self.path, "reboot")

    def test_a_long_request_is_dropped_and_the_agent_keeps_answering(self):
        self.started()
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(3)
        client.connect(self.path)
        client.sendall(b"x" * (MAX_REQUEST_BYTES * 4))
        self.assertEqual(client.recv(1000), b"")
        client.close()
        self.assertIn("state", query_socket(self.path, "health"))

    def test_a_client_that_hangs_up_does_not_stop_it(self):
        self.started()
        for _ in range(5):
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.connect(self.path)
            client.close()
        self.assertIn("state", query_socket(self.path, "health"))

    def test_a_request_in_pieces_is_put_together(self):
        self.started()
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(3)
        client.connect(self.path)
        client.sendall(b"hea")
        client.sendall(b"lth\n")
        data = b""
        while not data.endswith(b"\n"):
            data += client.recv(65536)
        client.close()
        self.assertIn("state", json.loads(data))

    def test_a_leftover_socket_of_a_dead_agent_is_replaced(self):
        dead = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        dead.bind(self.path)
        dead.close()
        self.assertTrue(os.path.exists(self.path))
        self.started()
        self.assertIn("state", query_socket(self.path, "health"))

    def test_a_live_agent_is_not_replaced(self):
        self.started()
        other = LocalSocketServer(config_with(None), path=self.path)
        with self.assertRaises(ValueError):
            other.start()
        self.assertIn("state", query_socket(self.path, "health"))

    def test_a_file_that_is_not_a_socket_is_never_touched(self):
        Path(self.path).write_text("precious", encoding="utf-8")
        other = LocalSocketServer(config_with(None), path=self.path)
        with self.assertRaises(ValueError):
            other.start()
        self.assertEqual(Path(self.path).read_text(encoding="utf-8"), "precious")

    def test_a_missing_folder_is_an_error(self):
        other = LocalSocketServer(config_with(None), path=os.path.join(self.folder.name, "no-such", "agent.sock"))
        with self.assertRaises(ValueError):
            other.start()

    def test_the_umask_of_the_process_is_given_back(self):
        before = os.umask(0o022)
        try:
            self.started()
            self.assertEqual(os.umask(0o022), 0o022)
        finally:
            os.umask(before)

    def test_the_query_command_prints_the_report(self):
        self.started()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(["--socket", self.path, "--what", "describe", "query"])
        self.assertEqual(code, 0)
        self.assertIn("node_id", json.loads(out.getvalue()))

    def test_the_query_command_needs_a_socket_and_reports_a_dead_one(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(main(["query"]), 2)
            self.assertEqual(main(["--socket", os.path.join(self.folder.name, "none.sock"), "query"]), 2)
        self.assertIn("hydra-umc-agent:", err.getvalue())


if __name__ == "__main__":
    unittest.main()
