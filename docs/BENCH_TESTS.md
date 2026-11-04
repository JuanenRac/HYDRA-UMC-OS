# Bench tests

Every test below is **not executed**. The installers, the agent and the units are covered by text checks and host tests; nothing here has run on a Compute Module 5 with the target image. Write a result only after a person ran the step.

## What the software already covers (no board needed)

- `python tools/hydra_project_tool.py test` runs the agent tests (report only on change, heartbeat), the installer generation check, the checks of the units and the secrets policy.
- `verify_cm5_runtime.sh --secrets --json` is read-only and never opens a secret file.

## Setup

- A Compute Module 5 flashed with the official Debian trixie image, reachable by SSH, with the programs installed by the generated installers.
- A second HDMI display for the kiosk steps and a Wi-Fi network the board can join.
- A copy of the data to protect before the update and recovery steps.

## Steps

| # | Step | Expected result | Result |
|---|------|-----------------|--------|
| 1 | Run `verify_cm5_runtime.sh --secrets`. | Owner, group and mode of each secret file in `/etc/hydra-umc` follow the policy; a file open to everybody fails the check. | not executed |
| 2 | Run an installer twice, as a user that does not own the checkout. | It builds as the owner of the checkout, switches the current release and keeps the previous one for a rollback. | not executed |
| 3 | Break a build on purpose and run the installer again. | The update stops, the running release is untouched and the rollback command returns to the previous one. | not executed |
| 4 | Run the recovery script and restore the backup on a clean board. | The backup holds the database taken with `sqlite3 .backup`, the settings and the keys named in its list; the restored board starts. | not executed |
| 5 | Feed the Wi-Fi provisioning page a wrong password, then a right one, from a phone. | The page answers at once (trying to join), the setup network goes down a few seconds later; after the phone reconnects to the setup network the page (or `/status`) shows the failure of the wrong one; the right one joins. | not executed |
| 6 | Start the agent in serve mode and look at the journal for ten minutes. | It writes only when the state changes plus the heartbeat every five minutes. | not executed |
| 7 | Read the agent report with the accelerator present and under load. | Temperature and throttling (`vcgencmd`) appear when the checks are built; until then record that they are missing. | not executed |
| 8 | Check the hardened agent and Wi-Fi units with `systemd-analyze security`. | Record the exposure level and any directive the image refuses. | not executed |
| 9 | Start the kiosk (cage and a Wayland browser) on the HDMI display. | The page fills the screen and survives a restart of the browser. | not executed |

## Known gaps

Steps 2 to 4 describe the wanted behaviour of the update and recovery scripts (build as the owner of the checkout, a current release with a rollback, a backup that includes the generated settings). The scripts do not do all of it yet, so those steps are expected to fail today; record exactly where.

## What this bench cannot show

Behaviour of a two-slot image and of an A/B bootloader is only designed (see the architecture notes), so there is no step for it; it needs a board with the bootloader support and a way to recover a bricked unit.
