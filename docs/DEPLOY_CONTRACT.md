# Deployment contract of the installers

The `provisioning/install_*.sh` scripts put one program of the CM5 in place: they copy it into `/opt/hydra-umc/<component>`, install its systemd unit and reload systemd. The
deployment contract adds what an update needs and a first installation does not: keep what is installed now, restart the unit if it runs, check that it answers, and put the
earlier program back if it does not. It is versioned, so that an installer and the tool that runs it can tell whether they speak the same one.

## Contract 1

An installer that follows contract 1:

1. declares `DEPLOY_CONTRACT=1` and sources `provisioning/deploy_lib.sh`, after it has checked `--apply` and `root` and has set `TARGET`;
2. calls `deploy_begin <SERVICE> "$TARGET"` before it changes anything in the target (`<SERVICE>` is the repository it installs, for example `HYDRA-UMC-SERVER`);
3. calls `deploy_finish <SERVICE> "$TARGET"` after its last `systemctl daemon-reload`, so that the unit that gets restarted is the new one.

`deploy_lib.sh` then does the rest through `tools/deploy_tree.py`:

| Step | What happens |
| --- | --- |
| `deploy_begin` | The program that is installed now (everything in the target except the folders that hold state) is kept as a numbered release in `/opt/hydra-umc/.releases/<component>/releases/`, unless an identical one is already kept. Nothing in the target changes. If the copy cannot be made the installer stops before it installs anything. |
| `deploy_finish` | The new program is kept as the current release. The same program as before: nothing else happens (`unchanged`). The unit is not running: it is left alone (`installed`; the operator enables it after review, as the installers say). The unit runs: `systemctl try-restart <unit>`, then the health route of the registry is polled (`http://127.0.0.1:<port><health_path>` from `provisioning/ports.yaml`, a 2xx on this machine; without a route, the unit has to be active) until it answers or `healthTimeoutS` passes. |
| It does not hold | The earlier program is put back in the target, the unit is restarted on it, and the installer ends with status 3. A first installation has nothing to go back to: it stays, and the status is 3 as well. |

The folders `data`, `models` and `workspace` of the target hold what the program writes; they are never kept, replaced or removed. A service user may write only in those
(`provisioning/install_plan.py --check` fails when an installer creates another folder owned by the service user).

### Settings

`/opt/hydra-umc/.releases/deploy.json` (all optional; a value that is not valid is replaced by the default and said on the standard error):

| Key | Default | Meaning |
| --- | --- | --- |
| `keep` | 2 | Releases kept per component (2 to 100); the one in use and the previous one are never removed. |
| `healthTimeoutS` | 30 | Seconds to wait for the health check (1 to 600). |
| `healthIntervalS` | 1 | Seconds between two tries (0.1 to 30). |
| `restartCommand` | `systemctl try-restart {unit}` | Another way to restart; `{unit}`, `{component}`, `{version}`, `{release}`, `{target}` and `{root}` are replaced. No shell runs it. |
| `healthCommand` | empty | A command that exits 0 when the program is healthy; it replaces the route (use it for a service whose route needs a token). |
| `restartOnDeploy` | `true` | `false` keeps the new program but never restarts the unit. |
| `rollbackOnFailure` | `true` | `false` keeps the new program when it does not hold (the status is still 3). |

`HYDRA_UMC_DEPLOY=off` in the environment skips both steps for one run, and the installer behaves as it did before the contract.

## Running it

`hydra-umc-os` (written to `/usr/local/bin` by `install_cm5_base.sh --apply`) runs an installer by project:

```
hydra-umc-os plan [PROJECT]            the row of the table: installer, unit, port, health route, contract
hydra-umc-os deploy PROJECT [--apply]  without --apply it only says what it would run
hydra-umc-os rollback PROJECT          the previous program back, restart and health check when the unit runs
hydra-umc-os status [PROJECT]          the releases kept and the history
```

`deploy --apply` ends with one JSON line (`result`: `deployed`, `installed`, `installed-not-restarted`, `unchanged`, `rolled-back`, `failed`, `refused`) and exits 0, 3 (the unit did
not hold and the earlier program is back), 2 (refused: unknown project, no contract, a contract this tool does not support) or the status of the installer. This is what the updater
runs after it promotes a project (`HYDRA_UMC_UPDATER_OS_DEPLOY`, in the updater's own documentation).

## The table and its versions

`provisioning/install_plan.json` is generated from the scripts (`python provisioning/install_plan.py`, checked by `--check`). Each row carries the contract the installer declares;
the file carries the contract the tool supports (`supported_contract`). `--check` fails when an installer that puts a unit in place neither follows the contract nor is listed
with the reason it does not (the agent of the node and the Wi-Fi setup service come from this repository and are not restarted by an installer).

A change that an installer written for contract 1 could not follow is contract 2: the lib and the command refuse an installer that declares another number, before anything is
installed, and the table says which installers have moved. Contract 1 is not changed in place.

## How the installers are produced

The `install_*.sh` of the programs that have a complete row in the table (repository, folder, user, units, contract 1) are generated, not edited: `python provisioning/generate_installers.py --replace`
writes them from `provisioning/install_plan.json` and `config/installer_generation.json`, so the guards, the service user, the program folder, the unit files, the project manifest and the calls
of the contract are the same in every one. What a program needs beyond that is a hook, `provisioning/build_hooks/<folder>.sh`, sourced as root after the service user and the folder exist and
before the shared copy step (compile, fetch the toolchain, install packages, create the settings file, lay out the workspace); it may define `hook_after_install`, which runs once the program
is installed, and it must not call `sudo`. `<folder>.preflight.sh` reads the options of the installer before the dry-run policy. `tools/verify_installer_generation.py` fails when a program that
needs a hook has none or when an installer differs from what the generator writes. The installers whose row is incomplete (the base system, the kiosk, the splash screen, the local agent, the
Wi-Fi setup, the industrial gateway, the technician, the vision streamer) keep their own script.
## What it does not do

* It does not deploy a signed package: that is `tools/deploy_release.py`, which keeps its own `releases/current` layout and is not wired to the units yet.
* It does not start a unit that is not running, and it does not enable anything.
* It has been run on a Linux host with systemd (a first installation, the same program again, a changed program with the unit running, and a health check that fails), not on
  the CM5.
