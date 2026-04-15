using System;
using System.Collections.Generic;
using UAssetAPI;
using UAssetAPI.ExportTypes;
using UAssetAPI.PropertyTypes.Objects;
using UAssetAPI.PropertyTypes.Structs;
using UAssetAPI.UnrealTypes;

class Program
{
    static void Main(string[] args)
    {
        if (args.Length < 2)
        {
            Console.WriteLine("Usage: FontModifier <input.uasset> <output_dir>");
            Console.WriteLine("  Patches NanumSquareRound_Font to include Thai Unicode range");
            return;
        }

        var inputPath = args[0];
        var outputDir = args[1];
        
        Console.WriteLine($"Loading: {inputPath}");
        var asset = new UAsset(inputPath, EngineVersion.VER_UE5_5);
        
        Console.WriteLine($"Package: {asset.FolderName}");
        Console.WriteLine($"Exports: {asset.Exports.Count}");

        // Find the Font export
        NormalExport fontExport = null;
        foreach (var exp in asset.Exports)
        {
            Console.WriteLine($"Export: {exp.ObjectName} ({exp.GetType().Name}) class={exp.GetExportClassType()}");
            if (exp is NormalExport ne)
            {
                fontExport = ne; // Use the first (and only) export
            }
        }

        if (fontExport == null)
        {
            Console.WriteLine("ERROR: No Font export found");
            return;
        }

        Console.WriteLine($"Font export: {fontExport.ObjectName}");

        // Find the CompositeFont property
        StructPropertyData compositeFont = null;
        foreach (var prop in fontExport.Data)
        {
            if (prop.Name.Value.Value == "CompositeFont" && prop is StructPropertyData spd)
            {
                compositeFont = spd;
                break;
            }
        }

        if (compositeFont == null)
        {
            Console.WriteLine("ERROR: No CompositeFont property found");
            return;
        }

        // Navigate the structure
        // CompositeFont -> DefaultTypeface, FallbackTypeface, SubTypefaces
        var defaultTypeface = FindStructProperty(compositeFont.Value, "DefaultTypeface");
        var fallbackTypeface = FindStructProperty(compositeFont.Value, "FallbackTypeface");
        var subTypefaces = FindArrayProperty(compositeFont.Value, "SubTypefaces");

        Console.WriteLine($"DefaultTypeface: {defaultTypeface != null}");
        Console.WriteLine($"FallbackTypeface: {fallbackTypeface != null}");
        Console.WriteLine($"SubTypefaces: {subTypefaces?.Value?.Length ?? 0}");

        // Dump current SubTypefaces
        if (subTypefaces?.Value != null)
        {
            for (int i = 0; i < subTypefaces.Value.Length; i++)
            {
                var sub = subTypefaces.Value[i] as StructPropertyData;
                if (sub == null) continue;
                
                var ranges = FindArrayProperty(sub.Value, "CharacterRanges");
                var typeface = FindStructProperty(sub.Value, "Typeface");
                
                Console.WriteLine($"\nSubTypeface[{i}]:");
                if (ranges?.Value != null)
                {
                    for (int j = 0; j < ranges.Value.Length; j++)
                    {
                        var range = ranges.Value[j] as StructPropertyData;
                        if (range == null) continue;
                        var lower = FindStructProperty(range.Value, "LowerBound");
                        var upper = FindStructProperty(range.Value, "UpperBound");
                        var lowerVal = FindIntProperty(lower?.Value, "Value");
                        var upperVal = FindIntProperty(upper?.Value, "Value");
                        Console.WriteLine($"  Range[{j}]: U+{lowerVal?.Value:X4}-U+{upperVal?.Value:X4}");
                    }
                }
                
                // Show which FontFace this maps to
                if (typeface?.Value != null)
                {
                    var fonts = FindArrayProperty(typeface.Value, "Fonts");
                    if (fonts?.Value != null && fonts.Value.Length > 0)
                    {
                        var fontEntry = fonts.Value[0] as StructPropertyData;
                        var fontData = FindStructProperty(fontEntry?.Value, "Font");
                        var fd = FindFontData(fontData?.Value);
                        if (fd != null)
                            Console.WriteLine($"  FontFace: Index={fd.LocalFontFaceAsset}");
                    }
                }
            }
        }

        // Now add Thai range to SubTypefaces
        // We'll add a new SubTypeface entry with Thai range that maps to DroidSansFallback
        Console.WriteLine("\n--- Adding Thai Unicode range ---");
        
        // Find DroidSansFallback import index
        int droidIdx = 0;
        for (int i = 0; i < asset.Imports.Count; i++)
        {
            if (asset.Imports[i].ObjectName.Value.Value == "DroidSansFallback")
            {
                droidIdx = -(i + 1); // Import indices are negative
                break;
            }
        }
        Console.WriteLine($"DroidSansFallback import index: {droidIdx}");

        // For now, let's just dump the raw bytes of the uexp to understand the format
        Console.WriteLine("\n--- Raw uexp structure analysis ---");
        Console.WriteLine($"SubTypefaces array count: {subTypefaces?.Value?.Length ?? 0}");
        
        // The simplest fix: modify the SubTypeface CharacterRanges to include Thai
        // Thai range: U+0E00 (3584) to U+0E7F (3711)
        
        if (subTypefaces?.Value != null && subTypefaces.Value.Length > 0)
        {
            var sub0 = subTypefaces.Value[0] as StructPropertyData;
            if (sub0 != null)
            {
                var charRanges = FindArrayProperty(sub0.Value, "CharacterRanges");
                if (charRanges?.Value != null)
                {
                    Console.WriteLine($"Current CharacterRanges: {charRanges.Value.Length}");
                    
                    // Add a new range for Thai
                    var thaiRange = CreateRangeEntry(asset, 0x0E00, 0x0E7F, "Inclusive");
                    var newRanges = new PropertyData[charRanges.Value.Length + 1];
                    Array.Copy(charRanges.Value, newRanges, charRanges.Value.Length);
                    newRanges[charRanges.Value.Length] = thaiRange;
                    charRanges.Value = newRanges;
                    
                    Console.WriteLine($"Updated CharacterRanges: {charRanges.Value.Length}");
                    for (int j = 0; j < charRanges.Value.Length; j++)
                    {
                        var range = charRanges.Value[j] as StructPropertyData;
                        if (range == null) continue;
                        var lower = FindStructProperty(range.Value, "LowerBound");
                        var upper = FindStructProperty(range.Value, "UpperBound");
                        var lowerVal = FindIntProperty(lower?.Value, "Value");
                        var upperVal = FindIntProperty(upper?.Value, "Value");
                        Console.WriteLine($"  Range[{j}]: U+{lowerVal?.Value:X4}-U+{upperVal?.Value:X4}");
                    }
                }
            }
        }

        // Save
        var outputPath = System.IO.Path.Combine(outputDir, "NanumSquareRound_Font.uasset");
        Console.WriteLine($"\nSaving to: {outputPath}");
        asset.Write(outputPath);
        Console.WriteLine("Done!");
    }

    static StructPropertyData FindStructProperty(List<PropertyData> props, string name)
    {
        foreach (var p in props)
            if (p.Name.Value.Value == name && p is StructPropertyData spd)
                return spd;
        return null;
    }

    static ArrayPropertyData FindArrayProperty(List<PropertyData> props, string name)
    {
        foreach (var p in props)
            if (p.Name.Value.Value == name && p is ArrayPropertyData apd)
                return apd;
        return null;
    }

    static IntPropertyData FindIntProperty(List<PropertyData> props, string name)
    {
        foreach (var p in props)
            if (p.Name.Value.Value == name && p is IntPropertyData ipd)
                return ipd;
        return null;
    }

    static FFontData FindFontData(List<PropertyData> props)
    {
        foreach (var p in props)
            if (p is FontDataPropertyData fdp)
                return fdp.Value;
        return null;
    }

    static StructPropertyData CreateRangeEntry(UAsset asset, int lower, int upper, string enumType)
    {
        // Create a CharacterRange struct
        var range = new StructPropertyData(FName.FromString(asset, ""), null);
        range.StructType = FName.FromString(asset, "Int32Interval");
        
        var lowerBound = new StructPropertyData(FName.FromString(asset, "LowerBound"), null);
        lowerBound.StructType = FName.FromString(asset, "RangeBound");
        var lowerType = new EnumPropertyData();
        lowerType.Name = FName.FromString(asset, "Type");
        lowerType.Value = FName.FromString(asset, enumType);
        var lowerValue = new IntPropertyData(FName.FromString(asset, "Value"));
        lowerValue.Value = lower;
        lowerBound.Value = new List<PropertyData> { lowerType, lowerValue };

        var upperBound = new StructPropertyData(FName.FromString(asset, "UpperBound"), null);
        upperBound.StructType = FName.FromString(asset, "RangeBound");
        var upperType = new EnumPropertyData();
        upperType.Name = FName.FromString(asset, "Type");
        upperType.Value = FName.FromString(asset, enumType);
        var upperValue = new IntPropertyData(FName.FromString(asset, "Value"));
        upperValue.Value = upper;
        upperBound.Value = new List<PropertyData> { upperType, upperValue };

        range.Value = new List<PropertyData> { lowerBound, upperBound };
        return range;
    }
}
