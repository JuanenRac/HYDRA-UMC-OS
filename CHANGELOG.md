# Changelog

## [Unreleased]

- **The update of everything installed asks a signed tag only of the programs of a list, keeps one exact copy per program, and has a rule of sudo without wildcards:** `signedTags` in `fleet-update.json` names the programs whose release tag must verify with `git verify-tag` (the server, which carries its Studio, and the critical services by default; `requireSignedTags` asks it of every program); the others are trusted by "the tag is the commit GitHub gives". The copy of a program is `<name>.bak.tgz` (the program, its unit and its drop-ins), and a program that was cut and is taken up again keeps the copy it already had instead of copying what may be half of the new one. `tools/make_fleet_sudoers.py` writes the rule of sudo for the account of the server, one line per command with the exact words. A program that the run had skipped because it stopped earlier can now be run in the next `run`; an unreachable GitHub is `no_release` for every row, including the Studio. A program that was cut after its installer had finished (the usual case of the server, whose installer restarts the unit that runs the tool) is taken up by the checks alone. `tools/verify_fleet_update.py` goes from 19 to 35 cases (taking up a failed program and going on, a second run with nothing to do, an installer that ends well but changes nothing, a backup that cannot be made, a tools checkout that does not match, the Studio tag that does not match, an unreachable GitHub, a dirty checkout, an inactive unit, the log, a file that is not a plan, the signed list and the sudo rule).

- **`tools/fleet_update.py` updates every installed program to the newest release, with the progress in a file:** `plan`, `run --yes`, `resume --yes --only <program>` and `status`, in the order of the dependencies and stopping at the first failure. Per program: free disk (more for the server), the tag fetched and compared with the commit GitHub gives (and its signature when `requireSignedTags` is on), a `.tgz` of the program with its unit files and a hash of each, the server built in named steps, the installer with `--apply`, then the checks (version, unit active, health route, no import error in the journal, the Python SDK importable by the unit). A failure puts the program back, removes the drop-ins the installer added and says whether the unit files are as they were; a cut run is `interrupted` and `resume` takes up that program. Nothing restarts the machine. `tools/verify_fleet_update.py` (19 cases on a simulated device, in the CI) covers the plan, the order, the way to done, a failing installer, a failing health check, an import error, the SDK off the path, a tag that is not the commit GitHub gives, an unsigned tag, a full disk, a failing build, the unit files after a rollback and a cut run; not yet run on a CM5.

- **The deploy tool and the package check keep one marker line that the server reads when Studio starts an update:** `tools/verify_deploy_release.py` now checks that a good install ends its standard output with `DEPLOY=PASS`, that a restart that fails puts the earlier release back with status 3 and one `DEPLOY=FAIL` line that says so, that a refusal (the same version) is a `DEPLOY=FAIL refused` line, and that `package_component.py verify` prints `PACKAGE=OK <component> <version> <sha256>` for a good package and `PACKAGE=REFUSED` with status 1 for an unsigned one. `docs/UPDATE_MODEL.md` tells how the server uses them and what is still missing on a device (units that run from the releases, the rule that lets the server restart its own unit).

- **The shared tools and the CI jobs have time limits:** the project tool, the validators and the build test pass a timeout to every child process (`HYDRA_UMC_GIT_TIMEOUT_S`, 120 s by default, and `HYDRA_UMC_COMMAND_TIMEOUT_S`, 3600 s by default; a value that is not a positive number means the default), and the baseline and notify jobs of the workflows carry `timeout-minutes`, so a stuck step ends with a message instead of holding a runner.
All notable changes to this project are documented here.

- **More tests of the agent and a simulation bench with a coverage floor:** `agent/tests/test_agent_edges.py` (80 tests) covers every refusal of the configuration, probe, socket and profile readers, the probe verdicts with a runner that answers by itself, the boundaries of the health thresholds, the report gate, the command line (`describe`, `health`, `query`, `serve` with a stopped loop) and a seeded fuzz of the configuration reader. `agent/tests/test_simulated_cm5.py` (15 tests) runs the real agent against a simulated Compute Module 5 (a warm-up, a brown-out, a filling disk, a pulled cable, a dead service, tools that are missing or hang) and a seeded random timeline that checks the overall state is always the worst check. The new workflow "Simulation bench" runs them with the socket tests and a job measures the coverage of the agent with a floor that must not go down. Nothing was run on a real board.

- **`LICENSE` holds the complete GPL-3.0 text, as the other repositories do:** until now it held a short notice. The notice moves to `LICENSE.md` (code under GPL-3.0-or-later, documentation under CC BY-SA 4.0, third-party software keeps its own license).
- **README: the platform statement:** the description says what this project serves today (the CM5 pilot bench) and that the target platform of HYDRA-UMC, an NVIDIA Jetson Orin NX 16 GB, is a design that has not been built or tested.
- **The certificate of the ROS 2 bridge and the identity switch of the broker in `hydra_mqtt_tls.sh`:** `env --client hydra-umc-bridge-ros2` prints the `HYDRA_UMC_ROS2_MTLS*` lines of that bridge (which refuses the `HYDRA_MQTT_TLS*` ones next to them) instead of the generic client lines, and `env --identity` adds `MQTT_TLS_CERT_IDENTITY=1` so the broker binds the certificate name to the client id (off unless asked for). `client hydra-umc-bridge-ros2` already made the certificate with that common name and a 0600 key. One more test in `tools/verify_mqtt_tls.py`. Nothing was run on a CM5.

- **Four more profiles for the kinds of node that need no new hardware code (`dsi`, `industrial`, `laboratory`, `fleet`) and a matrix of modules:** each is a declaration like `control` (the agent and the Server plus the services of that kind of node: safety zones and job dispatcher; datalake, telemetry collector and anomaly detector; orchestrator, swarm sync and node healing), nothing is installed or started by it, and a capability that needs hardware (`dsi_display`, `industrial_network`) is only named under `requires`. `tools/verify_profiles.py` loads every profile with the agent's own validator, checks that each service is the agent, the Server or a unit the install plan installs, and prints `docs/CM5_MODULE_MATRIX.md` from the profiles and the plan (the check fails when the committed matrix differs; `--write` rewrites it). The Debian package installs the new profiles. Not run on a real CM5.

- **The installer makes the directory of the trust store of the CM5, owned by root with mode 0700:** `install_cm5_base.sh --apply` runs `provisioning/ensure_trust_dir.py`, which loads `ensure_trust_dir` from HYDRA-UMC-DEV-SERVER (the program that reads the store and applies a signed rotation to it, so the rules of the directory stay in one place) and calls it for `/etc/hydra-umc/trust`. Without `--apply` it only says what it would do; a refusal of the function (not root) stops with status 2, and when that program is not found it ends with status 3, which the installer lets pass because the directory is created by root when the program is deployed. `tools/verify_trust_dir.py` proves the call with a stand-in package and, when the checkout of HYDRA-UMC-DEV-SERVER is next to this one, with the real function.

## [0.6.1] - A slot manager for a two-slot system image, off by default: `provisioning/ab_slots.py` writes an image to the idle slot after its SHA-256 matches, asks the boot loader to try it once (the Raspberry Pi `tryboot` entry of `autoboot.txt`) and makes it the default

- **A slot manager for a two-slot system image, off by default:** `provisioning/ab_slots.py` writes an image to the idle slot after its SHA-256 matches, asks the boot loader to try it once (the Raspberry Pi `tryboot` entry of `autoboot.txt`) and makes it the default only when it reports healthy inside a time limit; a late or missing report, a slot that never started or a board that fell back to the old slot marks the tried slot bad and leaves the default boot entry untouched. Commands that change something need `HYDRA_UMC_AB_SLOTS=1`, a damaged state file is refused and nothing runs `dd` or `reboot`. `tools/verify_ab_slots.py` (55 checks, a seeded random walk of 2400 operations) runs in the build test; not run on a board.
- **The packages the installers ask for are planned by apt on the release and architecture of the image:** `tools/apt_packages_check.py` reads the `apt-get install` commands of the installers (`--list`) and, in the arm64 trixie container of the manual QEMU workflow, asks apt to plan each installer's packages one installer at a time without installing anything (`--simulate`), so a name that does not exist in trixie or a conflict is reported with the installer that asked for it. `tools/verify_apt_packages.py` tests the reading (continuations, options, comments, stops at a pipe, names with a variable).
- **A Wayland session for the HDMI kiosk, off by default:** `install_kiosk.sh --session wayland` (or `HYDRA_KIOSK_SESSION=wayland`) installs cage and Chromium and no X server, window manager or compositing manager, and writes a profile line that runs `cage -- kiosk-session-wayland.sh` on tty1 only; the text consoles stay closed unless `HYDRA_KIOSK_ALLOW_VT_SWITCH=1` (then `cage -s`). It is the same locked account, browser profile, policy and flags as the X11 session, which stays the default and keeps the settings tuned on the device. A rerun removes the line of either session before writing its own. The manual workflow "Wayland kiosk on a virtual screen" runs the installer in dry-run for both sessions and starts the real session script under the real cage (headless) with the real Chromium as the kiosk account in a Debian trixie container; the check on the HDMI display itself is still to be done on the board.
- **A local UNIX socket for the agent, off by default:** `diagnostics.local_socket` makes `serve` also answer `describe` and `health` on a socket (`/run/hydra-umc-agent/agent.sock`, mode `0660` or stricter, never open to other users), one line of JSON per request; any other request, a request over 64 bytes or a client that stalls costs only that client; a `health` report is reused for `cache_seconds` so the probes cannot be run in a loop; a leftover socket of a dead agent is replaced and a live one, or a file that is not a socket, is never touched. The new command `query --socket PATH` reads it, the unit gets `RuntimeDirectory=hydra-umc-agent`, and `agent/tests/test_agent_socket.py` covers the configuration, the answers, the cache, the file mode and the start-up cases.
- **Optional probes in the agent, off by default:** `diagnostics.probes` adds `throttling` (`vcgencmd get_throttled`: under-voltage or throttling now is a FAIL, a cap or anything since the boot a WARN), `hailo` (the device node is there or not) and `unit:<name>` (`systemctl is-active`) to `health`. Nothing runs unless `enabled` is exactly `true`; the programs are started without a shell with a time limit, a missing, slow or failing tool is a WARN with its reason, and every key of the block is validated when the file is loaded. 22 new tests, 17 of them with a runner that answers by itself and 5 starting real stand-in programs on Linux (a script that prints what `vcgencmd` prints, one that hangs, one that exits with an error). Not tried with the real `vcgencmd`, a Hailo module or the units of a CM5.
- **The polkit rules are asked to a real polkit (manual workflow):** `tools/verify_polkit_rules.py` and the workflow "Polkit rules (manual)" copy `provisioning/polkit/*.rules` to a runner, create the accounts of the table and run `pkcheck` about a process of each of them: 28 cases, all as meant (reboot and power-off granted to `hydra-umc-server`, suspend and hibernate refused, start/stop/restart granted for other `hydra-umc-*.service` units, refused for the server itself, the Wi-Fi setup, the agent, `ssh`, other verbs, a name with upper case, an empty name or a suffix, a missing unit, and any other account). It runs on a runner; the same rules on a CM5 are still to be tried by pressing the button of the display.
- **A sudoers rule for the account of the updater, generated from the install plan:** `provisioning/sudoers.d/hydra-umc-updater` has one line per project that follows the deployment contract, each with the exact words `/usr/local/bin/hydra-umc-os deploy HYDRA-UMC-X --apply` (no wildcard: not `rollback`, not another argument, not another project). `tools/make_updater_sudoers.py` writes and checks it (`--check` is in the checks of a push), `install_cm5_base.sh` installs it only with `HYDRA_UMC_INSTALL_UPDATER_SUDOERS=1` (off by default) after `visudo -cf`, and `tools/verify_sudoers_rule.py` (in the same manual workflow) runs `sudo -n` as the account and as a stranger against a stand-in: 20 cases as meant. 6 new tests in `tools/verify_updater_sudoers.py`.
- **The installer checks run on arm64 under QEMU (manual workflow):** `qemu-arm64.yml` runs the plan check, the release guard, the dry run of `install_cm5_base.sh`, `bash -n` over every provisioning script and six verify scripts inside a Debian trixie arm64 container emulated with qemu-user, the architecture of the CM5. It finds what an x86-64 run cannot (a missing arm64 package, a path that differs); it is not the board and it runs no kernel or systemd.

- **The host firewall, loaded for real into network namespaces:** `tools/firewall_netns_check.sh` and the manual workflow "Host firewall in namespaces" load the rules of `provisioning/hydra_firewall.sh` into the nftables of a Linux kernel inside a namespace that plays the CM5, and connect to the broker, TLS and server ports from the field network, the clients' network and an outsider; the field reaches the broker, the clients only the server, the outsider neither, a port the table never mentions stays open and removing the table gives everything back. It proves the rules on real packets of a kernel, not on a CM5.
## [0.6.0] - The build test of the repository compiles only on CI or when allowed: for the stacks that compile (rust, go, android, flutter, firmware-c), tools/buildtest.py prints BUILDTEST=SKIPPED with exit status 2 on a plain PC, never a... (and 12 more changes)

- **The build test of the repository compiles only on CI or when allowed:** for the stacks that compile (`rust`, `go`, `android`, `flutter`, `firmware-c`), `tools/build_test.py` prints `BUILD_TEST=SKIPPED` with exit status 2 on a plain PC, never a pass; `ALLOW_LOCAL_BUILD=1` allows it and a CI runner always may. The `python` and `node` stacks are not locked.

- **The connector hub is in the list of services that take the identity of the server:** `config/service_identity.json` names its unit, its variable (`HYDRA_UMC_CONNECTOR_HUB_IDENTITY_KEY_FILE`) and its group, so the identity command hands it the key like the others; the hub keeps its own verifier and its EdDSA key set.

- **The identity guide describes the safe order for the identity of the services:** the calls of the server to the services now carry its signed token when its own switch is on, so the guide gives the order (the server first, then the key of each service one at a time with the provisioning command, and the way back in the opposite order). The test of the provisioning command makes a throwaway key for each run and never prints it.

- **The identity of the server reaches thirteen more services and nothing is open with it on:** `config/service_identity.json` lists the Python, Go and Rust services that take the signed token of the server, `docs/SERVER_IDENTITY.md` says how a container health check works once the key is on (the probe that signs its own short-lived token), and what is left with its reason.

- **The manual package build never checks out the program of another repository (`package-build.yml`):** the planning job resolves the ref, verifies that the commit is part of the main branch of that repository and reads its commit time; each program is then built in its own job (`build-os-agent`, `build-studio`) from an archive of exactly that commit fetched by its full hash, the Node.js setup has the package-manager cache switched off, and the package dates come from the verified commit, so no cache that code of another repository could write is ever read by a later run.

- **One identity for the services, off until asked (`provisioning/service_identity.py`):** `--enable NAME ...` gives a service the signing key of the server as a private key file (mode 0640, group of the service) and a systemd drop-in that turns on its `--identity-key-file` switch, so the service accepts the signed token of HYDRA-UMC-SERVER and refuses a request with no credential; `--disable` turns it off again and `--status` lists it. Dry run unless `--apply`, the key is never printed, and a missing, example or short `JWT_SECRET` is refused. The services live in `config/service_identity.json` (the cognitive node, the vision node and the VLA engine today); the design and the services still to follow are in `docs/SERVER_IDENTITY.md`. Checked by `tools/verify_service_identity.py`.

- **A manual smoke test of the installer (`install-smoke.yml`):** started by hand and by the owner only, so it never runs on a push. With `dry_run` on (the default) it runs `provisioning/install_cm5_base.sh` without `--apply` (Server and Voice UI included) and installs nothing; with it off it runs the installer with `--apply` inside a throw-away Debian container whose first process is systemd, then checks every unit it wrote with `systemd-analyze verify` and prints `systemd-analyze security`. It holds no key and publishes nothing.
- **The Wi-Fi setup page answers before the setup network goes down:** `provisioning/wifi_provision.py` now sends the answer ("trying to join") first and joins the chosen network afterwards, in its own thread after a configurable delay (`--join-delay-seconds`, `HYDRA_UMC_JOIN_DELAY_S`, default 3). The outcome is read at `GET /status` and on the page after the phone reconnects to the setup network, and is kept in `last_join.json` of the state folder (never the password). A second attempt while one runs is refused (409), the setup window is not closed under a running attempt, and the loop no longer blocks while `nmcli` works.
- **The recovery backup follows what is installed:** `provisioning/cm5_recovery.sh` takes its scope from `provisioning/recovery_scope.py`: every `/etc/hydra-umc*` and `/var/lib/hydra-umc*` folder, the `data` folder of every program, all `hydra-umc-*.service` units and the polkit rules. SQLite databases are copied with the SQLite backup API (consistent while a service writes) and the live files are left out; a restore stops every running `hydra-umc-*` service, removes stale `-wal`/`-shm` files and refuses any path outside the scope. New check: `tools/verify_recovery_scope.py` (runs the real script against a temporary root).
- **Dependencies are installed without their install scripts:** the build hooks of the server and the dashboard pass `--ignore-scripts` to `npm ci` unless `npm_scripts = on` is set in `/etc/hydra-umc/provisioning.conf` (or `HYDRA_UMC_NPM_SCRIPTS=on`), and the dashboard builds as the user who owns the checkout, not as root. New check: `tools/verify_npm_installer.py`.
- **Narrower systemd units:** the agent unit gets `ProtectProc=invisible`, `PrivateDevices`, `ProtectClock`, `ProtectKernelLogs`, `RestrictNamespaces`, `RestrictAddressFamilies=AF_UNIX`, a system call filter and a working directory in the data folder; the Wi-Fi setup unit (root) gets `ProtectSystem=strict`, a private `/tmp`, an address family list, a system call filter and the other `Protect*`/`Restrict*` directives. The disk check of the agent measures the volume named by `diagnostics.storage_path` (default: the working folder). New check: `tools/verify_unit_hardening.py`. The measured exposure level on a device is still a bench step.

- **A package of a program of the CM5 is built the same way every time, and GitHub Actions builds it twice:** `tools/package_component.py` now writes a package with fixed times, owners and gzip header, so the same files give the same bytes (a test checks it after the files get a later time). The manual workflow `package-build.yml` (owner only, pinned commit, dry-run style: nothing is published) builds `studio` or `os-agent` (the server needs its frontend assembled into `public/` first, which is not built there yet) on an x86-64 and an arm64 runner, stops unless both give the same package, and uploads it with its hashes, a build manifest and a build-provenance attestation. It holds no key: the package is signed afterwards on the maintainer's machine.

- **A credential for the droid bridge, and the global stop can be read:** `provisioning/gateway_env.py` now creates a credential and an ACL rule for `droids` (its own namespace, like the other machine bridges), and every bridge rule may subscribe to the retained global stop announcement (`hydra/swarm/safety/estop`) without being able to publish to it, so a bridge that follows the global stop hears it when the broker enforces the ACL. An existing `gateway.env` is not rewritten. Two more checks in `tools/verify_gateway_env.py`.

## [0.5.9] - The check of an environment file reports the line and the reason, never the setting's text: provisioning/generatesecrets.py --check now prints line N and a fixed reason (example value, empty, too short) for every secret... (and 4 more changes)

- **The check of an environment file reports the line and the reason, never the setting's text:** `provisioning/generate_secrets.py --check` now prints `line N` and a fixed reason (example value, empty, too short) for every secret setting it refuses, so the report is never built from what the file contains; `problem_codes()` gives the same facts to other tools, and a test covers the report.

- **Generated passwords go to a root-only file, not to the journal:** `provisioning/gateway_env.py` (the MQTT credentials of the machine bridges) and `provisioning/wifi_provision.py` (the password and the setup code of the Wi-Fi setup network) write the values to a file only root can read (mode 0600, in a folder with mode 0700, written in one step from a temporary file) and print its PATH and the command that reads it, never the values. The setting `print_once` (`--print-once` / `--no-print-once`, `HYDRA_UMC_PRINT_ONCE`, or `print_once = true` in `/etc/hydra-umc/provisioning.conf`; off by default) brings back the old behaviour, printing the values once when they are created, for a device without a screen. An existing file is never overwritten, a mode more open than 0600 is corrected and a link is refused. The shared code is `provisioning/secret_output.py` (installed next to `wifi_provision.py`); `tools/verify_gateway_env.py` checks the modes, that nothing is printed by default, that `print_once` prints once and the atomic write. How to read and rotate the passwords: `docs/CM5_PROVISIONING.md`.
- **The password of the first administrator goes to a root-only file too:** `provisioning/generate_secrets.py` (run by `install_server.sh`) writes the generated `HYDRA_UMC_BOOTSTRAP_ADMIN_PASSWORD` to `credentials/server-admin.txt` next to the env file (`--admin-credentials-file` to choose another; mode 0600 in a folder with mode 0700, written in one step, a link is refused) and prints its PATH and the command that reads it (`sudo cat`), never the value. The same `print_once` setting as `gateway_env.py` and `wifi_provision.py` (`--print-once` / `--no-print-once`, `HYDRA_UMC_PRINT_ONCE`, `print_once = true` in `/etc/hydra-umc/provisioning.conf`; off by default; the code is `provisioning/secret_output.py`) also prints it once for a device without a screen. If the credentials file already exists the run stops before it writes anything, so a password is never lost and a file is never overwritten; an env file that already has its password is left as it is. To keep the old behaviour switch `print_once` on before the first start. Verified by `tools/verify_generate_secrets.py` (the modes, that nothing is printed by default, the three ways to turn `print_once` on and which one wins, the existing file and the link); the README says so in the 8 languages. How to read and rotate it: `docs/CM5_PROVISIONING.md`.
- **The installers open the common `GET /health` of ten services on the CM5:** the services that answer `404` on `GET /health` until the operator opens it (the anomaly detector, cognitive node, data lake, detection HEF, docs QA, production reports, safety zones, semantic planner, vision node and visual servoing API; the data lake and the production reports used to answer it to anybody) get from their `install_*.sh` the drop-in `10-health-open.conf` of their main unit with `HYDRA_UMC_<SERVICE>_HEALTH_OPEN=1`. The list is `health_open` in `config/installer_generation.json`; the generator writes the lines, the ten installers are regenerated and `tools/verify_installer_generation.py` checks them. The health paths of `provisioning/ports.yaml` are unchanged.
- **Bench test script:** `docs/BENCH_TESTS.md` lists the checks of the installers, the update and recovery scripts, the agent and the kiosk that need a Compute Module 5, all marked not executed, with the known gaps.

## [0.5.8] - The installers are generated from the manifests with a build hook for each program that needs one, a panel of the permissions of the secrets and the check of the generation in the build

- **Installers generated from the table:** `provisioning/generate_installers.py` writes an `install_*.sh` from each row of `install_plan.json` (guards, system user, program folder, unit files, project manifest and the deployment contract); whatever a program does beyond the shared shape goes in `provisioning/build_hooks/<name>.sh`, which the generated script sources, and the options that must be read even in a dry run in `<name>.preflight.sh`. `--check` proves every generated script reads back as its row, that every program that needs a hook has it and that bash parses all of them; nothing is executed. Writing over the scripts of `provisioning/` is only done by the explicit `--replace` command, after the whole check passes (the option `allow_replace_existing` of `config/installer_generation.json` stays off). New verification: `tools/verify_installer_generation.py`, which also fails when an installer of the folder differs from what the generator writes.

- **Changed: the installers are generated from the manifests.** 21 of the `install_*.sh` (one per program; the server, the voice interface, the data lake, the compiled and the Python programs) are now the output of `generate_installers.py` instead of copies written by hand, and 21 build hooks keep what each one did beyond the shared steps (compiling the Rust and Go programs, building the web apps, the settings files with their secrets, the workspaces, the optional journal). The steps, the users, the folders, the permissions, the units and their order are the same as before; the differences that exist are that a dry run only says that it is one (it no longer lists each step), that the source folder is checked right after the service user is created, and that the installer of the watchdog now accepts `--apply` in any position. The installers of the base system, the kiosk, the splash screen, the local agent, the Wi-Fi setup, the industrial gateway, the technician and the vision streamer keep their own scripts. Not run on the CM5.
- **Hooks and tests follow the new layout:** the verification of the Go toolchain, of the optional journals, of the voice interface contract and of the result keys read an installer together with its hook.
- **A secrets and permissions panel in the runtime check:** `verify_cm5_runtime.sh --secrets` lists owner, group and mode of the files of `/etc/hydra-umc` that hold secrets (policy in `config/secrets_policy.json`: folder, name patterns, owner, group prefix and loosest mode) and fails on a file open to everybody; it never opens a file, so no value is read or printed. `--json` prints the whole runtime check (and the panel) as one JSON document for STUDIO and the operations agent, with the same exit code. Off unless asked for. New module `provisioning/secrets_panel.py` and `tools/verify_secrets_panel.py`.

## [0.5.7] - A deployment contract for the installers with one table of them, hydra-umc-os deploy PROJECT and a tool that installs a signed package as a numbered release and goes back when it does not hold

- **A deployment contract for the installers** (`docs/DEPLOY_CONTRACT.md`, contract 1): an installer declares `DEPLOY_CONTRACT=1`, sources `provisioning/deploy_lib.sh`, calls `deploy_begin` before it changes the target and `deploy_finish` after its last `systemctl daemon-reload`. The program that is installed now is kept as a numbered release (`tools/deploy_tree.py`, under `/opt/hydra-umc/.releases`; the folders `data`, `models` and `workspace` are never kept, replaced or removed); the new one is kept as the current release; a unit that runs is restarted with `systemctl try-restart` and its health route (or, without one, that the unit is active) is polled until `healthTimeoutS`; a unit that does not come back gets the earlier program put back, is restarted on it, and the installer ends with status 3. A unit that is not running is never started or restarted, the same program is not kept twice, and `HYDRA_UMC_DEPLOY=off` skips both steps. 22 installers follow it (the agent of the node and the Wi-Fi setup service are listed in the table with the reason they do not). Settings in `deploy.json` (`keep` 2, `healthTimeoutS`, `healthIntervalS`, `restartCommand`, `healthCommand`, `restartOnDeploy`, `rollbackOnFailure`). Run on a Linux host with systemd and a real unit (first installation, the same program again, a changed program with the unit running, a health check that fails and the program put back); not run on the CM5.
- **`hydra-umc-os deploy <PROJECT>`:** `provisioning/hydra_umc_os.py` (written to `/usr/local/bin/hydra-umc-os` by `install_cm5_base.sh --apply`) resolves a project (repository, short name or script) in the table of installers, refuses what does not follow the contract it supports (an installer that declares another number, or none), runs its installer with `--apply` and reports one JSON line with the exit status (0, 3 when the unit did not hold and the earlier program is back, 2 refused). `plan`, `rollback` and `status` complete it; without `--apply` it only says what it would run. The updater calls it after a promotion.
- **The table of installers is versioned:** `install_plan.json` is `hydra-install-plan/2`, carries `supported_contract`, the contract, the service and the state folders of every installer, finds the program and folder of an installer that sets them on one line (`install_server.sh`), and `--check` fails for an installer that puts a unit in place without following the contract or being listed with the reason, one whose `deploy_finish` comes before the last reload, and a service user that writes in a folder a release would replace.

- **The installers of the programs as one table:** `provisioning/install_plan.py` reads from each `install_*.sh` the repository it installs, the folder below `/opt/hydra-umc`, the system user, the unit files and whether it runs `git clone`, joins the port, the health path and the unit of the registry, and writes `provisioning/install_plan.json` (29 installers). `--check` fails when the table is out of date, when a service of the registry has no unit file in its script, when the target folder is not named after the unit or when a script does not install the `hydra-umc.project.json` of its project; `tools/verify_install_plan.py` (in the CI) proves it. It is the starting point of one installer driven by data; the 29 scripts still do the installing.

- **A tool that installs a signed package as a numbered release and goes back when it does not hold:** `tools/deploy_release.py` verifies the package (`package_component.py`: hash, Ed25519 signature of the component, version and hash, only paths of the layout), refuses the same or an older version unless asked, extracts it into `<root>/<component>/releases/<version>-<n>`, switches `current` (a link where the host can make one, `state.json` always) and runs the restart and health commands of `<root>/deploy.json` (empty by default, so nothing outside the root is touched); when the restart or the health check fails the earlier release is put back and restarted and the exit status is 3. `rollback`, `prune` (never the release in use nor the previous one) and `status` complete it, and 19 tests run it in temporary folders with no systemd and no network (`tools/verify_deploy_release.py`, in the CI). The installers of the programs do not use it yet and it has not been run on a CM5.

## [0.5.6] - One local screen at a time, a server install that checks the 3D models of the frontend and the example downsampling units of the data lake

- **`install_datalake.sh` also installs the example downsampling units (never enabled):** the script and the `.service`/`.timer` of the data lake are copied next to the retention units; they are a dry run until the operator sets `HYDRA_UMC_DATALAKE_DOWNSAMPLE_DRY_RUN=false`, and the final message tells how to enable the timer.

- **The server install checks that the frontend has its 3D models:** `install_server.sh` stops with the steps to follow when the STUDIO build it would install has no model files (they now come from one verified package and not from the repository), and `CM5_DEPLOYMENT_SEQUENCE.md` has a new step 5b with the exact order to update the CM5 (pull, bring the models with or without Internet, rebuild the frontend, install, restart). Written and checked against stubs; it has not run on a CM5.
- **One local screen at a time:** `install_kiosk.sh` reads a new setting, `HYDRA_LOCAL_SCREEN` = `hdmi` | `dsi` | `none` (the environment, then `/etc/hydra-umc/local-screen.conf`, then `hdmi`, which is the default and what it did before), through the new `provisioning/local_screen.sh`; `--screen hdmi|dsi|none` saves the choice. It installs the HDMI kiosk only for `hdmi`: for `dsi` or `none` it takes back the autologin it put on `tty1` and installs nothing (for `none` it also switches the DSI app off and gives `tty1` back to the console login), and for `hdmi` it switches the DSI app of HYDRA-UMC-DSI off if it is installed. The kiosk account's profile no longer starts X when the saved choice is `dsi` or `none`. A value that is none of the three stops the installer. `tools/verify_kiosk_installer.py` tests it against stubs; it has not run on a CM5.

## [0.5.5] - The server environment example with the server port variable, a new installation that starts with TLS and the universal README

- **The server environment example uses `HYDRA_UMC_SERVER_PORT`:** the example `server.env` sets the port of the server with the variable of the service instead of the shared `PORT`; an environment file that still has `PORT` keeps working, with a warning.

- **A new installation starts with TLS:** `install_industrial_gateway.sh` treats an installation without a `gateway.env` as new, makes the certificates of its own authority with `hydra_mqtt_tls.sh init` when they are not there, and `gateway_env.py` writes `MQTT_TLS_DIR` into the new file so the broker starts on TLS. An installation that already has the file is not changed; `HYDRA_UMC_NEW_INSTALL_TLS=off` skips the authority step. The server side of the same default is in HYDRA-UMC-SERVER.

- **README in the universal layout:** the README and its seven translations follow the layout that the four families share (22 sections in a fixed order), with an architecture picture and a repository-structure picture drawn from `docs/architecture.json` and `docs/structure.json`; the CI validator checks both pictures and the file tree.

- **The layout of the README is checked in the CI:** the validator runs `tools/universal_readme_check.py` and lists, as a warning, what differs from the universal layout of the README.

## [0.5.4] - The installers hand out the signing keys and the Go services are built with a pinned Go

### Firmware and protocol

- The agent in `serve` mode can write a report only when the overall state or the state of a check changes, plus a heartbeat every five minutes (`--report-on-change`, `--heartbeat`). The installed unit turns it on, which keeps the journal short; running the agent by hand still writes every report. Tested.
- The READMEs no longer say the agent can report an inhibited state (it reports READY, DEGRADED or FAULT), describe the per-device access point password and one-time setup code instead of a placeholder password, and list the projects that are not children of this repository under directly related ones. The same check keeps them from drifting.

### Programs and windows

- **The HDMI kiosk runs as its own locked account** (`install_kiosk.sh`): `hydra-umc-kiosk` (a normal user with a login shell, a locked password, no sudo, only the `video`, `render` and `input` groups; `HYDRA_KIOSK_USER` names another existing account) autologins on tty1 and runs the browser, where it used to be the administrator who ran the script, so a keyboard on the screen, or a way out of the browser, no longer gives their session. The kiosk line of an earlier version is taken out of that administrator's `.bash_profile`. X no longer lets the keyboard switch to a text console or kill the server (`DontVTSwitch`, `DontZap`; `HYDRA_KIOSK_ALLOW_VT_SWITCH=1` leaves it alone), and a Chromium policy turns off the developer tools, the password manager and sign-in. The browser profile is new, so STUDIO asks for its login once. New `tools/verify_kiosk_installer.py` (13 tests: static checks, and the account and profile blocks run in bash against stubs in a temporary folder). Not run on a real HDMI screen.
- **Audit journals in the installers, on by default**: `install_local_technician.sh` switches on the technician's append-only, hash-chained audit journal and `install_node_healing.sh` the watchdog's journal, both rotated at 5 MiB with 5 files kept, because what the technician was asked to do and what the watchdog decided about a node is the evidence that matters after a failure. Each installer writes a documented settings file (`/etc/hydra-umc-local-technician/local-technician.env`, read by the CLI wrapper, and `/etc/hydra-umc-node-healing/journal.env`, read by the unit) with the line active, and never overwrites an existing one. `--no-audit` / `--no-journal` (or `HYDRA_UMC_LOCAL_TECHNICIAN_AUDIT=off`, `HYDRA_UMC_NODE_HEALING_JOURNAL=off`) leave a journal off and comment an active line out, never deleting what was recorded; `--audit` / `--journal` are still accepted and mean the default. Unknown options and bad values are refused.
- Added `provisioning/os_release_guard.py`, run by `install_cm5_base.sh` before anything is changed: it warns when the system is not Debian trixie. `HYDRA_UMC_OS_GUARD=enforce` stops the installer instead, `off` silences it and `HYDRA_UMC_SUPPORTED_DEBIAN` lists the accepted releases. Tested by `tools/verify_os_guard_and_docs.py`.

### Tests, builds and checks

- **The installers hand out the signing keys.** `HYDRA_UMC_VOICE_UI_RESULT_KEY` (the key the Voice UI signs the result of a confirmation with and the server checks) is generated once per device by whichever of `install_server.sh` and `install_voice_ui.sh` runs first and written to both env files (a file from an older template gets the line), with `HYDRA_UMC_VOICE_CONFIRM_REQUIRE_SIGNATURE=1` for the server and `HYDRA_UMC_VOICE_UI_REQUIRE_SUBJECT=1` for the Voice UI; `generate_secrets.py` gains `--ensure KEY[=VALUE]` (adds a missing line, never changes one that is there) and refuses a `*_RESULT_KEY` shorter than 32 characters. `install_local_technician.sh` creates `/etc/hydra-umc-local-technician/result.key` with the new `provisioning/make_result_key.py` (64 random hexadecimal characters, 0600 from the first byte, never printed, never replaced, never followed through a symbolic link) and writes `HYDRA_UMC_LOCAL_TECHNICIAN_RESULT_KEY_FILE` to its settings file; `--no-signing` / `HYDRA_UMC_LOCAL_TECHNICIAN_SIGNING=off` leaves it out. Checked by `tools/verify_result_keys.py` (19 tests); not run on a CM5.
- **The Go services are built with a pinned Go.** `install_node_healing.sh` and `install_telemetry_collector.sh` installed the `golang-go` of the Debian archive, older than their `go.mod` asks for, so they could not build; they now use the same checksum-verified go.dev release as `install_job_dispatcher.sh`, which moved into the shared `provisioning/go_toolchain.sh` (one pin to raise). New `tools/verify_go_toolchain.py`, run by `build-test` and CI. Not run on a real CM5.
- **The secrets of the Industrial Gateway stack leave the user's checkout**: `install_industrial_gateway.sh` writes them to `/etc/hydra-umc/gateway.env` (root only, 0600; `HYDRA_GATEWAY_ENV` names another place) and every `docker compose` command takes `--env-file` for it, so a `git clean -xdf` or a fresh clone cannot take them away and the updater, which works as a normal user in that checkout, has no file of root to trip over. The compose file does not change. A `.env` left in the checkout by an earlier version is moved to the new place (moved, not copied: there is never a second copy), and if both files exist the new one wins and the old one is reported, not touched. New `tools/verify_gateway_installer.py` (8 tests: static checks of the script and the move block run in bash in a temporary folder). Not run on a real CM5, with Docker.
- **The installers read the service registry.** New `provisioning/service_registry.sh` reads the port, the health route and the systemd unit of a service from `provisioning/ports.yaml` (a copy of `HYDRA-UMC-SDK/contracts/ports.yaml` that the SDK keeps identical). The 21 installers of a service end by saying where to look once it runs (`curl --fail http://127.0.0.1:<port><route>`), and the installer of the industrial stack does it for its four parts. `verify_cm5_runtime.sh --with-services` probes the health route of every running service of the registry, skips what is not running and stays read-only. The registry now carries a health route for every service that speaks HTTP (22 of 24; the MQTT broker and the OPC-UA server have none on their port). New `tools/verify_service_registry.py` (run by `build-test` and CI) with 15 tests, among them the runtime check against stubs of `systemctl` and `curl`. Not run on a real CM5.
- New `tools/verify_optional_journals.py` (run by `build-test` and CI): syntax, dry run, refusals, defaults, the documented settings files and, when the sibling projects are checked out, that the names the installers write are the ones the projects read. Not run on a real CM5.
- Building no longer changes the version; raising it is the explicit `bump` command (`python tools/hydra_project_tool.py bump`). The build scripts only report the version they built, and CI fails if a build script runs a bump.
- The Debian package of the platform base is complete: `tools/build_deb.py` builds `hydra-umc-platform-base_<version>_all.deb` in plain Python (no dpkg needed, the same bytes every time) with the agent, the command, the unit, the example configuration and profiles, and post-install, pre-removal and post-removal scripts that create the service account and directories, keep an existing configuration and never enable or start the service. `tools/verify_deb_package.py` reads the archive back (and asks `dpkg-deb` when it is installed). The old incomplete package metadata is gone. Not installed on a real CM5 yet.

### Other changes

- The update model document says plainly that it describes the target contract and that no component implements it end to end yet.
- Every device now gets a name of its own: the default host name (`first_boot.sh`) and the default name of the setup network end with six characters taken from the device (the Raspberry Pi serial number, else the MAC address, else the machine id), so two devices flashed from the same image no longer share a name. A host name or network name chosen by the operator is never changed, and `HYDRA_UMC_DEVICE_SUFFIX=off` keeps the fixed names. The setup unit no longer fixes the network name on its command line. Tested by `tools/verify_device_identity.py`.
- `bump_version.py` no longer carries a rule of its own: it runs the shared utility and then carries the agent's own version along. Tested by `tools/verify_bump_version.py` over the roll-overs.
- The `control` profile now declares `hydra-umc-server` next to the agent; the profile stays an editable declaration (copy it, drop the entry, pass it to the preflight with `--profile`). Tested.

## [0.5.3] - Component packages, broker TLS, a firewall and encrypted settings backups

- The banner follows the animated style of the ecosystem banners, with the name, the kind and the technologies of the project.
- Added `tools/package_component.py`: packs the server, Studio or the device agent as `hydra-<component>-<version>.tgz` with its `.sha256` and an Ed25519 `.sig` over the component, the version and the hash. `verify` refuses a changed package (even with a rewritten hash), a missing or foreign signature, a package passed off as another component or version, and members that are links or leave the target. The public key is `config/release_key.pub`; the private key is never in a repository. Tested by `tools/verify_package_component.py` (RFC 8032 vectors, 18 tests).
- Added `provisioning/hydra_mqtt_tls.sh`: a certificate authority of this installation, the certificate of the broker and one certificate per bridge for mutual TLS. Tested with real handshakes by `tools/verify_mqtt_tls.py`.
- Added `provisioning/hydra_firewall.sh`: nftables rules that close the broker ports to everything but the field network and the server port to the clients' network, without taking over the machine. Tested by `tools/verify_firewall.py`.
- Added `provisioning/backup_settings.sh` and `restore_settings.sh`: an AES-256 encrypted backup with a keyed hash that is checked before anything is decrypted. Tested by `tools/verify_backup_settings.py`.
- CI runs the four new checks.

- Added `tools/hydra_project_tool.py`: the same `validate`, `test`, `version`, `status` and `bump` commands in every repository. The checks run with `HYDRA_UMC_CI=1` and fail if the version changes; only `bump` changes it.

## [0.5.2]

- Maturity is functional: nothing here has been verified on real hardware yet.
- The READMEs say, in the eight languages, what is planned and what has only been tested against fakes, emulators or fixtures, and carry a short safety and security status note.

## [0.5.1]

- Build version synchronized with `hydra-umc.project.json` and the repository-native version source.
- The licence is written as GPL-3.0-or-later in every header and in the package metadata.

## [0.5.0] - Trixie everywhere

- Comments and docs that still named Debian bookworm as the base (the job dispatcher's Go install note, the Wi-Fi setup module, the installation guide) now say trixie, matching `install_industrial_gateway.sh` and the base image the Rebuilder downloads.

## [0.5.0]

- Automated build version increment from 0.4.9.

## [0.4.9] - A build that works again, an agent that keeps running, a setup form that stays closed

- The agent in the package said 0.4.6 although the product was 0.4.8, and `bump_version.py` refused every build because the manifest and the package disagreed. Both are 0.4.9 now, the manifest follows the version in `agent/pyproject.toml` (a changelog edit can no longer hide the drift) and a test pins the agent version to the manifest.
- `install_server.sh` and `install_voice_ui.sh` changed the owner of an existing `/etc/hydra-umc` to root:root, after which the agent (group `hydra-umc-agent`) could no longer read its configuration and restarted in a loop; an existing directory is now left alone.
- The Wi-Fi setup service served its form on every port 8080 interface for 30 minutes at every boot even when the device was already online, which delayed `network-online.target` and left a root-run form open on the production network. It now exits at once when the device is connected. A non-numeric `HYDRA_UMC_AP_WINDOW_S` falls back to the default instead of crash-looping, and the access point password and setup code are written to the journal only when they are generated.
- The agent in `serve` mode prints one compact line per report instead of 25 indented lines every 30 seconds.
- `generate_secrets.py` treats an empty `JWT_SECRET` as a problem (the Server refuses it) and a mirrored env file keeps its owner, group and mode.
- `gateway_env.py` also creates a credential and an ACL rule (`vda5050/#`) for the AMR bridge, which connects to the broker like the others.
- The polkit rule for the Server only allows start, stop and restart, and never of the Wi-Fi setup or agent units.
- `build-test` skips the voice gateway contract check, with a notice, when the sibling Voice UI checkout is missing, instead of failing.
- The architecture document no longer says the agent produces `INHIBITED` (it is planned); checks went from 46 to 49 for Wi-Fi, 22 to 23 for secrets and 12 to 13 for the gateway environment, plus 2 agent tests (17).

## [0.4.8] - Secrets generated per device, a Wi-Fi setup network with its own password and code

- New `provisioning/generate_secrets.py`: `install_server.sh` and `install_voice_ui.sh` create their env file from the example when it is missing and replace every example value (`JWT_SECRET`, the bootstrap administrator password, the voice relay token) with a random one of the device; a value the operator already chose is left alone, the voice relay token is the same in `server.env` and `voice-ui.env` whichever is installed first, the administrator password is printed once, and the installers refuse to go on while an example value or a short secret is left.
- `preflight_cm5.py` fails when a `/etc/hydra-umc/*.env` still carries an example value or a short secret (`--env-dir`, skipped on a host without that directory).
- New `provisioning/gateway_env.py`: `install_industrial_gateway.sh` writes the `.env` of the Industrial Gateway stack (the gateway's JWT secret, one MQTT credential and one ACL rule per machine bridge, shown once), which the production gateway and broker now require.
- The Wi-Fi setup network no longer has a published password: each device generates its own 16-character password and a one-time 8-digit setup code on its first start (kept in `/var/lib/hydra-umc/wifi-provision/credentials.json`, 0600, and logged once for the device label); the setup form asks for the code and locks for a minute after five wrong ones, the network stays open 30 minutes after each start (`HYDRA_UMC_AP_WINDOW_S`), and the form refuses requests over 4 KB.
- `tools/verify_generate_secrets.py` (22 checks), `tools/verify_gateway_env.py` (12 checks), 22 more Wi-Fi checks (46 in total) and one more preflight negative check; the README says so in 7 languages plus a Portuguese README.

## [0.4.7] - first_boot.sh: real fix for Bluetooth devices that pair but never bond

Found live pairing a physical Xbox controller directly to a CM5: BlueZ's own default
`ClassicBondedOnly=true` (`/etc/bluetooth/input.conf`) refuses the HID connection for any device that
bonds over LE rather than classic BR/EDR on this hardware (Raspberry Pi's own Broadcom BCM4345C0) -
`bluetoothctl pair`/`trust` both genuinely succeed, but the device is stuck at Paired=yes/Bonded=no
forever and never becomes a real `/dev/input` device. `first_boot.sh` now sets
`ClassicBondedOnly=false` and restarts `bluetooth` as part of base provisioning, idempotently and with
the same dry-run/apply convention as every other step in this script. Unblocks HYDRA-UMC-SERVER's own
new `POST /api/system/bluetooth/pair` (Config > Bluetooth in STUDIO).

## [0.4.6] - install_local_technician.sh real bug: configs/ isn't a real, versioned directory

Found running the new script for real against a fresh clone: `configs/`
is genuinely empty and untracked in HYDRA-UMC-LOCAL-TECHNICIAN's own
repository (its own `.gitignore` deliberately keeps real config out of
version control) - `cp -a "$SOURCE/configs" ...` only ever worked by
accident on a dev checkout that happened to have a local, uncommitted
`configs/` directory lying around, and failed outright on the real CM5
against a genuine fresh clone. Dropped; only `src/` and `contracts/`
(both real, tracked directories) are installed.

## [0.4.5] - HYDRA-UMC-LOCAL-TECHNICIAN: installable on the CM5 for the first time

New `provisioning/install_local_technician.sh`. HYDRA-UMC-LOCAL-TECHNICIAN
(family "Cognitive AI Node", parent HYDRA-UMC-COGNITIVE-NODE) has a real,
tested CLI (`hydra-umc-local-technician`) but had never been installed
anywhere on this device - genuinely invisible in STUDIO's own AI Family
panel, not stale. Unlike every other project this repo installs, it
declares no `service` block and has no systemd unit yet (Fase 0 of six -
a bounded, policy-gated CLI, not a standing daemon, see its own README
Roadmap): this script only drops its real source/contracts and its own
manifest at the same real `/opt/hydra-umc/<name>/` host path every other
project's manifest lives at, so `GET /api/ecosystem/status` picks it up
and reports it honestly as "not a service" (`live: null`), the same
convention every other CLI/library-shaped project already gets.

## [0.4.4] - Real bug found live: every install_*.sh deployed a build that never updated its own manifest

Live report: STUDIO's own Services and AI Family panels showed every
CM5 project stuck on ancient version numbers no matter how many real
updates had actually been installed since. Root cause, confirmed
against the real device: every `provisioning/install_*.sh` here copies
a project's built artifacts (its compiled binary, its `dist/`, its
`package.json`) into `/opt/hydra-umc/<name>/` on every real re-install,
but never that same project's own `hydra-umc.project.json` - the one
file `GET /api/ecosystem/status` (HYDRA-UMC-SERVER) actually reads for
name/version/maturity/family. Whatever manifest happened to land there
on the very first install (by hand, once) stayed frozen forever after,
completely decoupled from the real, current code sitting right next to
it - confirmed live: `/opt/hydra-umc/server/package.json` (updated
more recently) reported a different, newer version than its own sibling
`hydra-umc.project.json` (left untouched for much longer).

Fixed in all 22 project-deploying scripts that were missing it (every
`install_*.sh` except `install_cm5_base.sh`/`install_kiosk.sh`/
`install_splashscreen.sh`/`install_wifi_provision.sh`, which install
OS-level components with no sibling GitHub project/manifest of their
own): each now copies its own `hydra-umc.project.json` into its real
`/opt/hydra-umc/<name>/` target as the last real step before
`systemctl daemon-reload`, so a re-run always leaves the manifest
reporting exactly the source that was actually just installed.

`install_industrial_gateway.sh` needed a different real fix, not just
the same copy: its whole stack (HYDRA-UMC-GATEWAY-INDUSTRIAL/
OPCUA-SERVER/MQTT-BROKER/MTCONNECT-ADAPTER) runs as Docker containers,
so none of the 4 ever had an `/opt/hydra-umc/<name>/` directory for a
manifest to live in at all - genuinely invisible to
`getEcosystemStatus()`'s discovery, not just stale. Now drops each of
the 4 real manifests at the same real host path every other project's
manifest lives at, so the same discovery path picks these up too
without the container itself needing to know that directory exists.

Verified: `tools/build_test.py` (agent tests, all 6 verify_*.py
scripts, `preflight_cm5.py --skip-sdk`) and `tools/ci_validate.py` both
pass; every touched script re-checked with `bash -n` (real syntax
check, all 24 clean).

## [0.4.3] - Real CI bugs fixed: a sibling checkout that always failed, and an agent that couldn't load standalone once it did

found and fixed on review of the GitHub Actions runs across the
ecosystem:

- **The "Check out HYDRA-UMC-SDK as a real sibling checkout" CI step**
  used `actions/checkout@v5` with `path: ../HYDRA-UMC-SDK` - outside
  `$GITHUB_WORKSPACE`, which the action itself refuses to resolve to (a
  deliberate security boundary), so this step failed on every run since
  it was introduced. Replaced with a plain `git clone` via `run:`,
  which has no such restriction and reaches the exact same real sibling
  layout `provisioning/verify_install_and_recovery.sh` and
  `preflight_cm5.py` already expect.
- **A real regression from 0.4.2, only now exposed:** `agent.py`'s
  new `from . import __version__` needs a real parent package context
  to resolve against - `provisioning/preflight_cm5.py`'s own
  `import_agent()` loaded it as a standalone file with no package
  identity at all, and `tools/verify_sdk_contracts.py` runs it as a
  bare script (`python agent.py describe`/`health`), which has no
  package context either. Both raised a real `ImportError` - never
  caught before because the checkout bug above meant
  `install_cm5_base.sh` (and therefore `preflight_cm5.py`) was never
  actually exercised by CI until now. Fixed at the root: `agent.py`
  falls back to importing `hydra_umc_os` the ordinary way (its own
  parent directory on `sys.path`) when the relative import has no
  package to resolve against; `preflight_cm5.py`'s `import_agent()`
  now imports the module normally instead of loading it standalone.
- **A real, pre-existing manifest/native-version desync found in the
  same pass:** `hydra-umc.project.json` had already drifted ahead of
  `agent/pyproject.toml`/`agent/src/hydra_umc_os/__init__.py` (0.4.1
  vs. 0.4.0, predating that regression, which then continued the same pattern
  bumping the manifest by hand to 0.4.2 without touching the native
  sources) - exactly the class of gap an earlier review already flagged
  this repo as prone to repeating. Synced before this build's own
  version increment.

## [0.4.2] - health() links a real agent version and boot session id

- **`agent/src/hydra_umc_os/agent.py`** - `HealthReport` used to carry no
  link to which agent build produced it, nor to which running process
  instance. A caller polling `health()`/`serve` over time (HYDRA-UMC-
  UPDATER, a dashboard, ...) had no way to tell "continuously healthy
  since boot" apart from "the process just restarted and happens to
  report READY again" - two different real situations that looked
  identical. Two new fields: `agent_version` (this installed package's
  own `hydra_umc_os.__version__`) and `boot_session_id` (a random id
  generated once when the process starts, stable across every
  `health()` call from the same `serve` loop). Additive only - existing
  fields/shape unchanged. `docs/AGENT_REFERENCE.md`'s own `health`
  example and field list updated to match (also corrects a stale
  description there: `state` reacts to ANY check failing/warning, not
  only storage/temperature/network specifically). 2 new tests.

## [0.4.1] - a real --apply install + a real backup/wipe/restore cycle, not just bash -n

- **`provisioning/verify_install_and_recovery.sh`** - CI (and any real,
  disposable systemd-based Debian/Ubuntu machine) only ever ran `bash -n`
  (syntax-only) against `provisioning/*.sh` - a real `--apply` install and
  a real backup/wipe/restore cycle had never been exercised anywhere
  except by hand, directly on a real CM5. This script runs
  `install_cm5_base.sh --apply` for real, verifies every real bit of
  state it claims to create (the `hydra-umc-agent` user, `/etc/hydra-umc`/
  `/var/lib/hydra-umc`/`/opt/hydra-umc`, the agent's own systemd unit, the
  real hostname change), then runs a real `cm5_recovery.sh` backup,
  wipes the real state, restores it, and verifies the restored content
  AND ownership match exactly (`--numeric-owner` round-tripped for real).
  Wired into CI (`.github/workflows/ci.yml`, real `ubuntu-latest` - a
  genuinely disposable VM per run, safe to actually mutate) with a real
  sibling `HYDRA-UMC-SDK` checkout, the same real dependency
  `preflight_cm5.py`'s own `SDK_OS_CONTRACT` check already requires.
  Manually verified first against a real, disposable WSL Ubuntu 24.04
  instance before being wired into CI.

## [0.4.0] - install_server.sh no longer leaves stale public/dist files behind

- **`provisioning/install_server.sh`** - a plain `cp -a` over an existing
  `$TARGET/dist`/`$TARGET/public` never removed a file the new SOURCE
  build had renamed or dropped. Found live on this repo's own test CM5
  node: after HYDRA-UMC-SERVER pulled in HYDRA-UMC-STUDIO's LumenPnP fix
  (`z_carriage_n1`/`z_carriage_n2` replaced by `z_carriage_left`/`right`
  + `nozzle_left`/`right`), the old, now-unused mesh files stayed served
  from `/opt/hydra-umc/server/public/` indefinitely. Now clears both
  directories before copying, same pattern `install_dashboard_ai.sh`'s
  own `dist` copy already used.

## [0.3.9] - real pre-validation before any rollback mutation

- **`provisioning/rollback.py`'s `restore_all()`**: used to validate one
  manifest entry, mutate it, validate the next, mutate that one, and so
  on - a bad entry (missing backup) discovered partway through left every
  entry processed before it already restored/deleted, a real, ambiguous
  partial rollback with no way for a caller to know how far it got.
  Every entry is now validated in a first pass, before any real file is
  touched, so a single missing/inconsistent backup anywhere in the
  manifest aborts with zero mutations. A real I/O failure that only
  surfaces during the second, mutating pass (disk full, permission
  revoked, a target's own parent occupied by a real file instead of a
  directory - pre-validation cannot rule these out) now raises a new
  `PartialRestoreError` naming exactly which targets were already
  restored, instead of an undiagnosed partial state.
- `tools/verify_rollback.py` gained 2 new real, subprocess-driven checks
  (8 total): a manifest whose last-restored entry has a missing backup
  aborts with the earlier entry's own target left untouched, and a real
  mid-restore I/O failure (a target's parent path replaced by a file)
  reports a diagnostic naming the target that succeeded before it.
  `tools/build_test.py`: all checks passing.

## [0.3.8] - Real per-node data/ directory for install_swarm_sync.sh

- **`provisioning/install_swarm_sync.sh`** - real gap found while wiring
  real per-node CRDT persistence into HYDRA-UMC-SWARM-SYNC (that repo's
  own CHANGELOG): its `serve` mode now writes a real, durable state file
  when `--state-file` is configured, but this script never created a
  writable directory for it - `systemd/hydra-umc-swarm-sync.service`'s
  own `ProtectSystem=strict` would have refused that write on a real
  deployment. Now creates `data/` for the service account, matching
  HYDRA-UMC-DATALAKE/HYDRA-UMC-JOB-DISPATCHER's own already-working
  convention.

## [0.3.7] - Real Go toolchain for install_job_dispatcher.sh, not whatever Debian happens to ship

- **`provisioning/install_job_dispatcher.sh`** - real gap found while
  wiring real SQLite-backed persistence into HYDRA-UMC-JOB-DISPATCHER
  (that repo's own CHANGELOG): its `go.mod` now needs a real Go >= 1.21
  (`modernc.org/sqlite`, the pure-Go driver its new persistence layer
  uses), but Raspberry Pi OS's own base, Debian 12 "bookworm", ships
  `golang-go` 2:1.19~1 (verified against packages.debian.org) - one real
  minor version short. This script's own `apt-get install golang-go`
  would have failed the on-device build the first time it ran against
  real hardware, not a hypothetical. Replaced with a pinned, checksum-
  verified upstream Go 1.27.1 `linux-arm64` tarball from go.dev (real
  sha256 captured from that page's own JSON API) instead of depending on
  whatever Debian happens to package - verified for real (downloaded,
  checksum-matched, extracted, confirmed a genuine `aarch64` ELF `go`
  binary), though not yet run on real ARM hardware in this pass. Also
  now creates the real `data/` directory the service's own updated
  systemd unit needs writable under `ProtectSystem=strict`, matching
  HYDRA-UMC-DATALAKE's own already-working convention exactly - a step
  this script never had before since the service had nothing durable to
  write until now.
- **`bump_version.py`** - its own auto-generated CHANGELOG stub embedded
  a literal calendar date (`date.today().isoformat()`) into this public
  file - every real entry in this CHANGELOG is dated only by its
  position, never a literal date. The exact same bug, found and fixed in
  the same pass across HYDRA-UMC-SDK and 5 more repos
  (HYDRA-UMC-BRIDGE-CNC/LASER/OPENPNP/PRINTER3D/ROS2) that all copied the
  same template.

## [0.3.6] - Polkit-scoped service control for hydra-umc-server, CI shell syntax checks

- **`provisioning/polkit/50-hydra-umc-server-service-control.rules`**
  (new), installed by `install_server.sh` alongside the existing
  reboot/poweroff rule - grants the unprivileged `hydra-umc-server`
  account start/stop/restart via systemd's own polkit-gated D-Bus API,
  scoped to exactly the `hydra-umc-*.service` namespace (never this
  server's own unit, never anything outside this ecosystem's own
  units). Backs HYDRA-UMC-SERVER's own `POST /api/ecosystem/service/
  :unit/:action` (admin-only) - see that repo's own 0.3.7 changelog
  entry for the server-side half of this feature. Verified installed
  and present on the real CM5 (`sudo ls /etc/polkit-1/rules.d/`).
- **`provisioning/install_datalake.sh`** now also installs
  HYDRA-UMC-DATALAKE's own new `hydra-umc-datalake-retention.service`/
  `.timer` (real daily retention-apply schedule). Both units are
  optional, left for the operator to enable after review, same policy
  the main service already follows.

- **`.github/workflows/ci.yml`** - a new `bash -n` (syntax-only) pass over
  every `provisioning/**/*.sh` script: CI already validated Python/Node syntax
  and tests but never checked the ~30 `install_*.sh` scripts that are
  this repo's actual deliverable, so a shell syntax error only ever
  surfaced by running it on a real CM5. CI-only fix, no runtime script
  changed. shellcheck itself (style/quoting, not just syntax) is a real,
  separate follow-up once its own findings across ~30 scripts have been
  triaged.

## [0.3.5] - Dashboard-AI static serving

- **`provisioning/install_dashboard_ai.sh`** (new) - builds and installs
  HYDRA-UMC-DASHBOARD-AI's real static SPA (`npm run build` -> `dist/`,
  built on-device the same way `install_server.sh` builds
  HYDRA-UMC-SERVER) behind that repo's own new
  `scripts/serve_static.py` (stdlib, no Node runtime needed once built).
  Own port (8115)/service - deliberately not folded into
  HYDRA-UMC-SERVER's own `public/` the way HYDRA-UMC-STUDIO is, since
  this dashboard already talks straight to HYDRA-UMC-DATALAKE/
  HYDRA-UMC-ANOMALY-DETECTOR by their own configured base URLs.

## [0.3.4] - Server mode for the 4 Rust services, closing the CLI-only-services list

- **`provisioning/install_twin.sh`** (new) - installs the real family-
  status/family-sync API. First Rust service in this ecosystem to get a
  real HTTP server (`tiny_http`).
- **`provisioning/install_swarm_sync.sh`** (new) - installs the real
  CRDT-reconciliation API (POST /reconcile) - still a request/response
  computation, not the deliberately-deferred live gossip network.
- **`provisioning/install_hil_bridge.sh`** (new) - installs the real
  route/mirror-bridging API - no real gRPC/WebSocket transport exists
  yet, so both routes still only reach the CLI's own honest fakes
  (`RecordingSink`/`SimulatedTransport`).
- **`provisioning/install_orchestrator.sh`** (new) - installs the real
  mission-registry API (dispatch/start/complete/cancel/fail/recover) -
  purely in-memory bookkeeping, no real gRPC wiring to Job-Dispatcher/
  Node-Healing and no real E-STOP-sending code anywhere in that
  repository; this does not grant any new physical authority.
- All 4 compile as release binaries on-device (unlike the Go services,
  which build from source with the same `cargo build --release`
  pattern `install_twin.sh` established first).
- This closes the full "CLI-only, no real server loop
  yet" gap for every repo that had real, wrappable logic already
  written. The 5 hardware bridges (CNC, Laser, OpenPnP, Printer3D, ROS2)
  remain the one category left untouched - real physical actuators, a
  network transport decision that stays deliberately not invented here.

## [0.3.3] - Server mode for 3 more CLI-only repos

- **`provisioning/install_safety_zones.sh`** (new) - installs the real
  zone-breach/E-STOP-request API (POST /check). Never asserts an E-STOP
  itself, only ever requests one, same as the CLI.
- **`provisioning/install_semantic_planner.sh`** (new) - installs the
  real goal-decomposition/recovery API (POST /decompose, POST /recover).
- **`provisioning/install_docs_qa.sh`** (new) - installs the real
  TF-IDF documentation-retrieval API (GET /query), index built once at
  startup rather than per-request like the CLI - a real improvement, not
  just a wrapper. Copies this repo's own README.md/CHANGELOG.md
  alongside `src/` so the default corpus resolves to something real once
  deployed.
- These 3 close the rest of the "CLI-only, no real server
  loop yet" gap for the repos that had real, wrappable business
  logic already written (config.py's own `load_zones`/`load_zone_set`/
  `load_detections` in Safety-Zones needed a real, behavior-preserving
  split into file-reading wrappers + `parse_*` functions first, so the
  new API could take JSON directly in the request body instead of a
  server-side file path). The remaining CLI-only repos
  (the 5 hardware bridges, and the 4 Rust services Orchestrator/
  Swarm-Sync/Twin/HIL-Bridge) are not addressed here - see those repos'
  own state for why.

## [0.3.2] - The 0.3.1 workspace approach was unreadable by its own service accounts

- **`provisioning/install_vision_node.sh`/`install_cognitive_node.sh`/
  `install_vla_engine.sh`** - none of the 3 symlinked `--workspace`
  directories were readable by their own unprivileged systemd service
  accounts. Live-verified on this device: the real sibling-checkout root
  ($ROOT) lives under the operator's own home directory, itself `0700`
  (Debian's own default) - `ProtectHome=read-only` only controls whether
  systemd *hides* `/home` from a unit, not the real underlying Unix
  permission bits, so it never actually fixed anything. All 3 scripts
  now copy out just the small manifest/model files each service actually
  needs into a real `root:root 0755` tree under `/opt` instead - see
  each repo's own CHANGELOG for the exact writeup
  (HYDRA-UMC-VISION-NODE 0.0.6, HYDRA-UMC-COGNITIVE-NODE 0.0.8,
  HYDRA-UMC-VLA-ENGINE 0.1.0).

## [0.3.1] - Server mode for the 5 AI-family repos that were CLI-only

- **`provisioning/install_visual_servoing_api.sh`** (new) - installs the
  real PBVS correction/authorization API (POST /correct, POST /request).
- **`provisioning/install_detection_hef.sh`** (new) - installs the real
  compiled-model registry + safe-load API (GET /registry, /latest,
  /load), config outside the shared `/etc/hydra-umc/` tree (same real
  permission lesson from Node-Healing's own install).
- **`provisioning/install_vision_node.sh`** (new) - installs the real
  family/pipeline-status/frame-validation API (GET /family-status,
  /pipeline-status, POST /validate-frame).
- **`provisioning/install_cognitive_node.sh`** (new) - installs the real
  family-status API (GET /family-status).
- **`provisioning/install_vla_engine.sh`** (new) - installs the real
  action-tokenization/trajectory/status API (POST /tokens/encode,
  /decode, POST /trajectory/integrate, GET /status).
- Vision-Node/Cognitive-Node/VLA-Engine's own `GET /family-status`/
  `/status` need the real sibling-checkout layout to report anything but
  "all missing" - each symlinks its own `workspace` to `$ROOT` (the same
  sibling-checkout root every script in this file already resolves)
  rather than copying those repos a second time. Real bug caught before
  deploying any of the three: that root lives under the operator's home
  directory, so each one's systemd unit sets `ProtectHome=read-only`,
  not this file's usual `true` (which would make `/home/` - and each
  symlink's real target - inaccessible outright, not just unwritable).
- Real gap found checking the ecosystem against actual CM5 hardware: of
  the 8 real "AI"-family repos, only Anomaly-Detector and Vision-Streamer
  already ran as a real HTTP service before this session; these 5 close
  the rest (Dashboard-AI is a Vite/React UI, not a Python CLI needing
  this same treatment - separate, different kind of work).

## [0.3.0] - The 0.2.9 fix was still wrong: Node-Healing can't watch zero nodes

- **`provisioning/install_node_healing.sh`** - live-verified on this
  device: `config.LoadNodes()` itself refuses an empty registry ("is
  empty - nothing to watch"), so 0.2.9's `nodes.json` = `[]` fix
  auto-restart-looped exactly like the permission bug it replaced, just
  with a different error. There is genuinely no real HealthService-
  speaking node anywhere in this ecosystem yet, so this script now
  installs the capability only (binary + unit, matching
  `install_vision_streamer.sh`'s own pattern) and does not create a
  registry or enable/start the service - see the script's own printed
  instructions for what to do once a real node exists. See
  HYDRA-UMC-NODE-HEALING's own CHANGELOG (0.1.1) for the full writeup.

## [0.2.9] - Node-Healing permission bugfix, found live on this device

- **`provisioning/install_node_healing.sh`** - the node registry moves
  from `/etc/hydra-umc/node-healing/nodes.json` to
  `/etc/hydra-umc-node-healing/nodes.json`. Real bug found live on this
  device's first `systemctl enable --now`: `/etc/hydra-umc/` is `0750
  root:hydra-umc-agent`, so `hydra-umc-node-healing`'s own unprivileged
  account could never traverse into it to open its `--nodes` file -
  `permission denied` on every start, auto-restart-looping. See
  HYDRA-UMC-NODE-HEALING's own CHANGELOG (0.1.0) for the full writeup.

## [0.2.8] - Job-Dispatcher, Node-Healing, Telemetry-Collector, Production-Reports install

- **`provisioning/install_job_dispatcher.sh`** (new) - first Go service
  installed on this CM5: provisions `golang-go` if missing and builds
  HYDRA-UMC-JOB-DISPATCHER's real priority mission queue on-device (pure
  Go, no cgo dependency). Loopback-only systemd unit.
- **`provisioning/install_node_healing.sh`** (new) - builds
  HYDRA-UMC-NODE-HEALING's real watchdog loop on-device, starts it
  watching an intentionally empty node registry (its own
  `nodes.example.json` targets 3 HydraNodes with no real HealthService
  server yet - honest starting state, not a registry that would only
  ever report every node unreachable).
- **`provisioning/install_telemetry_collector.sh`** (new) - builds
  HYDRA-UMC-TELEMETRY-COLLECTOR's real CAN/WebSocket ingestion pipeline
  on-device, wired to feed HYDRA-UMC-DATALAKE via `-datalake-url`.
- **`provisioning/install_production_reports.sh`** (new) - installs
  HYDRA-UMC-PRODUCTION-REPORTS' real stdlib-only OEE/availability
  reporting API (copy `src/` + `PYTHONPATH`, same shape as
  `install_datalake.sh`), pinned loopback-only.
- Real gap found checking the ecosystem against actual CM5 hardware: all
  4 already had real, tested server/daemon code and had simply never
  been built or installed anywhere. The remaining "service"/"api"-role
  repos reviewed alongside these (the 5 hardware bridges, Safety-Zones,
  Semantic-Planner, Docs-QA, and the Orchestrator/Swarm-Sync/Twin/
  HIL-Bridge Rust services) do NOT yet have a real running server/daemon
  loop of their own - installing a systemd unit for those would be
  packaging code that doesn't run persistently yet, not closing a real
  gap. That's separate, real feature work, not addressed here.

## [0.2.7] - Vision-Streamer installs (real USB camera -> robot A1 pipeline)

- **`provisioning/install_vision_streamer.sh`** (new) - installs
  HYDRA-UMC-VISION-STREAMER's real OpenCV-backed MJPEG capture+serve
  (`python3-opencv`/`v4l-utils` from Debian's own repos, no venv/pip
  needed) as a templated systemd unit, one instance per admin-assigned
  camera slot (`hydra-umc-vision-streamer@N`, matching the `cameraId`
  HYDRA-UMC-STUDIO's admin panel already assigns). Closes the last real
  gap in the camera -> robot A1 pipeline reviewed:
  HYDRA-UMC-SERVER's own `GET /api/camera/:id/stream` proxy and
  HYDRA-UMC-STUDIO's `CameraPIP`/`CamerasView` were already real, but
  nothing on the CM5 actually opened a physical `/dev/videoN` yet. This
  installs the capability only - enabling a specific slot for a specific
  physically-connected camera is a deliberate manual follow-up (see that
  unit's own `cameras.env.example` for why an automatic guess isn't
  attempted). Live-verified on this device: `GET /api/camera/1/stream`
  correctly returns 503 with no slot enabled yet (no camera streamer
  running); real hardware verification (a physically-connected USB
  camera) is still pending.

## [0.2.6] - Anomaly-Detector installs

- **`provisioning/install_anomaly_detector.sh`** (new) - installs
  HYDRA-UMC-ANOMALY-DETECTOR's real FFT + z-score anomaly-detection API
  (python3-numpy from Debian's own repos, no venv/pip needed) as a
  loopback-bound systemd service. Real gap found checking the ecosystem against actual CM5 hardware: the only one of the 8 real "AI" repos
  that already runs as a real HTTP service (the other 7 are CLIs only)
  had never been installed anywhere. Live-verified: `GET /stats`
  responds.

## [0.2.5] - Datalake installs; bootstrap admin password removed from disk

- **`provisioning/install_datalake.sh`** (new) - installs
  HYDRA-UMC-DATALAKE's real stdlib-only, sqlite3-backed time-series API
  as a loopback-bound systemd service (`data/` is the one
  `ReadWritePaths` exception under `ProtectSystem=strict`). Real gap
  found checking the ecosystem against actual CM5 hardware: genuinely
  working, tested HTTP API that nothing ever installed anywhere.
  Live-verified: `GET /stats` responds, and Server's own
  `GET /api/telemetry/query` proxy reaches it successfully end to end
  once `HYDRA_UMC_DATALAKE_URL` is uncommented in `server.env`.

- **`HYDRA_UMC_BOOTSTRAP_ADMIN_PASSWORD` stayed in `server.env` in
  plaintext past first start** on this device, found while wiring up the
  Datalake proxy above - the real admin account was already persisted
  (hashed) to Server's own `data/users.json`, exactly as
  `server.env.example`'s own comment always said this variable should be
  removed after ("SET_LOCALLY_AND_REMOVE_AFTER_FIRST_START") - it just
  never had been. Removed from this device's own `server.env`; not a
  code change, a real operational gap closed on the live node.

## [0.2.4] - Real gap closed: the Industry 4.0 Gateway now installs

- **`provisioning/install_industrial_gateway.sh`** (new) - installs Docker
  and brings up HYDRA-UMC-GATEWAY-INDUSTRIAL's own real
  `docker-compose.yml` (all 3 real protocol bridges - OPC-UA, MQTT,
  MTConnect - plus the Gateway's own aggregation surface). Real gap found checking the ecosystem against actual CM5 hardware: genuinely working,
  tested code that nothing ever installed anywhere. Live-verified on this
  CM5: all 4 containers build and stay up, `GET /status` reports
  `allReachable:true` for all 3 children with real measured latencies.

- **2 real Debian package-naming surprises**, found live installing this
  for the first time: Compose v2's package is `docker-compose`, not
  `docker-compose-v2`; `docker.io` installs `dockerd`/`docker-proxy`/
  `docker-init` only - the actual `docker` CLI client is the separate
  `docker-cli` package (`docker-buildx` also added, the modern build
  backend `compose ... --build` wants). Also found and fixed, in each of
  the 4 real child repos: their own `Dockerfile`s never installed
  dependencies in the runtime stage (`MODULE_NOT_FOUND` on every real
  run) - see each repo's own CHANGELOG.

## [0.2.3] - Documented Datalake/spi_bridge proxy env vars

- **`provisioning/server.env.example`** now documents (commented out)
  `HYDRA_UMC_DATALAKE_URL`/`HYDRA_UMC_DATALAKE_TIMEOUT_MS` and
  `HYDRA_UMC_SPI_BRIDGE_URL`/`HYDRA_UMC_SPI_BRIDGE_TIMEOUT_MS` - real gap
  found checking the ecosystem against actual CM5 hardware: `server.ts`
  already reads both (STUDIO's Ecosystem > Telemetry panel and the
  Flasher/Tester's real CANOTA hardware path), but neither ever appeared
  in the example file operators actually provision `server.env` from.
  Left unset by default (Server already answers 503 "not configured"
  rather than guessing a process is there) until HYDRA-UMC-DATALAKE and
  `spi_bridge` are actually installed and running.

## [0.2.2] - The kiosk now shows a mouse cursor with a real mouse attached

- **A physical USB mouse plugged into the CM5's IO board showed no
  pointer at all**, reported live: `-nocursor` on the kiosk's own Xorg
  invocation unconditionally disabled cursor rendering, a reasonable
  default when no pointing device was expected but wrong now that one is
  attached. Removed; `unclutter` (already running) still auto-hides it
  after a second of inactivity, so a touch-only session looks the same as
  before while a real mouse now shows and works.

## [0.2.1] - Fixed the polkit rule install path from [0.2.0]

- **`install_server.sh` couldn't install its own new polkit rule**, found
  running `--apply` live right after `[0.2.0]`: `$ROOT` in this script is
  deliberately the PARENT of this repo (so `SOURCE` can reach the sibling
  `HYDRA-UMC-SERVER` checkout next to it), not this repo's own root - the
  polkit install line used `$ROOT` directly and looked for the rule file
  one directory too high. Added `OS_ROOT` (one level down from `$ROOT`,
  this repo's own real root) and pointed the polkit install line at that
  instead.

## [0.2.0] - Kiosk power buttons: polkit grant for shutdown/restart

- **`provisioning/polkit/49-hydra-umc-server-power.rules`** (new),
  installed by `install_server.sh` - grants the unprivileged
  `hydra-umc-server` service account (`NoNewPrivileges`) exactly 2
  `systemd-logind` actions (`org.freedesktop.login1.reboot` and
  `...power-off`, plus their `-multiple-sessions` variants), nothing
  broader. Backs HYDRA-UMC-SERVER's new loopback-only `POST
  /api/system/{reboot,shutdown}` (see that repo's own changelog), which
  in turn back the shutdown/restart buttons STUDIO's `AuthGate.tsx` now
  shows on its pre-login screen - a real power button for an operator
  standing at this device's own HDMI kiosk (`install_kiosk.sh`), usable
  before logging in, the same as a real one would.

## [0.1.9] - verify_cm5_runtime.sh's Server checks, exercised live for the first time

- **`--with-server` never passed, on the first CM5 this was ever run
  against with Server actually installed**, in 2 real, independent ways:
  (1) `install_server.sh` only ever `chmod`'d `server.env`, never
  `chgrp`'d it - an operator following `CM5_DEPLOYMENT_SEQUENCE.md`'s own
  documented flow (create it as `root:root`) ends with
  `root:root:640`, but the verifier checks for `root:hydra-umc-server:640`
  specifically; this script had no way to pass as originally written.
  Now `chown root:$SERVER_USER`s it once that group is guaranteed to
  exist. (2) the verifier's own `/api/hydra-info` check asserted
  `product == "server"` - HYDRA-UMC-SERVER's own real contract
  (`src/server.ts`) documents and returns `product` as a human-readable,
  operator-customisable server name (defaulting to `"HYDRA-UMC STUDIO"`),
  never the literal string `"server"`. Now checks for a non-empty string,
  matching what the real endpoint actually guarantees. Voice UI's own
  equivalent check was verified correct against `HYDRA-UMC-VOICE-UI`'s
  real source - `"HYDRA-UMC-VOICE-UI"` genuinely is a fixed constant
  there, unlike Server's operator-customisable name.

## [0.1.8] - Kiosk boot is finally quiet: the real, complete story

- **The kiosk boot still showed text**, across many further rounds of
  live testing on the physical HDMI display after `[0.1.7]`, each one a
  genuinely different, unrelated source once actually read/photographed
  rather than guessed at from a fast description:
  - This device's real serial console (`console=serial0,115200`, kept
    intentionally for hardware debugging) makes Plymouth fall back to
    its own text-only "details" plugin by design, regardless of quiet/
    splash/the theme itself. `plymouth.ignore-serial-consoles` is
    Plymouth's own documented opt-out; it now shows this theme's real
    static frame instead.
  - `loglevel=3` still let real driver-probe warnings on this device
    (dwc2/brcm-pcie regulator notices) through - lowered to `loglevel=0`.
  - `console=tty1` routed kernel/systemd console output to the visible
    VT; changed to `console=tty3` - a real, working text console still
    exists (switchable from a physical keyboard), it is simply not the
    one shown by default. `systemd.show_status=0` and `fbcon=map:10`
    added as further defense in depth.
  - Xorg's own startup banner writes directly to the VT device, not
    through inherited stdout/stderr - `-verbose 0 -logverbose 0` passed
    to X is the documented way to quiet it.
  - The very last remaining line turned out to be `update-motd.d`'s
    `10-uname` script (`Linux hostname kernel-version arch`), printed by
    every login on this account regardless of agetty/Xorg/Plymouth - a
    plain `~/.hushlogin` is the standard, one-line fix.
  - **A genuine dead end, tried and reverted**: keeping Plymouth's splash
    up for the device's entire boot (masking `plymouth-quit*.service`,
    quitting it manually right before Chromium) to cover every source at
    once - live-tested, and it deadlocked agetty's own tty1 autologin
    outright instead (stuck as bare `(agetty)`, never reaching login).
    Not used; Plymouth quits on its own normal ~4s schedule.
  - `picom` (added in `[0.1.7]` for the real Present-extension freeze)
    stays - unrelated to any of the above, still needed.

## [0.1.7] - The real fix for the kiosk freeze: a compositor

- **`[0.1.6]`'s `Option "Present" "false"` did not actually fix the kiosk
  freeze** - live-verified: Xorg.0.log kept showing the exact same
  "Present-flip: queue flip during flip on CRTC 2 failed: Invalid
  argument" errors after applying it and rebooting. Root cause: that
  option name does not exist for `xf86-video-modesetting` at all - it did
  nothing except let X's own internal "too frequent flip errors" rate
  limiter make the *log* quieter. A second attempt, the real, documented
  `Option "PageFlip" "false"`, also did not fix it live - that option
  controls the driver's own internal double-buffering, a different layer
  from the Present *extension* requests Chromium's GPU process sends as
  an X client, so this specific race was untouched either way.
- **What actually fixed it, live-verified** (0 Present-flip errors in
  Xorg.0.log after, versus ~2900 before, across an otherwise-identical
  reboot): giving X a real compositing manager. `install_kiosk.sh` now
  installs `picom`; `kiosk-session.sh` starts it (`--backend xrender`,
  the simpler/more compatible backend - this kiosk only ever shows one
  fullscreen window) right after Plymouth hands off and before Chromium,
  so Present requests have something to arbitrate through instead of
  racing the CRTC directly. The now-inert `PageFlip` option was removed
  from the xorg.conf.d device section; `kmsdev` (still needed, see
  `[0.1.3]`) stays.

## [0.1.6] - Kiosk display no longer freezes (X Present-extension race)

- **The kiosk display froze after `[0.1.5]`** - reported and confirmed
  live: every kiosk process stayed alive (Xorg, Chromium, openbox all
  still running, Server and the agent both healthy) but the screen
  stopped updating. `Xorg.0.log` showed the real cause: thousands of
  repeated `Present-flip: queue flip during flip on CRTC 2 failed:
  Invalid argument` lines - Chromium's own GPU process racing X's
  Present extension for direct-scanout page-flips with nothing to
  arbitrate between them (openbox runs no compositing manager), so no
  new frame ever actually reached the screen. `install_kiosk.sh` now
  also sets `Option "Present" "false"` in the same `modesetting` device
  section - the standard, documented mitigation for this exact
  driver/Present race.

## [0.1.5] - Splash now covers the whole boot, not just its first ~4s

- **Boot-log lines were still visible after `[0.1.4]`'s `quiet splash`
  fix** - reported live watching this device boot again. Root cause found
  in `journalctl`: systemd's own `plymouth-quit.service` fired only ~4s
  into boot, long before slower units (`network-online.target`,
  `hydra-umc-server`, `hydra-umc-agent`) finish - their own "Started ..."
  lines kept printing to the now-uncovered text console for several more
  seconds, before the tty1 autologin chain even got a chance to start X.
  `install_kiosk.sh` now masks `plymouth-quit.service` and
  `plymouth-quit-wait.service`; `kiosk-session.sh` quits Plymouth itself,
  right before Chromium starts, once X already has the display. The
  splash now covers this device's entire real boot, not just its first
  few seconds.

## [0.1.4] - Quiet kiosk boot, and no more duplicate splash

- **The kernel/systemd boot log was visible on the HDMI display**, reported
  live watching this device boot: `cmdline.txt` shipped with no `quiet`/
  `splash` kernel parameter, so every boot-time log line printed straight
  to tty1 instead of Plymouth's graphical frame ever getting a chance to
  show. `install_kiosk.sh` now appends `quiet splash logo.nologo
  loglevel=3 vt.global_cursor_default=0` to `cmdline.txt` (idempotent -
  only tokens not already present are added, so it never fights an
  operator's own customised cmdline).
- **The splash showed twice** - `HYDRA_UMC_SPLASHSCREEN.svg` once, real
  and animated, from the kiosk's own `splash.html`, then STUDIO's own
  `App.tsx` showed the same artwork again (static, 10s) once the kiosk
  handed off to it. STUDIO's existing `hideUI=true` already skipped its
  splash, but also hides all navigation - wrong for this general-purpose
  dashboard kiosk. STUDIO's own `App.tsx` (see that repo's `4bef0bb`) now
  has an independent `skipSplash=true` for exactly this; the kiosk hand-off
  URL uses it.

## [0.1.3] - Real HDMI kiosk: animated splash, then STUDIO fullscreen

- **`provisioning/install_kiosk.sh`** (new) - a minimal X11 + Chromium
  kiosk session for the CM5's HDMI output. Plymouth (`install_splashscreen.sh`)
  can only render a static raster frame or its own tiny scripting language,
  never `HYDRA_UMC_SPLASHSCREEN.svg`'s real `<animate>`/`<animateTransform>`
  elements and `@keyframes` - so this instead boots a real browser that
  shows the actual, unmodified SVG file first
  (`provisioning/kiosk/splash.html`) and hands off to
  HYDRA-UMC-SERVER's own STUDIO UI fullscreen once Server actually answers
  `/api/hydra-info`, not on a fixed timer alone. Same dry-run/`--apply`
  convention as every other provisioning script.

- **Two real, live-hardware kiosk boot failures**, found and fixed on the
  first CM5 this was ever run against: (1) `xserver-xorg`'s bundled
  `xserver-xorg-video-all` pulls in the legacy `fbdev` driver alongside the
  real KMS `modesetting` driver, and X's own auto-probe died with "Cannot
  run in framebuffer mode" instead of just using the KMS driver it had
  already found; (2) even with `modesetting` pinned alone, X still failed
  with "No devices detected"/"no screens found" despite a real monitor
  confirmed connected at the kernel level - this CM5's `vc4-kms-v3d`
  overlay exposes 2 DRM nodes (`card0`, v3d, compute-only; `card1`, vc4,
  the real display controller), and `modesetting`'s own autodetection did
  not reliably resolve to `card1` on its own. Both fixed with an explicit
  `/etc/X11/xorg.conf.d/20-hydra-umc-modesetting.conf` pinning
  `Driver "modesetting"` and `Option "kmsdev" "/dev/dri/card1"`.

## [0.1.2] - install_cm5_base.sh no longer depends on git's executable bit

- **`provisioning/install_cm5_base.sh` invoked `first_boot.sh`,
  `install_local_agent.sh`, `install_wifi_provision.sh`,
  `install_server.sh` and `install_voice_ui.sh` by direct execution**
  (`provisioning/X.sh --apply`), relying on their git executable bit.
  Found live on the first real CM5 this was ever run against from a
  fresh `git clone`: every one of these scripts was tracked as mode
  `100644` (no `+x`) in this repository, so the very first `--apply` run
  failed immediately with "Permission denied" right after preflight had
  just passed. Every sub-script call is now prefixed with `bash`,
  matching how `CM5_DEPLOYMENT_SEQUENCE.md` itself already invokes these
  scripts - independent of git's executable-bit handling across
  different clone/checkout paths. The executable bit itself is also now
  set correctly in git for every `provisioning/*.sh` script and the
  top-level `build.sh`/`run.sh`, as defense in depth for direct
  invocation.

## [0.1.1] - Removed a real duplicate/drift risk between the two deployment docs

- **`docs/CM5_PROVISIONING.md`** - its own 13-step "Deployment sequence"
  duplicated `provisioning/CM5_DEPLOYMENT_SEQUENCE.md`'s own real,
  gated procedure at a different granularity - a real, found drift risk:
  the two lists no longer even had matching step counts after
  `CM5_DEPLOYMENT_SEQUENCE.md`'s own recent rewrite into gates. Collapsed
  to a single pointer at the one real source of truth, keeping this
  document focused on what's genuinely unique to it (identity table, SSH
  policy detail, boot identity/splash, rollback/recovery summary).
- **`README.md`** - fixed a stale `CM5_DEPLOYMENT_SEQUENCE.md` "step 9"
  reference (the AP password step moved to section 3 in that document's
  own gate-based rewrite) to point at the real, current location.

## [0.1.0] - Real, verified CM5-from-Windows flashing procedure

- **`docs/CM5_WINDOWS_HOST_FLASHING.md`** (new) - the real, verified
  procedure for getting a bare CM5 + official IO Board onto Raspberry Pi
  OS Lite ARM64 from a Windows host, captured from an actual real-hardware
  session rather than written speculatively. Covers the two real failure
  modes in order: a missing Windows driver on the "BCM2712D0 Boot"
  boot-ROM stage (fixed with Zadig + WinUSB), and - when that alone isn't
  enough, a real, reported case for CM5 specifically - a WSL2 +
  usbipd-win + a real compiled `raspberrypi/usbboot` `rpiboot` fallback
  (including the two real usbipd gotchas hit while building this:
  `usbipd`'s own PATH not refreshing in an already-open shell, and the
  CM5's own mid-boot USB re-enumeration needing `--auto-attach`, not a
  plain one-shot `attach`, to survive). Documents the real `custom.toml`
  schema for anyone scripting this from a host without Windows' own UAC
  elevation problem, and the real one-line generate-and-hash pattern that
  sets a console password without its plaintext ever being displayed or
  logged, honoring `CM5_PROVISIONING.md`'s own "never write it into a
  repository, shell script, log or support ticket" policy for real.
- Cross-referenced from `provisioning/CM5_DEPLOYMENT_SEQUENCE.md`'s own
  step 1.

## [0.0.9] - Real WiFi first-contact provisioning (AP mode + client join)

- **`provisioning/wifi_provision.py`** (new) - the real gap
  `CM5_DEPLOYMENT_SEQUENCE.md`'s own "Configure local Wi-Fi using the
  Raspberry Pi supported first-boot method" was an honest pointer at, not
  a design this repo owned any part of. Real NetworkManager (`nmcli`)
  AP-mode fallback: when the interface has no active WiFi connection,
  brings up a real hotspot (`nmcli device wifi hotspot`) an operator's
  phone/laptop can join directly, and serves a small real HTTP form
  (stdlib `http.server`, same handler-factory shape as
  `HYDRA-UMC/src/cm5_host/spi_bridge/spi_bridge/http_service.py`) for the
  real target SSID/password. A submitted attempt tears the AP down (a
  single radio can't be an AP and a client at once), tries the real
  join, and restores the AP only on failure so the operator isn't
  stranded. Every `nmcli` call lives behind one real, injectable
  `NetworkManagerRunner` Protocol.
- **`systemd/hydra-umc-wifi-provision.service`** (new) - runs
  `wifi_provision.py --apply` once at boot as `Type=oneshot`; a real
  no-op when already connected. Runs as root (real network
  reconfiguration needs it, unlike `hydra-umc-agent.service`'s own
  deliberately read-only, unprivileged scope).
- **`provisioning/install_wifi_provision.sh`** (new) - installs both to
  `/opt/hydra-umc/wifi-provision/`, same real install-root convention as
  `install_local_agent.sh`'s own `/opt/hydra-umc/os-agent`. Wired into
  `install_cm5_base.sh`'s own base flow. Deliberately does not enable the
  service - it must not start with the module's own placeholder AP
  password on a real, over-the-air-reachable device; the real per-device
  password step is documented in `CM5_DEPLOYMENT_SEQUENCE.md` step 9.
- **`tools/verify_wifi_provision.py`** (new) - the real state machine
  (`ensure_hotspot_if_disconnected`/`attempt_join`) verified against an
  in-memory `FakeNetworkManager` implementing the real
  `NetworkManagerRunner` Protocol, plus a real end-to-end HTTP round-trip
  against `serve_until_joined()` over a real loopback socket (only
  `nmcli` itself is faked) - 24 checks, no real WiFi radio, root, or
  NetworkManager install required. Wired into `tools/build_test.py`.
- Found and fixed while building this: a failed join attempt used to
  restore the AP with the module's own `DEFAULT_AP_PASSWORD` placeholder
  instead of whatever `--ap-password`/`HYDRA_UMC_AP_PASSWORD` this run
  was actually configured with - a real deployment that set a custom
  password would have silently fallen back to the shared, publicly-known
  default the moment any join attempt failed. Fixed before this ever
  shipped; covered by two new checks in `verify_wifi_provision.py`.

## [0.0.8] - Fixed the real port collision with HYDRA-UMC-JOB-DISPATCHER

- **Voice gateway loopback endpoint moved 8090 -> 8091**, matching the
  real fix landing in HYDRA-UMC-VOICE-UI's own repo (that port was
  identical to HYDRA-UMC-JOB-DISPATCHER's own default - flagged there,
  not fixed, until now). Updated every real reference in this repo:
  `tools/verify_voice_gateway_deployment_contract.py`'s own expected
  endpoint and systemd `ExecStart` check,
  `provisioning/server.env.example`'s `HYDRA_UMC_VOICE_UI_URL`,
  `provisioning/verify_cm5_runtime.sh`'s health probe, and
  `docs/CM5_ECOSYSTEM_DEPLOYMENT.md`/`docs/CM5_PACKAGE_MANIFEST.md`.
  `VOICE_GATEWAY_DEPLOYMENT_CONTRACT=PASS`, full `build-test.bat` suite
  passing (13 agent tests + every deployment-contract check).

## [0.0.7] - Documented the real anti-rollback update contract

- **`docs/UPDATE_MODEL.md`** - added the missing standard GPL header (this
  file had none), and documented the real anti-rollback precondition a
  future CM5 deployment flow must honor before changing a checkout: the
  candidate manifest must validate, identify the same project, and not
  declare a lower version than the installed manifest - the same real
  contract `HYDRA-UMC-UPDATER`'s own `clone_or_pull()` now enforces (see
  that repo's own changelog). Honestly notes this is a deployment
  contract, not a claim that rollback has been exercised on a real CM5
  yet. Documentation-only - no code changed.

## [0.0.6] - Fixed after an ecosystem-wide bug sweep

- **Real version-mirror drift, `agent/pyproject.toml` and
  `agent/src/hydra_umc_os/__init__.py`** - this repo's own manifest
  declares `native_version.file` as `CHANGELOG.md` itself (not the
  agent's own package files), so the ecosystem-wide
  `bump_manifest_version.py` bumping the manifest+changelog here never
  touches the real agent package's own version strings - only this
  repo's own separate `bump_version.py` (which requires the manifest and
  agent package to already match before it can run) does. That left the
  real installed agent one build behind what the manifest/changelog
  claimed. Manually caught both files up to 0.0.6 to match - a real
  reconciliation, not a version bump. 13/13 agent tests still passing.

- **`provisioning/inventory_cm5_projects.py`** - fixed a broken import that
  made this script fail outright: it imported a static `PROJECTS` list
  from `hydra_umc_updater.registry` that no longer exists (project
  discovery moved to reading each repository's own
  `hydra-umc.project.json`, and the static catalog was removed). Now uses
  the same `discover_workspace()` manifest-based discovery every other
  ecosystem tool uses; verified by actually running it against this
  workspace.
- **`agent/src/hydra_umc_os/agent.py`** (`health()`) - an unreadable
  temperature sensor (`read_temperature_celsius()` returning `None` - no
  `thermal_zone0`, a permission error, garbage contents) set the
  `temperature` check itself to `WARN`, but the overall device state only
  ever folded *network*'s `WARN` into `DEGRADED` - so a node that can't
  read its own temperature was reported as overall `READY`. Any `WARN`
  check now degrades the overall state. Covered by a new test
  (`test_degraded_when_the_temperature_sensor_is_unreadable`); the
  pre-existing `test_ready_when_storage_and_network_are_available` test
  now passes an explicit in-range temperature instead of implicitly
  depending on whether the test machine happens to expose a real thermal
  sensor.

## [0.0.5] - Idempotent preflight verification, real system-file rollback

- **A real, host-independent system-file backup/rollback mechanism** (`provisioning/rollback.py`, new) - `backup`/`restore` CLI subcommands record a real, append-only manifest before an installer overwrites a real system file, and can restore it (or delete it, if the installer created it fresh) afterward. Wired into `install_local_agent.sh`'s systemd unit install step, the one file this installer unconditionally overwrites on every run.
- **`tools/verify_rollback.py`** (new) - proves the backup/restore mechanism correct against synthetic files in a temp directory (no root, no CM5 needed): a pre-existing file's real content is restored exactly, a freshly-created file is removed on restore rather than left behind, restoring twice in a row is a real no-op (not an error), and restoring against a missing manifest fails honestly instead of silently doing nothing.
- **`tools/verify_preflight_idempotent.py`** (new) - runs `provisioning/preflight_cm5.py` twice in a row and proves byte-identical output plus zero real files touched under this repository, turning the preflight's own "read-only" claim into a checked, reproducible property instead of only a docstring.
- Both new checks are wired into `tools/build_test.py`'s real test run alongside the existing agent unit tests and deployment-contract verifications.

- Automated build version increment from 0.0.3.

## [0.0.4] - Reworked CM5 deployment sequence, per-service accounts, real preflight gate

- Reworked the CM5 deployment sequence and first-boot checklist into explicit
  physical and software gates: carrier/power validation, key-based SSH,
  read-only preflight, reviewed dry run, BASE verification/reboot/recovery,
  loopback Server and one-at-a-time hardware enablement. The procedure now
  states the `HYDRA-UMC-TEST` / `hydra-umc-test` / `hydra-umc` identity,
  secret-handling boundary and what host/WSL tests cannot prove.

- Optional loopback-only HYDRA-UMC-VOICE-UI provisioning, environment
  templates and runtime health verification. This recognised-text gateway is
  separate from the future Hailo STT/TTS stack and cannot actuate hardware.

- Removed a duplicate standard-library import from the diagnostics agent.
- Made the local Server installer reject an absent or unsupported Node.js/npm
  runtime instead of failing later during dependency installation.

- Aligned CM5 first-boot provisioning with the selected `hydra-umc`
  administrator identity. The agent now uses a separate non-login
  `hydra-umc-agent` account, while `/etc/hydra-umc` remains root-owned and
  restricted instead of writable by the service account.
- Reject profile files with empty, non-string or duplicate service and
  capability entries before they can be used to select a deployment profile.
- Reject zero, negative and non-finite `serve` intervals before the agent can
  enter a busy loop or fail later inside its periodic sleep.
- Provision HYDRA-UMC-SERVER under its own non-login account instead of the
  obsolete administrator identity, with root-owned application code and a
  service-owned data directory.
- Corrected the agent systemd command to use the path installed by
  `install_local_agent.sh`, and made the installed agent code root-owned so a
  compromised diagnostics process cannot replace it before a restart.
- Report a `FAULT` when a readable CM5 thermal zone reaches the configured
  maximum temperature (default `80.0`), instead of incorrectly reporting it
  as healthy. Configuration now rejects unsafe storage or temperature limits.

- Added `provisioning/preflight_cm5.py`, a read-only BASE/CONTROL gate that
  validates identity, configuration, profile, deployment contracts and the
  live OS-to-SDK schema contract before a CM5 is modified.
- Added staged `install_cm5_base.sh`, read-only installed-runtime verification,
  scoped backup/restore and negative preflight checks for invalid configuration,
  identity, SDK and Server plans.

- Host-side agent unit and deployment-contract checks, run by `build-test`
  and CI, to keep first boot, installer and systemd identity/path/permissions
  aligned.

- `docs/AGENT_REFERENCE.md` - full CLI/JSON reference for
  `hydra-umc-agent` (`describe`/`health`/`serve`), documenting every real
  output field and how `state`/`checks.*` are derived, plus the
  `--config` file's exact schema. Verified live against the running
  agent. Linked from `docs/SERVICE_MODEL.md`. Documentation-only - no
  code changed, no version bump.

## [0.0.3]

- Automated build version increment from 0.0.2.

## [0.0.2]

- Read-only Python device agent with `describe`, `health`, and periodic
  `serve` commands.
- Validated non-secret configuration example and deterministic health states.
- Hardened `systemd` service unit and Debian package metadata.
- Five host-side unit tests covering configuration and READY/DEGRADED/FAULT
  health transitions.

- No production image is built or distributed by this repository yet.
- This release does not command the MCU, CAN, URTC, motion, or updates.

## [0.0.1]

- Initial public project documentation and multilingual README files.
- CM5/Raspberry Pi OS architecture, service, installation, and update design.
- Explicit boundaries between HYDRA-UMC-OS, SDK, official OS components, MCU,
  and URTC.
