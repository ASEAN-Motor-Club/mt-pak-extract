using System;
using System.IO;
using UAssetAPI;
using UAssetAPI.UnrealTypes;
using UAssetAPI.Unversioned;

namespace AssetEditor
{
    class Program
    {
        static string? RootDir;
        static Usmap? Mappings;
        
        static void Main(string[] args)
        {
            Console.WriteLine("=== MotorTown Asset Editor (UAssetAPI) ===");
            Console.WriteLine();
            
            // Determine root directory
            var currentDir = Directory.GetCurrentDirectory();
            // Case 1: Run from project root (mt-pak-extract)
            // Case 2: Run from csharp/AssetEditor
            RootDir = File.Exists(Path.Combine(currentDir, "Mappings.usmap")) 
                ? currentDir 
                : Path.GetFullPath(Path.Combine(currentDir, "..", ".."));
            
            var usmapPath = Path.Combine(RootDir, "Mappings.usmap");
            
            if (!File.Exists(usmapPath))
            {
                Console.WriteLine($"Error: Mappings file not found at {usmapPath}");
                return;
            }
            
            // Load mappings once
            Console.WriteLine("Loading mappings...");
            Mappings = new Usmap(usmapPath);
            Console.WriteLine($"Loaded {Mappings.Schemas.Count} schemas");
            Console.WriteLine();
            
            // Parse command
            if (args.Length == 0)
            {
                ShowUsage();
                return;
            }
            
            string command = args[0];
            
            switch (command)
            {
                case "verify-binary":
                    if (args.Length < 2)
                    {
                        Console.WriteLine("Usage: verify-binary <asset.uasset>");
                        return;
                    }
                    VerifyBinaryEquality(args[1]);
                    break;
                    
               case "add-cargo":
                    if (args.Length < 2)
                    {
                        Console.WriteLine("Usage: add-cargo <config.yaml>");
                        return;
                    }
                    AddCargoCommand(args[1]);
                    break;
                    
                case "list-cargos":
                    if (args.Length < 2)
                    {
                        Console.WriteLine("Usage: list-cargos <Cargos.uasset>");
                        return;
                    }
                    ListCargosCommand(args[1]);
                    break;
                    
                case "add-production":
                    if (args.Length < 2)
                    {
                        Console.WriteLine("Usage: add-production <config.yaml>");
                        return;
                    }
                    AddProductionCommand(args[1]);
                    break;
                    
                case "list-productions":
                    if (args.Length < 2)
                    {
                        Console.WriteLine("Usage: list-productions <Factory.uasset>");
                        return;
                    }
                    ListProductionsCommand(args[1]);
                    break;
                    
                default:
                    Console.WriteLine($"Unknown command: {command}");
                    ShowUsage();
                    break;
            }
        }
        
        static void ShowUsage()
        {
            Console.WriteLine("Usage: dotnet run -- <command> [args]");
            Console.WriteLine();
            Console.WriteLine("Commands:");
            Console.WriteLine("  verify-binary <asset.uasset>          - Test binary equality (lossless read/write)");
            Console.WriteLine("  add-cargo <config.yaml>               - Add new cargo to Cargos.uasset");
            Console.WriteLine("  list-cargos <Cargos.uasset>           - List all cargos in DataTable");
            Console.WriteLine("  add-production <config.yaml>          - Add production configs to factory blueprint");
            Console.WriteLine("  list-productions <Factory.uasset>     - List all production configs");
            Console.WriteLine();
        }
        
        static void VerifyBinaryEquality(string assetPath)
        {
            if (!Path.IsPathRooted(assetPath))
            {
                assetPath = Path.Combine(RootDir!, assetPath);
            }
            
            if (!File.Exists(assetPath))
            {
                Console.WriteLine($"Error: File not found: {assetPath}");
                return;
            }
            
            Console.WriteLine($"Testing binary equality for: {Path.GetFileName(assetPath)}");
            Console.WriteLine();
            
            try
            {
                // Load asset
                var asset = new UAsset(assetPath, EngineVersion.VER_UE5_5, Mappings);
                Console.WriteLine($"✓ Loaded asset successfully");
                Console.WriteLine($"  Exports: {asset.Exports.Count}");
                Console.WriteLine($"  Imports: {asset.Imports.Count}");
                Console.WriteLine($"  Unversioned Properties: {asset.HasUnversionedProperties}");
                Console.WriteLine();
                
                // Test binary equality
                Console.WriteLine("Testing binary equality...");
                bool isEqual = asset.VerifyBinaryEquality();
                
                if (isEqual)
                {
                    Console.WriteLine("✅ PASS: Binary equality maintained!");
                    Console.WriteLine();
                    Console.WriteLine("This asset can be safely modified with UAssetAPI.");
                    Console.WriteLine("Read → Write produces byte-identical output.");
                }
                else
                {
                    Console.WriteLine("❌ FAIL: Binary equality NOT maintained");
                    Console.WriteLine();
                    Console.WriteLine("⚠️  WARNING: UAssetAPI may not serialize this asset correctly.");
                    Console.WriteLine("Modifications may corrupt the file or cause game crashes.");
                    Console.WriteLine();
                    Console.WriteLine("Recommended actions:");
                    Console.WriteLine("  1. Report this asset to UAssetAPI developers");
                    Console.WriteLine("  2. Use with extreme caution");
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine($"❌ ERROR: {ex.Message}");
                Console.WriteLine();
                Console.WriteLine(ex.StackTrace);
            }
        }
        
        static void AddCargoCommand(string configPath)
        {
            if (!Path.IsPathRooted(configPath))
            {
                configPath = Path.Combine(RootDir!, configPath);
            }
            
            if (!File.Exists(configPath))
            {
                Console.WriteLine($"Error: Config file not found: {configPath}");
                return;
            }
            
            Console.WriteLine($"Loading cargo config from: {Path.GetFileName(configPath)}");
            var cargoConfig = CargoConfig.LoadFromYaml(configPath);
            Console.WriteLine($"  Cargo ID: {cargoConfig.CargoId}");
            Console.WriteLine();
            
            // Find or verify Cargos.uasset exists
            string cargosPath = Path.Combine(RootDir!, "out", "Cargos.uasset");
            if (!File.Exists(cargosPath))
            {
                Console.WriteLine($"Error: Cargos.uasset not found at {cargosPath}");
                Console.WriteLine("Run the extractor first: cargo run -- --config assets.json");
                return;
            }
            
            try
            {
                // Load asset
                var asset = new UAsset(cargosPath, EngineVersion.VER_UE5_5, Mappings);
                Console.WriteLine($"✓ Loaded Cargos.uasset ({asset.Exports.Count} exports)");
                
                // Add cargo
                CargoEditor.AddCargo(asset, cargoConfig);
                
                // Save modified asset
                string outputPath = Path.Combine(RootDir!, "out", "Cargos_modified.uasset");
                asset.Write(outputPath);
                Console.WriteLine();
                Console.WriteLine($"✅ Saved modified asset: {Path.GetFileName(outputPath)}");
                Console.WriteLine();
                Console.WriteLine("Next steps:");
                Console.WriteLine("  1. Verify with: dotnet run -- verify-binary out/Cargos_modified.uasset");
                Console.WriteLine("  2. Repack into PAK (coming soon)");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"❌ ERROR: {ex.Message}");
                Console.WriteLine(ex.StackTrace);
            }
        }
        
        static void ListCargosCommand(string assetPath)
        {
            if (!Path.IsPathRooted(assetPath))
            {
                assetPath = Path.Combine(RootDir!, assetPath);
            }
            
            if (!File.Exists(assetPath))
            {
                Console.WriteLine($"Error: File not found: {assetPath}");
                return;
            }
            
            try
            {
                var asset = new UAsset(assetPath, EngineVersion.VER_UE5_5, Mappings);
                CargoEditor.ListCargos(asset);
            }
            catch (Exception ex)
            {
                Console.WriteLine($"❌ ERROR: {ex.Message}");
            }
        }
        
        static void AddProductionCommand(string configPath)
        {
            if (!Path.IsPathRooted(configPath))
            {
                configPath = Path.Combine(RootDir!, configPath);
            }
            
            if (!File.Exists(configPath))
            {
                Console.WriteLine($"Error: Config file not found: {configPath}");
                return;
            }
            
            Console.WriteLine($"Loading production config from: {Path.GetFileName(configPath)}");
            var prodConfig = ProductionConfig.LoadFromYaml(configPath);
            Console.WriteLine($"  Factory: {prodConfig.FactoryBlueprint}");
            Console.WriteLine($"  Recipes: {prodConfig.ProductionConfigs.Count}");
            Console.WriteLine();
            
            // Find factory blueprint
            string factoryPath = Path.Combine(RootDir!, "out", $"{prodConfig.FactoryBlueprint}.uasset");
            if (!File.Exists(factoryPath))
            {
                Console.WriteLine($"Error: Factory blueprint not found: {factoryPath}");
                Console.WriteLine("Run the extractor first to extract factory blueprints");
                return;
            }
            
            try
            {
                // Load blueprint
                var asset = new UAsset(factoryPath, EngineVersion.VER_UE5_5, Mappings);
                Console.WriteLine($"✓ Loaded {prodConfig.FactoryBlueprint}.uasset ({asset.Exports.Count} exports)");
                Console.WriteLine();
                
                // Add production configs
                ProductionEditor.AddProductionConfigs(asset, prodConfig);
                
                // Save modified asset
                string outputPath = Path.Combine(RootDir!, "out", $"{prodConfig.FactoryBlueprint}_modified.uasset");
                asset.Write(outputPath);
                Console.WriteLine();
                Console.WriteLine($"✅ Saved modified blueprint: {Path.GetFileName(outputPath)}");
                Console.WriteLine();
                Console.WriteLine("Next steps:");
                Console.WriteLine($"  1. Verify with: dotnet run -- list-productions out/{prodConfig.FactoryBlueprint}_modified.uasset");
                Console.WriteLine("  2. Repack into PAK (Phase 3)");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"❌ ERROR: {ex.Message}");
                Console.WriteLine(ex.StackTrace);
            }
        }
        
        static void ListProductionsCommand(string assetPath)
        {
            if (!Path.IsPathRooted(assetPath))
            {
                assetPath = Path.Combine(RootDir!, assetPath);
            }
            
            if (!File.Exists(assetPath))
            {
                Console.WriteLine($"Error: File not found: {assetPath}");
                return;
            }
            
            try
            {
                var asset = new UAsset(assetPath, EngineVersion.VER_UE5_5, Mappings);
                Console.WriteLine($"Factory: {Path.GetFileNameWithoutExtension(assetPath)}");
                Console.WriteLine();
                ProductionEditor.ListProductionConfigs(asset);
            }
            catch (Exception ex)
            {
                Console.WriteLine($"❌ ERROR: {ex.Message}");
            }
        }
    }
}
