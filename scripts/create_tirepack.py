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
import sys

from modbase import ModBuilder, add_common_args


class TireModBuilder(ModBuilder):
    """Builds tire mod PAKs with custom friction/physics parameters."""

    PARTS0_PAK_PATH = "MotorTown/Content/DataAsset/VehicleParts/VehicleParts0.uasset"

    def __init__(self, config_path, output_path, compat_mods=None,
                 tire_template=None):
        super().__init__("tire mod", config_path, output_path, compat_mods)
        self.tire_template_override = tire_template

        # Normalize config to list of tire entries
        if "tires" in self.config:
            self.tire_entries = self.config["tires"]
        else:
            self.tire_entries = [self.config]  # Single-tire backward compat

        self.tire_assets = []  # List of (tire_name, uasset_path, uexp_path)
        self.parts_outputs = {}  # {dt_name: (uasset_path, uexp_path)}

    def transform_assets(self):
        """Create tire physics assets by cloning and patching templates."""
        for i, entry in enumerate(self.tire_entries, 1):
            tire_physics = entry["tire_physics"]
            tire_name = tire_physics["name"]
            template_name = tire_physics["template"]

            tire_template = (
                self.tire_template_override or
                os.path.join(self.repo_root, "out", f"{template_name}.uasset")
            )
            if not os.path.exists(tire_template):
                self.fail(f"Tire template not found: {tire_template}")

            # Write single-entry config for C# tool
            single_config = os.path.join(self.build_dir, f"tire_{i}.json")
            with open(single_config, 'w') as f:
                json.dump(entry, f)

            self.log_step(f"1.{i}", f"Create tire physics asset ({tire_name})")
            tire_out = os.path.join(self.build_dir, f"tire_physics_{i}")
            os.makedirs(tire_out, exist_ok=True)

            self.run_dotnet(
                ["--patch-tire", single_config, tire_template, tire_out],
                f"--patch-tire {tire_name}",
            )

            tire_asset = os.path.join(tire_out, tire_name, f"{tire_name}.uasset")
            tire_uexp = os.path.join(tire_out, tire_name, f"{tire_name}.uexp")
            if not os.path.exists(tire_asset):
                self.fail(f"Tire asset not created: {tire_asset}")
            self.tire_assets.append((tire_name, tire_asset, tire_uexp))

    def register_in_tables(self):
        """Add tire parts to VehicleParts0 DataTable."""
        # Resolve VehicleParts0 template (base game or compat mod)
        base_template = os.path.join(self.repo_root, "out", "VehicleParts0.uasset")
        parts0_template = self.resolve_template_with_compat(
            base_template, self.PARTS0_PAK_PATH,
        )
        if not os.path.exists(parts0_template):
            self.fail(f"VehicleParts0 template not found: {parts0_template}")

        parts_templates = {"VehicleParts0": parts0_template}

        for dt_name, dt_template in parts_templates.items():
            self.log_step(2, f"Add {len(self.tire_entries)} tire(s) to {dt_name}")

            # Chain additions: each tire is added sequentially to the same DataTable
            current_template = dt_template
            parts_out = None

            for i, entry in enumerate(self.tire_entries, 1):
                tire_name = entry["tire_physics"]["name"]
                single_config = os.path.join(self.build_dir, f"tire_{i}.json")

                parts_out = os.path.join(self.build_dir, f"parts_{dt_name}_{i}")
                os.makedirs(parts_out, exist_ok=True)

                self.run_dotnet(
                    ["--add-tire-parts", single_config, current_template, parts_out],
                    f"--add-tire-parts {tire_name} to {dt_name}",
                )
                # Chain: use output as input for the next tire
                current_template = os.path.join(parts_out, f"{dt_name}.uasset")

            # Final output is the last iteration
            parts_asset = os.path.join(parts_out, f"{dt_name}.uasset")
            if not os.path.exists(parts_asset):
                self.fail(f"{dt_name} not created: {parts_asset}")
            self.parts_outputs[dt_name] = parts_asset

    def assemble_pak(self):
        """Stage tire assets (flat) and VehicleParts DataTables."""
        self.log_step(3, "Assemble PAK directory")

        # Tire physics assets — FLAT path (no subfolder!)
        for tire_name, tire_asset, _tire_uexp in self.tire_assets:
            self.stage_asset(tire_asset, "Cars/Parts/Tire", name=tire_name)

        # VehicleParts DataTables
        for dt_name, asset_path in self.parts_outputs.items():
            self.stage_datatable(asset_path, dt_name, "DataAsset/VehicleParts")

    def print_summary(self):
        self.log(f"  Tires: {', '.join(t[0] for t in self.tire_assets)}")


def main():
    parser = argparse.ArgumentParser(
        description="Create MotorTown tire mod PAK",
        epilog="Example: python3 scripts/create_tirepack.py -c tire_entries.json "
               "-o AMCTires_P.pak --compat-mod MoreTuning_P.pak",
    )
    add_common_args(parser)
    parser.add_argument("--tire-template", default=None,
                        help="Override tire physics template .uasset")
    args = parser.parse_args()

    builder = TireModBuilder(
        config_path=args.config,
        output_path=args.output,
        compat_mods=args.compat_mod,
        tire_template=args.tire_template,
    )
    builder.build()


if __name__ == "__main__":
    main()
