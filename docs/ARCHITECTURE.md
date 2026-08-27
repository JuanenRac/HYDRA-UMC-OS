<!--
=============================================================================
HYDRA-UMC-OS - Platform architecture specification
Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
CC BY-SA 4.0 - see LICENSE.md
=============================================================================
-->

# HYDRA-UMC-OS architecture

## Scope

HYDRA-UMC-OS is a product layer over Raspberry Pi OS ARM64 for the CM5.
The operating-system base remains maintained by Raspberry Pi and Debian.
HYDRA-UMC-OS packages and configures its own components without forking the
kernel or reimplementing native operating-system facilities.

## Layers

```text
HYDRA-UMC UI / Server / optional services
                 |
HYDRA-UMC-SDK contracts and clients
                 |
HYDRA-UMC-OS: packages, systemd, config, agent, diagnostics
                 |
Raspberry Pi OS / Linux / official device APIs
                 |
CM5 -- Hailo -- network -- MCU / URTC / CAN
```

## Component boundaries

| Component | Responsibility | Explicitly not responsible for |
| --- | --- | --- |
| `hydra-umc-agent` | Device descriptor, local health, profile application. | Motion control or UI business logic. |
| systemd units | Process lifecycle, restart and isolation. | A custom service manager. |
| config loader | Validate non-secret configuration before start. | Storing secrets in Git. |
| diagnostics | Read-only checks of disk, network, MCU and accelerators. | Bypassing safety or altering motion state. |
| updater integration | Invoke verified update workflow and report health. | Replacing official Raspberry Pi OS updates. |

## State model

`BOOTING -> DIAGNOSING -> READY` is the normal route. A non-critical failure
may produce `DEGRADED`; a missing safety prerequisite produces `INHIBITED`;
an MCU or safety fault produces `FAULT` or `SAFE_STOP`. The MCU remains the
authority for physical limits and emergency behavior.

## First public interfaces

The agent consumes `DeviceDescriptor`, `HealthReport`, `SafetyState`, and
`UpdateManifest` from HYDRA-UMC-SDK. It does not define parallel variants.
