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
import os

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

        self.tire_assets = []  # List of (tire_name, uasset_path)
        self.parts_outputs = {}  # {dt_name: uasset_path}

    # ── Config generation ──────────────────────────────────────────────

    def _clone_config(self, entry):
        """Generate --clone-asset config for a single tire physics asset."""
        tp = entry["tire_physics"]
        tire_name = tp["name"]

        patches = []
        for param in ["static_mu", "sliding_mu", "offroad_friction",
                       "spring_x", "spring_y", "damping_x", "damping_y"]:
            if param in tp:
                # Map snake_case to PascalCase
                pascal = "".join(w.capitalize() for w in param.split("_"))
                patches.append({
                    "path": f"TirePhysicsParams.{pascal}",
                    "op": "set_or_add_float",
                    "value": tp[param],
                })

        return {
            "new_name": tire_name,
            "new_path": f"/Game/Cars/Parts/Tire/{tire_name}",
            "rename_exports": True,
            "rename_imports": True,
            "patch_namemap_0": True,
            "fname_number": 0,
            "export_patches": [{
                "match_class": "MTTirePhysicsDataAsset",
                "patches": patches,
            }] if patches else [],
        }

    def _parts_row_config(self, entry):
        """Generate --add-rows config for a single tire in VehicleParts."""
        tp = entry["tire_part"]
        tire_name = entry["tire_physics"]["name"]

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
             "package_path": f"/Game/Cars/Parts/Tire/{tire_name}",
             "asset_name": tire_name},
            {"path": "Tire.TirePhysicsDataAsset_BikeRear", "op": "null_ref"},
            {"path": "GameplayTags", "op": "clear_tags"},
        ]

        if "display_name" in tp:
            patches.append({"path": "Name2", "op": "set_display_name",
                            "value": tp["display_name"]})
            patches.append({"path": "Desciption", "op": "set_description",
                            "value": tp["display_name"][0]})

        if "vehicle_keys" in tp:
            patches.append({"path": "VehicleKeys", "op": "set_name_array",
                            "values": tp["vehicle_keys"]})

        if "level_requirement" in tp:
            patches.append({"path": "LevelRequirementToBuy",
                            "op": "set_name_int_map",
                            "value": tp["level_requirement"]})

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
            tire_physics = entry["tire_physics"]
            tire_name = tire_physics["name"]
            template_name = tire_physics["template"]

            tire_template = (
                self.tire_template_override or
                os.path.join(self.repo_root, "out", f"{template_name}.uasset")
            )
            if not os.path.exists(tire_template):
                self.fail(f"Tire template not found: {tire_template}")

            self.log_step(f"1.{i}", f"Create tire physics asset ({tire_name})")
            tire_out = os.path.join(self.build_dir, f"tire_physics_{i}")
            os.makedirs(tire_out, exist_ok=True)

            config = self._clone_config(entry)
            self.run_generic("--clone-asset", config, tire_template, tire_out,
                             f"clone-tire-{i}")

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

        # Chain additions: each tire is added sequentially
        current_template = parts0_template
        parts_out = None

        for i, entry in enumerate(self.tire_entries, 1):
            tire_name = entry["tire_physics"]["name"]
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
