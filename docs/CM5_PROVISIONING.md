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

## Local screen: HDMI, DSI or none

The HDMI kiosk of this repository (X11 and Chromium) and the app of
HYDRA-UMC-DSI (cage and Flutter) both want `tty1` and the seat of the console,
so only one of them is installed and enabled at a time. The choice is one
setting, `HYDRA_LOCAL_SCREEN`, read by `provisioning/local_screen.sh`:

| Value | Effect |
| --- | --- |
| `hdmi` (default) | `provisioning/install_kiosk.sh` installs the HDMI kiosk; the DSI app, if installed, is switched off |
| `dsi` | nothing is installed here; the autologin put on `tty1` is taken back and `kiosk/install_kiosk.sh` of HYDRA-UMC-DSI owns the screen |
| `none` | no local screen: neither of them takes `tty1`, which goes back to the console login |

The value is read from, first one wins, the environment variable
`HYDRA_LOCAL_SCREEN` (this run only), the line `HYDRA_LOCAL_SCREEN=<value>` of
`/etc/hydra-umc/local-screen.conf` (`HYDRA_LOCAL_SCREEN_FILE` names another
file) and then `hdmi`. `sudo provisioning/install_kiosk.sh --apply --screen dsi`
saves the choice in that file. A value that is none of the three stops the
installer: nothing is installed on a guess. When the saved choice is `dsi` or
`none`, the profile of the kiosk account no longer starts X.

The kiosk session runs as its own account, `hydra-umc-kiosk` (no sudo, no
password, no SSH key); `HYDRA_KIOSK_USER` names another existing account, which
is then the operator's decision, and `HYDRA_KIOSK_ALLOW_VT_SWITCH=1` leaves the
switch between virtual terminals alone (the kiosk blocks it by default).

The earlier second HDMI kiosk (a Qt 6 application in the main repository) was
retired: this one is the only HDMI kiosk of the ecosystem.
`tools/verify_kiosk_installer.py` tests the installer against stubs and runs in
the CI. It has not run on a real CM5.

## Settings of the installers

Every installer is a dry run until `--apply`. The settings that change what the
installers write are:

| Setting | Used by | Meaning |
| --- | --- | --- |
| `HYDRA_LOCAL_SCREEN`, `HYDRA_LOCAL_SCREEN_FILE` | `install_kiosk.sh` | which local screen (see above) |
| `HYDRA_KIOSK_USER`, `HYDRA_KIOSK_ALLOW_VT_SWITCH` | `install_kiosk.sh` | account of the kiosk session and virtual-terminal switching |
| `HYDRA_GATEWAY_ENV` | `install_industrial_gateway.sh` | the file the gateway reads (default `/etc/hydra-umc/gateway.env`) |
| `MQTT_TLS_DIR` | `gateway_env.py` | folder with the certificate of the broker (`server.pem`, `server.key`, made by `hydra_mqtt_tls.sh init`) |
| `HYDRA_UMC_NEW_INSTALL_TLS=off` | `install_industrial_gateway.sh` | on a new installation, skip the certificate authority (the broker then needs `MQTT_TLS_DIR` from elsewhere) |
| `HYDRA_UMC_LOCAL_TECHNICIAN_RESULT_KEY_FILE` | `install_local_technician.sh` | key that signs the technician's results; `--no-signing` switches it off |
| `HYDRA_UMC_SERVER_PORT` | `provisioning/server.env.example` | port of HYDRA-UMC-SERVER on this node (default 3000) |
| `--audit`, `--journal` | `install_local_technician.sh`, `install_node_healing.sh` | the append-only audit journal of the technician and the journal of the watchdog; both are on by default in the installers and the flags are still accepted |
| `--profile` | `preflight_cm5.py` | the profile file to check (default `config/profiles/base.json`) |

Not run on a real CM5: these are written and tested against stubs.

## Rollback and recovery

Every provisioning script defaults to dry-run and requires `--apply` for a
change. Do not enable movement, MCU, CAN, or URTC control during first boot.
If a service fails, disable it with `systemctl disable --now hydra-umc-agent`
and recover through the local console.

For the public staged installation order of all CM5-capable ecosystem
repositories, read [CM5 ecosystem deployment](CM5_ECOSYSTEM_DEPLOYMENT.md).
