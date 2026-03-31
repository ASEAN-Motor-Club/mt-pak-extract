#!/usr/bin/env python3
"""
Create a MotorTown cargo mod PAK.

Pipeline:
  1. Add cargo rows to Cargos.uasset (--add-cargos)
  2. Patch SmallBox.uasset into new cargo blueprints (--patch-blueprint)
  3. Add production config recipes to delivery points (--add-recipes)
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
import sys

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

    def transform_assets(self):
        """Patch SmallBox template into new cargo blueprints."""
        self.log_step(1, "Patch cargo blueprints")
        self.blueprints_output_dir = os.path.join(self.build_dir, "blueprints")
        os.makedirs(self.blueprints_output_dir)

        self.run_dotnet(
            ["--patch-blueprint", self.config_path,
             self.blueprint_template, self.blueprints_output_dir],
            "--patch-blueprint",
        )

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

        self.run_dotnet(
            ["--add-cargos", self.config_path,
             cargos_template, self.cargos_output_dir],
            "--add-cargos",
        )

        # Step: Add production config recipes
        self.log_step(3, "Add delivery point recipes")
        self.recipes_output_dir = os.path.join(self.build_dir, "recipes")
        os.makedirs(self.recipes_output_dir)

        self.run_dotnet(
            ["--add-recipes", self.recipes_path, self.recipes_output_dir],
            "--add-recipes",
        )

    def assemble_pak(self):
        """Stage Cargos DataTable, blueprints, and delivery point assets."""
        self.log_step(4, "Assemble PAK directory")

        # Cargos DataTable
        cargos_asset = os.path.join(self.cargos_output_dir, "Cargos.uasset")
        self.stage_datatable(cargos_asset, "Cargos", "DataAsset")

        # Cargo blueprints — placed directly in Delivery/ (no subfolder!)
        for name in self.cargo_names:
            bp_asset = os.path.join(
                self.blueprints_output_dir, name, f"{name}.uasset")
            if os.path.exists(bp_asset):
                self.stage_asset(bp_asset, "Objects/Mission/Delivery", name=name)

        # Delivery point assets — collect from all recipe sections
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
