#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - The Rust compiler a Rust program needs before it is built
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Sourced, never run. The Rust programs (the digital twin, the orchestrator, the HIL bridge, the swarm sync) are built on the device
# with the `cargo` of the Debian archive. A program says in `rust-version` of its Cargo.toml the oldest compiler that builds it; when
# the compiler of the device is older, the build would stop half way with a message about one of its libraries. This check says it
# first, in plain words, and nothing is built.
#
#   require_rust SOURCE_DIR NAME   returns 0 when `rustc` is new enough (or the program names no version); exits 2 when it is not

require_rust() {
  local source="$1" name="$2" wanted have
  wanted="$(tr -d '\r' < "$source/Cargo.toml" | awk '/^\[/ { section = $0 } section == "[package]" && /^rust-version[ \t]*=/ { split($0, part, "\""); print part[2]; exit }')"
  [[ -n "$wanted" ]] || return 0
  have="$(rustc --version 2>/dev/null | awk 'NR == 1 { split($2, part, "-"); print part[1] }')"
  [[ -n "$have" ]] || { echo "$name needs rustc $wanted or newer to build, and no rustc answers on this device. Nothing was built." >&2; exit 2; }
  if [[ "$(printf '%s\n%s\n' "$wanted" "$have" | sort -V | head -n1)" != "$wanted" ]]; then
    echo "$name needs rustc $wanted or newer to build; this device has rustc $have. Nothing was built." >&2
    echo "Install a version of $name that builds with rustc $have, or upgrade the Rust compiler of the device first." >&2
    exit 2
  fi
}
