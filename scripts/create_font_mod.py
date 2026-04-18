#!/usr/bin/env python3
"""Create a MotorTown font replacement mod PAK from a TTF/OTF file.

Replaces the main UI font (Nanum Square Round) with any TTF/OTF font.
The game loads font data from .ufont files (raw TTF data with different extension).

Usage:
    python3 scripts/create_font_mod.py --input MyFont.ttf --output MyFontMod_P.pak
    python3 scripts/create_font_mod.py --input MyFont.ttf --output MyFontMod_P.pak --replace-ehsmb
    python3 scripts/create_font_mod.py --input MyFont.ttf --output MyFontMod_P.pak --replace-all

Font targets:
    NanumSquareRound (L/R/B/EB)  - Main UI font (default)
    EHSMB                        - Highway/LCD sign font (--replace-ehsmb)
    REGISTER                     - Register label font (--replace-register)
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from modbase import load_mod_config, compute_output_path, resolve_game_version

FONT_TARGETS = {
    "nanum": {
        "dir": "MotorTown/Content/UI/Font/Nanum_SquareRound",
        "files": [
            "NanumSquareRoundL.ufont",
            "NanumSquareRoundR.ufont",
            "NanumSquareRoundB.ufont",
            "NanumSquareRoundEB.ufont",
        ],
        "description": "Main UI font (Nanum Square Round)",
    },
    "ehsmb": {
        "dir": "MotorTown/Content/UI/Font",
        "files": ["EHSMB.ufont"],
        "description": "Highway/LCD sign font (EHSMB)",
    },
    "register": {
        "dir": "MotorTown/Content/UI/Font",
        "files": ["REGISTER.ufont"],
        "description": "Register label font",
    },
}


def create_font_mod(input_ttf: str, output_pak: str, targets: list[str]):
    input_path = Path(input_ttf)
    if not input_path.exists():
        print(f"Error: {input_ttf} not found")
        sys.exit(1)

    # Verify it's a valid font file
    with open(input_path, "rb") as f:
        magic = f.read(4)
    if magic not in (
        b"\x00\x01\x00\x00",  # TrueType
        b"OTTO",  # OpenType CFF
        b"true",  # TrueType (old Mac format)
        b"ttcf",  # TrueType Collection
    ):
        print(f"Warning: {input_ttf} may not be a valid TTF/OTF file")

    with tempfile.TemporaryDirectory() as tmpdir:
        mod_dir = Path(tmpdir) / "font_mod"

        for target_name in targets:
            target = FONT_TARGETS[target_name]
            target_dir = mod_dir / target["dir"]
            target_dir.mkdir(parents=True, exist_ok=True)

            for ufont_name in target["files"]:
                dest = target_dir / ufont_name
                shutil.copy2(input_path, dest)
                print(f"  {target['dir']}/{ufont_name} ({dest.stat().st_size} bytes)")

        # Build mod_pack
        project_root = Path(__file__).parent.parent
        mod_pack_bin = project_root / "target" / "release" / "mod_pack"

        if not mod_pack_bin.exists():
            print("Building mod_pack...")
            subprocess.run(
                ["cargo", "build", "--release", "--bin", "mod_pack"],
                cwd=project_root,
                check=True,
                capture_output=True,
            )

        output_path = Path(output_pak)
        result = subprocess.run(
            [str(mod_pack_bin), str(mod_dir), str(output_path)],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            print(f"Error creating PAK: {result.stderr}")
            sys.exit(1)

        print(f"\nMod PAK created: {output_path} ({output_path.stat().st_size / 1024 / 1024:.1f} MB)")
        print(f"Targets: {', '.join(targets)}")
        print(f"\nTo install: Copy {output_path.name} to the game's Paks directory")


def main():
    parser = argparse.ArgumentParser(description="Create MotorTown font replacement mod")
    parser.add_argument("-i", "--input", required=True, help="Input TTF/OTF font file")
    parser.add_argument("-o", "--output", default=None, help="Output .pak file path (auto-generated from mod.json if omitted)")
    parser.add_argument("--mod", default=None,
                        help="Mod directory (e.g. mods/font-replace) to load mod.json from")
    parser.add_argument(
        "--replace-ehsmb",
        action="store_true",
        help="Also replace EHSMB (highway sign) font",
    )
    parser.add_argument(
        "--replace-register",
        action="store_true",
        help="Also replace REGISTER font",
    )
    parser.add_argument(
        "--replace-all",
        action="store_true",
        help="Replace all game fonts (nanum + ehsmb + register)",
    )

    args = parser.parse_args()

    if args.mod and not args.output:
        mod = load_mod_config(args.mod)
        game_ver = resolve_game_version()
        output_pak = compute_output_path(mod, game_ver)
    elif args.output:
        output_pak = args.output
    else:
        parser.error("Either --output or --mod is required")

    targets = ["nanum"]
    if args.replace_ehsmb or args.replace_all:
        targets.append("ehsmb")
    if args.replace_register or args.replace_all:
        targets.append("register")

    print(f"Creating font mod from: {args.input}")
    print(f"Output: {output_pak}")
    print(f"Targets: {', '.join(t + ' (' + FONT_TARGETS[t]['description'] + ')' for t in targets)}")
    print()

    create_font_mod(args.input, output_pak, targets)


if __name__ == "__main__":
    main()
