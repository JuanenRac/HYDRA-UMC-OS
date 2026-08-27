# CM5 phase package manifest

## Base

`python3`, `python3-venv`, `ca-certificates`, `systemd`, `NetworkManager`,
`openssh-server`, and the HYDRA-UMC-OS package.

## Server

Node.js 20 LTS plus the lockfile-resolved dependencies of HYDRA-UMC-SERVER.
Install with `npm ci`, build once, then run only `dist/server.cjs` through
systemd. The server is the local dashboard endpoint at port 3000.

## Vision / Hailo

Do not preinstall unpinned Hailo packages. After physical detection, select a
single compatible set of PCIe driver, HailoRT, TAPPAS and Python bindings for
the detected accelerator. Record every installed version in deployment logs.

## Deferred stacks

Flutter, Rust toolchains, Go toolchains, large LLM runtimes, MuJoCo/physics,
and optional industrial gateways are not base-image dependencies. Add them by
profile after resource and hardware validation.
