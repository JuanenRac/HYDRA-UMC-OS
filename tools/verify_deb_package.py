#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - tools/verify_deb_package.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Check the .deb that tools/build_deb.py builds.

The archive is read back with plain Python (ar, tar, gzip), so the check needs no dpkg: the three
members, the control fields, the checksums, the maintainer scripts, the files and their modes, the
unit and the agent inside. When dpkg-deb is installed (the CI runner has it) it is asked as well.
"""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import build_deb  # noqa: E402

failures: list[str] = []


def expect(condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def read_ar(raw: bytes) -> list[tuple[str, bytes]]:
    expect(raw.startswith(b"!<arch>\n"), "the file must start with the ar signature")
    members: list[tuple[str, bytes]] = []
    position = 8
    while position < len(raw):
        header = raw[position:position + 60]
        expect(len(header) == 60 and header[58:60] == b"`\n", "an ar member header is malformed")
        name = header[:16].decode("ascii").strip().rstrip("/")
        size = int(header[48:58].decode("ascii").strip())
        start = position + 60
        members.append((name, raw[start:start + size]))
        position = start + size + (size % 2)
    return members


def read_tar_gz(blob: bytes) -> dict[str, tarfile.TarInfo | bytes]:
    out: dict[str, tuple[tarfile.TarInfo, bytes]] = {}
    with tarfile.open(fileobj=io.BytesIO(gzip.decompress(blob)), mode="r") as tar:
        for info in tar.getmembers():
            out[info.name] = (info, tar.extractfile(info).read() if info.isfile() else b"")
    return out  # type: ignore[return-value]


def main() -> int:
    manifest = json.loads((ROOT / "hydra-umc.project.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as directory:
        first = build_deb.build(Path(directory) / "a")
        second = build_deb.build(Path(directory) / "b")
        raw = first.read_bytes()
        expect(raw == second.read_bytes(), "two builds must give the same bytes")
        expect(first.name == f"hydra-umc-platform-base_{manifest['version']}_all.deb", f"unexpected file name {first.name}")

        members = read_ar(raw)
        expect([name for name, _ in members] == ["debian-binary", "control.tar.gz", "data.tar.gz"], "the members must be debian-binary, control.tar.gz and data.tar.gz in that order")
        parts = dict(members)
        expect(parts.get("debian-binary") == b"2.0\n", "debian-binary must say 2.0")

        control_tar = read_tar_gz(parts["control.tar.gz"])
        data_tar = read_tar_gz(parts["data.tar.gz"])

        control = control_tar["./control"][1].decode("utf-8")
        fields = {line.split(":", 1)[0]: line.split(":", 1)[1].strip() for line in control.splitlines() if line and not line.startswith(" ")}
        expect(fields.get("Package") == "hydra-umc-platform-base", "Package")
        expect(fields.get("Version") == manifest["version"], "the package version must be the manifest version")
        expect(fields.get("Architecture") == "all", "Architecture")
        expect("python3 (>= 3.11)" in fields.get("Depends", "") and "systemd" in fields.get("Depends", ""), "Depends")
        expect("adduser" in fields.get("Depends", ""), "the post-install script uses adduser, so the package must depend on it")
        expect(fields.get("Installed-Size", "0").isdigit() and int(fields["Installed-Size"]) > 0, "Installed-Size")
        expect(any(line.startswith(" ") for line in control.splitlines()), "the long description must be indented")
        expect(control.endswith("\n"), "the control file must end with a newline")

        for script in ("postinst", "prerm", "postrm"):
            info, content = control_tar[f"./{script}"]
            expect(info.mode & 0o111 == 0o111, f"{script} must be executable")
            expect(content.startswith(b"#!/bin/sh\n"), f"{script} must start with a /bin/sh shebang")
            expect(b"\r" not in content, f"{script} must use plain line feeds")
            expect(b"set -e" in content, f"{script} must stop on errors")
        postinst = control_tar["./postinst"][1].decode("utf-8")
        commands = chr(10).join(line for line in postinst.splitlines() if not line.lstrip().startswith(("#", "echo")))
        expect("systemctl enable" not in commands and "systemctl start" not in commands, "the post-install script must not enable or start the service")
        expect("[ ! -f /etc/hydra-umc/config.json ]" in postinst, "an existing device configuration must be kept")

        sums = {}
        for line in control_tar["./md5sums"][1].decode("utf-8").splitlines():
            digest, _, path = line.partition("  ")
            sums[path] = digest
        files = {name[2:]: item for name, item in data_tar.items() if item[0].isfile()}
        expect(set(sums) == set(files), "md5sums must list exactly the files of the package")
        for path, (_, content) in files.items():
            expect(sums.get(path) == hashlib.md5(content).hexdigest(), f"md5sum of {path}")

        for name, (info, _) in data_tar.items():
            expect(info.uid == 0 and info.gid == 0, f"{name} must belong to root")
            expect(info.mtime == 0, f"{name} must carry the fixed time stamp")
            expect(".." not in name.split("/") and not name.startswith("/"), f"{name} must stay inside the package")
        expect(files["usr/bin/hydra-umc-agent"][0].mode == 0o755, "the command must be executable")
        expect(b"PYTHONPATH=/opt/hydra-umc/os-agent" in files["usr/bin/hydra-umc-agent"][1], "the command must point at the installed agent")
        for agent_file in ("agent.py", "__init__.py"):
            expect(f"opt/hydra-umc/os-agent/hydra_umc_os/{agent_file}" in files, f"{agent_file} must be installed")
            source = (ROOT / "agent" / "src" / "hydra_umc_os" / agent_file).read_bytes().replace(b"\r\n", b"\n")
            expect(files[f"opt/hydra-umc/os-agent/hydra_umc_os/{agent_file}"][1] == source, f"{agent_file} must be the one of the repository")
        expect(not any("__pycache__" in path or path.endswith(".pyc") for path in files), "no compiled files in the package")
        unit = files["usr/lib/systemd/system/hydra-umc-agent.service"][1].decode("utf-8")
        expect("ExecStart=/usr/bin/hydra-umc-agent " in unit, "the unit must run the command the package installs")
        expect("/usr/local/" not in unit, "a package must not rely on /usr/local")
        expect("\r" not in unit, "the unit must use plain line feeds")
        for profile in ("base.json", "control.json", "vision.json"):
            expect(f"usr/share/hydra-umc/config/profiles/{profile}" in files, f"profile {profile} must be installed")
        installed_manifest = json.loads(files["opt/hydra-umc/os-agent/hydra-umc.project.json"][1])
        expect(installed_manifest["version"] == manifest["version"], "the installed manifest must carry the version")
        expect(b"GPL-3.0" in files[f"usr/share/doc/hydra-umc-platform-base/copyright"][1], "the copyright file must name the licence")

        shell = shutil.which("sh")
        if shell:
            for script in ("postinst", "prerm", "postrm"):
                path = Path(directory) / script
                path.write_bytes(control_tar[f"./{script}"][1])
                result = subprocess.run([shell, "-n", str(path)], capture_output=True, text=True)
                expect(result.returncode == 0, f"{script} has a syntax error: {result.stderr}")

        dpkg_deb = shutil.which("dpkg-deb")
        if dpkg_deb:
            info = subprocess.run([dpkg_deb, "--info", str(first)], capture_output=True, text=True)
            expect(info.returncode == 0 and "Package: hydra-umc-platform-base" in info.stdout, f"dpkg-deb --info refused the package: {info.stderr}")
            listing = subprocess.run([dpkg_deb, "--contents", str(first)], capture_output=True, text=True)
            expect(listing.returncode == 0 and "usr/bin/hydra-umc-agent" in listing.stdout, f"dpkg-deb --contents refused the package: {listing.stderr}")

    if failures:
        for message in failures:
            print(f"DEB_PACKAGE=FAIL {message}", file=sys.stderr)
        return 1
    print(f"DEB_PACKAGE=PASS files={len(files)} dpkg_deb={'checked' if dpkg_deb else 'not available'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
