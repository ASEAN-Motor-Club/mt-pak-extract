using System.Text.Json;
using CUE4Parse.FileProvider;
using CUE4Parse.MappingsProvider;
using CUE4Parse.UE4.Assets;
using CUE4Parse.UE4.Assets.Exports;
using CUE4Parse.UE4.Assets.Exports.Actor;
using CUE4Parse.UE4.Objects.Core.Misc;
using CUE4Parse.UE4.Objects.UObject;
using CUE4Parse.UE4.Versions;
using CUE4Parse.Encryption.Aes;
using CUE4Parse.Compression;

class Program
{
    static async Task Main(string[] args)
    {
        Console.WriteLine("=== MotorTown Level Extractor (CUE4Parse) ===");
        Console.WriteLine();

        // Determine root directory (two levels up from csharp/LevelExtractor)
        var rootDir = Path.GetFullPath(Path.Combine("..", ".."));

        // Parse args
        string? pakDirArg = null;
        string? outputArg = null;
        for (int i = 0; i < args.Length; i++)
        {
            if (args[i] == "--pak-dir" && i + 1 < args.Length)
                pakDirArg = args[++i];
            else if (args[i] == "--output" && i + 1 < args.Length)
                outputArg = args[++i];
        }

        var pakDir = pakDirArg ?? rootDir;
        var outputPath = outputArg ?? Path.Combine(rootDir, "out", "level_actors.json");

        // Load AES key from .env
        var envPath = Path.Combine(rootDir, ".env");
        if (!File.Exists(envPath))
        {
            Console.WriteLine($"Error: .env file not found at {envPath}");
            return;
        }
        var keyHex = File.ReadAllLines(envPath)
            .Where(l => l.StartsWith("KEY="))
            .Select(l => l.Substring(4).Trim())
            .FirstOrDefault();
        if (string.IsNullOrEmpty(keyHex))
        {
            Console.WriteLine("Error: KEY not found in .env");
            return;
        }

        // Check for mappings
        var usmapPath = Path.Combine(rootDir, "Mappings.usmap");
        if (!File.Exists(usmapPath))
        {
            Console.WriteLine($"Error: Mappings.usmap not found at {usmapPath}");
            return;
        }

        // Initialize Oodle decompression (required for PAK reading)
        var oodlePaths = new[]
        {
            Path.Combine(rootDir, "target", "release"),
            Path.Combine(rootDir, "target", "debug"),
        };
        string? oodlePath = null;
        foreach (var dir in oodlePaths)
        {
            if (!Directory.Exists(dir)) continue;
            var dylib = Directory.GetFiles(dir, "liboo2core*.*").FirstOrDefault();
            if (dylib != null) { oodlePath = dylib; break; }
        }
        if (oodlePath == null)
        {
            Console.WriteLine("Error: Oodle native library not found in target/release/ or target/debug/");
            Console.WriteLine("Run 'cargo build --release' first to build the Oodle library.");
            return;
        }
        Console.WriteLine($"Oodle library: {oodlePath}");
        OodleHelper.Initialize(oodlePath);

        // Initialize CUE4Parse file provider
        Console.WriteLine($"PAK directory: {pakDir}");
        Console.WriteLine("Initializing file provider...");

        var provider = new DefaultFileProvider(
            pakDir,
            SearchOption.TopDirectoryOnly,
            new VersionContainer(EGame.GAME_UE5_5)
        );
        provider.MappingsContainer = new FileUsmapTypeMappingsProvider(usmapPath);
        provider.Initialize();

        // Submit AES key
        Console.WriteLine("Submitting AES decryption key...");
        var aesKey = new FAesKey(keyHex);
        await provider.SubmitKeyAsync(new FGuid(), aesKey);
        Console.WriteLine($"Mounted files: {provider.Files.Count}");

        // Find Jeju .umap files
        Console.WriteLine();
        var jejuMaps = provider.Files
            .Where(kv => kv.Key.EndsWith(".umap"))
            .Where(kv => kv.Key.Contains("Jeju", StringComparison.OrdinalIgnoreCase))
            .ToList();
        Console.WriteLine($"Jeju .umap files: {jejuMaps.Count}");

        // Load and process all maps
        Console.WriteLine();
        var allActors = new List<Dictionary<string, object?>>();
        int loadedMaps = 0, failedMaps = 0, errorsPrinted = 0;

        foreach (var mapFile in jejuMaps)
        {
            try
            {
                var package = provider.LoadPackage(mapFile.Value);
                foreach (var obj in package.GetExports())
                {
                    // Only process top-level actors (Outer == PersistentLevel)
                    if (obj is AActor actor && obj.Outer?.Name == "PersistentLevel")
                    {
                        allActors.Add(new Dictionary<string, object?>
                        {
                            ["name"] = obj.Name,
                            ["blueprint_class"] = obj.ExportType,
                            ["map"] = Path.GetFileNameWithoutExtension(mapFile.Key),
                        });
                    }
                }
                loadedMaps++;
            }
            catch (Exception ex)
            {
                if (errorsPrinted++ < 3)
                    Console.WriteLine($"  Failed: {ex.GetType().Name}: {ex.Message}");
                failedMaps++;
            }
        }

        Console.WriteLine($"Loaded {loadedMaps} maps, {failedMaps} failed");
        Console.WriteLine($"Total placed actors: {allActors.Count}");

        // Summary by class
        Console.WriteLine("\n=== Actor classes (top 40) ===");
        var byClass = allActors
            .GroupBy(a => a["blueprint_class"]?.ToString() ?? "?")
            .OrderByDescending(g => g.Count())
            .ToList();
        foreach (var g in byClass.Take(40))
        {
            Console.WriteLine($"  {g.Key}: {g.Count()}");
        }
        Console.WriteLine($"  ({byClass.Count} unique classes total)");

        // Save output
        Directory.CreateDirectory(Path.GetDirectoryName(outputPath)!);
        var options = new JsonSerializerOptions { WriteIndented = true };
        var json = JsonSerializer.Serialize(new
        {
            extracted_at = DateTime.UtcNow.ToString("o"),
            maps_loaded = loadedMaps,
            total_actors = allActors.Count,
            unique_classes = byClass.Count,
            class_summary = byClass.Select(g => new { blueprint_class = g.Key, count = g.Count() }),
            actors = allActors,
        }, options);
        File.WriteAllText(outputPath, json);
        Console.WriteLine($"\nSaved to: {outputPath}");
    }
}
