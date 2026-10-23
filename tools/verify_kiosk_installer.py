#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - Kiosk installer: who the screen runs as
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""provisioning/install_kiosk.sh runs the HDMI session as its own locked account, hydra-umc-kiosk, and not as the
administrator who ran it. Static checks of the script, and the two blocks that touch accounts (the kiosk user, and the
cleanup of the previous user's profile) run in bash against stubs of useradd, passwd, usermod, id and getent in a
temporary folder: nothing is installed, no root is needed."""
from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSTALLER = ROOT / "provisioning" / "install_kiosk.sh"
BASH = shutil.which("bash")


def posix(path: Path) -> str:
    return re.sub(r"^([A-Za-z]):", lambda m: "/" + m.group(1).lower(), path.as_posix()) if os.name == "nt" else path.as_posix()


def block(text: str, name: str) -> str:
    return text.split(f"# --- {name} begin")[1].split(f"# --- {name} end")[0]


class StaticTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = INSTALLER.read_text(encoding="utf-8")

    def test_the_default_account_is_a_dedicated_one_not_the_administrator(self) -> None:
        self.assertIn('KIOSK_USER="${HYDRA_KIOSK_USER:-hydra-umc-kiosk}"', self.text)
        self.assertIsNone(re.search(r'^KIOSK_USER=.*SUDO_USER', self.text, re.MULTILINE), "the administrator who ran the script is no longer the session")

    def test_the_account_has_no_sudo_a_locked_password_and_only_screen_groups(self) -> None:
        lines = block(self.text, "kiosk user").splitlines()
        users = "\n".join(line for line in lines if not line.lstrip().startswith("#"))
        self.assertIn("passwd --lock", users)
        for group in ("sudo", "adm", "wheel", "root", "docker"):
            self.assertNotRegex(users, rf"\b{group}\b", f"the kiosk account must not be in {group}")
        self.assertIn("for group in video render input", users)

    def test_autologin_and_the_profile_use_that_account(self) -> None:
        self.assertIn("--autologin $KIOSK_USER", self.text)
        self.assertIn('"$KIOSK_HOME/.bash_profile"', self.text)

    def test_the_text_consoles_are_closed_unless_the_operator_asks(self) -> None:
        self.assertIn('Option "DontVTSwitch" "true"', self.text)
        self.assertIn('Option "DontZap" "true"', self.text)
        self.assertIn('HYDRA_KIOSK_ALLOW_VT_SWITCH:-0', self.text)

    def test_the_browser_has_no_developer_tools_and_no_password_manager(self) -> None:
        self.assertIn('"DeveloperToolsAvailability": 2', self.text)
        self.assertIn('"PasswordManagerEnabled": false', self.text)

    def test_the_script_has_valid_syntax(self) -> None:
        if not BASH:
            self.skipTest("bash is needed")
        self.assertEqual(subprocess.run([BASH, "-n", INSTALLER.as_posix()], capture_output=True, text=True).returncode, 0)


@unittest.skipUnless(BASH, "bash is needed")
class AccountBlockTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.stubs = self.root / "stubs"
        self.stubs.mkdir()
        self.log = self.root / "log.txt"
        self.accounts = self.root / "accounts"  # one file per existing account, holding its home
        self.accounts.mkdir()
        self.homes = self.root / "homes"
        self.homes.mkdir()
        self.stub("id", 'name="${@: -1}"; [[ -e "$ACCOUNTS/$name" ]]')
        self.stub(
            "getent",
            'if [[ "$1" == group ]]; then [[ " $GROUPS_THAT_EXIST " == *" $2 "* ]]; '
            'else [[ -e "$ACCOUNTS/$2" ]] && echo "$2:x:1000:1000::$(cat "$ACCOUNTS/$2"):/bin/bash"; fi',
        )
        self.stub("useradd", 'echo "useradd $*" >> "$LOG"; name="${@: -1}"; echo "/var/lib/$name" > "$ACCOUNTS/$name"')
        for name in ("passwd", "usermod", "chown"):
            self.stub(name, f'echo "{name} $*" >> "$LOG"')
        self.stub("install", 'echo "install $*" >> "$LOG"')

    def stub(self, name: str, body: str) -> None:
        path = self.stubs / name
        path.write_text("#!/usr/bin/env bash\n" + body + "\n", encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IEXEC)

    def run_blocks(self, names: list[str], apply: bool = True, **variables: str) -> subprocess.CompletedProcess[str]:
        text = INSTALLER.read_text(encoding="utf-8")
        script = (
            'run() { if $APPLY; then "$@"; else printf "[dry-run] "; printf "%q " "$@"; printf "\\n"; fi; }\n'
            + "\n".join(block(text, name) for name in names)
        )
        env = {
            **os.environ,
            "PATH": f"{posix(self.stubs)}:{os.environ['PATH']}",
            "APPLY": "true" if apply else "false",
            "KIOSK_USER": "hydra-umc-kiosk",
            "PREVIOUS_KIOSK_USER": "",
            "LOG": posix(self.log),
            "ACCOUNTS": posix(self.accounts),
            "GROUPS_THAT_EXIST": "video render input sudo adm",
            **variables,
        }
        return subprocess.run([BASH, "-c", script], capture_output=True, text=True, env=env, check=False)

    def logged(self) -> str:
        return self.log.read_text(encoding="utf-8") if self.log.exists() else ""

    def test_a_missing_account_is_created_locked_with_a_login_shell_and_only_the_screen_groups(self) -> None:
        result = self.run_blocks(["kiosk user"])
        self.assertEqual(result.returncode, 0, result.stderr)
        log = self.logged()
        self.assertRegex(log, r"useradd --create-home --home-dir /var/lib/hydra-umc-kiosk --shell /bin/bash .*hydra-umc-kiosk")
        self.assertIn("passwd --lock hydra-umc-kiosk", log)
        for group in ("video", "render", "input"):
            self.assertIn(f"usermod --append --groups {group} hydra-umc-kiosk", log)
        for forbidden in ("sudo", "adm", "wheel"):
            self.assertNotIn(forbidden, log)
        self.assertIn("kiosk user: hydra-umc-kiosk (home /var/lib/hydra-umc-kiosk)", result.stdout)

    def test_an_account_that_already_exists_is_not_created_again_or_given_a_new_password(self) -> None:
        (self.accounts / "hydra-umc-kiosk").write_text("/var/lib/hydra-umc-kiosk", encoding="utf-8")
        result = self.run_blocks(["kiosk user"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("useradd", self.logged())
        self.assertNotIn("passwd", self.logged())

    def test_a_group_that_does_not_exist_is_skipped(self) -> None:
        result = self.run_blocks(["kiosk user"], GROUPS_THAT_EXIST="video")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usermod --append --groups video", self.logged())
        self.assertNotIn("render", self.logged())

    def test_a_dry_run_changes_nothing_and_says_what_it_would_do(self) -> None:
        result = self.run_blocks(["kiosk user"], apply=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.logged(), "")
        self.assertIn("[dry-run] useradd", result.stdout)
        self.assertIn("[dry-run] passwd --lock", result.stdout)

    def test_the_kiosk_line_leaves_the_profile_of_the_previous_user_and_nothing_else_does(self) -> None:
        home = self.homes / "admin"
        home.mkdir()
        profile = home / ".bash_profile"
        profile.write_text(
            "export EDITOR=vim\n"
            '[ -z "$DISPLAY" ] && exec startx /opt/hydra-umc/kiosk/kiosk-session.sh -- -verbose 0 &> /dev/null\n'
            "alias ll='ls -l'\n",
            encoding="utf-8",
        )
        (self.accounts / "admin").write_text(posix(home), encoding="utf-8")
        result = self.run_blocks(["previous user"], PREVIOUS_KIOSK_USER="admin")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(profile.read_text(encoding="utf-8"), "export EDITOR=vim\nalias ll='ls -l'\n")
        self.assertIn("Removed the kiosk line", result.stdout)

    def test_root_the_kiosk_account_itself_and_nobody_are_left_alone(self) -> None:
        home = self.homes / "root"
        home.mkdir()
        original = "exec startx /opt/hydra-umc/kiosk/kiosk-session.sh\n"
        (home / ".bash_profile").write_text(original, encoding="utf-8")
        (self.accounts / "root").write_text(posix(home), encoding="utf-8")
        (self.accounts / "hydra-umc-kiosk").write_text(posix(home), encoding="utf-8")
        for previous in ("root", "hydra-umc-kiosk", ""):
            result = self.run_blocks(["previous user"], PREVIOUS_KIOSK_USER=previous)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((home / ".bash_profile").read_text(encoding="utf-8"), original, previous)

    def test_a_dry_run_leaves_the_profile_of_the_previous_user_alone(self) -> None:
        home = self.homes / "admin"
        home.mkdir()
        original = "exec startx /opt/hydra-umc/kiosk/kiosk-session.sh\n"
        (home / ".bash_profile").write_text(original, encoding="utf-8")
        (self.accounts / "admin").write_text(posix(home), encoding="utf-8")
        result = self.run_blocks(["previous user"], apply=False, PREVIOUS_KIOSK_USER="admin")
        self.assertEqual((home / ".bash_profile").read_text(encoding="utf-8"), original)
        self.assertIn("[dry-run] remove the kiosk line", result.stdout)


if __name__ == "__main__":
    unittest.main()
