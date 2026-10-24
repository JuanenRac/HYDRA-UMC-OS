#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - The Go toolchain the Go services are built with
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Sourced, never run. The Go services (the job dispatcher, the node watchdog, the telemetry collector) are built on the device, and
# their go.mod asks for a Go newer than the one the Debian archive packages: the packaged golang-go cannot build them. So the
# installers use one pinned upstream release from go.dev, verified against its SHA-256 before it is unpacked, and keep it beside
# any other Go in /usr/local/go-<version> (nothing in the system Go is touched).
#
#   ensure_go     installs the pinned toolchain when it is not there yet and sets GO_BIN to its go binary; exits 2 when it cannot
#
# GO_VERSION, GO_TARBALL and GO_SHA256 are changed together, and only upward: a project that needs a newer Go raises all three here.
# The values are the ones go.dev publishes for the arm64 Linux archive (the CM5). HYDRA_UMC_GO_ROOT names another install location.

GO_VERSION="1.27.1"
GO_TARBALL="go${GO_VERSION}.linux-arm64.tar.gz"
GO_SHA256="3450b45a3f9ee8568792736a5c5e70a1f2e9b36c35a8f74958c03e51d7d92bec"
GO_ROOT="${HYDRA_UMC_GO_ROOT:-/usr/local/go-${GO_VERSION}}"

ensure_go() {
  if [[ ! -x "$GO_ROOT/bin/go" ]]; then
    local workdir
    workdir="$(mktemp -d)"
    curl -fsSL -o "$workdir/$GO_TARBALL" "https://go.dev/dl/$GO_TARBALL" || { rm -rf "$workdir"; echo "Could not download $GO_TARBALL from go.dev." >&2; exit 2; }
    if ! echo "$GO_SHA256  $workdir/$GO_TARBALL" | sha256sum -c - >/dev/null; then
      rm -rf "$workdir"
      echo "The SHA-256 of $GO_TARBALL does not match the pinned value: not installing it." >&2
      exit 2
    fi
    rm -rf "$GO_ROOT"
    mkdir -p "$GO_ROOT"
    tar -C "$GO_ROOT" --strip-components=1 -xzf "$workdir/$GO_TARBALL"
    rm -rf "$workdir"
  fi
  GO_BIN="$GO_ROOT/bin/go"
  [[ -x "$GO_BIN" ]] || { echo "Go toolchain install at $GO_ROOT did not produce a real go binary." >&2; exit 2; }
}
