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

from modbase import ModBuilder, add_common_args, load_mod_config, compute_output_path, resolve_game_version


class CargoModBuilder(ModBuilder):
    """Builds cargo mod PAKs with new cargo types and delivery routes."""

    CARGOS_PAK_PATH = "MotorTown/Content/DataAsset/Cargos.uasset"
    # Name for the child DataTable added to the CompositeDataTable
    CHILD_TABLE_NAME = "Cargos_ScheduleI"

    def __init__(self, config_path, output_path, recipes_path,
                 compat_mods=None, cargos_template=None,
                 blueprint_template=None):
        super().__init__("cargo mod", config_path, output_path, compat_mods)
        self.recipes_path = os.path.abspath(recipes_path)
        self.cargos_template = cargos_template or os.path.join(
            self.repo_root, "out", "Cargos.uasset")
        self.child_table_template = os.path.join(
            self.repo_root, "out", "Cargos_Deprecated.uasset")
        self.blueprint_template = blueprint_template or os.path.join(
            self.repo_root, "out", "SmallBox.uasset")

        if not os.path.exists(self.recipes_path):
            self.fail(f"Recipes not found: {self.recipes_path}")

        with open(self.recipes_path) as f:
            self.recipe_config = json.load(f)

        self.cargo_names = [e["blueprint_name"] for e in self.config["entries"]]

        # Outputs
        self.cargos_output_dir: str | None = None
        self.child_table_output_dir: str | None = None
        self.blueprints_output_dir: str | None = None
        self.recipes_output_dir: str | None = None

        self.log(f"\n=== Cargo Mod ===")
        self.log(f"  Cargos: {', '.join(self.cargo_names)}")
        self.log(f"  Sources: {[s['delivery_point'] for s in self.recipe_config.get('sources', [])]}")
        self.log(f"  Sinks: {[s['delivery_point'] for s in self.recipe_config.get('sinks', [])]}")
        self.log(f"  Catalysts: {[s['delivery_point'] for s in self.recipe_config.get('catalysts', [])]}")

    # ── Config generation ──────────────────────────────────────────────

    def _blueprint_clone_configs(self):
        """Generate per-template --clone-asset configs for all cargo blueprints.

        Returns dict mapping template_path -> {"assets": [...]} config.
        Entries with a "blueprint_template" field use that template;
        all others use self.blueprint_template (SmallBox).
        """
        from collections import defaultdict
        groups = defaultdict(list)

        for entry in self.config["entries"]:
            bp_name = entry["blueprint_name"]
            mesh_path = entry.get("mesh_path")
            mass_kg = entry["mass_kg"]

            template = entry.get("blueprint_template",
                                 self.blueprint_template)
            template = os.path.join(self.repo_root, template) \
                if not os.path.isabs(template) else template
            template_name = os.path.splitext(os.path.basename(template))[0]

            asset_spec = {
                "new_name": bp_name,
                "old_name": entry.get("clone_old_name", template_name),
                "new_path": f"/Game/Objects/Mission/Delivery/{bp_name}",
                "rename_exports": True,
                "rename_imports": True,
                "export_patches": [{
                    "match_class": "StaticMeshComponent",
                    "patches": [
                        {"path": "BodyInstance.MassInKgOverride",
                         "op": "set", "value": mass_kg},
                    ],
                }],
            }

            # Only replace mesh if mesh_path is provided
            if "import_replacements" in entry:
                # Use explicit import_replacements from entry (supports import_index)
                asset_spec["import_replacements"] = entry["import_replacements"]
            elif mesh_path:
                imp_repl = {
                    "match_class": "StaticMesh",
                    "new_package_path": mesh_path,
                    "new_name": mesh_path.split("/")[-1],
                }
                if entry.get("replace_all_meshes"):
                    imp_repl["replace_all"] = True
                asset_spec["import_replacements"] = [imp_repl]

            # Pass through extra export patches (e.g. position adjustments)
            if "extra_export_patches" in entry:
                asset_spec["export_patches"].extend(entry["extra_export_patches"])

            groups[template].append(asset_spec)

        return {tpl: {"assets": assets} for tpl, assets in groups.items()}

    def _cargo_rows_config(self):
        """Generate --add-rows config for child DataTable.

        Rows are added to a standalone child DataTable (not the parent
        CompositeDataTable), which gets registered via ParentTables.
        """
        rows = []
        for entry in self.config["entries"]:
            patches = [
                {"path": "bDepcreated", "op": "set", "value": False},
                {"path": "Name", "op": "set_localization_guid",
                 "value": entry["display_name"][0]},
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
                 "op": "set", "value": entry.get("payment_multiplier", 2.0)},
                {"path": "PaymentSqrtRatio", "op": "set", "value": 1.0},
                {"path": "ActorClass", "op": "set_import_ref",
                 "class_package": "/Script/Engine",
                 "class_name": "BlueprintGeneratedClass",
                 "package_path": f"/Game/Objects/Mission/Delivery/{entry['blueprint_name']}",
                 "asset_name": f"{entry['blueprint_name']}_C",
                 "add_cdo_import": True},
                {"path": "GameplayTags", "op": "clear_tags"},
                {"path": "bAllowStacking", "op": "set",
                 "value": entry.get("allow_stacking", False)},
                {"path": "bUseDamage", "op": "set", "value": False},
                {"path": "Fragile", "op": "set", "value": entry.get("fragile", 0)},
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

        return {
            "output_filename": self.CHILD_TABLE_NAME,
            "rows": rows,
        }

    def _composite_parent_config(self):
        """Generate --patch-export-props config for the parent CompositeDataTable.

        Appends our child DataTable to the ParentTables array so the engine
        discovers and merges our cargo rows at runtime.
        """
        return {
            "patches": [
                {
                    "path": "ParentTables",
                    "op": "append_import_to_array",
                    "class_package": "/Script/Engine",
                    "class_name": "DataTable",
                    "package_path": f"/Game/DataAsset/{self.CHILD_TABLE_NAME}",
                    "asset_name": self.CHILD_TABLE_NAME,
                },
            ],
        }

    def _recipe_cdo_config(self, dp_name, recipes, storage_entries,
                          demand_entries=None, cdo_patches=None,
                          replace_production_configs=False):
        """Generate --patch-cdo-arrays config for a delivery point."""
        arrays = []

        if recipes:
            entries = []
            for mode, recipe in recipes:
                patches = self._recipe_patches(mode, recipe)
                entries.append({"patches": patches})

            arrays.append({
                "property_name": "ProductionConfigs",
                "template_source": os.path.join(
                    self.repo_root, "out", "Factory_Toy.uasset"),
                "entries": entries,
                "replace": replace_production_configs,
            })

        if demand_entries:
            entries = []
            for entry in demand_entries:
                cargo_key = entry.get("cargo_key", None)
                patches = [
                    {"path": "CargoType", "op": "set_enum",
                     "value": entry.get("cargo_type", "None")},
                ]
                if cargo_key is not None:
                    patches.append({"path": "CargoKey", "op": "set_name",
                                    "value": cargo_key})
                else:
                    patches.append({"path": "CargoKey", "op": "null_ref"})
                patches.extend([
                    {"path": "PaymentMultiplier", "op": "set",
                     "value": entry.get("payment_multiplier", 1)},
                    {"path": "MaxStorage", "op": "set",
                     "value": entry.get("max_storage", 0)},
                ])
                entries.append({"patches": patches})

            arrays.append({
                "property_name": "DemandConfigs",
                "template_source": os.path.join(
                    self.repo_root, "out", "Resident.uasset"),
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
                "template_source": os.path.join(
                    self.repo_root, "out", "Factory_Toy.uasset"),
                "replace": True,
                "entries": entries,
            })

        result = {
            "output_filename": dp_name,
            "arrays": arrays,
        }
        if cdo_patches:
            result["cdo_patches"] = cdo_patches
        return result

    def _recipe_patches(self, mode, recipe):
        """Generate patches for a single production config entry."""
        if mode == "transform":
            input_map = {recipe["input_cargo"]: recipe.get("input_count", 1)}
            output_map = {recipe["output_cargo"]: recipe.get("output_count", 1)}
            production_time = recipe["production_time"]
            hidden = recipe.get("hidden", False)
            speed_mult = recipe.get("speed_multiplier", 1)
        elif mode == "source":
            input_map = {}
            output_map = {recipe["cargo"]: 1}
            production_time = recipe["production_time"]
            hidden = recipe.get("hidden", False)
            speed_mult = recipe.get("speed_multiplier", 1)
        elif mode == "catalyst":
            input_map = {recipe["cargo"]: recipe.get("count", 1)}
            output_map = {}
            production_time = recipe["production_time"]
            hidden = recipe.get("hidden", False)
            speed_mult = recipe.get("speed_multiplier", 2)
        else:  # sink
            input_map = {recipe["cargo"]: 1}
            output_map = {}
            production_time = recipe["production_time"]
            hidden = recipe.get("hidden", True)
            speed_mult = recipe.get("speed_multiplier", 1)

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
            {"path": "ProductionSpeedMultiplier", "op": "set",
             "value": speed_mult},
            {"path": "LocalFoodSupply", "op": "set", "value": 0},
            {"path": "bHidden", "op": "set", "value": hidden},
            {"path": "TimeSinceLastProduction", "op": "set", "value": 0},
            {"path": "ProductionFlags", "op": "set", "value": 0},
        ]

    # ── Build hooks ────────────────────────────────────────────────────

    def transform_assets(self):
        """Patch templates into new cargo blueprints."""
        self.log_step(1, "Patch cargo blueprints")
        self.blueprints_output_dir = os.path.join(self.build_dir, "blueprints")
        os.makedirs(self.blueprints_output_dir)

        configs = self._blueprint_clone_configs()
        for template_path, config in configs.items():
            self.run_generic("--clone-asset", config,
                             template_path, self.blueprints_output_dir,
                             "clone-blueprints")

    def register_in_tables(self):
        """Create child DataTable and register in parent CompositeDataTable."""
        # Resolve Cargos template (base game or compat mod)
        cargos_template = self.resolve_template_with_compat(
            self.cargos_template, self.CARGOS_PAK_PATH,
        )

        # Step 2a: Clone Cargos_Deprecated → Cargos_ScheduleI (renames internal paths)
        self.log_step("2a", f"Clone child DataTable ({self.CHILD_TABLE_NAME})")
        clone_dir = os.path.join(self.build_dir, "child_clone")
        os.makedirs(clone_dir)

        clone_config = {
            "assets": [{
                "new_name": self.CHILD_TABLE_NAME,
                "old_name": "Cargos_Deprecated",
                "new_path": f"/Game/DataAsset/{self.CHILD_TABLE_NAME}",
                "rename_exports": True,
                "rename_imports": True,
                "patch_namemap_0": True,
            }],
        }
        self.run_generic("--clone-asset", clone_config,
                         self.child_table_template, clone_dir,
                         "clone-child-table")

        # Step 2b: Add cargo rows to the cloned child table
        self.log_step("2b", f"Add cargo rows to {self.CHILD_TABLE_NAME}")
        self.child_table_output_dir = os.path.join(self.build_dir, "child_table")
        os.makedirs(self.child_table_output_dir)

        cloned_child = os.path.join(
            clone_dir, self.CHILD_TABLE_NAME, f"{self.CHILD_TABLE_NAME}.uasset")
        config = self._cargo_rows_config()
        self.run_generic("--add-rows", config,
                         cloned_child, self.child_table_output_dir,
                         "add-cargo-rows-child")

        # Step 2c: Patch parent CompositeDataTable to register child
        self.log_step("2c", "Register child in parent CompositeDataTable")
        self.cargos_output_dir = os.path.join(self.build_dir, "cargos")
        os.makedirs(self.cargos_output_dir)

        parent_config = self._composite_parent_config()
        self.run_generic("--patch-export-props", parent_config,
                         cargos_template, self.cargos_output_dir,
                         "patch-composite-parent")

        # Step: Add production config recipes
        self.log_step(3, "Add delivery point recipes")
        self.recipes_output_dir = os.path.join(self.build_dir, "recipes")
        os.makedirs(self.recipes_output_dir)

        # Group all work by delivery_point
        work_by_dp = {}  # {dp_name: {"template": path, "recipes": [...], "storage": [...], "demand": [...], "cdo": [...]}}

        def resolve_tp(entry):
            tp = entry["template_path"]
            return tp if os.path.isabs(tp) else os.path.join(self.repo_root, tp)

        def get_work(dp_name, template_entry):
            return work_by_dp.setdefault(dp_name, {
                "template": resolve_tp(template_entry), "recipes": [],
                "storage": [], "demand": [], "cdo": None,
                "replace_production_configs": template_entry.get("replace_production_configs", False)})

        for section, mode in [("sources", "source"), ("sinks", "sink"),
                               ("transforms", "transform"),
                               ("catalysts", "catalyst")]:
            for dp in self.recipe_config.get(section, []):
                dp_name = dp["delivery_point"]
                work = get_work(dp_name, dp)
                for recipe in dp["recipes"]:
                    work["recipes"].append((mode, recipe))

        for dp in self.recipe_config.get("storage", []):
            dp_name = dp["delivery_point"]
            work = get_work(dp_name, dp)
            for entry in dp["entries"]:
                work["storage"].append(entry)

        for dp in self.recipe_config.get("demand_configs", []):
            dp_name = dp["delivery_point"]
            work = get_work(dp_name, dp)
            for entry in dp["entries"]:
                work["demand"].append(entry)

        for dp in self.recipe_config.get("cdo_patches", []):
            dp_name = dp["delivery_point"]
            work = get_work(dp_name, dp)
            work["cdo"] = dp.get("patches", [])

        # Clone+rename templates that differ from target delivery point name
        cloned_templates = {}
        for dp_name, work in work_by_dp.items():
            template_basename = os.path.splitext(os.path.basename(work["template"]))[0]
            if template_basename != dp_name:
                clone_dir = os.path.join(self.build_dir, "dp_clones", dp_name)
                os.makedirs(clone_dir, exist_ok=True)
                clone_config = {
                    "assets": [{
                        "new_name": dp_name,
                        "old_name": template_basename,
                        "new_path": f"/Game/Objects/Mission/Delivery/DeliveryPoint/{dp_name}",
                        "rename_exports": True,
                        "rename_imports": True,
                        "patch_namemap_0": True,
                    }],
                }
                self.run_generic("--clone-asset", clone_config,
                                 work["template"], clone_dir,
                                 f"clone-dp-{dp_name}")
                cloned_templates[dp_name] = os.path.join(clone_dir, dp_name, f"{dp_name}.uasset")
                self.log(f"  Cloned {template_basename} -> {dp_name}")

        # Process each delivery point
        for dp_name, work in work_by_dp.items():
            template = cloned_templates.get(dp_name, work["template"])
            config = self._recipe_cdo_config(
                dp_name, work["recipes"], work["storage"],
                demand_entries=work["demand"] if work["demand"] else None,
                cdo_patches=work["cdo"] if work["cdo"] else None,
                replace_production_configs=work.get("replace_production_configs", False))
            self.run_generic("--patch-cdo-arrays", config,
                             template, self.recipes_output_dir,
                             f"recipes-{dp_name}")

    def assemble_pak(self):
        """Stage DataTables, blueprints, and delivery point assets."""
        self.log_step(4, "Assemble PAK directory")

        # Parent CompositeDataTable (Cargos.uasset with updated ParentTables)
        cargos_asset = os.path.join(self.cargos_output_dir, "Cargos.uasset")
        self.stage_datatable(cargos_asset, "Cargos", "DataAsset")

        # Child DataTable (Cargos_ScheduleI.uasset with our cargo rows)
        child_asset = os.path.join(
            self.child_table_output_dir, f"{self.CHILD_TABLE_NAME}.uasset")
        self.stage_datatable(child_asset, self.CHILD_TABLE_NAME, "DataAsset")

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
    parser.add_argument("--recipes", "-r", default=None,
                        help="Delivery point recipe entries JSON config")
    parser.add_argument("--cargos-template", default=None,
                        help="Base game Cargos.uasset template")
    parser.add_argument("--blueprint-template", default=None,
                        help="Base game SmallBox.uasset template")
    parser.add_argument("--mod", default=None,
                        help="Mod directory (e.g. mods/schedule-i) to load mod.json from")
    args = parser.parse_args()

    if args.mod:
        mod = load_mod_config(args.mod)
        config_path = mod["configs"][0]
        recipes_path = mod["configs"][1] if len(mod["configs"]) > 1 else args.recipes
        game_ver = resolve_game_version()
        output_path = compute_output_path(mod, game_ver)
    else:
        config_path = args.config
        recipes_path = args.recipes or "recipe_entries.json"
        output_path = args.output

    builder = CargoModBuilder(
        config_path=config_path,
        output_path=output_path,
        recipes_path=recipes_path,
        compat_mods=args.compat_mod,
        cargos_template=args.cargos_template,
        blueprint_template=args.blueprint_template,
    )
    builder.build()


if __name__ == "__main__":
    main()
