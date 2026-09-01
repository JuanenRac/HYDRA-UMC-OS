<!--
=============================================================================
HYDRA-UMC-OS - Public project overview and implementation guide
Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
CC BY-SA 4.0 - see LICENSE.md
=============================================================================
-->

<p align="center">
  <img src="images/HYDRA_UMC_BANNER.svg" alt="HYDRA-UMC-OS banner" width="100%">
</p>

<p align="center">
  🇺🇸 <b>English</b> |
  <a href="README_spa.md">🇪🇸 Español</a> |
  <a href="README_fra.md">🇫🇷 Français</a> |
  <a href="README_ita.md">🇮🇹 Italiano</a> |
  <a href="README_deu.md">🇩🇪 Deutsch</a> |
  <a href="README_zho.md">🇨🇳 简体中文</a> |
  <a href="README_jpn.md">🇯🇵 日本語</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/License-GPL%203.0-blue.svg" alt="License: GPL 3.0">
  <img src="https://img.shields.io/badge/Platform-Raspberry%20Pi%20OS%20%7C%20CM5-red.svg" alt="Platform: Raspberry Pi OS | CM5">
  <img src="https://img.shields.io/badge/Services-systemd%20%7C%20udev-orange.svg" alt="Services: systemd | udev">
  <img src="https://img.shields.io/badge/Stack-Debian%20%7C%20Python%20%7C%20Shell-blueviolet.svg" alt="Stack: Debian | Python | Shell">
</p>

# HYDRA-UMC-OS

## 🖥️ HYDRA-UMC platform layer for Raspberry Pi OS

HYDRA-UMC-OS is the installable platform layer for a HYDRA-UMC CM5 node.
It is built on Raspberry Pi OS ARM64; it does not replace Linux, the
Raspberry Pi kernel, systemd, NetworkManager, libcamera, or vendor SDKs.

Its responsibility is to provide a reproducible HYDRA-UMC device profile:
configuration, service lifecycle, local identity, diagnostics, visual
branding, and coordinated updates for HYDRA-UMC components.

## 🚧 Status

The base agent, its validated non-secret configuration, a hardened systemd
unit, and host-side tests are implemented. The agent is deliberately
read-only: production image assembly and CM5 hardware validation remain
separate release gates.

The installation preflight (`provisioning/preflight_cm5.py`) is proven
idempotent and side-effect-free by a real test - two consecutive runs
produce byte-identical output and touch zero files under this
repository - and a real, host-independent backup/rollback mechanism
(`provisioning/rollback.py`) protects the one system file
`install_local_agent.sh` unconditionally overwrites on every run. Both
are verified without root or a CM5 - see `tools/verify_preflight_idempotent.py`
and `tools/verify_rollback.py`.

**WiFi first-contact provisioning is real too** (`provisioning/wifi_provision.py`
/ `hydra-umc-wifi-provision.service`): a real NetworkManager AP-mode
fallback for a headless CM5 with no known network yet - brings up a real
hotspot (`nmcli device wifi hotspot`) an operator's phone/laptop can join
to submit the real target SSID/password through a small local HTTP form,
tears the AP down and joins the real network on success, restores it on
failure so the device is never stranded. The state machine is fully
unit-tested against a fake NetworkManager, including a real end-to-end
HTTP round-trip over a real loopback socket - see
`tools/verify_wifi_provision.py`. Installed by `install_cm5_base.sh` but
deliberately not auto-enabled, since it must not start with its own
placeholder AP password on a real, over-the-air-reachable device - see
`provisioning/CM5_DEPLOYMENT_SEQUENCE.md` section 3 for the real password
step required first.

## 🎯 Planned first milestone

1. Build a Raspberry Pi OS ARM64 profile for CM5.
2. Install `hydra-umc-platform-base` and `hydra-umc-agent`.
3. Detect CM5 interfaces and report a `DeviceDescriptor` and `HealthReport`.
4. Start only enabled services through systemd.
5. Display READY, DEGRADED, INHIBITED, or FAULT locally.

## 📂 Repository layout

<p align="center">
  <img src="images/REPOSITORY_LAYOUT.svg" alt="Visual map of the HYDRA-UMC-OS repository layout" width="100%">
</p>

| Path | Purpose |
| --- | --- |
| `docs/` | Architecture, installation, service and update specifications. |
| `image-builder/` | Official Raspberry Pi OS image-assembly boundary and reproducibility notes. |
| `packages/` | Debian package metadata for `hydra-umc-platform-base`. |
| `agent/` | Read-only Python device descriptor and health agent with unit tests. |
| `systemd/` | Hardened `hydra-umc-agent.service` and `hydra-umc-wifi-provision.service` lifecycle units. |
| `config/` | Default schemas and non-secret configuration. |

Read [the architecture](docs/ARCHITECTURE.md) before implementing code.

## 🛠️ BUILD & RUN

Use the non-versioning build check before a release build:

| Action | Windows | Linux / macOS |
|---|---|---|
| Build check (no version or CHANGELOG change) | `build-test.bat` | `./build-test.sh` |
| Run / development (when provided) | `run*.bat` or `dev*.bat` | `./run*.sh` or `./dev*.sh` |

## 🔗 Related Projects

> Canonical public ecosystem relationship map.

| Project | Relationship with HYDRA-UMC-OS |
| --- | --- |
| [HYDRA-UMC-SDK](https://github.com/JuanenRac/HYDRA-UMC-SDK) | Versioned contracts, thin clients, and conformance fixtures used by the device agent. |
| [HYDRA-UMC-SERVER](https://github.com/JuanenRac/HYDRA-UMC-SERVER) | Authenticated service boundary for the node's managed integrations. |
| [HYDRA-UMC-UPDATER](https://github.com/JuanenRac/HYDRA-UMC-UPDATER) | Artifact registry, compatibility metadata, and coordinated update workflow. |
| [HYDRA-UMC](https://github.com/JuanenRac/HYDRA-UMC) | CM5/MCU hardware and firmware platform that the OS layer configures and supervises. |
| [URTC](https://github.com/JuanenRac/URTC) | Independent tool-controller platform integrated through explicit, versioned adapters. |

**Rest of the ecosystem:** explore the seven public layers in the [JuanenRac ecosystem dashboard](https://juanenrac.github.io/JuanenRac/).

## 👤 AUTHOR
**JuanenRac** (Electro Hobby 3D)
📧 electrohobby3d@gmail.com
📺 [youtube.com/@electrohobby3d](https://youtube.com/@electrohobby3d)

## 📜 LICENSE

Code is GPL-3.0-or-later and documentation is CC BY-SA 4.0. See [LICENSE](LICENSE).

`build-test.bat` and `build-test.sh` compile or validate the project stack without incrementing `hydra-umc.project.json` or modifying `CHANGELOG.md`. They may create normal compiler output only. Existing `build*.bat`, `build*.sh`, `run*` and `dev*` scripts retain their project-specific, versioned or runtime behavior; use them when that behavior is required.