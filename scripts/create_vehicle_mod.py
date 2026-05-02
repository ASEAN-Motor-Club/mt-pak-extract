#!/usr/bin/env python3
"""
Create a vehicle mod PAK for MotorTown.

Patches vehicle rows in DataTables and/or blueprint exports.
Supports single vehicle (legacy) or multiple vehicles per mod.

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
        self.patched_datatables = {}   # datatable_name -> path
        self.patched_blueprints = {}   # blueprint_name -> (path, folder)

    def transform_assets(self):
        pass  # No new assets to create

    def _get_vehicles(self):
        """Return list of vehicle configs to process."""
        if "vehicles" in self.config:
            return self.config["vehicles"]
        # Legacy single-vehicle format
        return [self.config]

    def register_in_tables(self):
        """Patch vehicle rows in DataTables and/or blueprints."""
        vehicles = self._get_vehicles()

        # Group DataTable patches by datatable file
        dt_groups = {}
        for v in vehicles:
            dt_file = v.get("datatable_file")
            if not dt_file:
                continue
            if dt_file not in dt_groups:
                dt_groups[dt_file] = []
            dt_groups[dt_file].append(v)

        # Patch each DataTable once with all rows
        for dt_file, vlist in dt_groups.items():
            base_template = os.path.join(self.repo_root, "out", f"{dt_file}.uasset")
            if not os.path.exists(base_template):
                self.fail(f"DataTable template not found: {base_template}")

            row_names = ", ".join(v["vehicle_id"] for v in vlist)
            self.log_step(1, f"Patch {len(vlist)} rows in {dt_file} ({row_names})")

            patch_config = {
                "output_filename": dt_file,
                "patches": [
                    {
                        "row_name": v["vehicle_id"],
                        "patches": v.get("patches", []),
                    }
                    for v in vlist
                ],
            }

            patch_out = os.path.join(self.build_dir, "patched_vehicles")
            os.makedirs(patch_out, exist_ok=True)

            self.run_generic("--patch-rows", patch_config, base_template, patch_out,
                             f"patch-{dt_file}")

            patched_asset = os.path.join(patch_out, f"{dt_file}.uasset")
            if not os.path.exists(patched_asset):
                self.fail(f"Patched DataTable not created: {patched_asset}")

            self.patched_datatables[dt_file] = patched_asset

        # Patch each blueprint
        step = 2 if self.patched_datatables else 1
        for v in vehicles:
            bp_file = v.get("blueprint_file")
            bp_patches = v.get("blueprint_patches")
            if not bp_file or not bp_patches:
                continue

            vehicle_id = v["vehicle_id"]
            self.log_step(step, f"Patch blueprint {bp_file} ({vehicle_id})")
            step += 1

            base_blueprint = os.path.join(self.repo_root, "out", f"{bp_file}.uasset")
            if not os.path.exists(base_blueprint):
                self.fail(f"Blueprint template not found: {base_blueprint}")

            bp_out = os.path.join(self.build_dir, "patched_blueprints")
            os.makedirs(bp_out, exist_ok=True)

            bp_config = {
                "output_filename": bp_file,
                "exports": bp_patches,
            }

            self.run_generic("--patch-named-exports", bp_config, base_blueprint, bp_out,
                             f"patch-bp-{vehicle_id}")

            patched_bp = os.path.join(bp_out, f"{bp_file}.uasset")
            if not os.path.exists(patched_bp):
                self.fail(f"Patched blueprint not created: {patched_bp}")

            bp_folder = v.get("blueprint_folder", bp_file)
            self.patched_blueprints[bp_file] = (patched_bp, bp_folder)

    def assemble_pak(self):
        """Stage all patched DataTables and blueprints."""
        total = len(self.patched_datatables) + len(self.patched_blueprints)
        self.log_step(total + 1, "Assemble PAK directory")

        for dt_name, dt_path in self.patched_datatables.items():
            self.stage_datatable(dt_path, dt_name, "DataAsset/Vehicles")

        for bp_name, (bp_path, bp_folder) in self.patched_blueprints.items():
            self.stage_blueprint(bp_path, bp_name, f"Cars/Models/{bp_folder}")

    def print_summary(self):
        for dt_name in self.patched_datatables:
            self.log(f"  Patched DataTable: {dt_name}")
        for bp_name in self.patched_blueprints:
            self.log(f"  Patched blueprint: {bp_name}")


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
