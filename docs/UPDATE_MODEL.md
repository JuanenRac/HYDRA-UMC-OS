<!--
=============================================================================
HYDRA-UMC-OS - Update model
Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
GPL-3.0-or-later - see LICENSE
=============================================================================
-->

# Update model

Raspberry Pi OS, HYDRA-UMC packages, Hailo runtimes/models, and MCU/URTC
firmware have separate update channels. They are never represented as one
opaque binary.

HYDRA-UMC artifacts require a manifest with version, compatibility, hash, and
signature. Before any future CM5 deployment flow changes a checkout, its
candidate manifest must validate, identify the same project, and not declare a
lower version than the installed manifest. The updater checks the target device
and dependency range, installs the candidate, restarts only required services,
and evaluates health. A failed health check must surface an actionable fault
and use rollback where supported. This is a deployment contract; it does not
claim that a rollback has been exercised on a CM5 before hardware testing.

**Status.** The paragraph above describes the target contract. Today no component
implements it end to end: the installers (`provisioning/install_*.sh`) copy a
checkout into place and restart its unit without a signed manifest, a
dependency-range check, a health gate or an automatic rollback, and
`tools/package_component.py` only packs and verifies signed component archives.
Read it as the direction of the work, not as a description of what runs on a
device.

**Built, not yet on a device.** `tools/deploy_release.py` is the core of that flow, tested in
temporary folders: it verifies a signed package, refuses the same or an older version, installs it
as a numbered release, switches `current`, runs the restart and health commands of
`<root>/deploy.json`, puts the earlier release back (exit status 3) when either fails, and offers
`rollback`, `prune` and `status`. No installer calls it yet and no rollback has been exercised on a
CM5.

**Started from Studio, built and checked on the host only.** HYDRA-UMC-SERVER can run that same flow for the user of Studio (`/api/admin/self-update`, off by default): it fetches `hydra-<component>-<version>.tgz`, its `.sha256` and its `.sig` from the newest release of the repository of the program, has `tools/package_component.py verify` check them (it prints one `PACKAGE=OK <component> <version> <sha256>` line, or `PACKAGE=REFUSED` on the error output with status 1), and starts `tools/deploy_release.py install` detached, with its output in a file, because restarting the server kills whatever the server started: the server reads the file for the last line, `DEPLOY=PASS` on the standard output or `DEPLOY=FAIL <reason>` on the error output (status 2 refused, 3 went back to the release that was in use), and the state of the component for the version in use. Both lines are part of the contract of the tool and `tools/verify_deploy_release.py` checks them. Only the unit of the component named in `restartCommand` is restarted (for example `systemctl try-restart hydra-umc-{component}` with a rule that lets the account of the server run exactly that), never the machine. What is not done yet: the units still run from `/opt/hydra-umc/<component>` and not from `<root>/<component>/current`, and no rule of sudo exists for that restart, so on a device this flow is not wired; it has not run on a CM5.

**Every installed program from Studio, built and checked on the host only.** `tools/fleet_update.py` brings the programs under `/opt/hydra-umc` to the newest published release, one at a time, in the order of their dependencies (the tools of this repository and the SDK as checkouts, the services from the leaves to the orchestration, the server last with its frontend). `plan` only looks; `run --yes` applies; `resume --yes --only <program>` takes up a program whose step was cut; `status` reads the file. The progress is a file (`hydra-fleet-update/1`, written atomically at every step, with a heartbeat file beside it), so the server that started it can restart in the middle and Studio still sees where it is. For each program: free disk (more for the server, which is built on the device), the tag fetched and its commit compared with the one GitHub gives (and `git verify-tag` for the programs of the list `signedTags` of the settings, by default the server with its Studio and the critical services, or for all of them with `requireSignedTags`), a `.tgz` of the program in use (one exact name, `<name>.bak.tgz`, kept as it was when the program is cut and taken up again) together with its unit and drop-ins and a hash of each, the build of the server in named steps, the installer of `provisioning/` with `--apply` (it restarts that unit only), then the checks: version, unit active, health route, no import error or missing file in the journal, and the Python SDK importable by the unit. A failure puts the `.tgz` back, removes the drop-ins the installer added, reloads systemd and says whether the unit files are as they were (`unitRestored`); the run stops there. A cut run is `interrupted` and is never retried by itself. Settings (`fleet-update.json` beside the file): `signedTags`, `requireSignedTags`, `minFreeMb`, `minFreeMbServer`, `workspace`, `root`, `backups`, `owner`. `tools/make_fleet_sudoers.py` writes the rule of sudo for the account of the server: one line per command the tool issues, with the exact words and no wildcard (the check proves that every command the tool passes to sudo is one of its lines); the checkout of this repository must belong to root, because the installers run as root. Nothing here restarts the machine. It has not run on a CM5; `tools/verify_fleet_update.py` proves it on a simulated device.

**Two slots, built and checked on the host only.** `provisioning/ab_slots.py` is the state machine of a
two-slot (A/B) system image: an image is written to the idle slot after its SHA-256 matches, the boot
loader is asked to try it once (the Raspberry Pi `tryboot` entry of `autoboot.txt`), and the new system has
a time limit to report healthy. Only a healthy report in time (`confirm`) changes the default boot entry; a
late or missing report, a slot that never started, or a board that fell back to the old slot marks the tried
slot bad until a new image is written to it, so a bad image can never become the default. It decides and
records; a backend carries the decision out (`SimulatedBackend` for the checks, `AutobootBackend` for the
text of `autoboot.txt`), and it never runs `dd` or `reboot` itself. Every command that changes something is
refused unless `HYDRA_UMC_AB_SLOTS=1` is set (off by default), and a damaged state file is refused, not
repaired. `tools/verify_ab_slots.py` proves it with both backends and a seeded random walk. The image
builder does not yet produce two-slot images, no installer or unit calls it, and it has not run on a board:
that needs a CM5 with a boot loader that supports `tryboot_a_b`.

Firmware retains its own tested update and recovery process. Do not couple a
Raspberry Pi OS upgrade to a firmware change without a maintenance plan.
