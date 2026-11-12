#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - Two-slot operating system update (slot manager)
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The state machine of a two-slot (A/B) operating system image.

The image has two slots. One is `active` and boots by default. An update is written to the idle slot, the boot loader is told to try it
ONCE (`tryboot`), and the new system has a time limit to say it is healthy. If it does, the idle slot becomes the active one; if it does not
(it never reports, the deadline passes, or the board fell back to the old slot on its own), nothing is changed in the default boot entry and
the failed slot is marked bad until a new image is written to it. The default boot entry is changed in exactly one place, `confirm`.

Nothing here touches a disk. The slot manager only decides and records; a backend carries the decision out:

* `SimulatedBackend` keeps the "slots" as files in a directory and the "boot entry" in memory. It is what the checks and a developer use.
* `AutobootBackend` writes the Raspberry Pi `autoboot.txt` of the boot partition (`tryboot_a_b=1`, `[all]` and `[tryboot]` sections) in a directory
  it is given, and records the write of an image by calling a function it is given. It never runs `dd` or `reboot` by itself.

Every command that changes something refuses to run unless `HYDRA_UMC_AB_SLOTS=1` is set (off by default); `status` and `plan` always work.
The state file is written atomically and a state that cannot be read, or that contradicts itself, is refused rather than repaired by guessing.
`tools/verify_ab_slots.py` proves the machine with both backends and a seeded random walk; it has not been run on a board.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

SCHEMA = 1
SLOTS = ("A", "B")
ENABLE_ENVIRONMENT = "HYDRA_UMC_AB_SLOTS"
DEFAULT_TRIAL_SECONDS = 600
MIN_TRIAL_SECONDS = 30
MAX_TRIAL_SECONDS = 24 * 3600


class SlotError(Exception):
    """A request that must not be carried out, or a state that cannot be trusted."""


def other(slot: str) -> str:
    if slot not in SLOTS:
        raise SlotError(f"unknown slot {slot!r}")
    return "B" if slot == "A" else "A"


@dataclass(frozen=True)
class SlotLayout:
    """Where each slot lives: the number of its boot partition (the one `autoboot.txt` points at)."""

    boot_partition: dict[str, int]

    def __post_init__(self) -> None:
        if set(self.boot_partition) != set(SLOTS):
            raise SlotError("the layout needs a boot partition for slot A and for slot B")
        numbers = list(self.boot_partition.values())
        if any(not isinstance(n, int) or isinstance(n, bool) or n < 1 for n in numbers) or len(set(numbers)) != 2:
            raise SlotError("the boot partitions must be two different positive integers")


DEFAULT_LAYOUT = SlotLayout({"A": 2, "B": 3})


class Backend(Protocol):
    def write_image(self, slot: str, image: Path) -> None: ...
    def set_default(self, slot: str) -> None: ...
    def set_trial(self, slot: str, default: str) -> None: ...
    def clear_trial(self, default: str) -> None: ...


class SimulatedBackend:
    """Slots are files in `directory`; the boot entry is what `default` and `trial` say. Records every call in `events`."""

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.default: str | None = None
        self.trial: str | None = None
        self.events: list[tuple[str, str]] = []

    def write_image(self, slot: str, image: Path) -> None:
        target = self.directory / f"slot-{slot}.img"
        shutil.copyfile(image, target)
        self.events.append(("write", slot))

    def set_default(self, slot: str) -> None:
        self.default = slot
        self.trial = None
        self.events.append(("default", slot))

    def set_trial(self, slot: str, default: str) -> None:
        self.default = default
        self.trial = slot
        self.events.append(("trial", slot))

    def clear_trial(self, default: str) -> None:
        self.default = default
        self.trial = None
        self.events.append(("clear", default))

    def booted(self, tried: bool) -> str:
        """The slot a reboot would start: the trial one the first time (the loader forgets it after one boot), the default otherwise."""
        if tried and self.trial is not None:
            slot = self.trial
            self.trial = None
            return slot
        if self.default is None:
            raise SlotError("no default slot was ever set")
        return self.default


def autoboot_text(default: str, trial: str | None, layout: SlotLayout = DEFAULT_LAYOUT) -> str:
    """The `autoboot.txt` of the Raspberry Pi boot loader: `[all]` is the default entry, `[tryboot]` is used once when the reboot asks for it."""
    lines = ["[all]", "tryboot_a_b=1", f"boot_partition={layout.boot_partition[default]}"]
    if trial is not None:
        if trial == default:
            raise SlotError("the trial slot must be the idle one")
        lines += ["[tryboot]", f"boot_partition={layout.boot_partition[trial]}"]
    return "\n".join(lines) + "\n"


class AutobootBackend:
    """Writes `autoboot.txt` in `boot_dir`; the image of a slot is handed to `writer(slot, image)` (a real one would write the partition)."""

    def __init__(self, boot_dir: Path, writer: Callable[[str, Path], None], layout: SlotLayout = DEFAULT_LAYOUT) -> None:
        self.boot_dir = Path(boot_dir)
        self._writer = writer
        self.layout = layout

    def _write(self, text: str) -> None:
        self.boot_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write(self.boot_dir / "autoboot.txt", text)

    def write_image(self, slot: str, image: Path) -> None:
        self._writer(slot, image)

    def set_default(self, slot: str) -> None:
        self._write(autoboot_text(slot, None, self.layout))

    def set_trial(self, slot: str, default: str) -> None:
        self._write(autoboot_text(default, slot, self.layout))

    def clear_trial(self, default: str) -> None:
        self._write(autoboot_text(default, None, self.layout))


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


class SlotManager:
    """The decisions. `state_path` is the JSON file of the state; `backend` carries them out."""

    def __init__(self, state_path: Path, backend: Backend, *, enabled: bool | None = None, initial_active: str = "A") -> None:
        self.state_path = Path(state_path)
        self.backend = backend
        self.enabled = os.environ.get(ENABLE_ENVIRONMENT, "").strip() == "1" if enabled is None else bool(enabled)
        self._initial_active = initial_active

    # ---- state -----------------------------------------------------------------------------------
    def _fresh(self) -> dict[str, object]:
        other(self._initial_active)
        return {"schema": SCHEMA, "active": self._initial_active, "bad": [], "staged": None, "trial": None, "history": []}

    def load(self) -> dict[str, object]:
        if not self.state_path.exists():
            return self._fresh()
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise SlotError(f"the state file cannot be read ({type(error).__name__}); it is not repaired by guessing") from error
        self._check(state)
        return state

    @staticmethod
    def _check(state: object) -> None:
        if not isinstance(state, dict) or state.get("schema") != SCHEMA:
            raise SlotError("the state file has an unknown schema")
        active = state.get("active")
        if active not in SLOTS:
            raise SlotError("the state file names no valid active slot")
        bad = state.get("bad")
        if not isinstance(bad, list) or any(s not in SLOTS for s in bad):
            raise SlotError("the list of bad slots is damaged")
        trial = state.get("trial")
        if trial is not None and (not isinstance(trial, dict) or trial.get("slot") != other(active) or not isinstance(trial.get("deadline"), (int, float))):
            raise SlotError("the trial in the state file contradicts the active slot")
        staged = state.get("staged")
        if staged is not None and (not isinstance(staged, dict) or staged.get("slot") != other(active)):
            raise SlotError("the staged image in the state file is not for the idle slot")
        if trial is not None and staged is None:
            raise SlotError("a trial without a staged image")

    def _save(self, state: dict[str, object]) -> None:
        self._check(state)
        history = state["history"]
        assert isinstance(history, list)
        del history[:-50]
        _atomic_write(self.state_path, json.dumps(state, indent=2, sort_keys=True) + "\n")

    def _need_enabled(self) -> None:
        if not self.enabled:
            raise SlotError(f"switched off: set {ENABLE_ENVIRONMENT}=1 to let a command change the slots")

    @staticmethod
    def _note(state: dict[str, object], event: str, now: float, **extra: object) -> None:
        history = state["history"]
        assert isinstance(history, list)
        history.append({"event": event, "at": now, **extra})

    # ---- read-only -------------------------------------------------------------------------------
    def status(self) -> dict[str, object]:
        state = self.load()
        active = str(state["active"])
        return {"active": active, "idle": other(active), "bad": state["bad"], "staged": state["staged"], "trial": state["trial"], "history": state["history"][-5:]}  # type: ignore[index]

    def plan(self) -> dict[str, object]:
        """What an update would do now, without doing it."""
        state = self.load()
        active = str(state["active"])
        idle = other(active)
        blocked = None
        if state["trial"] is not None:
            blocked = "a trial is running: confirm it or roll it back first"
        return {
            "write_to": idle,
            "then": ["write the image to the idle slot", f"try slot {idle} once", "wait for the health report within the time limit", f"make slot {idle} the default only after it reports healthy"],
            "blocked": blocked,
            "idle_was_bad": idle in state["bad"],  # type: ignore[operator]
        }

    # ---- changes ---------------------------------------------------------------------------------
    def stage(self, image: Path, *, expected_sha256: str, now: float) -> dict[str, object]:
        """Write `image` to the idle slot after checking its SHA-256. Never touches the active slot or the default boot entry."""
        self._need_enabled()
        state = self.load()
        if state["trial"] is not None:
            raise SlotError("a trial is running: confirm it or roll it back before writing a new image")
        image = Path(image)
        if not image.is_file():
            raise SlotError("the image does not exist")
        digest = sha256_of(image)
        if len(expected_sha256) != 64 or digest != expected_sha256.lower():
            raise SlotError("the SHA-256 of the image is not the expected one; nothing was written")
        idle = other(str(state["active"]))
        self.backend.write_image(idle, image)
        bad = state["bad"]
        assert isinstance(bad, list)
        if idle in bad:
            bad.remove(idle)
        state["staged"] = {"slot": idle, "sha256": digest}
        self._note(state, "staged", now, slot=idle)
        self._save(state)
        return {"staged": idle, "sha256": digest}

    def begin_trial(self, *, now: float, timeout_seconds: float = DEFAULT_TRIAL_SECONDS) -> dict[str, object]:
        """Tell the boot loader to try the staged slot once. The default boot entry stays the active slot."""
        self._need_enabled()
        if not (MIN_TRIAL_SECONDS <= timeout_seconds <= MAX_TRIAL_SECONDS):
            raise SlotError(f"the time limit must be between {MIN_TRIAL_SECONDS} and {MAX_TRIAL_SECONDS} seconds")
        state = self.load()
        if state["trial"] is not None:
            raise SlotError("a trial is already running")
        staged = state["staged"]
        if staged is None:
            raise SlotError("no image was written to the idle slot")
        assert isinstance(staged, dict)
        slot = str(staged["slot"])
        if slot in state["bad"]:  # type: ignore[operator]
            raise SlotError("that slot failed its trial; write a new image first")
        active = str(state["active"])
        self.backend.set_trial(slot, active)
        state["trial"] = {"slot": slot, "deadline": now + float(timeout_seconds), "timeout": float(timeout_seconds), "rebooted": False}
        self._note(state, "trial", now, slot=slot)
        self._save(state)
        return {"trial": slot, "deadline": now + float(timeout_seconds)}

    def mark_reboot(self, *, now: float) -> dict[str, object]:
        """Call right before the reboot that asks the boot loader for the trial (`reboot "0 tryboot"`): the time limit starts now, and an old-slot boot
        after this point means the new slot did not start."""
        self._need_enabled()
        state = self.load()
        trial = state["trial"]
        if trial is None:
            raise SlotError("no trial is running")
        assert isinstance(trial, dict)
        if now > float(trial["deadline"]):
            return self._fail(state, now, "the time limit passed before the reboot")
        trial["rebooted"] = True
        trial["deadline"] = now + float(trial.get("timeout", DEFAULT_TRIAL_SECONDS))
        self._note(state, "reboot", now, slot=trial["slot"])
        self._save(state)
        return {"reboot": trial["slot"], "deadline": trial["deadline"]}

    def confirm(self, *, now: float) -> dict[str, object]:
        """The trial slot reported healthy in time: it becomes the default. The only place the default changes."""
        self._need_enabled()
        state = self.load()
        trial = state["trial"]
        if trial is None:
            raise SlotError("no trial is running")
        assert isinstance(trial, dict)
        if now > float(trial["deadline"]):
            return self._fail(state, now, "the health report came after the time limit")
        slot = str(trial["slot"])
        self.backend.set_default(slot)
        state["active"] = slot
        state["trial"] = None
        state["staged"] = None
        self._note(state, "confirmed", now, slot=slot)
        self._save(state)
        return {"active": slot}

    def rollback(self, *, now: float, reason: str = "rolled back by the operator") -> dict[str, object]:
        """Give up the trial: the default boot entry was never changed, so the old slot keeps booting. The tried slot is marked bad."""
        self._need_enabled()
        state = self.load()
        if state["trial"] is None:
            raise SlotError("no trial is running")
        return self._fail(state, now, reason)

    def _fail(self, state: dict[str, object], now: float, reason: str) -> dict[str, object]:
        trial = state["trial"]
        assert isinstance(trial, dict)
        slot = str(trial["slot"])
        active = str(state["active"])
        self.backend.clear_trial(active)
        bad = state["bad"]
        assert isinstance(bad, list)
        if slot not in bad:
            bad.append(slot)
        state["trial"] = None
        state["staged"] = None
        self._note(state, "failed", now, slot=slot, reason=reason)
        self._save(state)
        return {"active": active, "failed": slot, "reason": reason}

    def evaluate(self, *, now: float, booted: str, healthy: bool) -> dict[str, object]:
        """Called by whatever runs at boot with the slot that actually started and whether it is healthy.

        * the trial slot started and is healthy in time -> confirm; unhealthy or late -> fail it;
        * the OLD slot started after the reboot for the trial was marked -> the board fell back (power cut, reset, loader refused): the trial failed;
        * the OLD slot started before that reboot -> nothing happened yet;
        * the trial deadline passed with nothing reported -> fail it.
        Without an open trial nothing changes.
        """
        self._need_enabled()
        if booted not in SLOTS:
            raise SlotError(f"unknown slot {booted!r}")
        state = self.load()
        trial = state["trial"]
        if trial is None:
            return {"active": state["active"], "unchanged": True}
        assert isinstance(trial, dict)
        if booted == trial["slot"]:
            if healthy and now <= float(trial["deadline"]):
                return self.confirm(now=now)
            return self._fail(state, now, "the new system did not report healthy in time" if not healthy else "the health report came after the time limit")
        if now > float(trial["deadline"]):
            return self._fail(state, now, "the time limit passed with the new slot not reporting")
        if booted == state["active"] and trial.get("rebooted"):
            return self._fail(state, now, "the board came back on the old slot before the new one reported healthy")
        return {"active": state["active"], "unchanged": True}


# ---- command line --------------------------------------------------------------------------------
def _build(args: argparse.Namespace) -> SlotManager:
    state = Path(args.state)
    if args.backend == "sim":
        backend: Backend = SimulatedBackend(Path(args.dir))
    else:
        def writer(slot: str, image: Path) -> None:
            raise SlotError(f"writing the partition of slot {slot} is done by the installer of the board, not by this tool (image {image.name})")

        backend = AutobootBackend(Path(args.dir), writer)
    return SlotManager(state, backend)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    parser.add_argument("--state", required=True, help="the JSON state file")
    parser.add_argument("--backend", choices=("sim", "autoboot"), default="sim")
    parser.add_argument("--dir", required=True, help="sim: the folder of the slot files; autoboot: the boot partition folder that holds autoboot.txt")
    parser.add_argument("--now", type=float, default=None, help="the time in seconds (default: the clock); for the checks")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    sub.add_parser("plan")
    stage = sub.add_parser("stage")
    stage.add_argument("image")
    stage.add_argument("--sha256", required=True)
    trial = sub.add_parser("begin-trial")
    trial.add_argument("--timeout", type=float, default=DEFAULT_TRIAL_SECONDS)
    sub.add_parser("mark-reboot")
    sub.add_parser("confirm")
    rollback = sub.add_parser("rollback")
    rollback.add_argument("--reason", default="rolled back by the operator")
    evaluate = sub.add_parser("evaluate")
    evaluate.add_argument("--booted", required=True, choices=SLOTS)
    evaluate.add_argument("--healthy", action="store_true")
    args = parser.parse_args(argv)
    import time

    now = time.time() if args.now is None else args.now
    manager = _build(args)
    try:
        if args.command == "status":
            result = manager.status()
        elif args.command == "plan":
            result = manager.plan()
        elif args.command == "stage":
            result = manager.stage(Path(args.image), expected_sha256=args.sha256, now=now)
        elif args.command == "begin-trial":
            result = manager.begin_trial(now=now, timeout_seconds=args.timeout)
        elif args.command == "mark-reboot":
            result = manager.mark_reboot(now=now)
        elif args.command == "confirm":
            result = manager.confirm(now=now)
        elif args.command == "rollback":
            result = manager.rollback(now=now, reason=args.reason)
        else:
            result = manager.evaluate(now=now, booted=args.booted, healthy=args.healthy)
    except SlotError as error:
        print(f"AB_SLOTS=REFUSED {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
