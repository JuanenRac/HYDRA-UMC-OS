#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - tools/build_deb.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Build the hydra-umc-platform-base .deb without dpkg.

A .deb is an ``ar`` archive of three members (debian-binary, control.tar.gz, data.tar.gz). They are
written here in plain Python, so the package builds on any machine (also the Windows host that
prepares an image) and the result does not depend on the moment or the user that built it: every
file is owned by root and carries the same time stamp.

What the package installs is what provisioning/install_local_agent.sh installs, in the places a
package uses: the agent under /opt/hydra-umc/os-agent, the command /usr/bin/hydra-umc-agent, the
unit in /usr/lib/systemd/system, the example configuration and profiles in /usr/share/hydra-umc.
The configuration of the device, /etc/hydra-umc/config.json, is created by the post-install script
only when there is none. Nothing is enabled or started.

    python tools/build_deb.py [--output DIR]
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import re
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = "hydra-umc-platform-base"
EPOCH = 0  # the same time stamp in every member: the package does not change with the clock

WRAPPER = """#!/usr/bin/env sh
export PYTHONPATH=/opt/hydra-umc/os-agent
exec /usr/bin/python3 -m hydra_umc_os.agent "$@"
"""


def read_text_lf(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n")


def package_version() -> str:
    manifest = json.loads((ROOT / "hydra-umc.project.json").read_text(encoding="utf-8"))
    version = manifest["version"]
    if not re.fullmatch(r"\d+(\.\d+){2,3}", version):
        raise SystemExit(f"the version {version!r} is not a valid package version")
    return version


def data_files() -> dict[str, tuple[bytes, int]]:
    """Path inside the package (without the leading slash) -> (content, mode)."""
    files: dict[str, tuple[bytes, int]] = {}
    agent_dir = ROOT / "agent" / "src" / "hydra_umc_os"
    for source in sorted(agent_dir.glob("*.py")):
        files[f"opt/hydra-umc/os-agent/hydra_umc_os/{source.name}"] = (read_text_lf(source), 0o644)
    files["opt/hydra-umc/os-agent/hydra-umc.project.json"] = (read_text_lf(ROOT / "hydra-umc.project.json"), 0o644)
    files["usr/bin/hydra-umc-agent"] = (WRAPPER.encode("utf-8"), 0o755)
    unit = read_text_lf(ROOT / "systemd" / "hydra-umc-agent.service").decode("utf-8")
    unit = unit.replace("/usr/local/bin/hydra-umc-agent", "/usr/bin/hydra-umc-agent")
    files["usr/lib/systemd/system/hydra-umc-agent.service"] = (unit.encode("utf-8"), 0o644)
    files["usr/share/hydra-umc/config/hydra-umc-os.example.json"] = (read_text_lf(ROOT / "config" / "hydra-umc-os.example.json"), 0o644)
    files["usr/share/hydra-umc/config/identity.example.json"] = (read_text_lf(ROOT / "config" / "identity.example.json"), 0o644)
    for profile in sorted((ROOT / "config" / "profiles").glob("*.json")):
        files[f"usr/share/hydra-umc/config/profiles/{profile.name}"] = (read_text_lf(profile), 0o644)
    files[f"usr/share/doc/{PACKAGE}/copyright"] = (read_text_lf(ROOT / "packages" / "debian" / "copyright"), 0o644)
    return files


def control_text(version: str, installed_kib: int) -> str:
    return (
        f"Package: {PACKAGE}\n"
        f"Version: {version}\n"
        "Section: admin\n"
        "Priority: optional\n"
        "Architecture: all\n"
        f"Installed-Size: {installed_kib}\n"
        "Maintainer: JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>\n"
        "Depends: python3 (>= 3.11), systemd, adduser\n"
        "Homepage: https://github.com/JuanenRac/HYDRA-UMC-OS\n"
        "Description: HYDRA-UMC-OS platform base\n"
        " Read-only identity and health agent for a HYDRA-UMC node, its default\n"
        " configuration and profiles, and the systemd unit that runs it. The unit is\n"
        " installed but not enabled: starting it is an explicit decision.\n"
    )


def _tar_member(name: str, content: bytes | None, mode: int, directory: bool = False) -> tuple[tarfile.TarInfo, io.BytesIO | None]:
    info = tarfile.TarInfo(name)
    info.uid = info.gid = 0
    info.uname = info.gname = "root"
    info.mtime = EPOCH
    if directory:
        info.type = tarfile.DIRTYPE
        info.mode = 0o755
        return info, None
    assert content is not None
    info.size = len(content)
    info.mode = mode
    return info, io.BytesIO(content)


def make_tar_gz(members: list[tuple[str, bytes, int]], directories: list[str] | None = None) -> bytes:
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", mtime=EPOCH, compresslevel=9) as gz:
        with tarfile.open(fileobj=gz, mode="w", format=tarfile.GNU_FORMAT) as tar:
            for directory in sorted(directories or []):
                info, _ = _tar_member(directory, None, 0o755, directory=True)
                tar.addfile(info)
            for name, content, mode in members:
                info, stream = _tar_member(name, content, mode)
                tar.addfile(info, stream)
    return buffer.getvalue()


def ar_archive(members: list[tuple[str, bytes]]) -> bytes:
    out = bytearray(b"!<arch>\n")
    for name, content in members:
        header = f"{name + '/':<16}{EPOCH:<12}{0:<6}{0:<6}{'100644':<8}{len(content):<10}`\n"
        assert len(header) == 60, header
        out += header.encode("ascii") + content
        if len(content) % 2:
            out += b"\n"
    return bytes(out)


def build(output: Path) -> Path:
    version = package_version()
    files = data_files()
    directories: set[str] = {"./"}
    for path in files:
        parts = path.split("/")[:-1]
        for index in range(1, len(parts) + 1):
            directories.add("./" + "/".join(parts[:index]) + "/")
    installed_kib = max(1, -(-sum(len(content) for content, _ in files.values()) // 1024))
    data = make_tar_gz([(f"./{path}", content, mode) for path, (content, mode) in sorted(files.items())], sorted(directories))
    md5sums = "".join(f"{hashlib.md5(content).hexdigest()}  {path}\n" for path, (content, _) in sorted(files.items()))
    scripts = {name: read_text_lf(ROOT / "packages" / "debian" / name) for name in ("postinst", "prerm", "postrm")}
    control_members = [
        ("./control", control_text(version, installed_kib).encode("utf-8"), 0o644),
        ("./md5sums", md5sums.encode("utf-8"), 0o644),
        *[(f"./{name}", content, 0o755) for name, content in scripts.items()],
    ]
    control = make_tar_gz(control_members, ["./"])
    archive = ar_archive([("debian-binary", b"2.0\n"), ("control.tar.gz", control), ("data.tar.gz", data)])
    output.mkdir(parents=True, exist_ok=True)
    target = output / f"{PACKAGE}_{version}_all.deb"
    target.write_bytes(archive)
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, default=ROOT / "build" / "deb")
    args = parser.parse_args(argv)
    target = build(args.output)
    print(f"DEB_BUILD=PASS {target} ({target.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
