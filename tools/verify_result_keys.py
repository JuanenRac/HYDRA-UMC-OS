#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - Verification of the keys the installers hand out to the services
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Two services sign what they answer, and the installer is the one who gives them the key:

* the Voice UI signs the result of a confirmation and HYDRA-UMC-SERVER checks it (`HYDRA_UMC_VOICE_UI_RESULT_KEY`, the same value in `/etc/hydra-umc/voice-ui.env` and
  `/etc/hydra-umc/server.env`, generated when the device is installed);
* the local technician signs the result of every tool (`HYDRA_UMC_LOCAL_TECHNICIAN_RESULT_KEY_FILE`, a root-only file made when the device is installed).

This checks, without root and without installing anything: that one run of the two installers' calls gives both files the same fresh key whichever runs first and whichever
file is older; that a key or a setting the operator already chose is never replaced; that the key file of the technician is created 0600, kept on a second run and never
followed through a symbolic link; that no key is written into the repository; and that the names the installers write are the ones the services read."""
from __future__ import annotations

import importlib.util
import os
import re
import stat
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROVISIONING = ROOT / "provisioning"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


gs = load("hydra_umc_os_generate_secrets_for_keys", PROVISIONING / "generate_secrets.py")
mk = load("hydra_umc_os_make_result_key", PROVISIONING / "make_result_key.py")

KEY = "HYDRA_UMC_VOICE_UI_RESULT_KEY"
REQUIRE = "HYDRA_UMC_VOICE_CONFIRM_REQUIRE_SIGNATURE"
SUBJECT = "HYDRA_UMC_VOICE_UI_REQUIRE_SUBJECT"
VOICE_TEMPLATE_OLD = "HYDRA_UMC_VOICE_UI_TOKEN=SET_LOCALLY_TO_A_LONG_RANDOM_VALUE\nHYDRA_UMC_VOICE_UI_CONFIRM_SECRET=SET_LOCALLY_TO_A_LONG_RANDOM_VALUE\n"


def values(path: Path) -> dict[str, str]:
    return {key: value for _, key, value in gs.parse(path.read_text(encoding="utf-8"))}


def server_call(server: Path, voice: Path) -> list[str]:
    """The arguments install_server.sh gives generate_secrets.py (kept in step with the script by a test below)."""
    return [
        str(server), "--create-from", str(PROVISIONING / "server.env.example"), "--apply",
        "--adopt", f"HYDRA_UMC_VOICE_UI_TOKEN={voice}:HYDRA_UMC_VOICE_UI_TOKEN",
        "--mirror", f"HYDRA_UMC_VOICE_UI_TOKEN={voice}:HYDRA_UMC_VOICE_UI_TOKEN",
        "--ensure", KEY, "--adopt", f"{KEY}={voice}:{KEY}", "--mirror", f"{KEY}={voice}:{KEY}",
        "--ensure", f"{REQUIRE}=1",
    ]


def voice_call(voice: Path, server: Path, template: Path) -> list[str]:
    return [
        str(voice), "--create-from", str(template), "--apply",
        "--adopt", f"HYDRA_UMC_VOICE_UI_TOKEN={server}:HYDRA_UMC_VOICE_UI_TOKEN",
        "--ensure", KEY, "--adopt", f"{KEY}={server}:{KEY}", "--ensure", f"{SUBJECT}=1",
    ]


class VoiceKeyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.server, self.voice = self.base / "server.env", self.base / "voice-ui.env"
        self.template = self.base / "voice-ui.env.example"
        self.template.write_text(VOICE_TEMPLATE_OLD, encoding="utf-8")  # the Voice UI template that does not know the key yet

    def run_main(self, args: list[str]) -> None:
        self.assertEqual(gs.main(args), 0)

    def test_the_server_installer_first_gives_both_files_the_same_new_key(self) -> None:
        self.voice.write_text(VOICE_TEMPLATE_OLD, encoding="utf-8")  # an older install: no key line yet
        self.run_main(server_call(self.server, self.voice))
        server, voice = values(self.server), values(self.voice)
        self.assertEqual(len(server[KEY]), 64)
        self.assertEqual(server[KEY], voice[KEY], "the key was added to the older voice file and mirrored")
        self.assertEqual(server[REQUIRE], "1")
        self.assertEqual(gs.main([str(self.server), "--check"]), 0)

    def test_the_voice_installer_first_and_the_server_after_end_up_with_one_key(self) -> None:
        self.run_main(voice_call(self.voice, self.server, self.template))
        first = values(self.voice)[KEY]
        self.assertEqual(len(first), 64)
        self.assertEqual(values(self.voice)[SUBJECT], "1")
        self.run_main(server_call(self.server, self.voice))
        self.assertEqual(values(self.server)[KEY], first, "the server adopts the key the voice installer already made")
        self.assertEqual(values(self.voice)[KEY], first)

    def test_a_second_run_of_either_installer_changes_nothing(self) -> None:
        self.run_main(voice_call(self.voice, self.server, self.template))
        self.run_main(server_call(self.server, self.voice))
        before = (self.server.read_text(encoding="utf-8"), self.voice.read_text(encoding="utf-8"))
        self.run_main(voice_call(self.voice, self.server, self.template))
        self.run_main(server_call(self.server, self.voice))
        self.assertEqual((self.server.read_text(encoding="utf-8"), self.voice.read_text(encoding="utf-8")), before)

    def test_a_key_and_a_setting_the_operator_chose_are_never_replaced(self) -> None:
        own = "ab" * 32
        self.voice.write_text(VOICE_TEMPLATE_OLD + f"{KEY}={own}\n{SUBJECT}=0\n", encoding="utf-8")
        self.run_main(server_call(self.server, self.voice))
        self.assertEqual(values(self.voice)[KEY], own)
        self.assertEqual(values(self.server)[KEY], own, "the server adopted the operator's key")
        self.assertEqual(values(self.voice)[SUBJECT], "0", "a line that is there is not touched")
        self.server.write_text(self.server.read_text(encoding="utf-8").replace(f"{REQUIRE}=1", f"{REQUIRE}=0"), encoding="utf-8")
        self.run_main(server_call(self.server, self.voice))
        self.assertEqual(values(self.server)[REQUIRE], "0")

    def test_the_keys_are_private_and_the_files_do_not_hold_a_placeholder(self) -> None:
        self.run_main(voice_call(self.voice, self.server, self.template))
        self.run_main(server_call(self.server, self.voice))
        if os.name != "nt":
            for path in (self.server, self.voice):
                self.assertEqual(stat.S_IMODE(os.stat(path).st_mode) & 0o077, 0, path)
        self.assertEqual(gs.problems(self.voice.read_text(encoding="utf-8")), [])
        self.assertEqual(gs.problems(self.server.read_text(encoding="utf-8")), [])

    def test_two_devices_never_get_the_same_key(self) -> None:
        keys = set()
        for number in range(3):
            voice, server = self.base / f"v{number}.env", self.base / f"s{number}.env"
            self.run_main(voice_call(voice, server, self.template))
            keys.add(values(voice)[KEY])
        self.assertEqual(len(keys), 3)

    def test_a_short_key_is_refused_by_the_check(self) -> None:
        self.assertEqual(gs.problems(f"{KEY}=short\n"), [f"{KEY} has fewer than 32 characters"])
        self.assertEqual(gs.problems(f"{KEY}=" + "a" * 32 + "\n"), [])
        self.assertTrue(gs.problems(f"{KEY}=SET_LOCALLY_TO_THE_SAME_LONG_RANDOM_VALUE\n"))

    def test_ensure_adds_only_what_is_missing_and_only_a_variable_name(self) -> None:
        text, added = gs.ensure_lines("A=1\n", ["B", "C=2", "A=9", "not a name=3", "B=7"])
        self.assertEqual(added, ["B", "C"])
        self.assertEqual({k: v for _, k, v in gs.parse(text)}, {"A": "1", "B": gs.ENSURE_PLACEHOLDER, "C": "2"})
        self.assertEqual(gs.ensure_lines("", ["X=1"])[0], "\nX=1\n".lstrip("\n"))


class TechnicianKeyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "etc" / "result.key"

    def test_the_key_file_is_created_private_with_a_random_key(self) -> None:
        self.assertEqual(mk.make(self.path), "created")
        text = self.path.read_text(encoding="utf-8")
        self.assertRegex(text, r"^[0-9a-f]{64}\n$")
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o600)

    def test_a_key_that_exists_is_kept_and_a_second_device_gets_another(self) -> None:
        mk.make(self.path)
        first = self.path.read_text(encoding="utf-8")
        self.assertEqual(mk.make(self.path), "kept")
        self.assertEqual(self.path.read_text(encoding="utf-8"), first)
        other = self.path.with_name("other.key")
        mk.make(other)
        self.assertNotEqual(other.read_text(encoding="utf-8"), first)

    def test_an_operators_own_key_is_kept_and_an_open_file_is_closed(self) -> None:
        self.path.parent.mkdir(parents=True)
        self.path.write_text("an-operator-chosen-key-1234567890\n", encoding="utf-8")
        os.chmod(self.path, 0o644)
        self.assertEqual(mk.make(self.path), "kept")
        self.assertEqual(self.path.read_text(encoding="utf-8"), "an-operator-chosen-key-1234567890\n")
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode) & 0o077, 0, "a key others could read is closed to them")

    def test_a_file_that_is_not_a_usable_key_is_an_error_and_is_not_overwritten(self) -> None:
        self.path.parent.mkdir(parents=True)
        for content in ("", "short\n", "\n\n"):
            self.path.write_text(content, encoding="utf-8")
            with self.assertRaises(SystemExit):
                mk.make(self.path)
            self.assertEqual(self.path.read_text(encoding="utf-8"), content)

    @unittest.skipIf(os.name == "nt", "symbolic links need privileges on Windows")
    def test_a_symbolic_link_is_never_followed(self) -> None:
        self.path.parent.mkdir(parents=True)
        target = self.path.parent / "elsewhere"
        target.write_text("x" * 40 + "\n", encoding="utf-8")
        self.path.symlink_to(target)
        with self.assertRaises(SystemExit):
            mk.make(self.path)

    def test_the_command_does_not_print_the_key(self) -> None:
        import contextlib
        import io

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(mk.main([str(self.path)]), 0)
        self.assertNotIn(self.path.read_text(encoding="utf-8").strip(), out.getvalue())
        self.assertIn("RESULT_KEY=CREATED", out.getvalue())


class InstallerTextTests(unittest.TestCase):
    def test_the_installers_pass_the_arguments_these_tests_assume(self) -> None:
        server = (PROVISIONING / "install_server.sh").read_text(encoding="utf-8")
        voice = (PROVISIONING / "install_voice_ui.sh").read_text(encoding="utf-8")
        for fragment in (f"--ensure {KEY}", f'--adopt "{KEY}=/etc/hydra-umc/voice-ui.env:{KEY}"', f'--mirror "{KEY}=/etc/hydra-umc/voice-ui.env:{KEY}"', f"--ensure {REQUIRE}=1"):
            self.assertIn(fragment, server, fragment)
        for fragment in (f"--ensure {KEY}", f'--adopt "{KEY}=/etc/hydra-umc/server.env:{KEY}"', f"--ensure {SUBJECT}=1"):
            self.assertIn(fragment, voice, fragment)

    def test_the_technician_installer_makes_the_key_file_and_can_leave_signing_off(self) -> None:
        text = (PROVISIONING / "install_local_technician.sh").read_text(encoding="utf-8")
        self.assertIn('SIGNING="${HYDRA_UMC_LOCAL_TECHNICIAN_SIGNING:-on}"', text)
        self.assertIn("--no-signing)", text)
        self.assertIn("make_result_key.py", text)
        self.assertIn("HYDRA_UMC_LOCAL_TECHNICIAN_RESULT_KEY_FILE=$KEY_FILE", text)
        self.assertIn("/etc/hydra-umc-local-technician/result.key", text.replace("$SETTINGS_DIR", "/etc/hydra-umc-local-technician"))
        # the key itself is never written by the shell script (it would end up in a process list or a log)
        self.assertNotIn("openssl rand", text)
        self.assertNotIn("token_hex", text)

    def test_the_template_asks_for_the_key_and_the_signature(self) -> None:
        template = (PROVISIONING / "server.env.example").read_text(encoding="utf-8")
        self.assertIn(f"{KEY}=SET_LOCALLY", template)
        self.assertIn(f"{REQUIRE}=1", template)

    def test_no_key_is_written_into_the_repository(self) -> None:
        hexkey = re.compile(r"(?<![0-9a-fA-F])[0-9a-f]{64}(?![0-9a-fA-F])")
        offenders = []
        for path in list(PROVISIONING.glob("*")) + list((ROOT / "config").rglob("*")) + list((ROOT / "systemd").rglob("*")):
            if path.is_file() and path.suffix in {"", ".sh", ".py", ".env", ".example", ".service", ".yaml", ".yml", ".conf"}:
                try:
                    text = path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                for line in text.splitlines():
                    if re.search(r"(KEY|SECRET|TOKEN)\s*=", line) and hexkey.search(line):
                        offenders.append(f"{path.name}: {line[:60]}")
        self.assertEqual(offenders, [])

    def test_the_names_match_what_the_services_read_when_they_are_checked_out(self) -> None:
        server = ROOT.parent / "HYDRA-UMC-SERVER" / "src" / "voiceConfirm.ts"
        if server.is_file():
            text = server.read_text(encoding="utf-8")
            self.assertIn(f'"{KEY}"', text)
            self.assertIn(REQUIRE, text)
        technician = ROOT.parent / "HYDRA-UMC-LOCAL-TECHNICIAN" / "src" / "hydra_umc_local_technician" / "orchestrator" / "result_signing.py"
        if technician.is_file():
            text = technician.read_text(encoding="utf-8")
            self.assertIn('"HYDRA_UMC_LOCAL_TECHNICIAN_RESULT_KEY"', text)
            self.assertIn("_FILE", text)
        voice = ROOT.parent / "HYDRA-UMC-VOICE-UI" / "src"
        if voice.is_dir():
            joined = "".join(p.read_text(encoding="utf-8") for p in voice.rglob("*.py"))
            self.assertIn(KEY, joined)
            self.assertIn(SUBJECT, joined)


if __name__ == "__main__":
    unittest.main(verbosity=1)
