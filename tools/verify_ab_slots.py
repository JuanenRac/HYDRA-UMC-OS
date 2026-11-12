#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - Two-slot update verification
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Prove the two-slot update state machine (provisioning/ab_slots.py) without a board.

The simulated backend stands in for the boot loader, the autoboot backend writes the real text of the Raspberry Pi `autoboot.txt` into a
temporary folder, and a seeded random walk of operations checks the invariants that must hold whatever happens:

* the default boot entry equals the active slot at all times, and it changes only inside `confirm`;
* at most one trial is open, always on the idle slot;
* a slot that failed its trial is never tried again until a new image is written to it.

Nothing here has run on a real CM5 or with a real boot loader: that is the board test.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "provisioning"))

import ab_slots
from ab_slots import (
    AutobootBackend,
    SimulatedBackend,
    SlotError,
    SlotLayout,
    SlotManager,
    autoboot_text,
)

CHECKS = 0


def fail(message: str) -> None:
    print(f"AB_SLOTS_VERIFY=FAIL {message}", file=sys.stderr)
    raise SystemExit(1)


def check(name: str, condition: bool) -> None:
    global CHECKS
    if not condition:
        fail(name)
    CHECKS += 1
    print(f"AB_SLOTS_VERIFY=PASS {name}")


def refuses(name: str, action) -> None:  # type: ignore[no-untyped-def]
    try:
        action()
    except SlotError:
        check(name, True)
        return
    fail(f"{name}: it did not refuse")


def make_image(directory: Path, content: bytes, name: str = "image.bin") -> tuple[Path, str]:
    path = directory / name
    path.write_bytes(content)
    return path, hashlib.sha256(content).hexdigest()


def fresh(directory: Path, *, enabled: bool = True) -> tuple[SlotManager, SimulatedBackend]:
    backend = SimulatedBackend(directory / "slots")
    return SlotManager(directory / "state.json", backend, enabled=enabled), backend


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="hydra-umc-ab-") as temporary:
        base = Path(temporary)

        # --- the happy path -----------------------------------------------------------------
        d = base / "happy"
        d.mkdir()
        manager, backend = fresh(d)
        image, digest = make_image(d, b"system-v2")
        check("a new system starts with slot A active and slot B idle", manager.status()["active"] == "A" and manager.status()["idle"] == "B")
        manager.stage(image, expected_sha256=digest, now=1000)
        check("the image goes to the idle slot only", (d / "slots" / "slot-B.img").read_bytes() == b"system-v2" and not (d / "slots" / "slot-A.img").exists())
        manager.begin_trial(now=1001, timeout_seconds=120)
        check("the trial leaves the default boot entry on the old slot", backend.default == "A" and backend.trial == "B")
        manager.mark_reboot(now=1005)
        booted = backend.booted(tried=True)
        check("the loader starts the trial slot once", booted == "B" and backend.trial is None)
        result = manager.evaluate(now=1040, booted=booted, healthy=True)
        check("a healthy report inside the limit makes it the default", result["active"] == "B" and backend.default == "B" and manager.status()["trial"] is None)
        check("the next boot is the new slot", backend.booted(tried=False) == "B")

        # --- the second update goes back to the first slot ------------------------------------
        image2, digest2 = make_image(d, b"system-v3", "image2.bin")
        manager.stage(image2, expected_sha256=digest2, now=2000)
        check("the idle slot is now A", (d / "slots" / "slot-A.img").read_bytes() == b"system-v3")

        # --- unhealthy: rolled back, marked bad ----------------------------------------------
        manager.begin_trial(now=2001)
        manager.mark_reboot(now=2002)
        failed = manager.evaluate(now=2050, booted=backend.booted(tried=True), healthy=False)
        check("an unhealthy new system is rolled back and marked bad", failed["failed"] == "A" and failed["active"] == "B" and backend.default == "B" and manager.status()["bad"] == ["A"])
        refuses("a failed slot is not tried again without a new image", lambda: manager.begin_trial(now=2100))

        # --- late report ------------------------------------------------------------------
        manager.stage(image2, expected_sha256=digest2, now=3000)
        check("a new image clears the bad mark", manager.status()["bad"] == [])
        manager.begin_trial(now=3001, timeout_seconds=60)
        manager.mark_reboot(now=3002)
        late = manager.evaluate(now=3002 + 61, booted="A", healthy=True)
        check("a report after the time limit is a failure", late["failed"] == "A" and backend.default == "B")

        # --- the board fell back on its own ----------------------------------------------------
        manager.stage(image2, expected_sha256=digest2, now=4000)
        manager.begin_trial(now=4001, timeout_seconds=300)
        before = manager.evaluate(now=4002, booted="B", healthy=True)
        check("the old slot starting BEFORE the reboot was marked changes nothing", before.get("unchanged") is True and manager.status()["trial"] is not None)
        manager.mark_reboot(now=4010)
        fell = manager.evaluate(now=4040, booted="B", healthy=False)
        check("the old slot starting AFTER the marked reboot fails the trial", fell["failed"] == "A")

        # --- an operator rollback -----------------------------------------------------------
        manager.stage(image2, expected_sha256=digest2, now=5000)
        manager.begin_trial(now=5001)
        rolled = manager.rollback(now=5002, reason="operator")
        check("an operator can give the trial up", rolled["failed"] == "A" and backend.trial is None and backend.default == "B")
        refuses("rolling back without a trial is refused", lambda: manager.rollback(now=5003))
        refuses("confirming without a trial is refused", lambda: manager.confirm(now=5003))

        # --- refusals -------------------------------------------------------------------
        d2 = base / "refusals"
        d2.mkdir()
        manager2, backend2 = fresh(d2)
        img, dig = make_image(d2, b"x" * 100)
        refuses("a wrong SHA-256 writes nothing", lambda: manager2.stage(img, expected_sha256="0" * 64, now=1))
        check("... and nothing reached the slot", not (d2 / "slots" / "slot-B.img").exists())
        refuses("a short SHA-256 is refused", lambda: manager2.stage(img, expected_sha256=dig[:10], now=1))
        refuses("a missing image is refused", lambda: manager2.stage(d2 / "nothing.bin", expected_sha256=dig, now=1))
        refuses("a trial without an image is refused", lambda: manager2.begin_trial(now=1))
        manager2.stage(img, expected_sha256=dig, now=1)
        refuses("a time limit below the minimum is refused", lambda: manager2.begin_trial(now=2, timeout_seconds=1))
        refuses("a time limit above the maximum is refused", lambda: manager2.begin_trial(now=2, timeout_seconds=10 ** 7))
        manager2.begin_trial(now=2)
        refuses("a second trial is refused", lambda: manager2.begin_trial(now=3))
        refuses("a new image during a trial is refused", lambda: manager2.stage(img, expected_sha256=dig, now=3))
        late_confirm = manager2.confirm(now=2 + 10 ** 5)
        check("confirming after the deadline fails the trial instead", "failed" in late_confirm and backend2.default == "A")
        refuses("an unknown slot name is refused", lambda: manager2.evaluate(now=5, booted="C", healthy=True))

        # --- switched off ---------------------------------------------------------------
        d3 = base / "off"
        d3.mkdir()
        off, off_backend = fresh(d3, enabled=False)
        img3, dig3 = make_image(d3, b"y")
        refuses("a switched-off manager refuses to stage", lambda: off.stage(img3, expected_sha256=dig3, now=1))
        refuses("... to begin a trial", lambda: off.begin_trial(now=1))
        refuses("... to confirm", lambda: off.confirm(now=1))
        check("... but status and plan still work", off.status()["active"] == "A" and off.plan()["write_to"] == "B")
        check("... and nothing was written", off_backend.events == [] and not (d3 / "state.json").exists())
        with_env = subprocess.run(
            (sys.executable, str(ROOT / "provisioning" / "ab_slots.py"), "--state", str(d3 / "s.json"), "--dir", str(d3 / "b"), "--now", "1", "stage", str(img3), "--sha256", dig3),
            text=True, capture_output=True, check=False, env={k: v for k, v in os.environ.items() if k != ab_slots.ENABLE_ENVIRONMENT},
        )
        check("the command line refuses without the environment switch", with_env.returncode == 1 and "AB_SLOTS=REFUSED" in with_env.stderr)
        switched = subprocess.run(
            (sys.executable, str(ROOT / "provisioning" / "ab_slots.py"), "--state", str(d3 / "s.json"), "--dir", str(d3 / "b"), "--now", "1", "stage", str(img3), "--sha256", dig3),
            text=True, capture_output=True, check=False, env={**os.environ, ab_slots.ENABLE_ENVIRONMENT: "1"},
        )
        check("the command line works with the switch", switched.returncode == 0 and json.loads(switched.stdout)["staged"] == "B")

        # --- a damaged state is never repaired by guessing ----------------------------------------
        d4 = base / "damaged"
        d4.mkdir()
        manager4, _ = fresh(d4)
        (d4 / "state.json").write_text("{not json", encoding="utf-8")
        refuses("a state that is not JSON is refused", lambda: manager4.status())
        bad_states = [
            {"schema": 2, "active": "A", "bad": [], "staged": None, "trial": None, "history": []},
            {"schema": 1, "active": "C", "bad": [], "staged": None, "trial": None, "history": []},
            {"schema": 1, "active": "A", "bad": ["Z"], "staged": None, "trial": None, "history": []},
            {"schema": 1, "active": "A", "bad": [], "staged": {"slot": "A"}, "trial": None, "history": []},
            {"schema": 1, "active": "A", "bad": [], "staged": {"slot": "B"}, "trial": {"slot": "A", "deadline": 1}, "history": []},
            {"schema": 1, "active": "A", "bad": [], "staged": None, "trial": {"slot": "B", "deadline": 1}, "history": []},
            {"schema": 1, "active": "A", "bad": [], "staged": {"slot": "B"}, "trial": {"slot": "B", "deadline": "soon"}, "history": []},
            [],
        ]
        for index, state in enumerate(bad_states):
            (d4 / "state.json").write_text(json.dumps(state), encoding="utf-8")
            refuses(f"damaged state {index} is refused", lambda: manager4.status())

        # --- the autoboot.txt of the Raspberry Pi -----------------------------------------------
        check("autoboot.txt without a trial", autoboot_text("A", None) == "[all]\ntryboot_a_b=1\nboot_partition=2\n")
        check("autoboot.txt with a trial", autoboot_text("A", "B") == "[all]\ntryboot_a_b=1\nboot_partition=2\n[tryboot]\nboot_partition=3\n")
        check("autoboot.txt follows a custom layout", autoboot_text("B", "A", SlotLayout({"A": 5, "B": 6})) == "[all]\ntryboot_a_b=1\nboot_partition=6\n[tryboot]\nboot_partition=5\n")
        refuses("the trial slot cannot be the default one", lambda: autoboot_text("A", "A"))
        refuses("a layout with the same partition twice is refused", lambda: SlotLayout({"A": 2, "B": 2}))
        refuses("a layout without a slot is refused", lambda: SlotLayout({"A": 2}))
        written: list[tuple[str, str]] = []
        d5 = base / "autoboot"
        d5.mkdir()
        boot = d5 / "boot"
        auto = AutobootBackend(boot, lambda slot, image: written.append((slot, image.name)))
        manager5 = SlotManager(d5 / "state.json", auto, enabled=True)
        img5, dig5 = make_image(d5, b"z" * 10)
        manager5.stage(img5, expected_sha256=dig5, now=1)
        check("the autoboot backend hands the image to the writer for the idle slot", written == [("B", "image.bin")])
        check("staging does not touch autoboot.txt", not (boot / "autoboot.txt").exists())
        manager5.begin_trial(now=2)
        check("the trial adds the [tryboot] section", (boot / "autoboot.txt").read_text(encoding="utf-8") == autoboot_text("A", "B"))
        manager5.mark_reboot(now=3)
        manager5.evaluate(now=4, booted="B", healthy=True)
        check("confirming makes the new slot the default and drops the trial", (boot / "autoboot.txt").read_text(encoding="utf-8") == autoboot_text("B", None))
        leftovers = [p.name for p in boot.iterdir() if p.name != "autoboot.txt"]
        check("no temporary file is left in the boot folder", leftovers == [])

        # --- a seeded random walk keeps the invariants ----------------------------------------
        rng = random.Random(20260512)
        for walk in range(40):
            dw = base / f"walk{walk}"
            dw.mkdir()
            mgr, bk = fresh(dw)
            clock = 1000.0
            images = [make_image(dw, bytes([i]) * 20, f"i{i}.bin") for i in range(3)]
            for step in range(60):
                clock += rng.choice((1, 5, 50, 400, 5000))
                action = rng.choice(("stage", "stage_bad", "trial", "mark", "boot_try", "boot_default", "eval_ok", "eval_bad", "confirm", "rollback"))
                before = mgr.status()
                try:
                    if action == "stage":
                        path, dg = rng.choice(images)
                        mgr.stage(path, expected_sha256=dg, now=clock)
                    elif action == "stage_bad":
                        path, dg = rng.choice(images)
                        mgr.stage(path, expected_sha256="f" * 64, now=clock)
                    elif action == "trial":
                        mgr.begin_trial(now=clock, timeout_seconds=rng.choice((30, 120, 3600)))
                    elif action == "mark":
                        mgr.mark_reboot(now=clock)
                    elif action == "boot_try":
                        mgr.evaluate(now=clock, booted=bk.booted(tried=True), healthy=rng.random() < 0.7)
                    elif action == "boot_default":
                        mgr.evaluate(now=clock, booted=bk.booted(tried=False), healthy=rng.random() < 0.7)
                    elif action == "eval_ok":
                        mgr.evaluate(now=clock, booted=rng.choice("AB"), healthy=True)
                    elif action == "eval_bad":
                        mgr.evaluate(now=clock, booted=rng.choice("AB"), healthy=False)
                    elif action == "confirm":
                        mgr.confirm(now=clock)
                    else:
                        mgr.rollback(now=clock)
                except SlotError:
                    pass
                after = mgr.status()
                if bk.default is not None and bk.default != after["active"]:
                    fail(f"walk {walk} step {step}: the default boot entry {bk.default} is not the active slot {after['active']}")
                if after["trial"] is not None and after["trial"]["slot"] == after["active"]:
                    fail(f"walk {walk} step {step}: the trial is on the active slot")
                if after["trial"] is not None and after["trial"]["slot"] in after["bad"]:
                    fail(f"walk {walk} step {step}: a bad slot is being tried")
                if after["active"] != before["active"]:
                    if action not in ("confirm", "boot_try", "boot_default", "eval_ok", "eval_bad"):
                        fail(f"walk {walk} step {step}: the active slot changed inside {action}")
                    if after["active"] != (before["trial"] or {}).get("slot"):
                        fail(f"walk {walk} step {step}: the active slot changed to something that was not on trial")
        check("40 seeded walks of 60 operations keep every invariant", True)

    print(f"AB_SLOTS_VERIFY=PASS all {CHECKS} checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
