#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - Encrypted settings backup verification
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Prove provisioning/backup_settings.sh and restore_settings.sh with real OpenSSL: a round trip, nothing readable in the archive, a wrong passphrase, a changed archive (even with its
checksum rewritten), a missing keyed hash and an archive with unsafe paths are all refused without touching the data directory. Skipped (and said so) without bash and openssl."""

from __future__ import annotations

import hashlib
import hmac
import io
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKUP = (ROOT / "provisioning" / "backup_settings.sh").as_posix()
RESTORE = (ROOT / "provisioning" / "restore_settings.sh").as_posix()
BASH = shutil.which("bash")
OPENSSL = shutil.which("openssl")
SECRET = "super-secret-user-hash-1234"


def env() -> dict[str, str]:
    result = dict(os.environ)
    if result.get("OPENSSL_CONF") and not Path(result["OPENSSL_CONF"]).is_file():
        result.pop("OPENSSL_CONF")
    return result


def sh(script: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([BASH, script, *arguments], env=env(), capture_output=True, text=True, check=False)


@unittest.skipUnless(BASH and OPENSSL, "bash and openssl are needed")
class BackupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)
        data = self.work / "data"
        data.mkdir()
        (data / "users.json").write_text('{"admin":"' + SECRET + '"}', encoding="utf-8")
        (data / "settings.json").write_text('{"mode":"armed"}', encoding="utf-8")
        (data / "scratch.tmp").write_text("temporary", encoding="utf-8")
        self.passfile = self.work / "pass"
        self.passfile.write_text("a-long-enough-passphrase\n", encoding="utf-8")
        self.wrong = self.work / "wrong"
        self.wrong.write_text("another-long-passphrase\n", encoding="utf-8")
        result = sh(BACKUP, "--data-dir", str(data), "--out-dir", str(self.work / "out"), "--passphrase-file", str(self.passfile))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("HYDRA_BACKUP=PASS", result.stdout)
        self.archive = next((self.work / "out").glob("*.enc"))

    def sidecar(self, suffix: str, archive: Path | None = None) -> Path:
        target = archive or self.archive
        return target.with_name(target.name + suffix)

    def restore(self, target: str, passphrase: Path | None = None, *extra: str, archive: Path | None = None) -> subprocess.CompletedProcess[str]:
        return sh(RESTORE, "--file", str(archive or self.archive), "--data-dir", str(self.work / target), "--passphrase-file", str(passphrase or self.passfile), *extra)

    def test_nothing_readable_is_in_the_archive(self) -> None:
        raw = self.archive.read_bytes()
        for needle in (SECRET.encode(), b"users.json", b"armed", b"ustar"):
            self.assertNotIn(needle, raw)
        self.assertTrue(self.sidecar(".sha256").is_file())
        self.assertRegex(self.sidecar(".hmac").read_text(), r"^[0-9a-f]{64}  hydra-umc-data-.*\.tar\.gz\.enc\n$")

    def test_the_keyed_hash_is_the_documented_one(self) -> None:
        key = hashlib.sha256(b"hydra-backup-mac:" + self.passfile.read_bytes()).digest()
        expected = hmac.new(key, self.archive.read_bytes(), hashlib.sha256).hexdigest()
        self.assertEqual(self.sidecar(".hmac").read_text().split()[0], expected)

    def test_a_dry_run_lists_and_changes_nothing(self) -> None:
        result = self.restore("restored")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("users.json", result.stdout)
        self.assertNotIn("scratch.tmp", result.stdout)
        self.assertIn("HYDRA_RESTORE=DRY-RUN", result.stdout)
        self.assertFalse((self.work / "restored").exists())

    def test_the_round_trip_restores_the_files_and_keeps_the_old_directory(self) -> None:
        live = self.work / "live"
        live.mkdir()
        (live / "old.txt").write_text("old", encoding="utf-8")
        result = self.restore("live", None, "--apply")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("HYDRA_RESTORE=PASS", result.stdout)
        self.assertEqual((live / "users.json").read_text(encoding="utf-8"), '{"admin":"' + SECRET + '"}')
        self.assertEqual((live / "settings.json").read_text(encoding="utf-8"), '{"mode":"armed"}')
        self.assertFalse((live / "scratch.tmp").exists())
        kept = list(self.work.glob("live.before-restore-*"))
        self.assertEqual(len(kept), 1)
        self.assertEqual((kept[0] / "old.txt").read_text(encoding="utf-8"), "old")

    def test_a_wrong_passphrase_is_refused_and_nothing_is_written(self) -> None:
        result = self.restore("restored", self.wrong, "--apply")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("passphrase is wrong", result.stderr)
        self.assertFalse((self.work / "restored").exists())

    def test_a_changed_archive_is_refused_even_when_its_checksum_is_rewritten(self) -> None:
        data = bytearray(self.archive.read_bytes())
        data[len(data) // 2] ^= 0x01
        self.archive.write_bytes(bytes(data))
        self.sidecar(".sha256").write_text(hashlib.sha256(bytes(data)).hexdigest() + "  " + self.archive.name + "\n", encoding="utf-8")
        result = self.restore("restored", None, "--apply")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("was changed", result.stderr)
        self.assertFalse((self.work / "restored").exists())

    def test_a_missing_keyed_hash_is_refused(self) -> None:
        self.sidecar(".hmac").unlink()
        result = self.restore("restored", None, "--apply")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(".hmac", result.stderr)
        self.assertFalse((self.work / "restored").exists())

    def test_an_archive_with_unsafe_paths_is_refused_even_when_it_is_correctly_signed(self) -> None:
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
            for name in ("data/ok.txt", "data/../../evil.txt"):
                info = tarfile.TarInfo(name)
                info.size = 1
                tar.addfile(info, io.BytesIO(b"x"))
        forged = self.work / "forged" / "hydra-umc-data-forged.tar.gz.enc"
        forged.parent.mkdir()
        command = ["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-iter", "200000", "-salt", "-pass", "file:" + str(self.passfile)]
        encrypted = subprocess.run(command, input=buffer.getvalue(), capture_output=True, env=env(), check=True).stdout
        forged.write_bytes(encrypted)
        key = hashlib.sha256(b"hydra-backup-mac:" + self.passfile.read_bytes()).digest()
        self.sidecar(".hmac", forged).write_text(hmac.new(key, encrypted, hashlib.sha256).hexdigest() + "  " + forged.name + "\n", encoding="utf-8")
        result = self.restore("restored", None, "--apply", archive=forged)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unsafe paths", result.stderr)
        self.assertFalse((self.work / "restored").exists())

    def test_a_short_passphrase_and_bad_arguments_are_refused(self) -> None:
        short = self.work / "short"
        short.write_text("tooshort\n", encoding="utf-8")
        result = sh(BACKUP, "--data-dir", str(self.work / "data"), "--out-dir", str(self.work / "out2"), "--passphrase-file", str(short))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("at least 12", result.stderr)
        self.assertEqual(list((self.work / "out2").glob("*.enc")), [])
        for arguments in ([], ["--data-dir", str(self.work / "nowhere"), "--out-dir", str(self.work), "--passphrase-file", str(self.passfile)], ["--bogus"]):
            self.assertEqual(sh(BACKUP, *arguments).returncode, 2)


def main() -> int:
    if not (BASH and OPENSSL):
        print("BACKUP_VERIFY=SKIPPED bash or openssl is not available on this host")
        return 0
    result = unittest.main(module=__name__, exit=False, verbosity=1).result
    if result.wasSuccessful():
        print(f"BACKUP_VERIFY=PASS tests={result.testsRun}")
        return 0
    print("BACKUP_VERIFY=FAIL", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
