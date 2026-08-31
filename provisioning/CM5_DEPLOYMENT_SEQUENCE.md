# CM5 deployment sequence

1. Flash the current official Raspberry Pi OS Lite ARM64 image.
2. Configure local Wi-Fi using the Raspberry Pi supported first-boot method
   (Imager's own pre-seeded network, or `raspi-config`) - this is still the
   fastest path when the target network is already known at flash time.
   When it is not (a device shipped/relocated without a known network in
   advance), `install_cm5_base.sh` below installs a real fallback -
   `provisioning/wifi_provision.py` / `hydra-umc-wifi-provision.service` -
   that brings up a real NetworkManager access point (`nmcli device wifi
   hotspot`) an operator's phone/laptop can join directly to submit the
   real target SSID/password through a small local HTTP form. It is
   installed but deliberately NOT auto-enabled by `--enable-services` -
   see step 9 below for the real password step required before enabling it.
3. Enable SSH with an administrator's public key; do not use unauthenticated
   remote access.
4. Record image, kernel, firmware and CM5 serial information.
5. Copy this repository alongside `HYDRA-UMC-SDK`. The initial identity is display name `HYDRA-UMC-TEST`,
   technical hostname `hydra-umc-test`, administrator `hydra-umc`, and
   least-privilege service account `hydra-umc-agent`. Run the read-only gate
   `python3 provisioning/preflight_cm5.py --sdk-root ../HYDRA-UMC-SDK`; it must
   finish with `CM5_PREFLIGHT=PASS` before continuing.
6. Run `sudo bash provisioning/first_boot.sh` first in dry-run mode; inspect the output.
7. Run `sudo bash provisioning/first_boot.sh --apply`.
8. Install the HYDRA-UMC-OS package, then run the read-only agent and archive
   its `describe` and `health` output.
9. For the local dashboard, install a supported ARM64 Node.js 20+ runtime,
   create `/etc/hydra-umc/server.env` locally from `server.env.example`, then
   run `sudo bash provisioning/install_cm5_base.sh --apply --with-server`.
   Service activation remains a separate explicit decision:
   `--enable-services`. If this device needs the WiFi AP-mode fallback
   from step 2, set a real, per-device AP password first - `nmcli device
   wifi hotspot` password is otherwise the module's own known, shared
   placeholder:
   ```
   install -m 0600 -o root -g root /dev/null /etc/hydra-umc/wifi-provision.env
   echo 'HYDRA_UMC_AP_PASSWORD=<a real, per-device password>' >> /etc/hydra-umc/wifi-provision.env
   systemctl enable --now hydra-umc-wifi-provision
   ```
10. Archive state before enabling optional profiles with
    `sudo bash provisioning/cm5_recovery.sh backup /root/hydra-umc-state.tar.gz --apply`.
    Recovery restores only HYDRA-UMC paths and leaves services stopped for
    review.
11. Apply branding after boot and recovery have been verified. Run
   `sudo bash provisioning/install_splashscreen.sh` first in dry-run mode; it converts
   `HYDRA_UMC_SPLASHSCREEN.svg` locally into a reversible Plymouth theme.
12. Keep control and vision profiles disabled until their physical interfaces
   are individually validated.
