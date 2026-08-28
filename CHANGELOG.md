# Changelog

## Unreleased

### Added

- Optional loopback-only HYDRA-UMC-VOICE-UI provisioning, environment
  templates and runtime health verification. This recognised-text gateway is
  separate from the future Hailo STT/TTS stack and cannot actuate hardware.

### Fixed

- Removed a duplicate standard-library import from the diagnostics agent.
- Made the local Server installer reject an absent or unsupported Node.js/npm
  runtime instead of failing later during dependency installation.

- Aligned CM5 first-boot provisioning with the selected `hydra-umc`
  administrator identity. The agent now uses a separate non-login
  `hydra-umc-agent` account, while `/etc/hydra-umc` remains root-owned and
  restricted instead of writable by the service account.
- Reject profile files with empty, non-string or duplicate service and
  capability entries before they can be used to select a deployment profile.
- Reject zero, negative and non-finite `serve` intervals before the agent can
  enter a busy loop or fail later inside its periodic sleep.
- Provision HYDRA-UMC-SERVER under its own non-login account instead of the
  obsolete administrator identity, with root-owned application code and a
  service-owned data directory.
- Corrected the agent systemd command to use the path installed by
  `install_local_agent.sh`, and made the installed agent code root-owned so a
  compromised diagnostics process cannot replace it before a restart.
- Report a `FAULT` when a readable CM5 thermal zone reaches the configured
  maximum temperature (default `80.0`), instead of incorrectly reporting it
  as healthy. Configuration now rejects unsafe storage or temperature limits.

### Added

- Added `provisioning/preflight_cm5.py`, a read-only BASE/CONTROL gate that
  validates identity, configuration, profile, deployment contracts and the
  live OS-to-SDK schema contract before a CM5 is modified.
- Added staged `install_cm5_base.sh`, read-only installed-runtime verification,
  scoped backup/restore and negative preflight checks for invalid configuration,
  identity, SDK and Server plans.

- Host-side agent unit and deployment-contract checks, run by `build-test`
  and CI, to keep first boot, installer and systemd identity/path/permissions
  aligned.

## Documentation

### Added

- `docs/AGENT_REFERENCE.md` - full CLI/JSON reference for
  `hydra-umc-agent` (`describe`/`health`/`serve`), documenting every real
  output field and how `state`/`checks.*` are derived, plus the
  `--config` file's exact schema. Verified live against the running
  agent. Linked from `docs/SERVICE_MODEL.md`. Documentation-only - no
  code changed, no version bump.

## [0.0.3] - 2026-08-26

### Changed

- Automated build version increment from 0.0.2.

## [0.0.2] - 2026-08-26

### Added

- Read-only Python device agent with `describe`, `health`, and periodic
  `serve` commands.
- Validated non-secret configuration example and deterministic health states.
- Hardened `systemd` service unit and Debian package metadata.
- Five host-side unit tests covering configuration and READY/DEGRADED/FAULT
  health transitions.

### Limits

- No production image is built or distributed by this repository yet.
- This release does not command the MCU, CAN, URTC, motion, or updates.

## [0.0.1] - 2026-08-26

### Added

- Initial public project documentation and multilingual README files.
- CM5/Raspberry Pi OS architecture, service, installation, and update design.
- Explicit boundaries between HYDRA-UMC-OS, SDK, official OS components, MCU,
  and URTC.
