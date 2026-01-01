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
        
        // Check for batch mode
        bool batchMode = args.Contains("--batch");
        
        Console.WriteLine($"Usage: dotnet run -- [--batch] [path/to/asset.uasset]");
        Console.WriteLine($"  --batch: Parse all assets in out/ folder");
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
        
        if (batchMode)
        {
            ProcessBatch();
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
        
        // Process exports
        object? result = null;
        
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
                        rowData[prop.Name.Value.Value] = ExtractPropertyValue(prop);
                    }
                    rows.Add(rowData);
                }
                
                result = new {
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
                    properties[prop.Name.Value.Value] = ExtractPropertyValue(prop);
                }
                
                result = new {
                    Type = "NormalExport",
                    Class = export.GetExportClassType().Value.Value,
                    Properties = properties
                };
                Console.WriteLine($"    NormalExport: {properties.Count} properties");
            }
        }
        
        // Save output
        if (result != null)
        {
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
    }
    
    static object? ExtractPropertyValue(PropertyData prop)
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
            ObjectPropertyData objProp => ResolveObjectReference(objProp),
            SoftObjectPropertyData softProp => softProp.Value.AssetPath.AssetName?.Value?.Value,
            ArrayPropertyData arrProp => ExtractArrayValue(arrProp),
            StructPropertyData structProp => ExtractStructValue(structProp),
            TextPropertyData textProp => textProp.Value?.Value,
            BytePropertyData byteProp => byteProp.Value,
            Vector2DPropertyData vec2Prop => new { X = vec2Prop.Value.X, Y = vec2Prop.Value.Y },
            VectorPropertyData vecProp => new { X = vecProp.Value.X, Y = vecProp.Value.Y, Z = vecProp.Value.Z },
            _ => $"<{prop.GetType().Name}>"
        };
    }
    
    static string? ResolveObjectReference(ObjectPropertyData objProp)
    {
        if (objProp.Value == null || objProp.Value.Index == 0)
            return null;
        return $"ObjectRef:{objProp.Value.Index}";
    }
    
    static object? ExtractArrayValue(ArrayPropertyData arrProp)
    {
        var items = new List<object?>();
        foreach (var item in arrProp.Value)
        {
            items.Add(ExtractPropertyValue(item));
        }
        return items;
    }
    
    static object? ExtractStructValue(StructPropertyData structProp)
    {
        var result = new Dictionary<string, object?>();
        result["_StructType"] = structProp.StructType?.Value?.Value;
        
        foreach (var prop in structProp.Value)
        {
            result[prop.Name.Value.Value] = ExtractPropertyValue(prop);
        }
        
        return result;
    }
}
