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
import re
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
        pem = "-----BEGIN " + "PRIVATE KEY-----\n" + base64.b64encode(bytes.fromhex("302e020100300506032b657004220420") + seed).decode() + "\n-----END PRIVATE KEY-----\n"
        self.assertEqual(pc.seed_from_pem(pem), seed)
        with self.assertRaises(SystemExit):
            pc.seed_from_pem("-----BEGIN " + "PRIVATE KEY-----\nAAAA\n-----END PRIVATE KEY-----\n")


class NamesTheServerLooksForTests(unittest.TestCase):
    """What HYDRA-UMC-SERVER asks a release for is what this repository packs and what its workflow builds."""

    def test_every_component_of_the_self_update_has_a_layout_and_is_built_by_the_workflow(self) -> None:
        source = Path(__file__).resolve().parent.parent.parent / "HYDRA-UMC-SERVER" / "src" / "selfUpdate.ts"
        workflow = (Path(__file__).resolve().parent.parent / ".github" / "workflows" / "component-package.yml").read_text(encoding="utf-8")
        expected = {"server": "HYDRA-UMC-SERVER", "studio": "HYDRA-UMC-STUDIO", "os-agent": "HYDRA-UMC-OS"}
        if source.is_file():
            text = source.read_text(encoding="utf-8")
            block = re.search(r"SELF_UPDATE_COMPONENTS = \{(.*?)\}", text, re.S)
            assert block
            self.assertEqual(dict(re.findall(r'"?([a-z-]+)"?:\s*"(HYDRA-UMC-[A-Z-]+)"', block.group(1))), expected)
            self.assertIn("`hydra-${component}-${version}.tgz`", text)
        for component, repository in expected.items():
            self.assertEqual(pc.LAYOUT[component][0], repository)
            self.assertTrue(pc.NAME_PATTERN.match(f"hydra-{component}-0.1.0.tgz"))
        for component in pc.LAYOUT:
            self.assertRegex(workflow, rf"(?m)^          - {component}$", component)


class EveryProgramOfTheDeviceHasAPackage(unittest.TestCase):
    """A program the installers put on the device can travel as a package, with the same units and a description the root helper can follow."""

    def test_every_installer_row_with_a_program_folder_has_a_layout_with_its_units(self) -> None:
        rows = json.loads((ROOT / "provisioning" / "install_plan.json").read_text(encoding="utf-8"))["installers"]
        # the setup of the machine itself (Wi-Fi setup) is not a program with its own releases
        programs = {str(r["target"]).rsplit("/", 1)[-1]: r for r in rows if r.get("target") and not str(r["target"]).endswith("/wifi-provision")}
        for name, row in sorted(programs.items()):
            with self.subTest(program=name):
                self.assertIn(name, pc.LAYOUT)
                spec = pc.install_spec(name, "1.0.0")
                self.assertTrue(set(row.get("units") or []) <= set(spec["units"]), spec["units"])
                targets = {target for _source, target in pc.LAYOUT[name][1]}
                self.assertTrue({f"systemd/{unit}" for unit in spec["units"]} <= targets, spec["units"])
                self.assertEqual(spec["user"] is None, name in ("local-technician", "os-agent"), spec["user"])
        helper = pc.install_spec("helper", "1.0.0")
        self.assertEqual((helper["units"], helper["mainUnit"], helper["user"]), (["hydra-umc-helper.service", "hydra-umc-helper.path"], "hydra-umc-helper.path", None))

    def test_the_spec_says_what_the_installer_did(self) -> None:
        self.assertEqual(pc.install_spec("datalake", "1.0.0")["health"], {"port": 8095, "path": "/stats"})
        self.assertEqual(pc.install_spec("datalake", "1.0.0")["dropins"], {"hydra-umc-datalake.service.d/10-health-open.conf": "[Service]\nEnvironment=HYDRA_UMC_DATALAKE_HEALTH_OPEN=1\n"})
        planner = pc.install_spec("semantic-planner", "1.0.0")
        self.assertIn("/opt/hydra-umc/semantic-planner/pydeps", planner["dropins"]["hydra-umc-semantic-planner.service.d/20-pydeps.conf"])
        self.assertEqual(planner["python"], "3.13")
        server = pc.install_spec("server", "1.0.0")
        self.assertEqual((server["user"], server["homeInData"], server["userDirs"], server["needsFiles"]), ("hydra-umc-server", True, ["data"], ["/etc/hydra-umc/server.env"]))
        self.assertEqual(pc.install_spec("voice-ui", "1.0.0")["mainUnit"], "hydra-umc-voice-ui.service")
        self.assertIsNone(pc.install_spec("vision-streamer", "1.0.0")["mainUnit"])


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
                                  "systemd/hydra-umc-server.service": "[Unit]", "src/server.ts": "no",
                                  "node_modules/a/index.js": "a", "node_modules/a/node_modules/b/index.js": "b", "node_modules/.bin/a": "link"}.items():
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
                if link == b"<dir>":
                    info.type = tarfile.DIRTYPE
                    tar.addfile(info)
                elif link is not None:
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

    def test_the_rust_programs_pack_what_the_build_left_and_verify(self) -> None:
        for component, repository, extra in (("twin", "HYDRA-UMC-TWIN", "package/workspace/HYDRA-UMC-HIL-BRIDGE/hydra-umc.project.json"), ("orchestrator", "HYDRA-UMC-ORCHESTRATOR", "")):
            repo = self.root / repository
            files = ["hydra-umc.project.json", f"package/hydra-umc-{component}", f"systemd/hydra-umc-{component}.service"] + ([extra] if extra else [])
            for relative in files:
                target = repo / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(json.dumps({"version": "0.2.1"}), encoding="utf-8")
            built, version, _digest = pc.build(component, repo, self.out)
            pc.sign_package(built, self.seed, self.trust)
            self.assertEqual(self.verify(built)[:2], (component, "0.2.1"))
            with tarfile.open(built) as tar:
                names = {member.name for member in tar.getmembers()}
            self.assertEqual(names, {name.removeprefix("package/") for name in files} | {"hydra-install.json"})

    def test_every_package_installs_with_the_version_where_the_fleet_update_reads_it(self) -> None:
        # the real packer and the real installer, no stand-ins: pack, sign, install, read <component>/current/hydra-umc.project.json
        spec = importlib.util.spec_from_file_location("hydra_deploy_release_e2e", Path(__file__).resolve().parent / "deploy_release.py")
        assert spec and spec.loader
        deploy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(deploy)
        sources = {
            "server": ("HYDRA-UMC-SERVER", ["dist/server.cjs", "public/index.html", "package.json", "package-lock.json", "systemd/hydra-umc-server.service", "node_modules/a/index.js"]),
            "studio": ("HYDRA-UMC-STUDIO", ["dist/index.html"]),
            "os-agent": ("HYDRA-UMC-OS", ["agent/src/hydra_umc_os/agent.py", "agent/pyproject.toml", "systemd/hydra-umc-agent.service"]),
        }
        expected = {"server": "dist/server.cjs", "studio": "dist/index.html", "os-agent": "hydra_umc_os/agent.py"}
        for component, (repository, files) in sources.items():
            repo = self.root / "e2e" / repository
            for relative in files:
                target = repo / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("code", encoding="utf-8")
            (repo / "hydra-umc.project.json").write_text(json.dumps({"version": "0.9.1"}), encoding="utf-8")
            built, _version, _digest = pc.build(component, repo, self.out)
            pc.sign_package(built, self.seed, self.trust)
            with tarfile.open(built) as tar:
                names = {member.name for member in tar.getmembers()}
            self.assertIn("hydra-umc.project.json", names, component)
            self.assertIn(expected[component], names, component)
            installed = self.root / "e2e" / "installed"
            try:
                deploy.install(built, installed, trusted_key=self.public, settings=dict(deploy.DEFAULTS), sleep=lambda _s: None)
            except OSError as error:  # a Windows account without the right to make links
                self.skipTest(f"links cannot be made here: {error}")
            current = installed / component / "current"
            self.assertEqual(json.loads((current / "hydra-umc.project.json").read_text(encoding="utf-8"))["version"], "0.9.1", component)

    def test_the_package_holds_only_the_layout_and_no_build_leftovers(self) -> None:
        with tarfile.open(self.package) as tar:
            names = {member.name for member in tar.getmembers()}
        self.assertEqual(names, {"dist/server.cjs", "public/index.html", "package.json", "package-lock.json", "systemd/hydra-umc-server.service",
                                 "node_modules/a/index.js", "node_modules/a/node_modules/b/index.js", "hydra-umc.project.json", "hydra-install.json"})
        self.assertEqual(self.package.name, "hydra-server-0.8.1.0.tgz")
        self.assertEqual(self.digest, hashlib.sha256(self.package.read_bytes()).hexdigest())

    def test_the_archive_is_opened_from_the_bytes_that_were_verified(self) -> None:
        component, _version, digest, data = pc.verify_package_bytes(self.package, self.public)
        self.assertEqual(component, "server")
        self.assertEqual(data, self.package.read_bytes())
        self.assertEqual(digest, hashlib.sha256(data).hexdigest())
        # a file that is swapped after the check does not count when the members are read from the verified bytes
        forged = self.rebuild_with([("../evil", b"x", None)])
        with self.assertRaises(pc.PackageRefused):
            pc.check_members(forged, "server")
        pc.check_members(forged, "server", data)

    def test_the_same_files_always_give_the_same_bytes(self) -> None:
        import os
        import time
        later = time.time() + 3600
        for item in self.repo.rglob("*"):
            if item.is_file():
                os.utime(item, (later, later))
        again, _version, digest = pc.build("server", self.repo, self.root / "again")
        self.assertEqual(digest, self.digest)
        self.assertEqual(again.read_bytes(), self.package.read_bytes())

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

    def test_a_folder_that_escapes_the_target_is_refused(self) -> None:
        for bad in ("../../etc/hydra", "/etc/hydra", "dist/../../x", "dist" + chr(92) + ".." + chr(92) + "x"):
            with self.subTest(bad):
                forged = self.rebuild_with([("dist/server.cjs", b"x", None), (bad, b"", b"<dir>")])
                with self.assertRaisesRegex(pc.PackageRefused, "outside the target"):
                    self.verify(forged)
        self.verify(self.rebuild_with([("dist", b"", b"<dir>"), ("dist/server.cjs", b"x", None)]))

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
