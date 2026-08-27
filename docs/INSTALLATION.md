# Installation design

For the complete public CM5 procedure, identity, SSH policy, visual boot
handoff, and recovery sequence, read [CM5 provisioning](CM5_PROVISIONING.md).

## Target

The initial target is a Raspberry Pi CM5 using a documented Raspberry Pi OS
ARM64 release. Development images and production images must record the base
release, kernel, firmware, installed HYDRA-UMC package versions, and SDK range.

## Intended installation sequence

1. Start from an official Raspberry Pi OS image.
2. Apply OS updates through normal supported mechanisms.
3. Install `hydra-umc-platform-base` from a trusted repository or local artifact.
4. Place validated non-secret configuration in `/etc/hydra-umc/`.
5. Enable `hydra-umc-agent.service`.
6. Reboot and inspect `HealthReport` before enabling optional profiles.

## Profiles

`base` contains the agent and diagnostics. `control` adds the CM5-MCU adapter
and local operation UI. `vision`, `industrial`, `lab`, and `fleet` are opt-in
extensions. No profile installs a feature merely because hardware might exist.

## Non-goals

This project must not install custom kernels, replace `apt`, alter official
firmware blindly, or treat a successful package install as a successful node.
