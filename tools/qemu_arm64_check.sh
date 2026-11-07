#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - tools/qemu_arm64_check.sh
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Run inside a Debian trixie arm64 container by .github/workflows/qemu-arm64.yml (the repositories are mounted at /opt/hydra-umc, the OS one in
# /opt/hydra-umc/HYDRA-UMC-OS). Prints one line per check and exits 1 when one fails. Nothing is installed on a device: the installer runs without --apply.
set -uo pipefail
FAIL=0
ok() { echo "PASS  $*"; }
bad() { echo "FAIL  $*"; FAIL=1; }

OS=/opt/hydra-umc/HYDRA-UMC-OS
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq >/dev/null
apt-get install -y -qq --no-install-recommends python3 ca-certificates sudo >/dev/null 2>&1 || { echo "FAIL  could not install python3"; exit 1; }
arch="$(uname -m)"
echo "machine: $arch  release: $(. /etc/os-release; echo "$PRETTY_NAME")  dpkg: $(dpkg --print-architecture)"
[ "$arch" = "aarch64" ] && ok "the container runs as aarch64" || bad "the container does not run as aarch64 ($arch)"
[ "$(dpkg --print-architecture)" = "arm64" ] && ok "dpkg architecture is arm64" || bad "dpkg architecture is not arm64"

cd "$OS" || exit 1
if python3 provisioning/install_plan.py --check >/tmp/plan.log 2>&1; then ok "install_plan.py --check"; else bad "install_plan.py --check"; tail -n 20 /tmp/plan.log; fi
if python3 provisioning/os_release_guard.py --mode enforce >/tmp/guard.log 2>&1; then ok "the release guard accepts trixie (enforce)"; else bad "the release guard rejects this release"; cat /tmp/guard.log; fi
if bash provisioning/install_cm5_base.sh --with-server --with-voice-ui >/tmp/base.log 2>&1; then ok "install_cm5_base.sh dry run"; else bad "install_cm5_base.sh dry run"; tail -n 30 /tmp/base.log; fi
# the packages the installers ask for, planned by apt on the release and the architecture of the image (nothing is installed)
if python3 tools/apt_packages_check.py --simulate >/tmp/apt.log 2>&1; then ok "apt plans the packages of every installer"; cat /tmp/apt.log; else bad "apt cannot plan the packages of an installer"; cat /tmp/apt.log; fi
for script in provisioning/*.sh; do
  if bash -n "$script" 2>/tmp/syntax.log; then :; else bad "bash -n $script"; cat /tmp/syntax.log; fi
done
ok "bash -n over every provisioning script finished"
# the unit tests of the provisioning scripts that need only Python
count=0
for check in tools/verify_install_plan.py tools/verify_service_registry.py tools/verify_unit_hardening.py tools/verify_firewall.py tools/verify_device_identity.py tools/verify_result_keys.py; do
  [ -f "$check" ] || continue
  count=$((count + 1))
  if python3 "$check" >/tmp/check.log 2>&1; then ok "$check"; else bad "$check"; tail -n 15 /tmp/check.log; fi
done
echo "ran $count verify scripts on the architecture of the board"
echo "evidence=simulator (qemu-user arm64 emulation, not the board)"
exit "$FAIL"
