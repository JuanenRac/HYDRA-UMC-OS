#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - tools/kiosk_wayland_check.sh
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Run inside a Debian trixie container by .github/workflows/kiosk-wayland.yml (the repository is mounted read-only at /work).
# It checks the Wayland session of the HDMI kiosk without a screen, a GPU or a seat:
#   1. the installer, in dry-run, plans cage and no X server for --session wayland, and still plans X11 by default;
#   2. the real session script starts the real Chromium under the real cage on the headless backend, as the locked kiosk account,
#      and Chromium stays alive and reports no Wayland error.
# Prints one line per check and exits 1 when one fails.
set -uo pipefail
FAIL=0
ok() { echo "PASS  $*"; }
bad() { echo "FAIL  $*"; FAIL=1; }

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq >/dev/null
apt-get install -y -qq --no-install-recommends cage chromium procps passwd util-linux >/dev/null 2>&1 || { echo "FAIL  could not install cage and chromium"; exit 1; }
echo "release: $(. /etc/os-release; echo "$PRETTY_NAME")  cage: $(dpkg-query -W -f='${Version}' cage)  chromium: $(dpkg-query -W -f='${Version}' chromium)"

# 1. the installer, in dry-run (it changes nothing), from a copy of the repository
rm -rf /tmp/repo && mkdir -p /tmp/repo && cp -a /work/provisioning /work/images /tmp/repo/
mkdir -p /etc/hydra-umc
wayland_plan="$(bash /tmp/repo/provisioning/install_kiosk.sh --session wayland 2>&1)"
x11_plan="$(bash /tmp/repo/provisioning/install_kiosk.sh 2>&1)"
if echo "$wayland_plan" | grep -q "kiosk session: wayland" && echo "$wayland_plan" | grep -q "apt-get install -y --no-install-recommends cage chromium"; then ok "--session wayland plans cage and chromium"; else bad "--session wayland does not plan cage and chromium"; echo "$wayland_plan" | head -n 20; fi
if echo "$wayland_plan" | grep -qiE "xserver-xorg|openbox|picom|xorg.conf.d"; then bad "--session wayland still plans the X11 pieces"; else ok "--session wayland plans no X server, window manager or compositing manager"; fi
if echo "$x11_plan" | grep -q "kiosk session: x11" && echo "$x11_plan" | grep -q "xserver-xorg"; then ok "the default session is still X11"; else bad "the default session is not X11"; fi
bash /tmp/repo/provisioning/install_kiosk.sh --session plasma >/tmp/bad.log 2>&1; code=$?
if [ "$code" -eq 2 ]; then ok "an unknown session is refused (exit 2)"; else bad "an unknown session exited with $code"; fi
HYDRA_KIOSK_SESSION=wayland bash /tmp/repo/provisioning/install_kiosk.sh 2>&1 | grep -q "kiosk session: wayland" && ok "HYDRA_KIOSK_SESSION chooses the session" || bad "HYDRA_KIOSK_SESSION is not read"

# 2. the real session script under the real cage, as the locked account
useradd --create-home --home-dir /var/lib/hydra-umc-kiosk --shell /bin/bash hydra-umc-kiosk
passwd --lock hydra-umc-kiosk >/dev/null 2>&1
install -d -m 0755 /opt/hydra-umc/kiosk
install -m 0644 /work/provisioning/kiosk/splash.html /opt/hydra-umc/kiosk/splash.html
install -m 0644 /work/images/HYDRA_UMC_SPLASHSCREEN.svg /opt/hydra-umc/kiosk/HYDRA_UMC_SPLASHSCREEN.svg
# the container has no user namespaces and no GPU: only those two flags are added to the real command line
sed 's|^exec chromium \\|exec chromium --no-sandbox --disable-gpu --disable-dev-shm-usage \\|' /work/provisioning/kiosk/kiosk-session-wayland.sh >/opt/hydra-umc/kiosk/kiosk-session-wayland.sh
chmod 0755 /opt/hydra-umc/kiosk/kiosk-session-wayland.sh
grep -q -- "--ozone-platform=wayland" /opt/hydra-umc/kiosk/kiosk-session-wayland.sh && ok "the session script asks Chromium for Wayland" || bad "the session script does not ask for Wayland"
mkdir -m 0700 -p /tmp/xdg-kiosk && chown hydra-umc-kiosk:hydra-umc-kiosk /tmp/xdg-kiosk
runuser -u hydra-umc-kiosk -- env HOME=/var/lib/hydra-umc-kiosk XDG_RUNTIME_DIR=/tmp/xdg-kiosk WLR_BACKENDS=headless WLR_RENDERER=pixman WLR_LIBINPUT_NO_DEVICES=1 WLR_HEADLESS_OUTPUTS=1 \
  timeout 40 cage -- /opt/hydra-umc/kiosk/kiosk-session-wayland.sh >/tmp/cage-chromium.log 2>&1 &
sleep 25
if pgrep -u hydra-umc-kiosk -f "chromium.*--ozone-platform=wayland" >/dev/null; then ok "chromium (Wayland) is running under cage as hydra-umc-kiosk after 25 s"; else bad "chromium is not running under cage"; tail -n 25 /tmp/cage-chromium.log; fi
if pgrep -u hydra-umc-kiosk -x cage >/dev/null; then ok "cage is the compositor of the session"; else bad "cage is not running"; fi
if grep -qiE "Failed to connect to Wayland|Could not create|failed to create|wl_display|Missing X server|cannot open display" /tmp/cage-chromium.log; then bad "an error about the display in the log"; grep -iE "Failed to connect|Could not create|failed to create|wl_display|Missing X server|cannot open display" /tmp/cage-chromium.log | head -n 8; else ok "no display error in the log"; fi
if [ -d /var/lib/hydra-umc-kiosk/.config/hydra-umc-kiosk-chromium ]; then ok "the dedicated browser profile was created in the home of the account"; else bad "no browser profile"; fi
wait

echo "evidence=simulator (virtual screen, no GPU, no seat, no HDMI display)"
exit "$FAIL"
