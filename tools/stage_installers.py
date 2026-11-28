#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - tools/stage_installers.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""A copy of the installers that only root can write, made from the newest signed release of this repository.

    sudo /usr/bin/python3 /usr/local/lib/hydra-umc/stage_installers.py      (the rule of sudo gives it no argument)

Root fetches the release tags into a repository of its own under the installers folder (never the checkout of an account), takes the newest `vX.Y.Z`, checks it with
`git verify-tag` against the signers file of root, writes the tree of its commit into `<installers>/<tag>/HYDRA-UMC-OS` and moves the link `current` to it in one step.
It never goes back to an older release. The programs an installer copies still come from the checkouts of the account of the workspace (links next to the copy), so this
protects the installer scripts, not the programs they build: the root helper with signed packages (tools/root_helper.py) is the way that closes that. Settings
(owner, workspace) come from /etc/hydra-umc/fleet-update.json, which only root writes. Prints `STAGED=<tag>` on success. Not run on a CM5.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Any, Callable

INSTALLERS_ROOT = Path("/opt/hydra-umc/.installers")
SIGNERS = Path("/etc/hydra-umc/allowed_signers")
CONFIG = Path("/etc/hydra-umc/fleet-update.json")
REPOSITORY = "HYDRA-UMC-OS"
RELEASE_TAG = re.compile(r"v\d+(\.\d+){1,3}")
OWNER = re.compile(r"[A-Za-z0-9-]{1,39}")

Run = Callable[[list[str]], "tuple[int, bytes]"]


class StageError(Exception):
    pass


def default_run(argv: list[str]) -> tuple[int, bytes]:
    env = {**os.environ, "GIT_NO_REPLACE_OBJECTS": "1", "GIT_TERMINAL_PROMPT": "0"}
    done = subprocess.run(argv, capture_output=True, timeout=600, check=False, env=env)
    return done.returncode, done.stdout if done.returncode == 0 else done.stderr


def version_key(tag: str) -> tuple[int, ...]:
    return tuple(int(part) for part in tag[1:].split("."))


def read_settings(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as error:
        raise StageError(f"{path} cannot be read ({type(error).__name__})") from error
    return raw if isinstance(raw, dict) else {}


def current_tag(installers: Path) -> str | None:
    link = installers / "current"
    if not link.is_symlink():
        return None
    name = Path(os.readlink(link)).parts[0]
    return name if RELEASE_TAG.fullmatch(name) else None


def git(run: Run, mirror: Path, *words: str) -> bytes:
    code, out = run(["git", "--git-dir", str(mirror), *words])
    if code != 0:
        raise StageError(f"git {words[0]} failed: {out.decode('utf-8', 'replace').strip()[-200:]}")
    return out


def extract(data: bytes, target: Path) -> None:
    """The tree of the release, with nothing that could leave the folder and nothing writable by others."""
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as archive:
        for member in archive.getmembers():
            path = Path(member.name)
            if path.is_absolute() or ".." in path.parts or not (member.isfile() or member.isdir()):
                raise StageError(f"the archive of the release holds an entry that is not a plain file: {member.name}")
            destination = target / path
            if member.isdir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            assert source is not None
            destination.write_bytes(source.read())
            destination.chmod(0o755 if member.mode & 0o100 else 0o644)


def stage(installers: Path, url: str, signers: Path, workspace: Path | None, run: Run = default_run) -> str:
    if not signers.is_file():
        raise StageError(f"the signers file {signers} is missing: nothing can be verified")
    installers.mkdir(parents=True, exist_ok=True)
    mirror = installers / "repo.git"
    if not mirror.is_dir():
        code, out = run(["git", "init", "--bare", "-q", str(mirror)])
        if code != 0:
            raise StageError(f"cannot make the repository of root: {out.decode('utf-8', 'replace').strip()[-200:]}")
    git(run, mirror, "fetch", "--quiet", "--force", url, "refs/tags/*:refs/tags/*")
    tags = [t for t in git(run, mirror, "tag", "--list").decode("utf-8", "replace").split() if RELEASE_TAG.fullmatch(t)]
    if not tags:
        raise StageError("the repository has no release tag")
    tag = max(tags, key=version_key)
    held = current_tag(installers)
    if held is not None and version_key(held) > version_key(tag):
        return held  # never back to an older release
    git(run, mirror, "-c", "gpg.format=ssh", "-c", f"gpg.ssh.allowedSignersFile={signers}", "verify-tag", tag)
    commit = git(run, mirror, "rev-parse", f"{tag}^{{commit}}").decode("ascii", "replace").strip()
    if not re.fullmatch(r"[0-9a-f]{40,64}", commit):
        raise StageError("the tag does not name a commit")
    final = installers / tag
    if not final.is_dir():
        partial = installers / f".{tag}.partial"
        shutil.rmtree(partial, ignore_errors=True)
        extract(git(run, mirror, "archive", "--format=tar", commit), partial / REPOSITORY)
        os.replace(partial, final)
    if workspace is not None and workspace.is_dir():
        # the installers read each program from the folder next to this repository
        for sibling in sorted(workspace.glob("HYDRA-UMC*")):
            link = final / sibling.name
            if sibling.name != REPOSITORY and sibling.is_dir() and not link.exists() and not link.is_symlink():
                os.symlink(sibling, link, target_is_directory=True)
    pointer = installers / "current.new"
    if pointer.is_symlink():
        pointer.unlink()
    os.symlink(tag, pointer, target_is_directory=True)
    os.replace(pointer, installers / "current")
    return tag


def main(argv: list[str] | None = None, run: Run = default_run) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--installers-root", type=Path, default=INSTALLERS_ROOT)
    parser.add_argument("--signers", type=Path, default=SIGNERS)
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--url", help="where the tags come from (default: the repository of the owner on github.com)")
    args = parser.parse_args(argv)
    try:
        settings = read_settings(args.config)
        owner = str(settings.get("owner") or "JuanenRac")
        if not OWNER.fullmatch(owner):
            raise StageError("the owner of the settings is not a name of an account")
        workspace = str(settings.get("workspace") or "/home/hydra-umc/hydra-umc")
        tag = stage(args.installers_root, args.url or f"https://github.com/{owner}/{REPOSITORY}.git", args.signers,
                    Path(workspace) if workspace.startswith("/") else None, run)
    except (StageError, OSError, subprocess.TimeoutExpired, tarfile.TarError) as error:
        print(f"STAGE=FAIL {error}", file=sys.stderr)
        return 2
    print(f"STAGED={tag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
