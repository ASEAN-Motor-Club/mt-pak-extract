#!/usr/bin/env python3
"""
Create a tire mod PAK for MotorTown.

Supports both CAR tires (single physics asset) and BIKE tires (dual physics: front + rear).

Car tire config:
  {"tire_physics": {"name": "...", "template": "BasicTire_45", ...}, "tire_part": {...}}

Bike tire config:
  {"tire_physics": {"front": {"name": "...", "template": "Motorcycle_Front", ...},
                    "rear":  {"name": "...", "template": "Motorcycle_Rear",  ...}},
   "tire_part": {...}}

Usage:
    python3 scripts/create_tirepack.py -c tire_entries.json -o MyTires_P.pak
"""

import argparse
import os

from modbase import ModBuilder, add_common_args, load_mod_config, compute_output_path, resolve_game_version


class TireModBuilder(ModBuilder):
    """Builds tire mod PAKs with custom friction/physics parameters."""

    PARTS0_PAK_PATH = "MotorTown/Content/DataAsset/VehicleParts/VehicleParts0.uasset"

    def __init__(self, config_path, output_path, compat_mods=None,
                 tire_template=None):
        super().__init__("tire mod", config_path, output_path, compat_mods)
        self.tire_template_override = tire_template

        if "tires" in self.config:
            self.tire_entries = self.config["tires"]
        else:
            self.tire_entries = [self.config]

        self.tire_assets = []  # List of (tire_name, uasset_path)
        self.parts_outputs = {}  # {dt_name: uasset_path}

    # ── Helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _is_bike_tire(entry):
        """Detect bike mode: tire_physics has 'front' and 'rear' sub-dicts."""
        tp = entry.get("tire_physics", {})
        return "front" in tp and "rear" in tp

    @staticmethod
    def _get_physics(entry):
        """Return list of (role, physics_dict) for this entry."""
        if TireModBuilder._is_bike_tire(entry):
            return [("front", entry["tire_physics"]["front"]),
                    ("rear",  entry["tire_physics"]["rear"])]
        else:
            return [("single", entry["tire_physics"])]

    def _clone_config(self, physics):
        """Generate --clone-asset config for a single tire physics asset."""
        tire_name = physics["name"]

        patches = []
        for param in ["static_mu", "sliding_mu", "offroad_friction",
                       "spring_x", "spring_y", "damping_x", "damping_y",
                       "max_weight_kg", "rolling_resistance_coeff",
                       "wear_rate", "patch_length_coefficient"]:
            if param in physics:
                pascal = "".join(w.capitalize() for w in param.split("_"))
                patches.append({
                    "path": f"TirePhysicsParams.{pascal}",
                    "op": "set_or_add_float",
                    "value": physics[param],
                })

        return {
            "new_name": tire_name,
            "new_path": f"/Game/Cars/Parts/Tire/{tire_name}",
            "rename_exports": True,
            "rename_imports": True,
            "fname_number": 0,
            "export_patches": [{
                "match_class": "MTTirePhysicsDataAsset",
                "patches": patches,
            }] if patches else [],
        }

    def _parts_row_config(self, entry):
        """Generate --add-rows config for a single tire in VehicleParts."""
        tp = entry["tire_part"]
        is_bike = self._is_bike_tire(entry)

        if is_bike:
            front_name = entry["tire_physics"]["front"]["name"]
            rear_name  = entry["tire_physics"]["rear"]["name"]
            tire_name_for_row = front_name
        else:
            tire_name_for_row = entry["tire_physics"]["name"]

        patches = [
            {"path": "Name", "op": "set_localization_guid",
             "value": tp["display_name"][0]},
            {"path": "Cost", "op": "set", "value": tp["cost"]},
            {"path": "bIsHidden", "op": "set", "value": False},
            {"path": "MassKg", "op": "set", "value": tp.get("mass_kg", 10.0)},
            {"path": "VehicleTypes", "op": "set_enum_array",
             "enum_type": "EMTVehicleType",
             "values": tp["vehicle_types"]},
            {"path": "Tire.TirePhysicsDataAsset", "op": "set_import_ref",
             "class_package": "/Script/MotorTown",
             "class_name": "MTTirePhysicsDataAsset",
             "package_path": f"/Game/Cars/Parts/Tire/{tire_name_for_row}",
             "asset_name": tire_name_for_row},
            {"path": "GameplayTags", "op": "clear_tags"},
        ]

        if is_bike:
            # Set the rear tire physics reference too
            patches.append({
                "path": "Tire.TirePhysicsDataAsset_BikeRear",
                "op": "set_import_ref",
                "class_package": "/Script/MotorTown",
                "class_name": "MTTirePhysicsDataAsset",
                "package_path": f"/Game/Cars/Parts/Tire/{rear_name}",
                "asset_name": rear_name,
            })
        else:
            # Car tires: null out the bike rear reference
            patches.append({
                "path": "Tire.TirePhysicsDataAsset_BikeRear",
                "op": "null_ref",
            })

        if "display_name" in tp:
            patches.append({"path": "Name2", "op": "set_display_name",
                            "value": tp["display_name"]})
            patches.append({"path": "Desciption", "op": "set_description",
                            "value": tp["display_name"][0]})

        if "vehicle_keys" in tp:
            patches.append({"path": "VehicleKeys", "op": "set_name_array",
                            "values": tp["vehicle_keys"]})
        else:
            patches.append({"path": "VehicleKeys", "op": "clear_array"})

        if "level_requirement" in tp:
            patches.append({"path": "LevelRequirementToBuy",
                            "op": "set_name_int_map",
                            "value": tp["level_requirement"]})
        else:
            patches.append({"path": "LevelRequirementToBuy",
                            "op": "clear_map"})

        if "truck_classes" in tp:
            patches.append({"path": "TruckClasses", "op": "set_enum_array",
                            "enum_type": "EMTTruckClass",
                            "values": tp["truck_classes"]})

        if "bIsDualRearWheel" in tp:
            patches.append({"path": "Tire.bIsDualRearWheel", "op": "set",
                            "value": tp["bIsDualRearWheel"]})

        return {
            "template_row_match": {"PartType": "*Tire*"},
            "output_filename": "VehicleParts0",
            "rows": [{
                "row_name": tp["row_name"],
                "row_name_number": 0,
                "patches": patches,
            }],
        }

    # ── Build hooks ────────────────────────────────────────────────────

    def transform_assets(self):
        """Create tire physics assets by cloning and patching templates."""
        for i, entry in enumerate(self.tire_entries, 1):
            for role, physics in self._get_physics(entry):
                tire_name = physics["name"]
                template_name = physics["template"]

                tire_template = (
                    self.tire_template_override or
                    os.path.join(self.repo_root, "out", f"{template_name}.uasset")
                )
                if not os.path.exists(tire_template):
                    self.fail(f"Tire template not found: {tire_template}")

                self.log_step(f"1.{i}.{role}", f"Create tire physics ({tire_name})")
                tire_out = os.path.join(self.build_dir, f"tire_physics_{i}_{role}")
                os.makedirs(tire_out, exist_ok=True)

                config = self._clone_config(physics)
                self.run_generic("--clone-asset", config, tire_template, tire_out,
                                 f"clone-tire-{i}-{role}")

                tire_asset = os.path.join(tire_out, tire_name, f"{tire_name}.uasset")
                if not os.path.exists(tire_asset):
                    self.fail(f"Tire asset not created: {tire_asset}")
                self.tire_assets.append((tire_name, tire_asset))

    def register_in_tables(self):
        """Add tire parts to VehicleParts0 DataTable."""
        base_template = os.path.join(self.repo_root, "out", "VehicleParts0.uasset")
        parts0_template = self.resolve_template_with_compat(
            base_template, self.PARTS0_PAK_PATH,
        )
        if not os.path.exists(parts0_template):
            self.fail(f"VehicleParts0 template not found: {parts0_template}")

        self.log_step(2, f"Add {len(self.tire_entries)} tire(s) to VehicleParts0")

        current_template = parts0_template
        parts_out = None

        for i, entry in enumerate(self.tire_entries, 1):
            parts_out = os.path.join(self.build_dir, f"parts_VehicleParts0_{i}")
            os.makedirs(parts_out, exist_ok=True)

            config = self._parts_row_config(entry)
            self.run_generic("--add-rows", config, current_template, parts_out,
                             f"add-tire-{i}")
            current_template = os.path.join(parts_out, "VehicleParts0.uasset")

        parts_asset = os.path.join(parts_out, "VehicleParts0.uasset")
        if not os.path.exists(parts_asset):
            self.fail(f"VehicleParts0 not created: {parts_asset}")
        self.parts_outputs["VehicleParts0"] = parts_asset

    def assemble_pak(self):
        """Stage tire assets (flat) and VehicleParts DataTables."""
        self.log_step(3, "Assemble PAK directory")

        for tire_name, tire_asset in self.tire_assets:
            self.stage_asset(tire_asset, "Cars/Parts/Tire", name=tire_name)

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
    parser.add_argument("--mod", default=None,
                        help="Mod directory (e.g. mods/police-tyres) to load mod.json from")
    args = parser.parse_args()

    if args.mod:
        mod = load_mod_config(args.mod)
        config_path = mod["configs"][0]
        game_ver = resolve_game_version()
        output_path = compute_output_path(mod, game_ver)
        compat_suffix = mod.get("compat_suffix")
    else:
        config_path = args.config
        output_path = args.output
        compat_suffix = None

    builder = TireModBuilder(
        config_path=config_path,
        output_path=output_path,
        compat_mods=args.compat_mod,
        tire_template=args.tire_template,
    )
    builder.build()


if __name__ == "__main__":
    main()
