#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - Signed package verification
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Prove tools/package_component.py: Ed25519 against the RFC 8032 test vectors, a signed package that verifies, and every way of tampering with one that must be refused."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("package_component", ROOT / "tools" / "package_component.py")
assert spec and spec.loader
pc = importlib.util.module_from_spec(spec)
sys.modules["package_component"] = pc
spec.loader.exec_module(pc)

# RFC 8032 section 7.1
VECTORS = [
    ("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60", "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a", "",
     "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"),
    ("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb", "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c", "72",
     "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"),
]


class Ed25519Tests(unittest.TestCase):
    def test_rfc_8032_vectors(self) -> None:
        for seed, public, message, signature in VECTORS:
            with self.subTest(public=public[:8]):
                self.assertEqual(pc.ed25519_public_key(bytes.fromhex(seed)).hex(), public)
                produced = pc.ed25519_sign(bytes.fromhex(seed), bytes.fromhex(message))
                self.assertEqual(produced.hex(), signature)
                self.assertTrue(pc.ed25519_verify(bytes.fromhex(public), bytes.fromhex(message), produced))

    def test_a_changed_message_signature_or_key_is_refused(self) -> None:
        seed, public, message, signature = VECTORS[1]
        key, text, sig = bytes.fromhex(public), bytes.fromhex(message), bytes.fromhex(signature)
        self.assertFalse(pc.ed25519_verify(key, text + b"x", sig))
        self.assertFalse(pc.ed25519_verify(key, text, sig[:-1] + bytes([sig[-1] ^ 1])))
        self.assertFalse(pc.ed25519_verify(key, text, bytes([sig[0] ^ 1]) + sig[1:]))
        self.assertFalse(pc.ed25519_verify(bytes.fromhex(VECTORS[0][1]), text, sig))
        self.assertFalse(pc.ed25519_verify(key, text, sig[:63]))
        self.assertFalse(pc.ed25519_verify(key[:31], text, sig))
        # a scalar not below the group order is malleable and refused
        high = sig[:32] + (int.from_bytes(sig[32:], "little") + pc._Q).to_bytes(32, "little")
        self.assertFalse(pc.ed25519_verify(key, text, high))

    def test_the_private_key_pem_is_read_and_a_wrong_one_refused(self) -> None:
        seed = bytes.fromhex(VECTORS[0][0])
        import base64
        pem = "-----BEGIN PRIVATE KEY-----\n" + base64.b64encode(bytes.fromhex("302e020100300506032b657004220420") + seed).decode() + "\n-----END PRIVATE KEY-----\n"
        self.assertEqual(pc.seed_from_pem(pem), seed)
        with self.assertRaises(SystemExit):
            pc.seed_from_pem("-----BEGIN PRIVATE KEY-----\nAAAA\n-----END PRIVATE KEY-----\n")


class PackageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.seed = bytes.fromhex(VECTORS[0][0])
        self.public = VECTORS[0][1]
        self.trust = self.root / "release_key.pub"
        self.trust.write_text(self.public + "\n", encoding="ascii")
        self.repo = self.root / "HYDRA-UMC-SERVER"
        for relative, content in {"dist/server.cjs": "code", "dist/server.cjs.map": "no", "dist/__pycache__/x.pyc": "no", "public/index.html": "<html>", "package.json": "{}", "package-lock.json": "{}",
                                  "systemd/hydra-umc-server.service": "[Unit]", "src/server.ts": "no"}.items():
            target = self.repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        (self.repo / "hydra-umc.project.json").write_text(json.dumps({"version": "0.8.1.0"}), encoding="utf-8")
        self.out = self.root / "out"
        self.package, self.version, self.digest = pc.build("server", self.repo, self.out)
        self.signature = pc.sign_package(self.package, self.seed, self.trust)

    def verify(self, package: Path | None = None):
        return pc.verify_package(package or self.package, self.public)

    def rebuild_with(self, members: list[tuple[str, bytes, bytes | None]], name: str = "hydra-server-0.8.1.0.tgz") -> Path:
        """A signed package whose archive holds exactly `members` (name, data, link target): signed correctly, so only its content can make it refused."""
        folder = self.root / "forged"
        folder.mkdir(exist_ok=True)
        package = folder / name
        with tarfile.open(package, "w:gz") as tar:
            for member_name, data, link in members:
                info = tarfile.TarInfo(member_name)
                if link is not None:
                    info.type = tarfile.SYMTYPE
                    info.linkname = link.decode()
                    tar.addfile(info)
                else:
                    info.size = len(data)
                    tar.addfile(info, io.BytesIO(data))
        digest = hashlib.sha256(package.read_bytes()).hexdigest()
        (folder / (name + ".sha256")).write_text(f"{digest}  {name}\n", encoding="utf-8")
        pc.sign_package(package, self.seed, self.trust)
        return package

    def test_the_package_holds_only_the_layout_and_no_build_leftovers(self) -> None:
        with tarfile.open(self.package) as tar:
            names = {member.name for member in tar.getmembers()}
        self.assertEqual(names, {"dist/server.cjs", "public/index.html", "package.json", "package-lock.json", "systemd/hydra-umc-server.service"})
        self.assertEqual(self.package.name, "hydra-server-0.8.1.0.tgz")
        self.assertEqual(self.digest, hashlib.sha256(self.package.read_bytes()).hexdigest())

    def test_a_signed_package_verifies(self) -> None:
        self.assertEqual(self.verify(), ("server", "0.8.1.0", self.digest))
        self.assertEqual(self.signature.name, "hydra-server-0.8.1.0.tgz.sig")
        self.assertRegex(self.signature.read_text(encoding="ascii"), r"^[0-9a-f]{128}\n$")

    def test_a_changed_byte_is_refused(self) -> None:
        data = bytearray(self.package.read_bytes())
        data[len(data) // 2] ^= 0x01
        self.package.write_bytes(bytes(data))
        with self.assertRaisesRegex(pc.PackageRefused, "hash does not match"):
            self.verify()

    def test_a_changed_package_with_a_recomputed_hash_is_still_refused(self) -> None:
        # whoever can write the package can write the .sha256 next to it: only the signature stops this
        forged = self.rebuild_with([("dist/server.cjs", b"malicious", None)])
        (forged.parent / (forged.name + ".sig")).write_text(self.signature.read_text(encoding="ascii"), encoding="ascii")
        with self.assertRaisesRegex(pc.PackageRefused, "signature is not valid"):
            self.verify(forged)

    def test_a_missing_signature_or_hash_is_refused(self) -> None:
        self.signature.unlink()
        with self.assertRaisesRegex(pc.PackageRefused, r"\.sig is missing"):
            self.verify()
        (self.out / (self.package.name + ".sha256")).unlink()
        with self.assertRaisesRegex(pc.PackageRefused, r"\.sha256 is missing"):
            self.verify()

    def test_a_signature_by_another_key_is_refused(self) -> None:
        other = bytes.fromhex(VECTORS[1][0])
        text = pc.package_message("server", "0.8.1.0", self.digest)
        self.signature.write_text(pc.ed25519_sign(other, text).hex() + "\n", encoding="ascii")
        with self.assertRaisesRegex(pc.PackageRefused, "signature is not valid"):
            self.verify()

    def test_a_signed_package_cannot_be_passed_off_as_another_component_or_version(self) -> None:
        for new_name in ("hydra-studio-0.8.1.0.tgz", "hydra-server-0.9.0.0.tgz"):
            with self.subTest(new_name):
                copy = self.root / "copy" / new_name
                copy.parent.mkdir(exist_ok=True)
                copy.write_bytes(self.package.read_bytes())
                (copy.parent / (new_name + ".sha256")).write_text(f"{self.digest}  {new_name}\n", encoding="utf-8")
                (copy.parent / (new_name + ".sig")).write_text(self.signature.read_text(encoding="ascii"), encoding="ascii")
                with self.assertRaisesRegex(pc.PackageRefused, "signature is not valid"):
                    self.verify(copy)

    def test_a_name_that_is_not_a_package_is_refused(self) -> None:
        for name in ("server.tgz", "hydra-server-latest.tgz", "hydra-unknown-1.0.0.tgz", "hydra-server-0.8.1.0.zip"):
            with self.subTest(name):
                with self.assertRaises(pc.PackageRefused):
                    self.verify(self.root / name)

    def test_paths_that_escape_the_target_are_refused(self) -> None:
        for bad in ("../evil", "dist/../../evil", "/etc/cron.d/x", "dist\\..\\evil", "C:/Windows/x"):
            with self.subTest(bad):
                forged = self.rebuild_with([("dist/server.cjs", b"x", None), (bad, b"x", None)])
                with self.assertRaises(pc.PackageRefused):
                    self.verify(forged)

    def test_links_and_unexpected_members_are_refused(self) -> None:
        with self.assertRaisesRegex(pc.PackageRefused, "not a regular file"):
            self.verify(self.rebuild_with([("dist/server.cjs", b"", b"/etc/passwd")]))
        with self.assertRaisesRegex(pc.PackageRefused, "not part of a server package"):
            self.verify(self.rebuild_with([("dist/server.cjs", b"x", None), ("etc/shadow", b"x", None)]))

    def test_signing_refuses_an_untrusted_key_and_a_wrong_hash(self) -> None:
        with self.assertRaisesRegex(SystemExit, "not the one this repository trusts"):
            pc.sign_package(self.package, bytes.fromhex(VECTORS[1][0]), self.trust)
        (self.out / (self.package.name + ".sha256")).write_text("0" * 64 + "  x\n", encoding="utf-8")
        with self.assertRaisesRegex(SystemExit, "not the hash"):
            pc.sign_package(self.package, self.seed, self.trust)

    def test_packing_refuses_what_is_not_built_or_the_wrong_repository(self) -> None:
        (self.repo / "dist" / "server.cjs").unlink()
        with self.assertRaisesRegex(SystemExit, "build it first"):
            pc.build("server", self.repo, self.root / "out2")
        with self.assertRaisesRegex(SystemExit, "studio is HYDRA-UMC-STUDIO, not HYDRA-UMC-SERVER"):
            pc.build("studio", self.repo, self.root / "out3")

    def test_the_signed_text_cannot_be_ambiguous(self) -> None:
        with self.assertRaises(ValueError):
            pc.package_message("server|x", "1.0.0", "0" * 64)
        with self.assertRaises(ValueError):
            pc.package_message("server", "1.0.0", "ABC")

    def test_the_trusted_key_file_is_a_real_key(self) -> None:
        self.assertRegex(pc.trusted_key(), r"^[0-9a-f]{64}$")

    def test_the_key_here_is_the_key_the_sdk_publishes(self) -> None:
        for candidate in (ROOT.parent / "HYDRA-UMC-SDK", ROOT.parent / ".hydra-umc-sdk-contract"):
            published = candidate / "contracts" / "trust" / "release_key.pub"
            if published.is_file():
                self.assertEqual(published.read_text(encoding="ascii").strip(), pc.trusted_key())
                return
        self.skipTest("no SDK checkout next to this repository")


def main() -> int:
    result = unittest.main(module=__name__, exit=False, verbosity=1).result
    if result.wasSuccessful():
        print(f"PACKAGE_VERIFY=PASS tests={result.testsRun}")
        return 0
    print("PACKAGE_VERIFY=FAIL", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
