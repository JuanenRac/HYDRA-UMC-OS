<!--
=============================================================================
HYDRA-UMC-OS - CM5 software readiness boundary
Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
CC BY-SA 4.0 - see LICENSE.md
=============================================================================
-->

# CM5 software readiness boundary

This document records what has been verified without physical CM5 hardware
and where that verification stops. HYDRA-UMC-OS remains FUNCTIONAL until the
listed physical gates have evidence from the actual target board.

## Closed software baseline

- The BASE and CONTROL deployment plans validate identity, configuration,
  profiles, OS-agent deployment, Server deployment and SDK v1 compatibility
  before any system change.
- `install_cm5_base.sh` performs the reviewed order in dry-run by default.
  `--apply`, Server installation and service activation are separate explicit
  choices.
- The agent runs as the non-login `hydra-umc-agent` account with root-owned
  code/configuration and a limited writable state directory.
- Server installation requires a supported Node.js 20+ runtime, locked
  dependencies and a locally created restricted environment file.
- `verify_cm5_runtime.sh` is read-only: it checks service state, ownership,
  agent health and, when requested, the local Server discovery endpoint.
- `cm5_recovery.sh` backs up or restores only HYDRA-UMC configuration/state;
  restore leaves services stopped for explicit review.

Host and WSL validation covers the agent unit tests, invalid preflight plans,
the non-versioning build check, CI baseline and shell syntax. It does not
prove board-specific drivers, PCIe, storage, wireless, boot firmware,
temperature or external peripherals.

## First-board gate

On a CM5 with official Raspberry Pi OS Lite ARM64, first run:

```bash
python3 provisioning/preflight_cm5.py --sdk-root ../HYDRA-UMC-SDK
sudo bash provisioning/install_cm5_base.sh
```

After reviewing the dry run and recording image/kernel/firmware/serial
evidence, apply BASE explicitly:

```bash
sudo bash provisioning/install_cm5_base.sh --apply --enable-services
sudo bash provisioning/verify_cm5_runtime.sh
sudo bash provisioning/cm5_recovery.sh backup /root/hydra-umc-state.tar.gz --apply
```

Install Server only after its local secret file and supported Node.js runtime
have been prepared, then repeat runtime verification with `--with-server`.

## Deliberately not closed without hardware

- Boot splash behavior and recovery on the real CM5 boot chain.
- Wi-Fi/SSH resilience on real hardware. The AP-mode provisioning state
  machine itself is real and unit-tested against a fake NetworkManager
  (`tools/verify_wifi_provision.py`), but a real hotspot actually
  broadcasting, a real phone joining it, and real recovery from a dropped
  signal are all still unverified without a real WiFi radio.
- Actual storage thresholds and thermal readings.
- CM5-to-MCU/URTC discovery, heartbeat, timeout and safety rejection.
- PCIe, camera, Hailo-8/Hailo-10 runtime compatibility and power/cooling.
- Service restart behavior under real power loss and local-console recovery.

Do not enable CONTROL, VISION, CAN, MCU, URTC or Hailo solely because the
software baseline passes on a host. Each requires its own physical evidence.
