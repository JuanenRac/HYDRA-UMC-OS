#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - Install the HDMI kiosk: animated splash, then STUDIO fullscreen
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Plymouth (install_splashscreen.sh) cannot play this project's real splash
# animation - it only renders static raster frames or its own tiny scripting
# language, never inline SVG/CSS/SMIL. HYDRA_UMC_SPLASHSCREEN.svg's motion
# (its own <animate>/<animateTransform> elements and @keyframes) only plays
# back faithfully inside a real browser engine. So this script boots a
# minimal X11 session running exactly one thing - Chromium in kiosk mode -
# that shows the actual SVG file first (untouched, not re-implemented) and
# then hands off to HYDRA-UMC-SERVER's own STUDIO UI once it responds, both
# in the same fullscreen window. Deliberately not the future hmi_qt6 native
# path (see HYDRA-UMC/src/cm5_host/hmi_qt6) - that needs its own Qt6
# validation gate; this is the real, working HDMI-out kiosk in the meantime.
set -euo pipefail
APPLY=false
[[ "${1:-}" == "--apply" ]] && APPLY=true
[[ $EUID -eq 0 ]] || { echo "Run as root with sudo." >&2; exit 2; }
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KIOSK_USER="${SUDO_USER:-hydra-umc}"
KIOSK_HOME="$(getent passwd "$KIOSK_USER" | cut -d: -f6)"
[[ -n "$KIOSK_HOME" && -d "$KIOSK_HOME" ]] || { echo "Cannot resolve a home directory for $KIOSK_USER" >&2; exit 2; }
KIOSK_DIR=/opt/hydra-umc/kiosk
BOOT_CONFIG=/boot/firmware/config.txt
BOOT_CMDLINE=/boot/firmware/cmdline.txt
run() { if $APPLY; then "$@"; else printf '[dry-run] '; printf '%q ' "$@"; printf '\n'; fi; }

echo " ==============================================================="
echo "  HYDRA-UMC-OS - install_kiosk.sh"
echo "  HDMI kiosk: HYDRA_UMC_SPLASHSCREEN.svg, then STUDIO fullscreen."
echo "  Copyright (C) 2026 JuanenRac (Electro Hobby 3D)"
echo "  <electrohobby3d@gmail.com> | GPL-3.0-or-later - see LICENSE"
echo " ==============================================================="
echo "kiosk user: $KIOSK_USER"

run apt-get update
run apt-get install -y --no-install-recommends \
  xserver-xorg x11-xserver-utils xinit openbox picom chromium unclutter

# GPU memory split: harmless to set, but real testing on this device showed
# it is not the relevant knob here - this image already ships
# dtoverlay=vc4-kms-v3d (full KMS), which sources GPU memory from a CMA
# reservation rather than the legacy VideoCore split gpu_mem= controls, so
# vcgencmd get_mem gpu staying low is expected and not a problem by itself.
# Idempotent: only appends if no gpu_mem line exists yet, never edits an
# operator's own existing value.
if $APPLY; then
  if [[ -f "$BOOT_CONFIG" ]] && ! grep -q '^gpu_mem=' "$BOOT_CONFIG"; then
    printf '\n# HYDRA-UMC-OS kiosk: GPU memory for the Chromium kiosk session\ngpu_mem=128\n' >> "$BOOT_CONFIG"
    echo "gpu_mem=128 appended to $BOOT_CONFIG (takes effect on next reboot)"
  fi
else
  echo "[dry-run] append gpu_mem=128 to $BOOT_CONFIG unless a gpu_mem= line already exists"
fi

# Real complaint from watching this device boot with a monitor attached,
# tracked down across MANY rounds of live testing - each one looked like a
# leftover "boot log" until actually read/photographed on the physical
# screen, and turned out to be a completely different, unrelated source
# every time:
#
# 1. With no "quiet"/"splash" at all, the kernel and every systemd unit
#    print their normal boot log straight onto tty1. quiet/splash/
#    logo.nologo/loglevel=0/vt.global_cursor_default=0 address the basics
#    (loglevel=0, not the usual 3 - real driver-probe warnings on this
#    device, e.g. dwc2/brcm-pcie regulator notices, still printed at
#    loglevel=3); systemd.show_status=0 additionally silences systemd's
#    own "[ OK ] Started ..." unit-status lines specifically.
# 2. Even with those, boot-log-looking text was STILL visible. Root
#    cause, found by researching real Plymouth behaviour rather than
#    guessing further: this device also carries a real serial console
#    (console=serial0,115200, kept intentionally for actual hardware
#    debugging) - and Plymouth deliberately falls back to its own
#    text-only "details" plugin whenever ANY serial console is present,
#    by design, regardless of quiet/splash/the theme's own config.
#    plymouth.ignore-serial-consoles is Plymouth's own, documented
#    opt-out of that fallback; it now shows this theme's real static
#    frame (see install_splashscreen.sh) instead.
# 3. Text kept appearing even after (2). Genuinely tried keeping Plymouth
#    holding the display for the device's ENTIRE boot instead (masking
#    plymouth-quit*.service, quitting it manually right before Chromium
#    from kiosk-session.sh) so nothing underneath could ever become
#    visible regardless of source - live-tested, and it deadlocked
#    agetty's own autologin on tty1 outright (stuck as bare "(agetty)",
#    never reaching login) instead: Plymouth holding that same tty1/VT
#    session open conflicts with agetty trying to claim it. Reverted -
#    plymouth-quit*.service stays unmasked, Plymouth quits on its own
#    normal ~4s schedule.
# 4. What was actually left after (1)-(2) turned out to be TWO more
#    separate, unrelated sources, only identified once the operator could
#    read/photograph the exact text rather than describe a fast flash:
#    (a) Xorg's own startup banner, which writes directly to the VT
#    device rather than through inherited stdout/stderr - "-verbose 0
#    -logverbose 0" passed to X itself (below) is the documented,
#    intended way to quiet it; (b) update-motd.d's real "10-uname" script
#    (`Linux hostname kernel-version arch`), which every login session on
#    this account prints AFTER agetty's autologin succeeds, completely
#    independent of agetty/Xorg/Plymouth - a plain ~/.hushlogin (see
#    below) is the standard way to suppress it for one account.
#
# cmdline.txt is a single line, so tokens are appended in place rather
# than as new lines like config.txt above; idempotent - only a token not
# already present anywhere on the line gets added, so re-running this (or
# a cmdline.txt an operator already customised) never duplicates or
# fights an existing choice. console=tty1 -> console=tty3 is a real
# substitution rather than an append: tty1 stays the visible/active VT
# (nothing switches away from it) while kernel/systemd console output
# routes to the otherwise-unused tty3 instead - a working text console
# still exists for real debugging (switchable from a physical keyboard),
# it is simply not the one shown on the display by default.
if $APPLY; then
  if [[ -f "$BOOT_CMDLINE" ]]; then
    cmdline="$(cat "$BOOT_CMDLINE")"
    case " $cmdline " in
      *' console=tty3 '*) ;;
      *) cmdline="$(printf '%s' "$cmdline" | sed 's/console=tty1/console=tty3/')" ;;
    esac
    for token in quiet splash logo.nologo loglevel=0 vt.global_cursor_default=0 systemd.show_status=0 fbcon=map:10 plymouth.ignore-serial-consoles; do
      case " $cmdline " in
        *" $token "*) ;;
        *) cmdline="$cmdline $token" ;;
      esac
    done
    printf '%s' "$cmdline" > "$BOOT_CMDLINE"
    echo "cmdline.txt updated for a quiet graphical boot (takes effect on next reboot)"
  fi
else
  echo "[dry-run] ensure console=tty3 (not tty1) and quiet splash logo.nologo loglevel=0 vt.global_cursor_default=0 systemd.show_status=0 fbcon=map:10 plymouth.ignore-serial-consoles are present in $BOOT_CMDLINE"
fi

# Real bugs found live on this device's first boot into the kiosk, in order:
# (1) with both the modern KMS "modesetting" driver and the legacy "fbdev"
# driver available (xserver-xorg-video-all, pulled in by the xserver-xorg
# metapackage), X's driver auto-probe tried fbdev after modesetting and
# died with "Cannot run in framebuffer mode. Please specify busIDs for all
# framebuffer devices". (2) pinning bare "Driver modesetting" alone still
# failed with "No devices detected"/"no screens found" even with a real
# monitor confirmed connected (/sys/class/drm/card1-HDMI-A-1/status ==
# connected): the CM5 exposes 2 DRM nodes under vc4-kms-v3d - card0 is
# v3d (3D/compute only, no display output) and card1 is vc4 (the real
# display controller) - and modesetting's own autodetection did not
# reliably resolve to card1 on its own. Pinning kmsdev explicitly is the
# documented fix for this dual-node situation.
run install -d -m 0755 /etc/X11/xorg.conf.d
if $APPLY; then
  cat > /etc/X11/xorg.conf.d/20-hydra-umc-modesetting.conf <<'EOF'
Section "Device"
    Identifier "HYDRA-UMC-KMS"
    Driver "modesetting"
    Option "kmsdev" "/dev/dri/card1"
EndSection
EOF
else
  echo "[dry-run] write /etc/X11/xorg.conf.d/20-hydra-umc-modesetting.conf (pin Driver \"modesetting\", kmsdev /dev/dri/card1)"
fi

run install -d -o root -g root -m 0755 "$KIOSK_DIR"
run install -m 0644 "$ROOT/images/HYDRA_UMC_SPLASHSCREEN.svg" "$KIOSK_DIR/HYDRA_UMC_SPLASHSCREEN.svg"
run install -m 0644 "$ROOT/provisioning/kiosk/splash.html" "$KIOSK_DIR/splash.html"
run install -m 0755 "$ROOT/provisioning/kiosk/kiosk-session.sh" "$KIOSK_DIR/kiosk-session.sh"

# Autologin on the physical console (tty1) - the standard, minimal way to
# reach a graphical kiosk session on a Lite install with no display manager.
# --noissue: suppresses /etc/issue (distro banner); the "login:" prompt
# line itself is agetty's own separate, hardcoded output and briefly
# shows regardless, autologin or not - real, seen live, and small enough
# next to the other fixes above to not warrant chasing further.
run install -d -m 0755 /etc/systemd/system/getty@tty1.service.d
if $APPLY; then
  cat > /etc/systemd/system/getty@tty1.service.d/hydra-umc-autologin.conf <<EOF
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin $KIOSK_USER --noclear --noissue %I \$TERM
EOF
else
  echo "[dry-run] write /etc/systemd/system/getty@tty1.service.d/hydra-umc-autologin.conf (autologin: $KIOSK_USER, --noissue)"
fi
run systemctl daemon-reload

# ~/.hushlogin - see root cause 4(b) above: suppresses update-motd.d's
# per-login "Linux <hostname> <kernel version> <arch>" banner
# (10-uname), the one real, live-confirmed remaining line after every
# fix above. install(1) both creates it and fixes ownership in one call.
run install -o "$KIOSK_USER" -g "$KIOSK_USER" -m 0644 /dev/null "$KIOSK_HOME/.hushlogin"

# .bash_profile starts X only for an interactive login on the physical
# console (tty1), never for an SSH session - an SSH login has no controlling
# tty1 and $DISPLAY stays unset there, so this never fights an
# administrator's own SSH work on the same account. "&> /dev/null" is a
# real, live-diagnosed fix: X itself (not the kernel/systemd - unaffected
# by console=/quiet/fbcon settings) writes its own startup banner to
# whatever's on stdout/stderr when startx launches it, and that flashed on
# screen briefly every boot until this was redirected away.
PROFILE_LINE='[ -z "$DISPLAY" ] && [ "$(tty)" = "/dev/tty1" ] && exec startx /opt/hydra-umc/kiosk/kiosk-session.sh -- -nocursor -verbose 0 -logverbose 0 &> /dev/null'
if $APPLY; then
  touch "$KIOSK_HOME/.bash_profile"
  # Drop any earlier version of this exact line (e.g. before the &> /dev/null
  # above was added) before appending the current one, so re-running this
  # script after an update never leaves two competing startx lines behind.
  grep -v 'exec startx /opt/hydra-umc/kiosk/kiosk-session.sh' "$KIOSK_HOME/.bash_profile" > "$KIOSK_HOME/.bash_profile.tmp" || true
  mv "$KIOSK_HOME/.bash_profile.tmp" "$KIOSK_HOME/.bash_profile"
  echo "$PROFILE_LINE" >> "$KIOSK_HOME/.bash_profile"
  chown "$KIOSK_USER":"$KIOSK_USER" "$KIOSK_HOME/.bash_profile"
else
  echo "[dry-run] ensure $KIOSK_HOME/.bash_profile starts the kiosk session on tty1 only, output silenced"
fi

echo "Kiosk installed. Reboot to see it on HDMI, or on this console: sudo systemctl restart getty@tty1"
echo "Splash source stays HYDRA_UMC_SPLASHSCREEN.svg unmodified; edit provisioning/kiosk/splash.html to change hand-off timing."
