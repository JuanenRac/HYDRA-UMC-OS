#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-OS - provisioning/generate_installers.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Write the `install_*.sh` of the programs from the table of installers (install_plan.json) instead of by hand.

    python3 generate_installers.py --out DIR [--only twin]   write the generated scripts into a new folder
    python3 generate_installers.py --check                   generate in memory and prove each script reads back as its row
    python3 generate_installers.py --replace                 write the generated scripts over the ones in this folder
    python3 generate_installers.py --show twin               print one generated script

The 25 or so installers share one shape (guards, system user, program folder, unit files, project manifest, the deployment
contract). A generated script is that shape filled in from a row of the table; whatever a project does beyond it (a compile,
a model, a certificate) goes in an optional `build_hooks/<name>.sh` that the script sources, so the shared part cannot drift.
Nothing is run. A script is written only into a folder the caller names; an existing file is never overwritten, except by the
explicit `--replace` command (or with `allow_replace_existing` of config/installer_generation.json turned on, off by default),
which refuses to run while a row that needs a build hook has none. The rows that clone, compile or fetch on the device are listed
under `hooks` in that file. A hook may define the function `hook_after_install`, which the script calls once it has said that the
program is installed. Rows that have too little in the table are left to their own script. Standard library only.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
CONFIG_FILE = HERE.parent / "config" / "installer_generation.json"


def _load_plan_module() -> Any:
    spec = importlib.util.spec_from_file_location("install_plan", HERE / "install_plan.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("install_plan", module)
    spec.loader.exec_module(module)
    return module


def load_config(path: Path = CONFIG_FILE) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("format") != "hydra-installer-generation/1":
        raise ValueError(f"{path} is not a hydra-installer-generation/1 file")
    return config  # type: ignore[no-any-return]


def eligible(row: dict[str, Any]) -> bool:
    """A row can be generated when it names its repository, folder, user and units and follows the deployment contract."""
    return bool(row.get("source") and row.get("target") and row.get("user") and row.get("units") and row.get("contract") == 1)


def short_name(row: dict[str, Any]) -> str:
    """The folder of the program below /opt/hydra-umc, which names its hook."""
    return Path(str(row["target"])).name


def needs_hook(row: dict[str, Any], config: dict[str, Any]) -> bool:
    """True when the program does more than the shared shape (it compiles, fetches, installs packages or sets up more than its folder)."""
    return bool(row.get("target")) and short_name(row) in config["hooks"]


def preflight_path(row: dict[str, Any], config: dict[str, Any]) -> Path:
    return HERE / str(config["hook_dir"]) / f"{short_name(row)}.preflight.sh"


def hook_path(row: dict[str, Any], config: dict[str, Any]) -> Path:
    return HERE / str(config["hook_dir"]) / f"{short_name(row)}.sh"


def missing_hooks(rows: list[dict[str, Any]], config: dict[str, Any]) -> list[str]:
    """The hook files that rows need and that do not exist."""
    found = [f"{config['hook_dir']}/{short_name(r)}.sh" for r in rows if eligible(r) and needs_hook(r, config) and not hook_path(r, config).is_file()]
    found += [f"{config['hook_dir']}/{short_name(r)}.preflight.sh" for r in rows
              if eligible(r) and short_name(r) in config["preflights"] and not preflight_path(r, config).is_file()]
    return found


def generate(row: dict[str, Any], config: dict[str, Any]) -> str:
    """The text of the installer of one row."""
    if not eligible(row):
        raise ValueError(f"{row.get('script')}: not enough in the table to generate it")
    name = str(row["source"])
    short = Path(str(row["target"])).name
    script = str(row["script"])
    units = list(row["units"])
    data = str(config["data_dir"])
    hook = f"{config['hook_dir']}/{short}.sh"
    lines = [
        "#!/usr/bin/env bash",
        "# =============================================================================",
        f"# HYDRA-UMC-OS - {script} (generated by provisioning/generate_installers.py from install_plan.json)",
        "# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>",
        "# GPL-3.0-or-later - see LICENSE",
        "# =============================================================================",
        "set -euo pipefail",
        'HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"',
        *([f'source "$HERE/{config["hook_dir"]}/{short}.preflight.sh"'] if short in config["preflights"] else []),
        "APPLY=0",
        'for arg in "$@"; do if [[ "$arg" == "--apply" ]]; then APPLY=1; fi; done',
        '[[ $APPLY -eq 1 ]] || { echo "Dry-run policy: rerun with --apply after review${DRY_RUN_NOTE:-}."; exit 0; }',
        '[[ $EUID -eq 0 ]] || { echo "Run as root with sudo." >&2; exit 2; }',
        "",
        'ROOT="$(cd "$(dirname "$0")/../.." && pwd)"',
        f'SOURCE="$ROOT/{name}"',
        f"TARGET={row['target']}",
        "DEPLOY_CONTRACT=1",
        'source "$HERE/deploy_lib.sh"',
        f'deploy_begin {name} "$TARGET"',
        f'SVC_USER="{row["user"]}"',
        "",
        '[[ -f "$SOURCE/hydra-umc.project.json" ]] || { echo "' + name + ' source is incomplete: $SOURCE" >&2; exit 2; }',
    ]
    for unit in units:
        lines.append(f'[[ -f "$SOURCE/systemd/{unit}" ]] || {{ echo "{name} has no unit {unit}: $SOURCE" >&2; exit 2; }}')
    lines += [
        'if ! id -u "$SVC_USER" >/dev/null 2>&1; then',
        f'  useradd --system --home "$TARGET{"/" + data if short in config["home_in_data"] else ""}" '
        + ("--create-home" if short in config["home_in_data"] else "--no-create-home")
        + ' --shell /usr/sbin/nologin "$SVC_USER"',
        "fi",
        'install -d -o root -g root -m 0755 "$TARGET"',
        f'HOOK="$HERE/{hook}"',
    ]
    if needs_hook(row, config):
        lines.append(f'[[ -f "$HOOK" ]] || {{ echo "{name} needs its build hook {hook}: $HOOK" >&2; exit 2; }}')
        lines.append('source "$HOOK"')
    else:
        lines.append('if [[ -f "$HOOK" ]]; then source "$HOOK"; fi')
    for folder in ([] if short in config["no_copy_dirs"] else config["copy_dirs"]):
        lines += [
            f'if [[ -d "$SOURCE/{folder}" ]]; then',
            f'  rm -rf "$TARGET/{folder}"',
            f'  cp -a "$SOURCE/{folder}" "$TARGET/"',
            f'  chown -R root:root "$TARGET/{folder}"',
            f'  chmod -R go-w "$TARGET/{folder}"',
            "fi",
        ]
    if data in row.get("user_dirs", []):
        lines.append(f'install -d -o "$SVC_USER" -g "$SVC_USER" -m 0750 "$TARGET/{data}"')
    for unit in units:
        lines.append(f'install -m 0644 "$SOURCE/systemd/{unit}" /etc/systemd/system/{unit}')
    lines += [
        'install -m 0644 "$SOURCE/hydra-umc.project.json" "$TARGET/hydra-umc.project.json"',
        "systemctl daemon-reload",
        f'deploy_finish {name} "$TARGET"',
    ]
    main_unit = row.get("unit") or units[0]
    lines += [
        f'echo "{short} installed. Enable manually after review: systemctl enable --now {str(main_unit).removesuffix(".service")}"',
        'if declare -F hook_after_install >/dev/null; then hook_after_install; fi',
    ]
    if short not in config["no_health_announce"]:  # the programs that are not a service of the registry have no health route to announce
        lines += ['source "$HERE/service_registry.sh"', f"announce_health {name}"]
    lines.append("")
    return "\n".join(lines)


def build_all(plan_module: Any, config: dict[str, Any], only: str | None = None) -> tuple[dict[str, str], list[str]]:
    """script name -> text for every eligible row, and the names of the rows that could not be generated."""
    table = plan_module.build(HERE, plan_module.registry())
    made: dict[str, str] = {}
    skipped: list[str] = []
    for row in table["installers"]:
        if only and row["script"] != f"install_{only.replace('-', '_')}.sh":
            continue
        if eligible(row):
            made[str(row["script"])] = generate(row, config)
        else:
            skipped.append(str(row["script"]))
    return made, skipped


def check(plan_module: Any, config: dict[str, Any]) -> list[str]:
    """What is wrong with the generated scripts: one that does not read back as its row, or that bash cannot parse."""
    made, _ = build_all(plan_module, config)
    table = plan_module.build(HERE, plan_module.registry())
    rows = {row["script"]: row for row in table["installers"]}
    found: list[str] = [f"{name}: a build hook the table needs does not exist" for name in missing_hooks(list(rows.values()), config)]
    bash = shutil.which("bash")
    hook_dir = HERE / str(config["hook_dir"])
    for hook_file in sorted(hook_dir.glob("*.sh")) if hook_dir.is_dir() else []:
        if bash and subprocess.run([bash, "-n", str(hook_file)], capture_output=True, check=False).returncode != 0:
            found.append(f"{hook_file.name}: bash cannot parse the build hook")
    with tempfile.TemporaryDirectory() as tmp:
        for script, text in made.items():
            path = Path(tmp) / script
            path.write_text(text, encoding="utf-8", newline="\n")
            back = plan_module.read_script(path)
            row = rows[script]
            for key in ("source", "target", "user", "units", "contract", "begins", "finishes", "finish_after_reload", "installs_manifest"):
                if back[key] != row[key]:
                    found.append(f"{script}: {key} reads back as {back[key]!r}, the table says {row[key]!r}")
            extra = {k: row[k] for k in ("port", "health_path", "unit") if k in row}
            found.extend(plan_module.problems({"installers": [{**back, **extra}]}, {}))
            if bash and subprocess.run([bash, "-n", str(path)], capture_output=True, check=False).returncode != 0:
                found.append(f"{script}: bash cannot parse the generated script")
    return found


def replace_in_place(plan_module: Any, config: dict[str, Any], only: str | None) -> int:
    """Write the generated scripts over the hand-written ones of this folder, once, after the whole check passes (the option stays off)."""
    failures = check(plan_module, config)
    for failure in failures:
        print(f"REFUSED: {failure}", file=sys.stderr)
    if failures:
        return 2
    made, skipped = build_all(plan_module, config, only)
    for script, text in made.items():
        (HERE / script).write_text(text, encoding="utf-8", newline="\n")
    print(f"replaced {len(made)} installers in {HERE} ({len(skipped)} keep their own script)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, help="folder to write the scripts into")
    parser.add_argument("--only", help="one installer, by its name without install_ and .sh")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--replace", action="store_true", help="write the generated scripts over the ones in this folder (explicit, once)")
    parser.add_argument("--show", metavar="NAME")
    args = parser.parse_args(argv)
    plan_module = _load_plan_module()
    config = load_config()
    if args.show:
        made, _ = build_all(plan_module, config, args.show)
        if not made:
            print(f"no generable installer named {args.show}", file=sys.stderr)
            return 2
        print(next(iter(made.values())), end="")
        return 0
    if args.check:
        failures = check(plan_module, config)
        made, skipped = build_all(plan_module, config)
        rows = {r["script"]: r for r in plan_module.build(HERE, plan_module.registry())["installers"]}
        hooks = [s for s in made if needs_hook(rows[s], config)]
        for failure in failures:
            print(f"INSTALLER_GENERATION=FAIL {failure}", file=sys.stderr)
        if failures:
            return 1
        print(f"INSTALLER_GENERATION=PASS {len(made)} generated, {len(hooks)} of them need a build hook, {len(skipped)} left to their own script")
        return 0
    if args.replace:
        return replace_in_place(plan_module, config, args.only)
    if not args.out:
        parser.error("give --out, --check, --replace or --show")
    out = args.out.resolve()
    if out == HERE and not config["allow_replace_existing"]:
        print("REFUSED: writing into provisioning/ needs --replace or allow_replace_existing in config/installer_generation.json", file=sys.stderr)
        return 2
    made, skipped = build_all(plan_module, config, args.only)
    out.mkdir(parents=True, exist_ok=True)
    for script in made:
        target = out / script
        if target.exists() and not (out == HERE and config["allow_replace_existing"]):
            print(f"REFUSED: {target} already exists: not overwriting", file=sys.stderr)
            return 2
    for script, text in made.items():
        (out / script).write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {len(made)} installers to {out} ({len(skipped)} rows have too little in the table to generate)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
