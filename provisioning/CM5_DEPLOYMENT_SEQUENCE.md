# CM5 deployment sequence

1. Flash the current official Raspberry Pi OS Lite ARM64 image.
2. Configure local Wi-Fi using the Raspberry Pi supported first-boot method.
3. Enable SSH with an administrator's public key; do not use unauthenticated
   remote access.
4. Record image, kernel, firmware and CM5 serial information.
5. Copy this repository. The initial identity is display name `HYDRA-UMC-TEST`,
   technical hostname `hydra-umc-test`, administrator `hydra_umc`, and
   least-privilege service account `hydra-umc`. Run `sudo ./provisioning/first_boot.sh` first in
   dry-run mode; inspect the output.
6. Run `sudo ./provisioning/first_boot.sh --apply`.
7. Install the HYDRA-UMC-OS package, then run the read-only agent and archive
   its `describe` and `health` output.
8. Apply branding after boot and recovery have been verified. Run
   `provisioning/install_splashscreen.sh` first in dry-run mode; it converts
   `HYDRA_UMC_SPLASHSCREEN.svg` locally into a reversible Plymouth theme.
9. Keep control and vision profiles disabled until their physical interfaces
   are individually validated.
