<!--
HYDRA-UMC-OS - CM5 first boot checklist
Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
GPL-3.0 - see LICENSE
-->

# CM5 first boot checklist

Use this checklist alongside the complete
[CM5 deployment sequence](../provisioning/CM5_DEPLOYMENT_SEQUENCE.md). It is
a BASE-platform checklist, not authorisation to enable motion or peripherals.

## Before power-on

- [ ] CM5, carrier/IO board, storage, cooling and power supply are fitted and
      their revisions have been recorded.
- [ ] The official Raspberry Pi OS Lite ARM64 image and checksum are recorded.
- [ ] Raspberry Pi Imager is configured for hostname `hydra-umc-test`, account
      `hydra-umc`, local Wi-Fi when known and key-based SSH.
- [ ] The administrator password, Wi-Fi password, API tokens and private SSH
      key are not stored in Git or copied into deployment notes.

## First Raspberry Pi OS boot

- [ ] The device boots normally and identifies as `HYDRA-UMC-TEST` /
      `hydra-umc-test`.
- [ ] A key-based SSH session works; a second independent session is tested
      before password authentication is disabled.
- [ ] OS release, image checksum, kernel, firmware, serial number, carrier
      revision, storage, cooling and network-interface names are recorded.
- [ ] Official Raspberry Pi OS updates are applied and the device reboots
      cleanly.

## HYDRA-UMC-OS BASE gate

- [ ] `preflight_cm5.py` passes with the adjacent SDK checkout.
- [ ] `first_boot.sh` has been reviewed in dry-run mode before `--apply`.
- [ ] `install_cm5_base.sh --apply` completes without enabling control,
      vision, camera, CAN, MCU, URTC or Hailo services.
- [ ] `hydra-umc-agent describe`, `hydra-umc-agent health` and
      `verify_cm5_runtime.sh` are archived.
- [ ] The device reboots and reports healthy again.
- [ ] A scoped HYDRA-UMC recovery archive is created and copied off-device.

## Server gate

- [ ] `/etc/hydra-umc/server.env` is created locally with restrictive
      permissions and no secret was committed to Git.
- [ ] Server responds at `http://127.0.0.1:3000/api/hydra-info` after a reboot.
- [ ] UI clients use Server rather than direct hardware interfaces.

## Explicitly deferred

- [ ] Control/MCU/URTC/CAN, cameras, Hailo, actuators and bridge machines are
      still disabled until each has its own physical evidence and recovery
      test.
