#!/usr/bin/env python3
"""
Create a tire mod PAK for MotorTown.

Creates a new tire physics asset and adds it to both VehicleParts DataTables
(VehicleParts + VehicleParts0), then packages everything into a _P.pak file.

Usage:
    python3 scripts/create_tirepack.py \\
        --config tire_entries.json \\
        --output AMCBetterTires_P.pak
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

def main():
    parser = argparse.ArgumentParser(description="Create MotorTown tire mod PAK")
    parser.add_argument("--config", "-c", required=True, help="Tire config JSON")
    parser.add_argument("--output", "-o", required=True, help="Output PAK file path")
    parser.add_argument("--tire-template", default=None,
                        help="Tire physics template .uasset (default: out/<template>.uasset)")
    args = parser.parse_args()

    # Resolve paths relative to repo root
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.abspath(args.config)
    output_path = os.path.abspath(args.output)

    # Read config
    with open(config_path) as f:
        config = json.load(f)

    tire_physics = config["tire_physics"]
    tire_part = config["tire_part"]
    tire_name = tire_physics["name"]
    template_name = tire_physics["template"]

    # Resolve template paths
    tire_template = args.tire_template or os.path.join(repo_root, "out", f"{template_name}.uasset")
    # Both VehicleParts DataTables need to be patched
    parts_templates = {
        "VehicleParts": os.path.join(repo_root, "out", "VehicleParts.uasset"),
        "VehicleParts0": os.path.join(repo_root, "out", "VehicleParts0.uasset"),
    }

    if not os.path.exists(tire_template):
        print(f"Error: Tire template not found: {tire_template}")
        sys.exit(1)
    for name, path in parts_templates.items():
        if not os.path.exists(path):
            print(f"Error: {name} template not found: {path}")
            sys.exit(1)

    # Create temp build directory
    with tempfile.TemporaryDirectory(prefix="tirepack_") as build_dir:
        csharp_dir = os.path.join(repo_root, "csharp", "CargoExtractor")

        # Step 1: Create tire physics asset
        print(f"\n=== Step 1: Create tire physics asset ({tire_name}) ===")
        tire_out = os.path.join(build_dir, "tire_physics")
        os.makedirs(tire_out, exist_ok=True)
        result = subprocess.run(
            ["dotnet", "run", "--configuration", "Release", "--verbosity", "quiet", "--",
             "--patch-tire", config_path, tire_template, tire_out],
            cwd=csharp_dir,
            capture_output=True, text=True
        )
        print(result.stdout)
        if result.returncode != 0:
            print(f"Error: --patch-tire failed:\n{result.stderr}")
            sys.exit(1)

        # Verify tire asset exists
        tire_asset = os.path.join(tire_out, tire_name, f"{tire_name}.uasset")
        tire_uexp = os.path.join(tire_out, tire_name, f"{tire_name}.uexp")
        if not os.path.exists(tire_asset):
            print(f"Error: Tire asset not created: {tire_asset}")
            sys.exit(1)

        # Step 2: Add tire part to BOTH VehicleParts DataTables
        # The game loads VehicleParts (686 rows) then merges VehicleParts0 (50 rows) on top.
        # We need to add our tire to both to ensure it appears.
        parts_outputs = {}
        for dt_name, dt_template in parts_templates.items():
            step_label = "2a" if dt_name == "VehicleParts" else "2b"
            print(f"\n=== Step {step_label}: Add tire part to {dt_name} ===")
            parts_out = os.path.join(build_dir, f"parts_{dt_name}")
            os.makedirs(parts_out, exist_ok=True)
            result = subprocess.run(
                ["dotnet", "run", "--configuration", "Release", "--verbosity", "quiet", "--",
                 "--add-tire-parts", config_path, dt_template, parts_out],
                cwd=csharp_dir,
                capture_output=True, text=True
            )
            print(result.stdout)
            if result.returncode != 0:
                print(f"Error: --add-tire-parts failed for {dt_name}:\n{result.stderr}")
                sys.exit(1)

            parts_asset = os.path.join(parts_out, f"{dt_name}.uasset")
            parts_uexp = os.path.join(parts_out, f"{dt_name}.uexp")
            if not os.path.exists(parts_asset):
                print(f"Error: {dt_name} not created: {parts_asset}")
                sys.exit(1)
            parts_outputs[dt_name] = (parts_asset, parts_uexp)

        # Step 3: Assemble PAK directory structure
        print(f"\n=== Step 3: Assemble PAK directory ===")
        pak_dir = os.path.join(build_dir, "pak_content")
        
        # Tire physics asset — FLAT path (no subfolder), matching base game layout
        # UE resolves /Game/Cars/Parts/Tire/APF_77_Tire -> Content/Cars/Parts/Tire/APF_77_Tire.uasset
        tire_pak_dir = os.path.join(pak_dir, "MotorTown", "Content", "Cars", "Parts", "Tire")
        os.makedirs(tire_pak_dir, exist_ok=True)
        shutil.copy2(tire_asset, os.path.join(tire_pak_dir, f"{tire_name}.uasset"))
        shutil.copy2(tire_uexp, os.path.join(tire_pak_dir, f"{tire_name}.uexp"))
        print(f"  Copied: {tire_name}.uasset + .uexp -> Tire/ (flat)")

        # VehicleParts DataTables
        parts_pak_dir = os.path.join(pak_dir, "MotorTown", "Content", "DataAsset", "VehicleParts")
        os.makedirs(parts_pak_dir, exist_ok=True)

        for dt_name, (asset_path, uexp_path) in parts_outputs.items():
            # VehicleParts -> VehicleParts.uasset, VehicleParts0 -> VehicleParts0.uasset
            target_name = dt_name
            shutil.copy2(asset_path, os.path.join(parts_pak_dir, f"{target_name}.uasset"))
            shutil.copy2(uexp_path, os.path.join(parts_pak_dir, f"{target_name}.uexp"))
            print(f"  Copied: {target_name}.uasset + .uexp -> DataAsset/VehicleParts/")

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

    # Verify output
    if os.path.exists(output_path):
        size = os.path.getsize(output_path)
        print(f"\n=== Success! ===")
        print(f"  Output: {output_path}")
        print(f"  Size: {size:,} bytes")
    else:
        print(f"Error: Output PAK not created: {output_path}")
        sys.exit(1)

if __name__ == "__main__":
    main()
