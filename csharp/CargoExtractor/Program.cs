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
        Console.WriteLine("=== MotorTown UAsset Parser (UAssetAPI) ===");
        
        // Determine root directory (two levels up from csharp/CargoExtractor)
        RootDir = Path.GetFullPath(Path.Combine("..", ".."));
        var usmapPath = Path.Combine(RootDir, "Mappings.usmap");
        
        // Check for modes
        bool batchMode = args.Contains("--batch");
        bool batchMapsMode = args.Contains("--batch-maps");
        bool modifyDecalsMode = args.Contains("--add-decals");
        
        Console.WriteLine($"Usage: dotnet run -- [--batch] [--batch-maps] [--add-decals config.json template.uasset output_dir] [path/to/asset.uasset]");
        Console.WriteLine($"  --batch: Parse all assets in out/ folder");
        Console.WriteLine($"  --batch-maps: Parse all .umap files in out/maps/ folder");
        Console.WriteLine($"  --add-decals: Add new decal rows to Decals DataTable");
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
            // --add-decals config.json template.uasset output_dir
            var configIdx = Array.IndexOf(args, "--add-decals");
            var configPath = args.ElementAtOrDefault(configIdx + 1) ?? "decal_entries.json";
            var templatePath = args.ElementAtOrDefault(configIdx + 2) ?? Path.Combine(RootDir, "Decals.uasset");
            var outputDir = args.ElementAtOrDefault(configIdx + 3) ?? RootDir;
            
            ModifyDecals(configPath, templatePath, outputDir);
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
        
        // Read manifest
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
        
        // Negative indices are imports, positive are exports
        if (index < 0)
        {
            // Import reference (external asset)
            var importIdx = -index - 1;
            if (importIdx < asset.Imports.Count)
            {
                var import = asset.Imports[importIdx];
                var objectName = import.ObjectName?.Value?.Value;
                var classPackage = import.ClassPackage?.Value?.Value;
                var className = import.ClassName?.Value?.Value;
                
                // Build a meaningful path
                if (!string.IsNullOrEmpty(objectName))
                {
                    // Try to build a path from the import hierarchy
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
            // Export reference (local to this asset)
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
        
        // Walk up the import hierarchy
        while (current >= 0 && current < asset.Imports.Count)
        {
            var import = asset.Imports[current];
            var name = import.ObjectName?.Value?.Value;
            if (!string.IsNullOrEmpty(name))
            {
                parts.Insert(0, name);
            }
            
            // Get parent (OuterIndex is a FPackageIndex)
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
        
        // Load decal entries from config
        var configJson = File.ReadAllText(configPath);
        using var doc = JsonDocument.Parse(configJson);
        var entries = doc.RootElement.GetProperty("entries");
        
        Console.WriteLine($"Loading template: {Path.GetFileName(templatePath)}");
        var asset = new UAsset(templatePath, EngineVersion.VER_UE5_5, Mappings);
        
        // Find the DataTable export
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
        
        // Find the BrushMaterial import (index -3 in most cases)
        // It's the M_DecalBounds_Test import
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
            
            // Build asset path
            var packagePath = $"/Game/Materials/Decal/DecalTextures/{folder}/{file}";
            
            // Create the DataTable row struct
            var rowStruct = new StructPropertyData(FName.FromString(asset, rowName))
            {
                StructType = FName.FromString(asset, "MTDecalRow"),
                Value = new List<PropertyData>()
            };
            
            // Texture property (SoftObjectProperty)
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
            
            // BrushMaterial property (ObjectProperty)
            var brushProp = new ObjectPropertyData(FName.FromString(asset, "BrushMaterial"))
            {
                Value = new FPackageIndex(brushMaterialIdx)
            };
            rowStruct.Value.Add(brushProp);
            
            // Flags property (IntProperty)
            var flagsProp = new IntPropertyData(FName.FromString(asset, "Flags"))
            {
                Value = flags,
                IsZero = (flags == 0)
            };
            rowStruct.Value.Add(flagsProp);
            
            // Cost property (IntProperty)
            var costProp = new IntPropertyData(FName.FromString(asset, "Cost"))
            {
                Value = cost
            };
            rowStruct.Value.Add(costProp);
            
            // Clone ancestry from existing row for correct serialization
            if (dtExport.Table.Data.Count > 0)
            {
                var templateRow = dtExport.Table.Data[^1];
                rowStruct.Ancestry = (AncestryInfo)templateRow.Ancestry.Clone();
            }
            
            // Add row to DataTable
            dtExport.Table.Data.Add(rowStruct);
            Console.WriteLine($"  Added: {rowName} -> {packagePath}");
            added++;
        }
        
        Console.WriteLine($"\nAdded {added} rows. Total rows: {dtExport.Table.Data.Count}");
        
        // Resolve ancestries for manually constructed rows
        asset.ResolveAncestries();
        
        // Write output — both .uasset and .uexp are fresh and consistent.
        // Always build the mod PAK from these files, never reuse stale outputs.
        Directory.CreateDirectory(outputDir);
        var outputBase = Path.Combine(outputDir, "Decals.uasset");
        asset.Write(outputBase);
        
        Console.WriteLine($"Written: {Path.GetFileName(outputBase)} + Decals.uexp");
    }
}
