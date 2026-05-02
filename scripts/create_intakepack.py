#!/usr/bin/env python3
"""
Create an intake mod PAK for MotorTown.

Adds custom Intake-type rows to VehicleParts0 with tuned Slope,
BaseRPMRatio, and IntakeSpeedEfficencyMultiplier values.
No separate physics asset needed — all tuning is inline in the row.

Usage:
    python3 scripts/create_intakepack.py \\
        --config intake_entries.json \\
        --output MyIntakeMod_P.pak

    # Compatible with another mod
    python3 scripts/create_intakepack.py \\
        --config intake_entries.json \\
        --output MyIntakeMod_P.pak \\
        --compat-mod MoreTuning_P.pak
"""

import argparse
import os

from modbase import ModBuilder, add_common_args, load_mod_config, compute_output_path, resolve_game_version


class IntakeModBuilder(ModBuilder):
    """Builds intake mod PAKs with custom Intake sub-struct tuning."""

    PARTS0_PAK_PATH = "MotorTown/Content/DataAsset/VehicleParts/VehicleParts0.uasset"

    def __init__(self, config_path, output_path, compat_mods=None):
        super().__init__("intake mod", config_path, output_path, compat_mods)

        self.intake_entries = self.config.get("intakes", [])
        self.parts_outputs = {}

    def _parts_row_config(self, entry):
        """Generate --add-rows config for a single intake in VehicleParts0."""
        patches = [
            {"path": "Name", "op": "set_localization_guid",
             "value": entry["display_name"][0]},
            {"path": "Cost", "op": "set", "value": entry["cost"]},
            {"path": "bIsHidden", "op": "set", "value": False},
            {"path": "MassKg", "op": "set", "value": entry.get("mass_kg", 5.0)},
            {"path": "VehicleTypes", "op": "set_enum_array",
             "enum_type": "EMTVehicleType",
             "values": entry["vehicle_types"]},
            {"path": "Intake.Slope", "op": "set_or_add_float",
             "value": entry["intake"]["Slope"]},
            {"path": "Intake.BaseRPMRatio", "op": "set_or_add_float",
             "value": entry["intake"]["BaseRPMRatio"]},
            {"path": "Intake.IntakeSpeedEfficencyMultiplier", "op": "set_or_add_float",
             "value": entry["intake"]["IntakeSpeedEfficencyMultiplier"]},
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
            "template_row_match": {"PartType": "*Intake*"},
            "output_filename": "VehicleParts0",
            "rows": [{
                "row_name": entry["row_name"],
                "row_name_number": 0,
                "patches": patches,
            }],
        }

    def transform_assets(self):
        """No separate assets needed — Intake tuning is inline in VehicleParts."""
        pass

    def register_in_tables(self):
        """Add intake parts to VehicleParts0 DataTable."""
        base_template = os.path.join(self.repo_root, "out", "VehicleParts0.uasset")
        parts0_template = self.resolve_template_with_compat(
            base_template, self.PARTS0_PAK_PATH,
        )
        if not os.path.exists(parts0_template):
            self.fail(f"VehicleParts0 template not found: {parts0_template}")

        self.log_step(1, f"Add {len(self.intake_entries)} intake(s) to VehicleParts0")

        current_template = parts0_template
        parts_out = None

        for i, entry in enumerate(self.intake_entries, 1):
            row_name = entry["row_name"]
            parts_out = os.path.join(self.build_dir, f"parts_VehicleParts0_{i}")
            os.makedirs(parts_out, exist_ok=True)

            config = self._parts_row_config(entry)
            self.run_generic("--add-rows", config, current_template, parts_out,
                             f"add-intake-{i}")
            current_template = os.path.join(parts_out, "VehicleParts0.uasset")

        parts_asset = os.path.join(parts_out, "VehicleParts0.uasset")
        if not os.path.exists(parts_asset):
            self.fail(f"VehicleParts0 not created: {parts_asset}")
        self.parts_outputs["VehicleParts0"] = parts_asset

    def assemble_pak(self):
        """Stage VehicleParts DataTable only."""
        self.log_step(2, "Assemble PAK directory")

        for dt_name, asset_path in self.parts_outputs.items():
            self.stage_datatable(asset_path, dt_name, "DataAsset/VehicleParts")

    def print_summary(self):
        self.log(f"  Intakes: {', '.join(e['row_name'] for e in self.intake_entries)}")


def main():
    parser = argparse.ArgumentParser(
        description="Create MotorTown intake mod PAK",
        epilog="Example: python3 scripts/create_intakepack.py -c intake_entries.json "
               "-o PD_SC_P.pak --compat-mod MoreTuning_P.pak",
    )
    add_common_args(parser)
    parser.add_argument("--mod", default=None,
                        help="Mod directory (e.g. mods/police-sc) to load mod.json from")
    args = parser.parse_args()

    if args.mod:
        mod = load_mod_config(args.mod)
        config_path = mod["configs"][0]
        game_ver = resolve_game_version()
        output_path = compute_output_path(mod, game_ver)
    else:
        config_path = args.config
        output_path = args.output

    builder = IntakeModBuilder(
        config_path=config_path,
        output_path=output_path,
        compat_mods=args.compat_mod,
    )
    builder.build()


if __name__ == "__main__":
    main()
