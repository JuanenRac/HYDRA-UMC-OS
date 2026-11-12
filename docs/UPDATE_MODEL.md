<!--
=============================================================================
HYDRA-UMC-OS - Update model
Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
GPL-3.0-or-later - see LICENSE
=============================================================================
-->

# Update model

Raspberry Pi OS, HYDRA-UMC packages, Hailo runtimes/models, and MCU/URTC
firmware have separate update channels. They are never represented as one
opaque binary.

HYDRA-UMC artifacts require a manifest with version, compatibility, hash, and
signature. Before any future CM5 deployment flow changes a checkout, its
candidate manifest must validate, identify the same project, and not declare a
lower version than the installed manifest. The updater checks the target device
and dependency range, installs the candidate, restarts only required services,
and evaluates health. A failed health check must surface an actionable fault
and use rollback where supported. This is a deployment contract; it does not
claim that a rollback has been exercised on a CM5 before hardware testing.

**Status.** The paragraph above describes the target contract. Today no component
implements it end to end: the installers (`provisioning/install_*.sh`) copy a
checkout into place and restart its unit without a signed manifest, a
dependency-range check, a health gate or an automatic rollback, and
`tools/package_component.py` only packs and verifies signed component archives.
Read it as the direction of the work, not as a description of what runs on a
device.

**Built, not yet on a device.** `tools/deploy_release.py` is the core of that flow, tested in
temporary folders: it verifies a signed package, refuses the same or an older version, installs it
as a numbered release, switches `current`, runs the restart and health commands of
`<root>/deploy.json`, puts the earlier release back (exit status 3) when either fails, and offers
`rollback`, `prune` and `status`. No installer calls it yet and no rollback has been exercised on a
CM5.

**Two slots, built and checked on the host only.** `provisioning/ab_slots.py` is the state machine of a
two-slot (A/B) system image: an image is written to the idle slot after its SHA-256 matches, the boot
loader is asked to try it once (the Raspberry Pi `tryboot` entry of `autoboot.txt`), and the new system has
a time limit to report healthy. Only a healthy report in time (`confirm`) changes the default boot entry; a
late or missing report, a slot that never started, or a board that fell back to the old slot marks the tried
slot bad until a new image is written to it, so a bad image can never become the default. It decides and
records; a backend carries the decision out (`SimulatedBackend` for the checks, `AutobootBackend` for the
text of `autoboot.txt`), and it never runs `dd` or `reboot` itself. Every command that changes something is
refused unless `HYDRA_UMC_AB_SLOTS=1` is set (off by default), and a damaged state file is refused, not
repaired. `tools/verify_ab_slots.py` proves it with both backends and a seeded random walk. The image
builder does not yet produce two-slot images, no installer or unit calls it, and it has not run on a board:
that needs a CM5 with a boot loader that supports `tryboot_a_b`.

Firmware retains its own tested update and recovery process. Do not couple a
Raspberry Pi OS upgrade to a firmware change without a maintenance plan.
