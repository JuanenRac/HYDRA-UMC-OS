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

1. Flash the latest official Raspberry Pi OS Lite ARM64 image.
2. Configure the local Wi-Fi with Raspberry Pi's supported first-boot method.
3. Enable SSH with the administrator public key and verify a key login.
4. Record image release, kernel, firmware and CM5 serial information.
5. With a sibling `HYDRA-UMC-SDK` checkout available, run
   `python3 provisioning/preflight_cm5.py --sdk-root ../HYDRA-UMC-SDK`. It is
   read-only and must report `CM5_PREFLIGHT=PASS` before the CM5 is changed.
6. Run `sudo bash provisioning/first_boot.sh`; inspect its dry-run output.
7. Run `sudo bash provisioning/first_boot.sh --apply`.
8. Run `sudo bash provisioning/install_local_agent.sh`, inspect it, then repeat
   with `--apply`. Enable the service only after reviewing configuration.
9. Run the read-only `describe` and `health` commands; archive their JSON.
10. Optionally install local Server only after a supported ARM64 Node.js 20+
    runtime and a locally created `/etc/hydra-umc/server.env` are present:
    `sudo bash provisioning/install_cm5_base.sh --apply --with-server`.
    Add `--enable-services` only after review, then verify with
    `sudo bash provisioning/verify_cm5_runtime.sh --with-server`.
11. Before optional profiles, create a restricted recovery archive with
    `sudo bash provisioning/cm5_recovery.sh backup /root/hydra-umc-state.tar.gz --apply`.
12. Keep `control` and `vision` profiles disabled until each interface is
   physically validated.

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
