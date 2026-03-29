#!/usr/bin/env python3
"""
Create a MotorTown cargo mod PAK.

Pipeline:
  1. Add cargo rows to Cargos.uasset (--add-cargos)
  2. Patch SmallBox.uasset into new cargo blueprints (--patch-blueprint)
  3. Add production config recipes to delivery points (--add-recipes)
  4. Assemble PAK directory structure
  5. Build mod PAK via mod_pack

Usage:
  python3 scripts/create_cargopack.py --config cargo_entries.json --recipes recipe_entries.json --output CarPartsImport_P.pak
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def run(cmd, cwd=None, check=True):
    """Run a command and print output."""
    print(f"  $ {cmd}")
    result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip(), file=sys.stderr)
    if check and result.returncode != 0:
        print(f"  FAILED (exit {result.returncode})")
        sys.exit(1)
    return result


def main():
    parser = argparse.ArgumentParser(description="Create MotorTown cargo mod PAK")
    parser.add_argument("--config", "-c", default="cargo_entries.json",
                       help="Cargo entries JSON config")
    parser.add_argument("--recipes", "-r", default="recipe_entries.json",
                       help="Delivery point recipe entries JSON config")
    parser.add_argument("--output", "-o", default="CarPartsImport_P.pak",
                       help="Output PAK file path")
    parser.add_argument("--cargos-template", default="out/Cargos.uasset",
                       help="Base game Cargos.uasset template")
    parser.add_argument("--blueprint-template", default="out/SmallBox.uasset",
                       help="Base game SmallBox.uasset template")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    build_dir = root / "cargo_build"
    pak_staging = build_dir / "pak_staging"
    dotnet_dir = root / "csharp" / "CargoExtractor"

    # Clean build directory
    if build_dir.exists():
        shutil.rmtree(build_dir)
    build_dir.mkdir(parents=True)

    config_path = root / args.config
    recipes_path = root / args.recipes
    cargos_template = root / args.cargos_template
    bp_template = root / args.blueprint_template

    if not config_path.exists():
        print(f"Error: Config not found: {config_path}")
        sys.exit(1)
    if not recipes_path.exists():
        print(f"Error: Recipes not found: {recipes_path}")
        sys.exit(1)

    with open(config_path) as f:
        cargo_config = json.load(f)
    with open(recipes_path) as f:
        recipe_config = json.load(f)

    cargo_names = [e["blueprint_name"] for e in cargo_config["entries"]]
    print(f"\n=== Car Parts Import Cargo Mod ===")
    print(f"  Cargos: {', '.join(cargo_names)}")
    print(f"  Sources: {[s['delivery_point'] for s in recipe_config.get('sources', [])]}")
    print(f"  Sinks: {[s['delivery_point'] for s in recipe_config.get('sinks', [])]}")

    # ----------------------------------------------------------
    # Step 1: Add cargo rows to Cargos DataTable
    # ----------------------------------------------------------
    print(f"\n--- Step 1: Add cargo rows to Cargos DataTable ---")
    cargos_output = build_dir / "cargos"
    cargos_output.mkdir()
    run(
        f"dotnet run --configuration Release --verbosity quiet -- "
        f"--add-cargos {config_path} {cargos_template} {cargos_output}",
        cwd=dotnet_dir,
    )

    # ----------------------------------------------------------
    # Step 2: Patch cargo blueprints from SmallBox template
    # ----------------------------------------------------------
    print(f"\n--- Step 2: Patch cargo blueprints ---")
    blueprints_output = build_dir / "blueprints"
    blueprints_output.mkdir()
    run(
        f"dotnet run --configuration Release --verbosity quiet -- "
        f"--patch-blueprint {config_path} {bp_template} {blueprints_output}",
        cwd=dotnet_dir,
    )

    # ----------------------------------------------------------
    # Step 3: Add production config recipes to delivery points
    # ----------------------------------------------------------
    print(f"\n--- Step 3: Add delivery point recipes ---")
    recipes_output = build_dir / "recipes"
    recipes_output.mkdir()
    run(
        f"dotnet run --configuration Release --verbosity quiet -- "
        f"--add-recipes {recipes_path} {recipes_output}",
        cwd=dotnet_dir,
    )

    # ----------------------------------------------------------
    # Step 4: Assemble PAK directory structure
    # ----------------------------------------------------------
    print(f"\n--- Step 4: Assemble PAK directory ---")
    content = pak_staging / "MotorTown" / "Content"

    # Cargos DataTable
    dt_dir = content / "DataAsset"
    dt_dir.mkdir(parents=True)
    for ext in [".uasset", ".uexp"]:
        src = cargos_output / f"Cargos{ext}"
        if src.exists():
            shutil.copy2(src, dt_dir / f"Cargos{ext}")
            print(f"  Staged: DataAsset/Cargos{ext}")

    # Cargo blueprints — placed directly in Delivery/ (no subfolder!)
    # Engine maps package path /Game/.../Delivery/{name} to file Delivery/{name}.uasset
    bp_base = content / "Objects" / "Mission" / "Delivery"
    bp_base.mkdir(parents=True, exist_ok=True)
    for name in cargo_names:
        bp_src = blueprints_output / name
        for ext in [".uasset", ".uexp"]:
            src = bp_src / f"{name}{ext}"
            if src.exists():
                shutil.copy2(src, bp_base / f"{name}{ext}")
                print(f"  Staged: Objects/Mission/Delivery/{name}{ext}")

    # Delivery points
    dp_dir = content / "Objects" / "Mission" / "Delivery" / "DeliveryPoint"
    dp_dir.mkdir(parents=True)
    all_dps = set()
    for section in ["sources", "sinks"]:
        for dp in recipe_config.get(section, []):
            all_dps.add(dp["delivery_point"])
    for dp_name in all_dps:
        for ext in [".uasset", ".uexp"]:
            src = recipes_output / f"{dp_name}{ext}"
            if src.exists():
                shutil.copy2(src, dp_dir / f"{dp_name}{ext}")
                print(f"  Staged: Objects/Mission/Delivery/DeliveryPoint/{dp_name}{ext}")

    # ----------------------------------------------------------
    # Step 5: Build mod PAK
    # ----------------------------------------------------------
    print(f"\n--- Step 5: Build mod PAK ---")
    output_pak = root / args.output
    mod_pack = root / "target" / "release" / "mod_pack"

    if not mod_pack.exists():
        print("  Building mod_pack...")
        run("cargo build --release --bin mod_pack", cwd=root)

    run(f"{mod_pack} {pak_staging} {output_pak}")
    print(f"\n=== Mod PAK created: {output_pak} ===")

    # Verify
    mod_explore = root / "target" / "release" / "mod_explore"
    if mod_explore.exists():
        print(f"\n--- PAK contents ---")
        run(f"{mod_explore} {output_pak} --list", check=False)


if __name__ == "__main__":
    main()
