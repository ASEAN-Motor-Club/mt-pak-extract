#!/usr/bin/env python3
"""
Create a vehicle mod PAK for MotorTown.

Patches vehicle rows in DataTables and/or blueprint exports for AWD conversion.

Usage:
    python3 scripts/create_vehicle_mod.py -c vehicle_patch.json -o MyVehicleMod_P.pak
"""

import argparse
import os
import sys

from modbase import ModBuilder, add_common_args, load_mod_config, compute_output_path, resolve_game_version


class VehicleModBuilder(ModBuilder):
    """Builds vehicle mod PAKs by patching Vehicles DataTable rows and/or blueprints."""

    def __init__(self, config_path, output_path, compat_mods=None):
        super().__init__("vehicle mod", config_path, output_path, compat_mods)

    def transform_assets(self):
        pass  # No new assets to create

    def register_in_tables(self):
        """Patch vehicle rows in the specified DataTable and/or blueprint."""
        vehicle_id = self.config["vehicle_id"]
        datatable_file = self.config.get("datatable_file")
        dt_patches = self.config.get("patches", [])
        blueprint_file = self.config.get("blueprint_file")
        blueprint_patches = self.config.get("blueprint_patches")

        # Patch DataTable if configured
        if datatable_file and dt_patches:
            base_template = os.path.join(self.repo_root, "out", f"{datatable_file}.uasset")
            if not os.path.exists(base_template):
                self.fail(f"DataTable template not found: {base_template}")

            self.log_step(1, f"Patch {vehicle_id} in {datatable_file}")

            patch_config = {
                "output_filename": datatable_file,
                "patches": [
                    {
                        "row_name": vehicle_id,
                        "patches": dt_patches,
                    }
                ],
            }

            patch_out = os.path.join(self.build_dir, "patched_vehicles")
            os.makedirs(patch_out, exist_ok=True)

            self.run_generic("--patch-rows", patch_config, base_template, patch_out,
                             f"patch-{vehicle_id}")

            patched_asset = os.path.join(patch_out, f"{datatable_file}.uasset")
            if not os.path.exists(patched_asset):
                self.fail(f"Patched DataTable not created: {patched_asset}")

            self.patched_datatable = patched_asset
            self.datatable_name = datatable_file
        else:
            self.patched_datatable = None
            self.datatable_name = None

        # Patch blueprint if configured
        if blueprint_file and blueprint_patches:
            self.log_step(2 if self.patched_datatable else 1, f"Patch blueprint {blueprint_file}")

            base_blueprint = os.path.join(self.repo_root, "out", f"{blueprint_file}.uasset")
            if not os.path.exists(base_blueprint):
                self.fail(f"Blueprint template not found: {base_blueprint}")

            bp_out = os.path.join(self.build_dir, "patched_blueprints")
            os.makedirs(bp_out, exist_ok=True)

            bp_config = {
                "output_filename": blueprint_file,
                "exports": blueprint_patches,
            }

            self.run_generic("--patch-named-exports", bp_config, base_blueprint, bp_out,
                             f"patch-bp-{vehicle_id}")

            patched_bp = os.path.join(bp_out, f"{blueprint_file}.uasset")
            if not os.path.exists(patched_bp):
                self.fail(f"Patched blueprint not created: {patched_bp}")

            self.patched_blueprint = patched_bp
            self.blueprint_name = blueprint_file
        else:
            self.patched_blueprint = None
            self.blueprint_name = None

    def assemble_pak(self):
        """Stage the patched DataTable and/or blueprint."""
        self.log_step(3 if (self.patched_datatable and self.patched_blueprint) else 2, "Assemble PAK directory")

        if self.patched_datatable:
            self.stage_datatable(self.patched_datatable, self.datatable_name,
                                 "DataAsset/Vehicles")

        if self.patched_blueprint:
            # Blueprints go in Cars/Models/<Folder>/
            # Folder is usually the base model name (e.g. "Zydro" for "Zydro_Police")
            blueprint_folder = self.config.get("blueprint_folder", self.blueprint_name)
            self.stage_blueprint(self.patched_blueprint, self.blueprint_name,
                                 f"Cars/Models/{blueprint_folder}")

    def print_summary(self):
        if self.patched_datatable:
            self.log(f"  Patched DataTable: {self.datatable_name}")
        if self.patched_blueprint:
            self.log(f"  Patched blueprint: {self.blueprint_name}")


def main():
    parser = argparse.ArgumentParser(
        description="Create MotorTown vehicle mod PAK",
        epilog="Example: python3 scripts/create_vehicle_mod.py -c vehicle_patch.json "
               "-o MyVehicleMod_P.pak",
    )
    add_common_args(parser)
    parser.add_argument("--mod", default=None,
                        help="Mod directory (e.g. mods/zydro-police-awd) to load mod.json from")
    args = parser.parse_args()

    if args.mod:
        mod = load_mod_config(args.mod)
        config_path = mod["configs"][0]
        game_ver = resolve_game_version()
        output_path = compute_output_path(mod, game_ver)
    else:
        config_path = args.config
        output_path = args.output

    builder = VehicleModBuilder(
        config_path=config_path,
        output_path=output_path,
        compat_mods=args.compat_mod,
    )
    builder.build()


if __name__ == "__main__":
    main()
