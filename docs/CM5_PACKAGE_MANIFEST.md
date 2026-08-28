# CM5 phase package manifest

## Base

`python3`, `python3-venv`, `ca-certificates`, `systemd`, `NetworkManager`,
`openssh-server`, and the HYDRA-UMC-OS package.

## Server

Node.js 20 LTS plus the lockfile-resolved dependencies of HYDRA-UMC-SERVER.
Install with `npm ci`, build once, then run only `dist/server.cjs` through
systemd. The server is the local dashboard endpoint at port 3000.

## Optional bounded Voice UI gateway

No additional Python package is required for the current text-only gateway;
it uses Python's standard library and binds only to `127.0.0.1:8090`. Create
matching long random values in `/etc/hydra-umc/server.env` and
`/etc/hydra-umc/voice-ui.env`, then install with
`install_cm5_base.sh --apply --with-server --with-voice-ui`. This does not
install Whisper, neural TTS, HailoRT or a model.

## Vision / Hailo

Do not preinstall unpinned Hailo packages. After physical detection, select a
single compatible set of PCIe driver, HailoRT, TAPPAS and Python bindings for
the detected accelerator. Record every installed version in deployment logs.

## Deferred stacks

Flutter, Rust toolchains, Go toolchains, large LLM runtimes, MuJoCo/physics,
and optional industrial gateways are not base-image dependencies. Add them by
profile after resource and hardware validation.
