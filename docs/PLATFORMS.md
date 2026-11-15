# Platforms of the device

The system of the device is built for one platform. A platform is a declaration, never a switch that moves hardware: `config/platforms/<name>.json` (format `hydra-platform/1`)
says which base image the system is built on, which extra packages and units it needs and which build backends can build it.

| Platform | What it is | Base image | Adds | Backends | Evidence |
|---|---|---|---|---|---|
| `cm5` | Raspberry Pi Compute Module 5, the platform of the pilot bench and of every image built today | Raspberry Pi OS Lite, trixie | nothing | chroot, nspawn, pi-gen | bench |
| `jetson` | NVIDIA Jetson module (Orin NX class) | the root file system of the JetPack release the module runs (assumed Ubuntu 22.04, to be confirmed), supplied by the person who builds | the package `nvidia-jetpack` and the unit `nvpmodel.service` | chroot, nspawn | simulator |
| `rk3588` | a GENERIC RK3588 module: no board and no carrier have been chosen | a Debian arm64 root file system plus the kernel, device tree and boot loader of the board, supplied by the person who builds | `u-boot-tools`, `device-tree-compiler` | chroot, nspawn | simulator |

pi-gen builds Raspberry Pi images only, so it is allowed for `cm5` alone. The `cm5` platform adds no package and no unit: choosing it leaves the images of today exactly as they are.

## Which platform a machine uses

`HYDRA_UMC_PLATFORM`, else the first word of `/etc/hydra-umc/platform`, else `cm5`. A name that is not a platform is an error; it never falls back to another one.

```
python tools/platform_profile.py                 # the platforms, and the one this machine uses
python tools/platform_profile.py --show jetson   # base image, packages, units and the commands written out (nothing is run)
python tools/platform_profile.py --check         # every file of config/platforms is valid
python tools/verify_platform_profile.py          # the tests of the rules
```

The image builder (HYDRA-UMC-OS-REBUILDER) reads the same platforms through the option `platform.name` of its configuration file.

## What is not proven

Everything for `jetson` and `rk3588` was made in simulation: no image was built, nothing was flashed and no module was started. The package and unit names of JetPack are those known
today and are confirmed on a module (the bench test is to build the image for `jetson`, boot it, and check that `nvpmodel.service` is enabled and `nvidia-jetpack` is installed).
The RK3588 profile will get its kernel, device tree and boot loader when a module is chosen.
