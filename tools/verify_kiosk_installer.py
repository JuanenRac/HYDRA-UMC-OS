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


@unittest.skipUnless(BASH, "bash is needed")
class LocalScreenTests(unittest.TestCase):
    """The setting that says which local screen the CM5 drives (hdmi | dsi | none): the HDMI kiosk and the DSI app both
    want tty1, so only one of them is installed. The block runs in bash against stubs; nothing is installed."""

    LIBRARY = ROOT / "provisioning" / "local_screen.sh"

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.stubs = self.root / "stubs"
        self.stubs.mkdir()
        self.log = self.root / "log.txt"
        self.systemd = self.root / "systemd"
        (self.systemd / "getty@tty1.service.d").mkdir(parents=True)
        self.autologin = self.systemd / "getty@tty1.service.d" / "hydra-umc-autologin.conf"
        self.autologin.write_text("[Service]\n", encoding="utf-8")
        self.config = self.root / "etc" / "local-screen.conf"
        for name in ("systemctl", "install"):
            path = self.stubs / name
            path.write_text('#!/usr/bin/env bash\necho "' + name + ' $*" >> "$LOG"\n', encoding="utf-8")
            path.chmod(path.stat().st_mode | stat.S_IEXEC)
        # the stub of install must still make a directory, as local_screen_write asks for one
        (self.stubs / "install").write_text('#!/usr/bin/env bash\necho "install $*" >> "$LOG"\n[[ "$1" == -d ]] && mkdir -p "${@: -1}"\nexit 0\n', encoding="utf-8")

    def run_block(self, apply: bool = True, request: str = "", **variables: str) -> subprocess.CompletedProcess[str]:
        text = INSTALLER.read_text(encoding="utf-8")
        script = (
            'run() { if $APPLY; then "$@"; else printf "[dry-run] "; printf "%q " "$@"; printf "\n"; fi; }\n'
            + block(text, "local screen")
            + '\necho CONTINUED\n'
        )
        env = {
            **{key: value for key, value in os.environ.items() if key != "HYDRA_LOCAL_SCREEN"},
            "PATH": f"{posix(self.stubs)}:{os.environ['PATH']}",
            "APPLY": "true" if apply else "false",
            "SCREEN_REQUEST": request,
            "ROOT": posix(ROOT),
            "SYSTEMD_DIR": posix(self.systemd),
            "HYDRA_LOCAL_SCREEN_FILE": posix(self.config),
            "LOG": posix(self.log),
            **variables,
        }
        return subprocess.run([BASH, "-c", "set -euo pipefail\n" + script], capture_output=True, text=True, env=env, check=False)

    def logged(self) -> str:
        return self.log.read_text(encoding="utf-8") if self.log.exists() else ""

    def test_without_a_setting_the_screen_is_hdmi_and_the_installer_goes_on(self) -> None:
        result = self.run_block()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("local screen: hdmi", result.stdout)
        self.assertIn("CONTINUED", result.stdout)
        self.assertTrue(self.autologin.exists())
        self.assertIn("systemctl enable getty@tty1.service", self.logged())

    def test_hdmi_switches_the_dsi_app_off_when_it_is_installed(self) -> None:
        (self.systemd / "hydra-umc-dsi.service").write_text("[Unit]\n", encoding="utf-8")
        result = self.run_block()
        self.assertIn("CONTINUED", result.stdout)
        self.assertIn("systemctl disable --now hydra-umc-dsi.service", self.logged())

    def test_dsi_installs_no_kiosk_and_hands_tty1_back(self) -> None:
        result = self.run_block(HYDRA_LOCAL_SCREEN="dsi")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("CONTINUED", result.stdout)
        self.assertFalse(self.autologin.exists())
        self.assertIn("kiosk/install_kiosk.sh --screen dsi", result.stdout)
        self.assertNotIn("hydra-umc-dsi.service", self.logged())

    def test_none_hands_tty1_back_and_switches_the_dsi_app_off(self) -> None:
        (self.systemd / "hydra-umc-dsi.service").write_text("[Unit]\n", encoding="utf-8")
        result = self.run_block(HYDRA_LOCAL_SCREEN="none")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("CONTINUED", result.stdout)
        self.assertFalse(self.autologin.exists())
        log = self.logged()
        self.assertIn("systemctl disable --now hydra-umc-dsi.service", log)
        self.assertIn("systemctl enable getty@tty1.service", log)

    def test_a_value_that_is_not_one_of_the_three_stops_everything(self) -> None:
        for value in ("both", "HDMI-1", "ninguna", "1"):
            result = self.run_block(HYDRA_LOCAL_SCREEN=value)
            self.assertEqual(result.returncode, 2, value)
            self.assertNotIn("CONTINUED", result.stdout)
            self.assertIn("hdmi, dsi or none", result.stderr)
            self.assertTrue(self.autologin.exists(), value)

    def test_the_saved_file_is_read_and_the_environment_wins_over_it(self) -> None:
        self.config.parent.mkdir(parents=True)
        self.config.write_text("# comment\nHYDRA_LOCAL_SCREEN=dsi\n", encoding="utf-8")
        self.assertNotIn("CONTINUED", self.run_block().stdout)
        result = self.run_block(HYDRA_LOCAL_SCREEN="hdmi")
        self.assertIn("CONTINUED", result.stdout)

    def test_screen_saves_the_choice_and_a_dry_run_does_not(self) -> None:
        dry = self.run_block(apply=False, request="dsi")
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertFalse(self.config.exists())
        self.assertIn("[dry-run] save HYDRA_LOCAL_SCREEN=dsi", dry.stdout)
        self.assertTrue(self.autologin.exists(), "a dry run takes nothing back")
        result = self.run_block(request="dsi")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("HYDRA_LOCAL_SCREEN=dsi", self.config.read_text(encoding="utf-8"))
        self.assertEqual(self.run_block(request="").returncode, 0)  # the saved choice is read back without --screen

    def test_a_request_beats_the_environment(self) -> None:
        result = self.run_block(request="none", HYDRA_LOCAL_SCREEN="hdmi")
        self.assertIn("local screen: none", result.stdout)

    def test_the_profile_of_the_kiosk_account_does_not_start_x_for_another_screen(self) -> None:
        text = INSTALLER.read_text(encoding="utf-8")
        self.assertIn('grep -Eqx "HYDRA_LOCAL_SCREEN=(dsi|none)" /etc/hydra-umc/local-screen.conf', text)

    def test_nothing_in_the_installer_refers_to_the_retired_qt_shell(self) -> None:
        self.assertNotIn("hmi_qt6", INSTALLER.read_text(encoding="utf-8"))
        self.assertNotIn("hmi_qt6", (ROOT / "provisioning" / "kiosk" / "kiosk-session.sh").read_text(encoding="utf-8"))

    def test_the_library_has_valid_syntax(self) -> None:
        self.assertEqual(subprocess.run([BASH, "-n", self.LIBRARY.as_posix()], capture_output=True, text=True).returncode, 0)


if __name__ == "__main__":
    unittest.main()
