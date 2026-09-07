# Development rules

Use Raspberry Pi OS interfaces first: systemd for lifecycle, udev for device
discovery, NetworkManager for networking, journald for logs, and libcamera or
GStreamer for cameras. New code needs an ADR if it replaces a supported native
mechanism.

Test in this order: schema validation, unit test, service integration on a
host, CM5 smoke test, and hardware-in-the-loop when a MCU is involved. Never
test an unreviewed motion command on an uncontrolled physical machine.

## Current host verification

The base agent has no third-party runtime dependency. From `agent/`, run:

```text
python -m unittest discover -s tests -v
PYTHONPATH=src python -m hydra_umc_os.agent --config ../config/hydra-umc-os.example.json health
```

The second command is read-only. A host that is not a CM5 can report its own
platform metadata; this is expected and is not CM5 validation.
