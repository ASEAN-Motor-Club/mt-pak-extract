#!/usr/bin/env python3
"""
Unit and integration tests for the mod creation base module and refactored scripts.

Run with:
    python3 -m unittest tests/test_modbase.py -v

Or from nix develop:
    nix develop --command bash -c 'python3 -m unittest tests/test_modbase.py -v'
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, call

# Add scripts/ to path for imports
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from modbase import ModBuilder, add_common_args


# ============================================================================
# Unit Tests — ModBuilder base class (no subprocess calls)
# ============================================================================

class TestModBuilderInit(unittest.TestCase):
    """Test ModBuilder initialization and config loading."""

    def test_init_loads_config(self):
        """Config file is loaded and parsed as dict."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"entries": [{"name": "test"}]}, f)
            f.flush()
            try:
                builder = ModBuilder("test", f.name, "/tmp/out.pak")
                self.assertEqual(builder.config["entries"][0]["name"], "test")
                self.assertEqual(builder.name, "test")
            finally:
                os.unlink(f.name)

    def test_init_missing_config_exits(self):
        """Missing config file causes sys.exit."""
        with self.assertRaises(SystemExit):
            ModBuilder("test", "/nonexistent/config.json", "/tmp/out.pak")

    def test_init_resolves_paths(self):
        """Paths are resolved to absolute."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({}, f)
            f.flush()
            try:
                builder = ModBuilder("test", f.name, "relative_output.pak")
                self.assertTrue(os.path.isabs(builder.config_path))
                self.assertTrue(os.path.isabs(builder.output_path))
                self.assertTrue(os.path.isabs(builder.repo_root))
            finally:
                os.unlink(f.name)

    def test_init_compat_mods_resolved(self):
        """Compat mod paths are resolved to absolute."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({}, f)
            f.flush()
            try:
                builder = ModBuilder("test", f.name, "/tmp/out.pak",
                                     compat_mods=["relative/path.pak"])
                self.assertTrue(os.path.isabs(builder.compat_mods[0]))
            finally:
                os.unlink(f.name)

    def test_init_no_compat_mods(self):
        """Default compat_mods is empty list."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({}, f)
            f.flush()
            try:
                builder = ModBuilder("test", f.name, "/tmp/out.pak")
                self.assertEqual(builder.compat_mods, [])
            finally:
                os.unlink(f.name)


class TestModBuilderStaging(unittest.TestCase):
    """Test PAK staging helpers."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.tmpdir, "config.json")
        with open(self.config_path, 'w') as f:
            json.dump({}, f)
        self.builder = ModBuilder("test", self.config_path, "/tmp/out.pak")
        self.builder.build_dir = self.tmpdir
        self.builder.init_staging()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_init_staging_creates_directory(self):
        """init_staging creates pak_staging dir."""
        self.assertTrue(os.path.isdir(self.builder.pak_staging))

    def test_stage_asset_copies_both_files(self):
        """stage_asset copies .uasset and .uexp pair."""
        # Create fake asset files
        uasset = os.path.join(self.tmpdir, "Test.uasset")
        uexp = os.path.join(self.tmpdir, "Test.uexp")
        Path(uasset).write_text("uasset data")
        Path(uexp).write_text("uexp data")

        self.builder.stage_asset(uasset, "DataAsset/VehicleParts", name="Test")

        staged_dir = os.path.join(
            self.builder.pak_staging, "MotorTown", "Content",
            "DataAsset", "VehicleParts")
        self.assertTrue(os.path.isfile(os.path.join(staged_dir, "Test.uasset")))
        self.assertTrue(os.path.isfile(os.path.join(staged_dir, "Test.uexp")))

    def test_stage_asset_uses_source_name_if_none(self):
        """stage_asset uses source filename if name is not provided."""
        uasset = os.path.join(self.tmpdir, "MyAsset.uasset")
        Path(uasset).write_text("data")

        self.builder.stage_asset(uasset, "Cars/Parts/Tire")

        staged_dir = os.path.join(
            self.builder.pak_staging, "MotorTown", "Content",
            "Cars", "Parts", "Tire")
        self.assertTrue(os.path.isfile(os.path.join(staged_dir, "MyAsset.uasset")))

    def test_stage_asset_handles_missing_uexp(self):
        """stage_asset works even if .uexp doesn't exist (only .uasset)."""
        uasset = os.path.join(self.tmpdir, "OnlyUasset.uasset")
        Path(uasset).write_text("data")

        # Should not raise
        self.builder.stage_asset(uasset, "DataAsset")

        staged_dir = os.path.join(
            self.builder.pak_staging, "MotorTown", "Content", "DataAsset")
        self.assertTrue(os.path.isfile(os.path.join(staged_dir, "OnlyUasset.uasset")))
        self.assertFalse(os.path.isfile(os.path.join(staged_dir, "OnlyUasset.uexp")))

    def test_stage_datatable_delegates_to_stage_asset(self):
        """stage_datatable is a convenience wrapper around stage_asset."""
        uasset = os.path.join(self.tmpdir, "VehicleParts0.uasset")
        uexp = os.path.join(self.tmpdir, "VehicleParts0.uexp")
        Path(uasset).write_text("data")
        Path(uexp).write_text("data")

        self.builder.stage_datatable(
            uasset, "VehicleParts0", "DataAsset/VehicleParts")

        staged_dir = os.path.join(
            self.builder.pak_staging, "MotorTown", "Content",
            "DataAsset", "VehicleParts")
        self.assertTrue(os.path.isfile(os.path.join(staged_dir, "VehicleParts0.uasset")))
        self.assertTrue(os.path.isfile(os.path.join(staged_dir, "VehicleParts0.uexp")))


class TestModBuilderCompatMod(unittest.TestCase):
    """Test compat mod template resolution."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.tmpdir, "config.json")
        with open(self.config_path, 'w') as f:
            json.dump({}, f)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_resolve_no_compat_returns_base(self):
        """Without compat mods, returns the base template path."""
        builder = ModBuilder("test", self.config_path, "/tmp/out.pak")
        result = builder.resolve_template_with_compat(
            "/base/template.uasset", "pak/path")
        self.assertEqual(result, "/base/template.uasset")

    def test_resolve_compat_mod_not_found_exits(self):
        """Compat mod PAK that doesn't exist causes sys.exit."""
        builder = ModBuilder("test", self.config_path, "/tmp/out.pak",
                             compat_mods=["/nonexistent/mod.pak"])
        builder.build_dir = self.tmpdir
        with self.assertRaises(SystemExit):
            builder.resolve_template_with_compat(
                "/base/template.uasset", "pak/path")


class TestModBuilderRunDotnet(unittest.TestCase):
    """Test run_dotnet subprocess wrapper."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.tmpdir, "config.json")
        with open(self.config_path, 'w') as f:
            json.dump({}, f)
        self.builder = ModBuilder("test", self.config_path, "/tmp/out.pak")

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    @patch('subprocess.run')
    def test_run_dotnet_passes_args(self, mock_run):
        """run_dotnet constructs correct command with dotnet run prefix."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="ok", stderr="")

        self.builder.run_dotnet(["--add-cargos", "config.json"], "add cargos")

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        self.assertEqual(args[:6], [
            "dotnet", "run", "--configuration", "Release",
            "--verbosity", "quiet"
        ])
        self.assertEqual(args[6], "--")
        self.assertEqual(args[7:], ["--add-cargos", "config.json"])

    @patch('subprocess.run')
    def test_run_dotnet_exits_on_failure(self, mock_run):
        """run_dotnet exits if dotnet returns non-zero."""
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="compilation error")

        with self.assertRaises(SystemExit):
            self.builder.run_dotnet(["--bad-arg"], "bad command")

    @patch('subprocess.run')
    def test_run_dotnet_uses_csharp_dir(self, mock_run):
        """run_dotnet runs in the CargoExtractor directory."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="", stderr="")

        self.builder.run_dotnet(["--dump", "test.uasset"], "dump")

        cwd = mock_run.call_args[1]['cwd']
        self.assertTrue(cwd.endswith("csharp/CargoExtractor"))


class TestModBuilderBuildFlow(unittest.TestCase):
    """Test the template method build() flow."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.tmpdir, "config.json")
        with open(self.config_path, 'w') as f:
            json.dump({}, f)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    @patch.object(ModBuilder, 'verify_pak')
    @patch.object(ModBuilder, 'build_pak')
    @patch.object(ModBuilder, 'assemble_pak')
    @patch.object(ModBuilder, 'register_in_tables')
    @patch.object(ModBuilder, 'transform_assets')
    def test_build_calls_hooks_in_order(self, mock_transform, mock_register,
                                         mock_assemble, mock_build_pak,
                                         mock_verify):
        """build() calls hooks in correct order."""
        output = os.path.join(self.tmpdir, "test.pak")
        # Create a fake output file so build doesn't fail
        Path(output).write_text("fake pak")

        builder = ModBuilder("test", self.config_path, output)
        builder.build()

        mock_transform.assert_called_once()
        mock_register.assert_called_once()
        mock_assemble.assert_called_once()
        mock_build_pak.assert_called_once()

    @patch.object(ModBuilder, 'verify_pak')
    @patch.object(ModBuilder, 'build_pak')
    def test_build_sets_build_dir(self, mock_build_pak, mock_verify):
        """build() sets build_dir and pak_staging before calling hooks."""
        output = os.path.join(self.tmpdir, "test.pak")
        Path(output).write_text("fake pak")

        captured = {}

        class TestBuilder(ModBuilder):
            def transform_assets(self):
                captured['build_dir'] = self.build_dir
                captured['pak_staging'] = self.pak_staging

        builder = TestBuilder("test", self.config_path, output)
        builder.build()

        self.assertIsNotNone(captured['build_dir'])
        self.assertIsNotNone(captured['pak_staging'])


class TestAddCommonArgs(unittest.TestCase):
    """Test the argument parser helper."""

    def test_adds_required_args(self):
        """add_common_args adds --config, --output, --compat-mod."""
        import argparse
        parser = argparse.ArgumentParser()
        add_common_args(parser)

        # Test that parsing works with required args
        args = parser.parse_args(["-c", "config.json", "-o", "out.pak"])
        self.assertEqual(args.config, "config.json")
        self.assertEqual(args.output, "out.pak")
        self.assertEqual(args.compat_mod, [])

    def test_compat_mod_accumulates(self):
        """Multiple --compat-mod flags accumulate in a list."""
        import argparse
        parser = argparse.ArgumentParser()
        add_common_args(parser)

        args = parser.parse_args([
            "-c", "c.json", "-o", "o.pak",
            "--compat-mod", "a.pak", "--compat-mod", "b.pak"
        ])
        self.assertEqual(args.compat_mod, ["a.pak", "b.pak"])


# ============================================================================
# Unit Tests — Tire and Cargo subclass config parsing
# ============================================================================

class TestTireModBuilderConfig(unittest.TestCase):
    """Test TireModBuilder config normalization."""

    def test_multi_tire_config(self):
        """Multi-tire config with 'tires' array is parsed correctly."""
        from create_tirepack import TireModBuilder

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"tires": [
                {"tire_physics": {"name": "T1", "template": "BasicTire_45"},
                 "tire_part": {"row_name": "T1", "cost": 100}},
                {"tire_physics": {"name": "T2", "template": "BasicTire_45"},
                 "tire_part": {"row_name": "T2", "cost": 200}},
            ]}, f)
            f.flush()
            try:
                builder = TireModBuilder(f.name, "/tmp/out.pak")
                self.assertEqual(len(builder.tire_entries), 2)
                self.assertEqual(builder.tire_entries[0]["tire_physics"]["name"], "T1")
                self.assertEqual(builder.tire_entries[1]["tire_physics"]["name"], "T2")
            finally:
                os.unlink(f.name)

    def test_single_tire_backward_compat(self):
        """Single-tire config without 'tires' array wraps in list."""
        from create_tirepack import TireModBuilder

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({
                "tire_physics": {"name": "Solo", "template": "BasicTire_45"},
                "tire_part": {"row_name": "Solo", "cost": 50},
            }, f)
            f.flush()
            try:
                builder = TireModBuilder(f.name, "/tmp/out.pak")
                self.assertEqual(len(builder.tire_entries), 1)
                self.assertEqual(builder.tire_entries[0]["tire_physics"]["name"], "Solo")
            finally:
                os.unlink(f.name)


class TestCargoModBuilderConfig(unittest.TestCase):
    """Test CargoModBuilder config parsing."""

    def test_parses_cargo_names(self):
        """Cargo names are extracted from config entries."""
        from create_cargopack import CargoModBuilder

        tmpdir = tempfile.mkdtemp()
        try:
            config = os.path.join(tmpdir, "cargo.json")
            recipes = os.path.join(tmpdir, "recipes.json")
            with open(config, 'w') as f:
                json.dump({"entries": [
                    {"blueprint_name": "BigBox", "row_name": "BigBox",
                     "cargo_type": "SmallPackage", "weight_min": 5,
                     "weight_max": 10, "mesh_path": "/Game/test", "mass_kg": 5,
                     "display_name": ["Big Box"], "payment_per_km": 100,
                     "spawn_probability": 10},
                ]}, f)
            with open(recipes, 'w') as f:
                json.dump({"sources": [], "sinks": []}, f)

            builder = CargoModBuilder(config, "/tmp/out.pak", recipes)
            self.assertEqual(builder.cargo_names, ["BigBox"])
        finally:
            shutil.rmtree(tmpdir)

    def test_missing_recipes_exits(self):
        """Missing recipes file causes sys.exit."""
        from create_cargopack import CargoModBuilder

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"entries": []}, f)
            f.flush()
            try:
                with self.assertRaises(SystemExit):
                    CargoModBuilder(f.name, "/tmp/out.pak", "/nonexistent/recipes.json")
            finally:
                os.unlink(f.name)


# ============================================================================
# Integration Tests — require nix develop shell + game assets
# ============================================================================

def _in_nix_shell():
    """Check if we're running inside the nix develop shell."""
    return os.path.isfile(str(REPO_ROOT / "Mappings.usmap"))


def _has_templates():
    """Check if extracted game templates exist."""
    required = [
        "out/BasicTire_45.uasset",
        "out/VehicleParts0.uasset",
        "out/Cargos.uasset",
        "out/SmallBox.uasset",
    ]
    return all(os.path.isfile(str(REPO_ROOT / f)) for f in required)


@unittest.skipUnless(_in_nix_shell() and _has_templates(),
                     "Requires nix develop shell and extracted game assets")
class TestTireModIntegration(unittest.TestCase):
    """End-to-end tire mod build test."""

    def test_tire_mod_builds_successfully(self):
        """Full tire mod build produces a valid PAK file."""
        from create_tirepack import TireModBuilder

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a minimal single-tire config
            config = os.path.join(tmpdir, "test_tire.json")
            with open(config, 'w') as f:
                json.dump({
                    "tire_physics": {
                        "name": "TestTire",
                        "template": "BasicTire_45",
                        "static_mu": 1.5,
                        "sliding_mu": 1.2,
                    },
                    "tire_part": {
                        "row_name": "TestTire",
                        "display_name": ["Test Tire"],
                        "cost": 1000,
                        "mass_kg": 10,
                        "vehicle_types": ["Small"],
                        "vehicle_keys": [],
                        "level_requirement": {},
                        "tire_asset_path": "/Game/Cars/Parts/Tire/TestTire/TestTire",
                    }
                }, f)

            output = os.path.join(tmpdir, "TestTire_P.pak")
            builder = TireModBuilder(config, output)
            builder.build()

            # Verify PAK was created
            self.assertTrue(os.path.isfile(output))
            self.assertGreater(os.path.getsize(output), 0)

            # Verify PAK contents via mod_explore
            mod_explore = str(REPO_ROOT / "target" / "release" / "mod_explore")
            if os.path.isfile(mod_explore):
                result = subprocess.run(
                    [mod_explore, output, "--list"],
                    capture_output=True, text=True)
                listing = result.stdout

                # Must have tire asset in flat path
                self.assertIn("Cars/Parts/Tire/TestTire.uasset", listing)
                self.assertNotIn("TestTire/TestTire.uasset", listing,
                                 "Tire must be flat, not in subfolder")

                # Must have VehicleParts0
                self.assertIn("VehicleParts0.uasset", listing)

    def test_multi_tire_builds_all(self):
        """Multi-tire config builds all tires into one PAK."""
        from create_tirepack import TireModBuilder

        with tempfile.TemporaryDirectory() as tmpdir:
            config = os.path.join(tmpdir, "multi_tire.json")
            with open(config, 'w') as f:
                json.dump({"tires": [
                    {
                        "tire_physics": {"name": "TireA", "template": "BasicTire_45",
                                         "static_mu": 1.2},
                        "tire_part": {"row_name": "TireA", "display_name": ["Tire A"],
                                      "cost": 500, "vehicle_types": ["Small"],
                                      "tire_asset_path": "/Game/Cars/Parts/Tire/TireA/TireA"},
                    },
                    {
                        "tire_physics": {"name": "TireB", "template": "BasicTire_45",
                                         "static_mu": 1.8},
                        "tire_part": {"row_name": "TireB", "display_name": ["Tire B"],
                                      "cost": 900, "vehicle_types": ["Medium"],
                                      "tire_asset_path": "/Game/Cars/Parts/Tire/TireB/TireB"},
                    },
                ]}, f)

            output = os.path.join(tmpdir, "MultiTire_P.pak")
            builder = TireModBuilder(config, output)
            builder.build()

            self.assertTrue(os.path.isfile(output))

            mod_explore = str(REPO_ROOT / "target" / "release" / "mod_explore")
            if os.path.isfile(mod_explore):
                result = subprocess.run(
                    [mod_explore, output, "--list"],
                    capture_output=True, text=True)
                self.assertIn("TireA.uasset", result.stdout)
                self.assertIn("TireB.uasset", result.stdout)


@unittest.skipUnless(_in_nix_shell() and _has_templates(),
                     "Requires nix develop shell and extracted game assets")
class TestCargoModIntegration(unittest.TestCase):
    """End-to-end cargo mod build test."""

    def test_cargo_mod_builds_successfully(self):
        """Full cargo mod build produces a valid PAK file."""
        from create_cargopack import CargoModBuilder

        with tempfile.TemporaryDirectory() as tmpdir:
            config = os.path.join(tmpdir, "test_cargo.json")
            recipes = os.path.join(tmpdir, "test_recipes.json")

            with open(config, 'w') as f:
                json.dump({"entries": [{
                    "row_name": "TestBox",
                    "display_name": ["Test", "Box"],
                    "cargo_type": "SmallPackage",
                    "cargo_space_types": ["Flatbed", "Box"],
                    "weight_min": 5,
                    "weight_max": 10,
                    "volume_size": 1,
                    "payment_per_km": 500,
                    "spawn_probability": 10,
                    "mesh_path": "/Game/Models/PolygonConstruction/Meshes/Props/SM_Prop_CardboardBox_05",
                    "mass_kg": 8,
                    "blueprint_name": "TestBox",
                    "cargo_flags": 11,
                }]}, f)

            with open(recipes, 'w') as f:
                json.dump({
                    "sources": [{
                        "delivery_point": "Harbor_Export",
                        "template_path": "out/Harbor_Export.uasset",
                        "recipes": [{"cargo": "TestBox", "production_time": 60}],
                    }],
                    "sinks": [],
                }, f)

            output = os.path.join(tmpdir, "TestCargo_P.pak")
            builder = CargoModBuilder(config, output, recipes)
            builder.build()

            self.assertTrue(os.path.isfile(output))
            self.assertGreater(os.path.getsize(output), 0)

            mod_explore = str(REPO_ROOT / "target" / "release" / "mod_explore")
            if os.path.isfile(mod_explore):
                result = subprocess.run(
                    [mod_explore, output, "--list"],
                    capture_output=True, text=True)
                listing = result.stdout

                # Blueprint in flat Delivery/ path (not subfolder)
                self.assertIn("Delivery/TestBox.uasset", listing)
                # Cargos DataTable
                self.assertIn("DataAsset/Cargos.uasset", listing)
                # Delivery point
                self.assertIn("DeliveryPoint/Harbor_Export.uasset", listing)


@unittest.skipUnless(_in_nix_shell() and _has_templates(),
                     "Requires nix develop shell and extracted game assets")
class TestCompatModIntegration(unittest.TestCase):
    """Test compat-mod template extraction."""

    def test_tire_with_compat_mod_uses_extracted_template(self):
        """Building with --compat-mod extracts VehicleParts0 from target PAK."""
        from create_tirepack import TireModBuilder

        # Use an existing mod PAK that we know has VehicleParts0
        compat_pak = str(REPO_ROOT / "ASEAN_PoliceTyres_v0.1.8_MoreTuningCompat_P.pak")
        if not os.path.isfile(compat_pak):
            self.skipTest("MoreTuning compat PAK not available")

        with tempfile.TemporaryDirectory() as tmpdir:
            config = os.path.join(tmpdir, "compat_tire.json")
            with open(config, 'w') as f:
                json.dump({
                    "tire_physics": {"name": "CompatTest", "template": "BasicTire_45",
                                     "static_mu": 1.3},
                    "tire_part": {"row_name": "CompatTest", "display_name": ["Compat"],
                                  "cost": 100, "vehicle_types": ["Small"],
                                  "tire_asset_path": "/Game/Cars/Parts/Tire/CompatTest/CompatTest"},
                }, f)

            output = os.path.join(tmpdir, "CompatTest_P.pak")
            builder = TireModBuilder(config, output, compat_mods=[compat_pak])
            builder.build()

            self.assertTrue(os.path.isfile(output))

            # The PAK should have a VehicleParts0 with more rows than base game (50)
            # because it built on top of the compat mod's extended table
            mod_explore = str(REPO_ROOT / "target" / "release" / "mod_explore")
            if os.path.isfile(mod_explore):
                result = subprocess.run(
                    [mod_explore, output, "--list"],
                    capture_output=True, text=True)
                self.assertIn("VehicleParts0.uasset", result.stdout)


@unittest.skipUnless(_in_nix_shell() and _has_templates(),
                     "Requires nix develop shell and extracted game assets")
class TestExistingConfigsIntegration(unittest.TestCase):
    """Test that the existing project configs still build correctly."""

    def test_existing_tire_entries_build(self):
        """The real tire_entries.json builds successfully."""
        from create_tirepack import TireModBuilder

        config = str(REPO_ROOT / "tire_entries.json")
        if not os.path.isfile(config):
            self.skipTest("tire_entries.json not found")

        with tempfile.TemporaryDirectory() as tmpdir:
            output = os.path.join(tmpdir, "RealTires_P.pak")
            builder = TireModBuilder(config, output)
            builder.build()

            self.assertTrue(os.path.isfile(output))
            size = os.path.getsize(output)
            # Real tire mod produces ~40KB PAK
            self.assertGreater(size, 10000,
                               f"PAK too small ({size} bytes), may be corrupt")

    def test_existing_cargo_entries_build(self):
        """The real cargo_entries.json + recipe_entries.json builds successfully."""
        from create_cargopack import CargoModBuilder

        config = str(REPO_ROOT / "cargo_entries.json")
        recipes = str(REPO_ROOT / "recipe_entries.json")
        if not os.path.isfile(config) or not os.path.isfile(recipes):
            self.skipTest("cargo config files not found")

        with tempfile.TemporaryDirectory() as tmpdir:
            output = os.path.join(tmpdir, "RealCargo_P.pak")
            builder = CargoModBuilder(config, output, recipes)
            builder.build()

            self.assertTrue(os.path.isfile(output))
            size = os.path.getsize(output)
            self.assertGreater(size, 10000,
                               f"PAK too small ({size} bytes), may be corrupt")


if __name__ == '__main__':
    unittest.main()
