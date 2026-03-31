using System;
using System.IO;
using System.Text.Json;
using System.Collections.Generic;
using System.Linq;
using UAssetAPI;
using UAssetAPI.UnrealTypes;
using UAssetAPI.Unversioned;
using UAssetAPI.ExportTypes;
using UAssetAPI.PropertyTypes.Objects;
using UAssetAPI.PropertyTypes.Structs;

class Program
{
    static string? RootDir;
    static Usmap? Mappings;
    
    static void Main(string[] args)
    {
        Console.WriteLine("=== MotorTown UAsset Tool (UAssetAPI) ===");
        
        // Determine root directory (two levels up from csharp/CargoExtractor)
        RootDir = Path.GetFullPath(Path.Combine("..", ".."));
        var usmapPath = Path.Combine(RootDir, "Mappings.usmap");
        
        // Check for modes
        bool batchMode = args.Contains("--batch");
        bool batchMapsMode = args.Contains("--batch-maps");
        bool modifyDecalsMode = args.Contains("--add-decals");
        bool addCargosMode = args.Contains("--add-cargos");
        bool patchBlueprintMode = args.Contains("--patch-blueprint");
        bool addRecipesMode = args.Contains("--add-recipes");
        bool patchTireMode = args.Contains("--patch-tire");
        bool addTirePartsMode = args.Contains("--add-tire-parts");
        bool dumpMode = args.Contains("--dump");
        
        Console.WriteLine($"Usage: dotnet run -- [--batch] [--batch-maps] [--add-decals ...] [--add-cargos ...] [--patch-blueprint ...] [--add-recipes ...] [--patch-tire ...] [--add-tire-parts ...] [path/to/asset.uasset]");
        Console.WriteLine();
        
        // Check mappings exist
        if (!File.Exists(usmapPath))
        {
            Console.WriteLine($"Error: Mappings file not found at {usmapPath}");
            return;
        }
        
        // Load mappings once
        Console.WriteLine("Loading mappings...");
        Mappings = new Usmap(usmapPath);
        Console.WriteLine($"Loaded {Mappings.Schemas.Count} schemas");
        
        if (batchMapsMode)
        {
            ProcessBatchMaps();
        }
        else if (batchMode)
        {
            ProcessBatch();
        }
        else if (modifyDecalsMode)
        {
            var configIdx = Array.IndexOf(args, "--add-decals");
            var configPath = args.ElementAtOrDefault(configIdx + 1) ?? "decal_entries.json";
            var templatePath = args.ElementAtOrDefault(configIdx + 2) ?? Path.Combine(RootDir, "Decals.uasset");
            var outputDir = args.ElementAtOrDefault(configIdx + 3) ?? RootDir;
            ModifyDecals(configPath, templatePath, outputDir);
        }
        else if (addCargosMode)
        {
            // --add-cargos config.json template.uasset output_dir
            var idx = Array.IndexOf(args, "--add-cargos");
            var configPath = args.ElementAtOrDefault(idx + 1) ?? "cargo_entries.json";
            var templatePath = args.ElementAtOrDefault(idx + 2) ?? Path.Combine(RootDir, "out", "Cargos.uasset");
            var outputDir = args.ElementAtOrDefault(idx + 3) ?? RootDir;
            ModifyCargos(configPath, templatePath, outputDir);
        }
        else if (patchBlueprintMode)
        {
            // --patch-blueprint config.json template.uasset output_dir
            var idx = Array.IndexOf(args, "--patch-blueprint");
            var configPath = args.ElementAtOrDefault(idx + 1) ?? "cargo_entries.json";
            var templatePath = args.ElementAtOrDefault(idx + 2) ?? Path.Combine(RootDir, "out", "SmallBox.uasset");
            var outputDir = args.ElementAtOrDefault(idx + 3) ?? RootDir;
            PatchBlueprints(configPath, templatePath, outputDir);
        }
        else if (addRecipesMode)
        {
            // --add-recipes config.json output_dir
            var idx = Array.IndexOf(args, "--add-recipes");
            var configPath = args.ElementAtOrDefault(idx + 1) ?? "recipe_entries.json";
            var outputDir = args.ElementAtOrDefault(idx + 2) ?? RootDir;
            AddRecipes(configPath, outputDir);
        }
        else if (patchTireMode)
        {
            // --patch-tire config.json template.uasset output_dir
            var idx = Array.IndexOf(args, "--patch-tire");
            var configPath = args.ElementAtOrDefault(idx + 1) ?? "tire_entries.json";
            var templatePath = args.ElementAtOrDefault(idx + 2) ?? Path.Combine(RootDir, "out", "BasicTire_45.uasset");
            var outputDir = args.ElementAtOrDefault(idx + 3) ?? RootDir;
            PatchTire(configPath, templatePath, outputDir);
        }
        else if (addTirePartsMode)
        {
            // --add-tire-parts config.json template.uasset output_dir
            var idx = Array.IndexOf(args, "--add-tire-parts");
            var configPath = args.ElementAtOrDefault(idx + 1) ?? "tire_entries.json";
            var templatePath = args.ElementAtOrDefault(idx + 2) ?? Path.Combine(RootDir, "out", "VehicleParts.uasset");
            var outputDir = args.ElementAtOrDefault(idx + 3) ?? RootDir;
            AddTireParts(configPath, templatePath, outputDir);
        }
        else if (dumpMode)
        {
            // Dump NameMap, imports, and export details
            var idx = Array.IndexOf(args, "--dump");
            var dumpPath = args.ElementAtOrDefault(idx + 1) ?? Path.Combine(RootDir, "Cargos.uasset");
            if (!Path.IsPathRooted(dumpPath)) dumpPath = Path.Combine(RootDir, dumpPath);
            
            var dumpAsset = new UAsset(dumpPath, EngineVersion.VER_UE5_5, Mappings);
            Console.WriteLine($"\n=== Dump: {Path.GetFileName(dumpPath)} ===");
            Console.WriteLine($"  FolderName: {dumpAsset.FolderName}");
            Console.WriteLine($"  PackageGuid: {dumpAsset.PackageGuid}");
            
            Console.WriteLine($"\n  --- NameMap ({dumpAsset.GetNameMapIndexList().Count} entries) ---");
            for (int i = 0; i < dumpAsset.GetNameMapIndexList().Count; i++)
            {
                Console.WriteLine($"  Name[{i}]: '{dumpAsset.GetNameReference(i)}'");
            }
            
            Console.WriteLine($"\n  --- Imports ({dumpAsset.Imports.Count}) ---");
            for (int i = 0; i < dumpAsset.Imports.Count; i++)
            {
                var imp = dumpAsset.Imports[i];
                Console.WriteLine($"  Import[{i}]: ClassPkg={imp.ClassPackage}, Class={imp.ClassName}, Outer={imp.OuterIndex}, Name={imp.ObjectName}");
            }
            
            Console.WriteLine($"\n  --- Exports ({dumpAsset.Exports.Count}) ---");
            for (int i = 0; i < dumpAsset.Exports.Count; i++)
            {
                var exp = dumpAsset.Exports[i];
                Console.WriteLine($"  Export[{i}]: Name={exp.ObjectName}, Class={exp.GetExportClassType()}, Outer={exp.OuterIndex}");
            }
        }
        else
        {
            // Single file mode
            string uassetPath;
            if (args.Length > 0 && !args[0].StartsWith("--"))
            {
                uassetPath = args[0];
                if (!Path.IsPathRooted(uassetPath))
                {
                    uassetPath = Path.Combine(RootDir, uassetPath);
                }
            }
            else
            {
                uassetPath = Path.Combine(RootDir, "Cargos.uasset");
            }
            
            ProcessSingleFile(uassetPath, RootDir);
        }
    }
    
    // ========================================================================
    // --add-cargos: Deep-clone existing rows in Cargos DataTable
    // ========================================================================
    static void ModifyCargos(string configPath, string templatePath, string outputDir)
    {
        if (!File.Exists(configPath))
        {
            Console.WriteLine($"Error: Config not found: {configPath}");
            return;
        }
        if (!File.Exists(templatePath))
        {
            Console.WriteLine($"Error: Template not found: {templatePath}");
            return;
        }
        
        var configJson = File.ReadAllText(configPath);
        using var doc = JsonDocument.Parse(configJson);
        var entries = doc.RootElement.GetProperty("entries");
        
        Console.WriteLine($"Loading Cargos template: {Path.GetFileName(templatePath)}");
        var asset = new UAsset(templatePath, EngineVersion.VER_UE5_5, Mappings);
        
        var dtExport = FindDataTable(asset);
        if (dtExport == null) return;
        
        Console.WriteLine($"Existing rows: {dtExport.Table.Data.Count}");
        
        // Get a template row to deep-clone from (use last row)
        var templateRow = dtExport.Table.Data[^1];
        
        int added = 0;
        foreach (var entry in entries.EnumerateArray())
        {
            var rowName = entry.GetProperty("row_name").GetString()!;
            var displayName = entry.GetProperty("display_name");
            var cargoType = entry.GetProperty("cargo_type").GetString()!;
            var blueprintName = entry.GetProperty("blueprint_name").GetString()!;
            var weightMin = entry.GetProperty("weight_min").GetSingle();
            var weightMax = entry.GetProperty("weight_max").GetSingle();
            var paymentPerKm = entry.GetProperty("payment_per_km").GetSingle();
            var spawnProbability = entry.GetProperty("spawn_probability").GetInt32();
            var massKg = entry.GetProperty("mass_kg").GetSingle();
            // CargoFlags: 11 = standard loadable cargo (forklift/crane compatible)
            var cargoFlags = entry.TryGetProperty("cargo_flags", out var cfProp) ? cfProp.GetInt32() : 11;
            var numCargoMin = entry.TryGetProperty("num_cargo_min", out var ncMinProp) ? ncMinProp.GetInt32() : 0;
            var numCargoMax = entry.TryGetProperty("num_cargo_max", out var ncMaxProp) ? ncMaxProp.GetInt32() : 1;
            var allowStacking = entry.TryGetProperty("allow_stacking", out var asProp) && asProp.GetBoolean();
            
            // Deep-clone the template row
            var newRow = (StructPropertyData)templateRow.Clone();
            newRow.Name = FName.FromString(asset, rowName);
            
            // Modify the cloned row's properties
            foreach (var prop in newRow.Value)
            {
                var propName = prop.Name.Value.Value;
                
                switch (propName)
                {
                    case "bDepcreated":
                        ((BoolPropertyData)prop).Value = false;
                        break;
                        
                    case "Name":
                        SetLocalizationGuid(prop);
                        break;
                        
                    case "Name2":
                        SetDisplayName(prop, displayName, asset);
                        break;
                        
                    case "CargoType":
                        if (prop is EnumPropertyData ctProp)
                        {
                            // Unversioned enums: use bare value name with DefineDummy
                            ctProp.Value = FName.DefineDummy(asset, cargoType);
                        }
                        break;
                        
                    case "CargoSpaceTypes":
                        if (prop is ArrayPropertyData cstArr && entry.TryGetProperty("cargo_space_types", out var cstJson))
                        {
                            SetEnumArray(cstArr, cstJson, asset, "EMTCargoSpaceType");
                        }
                        break;
                        
                    case "WeightRange":
                        if (prop is StructPropertyData wrStruct)
                        {
                            // Vector2D — look for X/Y or WeightRange sub-struct
                            SetVector2D(wrStruct, weightMin, weightMax, asset, "WeightRange");
                        }
                        break;
                        
                    case "VolumeSize":
                        SetNumericProperty(prop, 1);
                        break;
                        
                    case "SpawnProbability":
                        SetNumericProperty(prop, spawnProbability);
                        break;
                        
                    case "NumCargoMin":
                        SetNumericProperty(prop, numCargoMin);
                        break;
                        
                    case "NumCargoMax":
                        SetNumericProperty(prop, numCargoMax);
                        break;
                        
                    case "PaymentPer1Km":
                        SetNumericProperty(prop, paymentPerKm);
                        break;
                        
                    case "PaymentPer1KmMultiplierByMaxWeight":
                        SetNumericProperty(prop, 2.0f);
                        break;
                    
                    case "PaymentSqrtRatio":
                        SetNumericProperty(prop, 1.0f);
                        break;
                        
                    case "ActorClass":
                        // ActorClass is ObjectPropertyData (Import reference)
                        // Add a Package + BlueprintGeneratedClass import chain
                        if (prop is ObjectPropertyData actorProp)
                        {
                            var pkgPath = $"/Game/Objects/Mission/Delivery/{blueprintName}";
                            var (_, classImportIdx) = AddImportChain(
                                asset, "/Script/Engine", "BlueprintGeneratedClass",
                                pkgPath, $"{blueprintName}_C"
                            );
                            actorProp.Value = FPackageIndex.FromImport(classImportIdx - 1);
                        }
                        break;
                        
                    case "GameplayTags":
                        // Clear gameplay tags
                        if (prop is StructPropertyData tagsStruct)
                        {
                            foreach (var sp in tagsStruct.Value)
                            {
                                if (sp is GameplayTagContainerPropertyData tagContainer)
                                {
                                    tagContainer.Value = Array.Empty<FName>();
                                }
                            }
                        }
                        break;
                        
                    case "bAllowStacking":
                        ((BoolPropertyData)prop).Value = allowStacking;
                        break;
                        
                    case "bUseDamage":
                        ((BoolPropertyData)prop).Value = false;
                        break;
                        
                    case "Fragile":
                        SetNumericProperty(prop, 0);
                        break;
                        
                    case "CargoFlags":
                        SetNumericProperty(prop, cargoFlags);
                        break;
                        
                    case "DumpCargoSurfaceMesh":
                    case "DumpCargoSurfaceMaterial":
                    case "DumpPileActorClass":
                        if (prop is SoftObjectPropertyData softNull)
                        {
                            softNull.Value = new FSoftObjectPath(
                                new FTopLevelAssetPath(new FName(asset, 0), new FName(asset, 0)),
                                null
                            );
                        }
                        else if (prop is ObjectPropertyData objNull)
                        {
                            objNull.Value = FPackageIndex.FromRawIndex(0);
                        }
                        break;
                        
                    case "MinDeliveryDistance":
                    case "MaxDeliveryDistance":
                    case "BaseTimeSeconds":
                    case "TimerBySpeedKPH":
                    case "TimerByRoadSpeedLimitRatio":
                    case "BasePayment":
                    case "PaymentSqrtRatioMinCapcity":
                    case "MaxDamagePaymentMultiplier":
                    case "DamageBonusMultiplier":
                    case "ManualLoadingPayment":
                        // Leave cloned defaults (usually 0)
                        break;
                        
                    case "bTimer":
                    case "bHoldingOffsetUsingItemBounds":
                        ((BoolPropertyData)prop).Value = false;
                        break;
                        
                    case "InTimeTipRange":
                        // Leave cloned defaults
                        break;
                        
                    case "Colors":
                        if (prop is ArrayPropertyData colorsArr)
                        {
                            colorsArr.Value = Array.Empty<PropertyData>();
                        }
                        break;
                }
            }
            
            // Add row to DataTable
            dtExport.Table.Data.Add(newRow);
            Console.WriteLine($"  Added cargo: {rowName} (CargoType={cargoType}, Weight={weightMin}-{weightMax}kg)");
            added++;
        }
        
        Console.WriteLine($"\nAdded {added} rows. Total rows: {dtExport.Table.Data.Count}");
        
        // Write output
        Directory.CreateDirectory(outputDir);
        var outputPath = Path.Combine(outputDir, "Cargos.uasset");
        asset.Write(outputPath);
        Console.WriteLine($"Written: Cargos.uasset + Cargos.uexp to {outputDir}");
    }
    
    // ========================================================================
    // --patch-blueprint: Clone SmallBox.uasset into new cargo blueprints
    // ========================================================================
    static void PatchBlueprints(string configPath, string templatePath, string outputDir)
    {
        if (!File.Exists(configPath))
        {
            Console.WriteLine($"Error: Config not found: {configPath}");
            return;
        }
        if (!File.Exists(templatePath))
        {
            Console.WriteLine($"Error: Template not found: {templatePath}");
            return;
        }
        
        var configJson = File.ReadAllText(configPath);
        using var doc = JsonDocument.Parse(configJson);
        var entries = doc.RootElement.GetProperty("entries");
        
        foreach (var entry in entries.EnumerateArray())
        {
            var blueprintName = entry.GetProperty("blueprint_name").GetString()!;
            var meshPath = entry.GetProperty("mesh_path").GetString()!;
            var massKg = entry.GetProperty("mass_kg").GetSingle();
            
            Console.WriteLine($"\nPatching blueprint: {blueprintName}");
            Console.WriteLine($"  Template: {Path.GetFileName(templatePath)}");
            Console.WriteLine($"  Mesh: {meshPath}");
            Console.WriteLine($"  Mass: {massKg}kg");
            
            // Load fresh copy of template for each blueprint
            var asset = new UAsset(templatePath, EngineVersion.VER_UE5_5, Mappings);
            
            var oldName = Path.GetFileNameWithoutExtension(templatePath); // "SmallBox"
            var newAssetPath = $"/Game/Objects/Mission/Delivery/{blueprintName}";
            var oldAssetPath = $"/Game/Objects/Mission/Delivery/{oldName}";
            
            // 0. Patch internal package identity (FolderName) — CRITICAL
            // Without this, the engine resolves the blueprint as the template's class
            asset.FolderName = FString.FromString(newAssetPath);
            
            // NOTE: Do NOT modify NameMap entries directly (SetNameReference)
            // — this corrupts hash integrity and breaks .uexp deserialization.
            // FName.FromString() used below in import/export renaming safely adds
            // new entries. Stale old entries remain but are harmless.
            
            // Update imports that reference old package path
            for (int i = 0; i < asset.Imports.Count; i++)
            {
                var imp = asset.Imports[i];
                if (imp.ObjectName.Value.Value.Contains(oldName))
                {
                    imp.ObjectName = FName.FromString(asset, 
                        imp.ObjectName.Value.Value.Replace(oldName, blueprintName));
                }
            }
            
            // 1. Rename exports
            foreach (var export in asset.Exports)
            {
                var exportName = export.ObjectName.Value.Value;
                if (exportName.Contains(oldName))
                {
                    var newExportName = exportName.Replace(oldName, blueprintName);
                    export.ObjectName = FName.FromString(asset, newExportName);
                    Console.WriteLine($"  Renamed export: {exportName} -> {newExportName}");
                }
            }
            
            // 2. Replace StaticMesh import chain
            // Find the existing static mesh import and its parent package import
            int meshImportIdx = -1;
            int meshPkgImportIdx = -1;
            for (int i = 0; i < asset.Imports.Count; i++)
            {
                var imp = asset.Imports[i];
                if (imp.ClassName.Value.Value == "StaticMesh")
                {
                    meshImportIdx = i;
                    // Find the package import that this mesh's Outer points to
                    if (imp.OuterIndex.Index < 0)
                    {
                        meshPkgImportIdx = -imp.OuterIndex.Index - 1;
                    }
                }
            }
            
            if (meshImportIdx >= 0)
            {
                var meshName = Path.GetFileName(meshPath);  // "Spider_L"
                
                // Replace the mesh package import IN-PLACE (no orphaned imports)
                if (meshPkgImportIdx >= 0 && meshPkgImportIdx < asset.Imports.Count)
                {
                    asset.Imports[meshPkgImportIdx].ObjectName = FName.FromString(asset, meshPath);
                    Console.WriteLine($"  Replaced mesh package: {meshPath}");
                }
                
                // Replace the mesh import IN-PLACE  
                asset.Imports[meshImportIdx].ObjectName = FName.FromString(asset, meshName);
                // OuterIndex already points to the package import we just updated
                
                Console.WriteLine($"  Replaced mesh import: {meshName}");
            }
            
            // 3. Patch MassInKgOverride
            foreach (var export in asset.Exports)
            {
                if (export is NormalExport normalExport && 
                    export.GetExportClassType()?.Value?.Value == "StaticMeshComponent")
                {
                    foreach (var prop in normalExport.Data)
                    {
                        if (prop.Name.Value.Value == "BodyInstance" && prop is StructPropertyData bodyInstance)
                        {
                            foreach (var bp in bodyInstance.Value)
                            {
                                if (bp.Name.Value.Value == "MassInKgOverride" && bp is FloatPropertyData massProp)
                                {
                                    massProp.Value = massKg;
                                    Console.WriteLine($"  Set MassInKgOverride: {massKg}");
                                }
                            }
                        }
                    }
                }
            }
            
            // NOTE: Adding collision components via cross-asset Clone() crashes the game
            // due to incompatible unversioned header schemas. Instead, use meshes that
            // already have built-in collision (any standalone prop mesh, NOT vehicle parts).
            
            // Write output
            var bpOutputDir = Path.Combine(outputDir, blueprintName);
            Directory.CreateDirectory(bpOutputDir);
            var outputPath = Path.Combine(bpOutputDir, $"{blueprintName}.uasset");
            asset.Write(outputPath);
            Console.WriteLine($"  Written: {blueprintName}.uasset + .uexp to {bpOutputDir}");
        }
    }
    
    // ========================================================================
    // --add-recipes: Deep-clone ProductionConfigs in delivery point blueprints
    // Supports sources, sinks, transforms, and storage sections.
    // Groups all entries by delivery_point to avoid overwrite conflicts.
    // ========================================================================
    
    enum RecipeMode { Source, Sink, Transform }
    
    // Collected work items for a single delivery point
    class DeliveryPointWork
    {
        public string TemplatePath { get; set; } = "";
        public List<(RecipeMode Mode, JsonElement Recipe)> Recipes { get; } = new();
        public List<JsonElement> StorageEntries { get; } = new();
    }
    
    static void AddRecipes(string configPath, string outputDir)
    {
        if (!File.Exists(configPath))
        {
            Console.WriteLine($"Error: Config not found: {configPath}");
            return;
        }
        
        var configJson = File.ReadAllText(configPath);
        using var doc = JsonDocument.Parse(configJson);
        
        // Group all work by delivery_point name
        var workByDp = new Dictionary<string, DeliveryPointWork>();
        
        DeliveryPointWork GetOrCreate(string dpName, string templatePath)
        {
            if (!workByDp.TryGetValue(dpName, out var work))
            {
                work = new DeliveryPointWork { TemplatePath = templatePath };
                workByDp[dpName] = work;
            }
            return work;
        }
        
        string ResolveTemplatePath(JsonElement entry)
        {
            var tp = entry.GetProperty("template_path").GetString()!;
            return Path.IsPathRooted(tp) ? tp : Path.Combine(RootDir!, tp);
        }
        
        // Collect sources
        if (doc.RootElement.TryGetProperty("sources", out var sources))
        {
            foreach (var source in sources.EnumerateArray())
            {
                var dpName = source.GetProperty("delivery_point").GetString()!;
                var work = GetOrCreate(dpName, ResolveTemplatePath(source));
                foreach (var recipe in source.GetProperty("recipes").EnumerateArray())
                    work.Recipes.Add((RecipeMode.Source, recipe));
            }
        }
        
        // Collect sinks
        if (doc.RootElement.TryGetProperty("sinks", out var sinks))
        {
            foreach (var sink in sinks.EnumerateArray())
            {
                var dpName = sink.GetProperty("delivery_point").GetString()!;
                var work = GetOrCreate(dpName, ResolveTemplatePath(sink));
                foreach (var recipe in sink.GetProperty("recipes").EnumerateArray())
                    work.Recipes.Add((RecipeMode.Sink, recipe));
            }
        }
        
        // Collect transforms
        if (doc.RootElement.TryGetProperty("transforms", out var transforms))
        {
            foreach (var transform in transforms.EnumerateArray())
            {
                var dpName = transform.GetProperty("delivery_point").GetString()!;
                var work = GetOrCreate(dpName, ResolveTemplatePath(transform));
                foreach (var recipe in transform.GetProperty("recipes").EnumerateArray())
                    work.Recipes.Add((RecipeMode.Transform, recipe));
            }
        }
        
        // Collect storage
        if (doc.RootElement.TryGetProperty("storage", out var storage))
        {
            foreach (var storageEntry in storage.EnumerateArray())
            {
                var dpName = storageEntry.GetProperty("delivery_point").GetString()!;
                var work = GetOrCreate(dpName, ResolveTemplatePath(storageEntry));
                foreach (var entry in storageEntry.GetProperty("entries").EnumerateArray())
                    work.StorageEntries.Add(entry);
            }
        }
        
        // Process each delivery point once
        foreach (var (dpName, work) in workByDp)
        {
            Console.WriteLine($"\nProcessing delivery point: {dpName}");
            ProcessDeliveryPoint(work.TemplatePath, dpName, work.Recipes, work.StorageEntries, outputDir);
        }
    }
    
    static void ProcessDeliveryPoint(
        string templatePath, string dpName,
        List<(RecipeMode Mode, JsonElement Recipe)> recipes,
        List<JsonElement> storageEntries,
        string outputDir)
    {
        if (!File.Exists(templatePath))
        {
            Console.WriteLine($"  Error: Template not found: {templatePath}");
            return;
        }
        
        Console.WriteLine($"  Loading: {Path.GetFileName(templatePath)}");
        var asset = new UAsset(templatePath, EngineVersion.VER_UE5_5, Mappings);
        
        // Find the Default__ CDO export
        NormalExport? cdoExport = null;
        foreach (var export in asset.Exports)
        {
            if (export is NormalExport ne && export.ObjectName.Value.Value.StartsWith("Default__"))
            {
                cdoExport = ne;
                break;
            }
        }
        
        if (cdoExport == null)
        {
            Console.WriteLine($"  Error: No Default__ CDO export found");
            return;
        }
        
        // Process production config recipes
        if (recipes.Count > 0)
        {
            AddProductionConfigs(asset, cdoExport, dpName, recipes);
        }
        
        // Process storage entries
        if (storageEntries.Count > 0)
        {
            AddStorageConfigs(asset, cdoExport, dpName, storageEntries);
        }
        
        // Resolve ancestries for new structs
        asset.ResolveAncestries();
        
        // Write output — single write per delivery point
        Directory.CreateDirectory(outputDir);
        var outputPath = Path.Combine(outputDir, $"{dpName}.uasset");
        asset.Write(outputPath);
        Console.WriteLine($"  Written: {dpName}.uasset + .uexp to {outputDir}");
    }
    
    static void AddProductionConfigs(
        UAsset asset, NormalExport cdoExport, string dpName,
        List<(RecipeMode Mode, JsonElement Recipe)> recipes)
    {
        ArrayPropertyData? productionConfigsProp = null;
        foreach (var prop in cdoExport.Data)
        {
            if (prop.Name.Value.Value == "ProductionConfigs" && prop is ArrayPropertyData arrProp)
            {
                productionConfigsProp = arrProp;
                break;
            }
        }
        
        if (productionConfigsProp == null)
        {
            Console.WriteLine($"  Error: No ProductionConfigs found in CDO export");
            return;
        }
        
        Console.WriteLine($"  Existing ProductionConfigs: {productionConfigsProp.Value.Length}");
        
        var configList = new List<PropertyData>(productionConfigsProp.Value);
        var templateConfig = (StructPropertyData)productionConfigsProp.Value[0];
        
        foreach (var (mode, recipe) in recipes)
        {
            // Read recipe fields based on mode
            string cargoName;
            string? inputCargo = null;
            int inputCount = 1;
            string? outputCargo = null;
            int outputCount = 1;
            int productionTime;
            bool hidden;
            
            if (mode == RecipeMode.Transform)
            {
                inputCargo = recipe.GetProperty("input_cargo").GetString()!;
                inputCount = recipe.TryGetProperty("input_count", out var icProp) ? icProp.GetInt32() : 1;
                outputCargo = recipe.GetProperty("output_cargo").GetString()!;
                outputCount = recipe.TryGetProperty("output_count", out var ocProp) ? ocProp.GetInt32() : 1;
                productionTime = recipe.GetProperty("production_time").GetInt32();
                hidden = recipe.TryGetProperty("hidden", out var hProp) ? hProp.GetBoolean() : false;
                cargoName = $"{inputCargo}->{outputCargo}";
            }
            else
            {
                cargoName = recipe.GetProperty("cargo").GetString()!;
                productionTime = recipe.GetProperty("production_time").GetInt32();
                hidden = recipe.TryGetProperty("hidden", out var hProp) ? hProp.GetBoolean() : (mode == RecipeMode.Sink);
            }
            
            // Deep-clone the template config
            var newConfig = (StructPropertyData)templateConfig.Clone();
            
            foreach (var prop in newConfig.Value)
            {
                var propName = prop.Name.Value.Value;
                
                switch (propName)
                {
                    case "InputCargos":
                        if (prop is MapPropertyData inputMap)
                        {
                            inputMap.Value = new TMap<PropertyData, PropertyData>();
                            if (mode == RecipeMode.Sink)
                            {
                                var key = new NamePropertyData(FName.FromString(asset, "InputCargos"))
                                    { Value = FName.FromString(asset, cargoName) };
                                var val = new IntPropertyData(FName.FromString(asset, "InputCargos"))
                                    { Value = 1 };
                                inputMap.Value.Add(key, val);
                            }
                            else if (mode == RecipeMode.Transform)
                            {
                                var key = new NamePropertyData(FName.FromString(asset, "InputCargos"))
                                    { Value = FName.FromString(asset, inputCargo!) };
                                var val = new IntPropertyData(FName.FromString(asset, "InputCargos"))
                                    { Value = inputCount };
                                inputMap.Value.Add(key, val);
                            }
                            // Source: leave empty (no inputs)
                        }
                        break;
                        
                    case "OutputCargos":
                        if (prop is MapPropertyData outputMap)
                        {
                            outputMap.Value = new TMap<PropertyData, PropertyData>();
                            if (mode == RecipeMode.Source)
                            {
                                var key = new NamePropertyData(FName.FromString(asset, "OutputCargos"))
                                    { Value = FName.FromString(asset, cargoName) };
                                var val = new IntPropertyData(FName.FromString(asset, "OutputCargos"))
                                    { Value = 1 };
                                outputMap.Value.Add(key, val);
                            }
                            else if (mode == RecipeMode.Transform)
                            {
                                var key = new NamePropertyData(FName.FromString(asset, "OutputCargos"))
                                    { Value = FName.FromString(asset, outputCargo!) };
                                var val = new IntPropertyData(FName.FromString(asset, "OutputCargos"))
                                    { Value = outputCount };
                                outputMap.Value.Add(key, val);
                            }
                            // Sink: leave empty (no outputs)
                        }
                        break;
                        
                    case "InputCargoTypes":
                    case "OutputCargoTypes":
                        if (prop is MapPropertyData typeMap)
                        {
                            typeMap.Value = new TMap<PropertyData, PropertyData>();
                        }
                        break;
                        
                    case "InputCargoGameplayTagQuery":
                    case "OutputCargoRowGameplayTagQuery":
                        if (prop is StructPropertyData tagQuery)
                        {
                            foreach (var sp in tagQuery.Value)
                            {
                                switch (sp.Name.Value.Value)
                                {
                                    case "TokenStreamVersion":
                                        SetNumericProperty(sp, 0);
                                        break;
                                    case "TagDictionary":
                                        if (sp is ArrayPropertyData tagArr)
                                            tagArr.Value = Array.Empty<PropertyData>();
                                        break;
                                    case "QueryTokenStream":
                                        if (sp is ArrayPropertyData qtsArr)
                                            qtsArr.Value = Array.Empty<PropertyData>();
                                        break;
                                    case "UserDescription":
                                    case "AutoDescription":
                                        if (sp is StrPropertyData strProp)
                                            strProp.Value = null;
                                        break;
                                }
                            }
                        }
                        break;
                        
                    case "bStoreInputCargo":
                        ((BoolPropertyData)prop).Value = false;
                        break;
                        
                    case "ProductionTimeSeconds":
                        SetNumericProperty(prop, productionTime);
                        break;
                        
                    case "ProductionSpeedMultiplier":
                        SetNumericProperty(prop, 1);
                        break;
                        
                    case "LocalFoodSupply":
                        SetNumericProperty(prop, 0);
                        break;
                        
                    case "bHidden":
                        ((BoolPropertyData)prop).Value = hidden;
                        break;
                        
                    case "TimeSinceLastProduction":
                        SetNumericProperty(prop, 0);
                        break;
                        
                    case "ProductionFlags":
                        SetNumericProperty(prop, 0);
                        break;
                }
            }
            
            configList.Add(newConfig);
            var roleLabel = mode switch
            {
                RecipeMode.Source => $"OUTPUT={cargoName}",
                RecipeMode.Sink => $"INPUT={cargoName}",
                RecipeMode.Transform => $"TRANSFORM {inputCargo}×{inputCount}->{outputCargo}×{outputCount}",
                _ => cargoName
            };
            Console.WriteLine($"  Added recipe: {roleLabel} (time={productionTime}s, hidden={hidden})");
        }
        
        productionConfigsProp.Value = configList.ToArray();
        Console.WriteLine($"  Total ProductionConfigs: {productionConfigsProp.Value.Length}");
    }
    
    static void AddStorageConfigs(
        UAsset asset, NormalExport cdoExport, string dpName,
        List<JsonElement> storageEntries)
    {
        ArrayPropertyData? storageConfigsProp = null;
        foreach (var prop in cdoExport.Data)
        {
            if (prop.Name.Value.Value == "StorageConfigs" && prop is ArrayPropertyData arrProp)
            {
                storageConfigsProp = arrProp;
                break;
            }
        }
        
        if (storageConfigsProp == null)
        {
            Console.WriteLine($"  Error: No StorageConfigs found in CDO export");
            return;
        }
        
        Console.WriteLine($"  Existing StorageConfigs: {storageConfigsProp.Value.Length}");
        
        var configList = new List<PropertyData>(storageConfigsProp.Value);
        var templateEntry = (StructPropertyData)storageConfigsProp.Value[0];
        
        foreach (var entry in storageEntries)
        {
            var cargoKey = entry.GetProperty("cargo_key").GetString()!;
            var maxStorage = entry.TryGetProperty("max_storage", out var msProp) ? msProp.GetInt32() : 10;
            
            var newEntry = (StructPropertyData)templateEntry.Clone();
            
            foreach (var prop in newEntry.Value)
            {
                var propName = prop.Name.Value.Value;
                
                switch (propName)
                {
                    case "CargoType":
                        // Leave as cloned template value — CargoKey takes priority
                        // when set. Setting enum to "None" crashes the ByteProperty
                        // serializer in UE5's unversioned header format.
                        break;
                        
                    case "CargoKey":
                        if (prop is NamePropertyData keyProp)
                        {
                            keyProp.Value = FName.FromString(asset, cargoKey);
                        }
                        break;
                        
                    case "MaxStorage":
                        SetNumericProperty(prop, maxStorage);
                        break;
                        
                    case "MaxStorageRandomRange":
                        // Clear random range — use fixed MaxStorage
                        if (prop is StructPropertyData rangeProp)
                        {
                            foreach (var sp in rangeProp.Value)
                            {
                                SetNumericProperty(sp, 0);
                            }
                        }
                        break;
                }
            }
            
            configList.Add(newEntry);
            Console.WriteLine($"  Added storage: CargoKey={cargoKey}, MaxStorage={maxStorage}");
        }
        
        storageConfigsProp.Value = configList.ToArray();
        Console.WriteLine($"  Total StorageConfigs: {storageConfigsProp.Value.Length}");
    }
    
    // ========================================================================
    // --patch-tire: Clone tire physics asset, rename, modify friction values
    // ========================================================================
    static void PatchTire(string configPath, string templatePath, string outputDir)
    {
        if (!File.Exists(configPath))
        {
            Console.WriteLine($"Error: Config not found: {configPath}");
            return;
        }
        if (!File.Exists(templatePath))
        {
            Console.WriteLine($"Error: Template not found: {templatePath}");
            return;
        }
        
        var configJson = File.ReadAllText(configPath);
        using var doc = JsonDocument.Parse(configJson);
        var tirePhysics = doc.RootElement.GetProperty("tire_physics");
        
        var tireName = tirePhysics.GetProperty("name").GetString()!;
        var staticMu = tirePhysics.TryGetProperty("static_mu", out var smProp) ? smProp.GetSingle() : -1f;
        var slidingMu = tirePhysics.TryGetProperty("sliding_mu", out var slProp) ? slProp.GetSingle() : -1f;
        var offroadFriction = tirePhysics.TryGetProperty("offroad_friction", out var ofProp) ? ofProp.GetSingle() : -1f;
        var springX = tirePhysics.TryGetProperty("spring_x", out var sxProp) ? sxProp.GetSingle() : -1f;
        var springY = tirePhysics.TryGetProperty("spring_y", out var syProp) ? syProp.GetSingle() : -1f;
        var dampingX = tirePhysics.TryGetProperty("damping_x", out var dxProp) ? dxProp.GetSingle() : -1f;
        var dampingY = tirePhysics.TryGetProperty("damping_y", out var dyProp) ? dyProp.GetSingle() : -1f;
        
        Console.WriteLine($"\nPatching tire physics: {tireName}");
        Console.WriteLine($"  Template: {Path.GetFileName(templatePath)}");
        Console.WriteLine($"  StaticMu: {staticMu}, SlidingMu: {slidingMu}, OffroadFriction: {offroadFriction}");
        if (springX >= 0 || dampingX >= 0)
            Console.WriteLine($"  SpringX: {springX}, SpringY: {springY}, DampingX: {dampingX}, DampingY: {dampingY}");
        
        // Load fresh copy of template
        var asset = new UAsset(templatePath, EngineVersion.VER_UE5_5, Mappings);
        
        var oldName = Path.GetFileNameWithoutExtension(templatePath); // e.g. "BasicTire_45"
        // The internal export name may differ from filename (BasicTire_45 has export "BasicTire")
        // We need to find the actual export name
        string? oldExportName = null;
        foreach (var export in asset.Exports)
        {
            if (export is NormalExport ne && export.GetExportClassType()?.Value?.Value == "MTTirePhysicsDataAsset")
            {
                oldExportName = export.ObjectName.Value.Value;
                break;
            }
        }
        oldExportName ??= oldName;
        
        var newAssetPath = $"/Game/Cars/Parts/Tire/{tireName}";
        
        // Determine the old package path from NameMap[0] (self-package reference in UE5)
        var oldPackagePath = asset.GetNameReference(0)?.Value;
        Console.WriteLine($"  Old package path (NameMap[0]): {oldPackagePath}");
        
        // 1. Patch internal package identity
        asset.FolderName = FString.FromString(newAssetPath);
        
        // 1b. Rename exports FIRST — use direct FName constructor to set Number=0
        //     (BasicTire_45 was stored as FName("BasicTire", Number=46), we need Number=0)
        foreach (var export in asset.Exports)
        {
            var exportName = export.ObjectName.Value.Value;
            if (exportName.Contains(oldExportName))
            {
                export.ObjectName = new FName(asset, tireName, 0);
                Console.WriteLine($"  Renamed export: {exportName} -> {tireName}");
            }
        }
        
        // 1c. Update imports that reference old name
        for (int i = 0; i < asset.Imports.Count; i++)
        {
            var imp = asset.Imports[i];
            var impName = imp.ObjectName.Value.Value;
            if (impName.Contains(oldExportName))
            {
                imp.ObjectName = new FName(asset, 
                    impName.Replace(oldExportName, tireName), 0);
                Console.WriteLine($"  Renamed import: {impName} -> {imp.ObjectName.Value.Value}");
            }
            // Also check for path-based references (e.g. /Game/Cars/Parts/Tire/BasicTire)
            else if (impName.Contains($"/Game/Cars/Parts/Tire/{oldName}") || impName.Contains($"/Game/Cars/Parts/Tire/{oldExportName}"))
            {
                var newImpName = impName
                    .Replace($"/Game/Cars/Parts/Tire/{oldName}", newAssetPath)
                    .Replace($"/Game/Cars/Parts/Tire/{oldExportName}", newAssetPath);
                imp.ObjectName = new FName(asset, newImpName, 0);
                Console.WriteLine($"  Renamed import path: {impName} -> {newImpName}");
            }
        }
        
        // 1d. Patch NameMap — clean up stale old entries
        for (int i = 0; i < asset.GetNameMapIndexList().Count; i++)
        {
            var nameRef = asset.GetNameReference(i);
            if (nameRef?.Value == null) continue;
            
            // Rename old package path -> new package path
            if (nameRef.Value == oldPackagePath && oldPackagePath != null)
            {
                asset.SetNameReference(i, FString.FromString(newAssetPath));
                Console.WriteLine($"  Renamed NameMap[{i}]: {oldPackagePath} -> {newAssetPath}");
            }
        }
        
        // 4. Modify tire physics parameters
        foreach (var export in asset.Exports)
        {
            if (export is NormalExport ne)
            {
                foreach (var prop in ne.Data)
                {
                    if (prop.Name.Value.Value == "TirePhysicsParams" && prop is StructPropertyData tireParams)
                    {
                        Console.WriteLine($"  Found TirePhysicsParams struct with {tireParams.Value.Count} properties");
                        
                        bool hasStaticMu = false;
                        bool hasSlidingMu = false;
                        bool hasOffroadFriction = false;
                        
                        foreach (var tp in tireParams.Value)
                        {
                            var tpName = tp.Name.Value.Value;
                            switch (tpName)
                            {
                                case "StaticMu":
                                    if (staticMu >= 0) SetNumericProperty(tp, staticMu);
                                    hasStaticMu = true;
                                    Console.WriteLine($"    StaticMu = {staticMu}");
                                    break;
                                case "SlidingMu":
                                    if (slidingMu >= 0) SetNumericProperty(tp, slidingMu);
                                    hasSlidingMu = true;
                                    Console.WriteLine($"    SlidingMu = {slidingMu}");
                                    break;
                                case "OffroadFriction":
                                    if (offroadFriction >= 0) SetNumericProperty(tp, offroadFriction);
                                    hasOffroadFriction = true;
                                    Console.WriteLine($"    OffroadFriction = {offroadFriction}");
                                    break;
                                case "SpringX":
                                    if (springX >= 0) SetNumericProperty(tp, springX);
                                    Console.WriteLine($"    SpringX = {springX}");
                                    break;
                                case "SpringY":
                                    if (springY >= 0) SetNumericProperty(tp, springY);
                                    Console.WriteLine($"    SpringY = {springY}");
                                    break;
                                case "DampingX":
                                    if (dampingX >= 0) SetNumericProperty(tp, dampingX);
                                    Console.WriteLine($"    DampingX = {dampingX}");
                                    break;
                                case "DampingY":
                                    if (dampingY >= 0) SetNumericProperty(tp, dampingY);
                                    Console.WriteLine($"    DampingY = {dampingY}");
                                    break;
                            }
                        }
                        
                        // Add missing properties by cloning from existing float properties
                        if (!hasStaticMu && staticMu >= 0)
                        {
                            // Find any existing float property to clone structure from
                            var templateFloat = tireParams.Value.OfType<FloatPropertyData>().First();
                            var newProp = (FloatPropertyData)templateFloat.Clone();
                            newProp.Name = FName.FromString(asset, "StaticMu");
                            newProp.Value = staticMu;
                            tireParams.Value.Add(newProp);
                            Console.WriteLine($"    Added StaticMu = {staticMu}");
                        }
                        if (!hasSlidingMu && slidingMu >= 0)
                        {
                            var templateFloat = tireParams.Value.OfType<FloatPropertyData>().First();
                            var newProp = (FloatPropertyData)templateFloat.Clone();
                            newProp.Name = FName.FromString(asset, "SlidingMu");
                            newProp.Value = slidingMu;
                            tireParams.Value.Add(newProp);
                            Console.WriteLine($"    Added SlidingMu = {slidingMu}");
                        }
                        if (!hasOffroadFriction && offroadFriction >= 0)
                        {
                            var templateFloat = tireParams.Value.OfType<FloatPropertyData>().First();
                            var newProp = (FloatPropertyData)templateFloat.Clone();
                            newProp.Name = FName.FromString(asset, "OffroadFriction");
                            newProp.Value = offroadFriction;
                            tireParams.Value.Add(newProp);
                            Console.WriteLine($"    Added OffroadFriction = {offroadFriction}");
                        }
                    }
                }
            }
        }
        
        // Write output
        var tireOutputDir = Path.Combine(outputDir, tireName);
        Directory.CreateDirectory(tireOutputDir);
        var outputPath = Path.Combine(tireOutputDir, $"{tireName}.uasset");
        asset.Write(outputPath);
        Console.WriteLine($"  Written: {tireName}.uasset + .uexp to {tireOutputDir}");
    }
    
    // ========================================================================
    // --add-tire-parts: Add tire entry to VehicleParts DataTable
    // ========================================================================
    static void AddTireParts(string configPath, string templatePath, string outputDir)
    {
        if (!File.Exists(configPath))
        {
            Console.WriteLine($"Error: Config not found: {configPath}");
            return;
        }
        if (!File.Exists(templatePath))
        {
            Console.WriteLine($"Error: Template not found: {templatePath}");
            return;
        }
        
        var configJson = File.ReadAllText(configPath);
        using var doc = JsonDocument.Parse(configJson);
        var tirePart = doc.RootElement.GetProperty("tire_part");
        
        var rowName = tirePart.GetProperty("row_name").GetString()!;
        var displayName = tirePart.TryGetProperty("display_name", out var dnProp) ? dnProp : (JsonElement?)null;
        var cost = tirePart.GetProperty("cost").GetInt32();
        var massKg = tirePart.TryGetProperty("mass_kg", out var mkProp) ? mkProp.GetSingle() : 10f;
        var vehicleTypes = tirePart.GetProperty("vehicle_types");
        var tireAssetPath = tirePart.GetProperty("tire_asset_path").GetString()!;
        // Extract just the asset name from the path (last segment)
        var tireAssetName = tireAssetPath.Split('/').Last();
        // Extract the package path (everything before the last /AssetName)
        var tirePackagePath = tireAssetPath.Substring(0, tireAssetPath.LastIndexOf('/'));
        
        Console.WriteLine($"\nAdding tire part to VehicleParts: {rowName}");
        Console.WriteLine($"  Template: {Path.GetFileName(templatePath)}");
        Console.WriteLine($"  TireAsset: {tireAssetPath}");
        Console.WriteLine($"  Cost: {cost}, Mass: {massKg}kg");
        
        var asset = new UAsset(templatePath, EngineVersion.VER_UE5_5, Mappings);
        
        var dtExport = FindDataTable(asset);
        if (dtExport == null) return;
        
        Console.WriteLine($"Existing rows: {dtExport.Table.Data.Count}");
        
        // Find the LAST tire row to clone from (Offroad — a car tire, not motorcycle)
        StructPropertyData? templateRow = null;
        foreach (var row in dtExport.Table.Data)
        {
            if (row is StructPropertyData spd)
            {
                foreach (var prop in spd.Value)
                {
                    if (prop.Name.Value.Value == "PartType" && prop is EnumPropertyData enumProp
                        && enumProp.Value.Value.Value.Contains("Tire"))
                    {
                        templateRow = spd;  // Keep overwriting — ends up with last tire row
                        break;
                    }
                }
            }
        }
        if (templateRow != null)
            Console.WriteLine($"  Using template row: {templateRow.Name.Value.Value}");
        
        if (templateRow == null)
        {
            Console.WriteLine("Error: No tire row found in DataTable to clone from");
            return;
        }
        
        // Add import entries for the new tire physics asset
        var (pkgImportIdx, tireImportIdx) = AddImportChain(
            asset, "/Script/MotorTown", "MTTirePhysicsDataAsset",
            tirePackagePath, tireAssetName
        );
        
        // Deep-clone the template row
        var newRow = (StructPropertyData)templateRow.Clone();
        // Use direct FName constructor to prevent _77 suffix being parsed as instance number
        // (FName.FromString("APF_77") would split into "APF" + Number=78)
        newRow.Name = new FName(asset, rowName, 0);
        
        // Modify the cloned row
        foreach (var prop in newRow.Value)
        {
            var propName = prop.Name.Value.Value;
            
            switch (propName)
            {
                case "Name":
                    SetLocalizationGuid(prop);
                    break;
                    
                case "Name2":
                    if (displayName.HasValue)
                        SetDisplayName(prop, displayName.Value, asset);
                    break;
                    
                case "Desciption":
                    SetDescriptionFallback(prop, displayName.HasValue 
                        ? displayName.Value[0].GetString() ?? rowName : rowName);
                    break;
                    
                case "Cost":
                    SetNumericProperty(prop, cost);
                    break;
                    
                case "bIsHidden":
                    ((BoolPropertyData)prop).Value = false;
                    break;
                    
                case "MassKg":
                    SetNumericProperty(prop, massKg);
                    break;
                    
                case "VehicleTypes":
                    if (prop is ArrayPropertyData vtArr)
                        SetEnumArray(vtArr, vehicleTypes, asset, "EMTVehicleType");
                    break;
                    
                case "Tire":
                    if (prop is StructPropertyData tireStruct)
                    {
                        foreach (var tp in tireStruct.Value)
                        {
                            if (tp.Name.Value.Value == "TirePhysicsDataAsset" && tp is ObjectPropertyData tirePDA)
                            {
                                // Point to our new tire physics asset import
                                tirePDA.Value = FPackageIndex.FromImport(tireImportIdx - 1);
                                Console.WriteLine($"  Set TirePhysicsDataAsset -> import [{tireImportIdx}] ({tireAssetName})");
                            }
                            else if (tp.Name.Value.Value == "TirePhysicsDataAsset_BikeRear" && tp is ObjectPropertyData bikeRearPDA)
                            {
                                // Null out bike rear tire — this is a car tire
                                bikeRearPDA.Value = FPackageIndex.FromRawIndex(0);
                            }
                        }
                    }
                    break;
                    
                case "GameplayTags":
                    if (prop is StructPropertyData tagsStruct)
                    {
                        foreach (var sp in tagsStruct.Value)
                        {
                            if (sp is GameplayTagContainerPropertyData tagContainer)
                            {
                                tagContainer.Value = Array.Empty<FName>();
                            }
                        }
                    }
                    break;
                    
                case "VehicleKeys":
                    // Restrict to specific vehicle keys (e.g., ["Elisa_Police", "Muhan_Police"])
                    if (prop is ArrayPropertyData vkArr && tirePart.TryGetProperty("vehicle_keys", out var vkProp))
                    {
                        var vkList = new List<PropertyData>();
                        foreach (var vk in vkProp.EnumerateArray())
                        {
                            var nameProp = new NamePropertyData(FName.FromString(asset, "VehicleKeys"));
                            nameProp.Value = FName.FromString(asset, vk.GetString()!);
                            vkList.Add(nameProp);
                        }
                        vkArr.Value = vkList.ToArray();
                        if (vkList.Count > 0)
                            Console.WriteLine($"  Restricted to vehicles: {string.Join(", ", vkProp.EnumerateArray().Select(v => v.GetString()))}");
                    }
                    break;
                    
                case "LevelRequirementToBuy":
                    // Set level requirement (e.g., {"CL_Police": 10})
                    if (prop is MapPropertyData levelMap && tirePart.TryGetProperty("level_requirement", out var lvlProp))
                    {
                        levelMap.Value.Clear();
                        foreach (var lvlEntry in lvlProp.EnumerateObject())
                        {
                            var keyProp = new NamePropertyData(new FName(asset, "LevelRequirementToBuy", 0));
                            keyProp.Value = FName.FromString(asset, lvlEntry.Name);
                            
                            var valProp = new IntPropertyData(new FName(asset, "LevelRequirementToBuy", 0));
                            valProp.Value = lvlEntry.Value.GetInt32();
                            
                            levelMap.Value.Add(keyProp, valProp);
                        }
                        Console.WriteLine($"  Level requirements: {string.Join(", ", lvlProp.EnumerateObject().Select(e => $"{e.Name}={e.Value}"))}");
                    }
                    break;
            }
        }
        
        // Add row to DataTable
        dtExport.Table.Data.Add(newRow);
        Console.WriteLine($"  Added tire part: {rowName}");
        Console.WriteLine($"  Total rows: {dtExport.Table.Data.Count}");
        
        // Write output — preserve original filename (VehicleParts.uasset or VehicleParts0.uasset)
        Directory.CreateDirectory(outputDir);
        var outputFileName = Path.GetFileNameWithoutExtension(templatePath);
        var outputPath = Path.Combine(outputDir, $"{outputFileName}.uasset");
        asset.Write(outputPath);
        Console.WriteLine($"Written: {outputFileName}.uasset + {outputFileName}.uexp to {outputDir}");
    }
    
    // ========================================================================
    // Helper methods
    // ========================================================================
    
    static void SetNumericProperty(PropertyData prop, float value)
    {
        switch (prop)
        {
            case FloatPropertyData fp:
                fp.Value = value;
                break;
            case IntPropertyData ip:
                ip.Value = (int)value;
                break;
            case Int64PropertyData i64p:
                i64p.Value = (long)value;
                break;
            case DoublePropertyData dp:
                dp.Value = value;
                break;
        }
    }
    
    static void SetVector2D(StructPropertyData vecStruct, float x, float y, UAsset asset, string propertyName)
    {
        // Vector2D can be stored as a sub-struct with X/Y FloatProperties
        // or as a named struct with the property name as key containing X/Y
        foreach (var sp in vecStruct.Value)
        {
            if (sp is StructPropertyData innerStruct && sp.Name.Value.Value == propertyName)
            {
                // Has inner struct — check for X/Y
                foreach (var inner in innerStruct.Value)
                {
                    if (inner.Name.Value.Value == "X") SetNumericProperty(inner, x);
                    else if (inner.Name.Value.Value == "Y") SetNumericProperty(inner, y);
                }
                return;
            }
            else if (sp is Vector2DPropertyData vec2d)
            {
                // Direct Vector2D property
                vec2d.Value = new FVector2D(x, y);
                return;
            }
        }
        
        // Fallback: look for X/Y directly in the struct
        foreach (var sp in vecStruct.Value)
        {
            if (sp.Name.Value.Value == "X") SetNumericProperty(sp, x);
            else if (sp.Name.Value.Value == "Y") SetNumericProperty(sp, y);
        }
    }
    
    // ========================================================================
    // Shared DataTable helpers — used by cargo, tire, and decal commands
    // ========================================================================
    
    /// <summary>Find the first DataTableExport in an asset.</summary>
    static DataTableExport? FindDataTable(UAsset asset)
    {
        foreach (var export in asset.Exports)
        {
            if (export is DataTableExport dt) return dt;
        }
        Console.WriteLine("Error: No DataTable found in template");
        return null;
    }
    
    /// <summary>
    /// Set a Name property to a random GUID for localization uniqueness.
    /// Used by cargo and tire DataTable rows.
    /// </summary>
    static void SetLocalizationGuid(PropertyData prop)
    {
        if (prop is TextPropertyData nameTxt)
        {
            var guid = Guid.NewGuid().ToString("N").ToUpper();
            nameTxt.Value = FString.FromString(guid.Substring(0, 32));
            nameTxt.HistoryType = TextHistoryType.None;
        }
    }
    
    /// <summary>
    /// Set the Name2 (MTTextByTexts) struct's Texts array from a JSON array of strings.
    /// This is the actual display name shown in the game shop UI.
    /// Used by cargo and tire DataTable rows.
    /// </summary>
    static void SetDisplayName(PropertyData prop, JsonElement displayName, UAsset asset)
    {
        if (prop is StructPropertyData name2Struct)
        {
            foreach (var sp in name2Struct.Value)
            {
                if (sp.Name.Value.Value == "Texts" && sp is ArrayPropertyData textsArr)
                {
                    var textList = new List<PropertyData>();
                    foreach (var txt in displayName.EnumerateArray())
                    {
                        var textVal = txt.GetString();
                        var textProp = new TextPropertyData(FName.FromString(asset, "Texts"));
                        textProp.Value = FString.FromString(textVal);
                        textProp.CultureInvariantString = FString.FromString(textVal);
                        textProp.HistoryType = TextHistoryType.None;
                        textList.Add(textProp);
                    }
                    textsArr.Value = textList.ToArray();
                }
            }
        }
    }
    
    /// <summary>
    /// Set the Desciption (sic) text property as a fallback display name.
    /// </summary>
    static void SetDescriptionFallback(PropertyData prop, string text)
    {
        if (prop is TextPropertyData descTxt)
        {
            descTxt.Value = FString.FromString(text);
            descTxt.CultureInvariantString = FString.FromString(text);
            descTxt.HistoryType = TextHistoryType.None;
        }
    }
    
    /// <summary>
    /// Add a Package + Asset import chain to an asset.
    /// Returns (packageImportIdx, assetImportIdx) — 1-indexed.
    /// Used by cargo (ActorClass) and tire (TirePhysicsDataAsset) commands.
    /// </summary>
    static (int pkgIdx, int assetIdx) AddImportChain(
        UAsset asset, string classPackage, string className,
        string packagePath, string assetName)
    {
        // 1. Package import (outer = 0 = top-level)
        var pkgImport = new Import(
            "/Script/CoreUObject", "Package",
            FPackageIndex.FromRawIndex(0),
            packagePath, false, asset
        );
        asset.Imports.Add(pkgImport);
        int pkgIdx = asset.Imports.Count; // 1-indexed
        
        // 2. Asset import (outer = package)
        var assetImport = new Import(
            classPackage, className,
            FPackageIndex.FromImport(pkgIdx - 1),
            assetName, false, asset
        );
        asset.Imports.Add(assetImport);
        int assetIdx = asset.Imports.Count; // 1-indexed
        
        Console.WriteLine($"  Added imports: Package [{pkgIdx}] = {packagePath}");
        Console.WriteLine($"  Added imports: Asset [{assetIdx}] = {assetName}");
        
        return (pkgIdx, assetIdx);
    }
    
    /// <summary>
    /// Set an enum array property from a JSON array of enum value strings.
    /// Handles the UE5 clone + FName pattern for unversioned enum arrays.
    /// Used by CargoSpaceTypes and VehicleTypes.
    /// </summary>
    static void SetEnumArray(ArrayPropertyData arr, JsonElement values,
        UAsset asset, string defaultEnumTypeName)
    {
        if (arr.Value.Length == 0) return;
        
        var templateEnum = (EnumPropertyData)arr.Value[0];
        var enumTypeName = templateEnum.EnumType?.Value?.Value ?? defaultEnumTypeName;
        var list = new List<PropertyData>();
        
        foreach (var val in values.EnumerateArray())
        {
            var clone = (EnumPropertyData)templateEnum.Clone();
            clone.Value = FName.FromString(asset, $"{enumTypeName}::{val.GetString()!}");
            list.Add(clone);
        }
        arr.Value = list.ToArray();
    }
    
    // ========================================================================
    // Parser modes (existing)
    // ========================================================================
    
    static void ProcessBatch()
    {
        var outDir = Path.Combine(RootDir!, "out");
        var manifestPath = Path.Combine(outDir, "manifest.json");
        
        if (!File.Exists(manifestPath))
        {
            Console.WriteLine($"Error: No manifest.json in {outDir}");
            Console.WriteLine("Run Rust extractor first: cargo run -- --config assets.json");
            return;
        }
        
        Console.WriteLine($"\nBatch processing assets in {outDir}");
        
        var manifestJson = File.ReadAllText(manifestPath);
        using var doc = JsonDocument.Parse(manifestJson);
        var extracted = doc.RootElement.GetProperty("extracted");
        
        int success = 0, failed = 0;
        
        foreach (var asset in extracted.EnumerateArray())
        {
            var name = asset.GetProperty("name").GetString()!;
            var uassetFile = asset.GetProperty("uasset").GetString()!;
            var uassetPath = Path.Combine(outDir, uassetFile);
            
            Console.WriteLine($"\n  Processing: {name}");
            
            try
            {
                ProcessSingleFile(uassetPath, outDir);
                success++;
            }
            catch (Exception ex)
            {
                Console.WriteLine($"    FAILED: {ex.Message}");
                failed++;
            }
        }
        
        Console.WriteLine($"\n=== Batch complete: {success} succeeded, {failed} failed ===");
    }
    
    static void ProcessBatchMaps()
    {
        var mapsDir = Path.Combine(RootDir!, "out", "maps");
        var manifestPath = Path.Combine(mapsDir, "manifest.json");
        
        if (!File.Exists(manifestPath))
        {
            Console.WriteLine($"Error: No manifest.json in {mapsDir}");
            Console.WriteLine("Run Rust extractor first: cargo run -- --extract-maps");
            return;
        }
        
        Console.WriteLine($"\nBatch processing .umap files in {mapsDir}");
        
        var manifestJson = File.ReadAllText(manifestPath);
        using var doc = JsonDocument.Parse(manifestJson);
        var extracted = doc.RootElement.GetProperty("extracted");
        
        int success = 0, failed = 0;
        
        foreach (var asset in extracted.EnumerateArray())
        {
            var name = asset.GetProperty("name").GetString()!;
            var uassetFile = asset.GetProperty("uasset").GetString()!;
            var filePath = Path.Combine(mapsDir, uassetFile);
            
            Console.WriteLine($"\n  Processing map: {name}");
            
            try
            {
                ProcessSingleFile(filePath, mapsDir);
                success++;
            }
            catch (Exception ex)
            {
                Console.WriteLine($"    FAILED: {ex.Message}");
                failed++;
            }
        }
        
        Console.WriteLine($"\n=== Batch maps complete: {success} succeeded, {failed} failed ===");
    }
    
    static void ProcessSingleFile(string uassetPath, string outputDir)
    {
        if (!File.Exists(uassetPath))
        {
            throw new FileNotFoundException($"File not found: {uassetPath}");
        }
        
        var baseName = Path.GetFileNameWithoutExtension(uassetPath);
        var outputPath = Path.Combine(outputDir, $"{baseName}_parsed.json");
        
        Console.WriteLine($"    Loading: {Path.GetFileName(uassetPath)}");
        var asset = new UAsset(uassetPath, EngineVersion.VER_UE5_5, Mappings);
        
        Console.WriteLine($"    Exports: {asset.Exports.Count}, Imports: {asset.Imports.Count}");
        
        // Process all exports
        var exports = new List<object>();
        object? dataTable = null;
        
        foreach (var export in asset.Exports)
        {
            if (export is DataTableExport dtExport)
            {
                var rows = new List<Dictionary<string, object?>>();
                foreach (var row in dtExport.Table.Data)
                {
                    var rowData = new Dictionary<string, object?>();
                    rowData["RowName"] = row.Name.Value.Value;
                    
                    foreach (var prop in row.Value)
                    {
                        rowData[prop.Name.Value.Value] = ExtractPropertyValue(prop, asset);
                    }
                    rows.Add(rowData);
                }
                
                dataTable = new {
                    Type = "DataTable",
                    RowCount = rows.Count,
                    Rows = rows
                };
                Console.WriteLine($"    DataTable: {rows.Count} rows");
            }
            else if (export is NormalExport normalExport)
            {
                var properties = new Dictionary<string, object?>();
                foreach (var prop in normalExport.Data)
                {
                    properties[prop.Name.Value.Value] = ExtractPropertyValue(prop, asset);
                }
                
                var exportData = new {
                    ExportName = export.ObjectName?.Value?.Value,
                    Class = export.GetExportClassType()?.Value?.Value,
                    Properties = properties
                };
                exports.Add(exportData);
                Console.WriteLine($"    NormalExport: {properties.Count} properties");
            }
        }
        
        // Save output - prefer DataTable format, otherwise collect all exports
        object result;
        if (dataTable != null)
        {
            result = dataTable;
        }
        else
        {
            result = new {
                Type = "Blueprint",
                ExportCount = exports.Count,
                Exports = exports
            };
        }
        
        var output = new {
            SourceAsset = Path.GetFileName(uassetPath),
            ParsedAt = DateTime.UtcNow.ToString("o"),
            Data = result
        };
            
        var options = new JsonSerializerOptions { WriteIndented = true };
        var json = JsonSerializer.Serialize(output, options);
        File.WriteAllText(outputPath, json);
        Console.WriteLine($"    Saved: {Path.GetFileName(outputPath)}");
    }
    
    static object? ExtractPropertyValue(PropertyData prop, UAsset asset)
    {
        return prop switch
        {
            BoolPropertyData boolProp => boolProp.Value,
            IntPropertyData intProp => intProp.Value,
            Int64PropertyData int64Prop => int64Prop.Value,
            UInt32PropertyData uint32Prop => uint32Prop.Value,
            UInt64PropertyData uint64Prop => uint64Prop.Value,
            FloatPropertyData floatProp => floatProp.Value,
            DoublePropertyData doubleProp => doubleProp.Value,
            StrPropertyData strProp => strProp.Value?.Value,
            NamePropertyData nameProp => nameProp.Value?.Value?.Value,
            EnumPropertyData enumProp => enumProp.Value?.Value?.Value,
            ObjectPropertyData objProp => ResolveObjectReference(objProp, asset),
            SoftObjectPropertyData softProp => ExtractSoftObjectValue(softProp),
            ArrayPropertyData arrProp => ExtractArrayValue(arrProp, asset),
            StructPropertyData structProp => ExtractStructValue(structProp, asset),
            MapPropertyData mapProp => ExtractMapValue(mapProp, asset),
            TextPropertyData textProp => textProp.Value?.Value,
            BytePropertyData byteProp => byteProp.Value,
            Vector2DPropertyData vec2Prop => new { X = vec2Prop.Value.X, Y = vec2Prop.Value.Y },
            VectorPropertyData vecProp => new { X = vecProp.Value.X, Y = vecProp.Value.Y, Z = vecProp.Value.Z },
            GameplayTagContainerPropertyData tagProp => ExtractGameplayTags(tagProp),
            GuidPropertyData guidProp => guidProp.Value.ToString("N"),
            _ => $"<{prop.GetType().Name}>"
        };
    }
    
    static object? ExtractSoftObjectValue(SoftObjectPropertyData softProp)
    {
        var assetName = softProp.Value.AssetPath.AssetName?.Value?.Value;
        var subPath = softProp.Value.SubPathString?.Value;
        
        if (string.IsNullOrEmpty(assetName))
            return null;
            
        if (!string.IsNullOrEmpty(subPath))
            return $"{assetName}:{subPath}";
            
        return assetName;
    }
    
    static object? ResolveObjectReference(ObjectPropertyData objProp, UAsset asset)
    {
        if (objProp.Value == null || objProp.Value.Index == 0)
            return null;
            
        var index = objProp.Value.Index;
        
        if (index < 0)
        {
            var importIdx = -index - 1;
            if (importIdx < asset.Imports.Count)
            {
                var import = asset.Imports[importIdx];
                var objectName = import.ObjectName?.Value?.Value;
                var className = import.ClassName?.Value?.Value;
                
                if (!string.IsNullOrEmpty(objectName))
                {
                    var path = BuildImportPath(asset, importIdx);
                    return new {
                        Type = "Import",
                        Path = path,
                        ObjectName = objectName,
                        ClassName = className
                    };
                }
            }
        }
        else
        {
            var exportIdx = index - 1;
            if (exportIdx < asset.Exports.Count)
            {
                var export = asset.Exports[exportIdx];
                return new {
                    Type = "Export",
                    Index = exportIdx,
                    ObjectName = export.ObjectName?.Value?.Value,
                    ClassName = export.GetExportClassType()?.Value?.Value
                };
            }
        }
        
        return $"UnresolvedRef:{index}";
    }
    
    static string BuildImportPath(UAsset asset, int importIdx)
    {
        var parts = new List<string>();
        var current = importIdx;
        
        while (current >= 0 && current < asset.Imports.Count)
        {
            var import = asset.Imports[current];
            var name = import.ObjectName?.Value?.Value;
            if (!string.IsNullOrEmpty(name))
            {
                parts.Insert(0, name);
            }
            
            var outerIdx = import.OuterIndex.Index;
            if (outerIdx < 0)
            {
                current = -outerIdx - 1;
            }
            else
            {
                break;
            }
        }
        
        return string.Join("/", parts);
    }
    
    static object? ExtractArrayValue(ArrayPropertyData arrProp, UAsset asset)
    {
        var items = new List<object?>();
        foreach (var item in arrProp.Value)
        {
            items.Add(ExtractPropertyValue(item, asset));
        }
        return items;
    }
    
    static object? ExtractMapValue(MapPropertyData mapProp, UAsset asset)
    {
        var entries = new List<object>();
        
        foreach (var kvp in mapProp.Value)
        {
            var key = ExtractPropertyValue(kvp.Key, asset);
            var value = ExtractPropertyValue(kvp.Value, asset);
            
            entries.Add(new {
                Key = key,
                Value = value
            });
        }
        
        return new {
            _Type = "Map",
            KeyType = mapProp.KeyType?.Value?.Value,
            ValueType = mapProp.ValueType?.Value?.Value,
            Entries = entries
        };
    }
    
    static object? ExtractStructValue(StructPropertyData structProp, UAsset asset)
    {
        var result = new Dictionary<string, object?>();
        result["_StructType"] = structProp.StructType?.Value?.Value;
        
        foreach (var prop in structProp.Value)
        {
            result[prop.Name.Value.Value] = ExtractPropertyValue(prop, asset);
        }
        
        return result;
    }
    
    static object? ExtractGameplayTags(GameplayTagContainerPropertyData tagProp)
    {
        var tags = new List<string>();
        foreach (var tag in tagProp.Value)
        {
            if (tag?.Value?.Value != null)
            {
                tags.Add(tag.Value.Value);
            }
        }
        return tags;
    }
    
    static void ModifyDecals(string configPath, string templatePath, string outputDir)
    {
        if (!File.Exists(configPath))
        {
            Console.WriteLine($"Error: Config not found: {configPath}");
            return;
        }
        if (!File.Exists(templatePath))
        {
            Console.WriteLine($"Error: Template not found: {templatePath}");
            return;
        }
        
        var configJson = File.ReadAllText(configPath);
        using var doc = JsonDocument.Parse(configJson);
        var entries = doc.RootElement.GetProperty("entries");
        
        Console.WriteLine($"Loading template: {Path.GetFileName(templatePath)}");
        var asset = new UAsset(templatePath, EngineVersion.VER_UE5_5, Mappings);
        
        DataTableExport? dtExport = null;
        foreach (var export in asset.Exports)
        {
            if (export is DataTableExport dt)
            {
                dtExport = dt;
                break;
            }
        }
        
        if (dtExport == null)
        {
            Console.WriteLine("Error: No DataTable found in template");
            return;
        }
        
        Console.WriteLine($"Existing rows: {dtExport.Table.Data.Count}");
        
        int brushMaterialIdx = -3;
        for (int i = 0; i < asset.Imports.Count; i++)
        {
            var imp = asset.Imports[i];
            if (imp.ObjectName?.Value?.Value == "M_DecalBounds_Test")
            {
                brushMaterialIdx = -(i + 1);
                break;
            }
        }
        Console.WriteLine($"BrushMaterial import index: {brushMaterialIdx}");
        
        int added = 0;
        foreach (var entry in entries.EnumerateArray())
        {
            var rowName = entry.GetProperty("row_name").GetString()!;
            var folder = entry.GetProperty("folder").GetString()!;
            var file = entry.GetProperty("file").GetString()!;
            var cost = entry.GetProperty("cost").GetInt32();
            var flags = entry.GetProperty("flags").GetInt32();
            
            var packagePath = $"/Game/Materials/Decal/DecalTextures/{folder}/{file}";
            
            var rowStruct = new StructPropertyData(FName.FromString(asset, rowName))
            {
                StructType = FName.FromString(asset, "MTDecalRow"),
                Value = new List<PropertyData>()
            };
            
            var textureProp = new SoftObjectPropertyData(FName.FromString(asset, "Texture"))
            {
                Value = new FSoftObjectPath(
                    new FTopLevelAssetPath(
                        FName.FromString(asset, packagePath),
                        FName.FromString(asset, file)
                    ),
                    null
                )
            };
            rowStruct.Value.Add(textureProp);
            
            var brushProp = new ObjectPropertyData(FName.FromString(asset, "BrushMaterial"))
            {
                Value = new FPackageIndex(brushMaterialIdx)
            };
            rowStruct.Value.Add(brushProp);
            
            var flagsProp = new IntPropertyData(FName.FromString(asset, "Flags"))
            {
                Value = flags,
                IsZero = (flags == 0)
            };
            rowStruct.Value.Add(flagsProp);
            
            var costProp = new IntPropertyData(FName.FromString(asset, "Cost"))
            {
                Value = cost
            };
            rowStruct.Value.Add(costProp);
            
            if (dtExport.Table.Data.Count > 0)
            {
                var templateRow = dtExport.Table.Data[^1];
                rowStruct.Ancestry = (AncestryInfo)templateRow.Ancestry.Clone();
            }
            
            dtExport.Table.Data.Add(rowStruct);
            Console.WriteLine($"  Added: {rowName} -> {packagePath}");
            added++;
        }
        
        Console.WriteLine($"\nAdded {added} rows. Total rows: {dtExport.Table.Data.Count}");
        
        asset.ResolveAncestries();
        
        Directory.CreateDirectory(outputDir);
        var outputBase = Path.Combine(outputDir, "Decals.uasset");
        asset.Write(outputBase);
        
        Console.WriteLine($"Written: {Path.GetFileName(outputBase)} + Decals.uexp");
    }
}
