<!--
HYDRA-UMC-OS - CM5 deployment sequence
Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
GPL-3.0 - see LICENSE
-->

# HYDRA-UMC-OS CM5 deployment sequence

This is the operational procedure for turning an official Raspberry Pi OS
Lite ARM64 installation into a **HYDRA-UMC-OS BASE** node. It deliberately
does not replace Raspberry Pi OS, its kernel, firmware, drivers, networking or
package manager. HYDRA-UMC adds validated configuration, services, health,
diagnostics and ecosystem packages in controlled phases.

Run one gate at a time. A failed gate is a stop condition: preserve its logs,
fix the cause and repeat that gate. Do not compensate by enabling later
services.

## 0. Prepare before powering the CM5

1. Confirm the CM5 carrier/IO board, power supply, storage and cooling are
   present and compatible. Do not attempt deployment on an incomplete or
   unstable carrier.
2. Download the current official Raspberry Pi OS Lite **ARM64** image and
   verify its checksum using the official Raspberry Pi release information.
3. Prepare an administrator SSH public key. Keep private keys, Wi-Fi
   credentials, API tokens and service secrets outside Git.
4. Keep local checkouts of `HYDRA-UMC-OS`, `HYDRA-UMC-SDK` and
   `HYDRA-UMC-SERVER` ready on the workstation. Record their commit IDs in
   the deployment evidence.

**Gate 0:** the physical platform and image source are known; no software has
been installed on the CM5 yet.

## 1. Create the Raspberry Pi OS base

Use Raspberry Pi Imager's supported advanced configuration (or the supported
first-boot equivalent) to set:

On a Windows host, Raspberry Pi Imager may not detect the CM5 at all (a
missing driver on the boot-ROM stage, or an unreliable second-stage
handoff) - see
[CM5_WINDOWS_HOST_FLASHING.md](../docs/CM5_WINDOWS_HOST_FLASHING.md) for
the real, verified troubleshooting sequence (driver binding, and a
WSL2 + usbipd + real `rpiboot` fallback) before assuming the hardware
itself is at fault.

| Setting | Required value |
| --- | --- |
| Image | Official Raspberry Pi OS Lite ARM64 |
| Visible device name | `HYDRA-UMC-TEST` |
| Linux hostname / DNS name | `hydra-umc-test` |
| Administrator account | `hydra-umc` |
| Network | Local Wi-Fi only when its credentials are already known |
| Remote access | SSH enabled with the administrator public key |

Define the administrator password interactively in Imager or on the device;
never write it into a repository, shell script, log or support ticket. SSH
without typing a password means **key-based SSH**, not anonymous or
password-only remote access. Verify a second key-based SSH session before
disabling password authentication, following
[ssh_hardening.md](ssh_hardening.md).

If the target Wi-Fi is unknown at imaging time, do not invent credentials. The
optional HYDRA-UMC Wi-Fi provisioning access-point fallback is installed in
phase 3 and must receive a unique per-device password before it is enabled.

**Gate 1:** boot succeeds, the expected hostname and `hydra-umc` account are
visible, and key-based SSH works from the workstation.

## 2. Capture the clean-device evidence

On the CM5, apply the normal Raspberry Pi OS updates and reboot once. Record:

- OS release and image checksum;
- `uname -a`, kernel and Raspberry Pi firmware revision;
- CM5 serial number, carrier/IO-board revision, storage and cooling details;
- network interface names and the successful SSH key fingerprint.

Archive this evidence off-device. It is the recovery baseline and makes later
hardware-specific failures reproducible.

**Gate 2:** the device has rebooted cleanly after official OS updates and the
baseline evidence is saved.

## 3. Install HYDRA-UMC-OS BASE, first as a dry run

Copy or clone the OS and SDK repositories beside each other on the CM5. From
the `HYDRA-UMC-OS` checkout, run the read-only gate first:

```bash
python3 provisioning/preflight_cm5.py --sdk-root ../HYDRA-UMC-SDK
sudo bash provisioning/first_boot.sh
```

Both commands must report success before applying changes. Review the dry-run
output, then apply the first-boot configuration explicitly:

```bash
sudo bash provisioning/first_boot.sh --apply
sudo bash provisioning/install_cm5_base.sh --apply
```

The BASE profile installs only the constrained OS agent, configuration and
diagnostics. It does **not** enable motion, MCU, CAN, URTC, cameras, Hailo or
other hardware profiles. Services remain an explicit activation decision.

For the optional Wi-Fi access-point fallback, first create a root-only
per-device secret, then enable the service only when it is actually required:

```bash
sudo install -m 0600 -o root -g root /dev/null /etc/hydra-umc/wifi-provision.env
sudo sh -c 'printf "%s\\n" "HYDRA_UMC_AP_PASSWORD=<unique-device-password>" >> /etc/hydra-umc/wifi-provision.env'
sudo systemctl enable --now hydra-umc-wifi-provision
```

**Gate 3:** preflight, reviewed dry run and BASE installation succeed without
enabling a physical-control profile.

## 4. Verify, reboot and create a recovery point

Run the installed agent and runtime verifier, archive their JSON and journal
output, then reboot and repeat the checks:

```bash
hydra-umc-agent describe
hydra-umc-agent health
sudo bash provisioning/verify_cm5_runtime.sh
sudo reboot
```

After the reboot, take the scoped recovery archive:

```bash
sudo bash provisioning/cm5_recovery.sh backup /root/hydra-umc-state.tar.gz --apply
```

Recovery only restores HYDRA-UMC-managed configuration, state and units, and
leaves services stopped for review. It must never overwrite arbitrary
Raspberry Pi OS files or user data.

**Gate 4:** health, storage, network, temperature reporting and reboot are
verified; the recovery archive exists off-device as well as locally.

## 5. Install the local control plane, but keep it loopback-only

Install a supported ARM64 Node.js runtime (20 or newer), create
`/etc/hydra-umc/server.env` locally from `server.env.example`, and keep its
secrets root-readable only. Then install Server:

```bash
sudo bash provisioning/install_cm5_base.sh --apply --with-server
```

Enable its service only after reviewing the installed files and configuration:

```bash
sudo bash provisioning/install_cm5_base.sh --apply --with-server --enable-services
curl --fail http://127.0.0.1:3000/api/hydra-info
```

`HYDRA-UMC-SERVER` is the API boundary. Studio, mobile apps, Watch and other
clients access Server; they do not receive direct CAN, GPIO or motion access.
The local UI endpoint is `http://localhost:3000`. Optional text-only Voice UI
remains loopback-only (`127.0.0.1:8091`) and is not a substitute for the future
Hailo STT/TTS stack.

**Gate 5:** Server survives a reboot, reports healthy locally and has no
unintended public network exposure.

## 6. Apply visual branding only after recovery is proven

The canonical asset is `HYDRA_UMC_SPLASHSCREEN.svg`. The boot implementation
uses a reversible Plymouth theme; native boot splash support may require a
locally generated raster fallback because Plymouth does not guarantee animated
SVG playback. Test the installer in dry-run mode first:

```bash
sudo bash provisioning/install_splashscreen.sh
```

Apply it only after a successful BASE reboot and recovery test. Keep the source
SVG with the project; do not claim boot animation behaviour that has not been
observed on the actual CM5 display path.

**Gate 6:** branding is cosmetic, reversible and cannot block a normal boot.

## 7. Enable hardware-dependent profiles one at a time

The following are separate physical-validation gates, not a bulk install:

1. **CONTROL:** CM5-to-MCU/URTC transport, version/HELLO, capabilities, CRC,
   timeouts, heartbeat, SAFE_STOP and no-motion failure behaviour.
2. **VISION:** camera permissions, stable device paths, cooling, power and one
   camera at a time.
3. **HAILO-8 / HAILO-10:** PCIe enumeration, exact model, official compatible
   runtime, cooling and one inference validation before enabling any service.
4. **Bridges:** ROS2, OpenPnP, Printer3D, CNC and Laser remain offline or
   simulation-only until their real machine-specific interlocks are tested.

Record an evidence bundle for every enabled capability: exact hardware,
versions, commands, logs, result, recovery action and operator approval. A
failed capability leaves the BASE/Server platform available; it must not turn
into a partial control deployment.

## Operational boundary

Host and WSL tests prove syntax, contracts and installer logic. They do not
prove CM5 boot, Wi-Fi, temperature, storage, PCIe, cameras, actuators,
emergency stop or electrical safety. A project is promoted only when the
relevant real-device evidence exists.

Related reference documents:

- [CM5 first boot checklist](../docs/CM5_FIRST_BOOT_CHECKLIST.md)
- [CM5 ecosystem deployment phases](../docs/CM5_ECOSYSTEM_DEPLOYMENT.md)
- [CM5 software readiness](../docs/CM5_SOFTWARE_READINESS.md)
- [CM5 provisioning reference](../docs/CM5_PROVISIONING.md)
