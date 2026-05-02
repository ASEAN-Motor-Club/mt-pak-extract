#!/usr/bin/env python3
"""
Create a fuel tank mod PAK for MotorTown.

Adds custom FuelTank-type rows to VehicleParts and patches Vehicles DataTable
to equip police cars with auxiliary fuel tanks.

Usage:
    python3 scripts/create_fueltank_mod.py \
        --config fueltank_config.json \
        --output MyFuelTankMod_P.pak

    # Compatible with another mod
    python3 scripts/create_fueltank_mod.py \
        --config fueltank_config.json \
        --output MyFuelTankMod_P.pak \
        --compat-mod MoreTuning_P.pak
"""

import argparse
import os

from modbase import ModBuilder, add_common_args, load_mod_config, compute_output_path, resolve_game_version


class FuelTankModBuilder(ModBuilder):
    """Builds fuel tank mod PAKs with custom FuelTank parts for police cars."""

    PARTS_PAK_PATH = "MotorTown/Content/DataAsset/VehicleParts/VehicleParts.uasset"
    VEHICLES_PAK_PATH = "MotorTown/Content/DataAsset/Vehicles/Vehicles.uasset"

    def __init__(self, config_path, output_path, compat_mods=None):
        super().__init__("fuel tank mod", config_path, output_path, compat_mods)

        self.fueltank_entries = self.config.get("fueltanks", [])
        self.vehicle_patches = self.config.get("vehicle_patches", [])
        self.parts_outputs = {}
        self.vehicles_output = None

    def _parts_row_config(self, entry):
        """Generate --add-rows config for a single fuel tank in VehicleParts."""
        patches = [
            {"path": "Name", "op": "set_localization_guid",
             "value": entry["display_name"][0]},
            {"path": "Cost", "op": "set", "value": entry["cost"]},
            {"path": "bIsHidden", "op": "set", "value": False},
            {"path": "MassKg", "op": "set", "value": entry.get("mass_kg", 20.0)},
            {"path": "VehicleTypes", "op": "set_enum_array",
             "enum_type": "EMTVehicleType",
             "values": entry["vehicle_types"]},
            {"path": "FuelTank.FuelLiter", "op": "set_or_add_float",
             "value": entry["fuel_liters"]},
            {"path": "GameplayTags", "op": "clear_tags"},
        ]

        if "display_name" in entry:
            patches.append({"path": "Name2", "op": "set_display_name",
                            "value": entry["display_name"]})
            patches.append({"path": "Desciption", "op": "set_description",
                            "value": entry["display_name"][0]})

        if "vehicle_keys" in entry:
            patches.append({"path": "VehicleKeys", "op": "set_name_array",
                            "values": entry["vehicle_keys"]})

        if "level_requirement" in entry:
            patches.append({"path": "LevelRequirementToBuy",
                            "op": "set_name_int_map",
                            "value": entry["level_requirement"]})

        return {
            "template_row_match": {"RowName": "FuelTank_01"},
            "output_filename": "VehicleParts",
            "rows": [{
                "row_name": entry["row_name"],
                "row_name_number": 0,
                "patches": patches,
            }],
        }

    def _vehicles_patch_config(self):
        """Generate --patch-rows config for all target vehicles."""
        patches = []
        for vp in self.vehicle_patches:
            row_patches = [
                {
                    "path": "Parts",
                    "op": "add_map_entry",
                    "key": "EMTVehiclePartSlot::Utility0",
                    "value": vp["default_tank"],
                },
            ]
            if vp.get("add_fuel_pump", False):
                row_patches.append({
                    "path": "bHasFuelPump",
                    "op": "set",
                    "value": True,
                })
            patches.append({
                "row_name": vp["vehicle_id"],
                "patches": row_patches,
            })

        return {
            "output_filename": "Vehicles",
            "patches": patches,
        }

    def transform_assets(self):
        """No separate assets needed — FuelTank tuning is inline in VehicleParts."""
        pass

    def register_in_tables(self):
        """Add fuel tank parts to VehicleParts and patch Vehicles DataTable."""
        # ── Step 1: Add fuel tank rows to VehicleParts ──
        base_parts_template = os.path.join(self.repo_root, "out", "VehicleParts.uasset")
        parts_template = self.resolve_template_with_compat(
            base_parts_template, self.PARTS_PAK_PATH,
        )
        if not os.path.exists(parts_template):
            self.fail(f"VehicleParts template not found: {parts_template}")

        self.log_step(1, f"Add {len(self.fueltank_entries)} fuel tank(s) to VehicleParts")

        current_template = parts_template
        parts_out = None

        for i, entry in enumerate(self.fueltank_entries, 1):
            row_name = entry["row_name"]
            parts_out = os.path.join(self.build_dir, f"parts_VehicleParts_{i}")
            os.makedirs(parts_out, exist_ok=True)

            config = self._parts_row_config(entry)
            self.run_generic("--add-rows", config, current_template, parts_out,
                             f"add-fueltank-{i}")
            current_template = os.path.join(parts_out, "VehicleParts.uasset")

        parts_asset = os.path.join(parts_out, "VehicleParts.uasset")
        if not os.path.exists(parts_asset):
            self.fail(f"VehicleParts not created: {parts_asset}")
        self.parts_outputs["VehicleParts"] = parts_asset

        # ── Step 2: Patch Vehicles DataTable ──
        base_vehicles_template = os.path.join(self.repo_root, "out", "Vehicles.uasset")
        vehicles_template = self.resolve_template_with_compat(
            base_vehicles_template, self.VEHICLES_PAK_PATH,
        )
        if not os.path.exists(vehicles_template):
            self.fail(f"Vehicles template not found: {vehicles_template}")

        self.log_step(2, f"Patch {len(self.vehicle_patches)} vehicle(s) in Vehicles")

        vehicles_out = os.path.join(self.build_dir, "patched_vehicles")
        os.makedirs(vehicles_out, exist_ok=True)

        vehicles_config = self._vehicles_patch_config()
        self.run_generic("--patch-rows", vehicles_config, vehicles_template, vehicles_out,
                         "patch-vehicles")

        vehicles_asset = os.path.join(vehicles_out, "Vehicles.uasset")
        if not os.path.exists(vehicles_asset):
            self.fail(f"Vehicles not patched: {vehicles_asset}")
        self.vehicles_output = vehicles_asset

    def assemble_pak(self):
        """Stage VehicleParts and Vehicles DataTables."""
        self.log_step(3, "Assemble PAK directory")

        for dt_name, asset_path in self.parts_outputs.items():
            self.stage_datatable(asset_path, dt_name, "DataAsset/VehicleParts")

        if self.vehicles_output:
            self.stage_datatable(self.vehicles_output, "Vehicles", "DataAsset/Vehicles")

    def print_summary(self):
        tanks = ", ".join(e["row_name"] for e in self.fueltank_entries)
        vehicles = ", ".join(v["vehicle_id"] for v in self.vehicle_patches)
        self.log(f"  Fuel tanks: {tanks}")
        self.log(f"  Vehicles patched: {vehicles}")


def main():
    parser = argparse.ArgumentParser(
        description="Create MotorTown fuel tank mod PAK",
        epilog="Example: python3 scripts/create_fueltank_mod.py -c fueltank_config.json "
               "-o PD_FuelTanks_P.pak --compat-mod MoreTuning_P.pak",
    )
    add_common_args(parser)
    parser.add_argument("--mod", default=None,
                        help="Mod directory (e.g. mods/police-fueltank) to load mod.json from")
    args = parser.parse_args()

    if args.mod:
        mod = load_mod_config(args.mod)
        config_path = mod["configs"][0]
        game_ver = resolve_game_version()
        output_path = compute_output_path(mod, game_ver)
    else:
        config_path = args.config
        output_path = args.output

    builder = FuelTankModBuilder(
        config_path=config_path,
        output_path=output_path,
        compat_mods=args.compat_mod,
    )
    builder.build()


if __name__ == "__main__":
    main()
