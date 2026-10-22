#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - tools/package_component.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Pack one program of the CM5 as a signed release package, and check a package before anything installs it.

    python tools/package_component.py pack server --repo ../HYDRA-UMC-SERVER --out dist-packages
    python tools/package_component.py pack server --repo ../HYDRA-UMC-SERVER --out dist-packages --sign
    python tools/package_component.py verify dist-packages/hydra-server-0.8.1.0.tgz
    python tools/package_component.py sign   dist-packages/hydra-server-0.8.1.0.tgz
    python tools/package_component.py publish server --repo ../HYDRA-UMC-SERVER --out dist-packages

A package is `hydra-<component>-<version>.tgz`, its hash `hydra-<component>-<version>.tgz.sha256` and its signature `hydra-<component>-<version>.tgz.sig`: the Ed25519 signature, by
the key of the releases, of the text `hydra-pkg/1|<component>|<version>|<sha256>`. Binding the component and the version to the hash means a signed package of one program, or of an
older version, cannot be presented as another one or as the newest.

* The key is never in a repository. The signer reads it from `HYDRA_RELEASE_KEY` (a path) or `~/.hydra-umc-keys/hydra_release_ed25519.pem` and checks that it is the key this
  repository trusts (`config/release_key.pub`, the same 64 hexadecimal digits as `contracts/trust/release_key.pub` of the SDK) before it writes a signature: a signature by any other
  key is never written.
* `verify` is what the installer must run: it recomputes the hash, compares it with the `.sha256`, checks the signature against the trusted key, and refuses a package whose name,
  member paths or member types are not what a package of this kind holds. It exits 0 only when every check passes.
* Ed25519 is implemented here in pure Python (RFC 8032) because the standard library has none; it is checked against the RFC's own test vectors by `tools/verify_package_component.py`.
* `publish` needs the GitHub CLI signed in and refuses an unsigned package.

Standard library only.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import tarfile
from pathlib import Path

OWNER = "JuanenRac"
SKIP_PARTS = {"__pycache__", ".pytest_cache", ".git", "node_modules"}
SKIP_SUFFIXES = (".pyc", ".map")
TRUST_FILE = Path(__file__).resolve().parent.parent / "config" / "release_key.pub"
MESSAGE_PREFIX = "hydra-pkg/1"
NAME_PATTERN = re.compile(r"^hydra-([a-z][a-z0-9-]*)-(\d+\.\d+\.\d+(?:\.\d+)?)\.tgz$")

# component -> (repository, [(path in the repository, path in the package)], what must be there before packing)
LAYOUT: dict[str, tuple[str, list[tuple[str, str]], list[str]]] = {
    "server": (
        "HYDRA-UMC-SERVER",
        [("dist", "dist"), ("public", "public"), ("package.json", "package.json"), ("package-lock.json", "package-lock.json"), ("systemd/hydra-umc-server.service", "systemd/hydra-umc-server.service")],
        ["dist/server.cjs", "public", "package.json", "package-lock.json"],
    ),
    "studio": ("HYDRA-UMC-STUDIO", [("dist", "dist")], ["dist/index.html"]),
    "os-agent": ("HYDRA-UMC-OS", [("agent/src/hydra_umc_os", "agent/src/hydra_umc_os"), ("agent/pyproject.toml", "agent/pyproject.toml")], ["agent/src/hydra_umc_os/agent.py"]),
}

# ---- Ed25519 (RFC 8032), pure Python ----------------------------------------------------------------------------------------------------------------------------------------
_P = 2**255 - 19
_Q = 2**252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P
_I = pow(2, (_P - 1) // 4, _P)
Point = tuple[int, int, int, int]


def _recover_x(y: int, sign: int) -> int | None:
    if y >= _P:
        return None
    x2 = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P) % _P
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P:
        x = x * _I % _P
    if (x * x - x2) % _P:
        return None
    return _P - x if (x & 1) != sign else x


_BASE_Y = 4 * pow(5, _P - 2, _P) % _P
_BASE_X = _recover_x(_BASE_Y, 0) or 0
_BASE: Point = (_BASE_X, _BASE_Y, 1, _BASE_X * _BASE_Y % _P)


def _add(a: Point, b: Point) -> Point:
    aa, bb = (a[1] - a[0]) * (b[1] - b[0]) % _P, (a[1] + a[0]) * (b[1] + b[0]) % _P
    cc, dd = 2 * a[3] * b[3] * _D % _P, 2 * a[2] * b[2] % _P
    e, f, g, h = bb - aa, dd - cc, dd + cc, bb + aa
    return e * f % _P, g * h % _P, f * g % _P, e * h % _P


def _multiply(scalar: int, point: Point) -> Point:
    result: Point = (0, 1, 1, 0)
    while scalar:
        if scalar & 1:
            result = _add(result, point)
        point = _add(point, point)
        scalar >>= 1
    return result


def _encode(point: Point) -> bytes:
    zinv = pow(point[2], _P - 2, _P)
    x, y = point[0] * zinv % _P, point[1] * zinv % _P
    return (y | ((x & 1) << 255)).to_bytes(32, "little")


def _decode(data: bytes) -> Point | None:
    number = int.from_bytes(data, "little")
    y, sign = number & ((1 << 255) - 1), number >> 255
    x = _recover_x(y, sign)
    return None if x is None else (x, y, 1, x * y % _P)


def _expand(seed: bytes) -> tuple[int, bytes]:
    digest = hashlib.sha512(seed).digest()
    scalar = int.from_bytes(digest[:32], "little")
    scalar &= (1 << 254) - 8
    scalar |= 1 << 254
    return scalar, digest[32:]


def ed25519_public_key(seed: bytes) -> bytes:
    scalar, _prefix = _expand(seed)
    return _encode(_multiply(scalar, _BASE))


def ed25519_sign(seed: bytes, message: bytes) -> bytes:
    scalar, prefix = _expand(seed)
    public = _encode(_multiply(scalar, _BASE))
    r = int.from_bytes(hashlib.sha512(prefix + message).digest(), "little") % _Q
    point_r = _encode(_multiply(r, _BASE))
    k = int.from_bytes(hashlib.sha512(point_r + public + message).digest(), "little") % _Q
    return point_r + ((r + k * scalar) % _Q).to_bytes(32, "little")


def ed25519_verify(public_key: bytes, message: bytes, signature: bytes) -> bool:
    """True only for a valid Ed25519 signature of `message` by `public_key`."""
    if len(public_key) != 32 or len(signature) != 64:
        return False
    point_a, point_r = _decode(public_key), _decode(signature[:32])
    scalar = int.from_bytes(signature[32:], "little")
    if point_a is None or point_r is None or scalar >= _Q:
        return False
    k = int.from_bytes(hashlib.sha512(signature[:32] + public_key + message).digest(), "little") % _Q
    return _encode(_multiply(scalar, _BASE)) == _encode(_add(point_r, _multiply(k, point_a)))


# ---- the key and the signed text ----------------------------------------------------------------------------------------------------------------------------------------------
def trusted_key(trust_file: Path | None = None) -> str:
    """The public key this repository trusts: 64 lowercase hexadecimal digits in config/release_key.pub."""
    path = trust_file or TRUST_FILE
    text = path.read_text(encoding="ascii").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", text):
        raise SystemExit(f"{path.name} does not hold a public key of 64 hexadecimal digits")
    return text


def seed_from_pem(pem: str) -> bytes:
    """The 32-byte seed of an Ed25519 private key in PKCS#8 PEM (the format `openssl genpkey -algorithm ed25519` writes)."""
    body = "".join(line for line in pem.strip().splitlines() if not line.startswith("-----"))
    der = base64.b64decode(body)
    if len(der) != 48 or not der.startswith(bytes.fromhex("302e020100300506032b657004220420")):
        raise SystemExit("the key file is not an unencrypted Ed25519 private key (PKCS#8)")
    return der[16:]


def key_path() -> Path:
    given = os.environ.get("HYDRA_RELEASE_KEY")
    return Path(given) if given else Path.home() / ".hydra-umc-keys" / "hydra_release_ed25519.pem"


def package_message(component: str, version: str, sha256_hex: str) -> bytes:
    for part in (component, version):
        if not part or re.search(r"[|\s]", part):
            raise ValueError("a part of the signed text cannot be empty or hold a space or a '|'")
    if not re.fullmatch(r"[0-9a-f]{64}", sha256_hex):
        raise ValueError("the hash must be 64 lowercase hexadecimal digits")
    return f"{MESSAGE_PREFIX}|{component}|{version}|{sha256_hex}".encode("utf-8")


def signature_ok(component: str, version: str, sha256_hex: str, signature_text: str, public_key_hex: str) -> bool:
    text = signature_text.strip()
    if not re.fullmatch(r"[0-9a-fA-F]{128}", text):
        return False
    try:
        message = package_message(component, version, sha256_hex)
    except ValueError:
        return False
    return ed25519_verify(bytes.fromhex(public_key_hex), message, bytes.fromhex(text))


# ---- packing -------------------------------------------------------------------------------------------------------------------------------------------------------------------------
def version_of(repo: Path) -> str:
    manifest = json.loads((repo / "hydra-umc.project.json").read_text(encoding="utf-8"))
    version = str(manifest["version"])
    if not re.fullmatch(r"\d+\.\d+\.\d+(\.\d+)?", version):
        raise SystemExit(f"{repo.name}: the version {version!r} is not one of the family's")
    return version


def files_under(root: Path):
    for path in sorted(root.rglob("*")):
        if path.is_file() and not (set(path.relative_to(root).parts) & SKIP_PARTS) and not path.name.endswith(SKIP_SUFFIXES):
            yield path


def build(component: str, repo: Path, out: Path) -> tuple[Path, str, str]:
    """Write the package and its .sha256; return (package, version, sha256)."""
    if component not in LAYOUT:
        raise SystemExit(f"unknown component {component!r}; known: {', '.join(sorted(LAYOUT))}")
    name, parts, required = LAYOUT[component]
    if repo.name != name:
        raise SystemExit(f"{component} is {name}, not {repo.name}")
    missing = [item for item in required if not (repo / item).exists()]
    if missing:
        raise SystemExit(f"{name} is not ready to pack (build it first): missing {', '.join(missing)}")
    version = version_of(repo)
    out.mkdir(parents=True, exist_ok=True)
    package = out / f"hydra-{component}-{version}.tgz"
    with tarfile.open(package, "w:gz") as tar:
        def add(path: Path, arcname: str) -> None:
            info = tar.gettarinfo(str(path), arcname)
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mode = 0o755 if info.mode & 0o111 else 0o644
            with open(path, "rb") as handle:
                tar.addfile(info, handle)

        for source, target in parts:
            path = repo / source
            if path.is_dir():
                for item in files_under(path):
                    add(item, f"{target}/{item.relative_to(path).as_posix()}")
            elif path.is_file():
                add(path, target)
    digest = hashlib.sha256(package.read_bytes()).hexdigest()
    (out / (package.name + ".sha256")).write_text(f"{digest}  {package.name}\n", encoding="utf-8", newline="\n")
    return package, version, digest


def sign_package(package: Path, signing_seed: bytes | None = None, trust_file: Path | None = None) -> Path:
    """Write <package>.sig. Refuses a key that is not the trusted one, and a package whose name or .sha256 does not match its bytes."""
    match = NAME_PATTERN.match(package.name)
    if not match:
        raise SystemExit(f"{package.name} is not a package named hydra-<component>-<version>.tgz")
    component, version = match.groups()
    digest = hashlib.sha256(package.read_bytes()).hexdigest()
    sha_file = package.parent / (package.name + ".sha256")
    if sha_file.is_file() and not sha_file.read_text(encoding="utf-8").lower().startswith(digest):
        raise SystemExit("the .sha256 next to the package is not the hash of this file")
    if signing_seed is None:
        path = key_path()
        if not path.is_file():
            raise SystemExit(f"there is no signing key at {path} (HYDRA_RELEASE_KEY names another place)")
        signing_seed = seed_from_pem(path.read_text(encoding="ascii"))
    if ed25519_public_key(signing_seed).hex() != trusted_key(trust_file):
        raise SystemExit("the key that would sign is not the one this repository trusts: the installer would refuse the package")
    signature = ed25519_sign(signing_seed, package_message(component, version, digest))
    target = package.parent / (package.name + ".sig")
    target.write_text(signature.hex() + "\n", encoding="ascii", newline="\n")
    return target


class PackageRefused(Exception):
    """A package that must not be installed; the message says why."""


def verify_package(package: Path, public_key_hex: str | None = None) -> tuple[str, str, str]:
    """Return (component, version, sha256) for a package that passes every check; raise PackageRefused otherwise."""
    match = NAME_PATTERN.match(package.name)
    if not match:
        raise PackageRefused(f"{package.name} is not named hydra-<component>-<version>.tgz")
    component, version = match.groups()
    if component not in LAYOUT:
        raise PackageRefused(f"{component} is not a component of the CM5")
    try:
        data = package.read_bytes()
    except OSError as error:
        raise PackageRefused(f"the package cannot be read: {error}") from error
    digest = hashlib.sha256(data).hexdigest()
    sha_file = package.parent / (package.name + ".sha256")
    sig_file = package.parent / (package.name + ".sig")
    if not sha_file.is_file():
        raise PackageRefused("the .sha256 is missing")
    if not sha_file.read_text(encoding="utf-8").strip().lower().startswith(digest):
        raise PackageRefused("the hash does not match the package: it was changed after it was published")
    if not sig_file.is_file():
        raise PackageRefused("the .sig is missing: an unsigned package is never installed")
    key = public_key_hex or trusted_key()
    if not signature_ok(component, version, digest, sig_file.read_text(encoding="ascii"), key):
        raise PackageRefused("the signature is not valid for this component, this version and this hash")
    check_members(package, component)
    return component, version, digest


def check_members(package: Path, component: str) -> None:
    """Only regular files and directories, only paths below the layout of the component: nothing can be written outside the target."""
    allowed = tuple(target for _source, target in LAYOUT[component][1])
    try:
        with tarfile.open(package, "r:gz") as tar:
            for member in tar.getmembers():
                name = member.name
                if member.isdir():
                    continue
                if not member.isreg():
                    raise PackageRefused(f"{name} is not a regular file")
                if name.startswith(("/", "\\")) or ".." in Path(name).parts or "\\" in name or re.match(r"^[A-Za-z]:", name):
                    raise PackageRefused(f"{name} would be written outside the target")
                if not any(name == target or name.startswith(target + "/") for target in allowed):
                    raise PackageRefused(f"{name} is not part of a {component} package")
    except (tarfile.TarError, OSError, EOFError) as error:
        raise PackageRefused(f"the archive cannot be read: {error}") from error


def publish(component: str, repo: Path, package: Path, version: str) -> None:
    signature = package.parent / (package.name + ".sig")
    if not signature.is_file():
        raise SystemExit("not publishing an unsigned package: the installer would refuse it")
    verify_package(package)
    repo_name = f"{OWNER}/{LAYOUT[component][0]}"
    assets = [str(package), str(package) + ".sha256", str(signature)]
    exists = subprocess.run(["gh", "release", "view", f"v{version}", "-R", repo_name], capture_output=True, text=True, check=False).returncode == 0
    if exists:
        subprocess.run(["gh", "release", "upload", f"v{version}", *assets, "--clobber", "-R", repo_name], check=True)
    else:
        raise SystemExit(f"v{version} has no release in {repo_name}: create the release first, then publish uploads the package to it")
    print(f"published {repo_name} v{version}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("pack", "publish"):
        sub = commands.add_parser(name)
        sub.add_argument("component", choices=sorted(LAYOUT))
        sub.add_argument("--repo", required=True)
        sub.add_argument("--out", default="dist-packages")
        if name == "pack":
            sub.add_argument("--sign", action="store_true", help="also write the .sig (needs the key of the releases)")
    for name in ("verify", "sign"):
        commands.add_parser(name).add_argument("package")
    arguments = parser.parse_args(argv)
    if arguments.command == "verify":
        try:
            component, version, digest = verify_package(Path(arguments.package).resolve())
        except PackageRefused as error:
            print(f"PACKAGE=REFUSED {error}", file=sys.stderr)
            return 1
        print(f"PACKAGE=OK {component} {version} {digest}")
        return 0
    if arguments.command == "sign":
        print(sign_package(Path(arguments.package).resolve()).name + "  signed")
        return 0
    repo, out = Path(arguments.repo).resolve(), Path(arguments.out).resolve()
    package, version, digest = build(arguments.component, repo, out)
    print(f"{package.name}  {digest}")
    if arguments.command == "pack" and arguments.sign:
        print(sign_package(package).name + "  signed")
    if arguments.command == "publish":
        sign_package(package)
        publish(arguments.component, repo, package, version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
