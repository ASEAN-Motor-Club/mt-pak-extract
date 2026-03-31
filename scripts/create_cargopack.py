#!/usr/bin/env python3
"""
Create a MotorTown cargo mod PAK.

Pipeline:
  1. Patch SmallBox.uasset into new cargo blueprints (--clone-asset)
  2. Add cargo rows to Cargos.uasset (--add-rows)
  3. Add production config recipes to delivery points (--patch-cdo-arrays)
  4. Assemble PAK directory structure
  5. Build mod PAK via mod_pack

Usage:
  python3 scripts/create_cargopack.py \\
    --config cargo_entries.json \\
    --recipes recipe_entries.json \\
    --output CarPartsImport_P.pak
"""

import argparse
import json
import os

from modbase import ModBuilder, add_common_args


class CargoModBuilder(ModBuilder):
    """Builds cargo mod PAKs with new cargo types and delivery routes."""

    CARGOS_PAK_PATH = "MotorTown/Content/DataAsset/Cargos.uasset"

    def __init__(self, config_path, output_path, recipes_path,
                 compat_mods=None, cargos_template=None,
                 blueprint_template=None):
        super().__init__("cargo mod", config_path, output_path, compat_mods)
        self.recipes_path = os.path.abspath(recipes_path)
        self.cargos_template = cargos_template or os.path.join(
            self.repo_root, "out", "Cargos.uasset")
        self.blueprint_template = blueprint_template or os.path.join(
            self.repo_root, "out", "SmallBox.uasset")

        if not os.path.exists(self.recipes_path):
            self.fail(f"Recipes not found: {self.recipes_path}")

        with open(self.recipes_path) as f:
            self.recipe_config = json.load(f)

        self.cargo_names = [e["blueprint_name"] for e in self.config["entries"]]

        # Outputs
        self.cargos_output_dir: str | None = None
        self.blueprints_output_dir: str | None = None
        self.recipes_output_dir: str | None = None

        self.log(f"\n=== Cargo Mod ===")
        self.log(f"  Cargos: {', '.join(self.cargo_names)}")
        self.log(f"  Sources: {[s['delivery_point'] for s in self.recipe_config.get('sources', [])]}")
        self.log(f"  Sinks: {[s['delivery_point'] for s in self.recipe_config.get('sinks', [])]}")

    # ── Config generation ──────────────────────────────────────────────

    def _blueprint_clone_config(self):
        """Generate --clone-asset config for all cargo blueprints."""
        assets = []
        for entry in self.config["entries"]:
            bp_name = entry["blueprint_name"]
            mesh_path = entry["mesh_path"]
            mass_kg = entry["mass_kg"]

            assets.append({
                "new_name": bp_name,
                "new_path": f"/Game/Objects/Mission/Delivery/{bp_name}",
                "rename_exports": True,
                "rename_imports": True,
                "import_replacements": [{
                    "match_class": "StaticMesh",
                    "new_package_path": mesh_path,
                    "new_name": mesh_path.split("/")[-1],
                }],
                "export_patches": [{
                    "match_class": "StaticMeshComponent",
                    "patches": [
                        {"path": "BodyInstance.MassInKgOverride",
                         "op": "set", "value": mass_kg},
                    ],
                }],
            })

        return {"assets": assets}

    def _cargo_rows_config(self):
        """Generate --add-rows config for Cargos DataTable."""
        rows = []
        for entry in self.config["entries"]:
            patches = [
                {"path": "bDepcreated", "op": "set", "value": False},
                {"path": "Name", "op": "set_localization_guid"},
                {"path": "Name2", "op": "set_display_name",
                 "value": entry["display_name"]},
                {"path": "CargoType", "op": "set_enum",
                 "value": entry["cargo_type"]},
                {"path": "WeightRange", "op": "set_vector2d",
                 "x": entry["weight_min"], "y": entry["weight_max"]},
                {"path": "VolumeSize", "op": "set", "value": 1},
                {"path": "SpawnProbability", "op": "set",
                 "value": entry["spawn_probability"]},
                {"path": "NumCargoMin", "op": "set",
                 "value": entry.get("num_cargo_min", 0)},
                {"path": "NumCargoMax", "op": "set",
                 "value": entry.get("num_cargo_max", 1)},
                {"path": "PaymentPer1Km", "op": "set",
                 "value": entry["payment_per_km"]},
                {"path": "PaymentPer1KmMultiplierByMaxWeight",
                 "op": "set", "value": 2.0},
                {"path": "PaymentSqrtRatio", "op": "set", "value": 1.0},
                {"path": "ActorClass", "op": "set_import_ref",
                 "class_package": "/Script/Engine",
                 "class_name": "BlueprintGeneratedClass",
                 "package_path": f"/Game/Objects/Mission/Delivery/{entry['blueprint_name']}",
                 "asset_name": f"{entry['blueprint_name']}_C"},
                {"path": "GameplayTags", "op": "clear_tags"},
                {"path": "bAllowStacking", "op": "set",
                 "value": entry.get("allow_stacking", False)},
                {"path": "bUseDamage", "op": "set", "value": False},
                {"path": "Fragile", "op": "set", "value": 0},
                {"path": "CargoFlags", "op": "set",
                 "value": entry.get("cargo_flags", 11)},
                {"path": "DumpCargoSurfaceMesh", "op": "null_ref"},
                {"path": "DumpCargoSurfaceMaterial", "op": "null_ref"},
                {"path": "DumpPileActorClass", "op": "null_ref"},
                {"path": "bTimer", "op": "set", "value": False},
                {"path": "bHoldingOffsetUsingItemBounds", "op": "set",
                 "value": False},
                {"path": "Colors", "op": "clear_array"},
            ]

            if "cargo_space_types" in entry:
                patches.append({
                    "path": "CargoSpaceTypes", "op": "set_enum_array",
                    "enum_type": "EMTCargoSpaceType",
                    "values": entry["cargo_space_types"],
                })

            rows.append({
                "row_name": entry["row_name"],
                "patches": patches,
            })

        return {"rows": rows}

    def _recipe_cdo_config(self, dp_name, recipes, storage_entries):
        """Generate --patch-cdo-arrays config for a delivery point."""
        arrays = []

        if recipes:
            entries = []
            for mode, recipe in recipes:
                patches = self._recipe_patches(mode, recipe)
                entries.append({"patches": patches})

            arrays.append({
                "property_name": "ProductionConfigs",
                "entries": entries,
            })

        if storage_entries:
            entries = []
            for entry in storage_entries:
                patches = [
                    {"path": "CargoKey", "op": "set_name",
                     "value": entry["cargo_key"]},
                    {"path": "MaxStorage", "op": "set",
                     "value": entry.get("max_storage", 10)},
                ]
                # Clear random range
                patches.append({
                    "path": "MaxStorageRandomRange.X", "op": "set", "value": 0})
                patches.append({
                    "path": "MaxStorageRandomRange.Y", "op": "set", "value": 0})
                entries.append({"patches": patches})

            arrays.append({
                "property_name": "StorageConfigs",
                "entries": entries,
            })

        return {
            "output_filename": dp_name,
            "arrays": arrays,
        }

    def _recipe_patches(self, mode, recipe):
        """Generate patches for a single production config entry."""
        if mode == "transform":
            input_map = {recipe["input_cargo"]: recipe.get("input_count", 1)}
            output_map = {recipe["output_cargo"]: recipe.get("output_count", 1)}
            production_time = recipe["production_time"]
            hidden = recipe.get("hidden", False)
        elif mode == "source":
            input_map = {}
            output_map = {recipe["cargo"]: 1}
            production_time = recipe["production_time"]
            hidden = recipe.get("hidden", False)
        else:  # sink
            input_map = {recipe["cargo"]: 1}
            output_map = {}
            production_time = recipe["production_time"]
            hidden = recipe.get("hidden", True)

        return [
            {"path": "InputCargos", "op": "set_name_int_map",
             "value": input_map},
            {"path": "OutputCargos", "op": "set_name_int_map",
             "value": output_map},
            {"path": "InputCargoTypes", "op": "clear_map"},
            {"path": "OutputCargoTypes", "op": "clear_map"},
            {"path": "InputCargoGameplayTagQuery", "op": "clear_tag_query"},
            {"path": "OutputCargoRowGameplayTagQuery", "op": "clear_tag_query"},
            {"path": "bStoreInputCargo", "op": "set", "value": False},
            {"path": "ProductionTimeSeconds", "op": "set",
             "value": production_time},
            {"path": "ProductionSpeedMultiplier", "op": "set", "value": 1},
            {"path": "LocalFoodSupply", "op": "set", "value": 0},
            {"path": "bHidden", "op": "set", "value": hidden},
            {"path": "TimeSinceLastProduction", "op": "set", "value": 0},
            {"path": "ProductionFlags", "op": "set", "value": 0},
        ]

    # ── Build hooks ────────────────────────────────────────────────────

    def transform_assets(self):
        """Patch SmallBox template into new cargo blueprints."""
        self.log_step(1, "Patch cargo blueprints")
        self.blueprints_output_dir = os.path.join(self.build_dir, "blueprints")
        os.makedirs(self.blueprints_output_dir)

        config = self._blueprint_clone_config()
        self.run_generic("--clone-asset", config,
                         self.blueprint_template, self.blueprints_output_dir,
                         "clone-blueprints")

    def register_in_tables(self):
        """Add cargo rows to Cargos DataTable and delivery point recipes."""
        # Resolve Cargos template (base game or compat mod)
        cargos_template = self.resolve_template_with_compat(
            self.cargos_template, self.CARGOS_PAK_PATH,
        )

        # Step: Add cargo rows
        self.log_step(2, "Add cargo rows to Cargos DataTable")
        self.cargos_output_dir = os.path.join(self.build_dir, "cargos")
        os.makedirs(self.cargos_output_dir)

        config = self._cargo_rows_config()
        self.run_generic("--add-rows", config,
                         cargos_template, self.cargos_output_dir,
                         "add-cargo-rows")

        # Step: Add production config recipes
        self.log_step(3, "Add delivery point recipes")
        self.recipes_output_dir = os.path.join(self.build_dir, "recipes")
        os.makedirs(self.recipes_output_dir)

        # Group all work by delivery_point
        work_by_dp = {}  # {dp_name: {"template": path, "recipes": [...], "storage": [...]}}

        def resolve_tp(entry):
            tp = entry["template_path"]
            return tp if os.path.isabs(tp) else os.path.join(self.repo_root, tp)

        for section, mode in [("sources", "source"), ("sinks", "sink"),
                               ("transforms", "transform")]:
            for dp in self.recipe_config.get(section, []):
                dp_name = dp["delivery_point"]
                work = work_by_dp.setdefault(dp_name, {
                    "template": resolve_tp(dp), "recipes": [], "storage": []})
                for recipe in dp["recipes"]:
                    work["recipes"].append((mode, recipe))

        for dp in self.recipe_config.get("storage", []):
            dp_name = dp["delivery_point"]
            work = work_by_dp.setdefault(dp_name, {
                "template": resolve_tp(dp), "recipes": [], "storage": []})
            for entry in dp["entries"]:
                work["storage"].append(entry)

        # Process each delivery point
        for dp_name, work in work_by_dp.items():
            config = self._recipe_cdo_config(
                dp_name, work["recipes"], work["storage"])
            self.run_generic("--patch-cdo-arrays", config,
                             work["template"], self.recipes_output_dir,
                             f"recipes-{dp_name}")

    def assemble_pak(self):
        """Stage Cargos DataTable, blueprints, and delivery point assets."""
        self.log_step(4, "Assemble PAK directory")

        # Cargos DataTable
        cargos_asset = os.path.join(self.cargos_output_dir, "Cargos.uasset")
        self.stage_datatable(cargos_asset, "Cargos", "DataAsset")

        # Cargo blueprints
        for name in self.cargo_names:
            bp_asset = os.path.join(
                self.blueprints_output_dir, name, f"{name}.uasset")
            if os.path.exists(bp_asset):
                self.stage_asset(bp_asset, "Objects/Mission/Delivery", name=name)

        # Delivery point assets
        all_dps = set()
        for section in ["sources", "sinks", "transforms"]:
            for dp in self.recipe_config.get(section, []):
                all_dps.add(dp["delivery_point"])
        for dp in self.recipe_config.get("storage", []):
            all_dps.add(dp["delivery_point"])

        for dp_name in all_dps:
            dp_asset = os.path.join(self.recipes_output_dir, f"{dp_name}.uasset")
            if os.path.exists(dp_asset):
                self.stage_asset(
                    dp_asset,
                    "Objects/Mission/Delivery/DeliveryPoint",
                    name=dp_name,
                )

    def print_summary(self):
        self.log(f"  Cargos: {', '.join(self.cargo_names)}")


def main():
    parser = argparse.ArgumentParser(description="Create MotorTown cargo mod PAK")
    add_common_args(parser)
    parser.add_argument("--recipes", "-r", default="recipe_entries.json",
                        help="Delivery point recipe entries JSON config")
    parser.add_argument("--cargos-template", default=None,
                        help="Base game Cargos.uasset template")
    parser.add_argument("--blueprint-template", default=None,
                        help="Base game SmallBox.uasset template")
    args = parser.parse_args()

    builder = CargoModBuilder(
        config_path=args.config,
        output_path=args.output,
        recipes_path=args.recipes,
        compat_mods=args.compat_mod,
        cargos_template=args.cargos_template,
        blueprint_template=args.blueprint_template,
    )
    builder.build()


if __name__ == "__main__":
    main()
