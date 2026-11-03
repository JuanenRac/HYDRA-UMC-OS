#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - Where a generated password goes (a private file) and whether it is also printed
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Shared by provisioning/gateway_env.py and provisioning/wifi_provision.py.

A password that a provisioning tool generates is written to a file only root can read (mode 0600, in a folder with mode 0700, written atomically). By default the tool shows the PATH of
that file and never the value, so the journal of the service never receives a password. For a device without a screen the operator can switch `print_once` on: the tool then also
prints the value, once, when it creates it.

`print_once` is off unless one of these turns it on (the first that is set wins):

1. the command-line flag `--print-once` (or `--no-print-once`);
2. the environment variable `HYDRA_UMC_PRINT_ONCE` (`1`, `true`, `yes` or `on` to turn it on);
3. the line `print_once = true` in the configuration file `/etc/hydra-umc/provisioning.conf` (or the file named by `HYDRA_UMC_PROVISIONING_CONF`).

Standard library only.
"""
from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path

DEFAULT_CONF = "/etc/hydra-umc/provisioning.conf"
_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off", ""}


def _parse_bool(raw: str | None) -> bool | None:
    if raw is None:
        return None
    value = raw.strip().strip("\"'").lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    return None  # not a recognised value: the conservative default stays


def _from_conf(conf: Path) -> bool | None:
    try:
        text = conf.read_text(encoding="utf-8")
    except OSError:
        return None
    found: bool | None = None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip().lower() == "print_once":
            found = _parse_bool(value.split("#", 1)[0])
    return found


def print_once_enabled(flag: bool | None = None, environ: dict[str, str] | None = None, conf: Path | None = None) -> bool:
    """Whether a generated password may also be printed once (off by default)."""
    if flag is not None:
        return flag
    env = os.environ if environ is None else environ
    from_env = _parse_bool(env.get("HYDRA_UMC_PRINT_ONCE"))
    if from_env is not None:
        return from_env
    path = conf or Path(env.get("HYDRA_UMC_PROVISIONING_CONF") or DEFAULT_CONF)
    from_file = _from_conf(path)
    return bool(from_file)


def ensure_private_dir(path: Path) -> None:
    """Create the folder (mode 0700) or tighten an existing one to 0700."""
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "nt":
        return
    if stat.S_IMODE(path.stat().st_mode) != 0o700:
        path.chmod(0o700)


def ensure_private_file(path: Path) -> bool:
    """A file that holds a secret must be 0600 and not a link: fix lax permissions (True when it had to be fixed) or refuse (PermissionError)."""
    if path.is_symlink():
        raise PermissionError(f"{path} is a symbolic link: refusing to use it for a secret")
    if os.name == "nt":
        return False
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        try:
            path.chmod(0o600)
        except OSError as error:
            raise PermissionError(f"{path} has mode {mode:04o} and it cannot be changed to 0600: {error}") from error
        return True
    return False


def write_private_atomic(path: Path, text: str, overwrite: bool = False) -> bool:
    """Write the file with mode 0600 so that it never exists half written nor readable by others.

    The text goes to a temporary file of the same folder (created 0600), is flushed to disk and then put in place: with `overwrite` False an existing file is never replaced (returns
    False), with True it is replaced in one step. Returns True when the file was written.
    """
    ensure_private_dir(path.parent)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        if os.name != "nt":
            os.chmod(temporary, 0o600)
        if overwrite:
            os.replace(temporary, path)
            return True
        try:
            os.link(temporary, path)  # fails when the file exists: it is never replaced
        except FileExistsError:
            return False
        return True
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
