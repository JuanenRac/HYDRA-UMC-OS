#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - Installer generation verification
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Prove provisioning/generate_installers.py: every installer it generates reads back as its row of the table and follows the
deployment contract, nothing existing is overwritten, and writing into provisioning/ is refused while the option is off.
The generated scripts are never executed."""

from __future__ import annotations

import importlib.util
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROVISIONING = ROOT / "provisioning"
spec = importlib.util.spec_from_file_location("generate_installers", PROVISIONING / "generate_installers.py")
assert spec and spec.loader
gen = importlib.util.module_from_spec(spec)
sys.modules["generate_installers"] = gen
spec.loader.exec_module(gen)


class GenerateInstallersTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = gen._load_plan_module()
        self.config = gen.load_config()

    def test_every_generated_script_reads_back_as_its_row(self) -> None:
        self.assertEqual(gen.check(self.plan, self.config), [])
        made, skipped = gen.build_all(self.plan, self.config)
        self.assertGreaterEqual(len(made), 20)
        self.assertIn("install_twin.sh", made)
        self.assertTrue(all(name not in made for name in skipped))

    def test_the_shape_has_the_guards_and_the_contract(self) -> None:
        text = gen.build_all(self.plan, self.config, "twin")[0]["install_twin.sh"]
        for fragment in ('--apply', "EUID -eq 0", "DEPLOY_CONTRACT=1", "deploy_begin HYDRA-UMC-TWIN", "deploy_finish HYDRA-UMC-TWIN",
                         "hydra-umc.project.json", "announce_health"):
            self.assertIn(fragment, text)
        self.assertLess(text.index("systemctl daemon-reload"), text.index("deploy_finish"))
        self.assertNotIn("enable --now hydra", text.split("echo ")[0])

    def rows(self) -> dict[str, dict]:
        return {r["script"]: r for r in self.plan.build(PROVISIONING, self.plan.registry())["installers"]}

    def test_every_program_that_needs_a_build_hook_has_one_and_the_script_sources_it(self) -> None:
        made, _ = gen.build_all(self.plan, self.config)
        rows = self.rows()
        for script, text in made.items():
            row = rows[script]
            short = gen.short_name(row)
            self.assertTrue(gen.needs_hook(row, self.config), f"{script} is generated but has no entry under hooks")
            hook = PROVISIONING / self.config["hook_dir"] / f"{short}.sh"
            self.assertTrue(hook.is_file(), f"{script} needs {hook.name}")
            self.assertIn(f'HOOK="$HERE/{self.config["hook_dir"]}/{short}.sh"', text)
            self.assertIn('source "$HOOK"', text)
            self.assertNotIn("sudo", re.sub(r"^\s*#.*$", "", hook.read_text(encoding="utf-8"), flags=re.MULTILINE), f"{hook.name} must not call sudo")
        self.assertEqual(gen.missing_hooks(list(rows.values()), self.config), [])

    def test_no_hook_is_left_without_a_row_and_no_hook_runs_on_its_own(self) -> None:
        rows = self.rows()
        shorts = {gen.short_name(r) for r in rows.values() if gen.eligible(r)}
        for hook in sorted((PROVISIONING / self.config["hook_dir"]).glob("*.sh")):
            name = hook.name.removesuffix(".preflight.sh").removesuffix(".sh")
            self.assertIn(name, shorts, f"{hook.name} belongs to no generated installer")
            text = hook.read_text(encoding="utf-8")
            self.assertTrue(text.startswith("#!/usr/bin/env bash"), hook.name)
            self.assertNotIn("set -e", text, f"{hook.name} is sourced: it must not change the shell options of the installer")
        for name in self.config["hooks"] + self.config["preflights"]:
            self.assertIn(name, shorts, f"{name} in the configuration has no generated installer")

    def test_the_installers_in_the_folder_are_the_generated_ones(self) -> None:
        made, _ = gen.build_all(self.plan, self.config)
        for script, text in made.items():
            on_disk = (PROVISIONING / script).read_text(encoding="utf-8").replace("\r\n", "\n")
            self.assertEqual(on_disk, text, f"{script} differs from what generate_installers.py writes (edit the table or its hook, then run it with --replace)")

    def test_what_the_hand_written_ones_did_is_kept_by_the_hooks(self) -> None:
        facts = {
            "cargo build --release": ("hil-bridge", "orchestrator", "swarm-sync", "twin"),
            '"$GO_BIN" build': ("job-dispatcher", "node-healing", "telemetry-collector"),
            "npm ci": ("dashboard-ai", "server"),
            "generate_secrets.py": ("server", "voice-ui"),
            "workspace": ("cognitive-node", "twin", "vision-node", "vla-engine"),
            "registry.json": ("detection-hef",),
            "downsample.sh": ("datalake",),
            "python3-numpy": ("anomaly-detector",),
        }
        for fragment, names in facts.items():
            for name in names:
                text = (PROVISIONING / self.config["hook_dir"] / f"{name}.sh").read_text(encoding="utf-8")
                self.assertIn(fragment, text, f"{name}: the hook lost {fragment!r}")
        self.assertIn("--create-home", gen.build_all(self.plan, self.config, "server")[0]["install_server.sh"])
        self.assertIn("node-healing.preflight.sh", gen.build_all(self.plan, self.config, "node-healing")[0]["install_node_healing.sh"])

    def test_nothing_is_overwritten_and_the_provisioning_folder_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(gen.main(["--out", tmp, "--only", "twin"]), 0)
            self.assertTrue((Path(tmp) / "install_twin.sh").is_file())
            self.assertEqual(gen.main(["--out", tmp, "--only", "twin"]), 2)
        self.assertFalse(self.config["allow_replace_existing"])
        self.assertEqual(gen.main(["--out", str(PROVISIONING)]), 2)

    def test_show_and_check_commands(self) -> None:
        self.assertEqual(gen.main(["--show", "twin"]), 0)
        self.assertEqual(gen.main(["--show", "nothing"]), 2)


if __name__ == "__main__":
    unittest.main()
