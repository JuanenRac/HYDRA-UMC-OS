# Changelog

## [0.3.3] - Server mode for 3 more CLI-only repos found in the item-3 audit

### Added

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
- These 3 close the rest of the item-3 audit's "CLI-only, no real server
  loop yet" finding for the repos that had real, wrappable business
  logic already written (config.py's own `load_zones`/`load_zone_set`/
  `load_detections` in Safety-Zones needed a real, behavior-preserving
  split into file-reading wrappers + `parse_*` functions first, so the
  new API could take JSON directly in the request body instead of a
  server-side file path). The remaining CLI-only repos from that same
  audit (the 5 hardware bridges, and the 4 Rust services Orchestrator/
  Swarm-Sync/Twin/HIL-Bridge) are not addressed here - see those repos'
  own state for why.

## [0.3.2] - The 0.3.1 workspace approach was unreadable by its own service accounts

### Fixed

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

### Added

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
- Real gap found auditing the ecosystem against actual CM5 hardware: of
  the 8 real "AI"-family repos, only Anomaly-Detector and Vision-Streamer
  already ran as a real HTTP service before this session; these 5 close
  the rest (Dashboard-AI is a Vite/React UI, not a Python CLI needing
  this same treatment - separate, different kind of work).

## [0.3.0] - The 0.2.9 fix was still wrong: Node-Healing can't watch zero nodes

### Fixed

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

### Fixed

- **`provisioning/install_node_healing.sh`** - the node registry moves
  from `/etc/hydra-umc/node-healing/nodes.json` to
  `/etc/hydra-umc-node-healing/nodes.json`. Real bug found live on this
  device's first `systemctl enable --now`: `/etc/hydra-umc/` is `0750
  root:hydra-umc-agent`, so `hydra-umc-node-healing`'s own unprivileged
  account could never traverse into it to open its `--nodes` file -
  `permission denied` on every start, auto-restart-looping. See
  HYDRA-UMC-NODE-HEALING's own CHANGELOG (0.1.0) for the full writeup.

## [0.2.8] - Job-Dispatcher, Node-Healing, Telemetry-Collector, Production-Reports install

### Added

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
- Real gap found auditing the ecosystem against actual CM5 hardware: all
  4 already had real, tested server/daemon code and had simply never
  been built or installed anywhere. The remaining "service"/"api"-role
  repos audited alongside these (the 5 hardware bridges, Safety-Zones,
  Semantic-Planner, Docs-QA, and the Orchestrator/Swarm-Sync/Twin/
  HIL-Bridge Rust services) do NOT yet have a real running server/daemon
  loop of their own - installing a systemd unit for those would be
  packaging code that doesn't run persistently yet, not closing a real
  gap. That's separate, real feature work, not addressed here.

## [0.2.7] - Vision-Streamer installs (real USB camera -> robot A1 pipeline)

### Added

- **`provisioning/install_vision_streamer.sh`** (new) - installs
  HYDRA-UMC-VISION-STREAMER's real OpenCV-backed MJPEG capture+serve
  (`python3-opencv`/`v4l-utils` from Debian's own repos, no venv/pip
  needed) as a templated systemd unit, one instance per admin-assigned
  camera slot (`hydra-umc-vision-streamer@N`, matching the `cameraId`
  HYDRA-UMC-STUDIO's admin panel already assigns). Closes the last real
  gap in the camera -> robot A1 pipeline audited this session:
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

### Added

- **`provisioning/install_anomaly_detector.sh`** (new) - installs
  HYDRA-UMC-ANOMALY-DETECTOR's real FFT + z-score anomaly-detection API
  (python3-numpy from Debian's own repos, no venv/pip needed) as a
  loopback-bound systemd service. Real gap found auditing the ecosystem
  against actual CM5 hardware: the only one of the 8 real "AI" repos
  that already runs as a real HTTP service (the other 7 are CLIs only)
  had never been installed anywhere. Live-verified: `GET /stats`
  responds.

## [0.2.5] - Datalake installs; bootstrap admin password removed from disk

### Added

- **`provisioning/install_datalake.sh`** (new) - installs
  HYDRA-UMC-DATALAKE's real stdlib-only, sqlite3-backed time-series API
  as a loopback-bound systemd service (`data/` is the one
  `ReadWritePaths` exception under `ProtectSystem=strict`). Real gap
  found auditing the ecosystem against actual CM5 hardware: genuinely
  working, tested HTTP API that nothing ever installed anywhere.
  Live-verified: `GET /stats` responds, and Server's own
  `GET /api/telemetry/query` proxy reaches it successfully end to end
  once `HYDRA_UMC_DATALAKE_URL` is uncommented in `server.env`.

### Fixed

- **`HYDRA_UMC_BOOTSTRAP_ADMIN_PASSWORD` stayed in `server.env` in
  plaintext past first start** on this device, found while wiring up the
  Datalake proxy above - the real admin account was already persisted
  (hashed) to Server's own `data/users.json`, exactly as
  `server.env.example`'s own comment always said this variable should be
  removed after ("SET_LOCALLY_AND_REMOVE_AFTER_FIRST_START") - it just
  never had been. Removed from this device's own `server.env`; not a
  code change, a real operational gap closed on the live node.

## [0.2.4] - Real gap closed: the Industry 4.0 Gateway now installs

### Added

- **`provisioning/install_industrial_gateway.sh`** (new) - installs Docker
  and brings up HYDRA-UMC-GATEWAY-INDUSTRIAL's own real
  `docker-compose.yml` (all 3 real protocol bridges - OPC-UA, MQTT,
  MTConnect - plus the Gateway's own aggregation surface). Real gap found
  auditing the ecosystem against actual CM5 hardware: genuinely working,
  tested code that nothing ever installed anywhere. Live-verified on this
  CM5: all 4 containers build and stay up, `GET /status` reports
  `allReachable:true` for all 3 children with real measured latencies.

### Fixed

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

### Added

- **`provisioning/server.env.example`** now documents (commented out)
  `HYDRA_UMC_DATALAKE_URL`/`HYDRA_UMC_DATALAKE_TIMEOUT_MS` and
  `HYDRA_UMC_SPI_BRIDGE_URL`/`HYDRA_UMC_SPI_BRIDGE_TIMEOUT_MS` - real gap
  found auditing the ecosystem against actual CM5 hardware: `server.ts`
  already reads both (STUDIO's Ecosystem > Telemetry panel and the
  Flasher/Tester's real CANOTA hardware path), but neither ever appeared
  in the example file operators actually provision `server.env` from.
  Left unset by default (Server already answers 503 "not configured"
  rather than guessing a process is there) until HYDRA-UMC-DATALAKE and
  `spi_bridge` are actually installed and running.

## [0.2.2] - The kiosk now shows a mouse cursor with a real mouse attached

### Fixed

- **A physical USB mouse plugged into the CM5's IO board showed no
  pointer at all**, reported live: `-nocursor` on the kiosk's own Xorg
  invocation unconditionally disabled cursor rendering, a reasonable
  default when no pointing device was expected but wrong now that one is
  attached. Removed; `unclutter` (already running) still auto-hides it
  after a second of inactivity, so a touch-only session looks the same as
  before while a real mouse now shows and works.

## [0.2.1] - Fixed the polkit rule install path from [0.2.0]

### Fixed

- **`install_server.sh` couldn't install its own new polkit rule**, found
  running `--apply` live right after `[0.2.0]`: `$ROOT` in this script is
  deliberately the PARENT of this repo (so `SOURCE` can reach the sibling
  `HYDRA-UMC-SERVER` checkout next to it), not this repo's own root - the
  polkit install line used `$ROOT` directly and looked for the rule file
  one directory too high. Added `OS_ROOT` (one level down from `$ROOT`,
  this repo's own real root) and pointed the polkit install line at that
  instead.

## [0.2.0] - Kiosk power buttons: polkit grant for shutdown/restart

### Added

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

### Fixed

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

### Fixed

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

### Fixed

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

### Fixed

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

### Fixed

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

### Fixed

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

### Added

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

### Fixed

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

### Fixed

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

### Fixed

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

### Added

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

### Added

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

### Fixed

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

### Documentation

- **`docs/UPDATE_MODEL.md`** - added the missing standard GPL header (this
  file had none), and documented the real anti-rollback precondition a
  future CM5 deployment flow must honor before changing a checkout: the
  candidate manifest must validate, identify the same project, and not
  declare a lower version than the installed manifest - the same real
  contract `HYDRA-UMC-UPDATER`'s own `clone_or_pull()` now enforces (see
  that repo's own changelog). Honestly notes this is a deployment
  contract, not a claim that rollback has been exercised on a real CM5
  yet. Documentation-only - no code changed.

## [0.0.6] - Fixed after a live ecosystem bug audit

### Fixed (additional, same version)

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

### Fixed

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

### Added

- **A real, host-independent system-file backup/rollback mechanism** (`provisioning/rollback.py`, new) - `backup`/`restore` CLI subcommands record a real, append-only manifest before an installer overwrites a real system file, and can restore it (or delete it, if the installer created it fresh) afterward. Wired into `install_local_agent.sh`'s systemd unit install step, the one file this installer unconditionally overwrites on every run.
- **`tools/verify_rollback.py`** (new) - proves the backup/restore mechanism correct against synthetic files in a temp directory (no root, no CM5 needed): a pre-existing file's real content is restored exactly, a freshly-created file is removed on restore rather than left behind, restoring twice in a row is a real no-op (not an error), and restoring against a missing manifest fails honestly instead of silently doing nothing.
- **`tools/verify_preflight_idempotent.py`** (new) - runs `provisioning/preflight_cm5.py` twice in a row and proves byte-identical output plus zero real files touched under this repository, turning the preflight's own "read-only" claim into a checked, reproducible property instead of only a docstring.
- Both new checks are wired into `tools/build_test.py`'s real test run alongside the existing agent unit tests and deployment-contract verifications.

### Changed

- Automated build version increment from 0.0.3.

## Unreleased

### Documentation

- Reworked the CM5 deployment sequence and first-boot checklist into explicit
  physical and software gates: carrier/power validation, key-based SSH,
  read-only preflight, reviewed dry run, BASE verification/reboot/recovery,
  loopback Server and one-at-a-time hardware enablement. The procedure now
  states the `HYDRA-UMC-TEST` / `hydra-umc-test` / `hydra-umc` identity,
  secret-handling boundary and what host/WSL tests cannot prove.

### Added

- Optional loopback-only HYDRA-UMC-VOICE-UI provisioning, environment
  templates and runtime health verification. This recognised-text gateway is
  separate from the future Hailo STT/TTS stack and cannot actuate hardware.

### Fixed

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

### Added

- Added `provisioning/preflight_cm5.py`, a read-only BASE/CONTROL gate that
  validates identity, configuration, profile, deployment contracts and the
  live OS-to-SDK schema contract before a CM5 is modified.
- Added staged `install_cm5_base.sh`, read-only installed-runtime verification,
  scoped backup/restore and negative preflight checks for invalid configuration,
  identity, SDK and Server plans.

- Host-side agent unit and deployment-contract checks, run by `build-test`
  and CI, to keep first boot, installer and systemd identity/path/permissions
  aligned.

## Documentation

### Added

- `docs/AGENT_REFERENCE.md` - full CLI/JSON reference for
  `hydra-umc-agent` (`describe`/`health`/`serve`), documenting every real
  output field and how `state`/`checks.*` are derived, plus the
  `--config` file's exact schema. Verified live against the running
  agent. Linked from `docs/SERVICE_MODEL.md`. Documentation-only - no
  code changed, no version bump.

## [0.0.3] - 2026-08-26

### Changed

- Automated build version increment from 0.0.2.

## [0.0.2] - 2026-08-26

### Added

- Read-only Python device agent with `describe`, `health`, and periodic
  `serve` commands.
- Validated non-secret configuration example and deterministic health states.
- Hardened `systemd` service unit and Debian package metadata.
- Five host-side unit tests covering configuration and READY/DEGRADED/FAULT
  health transitions.

### Limits

- No production image is built or distributed by this repository yet.
- This release does not command the MCU, CAN, URTC, motion, or updates.

## [0.0.1] - 2026-08-26

### Added

- Initial public project documentation and multilingual README files.
- CM5/Raspberry Pi OS architecture, service, installation, and update design.
- Explicit boundaries between HYDRA-UMC-OS, SDK, official OS components, MCU,
  and URTC.
