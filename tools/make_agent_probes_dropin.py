#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - tools/make_agent_probes_dropin.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The drop-in of the unit of the diagnostics agent that its optional probes need.

    python3 tools/make_agent_probes_dropin.py --config /etc/hydra-umc/config.json --out /etc/systemd/system/hydra-umc-agent.service.d/20-probes.conf

The unit keeps `PrivateDevices=true`, so `vcgencmd get_throttled` (/dev/vcio) and the node of the Hailo are not there. Only while `diagnostics.probes.enabled` is exactly
true, this writes a drop-in that adds those two nodes and nothing else; with the probes off (the default) it removes a drop-in left from before. Not run on a CM5.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

VCIO = "/dev/vcio"
DEVICE = re.compile(r"/dev/[A-Za-z0-9_-]{1,40}")


def probes_of(config: Any) -> dict[str, Any]:
    diagnostics = config.get("diagnostics") if isinstance(config, dict) else None
    probes = diagnostics.get("probes") if isinstance(diagnostics, dict) else None
    return probes if isinstance(probes, dict) else {}


def render(probes: dict[str, Any]) -> str:
    """The text of the drop-in, or "" when the probes are off. A Hailo node that is not a plain /dev name is refused."""
    if probes.get("enabled") is not True:
        return ""
    lines = [
        "# Written by tools/make_agent_probes_dropin.py because diagnostics.probes.enabled is true.",
        "[Service]",
        f"DeviceAllow={VCIO} rw",
        f"BindPaths=-{VCIO}",
        "SupplementaryGroups=video",
    ]
    hailo = probes.get("hailo_device")
    if hailo is not None:
        if not isinstance(hailo, str) or not DEVICE.fullmatch(hailo) or hailo == VCIO:
            raise ValueError("diagnostics.probes.hailo_device must be a plain device node under /dev")
        lines += [f"DeviceAllow={hailo} r", f"BindReadOnlyPaths=-{hailo}"]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        config = json.loads(args.config.read_text(encoding="utf-8")) if args.config.is_file() else {}
        text = render(probes_of(config))
    except (OSError, ValueError) as error:
        print(f"AGENT_PROBES=FAIL {error}", file=sys.stderr)
        return 2
    if not text:
        if args.out.is_file():
            args.out.unlink()
        print("AGENT_PROBES=OFF")
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8", newline="\n")
    args.out.chmod(0o644)
    print(f"AGENT_PROBES=ON {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
