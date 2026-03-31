#!/usr/bin/env python3
"""
modbase — Shared base module for MotorTown mod PAK creation.

Provides:
  - ModBuilder: base class with the standard 4-stage build flow
  - Shared helpers: run_dotnet, build_pak, verify_pak, compat-mod extraction
  - PAK staging utilities

All mod-type scripts (create_tirepack.py, create_cargopack.py, etc.)
subclass ModBuilder and implement only their type-specific logic.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


class ModBuilder:
    """Base class for MotorTown mod PAK creation.

    Subclasses implement:
      - transform_assets(): create/patch type-specific UAsset files
      - register_in_tables(): add rows to DataTables
      - assemble_pak(): arrange files into the PAK directory layout

    The build() method orchestrates the full pipeline:
      1. transform_assets()
      2. register_in_tables()
      3. assemble_pak()
      4. build_pak()
      5. verify_pak()
    """

    def __init__(self, name: str, config_path: str, output_path: str,
                 compat_mods: list[str] | None = None):
        self.name = name
        self.config_path = os.path.abspath(config_path)
        self.output_path = os.path.abspath(output_path)
        self.compat_mods = [os.path.abspath(m) for m in (compat_mods or [])]

        self.repo_root = str(Path(__file__).resolve().parent.parent)
        self.csharp_dir = os.path.join(self.repo_root, "csharp", "UAssetTool")

        # Set during build()
        self.build_dir: str | None = None
        self.pak_staging: str | None = None
        self.config: dict = {}

        # Load config
        if not os.path.exists(self.config_path):
            self.fail(f"Config not found: {self.config_path}")
        with open(self.config_path) as f:
            self.config = json.load(f)

    # ── Shared infrastructure ──────────────────────────────────────────

    def fail(self, msg: str):
        """Print error and exit."""
        print(f"Error: {msg}", file=sys.stderr)
        sys.exit(1)

    def log(self, msg: str):
        """Print a log message."""
        print(msg)

    def log_step(self, step_num: int | str, label: str):
        """Print a step header."""
        print(f"\n=== Step {step_num}: {label} ===")

    def run_dotnet(self, args: list[str], label: str):
        """Run a C# dotnet command in the UAssetTool project.

        Args:
            args: command-line arguments after '--'
            label: human-readable description for error messages
        """
        result = subprocess.run(
            ["dotnet", "run", "--configuration", "Release",
             "--verbosity", "quiet", "--"] + args,
            cwd=self.csharp_dir,
            capture_output=True, text=True,
        )
        if result.stdout.strip():
            print(result.stdout.strip())
        if result.returncode != 0:
            print(f"Error: {label} failed:\n{result.stderr}", file=sys.stderr)
            sys.exit(1)
        return result

    def run_generic(self, operation: str, config: dict,
                    template: str, output_dir: str, label: str):
        """Run a generic C# UAssetTool operation with a generated config.

        Writes config to a temp JSON file in the build dir and invokes
        the C# tool with the specified operation.

        Args:
            operation: one of '--add-rows', '--clone-asset', '--patch-cdo-arrays'
            config: dict to serialize as the operation's config JSON
            template: path to the template .uasset file
            output_dir: directory for output files
            label: human-readable label for error messages
        """
        config_path = os.path.join(self.build_dir, f"{label.replace(' ', '_')}.json")
        with open(config_path, 'w') as f:
            json.dump(config, f)
        self.run_dotnet([operation, config_path, template, output_dir], label)

    def ensure_mod_pack(self) -> str:
        """Ensure mod_pack binary is built. Returns path to binary."""
        mod_pack = os.path.join(self.repo_root, "target", "release", "mod_pack")
        if not os.path.isfile(mod_pack):
            self.log("  Building mod_pack...")
            result = subprocess.run(
                ["cargo", "build", "--release", "--bin", "mod_pack"],
                cwd=self.repo_root, capture_output=True, text=True,
            )
            if result.returncode != 0:
                self.fail(f"Failed to build mod_pack:\n{result.stderr}")
        return mod_pack

    def build_pak(self, staging_dir: str):
        """Build a mod PAK from a staged directory using mod_pack."""
        mod_pack = self.ensure_mod_pack()
        result = subprocess.run(
            [mod_pack, staging_dir, self.output_path],
            capture_output=True, text=True,
        )
        if result.stdout.strip():
            print(result.stdout.strip())
        if result.returncode != 0:
            self.fail(f"mod_pack failed:\n{result.stderr}")

    def verify_pak(self):
        """List PAK contents for verification using mod_explore."""
        mod_explore = os.path.join(self.repo_root, "target", "release", "mod_explore")
        if os.path.isfile(mod_explore) and os.path.isfile(self.output_path):
            print(f"\n--- PAK contents ---")
            subprocess.run(
                [mod_explore, self.output_path, "--list"],
                capture_output=False,
            )

    # ── Compat mod support ─────────────────────────────────────────────

    def extract_from_compat_mod(self, pak_path: str, asset_pak_path: str,
                                 dest_dir: str) -> str | None:
        """Extract a single asset from another mod's PAK file.

        Args:
            pak_path: path to the .pak file
            asset_pak_path: asset path inside the PAK
                (e.g., 'MotorTown/Content/DataAsset/VehicleParts/VehicleParts0.uasset')
            dest_dir: directory to store extracted files

        Returns:
            path to extracted .uasset, or None if not found
        """
        basename = os.path.splitext(os.path.basename(asset_pak_path))[0]
        os.makedirs(dest_dir, exist_ok=True)

        for ext in ["uasset", "uexp"]:
            full_pak_path = asset_pak_path.replace(".uasset", f".{ext}")
            result = subprocess.run(
                ["cargo", "run", "--release", "--quiet", "--bin", "mod_explore",
                 "--", pak_path, "--extract", full_pak_path],
                cwd=self.repo_root,
                capture_output=True, text=True,
            )
            if result.returncode == 0:
                # mod_explore writes to mod_out/ in CWD
                src = os.path.join(self.repo_root, "mod_out", f"{basename}.{ext}")
                dst = os.path.join(dest_dir, f"{basename}.{ext}")
                if os.path.exists(src):
                    shutil.move(src, dst)
            else:
                mod_name = os.path.basename(pak_path)
                print(f"  Warning: Could not extract {basename}.{ext} from {mod_name}")

        extracted = os.path.join(dest_dir, f"{basename}.uasset")
        return extracted if os.path.exists(extracted) else None

    def resolve_template_with_compat(self, base_template: str,
                                      asset_pak_path: str) -> str:
        """Resolve a DataTable template, preferring compat mod version if available.

        Iterates through --compat-mod PAKs in order; the last one that contains
        the asset wins. Falls back to base_template if none have it.

        Args:
            base_template: path to the base game template .uasset
            asset_pak_path: PAK-internal path to extract from compat mods

        Returns:
            path to the resolved template .uasset
        """
        if not self.compat_mods:
            return base_template

        template = base_template
        for mod_pak in self.compat_mods:
            if not os.path.exists(mod_pak):
                self.fail(f"Compat mod PAK not found: {mod_pak}")

            mod_name = os.path.basename(mod_pak)
            self.log(f"\n  Extracting from compat mod: {mod_name}")

            extract_dir = tempfile.mkdtemp(prefix="compat_", dir=self.build_dir)
            extracted = self.extract_from_compat_mod(mod_pak, asset_pak_path, extract_dir)
            if extracted:
                template = extracted
                self.log(f"  ✓ Using template from: {mod_name}")
            else:
                basename = os.path.basename(asset_pak_path)
                self.log(f"  Warning: {mod_name} does not contain {basename}, skipping")

        return template

    # ── PAK staging helpers ────────────────────────────────────────────

    def init_staging(self) -> str:
        """Create and return the PAK staging directory."""
        self.pak_staging = os.path.join(self.build_dir, "pak_staging")
        os.makedirs(self.pak_staging, exist_ok=True)
        return self.pak_staging

    def stage_asset(self, src_uasset: str, pak_relative_dir: str, name: str | None = None):
        """Copy a .uasset/.uexp pair to the PAK staging directory.

        Args:
            src_uasset: path to the source .uasset file
            pak_relative_dir: path relative to MotorTown/Content/
                (e.g., 'Cars/Parts/Tire')
            name: override filename (without extension). If None, uses source filename.
        """
        if name is None:
            name = os.path.splitext(os.path.basename(src_uasset))[0]

        dest_dir = os.path.join(self.pak_staging, "MotorTown", "Content", pak_relative_dir)
        os.makedirs(dest_dir, exist_ok=True)

        for ext in [".uasset", ".uexp"]:
            src = src_uasset.replace(".uasset", ext)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(dest_dir, f"{name}{ext}"))
                self.log(f"  Staged: {pak_relative_dir}/{name}{ext}")

    def stage_datatable(self, src_path: str, datatable_name: str, pak_subdir: str):
        """Stage a DataTable asset into the PAK layout.

        Convenience wrapper around stage_asset for DataTables.

        Args:
            src_path: path to the .uasset file
            datatable_name: name of the DataTable (e.g., 'VehicleParts0')
            pak_subdir: PAK content subdirectory (e.g., 'DataAsset/VehicleParts')
        """
        self.stage_asset(src_path, pak_subdir, name=datatable_name)

    # ── Main build flow ────────────────────────────────────────────────

    def build(self):
        """Execute the full mod build pipeline.

        Template method pattern — subclasses implement the hooks:
          transform_assets()  → create/patch type-specific asset files
          register_in_tables() → add rows to DataTables
          assemble_pak()      → arrange files in PAK directory layout
        """
        print(f"\n=== Building {self.name} ===")

        with tempfile.TemporaryDirectory(prefix=f"modpack_{self.name}_") as build_dir:
            self.build_dir = build_dir
            self.init_staging()

            self.transform_assets()
            self.register_in_tables()
            self.assemble_pak()

            print(f"\n=== Building PAK ===")
            self.build_pak(self.pak_staging)

        # Report results
        if os.path.exists(self.output_path):
            size = os.path.getsize(self.output_path)
            print(f"\n=== Success! ===")
            print(f"  Output: {self.output_path}")
            print(f"  Size: {size:,} bytes")
            self.print_summary()
            self.verify_pak()
        else:
            self.fail(f"Output PAK not created: {self.output_path}")

    # ── Subclass hooks ─────────────────────────────────────────────────

    def transform_assets(self):
        """Create or patch type-specific UAsset files.

        Override in subclasses to implement mod-type-specific asset creation
        (e.g., tire physics patching, cargo blueprint creation, image injection).
        """
        pass

    def register_in_tables(self):
        """Add rows to DataTables.

        Override in subclasses to register new items in the appropriate
        DataTables (e.g., VehicleParts0, Cargos, Decals).
        """
        pass

    def assemble_pak(self):
        """Arrange output files into the PAK directory layout.

        Override in subclasses to call stage_asset() / stage_datatable()
        with the correct PAK-relative paths for each mod type.
        """
        pass

    def print_summary(self):
        """Print a mod-type-specific summary after successful build.

        Override in subclasses to report what was built.
        """
        pass


def add_common_args(parser):
    """Add arguments common to all mod builders."""
    parser.add_argument("--config", "-c", required=True,
                        help="Mod config JSON file")
    parser.add_argument("--output", "-o", required=True,
                        help="Output PAK file path (must end in _P.pak)")
    parser.add_argument("--compat-mod", action="append", default=[], metavar="PAK",
                        help="Build on top of another mod's DataTable "
                             "(can specify multiple, last wins)")
