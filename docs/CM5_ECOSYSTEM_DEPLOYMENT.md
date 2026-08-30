<!--
HYDRA-UMC-OS - CM5 ecosystem deployment phases
Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
CC BY-SA 4.0 - see LICENSE.md
-->

# CM5 ecosystem deployment phases

The CM5 must not receive every CM5-targeted repository on its first day. Each
phase has an explicit verification gate and may be rolled back independently.

## Phase 0 — Raspberry Pi OS Lite base

Install the official ARM64 Lite image, local Wi-Fi, key-based SSH, identity,
OS agent and its read-only health checks. Run the preflight, reviewed dry-run,
runtime verification and scoped backup in that order. No motion, CAN, Hailo,
UI or service profile is enabled in this phase. See
[CM5 software readiness](CM5_SOFTWARE_READINESS.md) for the precise boundary
between host-validated software and physical validation.

## Phase 1 — Local control plane

Install `HYDRA-UMC-SERVER` with its locked Node.js dependencies and a systemd
unit. Its service boundary listens on port 3000; the local UI opens
`http://localhost:3000` only after Server health, authentication and restart
behavior have been verified. `HYDRA-UMC-STUDIO`, DSI, mobile clients and CLI
remain clients of Server; they are not privileged OS services.

The bounded text-only `HYDRA-UMC-VOICE-UI` gateway may be installed as an
optional loopback companion in this phase with `--with-server --with-voice-ui`.
It does not install Hailo, STT or TTS models: Server owns the matching secret
and relays authenticated voice turns to `127.0.0.1:8091`. Verify both services
before any paired Wear client is introduced.

## Phase 2 — Observability and contracts

Install SDK contract fixtures, Telemetry Collector, DataLake and only the
minimal diagnostics integrations that pass host and CM5 checks. Each receives
a dedicated service account and only its required writable directory.

## Phase 3 — Hailo-8 perception

Before installing vision projects, confirm PCIe enumeration, cooling, power,
camera access and exact accelerator model. Install one mutually compatible
Hailo runtime stack, verify it with `hailortcli`, then enable Vision Node,
Detection HEF, Safety Zones, Visual Servoing and Vision Streamer one at a
time. Do not mix arbitrary driver, runtime and Python-wheel versions.

## Phase 4 — Hailo-10 cognition

Hailo-10 integration remains conditional on physical hardware, PCIe topology,
power budget and an official compatible runtime for the exact accelerator.
Do not install Cognitive Node, VLA Engine, Semantic Planner or Docs QA as boot
services until that verification succeeds. The Phase 1 Voice UI gateway is an
exception only because it is stdlib-only, accepts recognised text and cannot
actuate hardware; Hailo STT/TTS remains a Phase 4 gate.

## Phase 5 — optional services

Orchestration, industrial gateways, MQTT, OPC-UA, MTConnect, twin/HIL and
simulation are opt-in packages. Their resource budget and port exposure are
reviewed individually; they are never enabled merely because a repository is
CM5-capable.

## Permissions and secrets

Every service runs as its own non-login account. Hardware permissions must be
granted with narrow udev groups/rules after the actual device path is known.
Secrets are created directly on the CM5 under `/etc/hydra-umc/` with restrictive
permissions; they are not copied from Git or placed in fixtures.
