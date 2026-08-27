# Update model

Raspberry Pi OS, HYDRA-UMC packages, Hailo runtimes/models, and MCU/URTC
firmware have separate update channels. They are never represented as one
opaque binary.

HYDRA-UMC artifacts require a manifest with version, compatibility, hash, and
signature. The updater checks the target device and dependency range, installs
the candidate, restarts only required services, and evaluates health. A failed
health check must surface an actionable fault and use rollback where supported.

Firmware retains its own tested update and recovery process. Do not couple a
Raspberry Pi OS upgrade to a firmware change without a maintenance plan.
