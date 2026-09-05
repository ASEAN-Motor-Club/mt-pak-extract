using System;
using System.IO;
using System.Text.Json;
using System.Collections.Concurrent;
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

    /// <summary>
    /// Build a UE5.5+ FPropertyTypeName for a programmatically created property.
    /// Parser-populated properties get this from the binary; anything we create
    /// in code must set it or UE5.5 nametagged serialization NPEs.
    /// </summary>
    static FPropertyTypeName MakeTypeName(INameMap asset, FString typeName)
    {
        var name = FName.FromString(asset, typeName?.Value) ?? new FName(asset, 0, 0);
        return new FPropertyTypeName(new List<FPropertyTypeNameNode>
        {
            new FPropertyTypeNameNode { Name = name, InnerCount = 0 }
        });
    }

    
    static void Main(string[] args)
    {
        Console.WriteLine("=== MotorTown UAsset Tool ===");
        
        RootDir = Path.GetFullPath(Path.Combine("..", ".."));
        var usmapPath = Path.Combine(RootDir, "Mappings.usmap");
        
        // Check modes
        bool batchMode = args.Contains("--batch");
        bool batchMapsMode = args.Contains("--batch-maps");
        bool addRowsMode = args.Contains("--add-rows");
        bool cloneAssetMode = args.Contains("--clone-asset");
        bool patchCdoMode = args.Contains("--patch-cdo-arrays");
        bool patchRowsMode = args.Contains("--patch-rows");
        bool patchExportMode = args.Contains("--patch-export-props");
        bool patchNamedExportsMode = args.Contains("--patch-named-exports");
        bool dumpMode = args.Contains("--dump");
        
        Console.WriteLine($"Usage: dotnet run -- [--batch] [--batch-maps] [--add-rows ...] [--clone-asset ...] [--patch-cdo-arrays ...] [--patch-rows ...] [--patch-export-props ...] [--patch-named-exports ...] [--dump ...] [path/to/asset.uasset]");
        Console.WriteLine();
        
        if (!File.Exists(usmapPath))
        {
            Console.WriteLine($"Error: Mappings file not found at {usmapPath}");
            return;
        }
        
        Console.WriteLine("Loading mappings...");
        Mappings = new Usmap(usmapPath);
        Console.WriteLine($"Loaded {Mappings.Schemas.Count} schemas");
        
        PatchMappingsForVersion();
        
        if (batchMapsMode)
        {
            ProcessBatchMaps();
        }
        else if (batchMode)
        {
            ProcessBatch();
        }
        else if (addRowsMode)
        {
            var idx = Array.IndexOf(args, "--add-rows");
            var configPath = args.ElementAtOrDefault(idx + 1) ?? "config.json";
            var templatePath = args.ElementAtOrDefault(idx + 2) ?? Path.Combine(RootDir, "template.uasset");
            var outputDir = args.ElementAtOrDefault(idx + 3) ?? RootDir;
            AddRows(configPath, templatePath, outputDir);
        }
        else if (cloneAssetMode)
        {
            var idx = Array.IndexOf(args, "--clone-asset");
            var configPath = args.ElementAtOrDefault(idx + 1) ?? "config.json";
            var templatePath = args.ElementAtOrDefault(idx + 2) ?? Path.Combine(RootDir, "template.uasset");
            var outputDir = args.ElementAtOrDefault(idx + 3) ?? RootDir;
            CloneAsset(configPath, templatePath, outputDir);
        }
        else if (patchCdoMode)
        {
            var idx = Array.IndexOf(args, "--patch-cdo-arrays");
            var configPath = args.ElementAtOrDefault(idx + 1) ?? "config.json";
            var templatePath = args.ElementAtOrDefault(idx + 2) ?? Path.Combine(RootDir, "template.uasset");
            var outputDir = args.ElementAtOrDefault(idx + 3) ?? RootDir;
            PatchCdoArrays(configPath, templatePath, outputDir);
        }
        else if (patchRowsMode)
        {
            var idx = Array.IndexOf(args, "--patch-rows");
            var configPath = args.ElementAtOrDefault(idx + 1) ?? "config.json";
            var templatePath = args.ElementAtOrDefault(idx + 2) ?? Path.Combine(RootDir, "template.uasset");
            var outputDir = args.ElementAtOrDefault(idx + 3) ?? RootDir;
            PatchRows(configPath, templatePath, outputDir);
        }
        else if (patchExportMode)
        {
            var idx = Array.IndexOf(args, "--patch-export-props");
            var configPath = args.ElementAtOrDefault(idx + 1) ?? "config.json";
            var templatePath = args.ElementAtOrDefault(idx + 2) ?? Path.Combine(RootDir, "template.uasset");
            var outputDir = args.ElementAtOrDefault(idx + 3) ?? RootDir;
            PatchExportProps(configPath, templatePath, outputDir);
        }
        else if (patchNamedExportsMode)
        {
            var idx = Array.IndexOf(args, "--patch-named-exports");
            var configPath = args.ElementAtOrDefault(idx + 1) ?? "config.json";
            var templatePath = args.ElementAtOrDefault(idx + 2) ?? Path.Combine(RootDir, "template.uasset");
            var outputDir = args.ElementAtOrDefault(idx + 3) ?? RootDir;
            PatchNamedExports(configPath, templatePath, outputDir);
        }
        else if (dumpMode)
        {
            var idx = Array.IndexOf(args, "--dump");
            var dumpPath = args.ElementAtOrDefault(idx + 1) ?? Path.Combine(RootDir, "Cargos.uasset");
            if (!Path.IsPathRooted(dumpPath)) dumpPath = Path.Combine(RootDir, dumpPath);
            
            var dumpAsset = new UAsset(dumpPath, EngineVersion.VER_UE5_5, Mappings);
            Console.WriteLine($"\n=== Dump: {Path.GetFileName(dumpPath)} ===");
            Console.WriteLine($"  HasUnversioned={dumpAsset.HasUnversionedProperties}, FolderName: {dumpAsset.FolderName}");
            Console.WriteLine($"  PackageFlags: {dumpAsset.PackageFlags} (0x{(uint)dumpAsset.PackageFlags:X8})");
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
                Console.WriteLine($"  Export[{i}]: Name={exp.ObjectName}, Class={exp.GetExportClassType()}, Outer={exp.OuterIndex}, C#Type={exp.GetType().Name}, SerialOffset=0x{exp.SerialOffset:X}, SerialSize={exp.SerialSize}");
                
                if (exp is StructExport sexp)
                {
                    var superName = sexp.SuperStruct.IsImport() ? sexp.SuperStruct.ToImport(dumpAsset).ObjectName.ToString() : (sexp.SuperStruct.IsExport() ? sexp.SuperStruct.ToExport(dumpAsset).ObjectName.ToString() : $"idx={sexp.SuperStruct.Index}");
                    Console.WriteLine($"    StructExport: SuperStruct={superName}, LoadedProperties={sexp.LoadedProperties?.Length ?? 0}, Children={sexp.Children?.Length ?? 0}");
                    if (sexp.LoadedProperties != null)
                    {
                        for (int pi = 0; pi < sexp.LoadedProperties.Length; pi++)
                        {
                            var fp = sexp.LoadedProperties[pi];
                            Console.WriteLine($"      FProperty[{pi}]: Name={fp.Name}, SerializedType={fp.SerializedType}, ArrayDim={fp.ArrayDim}, ElementSize={fp.ElementSize}, Flags={fp.PropertyFlags}");
                        }
                    }
                    if (exp is ClassExport cexp)
                    {
                        Console.WriteLine($"    ClassExport: ClassFlags={cexp.ClassFlags}, ClassGeneratedBy={cexp.ClassGeneratedBy.Index}, ClassDefaultObject={cexp.ClassDefaultObject.Index}, FuncMap.Count={cexp.FuncMap?.Count ?? 0}");
                    }
                }
                
                // Dump raw export data for CDO
                if (exp.ObjectName?.Value?.Value?.StartsWith("Default__") == true)
                {
                    if (exp is UAssetAPI.ExportTypes.RawExport rawExp)
                    {
                        Console.WriteLine($"    RawExport CDO data ({rawExp.Data?.Length ?? 0} bytes):");
                        if (rawExp.Data != null && rawExp.Data.Length > 0)
                        {
                            for (int di = 0; di < Math.Min(rawExp.Data.Length, 256); di += 16)
                            {
                                var hexLine = string.Join(" ", rawExp.Data.Skip(di).Take(16).Select(b => $"{b:X2}"));
                                Console.WriteLine($"      0x{di:X4}: {hexLine}");
                            }
                        }
                    }
                    else if (exp is UAssetAPI.ExportTypes.NormalExport neCdo)
                    {
                        Console.WriteLine($"    NormalExport CDO: {neCdo.Data?.Count ?? 0} properties");
                        foreach (var p in neCdo.Data ?? new List<PropertyData>())
                        {
                            Console.WriteLine($"      {p.Name?.Value?.Value} ({p.PropertyType}) IsZero={p.IsZero}");
                            DumpProperty(p, "        ");
                        }
                    }
                }
                
                // Dump export data (properties) - skip CDO since we already printed it
                if (exp is UAssetAPI.ExportTypes.DataTableExport dte)
                {
                    Console.WriteLine($"    Rows ({dte.Table?.Data?.Count ?? 0}):");
                    foreach (var row in dte.Table?.Data ?? new List<StructPropertyData>())
                    {
                        Console.WriteLine($"      Row '{row.Name?.Value?.Value}':");
                        foreach (var p in row.Value ?? new List<PropertyData>())
                        {
                            DumpProperty(p, "        ");
                        }
                    }
                }
                else if (exp is UAssetAPI.ExportTypes.NormalExport normalExp && !exp.ObjectName?.Value?.Value?.StartsWith("Default__") == true)
                {
                    Console.WriteLine($"    Properties ({normalExp.Data.Count}):");
                    foreach (var prop in normalExp.Data)
                    {
                        DumpProperty(prop, "      ");
                    }
                }
            }
        }
        else
        {
            string uassetPath;
            if (args.Length > 0 && !args[0].StartsWith("--"))
            {
                uassetPath = args[0];
                if (!Path.IsPathRooted(uassetPath))
                    uassetPath = Path.Combine(RootDir, uassetPath);
            }
            else
            {
                uassetPath = Path.Combine(RootDir, "Cargos.uasset");
            }
            ProcessSingleFile(uassetPath, RootDir);
        }
    }
    
    static void DumpProperty(UAssetAPI.PropertyTypes.Objects.PropertyData prop, string indent)
    {
        var name = prop.Name?.ToString() ?? "?";
        var type = prop.PropertyType?.ToString() ?? "?";
        
        switch (prop)
        {
            case UAssetAPI.PropertyTypes.Structs.FontDataPropertyData fd:
                Console.WriteLine($"{indent}{name} (FontData):");
                if (fd.Value != null)
                {
                    Console.WriteLine($"{indent}  LocalFontFaceAsset: Index={fd.Value.LocalFontFaceAsset?.Index ?? 0}");
                    if (fd.Value.LocalFontFaceAsset?.Index == 0 && fd.Value.FontFilename != null)
                        Console.WriteLine($"{indent}  FontFilename: {fd.Value.FontFilename}");
                    Console.WriteLine($"{indent}  Hinting: {fd.Value.Hinting}");
                    Console.WriteLine($"{indent}  LoadingPolicy: {fd.Value.LoadingPolicy}");
                    Console.WriteLine($"{indent}  SubFaceIndex: {fd.Value.SubFaceIndex}");
                    Console.WriteLine($"{indent}  bIsCooked: {fd.Value.bIsCooked}");
                }
                break;
            case UAssetAPI.PropertyTypes.Structs.StructPropertyData spd:
                Console.WriteLine($"{indent}{name} (StructProperty):");
                if (spd.Value != null)
                {
                    foreach (var sp in spd.Value)
                        DumpProperty(sp, indent + "  ");
                }
                break;
            case UAssetAPI.PropertyTypes.Objects.ArrayPropertyData apd:
                Console.WriteLine($"{indent}{name} (Array[{apd.Value?.Length ?? 0}]):");
                if (apd.Value != null)
                {
                    for (int j = 0; j < apd.Value.Length; j++)
                        DumpProperty(apd.Value[j], indent + $"  [{j}] ");
                }
                break;
            case UAssetAPI.PropertyTypes.Objects.StrPropertyData str:
                Console.WriteLine($"{indent}{name} (Str): {str.Value?.Value ?? "(null)"}");
                break;
            case UAssetAPI.PropertyTypes.Objects.NamePropertyData np:
                Console.WriteLine($"{indent}{name} (Name): {np.Value?.Value?.Value ?? "(null)"}");
                break;
            case UAssetAPI.PropertyTypes.Objects.IntPropertyData ip:
                Console.WriteLine($"{indent}{name} (Int): {ip.Value}");
                break;
            case UAssetAPI.PropertyTypes.Objects.BytePropertyData bp:
                Console.WriteLine($"{indent}{name} (Byte): {bp.Value} [{bp.EnumType?.Value?.Value ?? ""}]");
                break;
            case UAssetAPI.PropertyTypes.Objects.BoolPropertyData bpd:
                Console.WriteLine($"{indent}{name} (Bool): {bpd.Value}");
                break;
            case UAssetAPI.PropertyTypes.Objects.FloatPropertyData fp:
                Console.WriteLine($"{indent}{name} (Float): {fp.Value}");
                break;
            case UAssetAPI.PropertyTypes.Objects.SoftObjectPropertyData sop:
                Console.WriteLine($"{indent}{name} (SoftObject):");
                Console.WriteLine($"{indent}  PackageName: '{sop.Value.AssetPath.PackageName?.Value?.Value ?? "(null)"}'");
                Console.WriteLine($"{indent}  AssetName: '{sop.Value.AssetPath.AssetName?.Value?.Value ?? "(null)"}'");
                Console.WriteLine($"{indent}  SubPathString: '{sop.Value.SubPathString?.Value ?? "(null)"}'");
                break;
            case UAssetAPI.PropertyTypes.Objects.ObjectPropertyData op:
                Console.WriteLine($"{indent}{name} (Object): Index={op.Value}");
                break;
            case UAssetAPI.PropertyTypes.Objects.EnumPropertyData ep:
                Console.WriteLine($"{indent}{name} (Enum): {ep.Value?.Value?.Value ?? "(null)"}");
                break;
            case UAssetAPI.PropertyTypes.Objects.MapPropertyData mp:
                Console.WriteLine($"{indent}{name} (Map[{mp.Value?.Count ?? 0}])");
                break;
            default:
                Console.WriteLine($"{indent}{name} ({type})");
                break;
        }
    }
    
    // ========================================================================
    // --add-rows: Generic DataTable row addition (clone + construct modes)
    // ========================================================================
    static void AddRows(string configPath, string templatePath, string outputDir)
    {
        if (!File.Exists(configPath)) { Console.WriteLine($"Error: Config not found: {configPath}"); return; }
        if (!File.Exists(templatePath)) { Console.WriteLine($"Error: Template not found: {templatePath}"); return; }
        
        var configJson = File.ReadAllText(configPath);
        using var doc = JsonDocument.Parse(configJson);
        var root = doc.RootElement;
        
        // Validate
        if (!root.TryGetProperty("rows", out _) && !root.TryGetProperty("construct_rows", out _))
        {
            Console.WriteLine("Error: Config must have 'rows' and/or 'construct_rows'");
            return;
        }
        
        Console.WriteLine($"Loading template: {Path.GetFileName(templatePath)}");
        var asset = new UAsset(templatePath, EngineVersion.VER_UE5_5, Mappings);
        
        var dtExport = FindDataTable(asset);
        if (dtExport == null) return;
        
        Console.WriteLine($"Existing rows: {dtExport.Table.Data.Count}");
        
        var outputFileName = root.TryGetProperty("output_filename", out var ofProp)
            ? ofProp.GetString()!
            : Path.GetFileNameWithoutExtension(templatePath);
        
        // === Clone mode ===
        if (root.TryGetProperty("rows", out var rows))
        {
            // Find template row
            StructPropertyData templateRow;
            if (root.TryGetProperty("template_row_match", out var matchProp))
            {
                StructPropertyData? matched = null;
                foreach (var row in dtExport.Table.Data)
                {
                    if (row is StructPropertyData spd)
                    {
                        foreach (var prop in spd.Value)
                        {
                            foreach (var matchEntry in matchProp.EnumerateObject())
                            {
                                // Special case: match by DataTable row name
                                if (matchEntry.Name == "RowName")
                                {
                                    var matchValue = matchEntry.Value.GetString()!;
                                    bool matches = matchValue.Contains("*")
                                        ? spd.Name.Value.Value.Contains(matchValue.Trim('*'))
                                        : spd.Name.Value.Value == matchValue;
                                    if (matches) matched = spd;
                                    continue;
                                }

                                if (prop.Name.Value.Value == matchEntry.Name)
                                {
                                    var matchValue = matchEntry.Value.GetString()!;
                                    string? propValue = null;
                                    if (prop is EnumPropertyData ep) propValue = ep.Value?.Value?.Value;
                                    else if (prop is StrPropertyData sp) propValue = sp.Value?.Value;
                                    else if (prop is NamePropertyData np) propValue = np.Value?.Value?.Value;
                                    else if (prop is TextPropertyData tp) propValue = tp.Value?.Value;
                                    
                                    if (propValue != null)
                                    {
                                        bool matches = matchValue.Contains("*")
                                            ? propValue.Contains(matchValue.Trim('*'))
                                            : propValue == matchValue;
                                        if (matches) matched = spd;
                                    }
                                }
                            }
                        }
                    }
                }
                templateRow = matched ?? (StructPropertyData)dtExport.Table.Data[^1];
                Console.WriteLine($"  Template row (matched): {templateRow.Name.Value.Value}");
            }
            else
            {
                var rowIdx = root.TryGetProperty("template_row", out var trProp)
                    ? (trProp.ValueKind == JsonValueKind.String
                        ? (trProp.GetString() == "first" ? 0 : dtExport.Table.Data.Count - 1)
                        : trProp.GetInt32())
                    : dtExport.Table.Data.Count - 1;
                templateRow = (StructPropertyData)dtExport.Table.Data[rowIdx];
            }
            
            int added = 0;
            foreach (var rowEntry in rows.EnumerateArray())
            {
                var rowName = rowEntry.GetProperty("row_name").GetString()!;
                var fnameNumber = rowEntry.TryGetProperty("row_name_number", out var rnnProp) ? rnnProp.GetInt32() : -1;
                
                var newRow = (StructPropertyData)templateRow.Clone();
                newRow.Name = fnameNumber >= 0
                    ? new FName(asset, rowName, fnameNumber)
                    : FName.FromString(asset, rowName);
                
                if (rowEntry.TryGetProperty("patches", out var patches))
                    ApplyPatches(newRow.Value, patches, asset);
                
                dtExport.Table.Data.Add(newRow);
                Console.WriteLine($"  Added row: {rowName}");
                added++;
            }
            Console.WriteLine($"Added {added} cloned rows.");
        }
        
        // === Construct mode ===
        if (root.TryGetProperty("construct_rows", out var constructRows))
        {
            int added = 0;
            foreach (var rowEntry in constructRows.EnumerateArray())
            {
                var rowName = rowEntry.GetProperty("row_name").GetString()!;
                var structType = rowEntry.GetProperty("struct_type").GetString()!;
                var copyAncestry = rowEntry.TryGetProperty("copy_ancestry", out var caProp) && caProp.GetBoolean();
                
                var rowStruct = new StructPropertyData(FName.FromString(asset, rowName))
                {
                    StructType = FName.FromString(asset, structType),
                    Value = new List<PropertyData>()
                };
                
                foreach (var propEntry in rowEntry.GetProperty("properties").EnumerateArray())
                {
                    var propName = propEntry.GetProperty("name").GetString()!;
                    var propType = propEntry.GetProperty("type").GetString()!;
                    
                    PropertyData newProp;
                    switch (propType)
                    {
                        case "SoftObject":
                            newProp = new SoftObjectPropertyData(FName.FromString(asset, propName))
                            {
                                Value = new FSoftObjectPath(
                                    new FTopLevelAssetPath(
                                        FName.FromString(asset, propEntry.GetProperty("package").GetString()!),
                                        FName.FromString(asset, propEntry.GetProperty("asset").GetString()!)
                                    ), null)
                            };
                            break;
                        case "ObjectRef":
                            var matchImport = propEntry.GetProperty("match_import").GetString()!;
                            int importIdx = -1;
                            for (int i = 0; i < asset.Imports.Count; i++)
                            {
                                if (asset.Imports[i].ObjectName?.Value?.Value == matchImport)
                                { importIdx = -(i + 1); break; }
                            }
                            newProp = new ObjectPropertyData(FName.FromString(asset, propName))
                            { Value = new FPackageIndex(importIdx) };
                            break;
                        case "Int":
                            var intVal = propEntry.GetProperty("value").GetInt32();
                            newProp = new IntPropertyData(FName.FromString(asset, propName))
                            { Value = intVal, IsZero = (intVal == 0) };
                            break;
                        case "Float":
                            newProp = new FloatPropertyData(FName.FromString(asset, propName))
                            { Value = propEntry.GetProperty("value").GetSingle() };
                            break;
                        case "Bool":
                            newProp = new BoolPropertyData(FName.FromString(asset, propName))
                            { Value = propEntry.GetProperty("value").GetBoolean() };
                            break;
                        case "String":
                            newProp = new StrPropertyData(FName.FromString(asset, propName))
                            { Value = FString.FromString(propEntry.GetProperty("value").GetString()) };
                            break;
                        default:
                            Console.WriteLine($"  Warning: Unknown property type '{propType}' for '{propName}'");
                            continue;
                    }
                    rowStruct.Value.Add(newProp);
                }
                
                if (copyAncestry && dtExport.Table.Data.Count > 0)
                {
                    var lastRow = dtExport.Table.Data[^1];
                    rowStruct.Ancestry = (AncestryInfo)lastRow.Ancestry.Clone();
                }
                
                dtExport.Table.Data.Add(rowStruct);
                Console.WriteLine($"  Constructed row: {rowName}");
                added++;
            }
            Console.WriteLine($"Added {added} constructed rows.");
        }
        
        Console.WriteLine($"Total rows: {dtExport.Table.Data.Count}");
        asset.ResolveAncestries();
        
        Directory.CreateDirectory(outputDir);
        var outputPath = Path.Combine(outputDir, $"{outputFileName}.uasset");
        asset.Write(outputPath);
        Console.WriteLine($"Written: {outputFileName}.uasset + {outputFileName}.uexp to {outputDir}");
    }
    
    // ========================================================================
    // --clone-asset: Generic asset cloning, renaming, and patching
    // ========================================================================
    static void CloneAsset(string configPath, string templatePath, string outputDir)
    {
        if (!File.Exists(configPath)) { Console.WriteLine($"Error: Config not found: {configPath}"); return; }
        if (!File.Exists(templatePath)) { Console.WriteLine($"Error: Template not found: {templatePath}"); return; }
        
        var configJson = File.ReadAllText(configPath);
        using var doc = JsonDocument.Parse(configJson);
        var root = doc.RootElement;
        
        // Support single or multi-asset configs
        JsonElement[] assetSpecs;
        if (root.TryGetProperty("assets", out var assetsArray))
            assetSpecs = assetsArray.EnumerateArray().ToArray();
        else
            assetSpecs = new[] { root };
        
        foreach (var spec in assetSpecs)
        {
            if (!spec.TryGetProperty("new_name", out _) || !spec.TryGetProperty("new_path", out _))
            {
                Console.WriteLine("Error: Each asset spec requires 'new_name' and 'new_path'");
                continue;
            }
            
            var newName = spec.GetProperty("new_name").GetString()!;
            var newPath = spec.GetProperty("new_path").GetString()!;
            var renameExports = spec.TryGetProperty("rename_exports", out var reProp) && reProp.GetBoolean();
            var renameImports = spec.TryGetProperty("rename_imports", out var riProp) && riProp.GetBoolean();
            var fnameNumber = spec.TryGetProperty("fname_number", out var fnProp) ? fnProp.GetInt32() : -1;
            
            Console.WriteLine($"\nCloning asset: {newName}");
            Console.WriteLine($"  Template: {Path.GetFileName(templatePath)}");
            Console.WriteLine($"  New path: {newPath}");
            
            var asset = new UAsset(templatePath, EngineVersion.VER_UE5_5, Mappings);
            var oldName = Path.GetFileNameWithoutExtension(templatePath);
            
            // Detect old export name (may differ from filename, e.g. BasicTire_45 → "BasicTire")
            string oldExportName;
            if (spec.TryGetProperty("old_name", out var onProp))
            {
                oldExportName = onProp.GetString()!;
            }
            else
            {
                oldExportName = oldName;
                foreach (var export in asset.Exports)
                {
                    if (export is NormalExport && !export.ObjectName.Value.Value.StartsWith("Default__"))
                    {
                        var eName = export.ObjectName.Value.Value;
                        if (eName != oldName) { oldExportName = eName; break; }
                    }
                }
            }
            
            // 1. Patch FolderName and PackageGuid
            asset.FolderName = FString.FromString(newPath);
            asset.PackageGuid = Guid.NewGuid();
            
            // 2. Rename exports
            if (renameExports)
            {
                foreach (var export in asset.Exports)
                {
                    var exportName = export.ObjectName.Value.Value;
                    if (exportName.Contains(oldExportName) || exportName.Contains(oldName))
                    {
                        var newExportName = exportName.Replace(oldExportName, newName).Replace(oldName, newName);
                        export.ObjectName = fnameNumber >= 0
                            ? new FName(asset, newExportName, fnameNumber)
                            : FName.FromString(asset, newExportName);
                        Console.WriteLine($"  Renamed export: {exportName} -> {newExportName}");
                    }
                }
            }
            
            // 3. Rename imports
            if (renameImports)
            {
                for (int i = 0; i < asset.Imports.Count; i++)
                {
                    var imp = asset.Imports[i];
                    var impName = imp.ObjectName.Value.Value;
                    if (impName.Contains(oldExportName) || impName.Contains(oldName))
                    {
                        var newImpName = impName.Replace(oldExportName, newName).Replace(oldName, newName);
                        imp.ObjectName = fnameNumber >= 0
                            ? new FName(asset, newImpName, fnameNumber)
                            : FName.FromString(asset, newImpName);
                        Console.WriteLine($"  Renamed import: {impName} -> {newImpName}");
                    }
                }
            }
            
            // 4. Patch all NameMap entries referencing old path/name
            var nameList = asset.GetNameMapIndexList();
            for (int ni = 0; ni < nameList.Count; ni++)
            {
                var entry = nameList[ni]?.Value;
                if (entry == null) continue;
                string replaced = entry;
                if (entry.Contains(oldExportName))
                    replaced = replaced.Replace(oldExportName, newName);
                if (entry != oldName && entry.Contains(oldName))
                    replaced = replaced.Replace(oldName, newName);
                if (replaced != entry)
                {
                    asset.SetNameReference(ni, FString.FromString(replaced));
                    Console.WriteLine($"  Renamed NameMap[{ni}]: {entry} -> {replaced}");
                }
            }
            
            // 5. Import replacements
            if (spec.TryGetProperty("import_replacements", out var irProp))
            {
                foreach (var replacement in irProp.EnumerateArray())
                {
                    var matchClass = replacement.GetProperty("match_class").GetString()!;
                    var newPkgPath = replacement.GetProperty("new_package_path").GetString()!;
                    var newImpName = replacement.GetProperty("new_name").GetString()!;
                    var matchName = replacement.TryGetProperty("match_name", out var mnProp) ? mnProp.GetString() : null;
                    int? importIndex = replacement.TryGetProperty("import_index", out var iiProp) ? iiProp.GetInt32() : null;
                    bool replaceAll = replacement.TryGetProperty("replace_all", out var raProp) && raProp.GetBoolean();
                    
                    // Collect all matching import indices
                    var matches = new List<(int meshIdx, int pkgIdx)>();
                    for (int i = 0; i < asset.Imports.Count; i++)
                    {
                        if (asset.Imports[i].ClassName.Value.Value != matchClass) continue;
                        if (matchName != null && asset.Imports[i].ObjectName.Value.Value != matchName) continue;
                        
                        int pkgIdx = -1;
                        if (asset.Imports[i].OuterIndex.Index < 0)
                            pkgIdx = -asset.Imports[i].OuterIndex.Index - 1;
                        matches.Add((i, pkgIdx));
                    }
                    
                    if (importIndex.HasValue)
                    {
                        // Target specific import slot by import_index
                        if (importIndex.Value >= 0 && importIndex.Value < matches.Count)
                        {
                            var (meshIdx, pkgIdx) = matches[importIndex.Value];
                            if (pkgIdx >= 0 && pkgIdx < asset.Imports.Count)
                            {
                                asset.Imports[pkgIdx].ObjectName = FName.FromString(asset, newPkgPath);
                                Console.WriteLine($"  Replaced {matchClass}[{importIndex.Value}] package: {newPkgPath}");
                            }
                            asset.Imports[meshIdx].ObjectName = FName.FromString(asset, newImpName);
                            Console.WriteLine($"  Replaced {matchClass}[{importIndex.Value}] import: {newImpName}");
                        }
                        else
                        {
                            Console.WriteLine($"  WARNING: import_index {importIndex.Value} out of range (found {matches.Count} matches)");
                        }
                    }
                    else if (replaceAll)
                    {
                        // Replace ALL matching imports
                        foreach (var (meshIdx, pkgIdx) in matches)
                        {
                            if (pkgIdx >= 0 && pkgIdx < asset.Imports.Count)
                            {
                                asset.Imports[pkgIdx].ObjectName = FName.FromString(asset, newPkgPath);
                                Console.WriteLine($"  Replaced {matchClass} package: {newPkgPath}");
                            }
                            asset.Imports[meshIdx].ObjectName = FName.FromString(asset, newImpName);
                            Console.WriteLine($"  Replaced {matchClass} import: {newImpName}");
                        }
                    }
                    else
                    {
                        // Default: replace the LAST matching import
                        if (matches.Count > 0)
                        {
                            var (meshIdx, pkgIdx) = matches[^1];
                            if (pkgIdx >= 0 && pkgIdx < asset.Imports.Count)
                            {
                                asset.Imports[pkgIdx].ObjectName = FName.FromString(asset, newPkgPath);
                                Console.WriteLine($"  Replaced {matchClass} package: {newPkgPath}");
                            }
                            asset.Imports[meshIdx].ObjectName = FName.FromString(asset, newImpName);
                            Console.WriteLine($"  Replaced {matchClass} import: {newImpName}");
                        }
                    }
                }
            }
            
            // 6. Export patches
            if (spec.TryGetProperty("export_patches", out var epProp))
            {
                foreach (var exportPatch in epProp.EnumerateArray())
                {
                    var matchClass = exportPatch.TryGetProperty("match_class", out var mcProp) ? mcProp.GetString() : null;
                    
                    foreach (var export in asset.Exports)
                    {
                        if (export is NormalExport ne)
                        {
                            bool classMatch = matchClass == null || export.GetExportClassType()?.Value?.Value == matchClass;
                            if (classMatch && exportPatch.TryGetProperty("patches", out var patches))
                                ApplyPatches(ne.Data, patches, asset);
                        }
                    }
                }
            }
            
// Write output
            var assetOutputDir = Path.Combine(outputDir, newName);
            Directory.CreateDirectory(assetOutputDir);
            var outputPath = Path.Combine(assetOutputDir, $"{newName}.uasset");
            asset.Write(outputPath);
            Console.WriteLine($"  Written: {newName}.uasset + .uexp to {assetOutputDir}");
        }
    }
    
    // ========================================================================
    // --patch-export-props: Patch properties on the main export directly
    // ========================================================================
    static void PatchExportProps(string configPath, string templatePath, string outputDir)
    {
        if (!File.Exists(configPath)) { Console.WriteLine($"Error: Config not found: {configPath}"); return; }
        if (!File.Exists(templatePath)) { Console.WriteLine($"Error: Template not found: {templatePath}"); return; }
        
        var configJson = File.ReadAllText(configPath);
        using var doc = JsonDocument.Parse(configJson);
        var root = doc.RootElement;
        
        Console.WriteLine($"Loading: {Path.GetFileName(templatePath)}");
        var asset = new UAsset(templatePath, EngineVersion.VER_UE5_5, Mappings);
        
        var outputFileName = root.TryGetProperty("output_filename", out var ofProp)
            ? ofProp.GetString()!
            : Path.GetFileNameWithoutExtension(templatePath);
        
        // Find the first NormalExport (typically Export[0])
        NormalExport? mainExport = null;
        foreach (var export in asset.Exports)
        {
            if (export is NormalExport ne)
            {
                mainExport = ne;
                break;
            }
        }
        if (mainExport == null)
        {
            // Try DataTableExport
            foreach (var export in asset.Exports)
            {
                if (export is DataTableExport dte)
                {
                    mainExport = dte;
                    break;
                }
            }
        }
        if (mainExport == null) { Console.WriteLine("Error: No NormalExport found"); return; }
        
        Console.WriteLine($"  Export: {mainExport.ObjectName.Value.Value}");
        
        // Apply patches on the export's properties
        if (root.TryGetProperty("patches", out var patches))
        {
            ApplyPatches(mainExport.Data, patches, asset);
            Console.WriteLine("  Applied export property patches");
        }
        
        asset.ResolveAncestries();
        Directory.CreateDirectory(outputDir);
        var outputPath = Path.Combine(outputDir, $"{outputFileName}.uasset");
        asset.Write(outputPath);
        Console.WriteLine($"Written: {outputFileName}.uasset + {outputFileName}.uexp to {outputDir}");
    }
    
    // ========================================================================
    // --patch-named-exports: Patch properties on specific named exports
    // ========================================================================
    static void PatchNamedExports(string configPath, string templatePath, string outputDir)
    {
        if (!File.Exists(configPath)) { Console.WriteLine($"Error: Config not found: {configPath}"); return; }
        if (!File.Exists(templatePath)) { Console.WriteLine($"Error: Template not found: {templatePath}"); return; }
        
        var configJson = File.ReadAllText(configPath);
        using var doc = JsonDocument.Parse(configJson);
        var root = doc.RootElement;
        
        if (!root.TryGetProperty("exports", out var exportPatches))
        {
            Console.WriteLine("Error: Config must have 'exports' array with {export_name, patches} entries");
            return;
        }
        
        Console.WriteLine($"Loading: {Path.GetFileName(templatePath)}");
        var asset = new UAsset(templatePath, EngineVersion.VER_UE5_5, Mappings);
        
        var outputFileName = root.TryGetProperty("output_filename", out var ofProp)
            ? ofProp.GetString()!
            : Path.GetFileNameWithoutExtension(templatePath);
        
        int patched = 0;
        foreach (var exportSpec in exportPatches.EnumerateArray())
        {
            var exportName = exportSpec.GetProperty("export_name").GetString()!;
            
            Export? targetExport = null;
            foreach (var export in asset.Exports)
            {
                if (export.ObjectName.Value.Value == exportName)
                {
                    targetExport = export;
                    break;
                }
            }
            
            if (targetExport == null)
            {
                Console.WriteLine($"  Warning: Export '{exportName}' not found, skipping");
                continue;
            }
            
            NormalExport? normalExport = null;
            if (targetExport is NormalExport ne)
            {
                normalExport = ne;
            }
            else if (targetExport is RawExport rawExp)
            {
                try
                {
                    var converted = rawExp.ConvertToChildExport<NormalExport>();
                    var reader = new AssetBinaryReader(new MemoryStream(rawExp.Data ?? []))
                    {
                        Asset = asset
                    };
                    converted.Data = new List<PropertyData>();
                    var nextStarting = rawExp.Data?.Length ?? 0;
                    converted.Read(reader, nextStarting);
                    var idx = asset.Exports.IndexOf(rawExp);
                    asset.Exports[idx] = converted;
                    normalExport = converted;
                    Console.WriteLine($"  Reparsed RawExport '{exportName}' as NormalExport ({converted.Data?.Count ?? 0} properties)");
                }
                catch (Exception convEx)
                {
                    Console.WriteLine($"  Warning: RawExport reparse failed for '{exportName}': {convEx.Message}");
                    continue;
                }
            }
            
            if (normalExport == null)
            {
                Console.WriteLine($"  Warning: Export '{exportName}' is not a NormalExport, skipping");
                continue;
            }
            
            if (exportSpec.TryGetProperty("patches", out var patches))
            {
                ApplyPatches(normalExport.Data, patches, asset);
                Console.WriteLine($"  Patched export: {exportName}");
                patched++;
            }
        }
        
        Console.WriteLine($"Patched {patched} exports.");
        
        asset.ResolveAncestries();
        Directory.CreateDirectory(outputDir);
        var outputPath = Path.Combine(outputDir, $"{outputFileName}.uasset");
        asset.Write(outputPath);
        Console.WriteLine($"Written: {outputFileName}.uasset + {outputFileName}.uexp to {outputDir}");
    }
    
    // ========================================================================
    // --patch-rows: Patch existing DataTable rows by RowName
    // ========================================================================
    static void PatchRows(string configPath, string templatePath, string outputDir)
    {
        if (!File.Exists(configPath)) { Console.WriteLine($"Error: Config not found: {configPath}"); return; }
        if (!File.Exists(templatePath)) { Console.WriteLine($"Error: Template not found: {templatePath}"); return; }
        
        var configJson = File.ReadAllText(configPath);
        using var doc = JsonDocument.Parse(configJson);
        var root = doc.RootElement;
        
        if (!root.TryGetProperty("patches", out var rowPatches))
        {
            Console.WriteLine("Error: Config must have 'patches' array with {row_name, patches} entries");
            return;
        }
        
        Console.WriteLine($"Loading template: {Path.GetFileName(templatePath)}");
        var asset = new UAsset(templatePath, EngineVersion.VER_UE5_5, Mappings);
        
        var dtExport = FindDataTable(asset);
        if (dtExport == null) return;
        
        Console.WriteLine($"Existing rows: {dtExport.Table.Data.Count}");
        
        var outputFileName = root.TryGetProperty("output_filename", out var ofProp)
            ? ofProp.GetString()!
            : Path.GetFileNameWithoutExtension(templatePath);
        
        int patched = 0;
        foreach (var rowPatch in rowPatches.EnumerateArray())
        {
            var rowName = rowPatch.GetProperty("row_name").GetString()!;
            
            StructPropertyData? targetRow = null;
            foreach (var row in dtExport.Table.Data)
            {
                if (row is StructPropertyData spd && spd.Name.Value.Value == rowName)
                {
                    targetRow = spd;
                    break;
                }
            }
            
            if (targetRow == null)
            {
                Console.WriteLine($"  Warning: Row '{rowName}' not found, skipping");
                continue;
            }
            
            if (rowPatch.TryGetProperty("patches", out var patches))
            {
                ApplyPatches(targetRow.Value, patches, asset);
                Console.WriteLine($"  Patched row: {rowName}");
                patched++;
            }
        }
        
        Console.WriteLine($"Patched {patched} rows.");
        Console.WriteLine($"Total rows: {dtExport.Table.Data.Count}");
        asset.ResolveAncestries();
        
        Directory.CreateDirectory(outputDir);
        var outputPath = Path.Combine(outputDir, $"{outputFileName}.uasset");
        asset.Write(outputPath);
        Console.WriteLine($"Written: {outputFileName}.uasset + {outputFileName}.uexp to {outputDir}");
    }
    
    // ========================================================================
    // --patch-cdo-arrays: Generic CDO array patching
    // ========================================================================
    static void PatchCdoArrays(string configPath, string templatePath, string outputDir)
    {
        if (!File.Exists(configPath)) { Console.WriteLine($"Error: Config not found: {configPath}"); return; }
        if (!File.Exists(templatePath)) { Console.WriteLine($"Error: Template not found: {templatePath}"); return; }
        
        var configJson = File.ReadAllText(configPath);
        using var doc = JsonDocument.Parse(configJson);
        var root = doc.RootElement;
        
        if (!root.TryGetProperty("arrays", out _))
        {
            Console.WriteLine("Error: Config must have 'arrays'");
            return;
        }
        
        var outputFileName = root.TryGetProperty("output_filename", out var ofProp)
            ? ofProp.GetString()!
            : Path.GetFileNameWithoutExtension(templatePath);
        
        Console.WriteLine($"Loading: {Path.GetFileName(templatePath)}");
        DebugPrintSchema("MTVehicleColorSlot");
        DebugPrintSchema("MTVehicleColor");
        var asset = new UAsset(templatePath, EngineVersion.VER_UE5_5, Mappings);
        
        NormalExport? cdoExport = null;
        foreach (var export in asset.Exports)
        {
            if (export.ObjectName.Value.Value.StartsWith("Default__"))
            {
                if (export is NormalExport ne)
                {
                    cdoExport = ne;
                    break;
                }
                else if (export is RawExport rawExp)
                {
                    try
                    {
                        var converted = rawExp.ConvertToChildExport<NormalExport>();
                        var reader = new AssetBinaryReader(new MemoryStream(rawExp.Data ?? []))
                        {
                            Asset = asset
                        };
                        converted.Data = new List<PropertyData>();
                        var nextStarting = rawExp.Data?.Length ?? 0;
                        converted.Read(reader, nextStarting);
                        // Replace in asset's exports list
                        var idx = asset.Exports.IndexOf(rawExp);
                        asset.Exports[idx] = converted;
                        cdoExport = converted;
                        Console.WriteLine($"  Reparsed RawExport CDO as NormalExport ({converted.Data?.Count ?? 0} properties)");
                        break;
                    }
                    catch (Exception convEx)
                    {
                        Console.WriteLine($"  Warning: CDO RawExport reparse failed: {convEx.Message}");
                        Console.WriteLine(convEx.ToString());
                    }
                }
            }
        }
        
        if (cdoExport == null)
        {
            Console.WriteLine("Error: No Default__ CDO export found");
            return;
        }
        
        // Apply CDO-level property patches (not array entries)
        if (root.TryGetProperty("cdo_patches", out var cdoPatches))
        {
            ApplyPatches(cdoExport.Data, cdoPatches, asset);
            Console.WriteLine("  Applied CDO patches");
        }
        
        foreach (var arraySpec in root.GetProperty("arrays").EnumerateArray())
        {
            var propertyName = arraySpec.GetProperty("property_name").GetString()!;
            
            ArrayPropertyData? arrProp = null;
            StructPropertyData? fallbackTemplate = null;
            foreach (var prop in cdoExport.Data)
            {
                if (prop.Name.Value.Value == propertyName && prop is ArrayPropertyData ap)
                { arrProp = ap; break; }
            }
            
            if (arrProp == null)
            {
                // Try to create from template_source
                if (arraySpec.TryGetProperty("template_source", out var tsProp))
                {
                    var templatePath2 = tsProp.GetString()!;
                    if (!File.Exists(templatePath2))
                    {
                        Console.WriteLine($"  Error: Template not found: {templatePath2}");
                        continue;
                    }
                    var templateAsset = new UAsset(templatePath2, EngineVersion.VER_UE5_5, Mappings);
                    NormalExport? templateCdo = null;
                    foreach (var exp in templateAsset.Exports)
                    {
                        if (exp is NormalExport ne && exp.ObjectName.Value.Value.StartsWith("Default__"))
                        { templateCdo = ne; break; }
                    }
                    if (templateCdo == null)
                    {
                        Console.WriteLine($"  Error: No CDO in template for {propertyName}");
                        continue;
                    }
                    ArrayPropertyData? templateArr = null;
                    foreach (var p in templateCdo.Data)
                    {
                        if (p.Name.Value.Value == propertyName && p is ArrayPropertyData ap)
                        { templateArr = ap; break; }
                    }
                    if (templateArr == null || templateArr.Value.Length == 0)
                    {
                        Console.WriteLine($"  Error: No {propertyName} in template");
                        continue;
                    }
                    fallbackTemplate = (StructPropertyData)templateArr.Value[0];
                    // Create new array in target CDO
                    arrProp = new ArrayPropertyData(new FName(cdoExport.Asset, propertyName));
                    arrProp.Value = [];
                    cdoExport.Data.Add(arrProp);
                    Console.WriteLine($"  Created {propertyName} array from template");
                }
                else
                {
                    Console.WriteLine($"  Error: No {propertyName} array found in CDO");
                    continue;
                }
            }
            
            Console.WriteLine($"  Existing {propertyName}: {arrProp.Value.Length}");
            bool replaceArray = arraySpec.TryGetProperty("replace", out var replaceProp) && replaceProp.GetBoolean();
            var configList = replaceArray
                ? new List<PropertyData>()
                : new List<PropertyData>(arrProp.Value);
            if (replaceArray)
                Console.WriteLine($"  Replace mode: clearing existing {propertyName} entries");
            var templateEntry = arrProp.Value.Length > 0
                ? (StructPropertyData)arrProp.Value[0]
                : fallbackTemplate!;
            
            foreach (var entry in arraySpec.GetProperty("entries").EnumerateArray())
            {
                var newEntry = (StructPropertyData)templateEntry.Clone();
                if (entry.TryGetProperty("patches", out var patches))
                    ApplyPatches(newEntry.Value, patches, asset);
                configList.Add(newEntry);
                Console.WriteLine($"  Added {propertyName} entry");
            }
            
            arrProp.Value = configList.ToArray();
            Console.WriteLine($"  Total {propertyName}: {arrProp.Value.Length}");
        }
        
        asset.ResolveAncestries();
        
        Directory.CreateDirectory(outputDir);
        var outputPath = Path.Combine(outputDir, $"{outputFileName}.uasset");
        asset.Write(outputPath);
        Console.WriteLine($"Written: {outputFileName}.uasset + .uexp to {outputDir}");
    }
    
    // ========================================================================
    // Property Patch Engine
    // ========================================================================
    static void ApplyPatches(IList<PropertyData> properties, JsonElement patches, UAsset asset)
    {
        foreach (var patch in patches.EnumerateArray())
        {
            var path = patch.GetProperty("path").GetString()!;
            var op = patch.GetProperty("op").GetString()!;
            ApplyPatch(properties, path, op, patch, asset);
        }
    }
    
    static void ApplyPatch(IList<PropertyData> properties, string path, string op, JsonElement patch, UAsset asset)
    {
        switch (op)
        {
            case "set":
            {
                var prop = ResolveProperty(properties, path);
                if (prop == null && !path.Contains('.'))
                {
                    // Cloned entries from zero-masked vanilla structs (e.g.
                    // Export_Harbor's existing DemandConfigs) omit
                    // default-valued fields entirely, so a scalar 'set' has
                    // nothing to hit. Create the field instead of warning —
                    // the unversioned header generator matches properties by
                    // name, so append order is irrelevant.
                    var newVal = patch.GetProperty("value");
                    if (newVal.ValueKind == JsonValueKind.Number)
                    {
                        // "2.0" stays Float even when the value is whole;
                        // "10" is Int. Distinguish via the raw JSON text.
                        bool isFloat = newVal.GetRawText().Contains('.');
                        prop = isFloat
                            ? new FloatPropertyData(new FName(asset, path))
                            : new IntPropertyData(new FName(asset, path));
                    }
                    else if (newVal.ValueKind is JsonValueKind.True or JsonValueKind.False)
                    {
                        prop = new BoolPropertyData(new FName(asset, path));
                    }
                    if (prop != null)
                    {
                        properties.Add(prop);
                        Console.WriteLine($"    Added missing property '{path}' ({prop.PropertyType})");
                    }
                }
                if (prop == null) { Console.WriteLine($"    Warning: Property '{path}' not found for 'set'"); break; }
                var val = patch.GetProperty("value");
                switch (val.ValueKind)
                {
                    case JsonValueKind.Number:
                        SetNumericProperty(prop, val.GetSingle());
                        break;
                    case JsonValueKind.True:
                    case JsonValueKind.False:
                        if (prop is BoolPropertyData bp) bp.Value = val.GetBoolean();
                        break;
                    case JsonValueKind.String:
                        if (prop is StrPropertyData sp) sp.Value = FString.FromString(val.GetString());
                        else if (prop is NamePropertyData np) np.Value = FName.FromString(asset, val.GetString()!);
                        else if (prop is TextPropertyData tp)
                        {
                            tp.Namespace = FString.FromString("");
                            tp.Value = FString.FromString(val.GetString()!);
                            tp.CultureInvariantString = FString.FromString(val.GetString()!);
                            tp.HistoryType = TextHistoryType.Base;
                        }
                        else if (prop is SoftObjectPropertyData softStr)
                        {
                            // 0.7.19 CargoRow format: soft class ref stored with the
                            // class name in AssetName and an empty PackageName
                            softStr.Value = new FSoftObjectPath(
                                new FTopLevelAssetPath(new FName(asset, 0), FName.FromString(asset, val.GetString()!)), null);
                            Console.WriteLine($"    set (soft path): {path} -> {val.GetString()}");
                        }
                        else
                        {
                            Console.WriteLine($"    [type-probe] cannot set string on '{path}': {prop.GetType().Name}");
                        }
                        break;
                }
                break;
            }
            
            case "set_enum":
            {
                var prop = ResolveProperty(properties, path);
                if (prop is EnumPropertyData ep)
                {
                    // Qualify with the property's enum type and add to the
                    // NameMap (FName.FromString) — DefineDummy leaves a dummy
                    // FName that newer UAssetAPI refuses to serialize.
                    var enumTypeName = ep.EnumType?.Value?.Value;
                    var val = patch.GetProperty("value").GetString()!;
                    ep.Value = !string.IsNullOrEmpty(enumTypeName) && !val.Contains("::")
                        ? FName.FromString(asset, $"{enumTypeName}::{val}")
                        : FName.FromString(asset, val);
                }
                break;
            }
            
            case "set_enum_array":
            {
                var prop = ResolveProperty(properties, path);
                if (prop is ArrayPropertyData arr)
                    SetEnumArray(arr, patch.GetProperty("values"), asset,
                        patch.GetProperty("enum_type").GetString()!);
                break;
            }
            
            case "set_localization_guid":
            {
                var prop = ResolveProperty(properties, path);
                if (prop != null)
                {
                    string? displayText = patch.TryGetProperty("value", out var vProp) ? vProp.GetString() : null;
                    SetLocalizationGuid(prop, displayText);
                }
                break;
            }
            
            case "set_display_name":
            {
                var prop = ResolveProperty(properties, path);
                if (prop != null) SetDisplayName(prop, patch.GetProperty("value"), asset);
                break;
            }
            
            case "set_description":
            {
                var prop = ResolveProperty(properties, path);
                if (prop != null) SetDescriptionFallback(prop, patch.GetProperty("value").GetString()!);
                break;
            }
            
            case "set_vector2d":
            {
                var prop = ResolveProperty(properties, path);
                if (prop is StructPropertyData vecStruct)
                    SetVector2D(vecStruct, patch.GetProperty("x").GetSingle(),
                        patch.GetProperty("y").GetSingle(), asset, path.Split('.').Last());
                break;
            }
            
            case "set_vector":
            {
                var prop = ResolveProperty(properties, path);
                if (prop is StructPropertyData vecStruct)
                    SetVector(vecStruct, patch.GetProperty("x").GetSingle(),
                        patch.GetProperty("y").GetSingle(), patch.GetProperty("z").GetSingle(),
                        asset, path.Split('.').Last());
                break;
            }
            
            case "set_import_ref":
            case "set_or_create_import_ref":
            {
                var (container, prop) = ResolvePropertyWithContainer(properties, path);
                var addCdoImport = patch.TryGetProperty("add_cdo_import", out var cdoFlag) && cdoFlag.GetBoolean();
                var (_, importIdx) = AddImportChain(asset,
                    patch.GetProperty("class_package").GetString()!,
                    patch.GetProperty("class_name").GetString()!,
                    patch.GetProperty("package_path").GetString()!,
                    patch.GetProperty("asset_name").GetString()!,
                    addCdoImport);
                var pkgIdx = FPackageIndex.FromImport(importIdx - 1);
                
                if (prop is ObjectPropertyData objProp)
                {
                    objProp.Value = pkgIdx;
                }
                else if (op == "set_import_ref" && prop != null)
                {
                    // 0.7.19+ schema drift: refs like the DataTable ActorClass
                    // may deserialize as a non-Object property type, so the
                    // branch above silently no-oped and every cloned row kept
                    // the template row's ActorClass (Transformer bug). Replace
                    // the property with an ObjectPropertyData pointing at the
                    // new import — UE tag-serialization binds it to the row's
                    // FObjectProperty at load time.
                    var leafName = path.Split('.').Last();
                    var repl = new ObjectPropertyData(FName.FromString(asset, leafName)) { Value = pkgIdx };
                    repl.PropertyTypeName = MakeTypeName(asset, repl.PropertyType);
                    if (container != null)
                    {
                        int ridx = -1;
                        for (int i = 0; i < container.Count; i++)
                            if (ReferenceEquals(container[i], prop)) { ridx = i; break; }
                        if (ridx >= 0) container[ridx] = repl;
                        else container.Add(repl);
                    }
                    else
                    {
                        properties.Add(repl);
                    }
                    Console.WriteLine($"    set_import_ref: replaced {prop.GetType().Name} at '{path}' with ObjectPropertyData -> {patch.GetProperty("asset_name").GetString()}");
                }
                else if (op == "set_import_ref" && prop == null)
                {
                    var leafName = path.Split('.').Last();
                    var appended = new ObjectPropertyData(FName.FromString(asset, leafName)) { Value = pkgIdx };
                    appended.PropertyTypeName = MakeTypeName(asset, appended.PropertyType);
                    properties.Add(appended);
                    Console.WriteLine($"    set_import_ref: WARNING '{path}' not found on row — appended ObjectPropertyData -> {patch.GetProperty("asset_name").GetString()}");
                }
                else if (op == "set_or_create_import_ref" && container != null)
                {
                    var leafName = path.Split('.').Last();
                    var newProp = new ObjectPropertyData(FName.FromString(asset, leafName))
                    {
                        Value = pkgIdx
                    };
                    newProp.PropertyTypeName = MakeTypeName(asset, newProp.PropertyType);
                    container.Add(newProp);
                    Console.WriteLine($"    Created import ref: {path} -> {patch.GetProperty("asset_name").GetString()}");
                }
                else if (op == "set_or_create_import_ref")
                {
                    // Top-level property on CDO — add directly to properties list
                    var leafName = path.Split('.').Last();
                    var newProp = new ObjectPropertyData(FName.FromString(asset, leafName))
                    {
                        Value = pkgIdx
                    };
                    newProp.PropertyTypeName = MakeTypeName(asset, newProp.PropertyType);
                    properties.Add(newProp);
                    Console.WriteLine($"    Created top-level import ref: {path} -> {patch.GetProperty("asset_name").GetString()}");
                }
                break;
            }
            
            case "null_ref":
            {
                var prop = ResolveProperty(properties, path);
                if (prop is ObjectPropertyData objProp)
                    objProp.Value = FPackageIndex.FromRawIndex(0);
                else if (prop is SoftObjectPropertyData softProp)
                    softProp.Value = new FSoftObjectPath(
                        new FTopLevelAssetPath(new FName(asset, 0), new FName(asset, 0)), null);
                break;
            }
            
            case "set_soft_object":
            {
                var prop = ResolveProperty(properties, path);
                if (prop is SoftObjectPropertyData softProp)
                    softProp.Value = new FSoftObjectPath(
                        new FTopLevelAssetPath(
                            FName.FromString(asset, patch.GetProperty("package").GetString()!),
                            FName.FromString(asset, patch.GetProperty("asset").GetString()!)),
                        null);
                break;
            }
            
            case "clear_array":
            {
                var prop = ResolveProperty(properties, path);
                if (prop is ArrayPropertyData arr)
                    arr.Value = Array.Empty<PropertyData>();
                break;
            }
            
            case "append_import_to_array":
            {
                // Append a new import reference to an array of ObjectPropertyData
                // Used for adding child tables to CompositeDataTable's ParentTables
                var prop = ResolveProperty(properties, path);
                if (prop is ArrayPropertyData arr)
                {
                    var addCdoImport = patch.TryGetProperty("add_cdo_import", out var cdoFlag) && cdoFlag.GetBoolean();
                    var (_, importIdx) = AddImportChain(asset,
                        patch.GetProperty("class_package").GetString()!,
                        patch.GetProperty("class_name").GetString()!,
                        patch.GetProperty("package_path").GetString()!,
                        patch.GetProperty("asset_name").GetString()!,
                        addCdoImport);
                    
                    var newEntry = new ObjectPropertyData(FName.FromString(asset, arr.Value.Length.ToString()))
                    {
                        Value = FPackageIndex.FromImport(importIdx - 1)
                    };
                    newEntry.PropertyTypeName = MakeTypeName(asset, newEntry.PropertyType);

                    var list = new List<PropertyData>(arr.Value);
                    list.Add(newEntry);
                    arr.Value = list.ToArray();
                    Console.WriteLine($"    Appended to {path}: {patch.GetProperty("asset_name").GetString()} (array now has {arr.Value.Length} entries)");
                }
                break;
            }
            
            case "clear_map":
            {
                var prop = ResolveProperty(properties, path);
                if (prop is MapPropertyData mapProp)
                    mapProp.Value = new TMap<PropertyData, PropertyData>();
                break;
            }
            
            case "clear_tags":
            {
                var prop = ResolveProperty(properties, path);
                if (prop is StructPropertyData tagsStruct)
                {
                    foreach (var sp in tagsStruct.Value)
                    {
                        if (sp is GameplayTagContainerPropertyData tc)
                            tc.Value = Array.Empty<FName>();
                    }
                }
                break;
            }
            
            case "add_gameplay_tags":
            {
                var prop = ResolveProperty(properties, path);
                if (prop is StructPropertyData tagsStruct)
                {
                    foreach (var sp in tagsStruct.Value)
                    {
                        if (sp is GameplayTagContainerPropertyData tc)
                        {
                            var existing = tc.Value?.ToList() ?? new List<FName>();
                            foreach (var tag in patch.GetProperty("tags").EnumerateArray())
                            {
                                var tagName = tag.GetString()!;
                                var fname = FName.FromString(asset, tagName);
                                if (!existing.Any(e => e.Value?.Value == tagName))
                                {
                                    existing.Add(fname);
                                    Console.WriteLine($"    Added tag: {tagName}");
                                }
                            }
                            tc.Value = existing.ToArray();
                        }
                    }
                }
                break;
            }
            
            case "clear_tag_query":
            {
                var prop = ResolveProperty(properties, path);
                if (prop is StructPropertyData tagQuery)
                {
                    foreach (var sp in tagQuery.Value)
                    {
                        switch (sp.Name.Value.Value)
                        {
                            case "TokenStreamVersion": SetNumericProperty(sp, 0); break;
                            case "TagDictionary":
                                if (sp is ArrayPropertyData ta) ta.Value = Array.Empty<PropertyData>(); break;
                            case "QueryTokenStream":
                                if (sp is ArrayPropertyData qa) qa.Value = Array.Empty<PropertyData>(); break;
                            case "UserDescription":
                            case "AutoDescription":
                                if (sp is StrPropertyData strP) strP.Value = null; break;
                        }
                    }
                }
                break;
            }
            
            case "set_name":
            {
                var prop = ResolveProperty(properties, path);
                if (prop is NamePropertyData nameProp)
                    nameProp.Value = FName.FromString(asset, patch.GetProperty("value").GetString()!);
                break;
            }
            
            case "set_name_array":
            {
                var prop = ResolveProperty(properties, path);
                if (prop is ArrayPropertyData arr)
                {
                    var leafName = path.Split('.').Last();
                    var list = new List<PropertyData>();
                    foreach (var v in patch.GetProperty("values").EnumerateArray())
                    {
                        var np = new NamePropertyData(FName.FromString(asset, leafName));
                        np.PropertyTypeName = MakeTypeName(asset, np.PropertyType);
                        np.Value = FName.FromString(asset, v.GetString()!);
                        list.Add(np);
                    }
                    arr.Value = list.ToArray();
                }
                break;
            }
            
            case "set_name_int_map":
            {
                var prop = ResolveProperty(properties, path);
                if (prop is MapPropertyData mapProp)
                {
                    var leafName = path.Split('.').Last();
                    mapProp.Value = new TMap<PropertyData, PropertyData>();
                    if (patch.TryGetProperty("value", out var mapValue))
                    {
                        foreach (var entry in mapValue.EnumerateObject())
                        {
                            var keyProp = new NamePropertyData(new FName(asset, leafName, 0))
                            { Value = FName.FromString(asset, entry.Name) };
                            keyProp.PropertyTypeName = MakeTypeName(asset, keyProp.PropertyType);
                            var valProp = new IntPropertyData(new FName(asset, leafName, 0))
                            { Value = entry.Value.GetInt32() };
                            valProp.PropertyTypeName = MakeTypeName(asset, valProp.PropertyType);
                            mapProp.Value.Add(keyProp, valProp);
                        }
                    }
                }
                break;
            }
            
            case "add_map_entry":
            {
                var prop = ResolveProperty(properties, path);
                if (prop is MapPropertyData mapProp)
                {
                    var newKey = patch.GetProperty("key").GetString()!;
                    var newValue = patch.GetProperty("value").GetString()!;
                    
                    var newMap = new TMap<PropertyData, PropertyData>();
                    
                    foreach (var kvp in mapProp.Value)
                    {
                        var clonedKey = (PropertyData)kvp.Key.Clone();
                        var clonedVal = (PropertyData)kvp.Value.Clone();
                        newMap.Add(clonedKey, clonedVal);
                    }
                    
                    var firstEnumKey = mapProp.Value.Keys.OfType<EnumPropertyData>().FirstOrDefault();
                    PropertyData keyPropToAdd;
                    if (firstEnumKey != null)
                    {
                        keyPropToAdd = (EnumPropertyData)firstEnumKey.Clone();
                        ((EnumPropertyData)keyPropToAdd).Value = FName.FromString(asset, newKey);
                    }
                    else
                    {
                        var firstNameKey = mapProp.Value.Keys.OfType<NamePropertyData>().FirstOrDefault();
                        if (firstNameKey != null)
                        {
                            keyPropToAdd = (NamePropertyData)firstNameKey.Clone();
                            ((NamePropertyData)keyPropToAdd).Value = FName.FromString(asset, newKey);
                        }
                        else
                        {
                            Console.WriteLine($"    Warning: add_map_entry couldn't determine key type for '{path}'");
                            break;
                        }
                    }
                    
                    var firstNameVal = mapProp.Value.Values.OfType<NamePropertyData>().FirstOrDefault();
                    var firstStrVal = mapProp.Value.Values.OfType<StrPropertyData>().FirstOrDefault();
                    PropertyData valPropToAdd;
                    if (firstNameVal != null)
                    {
                        valPropToAdd = (NamePropertyData)firstNameVal.Clone();
                        ((NamePropertyData)valPropToAdd).Value = FName.FromString(asset, newValue);
                    }
                    else if (firstStrVal != null)
                    {
                        valPropToAdd = (StrPropertyData)firstStrVal.Clone();
                        ((StrPropertyData)valPropToAdd).Value = FString.FromString(newValue);
                    }
                    else
                    {
                        Console.WriteLine($"    Warning: add_map_entry couldn't determine value type for '{path}'");
                        break;
                    }
                    
                    newMap.Add(keyPropToAdd, valPropToAdd);
                    mapProp.Value = newMap;
                    Console.WriteLine($"    Added map entry: {newKey} = {newValue}");
                }
                break;
            }
            
            case "set_or_add_float":
            {
                var (container, prop) = ResolvePropertyWithContainer(properties, path);
                var val = patch.GetProperty("value").GetSingle();
                if (prop != null)
                {
                    SetNumericProperty(prop, val);
                }
                else if (container != null)
                {
                    var templateFloat = container.OfType<FloatPropertyData>().FirstOrDefault();
                    if (templateFloat != null)
                    {
                        var newProp = (FloatPropertyData)templateFloat.Clone();
                        newProp.Name = FName.FromString(asset, path.Split('.').Last());
                        newProp.Value = val;
                        container.Add(newProp);
                        Console.WriteLine($"    Added float: {path} = {val}");
                    }
                }
                break;
            }
            
            case "set_or_create_name":
            {
                var (container, prop) = ResolvePropertyWithContainer(properties, path);
                var val = patch.GetProperty("value").GetString()!;
                if (prop is NamePropertyData np)
                {
                    np.Value = FName.FromString(asset, val);
                }
                else if (prop is StrPropertyData sp)
                {
                    sp.Value = FString.FromString(val);
                }
                else if (container != null)
                {
                    var templateName = container.OfType<NamePropertyData>().FirstOrDefault();
                    if (templateName != null)
                    {
                        var newProp = (NamePropertyData)templateName.Clone();
                        newProp.Name = FName.FromString(asset, path.Split('.').Last());
                        newProp.Value = FName.FromString(asset, val);
                        container.Add(newProp);
                        Console.WriteLine($"    Created name: {path} = {val}");
                    }
                    else
                    {
                        var leafName = FName.FromString(asset, path.Split('.').Last());
                        var newProp = new NamePropertyData(leafName);
                        newProp.Value = FName.FromString(asset, val);
                        container.Add(newProp);
                        Console.WriteLine($"    Created name (no template): {path} = {val}");
                    }
                }
                else
                {
                    Console.WriteLine($"    Warning: Cannot set '{path}' — no property and no container found");
                }
                break;
            }
            
            case "set_or_create_int":
            {
                var (container, prop) = ResolvePropertyWithContainer(properties, path);
                var val = patch.GetProperty("value").GetInt32();
                if (prop is IntPropertyData ip)
                {
                    ip.Value = val;
                }
                else if (prop != null)
                {
                    SetNumericProperty(prop, val);
                }
                else if (container != null)
                {
                    var templateInt = container.OfType<IntPropertyData>().FirstOrDefault();
                    if (templateInt != null)
                    {
                        var newProp = (IntPropertyData)templateInt.Clone();
                        newProp.Name = FName.FromString(asset, path.Split('.').Last());
                        newProp.Value = val;
                        container.Add(newProp);
                        Console.WriteLine($"    Created int: {path} = {val}");
                    }
                    else
                    {
                        var leafName = FName.FromString(asset, path.Split('.').Last());
                        var newProp = new IntPropertyData(leafName) { Value = val };
                        container.Add(newProp);
                        Console.WriteLine($"    Created int (no template): {path} = {val}");
                    }
                }
                else
                {
                    Console.WriteLine($"    Warning: Cannot set '{path}' — no property and no container found");
                }
                break;
            }
            
            case "set_collision_profile":
            {
                var profileName = patch.GetProperty("profile_name").GetString()!;
                var channelResponses = patch.GetProperty("channels");
                
                var (container, existingProp) = ResolvePropertyWithContainer(properties, path);
                
                var bodyInstance = existingProp as StructPropertyData;
                if (bodyInstance == null && container != null)
                {
                    var leafName = path.Split('.').Last();
                    bodyInstance = new StructPropertyData(FName.FromString(asset, leafName));
                    bodyInstance.StructType = FName.DefineDummy(asset, "BodyInstance");
                    bodyInstance.Value = new List<PropertyData>();
                    container.Add(bodyInstance);
                    Console.WriteLine($"    Created BodyInstance struct at {path}");
                }
                
                if (bodyInstance != null)
                {
                    var bodyProps = new List<PropertyData>(bodyInstance.Value);
                    
                    var profileNameProp = bodyProps.OfType<NamePropertyData>().FirstOrDefault(p => p.Name.Value.Value == "CollisionProfileName");
                    if (profileNameProp == null)
                    {
                        profileNameProp = new NamePropertyData(FName.FromString(asset, "CollisionProfileName"));
                        bodyProps.Add(profileNameProp);
                    }
                    profileNameProp.Value = FName.FromString(asset, profileName);
                    
                    var responsesStruct = bodyProps.OfType<StructPropertyData>().FirstOrDefault(p => p.Name.Value.Value == "CollisionResponses");
                    if (responsesStruct == null)
                    {
                        responsesStruct = new StructPropertyData(FName.FromString(asset, "CollisionResponses"));
                        responsesStruct.StructType = FName.DefineDummy(asset, "CollisionResponse");
                        responsesStruct.Value = new List<PropertyData>();
                        bodyProps.Add(responsesStruct);
                    }
                    
                    var responsesProps = new List<PropertyData>(responsesStruct.Value);
                    
                    var responseToChannels = responsesProps.OfType<StructPropertyData>().FirstOrDefault(p => p.Name.Value.Value == "ResponseToChannels");
                    if (responseToChannels == null)
                    {
                        responseToChannels = new StructPropertyData(FName.FromString(asset, "ResponseToChannels"));
                        responseToChannels.StructType = FName.DefineDummy(asset, "CollisionResponseContainer");
                        responseToChannels.Value = new List<PropertyData>();
                        responsesProps.Add(responseToChannels);
                    }
                    
                    var channelProps = new List<PropertyData>(responseToChannels.Value);
                    foreach (var ch in channelResponses.EnumerateArray())
                    {
                        var channelName = ch.GetProperty("channel").GetString()!;
                        var responseName = ch.GetProperty("response").GetString()!;
                        
                        var existing = channelProps.OfType<EnumPropertyData>().FirstOrDefault(p => p.Name.Value.Value == channelName);
                        if (existing != null)
                        {
                            existing.Value = FName.FromString(asset, responseName);
                        }
                        else
                        {
                            var channelEnum = new EnumPropertyData(FName.FromString(asset, channelName));
                            channelEnum.Value = FName.FromString(asset, responseName);
                            channelEnum.EnumType = FName.DefineDummy(asset, "ECollisionResponse");
                            channelEnum.InnerType = FName.DefineDummy(asset, "ByteProperty");
                            channelProps.Add(channelEnum);
                        }
                    }
                    responseToChannels.Value = channelProps;
                    
                    responsesStruct.Value = responsesProps;
                    bodyInstance.Value = bodyProps;
                    
                    Console.WriteLine($"    Set collision profile: {profileName} with {channelProps.Count} channel responses");
                }
                else
                {
                    Console.WriteLine($"    Warning: Cannot set collision profile at '{path}' — BodyInstance not found and cannot be created");
                }
                break;
            }
            
            default:
                Console.WriteLine($"    Warning: Unknown op '{op}' for path '{path}'");
                break;
        }
    }
    
    /// <summary>Resolve a dot-separated property path to the leaf PropertyData.</summary>
    static PropertyData? ResolveProperty(IList<PropertyData> properties, string path)
    {
        var (_, prop) = ResolvePropertyWithContainer(properties, path);
        return prop;
    }
    
    /// <summary>Resolve a property path, returning both the containing list and the leaf property.</summary>
    static (IList<PropertyData>? container, PropertyData? prop) ResolvePropertyWithContainer(
        IList<PropertyData> properties, string path)
    {
        var parts = path.Split('.');
        IList<PropertyData> current = properties;
        
        for (int i = 0; i < parts.Length; i++)
        {
            PropertyData? found = null;
            var part = parts[i];
            var bracketIdx = part.IndexOf('[');
            
            if (bracketIdx >= 0 && part.EndsWith(']'))
            {
                var propName = part.Substring(0, bracketIdx);
                var indexStr = part.Substring(bracketIdx + 1, part.Length - bracketIdx - 2);
                if (!int.TryParse(indexStr, out var index))
                    return (null, null);
                
                foreach (var prop in current)
                {
                    if (prop.Name.Value.Value == propName && prop is ArrayPropertyData arr)
                    {
                        if (index < 0 || index >= arr.Value.Length) return (null, null);
                        found = arr.Value[index];
                        break;
                    }
                }
            }
            else
            {
                foreach (var prop in current)
                {
                    if (prop.Name.Value.Value == part)
                    { found = prop; break; }
                }
            }
            
            if (found == null)
                return i == parts.Length - 1 ? (current, null) : (null, null);
            
            if (i == parts.Length - 1)
                return (current, found);
            
            if (found is StructPropertyData structProp)
                current = structProp.Value;
            else
                return (null, null);
        }
        return (null, null);
    }
    
    // ========================================================================
    // Shared helpers
    // ========================================================================
    
    static void SetNumericProperty(PropertyData prop, float value)
    {
        switch (prop)
        {
            case FloatPropertyData fp: fp.Value = value; break;
            case IntPropertyData ip: ip.Value = (int)value; break;
            case Int64PropertyData i64p: i64p.Value = (long)value; break;
            case DoublePropertyData dp: dp.Value = value; break;
        }
    }
    
    static void SetVector2D(StructPropertyData vecStruct, float x, float y, UAsset asset, string propertyName)
    {
        foreach (var sp in vecStruct.Value)
        {
            if (sp is StructPropertyData innerStruct && sp.Name.Value.Value == propertyName)
            {
                foreach (var inner in innerStruct.Value)
                {
                    if (inner.Name.Value.Value == "X") SetNumericProperty(inner, x);
                    else if (inner.Name.Value.Value == "Y") SetNumericProperty(inner, y);
                }
                return;
            }
            else if (sp is Vector2DPropertyData vec2d)
            {
                vec2d.Value = new FVector2D(x, y);
                return;
            }
        }
        foreach (var sp in vecStruct.Value)
        {
            if (sp.Name.Value.Value == "X") SetNumericProperty(sp, x);
            else if (sp.Name.Value.Value == "Y") SetNumericProperty(sp, y);
        }
    }
    
    static void SetVector(StructPropertyData vecStruct, float x, float y, float z, UAsset asset, string propertyName)
    {
        foreach (var sp in vecStruct.Value)
        {
            if (sp is StructPropertyData innerStruct && sp.Name.Value.Value == propertyName)
            {
                foreach (var inner in innerStruct.Value)
                {
                    if (inner.Name.Value.Value == "X") SetNumericProperty(inner, x);
                    else if (inner.Name.Value.Value == "Y") SetNumericProperty(inner, y);
                    else if (inner.Name.Value.Value == "Z") SetNumericProperty(inner, z);
                }
                return;
            }
            else if (sp is VectorPropertyData vec)
            {
                vec.Value = new FVector(x, y, z);
                return;
            }
        }
        foreach (var sp in vecStruct.Value)
        {
            if (sp.Name.Value.Value == "X") SetNumericProperty(sp, x);
            else if (sp.Name.Value.Value == "Y") SetNumericProperty(sp, y);
            else if (sp.Name.Value.Value == "Z") SetNumericProperty(sp, z);
        }
    }
    
    static DataTableExport? FindDataTable(UAsset asset)
    {
        foreach (var export in asset.Exports)
        {
            if (export is DataTableExport dt) return dt;
        }
        
        // Try to convert RawExport DataTables (some cooked DataTables fail initial parse)
        foreach (var export in asset.Exports)
        {
            if (export is RawExport rawExp && export.GetExportClassType()?.Value?.Value?.EndsWith("DataTable") == true)
            {
                try
                {
                    var converted = rawExp.ConvertToChildExport<DataTableExport>();
                    var reader = new AssetBinaryReader(new MemoryStream(rawExp.Data ?? []))
                    {
                        Asset = asset
                    };
                    converted.Read(reader, rawExp.Data?.Length ?? 0);
                    var idx = asset.Exports.IndexOf(rawExp);
                    asset.Exports[idx] = converted;
                    Console.WriteLine($"  Converted RawExport DataTable ({converted.Table.Data.Count} rows)");
                    return converted;
                }
                catch (Exception ex)
                {
                    Console.WriteLine($"  Warning: RawExport DataTable conversion failed: {ex.Message}");
                }
            }
        }
        
        Console.WriteLine("Error: No DataTable found in template");
        return null;
    }

    static void PatchMappingsForVersion()
    {
        if (Mappings == null) return;

        string[][] schemaPatches = [
            ["MTVehicleColor", "9"],
            ["MTVehicleColorSlot", "5"],
        ];



        foreach (var patch in schemaPatches)
        {
            var schemaName = patch[0];
            var minPropCount = ushort.Parse(patch[1]);

            if (!Mappings.Schemas.TryGetValue(schemaName, out var schema)) continue;
            if (schema.PropCount >= minPropCount) continue;

            var newProps = new ConcurrentDictionary<int, UsmapProperty>(schema.Properties);
            for (int i = schema.PropCount; i < minPropCount; i++)
            {
                // Use BoolProperty for MTVehicleColorSlot index 5 (likely bUseColorAlpha-like flag)
                var propType = (schemaName == "MTVehicleColorSlot" && i == 5) 
                    ? EPropertyType.BoolProperty 
                    : EPropertyType.ByteProperty;
                newProps[i] = new UsmapProperty(
                    $"Unknown_{i}",
                    (ushort)i,
                    0,
                    1,
                    new UsmapPropertyData(propType)
                );
            }

            var newSchema = new UsmapSchema(
                schema.Name,
                schema.SuperType,
                minPropCount,
                newProps,
                Mappings.AreFNamesCaseInsensitive,
                schema.SuperTypeModulePath
            );

            foreach (var key in Mappings.Schemas.Keys.Where(k => k == schemaName || k.EndsWith("." + schemaName)).ToList())
            {
                Mappings.Schemas[key] = newSchema;
            }

            Console.WriteLine($"  Patched schema {schemaName}: PropCount {schema.PropCount} -> {minPropCount}");
        }
    }
    
    static void SetLocalizationGuid(PropertyData prop, string? displayText = null)
    {
        if (prop is TextPropertyData nameTxt)
        {
            var guid = Guid.NewGuid().ToString("N").ToUpper();
            nameTxt.Value = FString.FromString(guid.Substring(0, 32));
            nameTxt.HistoryType = TextHistoryType.Base;
            if (displayText != null)
            {
                nameTxt.CultureInvariantString = FString.FromString(displayText);
            }
        }
    }
    
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
                        textProp.Namespace = FString.FromString("");
                        textProp.Value = FString.FromString(Guid.NewGuid().ToString("N").ToUpper().Substring(0, 32));
                        textProp.CultureInvariantString = FString.FromString(textVal);
                        textProp.HistoryType = TextHistoryType.Base;
                        textList.Add(textProp);
                    }
                    textsArr.Value = textList.ToArray();
                }
            }
        }
    }
    
    static void SetDescriptionFallback(PropertyData prop, string text)
    {
        if (prop is TextPropertyData descTxt)
        {
            descTxt.Namespace = FString.FromString("");
            descTxt.Value = FString.FromString(Guid.NewGuid().ToString("N").ToUpper().Substring(0, 32));
            descTxt.CultureInvariantString = FString.FromString(text);
            descTxt.HistoryType = TextHistoryType.Base;
        }
    }
    
    static (int pkgIdx, int assetIdx) AddImportChain(
        UAsset asset, string classPackage, string className,
        string packagePath, string assetName, bool addCdoImport = false)
    {
        var pkgImport = new Import(
            "/Script/CoreUObject", "Package",
            FPackageIndex.FromRawIndex(0), packagePath, false, asset);
        asset.Imports.Add(pkgImport);
        int pkgIdx = asset.Imports.Count;
        
        var assetImport = new Import(
            classPackage, className,
            FPackageIndex.FromImport(pkgIdx - 1), assetName, false, asset);
        asset.Imports.Add(assetImport);
        int assetIdx = asset.Imports.Count;
        
        Console.WriteLine($"  Added imports: Package [{pkgIdx}] = {packagePath}");
        Console.WriteLine($"  Added imports: Asset [{assetIdx}] = {assetName}");
        
        if (addCdoImport)
        {
            // Add Default__*_C CDO import — this forces the engine to load
            // the blueprint package for new (non-overriding) assets
            var cdoName = $"Default__{assetName}";
            var cdoImport = new Import(
                packagePath, assetName,
                FPackageIndex.FromImport(pkgIdx - 1), cdoName, false, asset);
            asset.Imports.Add(cdoImport);
            int cdoIdx = asset.Imports.Count;
            Console.WriteLine($"  Added imports: CDO [{cdoIdx}] = {cdoName}");
        }
        
        return (pkgIdx, assetIdx);
    }
    
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
    // Read-only modes (unchanged)
    // ========================================================================
    
    static void ProcessBatch()
    {
        var outDir = Path.Combine(RootDir!, "out");
        var manifestPath = Path.Combine(outDir, "manifest.json");
        if (!File.Exists(manifestPath))
        {
            Console.WriteLine($"Error: No manifest.json in {outDir}");
            return;
        }
        Console.WriteLine($"\nBatch processing assets in {outDir}");
        var manifestJson = File.ReadAllText(manifestPath);
        using var doc = JsonDocument.Parse(manifestJson);
        var extracted = doc.RootElement.GetProperty("extracted");
        int success = 0, failed = 0;
        foreach (var a in extracted.EnumerateArray())
        {
            var name = a.GetProperty("name").GetString()!;
            var uassetFile = a.GetProperty("uasset").GetString()!;
            var uassetPath = Path.Combine(outDir, uassetFile);
            Console.WriteLine($"\n  Processing: {name}");
            try { ProcessSingleFile(uassetPath, outDir); success++; }
            catch (Exception ex) { Console.WriteLine($"    FAILED: {ex.Message}"); failed++; }
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
            return;
        }
        Console.WriteLine($"\nBatch processing .umap files in {mapsDir}");
        var manifestJson = File.ReadAllText(manifestPath);
        using var doc = JsonDocument.Parse(manifestJson);
        var extracted = doc.RootElement.GetProperty("extracted");
        int success = 0, failed = 0;
        foreach (var a in extracted.EnumerateArray())
        {
            var name = a.GetProperty("name").GetString()!;
            var uassetFile = a.GetProperty("uasset").GetString()!;
            var filePath = Path.Combine(mapsDir, uassetFile);
            Console.WriteLine($"\n  Processing map: {name}");
            try { ProcessSingleFile(filePath, mapsDir); success++; }
            catch (Exception ex) { Console.WriteLine($"    FAILED: {ex.Message}"); failed++; }
        }
        Console.WriteLine($"\n=== Batch maps complete: {success} succeeded, {failed} failed ===");
    }
    
    static void ProcessSingleFile(string uassetPath, string outputDir)
    {
        if (!File.Exists(uassetPath))
            throw new FileNotFoundException($"File not found: {uassetPath}");
        
        var baseName = Path.GetFileNameWithoutExtension(uassetPath);
        var outputPath = Path.Combine(outputDir, $"{baseName}_parsed.json");
        
        Console.WriteLine($"    Loading: {Path.GetFileName(uassetPath)}");
        var asset = new UAsset(uassetPath, EngineVersion.VER_UE5_5, Mappings);
        Console.WriteLine($"    Exports: {asset.Exports.Count}, Imports: {asset.Imports.Count}");
        
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
                        rowData[prop.Name.Value.Value] = ExtractPropertyValue(prop, asset);
                    rows.Add(rowData);
                }
                dataTable = new { Type = "DataTable", RowCount = rows.Count, Rows = rows };
                Console.WriteLine($"    DataTable: {rows.Count} rows");
            }
            else if (export is NormalExport normalExport)
            {
                var properties = new Dictionary<string, object?>();
                foreach (var prop in normalExport.Data)
                    properties[prop.Name.Value.Value] = ExtractPropertyValue(prop, asset);
                exports.Add(new {
                    ExportName = export.ObjectName?.Value?.Value,
                    Class = export.GetExportClassType()?.Value?.Value,
                    Properties = properties
                });
                Console.WriteLine($"    NormalExport: {properties.Count} properties");
            }
        }
        
        object result = dataTable ?? (object)new { Type = "Blueprint", ExportCount = exports.Count, Exports = exports };
        var output = new { SourceAsset = Path.GetFileName(uassetPath), ParsedAt = DateTime.UtcNow.ToString("o"), Data = result };
        var options = new JsonSerializerOptions { WriteIndented = true };
        File.WriteAllText(outputPath, JsonSerializer.Serialize(output, options));
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
        var pkg = softProp.Value.AssetPath.PackageName?.Value?.Value;
        var assetName = softProp.Value.AssetPath.AssetName?.Value?.Value;
        var subPath = softProp.Value.SubPathString?.Value;
        return new { package = pkg ?? "", asset = assetName ?? "", subpath = subPath ?? "" };
    }
    
    static object? ResolveObjectReference(ObjectPropertyData objProp, UAsset asset)
    {
        if (objProp.Value == null || objProp.Value.Index == 0) return null;
        var index = objProp.Value.Index;
        if (index < 0)
        {
            var importIdx = -index - 1;
            if (importIdx < asset.Imports.Count)
            {
                var import = asset.Imports[importIdx];
                var objectName = import.ObjectName?.Value?.Value;
                if (!string.IsNullOrEmpty(objectName))
                {
                    return new { Type = "Import", Path = BuildImportPath(asset, importIdx),
                        ObjectName = objectName, ClassName = import.ClassName?.Value?.Value };
                }
            }
        }
        else
        {
            var exportIdx = index - 1;
            if (exportIdx < asset.Exports.Count)
            {
                var export = asset.Exports[exportIdx];
                return new { Type = "Export", Index = exportIdx,
                    ObjectName = export.ObjectName?.Value?.Value,
                    ClassName = export.GetExportClassType()?.Value?.Value };
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
            if (!string.IsNullOrEmpty(name)) parts.Insert(0, name);
            var outerIdx = import.OuterIndex.Index;
            if (outerIdx < 0) current = -outerIdx - 1;
            else break;
        }
        return string.Join("/", parts);
    }
    
    static object? ExtractArrayValue(ArrayPropertyData arrProp, UAsset asset)
    {
        var items = new List<object?>();
        foreach (var item in arrProp.Value) items.Add(ExtractPropertyValue(item, asset));
        return items;
    }
    
    static object? ExtractMapValue(MapPropertyData mapProp, UAsset asset)
    {
        var entries = new List<object>();
        foreach (var kvp in mapProp.Value)
            entries.Add(new { Key = ExtractPropertyValue(kvp.Key, asset), Value = ExtractPropertyValue(kvp.Value, asset) });
        return new { _Type = "Map", KeyType = mapProp.KeyType?.Value?.Value, ValueType = mapProp.ValueType?.Value?.Value, Entries = entries };
    }
    
    static object? ExtractStructValue(StructPropertyData structProp, UAsset asset)
    {
        var result = new Dictionary<string, object?>();
        result["_StructType"] = structProp.StructType?.Value?.Value;
        foreach (var prop in structProp.Value)
            result[prop.Name.Value.Value] = ExtractPropertyValue(prop, asset);
        return result;
    }
    
    static object? ExtractGameplayTags(GameplayTagContainerPropertyData tagProp)
    {
        var tags = new List<string>();
        foreach (var tag in tagProp.Value)
            if (tag?.Value?.Value != null) tags.Add(tag.Value.Value);
        return tags;
    }

    // DEBUG: Print MTVehicleColorSlot schema info
    static void DebugPrintSchema(string schemaName)
    {
        if (Mappings == null) return;
        if (Mappings.Schemas.TryGetValue(schemaName, out var schema))
        {
            Console.WriteLine($"DEBUG Schema {schemaName}: PropCount={schema.PropCount}, Properties.Count={schema.Properties.Count}");
        foreach (var kvp in schema.Properties)
        {
            Console.WriteLine($"  [{kvp.Key}] {kvp.Value.Name} (SchemaIndex={kvp.Value.SchemaIndex}, Type={kvp.Value.PropertyData?.Type})");
        }
        }
        else
        {
            Console.WriteLine($"DEBUG Schema {schemaName}: NOT FOUND");
        }
    }
}
