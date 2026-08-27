# CM5 first boot checklist

1. Flash an official Raspberry Pi OS ARM64 image and apply normal OS updates.
2. Record OS release, kernel, firmware, CM5 serial and image checksum.
3. Install the OS agent only; do not enable control or vision profiles.
4. Run `hydra-umc-agent describe` and `health`; archive JSON and journald output.
5. Verify storage, network, temperature and reboot behavior.
6. Only after review, test one declared hardware requirement at a time.
7. Do not connect motion or enable MCU commands during this checklist.
