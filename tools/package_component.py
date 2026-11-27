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
import gzip
import hashlib
import io
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

# component -> (repository, [(path in the repository, path in the package)], what must be there before packing). Every package carries `hydra-umc.project.json`
# (the fleet update reads the installed version from it) and `hydra-install.json` (what the root helper does with it; see `install_spec`).
# `package/` is what the build in GitHub Actions leaves (the arm64 program, the built web page, the libraries of Python), never a file of the repository.
Entry = tuple[str, list[tuple[str, str]], list[str]]
MANIFEST = "hydra-umc.project.json"
SPEC_NAME = "hydra-install.json"
SPEC_FORMAT = "hydra-install/1"


def _entry(repository: str, parts: list[tuple[str, str]], units: tuple[str, ...] = ()) -> Entry:
    parts = [*parts, *((f"systemd/{unit}", f"systemd/{unit}") for unit in units), (MANIFEST, MANIFEST)]
    return repository, parts, [source for source, _target in parts]


def _python(name: str, units: tuple[str, ...] | None = None, *extra: tuple[str, str]) -> Entry:
    return _entry("HYDRA-UMC-" + name.upper(), [("src", "src"), *extra], (f"hydra-umc-{name}.service",) if units is None else units)


def _binary(name: str, program: str = "") -> Entry:
    program = program or f"hydra-umc-{name}"
    return _entry("HYDRA-UMC-" + name.upper(), [(f"package/{program}", program)], (f"hydra-umc-{name}.service",))


_PYDEPS = ("package/pydeps", "pydeps")
_WORKSPACE = ("package/workspace", "workspace")
_DATALAKE_UNITS = tuple(f"hydra-umc-datalake{suffix}" for suffix in (".service", "-downsample.service", "-downsample.timer", "-retention.service", "-retention.timer"))

LAYOUT: dict[str, Entry] = {
    # the libraries travel with the program: the device installs nothing from the network (`npm ci --omit=dev` runs where the package is built)
    "server": _entry("HYDRA-UMC-SERVER", [("dist", "dist"), ("public", "public"), ("package.json", "package.json"), ("package-lock.json", "package-lock.json"), ("node_modules", "node_modules")],
                     ("hydra-umc-server.service",)),
    "studio": _entry("HYDRA-UMC-STUDIO", [("dist", "dist")]),
    # the agent runs with PYTHONPATH=<its folder>, so `hydra_umc_os/` is at the root of the package, where install_local_agent.sh puts it
    "os-agent": ("HYDRA-UMC-OS", [("agent/src/hydra_umc_os", "hydra_umc_os"), ("agent/pyproject.toml", "pyproject.toml"), ("systemd/hydra-umc-agent.service", "systemd/hydra-umc-agent.service"), (MANIFEST, MANIFEST)],
                 ["agent/src/hydra_umc_os/agent.py", "systemd/hydra-umc-agent.service", MANIFEST]),
    "twin": _entry("HYDRA-UMC-TWIN", [("package/hydra-umc-twin", "hydra-umc-twin"), _WORKSPACE], ("hydra-umc-twin.service",)),
    "orchestrator": _binary("orchestrator"),
    "hil-bridge": _binary("hil-bridge"),
    "swarm-sync": _binary("swarm-sync"),
    "job-dispatcher": _binary("job-dispatcher"),
    "node-healing": _binary("node-healing"),
    "telemetry-collector": _binary("telemetry-collector", "telemetry-collector"),
    "anomaly-detector": _python("anomaly-detector", None, _PYDEPS),
    "cognitive-node": _python("cognitive-node", None, _WORKSPACE),
    "dashboard-ai": _entry("HYDRA-UMC-DASHBOARD-AI", [("package/dist", "dist"), ("scripts/serve_static.py", "serve_static.py")], ("hydra-umc-dashboard-ai.service",)),
    "datalake": _python("datalake", _DATALAKE_UNITS, ("systemd/hydra-umc-datalake-downsample.sh", "bin/downsample.sh")),
    "detection-hef": _python("detection-hef"),
    "docs-qa": _python("docs-qa", None, ("README.md", "README.md"), ("CHANGELOG.md", "CHANGELOG.md")),
    "local-technician": _python("local-technician", (), ("contracts", "contracts")),
    "production-reports": _python("production-reports", None, _PYDEPS),
    "safety-zones": _python("safety-zones"),
    "semantic-planner": _python("semantic-planner", None, ("configs", "configs"), _PYDEPS),
    "vision-node": _python("vision-node", None, _WORKSPACE),
    "vision-streamer": _python("vision-streamer", ("hydra-umc-vision-streamer@.service",)),
    "visual-servoing-api": _python("visual-servoing-api"),
    "vla-engine": _python("vla-engine"),
    "voice-ui": _python("voice-ui", None, ("deploy", "deploy")),
}


def _read(relative: str) -> dict:
    return json.loads((Path(__file__).resolve().parent.parent / relative).read_text(encoding="utf-8"))


def install_spec(component: str, version: str) -> dict:
    """What the root helper of the device does with a package, from the install plan and `config/package_install.json` of this repository. It is written inside the
    package, so it is covered by the signature, and the device needs neither of those two files."""
    config = _read("config/package_install.json")
    generation = _read("config/installer_generation.json")
    own = config["components"].get(component, {})
    row = next((r for r in _read("provisioning/install_plan.json")["installers"] if str(r.get("target") or "").rsplit("/", 1)[-1] == component), {})
    units = list(own.get("units", row.get("units") or []))
    main = own["mainUnit"] if "mainUnit" in own else row.get("unit") or (units[0] if units else None)
    target = f"/opt/hydra-umc/{component}"
    pydeps = component in config["pythonDependencies"]
    dropins: dict[str, str] = {}
    if main and component in generation.get("health_open", []):
        dropins[f"{main}.d/10-health-open.conf"] = "[Service]\nEnvironment=HYDRA_UMC_" + component.upper().replace("-", "_") + "_HEALTH_OPEN=1\n"
    if main and pydeps:
        dropins[f"{main}.d/20-pydeps.conf"] = f"[Service]\nEnvironment=PYTHONPATH={target}/src:{target}/pydeps:/opt/hydra-umc/sdk-python\n"
    user_dirs, root_dirs = list(row.get("user_dirs") or []), list(own.get("rootDirs", []))
    health = {"port": row["port"], "path": row["health_path"]} if row.get("port") and row.get("health_path") else None
    return {"format": SPEC_FORMAT, "component": component, "version": version, "units": units, "mainUnit": main, "dropins": dropins,
            "user": own.get("user", row.get("user")), "homeInData": component in generation.get("home_in_data", []), "userDirs": user_dirs,
            "stateDirs": user_dirs + root_dirs, "health": health, "python": config["python"] if pydeps else None,
            "needsFiles": own.get("needsFiles", []), "createIfMissing": own.get("createIfMissing", []), "wrappers": own.get("wrappers", []),
            "aptPackages": own.get("aptPackages", [])}


# what proves that a build or a checkout is complete, beyond the sources themselves being there
for _component, (_repository, _parts, _required) in LAYOUT.items():
    if _parts[0] == ("src", "src"):
        _required.append("src/hydra_umc_" + _component.replace("-", "_"))
LAYOUT["server"][2].append("dist/server.cjs")
LAYOUT["studio"][2].append("dist/index.html")


def spec_bytes(component: str, version: str) -> bytes:
    return (json.dumps(install_spec(component, version), indent=2, sort_keys=True) + "\n").encode("utf-8")


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
    # Inside the libraries of Node a nested `node_modules` is part of a library, so only the command links of `.bin` (links are refused by `verify`) are left out.
    libraries = root.name == "node_modules"
    skipped = {".bin"} if libraries else SKIP_PARTS
    for path in sorted(root.rglob("*")):
        if path.is_file() and not (set(path.relative_to(root).parts) & skipped) and not path.name.endswith(SKIP_SUFFIXES):
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
    # the same files always give the same bytes: the times are one fixed instant (SOURCE_DATE_EPOCH, 0 by default), members are added in sorted order and the gzip header holds no name or time of its own
    epoch = int(os.environ.get("SOURCE_DATE_EPOCH", "0"))
    with open(package, "wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=epoch) as compressed, tarfile.open(fileobj=compressed, mode="w", format=tarfile.GNU_FORMAT) as tar:
        def add(path: Path, arcname: str) -> None:
            info = tar.gettarinfo(str(path), arcname)
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mtime = epoch
            # what runs is executable whatever the machine that packs it says: the programs of the build and the scripts of bin/
            info.mode = 0o755 if info.mode & 0o111 or arcname.startswith("bin/") or arcname in (component, f"hydra-umc-{component}") else 0o644
            with open(path, "rb") as handle:
                tar.addfile(info, handle)

        for source, target in parts:
            path = repo / source
            if path.is_dir():
                for item in files_under(path):
                    add(item, f"{target}/{item.relative_to(path).as_posix()}")
            elif path.is_file():
                add(path, target)
        generated = spec_bytes(component, version)
        info = tarfile.TarInfo(SPEC_NAME)
        info.size, info.mtime, info.mode = len(generated), epoch, 0o644
        tar.addfile(info, io.BytesIO(generated))
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
    return verify_package_bytes(package, public_key_hex)[:3]


def verify_package_bytes(package: Path, public_key_hex: str | None = None) -> tuple[str, str, str, bytes]:
    """Like verify_package, and also returns the bytes that were verified: whoever installs the package must open the archive from these, not read the file again."""
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
    check_members(package, component, data)
    return component, version, digest, data


def check_members(package: Path, component: str, data: bytes | None = None) -> None:
    """Only regular files and directories, only paths below the layout of the component: nothing can be written outside the target.
    With `data` the archive is read from those bytes (the ones whose hash and signature were checked) and the file is not opened."""
    allowed = (*(target for _source, target in LAYOUT[component][1]), SPEC_NAME)
    try:
        with tarfile.open(package, "r:gz") if data is None else tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            for member in tar.getmembers():
                name = member.name
                if not member.isdir() and not member.isreg():
                    raise PackageRefused(f"{name} is not a regular file")
                # A folder is held to the same path rule as a file: its path decides where it is created.
                if name.startswith(("/", "\\")) or ".." in Path(name).parts or "\\" in name or re.match(r"^[A-Za-z]:", name):
                    raise PackageRefused(f"{name} would be written outside the target")
                if member.isdir():
                    continue
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
