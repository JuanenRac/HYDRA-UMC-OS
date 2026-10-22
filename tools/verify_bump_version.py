#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - tools/verify_bump_version.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Check that bump_version.py follows the one rule of the ecosystem.

Each case copies the two bump scripts into a scratch repository, runs bump_version.py there and
reads back the native version, the agent's own version, the manifest and the changelog.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CASES = [
    ("0.5.3", "0.5.4"),
    ("0.5.9", "0.6.0"),
    ("0.7.8", "0.7.9"),
    ("0.7.9", "0.8.0.0"),
    ("0.8.0.0", "0.8.0.1"),
    ("0.8.0.9", "0.8.1.0"),
    ("0.8.9.9", "0.9.0.0"),
]

failures: list[str] = []


def expect(condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def scratch_repository(base: Path, version: str) -> Path:
    repo = base / "repo"
    (repo / "agent" / "src" / "hydra_umc_os").mkdir(parents=True)
    for name in ("bump_version.py", "bump_manifest_version.py"):
        shutil.copy(ROOT / name, repo / name)
    manifest = json.loads((ROOT / "hydra-umc.project.json").read_text(encoding="utf-8"))
    manifest["version"] = version
    (repo / "hydra-umc.project.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (repo / "agent" / "pyproject.toml").write_text(f'[project]\nname = "x"\nversion = "{version}"\n', encoding="utf-8")
    (repo / "agent" / "src" / "hydra_umc_os" / "__init__.py").write_text(f'"""x"""\n__version__ = "{version}"\n', encoding="utf-8")
    (repo / "CHANGELOG.md").write_text(f"# Changelog\n\nIntro.\n\n## [{version}]\n\n- Something.\n", encoding="utf-8")
    return repo


def run_case(start: str, expected: str) -> None:
    with tempfile.TemporaryDirectory() as directory:
        repo = scratch_repository(Path(directory), start)
        result = subprocess.run([sys.executable, str(repo / "bump_version.py")], cwd=repo, capture_output=True, text=True)
        expect(result.returncode == 0, f"{start}: the bump failed: {result.stdout} {result.stderr}")
        manifest = json.loads((repo / "hydra-umc.project.json").read_text(encoding="utf-8"))
        expect(manifest["version"] == expected, f"{start}: the manifest says {manifest['version']}, expected {expected}")
        pyproject = (repo / "agent" / "pyproject.toml").read_text(encoding="utf-8")
        expect(f'version = "{expected}"' in pyproject, f"{start}: the package version is not {expected}")
        init = (repo / "agent" / "src" / "hydra_umc_os" / "__init__.py").read_text(encoding="utf-8")
        expect(f'__version__ = "{expected}"' in init, f"{start}: the agent version is not {expected}")
        changelog = (repo / "CHANGELOG.md").read_text(encoding="utf-8")
        expect(f"## [{expected}]" in changelog, f"{start}: the changelog has no entry for {expected}")
        expect("###" not in changelog, f"{start}: the changelog entry has a subheading")


def main() -> int:
    for start, expected in CASES:
        run_case(start, expected)
    source = (ROOT / "bump_version.py").read_text(encoding="utf-8")
    expect("def bump(" not in source and "def next_version(" not in source, "bump_version.py must not carry its own copy of the rule")
    expect("bump_manifest_version.py" in source, "bump_version.py must use the shared utility")
    # a manifest and a package that disagree are refused, not silently fixed
    with tempfile.TemporaryDirectory() as directory:
        repo = scratch_repository(Path(directory), "0.5.3")
        (repo / "agent" / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "0.5.9"\n', encoding="utf-8")
        result = subprocess.run([sys.executable, str(repo / "bump_version.py")], cwd=repo, capture_output=True, text=True)
        expect(result.returncode != 0, "a manifest that disagrees with the package must stop the bump")
    if failures:
        for message in failures:
            print(f"BUMP_VERSION=FAIL {message}", file=sys.stderr)
        return 1
    print(f"BUMP_VERSION=PASS cases={len(CASES) + 1}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
