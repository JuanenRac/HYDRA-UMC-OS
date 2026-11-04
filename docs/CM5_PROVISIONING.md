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
| `print_once` (`--print-once`, `HYDRA_UMC_PRINT_ONCE=1`, or `print_once = true` in `/etc/hydra-umc/provisioning.conf`) | `gateway_env.py`, `wifi_provision.py`, `generate_secrets.py` | off by default: a generated password goes to a file only root can read (0600, in a folder with mode 0700) and the tool prints that path, never the value. On makes the tool also print the value once, when it creates it, for a device without a screen |
| `npm_scripts` (`HYDRA_UMC_NPM_SCRIPTS=on`, or `npm_scripts = on` in `/etc/hydra-umc/provisioning.conf`) | build hooks of the server and the dashboard | off by default: the dependencies are installed with `--ignore-scripts`, so a changed dependency cannot run code as root during an install. Turn it on only for a program whose build needs the install scripts; the build runs as the user who owns the checkout |
| `--join-delay-seconds` (`HYDRA_UMC_JOIN_DELAY_S`) | `wifi_provision.py` | seconds between the answer to the phone and the moment the setup network goes down to join the chosen network (default 3). The answer is always sent first; the result is read at `/status` or on the page after the phone reconnects to the setup network |
| `diagnostics.storage_path` | the agent configuration (`config/hydra-umc-os.example.json`) | the folder whose volume the disk check measures (default: the working folder of the service, `/var/lib/hydra-umc`) |
| `HYDRA_UMC_RECOVERY_ROOT` | `cm5_recovery.sh` | another root instead of `/` (the tests use it; a device never sets it) |
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

`cm5_recovery.sh backup` saves what is installed, not a fixed list: the configuration and state folders (`/etc/hydra-umc*`, `/var/lib/hydra-umc*`), the `data` folder of every program in `/opt/hydra-umc`, the units `hydra-umc-*.service` and the polkit rules of HYDRA-UMC. SQLite databases are copied with the SQLite backup API (a consistent copy, even while a service writes), never as the live file. `restore` refuses an archive with a path outside that scope, stops every running `hydra-umc-*` service and removes stale `-wal`/`-shm` files before it extracts.

For the public staged installation order of all CM5-capable ecosystem
repositories, read [CM5 ecosystem deployment](CM5_ECOSYSTEM_DEPLOYMENT.md).

## Where the generated passwords are, and how to rotate them

| Password | File (root only, 0600; never versioned) | Read it | Rotate it |
| --- | --- | --- | --- |
| MQTT credentials of the machine bridges | `/etc/hydra-umc/credentials/gateway-bridges.txt` (the same values are in `gateway.env`) | `sudo cat /etc/hydra-umc/credentials/gateway-bridges.txt` | move `gateway.env` and that file out of the way, run `install_industrial_gateway.sh --apply` again and give each bridge its new password |
| Password of the first administrator of HYDRA-UMC-SERVER (`HYDRA_UMC_BOOTSTRAP_ADMIN_PASSWORD`) | `/etc/hydra-umc/credentials/server-admin.txt` (the same value is in `server.env`; `--admin-credentials-file` changes the path) | `sudo cat /etc/hydra-umc/credentials/server-admin.txt` | after the first sign-in change it in the application and remove the variable from `server.env`; to generate a new one before the first start, move `server.env` and that file away and run `install_server.sh --apply` again |
| Wi-Fi setup network password and setup code | `/var/lib/hydra-umc/wifi-provision/credentials.json` | `sudo cat /var/lib/hydra-umc/wifi-provision/credentials.json` | stop `hydra-umc-wifi-provision`, move that file away, start it again |

`generate_secrets.py` stops (exit code 1, nothing written) when `server-admin.txt` already exists or is a link, so a password is never lost nor placed in a file somebody else controls. An installation made before this setting keeps its files as they are (an existing file is never overwritten) and a mode more open than 0600 is corrected at the next run. To keep the old
behaviour (the password printed once in the journal) switch `print_once` on before the first start; a password that was already printed in an older journal stays there, so rotate it.
