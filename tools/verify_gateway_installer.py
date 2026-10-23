#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - Gateway installer: where the secrets live
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""provisioning/install_industrial_gateway.sh keeps the secrets of the stack in /etc/hydra-umc/gateway.env and hands the file to every compose
command with --env-file. Static checks of the script, and the block that moves a file left in the checkout by an earlier version is run in bash
against a temporary folder: nothing is installed, no root is needed."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSTALLER = ROOT / "provisioning" / "install_industrial_gateway.sh"
BASH = shutil.which("bash")
BEGIN, END = "# --- gateway env begin", "# --- gateway env end"


def posix(path: Path) -> str:
    return re.sub(r"^([A-Za-z]):", lambda m: "/" + m.group(1).lower(), path.as_posix()) if os.name == "nt" else path.as_posix()


class StaticTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = INSTALLER.read_text(encoding="utf-8")

    def test_the_secrets_live_outside_the_checkout(self) -> None:
        self.assertIn('GATEWAY_ENV="${HYDRA_GATEWAY_ENV:-/etc/hydra-umc/gateway.env}"', self.text)
        self.assertNotIn('gateway_env.py" "$GATEWAY_DIR/.env"', self.text)
        for call in re.findall(r"gateway_env\.py\"[^\n]*", self.text):
            self.assertIn('"$GATEWAY_ENV"', call)

    def test_every_compose_command_reads_the_same_env_file(self) -> None:
        self.assertIn('COMPOSE="docker compose --env-file $GATEWAY_ENV"', self.text)
        for line in self.text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or "docker compose" not in stripped:
                continue
            if stripped.startswith('COMPOSE="'):
                continue
            self.fail(f"a docker compose command that does not use $COMPOSE: {stripped}")

    def test_the_old_file_is_moved_not_copied(self) -> None:
        block = self.text.split(BEGIN)[1].split(END)[0]
        self.assertIn('mv "$LEGACY_ENV" "$GATEWAY_ENV"', block)
        self.assertNotIn("cp ", block)
        self.assertIn('chmod 0600 "$GATEWAY_ENV"', block)

    def test_the_script_has_valid_syntax(self) -> None:
        if not BASH:
            self.skipTest("bash is needed")
        self.assertEqual(subprocess.run([BASH, "-n", INSTALLER.as_posix()], capture_output=True, text=True).returncode, 0)


@unittest.skipUnless(BASH, "bash is needed")
class MoveBlockTests(unittest.TestCase):
    """The block between the markers, run with a stub of python3 and a temporary folder."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        (self.root / "checkout").mkdir()
        (self.root / "etc").mkdir()
        self.stubs = self.root / "stubs"
        self.stubs.mkdir()
        # python3 stub: records its arguments and creates the file it was asked for, like gateway_env.py --apply
        stub = self.stubs / "python3"
        stub.write_text('#!/usr/bin/env bash\necho "$@" >> "$STUB_LOG"\n[[ " $* " == *" --apply "* ]] && [[ ! -e "$2" ]] && echo "NEW=1" > "$2"\nexit 0\n', encoding="utf-8")
        stub.chmod(0o755)
        for name in ("chown", "install"):  # root-only commands: the stub only has to accept them
            path = self.stubs / name
            path.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
            path.chmod(0o755)
        self.log = self.root / "log.txt"
        block = INSTALLER.read_text(encoding="utf-8").split(BEGIN)[1].split(END)[0]
        self.script = f'cd "{posix(self.root)}"\n{block}\n'

    def run_block(self, apply: bool) -> subprocess.CompletedProcess[str]:
        env = {
            **os.environ,
            "PATH": f"{posix(self.stubs)}:{os.environ['PATH']}",
            "APPLY": "true" if apply else "false",
            "GATEWAY_ENV": posix(self.root / "etc" / "gateway.env"),
            "LEGACY_ENV": posix(self.root / "checkout" / ".env"),
            "STUB_LOG": posix(self.log),
        }
        return subprocess.run([BASH, "-c", f'$APPLY && true || true\n{self.script}', posix(INSTALLER)], capture_output=True, text=True, env=env, check=False)

    def test_a_file_in_the_checkout_is_moved_with_its_secrets_and_never_duplicated(self) -> None:
        (self.root / "checkout" / ".env").write_text("GATEWAY_JWT_SECRET=old\n", encoding="utf-8")
        result = self.run_block(apply=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.root / "checkout" / ".env").exists(), "the old file is gone: moved, not copied")
        self.assertEqual((self.root / "etc" / "gateway.env").read_text(encoding="utf-8"), "GATEWAY_JWT_SECRET=old\n")
        self.assertIn("Moved the secrets", result.stdout)
        # gateway_env.py was then asked about the NEW place, and finds the file there
        self.assertIn(f"{posix(self.root / 'etc' / 'gateway.env')} --apply", self.log.read_text(encoding="utf-8"))

    def test_with_both_files_the_new_one_wins_and_the_old_one_is_reported_not_touched(self) -> None:
        (self.root / "checkout" / ".env").write_text("OLD=1\n", encoding="utf-8")
        (self.root / "etc" / "gateway.env").write_text("NEW=1\n", encoding="utf-8")
        result = self.run_block(apply=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / "checkout" / ".env").read_text(encoding="utf-8"), "OLD=1\n")
        self.assertEqual((self.root / "etc" / "gateway.env").read_text(encoding="utf-8"), "NEW=1\n")
        self.assertIn("WARNING", result.stderr)

    def test_a_new_device_gets_the_file_generated_at_the_new_place(self) -> None:
        result = self.run_block(apply=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.root / "etc" / "gateway.env").exists())
        self.assertFalse((self.root / "checkout" / ".env").exists())

    def test_a_dry_run_moves_and_creates_nothing(self) -> None:
        (self.root / "checkout" / ".env").write_text("OLD=1\n", encoding="utf-8")
        result = self.run_block(apply=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("[dry-run] mv", result.stdout)
        self.assertTrue((self.root / "checkout" / ".env").exists())
        self.assertFalse((self.root / "etc" / "gateway.env").exists())


if __name__ == "__main__":
    unittest.main()
