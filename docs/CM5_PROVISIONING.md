<!--
=============================================================================
HYDRA-UMC-OS - CM5 Raspberry Pi OS provisioning guide
Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
CC BY-SA 4.0 - see LICENSE.md
=============================================================================
-->

# Converting Raspberry Pi OS Lite into HYDRA-UMC-OS

HYDRA-UMC-OS is a reproducible product layer over the current official
Raspberry Pi OS Lite ARM64 image. It does not replace the Raspberry Pi kernel,
APT, systemd, NetworkManager, or official device APIs.

Read [CM5 software readiness](CM5_SOFTWARE_READINESS.md) before applying the
first-board sequence. It separates validated host-side software from the
physical evidence still required on a real CM5.

## Initial node identity

| Item | Value | Reason |
| --- | --- | --- |
| Visible node name | `HYDRA-UMC-TEST` | Human-facing identity. |
| Technical hostname | `hydra-umc-test` | DNS and mDNS-compatible hostname. |
| Administrator | `hydra-umc` | Interactive account with controlled sudo access. |
| Service account | `hydra-umc-agent` | Non-login least-privilege account for the read-only agent. |

Never place a password, Wi-Fi secret, private SSH key, or access token in this
repository. Set the administrator password locally with `passwd hydra-umc`.

## Deployment sequence

The full, gated, step-by-step procedure lives in one place only -
[`provisioning/CM5_DEPLOYMENT_SEQUENCE.md`](../provisioning/CM5_DEPLOYMENT_SEQUENCE.md)
- to avoid two documents describing the same real sequence at different
granularity and drifting apart. On a Windows host, also read
[CM5_WINDOWS_HOST_FLASHING.md](CM5_WINDOWS_HOST_FLASHING.md) first - real,
verified driver/USB troubleshooting that document's own step 1 doesn't
cover. Use the
[first boot checklist](CM5_FIRST_BOOT_CHECKLIST.md) alongside it.

## SSH policy

Use public-key SSH. Disable `PasswordAuthentication` and root login only after
a second, independent key-based login has succeeded. Maintain local console
access during the first hardening change.

## Boot identity

`images/HYDRA_UMC_SPLASHSCREEN.svg` is the canonical animated HYDRA-UMC-OS
visual identity. The early firmware/kernel phase cannot render animated SVG.
It is therefore preserved for the post-boot visual handoff; a Plymouth theme
may use a generated static fallback only when required by the boot stack.

## Rollback and recovery

Every provisioning script defaults to dry-run and requires `--apply` for a
change. Do not enable movement, MCU, CAN, or URTC control during first boot.
If a service fails, disable it with `systemctl disable --now hydra-umc-agent`
and recover through the local console.

For the public staged installation order of all CM5-capable ecosystem
repositories, read [CM5 ecosystem deployment](CM5_ECOSYSTEM_DEPLOYMENT.md).
