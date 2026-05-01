#!/usr/bin/env python3
"""
Create a MotorTown furniture mod PAK.

Pipeline:
  1. Clone _Common_Prop blueprint and swap StaticMesh (--clone-asset)
  2. Add furniture rows to Buildings_Furnitures DataTable (--add-rows)
  3. Assemble PAK directory structure
  4. Build mod PAK via mod_pack

Usage:
  python3 scripts/create_furniture_mod.py \\
    --config furniture_entries.json \\
    --output MyFurniture_P.pak
"""

import argparse
import json
import os

from modbase import ModBuilder, add_common_args, load_mod_config, compute_output_path, resolve_game_version


class FurnitureModBuilder(ModBuilder):
    """Builds furniture mod PAKs with new placeable furniture items."""

    BUILDINGS_FURNITURES_PAK_PATH = "MotorTown/Content/DataAsset/Buildings/Buildings_Furnitures.uasset"

    def __init__(self, config_path, output_path, compat_mods=None,
                 buildings_template=None, blueprint_template=None):
        super().__init__("furniture mod", config_path, output_path, compat_mods)
        self.buildings_template = buildings_template or os.path.join(
            self.repo_root, "out", "Buildings_Furnitures.uasset")
        self.blueprint_template = blueprint_template or os.path.join(
            self.repo_root, "out", "_Common_Prop.uasset")

        self.furniture_names = [e["row_name"] for e in self.config["entries"]]

        # Outputs
        self.blueprints_output_dir: str | None = None
        self.buildings_output_dir: str | None = None

        self.log(f"\n=== Furniture Mod ===")
        self.log(f"  Items: {', '.join(self.furniture_names)}")

    def _blueprint_clone_configs(self):
        """Generate --clone-asset configs for furniture blueprints."""
        from collections import defaultdict
        groups = defaultdict(list)

        for entry in self.config["entries"]:
            bp_name = entry["row_name"]
            mesh_path = entry["mesh_path"]

            template = entry.get("blueprint_template", self.blueprint_template)
            template = os.path.join(self.repo_root, template) \
                if not os.path.isabs(template) else template
            template_name = os.path.splitext(os.path.basename(template))[0]

            asset_spec = {
                "new_name": bp_name,
                "old_name": entry.get("clone_old_name", template_name),
                "new_path": f"/Game/Objects/Housing/Furnitures/{bp_name}",
                "rename_exports": True,
                "rename_imports": True,
                "import_replacements": [{
                    "match_class": "StaticMesh",
                    "new_package_path": mesh_path,
                    "new_name": mesh_path.split("/")[-1],
                }],
            }

            groups[template].append(asset_spec)

        return {tpl: {"assets": assets} for tpl, assets in groups.items()}

    def _buildings_rows_config(self):
        """Generate --add-rows config for Buildings_Furnitures DataTable.

        Clones a template _Common_Prop row and patches ActorClass + StaticMeshes.
        """
        rows = []
        for entry in self.config["entries"]:
            bp_name = entry["row_name"]
            mesh_path = entry["mesh_path"]
            bp_package = f"/Game/Objects/Housing/Furnitures/{bp_name}"
            bp_asset = f"{bp_name}_C"

            patches = [
                # Patch ActorClass to point to our new blueprint
                {"path": "Steps[0].ActorClass", "op": "set_import_ref",
                 "class_package": "/Script/Engine",
                 "class_name": "BlueprintGeneratedClass",
                 "package_path": bp_package,
                 "asset_name": bp_asset},
                # Patch StaticMeshes map with our mesh
                {"path": "Steps[0].StaticMeshes", "op": "set_import_ref_map",
                 "entries": [{
                     "key": "StaticMesh",
                     "class_package": "/Script/Engine",
                     "class_name": "StaticMesh",
                     "package_path": mesh_path.rsplit("/", 1)[0],
                     "asset_name": mesh_path.rsplit("/", 1)[-1],
                 }]},
            ]

            # Use template_row_match with a specific row that uses _Common_Prop
            template_match = entry.get("template_row_match",
                                       {"BuildingRowType": "Furniture"})

            rows.append({
                "row_name": bp_name,
                "patches": patches,
                "template_row_match": template_match,
            })

        return {
            "rows": rows,
        }

    def transform_assets(self):
        """Clone _Common_Prop blueprint into new furniture blueprints."""
        self.log_step(1, "Clone furniture blueprints")
        self.blueprints_output_dir = os.path.join(self.build_dir, "blueprints")
        os.makedirs(self.blueprints_output_dir)

        configs = self._blueprint_clone_configs()
        for template_path, config in configs.items():
            self.run_generic("--clone-asset", config,
                             template_path, self.blueprints_output_dir,
                             "clone-blueprints")

    def register_in_tables(self):
        """Add furniture rows to Buildings_Furnitures DataTable."""
        self.log_step(2, "Add furniture rows to Buildings_Furnitures")

        # Resolve template (base game or compat mod)
        buildings_template = self.resolve_template_with_compat(
            self.buildings_template, self.BUILDINGS_FURNITURES_PAK_PATH,
        )

        self.buildings_output_dir = os.path.join(self.build_dir, "buildings")
        os.makedirs(self.buildings_output_dir)

        config = self._buildings_rows_config()
        self.run_generic("--add-rows", config,
                         buildings_template, self.buildings_output_dir,
                         "add-furniture-rows")

    def assemble_pak(self):
        """Stage blueprints and DataTable into PAK layout."""
        self.log_step(3, "Assemble PAK directory")

        # Stage Buildings_Furnitures DataTable
        buildings_asset = os.path.join(
            self.buildings_output_dir, "Buildings_Furnitures.uasset")
        self.stage_datatable(buildings_asset, "Buildings_Furnitures",
                             "DataAsset/Buildings")

        # Stage furniture blueprints
        for name in self.furniture_names:
            bp_asset = os.path.join(
                self.blueprints_output_dir, name, f"{name}.uasset")
            if os.path.exists(bp_asset):
                self.stage_asset(
                    bp_asset, "Objects/Housing/Furnitures", name=name)

    def print_summary(self):
        self.log(f"  Furniture items: {', '.join(self.furniture_names)}")


def main():
    parser = argparse.ArgumentParser(description="Create MotorTown furniture mod PAK")
    add_common_args(parser)
    parser.add_argument("--buildings-template", default=None,
                        help="Base game Buildings_Furnitures.uasset template")
    parser.add_argument("--blueprint-template", default=None,
                        help="Furniture blueprint template (_Common_Prop.uasset)")
    parser.add_argument("--mod", default=None,
                        help="Mod directory to load mod.json from")
    args = parser.parse_args()

    if args.mod:
        mod = load_mod_config(args.mod)
        config_path = mod["configs"][0]
        game_ver = resolve_game_version()
        output_path = compute_output_path(mod, game_ver)
    else:
        config_path = args.config
        output_path = args.output

    builder = FurnitureModBuilder(
        config_path=config_path,
        output_path=output_path,
        compat_mods=args.compat_mod,
        buildings_template=args.buildings_template,
        blueprint_template=args.blueprint_template,
    )
    builder.build()


if __name__ == "__main__":
    main()
