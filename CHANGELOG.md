# Changelog

## [0.0.6] - Fixed after a live ecosystem bug audit

### Fixed (additional, same version)

- **Real version-mirror drift, `agent/pyproject.toml` and
  `agent/src/hydra_umc_os/__init__.py`** - this repo's own manifest
  declares `native_version.file` as `CHANGELOG.md` itself (not the
  agent's own package files), so the ecosystem-wide
  `bump_manifest_version.py` bumping the manifest+changelog here never
  touches the real agent package's own version strings - only this
  repo's own separate `bump_version.py` (which requires the manifest and
  agent package to already match before it can run) does. That left the
  real installed agent one build behind what the manifest/changelog
  claimed. Manually caught both files up to 0.0.6 to match - a real
  reconciliation, not a version bump. 13/13 agent tests still passing.

### Fixed

- **`provisioning/inventory_cm5_projects.py`** - fixed a broken import that
  made this script fail outright: it imported a static `PROJECTS` list
  from `hydra_umc_updater.registry` that no longer exists (project
  discovery moved to reading each repository's own
  `hydra-umc.project.json`, and the static catalog was removed). Now uses
  the same `discover_workspace()` manifest-based discovery every other
  ecosystem tool uses; verified by actually running it against this
  workspace.
- **`agent/src/hydra_umc_os/agent.py`** (`health()`) - an unreadable
  temperature sensor (`read_temperature_celsius()` returning `None` - no
  `thermal_zone0`, a permission error, garbage contents) set the
  `temperature` check itself to `WARN`, but the overall device state only
  ever folded *network*'s `WARN` into `DEGRADED` - so a node that can't
  read its own temperature was reported as overall `READY`. Any `WARN`
  check now degrades the overall state. Covered by a new test
  (`test_degraded_when_the_temperature_sensor_is_unreadable`); the
  pre-existing `test_ready_when_storage_and_network_are_available` test
  now passes an explicit in-range temperature instead of implicitly
  depending on whether the test machine happens to expose a real thermal
  sensor.

## [0.0.5] - Idempotent preflight verification, real system-file rollback

### Added

- **A real, host-independent system-file backup/rollback mechanism** (`provisioning/rollback.py`, new) - `backup`/`restore` CLI subcommands record a real, append-only manifest before an installer overwrites a real system file, and can restore it (or delete it, if the installer created it fresh) afterward. Wired into `install_local_agent.sh`'s systemd unit install step, the one file this installer unconditionally overwrites on every run.
- **`tools/verify_rollback.py`** (new) - proves the backup/restore mechanism correct against synthetic files in a temp directory (no root, no CM5 needed): a pre-existing file's real content is restored exactly, a freshly-created file is removed on restore rather than left behind, restoring twice in a row is a real no-op (not an error), and restoring against a missing manifest fails honestly instead of silently doing nothing.
- **`tools/verify_preflight_idempotent.py`** (new) - runs `provisioning/preflight_cm5.py` twice in a row and proves byte-identical output plus zero real files touched under this repository, turning the preflight's own "read-only" claim into a checked, reproducible property instead of only a docstring.
- Both new checks are wired into `tools/build_test.py`'s real test run alongside the existing agent unit tests and deployment-contract verifications.

### Changed

- Automated build version increment from 0.0.3.

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
