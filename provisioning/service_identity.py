#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - Give a service the key to verify the signed tokens of HYDRA-UMC-SERVER (off until asked)
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""HYDRA-UMC-SERVER is the one issuer of identity of the family. A service that carries `server_identity.py` of the SDK can verify the signed token the server issues at login
instead of keeping a token of its own, once the operator names the signing key of the server with `--identity-key-file` (or the environment variable of the service).

This script is the single place that distributes that key and turns the switch on:

* `--enable NAME ...` writes `<directory>/<name>-identity.key` (the `JWT_SECRET` of the server env file, mode 0640, group of the service when this runs as root and the group exists)
  and a systemd drop-in `<unit>.service.d/20-server-identity.conf` that sets the environment variable of the service to that file. The service then accepts a valid token of the
  server and refuses a request with no credential, even on loopback; restart the unit afterwards.
* `--disable NAME ...` renames the drop-in to `.conf.off` (the switch is off; the key file stays, remove it by hand when the service no longer needs it).
* `--status` says, for every service of `config/service_identity.json`, whether the switch is on.

Nothing is on unless an operator runs `--enable`: the default of every service is its own token or none. The secret is never printed. A server env file whose `JWT_SECRET` is
missing, still an example value or shorter than the minimum is refused (run `generate_secrets.py` first). The services, their units, groups and variables are in
`config/service_identity.json`, not in this script. Dry-run by default; `--apply` writes. Standard library only.

The signature of the token is symmetric: a service that can verify a token could also forge one, so the key file is readable only by the group of that service.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import generate_secrets  # noqa: E402 - the sibling module, found next to this file

DEFAULT_CONFIG = HERE.parent / "config" / "service_identity.json"
NAME = re.compile(r"^[a-z][a-z0-9-]{0,40}$")


def load_config(path: Path) -> dict:
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("format") != "hydra-service-identity/1":
        raise ValueError(f"{path}: unknown format")
    for name, entry in config["services"].items():
        if not NAME.match(name) or not all(entry.get(key) for key in ("unit", "environment", "group")):
            raise ValueError(f"{path}: the service {name!r} needs a unit, an environment variable and a group")
    return config


def server_secret(env_file: Path, variable: str, minimum: int) -> str:
    """The real signing key of the server, or ValueError saying why there is none (the message never holds the value)."""
    if not env_file.is_file():
        raise ValueError(f"{env_file} does not exist")
    for _, key, value in generate_secrets.parse(env_file.read_text(encoding="utf-8")):
        if key == variable:
            if not value:
                raise ValueError(f"{variable} is empty in {env_file}")
            if generate_secrets.is_placeholder(value):
                raise ValueError(f"{variable} is still an example value in {env_file}: run generate_secrets.py first")
            if len(value) < minimum:
                raise ValueError(f"{variable} has fewer than {minimum} characters in {env_file}")
            return value
    raise ValueError(f"{env_file} has no {variable}")


def write_private(path: Path, text: str, mode: int, group: str | None) -> None:
    """Atomic write with the final mode; the group is set when running as root and it exists."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=str(path.parent), prefix=".identity-")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        os.chmod(temporary, mode)
        if group and hasattr(os, "chown") and os.geteuid() == 0:
            try:
                import grp

                os.chown(temporary, 0, grp.getgrnam(group).gr_gid)
            except KeyError:
                print(f"IDENTITY=NOTE the group {group} does not exist yet: {path} stays root only until it does", file=sys.stderr)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def dropin_path(config: dict, entry: dict) -> Path:
    return Path(config["systemd_directory"]) / f"{entry['unit']}.d" / config["dropin_name"]


def key_path(config: dict, name: str) -> Path:
    return Path(config["directory"]) / f"{name}-identity.key"


def dropin_text(entry: dict, key_file: Path) -> str:
    return f"[Service]\nEnvironment={entry['environment']}={key_file}\n"


def status(config: dict) -> dict[str, bool]:
    return {name: dropin_path(config, entry).is_file() for name, entry in config["services"].items()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="the services that can take the identity of the server (default: config/service_identity.json)")
    parser.add_argument("--directory", help="where the key files go (default: the directory of the configuration)")
    parser.add_argument("--systemd-directory", help="where the unit drop-ins go (default: the one of the configuration)")
    parser.add_argument("--server-env", help="the env file of the server that holds the signing key (default: the one of the configuration)")
    parser.add_argument("--enable", nargs="+", metavar="NAME", default=[], help="turn the identity of the server on for these services")
    parser.add_argument("--disable", nargs="+", metavar="NAME", default=[], help="turn it off (the drop-in is renamed; the key file stays)")
    parser.add_argument("--status", action="store_true", help="say which services have it on")
    parser.add_argument("--apply", action="store_true", help="write the changes (default: dry run)")
    args = parser.parse_args(argv)

    try:
        config = load_config(Path(args.config))
    except (OSError, ValueError, KeyError) as error:
        print(f"IDENTITY=REFUSED {error}", file=sys.stderr)
        return 2
    if args.directory:
        config["directory"] = args.directory
    if args.systemd_directory:
        config["systemd_directory"] = args.systemd_directory
    if args.server_env:
        config["server_env"] = args.server_env

    unknown = sorted(set(args.enable + args.disable) - set(config["services"]))
    if unknown:
        print(f"IDENTITY=REFUSED unknown service(s): {', '.join(unknown)} (known: {', '.join(sorted(config['services']))})", file=sys.stderr)
        return 2
    if set(args.enable) & set(args.disable):
        print("IDENTITY=REFUSED a service cannot be enabled and disabled in the same run", file=sys.stderr)
        return 2
    if args.status or not (args.enable or args.disable):
        for name, on in sorted(status(config).items()):
            print(f"IDENTITY_STATUS {name}: {'on' if on else 'off'}")
        return 0

    secret = ""
    if args.enable:
        try:
            secret = server_secret(Path(config["server_env"]), config["secret_variable"], int(config["min_secret_length"]))
        except ValueError as error:
            print(f"IDENTITY=REFUSED {error}", file=sys.stderr)
            return 1
    mode = int(config["key_mode"], 8)
    for name in args.enable:
        entry = config["services"][name]
        key_file = key_path(config, name)
        drop_in = dropin_path(config, entry)
        if not args.apply:
            print(f"[dry-run] would write {key_file} (mode {config['key_mode']}, group {entry['group']}) and {drop_in}")
            continue
        write_private(key_file, secret + "\n", mode, entry["group"])
        drop_in.parent.mkdir(parents=True, exist_ok=True)
        drop_in.write_text(dropin_text(entry, key_file), encoding="utf-8", newline="\n")
        os.chmod(drop_in, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
        print(f"IDENTITY=ENABLED {name}: {key_file} and {drop_in}; run systemctl daemon-reload and restart {entry['unit']}")
    for name in args.disable:
        entry = config["services"][name]
        drop_in = dropin_path(config, entry)
        if not drop_in.is_file():
            print(f"IDENTITY=UNCHANGED {name}: it was off")
            continue
        if not args.apply:
            print(f"[dry-run] would rename {drop_in} to {drop_in.name}.off")
            continue
        drop_in.replace(drop_in.with_name(drop_in.name + ".off"))
        print(f"IDENTITY=DISABLED {name}: run systemctl daemon-reload and restart {entry['unit']}; the key file {key_path(config, name)} stays, remove it by hand")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
