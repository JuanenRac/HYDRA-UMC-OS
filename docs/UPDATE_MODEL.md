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

Firmware retains its own tested update and recovery process. Do not couple a
Raspberry Pi OS upgrade to a firmware change without a maintenance plan.
