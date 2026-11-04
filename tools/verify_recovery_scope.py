#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - Backup scope and consistent database copies verification
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Proves what provisioning/cm5_recovery.sh saves: the scope follows what is installed (not a fixed list), SQLite databases are copied with the backup API
while another connection holds a write-ahead log, and a restore refuses paths outside the scope. Runs the real script against a temporary root
(HYDRA_UMC_RECOVERY_ROOT); nothing outside the temporary folder is touched. The script part needs bash, tar and gzip and is skipped without them."""
from __future__ import annotations

import importlib.util
import os
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "provisioning" / "cm5_recovery.sh"
failures: list[str] = []


def expect(condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def load_scope():
    spec = importlib.util.spec_from_file_location("recovery_scope", ROOT / "provisioning" / "recovery_scope.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def build_root(base: Path) -> sqlite3.Connection:
    """A device in miniature; returns the connection that keeps the write-ahead log of the data lake database alive."""
    (base / "etc/hydra-umc").mkdir(parents=True)
    (base / "etc/hydra-umc/server.env").write_text("X=1\n", encoding="utf-8")
    (base / "etc/hydra-umc-detection-hef").mkdir()
    (base / "etc/hydra-umc-detection-hef/registry.json").write_text("{}", encoding="utf-8")
    (base / "etc/hydra-umc-node-healing").mkdir()
    (base / "etc/hydra-umc-node-healing/nodes.json").write_text("[]", encoding="utf-8")
    (base / "var/lib/hydra-umc/wifi-provision").mkdir(parents=True)
    (base / "var/lib/hydra-umc/wifi-provision/credentials.json").write_text("{}", encoding="utf-8")
    (base / "opt/hydra-umc/server/data").mkdir(parents=True)
    (base / "opt/hydra-umc/server/data/users.json").write_text("{}", encoding="utf-8")
    (base / "opt/hydra-umc/server/dist").mkdir()
    (base / "opt/hydra-umc/server/dist/app.js").write_text("code", encoding="utf-8")
    (base / "opt/hydra-umc/datalake/data").mkdir(parents=True)
    (base / "opt/hydra-umc/job-dispatcher/data").mkdir(parents=True)
    (base / "etc/systemd/system").mkdir(parents=True)
    for unit in ("hydra-umc-agent", "hydra-umc-server", "hydra-umc-voice-ui", "hydra-umc-wifi-provision", "hydra-umc-datalake"):
        (base / f"etc/systemd/system/{unit}.service").write_text("[Unit]\n", encoding="utf-8")
    (base / "etc/systemd/system/other.service").write_text("[Unit]\n", encoding="utf-8")
    (base / "etc/polkit-1/rules.d").mkdir(parents=True)
    (base / "etc/polkit-1/rules.d/50-hydra-umc-server-service-control.rules").write_text("//", encoding="utf-8")
    (base / "etc/polkit-1/rules.d/10-other.rules").write_text("//", encoding="utf-8")
    database = base / "opt/hydra-umc/datalake/data/lake.db"
    writer = sqlite3.connect(str(database))
    writer.execute("PRAGMA journal_mode=WAL")
    writer.execute("PRAGMA wal_autocheckpoint=0")
    writer.execute("CREATE TABLE readings (id INTEGER PRIMARY KEY, value TEXT)")
    writer.executemany("INSERT INTO readings (value) VALUES (?)", [(f"v{i}",) for i in range(200)])
    writer.commit()
    writer.execute("INSERT INTO readings (value) VALUES ('in the wal')")
    writer.commit()  # stays in the -wal file: a plain copy of lake.db alone would miss it
    (base / "opt/hydra-umc/job-dispatcher/data/jobs.sqlite").write_bytes(b"not a database")
    return writer


def rows(path: Path) -> int:
    connection = sqlite3.connect(str(path))
    try:
        return connection.execute("SELECT COUNT(*) FROM readings").fetchone()[0]
    finally:
        connection.close()


def check_scope_and_members() -> None:
    scope = load_scope()
    with tempfile.TemporaryDirectory() as folder:
        base = Path(folder)
        writer = build_root(base)
        try:
            paths = scope.top_level_paths(base)
            for wanted in ("etc/hydra-umc", "etc/hydra-umc-detection-hef", "etc/hydra-umc-node-healing", "var/lib/hydra-umc", "opt/hydra-umc/server/data",
                           "opt/hydra-umc/datalake/data", "opt/hydra-umc/job-dispatcher/data", "etc/systemd/system/hydra-umc-wifi-provision.service",
                           "etc/systemd/system/hydra-umc-voice-ui.service", "etc/systemd/system/hydra-umc-datalake.service",
                           "etc/polkit-1/rules.d/50-hydra-umc-server-service-control.rules"):
                expect(wanted in paths, f"the scope must include {wanted}")
            for unwanted in ("opt/hydra-umc/server/dist", "opt/hydra-umc/server", "etc/systemd/system/other.service", "etc/polkit-1/rules.d/10-other.rules"):
                expect(unwanted not in paths, f"the scope must not include {unwanted}")
            live = scope.live_db_files(base)
            expect("opt/hydra-umc/datalake/data/lake.db" in live, "the live database must be named")
            expect("opt/hydra-umc/datalake/data/lake.db-wal" in live, "the write-ahead log of the live database must be named")
            expect(not any("jobs.sqlite" in name for name in live), "a file that is not a database must not be treated as one")
            with tempfile.TemporaryDirectory() as stage_folder:
                copied = scope.snapshot(base, Path(stage_folder))
                expect(copied == ["opt/hydra-umc/datalake/data/lake.db"], f"only the real database is copied, got {copied}")
                if copied:
                    expect(rows(Path(stage_folder) / copied[0]) == 201, "the copy holds the rows that were still in the write-ahead log")
        finally:
            writer.close()
    for good in ("etc/hydra-umc/server.env", "./etc/hydra-umc-node-healing/nodes.json", "opt/hydra-umc/datalake/data/lake.db", "etc/systemd/system/hydra-umc-agent.service",
                 "var/lib/hydra-umc/", "etc/polkit-1/rules.d/49-hydra-umc-server-power.rules"):
        expect(scope.member_problem(good) is None, f"{good} must be accepted")
    for bad in ("/etc/passwd", "etc/hydra-umc/../passwd", "etc/hydra-umcx/file", "opt/hydra-umc/server/dist/app.js", "etc/systemd/system/other.service",
                "root/.ssh/authorized_keys", "opt/hydra-umc/server/data/../../x"):
        expect(scope.member_problem(bad) is not None, f"{bad} must be refused")


def run(*arguments: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run([shutil.which("bash") or "bash", SCRIPT.as_posix(), *arguments], capture_output=True, text=True, env={**os.environ, **env}, check=False)


def check_script() -> None:
    if not (shutil.which("bash") and shutil.which("tar") and shutil.which("gzip")):
        print("RECOVERY_SCOPE=SKIPPED the script part needs bash, tar and gzip")
        return
    with tempfile.TemporaryDirectory() as folder:
        base = Path(folder) / "root"
        base.mkdir()
        writer = build_root(base)
        env = {"HYDRA_UMC_RECOVERY_ROOT": base.as_posix()}
        if os.name == "nt":
            # the `install` of Git for Windows cannot change the mode of a folder: a stand-in that only creates it keeps the rest of the script under test
            shim = Path(folder) / "shim"
            shim.mkdir()
            stand_in = "\n".join(["#!/usr/bin/env bash", "for last; do :; done", 'mkdir -p "$last"', ""])
            (shim / "install").write_bytes(stand_in.encode("utf-8"))
            env["PATH"] = shim.as_posix() + os.pathsep + os.environ["PATH"]
        archive = Path(folder) / "out" / "state.tar.gz"
        try:
            result = run("backup", archive.as_posix(), "--apply", env=env)
            expect(result.returncode == 0 and "CM5_RECOVERY=PASS" in result.stdout, f"the backup must pass: {result.stdout} {result.stderr}")
            expect(archive.is_file(), "the archive must exist")
            if archive.is_file():
                with tarfile.open(archive) as handle:
                    names = [member.name.removeprefix("./") for member in handle.getmembers()]
                expect(names.count("opt/hydra-umc/datalake/data/lake.db") == 1, "the database must be in the archive once")
                expect(not any(name.endswith(("lake.db-wal", "lake.db-shm")) for name in names), "the live write-ahead files must stay out")
                expect("etc/hydra-umc-node-healing/nodes.json" in names, "the node healing configuration must be in the archive")
                expect("etc/systemd/system/hydra-umc-voice-ui.service" in names, "the unit of every program must be in the archive")
                expect("opt/hydra-umc/job-dispatcher/data/jobs.sqlite" in names, "a file that is not a database is copied as it is")
                expect(not any(name.startswith("opt/hydra-umc/server/dist") for name in names), "the program code is not part of the state")
            # change the state, then restore: the rows and the files come back, a stale write-ahead log is dropped
            writer.execute("DELETE FROM readings")
            writer.commit()
            writer.close()
            (base / "etc/hydra-umc/server.env").write_text("X=changed\n", encoding="utf-8")
            (base / "opt/hydra-umc/datalake/data/lake.db-wal").write_bytes(b"stale")
            result = run("restore", archive.as_posix(), "--apply", env=env)
            expect(result.returncode == 0 and "action=restore" in result.stdout, f"the restore must pass: {result.stdout} {result.stderr}")
            expect((base / "etc/hydra-umc/server.env").read_text(encoding="utf-8") == "X=1\n", "the configuration must be restored")
            expect(not (base / "opt/hydra-umc/datalake/data/lake.db-wal").exists(), "a stale write-ahead log must be removed before the restore")
            expect(rows(base / "opt/hydra-umc/datalake/data/lake.db") == 201, "the database must come back with its rows")
            # an archive with a path outside the scope is refused
            evil = Path(folder) / "evil.tar.gz"
            payload = Path(folder) / "payload.txt"
            payload.write_text("x", encoding="utf-8")
            with tarfile.open(evil, "w:gz") as handle:
                handle.add(payload, arcname="etc/cron.d/backdoor")
            result = run("restore", evil.as_posix(), "--apply", env=env)
            expect(result.returncode == 2 and not (base / "etc/cron.d/backdoor").exists(), "an archive outside the scope must be refused")
        finally:
            try:
                writer.close()
            except sqlite3.Error:
                pass


def main() -> int:
    check_scope_and_members()
    check_script()
    if failures:
        for message in failures:
            print(f"RECOVERY_SCOPE=FAIL {message}", file=sys.stderr)
        return 1
    print("RECOVERY_SCOPE=PASS scope, consistent database copies, restore whitelist")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
