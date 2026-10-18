#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - Generate the secrets of a deployment env file (no example value survives)
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""A deployment template carries example values (`JWT_SECRET=SET_LOCALLY_TO_A_LONG_RANDOM_VALUE`) so that nobody has to guess the variable names. A server that starts with them as
they stand lets anybody who has read the template forge an administrator's token or sign in with the example password.

This script fills every placeholder of an env file with a random value of its own, and refuses (`--check`) a file in which one is left or in which a secret is too short:

* a variable whose name contains PASSWORD gets 24 URL-safe characters; any other secret (SECRET, TOKEN, KEY) gets 64 hex characters;
* a value that is not a placeholder is never touched (the operator's own choice stays);
* `--adopt KEY=OTHER_FILE:OTHER_KEY` uses the real (not placeholder) value that another env file already has for OTHER_KEY instead of generating one for KEY (the order of the installers does not matter);
* `--mirror KEY=OTHER_FILE:OTHER_KEY` writes the value of KEY into another env file too when that one still has a placeholder (the voice relay token is the same in two files);
* the generated bootstrap administrator password is printed once (it is also in the file, which is 0600 root: remove the variable after the first start, as the template says).

Dry-run by default; `--apply` writes. Standard library only.
"""
from __future__ import annotations

import argparse
import os
import re
import secrets
import shutil
import stat
import sys
import tempfile
from pathlib import Path

PLACEHOLDER = re.compile(r"(set[_ -]?locally|change[_ -]?me|replace[_ -]?me|your[_ -]?(secret|password)|example|placeholder|remove[_ -]?after|hydra_industrial_secret|hydraumc-setup)", re.IGNORECASE)
LINE = re.compile(r"^(?P<key>[A-Za-z_][A-Za-z0-9_]*)=(?P<value>.*)$")
SECRET_NAME = re.compile(r"(SECRET|TOKEN|PASSWORD|KEY)", re.IGNORECASE)
MIN_SECRET_LENGTH = 32
MIN_PASSWORD_LENGTH = 12
ADMIN_PASSWORD_KEY = "HYDRA_UMC_BOOTSTRAP_ADMIN_PASSWORD"


def is_placeholder(value: str) -> bool:
    return bool(PLACEHOLDER.search(value))


def new_value(key: str) -> str:
    if "PASSWORD" in key.upper():
        return secrets.token_urlsafe(18)  # 24 URL-safe characters
    return secrets.token_hex(32)


def parse(text: str) -> list[tuple[int, str, str]]:
    """(line index, key, value) of every active KEY=VALUE line (comments and blank lines are skipped)."""
    found = []
    for index, line in enumerate(text.split("\n")):
        if line.lstrip().startswith("#"):
            continue
        match = LINE.match(line)
        if match:
            found.append((index, match.group("key"), match.group("value").strip()))
    return found


def problems(text: str) -> list[str]:
    """Why this env file must not be used (empty when it is fine)."""
    out = []
    for _, key, value in parse(text):
        if not SECRET_NAME.search(key):
            continue
        if not value and key.upper() in ("JWT_SECRET", "GATEWAY_JWT_SECRET"):
            out.append(f"{key} is empty")
        elif is_placeholder(value):
            out.append(f"{key} is still an example value")
        elif value and "PASSWORD" in key.upper() and len(value) < MIN_PASSWORD_LENGTH:
            out.append(f"{key} has fewer than {MIN_PASSWORD_LENGTH} characters")
        elif value and key.upper() in ("JWT_SECRET", "GATEWAY_JWT_SECRET") and len(value) < MIN_SECRET_LENGTH:
            out.append(f"{key} has fewer than {MIN_SECRET_LENGTH} characters")
    return out


def fill(text: str, mirrored: dict[str, str] | None = None) -> tuple[str, dict[str, str]]:
    """The text with every placeholder replaced, and the values that were generated (key -> value)."""
    lines = text.split("\n")
    generated: dict[str, str] = {}
    for index, key, value in parse(text):
        if SECRET_NAME.search(key) and is_placeholder(value):
            chosen = (mirrored or {}).get(key) or new_value(key)
            lines[index] = f"{key}={chosen}"
            generated[key] = chosen
    return "\n".join(lines), generated


def write_private(path: Path, text: str) -> None:
    """Atomic write, mode 0600 (the group is set by the installer that owns the file)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=str(path.parent), prefix=".secrets-")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        os.chmod(temporary, stat.S_IRUSR | stat.S_IWUSR)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("env_file")
    parser.add_argument("--create-from", help="copy this example file first when env_file does not exist")
    parser.add_argument("--check", action="store_true", help="only verify: exit 1 listing every example value or weak secret")
    parser.add_argument("--mirror", action="append", default=[], metavar="KEY=OTHER_FILE:OTHER_KEY", help="also write the value of KEY into another env file that still has a placeholder")
    parser.add_argument("--adopt", action="append", default=[], metavar="KEY=OTHER_FILE:OTHER_KEY", help="use the real value another env file already has instead of generating one")
    parser.add_argument("--apply", action="store_true", help="write the changes (default: dry run)")
    args = parser.parse_args(argv)

    path = Path(args.env_file)
    if args.check:
        if not path.exists():
            print(f"SECRETS_CHECK=FAIL {path} does not exist", file=sys.stderr)
            return 1
        found = problems(path.read_text(encoding="utf-8"))
        if found:
            for item in found:
                print(f"SECRETS_CHECK=FAIL {path}: {item}", file=sys.stderr)
            return 1
        print(f"SECRETS_CHECK=PASS {path}")
        return 0

    if not path.exists():
        if not args.create_from:
            print(f"{path} does not exist (use --create-from EXAMPLE)", file=sys.stderr)
            return 2
        text = Path(args.create_from).read_text(encoding="utf-8")
    else:
        text = path.read_text(encoding="utf-8")
    adopted: dict[str, str] = {}
    for spec in args.adopt:
        key, _, target = spec.partition("=")
        other_file, _, other_key = target.rpartition(":")
        if Path(other_file).exists():
            for _, found_key, found_value in parse(Path(other_file).read_text(encoding="utf-8")):
                if found_key == other_key and found_value and not is_placeholder(found_value):
                    adopted[key] = found_value
    new_text, generated = fill(text, adopted)

    if not generated and path.exists():
        print(f"SECRETS=UNCHANGED {path}: no example value to replace")
        return 0
    names = ", ".join(sorted(generated)) or "(none)"
    if not args.apply:
        print(f"[dry-run] would {'create' if not path.exists() else 'update'} {path} and generate: {names}")
        return 0

    write_private(path, new_text)
    print(f"SECRETS=GENERATED {path}: {names}")
    for spec in args.mirror:
        key, _, target = spec.partition("=")
        other_file, _, other_key = target.rpartition(":")
        other = Path(other_file)
        if key not in generated or not other.exists():
            continue
        mirrored_text, mirrored_values = fill(other.read_text(encoding="utf-8"), {other_key: generated[key]})
        if other_key in mirrored_values:
            before = os.stat(other)
            write_private(other, mirrored_text)
            # the destination keeps the owner, group and mode it had (for example
            # root:hydra-umc-voice-ui 0640), not those of the freshly written file
            os.chmod(other, before.st_mode & 0o7777)
            if hasattr(os, "chown"):
                try:
                    os.chown(other, before.st_uid, before.st_gid)
                except PermissionError:
                    pass
            print(f"SECRETS=MIRRORED {key} -> {other}:{other_key}")
    if ADMIN_PASSWORD_KEY in generated:
        print("")
        print("  First administrator (shown ONCE - it is also in the root-only env file; remove the variable after the first start):")
        print(f"    password: {generated[ADMIN_PASSWORD_KEY]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
