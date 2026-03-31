#!/usr/bin/env python3
"""
Create a tire mod PAK for MotorTown.

Creates new tire physics assets and registers them in VehicleParts0,
then packages everything into a _P.pak file.

Supports both single-tire and multi-tire configs:
  Single: {"tire_physics": {...}, "tire_part": {...}}
  Multi:  {"tires": [{"tire_physics": {...}, "tire_part": {...}}, ...]}

Usage:
    # Standalone (base game only)
    python3 scripts/create_tirepack.py \\
        --config tire_entries.json \\
        --output AMCBetterTires_P.pak

    # Compatible with another mod (builds on top of its VehicleParts0)
    python3 scripts/create_tirepack.py \\
        --config tire_entries.json \\
        --output AMCBetterTires_P.pak \\
        --compat-mod path/to/OtherMod_P.pak
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

def run_dotnet(csharp_dir, args, label):
    """Run a dotnet command and return the result."""
    result = subprocess.run(
        ["dotnet", "run", "--configuration", "Release", "--verbosity", "quiet", "--"] + args,
        cwd=csharp_dir,
        capture_output=True, text=True
    )
    print(result.stdout)
    if result.returncode != 0:
        print(f"Error: {label} failed:\n{result.stderr}")
        sys.exit(1)
    return result

def main():
    parser = argparse.ArgumentParser(
        description="Create MotorTown tire mod PAK",
        epilog="Example: python3 scripts/create_tirepack.py -c tire_entries.json -o AMCTires_P.pak --compat-mod MoreTuning_P.pak"
    )
    parser.add_argument("--config", "-c", required=True, help="Tire config JSON")
    parser.add_argument("--output", "-o", required=True, help="Output PAK file path")
    parser.add_argument("--tire-template", default=None,
                        help="Tire physics template .uasset (default: out/<template>.uasset)")
    parser.add_argument("--compat-mod", action="append", default=[], metavar="PAK",
                        help="Build on top of another mod's VehicleParts0 (can specify multiple, applied in order)")
    args = parser.parse_args()

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.abspath(args.config)
    output_path = os.path.abspath(args.output)

    with open(config_path) as f:
        config = json.load(f)

    # Normalize to list of tire entries
    if "tires" in config:
        tire_entries = config["tires"]
    else:
        tire_entries = [config]  # Single-tire backward compat

    print(f"\n=== Building tire mod with {len(tire_entries)} tire(s) ===")

    # Resolve VehicleParts0 template — base game or extracted from compat mod
    parts0_template = os.path.join(repo_root, "out", "VehicleParts0.uasset")

    if args.compat_mod:
        # Extract VehicleParts0 from the last compat mod PAK that contains it
        # (multiple --compat-mod flags are applied in order)
        for mod_pak in args.compat_mod:
            mod_pak = os.path.abspath(mod_pak)
            if not os.path.exists(mod_pak):
                print(f"Error: Compat mod PAK not found: {mod_pak}")
                sys.exit(1)

            mod_name = os.path.basename(mod_pak)
            print(f"\n  Extracting VehicleParts0 from: {mod_name}")

            extract_dir = tempfile.mkdtemp(prefix="compat_")
            for ext in ["uasset", "uexp"]:
                pak_path = f"MotorTown/Content/DataAsset/VehicleParts/VehicleParts0.{ext}"
                result = subprocess.run(
                    ["cargo", "run", "--release", "--quiet", "--bin", "mod_explore", "--",
                     mod_pak, "--extract", pak_path],
                    cwd=repo_root,
                    capture_output=True, text=True
                )
                if result.returncode != 0:
                    print(f"  Warning: Could not extract VehicleParts0.{ext} from {mod_name}")
                    print(f"  {result.stderr.strip()}")
                else:
                    # mod_explore writes to mod_out/ in CWD (repo_root)
                    src = os.path.join(repo_root, "mod_out", f"VehicleParts0.{ext}")
                    dst = os.path.join(extract_dir, f"VehicleParts0.{ext}")
                    if os.path.exists(src):
                        shutil.move(src, dst)

            extracted = os.path.join(extract_dir, "VehicleParts0.uasset")
            if os.path.exists(extracted):
                parts0_template = extracted
                print(f"  ✓ Using VehicleParts0 from: {mod_name}")
            else:
                print(f"  Warning: {mod_name} does not contain VehicleParts0, skipping")

    parts_templates = {
        "VehicleParts0": os.path.abspath(parts0_template),
    }
    for name, path in parts_templates.items():
        if not os.path.exists(path):
            print(f"Error: {name} template not found: {path}")
            sys.exit(1)

    with tempfile.TemporaryDirectory(prefix="tirepack_") as build_dir:
        csharp_dir = os.path.join(repo_root, "csharp", "CargoExtractor")
        tire_assets = []  # List of (tire_name, uasset_path, uexp_path)

        # Step 1: Create all tire physics assets
        for i, entry in enumerate(tire_entries, 1):
            tire_physics = entry["tire_physics"]
            tire_name = tire_physics["name"]
            template_name = tire_physics["template"]

            tire_template = args.tire_template or os.path.join(repo_root, "out", f"{template_name}.uasset")
            if not os.path.exists(tire_template):
                print(f"Error: Tire template not found: {tire_template}")
                sys.exit(1)

            # Write single-entry config for C# tool
            single_config_path = os.path.join(build_dir, f"tire_{i}.json")
            with open(single_config_path, 'w') as f:
                json.dump(entry, f)

            print(f"\n=== Step 1.{i}: Create tire physics asset ({tire_name}) ===")
            tire_out = os.path.join(build_dir, f"tire_physics_{i}")
            os.makedirs(tire_out, exist_ok=True)
            run_dotnet(csharp_dir,
                ["--patch-tire", single_config_path, tire_template, tire_out],
                f"--patch-tire {tire_name}")

            tire_asset = os.path.join(tire_out, tire_name, f"{tire_name}.uasset")
            tire_uexp = os.path.join(tire_out, tire_name, f"{tire_name}.uexp")
            if not os.path.exists(tire_asset):
                print(f"Error: Tire asset not created: {tire_asset}")
                sys.exit(1)
            tire_assets.append((tire_name, tire_asset, tire_uexp))

        # Step 2: Add all tire parts to both VehicleParts DataTables
        # Each tire must be added sequentially to the same DataTable
        parts_outputs = {}
        for dt_name, dt_template in parts_templates.items():
            print(f"\n=== Step 2: Add {len(tire_entries)} tire(s) to {dt_name} ===")

            # Start from the base template, then chain additions
            current_template = dt_template
            parts_out = None

            for i, entry in enumerate(tire_entries, 1):
                tire_name = entry["tire_physics"]["name"]
                single_config_path = os.path.join(build_dir, f"tire_{i}.json")

                parts_out = os.path.join(build_dir, f"parts_{dt_name}_{i}")
                os.makedirs(parts_out, exist_ok=True)

                run_dotnet(csharp_dir,
                    ["--add-tire-parts", single_config_path, current_template, parts_out],
                    f"--add-tire-parts {tire_name} to {dt_name}")

                # Chain: use output as input for the next tire
                current_template = os.path.join(parts_out, f"{dt_name}.uasset")

            # Final output is the last iteration
            parts_asset = os.path.join(parts_out, f"{dt_name}.uasset")
            parts_uexp = os.path.join(parts_out, f"{dt_name}.uexp")
            if not os.path.exists(parts_asset):
                print(f"Error: {dt_name} not created: {parts_asset}")
                sys.exit(1)
            parts_outputs[dt_name] = (parts_asset, parts_uexp)

        # Step 3: Assemble PAK directory structure
        print(f"\n=== Step 3: Assemble PAK directory ===")
        pak_dir = os.path.join(build_dir, "pak_content")
        
        # Tire physics assets — FLAT path (no subfolder)
        tire_pak_dir = os.path.join(pak_dir, "MotorTown", "Content", "Cars", "Parts", "Tire")
        os.makedirs(tire_pak_dir, exist_ok=True)
        for tire_name, tire_asset, tire_uexp in tire_assets:
            shutil.copy2(tire_asset, os.path.join(tire_pak_dir, f"{tire_name}.uasset"))
            shutil.copy2(tire_uexp, os.path.join(tire_pak_dir, f"{tire_name}.uexp"))
            print(f"  Copied: {tire_name}.uasset + .uexp -> Tire/ (flat)")

        # VehicleParts DataTables
        parts_pak_dir = os.path.join(pak_dir, "MotorTown", "Content", "DataAsset", "VehicleParts")
        os.makedirs(parts_pak_dir, exist_ok=True)
        for dt_name, (asset_path, uexp_path) in parts_outputs.items():
            shutil.copy2(asset_path, os.path.join(parts_pak_dir, f"{dt_name}.uasset"))
            shutil.copy2(uexp_path, os.path.join(parts_pak_dir, f"{dt_name}.uexp"))
            print(f"  Copied: {dt_name}.uasset + .uexp -> DataAsset/VehicleParts/")

        # Step 4: Build PAK
        print(f"\n=== Step 4: Build PAK ===")
        result = subprocess.run(
            ["cargo", "run", "--release", "--quiet", "--bin", "mod_pack", "--",
             pak_dir, output_path],
            cwd=repo_root,
            capture_output=True, text=True
        )
        print(result.stdout)
        if result.returncode != 0:
            print(f"Error: mod_pack failed:\n{result.stderr}")
            sys.exit(1)

    if os.path.exists(output_path):
        size = os.path.getsize(output_path)
        print(f"\n=== Success! ===")
        print(f"  Output: {output_path}")
        print(f"  Size: {size:,} bytes")
        print(f"  Tires: {', '.join(t[0] for t in tire_assets)}")
    else:
        print(f"Error: Output PAK not created: {output_path}")
        sys.exit(1)

if __name__ == "__main__":
    main()
