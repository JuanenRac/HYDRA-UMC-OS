#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - build_hooks/anomaly-detector.sh
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Checks the source and installs the numeric library the anomaly detector imports.
# Sourced by provisioning/install_anomaly_detector.sh as root, after the service user and $TARGET exist and before the shared copy step;
# never run on its own. Uses $ROOT, $SOURCE, $TARGET, $SVC_USER and $HERE of the installer. Safe to run again.

[[ -d "$SOURCE/src/hydra_umc_anomaly_detector" ]] || { echo "HYDRA-UMC-ANOMALY-DETECTOR source is incomplete: $SOURCE" >&2; exit 2; }
apt-get update
apt-get install -y --no-install-recommends python3-numpy
