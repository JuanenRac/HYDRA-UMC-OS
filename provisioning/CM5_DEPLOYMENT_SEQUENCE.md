# CM5 deployment sequence

1. Flash the current official Raspberry Pi OS Lite ARM64 image.
2. Configure local Wi-Fi using the Raspberry Pi supported first-boot method.
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
   `--enable-services`.
10. Archive state before enabling optional profiles with
    `sudo bash provisioning/cm5_recovery.sh backup /root/hydra-umc-state.tar.gz --apply`.
    Recovery restores only HYDRA-UMC paths and leaves services stopped for
    review.
11. Apply branding after boot and recovery have been verified. Run
   `sudo bash provisioning/install_splashscreen.sh` first in dry-run mode; it converts
   `HYDRA_UMC_SPLASHSCREEN.svg` locally into a reversible Plymouth theme.
12. Keep control and vision profiles disabled until their physical interfaces
   are individually validated.
