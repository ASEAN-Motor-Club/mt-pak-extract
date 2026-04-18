#!/usr/bin/env python3
"""
mods — MotorTown mod management CLI.

Provides a unified interface for building, listing, and managing mods.

Usage:
    mods list                    List all mods and their status
    mods build <mod-name>        Build a mod (auto-resolves game version + output path)
    mods show <mod-name>         Show mod details and build history
    mods game-version            Show the active game version
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from modbase import (
    load_mod_config, compute_output_path, resolve_game_version,
    get_active_game_version, MODS_DIR,
)

REPO_ROOT = str(Path(__file__).resolve().parent.parent)

TYPE_TO_SCRIPT = {
    "tire": "scripts/create_tirepack.py",
    "cargo": "scripts/create_cargopack.py",
    "decal": "scripts/create_decal_pack.py",
    "font": "scripts/create_font_mod.py",
}


def find_mod(name: str) -> dict | None:
    """Find a mod by name (matches mod.json 'name' or directory name)."""
    mods_path = os.path.join(REPO_ROOT, MODS_DIR)
    if not os.path.isdir(mods_path):
        return None
    for dirname in sorted(os.listdir(mods_path)):
        mod_dir = os.path.join(mods_path, dirname)
        mod_json = os.path.join(mod_dir, "mod.json")
        if not os.path.isfile(mod_json):
            continue
        mod = load_mod_config(mod_dir)
        if mod["name"] == name or dirname == name:
            return mod
    return None


def cmd_list(args):
    """List all mods."""
    mods_path = os.path.join(REPO_ROOT, MODS_DIR)
    if not os.path.isdir(mods_path):
        print("No mods directory found. Create mods/<name>/mod.json to define a mod.")
        return

    game_ver = get_active_game_version() or "none"
    print(f"Active game version: {game_ver}")
    print()
    print(f"{'Name':<20} {'Type':<8} {'Version':<10} {'Display Name':<25} {'Script'}")
    print("-" * 90)

    for dirname in sorted(os.listdir(mods_path)):
        mod_dir = os.path.join(mods_path, dirname)
        mod_json = os.path.join(mod_dir, "mod.json")
        if not os.path.isfile(mod_json):
            continue
        mod = load_mod_config(mod_dir)
        builds = os.listdir(mod["builds_dir"]) if os.path.isdir(mod["builds_dir"]) else []
        script = mod.get("script") or "(manual)"
        print(f"{mod['name']:<20} {mod['type']:<8} {mod['version']:<10} "
              f"{mod['display_name']:<25} {script}")
        if builds:
            print(f"  Builds: {', '.join(builds)}")


def cmd_build(args):
    """Build a mod."""
    mod = find_mod(args.mod)
    if mod is None:
        print(f"Error: Mod '{args.mod}' not found in {MODS_DIR}/", file=sys.stderr)
        print(f"  Available mods:", file=sys.stderr)
        mods_path = os.path.join(REPO_ROOT, MODS_DIR)
        if os.path.isdir(mods_path):
            for d in sorted(os.listdir(mods_path)):
                mj = os.path.join(mods_path, d, "mod.json")
                if os.path.isfile(mj):
                    print(f"  {d}", file=sys.stderr)
        sys.exit(1)

    game_ver = resolve_game_version(REPO_ROOT)
    mod_type = mod["type"]
    mod_dir = mod["config_dir"]

    script = mod.get("script")
    if not script:
        print(f"Error: Mod '{mod['name']}' has no build script defined in mod.json", file=sys.stderr)
        print(f"  This mod type ({mod_type}) must be built manually.", file=sys.stderr)
        sys.exit(1)

    script_path = os.path.join(REPO_ROOT, script)
    if not os.path.isfile(script_path):
        print(f"Error: Build script not found: {script_path}", file=sys.stderr)
        sys.exit(1)

    output_path = compute_output_path(mod, game_ver)
    os.makedirs(mod["builds_dir"], exist_ok=True)

    cmd = [sys.executable, script_path, "--mod", mod_dir]

    if mod_type == "tire":
        for cfg in mod["configs"]:
            cmd.extend(["--config", cfg])
        cmd.extend(["--output", output_path])
        if args.compat_mod:
            for cm in args.compat_mod:
                cmd.extend(["--compat-mod", cm])

    elif mod_type == "cargo":
        cmd.extend(["--config", mod["configs"][0]])
        if len(mod["configs"]) > 1:
            cmd.extend(["--recipes", mod["configs"][1]])
        cmd.extend(["--output", output_path])
        if args.compat_mod:
            for cm in args.compat_mod:
                cmd.extend(["--compat-mod", cm])

    elif mod_type == "decal":
        input_dir = args.input or os.path.join(mod_dir, "images")
        if not os.path.isdir(input_dir):
            print(f"Error: Input directory not found: {input_dir}", file=sys.stderr)
            print(f"  Place images in {mod_dir}/images/ or use --input", file=sys.stderr)
            sys.exit(1)
        cmd.extend(["--input", input_dir])
        cmd.extend(["--output", output_path])
        if args.category:
            cmd.extend(["--category", args.category])
        if args.cost is not None:
            cmd.extend(["--cost", str(args.cost)])

    elif mod_type == "font":
        input_file = args.input
        if not input_file:
            print(f"Error: Font mod requires --input <font.ttf/otf>", file=sys.stderr)
            sys.exit(1)
        cmd.extend(["--input", input_file])
        cmd.extend(["--output", output_path])

    else:
        print(f"Error: Unknown mod type: {mod_type}", file=sys.stderr)
        sys.exit(1)

    print(f"\n=== Building mod: {mod['display_name']} v{mod['version']} for game v{game_ver} ===")
    print(f"  Output: {output_path}")
    print(f"  Command: {' '.join(cmd)}\n")

    result = subprocess.run(cmd, cwd=REPO_ROOT)
    sys.exit(result.returncode)


def cmd_show(args):
    """Show details for a mod."""
    mod = find_mod(args.mod)
    if mod is None:
        print(f"Error: Mod '{args.mod}' not found", file=sys.stderr)
        sys.exit(1)

    game_ver = get_active_game_version() or "none"
    if game_ver != "none":
        output_path = compute_output_path(mod, resolve_game_version(REPO_ROOT))
    else:
        output_path = "N/A"

    print(f"Mod: {mod['name']}")
    print(f"  Display name: {mod['display_name']}")
    print(f"  Version: {mod['version']}")
    print(f"  Type: {mod['type']}")
    print(f"  Prefix: {mod.get('prefix', '')}")
    print(f"  Build script: {mod.get('script') or '(manual)'}")
    print(f"  Configs: {', '.join(os.path.basename(c) for c in mod.get('configs', []))}")
    print(f"  Expected output: {output_path}")
    print(f"  Builds dir: {mod['builds_dir']}")

    if os.path.isdir(mod["builds_dir"]):
        builds = sorted(os.listdir(mod["builds_dir"]))
        if builds:
            print(f"  Existing builds:")
            for b in builds:
                size = os.path.getsize(os.path.join(mod["builds_dir"], b))
                print(f"    {b} ({size / 1024 / 1024:.1f} MB)")
        else:
            print(f"  No builds yet")


def cmd_game_version(args):
    """Show the active game version."""
    ver = get_active_game_version()
    if ver:
        print(ver)
    else:
        print("No active game version set", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        prog="mods",
        description="MotorTown mod management CLI",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # list
    sub_list = subparsers.add_parser("list", help="List all mods")
    sub_list.set_defaults(func=cmd_list)

    # build
    sub_build = subparsers.add_parser("build", help="Build a mod")
    sub_build.add_argument("mod", help="Mod name or directory (e.g. police-tyres)")
    sub_build.add_argument("--compat-mod", action="append", default=[],
                           help="Compat mod PAK (for tire/cargo mods)")
    sub_build.add_argument("--input", "-i", default=None,
                           help="Input directory or file (for decal/font mods)")
    sub_build.add_argument("--category", "-c", default=None,
                           help="Decal category (for decal mods)")
    sub_build.add_argument("--cost", type=int, default=None,
                           help="Decal cost (for decal mods)")
    sub_build.set_defaults(func=cmd_build)

    # show
    sub_show = subparsers.add_parser("show", help="Show mod details")
    sub_show.add_argument("mod", help="Mod name or directory")
    sub_show.set_defaults(func=cmd_show)

    # game-version
    sub_gv = subparsers.add_parser("game-version", help="Show active game version")
    sub_gv.set_defaults(func=cmd_game_version)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()