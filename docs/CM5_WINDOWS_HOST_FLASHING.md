<!--
HYDRA-UMC-OS - CM5 flashing from a Windows host
Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
GPL-3.0 - see LICENSE
-->

# CM5 flashing from a Windows host

This is the real, verified procedure for turning a bare CM5 + official IO
Board into a Raspberry Pi OS Lite ARM64 install ready for
[CM5_DEPLOYMENT_SEQUENCE.md](../provisioning/CM5_DEPLOYMENT_SEQUENCE.md)'s
own Gate 1, from a **Windows** workstation. It exists because Windows is
explicitly not the officially supported host for CM5 provisioning (Linux
is), and the real failure modes below are common enough on Windows to be
worth a dedicated, verified walkthrough rather than rediscovering them
each time.

Read [CM5_DEPLOYMENT_SEQUENCE.md](../provisioning/CM5_DEPLOYMENT_SEQUENCE.md)
first for the actual gated sequence this replaces only step 1 of ("Create
the Raspberry Pi OS base"). This document does not repeat identity, SSH,
or secret-handling policy - it defers to that document and
[CM5_PROVISIONING.md](CM5_PROVISIONING.md) for those.

## 0. Physical setup

1. Fit a jumper across **J2** on the official CM5 IO Board (`nRPI_BOOT`).
   This disables eMMC boot and forces the CM5 into USB boot mode - without
   it, the host never sees the module as a USB device at all.
2. Connect a real USB-C **data** cable (not a charge-only cable - a
   common, hard-to-spot cause of "nothing happens") from the IO Board's
   **J11** ("USB-C slave") port to the host PC, directly into a
   motherboard port - not through a hub, and prefer USB 2.0 over USB 3.0
   if both are available (USB 3.0 controllers are a real, reported cause
   of hangs during the boot-mode enumeration).
3. If the IO Board has an NVMe SSD fitted in its M.2 slot, remove it
   before flashing the eMMC - a populated NVMe slot has been reported to
   confuse `rpiboot`'s own device discovery.
4. Power on the board.

## 1. First attempt: Raspberry Pi Imager alone

Open Raspberry Pi Imager and see if it detects the CM5 directly. If it
does, skip to [section 4](#4-writing-and-customising-the-image). If it
doesn't, the device is very likely stuck at its first-stage USB
enumeration with no usable driver bound to it - continue below.

## 2. Real cause: the "BCM2712D0 Boot" device has no Windows driver

Open Windows Device Manager while the board is powered and cabled. A
device named **"BCM2712D0 Boot"** (sometimes under "Other devices" with a
yellow warning) confirms this diagnosis - Windows enumerated the CM5's
boot-ROM stage but has no driver bound to talk to it, so neither
Raspberry Pi Imager's own bundled `rpiboot` nor a standalone one can
reach it.

Fix with [Zadig](https://zadig.akeo.ie/) (a real, standard tool for
binding generic USB drivers on Windows):

1. Run Zadig **as Administrator**.
2. **Options → List All Devices** (required - Zadig hides devices with an
   existing driver by default, and does not list boot-ROM devices any
   other way).
3. Select **"BCM2712D0 Boot"** in the dropdown.
4. Choose **WinUSB** as the target driver.
5. **Install Driver**.

The device version WinUSB itself reports after installing (something
like `6.1.7600.16385`) is Zadig's own bundled generic driver version -
normal, not a sign of anything wrong.

Retry Raspberry Pi Imager. If it now detects and writes successfully,
you're done - skip to [section 4](#4-writing-and-customising-the-image).
If it still doesn't reach the mass-storage stage (Imager sits waiting, or
the CM5 drops back to "BCM2712D0 Boot" repeatedly), continue below - this
is the real, reported case where Windows' own bundled `rpiboot` (in
Raspberry Pi Imager 2.x, and in the older 1.9.6 standalone) does not
reliably complete the second-stage handoff for a CM5 specifically, even
with the correct driver bound.

## 3. Real fallback: WSL2 + usbipd-win + a real compiled `rpiboot`

This gives the CM5 to a genuine Linux `rpiboot` (built from the official
source, not whatever Windows happened to bundle), while staying entirely
on the Windows host - no separate Linux machine or live USB needed.

### 3a. One-time setup

```powershell
# PowerShell, as Administrator
winget install usbipd
```

**Close and reopen the PowerShell window** after installing - `usbipd`
won't be on `PATH` in a window that was already open when it installed.

```powershell
wsl --install -d Ubuntu-24.04   # if you don't already have a WSL2 distro
```

Inside the WSL distro, install build dependencies and the real official
`rpiboot` source once:

```bash
sudo apt update
sudo apt install -y usbutils git build-essential libusb-1.0-0-dev pkg-config
git clone --depth=1 https://github.com/raspberrypi/usbboot
cd usbboot
make
```

### 3b. Give WSL passwordless sudo for this session

Every one of the commands below that needs `sudo` runs from a **separate**
`wsl -d ... -- bash -c "..."` invocation if driven by a script/agent
rather than typed by hand into one open WSL window - and `sudo`'s
timestamp cache is per-TTY, so a password cached in one window is
invisible to the next invocation. Rather than fighting that, grant this
WSL user real passwordless sudo once (affects only this local WSL
distro, never Windows or the CM5 itself):

```bash
sudo -v   # authenticate once interactively
echo 'YOUR_WSL_USERNAME ALL=(ALL) NOPASSWD: ALL' | sudo tee /etc/sudoers.d/090-nopasswd
sudo chmod 0440 /etc/sudoers.d/090-nopasswd
```

### 3c. Attach the CM5 to WSL and run the real `rpiboot`

With the board still in boot mode (J2 jumper fitted, cabled, powered):

```powershell
# PowerShell, as Administrator - find the busid
usbipd list
# Look for "BCM2712D0 Boot" - note its BUSID (e.g. 2-1)

usbipd bind --busid <BUSID>

# --auto-attach, not plain attach: the CM5 re-enumerates mid-boot
# (bootcode.bin succeeds, the device resets, and comes back as a NEW
# USB enumeration) - a plain `attach` is one-shot and loses it exactly
# at that point. --auto-attach keeps reattaching automatically and must
# be left running (its own window/process) for the whole flash.
usbipd attach --wsl --auto-attach --busid <BUSID>
```

In a WSL window:

```bash
cd ~/usbboot
sudo ./rpiboot
```

Watch for `Waiting for BCM2835/6/7/2711/2712...` (confirms this build
supports the CM5's BCM2712), then `Sending bootcode.bin` /
`Successful read 4 bytes`, then a second `Waiting for...` (the
re-enumeration `--auto-attach` exists to survive) before it finally
completes and the eMMC exposes itself as a **real USB mass-storage
device**.

### 3d. Back on Windows

The moment `rpiboot` completes, the device re-enumerates one more time -
from `usbipd`'s perspective as a *different* device (a different
VID:PID, since it's no longer presenting as "BCM2712D0 Boot") - and lands
back on the **Windows** side as a genuine mass-storage disk, not inside
WSL. Confirm it:

```powershell
Get-Disk | Select-Object Number, FriendlyName, Size, BusType
```

A disk named **`mmcblk0`** (the real Linux eMMC block-device name,
unmistakable - nothing else presents as this) on `BusType USB` is the
CM5. **Double-check `FriendlyName` and `Size` before continuing to any
other step in this document or in Raspberry Pi Imager** - writing to the
wrong disk number is destructive and not reversible.

You can now stop the `usbipd attach --auto-attach` loop (Ctrl+C) - it
served its purpose getting past the boot-ROM handoff; the disk now
belongs to Windows directly.

## 4. Writing and customising the image

Once Raspberry Pi Imager sees the `mmcblk0` device (either directly, per
section 1, or after section 3 above):

1. **Choose OS** → Raspberry Pi OS (other) → **Raspberry Pi OS Lite (64-bit)**.
2. **Choose Storage** → the `mmcblk0` device. Verify its size matches what
   `Get-Disk` reported before confirming.
3. Advanced options (gear icon) - set hostname, SSH (public key only -
   see [CM5_PROVISIONING.md](CM5_PROVISIONING.md)'s own SSH policy),
   username, WiFi, and locale/keyboard per your own deployment's real
   values. Never type a real secret into a shared terminal/log - Imager's
   own dialog is the right place for it.
4. **Write**.

**Why the GUI, not a scripted `dd`-equivalent:** writing raw bytes to
`\\.\PhysicalDriveN` and the mid-write partition remount both need an
**elevated (Administrator) PowerShell session** - and a session that
isn't already running elevated cannot silently click through Windows'
own UAC prompt (by design; that boundary exists specifically so nothing
automated can escalate itself without a human's explicit click). If
you're scripting this end to end, open your PowerShell window as
Administrator from the start; if an assistant/agent is driving it
without an elevated session, handing the actual write step to Raspberry
Pi Imager's own GUI (which has whatever elevation it needs already) is
the correct, real fallback - not a workaround to remove later.

For anyone who prefers to author the equivalent `custom.toml` by hand
instead of the GUI (e.g. scripting the whole flow from a real Linux
host, where the elevation problem above doesn't exist), the real,
current schema is:

```toml
config_version = 1

[system]
hostname = "hydra-umc-test"

[user]
name = "hydra-umc"
password = "<a real SHA-512-crypt hash - see below, never the plaintext>"
password_encrypted = true

[ssh]
enabled = true
password_authentication = false
authorized_keys = ["ssh-ed25519 AAAA... your-real-public-key"]

[wlan]
ssid = "YOUR-SSID"
password = "YOUR-WIFI-PASSWORD"
password_encrypted = false
hidden = false
country = "US"   # real ISO 3166-1 alpha-2 code - sets the WiFi regulatory domain

[locale]
keymap = "us"
timezone = "Europe/Madrid"
```

Place it as `custom.toml` in the root of the boot partition (the small
FAT32 volume Windows/Linux mounts after Imager writes the base image
without Advanced Options, or after a manual `dd`-equivalent write). Per
[CM5_PROVISIONING.md](CM5_PROVISIONING.md)'s own policy, the real
plaintext admin password should never be typed anywhere that gets
logged - generate and hash it in one step so the plaintext is never
displayed or recorded, e.g.:

```bash
# Real, one-line generate-and-hash - prints ONLY the hash, the plaintext
# is never captured anywhere
openssl passwd -5 -salt "$(openssl rand -hex 8)" "$(openssl rand -base64 24 | tr -dc 'A-Za-z0-9' | head -c 24)"
```

Since `[ssh].password_authentication = false` disables password login
over SSH entirely, that console-only hash is a real, working local
account with an intentionally unknown password - access is by SSH key
only, matching the deployment sequence's own policy. If local console
password access is ever needed, set it locally on the device with
`sudo passwd hydra-umc`, never by re-deriving what was generated here.

## 5. Continue the real sequence

Remove the J2 jumper, power-cycle the board, and continue from
[CM5_DEPLOYMENT_SEQUENCE.md](../provisioning/CM5_DEPLOYMENT_SEQUENCE.md)
Gate 1 (verify hostname, key-based SSH) onward.
