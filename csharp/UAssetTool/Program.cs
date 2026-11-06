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

        // Audit is a whole-directory read-only pass; it must be dispatched before the mode flags
        // below, because unknown args fall through to the default batch parse.
        int retargetIdx = Array.IndexOf(args, "--retarget-materials");
        if (retargetIdx >= 0)
        {
            if (retargetIdx + 3 >= args.Length) { Console.WriteLine("usage: --retarget-materials <inDir> <config.json> <outDir>"); return; }
            RootDir = Path.GetFullPath(Path.Combine("..", ".."));
            Mappings = new Usmap(Path.Combine(RootDir, "Mappings.usmap"));
            RetargetMaterials(args[retargetIdx + 1], args[retargetIdx + 2], args[retargetIdx + 3]);
            return;
        }

        int auditIdx = Array.IndexOf(args, "--audit-materials");
        {
            if (auditIdx >= 0)
            {
                if (auditIdx + 2 >= args.Length) { Console.WriteLine("usage: --audit-materials <dir> <out.tsv>"); return; }
                RootDir = Path.GetFullPath(Path.Combine("..", ".."));
                Mappings = new Usmap(Path.Combine(RootDir, "Mappings.usmap"));
                AuditMaterials(args[auditIdx + 1], args[auditIdx + 2]);
                return;
            }
        }
        
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
        bool makeCompositeMode = args.Contains("--make-composite");
        bool propProbeMode = args.Contains("--propprobe");
        bool alignImportsMode = args.Contains("--align-imports");
        bool dumpMode = args.Contains("--dump");
        bool ptProbe = args.Contains("--ptprobe");
        bool retargetMode = args.Contains("--retarget-mis");
        bool renameTexMode = args.Contains("--rename-texture-param");
        bool setMiParentMode = args.Contains("--set-mi-parent");
        bool setBlendMode = args.Contains("--set-blend");
        bool setTexParamMode = args.Contains("--set-texparam");
        bool clearOverridesMode = args.Contains("--clear-overrides");
        bool transMiMode = args.Contains("--trans-mis");
        int ptIdx = Array.IndexOf(args, "--ptprobe");
        
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
        
        if (renameTexMode)
        {
            int ri = Array.IndexOf(args, "--rename-texture-param");
            if (ri + 4 >= args.Length) { Console.WriteLine("usage: --rename-texture-param <inDir> <outDir> <from> <to>"); return; }
            RenameTextureParam(args[ri + 1], args[ri + 2], args[ri + 3], args[ri + 4]);
            return;
        }

        if (transMiMode)
        {
            int ti = Array.IndexOf(args, "--trans-mis");
            if (ti + 4 >= args.Length) { Console.WriteLine("usage: --trans-mis <inDir> <outDir> <listFile> <masterPkg> <masterName>"); return; }
            TransMIs(args[ti + 1], args[ti + 2], args[ti + 3], args[ti + 4], args[ti + 5]);
            return;
        }

        if (setTexParamMode)
        {
            int ti = Array.IndexOf(args, "--set-texparam");
            if (ti + 6 >= args.Length) { Console.WriteLine("usage: --set-texparam <inDir> <outDir> <listFile|-> <param> <texPkg> <texName>"); return; }
            SetTexParam(args[ti + 1], args[ti + 2], args[ti + 3], args[ti + 4], args[ti + 5], args[ti + 6]);
            return;
        }

        if (setBlendMode)
        {
            int bi = Array.IndexOf(args, "--set-blend");
            if (bi + 4 >= args.Length) { Console.WriteLine("usage: --set-blend <inDir> <outDir> <listFile|-> <masked|translucent>"); return; }
            var extra = args.Skip(bi + 5).ToArray();
            SetBlend(args[bi + 1], args[bi + 2], args[bi + 3], args[bi + 4], extra);
            return;
        }

        if (args.Contains("--set-clip"))
        {
            int ci2 = Array.IndexOf(args, "--set-clip");
            if (ci2 + 3 >= args.Length) { Console.WriteLine("usage: --set-clip <inDir> <outDir> <listFile>"); return; }
            SetClip(args[ci2 + 1], args[ci2 + 2], args[ci2 + 3]);
            return;
        }

        if (args.Contains("--apply-plan"))
        {
            int ai = Array.IndexOf(args, "--apply-plan");
            if (ai + 3 >= args.Length) { Console.WriteLine("usage: --apply-plan <inDir> <outDir> <plan.json> [masters.txt]"); return; }
            var mastersArg = ai + 4 < args.Length && !args[ai + 4].StartsWith("--") ? args[ai + 4] : null;
            ApplyPlan(args[ai + 1], args[ai + 2], args[ai + 3], mastersArg);
            return;
        }

        if (clearOverridesMode)
        {
            int ci = Array.IndexOf(args, "--clear-overrides");
            if (ci + 3 >= args.Length) { Console.WriteLine("usage: --clear-overrides <inDir> <outDir> <listFile|->"); return; }
            ClearOverrides(args[ci + 1], args[ci + 2], args[ci + 3]);
            return;
        }

        if (setMiParentMode)
        {
            int pi = Array.IndexOf(args, "--set-mi-parent");
            if (pi + 4 >= args.Length) { Console.WriteLine("usage: --set-mi-parent <inDir> <outDir> <listFile|-> <masterPkg> <masterName>"); return; }
            SetMiParent(args[pi + 1], args[pi + 2], args[pi + 3], args[pi + 4], args[pi + 5]);
            return;
        }

        if (retargetMode)
        {
            int ri = Array.IndexOf(args, "--retarget-mis");
            int fi = ri + 3 < args.Length && !args[ri + 3].StartsWith("--") ? ri + 3 : -1;
            RetargetMIs(args[ri + 1], args[ri + 2], fi > 0 ? args[fi] : null);
            return;
        }
        
        if (args.Contains("--prune-level"))
        {
            int li = Array.IndexOf(args, "--prune-level");
            if (li + 2 >= args.Length) { Console.WriteLine("usage: --prune-level <in.umap> <out.umap> [--drop-classes A,B] [--keep-mesh-prefix P] [--keep-names X,Y]"); return; }
            string drops = "", prefix = "", keeps = "";
            int di = Array.IndexOf(args, "--drop-classes"); if (di > 0) drops = args[di + 1];
            int pi2 = Array.IndexOf(args, "--keep-mesh-prefix"); if (pi2 > 0) prefix = args[pi2 + 1];
            int ki = Array.IndexOf(args, "--keep-names"); if (ki > 0) keeps = args[ki + 1];
            string keepIdxArg = "";
            int xi = Array.IndexOf(args, "--keep-export"); if (xi > 0) keepIdxArg = args[xi + 1];
            PruneLevel(args[li + 1], args[li + 2],
                drops.Split(',', StringSplitOptions.RemoveEmptyEntries),
                prefix,
                keeps.Split(',', StringSplitOptions.RemoveEmptyEntries),
                keepIdxArg.Split(',', StringSplitOptions.RemoveEmptyEntries).Select(x => int.Parse(x.Trim())).ToArray());
            return;
        }

        if (args.Contains("--set-bool"))
        {
            int li = Array.IndexOf(args, "--set-bool");
            if (li + 4 >= args.Length) { Console.WriteLine("usage: --set-bool <in.umap> <out.umap> <exportName> <propName> <true|false>"); return; }
            SetBoolProp(args[li + 1], args[li + 2], args[li + 3], args[li + 4],
                string.Equals(args[li + 5], "true", StringComparison.OrdinalIgnoreCase));
            return;
        }

        if (args.Contains("--set-class-ref"))
        {
            int li = Array.IndexOf(args, "--set-class-ref");
            if (li + 6 >= args.Length) { Console.WriteLine("usage: --set-class-ref <in.uasset> <out.uasset> <exportName> <propName> <packagePath> <className>"); return; }
            SetClassRef(args[li + 1], args[li + 2], args[li + 3], args[li + 4], args[li + 5], args[li + 6]);
            return;
        }

        if (args.Contains("--set-array-class-ref"))
        {
            int li = Array.IndexOf(args, "--set-array-class-ref");
            if (li + 8 > args.Length) { Console.WriteLine("usage: --set-array-class-ref <in.uasset> <out.uasset> <exportName> <arrayProp> <keyField> <field> <mapJson>"); return; }
            SetArrayClassRef(args[li + 1], args[li + 2], args[li + 3], args[li + 4], args[li + 5], args[li + 6], args[li + 7]);
            return;
        }

        if (args.Contains("--set-array-bool"))
        {
            int li = Array.IndexOf(args, "--set-array-bool");
            if (li + 8 > args.Length) { Console.WriteLine("usage: --set-array-bool <in.uasset> <out.uasset> <exportName> <arrayProp> <keyField> <field> <true|false> [key=value,key=value]"); return; }
            var only = li + 8 < args.Length ? args[li + 8] : "";
            SetArrayBool(args[li + 1], args[li + 2], args[li + 3], args[li + 4], args[li + 5], args[li + 6],
                string.Equals(args[li + 7], "true", StringComparison.OrdinalIgnoreCase), only);
            return;
        }

        if (args.Contains("--replace-spline"))
        {
            int li = Array.IndexOf(args, "--replace-spline");
            if (li + 4 >= args.Length) { Console.WriteLine("usage: --replace-spline <in.uasset> <out.uasset> <roadExportName> <points.json>"); return; }
            ReplaceSpline(args[li + 1], args[li + 2], args[li + 3], args[li + 4]);
            return;
        }

        if (args.Contains("--set-gate-transforms"))
        {
            int li = Array.IndexOf(args, "--set-gate-transforms");
            if (li + 3 >= args.Length) { Console.WriteLine("usage: --set-gate-transforms <in.uasset> <out.uasset> <gates.json>"); return; }
            SetGateTransforms(args[li + 1], args[li + 2], args[li + 3]);
            return;
        }

        if (args.Contains("--drop-actors"))
        {
            int li = Array.IndexOf(args, "--drop-actors");
            if (li + 3 >= args.Length) { Console.WriteLine("usage: --drop-actors <in.uasset> <out.uasset> <ClassA,ClassB>"); return; }
            DropActors(args[li + 1], args[li + 2], args[li + 3]);
            return;
        }

        if (args.Contains("--find-actor-block"))
        {
            int li = Array.IndexOf(args, "--find-actor-block");
            FindActorBlock(args[li + 1]);
            return;
        }

        if (args.Contains("--list-actors"))
        {
            int li = Array.IndexOf(args, "--list-actors");
            ListActors(args[li + 1]);
            return;
        }

        if (args.Contains("--roundtrip"))
        {
            int li = Array.IndexOf(args, "--roundtrip");
            UAsset.CaptureOriginalExportData = true;
            var rt = new UAsset(args[li + 1], EngineVersion.VER_UE5_5, Mappings);
            int nul = 0, sz = 0;
            foreach (var e in rt.Exports) if (e is NormalExport ne) { sz++; if (ne.OriginalData == null) nul++; }
            Console.WriteLine($"ROUNDTRIP exports={sz} originalDataNull={nul}");
            rt.Write(args[li + 2]);
            return;
        }

        if (args.Contains("--print-spline"))
        {
            int li = Array.IndexOf(args, "--print-spline");
            PrintSpline(args[li + 1], args[li + 2]);
            return;
        }

        if (args.Contains("--print-gates"))
        {
            int li = Array.IndexOf(args, "--print-gates");
            PrintGates(args[li + 1]);
            return;
        }

        if (args.Contains("--set-child-class-refs"))
        {
            int li = Array.IndexOf(args, "--set-child-class-refs");
            if (li + 6 >= args.Length) { Console.WriteLine("usage: --set-child-class-refs <in.uasset> <out.uasset> <ownerNamePrefix> <componentName> <packagePath> <className>"); return; }
            SetChildClassRefs(args[li + 1], args[li + 2], args[li + 3], args[li + 4], args[li + 5], args[li + 6]);
            return;
        }

        if (args.Contains("--set-spline"))
        {
            int li = Array.IndexOf(args, "--set-spline");
            if (li + 3 >= args.Length) { Console.WriteLine("usage: --set-spline <in.umap> <out.umap> <RoadActorName> <points.json> [--props k=v,...]"); return; }
            string props = "";
            int pr = Array.IndexOf(args, "--props"); if (pr > 0) props = args[pr + 1];
            SetRoadSpline(args[li + 1], args[li + 2], args[li + 3], args[li + 4], props);
            return;
        }

        if (args.Contains("--normalize-actors"))
        {
            int li = Array.IndexOf(args, "--normalize-actors");
            NormalizeActors(args[li + 1], args[li + 2]);
            return;
        }

        if (args.Contains("--verify-sizes"))
        {
            int li = Array.IndexOf(args, "--verify-sizes");
            VerifySizes(args[li + 1], li + 2 < args.Length && !args[li + 2].StartsWith("--") ? args[li + 2] : "");
            return;
        }

        if (args.Contains("--deps-dump"))
        {
            int li = Array.IndexOf(args, "--deps-dump");
            DumpDeps(args[li + 1], li + 2 < args.Length ? args[li + 2] : "");
            return;
        }

        if (args.Contains("--fix-road-bounds"))
        {
            int li = Array.IndexOf(args, "--fix-road-bounds");
            FixRoadBounds(args[li + 1], args[li + 2]);
            return;
        }

        if (args.Contains("--merge-actors"))
        {
            int li = Array.IndexOf(args, "--merge-actors");
            if (li + 4 >= args.Length) { Console.WriteLine("usage: --merge-actors <base.umap> <donor.umap> <out.umap> <classesCsv> [--skip-classes a,b]"); return; }
            string sk = "";
            int ni = Array.IndexOf(args, "--only-names");
            string onlyNames = ni > 0 && ni + 1 < args.Length ? args[ni + 1] : "";
            int si = Array.IndexOf(args, "--skip-classes");
            if (si > 0 && si + 1 < args.Length) sk = args[si + 1];
            MergeActors(args[li + 1], args[li + 2], args[li + 3], args[li + 4], sk, onlyNames);
            return;
        }

        if (args.Contains("--add-streaming-level"))
        {
            int li = Array.IndexOf(args, "--add-streaming-level");
            if (li + 4 >= args.Length) { Console.WriteLine("usage: --add-streaming-level <in.umap> <out.umap> <packagePath> <assetName>"); return; }
            AddStreamingLevel(args[li + 1], args[li + 2], args[li + 3], args[li + 4]);
            return;
        }

        if (args.Contains("--set-export-bytes"))
        {
            int bi = Array.IndexOf(args, "--set-export-bytes");
            if (bi + 4 >= args.Length) { Console.WriteLine("usage: --set-export-bytes <in> <out> <exportName> <hexFile>"); return; }
            SetExportBytes(args[bi + 1], args[bi + 2], args[bi + 3], args[bi + 4]);
            return;
        }

        if (args.Contains("--retarget-package"))
        {
            int li = Array.IndexOf(args, "--retarget-package");
            if (li + 4 >= args.Length) { Console.WriteLine("usage: --retarget-package <in> <out> <oldPath> <newPath> [--rename old=new,...]"); return; }
            string rn = "";
            int rr = Array.IndexOf(args, "--rename");
            if (rr > 0 && rr + 1 < args.Length) rn = args[rr + 1];
            RetargetPackage(args[li + 1], args[li + 2], args[li + 3], args[li + 4], rn);
            return;
        }

        if (args.Contains("--dump-export"))
        {
            int li = Array.IndexOf(args, "--dump-export");
            if (li + 2 >= args.Length) { Console.WriteLine("usage: --dump-export <asset> <exportName> [--limit N]"); return; }
            int lim = 3;
            int lx = Array.IndexOf(args, "--limit");
            if (lx > 0 && lx + 1 < args.Length) int.TryParse(args[lx + 1], out lim);
            DumpExport(args[li + 1], args[li + 2], Math.Max(1, lim));
            return;
        }

        if (args.Contains("--lane-roads"))
        {
            int li = Array.IndexOf(args, "--lane-roads");
            if (li + 3 >= args.Length) { Console.WriteLine("usage: --lane-roads <in.umap> <out.umap> <lane_roads.json>"); return; }
            RunLaneRoads(args[li + 1], args[li + 2], args[li + 3]);
            return;
        }

        if (args.Contains("--add-garage"))
        {
            int li = Array.IndexOf(args, "--add-garage");
            if (li + 6 >= args.Length) { Console.WriteLine("usage: --add-garage <in.umap> <out.umap> <x> <y> <z> <yaw>"); return; }
            RunAddGarage(args[li + 1], args[li + 2],
                double.Parse(args[li + 3], System.Globalization.CultureInfo.InvariantCulture),
                double.Parse(args[li + 4], System.Globalization.CultureInfo.InvariantCulture),
                double.Parse(args[li + 5], System.Globalization.CultureInfo.InvariantCulture),
                double.Parse(args[li + 6], System.Globalization.CultureInfo.InvariantCulture));
            return;
        }

        if (args.Contains("--clone-actor"))
        {
            int li = Array.IndexOf(args, "--clone-actor");
            if (li + 8 >= args.Length) { Console.WriteLine("usage: --clone-actor <in.umap> <out.umap> <templateActor> <newActorName> <x> <y> <z> <yaw>"); return; }
            CloneActorSubtree(args[li + 1], args[li + 2], args[li + 3], args[li + 4],
                double.Parse(args[li + 5], System.Globalization.CultureInfo.InvariantCulture),
                double.Parse(args[li + 6], System.Globalization.CultureInfo.InvariantCulture),
                double.Parse(args[li + 7], System.Globalization.CultureInfo.InvariantCulture),
                double.Parse(args[li + 8], System.Globalization.CultureInfo.InvariantCulture));
            return;
        }

        if (args.Contains("--bake-nav"))
        {
            int li = Array.IndexOf(args, "--bake-nav");
            if (li + 3 >= args.Length) { Console.WriteLine("usage: --bake-nav <in.umap> <out.umap> <nav.json>"); return; }
            RunBakeNav(args[li + 1], args[li + 2], args[li + 3]);
            return;
        }

        if (args.Contains("--level-actors"))
        {
            int li = Array.IndexOf(args, "--level-actors");
            if (li + 1 >= args.Length) { Console.WriteLine("usage: --level-actors <map.umap>"); return; }
            ListLevelActors(args[li + 1]);
            return;
        }

        if (args.Contains("--class-dump"))
        {
            int li = Array.IndexOf(args, "--class-dump");
            if (li + 2 >= args.Length) { Console.WriteLine("usage: --class-dump <map.umap> <ClassName> [--limit N]"); return; }
            int lim = 3;
            int lix = Array.IndexOf(args, "--limit");
            if (lix > 0 && lix + 1 < args.Length) int.TryParse(args[lix + 1], out lim);
            ClassDump(args[li + 1], args[li + 2], lim);
            return;
        }

        if (args.Contains("--add-bp-actor"))
        {
            int li = Array.IndexOf(args, "--add-bp-actor");
            if (li + 9 >= args.Length) { Console.WriteLine("usage: --add-bp-actor <in.umap> <out.umap> <pkgPath> <bpClass> <actorName> <x> <y> <z> <yaw>"); return; }
            AddBpActor(args[li + 1], args[li + 2], args[li + 3], args[li + 4], args[li + 5],
                       double.Parse(args[li + 6], System.Globalization.CultureInfo.InvariantCulture),
                       double.Parse(args[li + 7], System.Globalization.CultureInfo.InvariantCulture),
                       double.Parse(args[li + 8], System.Globalization.CultureInfo.InvariantCulture),
                       double.Parse(args[li + 9], System.Globalization.CultureInfo.InvariantCulture));
            return;
        }

        if (args.Contains("--move-actor"))
        {
            int li = Array.IndexOf(args, "--move-actor");
            if (li + 7 >= args.Length) { Console.WriteLine("usage: --move-actor <in.umap> <out.umap> <actorName> <x> <y> <z> <yaw>"); return; }
            MoveActor(args[li + 1], args[li + 2], args[li + 3],
                      double.Parse(args[li + 4], System.Globalization.CultureInfo.InvariantCulture),
                      double.Parse(args[li + 5], System.Globalization.CultureInfo.InvariantCulture),
                      double.Parse(args[li + 6], System.Globalization.CultureInfo.InvariantCulture),
                      double.Parse(args[li + 7], System.Globalization.CultureInfo.InvariantCulture));
            return;
        }

        if (args.Contains("--compact-imports"))
        {
            int li = Array.IndexOf(args, "--compact-imports");
            if (li + 2 >= args.Length) { Console.WriteLine("usage: --compact-imports <in.umap> <out.umap>"); return; }
            CompactImports(args[li + 1], args[li + 2]);
            return;
        }

        if (ptProbe)
        {
            var asset = new UAsset(args[ptIdx + 1], EngineVersion.VER_UE5_5, Mappings);
            void Walk(PropertyData d, string path)
            {
                if (d == null) return;
                string dname = d.Name == null ? "" : (d.Name.Value?.Value ?? "");
                if (path.EndsWith("ParentTables", StringComparison.Ordinal) || dname == "ParentTables")
                {
                    Console.WriteLine($"PT {path}: type={d.GetType().Name}");
                    if (d is ArrayPropertyData ap)
                    {
                        Console.WriteLine($"  count={ap.Value.Length} elemType={(ap.Value.Length>0?ap.Value[0].GetType().Name:"n/a")}");
                        foreach (var e in ap.Value)
                        {
                            string en = e.Name == null ? "?" : (e.Name.Value?.Value ?? "?");
                            string ev;
                            if (e is ObjectPropertyData o) ev = o.Value?.Index.ToString() ?? "null";
                            else ev = e.GetType().Name;
                            Console.WriteLine($"  elem {e.GetType().Name} name={en} val={ev}");
                        }
                    }
                }
                if (d is StructPropertyData sd) foreach (var c in sd.Value) Walk(c, path + "." + (c.Name == null ? "?" : c.Name.Value?.Value ?? "?"));
                if (d is ArrayPropertyData ap2 && ap2.Value.Length > 0 && ap2.Value[0] is StructPropertyData) foreach (var c in ap2.Value) Walk((PropertyData)c, path + "[]");
            }
            foreach (var ex in asset.Exports)
            {
                Console.WriteLine($"EXPORT {ex.ObjectName.Value} type={ex.GetType().Name}");
                System.Collections.Generic.IEnumerable<PropertyData> props = null;
                if (ex is UAssetAPI.ExportTypes.NormalExport ne) props = ne.Data;
                else if (ex is UAssetAPI.ExportTypes.DataTableExport dte) props = null;
                if (props != null) foreach (var p in props)
                {
                    string pn = p.Name == null ? "?" : (p.Name.Value?.Value ?? "?");
                    Console.WriteLine($"  PROP {pn}: {p.GetType().Name}");
                    Walk(p, pn);
                }
                else Console.WriteLine($"  (no generic Data accessor)");
            }
            Console.WriteLine("=== parenttables probe done ===");
            return;
        }

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
        else if (propProbeMode)
        {
            var idx = Array.IndexOf(args, "--propprobe");
            PropProbe(args.ElementAtOrDefault(idx + 1)!);
        }
        else if (makeCompositeMode)
        {
            var idx = Array.IndexOf(args, "--make-composite");
            var configPath = args.ElementAtOrDefault(idx + 1) ?? "config.json";
            var templatePath = args.ElementAtOrDefault(idx + 2) ?? Path.Combine(RootDir, "template.uasset");
            var outputDir = args.ElementAtOrDefault(idx + 3) ?? RootDir;
            MakeComposite(configPath, templatePath, outputDir);
        }
        else if (alignImportsMode)
        {
            var idx = Array.IndexOf(args, "--align-imports");
            AlignImports(args.ElementAtOrDefault(idx + 1) ?? Path.Combine(RootDir, "Cargos.uasset"),
                         args.ElementAtOrDefault(idx + 2) ?? Path.Combine(RootDir, "child.uasset"),
                         args.ElementAtOrDefault(idx + 3) ?? RootDir);
        }
        else if (args.Contains("--roundtrip"))
        {
            var idx = Array.IndexOf(args, "--roundtrip");
            var rtPath = args.ElementAtOrDefault(idx + 1) ?? Path.Combine(RootDir, "Cargos.uasset");
            if (!Path.IsPathRooted(rtPath)) rtPath = Path.Combine(RootDir, rtPath);
            var outRt = args.ElementAtOrDefault(idx + 2) ?? rtPath + ".rt.uasset";
            var a = new UAsset(rtPath, EngineVersion.VER_UE5_5, Mappings);
            a.Write(outRt);
            var orig = File.ReadAllBytes(rtPath);
            var redo = File.ReadAllBytes(outRt);
            Console.WriteLine($"orig={orig.Length} rewritten={redo.Length} identical={orig.SequenceEqual(redo)}");
            if (!orig.SequenceEqual(redo))
            {
                int n = Math.Min(orig.Length, redo.Length);
                for (int i = 0; i < n; i++)
                    if (orig[i] != redo[i])
                    {
                        Console.WriteLine($"first-diff at byte {i} (0x{i:X}): orig=0x{orig[i]:X2} rewritten=0x{redo[i]:X2}");
                        break;
                    }
                if (orig.Length != redo.Length)
                    Console.WriteLine($"length differs: {orig.Length} vs {redo.Length}");
            }
            return;
        }
        else if (args.Contains("--get-text"))
        {
            var idx = Array.IndexOf(args, "--get-text");
            var path = args.ElementAtOrDefault(idx + 1);
            var propPath = args.ElementAtOrDefault(idx + 2);
            if (path == null || propPath == null) { Console.WriteLine("usage: --get-text <asset.uasset> <prop.path>"); return; }
            if (!Path.IsPathRooted(path)) path = Path.Combine(RootDir, path);
            var a = new UAsset(path, EngineVersion.VER_UE5_5, Mappings);
            var all = new List<PropertyData>();
            foreach (var e in a.Exports) if (e is NormalExport ne) all.AddRange(ne.Data);
            var p = ResolveProperty(all, propPath);
            if (p == null) { Console.WriteLine($"GETTEXT_NOPROP {propPath}"); return; }
            if (p is TextPropertyData tp)
                Console.WriteLine($"GETTEXT {propPath} NS={(tp.Namespace?.Value ?? "<null>")} Key={(tp.Value?.Value ?? "<null>")} Invariant={(tp.CultureInvariantString?.Value ?? "<null>")} Flags={tp.Flags}");
            else
                Console.WriteLine($"GETTEXT_NOTTEXT {propPath} type={p.GetType().Name}");
            return;
        }
        else if (args.Contains("--textprobe"))
        {
            var idx = Array.IndexOf(args, "--textprobe");
            var path = args.ElementAtOrDefault(idx + 1) ?? Path.Combine(RootDir, "Cargos_ScheduleI.uasset");
            var rowFilter = args.ElementAtOrDefault(idx + 2);
            if (!Path.IsPathRooted(path)) path = Path.Combine(RootDir, path);
            var a = new UAsset(path, EngineVersion.VER_UE5_5, Mappings);
            var dt = FindDataTable(a);
            if (dt == null) { Console.WriteLine("no datatable"); return; }
            foreach (var row in dt.Table.Data)
            {
                var spd = row as StructPropertyData;
                if (spd == null) continue;
                var rowName = spd.Name?.Value?.Value ?? "?";
                if (!string.IsNullOrEmpty(rowFilter) && !string.Equals(rowName, rowFilter, StringComparison.OrdinalIgnoreCase)) continue;
                foreach (var prop in spd.Value)
                {
                    if (prop is TextPropertyData tp && (prop.Name.Value.Value == "Name"))
                    {
                        Console.WriteLine($"row={rowName} Name: Flags={tp.Flags} Hist={tp.HistoryType} NS={(tp.Namespace?.Value == null ? "<null>" : tp.Namespace.Value)} Key/Value={(tp.Value == null || tp.Value.Value == null ? "<null>" : tp.Value.Value)} Invariant={(tp.CultureInvariantString == null || tp.CultureInvariantString.Value == null ? "<null>" : tp.CultureInvariantString.Value)}");
                    }
                    if (prop.Name.Value.Value == "Name2" && prop is StructPropertyData n2)
                    {
                        foreach (var sp in n2.Value)
                        {
                            if (sp.Name.Value.Value == "Texts" && sp is ArrayPropertyData arr)
                            {
                                foreach (var el in arr.Value)
                                {
                                    if (el is TextPropertyData t2)
                                        Console.WriteLine($"row={rowName} Name2.Texts: Flags={t2.Flags} Hist={t2.HistoryType} NS={(t2.Namespace?.Value == null ? "<null>" : t2.Namespace.Value)} Key={(t2.Value == null || t2.Value.Value == null ? "<null>" : t2.Value.Value)} Invariant={(t2.CultureInvariantString == null || t2.CultureInvariantString.Value == null ? "<null>" : t2.CultureInvariantString.Value)}");
                                }
                            }
                            if (sp.Name.Value.Value == "Pattern" && sp is TextPropertyData pat)
                                Console.WriteLine($"row={rowName} Pattern: Flags={pat.Flags} Hist={pat.HistoryType} NS={(pat.Namespace?.Value == null ? "<null>" : pat.Namespace.Value)} Key={(pat.Value == null || pat.Value.Value == null ? "<null>" : pat.Value.Value)} Invariant={(pat.CultureInvariantString == null || pat.CultureInvariantString.Value == null ? "<null>" : pat.CultureInvariantString.Value)}");
                        }
                    }
                }
                break; // template row only
            }
            return;
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
                Console.WriteLine($"{indent}{name} (Map):");
                if (mp.Value != null)
                {
                    foreach (var kv in mp.Value)
                    {
                        var kDesc = kv.Key switch
                        {
                            UAssetAPI.PropertyTypes.Objects.NamePropertyData kn => kn.Value?.Value?.Value ?? "(null)",
                            UAssetAPI.PropertyTypes.Objects.StrPropertyData ks => ks.Value?.Value ?? "(null)",
                            _ => kv.Key?.PropertyType?.ToString() ?? "?"
                        };
                        var vDesc = kv.Value switch
                        {
                            UAssetAPI.PropertyTypes.Objects.IntPropertyData iv => iv.Value.ToString(),
                            UAssetAPI.PropertyTypes.Objects.Int64PropertyData ilv => ilv.Value.ToString(),
                            UAssetAPI.PropertyTypes.Objects.FloatPropertyData fv => fv.Value.ToString(),
                            _ => kv.Value?.PropertyType?.ToString() ?? "?"
                        };
                        Console.WriteLine($"{indent}  {kDesc} = {vDesc}");
                    }
                }
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
    // ---- print one export's properties, arrays summarised ----------------------
    // A world-partition map is ~370 MB of uexp; dumping it whole is unusable. This prints a
    // single named export with array counts and the first few elements, which is what you
    // need to learn a struct's layout (e.g. FMTRoadGraphData.NodeList).
    static void DumpExport(string path, string name, int limit)
    {
        var asset = new UAsset(path, EngineVersion.VER_UE5_5, Mappings);
        int hits = 0;
        for (int i = 0; i < asset.Exports.Count; i++)
        {
            var ex = asset.Exports[i];
            string nm = ex.ObjectName?.Value?.Value ?? "";
            if (!nm.Equals(name, StringComparison.OrdinalIgnoreCase) &&
                !nm.Contains(name, StringComparison.OrdinalIgnoreCase)) continue;
            if (!(ex is NormalExport ne)) continue;
            hits++;
            Console.WriteLine($"### Export[{i}] {nm} ({ClassNameOf(asset, ex)}) props={ne.Data.Count}");
            PrintProps(ne.Data, 0, limit);
            if (hits >= 4) break;
        }
        if (hits == 0) Console.WriteLine($"DUMPEXPORT_NONE '{name}'");
        Console.WriteLine($"DUMPEXPORT_END hits={hits}");
    }

    static void PrintProps(List<PropertyData> data, int depth, int limit)
    {
        string pad = new string(' ', 2 + depth * 2);
        foreach (var p in data)
        {
            string n = p.Name?.Value?.Value ?? "";
            string t = p.GetType().Name.Replace("PropertyData", "");
            switch (p)
            {
                case IntPropertyData ip: Console.WriteLine($"{pad}{n} (Int) = {ip.Value}"); break;
                case FloatPropertyData fp: Console.WriteLine($"{pad}{n} (Float) = {fp.Value}"); break;
                case DoublePropertyData dp: Console.WriteLine($"{pad}{n} (Double) = {dp.Value}"); break;
                case BoolPropertyData bp: Console.WriteLine($"{pad}{n} (Bool) = {bp.Value}"); break;
                case NamePropertyData np: Console.WriteLine($"{pad}{n} (Name) = {np.Value?.Value?.Value}"); break;
                case StrPropertyData sp: Console.WriteLine($"{pad}{n} (Str) = {sp.Value?.Value}"); break;
                case EnumPropertyData ep: Console.WriteLine($"{pad}{n} (Enum) = {ep.Value?.Value?.Value}"); break;
                case ObjectPropertyData op: Console.WriteLine($"{pad}{n} (Object) = {op.Value?.Index}"); break;
                case VectorPropertyData vp:
                    Console.WriteLine($"{pad}{n} (Vector) = ({vp.Value.X:F1}, {vp.Value.Y:F1}, {vp.Value.Z:F1})");
                    break;
                case RotatorPropertyData rp:
                    Console.WriteLine($"{pad}{n} (Rotator) = ({rp.Value.Pitch:F1}, {rp.Value.Yaw:F1}, {rp.Value.Roll:F1})");
                    break;
                case ArrayPropertyData ap:
                    Console.WriteLine($"{pad}{n} (Array[{ap.Value.Length}])");
                    for (int i = 0; i < Math.Min(ap.Value.Length, limit); i++)
                    {
                        Console.WriteLine($"{pad}  [{i}]");
                        if (ap.Value[i] is StructPropertyData sd0) PrintProps(sd0.Value, depth + 2, limit);
                        else PrintProps(new List<PropertyData> { ap.Value[i] }, depth + 2, limit);
                    }
                    break;
                case StructPropertyData sd:
                    Console.WriteLine($"{pad}{n} (Struct)");
                    PrintProps(sd.Value, depth + 1, limit);
                    break;
                case MapPropertyData mp:
                    Console.WriteLine($"{pad}{n} (Map[{mp.Value?.Count ?? 0}])");
                    break;
                default:
                    Console.WriteLine($"{pad}{n} ({t})");
                    break;
            }
        }
    }

    // ---- retarget a cooked package's identity ---------------------------------
    // The package name lives in three places: the summary (UE5 stores it in FolderName), the
    // name map (every import referring to this package), and the World export, which is named
    // after the package's short name. Miss any one and the map loads under its old identity or
    // fails to link. Name-map indices are rewritten in place so no FName index shifts.
    // Replace one export's serialized bytes verbatim (used for UWorld's native streaming block, which
    // UAssetAPI does not model: its Write path drops unparsed trailing data).
    static void SetExportBytes(string inPath, string outPath, string exportName, string hexFile)
    {
        var asset = new UAsset(inPath, EngineVersion.VER_UE5_5, Mappings);
        string hex = File.ReadAllText(hexFile).Replace(" ", "").Replace("\n", "").Replace("\r", "").Trim();
        byte[] data = new byte[hex.Length / 2];
        for (int i = 0; i < data.Length; i++) data[i] = Convert.ToByte(hex.Substring(i * 2, 2), 16);
        for (int i = 0; i < asset.Exports.Count; i++)
        {
            var ex = asset.Exports[i];
            if ((ex.ObjectName?.Value?.Value ?? "") != exportName) continue;
            if (ex is NormalExport ne) ne.Data = new List<PropertyData>();
            ex.OriginalData = data;
            ex.DataDirty = false;
            ex.Extras = Array.Empty<byte>();
            Console.WriteLine($"SETBYTES export[{i}] {exportName} -> {data.Length} bytes");
            asset.Write(outPath);
            Console.WriteLine($"SETBYTES_OK -> {outPath}");
            return;
        }
        Console.WriteLine($"SETBYTES_FAIL no export named {exportName}");
    }

    static void RetargetPackage(string inPath, string outPath, string oldPath, string newPath, string renames)
    {
        UAsset.CaptureOriginalExportData = true;
        var asset = new UAsset(inPath, EngineVersion.VER_UE5_5, Mappings);
        string oldShort = oldPath.Substring(oldPath.LastIndexOf('/') + 1);
        string newShort = newPath.Substring(newPath.LastIndexOf('/') + 1);

        var exact = new Dictionary<string, string>(StringComparer.Ordinal) { [oldPath] = newPath, [oldShort] = newShort };
        if (!string.IsNullOrEmpty(renames))
        {
            foreach (var pair in renames.Split(',', StringSplitOptions.RemoveEmptyEntries))
            {
                var bits = pair.Split('=');
                if (bits.Length == 2) exact[bits[0].Trim()] = bits[1].Trim();
            }
        }

        var names = asset.GetNameMapIndexList();
        int renamed = 0, repathed = 0;
        for (int i = 0; i < names.Count; i++)
        {
            string cur = names[i]?.Value ?? "";
            string next = cur;
            if (exact.TryGetValue(cur, out var hit)) next = hit;
            else if (cur.StartsWith(oldPath + "/", StringComparison.Ordinal) || cur.StartsWith(oldPath + ".", StringComparison.Ordinal))
                next = newPath + cur.Substring(oldPath.Length);
            if (next == cur) continue;
            asset.SetNameReference(i, new FString(next));
            if (next.StartsWith(newPath)) repathed++; else renamed++;
            Console.WriteLine($"NAME[{i}] '{cur}' -> '{next}'");
        }

        string folder = asset.FolderName?.Value ?? "";
        if (folder.StartsWith(oldPath, StringComparison.Ordinal))
        {
            asset.FolderName = new FString(newPath + folder.Substring(oldPath.Length));
            Console.WriteLine($"PACKAGE '{folder}' -> '{asset.FolderName.Value}'");
        }
        else if (folder.Length == 0 || folder == "None")
        {
            asset.FolderName = new FString(newPath);
            Console.WriteLine($"PACKAGE (empty) -> '{newPath}'");
        }

        int worlds = 0;
        for (int i = 0; i < asset.Exports.Count; i++)
        {
            var ex = asset.Exports[i];
            if (ClassNameOf(asset, ex) != "World") continue;
            string nm = ex.ObjectName?.Value?.Value ?? "";
            if (nm == oldShort || exact.ContainsKey(nm))
            {
                string nn = exact.TryGetValue(nm, out var mapped) ? mapped : newShort;
                ex.ObjectName = FName.FromString(asset, nn);
                worlds++;
                Console.WriteLine($"WORLD export[{i}] '{nm}' -> '{nn}'");
            }
        }

        asset.Write(outPath);
        Console.WriteLine($"RETARGET_OK names_pathed={repathed} names_renamed={renamed} worlds={worlds} -> {outPath}");
    }

    // ---- link a sublevel the way MT's own maps do ------------------------------
    // NS's main map carries no actor referencing its roads map: the link is a
    // LevelStreamingAlwaysLoaded export whose Outer is the World and whose WorldAsset points at
    // the sublevel package. Replicate that structure exactly rather than inventing one.
    static void AddStreamingLevel(string inPath, string outPath, string pkgPath, string assetName)
    {
        // Capture every export's original bytes: without this, adding one export re-serialises the
        // whole map through UAssetAPI's writer, which cannot reproduce cooked bytes (world block,
        // soft paths) and silently corrupts the package.
        UAsset.CaptureOriginalExportData = true;
        var asset = new UAsset(inPath, EngineVersion.VER_UE5_5, Mappings);

        int worldIdx1 = -1;
        for (int i = 0; i < asset.Exports.Count; i++)
            if (ClassNameOf(asset, asset.Exports[i]) == "World") { worldIdx1 = i + 1; break; }
        if (worldIdx1 < 0) { Console.WriteLine("STREAM_FAIL no World export"); return; }

        int enginePkg0 = -1;
        for (int i = 0; i < asset.Imports.Count; i++)
        {
            var im = asset.Imports[i];
            if (im.ObjectName?.Value?.Value == "/Script/Engine" && im.ClassName?.Value?.Value == "Package" && (im.OuterIndex?.Index ?? 0) == 0)
            { enginePkg0 = i; break; }
        }
        if (enginePkg0 < 0) { Console.WriteLine("STREAM_FAIL no /Script/Engine package import"); return; }

        int clsImport0 = -1;
        for (int i = 0; i < asset.Imports.Count; i++)
        {
            var im = asset.Imports[i];
            if (im.ObjectName?.Value?.Value == "LevelStreamingAlwaysLoaded" &&
                (im.OuterIndex?.Index ?? 0) == -(enginePkg0 + 1) &&
                im.ClassName?.Value?.Value == "Class") { clsImport0 = i; break; }
        }
        if (clsImport0 < 0)
        {
            asset.Imports.Add(new Import("/Script/CoreUObject", "Class", FPackageIndex.FromImport(enginePkg0), "LevelStreamingAlwaysLoaded", false, asset));
            clsImport0 = asset.Imports.Count - 1;
            Console.WriteLine($"  added import Class LevelStreamingAlwaysLoaded [{clsImport0 + 1}]");
        }

        var softPath = new FSoftObjectPath(FName.FromString(asset, pkgPath), FName.FromString(asset, assetName), new FString("None"));
        var soft = new SoftObjectPropertyData(FName.FromString(asset, "WorldAsset")) { Value = softPath };
        soft.PropertyTypeName = MakeTypeName(asset, new FString("SoftObjectProperty"));
        // This package serialises soft object paths by INDEX into an asset-level table; a path
        // that is not registered there throws on write.
        // The base map may have no soft-path table at all; a soft object path cannot be expressed
        // without one, so create it (the package format supports it via its own version flag).
        if (asset.SoftObjectPathList == null) asset.SoftObjectPathList = new List<FSoftObjectPath>();
        asset.SoftObjectPathList.Add(softPath);
        Console.WriteLine($"  registered SoftObjectPathList[{asset.SoftObjectPathList.Count - 1}] = {pkgPath}.{assetName}");

        var ex = new NormalExport(new List<PropertyData> { soft }, asset, Array.Empty<byte>())
        {
            ObjectName = FName.FromString(asset, "LevelStreamingAlwaysLoaded_0"),
            OuterIndex = new FPackageIndex(worldIdx1),
            ClassIndex = new FPackageIndex(-(clsImport0 + 1))
        };
        // A cook writes this object as a compact UNVERSIONED blob (44 bytes for a soft-path-only
        // LevelStreamingAlwaysLoaded). UAssetAPI's tagged writer emits ~63 bytes of name/type indices
        // instead, which the engine fails to parse and silently drops - the streaming level then never
        // registers even though the export is present. Emit the cooked shape: same-class template with
        // only the soft-path table index substituted.
        // The 44-byte cook-shaped blob below is UNVERSIONED and only valid for a package that
        // itself uses unversioned properties (dump header: HasUnversioned=True, e.g. the
        // Nordschleife maps). This project's own maps are HasUnversioned=False (tagged), where
        // unversioned bytes are unreadable and corrupt the export - so branch on the package.
        bool pkgUnversioned = asset.HasUnversionedProperties;
        byte[] cooked = pkgUnversioned ? Convert.FromHexString(
            "00020e030000000000000000" + "05000000" + "00000000000000000000803f000000000000043f0000803f00000000")
            : null;
        int softIdxForBytes = asset.SoftObjectPathList != null && asset.SoftObjectPathList.Count > 0
            ? asset.SoftObjectPathList.Count - 1
            : -1;
        if (pkgUnversioned && softIdxForBytes >= 0)
        {
            Array.Copy(BitConverter.GetBytes(softIdxForBytes), 0, cooked, 12, 4);
            ex.OriginalData = cooked;
            ex.DataDirty = false;
            Console.WriteLine($"  streaming export written in cooked form ({cooked.Length} B, softpath idx {softIdxForBytes})");
        }
        else
        {
            ex.DataDirty = true;   // package is versioned -> this export must be a TAGGED stream
            Console.WriteLine($"  package HasUnversioned={pkgUnversioned}; writing export as tagged properties");
        }
        asset.Exports.Add(ex);

        asset.Write(outPath);
        Console.WriteLine($"STREAM_OK export[{asset.Exports.Count - 1}] WorldAsset={pkgPath}.{assetName} -> {outPath}");
    }

    // ---- transplant actors from one cooked map into another -------------------
    // Merging is what makes roads usable: MT's road system and AI spawner query actors in the
    // loaded persistent level, so a streamed sublevel is invisible to them. This rebuilds the
    // donor's exports inside the base package: names are re-created in the base's name table,
    // every import is found-or-added (package/class/outer identity), every FPackageIndex is
    // remapped, and the actors are appended to the base ULevel::Actors list.
    class MergeCtx
    {
        public UAsset Base;
        public UAsset Donor;
        public Dictionary<int, int> ImportMap = new Dictionary<int, int>();
        public Dictionary<int, int> ExportMap = new Dictionary<int, int>();
        public int DonorLevel = -1, BaseLevel = -1, DonorWorld = -1, BaseWorld = -1;
        public int Dropped = 0;

        public int MapImport(int i)
        {
            if (ImportMap.TryGetValue(i, out var hit)) return hit;
            var di = Donor.Imports[i];
            string obj = di.ObjectName?.Value?.Value ?? "";
            string cp = di.ClassPackage?.Value?.Value ?? "";
            string cn = di.ClassName?.Value?.Value ?? "";
            int outerDon = di.OuterIndex?.Index ?? 0;
            int outerBase = outerDon == 0 ? 0 : MapImport(-outerDon - 1);
            for (int j = 0; j < Base.Imports.Count; j++)
            {
                var bi = Base.Imports[j];
                if ((bi.ObjectName?.Value?.Value ?? "") != obj) continue;
                if ((bi.ClassPackage?.Value?.Value ?? "") != cp) continue;
                if ((bi.ClassName?.Value?.Value ?? "") != cn) continue;
                int bo = bi.OuterIndex?.Index ?? 0;
                if (outerDon == 0 ? bo != 0 : bo != -(outerBase + 1)) continue;
                ImportMap[i] = j;
                return j;
            }
            // An import with no outer (the /Script/X package itself) must serialize a NULL outer.
            // FromImport(0) would emit -1, which means "outer is import 0" - a self-reference that
            // makes the package unresolvable and deadlocks every class created beneath it.
            var outerPi = outerDon == 0 ? new FPackageIndex(0) : FPackageIndex.FromImport(outerBase);
            Base.Imports.Add(new Import(cp, cn, outerPi, obj, di.bImportOptional, Base));
            ImportMap[i] = Base.Imports.Count - 1;
            return Base.Imports.Count - 1;
        }

        // Find (or synthesize) the class-default-object import Default__<Class> inside classPkg.
        // A cooked actor export always has TemplateIndex pointing at its archetype; an actor with
        // tpl=0 is accepted as a reference but can never be instantiated.
        public int FindOrAddCdoImport(string className, string classPkg)
        {
            for (int j = 0; j < Base.Imports.Count; j++)
            {
                var bi = Base.Imports[j];
                if ((bi.ObjectName?.Value?.Value ?? "") != "Default__" + className) continue;
                if ((bi.ClassPackage?.Value?.Value ?? "") != classPkg) continue;
                return j;
            }
            int pkgIdx = -1;
            for (int j = 0; j < Base.Imports.Count; j++)
            {
                var bi = Base.Imports[j];
                if ((bi.ObjectName?.Value?.Value ?? "") == classPkg && (bi.ClassName?.Value?.Value ?? "") == "Package")
                { pkgIdx = j; break; }
            }
            if (pkgIdx < 0)
            {
                Base.Imports.Add(new Import("/Script/CoreUObject", "Package", new FPackageIndex(0), classPkg, false, Base));
                pkgIdx = Base.Imports.Count - 1;
            }
            Base.Imports.Add(new Import(classPkg, className, FPackageIndex.FromImport(pkgIdx), "Default__" + className, false, Base));
            return Base.Imports.Count - 1;
        }

        public List<FPackageIndex> MapList(List<FPackageIndex> srcs)
        {
            var dst = new List<FPackageIndex>();
            if (srcs == null) return dst;
            foreach (var x in srcs)
            {
                var m = MapIndex(x);
                if (m != null && m.Index != 0 && !dst.Any(y => y.Index == m.Index)) dst.Add(m);
            }
            return dst;
        }

        public FPackageIndex MapIndex(FPackageIndex pi)
        {
            if (pi == null) return new FPackageIndex(0);
            int idx = pi.Index;
            if (idx == 0) return new FPackageIndex(0);
            if (idx < 0) return FPackageIndex.FromImport(MapImport(-idx - 1));
            int e = idx - 1;
            if (e == DonorLevel && BaseLevel >= 0) return new FPackageIndex(BaseLevel + 1);
            if (e == DonorWorld && BaseWorld >= 0) return new FPackageIndex(BaseWorld + 1);
            if (ExportMap.TryGetValue(e, out var m)) return new FPackageIndex(m + 1);
            Dropped++;
            return new FPackageIndex(0);
        }

        // FNames serialize by index into the name table, so every string the donor used has to
        // exist in the base package before the writer runs.
        public FName Name(FName f, bool keepDummy)
        {
            if (f == null) return null;
            // Cooked assets resolve struct types (Vector, Box, ...) into DUMMY FNames that were
            // never added to the name table. Those must stay dummy or the writer emits the struct
            // as a generic tagged blob (measured 3.5x bloat). Property NAMES, by contrast, cannot
            // stay dummy - the writer throws DummyFNameSerializationException.
            if (f.IsDummy && keepDummy)
            {
                var ds = FString.FromString(f.Value?.Value ?? string.Empty);
                if (!Base.ContainsNameReference(ds)) Base.AddNameReference(ds);
                return FName.DefineDummy(Base, f.Value?.Value ?? string.Empty, f.Number);
            }
            var fs = f.IsDummy ? FString.FromString(f.Value?.Value ?? string.Empty) : (f.Value ?? FString.FromString(string.Empty));
            if (!Base.ContainsNameReference(fs)) Base.AddNameReference(FString.FromString(fs.Value ?? string.Empty));
            return new FName(Base, fs, f.Number);
        }

        public object Deep(object o, string fieldName = null)
        {
            if (o == null) return null;
            var t = o.GetType();
            if (o is FName fn) return Name(fn, fieldName == "StructType");
            if (o is FPackageIndex pi) return MapIndex(pi);
            if (o is PropertyData pd)
            {
                var copy = Activator.CreateInstance(pd.GetType());
                CopyFields(pd, copy);
                return copy;
            }
            if (o is string) return o;
            if (o is Array arr)
            {
                if (o is byte[]) return o;
                var el = t.GetElementType();
                var dstArr = Array.CreateInstance(el, arr.Length);
                for (int i = 0; i < arr.Length; i++) dstArr.SetValue(Deep(arr.GetValue(i)), i);
                return dstArr;
            }
            if (o is System.Collections.IList src)
            {
                var dst = (System.Collections.IList)Activator.CreateInstance(t);
                foreach (var item in src) dst.Add(Deep(item));
                return dst;
            }
            return o;
        }

        void CopyFields(object from, object to)
        {
            for (var t = from.GetType(); t != null && t != typeof(object); t = t.BaseType)
                foreach (var f in t.GetFields(System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.DeclaredOnly))
                {
                    if (f.IsInitOnly) continue;
                    f.SetValue(to, Deep(f.GetValue(from), f.Name));
                }
        }
    }


    // ---------------------------------------------------------------- fix road bounds
    static PropertyData ChildNamed(PropertyData container, string name)
    {
        if (container is StructPropertyData sp)
            foreach (var c in sp.Value) if ((c.Name?.Value?.Value ?? "") == name) return c;
        if (container is ArrayPropertyData ap)
            foreach (var c in ap.Value) if ((c.Name?.Value?.Value ?? "") == name) return c;
        return null;
    }

    static void SetNum(PropertyData p, double v)
    {
        switch (p)
        {
            case FloatPropertyData f: f.Value = (float)v; break;
            case DoublePropertyData d: d.Value = v; break;
            case IntPropertyData i: i.Value = (int)Math.Round(v); break;
        }
    }

    static double GetNum(PropertyData p) => p switch
    {
        FloatPropertyData f => f.Value,
        DoublePropertyData d => d.Value,
        _ => 0.0
    };

    // FBox lives as Min/Max/IsValid; the engine trusts it for spatial queries, so a box inherited
    // from a template road (different map, different coordinates) is a crash risk as soon as the
    // road sits inside the play area.
    static void SetBox(PropertyData boxProp, double minX, double minY, double minZ, double maxX, double maxY, double maxZ)
    {
        if (!(boxProp is StructPropertyData box)) return;
        var inner = (box.Value.Count == 1 && box.Value[0] is StructPropertyData ib && ib.Value.Count > 0) ? ib : box;
        void SetVec(string n, double x, double y, double z)
        {
            if (!(ChildNamed(inner, n) is StructPropertyData vec)) return;
            var xs = ChildNamed(vec, "X"); var ys = ChildNamed(vec, "Y"); var zs = ChildNamed(vec, "Z");
            if (xs != null) SetNum(xs, x);
            if (ys != null) SetNum(ys, y);
            if (zs != null) SetNum(zs, z);
        }
        SetVec("Min", minX, minY, minZ);
        SetVec("Max", maxX, maxY, maxZ);
        if (ChildNamed(inner, "IsValid") is BoolPropertyData val) val.Value = true;
    }

    static void FixRoadBounds(string inPath, string outPath)
    {
        var asset = new UAsset(inPath, EngineVersion.VER_UE5_5, Mappings);
        int fixedActors = 0, loopsChanged = 0, reparamFixed = 0;
        foreach (var ex in asset.Exports.OfType<NormalExport>())
        {
            string cls = ex.ClassIndex.IsImport() ? asset.Imports[-ex.ClassIndex.Index - 1].ObjectName?.Value?.Value ?? "" : "";
            if (cls != "MotorTownRoad") continue;
            string aname = ex.ObjectName?.Value?.Value ?? "";

            var splineProp = ex.Data.FirstOrDefault(d => (d.Name?.Value?.Value ?? "") == "Spline") as ObjectPropertyData;
            int compIdx = splineProp?.Value.Index ?? 0;
            if (compIdx <= 0) { Console.WriteLine($"BOUNDS_SKIP {aname}: no spline"); continue; }
            if (!(asset.Exports[compIdx - 1] is NormalExport comp)) continue;

            var curves = comp.Data.FirstOrDefault(d => (d.Name?.Value?.Value ?? "") == "SplineCurves") as StructPropertyData;
            var pos = curves == null ? null : ChildNamed(curves, "Position") as StructPropertyData;
            var pts = pos == null ? null : ChildNamed(pos, "Points") as ArrayPropertyData;
            if (pts == null || pts.Value.Length == 0) { Console.WriteLine($"BOUNDS_SKIP {aname}: no points"); continue; }

            double minX = double.MaxValue, minY = double.MaxValue, minZ = double.MaxValue;
            double maxX = double.MinValue, maxY = double.MinValue, maxZ = double.MinValue;
            double fX = 0, fY = 0, fZ = 0, lX = 0, lY = 0, lZ = 0;
            int used = 0;
            for (int i = 0; i < pts.Value.Length; i++)
            {
                if (!(pts.Value[i] is StructPropertyData pt)) continue;
                if (!(ChildNamed(pt, "OutVal") is StructPropertyData ov)) continue;
                double x = GetNum(ChildNamed(ov, "X")), y = GetNum(ChildNamed(ov, "Y")), z = GetNum(ChildNamed(ov, "Z"));
                if (used == 0) { fX = x; fY = y; fZ = z; }
                lX = x; lY = y; lZ = z; used++;
                minX = Math.Min(minX, x); minY = Math.Min(minY, y); minZ = Math.Min(minZ, z);
                maxX = Math.Max(maxX, x); maxY = Math.Max(maxY, y); maxZ = Math.Max(maxZ, z);
            }
            if (used == 0) { Console.WriteLine($"BOUNDS_SKIP {aname}: no usable points"); continue; }

            const double MARGIN = 200.0;
            var bprop = ex.Data.FirstOrDefault(d => (d.Name?.Value?.Value ?? "") == "SplineBounds");
            if (bprop != null) SetBox(bprop, minX - MARGIN, minY - MARGIN, minZ - MARGIN, maxX + MARGIN, maxY + MARGIN, maxZ + MARGIN);

            // ReparamTable maps arc-length -> curve index. The engine's curve evaluation does a
            // binary search over it assuming InVal = point index and OutVal in [0,1]; filling it
            // with raw indices drives that search out of the array.
            var rep = ChildNamed(curves, "ReparamTable") as StructPropertyData;
            var repPts = rep == null ? null : ChildNamed(rep, "Points") as ArrayPropertyData;
            if (repPts != null && repPts.Value.Length == used)
            {
                var cum = new double[used];
                double total = 0.0;
                double px = 0, py = 0, pz = 0; bool havePrev = false;
                int k = 0;
                for (int i = 0; i < pts.Value.Length && k < used; i++)
                {
                    if (!(pts.Value[i] is StructPropertyData pt2)) continue;
                    if (!(ChildNamed(pt2, "OutVal") is StructPropertyData ov2)) continue;
                    double x = GetNum(ChildNamed(ov2, "X")), y = GetNum(ChildNamed(ov2, "Y")), z = GetNum(ChildNamed(ov2, "Z"));
                    if (havePrev) total += Math.Sqrt((x - px) * (x - px) + (y - py) * (y - py) + (z - pz) * (z - pz));
                    cum[k] = total; px = x; py = y; pz = z; havePrev = true; k++;
                }
                for (int i = 0; i < used; i++)
                {
                    if (!(repPts.Value[i] is StructPropertyData rp)) continue;
                    double norm = total > 0.0 ? cum[i] / total : 0.0;
                    if (ChildNamed(rp, "InVal") is PropertyData iv) SetNum(iv, i);
                    if (ChildNamed(rp, "OutVal") is PropertyData ovv) SetNum(ovv, norm);
                }
                reparamFixed++;
                if (fixedActors < 2) Console.WriteLine($"REPARAM {aname}: n={used} last={cum[used - 1]:F1}");
            }

            double dx = fX - lX, dy = fY - lY, dz = fZ - lZ;
            bool closed = dx * dx + dy * dy + dz * dz < 100.0 * 100.0;
            if (comp.Data.FirstOrDefault(d => (d.Name?.Value?.Value ?? "") == "bClosedLoop") is BoolPropertyData bl && bl.Value != closed)
            { bl.Value = closed; loopsChanged++; }

            fixedActors++;
        }
        asset.Write(outPath);
        Console.WriteLine($"FIXBOUNDS actors={fixedActors} closedloop_changed={loopsChanged} reparam={reparamFixed} -> {outPath}");
    }


    static void DumpDeps(string path, string filter)
    {
        var asset = new UAsset(path, EngineVersion.VER_UE5_5, Mappings);
        string NameOf(FPackageIndex pi)
        {
            if (pi == null) return "null";
            if (pi.Index == 0) return "0";
            if (pi.Index < 0)
            {
                int j = -pi.Index - 1;
                return j < asset.Imports.Count ? "imp:" + (asset.Imports[j].ObjectName?.Value?.Value ?? "?") : "imp?" + pi.Index;
            }
            int e = pi.Index - 1;
            return e < asset.Exports.Count ? "exp:" + (asset.Exports[e].ObjectName?.Value?.Value ?? "?") + "#" + pi.Index : "exp?" + pi.Index;
        }
        Console.WriteLine($"DEPS file={System.IO.Path.GetFileName(path)} exports={asset.Exports.Count} imports={asset.Imports.Count}");
        for (int ei = 0; ei < asset.Exports.Count; ei++)
        {
            var e = asset.Exports[ei];
            string nm = e.ObjectName?.Value?.Value ?? "";
            if (!string.IsNullOrEmpty(filter) || true) { }
            if (!string.IsNullOrEmpty(filter) && !nm.Contains(filter)) continue;
            var dm = asset.DependsMap != null && ei < asset.DependsMap.Count ? asset.DependsMap[ei] : null;
            Console.WriteLine($"  DEPENDS[{ei + 1}] {nm} n={dm?.Length ?? -1} [{string.Join(",", (dm ?? new int[0]).Take(12))}]");
            var e2 = e;
            Console.WriteLine($"  [{ei + 1}] {e2.GetType().Name} {nm} class={(e2.ClassIndex.IsImport() ? asset.Imports[-e2.ClassIndex.Index - 1].ObjectName?.Value?.Value : "?")} outer={NameOf(e2.OuterIndex)} tpl={NameOf(e2.TemplateIndex)} flags={e2.ObjectFlags}");
            Console.WriteLine($"    SSS=[{string.Join(",", e2.SerializationBeforeSerializationDependencies.Select(NameOf))}]");
            Console.WriteLine($"    CBS=[{string.Join(",", e2.CreateBeforeSerializationDependencies.Select(NameOf))}]");
            Console.WriteLine($"    SBC=[{string.Join(",", e2.SerializationBeforeCreateDependencies.Select(NameOf))}]");
            Console.WriteLine($"    CBC=[{string.Join(",", e2.CreateBeforeCreateDependencies.Select(NameOf))}]");
        }
    }


    static string ClassNameOfExport(UAsset a, Export e)
        => e.ClassIndex != null && e.ClassIndex.IsImport() ? a.Imports[-e.ClassIndex.Index - 1].ObjectName?.Value?.Value ?? "" : "";
    static string ClassPkgOfExport(UAsset a, Export e)
        => e.ClassIndex != null && e.ClassIndex.IsImport() ? a.Imports[-e.ClassIndex.Index - 1].ClassPackage?.Value?.Value ?? "" : "";

    static int EnsurePackageImport(UAsset a, string pkg)
    {
        for (int j = 0; j < a.Imports.Count; j++)
            if ((a.Imports[j].ObjectName?.Value?.Value ?? "") == pkg && (a.Imports[j].ClassName?.Value?.Value ?? "") == "Package")
                return j;
        a.Imports.Add(new Import("/Script/CoreUObject", "Package", new FPackageIndex(0), pkg, false, a));
        return a.Imports.Count - 1;
    }

    static int EnsureCdo(UAsset a, string cls, string clsPkg)
    {
        for (int j = 0; j < a.Imports.Count; j++)
            if ((a.Imports[j].ObjectName?.Value?.Value ?? "") == "Default__" + cls)
                return j;
        int pkg = EnsurePackageImport(a, clsPkg);
        a.Imports.Add(new Import(clsPkg, cls, FPackageIndex.FromImport(pkg), "Default__" + cls, false, a));
        return a.Imports.Count - 1;
    }

    static int EnsureSubobject(UAsset a, string sub, string cls, string clsPkg, int cdo)
    {
        for (int j = 0; j < a.Imports.Count; j++)
        {
            var bi = a.Imports[j];
            if ((bi.ObjectName?.Value?.Value ?? "") != sub) continue;
            if ((bi.ClassName?.Value?.Value ?? "") != cls) continue;
            if ((bi.OuterIndex?.Index ?? 0) != -(cdo + 1)) continue;
            return j;
        }
        a.Imports.Add(new Import(clsPkg, cls, FPackageIndex.FromImport(cdo), sub, false, a));
        return a.Imports.Count - 1;
    }

    // Give actors the shape a cook gives them: archetype import, component edges, owner edges and
    // object flags. Without these the async loader can hold a reference to the actor but never
    // instantiate it -> "Missing Dependency ... still waiting for creation".
    static int FindActorCountOffset(byte[] raw, int expected, int maxIdx, int minIdx)
        {
            for (int off = 0; off + 4 <= raw.Length; off += 4)
            {
                int c = BitConverter.ToInt32(raw, off);
                if (c != expected) continue;
                int p = off + 4;
                if ((long)p + (long)c * 4 + 4 > raw.Length) continue;

                bool ok = true;
                for (int k = 0; k < c; k++)
                {
                    int v = BitConverter.ToInt32(raw, p + k * 4);
                    if (v < minIdx || v > maxIdx) { ok = false; break; }
                }
                if (!ok) continue;

                // tail shape: FURL (int32 len + chars) then Model index then ModelComponents count
                p += c * 4;
                int urlLen = BitConverter.ToInt32(raw, p);
                if (urlLen < 0 || urlLen > 1024 || (long)p + 4 + urlLen + 8 > raw.Length) continue;
                p += 4 + urlLen;
                int model = BitConverter.ToInt32(raw, p); p += 4;
                int ncomp = BitConverter.ToInt32(raw, p); p += 4;
                if (model < minIdx || model > maxIdx) continue;
                if (ncomp < 0 || (long)p + (long)ncomp * 4 + 12 > raw.Length) continue;
                return off;
            }
            return -1;
        }

    // Splice new actor indices into the level's original native data block. Keeps every byte the cook
    // wrote (including the tail LevelExport.Write drops) and only bumps the count + appends indices.
    // Preserved blobs carry the donor's FName indices. Rebuild them against the merged name map by
    // matching name TEXT (donor index -> same name's index in this package) and rewriting each
    // (index, number) pair whose number is 0. Anything left unremapped makes the engine resolve a
    // wrong name and desync ("Serial size mismatch").
    static int RemapAllNameRefs(byte[] blob, UAsset don, UAsset bas, string tag)
    {
        if (blob == null || don == null || bas == null) return 0;
        var pairs = new Dictionary<int, int>();
        var donNames = don.GetNameMapIndexList();
        for (int i = 0; i < donNames.Count; i++)
        {
            var nm = donNames[i];
            if (nm == null || nm.Value == null) continue;
            int j = bas.AddNameReference(new FString(nm.Value));
            if (j != i) pairs[i] = j;
        }
        if (pairs.Count == 0) return 0;
        int patched = 0;
        // FName pairs are NOT 4-byte aligned to the blob start (a 6-byte unversioned header puts the
        // first one at offset 6), so step one byte and require an exact (index, 0) pair.
        for (int p = 0; p + 8 <= blob.Length; p += 1)
        {
            int idx = BitConverter.ToInt32(blob, p);
            if (idx < 0 || BitConverter.ToInt32(blob, p + 4) != 0) continue;
            if (!pairs.TryGetValue(idx, out int nidx)) continue;
            Array.Copy(BitConverter.GetBytes(nidx), 0, blob, p, 4);
            patched++;
        }
        if (patched > 0) Console.WriteLine($"NAME_REMAP {tag} patched={patched}");
        return patched;
    }

    // Collect the FName values a parsed property tree holds, in document order.
    static void CollectFNames(IEnumerable<PropertyData> props, List<FName> outl)
    {
        if (props == null) return;
        foreach (var p in props)
        {
            if (p == null) continue;
            if (p is NamePropertyData np) { if (np.Value != null) outl.Add(np.Value); }
            else if (p is StructPropertyData sp) CollectFNames(sp.Value, outl);
            else if (p is ArrayPropertyData ap) CollectFNames(ap.Value, outl);
            else if (p is MapPropertyData mp && mp.Value != null)
                foreach (var kv in mp.Value) { CollectFNames(new[] { kv.Key }, outl); CollectFNames(new[] { kv.Value }, outl); }
        }
    }

    // A preserved blob still carries the DONOR's name indices. In the merged package the name map is
    // different, so index 57 means "C1Shuto" in the donor and "BlueprintGeneratedClass" after merging
    // -> the engine reads a nonsense name and desyncs ("Serial size mismatch: Got 309, Expected 91").
    // Rewrite each donor FName in document order with its remapped index.
    static void RemapNameIndicesInBlob(byte[] blob, List<FName> donor, List<FName> mapped, string tag)
    {
        if (blob == null || donor == null || mapped == null) return;
        int pos = 0, patched = 0, wanted = 0;
        for (int k = 0; k < donor.Count && k < mapped.Count; k++)
        {
            int oldIdx = donor[k].Index, num = donor[k].Number;
            int newIdx = mapped[k].Index;
            if (oldIdx < 0 || newIdx < 0) continue;
            if (oldIdx == newIdx && num == mapped[k].Number) continue;
            wanted++;
            for (int i = pos; i + 8 <= blob.Length; i += 4)
            {
                if (BitConverter.ToInt32(blob, i) == oldIdx && BitConverter.ToInt32(blob, i + 4) == num)
                {
                    Array.Copy(BitConverter.GetBytes(newIdx), 0, blob, i, 4);
                    pos = i + 8;
                    patched++;
                    break;
                }
            }
        }
        if (wanted > 0)
            Console.WriteLine($"NAME_REMAP {tag} wanted={wanted} patched={patched}");
    }

    // Locate the level's native actor block: int32 count followed by `count` package indices, then an
    // FURL (length-prefixed string). ScriptSerializationEndOffset is NOT reliable across cook versions,
    // so find the block by shape and validate every value before touching it.
        // Splice new actor indices into the level's original native data block. Keeps every byte the cook
    // wrote (including the tail LevelExport.Write drops) and only bumps the count + appends indices.
    static void PatchLevelActorBlock(UAssetAPI.ExportTypes.LevelExport lvl, List<int> newIdx)
    {
        if (newIdx.Count == 0) return;
        var raw = lvl.OriginalData;
        if (raw == null) { Console.WriteLine("LEVEL_PATCH_FAIL no original bytes"); lvl.DataDirty = true; return; }
        int expected = (lvl.Actors?.Count ?? 0) - newIdx.Count;   // count as the cook wrote it
        int off = FindActorCountOffset(raw, expected, maxIdx: lvl.Actors != null ? Math.Max(expected, lvl.Actors.Count) + 4096 : 0, minIdx: -65536);
        if (off < 0)
        {
            Console.WriteLine($"LEVEL_PATCH_FAIL no actor block with count={expected} in {raw.Length} bytes (tagged_end={lvl.ScriptSerializationEndOffset})");
            lvl.DataDirty = true;
            return;
        }
        int arrayStart = off + 4;
        int arrayBytes = expected * 4;
        var outB = new List<byte>(raw.Length + newIdx.Count * 4);
        outB.AddRange(raw.Take(arrayStart + arrayBytes));
        foreach (var v in newIdx) outB.AddRange(BitConverter.GetBytes(v));
        outB.AddRange(raw.Skip(arrayStart + arrayBytes));
        var arr = outB.ToArray();
        Array.Copy(BitConverter.GetBytes(expected + newIdx.Count), 0, arr, off, 4);
        lvl.OriginalData = arr;
        lvl.DataDirty = false;   // write the patched original bytes, never a re-serialisation
        Console.WriteLine($"LEVEL_PATCH_OK actors {expected} -> {expected + newIdx.Count} at_off={off} bytes {raw.Length} -> {arr.Length}");
    }

    static void VerifySizes(string inPath, string filter)
    {
        var a = new UAsset(inPath, EngineVersion.VER_UE5_5, Mappings);
        int bad = 0, ok = 0, threw = 0;
        foreach (var ex in a.Exports)
        {
            string nm = ex.ObjectName?.Value?.Value ?? "";
            string cls = ex is NormalExport ne ? ClassNameOfExport(a, ne) : (ex is RawExport ? "RawExport" : ex.GetType().Name);
            // Preserved exports are written back byte-for-byte, so their declared size is correct by
            // construction; re-serialising them here would measure our writer, not the shipped data.
            if (ex.OriginalData != null && !ex.DataDirty) { ok++; continue; }
            long actual;
            try
            {
                if (ex is RawExport rex)
                {
                    actual = rex.Data == null ? 0 : rex.Data.Length;
                }
                else
                {
                    using var ms = new MemoryStream();
                    var w = new AssetBinaryWriter(ms, a);
                    ex.Write(w);
                    w.Flush();
                    actual = ms.Length;
                }
            }
            catch (Exception e)
            {
                threw++;
                Console.WriteLine($"SIZECHECK_THROW {cls} {nm} {e.GetType().Name}: {e.Message}");
                continue;
            }
            if (actual == ex.SerialSize) { ok++; continue; }
            bad++;
            if (filter.Length == 0 || cls.Contains(filter) || nm.Contains(filter))
                Console.WriteLine($"SIZEMISMATCH {cls} {nm} declared={ex.SerialSize} actual={actual} delta={actual - ex.SerialSize}");
        }
        int dep = a.DependsMap?.Count ?? -1;
        string depFlag = (dep == a.Exports.Count) ? "aligns" : "MISALIGNED";
        Console.WriteLine($"SIZES_OK checked={a.Exports.Count} match={ok} mismatched={bad} threw={threw} " +
                          $"imports={a.Imports.Count} dependsMap={dep} ({depFlag}) names={a.GetNameMapIndexList().Count} -> {inPath}");
    }

    static void NormalizeActors(string inPath, string outPath)
    {
        UAsset.CaptureOriginalExportData = true;
        var a = new UAsset(inPath, EngineVersion.VER_UE5_5, Mappings);
        var lvl = a.Exports.OfType<LevelExport>().FirstOrDefault();
        if (lvl == null) { Console.WriteLine("NORMALIZE_FAIL no level"); return; }
        int lvlIdx1 = a.Exports.IndexOf(lvl) + 1;
        int acts = 0, comps = 0;
        foreach (var ar in lvl.Actors)
        {
            if (ar == null || ar.Index <= 0 || ar.Index > a.Exports.Count) continue;
            if (!(a.Exports[ar.Index - 1] is NormalExport na)) continue;
            string cls = ClassNameOfExport(a, na); string clsPkg = ClassPkgOfExport(a, na);
            if (cls.Length == 0) continue;
            string nm = na.ObjectName?.Value?.Value ?? "";
            int cdo = EnsureCdo(a, cls, clsPkg);
            if (na.TemplateIndex == null || na.TemplateIndex.Index == 0) na.TemplateIndex = FPackageIndex.FromImport(cdo);

            var childIdx = new List<int>();
            for (int ci = 0; ci < a.Exports.Count; ci++)
                if (a.Exports[ci] is NormalExport ce && ce.OuterIndex != null && ce.OuterIndex.Index == ar.Index) childIdx.Add(ci);

            na.CreateBeforeSerializationDependencies = new List<FPackageIndex>();
            foreach (var ci in childIdx) na.CreateBeforeSerializationDependencies.Add(new FPackageIndex(ci + 1));
            na.CreateBeforeCreateDependencies = new List<FPackageIndex> { new FPackageIndex(lvlIdx1) };
            na.SerializationBeforeCreateDependencies = new List<FPackageIndex>();
            if (na.ClassIndex.IsImport()) na.SerializationBeforeCreateDependencies.Add(na.ClassIndex);
            na.SerializationBeforeCreateDependencies.Add(FPackageIndex.FromImport(cdo));

            foreach (var ci in childIdx)
            {
                if (!(a.Exports[ci] is NormalExport ce2)) continue;
                string cn2 = ce2.ObjectName?.Value?.Value ?? "";
                string sub = cn2.StartsWith(nm + "_") ? cn2.Substring(nm.Length + 1) : cn2;
                string ccls = ClassNameOfExport(a, ce2); string cpkg2 = ClassPkgOfExport(a, ce2);
                if (ccls.Length == 0) continue;
                int arch = EnsureSubobject(a, sub, ccls, cpkg2, cdo);
                ce2.TemplateIndex = FPackageIndex.FromImport(arch);
                ce2.ObjectFlags |= EObjectFlags.RF_DefaultSubObject;
                ce2.CreateBeforeCreateDependencies = new List<FPackageIndex> { new FPackageIndex(ar.Index) };
                ce2.CreateBeforeSerializationDependencies = new List<FPackageIndex>();
                ce2.SerializationBeforeCreateDependencies = new List<FPackageIndex>();
                if (ce2.ClassIndex.IsImport()) ce2.SerializationBeforeCreateDependencies.Add(ce2.ClassIndex);
                ce2.SerializationBeforeCreateDependencies.Add(FPackageIndex.FromImport(arch));
                if (!na.SerializationBeforeCreateDependencies.Any(x => ce2.ClassIndex != null && x.Index == ce2.ClassIndex.Index))
                    if (ce2.ClassIndex.IsImport()) na.SerializationBeforeCreateDependencies.Add(ce2.ClassIndex);
                comps++;
            }
            na.ObjectFlags |= EObjectFlags.RF_Transactional;
            acts++;
        }
        a.Write(outPath);
        Console.WriteLine($"NORMALIZE_OK actors={acts} components={comps} imports={a.Imports.Count} -> {outPath}");
    }

    static void MergeActors(string basePath, string donorPath, string outPath, string classesCsv, string skipCsv, string onlyNames = "")
    {
        // Preserve untouched exports byte-for-byte: re-serialising them through UAssetAPI does not
        // reproduce cook bytes and the game rejects the result ("Serial size mismatch").
        UAsset.CaptureOriginalExportData = true;
        var bas = new UAsset(basePath, EngineVersion.VER_UE5_5, Mappings);
        var don = new UAsset(donorPath, EngineVersion.VER_UE5_5, Mappings);
        var keep = new HashSet<string>((classesCsv ?? "").Split(',', StringSplitOptions.RemoveEmptyEntries).Select(s => s.Trim()));
        var skip = new HashSet<string>((skipCsv ?? "").Split(',', StringSplitOptions.RemoveEmptyEntries).Select(s => s.Trim()));

        int FindExport(UAsset a, string name)
        {
            for (int i = 0; i < a.Exports.Count; i++)
                if ((a.Exports[i].ObjectName?.Value?.Value ?? "") == name) return i;
            return -1;
        }

        var ctx = new MergeCtx { Base = bas, Donor = don };
        ctx.DonorLevel = FindExport(don, "PersistentLevel");
        ctx.BaseLevel = FindExport(bas, "PersistentLevel");
        ctx.DonorWorld = -1;
        ctx.BaseWorld = FindExport(bas, "C1");
        if (ctx.BaseWorld < 0)
            for (int i = 0; i < bas.Exports.Count; i++) if (ClassNameOf(bas, bas.Exports[i]) == "World") { ctx.BaseWorld = i; break; }
        for (int i = 0; i < don.Exports.Count; i++) if (ClassNameOf(don, don.Exports[i]) == "World") { ctx.DonorWorld = i; break; }

        // selection: classes to keep, plus everything whose outer chain reaches them
        var pick = new HashSet<int>();
        for (int i = 0; i < don.Exports.Count; i++)
        {
            var cls = ClassNameOf(don, don.Exports[i]);
            if (cls == "World" || cls == "WorldSettings" || cls == "Model" || cls == "Level" || cls == "LevelStreamingAlwaysLoaded") continue;
            if (skip.Contains(cls)) continue;
            // Name filter is for ROAD actors only: it lets a build carry just the course road
            // (NS's own shape is 2 road actors for a whole lap), while gates/nav still come along.
            if (onlyNames.Length > 0 && cls == "MotorTownRoad")
            {
                // FName splits "MotorTownRoad_2" into base "MotorTownRoad" + number 2, so compare
                // the DISPLAY form or the name filter silently matches nothing (the same FName
                // number trap that mis-named the road ids earlier).
                var onBase = don.Exports[i].ObjectName?.Value?.Value ?? "";
                int onNum = don.Exports[i].ObjectName?.Number ?? 0;
                string on = onNum > 0 ? onBase + "_" + onNum : onBase;
                // "@course" = the road carrying a CourseKey (the race-course road). Matching by
                // property is robust where names are ambiguous (FName numbers shift on rewrite).
                bool isCourse = onlyNames.Trim() == "@course" &&
                    (don.Exports[i] as NormalExport)?.Data.Any(d => (d.Name?.Value?.Value ?? "") == "CourseKey") == true;
                if (!isCourse && !onlyNames.Split(',').Any(n => n.Trim() == on)) continue;
            }
            if (onlyNames.Length > 0 && cls == "MotorTownRoad" && keep.Contains(cls))
            {
                var dbgName = don.Exports[i].ObjectName;
            }
            if (keep.Contains(cls)) pick.Add(i);
        }
        bool grew = true;
        while (grew)
        {
            grew = false;
            for (int i = 0; i < don.Exports.Count; i++)
            {
                if (pick.Contains(i)) continue;
                int o = don.Exports[i].OuterIndex?.Index ?? 0;
                if (o > 0 && pick.Contains(o - 1)) { pick.Add(i); grew = true; }
            }
        }

        // donor actor list, so registration is copied rather than guessed
        var donorActors = new HashSet<int>();
        if (ctx.DonorLevel >= 0 && don.Exports[ctx.DonorLevel] is UAssetAPI.ExportTypes.LevelExport dl && dl.Actors != null)
            foreach (var a in dl.Actors) if ((a?.Index ?? 0) > 0) donorActors.Add(a.Index - 1);

        int baseExportCount = bas.Exports.Count;
        int next = bas.Exports.Count;
        foreach (var i in pick.OrderBy(x => x)) ctx.ExportMap[i] = next++;

        var built = new List<Export>();
        foreach (var i in pick.OrderBy(x => x))
        {
            if (!(don.Exports[i] is NormalExport src)) { Console.WriteLine($"MERGE_SKIP non-normal export {i}"); continue; }
            var nd = new NormalExport(new List<PropertyData>(), bas, Array.Empty<byte>())
            {
                ObjectName = ctx.Name(src.ObjectName, false),
                ClassIndex = ctx.MapIndex(src.ClassIndex),
                OuterIndex = ctx.MapIndex(src.OuterIndex),
                SuperIndex = ctx.MapIndex(src.SuperIndex),
                TemplateIndex = ctx.MapIndex(src.TemplateIndex),
                ObjectFlags = src.ObjectFlags,
                IsInheritedInstance = src.IsInheritedInstance,
                bNotAlwaysLoadedForEditorGame = src.bNotAlwaysLoadedForEditorGame,
                ObjectGuid = src.ObjectGuid
            };
            nd.Data = (List<PropertyData>)ctx.Deep(src.Data);
            // Carry the donor's raw bytes. Race sections / roads / navigation use NATIVE binary
            // serialisation (their cooked data is not a tagged-property stream), so re-serialising
            // the parsed "--dump" view produces a tagged blob the game cannot parse
            // ("Serial size mismatch: Got 189, Expected 149"). Writing the original bytes keeps the
            // export exactly as the cook produced it.
            nd.OriginalData = src.OriginalData == null ? null : (byte[])src.OriginalData.Clone();
            nd.DataDirty = src.DataDirty;
            // NOTE: text-based name remapping is UNSAFE on opaque blobs - an int32 that happens to
            // equal a donor name index (e.g. an ObjectProperty's package index 41) gets rewritten and
            // silently breaks references. Disabled until a schema-driven rewrite exists.
            if (nd.OriginalData != null)
            {
                var donorNames = new List<FName>();
                CollectFNames(src.Data, donorNames);
                if (donorNames.Count > 0)
                {
                    var mappedNames = donorNames.Select(f => ctx.Name(f, false)).ToList();
                    RemapNameIndicesInBlob(nd.OriginalData, donorNames, mappedNames, src.ObjectName?.Value?.Value ?? "?");
                }
            }
            // Cooked exports carry preload dependency lists that tell the engine what must be
            // loaded/created before this object. Empty lists on a transplanted actor mean the
            // engine instantiates it before its class/archetype exists.
            nd.bForcedExport = src.bForcedExport;
            nd.bNotForClient = src.bNotForClient;
            nd.bNotForServer = src.bNotForServer;
            nd.bIsAsset = src.bIsAsset;
            nd.GeneratePublicHash = src.GeneratePublicHash;
            // Copy the donor's arcs (remapped), then guarantee an arc to the CLASS and TEMPLATE
            // imports on the serialization-before-create list. Without the template arc the loader
            // cannot instantiate the actor (it still needs its archetype), so an export that
            // something requests stays "waiting for creation" forever and the async loader fatals
            // with "Missing Dependency ... still waiting for creation".
            nd.SerializationBeforeSerializationDependencies = ctx.MapList(src.SerializationBeforeSerializationDependencies);
            nd.CreateBeforeSerializationDependencies = ctx.MapList(src.CreateBeforeSerializationDependencies);
            nd.SerializationBeforeCreateDependencies = ctx.MapList(src.SerializationBeforeCreateDependencies);
            nd.CreateBeforeCreateDependencies = ctx.MapList(src.CreateBeforeCreateDependencies);
            void Arc(FPackageIndex pi)
            {
                if (pi == null || pi.Index == 0 || !pi.IsImport()) return;
                var m = ctx.MapIndex(pi);
                if (m == null || m.Index == 0) return;
                if (!nd.SerializationBeforeCreateDependencies.Any(x => x.Index == m.Index))
                    nd.SerializationBeforeCreateDependencies.Add(m);
            }
            Arc(src.ClassIndex);
            Arc(src.TemplateIndex);
            built.Add(nd);
        }
        foreach (var e in built) bas.Exports.Add(e);

        int registered = 0;
        var regByClass = new Dictionary<string, int>();
        var pickByClass = new Dictionary<string, int>();
        foreach (var i in pick) { var c = ClassNameOf(don, don.Exports[i]); pickByClass[c] = pickByClass.TryGetValue(c, out var pc) ? pc + 1 : 1; }
        var levelEx = ctx.BaseLevel >= 0 ? bas.Exports[ctx.BaseLevel] as UAssetAPI.ExportTypes.LevelExport : null;
        var addedActorIndices = new List<int>();
        if (levelEx?.Actors != null)
        {
            foreach (var i in pick.OrderBy(x => x))
            {
                if (!donorActors.Contains(i)) continue;
                var newActorIdx = new FPackageIndex(ctx.ExportMap[i] + 1);
                levelEx.Actors.Add(newActorIdx);
                    levelEx.DataDirty = true;
                // The level lists every vanilla actor in CBS (create-before-serializing-level);
                // transplanted actors missing from that list leave the loader holding an actor
                // reference it was never told to create -> "still waiting for creation" fatal.
                addedActorIndices.Add(newActorIdx.Index);
                if (!levelEx.CreateBeforeSerializationDependencies.Any(x => x.Index == newActorIdx.Index))
                    levelEx.CreateBeforeSerializationDependencies.Add(newActorIdx);
                registered++;
                var rc = ClassNameOf(don, don.Exports[i]);
                regByClass[rc] = regByClass.TryGetValue(rc, out var rcv) ? rcv + 1 : 1;
            }
        }

        // The writer synthesises property TYPE names by looking them up in the name table; a
        // stripped cooked map (or a donor whose map never needed them) lacks them. Seed the
        // standard set up front instead of discovering them one exception at a time.
        foreach (var tn in new[] { "FloatProperty","DoubleProperty","IntProperty","Int8Property","Int16Property","Int64Property",
                                   "UInt16Property","UInt32Property","UInt64Property","ByteProperty","BoolProperty","NameProperty",
                                   "StrProperty","TextProperty","ObjectProperty","WeakObjectProperty","LazyObjectProperty",
                                   "ClassProperty","SoftObjectProperty","SoftClassProperty","InterfaceProperty","StructProperty",
                                   "ArrayProperty","MapProperty","SetProperty","DelegateProperty","MulticastDelegateProperty",
                                   "MulticastInlineDelegateProperty","FieldPathProperty","EnumProperty","OptionalProperty" })
        {
            var tf = FString.FromString(tn);
            if (!bas.ContainsNameReference(tf)) bas.AddNameReference(tf);
        }

        // The writer synthesises property type names ("FloatProperty", ...) by looking them up in
        // the name table and throws when absent; a stripped cooked map does not carry them all.
        foreach (var nm in don.GetNameMapIndexList())
        {
            var s = nm?.Value ?? "";
            if (!s.EndsWith("Property", StringComparison.Ordinal)) continue;
            if (!bas.ContainsNameReference(nm)) bas.AddNameReference(FString.FromString(s));
        }

        // ---- normalize transplanted actors the way a cook does ------------------
        // Cooked actor exports always carry: an archetype import (TemplateIndex), a CBS edge to
        // each of their component exports, a CBC edge to the level, and SBC edges to class,
        // archetype and component classes. Actors we manufactured had none of these, so the async
        // loader could reference them but never create them ("still waiting for creation").
        var levelExportForNorm = bas.Exports.OfType<LevelExport>().FirstOrDefault();
        int baseLevelIdx1 = levelExportForNorm != null ? bas.Exports.IndexOf(levelExportForNorm) + 1 : 0;
        int actorsFixed = 0;
        var regActors = new HashSet<int>();
        if (levelExportForNorm != null)
            foreach (var a in levelExportForNorm.Actors) if (a != null && a.Index > 0) regActors.Add(a.Index);
        for (int bi2 = 0; bi2 < bas.Exports.Count; bi2++)
        {
            if (!(bas.Exports[bi2] is NormalExport na)) continue;
            string aname2 = na.ObjectName?.Value?.Value ?? "";
            if (!regActors.Contains(bi2 + 1)) continue;
            bool transplanted = ctx.ExportMap.ContainsValue(bi2);
            if (!transplanted) continue;

            string cls = na.ClassIndex.IsImport() ? bas.Imports[-na.ClassIndex.Index - 1].ObjectName?.Value?.Value ?? "" : "";
            string cpkg = na.ClassIndex.IsImport() ? bas.Imports[-na.ClassIndex.Index - 1].ClassPackage?.Value?.Value ?? "" : "";
            if (cls.Length == 0) continue;

            // archetype
            int cdo = ctx.FindOrAddCdoImport(cls, cpkg.Replace("Default__", ""));
            if (na.TemplateIndex == null || na.TemplateIndex.Index == 0)
                na.TemplateIndex = FPackageIndex.FromImport(cdo);

            // component edges: children exports whose outer is this actor
            var comps = new List<int>();
            for (int ci = 0; ci < bas.Exports.Count; ci++)
                if (bas.Exports[ci] is NormalExport ce && ce.OuterIndex != null && ce.OuterIndex.Index == bi2 + 1) comps.Add(ci);

            na.CreateBeforeSerializationDependencies = new List<FPackageIndex>();
            foreach (var ci in comps) na.CreateBeforeSerializationDependencies.Add(new FPackageIndex(ci + 1));

            na.CreateBeforeCreateDependencies = new List<FPackageIndex>();
            if (baseLevelIdx1 > 0) na.CreateBeforeCreateDependencies.Add(new FPackageIndex(baseLevelIdx1));

            na.SerializationBeforeCreateDependencies = new List<FPackageIndex>();
            if (na.ClassIndex.IsImport()) na.SerializationBeforeCreateDependencies.Add(na.ClassIndex);
            na.SerializationBeforeCreateDependencies.Add(FPackageIndex.FromImport(cdo));
            foreach (var ci in comps)
                if (bas.Exports[ci] is NormalExport ce2 && ce2.ClassIndex.IsImport() &&
                    !na.SerializationBeforeCreateDependencies.Any(x => x.Index == ce2.ClassIndex.Index))
                    na.SerializationBeforeCreateDependencies.Add(ce2.ClassIndex);

            na.ObjectFlags = EObjectFlags.RF_Transactional;

            // Components are default subobjects: their archetype is the like-named subobject of
            // the class default object, they carry RF_DefaultSubObject, and they depend on their
            // actor. Without this a component is a free-floating object with no owner edge.
            foreach (var ci in comps)
            {
                if (!(bas.Exports[ci] is NormalExport ce3)) continue;
                string compName = ce3.ObjectName?.Value?.Value ?? "";
                string subName = compName.StartsWith(aname2 + "_") ? compName.Substring(aname2.Length + 1) : compName;
                string compCls = ce3.ClassIndex.IsImport() ? bas.Imports[-ce3.ClassIndex.Index - 1].ObjectName?.Value?.Value ?? "" : "";
                string compPkg = ce3.ClassIndex.IsImport() ? bas.Imports[-ce3.ClassIndex.Index - 1].ClassPackage?.Value?.Value ?? "" : "";
                if (compCls.Length == 0) continue;
                int arch = -1;
                for (int j = 0; j < bas.Imports.Count; j++)
                {
                    var bi3 = bas.Imports[j];
                    if ((bi3.ObjectName?.Value?.Value ?? "") != subName) continue;
                    if ((bi3.ClassName?.Value?.Value ?? "") != compCls) continue;
                    if ((bi3.OuterIndex?.Index ?? 0) != -(cdo + 1)) continue;
                    arch = j; break;
                }
                if (arch < 0)
                {
                    bas.Imports.Add(new Import(compPkg, compCls, FPackageIndex.FromImport(cdo), subName, false, bas));
                    arch = bas.Imports.Count - 1;
                }
                ce3.TemplateIndex = FPackageIndex.FromImport(arch);
                ce3.ObjectFlags |= EObjectFlags.RF_DefaultSubObject;
                ce3.CreateBeforeCreateDependencies = new List<FPackageIndex> { new FPackageIndex(bi2 + 1) };
                ce3.CreateBeforeSerializationDependencies = new List<FPackageIndex>();
                ce3.SerializationBeforeCreateDependencies = new List<FPackageIndex>();
                if (ce3.ClassIndex.IsImport()) ce3.SerializationBeforeCreateDependencies.Add(ce3.ClassIndex);
                ce3.SerializationBeforeCreateDependencies.Add(FPackageIndex.FromImport(arch));
            }
            actorsFixed++;
        }
        Console.WriteLine($"MERGE_NORMALIZED actors={actorsFixed}");

        // Cloned exports arrive by two paths (parsed NormalExport with preserved bytes, or a RawExport
        // whose Data is copied verbatim). Both still carry the DONOR's FName indices, so remap every
        // added export here, once, regardless of which path produced it.
        int remappedExports = 0;
        for (int i = baseExportCount; i < bas.Exports.Count; i++)
        {
            var ex = bas.Exports[i];
            if (ex == null) continue;
            string nm2 = ex.ObjectName?.Value?.Value ?? "?";
            if (ex.OriginalData == null && ex is RawExport rawChk) { /* no remap: see note above */ }
        }
        Console.WriteLine($"NAME_REMAP_TOTAL exports={remappedExports}");

        // The level's data is a NATIVE block (int32 NumActors + that many package indices, then URL /
        // Model / ModelComponents / script actor / nav list, and more that UAssetAPI's LevelExport.Write
        // does not implement — it stops at NavListEnd). Re-serialising truncates it, and the engine
        // reports "serialization error: corrupt data found". Patch the original bytes instead.
        if (levelEx != null) PatchLevelActorBlock(levelEx, addedActorIndices);

        bas.Write(outPath);
        Console.WriteLine($"MERGE_DONOR_ACTORS={donorActors.Count} PICK_BY_CLASS={string.Join(",", pickByClass.Select(kv => kv.Key + ":" + kv.Value))}");
        Console.WriteLine($"MERGE_REG_BY_CLASS={string.Join(",", regByClass.Select(kv => kv.Key + ":" + kv.Value))}");
        Console.WriteLine($"MERGE_ARCS sbc_total={bas.Exports.OfType<NormalExport>().Sum(e => e.SerializationBeforeCreateDependencies.Count)} exports_with_sbc={bas.Exports.OfType<NormalExport>().Count(e => e.SerializationBeforeCreateDependencies.Count > 0)}");
        Console.WriteLine($"MERGE_OK cloned={built.Count} registered={registered} imports={bas.Imports.Count} exports={bas.Exports.Count} dropped_refs={ctx.Dropped} -> {outPath}");
    }

    static void PropProbe(string path)
    {
        var asset = new UAsset(path, EngineVersion.VER_UE5_5, Mappings);
        Console.WriteLine($"Asset: {path}  imports={asset.Imports.Count} exports={asset.Exports.Count}");
        foreach (var exp in asset.Exports)
        {
            var ne = exp as NormalExport;
            Console.WriteLine($"Export {exp.ObjectName}: Class={exp.GetExportClassType()?.Value?.Value} C#Type={exp.GetType().Name} props={ne?.Data.Count ?? 0} serialSize={exp.SerialSize}");
            if (ne == null) continue;
            foreach (var p in ne.Data)
            {
                var tn = p.PropertyTypeName?.ToString() ?? "?";
                string val = p switch
                {
                    ObjectPropertyData o => $"-> import/export {o.Value.Index}",
                    SoftObjectPropertyData s => $"-> {s.Value.AssetPath.AssetName}",
                    ArrayPropertyData a => $"count={a.Value.Length}" + (a.Value.Length > 0 ? $" [{string.Join(",", a.Value.Take(4).Select(x => x.GetType().Name))}]" : ""),
                    NamePropertyData n => $"= '{n.Value}'",
                    IntPropertyData i => $"= {i.Value}",
                    BoolPropertyData b => $"= {b.Value}",
                    _ => ""
                };
                Console.WriteLine($"    {p.Name} : {tn} {val}");
            }
        }
    }

    // --make-composite
    // Turn a DataTable template into a CompositeDataTable at a new path:
    // clear inline rows (a composite resolves rows from ParentTables), point
    // RowStruct at the wanted struct, and set the ParentTables array.
    // Template must already be a CompositeDataTable (vanilla Cargos.uasset is).
    static void MakeComposite(string configPath, string templatePath, string outputDir)
    {
        if (!File.Exists(configPath)) { Console.WriteLine($"Error: Config not found: {configPath}"); return; }
        if (!File.Exists(templatePath)) { Console.WriteLine($"Error: Template not found: {templatePath}"); return; }

        var root = JsonDocument.Parse(File.ReadAllText(configPath)).RootElement;
        var newName = root.GetProperty("new_name").GetString()!;
        var newPath = root.GetProperty("new_path").GetString()!;

        var asset = new UAsset(templatePath, EngineVersion.VER_UE5_5, Mappings);
        asset.FolderName = FString.FromString(newPath);
        asset.PackageGuid = Guid.NewGuid();

        var mainExp = asset.Exports[0] as NormalExport;
        if (mainExp == null) { Console.WriteLine("Error: main export is not a NormalExport"); return; }

        var oldName = mainExp.ObjectName.Value.Value!;
        mainExp.ObjectName = FName.FromString(asset, newName);
        Console.WriteLine($"  Renamed export: {oldName} -> {newName}");

        // 1. Export class -> CompositeDataTable (keeps the template's own import
        // table, which the engine resolves child-row import indices against).
        var (_, compositeIdx) = AddImportChain(asset, "/Script/CoreUObject", "Class",
            "/Script/Engine", "CompositeDataTable", false);
        mainExp.ClassIndex = FPackageIndex.FromImport(compositeIdx - 1);
        Console.WriteLine($"  Export class -> CompositeDataTable (import {compositeIdx})");

        // 2. Clear inline rows — a composite resolves rows from ParentTables.
        bool clearRows = !root.TryGetProperty("keep_rows", out var kr) || !kr.GetBoolean();
        if (clearRows && mainExp is DataTableExport dte && dte.Table?.Data != null && dte.Table.Data.Count > 0)
        {
            Console.WriteLine($"  Clearing {dte.Table.Data.Count} inline rows (composite reads parents)");
            dte.Table.Data.Clear();
        }

        // 3. RowStruct (optional)
        if (root.TryGetProperty("row_struct", out var rs))
        {
            var (_, rsIdx) = AddImportChain(asset, "/Script/CoreUObject", "ScriptStruct",
                rs.GetProperty("package").GetString()!, rs.GetProperty("name").GetString()!, false);
            var rsProp = mainExp.Data.FirstOrDefault(p => p.Name?.Value?.Value == "RowStruct");
            if (rsProp is ObjectPropertyData rsObj)
            {
                rsObj.Value = FPackageIndex.FromImport(rsIdx - 1);
                Console.WriteLine($"  RowStruct -> {rs.GetProperty("name").GetString()}");
            }
            else Console.WriteLine("  WARNING: RowStruct property not found on main export");
        }

        // 4. ParentTables array — only build one if the template has none
        // (a hand-built array serializes wrong: missing type names / inner
        // FName, which the engine reads as garbage). Templates that already
        // carry ParentTables get it patched via clear_array/append_import_to_array.
        if (root.TryGetProperty("parents", out var parents))
        {
            var ptProp = mainExp.Data.FirstOrDefault(p => p.Name?.Value?.Value == "ParentTables");
            bool useExisting = ptProp is ArrayPropertyData
                && root.TryGetProperty("use_existing_array", out var uea) && uea.GetBoolean();
            if (useExisting)
            {
                Console.WriteLine("  ParentTables already present — leaving it to patches");
            }
            else
            {
                var arr = ptProp as ArrayPropertyData;
                if (arr == null)
                {
                    arr = new ArrayPropertyData(FName.FromString(asset, "ParentTables"));
                    arr.PropertyTypeName = MakeTypeName(asset, arr.PropertyType);
                    mainExp.Data.Add(arr);
                    Console.WriteLine("  Created ParentTables array");
                }
                var list = new List<PropertyData>();
                int n = 0;
                foreach (var p in parents.EnumerateArray())
                {
                    var (_, impIdx) = AddImportChain(asset, "/Script/Engine", "DataTable",
                        p.GetProperty("package_path").GetString()!, p.GetProperty("asset_name").GetString()!, false);
                    var opd = new ObjectPropertyData(FName.FromString(asset, n.ToString()))
                    {
                        Value = FPackageIndex.FromImport(impIdx - 1)
                    };
                    opd.PropertyTypeName = MakeTypeName(asset, opd.PropertyType);
                    list.Add(opd);
                    Console.WriteLine($"  ParentTables[{n}] -> {p.GetProperty("asset_name").GetString()}");
                    n++;
                }
                arr.Value = list.ToArray();
            }
        }

        if (root.TryGetProperty("patches", out var patches))
            ApplyPatches(mainExp.Data, patches, asset);

        var outDir = Path.Combine(outputDir, newName);
        Directory.CreateDirectory(outDir);
        var outPath = Path.Combine(outDir, $"{newName}.uasset");
        asset.Write(outPath);
        Console.WriteLine($"Written: {outPath} (+ .uexp)");
    }

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
                    // NOTE: match_class cannot match a Blueprint CDO whose
                    // ClassIndex is an EXPORT link (GetExportClassType returns a
                    // dummy index string) — use match_export (export ObjectName,
                    // applied AFTER rename) for CDO targets, e.g. "Default__X_C".
                    var meStr = exportPatch.TryGetProperty("match_export", out var meProp) ? meProp.GetString() : null;
                    var matchExport = meStr;
                    // match_occurrence: pick the Nth export matching match_class
                    // (cooked export names carry no _N suffix, so identical names
                    // can't be told apart otherwise)
                    int? matchOccurrence = exportPatch.TryGetProperty("match_occurrence", out var occProp) ? occProp.GetInt32() : null;
                    int occSeen = 0;
                    Console.WriteLine($"  [dbg] export_patch matchClass={matchClass} matchExport={matchExport}");

                    foreach (var export in asset.Exports)
                    {
                        if (export is NormalExport ne)
                        {
                            bool classMatch = matchClass == null || export.GetExportClassType()?.Value?.Value == matchClass;
                            bool nameMatch = matchExport == null || export.ObjectName.Value?.Value == matchExport;
                            bool occMatch = matchOccurrence == null || (classMatch && occSeen++ == matchOccurrence);
                            if (matchOccurrence != null && classMatch && occSeen - 1 < matchOccurrence) { /* counted above */ }
                            if (classMatch && nameMatch && occMatch && exportPatch.TryGetProperty("patches", out var patches))
                            {
                                ApplyPatches(ne.Data, patches, asset);
                            }
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
    // --set-class-ref: point an ObjectProperty at a class that lives in another
    // package (e.g. a ChildActorComponent's ChildActorClass -> /Game/Blueprints/
    // MTSunSky.MTSunSky_C). Adds the package + BlueprintGeneratedClass imports.
    // ========================================================================
    // --set-child-class-refs: same as --set-class-ref but for many child-actor
    // components at once -- every component named <componentName> whose owning
    // actor's object name starts with <ownerNamePrefix>. This is how NS places
    // garages: own prop actor + ChildActorClass pointing at the base game class.
    // ChildActor is forced to null so the child is constructed at runtime.
    // ========================================================================
    static void SetChildClassRefs(string inPath, string outPath, string ownerPrefix, string componentName, string packagePath, string className)
    {
        var asset = new UAsset(inPath, EngineVersion.VER_UE5_5, Mappings);
        var (pkgIdx, classIdx) = AddImportChain(asset, "/Script/Engine", "BlueprintGeneratedClass", packagePath, className);
        int hits = 0;
        foreach (var e in asset.Exports)
        {
            if (e is not NormalExport ne) continue;
            var nm = ne.ObjectName?.Value?.Value ?? "";
            if (!string.Equals(nm, componentName, StringComparison.OrdinalIgnoreCase)) continue;

            // owning actor: outer is a positive export index (1-based)
            var oi = ne.OuterIndex != null ? ne.OuterIndex.Index : 0;
            if (oi <= 0 || oi > asset.Exports.Count) continue;
            var owner = asset.Exports[oi - 1];
            var ownerName = owner?.ObjectName?.Value?.Value ?? "";
            if (!ownerName.StartsWith(ownerPrefix, StringComparison.OrdinalIgnoreCase)) continue;

            ObjectPropertyData? clsProp = null;
            ObjectPropertyData? childProp = null;
            foreach (var p in ne.Data)
            {
                if (p is not ObjectPropertyData op) continue;
                var pn = op.Name?.Value?.Value;
                if (string.Equals(pn, "ChildActorClass", StringComparison.OrdinalIgnoreCase)) clsProp = op;
                else if (string.Equals(pn, "ChildActor", StringComparison.OrdinalIgnoreCase)) childProp = op;
            }

            if (clsProp == null)
            {
                clsProp = new ObjectPropertyData(FName.FromString(asset, "ChildActorClass"))
                { Value = FPackageIndex.FromImport(classIdx - 1) };
                clsProp.PropertyTypeName = MakeTypeName(asset, clsProp.PropertyType);
                ne.Data.Add(clsProp);
            }
            else clsProp.Value = FPackageIndex.FromImport(classIdx - 1);

            if (childProp != null) childProp.Value = FPackageIndex.FromExport(0);
            hits++;
            Console.WriteLine($"  {ownerName}.{componentName} -> {className}");
        }

        asset.ResolveAncestries();
        asset.Write(outPath);
        Console.WriteLine($"SETCHILDCLASSREFS_{ (hits > 0 ? "OK" : "FAIL") } patched={hits} prefix={ownerPrefix} -> {outPath}");
    }

    // ========================================================================
    // ---- road geometry authoring -------------------------------------------------
    // Both modes only rewrite FLOAT VALUES inside existing structs, so every export keeps its
    // serialized size and the package layout is untouched. That is deliberate: adding exports to
    // a cooked map has broken the load twice, changing values inside them has not.

    static string PropName(PropertyData p) => p?.Name?.Value?.Value ?? "";

    static PropertyData? FindNamed(List<PropertyData>? list, string name)
    {
        if (list == null) return null;
        foreach (var p in list) if (p != null && PropName(p) == name) return p;
        return null;
    }

    static NormalExport? ExportByName(UAsset asset, string name)
    {
        foreach (var e in asset.Exports)
            if (e is NormalExport ne && (ne.ObjectName?.ToString() == name || ne.ObjectName?.Value?.Value == name)) return ne;
        return null;
    }

    // Unversioned cook packages nest math structs one level deeper than the versioned writer:
    // RelativeLocation is a StructPropertyData(StructType=Vector) whose single child is the
    // VectorPropertyData. Match either shape, else the setter silently touches nothing.
    static VectorPropertyData? Vec(List<PropertyData>? list, string name)
    {
        var p = FindNamed(list, name);
        if (p is VectorPropertyData v) return v;
        if (p is StructPropertyData sp && sp.Value != null)
            foreach (var c in sp.Value) if (c is VectorPropertyData cv) return cv;
        return null;
    }

    static RotatorPropertyData? Rot(List<PropertyData>? list, string name)
    {
        var p = FindNamed(list, name);
        if (p is RotatorPropertyData r) return r;
        if (p is StructPropertyData sp && sp.Value != null)
            foreach (var c in sp.Value) if (c is RotatorPropertyData cr) return cr;
        return null;
    }

    static BoxPropertyData? Box(List<PropertyData>? list, string name)
    {
        var p = FindNamed(list, name);
        if (p is BoxPropertyData b) return b;
        if (p is StructPropertyData sp && sp.Value != null)
            foreach (var c in sp.Value) if (c is BoxPropertyData cb) return cb;
        return null;
    }

    static void ReplaceSpline(string inPath, string outPath, string roadName, string pointsJson)
    {
        UAsset.CaptureOriginalExportData = true;   // must be set BEFORE load: OriginalData is captured during read
        var asset = new UAsset(inPath, EngineVersion.VER_UE5_5, Mappings);

        var road = ExportByName(asset, roadName);
        if (road == null) { Console.WriteLine($"REPLACE_SPLINE_FAIL road {roadName} not found"); return; }

        var splineProp = FindNamed(road.Data, "Spline") as ObjectPropertyData;
        if (splineProp == null) { Console.WriteLine("REPLACE_SPLINE_FAIL no Spline property"); return; }
        int exIdx = splineProp.Value.Index;
        if (exIdx <= 0) { Console.WriteLine("REPLACE_SPLINE_FAIL Spline is an import"); return; }
        var splineExp = asset.Exports[exIdx - 1] as NormalExport;
        if (splineExp == null) { Console.WriteLine("REPLACE_SPLINE_FAIL spline export missing"); return; }

        var curves = FindNamed(splineExp.Data, "SplineCurves") as StructPropertyData;
        var position = curves == null ? null : FindNamed(curves.Value, "Position") as StructPropertyData;
        var points = position == null ? null : FindNamed(position.Value, "Points") as ArrayPropertyData;
        if (points == null) { Console.WriteLine("REPLACE_SPLINE_FAIL SplineCurves.Position.Points not found"); return; }
        int n = points.Value.Length;

        // input: {"points": [[x,y,z], ...], "closed": true} or a bare [[x,y,z],...]
        double[][] src;
        bool closed = true;
        using (var doc = JsonDocument.Parse(File.ReadAllText(pointsJson)))
        {
            var root = doc.RootElement;
            var arr = root.ValueKind == JsonValueKind.Array ? root : root.GetProperty("points");
            if (root.ValueKind == JsonValueKind.Object && root.TryGetProperty("closed", out var c)) closed = c.GetBoolean();
            src = arr.EnumerateArray().Select(v => v.EnumerateArray().Select(d => d.GetDouble()).ToArray()).ToArray();
        }
        Console.WriteLine($"  source loop points={src.Length} closed={closed}; spline expects {n}");

        // resample by arc length so the curve follows the source shape exactly
        int m = src.Length + (closed ? 1 : 0);
        var cum = new double[m];
        for (int i = 1; i < m; i++) cum[i] = cum[i - 1] + Math.Sqrt(
            Math.Pow(src[i % src.Length][0] - src[(i - 1) % src.Length][0], 2) +
            Math.Pow(src[i % src.Length][1] - src[(i - 1) % src.Length][1], 2) +
            Math.Pow(src[i % src.Length][2] - src[(i - 1) % src.Length][2], 2));
        double total = cum[m - 1];
        var outp = new double[n][];
        int seg = 0;
        for (int i = 0; i < n; i++)
        {
            double want = total * i / (double)(closed ? n : n - 1);
            while (seg < m - 2 && cum[seg + 1] < want) seg++;
            double span = cum[seg + 1] - cum[seg];
            double t = span <= 1e-9 ? 0 : (want - cum[seg]) / span;
            var a = src[seg % src.Length]; var b = src[(seg + 1) % src.Length];
            outp[i] = new double[3];
            for (int k = 0; k < 3; k++) outp[i][k] = a[k] + (b[k] - a[k]) * t;
        }

        double minx = outp.Min(p => p[0]), maxx = outp.Max(p => p[0]);
        double miny = outp.Min(p => p[1]), maxy = outp.Max(p => p[1]);
        double minz = outp.Min(p => p[2]), maxz = outp.Max(p => p[2]);

        for (int i = 0; i < n; i++)
        {
            var sp = points.Value[i] as StructPropertyData;
            if (sp == null) continue;
            var prev = outp[(i - 1 + n) % n];
            var next = outp[(i + 1) % n];
            var leave = new[] { (next[0] - outp[i][0]), (next[1] - outp[i][1]), (next[2] - outp[i][2]) };
            var arrive = new[] { (outp[i][0] - prev[0]), (outp[i][1] - prev[1]), (outp[i][2] - prev[2]) };

            var o = Vec(sp.Value, "OutVal"); if (o != null) o.Value = new FVector((float)outp[i][0], (float)outp[i][1], (float)outp[i][2]);
            var lv = Vec(sp.Value, "LeaveTangent"); if (lv != null) lv.Value = new FVector((float)leave[0], (float)leave[1], (float)leave[2]);
            var av = Vec(sp.Value, "ArriveTangent"); if (av != null) av.Value = new FVector((float)arrive[0], (float)arrive[1], (float)arrive[2]);
        }

        var box = Box(road.Data, "SplineBounds");
        if (box != null)
        {
            box.Value = new TBox<FVector>(
                new FVector((float)(minx - 1000), (float)(miny - 1000), (float)(minz - 1000)),
                new FVector((float)(maxx + 1000), (float)(maxy + 1000), (float)(maxz + 1000)), 1);
            Console.WriteLine($"  SplineBounds set X {minx:F0}..{maxx:F0} Y {miny:F0}..{maxy:F0} Z {minz:F0}..{maxz:F0}");
        }

        splineExp.DataDirty = true;      // capture is on: the writer replays OriginalData unless dirtied
        road.DataDirty = true;
        asset.Write(outPath);
        Console.WriteLine($"REPLACE_SPLINE_OK {roadName}: {n} points from {src.Length} source points -> {outPath}");
    }

    static void FindActorBlock(string inPath)
    {
        UAsset.CaptureOriginalExportData = true;
        var asset = new UAsset(inPath, EngineVersion.VER_UE5_5, Mappings);
        var lvl = asset.Exports.OfType<LevelExport>().FirstOrDefault();
        if (lvl == null || lvl.Actors == null) { Console.WriteLine("FIND no level"); return; }
        var idx = lvl.Actors.Select(a => a.Index).ToArray();
        Console.WriteLine($"FIND actors={idx.Length} first10={string.Join(",", idx.Take(10))}");
        Console.WriteLine($"FIND level_export_serial={lvl.SerialSize} originalData={(lvl.OriginalData == null ? "null" : lvl.OriginalData.Length.ToString())}");

        var pattern = new byte[idx.Length * 4];
        Buffer.BlockCopy(idx, 0, pattern, 0, pattern.Length);
        foreach (var suffix in new[] { ".uexp", ".umap" })
        {
            string f = Path.ChangeExtension(inPath, suffix.TrimStart('.'));
            if (!File.Exists(f)) { Console.WriteLine($"FIND {suffix} missing"); continue; }
            var data = File.ReadAllBytes(f);
            int at = IndexOf(data, pattern);
            Console.WriteLine($"FIND {suffix} len={data.Length} actorArrayAt={at}");
            if (at >= 0)
            {
                int off = at - 4;
                Console.WriteLine($"FIND {suffix} countPrefixAt={off} countValue={(off >= 0 ? BitConverter.ToInt32(data, off) : -1)}");
            }
        }
    }

    static int IndexOf(byte[] haystack, byte[] needle)
    {
        for (int i = 0; i <= haystack.Length - needle.Length; i++)
        {
            int j = 0;
            while (j < needle.Length && haystack[i + j] == needle[j]) j++;
            if (j == needle.Length) return i;
        }
        return -1;
    }

    static void ListActors(string inPath)
    {
        var asset = new UAsset(inPath, EngineVersion.VER_UE5_5, Mappings);
        var lvl = asset.Exports.OfType<LevelExport>().FirstOrDefault();
        if (lvl == null || lvl.Actors == null) { Console.WriteLine("LIST_ACTORS no level"); return; }
        Console.WriteLine($"LIST_ACTORS count={lvl.Actors.Count}");
        var cls = new Dictionary<string, int>();
        foreach (var idx in lvl.Actors)
        {
            string cn = "?";
            int i = idx.Index;
            if (i > 0 && i - 1 < asset.Exports.Count) cn = ClassNameOfExport(asset, asset.Exports[i - 1] as NormalExport);
            cls[cn] = cls.GetValueOrDefault(cn) + 1;
        }
        foreach (var kv in cls.OrderByDescending(kv => kv.Value))
            Console.WriteLine("  " + kv.Value.ToString().PadLeft(4) + "  " + kv.Key);
    }

    static void DropActors(string inPath, string outPath, string classList)
    {
        var drop = new HashSet<string>(classList.Split(',').Select(x => x.Trim()).Where(x => x.Length > 0));
        UAsset.CaptureOriginalExportData = true;
        var asset = new UAsset(inPath, EngineVersion.VER_UE5_5, Mappings);
        var lvl = asset.Exports.OfType<LevelExport>().FirstOrDefault();
        if (lvl == null || lvl.Actors == null) { Console.WriteLine("DROP_ACTORS_FAIL no level"); return; }
        var raw = lvl.OriginalData;
        if (raw == null) { Console.WriteLine("DROP_ACTORS_FAIL no original bytes"); return; }

        var keep = new List<int>();
        var dropped = new Dictionary<string, int>();
        foreach (var idx in lvl.Actors)
        {
            int i = idx.Index;
            string cn = (i > 0 && i - 1 < asset.Exports.Count)
                ? ClassNameOfExport(asset, asset.Exports[i - 1] as NormalExport) : "?";
            if (drop.Contains(cn)) { dropped[cn] = dropped.GetValueOrDefault(cn) + 1; continue; }
            keep.Add(i);
        }
        if (dropped.Count == 0) { Console.WriteLine("DROP_ACTORS no match"); return; }

        int expected = lvl.Actors.Count;
        int off = FindActorCountOffset(raw, expected, maxIdx: Math.Max(expected, asset.Exports.Count) + 4096, minIdx: -65536);
        if (off < 0) { Console.WriteLine($"DROP_ACTORS_FAIL no actor block count={expected} in {raw.Length} bytes"); return; }

        int arrayStart = off + 4;
        int arrayBytes = expected * 4;
        var outB = new List<byte>(raw.Length);
        outB.AddRange(raw.Take(arrayStart));
        foreach (var v in keep) outB.AddRange(BitConverter.GetBytes(v));
        outB.AddRange(raw.Skip(arrayStart + arrayBytes));
        var arr = outB.ToArray();
        Array.Copy(BitConverter.GetBytes(keep.Count), 0, arr, off, 4);
        lvl.OriginalData = arr;
        lvl.DataDirty = false;          // write patched original bytes, never a re-serialisation
        lvl.SerialSize = arr.Length;    // table must agree with the region we wrote

        asset.Write(outPath);
        Console.WriteLine($"DROP_ACTORS_OK actors {expected} -> {keep.Count} " +
            $"({string.Join(",", dropped.Select(kv => kv.Key + ":" + kv.Value))}) bytes {raw.Length} -> {arr.Length}");
    }

    static void PrintSpline(string inPath, string roadName)
    {
        var asset = new UAsset(inPath, EngineVersion.VER_UE5_5, Mappings);
        var road = ExportByName(asset, roadName);
        if (road == null) { Console.WriteLine("PRINT_SPLINE no road"); return; }
        var splineProp = FindNamed(road.Data, "Spline") as ObjectPropertyData;
        var splineExp = asset.Exports[splineProp.Value.Index - 1] as NormalExport;
        var curves = FindNamed(splineExp.Data, "SplineCurves") as StructPropertyData;
        var position = FindNamed(curves.Value, "Position") as StructPropertyData;
        var points = FindNamed(position.Value, "Points") as ArrayPropertyData;
        Console.WriteLine($"PRINT_SPLINE {roadName} points={points.Value.Length}");
        foreach (int i in new[] { 0, 1, 500, points.Value.Length - 1 })
        {
            var sp = points.Value[i] as StructPropertyData;
            var o = Vec(sp.Value, "OutVal"); var lv = Vec(sp.Value, "LeaveTangent");
            var iv = FindNamed(sp.Value, "InVal") as FloatPropertyData;
            var im = FindNamed(sp.Value, "InterpMode") as BytePropertyData;
            Console.WriteLine($"  [{i}] InVal={iv?.Value} OutVal=({o?.Value.X:F1},{o?.Value.Y:F1},{o?.Value.Z:F1}) Leave=({lv?.Value.X:F2},{lv?.Value.Y:F2},{lv?.Value.Z:F2}) Interp={im?.Value}");
        }
    }

    static void PrintGates(string inPath)
    {
        var asset = new UAsset(inPath, EngineVersion.VER_UE5_5, Mappings);
        for (int i = 0; i < 64; i++)
        {
            var gate = ExportByName(asset, $"MotorTownRaceSection_{i}");
            if (gate == null) continue;
            var rc = FindNamed(gate.Data, "RootComponent") as ObjectPropertyData;
            if (rc == null || rc.Value.Index <= 0) continue;
            var comp = asset.Exports[rc.Value.Index - 1] as NormalExport;
            if (comp == null) continue;
            var loc = Vec(comp.Data, "RelativeLocation");
            var rot = Rot(comp.Data, "RelativeRotation");
            if (i == 0) {
                var rl = FindNamed(comp.Data, "RelativeLocation");
                Console.WriteLine($"  DEBUG RelativeLocation type={rl?.GetType().FullName} valType={(rl as StructPropertyData)?.StructType?.ToString()} childCount={(rl as StructPropertyData)?.Value?.Count} children=[{string.Join(",", ((rl as StructPropertyData)?.Value ?? new List<PropertyData>()).Select(x => x?.GetType().Name + ":" + x?.Name?.ToString()))}]");
            }
            if (i == 0) Console.WriteLine($"  DEBUG gate0 comp={comp.ObjectName} props={(comp.Data == null ? "NULL" : comp.Data.Count.ToString())} names=[{string.Join(",", (comp.Data ?? new List<PropertyData>()).Take(8).Select(x => x?.Name?.ToString()))}]");
            Console.WriteLine($"GATE {i} loc=({loc?.Value.X:F1},{loc?.Value.Y:F1},{loc?.Value.Z:F1}) yaw={rot?.Value.Yaw:F1}");
        }
    }

    static void SetGateTransforms(string inPath, string outPath, string gatesJson)
    {
        UAsset.CaptureOriginalExportData = true;
        var asset = new UAsset(inPath, EngineVersion.VER_UE5_5, Mappings);

        using var doc = JsonDocument.Parse(File.ReadAllText(gatesJson));
        int done = 0, missing = 0;
        foreach (var g in doc.RootElement.EnumerateArray())
        {
            int idx = g.GetProperty("index").GetInt32();
            var pos = g.GetProperty("pos").EnumerateArray().Select(v => v.GetDouble() * 100.0).ToArray(); // m -> cm
            double yaw = g.GetProperty("yaw").GetDouble();

            var gate = ExportByName(asset, $"MotorTownRaceSection_{idx}");
            if (gate == null) { missing++; continue; }
            var rc = FindNamed(gate.Data, "RootComponent") as ObjectPropertyData;
            if (rc == null || rc.Value.Index <= 0) { missing++; continue; }
            var comp = asset.Exports[rc.Value.Index - 1] as NormalExport;
            if (comp == null) { missing++; continue; }

            var loc = Vec(comp.Data, "RelativeLocation");
            if (loc != null) loc.Value = new FVector((float)pos[0], (float)pos[1], (float)pos[2]);
            var rot = Rot(comp.Data, "RelativeRotation");
            if (rot != null) rot.Value = new FRotator(0f, (float)yaw, 0f);
            if (loc == null && rot == null) { missing++; continue; }
            comp.DataDirty = true;
            done++;
        }
        asset.Write(outPath);
        Console.WriteLine($"SET_GATES_OK placed={done} missing={missing} -> {outPath}");
    }

    static void SetClassRef(string inPath, string outPath, string exportName, string propName, string packagePath, string className)
    {
        var asset = new UAsset(inPath, EngineVersion.VER_UE5_5, Mappings);
        NormalExport? target = null;
        foreach (var e in asset.Exports)
        {
            if (e is not NormalExport ne) continue;
            var nm = ne.ObjectName?.Value?.Value ?? "";
            var num = ne.ObjectName?.Number ?? 0;
            var full = num > 0 ? $"{nm}_{num - 1}" : nm;
            if (string.Equals(nm, exportName, StringComparison.OrdinalIgnoreCase) ||
                string.Equals(full, exportName, StringComparison.OrdinalIgnoreCase)) { target = ne; break; }
        }
        if (target == null) { Console.WriteLine($"SETCLASSREF_FAIL no export named {exportName}"); return; }

        ObjectPropertyData? prop = null;
        foreach (var p in target.Data)
            if (p is ObjectPropertyData op && string.Equals(op.Name?.Value?.Value, propName, StringComparison.OrdinalIgnoreCase))
                prop = op;

        var (pkgIdx, classIdx) = AddImportChain(asset, "/Script/Engine", "BlueprintGeneratedClass", packagePath, className);

        if (prop != null)
        {
            Console.WriteLine($"  before: {propName} = {prop.Value.Index}");
            prop.Value = FPackageIndex.FromImport(classIdx - 1);
        }
        else
        {
            Console.WriteLine($"  {propName} absent on {exportName}; creating (schema order: derived props first)");
            var np = new ObjectPropertyData(FName.FromString(asset, propName))
            { Value = FPackageIndex.FromImport(classIdx - 1) };
            target.Data.Insert(0, np);
        }

        asset.ResolveAncestries();
        asset.Write(outPath);
        Console.WriteLine($"SETCLASSREF_OK {exportName}.{propName} -> {packagePath}.{className} (import {classIdx}) -> {outPath}");
    }

    // --set-array-class-ref: point an ObjectProperty that lives inside a
    // TArray<FStruct> at a class in another package (e.g. a spawn setting's
    // VehicleClass -> /Game/Cars/Models/Hana.Hana_C). The field must already
    // exist in the cooked struct (unversioned property schema); we only
    // repoint it, we never insert.  Keyed by a field inside each element so
    // the order of the array does not matter.
    // ========================================================================
    static void SetArrayClassRef(string inPath, string outPath, string exportName,
        string arrayProp, string keyField, string field, string mapJsonPath)
    {
        var asset = new UAsset(inPath, EngineVersion.VER_UE5_5, Mappings);
        NormalExport? target = null;
        foreach (var e in asset.Exports)
        {
            if (e is not NormalExport ne) continue;
            var nm = ne.ObjectName?.Value?.Value ?? "";
            var num = ne.ObjectName?.Number ?? 0;
            var full = num > 0 ? $"{nm}_{num - 1}" : nm;
            if (string.Equals(nm, exportName, StringComparison.OrdinalIgnoreCase) ||
                string.Equals(full, exportName, StringComparison.OrdinalIgnoreCase)) { target = ne; break; }
        }
        if (target == null) { Console.WriteLine($"SETARRAYCLASS_FAIL no export named {exportName}"); return; }

        ArrayPropertyData? arr = null;
        foreach (var p in target.Data)
            if (p is ArrayPropertyData ap && string.Equals(ap.Name?.Value?.Value, arrayProp, StringComparison.OrdinalIgnoreCase))
                arr = ap;
        if (arr == null) { Console.WriteLine($"SETARRAYCLASS_FAIL no array {arrayProp} on {exportName}"); return; }

        var map = new Dictionary<string, string[]>();
        using (var doc = JsonDocument.Parse(File.ReadAllText(mapJsonPath)))
            foreach (var kv in doc.RootElement.EnumerateObject())
                map[kv.Name] = kv.Value.EnumerateArray().Select(x => x.GetString() ?? "").ToArray();

        int hits = 0;
        foreach (var el in arr.Value)
        {
            if (el is not StructPropertyData sp) continue;

            string? key = null;
            foreach (var pp in sp.Value)
            {
                if (!string.Equals(pp.Name?.Value?.Value, keyField, StringComparison.OrdinalIgnoreCase)) continue;
                if (pp is NamePropertyData npd) key = npd.Value?.Value?.Value;
                else if (pp is StrPropertyData spd) key = spd.Value?.Value;
            }
            if (key == null || !map.TryGetValue(key, out var refs) || refs.Length < 2) continue;

            var (_, classIdx) = AddImportChain(asset, "/Script/Engine", "BlueprintGeneratedClass", refs[0], refs[1]);
            bool set = false;
            foreach (var pp in sp.Value)
            {
                if (pp is ObjectPropertyData op && string.Equals(op.Name?.Value?.Value, field, StringComparison.OrdinalIgnoreCase))
                {
                    op.Value = FPackageIndex.FromImport(classIdx - 1);
                    set = true;
                }
            }
            if (set) { hits++; Console.WriteLine($"  {key} -> {refs[0]}.{refs[1]} (import {classIdx})"); }
            else Console.WriteLine($"  {key}: field {field} absent in struct, skipped");
        }

        asset.ResolveAncestries();
        asset.Write(outPath);
        Console.WriteLine($"SETARRAYCLASS_OK {hits} elements -> {outPath}");
    }

    // --set-array-bool: flip a BoolProperty inside TArray<FStruct> elements, selected by a
    // key field (e.g. SpawnSettings[SettingKey=Police].bUseNPCPoliceDensity). Optional
    // "key=value" filter restricts which rows are touched.
    // ========================================================================
    static void SetArrayBool(string inPath, string outPath, string exportName,
        string arrayProp, string keyField, string field, bool value, string only)
    {
        var asset = new UAsset(inPath, EngineVersion.VER_UE5_5, Mappings);
        NormalExport? target = null;
        foreach (var e in asset.Exports)
        {
            if (e is not NormalExport ne) continue;
            var nm = ne.ObjectName?.Value?.Value ?? "";
            var num = ne.ObjectName?.Number ?? 0;
            var full = num > 0 ? $"{nm}_{num - 1}" : nm;
            if (string.Equals(nm, exportName, StringComparison.OrdinalIgnoreCase) ||
                string.Equals(full, exportName, StringComparison.OrdinalIgnoreCase)) { target = ne; break; }
        }
        if (target == null) { Console.WriteLine($"SETARRAYBOOL_FAIL no export named {exportName}"); return; }

        ArrayPropertyData? arr = null;
        foreach (var p in target.Data)
            if (p is ArrayPropertyData ap && string.Equals(ap.Name?.Value?.Value, arrayProp, StringComparison.OrdinalIgnoreCase))
                arr = ap;
        if (arr == null) { Console.WriteLine($"SETARRAYBOOL_FAIL no array {arrayProp} on {exportName}"); return; }

        var wanted = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        if (!string.IsNullOrWhiteSpace(only))
            foreach (var kv in only.Split(','))
            {
                var bits = kv.Split('=');
                if (bits.Length == 2 && string.Equals(bits[0].Trim(), keyField, StringComparison.OrdinalIgnoreCase))
                    wanted.Add(bits[1].Trim());
            }

        int hits = 0;
        foreach (var el in arr.Value)
        {
            if (el is not StructPropertyData sp) continue;
            string? key = null;
            foreach (var pp in sp.Value)
            {
                if (!string.Equals(pp.Name?.Value?.Value, keyField, StringComparison.OrdinalIgnoreCase)) continue;
                if (pp is NamePropertyData npd) key = npd.Value?.Value?.Value;
                else if (pp is StrPropertyData spd) key = spd.Value?.Value;
            }
            if (key == null) continue;
            if (wanted.Count > 0 && !wanted.Contains(key)) continue;
            foreach (var pp in sp.Value)
            {
                if (pp is BoolPropertyData bp && string.Equals(bp.Name?.Value?.Value, field, StringComparison.OrdinalIgnoreCase))
                {
                    Console.WriteLine($"  {key}.{field}: {bp.Value} -> {value}");
                    bp.Value = value;
                    hits++;
                }
            }
        }

        asset.ResolveAncestries();
        asset.Write(outPath);
        Console.WriteLine($"SETARRAYBOOL_OK {hits} elements -> {outPath}");
    }

    // --set-bool: flip a BoolProperty on a named export (used to clear
    // NavigationSystemModuleConfig.bAutoSpawnMissingNavData on a custom level).
    // ========================================================================
    static void SetBoolProp(string inPath, string outPath, string exportName, string propName, bool value)
    {
        var asset = new UAsset(inPath, EngineVersion.VER_UE5_5, Mappings);
        NormalExport? target = null;
        foreach (var e in asset.Exports)
        {
            if (e is not NormalExport ne) continue;
            var nm = ne.ObjectName?.Value?.Value ?? "";
            var num = ne.ObjectName?.Number ?? 0;
            var full = num > 0 ? $"{nm}_{num - 1}" : nm;
            if (string.Equals(nm, exportName, StringComparison.OrdinalIgnoreCase) ||
                string.Equals(full, exportName, StringComparison.OrdinalIgnoreCase)) { target = ne; break; }
        }
        if (target == null) { Console.WriteLine($"SETBOOL_FAIL no export named {exportName}"); return; }

        int hits = 0;
        foreach (var prop in target.Data)
        {
            if (prop is BoolPropertyData bp && string.Equals(bp.Name?.Value?.Value, propName, StringComparison.OrdinalIgnoreCase))
            {
                Console.WriteLine($"  before: {bp.Name.Value.Value} = {bp.Value}");
                bp.Value = value;
                bp.IsZero = !value;
                hits++;
            }
        }
        if (hits == 0) { Console.WriteLine($"SETBOOL_FAIL no bool property {propName} on {exportName}"); return; }

        asset.ResolveAncestries();
        asset.Write(outPath);
        Console.WriteLine($"SETBOOL_OK {exportName}.{propName}={value} hits={hits} -> {outPath}");
    }

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
        // WRITE_VERSIONED=1: clear PKG_UnversionedProperties before writing so the
        // patched asset is serialized WITH property tags (versioned). The client
        // engine reads both formats (server-cooked tables load fine in b1), so a
        // versioned write sidesteps the unversioned schema-contract entirely.
        if (Environment.GetEnvironmentVariable("WRITE_VERSIONED") == "1")
        {
            asset.PackageFlags &= ~EPackageFlags.PKG_UnversionedProperties;
            Console.WriteLine("  WRITE_VERSIONED: cleared PKG_UnversionedProperties (tagged write)");
            // Unversioned parses produce dummy FNames (names resolved via mappings,
            // absent from the file's name map). A tagged write serializes each
            // property NAME, so every dummy FName must be materialized into the
            // name map first, else DummyFNameSerializationException.
            int n = 0;
            foreach (var prop in mainExport.Data) n += MaterializeNames(prop, asset);
            // DataTableExport rows live in Table.Data (row structs), NOT Data.
            if (mainExport is DataTableExport dte && dte.Table?.Data != null)
            {
                foreach (var row in dte.Table.Data)
                {
                    n += MaterializeNames(row, asset);
                    n += MaterializeTypeNames(row, asset);
                }
            }
            // Tagged writes also serialize each property's TYPE name tree
            // ("ArrayProperty", inner types, struct types). Unversioned files
            // never store these, so materialize them too.
            foreach (var tn in EnginePropertyTypeNames) n += MaterializeNameString(asset, tn);
            foreach (var prop in mainExport.Data) n += MaterializeTypeNames(prop, asset);
            Console.WriteLine($"  WRITE_VERSIONED: materialized {n} names into name map");
        }
        Directory.CreateDirectory(outputDir);
        var outputPath = Path.Combine(outputDir, $"{outputFileName}.uasset");
        asset.Write(outputPath);
        Console.WriteLine($"Written: {outputFileName}.uasset + {outputFileName}.uexp to {outputDir}");
    }

    // --align-imports: Rebuild a child DataTable's import table so it is a
    // superset of the composite's, with shared imports at IDENTICAL indices.
    // The engine's CompositeDataTable merge resolves copied child-row import
    // indices against the composite's import table; child tables whose imports
    // are ordered differently produce garbage refs (client TArray crash,
    // 2026-09-25 bisect). Every import reference in the child (export headers,
    // row properties, recursively through struct/array/map/set containers) is
    // remapped; child-only imports are appended after the composite set.
    static string ImportKey(UAsset a, Import imp)
    {
        string outer = "0";
        int oi = imp.OuterIndex != null ? imp.OuterIndex.Index : 0;
        if (oi < 0)
        {
            int i = -oi - 1;
            var list = a.Imports;
            if (i >= 0 && i < list.Count)
            {
                var cur = list[i];
                int guard = 0;
                while (cur.OuterIndex != null && cur.OuterIndex.Index < 0 && guard++ < 16)
                {
                    int j = -cur.OuterIndex.Index - 1;
                    if (j < 0 || j >= list.Count) break;
                    cur = list[j];
                }
                outer = cur.ObjectName.Value != null ? (cur.ObjectName.Value.Value ?? "") : "";
            }
        }
        string s(FName f) => f.Value != null ? (f.Value.Value ?? "") : "";
        return s(imp.ClassPackage) + "|" + s(imp.ClassName) + "|" + s(imp.ObjectName) + "|" + outer;
    }

    static Import CloneImportFor(UAsset child, Import imp, int outerIndex)
    {
        string s(FName f) => f.Value != null ? (f.Value.Value ?? "") : "";
        return new Import(
            new FName(child, s(imp.ClassPackage)),
            new FName(child, s(imp.ClassName)),
            new FPackageIndex(outerIndex),
            new FName(child, s(imp.ObjectName)),
            false);
    }

    static void WalkRemapProps(IEnumerable<PropertyData> props, Func<int, int> map)
    {
        foreach (var p in props)
        {
            switch (p)
            {
                case ObjectPropertyData opd:
                    if (opd.Value != null && opd.Value.Index < 0)
                        opd.Value = new FPackageIndex(map(opd.Value.Index));
                    break;
                case StructPropertyData spd:
                    WalkRemapProps(spd.Value, map);
                    break;
                case ArrayPropertyData apd:
                    if (apd.Value != null) WalkRemapProps(apd.Value, map);
                    break;
                case MapPropertyData mpd:
                    if (mpd.Value != null)
                    {
                        foreach (var kv in mpd.Value)
                        {
                            if (kv.Key != null) WalkRemapProps(new[] { kv.Key }, map);
                            if (kv.Value != null) WalkRemapProps(new[] { kv.Value }, map);
                        }
                    }
                    break;
            }
        }
    }

    static void AlignImports(string compPath, string childPath, string outputDir)
    {
        if (!Path.IsPathRooted(compPath)) compPath = Path.Combine(RootDir, compPath);
        if (!Path.IsPathRooted(childPath)) childPath = Path.Combine(RootDir, childPath);
        var comp = new UAsset(compPath, EngineVersion.VER_UE5_5, Mappings);
        var child = new UAsset(childPath, EngineVersion.VER_UE5_5, Mappings);
        Console.WriteLine($"Aligning imports: child={Path.GetFileName(childPath)} ({child.Imports.Count}) -> composite={Path.GetFileName(compPath)} ({comp.Imports.Count})");

        var compKeyToIdx = new Dictionary<string, int>();
        for (int i = 0; i < comp.Imports.Count; i++)
        {
            var k = ImportKey(comp, comp.Imports[i]);
            if (!compKeyToIdx.ContainsKey(k)) compKeyToIdx[k] = i;
        }

        // New table = composite imports verbatim (same order => outer chains stay valid)
        var newImports = new List<Import>();
        foreach (var ci in comp.Imports)
            newImports.Add(CloneImportFor(child, ci, ci.OuterIndex != null ? ci.OuterIndex.Index : 0));

        // Map child imports: shared keys -> composite index; child-only -> appended
        var remap = new int[child.Imports.Count];
        int next = newImports.Count;
        for (int i = 0; i < child.Imports.Count; i++)
        {
            var k = ImportKey(child, child.Imports[i]);
            if (compKeyToIdx.TryGetValue(k, out var ci))
            {
                remap[i] = ci;
            }
            else
            {
                var oldImp = child.Imports[i];
                int newOuter = 0;
                if (oldImp.OuterIndex != null && oldImp.OuterIndex.Index < 0)
                {
                    int j = -oldImp.OuterIndex.Index - 1;
                    newOuter = (j >= 0 && j < remap.Length && j < i) ? -(remap[j] + 1) : oldImp.OuterIndex.Index;
                }
                newImports.Add(CloneImportFor(child, oldImp, newOuter));
                remap[i] = next++;
            }
        }

        int MapRef(int idx)
        {
            if (idx >= 0) return idx;
            int old = -idx - 1;
            if (old >= 0 && old < remap.Length) return -(remap[old] + 1);
            return idx;
        }

        foreach (var exp in child.Exports)
        {
            if (exp.ClassIndex != null) exp.ClassIndex = new FPackageIndex(MapRef(exp.ClassIndex.Index));
            if (exp.SuperIndex != null) exp.SuperIndex = new FPackageIndex(MapRef(exp.SuperIndex.Index));
            if (exp.TemplateIndex != null) exp.TemplateIndex = new FPackageIndex(MapRef(exp.TemplateIndex.Index));
            if (exp.OuterIndex != null && exp.OuterIndex.Index < 0)
                exp.OuterIndex = new FPackageIndex(MapRef(exp.OuterIndex.Index));
            if (exp is NormalExport ne && ne.Data != null) WalkRemapProps(ne.Data, MapRef);
            if (exp is DataTableExport dte && dte.Table != null && dte.Table.Data != null)
                foreach (var row in dte.Table.Data) WalkRemapProps(row.Value, MapRef);
        }

        child.Imports = newImports;
        Directory.CreateDirectory(outputDir);
        var baseName = Path.GetFileNameWithoutExtension(childPath);
        var outPath = Path.Combine(outputDir, baseName + ".uasset");
        child.Write(outPath);
        Console.WriteLine($"Written: {baseName}.uasset (+ .uexp) to {outputDir} — imports now {newImports.Count} (composite-aligned)");
    }

    static readonly string[] EnginePropertyTypeNames =
    {
        "ObjectProperty", "IntProperty", "FloatProperty", "BoolProperty", "ByteProperty",
        "EnumProperty", "StructProperty", "ArrayProperty", "MapProperty", "NameProperty",
        "StrProperty", "TextProperty", "DoubleProperty", "Int64Property", "Int32Property",
        "Int16Property", "Int8Property", "UInt64Property", "UInt32Property", "UInt16Property",
        "UInt8Property", "ClassProperty", "SoftObjectProperty", "SoftClassProperty",
        "AssetObjectProperty", "AssetClassProperty", "DelegateProperty", "InterfaceProperty",
        "MulticastDelegateProperty", "SetProperty", "None", "Generic"
    };

    static int MaterializeNameString(UAsset asset, string s)
    {
        if (string.IsNullOrEmpty(s)) return 0;
        try { asset.SearchNameReference(new FString(s)); return 0; } // present
        catch (NameMapOutOfRangeException) { }
        FName.FromString(asset, s);
        return 1;
    }

    // Materialize type-name FNames (dummy or unmapped) for tagged writes.
    static int MaterializeTypeNames(PropertyData prop, UAsset asset)
    {
        int count = 0;
        switch (prop)
        {
            case StructPropertyData spd:
            {
                int c;
                if (spd.StructType != null) { spd.StructType = MaterializeFName(spd.StructType, asset, out c); count += c; }
                foreach (var inner in spd.Value) count += MaterializeTypeNames(inner, asset);
                break;
            }
            case ArrayPropertyData apd:
            {
                int c;
                if (apd.ArrayType != null) { apd.ArrayType = MaterializeFName(apd.ArrayType, asset, out c); count += c; }
                // Empty struct-typed arrays need an inner StructType for tagged
                // writes; resolve it from the usmap schema and register it via
                // ArrayStructTypeOverride (same mechanism ArrayPropertyData.Write
                // falls back to).
                if (apd.Value.Length == 0 && apd.ArrayType?.Value?.Value == "StructProperty"
                    && asset.Mappings != null && !asset.ArrayStructTypeOverride.ContainsKey(apd.Name.Value.Value)
                    && asset.Mappings.TryGetPropertyData<UsmapArrayData>(apd.Name, apd.Ancestry, asset, out var mArr)
                    && mArr != null && mArr.InnerType is UsmapStructData uStr)
                {
                    asset.ArrayStructTypeOverride[apd.Name.Value.Value] = new FString(uStr.StructType);
                    count++;
                }
                foreach (var inner in apd.Value.OfType<PropertyData>()) count += MaterializeTypeNames(inner, asset);
                break;
            }
            case MapPropertyData mpd:
            {
                int c;
                if (mpd.KeyType != null) { mpd.KeyType = MaterializeFName(mpd.KeyType, asset, out c); count += c; }
                if (mpd.ValueType != null) { mpd.ValueType = MaterializeFName(mpd.ValueType, asset, out c); count += c; }
                foreach (var kv in mpd.Value)
                {
                    if (kv.Key is PropertyData kp) count += MaterializeTypeNames(kp, asset);
                    if (kv.Value is PropertyData vp) count += MaterializeTypeNames(vp, asset);
                }
                break;
            }
            case EnumPropertyData epd:
            {
                int c;
                if (epd.EnumType != null) { epd.EnumType = MaterializeFName(epd.EnumType, asset, out c); count += c; }
                break;
            }
            case BytePropertyData bpd:
            {
                int c;
                if (bpd.EnumType != null) { bpd.EnumType = MaterializeFName(bpd.EnumType, asset, out c); count += c; }
                break;
            }
            case RawStructPropertyData rsp:
            {
                int c;
                if (rsp.StructType != null) { rsp.StructType = MaterializeFName(rsp.StructType, asset, out c); count += c; }
                break;
            }
        }
        return count;
    }

    // Re-register any dummy FName (unversioned parse) into the asset's name map.
    // Returns the materialized FName; assign it back at the call site.
    static FName MaterializeFName(FName fname, UAsset asset, out int count)
    {
        count = 0;
        if (fname != null && fname.IsDummy && !string.IsNullOrEmpty(fname.Value?.Value))
        {
            var made = FName.FromString(asset, fname.Value.Value);
            count = 1;
            return made;
        }
        return fname;
    }

    static int MaterializeNames(PropertyData prop, UAsset asset)
    {
        int count = 0;
        if (string.IsNullOrEmpty(prop.Name.Value?.Value) is false && prop.Name.IsDummy)
        {
            prop.Name = FName.FromString(asset, prop.Name.Value.Value);
            count++;
        }
        if (prop is NamePropertyData npd && npd.Value?.IsDummy == true)
        {
            npd.Value = FName.FromString(asset, npd.Value.Value.Value);
            count++;
        }
        // Enum values serialize as FNames in tagged writes.
        if (prop is EnumPropertyData epd && epd.Value != null && epd.Value.IsDummy)
        {
            epd.Value = FName.FromString(asset, epd.Value.Value.Value);
            count++;
        }
        if (prop is StructPropertyData spd)
            foreach (var inner in spd.Value) count += MaterializeNames(inner, asset);
        else if (prop is ArrayPropertyData apd)
            foreach (var inner in apd.Value.OfType<PropertyData>()) count += MaterializeNames(inner, asset);
        else if (prop is MapPropertyData mpd)
            foreach (var kv in mpd.Value)
            {
                if (kv.Key is PropertyData kp) count += MaterializeNames(kp, asset);
                if (kv.Value is PropertyData vp) count += MaterializeNames(vp, asset);
            }
        return count;
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
                TransferPropertyNames(newEntry, asset);
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
    // Cross-asset FName transfer (for --patch-cdo-arrays template_source clones)
    // ========================================================================
    // An FName cloned from a template asset keeps the TEMPLATE's name-map
    // index; serializing it into the target asset would write the WRONG name.
    // Rebind every FName in a cloned property tree by string value —
    // AddNameReference dedups, so existing names keep their index.
    // Not remapped: FPackageIndex object refs (import tables differ per
    // asset — cross-asset templates must not carry object references).
    static FName TransferOrKeep(FName fname, UAsset asset)
    {
        if (fname == null || fname.IsDummy) return fname;
        if (fname.Asset == null || ReferenceEquals(fname.Asset, asset)) return fname;
        var val = fname.Value;
        if (val == null) return fname;
        return new FName(asset, val, fname.Number);
    }

    static void TransferPropertyNames(PropertyData prop, UAsset asset)
    {
        if (prop == null) return;
        prop.Name = TransferOrKeep(prop.Name, asset);
        if (prop.PropertyTypeName?.Nodes != null)
        {
            for (int i = 0; i < prop.PropertyTypeName.Nodes.Count; i++)
            {
                var node = prop.PropertyTypeName.Nodes[i];
                node.Name = TransferOrKeep(node.Name, asset);
                prop.PropertyTypeName.Nodes[i] = node;
            }
        }

        switch (prop)
        {
            case StructPropertyData sp:
                sp.StructType = TransferOrKeep(sp.StructType, asset);
                if (sp.Value != null)
                    foreach (var child in sp.Value) TransferPropertyNames(child, asset);
                break;
            case ArrayPropertyData ap:
                ap.ArrayType = TransferOrKeep(ap.ArrayType, asset);
                if (ap.Value != null)
                    foreach (var child in ap.Value) TransferPropertyNames(child, asset);
                break;
            case MapPropertyData mp:
                mp.KeyType = TransferOrKeep(mp.KeyType, asset);
                mp.ValueType = TransferOrKeep(mp.ValueType, asset);
                if (mp.Value != null)
                {
                    var newMap = new TMap<PropertyData, PropertyData>();
                    foreach (var kvp in mp.Value)
                    {
                        TransferPropertyNames(kvp.Key, asset);
                        TransferPropertyNames(kvp.Value, asset);
                        newMap.Add(kvp.Key, kvp.Value);
                    }
                    mp.Value = newMap;
                }
                break;
            case NamePropertyData np:
                np.Value = TransferOrKeep(np.Value, asset);
                break;
            case EnumPropertyData ep:
                ep.EnumType = TransferOrKeep(ep.EnumType, asset);
                ep.Value = TransferOrKeep(ep.Value, asset);
                break;
            case SoftObjectPropertyData so:
                // FSoftObjectPath/FTopLevelAssetPath are structs; AssetPath
                // carries two FNames, SubPathString is a plain FString.
                so.Value = new FSoftObjectPath(
                    new FTopLevelAssetPath(
                        TransferOrKeep(so.Value.AssetPath.PackageName, asset),
                        TransferOrKeep(so.Value.AssetPath.AssetName, asset)),
                    so.Value.SubPathString);
                break;
        }
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
            Console.WriteLine($"    [dbg] ApplyPatch op={op} path={path}");
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
                        if (prop is BoolPropertyData bp) { bp.Value = val.GetBoolean(); bp.IsZero = !val.GetBoolean(); }
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
            
            case "remove":
            {
                // Vanilla convention for "not hand-carryable": omit bCanPickup
                // entirely (pallets/heavy cargo never serialize the bool; absence
                // = class default False). A serialized False bool is a tag the
                // vanilla loader never normally sees on these CDOs.
                var prop = ResolveProperty(properties, path);
                if (prop != null)
                {
                    properties.Remove(prop);
                    Console.WriteLine($"    Removed property '{path}' ({prop.GetType().Name})");
                }
                else
                {
                    Console.WriteLine($"    remove: property '{path}' not present (no-op)");
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
                // Replace, never mutate: append_struct_clone shares the template's child
                // PropertyData objects, so mutating one writes through to the row it was
                // cloned from (this renamed the stock DriveMaps[0] "Island" and
                // TimeAttackMaps[0] "Town Circuit 1" once already).
                var (cont, dp) = ResolvePropertyWithContainer(properties, path);
                if (dp is TextPropertyData oldText)
                {
                    if (cont != null)
                    {
                        int ci = -1;
                        for (int i = 0; i < cont.Count; i++) if (ReferenceEquals(cont[i], dp)) { ci = i; break; }
                        if (ci >= 0)
                        {
                            var freshText = new TextPropertyData(oldText.Name)
                            {
                                Namespace = FString.FromString(""),
                                Value = FString.FromString(Guid.NewGuid().ToString("N").ToUpper().Substring(0, 32)),
                                CultureInvariantString = FString.FromString(patch.GetProperty("value").GetString()!),
                                HistoryType = TextHistoryType.Base,
                            };
                            freshText.Flags |= ETextFlag.CultureInvariant;
                            cont[ci] = freshText;
                            break;
                        }
                    }
                    SetDescriptionFallback(dp, patch.GetProperty("value").GetString()!);
                }
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
            
            case "set_soft_ref":
            {
                // Vanilla-conformant soft object path (e.g. tire physics assets:
                // /Game/Cars/Parts/Tire/<Name> + <Name>). No import-table entry
                // is needed; the game resolves the package at use time. Writing
                // a hard ObjectPropertyData here desyncs the UE5.5 unversioned
                // header (schema type is FSoftObjectPath) and corrupts the row.
                var (container, prop) = ResolvePropertyWithContainer(properties, path);
                var packageName = patch.GetProperty("package_path").GetString()!;
                var assetName = patch.GetProperty("asset_name").GetString()!;
                var softPath = new FSoftObjectPath(
                    FName.FromString(asset, packageName),
                    FName.FromString(asset, assetName),
                    null);  // vanilla writes a NULL (0-length) SubPathString, not ""
                var leafName = path.Split('.').Last();

                SoftObjectPropertyData newSoft;
                int selfIdx = -1;
                if (container != null)
                    for (int i = 0; i < container.Count; i++)
                        if (ReferenceEquals(container[i], prop)) { selfIdx = i; break; }

                if (prop is SoftObjectPropertyData existing && selfIdx >= 0)
                {
                    // Replace rather than mutate: this property may be shared with the row an
                    // append_struct_clone copied from, and writing through would repoint the
                    // template row at our package.
                    newSoft = new SoftObjectPropertyData(existing.Name) { Value = softPath };
                    newSoft.PropertyTypeName = existing.PropertyTypeName;
                    container![selfIdx] = newSoft;
                }
                else if (prop is SoftObjectPropertyData existing2)
                {
                    existing2.Value = softPath;
                    newSoft = existing2;
                }
                else
                {
                    newSoft = new SoftObjectPropertyData(FName.FromString(asset, leafName)) { Value = softPath };
                    newSoft.PropertyTypeName = MakeTypeName(asset, newSoft.PropertyType);
                    if (container != null)
                    {
                        int ridx = -1;
                        for (int i = 0; i < container.Count; i++)
                            if (ReferenceEquals(container[i], prop)) { ridx = i; break; }
                        if (ridx >= 0) container[ridx] = newSoft;
                        else container.Add(newSoft);
                    }
                    else
                    {
                        properties.Add(newSoft);
                    }
                }
                Console.WriteLine($"    set_soft_ref: {path} -> {packageName}|{assetName}");
                break;
            }
            
            case "set_import_ref":
            case "set_or_create_import_ref":
            {
                var (container, prop) = ResolvePropertyWithContainer(properties, path);
                var addCdoImport = patch.TryGetProperty("add_cdo_import", out var cdoFlag) && cdoFlag.GetBoolean();
                int importIdx2;
                if (patch.TryGetProperty("use_existing_import", out var ueFlag) && ueFlag.GetBoolean())
                {
                    // Reference an existing import by (class_name, asset_name) —
                    // never append anything (zero import-table delta).
                    string dAsset = patch.GetProperty("asset_name").GetString()!;
                    string dClass = patch.GetProperty("class_name").GetString()!;
                    int found = -1;
                    for (int i = 0; i < asset.Imports.Count; i++)
                    {
                        var ast = asset.Imports[i];
                        if (ast.ClassName.Value?.Value == dClass
                            && ast.ObjectName.Value?.Value == dAsset)
                        { found = i + 1; break; }
                    }
                    if (found < 0)
                        throw new InvalidDataException($"use_existing_import: no import {dClass} '{dAsset}'");
                    importIdx2 = found;
                    Console.WriteLine($"  use_existing_import: import [{found}] = {dClass} '{dAsset}'");
                }
                else
                {
                    var (_, importIdx) = AddImportChain(asset,
                        patch.GetProperty("class_package").GetString()!,
                        patch.GetProperty("class_name").GetString()!,
                        patch.GetProperty("package_path").GetString()!,
                        patch.GetProperty("asset_name").GetString()!,
                        addCdoImport);
                    // dedupe_imports: reuse existing imports for the same object
                    // instead of appending duplicates.
                    importIdx2 = importIdx;
                    if (patch.TryGetProperty("dedupe_imports", out var ddFlag) && ddFlag.GetBoolean())
                {
                    string dPkg = patch.GetProperty("package_path").GetString()!;
                    string dAsset = patch.GetProperty("asset_name").GetString()!;
                    string dClass = patch.GetProperty("class_name").GetString()!;
                    for (int i = 0; i + 1 < asset.Imports.Count; i++)
                    {
                        var pkg = asset.Imports[i];
                        var ast = asset.Imports[i + 1];
                        if (pkg.ClassName.Value?.Value == "Package"
                            && pkg.ObjectName.Value?.Value == dPkg
                            && ast.ClassName.Value?.Value == dClass
                            && ast.ObjectName.Value?.Value == dAsset
                            && ast.OuterIndex != null && ast.OuterIndex.Index == -(i + 1))
                        {
                            importIdx2 = i + 2;
                            Console.WriteLine($"  dedupe_imports: reusing import [{importIdx2}] for {dPkg}/{dAsset}");
                            break;
                        }
                    }
                    }
                }
                var pkgIdx = FPackageIndex.FromImport(importIdx2 - 1);

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
                {
                    // Soft paths serialize through the asset's soft-path list;
                    // constructing the null path with raw name indices produced
                    // a stale list index on write (read back as the old ref).
                    // Use the same name-resolution as set_soft_ref.
                    softProp.Value = new FSoftObjectPath(
                        FName.FromString(asset, "None"),
                        FName.FromString(asset, "None"),
                        null);  // vanilla writes a NULL (0-length) SubPathString, not ""
                }
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
            
            case "set_map_entry_soft_object":
            {
                // Replace the value of an EXISTING named map entry with a
                // SoftObject path. Used for Buildings_Furnitures
                // Steps[0].StaticMeshes (key "StaticMesh", value is a
                // SoftObjectPropertyData inherited from the template row).
                var prop = ResolveProperty(properties, path);
                if (prop is MapPropertyData mapProp)
                {
                    var key = patch.GetProperty("key").GetString()!;
                    var found = false;
                    foreach (var kvp in mapProp.Value)
                    {
                        var keyName = kvp.Key.Name?.Value?.Value;
                        var keyValue = (kvp.Key as NamePropertyData)?.Value?.Value?.Value;
                        if ((keyName == key || keyValue == key) &&
                            kvp.Value is SoftObjectPropertyData softVal)
                        {
                            softVal.Value = new FSoftObjectPath(
                                new FTopLevelAssetPath(
                                    FName.FromString(asset, patch.GetProperty("package").GetString()!),
                                    FName.FromString(asset, patch.GetProperty("asset").GetString()!)),
                                null);
                            Console.WriteLine($"    Map entry '{path}[{key}]' -> {patch.GetProperty("package")}/{patch.GetProperty("asset")}");
                            found = true;
                            break;
                        }
                    }
                    if (!found)
                    {
                        var keys = string.Join(", ", mapProp.Value.Keys
                            .Select(k => k.Name?.Value?.Value ?? "?"));
                        Console.WriteLine($"    Warning: set_map_entry_soft_object: no entry '{key}' in {path} (keys: {keys})");
                    }
                }
                break;
            }
            
            case "append_struct_clone":
            {
                var target = ResolveProperty(properties, path) as ArrayPropertyData;
                if (target == null) { Console.WriteLine($"    Warning: append_struct_clone: '{path}' is not an ArrayPropertyData"); break; }
                int ti = patch.TryGetProperty("template_index", out var tEl) ? tEl.GetInt32() : 0;
                if (ti < 0 || ti >= target.Value.Length) { Console.WriteLine($"    Warning: append_struct_clone: template_index {ti} out of range (len {target.Value.Length})"); break; }
                if (target.Value[ti] is not StructPropertyData srcStruct) { Console.WriteLine($"    Warning: append_struct_clone: element {ti} is not a struct"); break; }
                // Shallow list copy is safe ONLY because every field we touch is REPLACED with a
                // freshly constructed property. Mutating a shared child would write through to the
                // template element (it renamed the stock DriveMaps[0] once already).
                var clone = new StructPropertyData(srcStruct.Name, srcStruct.StructType);
                clone.Value = new List<PropertyData>(srcStruct.Value);
                if (patch.TryGetProperty("fields", out var fields) && fields.ValueKind == JsonValueKind.Object)
                {
                    foreach (var f in fields.EnumerateObject())
                    {
                        int idx = clone.Value.FindIndex(p => p.Name?.Value?.Value == f.Name);
                        if (idx < 0) { Console.WriteLine($"    Warning: append_struct_clone: no field '{f.Name}' in template"); continue; }
                        var old = clone.Value[idx];
                        var name = FName.FromString(asset, f.Name);
                        PropertyData? fresh = null;
                        switch (f.Value.ValueKind)
                        {
                            case JsonValueKind.String when old is NamePropertyData:
                                fresh = new NamePropertyData(name) { Value = FName.FromString(asset, f.Value.GetString()!) };
                                break;
                            case JsonValueKind.String when old is StrPropertyData:
                                fresh = new StrPropertyData(name) { Value = FString.FromString(f.Value.GetString()!) };
                                break;
                            case JsonValueKind.True:
                            case JsonValueKind.False when old is BoolPropertyData:
                                fresh = new BoolPropertyData(name) { Value = f.Value.GetBoolean(), IsZero = !f.Value.GetBoolean() };
                                break;
                            case JsonValueKind.Object when old is SoftObjectPropertyData:
                                fresh = new SoftObjectPropertyData(name)
                                {
                                    Value = new FSoftObjectPath(
                                        new FTopLevelAssetPath(
                                            FName.FromString(asset, f.Value.GetProperty("package").GetString()!),
                                            FName.FromString(asset, f.Value.GetProperty("asset").GetString()!)),
                                        null)
                                };
                                break;
                            case JsonValueKind.String when old is TextPropertyData:
                                // Fresh Text (never mutate the template's shared child):
                                // CultureInvariant fallback text, like SetDescriptionFallback.
                                fresh = new TextPropertyData(name)
                                {
                                    Namespace = FString.FromString(""),
                                    Value = FString.FromString(Guid.NewGuid().ToString("N").ToUpper().Substring(0, 32)),
                                    CultureInvariantString = FString.FromString(f.Value.GetString()!),
                                    HistoryType = TextHistoryType.Base,
                                };
                                ((TextPropertyData)fresh).Flags |= ETextFlag.CultureInvariant;
                                break;
                            case JsonValueKind.Number when old is FloatPropertyData:
                                fresh = new FloatPropertyData(name) { Value = f.Value.GetSingle() };
                                break;
                        }
                        if (fresh == null) { Console.WriteLine($"    Warning: append_struct_clone: cannot set '{f.Name}' ({old.GetType().Name})"); continue; }
                        clone.Value[idx] = fresh;
                    }
                }
                target.Value = target.Value.Append(clone).ToArray();
                Console.WriteLine($"    appended struct to '{path}' (now {target.Value.Length} entries)");
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
                    
                    // Clone the last existing element and swap its Value — constructing
                    // a property from scratch fabricates an FName that corrupts
                    // unversioned (schema-driven) serialization on the client build.
                    var last = arr.Value.Length > 0 ? arr.Value[arr.Value.Length - 1] : null;
                    PropertyData newEntry;
                    if (last != null)
                    {
                        newEntry = (PropertyData)last.Clone();
                        if (newEntry is ObjectPropertyData opd)
                            opd.Value = FPackageIndex.FromImport(importIdx - 1);
                    }
                    else
                    {
                        var opd = new ObjectPropertyData(FName.FromString(asset, arr.Value.Length.ToString()))
                        {
                            Value = FPackageIndex.FromImport(importIdx - 1)
                        };
                        opd.PropertyTypeName = MakeTypeName(asset, opd.PropertyType);
                        newEntry = opd;
                    }

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
                            // Vanilla serializes LevelRequirementToBuy keys as
                            // EnumPropertyData with the license name as the
                            // enum VALUE (e.g. CL_Police). Property name must
                            // stay the map's leaf name; writing the license
                            // into the ctor arg corrupts the header.
                            var keyProp = new EnumPropertyData(new FName(asset, leafName, 0))
                            {
                                Value = FName.FromString(asset, entry.Name),
                                PropertyTypeName = MakeTypeName(asset, new FString("EnumProperty"))
                            };
                            var valProp = new IntPropertyData(new FName(asset, leafName, 0))
                            { Value = entry.Value.GetInt32() };
                            valProp.PropertyTypeName = MakeTypeName(asset, valProp.PropertyType);
                            mapProp.Value.Add(keyProp, valProp);
                        }
                    }
                }
                break;
            }
            
            case "set_map_entries":
            {
                // Replace the contents of a MapPropertyData with explicit
                // entries. Needed for Name->Enum maps (e.g.
                // FMTVehicleDiffLockingState's Differentials map: diff
                // component name -> EMTDiffLockStateType), which add_map_entry
                // cannot write — it infers value types from existing Name/Str
                // values only. Key/value property types are cloned from the
                // map's first existing entry when present; fresh Name/Enum
                // construction as fallback ('enum_type' names the enum).
                var prop = ResolveProperty(properties, path);
                if (prop is MapPropertyData mapProp)
                {
                    var leafName = path.Split('.').Last();
                    var templateKey = mapProp.Value.Keys.FirstOrDefault();
                    var templateVal = mapProp.Value.Values.FirstOrDefault();
                    var enumTypeName = patch.TryGetProperty("enum_type", out var etProp) ? etProp.GetString() : null;
                    if (enumTypeName == null && templateVal is EnumPropertyData ev0)
                        enumTypeName = ev0.EnumType?.Value?.Value;

                    var newMap = new TMap<PropertyData, PropertyData>();
                    foreach (var entry in patch.GetProperty("entries").EnumerateObject())
                    {
                        var entryVal = entry.Value.GetString()!;
                        PropertyData keyProp;
                        if (templateKey is NamePropertyData nk)
                        {
                            keyProp = (NamePropertyData)nk.Clone();
                            ((NamePropertyData)keyProp).Value = FName.FromString(asset, entry.Name);
                        }
                        else
                        {
                            keyProp = new NamePropertyData(new FName(asset, leafName, 0))
                            {
                                Value = FName.FromString(asset, entry.Name)
                            };
                            ((NamePropertyData)keyProp).PropertyTypeName = MakeTypeName(asset, keyProp.PropertyType);
                        }

                        PropertyData valProp;
                        if (templateVal is EnumPropertyData ev)
                        {
                            valProp = (EnumPropertyData)ev.Clone();
                            ((EnumPropertyData)valProp).Value = FName.FromString(asset, entryVal);
                            if (enumTypeName != null)
                                ((EnumPropertyData)valProp).EnumType = FName.FromString(asset, enumTypeName);
                        }
                        else if (templateVal is NamePropertyData nv)
                        {
                            valProp = (NamePropertyData)nv.Clone();
                            ((NamePropertyData)valProp).Value = FName.FromString(asset, entryVal);
                        }
                        else
                        {
                            if (enumTypeName == null)
                            {
                                Console.WriteLine("    Error: set_map_entries needs 'enum_type' when the map has no existing enum value to infer from");
                                break;
                            }
                            valProp = new EnumPropertyData(new FName(asset, leafName, 0))
                            {
                                EnumType = FName.FromString(asset, enumTypeName),
                                Value = FName.FromString(asset, entryVal)
                            };
                            ((EnumPropertyData)valProp).PropertyTypeName = MakeTypeName(asset, valProp.PropertyType);
                        }

                        newMap.Add(keyProp, valProp);
                    }
                    mapProp.Value = newMap;
                    var summary = string.Join(", ", newMap.Select(kvp => $"{kvp.Key}={kvp.Value}"));
                    Console.WriteLine($"    set_map_entries: {path} -> [{summary}]");
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
                    Console.WriteLine(ex.StackTrace ?? "(no stack)");
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
            // CultureInvariant flag (2) makes the engine fall back to the source string
            // instead of showing nothing for a key that has no localization entry.
            nameTxt.Flags |= ETextFlag.CultureInvariant;
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
                        // CultureInvariant flag: engine falls back to source string when
                        // the loc key has no entry (working police-tyres rows carry this).
                        textProp.Flags |= ETextFlag.CultureInvariant;
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
            descTxt.Flags |= ETextFlag.CultureInvariant;
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
    
    // --retarget-mis <inDir> <outDir>
    // Reparent every cooked MaterialInstanceConstant under inDir to a vanilla Motor Town
    // master material and remap our texture parameter names onto that master's parameter
    // set. Rationale: shader maps cooked in a separate project are rejected by Motor Town
    // (uncooked shader map ID -> default material, magenta test proved it), whereas a
    // master MT itself ships already has shaders the game owns and resolves.
    // Rename a texture parameter across a directory of material instances, in place of
    // re-authoring them in the editor. Used when an instance binds a parameter name the
    // master does not expose: the bind silently does nothing and the material renders the
    // master default (white), which is indistinguishable from "the texture is missing".
    static void RenameTextureParam(string inDir, string outDir, string from, string to)
    {
        Directory.CreateDirectory(outDir);
        int changed = 0, scanned = 0, failed = 0;
        foreach (var path in Directory.GetFiles(inDir, "*.uasset", SearchOption.AllDirectories))
        {
            scanned++;
            try
            {
                var asset = new UAsset(path, EngineVersion.VER_UE5_5, Mappings);
                var exp = asset.Exports.OfType<NormalExport>().FirstOrDefault();
                var arr = exp?.Data.OfType<ArrayPropertyData>()
                    .FirstOrDefault(p => p.Name?.Value?.Value == "TextureParameterValues");
                bool hit = false;
                if (arr != null)
                {
                    foreach (var el in arr.Value)
                    {
                        var sp = el as StructPropertyData;
                        if (sp == null) continue;
                        var info = sp.Value.OfType<StructPropertyData>()
                            .FirstOrDefault(s => s.Name?.Value?.Value == "ParameterInfo");
                        var nm = info?.Value.OfType<NamePropertyData>()
                            .FirstOrDefault(n => n.Name?.Value?.Value == "Name");
                        if (nm?.Value?.ToString() == from)
                        {
                            nm.Value = FName.FromString(asset, to);
                            hit = true;
                        }
                    }
                }
                asset.Write(Path.Combine(outDir, Path.GetFileName(path)));
                if (hit) changed++;
            }
            catch (Exception ex) { Console.WriteLine($"FAIL {Path.GetFileName(path)}: {ex.Message}"); failed++; }
        }
        Console.WriteLine($"rename_texture_param scanned={scanned} changed={changed} failed={failed} {from}->{to}");
    }

    // Move translucent material instances onto the translucent master and give each one an
    // OpacityTex binding. Instances that already carry the coverage in a separate opacity map
    // just need their "Opacity" parameter renamed; ones whose coverage lives in the colour
    // map's alpha reuse the BaseColor texture, cloned into a second parameter.
    static void TransMIs(string inDir, string outDir, string listFile, string masterPkg, string masterName)
    {
        Directory.CreateDirectory(outDir);
        var wanted = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        if (listFile != "-" && File.Exists(listFile))
            foreach (var line in File.ReadAllLines(listFile))
            {
                var t = line.Trim();
                if (t.Length != 0 && !t.StartsWith("#")) wanted.Add(t);
            }

        int changed = 0, copied = 0, renamed = 0, cloned = 0, failed = 0;
        foreach (var path in Directory.GetFiles(inDir, "*.uasset", SearchOption.AllDirectories))
        {
            var stem = Path.GetFileNameWithoutExtension(path);
            var uexp = Path.ChangeExtension(path, ".uexp");
            if (!wanted.Contains(stem))
            {
                File.Copy(path, Path.Combine(outDir, Path.GetFileName(path)), true);
                if (File.Exists(uexp)) File.Copy(uexp, Path.Combine(outDir, Path.GetFileName(uexp)), true);
                copied++;
                continue;
            }

            try
            {
                var asset = new UAsset(path, EngineVersion.VER_UE5_5, Mappings);
                var exp = asset.Exports.OfType<NormalExport>().FirstOrDefault();
                if (exp == null) { Console.WriteLine($"SKIP {stem}: no export"); failed++; continue; }

                var parentProp = exp.Data.OfType<ObjectPropertyData>()
                    .FirstOrDefault(p => p.Name?.Value?.Value == "Parent");
                if (parentProp == null) { Console.WriteLine($"SKIP {stem}: no Parent"); failed++; continue; }
                var (_, idx) = AddImportChain(asset, "/Script/Engine", "Material", masterPkg, masterName);
                parentProp.Value = FPackageIndex.FromImport(idx - 1);

                var arr = exp.Data.OfType<ArrayPropertyData>()
                    .FirstOrDefault(p => p.Name?.Value?.Value == "TextureParameterValues");
                StructPropertyData baseEntry = null;
                bool didRename = false;
                if (arr != null)
                {
                    foreach (var el in arr.Value)
                    {
                        var sp = el as StructPropertyData;
                        var nm = sp?.Value.OfType<StructPropertyData>()
                            .FirstOrDefault(s => s.Name?.Value?.Value == "ParameterInfo")?
                            .Value.OfType<NamePropertyData>()
                            .FirstOrDefault(n => n.Name?.Value?.Value == "Name");
                        if (nm == null) continue;
                        var cur = nm.Value?.ToString();
                        if (cur == "Opacity") { nm.Value = FName.FromString(asset, "OpacityTex"); didRename = true; renamed++; }
                        if (cur == "BaseColor") baseEntry = sp;
                    }

                    if (!didRename && baseEntry != null)
                    {
                        // Clone the BaseColor entry, then swap in a fresh ParameterInfo so the
                        // shared child properties are not written through to the original.
                        var clone = new StructPropertyData(baseEntry.Name, baseEntry.StructType)
                        {
                            Value = new List<PropertyData>(baseEntry.Value)
                        };
                        for (int i = 0; i < clone.Value.Count; i++)
                        {
                            if (clone.Value[i] is not StructPropertyData info) continue;
                            if (info.Name?.Value?.Value != "ParameterInfo") continue;
                            var freshInfo = new StructPropertyData(info.Name, info.StructType)
                            {
                                Value = new List<PropertyData>(info.Value)
                            };
                            for (int j = 0; j < freshInfo.Value.Count; j++)
                            {
                                if (freshInfo.Value[j] is NamePropertyData np && np.Name?.Value?.Value == "Name")
                                    freshInfo.Value[j] = new NamePropertyData(np.Name) { Value = FName.FromString(asset, "OpacityTex") };
                            }
                            clone.Value[i] = freshInfo;
                        }
                        arr.Value = arr.Value.Concat(new PropertyData[] { clone }).ToArray();
                        cloned++;
                    }
                }

                asset.Write(Path.Combine(outDir, Path.GetFileName(path)));
                changed++;
            }
            catch (Exception ex) { Console.WriteLine($"FAIL {stem}: {ex.Message}"); failed++; }
        }
        Console.WriteLine($"trans_mis changed={changed} copied={copied} renamed={renamed} cloned={cloned} failed={failed} master={masterName}");
    }

    // Point a named set of material instances at a specific master, leaving every other
    // instance in the directory byte-identical. Used to split cutout materials by how
    // their mask is stored: alpha in the colour map (MT's foliage master reads it) vs a
    // separate opacity texture (needs a master that samples that texture).
    // Write the per-instance blend override only. MT masters ship opaque; an instance that
    // inherits that paints its texture's backdrop (the "green square" foliage case). Parent,
    // parameter names and parameter values are left exactly as they are -- this is the
    // surgical counterpart to RetargetMIs, which reparents and renames at the same time.
    // Drop the per-instance BasePropertyOverrides block so the instance inherits the parent
    // material's own blend state. Unreal treats blend mode / two-sided / mask clip as compiled
    // state (MaterialInstanceBasePropertyOverrides), NOT as parameters: a cooked game cannot
    // build a new permutation, and the failure surfaces as a missing-shader lookup (UE-39754).
    // For a mod pak the only correct move is to let an already-masked parent supply the blend.
    static void ClearOverrides(string inDir, string outDir, string listFile)
    {
        Directory.CreateDirectory(outDir);
        var wanted = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        if (listFile != "-" && File.Exists(listFile))
            foreach (var line in File.ReadAllLines(listFile))
            {
                var t = line.Trim();
                if (t.Length != 0 && !t.StartsWith("#")) wanted.Add(t);
            }

        int cleared = 0, copied = 0, failed = 0;
        foreach (var path in Directory.GetFiles(inDir, "*.uasset", SearchOption.AllDirectories))
        {
            var stem = Path.GetFileNameWithoutExtension(path);
            var uexp = Path.ChangeExtension(path, ".uexp");
            try
            {
                if (!wanted.Contains(stem))
                {
                    File.Copy(path, Path.Combine(outDir, Path.GetFileName(path)), true);
                    if (File.Exists(uexp)) File.Copy(uexp, Path.Combine(outDir, Path.GetFileName(uexp)), true);
                    copied++;
                    continue;
                }

                var asset = new UAsset(path, EngineVersion.VER_UE5_5, Mappings);
                var exp = asset.Exports.OfType<NormalExport>().FirstOrDefault();
                if (exp == null) { Console.WriteLine("SKIP " + stem + ": no export"); failed++; continue; }

                var removed = exp.Data.RemoveAll(p => p.Name?.Value?.Value == "BasePropertyOverrides");
                cleared += removed;
                var target = Path.Combine(outDir, Path.GetFileName(path));
                asset.Write(target);
                var newUexp = Path.ChangeExtension(target, ".uexp");
                if (File.Exists(newUexp) == false && File.Exists(uexp))
                {
                    Console.WriteLine("WARN " + stem + ": no written uexp");
                }
            }
            catch (Exception ex) { Console.WriteLine($"FAIL {stem}: {ex.Message}"); failed++; }
        }
        Console.WriteLine($"clear_overrides props_removed={cleared} copied={copied} failed={failed}");
    }

    static void SetBlend(string inDir, string outDir, string listFile, string mode, string[] scalars = null)
    {
        bool trans = mode.Equals("translucent", StringComparison.OrdinalIgnoreCase);
        bool masked = mode.Equals("masked", StringComparison.OrdinalIgnoreCase);
        if (!trans && !masked) { Console.WriteLine("FAIL: mode must be masked|translucent"); return; }
        Console.WriteLine("set_blend start mode=" + mode + " scalars=" + (scalars == null ? "null" : string.Join(",", scalars)));

        Directory.CreateDirectory(outDir);
        var wanted = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        if (listFile != "-" && File.Exists(listFile))
            foreach (var line in File.ReadAllLines(listFile))
            {
                var t = line.Trim();
                if (t.Length != 0 && !t.StartsWith("#")) wanted.Add(t);
            }

        int changed = 0, copied = 0, failed = 0;
        foreach (var path in Directory.GetFiles(inDir, "*.uasset", SearchOption.AllDirectories))
        {
            var stem = Path.GetFileNameWithoutExtension(path);
            var uexp = Path.ChangeExtension(path, ".uexp");
            try
            {
                if (!wanted.Contains(stem))
                {
                    File.Copy(path, Path.Combine(outDir, Path.GetFileName(path)), true);
                    if (File.Exists(uexp)) File.Copy(uexp, Path.Combine(outDir, Path.GetFileName(uexp)), true);
                    copied++;
                    continue;
                }

                var asset = new UAsset(path, EngineVersion.VER_UE5_5, Mappings);
                var exp = asset.Exports.OfType<NormalExport>().FirstOrDefault();
                if (exp == null) { Console.WriteLine("SKIP " + stem + ": no export"); failed++; continue; }
                var props = exp.Data;

                props.RemoveAll(p => p.Name?.Value?.Value == "BasePropertyOverrides");
                var overrides = new StructPropertyData(FName.FromString(asset, "BasePropertyOverrides"))
                {
                    StructType = FName.FromString(asset, "MaterialInstanceBasePropertyOverrides")
                };
                var blend = new EnumPropertyData(FName.FromString(asset, "BlendMode"))
                {
                    Value = FName.FromString(asset, trans ? "BLEND_Translucent" : "BLEND_Masked"),
                    EnumType = FName.FromString(asset, "EBlendMode")
                };
                blend.PropertyTypeName = MakeTypeName(asset, blend.PropertyType);
                var two = new BoolPropertyData(FName.FromString(asset, "TwoSided")) { Value = true, IsZero = false };
                two.PropertyTypeName = MakeTypeName(asset, two.PropertyType);
                var clip = new FloatPropertyData(FName.FromString(asset, "OpacityMaskClipValue")) { Value = 0.3333f };
                clip.PropertyTypeName = MakeTypeName(asset, clip.PropertyType);

                overrides.Value.Add(blend);
                overrides.Value.Add(two);
                overrides.Value.Add(clip);
                overrides.PropertyTypeName = MakeTypeName(asset, overrides.PropertyType);
                props.Add(overrides);

                // Optional scalar overrides, e.g. Opacity=0.8 for paint that must blend into
                // the road instead of sitting on it as a solid plate. Clones an existing
                // scalar struct: a freshly built one has no ancestry and cannot serialise.
                if (scalars != null && scalars.Length > 0)
                {
                    var arr = props.OfType<ArrayPropertyData>()
                                   .FirstOrDefault(p => p.Name?.Value?.Value == "ScalarParameterValues");
                    StructPropertyData proto = arr?.Value.OfType<StructPropertyData>().FirstOrDefault()
                        ?? props.OfType<ArrayPropertyData>()
                               .FirstOrDefault(p => p.Name?.Value?.Value == "TextureParameterValues")
                               ?.Value.OfType<StructPropertyData>().FirstOrDefault();
                    if (proto == null) { Console.WriteLine("SKIP " + stem + ": no scalar proto"); failed++; continue; }

                    if (arr == null)
                    {
                        // No scalar array yet: clone the texture array (same element struct type)
                        // and empty it, rather than building a struct with no ancestry.
                        var texArr = props.OfType<ArrayPropertyData>()
                            .First(p => p.Name?.Value?.Value == "TextureParameterValues");
                        arr = (ArrayPropertyData)texArr.Clone();
                        arr.Name = FName.FromString(asset, "ScalarParameterValues");
                        arr.Value = Array.Empty<PropertyData>();
                        props.Add(arr);
                    }
                    foreach (var spec in scalars)
                    {
                        var eq = spec.IndexOf('=');
                        if (eq <= 0) continue;
                        var pname = spec.Substring(0, eq);
                        if (!float.TryParse(spec.Substring(eq + 1), out var val)) continue;
                        var clone = (StructPropertyData)proto.Clone();
                        var info = clone.Value.OfType<StructPropertyData>()
                                        .First(p => p.Name?.Value?.Value == "ParameterInfo");
                        var nprop = info.Value.OfType<NamePropertyData>()
                                          .First(p => p.Name?.Value?.Value == "Name");
                        nprop.Value = FName.FromString(asset, pname);
                        clone.Value.RemoveAll(p => p.Name?.Value?.Value == "ParameterValue");
                        var f = new FloatPropertyData(FName.FromString(asset, "ParameterValue")) { Value = val };
                        f.PropertyTypeName = MakeTypeName(asset, f.PropertyType);
                        clone.Value.Add(f);
                        arr.Value = arr.Value.Append(clone).ToArray();
                    }
                }

                asset.Write(Path.Combine(outDir, Path.GetFileName(path)));
                changed++;
            }
            catch (Exception ex) { Console.WriteLine("FAIL " + stem + ": " + ex.Message); failed++; }
        }
        Console.WriteLine($"set_blend changed={changed} copied={copied} failed={failed} mode={mode}");
    }

    // --set-clip <inDir> <outDir> <listFile>
    // listFile lines: "<MaterialInstanceName>\t<clip>" (or the name alone for the default).
    // Why: BeamNG gives every alpha-tested material its own alphaRef (0-255); the port must carry
    // that threshold as OpacityMaskClipValue = alphaRef/255 or the cut is wrong in both directions.
    static void SetClip(string inDir, string outDir, string listFile)
    {
        Directory.CreateDirectory(outDir);
        var wanted = new Dictionary<string, float>(StringComparer.OrdinalIgnoreCase);
        if (listFile != "-" && File.Exists(listFile))
            foreach (var line in File.ReadAllLines(listFile))
            {
                var t = line.Trim();
                if (t.Length == 0 || t.StartsWith("#")) continue;
                var parts = t.Split('\t', StringSplitOptions.RemoveEmptyEntries);
                var name = parts[0].Trim();
                var clip = 0.3333f;
                if (parts.Length > 1 && float.TryParse(parts[1].Trim(),
                        System.Globalization.NumberStyles.Float,
                        System.Globalization.CultureInfo.InvariantCulture, out var c)) clip = c;
                wanted[name] = clip;
            }

        int changed = 0, copied = 0, failed = 0;
        foreach (var path in Directory.GetFiles(inDir, "*.uasset", SearchOption.AllDirectories))
        {
            var stem = Path.GetFileNameWithoutExtension(path);
            var uexp = Path.ChangeExtension(path, ".uexp");
            try
            {
                if (!wanted.TryGetValue(stem, out var clipValue))
                {
                    File.Copy(path, Path.Combine(outDir, Path.GetFileName(path)), true);
                    if (File.Exists(uexp)) File.Copy(uexp, Path.Combine(outDir, Path.GetFileName(uexp)), true);
                    copied++;
                    continue;
                }

                var asset = new UAsset(path, EngineVersion.VER_UE5_5, Mappings);
                var exp = asset.Exports.OfType<NormalExport>().FirstOrDefault();
                if (exp == null) { Console.WriteLine("SKIP " + stem + ": no export"); failed++; continue; }
                var props = exp.Data;

                props.RemoveAll(p => p.Name?.Value?.Value == "BasePropertyOverrides");
                var overrides = new StructPropertyData(FName.FromString(asset, "BasePropertyOverrides"))
                {
                    StructType = FName.FromString(asset, "MaterialInstanceBasePropertyOverrides")
                };
                var blend = new EnumPropertyData(FName.FromString(asset, "BlendMode"))
                {
                    Value = FName.FromString(asset, "BLEND_Masked"),
                    EnumType = FName.FromString(asset, "EBlendMode")
                };
                blend.PropertyTypeName = MakeTypeName(asset, blend.PropertyType);
                var two = new BoolPropertyData(FName.FromString(asset, "TwoSided")) { Value = true, IsZero = false };
                two.PropertyTypeName = MakeTypeName(asset, two.PropertyType);
                var clip = new FloatPropertyData(FName.FromString(asset, "OpacityMaskClipValue")) { Value = clipValue };
                clip.PropertyTypeName = MakeTypeName(asset, clip.PropertyType);

                overrides.Value.Add(blend);
                overrides.Value.Add(two);
                overrides.Value.Add(clip);
                overrides.PropertyTypeName = MakeTypeName(asset, overrides.PropertyType);
                props.Add(overrides);

                asset.Write(Path.Combine(outDir, Path.GetFileName(path)));
                changed++;
            }
            catch (Exception ex) { Console.WriteLine("FAIL " + stem + ": " + ex.Message); failed++; }
        }
        Console.WriteLine($"set_clip changed={changed} copied={copied} failed={failed}");
    }

    // --apply-plan <inDir> <outDir> <plan.json>
    //
    // One pass, one row at a time, from the compiled plan. Every previous attempt applied a batch
    // with a single set of overrides, which is how 1,653 instances ended up with TwoSided=true and
    // a uniform clip. Here the parent, the colour parameter NAME and the overrides all come from
    // the row, so an instance can never inherit another instance's decision.
    // Point a static mesh material slot at a real material instance. The BeamNG->UE conversion left
    // slots holding the correct slot NAME but bound to WorldGridMaterial, so those triangles render
    // as the engine's flat gray while the rest of the mesh looks right.
    static void RetargetMaterials(string inDir, string configPath, string outDir)
    {
        Directory.CreateDirectory(outDir);
        using var doc = System.Text.Json.JsonDocument.Parse(File.ReadAllText(configPath));
        int changed = 0, missed = 0;
        foreach (var rule in doc.RootElement.GetProperty("rules").EnumerateArray())
        {
            var mesh = rule.GetProperty("mesh").GetString();
            var slot = rule.GetProperty("slot").GetString();
            var miPkg = rule.GetProperty("mi_package").GetString();
            var miName = rule.GetProperty("mi_name").GetString();
            var path = Path.Combine(inDir, mesh + ".uasset");
            var uexp = Path.Combine(inDir, mesh + ".uexp");
            if (!File.Exists(path)) { Console.WriteLine($"MISS {mesh}"); missed++; continue; }
            var asset = new UAsset(path, EngineVersion.VER_UE5_5, Mappings);
            // The StaticMesh export is not necessarily the first one (BodySetup and NavCollision
            // often precede it), so search every export for the material slot array.
            ArrayPropertyData mats = null;
            foreach (var e in asset.Exports.OfType<NormalExport>())
            {
                mats = e.Data.OfType<ArrayPropertyData>().FirstOrDefault(a => a.Name?.Value?.Value == "StaticMaterials");
                if (mats != null) break;
            }
            if (mats == null) { Console.WriteLine($"NOMAT {mesh}"); missed++; continue; }
            var (_, idx) = AddImportChain(asset, "/Script/Engine", "MaterialInstanceConstant", miPkg, miName);
            int hit = 0;
            foreach (var el in mats.Value.OfType<StructPropertyData>())
            {
                var nm = el.Value.OfType<NamePropertyData>().FirstOrDefault(n => n.Name?.Value?.Value == "MaterialSlotName");
                if (nm == null || nm.Value.ToString() != slot) continue;
                var iface = el.Value.OfType<ObjectPropertyData>().FirstOrDefault(o => o.Name?.Value?.Value == "MaterialInterface");
                if (iface == null) continue;
                iface.Value = FPackageIndex.FromImport(idx - 1);
                hit++;
            }
            if (hit == 0) { Console.WriteLine($"NOSLOT {mesh} {slot}"); missed++; continue; }
            // asset.Write emits BOTH halves. Copying the original .uexp afterwards is the trap that
            // silently reverted every material edit once: the payload lives in .uexp.
            asset.Write(Path.Combine(outDir, mesh + ".uasset"));
            Console.WriteLine($"RETARGET {mesh} {slot} -> {miName} x{hit}");
            changed++;
        }
        Console.WriteLine($"retarget_materials changed={changed} problems={missed}");
    }

    // One row per material instance: what the shipped asset actually says, so an audit compares
    // serialized reality against the plan instead of trusting the build counters.
    static void AuditMaterials(string dir, string outTsv)
    {
        var lines = new List<string> { "mi\tparent\tblend\ttwo_sided\tclip\toverride_block\ttexture_params" };
        int n = 0, bad = 0;
        foreach (var path in Directory.GetFiles(dir, "*.uasset").OrderBy(p => p))
        {
            var mi = Path.GetFileNameWithoutExtension(path);
            try
            {
                var asset = new UAsset(path, EngineVersion.VER_UE5_5, Mappings);
                var exp = asset.Exports.OfType<NormalExport>().FirstOrDefault();
                if (exp == null) { lines.Add($"{mi}\tNO_EXPORT\t-\t-\t-\t-"); bad++; continue; }
                var props = exp.Data;
                var parentProp = props.OfType<ObjectPropertyData>().FirstOrDefault(p => p.Name?.Value?.Value == "Parent");
                var parent = ParentPath(asset, parentProp) ?? "-";
                var ov = props.OfType<StructPropertyData>().FirstOrDefault(s => s.Name?.Value?.Value == "BasePropertyOverrides");
                string blend = "-", two = "-", clip = "-";
                // A texture bound to a parameter name the master does not expose is a dead binding:
                // the engine ignores it and the master's default texture shows instead. That is the
                // "material renders in a flat colour" family in one line.
                var tparr = props.OfType<ArrayPropertyData>().FirstOrDefault(a => a.Name?.Value?.Value == "TextureParameterValues");
                var pnames = new List<string>();
                if (tparr != null)
                    foreach (var el in tparr.Value.OfType<StructPropertyData>())
                    {
                        var info = el.Value.OfType<StructPropertyData>().FirstOrDefault(s => s.Name?.Value?.Value == "ParameterInfo");
                        var nm = info?.Value.OfType<NamePropertyData>().FirstOrDefault();
                        if (nm != null) pnames.Add(nm.Value.ToString());
                    }
                if (ov != null)
                {
                    var b = ov.Value.OfType<EnumPropertyData>().FirstOrDefault(x => x.Name?.Value?.Value == "BlendMode");
                    if (b != null) blend = b.Value?.ToString() ?? "-";
                    var t = ov.Value.OfType<BoolPropertyData>().FirstOrDefault(x => x.Name?.Value?.Value == "TwoSided");
                    if (t != null) two = t.Value ? "1" : "0";
                    var c = ov.Value.OfType<FloatPropertyData>().FirstOrDefault(x => x.Name?.Value?.Value == "OpacityMaskClipValue");
                    if (c != null) clip = c.Value.ToString("0.####", System.Globalization.CultureInfo.InvariantCulture);
                }
                lines.Add($"{mi}\t{parent}\t{blend}\t{two}\t{clip}\t{(ov != null ? 1 : 0)}\t{string.Join(",", pnames)}");
                n++;
            }
            catch (Exception e) { lines.Add($"{mi}\tERROR:{e.GetType().Name}\t-\t-\t-\t-"); bad++; }
        }
        File.WriteAllLines(outTsv, lines);
        Console.WriteLine($"audit_materials rows={n} problems={bad} out={outTsv}");
    }

    // Full object path of whatever an instance is currently parented to, e.g.
    // "/Game/Env/Materials/Master/M_PropMaster" (null when unresolved). The package import holds the
    // directory and the parent import holds only the asset name, so the two must be joined.
    static string ParentPath(UAsset asset, ObjectPropertyData parent)
    {
        // FPackageIndex encodes imports as NEGATIVE numbers: -9 means the 9th import (1-based).
        // Reading `Index <= 0` as "no parent" silently disabled the whole keep-parent rule.
        if (parent == null) return null;
        int ip = -parent.Value.Index;
        if (ip <= 0 || ip > asset.Imports.Count) return null;
        var pim = asset.Imports[ip - 1];
        var name = pim.ObjectName?.Value?.Value;
        if (name == null) return null;
        // A package import's name IS the full object path ("/Game/Env/.../M_PropMaster"); only the
        // Material import carries the bare name. Return the package path, never the two joined —
        // joining produces ".../M_PropMaster/M_PropMaster" and matches nothing.
        int op = -(pim.OuterIndex?.Index ?? 0);
        if (op > 0 && op <= asset.Imports.Count)
        {
            var dir = asset.Imports[op - 1].ObjectName?.Value?.Value;
            if (!string.IsNullOrEmpty(dir)) return dir;
        }
        return name;
    }

    static void ApplyPlan(string inDir, string outDir, string planPath, string mastersFile = null)
    {
        Directory.CreateDirectory(outDir);
        // Packages of Material assets that actually exist in the shipped game. An opaque instance
        // already parented to one of these renders; reparenting it is a change with no reason.
        var liveMasters = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        if (mastersFile != null && File.Exists(mastersFile))
            foreach (var line in File.ReadAllLines(mastersFile))
            { var t = line.Trim(); if (t.Length != 0) liveMasters.Add(t); }
        using var doc = System.Text.Json.JsonDocument.Parse(File.ReadAllText(planPath));
        var rows = new Dictionary<string, System.Text.Json.JsonElement>(StringComparer.OrdinalIgnoreCase);
        foreach (var r in doc.RootElement.GetProperty("rows").EnumerateArray())
            rows[r.GetProperty("mi").GetString() ?? ""] = r.Clone();

        int changed = 0, copied = 0, failed = 0, reparented = 0, renamed = 0, overridden = 0, keptElse = 0;
        foreach (var path in Directory.GetFiles(inDir, "*.uasset", SearchOption.AllDirectories))
        {
            var stem = Path.GetFileNameWithoutExtension(path);
            var uexp = Path.ChangeExtension(path, ".uexp");
            if (!rows.TryGetValue(stem, out var row)) { CopyPair(path, uexp, outDir); copied++; continue; }
            var treatment = row.TryGetProperty("treatment", out var tEl) ? tEl.GetString() ?? "" : "";
            if (treatment == "keep_authored" || treatment == "translucent_keep" || treatment == "")
            {
                CopyPair(path, uexp, outDir); copied++; continue;
            }
            try
            {
                var asset = new UAsset(path, EngineVersion.VER_UE5_5, Mappings);
                var exp = asset.Exports.OfType<NormalExport>().FirstOrDefault();
                if (exp == null) { CopyPair(path, uexp, outDir); Console.WriteLine("SKIP " + stem + ": no export"); failed++; continue; }
                var props = exp.Data;

                var master = row.GetProperty("master");
                var pkg = master.GetProperty("pkg").GetString() ?? "";
                var masterName = master.GetProperty("name").GetString() ?? "";
                var colourParam = master.TryGetProperty("colour_param", out var cpEl) ? cpEl.GetString() : null;

                // ---- parent ------------------------------------------------------------------
                var parent = props.OfType<ObjectPropertyData>().FirstOrDefault(p => p.Name?.Value?.Value == "Parent");
                // An opaque instance already parented to a master that ships in the game renders
                // correctly today. Reparenting it is a change with no reason behind it — that is how
                // the concrete and median-guardrail families lost their textures, because
                // M_PolygonMaster was chosen on a NameMap guess that never had a texture bound to it.
                var curPath = ParentPath(asset, parent);
                bool keepParent = treatment == "opaque" && curPath != null && liveMasters.Contains(curPath);
                if (keepParent) keptElse++;
                else
                {
                    // Reuse an existing import of the master if one is already there; AddImportChain
                    // does not dedupe and a second copy only bloats the table the engine resolves.
                    int reuse = 0;
                    for (int i = 0; i < asset.Imports.Count; i++)
                    {
                        var im = asset.Imports[i];
                        if (im.ObjectName?.Value?.Value == masterName
                            && im.ClassName?.Value?.Value == "Material"
                            && im.ClassPackage?.Value?.Value == "/Script/Engine")
                        { reuse = i + 1; break; }
                    }
                    int idx;
                    if (reuse > 0) idx = reuse;
                    else { var (_, ni) = AddImportChain(asset, "/Script/Engine", "Material", pkg, masterName); idx = ni; }
                    if (parent != null) { parent.Value = FPackageIndex.FromImport(idx - 1); reparented++; }
                }

                // ---- colour parameter name (belongs to the MASTER, never to the project) ------
                var arr = props.OfType<ArrayPropertyData>().FirstOrDefault(a => a.Name.Value.Value == "TextureParameterValues");
                if (!keepParent && arr != null && !string.IsNullOrEmpty(colourParam))
                    foreach (var el in arr.Value.OfType<StructPropertyData>())
                    {
                        var info = el.Value.OfType<StructPropertyData>().FirstOrDefault(s => s.Name.Value.Value == "ParameterInfo");
                        var nm = info?.Value.OfType<NamePropertyData>().FirstOrDefault();
                        if (nm == null) continue;
                        var cur = nm.Value.ToString();
                        if (string.Equals(cur, colourParam, StringComparison.OrdinalIgnoreCase)) continue;
                        // Only the colour slot is ever renamed; the other bindings keep their names.
                        if (cur == "BaseColor" || cur == "Color" || cur == "Base_Color" || cur == "Texture")
                        { nm.Value = new FName(asset, colourParam); renamed++; }
                    }

                // ---- overrides ---------------------------------------------------------------
                props.RemoveAll(p => p.Name?.Value?.Value == "BasePropertyOverrides");
                bool masked = treatment == "masked" || treatment == "bake" || treatment == "ownalpha";
                bool two = row.TryGetProperty("two_sided", out var twEl) && twEl.ValueKind == System.Text.Json.JsonValueKind.True;
                float clip = 0.5f;
                if (row.TryGetProperty("clip", out var cEl) && cEl.ValueKind == System.Text.Json.JsonValueKind.Number)
                    clip = (float)cEl.GetDouble();

                if (masked || two)
                {
                    var overrides = new StructPropertyData(FName.FromString(asset, "BasePropertyOverrides"))
                    {
                        StructType = FName.FromString(asset, "MaterialInstanceBasePropertyOverrides")
                    };
                    if (masked)
                    {
                        var blend = new EnumPropertyData(FName.FromString(asset, "BlendMode"))
                        {
                            Value = FName.FromString(asset, "BLEND_Masked"),
                            EnumType = FName.FromString(asset, "EBlendMode")
                        };
                        blend.PropertyTypeName = MakeTypeName(asset, blend.PropertyType);
                        overrides.Value.Add(blend);
                    }
                    if (two)
                    {
                        var t2 = new BoolPropertyData(FName.FromString(asset, "TwoSided")) { Value = true, IsZero = false };
                        t2.PropertyTypeName = MakeTypeName(asset, t2.PropertyType);
                        overrides.Value.Add(t2);
                    }
                    if (masked)
                    {
                        var cp = new FloatPropertyData(FName.FromString(asset, "OpacityMaskClipValue")) { Value = clip };
                        cp.PropertyTypeName = MakeTypeName(asset, cp.PropertyType);
                        overrides.Value.Add(cp);
                    }
                    overrides.PropertyTypeName = MakeTypeName(asset, overrides.PropertyType);
                    props.Add(overrides);
                    overridden++;
                }

                // asset.Write() emits the .uexp too. Copying the ORIGINAL .uexp afterwards is what
                // silently reverted every edit here: the payload lives in the .uexp, so the file looked
                // patched (new imports, new name map) and behaved exactly as before.
                asset.Write(Path.Combine(outDir, Path.GetFileName(path)));
                changed++;
            }
            catch (Exception ex) { CopyPair(path, uexp, outDir); Console.WriteLine("FAIL " + stem + ": " + ex.Message); failed++; }
        }
        Console.WriteLine($"apply_plan changed={changed} copied={copied} failed={failed} reparented={reparented} kept_parent={keptElse} renamed={renamed} overrides={overridden} masters={liveMasters.Count} mastersFile={mastersFile ?? "(none)"}");
    }

    static void SetMiParent(string inDir, string outDir, string listFile, string masterPkg, string masterName)
    {
        Directory.CreateDirectory(outDir);
        var wanted = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        if (listFile != "-" && File.Exists(listFile))
            foreach (var line in File.ReadAllLines(listFile))
            {
                var t = line.Trim();
                if (t.Length != 0 && !t.StartsWith("#")) wanted.Add(t);
            }

        int changed = 0, copied = 0, failed = 0;
        foreach (var path in Directory.GetFiles(inDir, "*.uasset", SearchOption.AllDirectories))
        {
            var stem = Path.GetFileNameWithoutExtension(path);
            var uexp = Path.ChangeExtension(path, ".uexp");
            try
            {
                if (!wanted.Contains(stem))
                {
                    File.Copy(path, Path.Combine(outDir, Path.GetFileName(path)), true);
                    if (File.Exists(uexp)) File.Copy(uexp, Path.Combine(outDir, Path.GetFileName(uexp)), true);
                    copied++;
                    continue;
                }

                var asset = new UAsset(path, EngineVersion.VER_UE5_5, Mappings);
                var exp = asset.Exports.OfType<NormalExport>().FirstOrDefault();
                var parent = exp?.Data.OfType<ObjectPropertyData>()
                    .FirstOrDefault(p => p.Name?.Value?.Value == "Parent");
                if (parent == null) { Console.WriteLine($"SKIP {stem}: no Parent"); failed++; continue; }

                var (_, idx) = AddImportChain(asset, "/Script/Engine", "Material", masterPkg, masterName);
                parent.Value = FPackageIndex.FromImport(idx - 1);
                asset.Write(Path.Combine(outDir, Path.GetFileName(path)));
                changed++;
            }
            catch (Exception ex) { Console.WriteLine($"FAIL {stem}: {ex.Message}"); failed++; }
        }
        Console.WriteLine($"set_mi_parent changed={changed} copied={copied} failed={failed} master={masterName}");
    }

    // Point one texture parameter at a different texture. Needed when the fix is a *texture*
    // change (e.g. an author mask baked into BaseColor alpha) and the instance must reference
    // the new asset without touching parents or the other bindings.
    // Rename a texture parameter, but only on instances whose live parent is <master>.
    // Needed because M_AlphaTest's parameter is "Color" while M_plants expects "BaseColor":
    // reparenting alone leaves the binding pointing at a parameter the new master ignores,
    // so the instance renders the master default (reads as a black background on cutouts).
    static void RenameTexParam(string inDir, string outDir, string listFile, string oldName, string newName, string master)
    {
        Directory.CreateDirectory(outDir);
        var wanted = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        if (listFile != "-" && File.Exists(listFile))
            foreach (var line in File.ReadAllLines(listFile))
            {
                var t = line.Trim();
                if (t.Length != 0 && !t.StartsWith("#")) wanted.Add(t);
            }

        int changed = 0, copied = 0, skipped = 0, failed = 0;
        foreach (var path in Directory.GetFiles(inDir, "*.uasset", SearchOption.AllDirectories))
        {
            var stem = Path.GetFileNameWithoutExtension(path);
            var uexp = Path.ChangeExtension(path, ".uexp");
            if (wanted.Count != 0 && !wanted.Contains(stem)) { CopyPair(path, uexp, outDir); copied++; continue; }
            try
            {
                var asset = new UAsset(path, EngineVersion.VER_UE5_5, Mappings);
                var exp = asset.Exports[0] as NormalExport;
                var parentProp = exp?.Data.OfType<ObjectPropertyData>()
                    .FirstOrDefault(pp => pp.Name?.Value?.Value == "Parent");
                var parentIdx = parentProp?.Value.Index ?? 0;
                var parentName = parentIdx > 0 ? asset.Imports[parentIdx - 1].ObjectName.Value.Value : "";
                if (!string.Equals(parentName, master, StringComparison.OrdinalIgnoreCase))
                { CopyPair(path, uexp, outDir); skipped++; continue; }

                var props = exp.Data;
                var arr = props.OfType<ArrayPropertyData>().FirstOrDefault(a => a.Name.Value.Value == "TextureParameterValues");
                bool hit = false;
                if (arr != null)
                    foreach (var el in arr.Value.OfType<StructPropertyData>())
                    {
                        var info = el.Value.OfType<StructPropertyData>().FirstOrDefault(s => s.Name.Value.Value == "ParameterInfo");
                        var nm = info?.Value.OfType<NamePropertyData>().FirstOrDefault();
                        if (nm != null && nm.Value.ToString() == oldName) { nm.Value = new FName(asset, newName); hit = true; }
                    }
                if (!hit) { CopyPair(path, uexp, outDir); skipped++; continue; }

                asset.Write(Path.Combine(outDir, Path.GetFileName(path)));
                changed++;
            }
            catch (Exception ex) { CopyPair(path, uexp, outDir); Console.WriteLine("FAIL " + stem + ": " + ex.Message); failed++; }
        }
        Console.WriteLine($"rename_texparam changed={changed} copied={copied} skipped={skipped} failed={failed} {oldName}->{newName} on={master}");
    }

    static void CopyPair(string path, string uexp, string outDir)
    {
        File.Copy(path, Path.Combine(outDir, Path.GetFileName(path)), true);
        if (File.Exists(uexp)) File.Copy(uexp, Path.Combine(outDir, Path.GetFileName(uexp)), true);
    }

    static void SetTexParam(string inDir, string outDir, string listFile, string param,
                            string texPkg, string texName)
    {
        Directory.CreateDirectory(outDir);
        var wanted = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        // Lines may be "MI" or "MI<TAB>textureName"; the tab form handles a different texture
        // per instance in a single pass (every masked MI has its own base colour map).
        var perInstance = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        if (listFile != "-" && File.Exists(listFile))
            foreach (var line in File.ReadAllLines(listFile))
            {
                var t = line.Trim();
                if (t.Length == 0 || t.StartsWith("#")) continue;
                var parts = t.Split('\t');
                wanted.Add(parts[0].Trim());
                if (parts.Length > 1 && parts[1].Trim().Length > 0) perInstance[parts[0].Trim()] = parts[1].Trim();
            }

        int changed = 0, copied = 0, failed = 0;
        foreach (var path in Directory.GetFiles(inDir, "*.uasset", SearchOption.AllDirectories))
        {
            var stem = Path.GetFileNameWithoutExtension(path);
            var uexp = Path.ChangeExtension(path, ".uexp");
            try
            {
                if (!wanted.Contains(stem))
                {
                    File.Copy(path, Path.Combine(outDir, Path.GetFileName(path)), true);
                    if (File.Exists(uexp)) File.Copy(uexp, Path.Combine(outDir, Path.GetFileName(uexp)), true);
                    copied++;
                    continue;
                }

                var asset = new UAsset(path, EngineVersion.VER_UE5_5, Mappings);
                var exp = asset.Exports.OfType<NormalExport>().FirstOrDefault();
                var arr = exp?.Data.OfType<ArrayPropertyData>()
                    .FirstOrDefault(p => p.Name?.Value?.Value == "TextureParameterValues");
                if (arr == null)
                {
                    CopyPair(path, uexp, outDir); copied++;
                    Console.WriteLine("SKIP " + stem + ": no texture params"); failed++;
                    continue;
                }

                var useName = perInstance.TryGetValue(stem, out var pn) ? pn : texName;
                var (_, idx) = AddImportChain(asset, "/Script/Engine", "Texture2D", texPkg, useName);
                var target = FPackageIndex.FromImport(idx - 1);

                bool hit = false;
                foreach (var el in arr.Value)
                {
                    if (el is not StructPropertyData sp) continue;
                    var info = sp.Value.OfType<StructPropertyData>()
                        .FirstOrDefault(s => s.Name?.Value?.Value == "ParameterInfo");
                    var nm = info?.Value.OfType<NamePropertyData>()
                        .FirstOrDefault(n => n.Name?.Value?.Value == "Name");
                    if (nm?.Value?.ToString() != param) continue;
                    var pv = sp.Value.OfType<ObjectPropertyData>()
                        .FirstOrDefault(o => o.Name?.Value?.Value == "ParameterValue");
                    if (pv == null) continue;
                    pv.Value = target;
                    hit = true;
                }
                if (!hit)
                {
                    CopyPair(path, uexp, outDir); copied++;
                    Console.WriteLine("SKIP " + stem + ": param " + param + " not bound"); failed++;
                    continue;
                }

                asset.Write(Path.Combine(outDir, Path.GetFileName(path)));
                changed++;
            }
            catch (Exception ex)
            {
                // Never drop an instance from the output: a missing MI makes the mesh fall
                // back to the engine default, which reads as "material missing" in game.
                CopyPair(path, uexp, outDir);
                Console.WriteLine("FAIL " + stem + ": " + ex.Message); failed++;
            }
        }
        Console.WriteLine($"set_texparam changed={changed} copied={copied} failed={failed} param={param} tex={texName}");
    }

    static void RetargetMIs(string inDir, string outDir, string forceMaskedFile = null)
    {
        // Two destinations, chosen per instance:
        //  - opaque surfaces  -> M_PropMaster (BLEND_Opaque, BaseColor/Normal/Metallic/Roughness)
        //  - cutout surfaces  -> M_PolygonMaster, the base game's general art master, with a
        //    per-instance BLEND_Masked override. The cutout comes from BaseColor's ALPHA
        //    channel (Use_OpacityFromAlpha), which is MT's own convention; no MT master samples
        //    a separate opacity texture. M_Decal_Base/M_PlantMaster were rejected because their
        //    Opacity input is a SCALAR and cannot take a mask texture.
        const string propPkg  = "/Game/Env/Materials/Master/M_PropMaster";
        const string propName = "M_PropMaster";
        const string polyPkg  = "/Game/Env/Materials/Master/M_PolygonMaster";
        const string polyName = "M_PolygonMaster";
        // MT's own masked foliage master -- BLEND_Masked + two-sided, reads BaseColor alpha.
        const string plantPkg  = "/Game/Models/Stylized_Forest/Materials/plants/M_plants";
        const string plantName = "M_plants";
        // Generic cutout master: MI_FenceMetal_01 parents it with BLEND_Masked + clip 0.3333.
        const string alphaPkg  = "/Game/AssetsvilleTown2/Materials/MasterMaterials/M_AlphaTest";
        const string alphaName = "M_AlphaTest";
        // Translucent master for signed glass / light boxes: BaseColor + scalar Opacity.
        const string transPkg  = "/Game/Env/Materials/Master/M_GlassTrans";
        const string transName = "M_GlassTrans";

        var propRename = new Dictionary<string, string?>
        {
            { "BaseColor",        "BaseColor"  },
            { "Normal",           "Normal"     },
            // M_PropMaster's Metallic/Roughness/Specular are SCALAR params -- its
            // TextureStreamingData lists exactly two textures (T_Normal_N, T_White_BC), so
            // BaseColor and Normal are the only texture inputs. Writing a Texture2D into the
            // scalar "Metallic"/"Roughness" params produces an instance that fails to compile
            // and renders as the engine checkerboard, which is what "materials missing" looked
            // like for most of the map. Drop them and let the master's scalar defaults apply.
            { "MetallicTex",      null         },
            { "RoughnessTex",     null         },
            { "EmissiveTex",      null         },
            { "EmissiveStrength", null         },
            { "OpacityTex",       null         },
        };
        var calcRename = new Dictionary<string, string?>
        {
            { "BaseColor",        "BaseColor"  },
            { "Normal",           "Normal"     },
            { "MetallicTex",      null         },
            { "RoughnessTex",     null         },
            { "OpacityTex",       null         },   // cutout now lives in BaseColor alpha
            { "EmissiveTex",      null         },
            { "EmissiveStrength", null         },
        };
        // M_AlphaTest declares only Color + Roughness, so the colour map must be renamed.
        var alphaRename = new Dictionary<string, string?>
        {
            { "BaseColor",        "Color"      },
            { "OpacityTex",       null         },
            { "Normal",           null         },
            { "MetallicTex",      null         },
            { "RoughnessTex",     null         },
            { "EmissiveTex",      null         },
            { "EmissiveStrength", null         },
        };

        Directory.CreateDirectory(outDir);
        var forceMasked = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var vegSet      = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var maskSet     = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var transSet    = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        if (!string.IsNullOrEmpty(forceMaskedFile) && File.Exists(forceMaskedFile))
        {
            // Sectioned list: [veg] / [masked] / [trans]. A bare list (no sections) is treated
            // as vegetation, which is what earlier builds passed.
            var cur = vegSet;
            foreach (var line in File.ReadAllLines(forceMaskedFile))
            {
                var t = line.Trim();
                if (t.Length == 0 || t.StartsWith("#")) continue;
                if (t.StartsWith("[") && t.EndsWith("]"))
                {
                    var sec = t.Trim('[', ']').Trim().ToLowerInvariant();
                    cur = sec switch { "masked" => maskSet, "trans" => transSet, _ => vegSet };
                    continue;
                }
                cur.Add(t);
            }
            Console.WriteLine($"veg={vegSet.Count} masked={maskSet.Count} trans={transSet.Count}");
        }
        int ok = 0, fail = 0, masked = 0, trans = 0;
        foreach (var path in Directory.GetFiles(inDir, "*.uasset", SearchOption.AllDirectories))
        {
            try
            {
                var asset = new UAsset(path, EngineVersion.VER_UE5_5, Mappings);
                var exp = asset.Exports.OfType<NormalExport>().FirstOrDefault();
                if (exp == null) { Console.WriteLine($"SKIP {Path.GetFileName(path)}: no NormalExport"); fail++; continue; }

                var props = exp.Data;
                var parent = props.OfType<ObjectPropertyData>().FirstOrDefault(p => p.Name?.Value?.Value == "Parent");
                if (parent == null) { Console.WriteLine($"SKIP {Path.GetFileName(path)}: no Parent"); fail++; continue; }

                // Is this a masked surface? Detect on the ORIGINAL parameter name, or honour a
                // force list. Vegetation/fence/wire materials carry no OpacityTex parameter --
                // their cutout is the colour map's alpha -- so they were routed opaque and
                // rendered with black where the texture is transparent.
                var baseName = Path.GetFileNameWithoutExtension(path);
                // NOT auto-detected from an OpacityTex parameter: those materials sample a separate
                // opacity map that no MT master accepts, and their BaseColor alpha is unrelated
                // (often smoothness), so masking them punches holes. Only an explicit list masks.
                // Vegetation MUST count as masked: M_plants cuts out through the BaseColor alpha,
                // and without the per-instance BLEND_Masked override the quad paints its texture's
                // green backdrop. Missing this is what left "some trees" opaque with green behind them.
                bool isVeg   = vegSet.Contains(baseName) || forceMasked.Contains(baseName);
                bool isMasked = isVeg || maskSet.Contains(baseName);
                bool isTrans = transSet.Contains(baseName);
                var rename = isMasked ? calcRename : propRename;
                // Three destinations, each matching an MT master's verified parameter contract:
                //  - foliage      -> M_plants      (BaseColor + masked; carries wind/grass graph)
                //  - other cutout -> M_AlphaTest   (Color + masked; the master MI_FenceMetal_01 uses)
                //  - translucent  -> M_GlassTrans  (BaseColor + Opacity; signed glass/light boxes)
                //  - opaque       -> M_PropMaster  (the recipe the shipped C1 release used)
                // M_AlphaTest's colour parameter is named Color, not BaseColor, so the rename map
                // has to change with the parent (see alphaRename below).
                string destPkg, destName;
                if (isVeg)        { destPkg = plantPkg;  destName = plantName; }
                else if (isTrans) { destPkg = transPkg;  destName = transName; }
                else if (isMasked){ destPkg = alphaPkg;  destName = alphaName; }
                else              { destPkg = propPkg;   destName = propName;  }
                var usedRename = (isMasked && !isVeg && !isTrans) ? alphaRename : calcRename;
                if (isMasked) masked++;
                if (isTrans) trans++;
                // Cutout surfaces go to MT's own masked foliage master (M_plants): BLEND_Masked,
                // two-sided, and its graph reads the BaseColor alpha -- exactly how MT's own
                // MI_TreeMedow_01 is set up (BaseColor only, masked, clip 0.3333).
                // M_PolygonMaster has no BlendMode at all, so its graph never routes alpha to
                // opacity and a masked override there only clips to the RGB (= black).
                bool usePlant = isVeg;
                if (isMasked) masked++;


                var (_, assetIdx) = AddImportChain(asset, "/Script/Engine", "Material",
                    destPkg, destName);
                parent.Value = FPackageIndex.FromImport(assetIdx - 1);

                foreach (var arrName in new[] { "TextureParameterValues", "ScalarParameterValues", "VectorParameterValues" })
                {
                    var arr = props.OfType<ArrayPropertyData>().FirstOrDefault(p => p.Name?.Value?.Value == arrName);
                    if (arr == null) continue;
                    var kept = new List<PropertyData>();
                    foreach (var el in arr.Value)
                    {
                        var sp = el as StructPropertyData;
                        if (sp == null) { kept.Add(el); continue; }
                        var info = sp.Value.OfType<StructPropertyData>().FirstOrDefault(s => s.Name?.Value?.Value == "ParameterInfo");
                        var nm = info?.Value.OfType<NamePropertyData>().FirstOrDefault(n => n.Name?.Value?.Value == "Name");
                        var cur = nm?.Value?.ToString() ?? "";
                        if (!usedRename.TryGetValue(cur, out var to)) { kept.Add(el); continue; }
                        if (to == null) continue;
                        if (nm != null) nm.Value = FName.FromString(asset, to);
                        kept.Add(el);
                    }
                    arr.Value = kept.ToArray();
                }

                // Masked surfaces: M_PolygonMaster ships as opaque, and MT's own masked
                // instances (e.g. MI_Mine_Master) override the blend on the instance.
                // BlendMode must be overridden per instance or the alpha cutout is ignored
                // and the quad paints solid.
                if (isMasked || isTrans)
                {
                    props.RemoveAll(p => p.Name?.Value?.Value == "BasePropertyOverrides");
                    var overrides = new StructPropertyData(FName.FromString(asset, "BasePropertyOverrides"))
                    {
                        StructType = FName.FromString(asset, "MaterialInstanceBasePropertyOverrides")
                    };
                    var blend = new EnumPropertyData(FName.FromString(asset, "BlendMode"))
                    {
                        Value = FName.FromString(asset, isTrans ? "BLEND_Translucent" : "BLEND_Masked"),
                        EnumType = FName.FromString(asset, "EBlendMode")
                    };
                    blend.PropertyTypeName = MakeTypeName(asset, blend.PropertyType);
                    var clip = new FloatPropertyData(FName.FromString(asset, "OpacityMaskClipValue")) { Value = 0.3333f };
                    clip.PropertyTypeName = MakeTypeName(asset, clip.PropertyType);
                    if (isMasked || isTrans)
                    {
                        // MT's tree instance is two-sided; foliage cards, fences and
                        // chain-link need it too -- one-sided cutout geometry draws
                        // nothing from the back, which reads as a broken material.
                        var ts = new BoolPropertyData(FName.FromString(asset, "TwoSided")) { Value = true, IsZero = false };
                        ts.PropertyTypeName = MakeTypeName(asset, ts.PropertyType);
                        overrides.Value.Add(ts);
                    }
                    overrides.Value.Add(blend);
                    if (!isTrans) overrides.Value.Add(clip);
                    overrides.PropertyTypeName = MakeTypeName(asset, overrides.PropertyType);
                    props.Add(overrides);

                    if (!isTrans)
                    {
                        // Cutout source is BaseColor's alpha on these masters.
                        EnsureScalar(asset, props, "Use_Opacity", 1f);
                        EnsureScalar(asset, props, "Use_OpacityFromAlpha", 1f);
                    }
                }

                asset.Write(Path.Combine(outDir, Path.GetFileName(path)));
                ok++;
            }
            catch (Exception ex) { Console.WriteLine($"FAIL {Path.GetFileName(path)}: {ex.Message}"); fail++; }
        }
        Console.WriteLine($"retargeted={ok} masked={masked} opaque={ok - masked} failed={fail}");
    }

    // Add a scalar parameter to an instance when it is not already present.
    static void EnsureScalar(UAsset asset, System.Collections.Generic.IList<PropertyData> props, string name, float value)
    {
        var arr = props.OfType<ArrayPropertyData>().FirstOrDefault(p => p.Name?.Value?.Value == "ScalarParameterValues");
        if (arr == null) return;
        if (ContainsParam(props, "ScalarParameterValues", name)) return;

        var entry = new StructPropertyData(FName.FromString(asset, "ScalarParameterValues"));
        var info = new StructPropertyData(FName.FromString(asset, "ParameterInfo"))
        {
            StructType = FName.FromString(asset, "MaterialParameterInfo")
        };
        var pname = new NamePropertyData(FName.FromString(asset, "Name")) { Value = FName.FromString(asset, name) };
        pname.PropertyTypeName = MakeTypeName(asset, pname.PropertyType);
        var assoc = new BytePropertyData(FName.FromString(asset, "Association")) { ByteType = BytePropertyType.Byte, EnumType = FName.FromString(asset, "EMaterialParameterAssociation"), Value = 0 };
        assoc.PropertyTypeName = MakeTypeName(asset, assoc.PropertyType);
        var idx = new IntPropertyData(FName.FromString(asset, "Index")) { Value = -1 };
        idx.PropertyTypeName = MakeTypeName(asset, idx.PropertyType);
        info.Value.Add(pname);
        info.Value.Add(assoc);
        info.Value.Add(idx);
        info.PropertyTypeName = MakeTypeName(asset, info.PropertyType);

        var pval = new FloatPropertyData(FName.FromString(asset, "ParameterValue")) { Value = value };
        pval.PropertyTypeName = MakeTypeName(asset, pval.PropertyType);

        entry.Value.Add(info);
        entry.Value.Add(pval);
        entry.PropertyTypeName = MakeTypeName(asset, entry.PropertyType);

        var kept = arr.Value.ToList();
        kept.Add(entry);
        arr.Value = kept.ToArray();
    }
    // Dump the properties of the first N exports of a given class in a map. Used to read the
    // base game's own MotorTownRoad / MTHouse / Garage actor settings as a reference.
    static void ClassDump(string mapPath, string className, int limit)
    {
        var asset = new UAsset(mapPath, EngineVersion.VER_UE5_5, Mappings);
        int shown = 0, total = 0;

        string ClassOf(UAssetAPI.ExportTypes.Export ex)
        {
            var ci = ex.ClassIndex;
            if (ci == null) return "?";
            int idx = ci.Index;
            if (idx < 0)
            {
                int ii = -idx - 1;
                return (ii >= 0 && ii < asset.Imports.Count) ? (asset.Imports[ii].ObjectName?.Value?.Value ?? "?") : "?";
            }
            if (idx > 0 && idx - 1 < asset.Exports.Count) return asset.Exports[idx - 1].ObjectName?.Value?.Value ?? "?";
            return "?";
        }

        var wanted = className.Split(',');
        var perClass = new Dictionary<string, int>();
        foreach (var ex in asset.Exports)
        {
            var cls = ClassOf(ex);
            if (Array.IndexOf(wanted, cls) < 0) continue;
            total++;
            perClass[cls] = perClass.TryGetValue(cls, out var pc) ? pc + 1 : 1;
            if (perClass[cls] > limit) continue;
            shown++;
            Console.WriteLine($"EXPORT [{cls}] {ex.ObjectName?.Value?.Value} (outer={(ex.OuterIndex?.Index ?? 0)})");
            if (ex is UAssetAPI.ExportTypes.NormalExport ne)
                foreach (var p in ne.Data) PrintProp(p, 1);
        }
        foreach (var kv in perClass) Console.WriteLine($"CLASS_TOTAL {kv.Key} {kv.Value}");
    }

    static void PrintProp(PropertyData p, int depth)
    {
        if (p == null || depth > 3) return;
        string pad = new string(' ', depth * 2);
        string name = p.Name?.Value?.Value ?? "?";
        switch (p)
        {
            case EnumPropertyData e:
                Console.WriteLine($"{pad}{name} (Enum) = {e.Value?.Value}");
                break;
            case BytePropertyData b:
                Console.WriteLine($"{pad}{name} (Byte) = {b.Value}");
                break;
            case IntPropertyData i:
                Console.WriteLine($"{pad}{name} (Int) = {i.Value}");
                break;
            case FloatPropertyData f:
                Console.WriteLine($"{pad}{name} (Float) = {f.Value}");
                break;
            case BoolPropertyData bo:
                Console.WriteLine($"{pad}{name} (Bool) = {bo.Value}");
                break;
            case NamePropertyData n:
                Console.WriteLine($"{pad}{name} (Name) = {n.Value?.Value}");
                break;
            case StrPropertyData s:
                Console.WriteLine($"{pad}{name} (Str) = {s.Value?.Value}");
                break;
            case ObjectPropertyData o:
                Console.WriteLine($"{pad}{name} (Object) = index {o.Value?.Index}");
                break;
            case StructPropertyData st:
                Console.WriteLine($"{pad}{name} (Struct {st.StructType?.Value?.Value})");
                foreach (var c in st.Value) PrintProp(c, depth + 1);
                break;
            case ArrayPropertyData ar:
                Console.WriteLine($"{pad}{name} (Array[{ar.Value.Length}])");
                if (ar.Value.Length > 0 && depth < 3) PrintProp(ar.Value[0], depth + 1);
                break;
            default:
                var t = p.GetType();
                var fields = t.GetProperties(System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance)
                    .Where(pr => pr.GetIndexParameters().Length == 0)
                    .Select(pr => { try { return pr.Name + "=" + (pr.GetValue(p)?.ToString() ?? "null"); } catch { return pr.Name + "=?"; } });
                Console.WriteLine($"{pad}{name} ({t.Name}) [{string.Join(", ", fields)}]");
                break;
        }
    }

    // List the actors placed in a cooked .umap: one line per actor with its class, plus a
    // per-class summary. Used to compare our corridor level against the base game and against
    // other map mods (e.g. checking no foreign spline/garage/home actors came along).
    static void ListLevelActors(string mapPath)
    {
        var asset = new UAsset(mapPath, EngineVersion.VER_UE5_5, Mappings);

        int persistentLevel = -1;
        for (int i = 0; i < asset.Exports.Count; i++)
        {
            var nm = asset.Exports[i].ObjectName?.Value?.Value ?? "";
            if (nm == "PersistentLevel") { persistentLevel = i + 1; break; }
        }
        Console.WriteLine($"MAP {Path.GetFileName(mapPath)} exports={asset.Exports.Count} imports={asset.Imports.Count} persistentLevel={(persistentLevel > 0 ? persistentLevel.ToString() : "NOT_FOUND")}");
        if (persistentLevel > 0 && asset.Exports[persistentLevel - 1] is UAssetAPI.ExportTypes.LevelExport le)
        {
            Console.WriteLine($"LEVEL_EXPORT actors={le.Actors?.Count ?? -1} url=yes model={(le.Model != null ? "yes" : "no")}");
            Console.WriteLine($"BOOKKEEPING exports={asset.Exports.Count} dependsMap={asset.DependsMap?.Count ?? -1}");
            foreach (var a in (le.Actors ?? new List<FPackageIndex>()).Take(5))
                Console.WriteLine($"  level_actor_index {a.Index}");
        }

        string ClassOf(UAssetAPI.ExportTypes.Export ex)
        {
            var ci = ex.ClassIndex;
            if (ci == null) return "?";
            int idx = ci.Index;
            if (idx < 0)
            {
                int ii = -idx - 1;
                if (ii >= 0 && ii < asset.Imports.Count)
                {
                    var nm = asset.Imports[ii].ObjectName?.Value?.Value ?? "?";
                    return nm.EndsWith("_C") ? nm : nm;
                }
                return "?";
            }
            if (idx > 0 && idx - 1 < asset.Exports.Count)
                return asset.Exports[idx - 1].ObjectName?.Value?.Value ?? "?";
            return "?";
        }

        var counts = new Dictionary<string, int>();
        int listed = 0;
        foreach (var ex in asset.Exports)
        {
            if (ex.OuterIndex == null) continue;
            // Cooked levels: actors are exports whose Outer is the PersistentLevel export.
            if (persistentLevel > 0 && ex.OuterIndex.Index != persistentLevel) continue;
            if (ex.OuterIndex.Index <= 0) continue;
            var cls = ClassOf(ex);
            var nm = ex.ObjectName?.Value?.Value ?? "?";
            Console.WriteLine($"ACTOR|{cls}|{nm}");
            counts[cls] = counts.TryGetValue(cls, out var c) ? c + 1 : 1;
            listed++;
        }

        Console.WriteLine($"TOTAL_ACTORS {listed}");
        foreach (var kv in counts.OrderByDescending(k => k.Value))
            Console.WriteLine($"CLASS|{kv.Key}|{kv.Value}");
    }

    // Remove actors (and their sub-object exports) from a cooked .umap and rewrite every
    // package index that survived. Cooked levels have no actor list of their own - actors are
    // found by scanning exports whose Outer is the PersistentLevel - so deleting the export is
    // what actually deletes the actor. Imports are left alone: unused imports are inert.
    static void CompactImports(string inPath, string outPath)
    {
        var asset = new UAsset(inPath, EngineVersion.VER_UE5_5, Mappings);
        int before = asset.Imports.Count;

        var used = new HashSet<int>();

        void VisitImport(int ii)
        {
            if (ii < 0 || ii >= asset.Imports.Count) return;
            if (!used.Add(ii)) return;
            var outer = asset.Imports[ii].OuterIndex;
            if (outer != null && outer.Index < 0) VisitImport(-outer.Index - 1);
        }

        void Visit(FPackageIndex pi)
        {
            if (pi != null && pi.Index < 0) VisitImport(-pi.Index - 1);
        }

        void Walk(PropertyData p)
        {
            if (p == null) return;
            switch (p)
            {
                case ObjectPropertyData o: Visit(o.Value); break;
                case ArrayPropertyData a:
                    for (int i = 0; i < a.Value.Length; i++) Walk(a.Value[i]);
                    break;
                case StructPropertyData s:
                    foreach (var c in s.Value) Walk(c);
                    break;
                case MapPropertyData m:
                    foreach (var kv in m.Value) { Walk(kv.Key); Walk(kv.Value); }
                    break;
            }
        }

        foreach (var ex in asset.Exports)
        {
            Visit(ex.OuterIndex);
            Visit(ex.ClassIndex);
            Visit(ex.SuperIndex);
            Visit(ex.TemplateIndex);
            if (ex is UAssetAPI.ExportTypes.NormalExport ne)
                foreach (var p in ne.Data) Walk(p);
        }

        // 0-based old import index -> new index, -1 = dropped
        var map = new int[before];
        var kept = new List<UAssetAPI.Import>();
        for (int i = 0; i < before; i++)
        {
            if (used.Contains(i)) { map[i] = kept.Count; kept.Add(asset.Imports[i]); }
            else map[i] = -1;
        }

        FPackageIndex Fix(FPackageIndex pi)
        {
            if (pi == null || pi.Index >= 0) return pi;
            int old = -pi.Index - 1;
            int nm = (old >= 0 && old < map.Length) ? map[old] : -1;
            if (nm < 0) { Console.WriteLine($"WARN import ref dropped without remap: {old}"); return new FPackageIndex(0); }
            return new FPackageIndex(-(nm + 1));
        }

        void FixProp(PropertyData p)
        {
            if (p == null) return;
            switch (p)
            {
                case ObjectPropertyData o: o.Value = Fix(o.Value); break;
                case ArrayPropertyData a:
                    for (int i = 0; i < a.Value.Length; i++) FixProp(a.Value[i]);
                    break;
                case StructPropertyData s:
                    foreach (var c in s.Value) FixProp(c);
                    break;
                case MapPropertyData m:
                    foreach (var kv in m.Value) { FixProp(kv.Key); FixProp(kv.Value); }
                    break;
            }
        }

        foreach (var ex in asset.Exports)
        {
            ex.OuterIndex = Fix(ex.OuterIndex);
            ex.ClassIndex = Fix(ex.ClassIndex);
            ex.SuperIndex = Fix(ex.SuperIndex);
            ex.TemplateIndex = Fix(ex.TemplateIndex);
            if (ex is UAssetAPI.ExportTypes.NormalExport ne)
                foreach (var p in ne.Data) FixProp(p);
        }
        foreach (var imp in kept)
            imp.OuterIndex = Fix(imp.OuterIndex);

        asset.Imports = kept;
        asset.Write(outPath);
        Console.WriteLine($"COMPACT_DONE imports {before} -> {kept.Count} -> {outPath}");
    }

    static void PruneLevel(string inPath, string outPath, string[] dropClasses, string keepMeshPrefix, string[] keepNames, int[] keepExportIdx)
    {
        var asset = new UAsset(inPath, EngineVersion.VER_UE5_5, Mappings);

        string ClassOf(UAssetAPI.ExportTypes.Export ex)
        {
            var ci = ex.ClassIndex;
            if (ci == null) return "?";
            int idx = ci.Index;
            if (idx < 0)
            {
                int ii = -idx - 1;
                return (ii >= 0 && ii < asset.Imports.Count) ? (asset.Imports[ii].ObjectName?.Value?.Value ?? "?") : "?";
            }
            if (idx > 0 && idx - 1 < asset.Exports.Count) return asset.Exports[idx - 1].ObjectName?.Value?.Value ?? "?";
            return "?";
        }

        string ImportPath(int negativeIdx)
        {
            var parts = new List<string>();
            int cur = -negativeIdx - 1;
            for (int guard = 0; guard < 8; guard++)
            {
                if (cur < 0 || cur >= asset.Imports.Count) break;
                var imp = asset.Imports[cur];
                parts.Add(imp.ObjectName?.Value?.Value ?? "?");
                if (imp.OuterIndex == null || imp.OuterIndex.Index >= 0) break;
                cur = -imp.OuterIndex.Index - 1;
            }
            parts.Reverse();
            return string.Join("/", parts);
        }

        // 1. Decide which exports to drop.
        var drop = new HashSet<int>(); // export index (0-based)
        for (int i = 0; i < asset.Exports.Count; i++)
        {
            var ex = asset.Exports[i];
            var cls = ClassOf(ex);
            if (Array.IndexOf(keepExportIdx, i + 1) >= 0) continue;
            var fn = ex.ObjectName;
            var baseName = fn?.Value?.Value ?? "";
            var name = fn != null && fn.Number > 0 ? baseName + "_" + fn.Number : baseName;
            if (Array.IndexOf(keepNames, name) >= 0 || Array.IndexOf(keepNames, baseName) >= 0) continue;
            if (Array.IndexOf(dropClasses, cls) < 0) continue;

            if (keepMeshPrefix.Length > 0 && cls == "StaticMeshActor")
            {
                string meshPath = "";
                if (ex is UAssetAPI.ExportTypes.NormalExport ne)
                {
                    var smcProp = ne.Data.OfType<ObjectPropertyData>()
                        .FirstOrDefault(p => (p.Name?.Value?.Value ?? "") == "StaticMeshComponent");
                    int compIdx = smcProp?.Value?.Index ?? 0;
                    if (compIdx > 0 && compIdx - 1 < asset.Exports.Count)
                    {
                        if (asset.Exports[compIdx - 1] is UAssetAPI.ExportTypes.NormalExport comp)
                        {
                            var meshProp = comp.Data.OfType<ObjectPropertyData>()
                                .FirstOrDefault(p => (p.Name?.Value?.Value ?? "") == "StaticMesh");
                            int meshIdx = meshProp?.Value?.Index ?? 0;
                            if (meshIdx < 0) meshPath = ImportPath(meshIdx);
                        }
                    }
                }
                if (meshPath.StartsWith(keepMeshPrefix, StringComparison.OrdinalIgnoreCase)) continue; // ours
            }
            drop.Add(i);
        }

        // 2. Also drop anything whose Outer chain reaches a dropped export (components etc).
        bool changed = true;
        while (changed)
        {
            changed = false;
            for (int i = 0; i < asset.Exports.Count; i++)
            {
                if (drop.Contains(i)) continue;
                var outer = asset.Exports[i].OuterIndex;
                if (outer == null || outer.Index <= 0) continue;
                if (drop.Contains(outer.Index - 1)) { drop.Add(i); changed = true; }
            }
        }

        Console.WriteLine($"PRUNE_DROP {drop.Count} of {asset.Exports.Count} exports");

        // 3. old export index (1-based) -> new index (1-based), 0 = removed.
        var remap = new int[asset.Exports.Count + 1];
        int next = 1;
        for (int i = 0; i < asset.Exports.Count; i++)
            remap[i + 1] = drop.Contains(i) ? 0 : next++;

        var kept = new List<UAssetAPI.ExportTypes.Export>();
        for (int i = 0; i < asset.Exports.Count; i++)
            if (!drop.Contains(i)) kept.Add(asset.Exports[i]);
        asset.Exports = kept;

        // 4. Rewrite every surviving package index, in outer/class slots and inside properties.
        FPackageIndex Fix(FPackageIndex pi)
        {
            if (pi == null) return pi;
            int idx = pi.Index;
            if (idx > 0)
            {
                int nm = (idx < remap.Length) ? remap[idx] : 0;
                if (nm == 0) { Console.WriteLine($"WARN dangling export ref {idx}"); return new FPackageIndex(0); }
                return new FPackageIndex(nm);
            }
            return pi;
        }

        void FixProp(PropertyData p)
        {
            switch (p)
            {
                case ObjectPropertyData o: o.Value = Fix(o.Value); break;
                case ArrayPropertyData a:
                    for (int i = 0; i < a.Value.Length; i++) FixProp(a.Value[i]);
                    break;
                case StructPropertyData s:
                    foreach (var c in s.Value) FixProp(c);
                    break;
                case MapPropertyData m:
                    foreach (var kv in m.Value) { FixProp(kv.Key); FixProp(kv.Value); }
                    break;
            }
        }

        foreach (var ex in asset.Exports)
        {
            ex.OuterIndex = Fix(ex.OuterIndex);
            ex.ClassIndex = Fix(ex.ClassIndex);
            if (ex is UAssetAPI.ExportTypes.NormalExport ne)
                foreach (var p in ne.Data) FixProp(p);
        }

        asset.Write(outPath);
        Console.WriteLine($"PRUNE_DONE kept={asset.Exports.Count} -> {outPath}");

        // Report what survived, by class, so the result is checkable at a glance.
        var counts = new Dictionary<string, int>();
        foreach (var ex in asset.Exports)
        {
            var c = ClassOf(ex);
            counts[c] = counts.TryGetValue(c, out var n) ? n + 1 : 1;
        }
        foreach (var kv in counts.OrderByDescending(k => k.Value))
            Console.WriteLine($"KEPT_CLASS|{kv.Key}|{kv.Value}");
    }

    // Rewrite a MotorTownRoad actor's spline points and settings in a cooked .umap, reusing the
    // cooked SplineComponent structure (we cannot author native MotorTown actors in a mod
    // project, so the game's own serialized layout is the template).
    static void SetRoadSpline(string inPath, string outPath, string actorName, string pointsJson, string props)
    {
        var asset = new UAsset(inPath, EngineVersion.VER_UE5_5, Mappings);

        string ClassOf(UAssetAPI.ExportTypes.Export ex)
        {
            var ci = ex.ClassIndex;
            if (ci == null) return "?";
            int idx = ci.Index;
            if (idx < 0)
            {
                int ii = -idx - 1;
                return (ii >= 0 && ii < asset.Imports.Count) ? (asset.Imports[ii].ObjectName?.Value?.Value ?? "?") : "?";
            }
            if (idx > 0 && idx - 1 < asset.Exports.Count) return asset.Exports[idx - 1].ObjectName?.Value?.Value ?? "?";
            return "?";
        }

        UAssetAPI.ExportTypes.NormalExport road = null;
        for (int i = 0; i < asset.Exports.Count; i++)
        {
            var ex = asset.Exports[i];
            if (ClassOf(ex) != "MotorTownRoad") continue;
            if ((ex.ObjectName?.Value?.Value ?? "") != actorName) continue;
            road = ex as UAssetAPI.ExportTypes.NormalExport;
            break;
        }
        if (road == null) { Console.WriteLine($"FAIL road actor {actorName} not found"); return; }

        // --- road settings ---------------------------------------------------
        var drop = new[] { "CourseKey", "RoadType" };
        road.Data.RemoveAll(p => Array.IndexOf(drop, p.Name?.Value?.Value ?? "") >= 0);
        foreach (var pair in (props ?? "").Split(',', StringSplitOptions.RemoveEmptyEntries))
        {
            var bits = pair.Split('=');
            if (bits.Length != 2) continue;
            string key = bits[0].Trim(), val = bits[1].Trim();
            // Course identity and road kind are enums/names, not numbers; the generic
            // int/float heuristics below would write them with the wrong property type.
            if (key == "CourseKey")
            {
                var np = new NamePropertyData(FName.FromString(asset, key)) { Value = FName.FromString(asset, val) };
                np.PropertyTypeName = MakeTypeName(asset, new FString("NameProperty"));
                road.Data.Add(np);
                Console.WriteLine($"PROP_SET {key}={val}");
                continue;
            }
            if (key == "RoadType")
            {
                var ep = new EnumPropertyData(FName.FromString(asset, key))
                {
                    EnumType = FName.FromString(asset, "EMTRoadType"),
                    Value = FName.FromString(asset, val)
                };
                ep.PropertyTypeName = MakeTypeName(asset, new FString("EnumProperty"));
                road.Data.Add(ep);
                Console.WriteLine($"PROP_SET {key}={val}");
                continue;
            }
            var existing = road.Data.FirstOrDefault(p => (p.Name?.Value?.Value ?? "") == key);
            bool isInt = int.TryParse(val, out int iv);
            bool isFloat = float.TryParse(val, out float fv);
            if (existing is FloatPropertyData ef && isFloat) { ef.Value = fv; continue; }
            if (existing is IntPropertyData ei && isInt) { ei.Value = iv; continue; }
            if (existing != null)
            {
                // A newly created property must carry the explicit property-type tag, otherwise the float is
                // written with the int bit pattern (LaneWidth=300 deserialises as 4.2E-43).
                if (isFloat) { var np = new FloatPropertyData(FName.FromString(asset, key)) { Value = fv }; np.PropertyTypeName = MakeTypeName(asset, new FString("FloatProperty")); road.Data.Add(np); }
                else if (isInt) { var np = new IntPropertyData(FName.FromString(asset, key)) { Value = iv }; np.PropertyTypeName = MakeTypeName(asset, new FString("IntProperty")); road.Data.Add(np); }
                continue;
            }
            // "300" parses as both int and float - the property's own name decides which it really is.
            var floatProps = new HashSet<string> { "LaneWidth", "SpeedLimitKPH", "CopyFromLandscapeWidthMultiplier", "MaxRoadSideTowDistance" };
            bool wantFloat = isFloat && (floatProps.Contains(key) || val.Contains('.')) && !(isInt && !floatProps.Contains(key) && !val.Contains('.'));
            if (wantFloat) { var np = new FloatPropertyData(FName.FromString(asset, key)) { Value = fv }; np.PropertyTypeName = MakeTypeName(asset, new FString("FloatProperty")); road.Data.Add(np); }
            else if (isInt) { var np = new IntPropertyData(FName.FromString(asset, key)) { Value = iv }; np.PropertyTypeName = MakeTypeName(asset, new FString("IntProperty")); road.Data.Add(np); }
            Console.WriteLine($"PROP_SET {key}={val}");
        }

        // --- spline points ---------------------------------------------------
        var splineProp = road.Data.OfType<ObjectPropertyData>().FirstOrDefault(p => (p.Name?.Value?.Value ?? "") == "Spline");
        int compIdx = splineProp?.Value?.Index ?? 0;
        if (compIdx <= 0 || compIdx - 1 >= asset.Exports.Count) { Console.WriteLine("FAIL spline component ref"); return; }
        if (!(asset.Exports[compIdx - 1] is UAssetAPI.ExportTypes.NormalExport comp)) { Console.WriteLine("FAIL spline component export type"); return; }

        var curves = comp.Data.OfType<StructPropertyData>().FirstOrDefault(p => (p.Name?.Value?.Value ?? "") == "SplineCurves");
        var position = curves?.Value.OfType<StructPropertyData>().FirstOrDefault(p => (p.Name?.Value?.Value ?? "") == "Position");
        var points = position?.Value.OfType<ArrayPropertyData>().FirstOrDefault(p => (p.Name?.Value?.Value ?? "") == "Points");
        if (points == null || points.Value.Length == 0) { Console.WriteLine("FAIL spline points struct not found"); return; }

        // FSplineCurves carries FOUR parallel curves (Position/Rotation/Scale/ReparamTable). They must all
        // have the same key count as Position or the spline is invalid at load, so rebuild every one of them.
        // Each sibling curve ("Rotation"/"Scale"/"ReparamTable") is a struct with its own "Points" array.
        ArrayPropertyData CurveArray(StructPropertyData parent, string name)
        {
            if (parent == null) return null;
            var curve = parent.Value.OfType<StructPropertyData>()
                .FirstOrDefault(p => (p.Name?.Value?.Value ?? "") == name);
            if (curve == null) return null;
            return curve.Value.OfType<ArrayPropertyData>()
                .FirstOrDefault(p => (p.Name?.Value?.Value ?? "") == "Points");
        }

        var template = points.Value[0] as StructPropertyData;
        if (template == null) { Console.WriteLine("FAIL spline point template"); return; }

        var raw = System.Text.Json.JsonDocument.Parse(File.ReadAllText(pointsJson));
        var pts = raw.RootElement.EnumerateArray()
            .Select(e => new FVector(e[0].GetSingle(), e[1].GetSingle(), e[2].GetSingle()))
            .ToList();
        int n = pts.Count;

        void RebuildCurve(ArrayPropertyData arr, string kind)
        {
            if (arr == null || arr.Value.Length == 0) { Console.WriteLine($"WARN curve '{kind}' missing"); return; }
            var tmpl = arr.Value[0] as StructPropertyData;
            if (tmpl == null) { Console.WriteLine($"WARN curve '{kind}' template not struct"); return; }
            var built = new List<PropertyData>(n);
            for (int i = 0; i < n; i++)
            {
                var cl = (StructPropertyData)CloneProp(tmpl);
                foreach (var child in cl.Value)
                {
                    switch (child.Name?.Value?.Value)
                    {
                        case "InVal":
                            if (child is FloatPropertyData inv) inv.Value = i;
                            break;
                        case "OutVal":
                            if (kind == "Position") SetVector(child, pts[i]);
                            else if (kind == "Rotation") SetQuat(child, new FQuat(0, 0, 0, 1));
                            else if (kind == "Scale") SetVector(child, new FVector(1f, 1f, 1f));
                            else SetScalar(child, i);
                            break;
                        case "ArriveTangent":
                            if (kind == "Position") SetVector(child, TangentAt(pts, i, n, true));
                            else if (kind == "Rotation") SetQuat(child, new FQuat(0, 0, 0, 1));
                            else if (kind == "Scale") SetVector(child, new FVector(0, 0, 0));
                            else SetScalar(child, 0);
                            break;
                        case "LeaveTangent":
                            if (kind == "Position") SetVector(child, TangentAt(pts, i, n, false));
                            else if (kind == "Rotation") SetQuat(child, new FQuat(0, 0, 0, 1));
                            else if (kind == "Scale") SetVector(child, new FVector(0, 0, 0));
                            else SetScalar(child, 0);
                            break;
                        case "InterpMode":
                            // keep template mode; Position stays CIM_CurveAuto
                            break;
                    }
                }
                built.Add(cl);
            }
            arr.Value = built.ToArray();
            Console.WriteLine($"CURVE_SET {kind} points={n}");
        }

        RebuildCurve(points, "Position");
        RebuildCurve(CurveArray(curves, "Rotation"), "Rotation");
        RebuildCurve(CurveArray(curves, "Scale"), "Scale");
        RebuildCurve(CurveArray(curves, "ReparamTable"), "ReparamTable");
        // SplineBounds drives culling/overlap tests - it must cover the new points, not NS's old box.
        double mnx = pts.Min(v => v.X), mny = pts.Min(v => v.Y), mnz = pts.Min(v => v.Z);
        double mxx = pts.Max(v => v.X), mxy = pts.Max(v => v.Y), mxz = pts.Max(v => v.Z);
        var bounds = road.Data.OfType<StructPropertyData>().FirstOrDefault(p => (p.Name?.Value?.Value ?? "") == "SplineBounds");
        if (bounds != null)
        {
            foreach (var child in bounds.Value)
            {
                switch (child.Name?.Value?.Value)
                {
                    case "Min": SetVector(child, new FVector(mnx, mny, mnz)); break;
                    case "Max": SetVector(child, new FVector(mxx, mxy, mxz)); break;
                    case "IsValid": if (child is BoolPropertyData bv) bv.Value = true; break;
                }
            }
            Console.WriteLine($"BOUNDS_SET min=({mnx:F0},{mny:F0},{mnz:F0}) max=({mxx:F0},{mxy:F0},{mxz:F0})");
        }
        else Console.WriteLine("WARN SplineBounds not found");

        Console.WriteLine($"SPLINE_SET points={n} on {actorName}");

        asset.Write(outPath);
        Console.WriteLine($"SPLINE_DONE -> {outPath}");
    }

    // ---- author N road actors from a lane dataset ------------------------------
    // Each source road (BeamNG DecalRoad) becomes its own AMotorTownRoad: the cooked template's
    // actor + SplineComponent exports are deep-cloned, the clone gets the road's own centreline
    // and lane properties. Cooked levels reconstruct the actor list from exports whose Outer is
    // the Level, so appending exports is all that is needed to place them.
    static void RunLaneRoads(string inPath, string outPath, string jsonPath)
    {
        var asset = new UAsset(inPath, EngineVersion.VER_UE5_5, Mappings);

        NormalExport actorTmpl = null;
        int levelIdx1 = -1;
        for (int i = 0; i < asset.Exports.Count; i++)
        {
            var ex = asset.Exports[i];
            string cls = ClassNameOf(asset, ex);
            if (cls == "Level" && levelIdx1 < 0) levelIdx1 = i + 1;
            else if (cls == "MotorTownRoad" && actorTmpl == null && ex is NormalExport ne) actorTmpl = ne;
        }
        if (levelIdx1 < 0) { Console.WriteLine("LANEROADS_FAIL no Level export"); return; }
        if (actorTmpl == null) { Console.WriteLine("LANEROADS_FAIL no MotorTownRoad template"); return; }

        var splineRef = actorTmpl.Data.OfType<ObjectPropertyData>().FirstOrDefault(p => (p.Name?.Value?.Value ?? "") == "Spline");
        int compRef = splineRef?.Value?.Index ?? 0;
        if (compRef <= 0 || !(asset.Exports[compRef - 1] is NormalExport compTmpl)) { Console.WriteLine("LANEROADS_FAIL no SplineComponent template"); return; }
        var curvesTmpl = compTmpl.Data.OfType<StructPropertyData>().FirstOrDefault(p => (p.Name?.Value?.Value ?? "") == "SplineCurves");
        if (curvesTmpl == null) { Console.WriteLine("LANEROADS_FAIL template has no SplineCurves"); return; }

        var doc = System.Text.Json.JsonDocument.Parse(File.ReadAllText(jsonPath));
        var roads = doc.RootElement.GetProperty("roads");

        // The engine spawns what ULevel::Actors lists, NOT what happens to have Outer == Level.
        // A cooked LevelExport carries that list explicitly, so every actor we add must be
        // appended to it as well; otherwise the export exists and never spawns.
        UAssetAPI.ExportTypes.LevelExport levelExport = null;
        if (levelIdx1 > 0 && asset.Exports[levelIdx1 - 1] is UAssetAPI.ExportTypes.LevelExport le) levelExport = le;
        if (levelExport == null) Console.WriteLine("LANEROADS_WARN no LevelExport - actors will not spawn");

        int made = 0;
        foreach (var r in roads.EnumerateArray())
        {
            string id = r.TryGetProperty("id", out var idEl) ? idEl.GetString() : made.ToString();
            var pts = r.GetProperty("points").EnumerateArray()
                .Select(e => new FVector(e[0].GetSingle(), e[1].GetSingle(), e[2].GetSingle())).ToList();
            if (pts.Count < 2) continue;
            int lanes = r.GetProperty("lanes").GetInt32();
            double laneWidth = r.GetProperty("lane_width").GetDouble();

            // The spline component is appended FIRST, so it takes the lower index; the actor gets
            // the next one. Registering the wrong one points ULevel::Actors at a component.
            int newCompIdx1 = asset.Exports.Count + 1;
            int actorIdx1 = newCompIdx1 + 1;
            string actorName = "C1Road_" + id;

            // --- spline component clone -------------------------------------
            var comp = new NormalExport(compTmpl);
            comp.ObjectName = FName.FromString(asset, actorName + "_Spline");
            comp.OuterIndex = new FPackageIndex(actorIdx1);
            comp.ClassIndex = compTmpl.ClassIndex;
            comp.Data = compTmpl.Data.Select(CloneProp).ToList();

            var curves = comp.Data.OfType<StructPropertyData>().FirstOrDefault(p => (p.Name?.Value?.Value ?? "") == "SplineCurves");
            if (curves == null) { Console.WriteLine($"LANEROADS_FAIL {actorName} no curves"); continue; }

            ArrayPropertyData CurveArray(StructPropertyData parent, string name)
            {
                var c = parent.Value.OfType<StructPropertyData>().FirstOrDefault(p => (p.Name?.Value?.Value ?? "") == name);
                return c?.Value.OfType<ArrayPropertyData>().FirstOrDefault(p => (p.Name?.Value?.Value ?? "") == "Points");
            }

            int n = pts.Count;
            void Rebuild(ArrayPropertyData arr, string kind)
            {
                if (arr == null || arr.Value.Length == 0) return;
                if (!(arr.Value[0] is StructPropertyData tmpl)) return;
                var built = new List<PropertyData>(n);
                for (int i = 0; i < n; i++)
                {
                    var cl = (StructPropertyData)CloneProp(tmpl);
                    foreach (var child in cl.Value)
                    {
                        switch (child.Name?.Value?.Value)
                        {
                            case "InVal":
                                if (child is FloatPropertyData inv) inv.Value = i;
                                break;
                            case "OutVal":
                                if (kind == "Position") SetVector(child, pts[i]);
                                else if (kind == "Rotation") SetQuat(child, new FQuat(0, 0, 0, 1));
                                else if (kind == "Scale") SetVector(child, new FVector(1f, 1f, 1f));
                                else SetScalar(child, i);
                                break;
                            case "ArriveTangent":
                                if (kind == "Position") SetVector(child, TangentOpen(pts, i, true));
                                else if (kind == "Rotation") SetQuat(child, new FQuat(0, 0, 0, 1));
                                else if (kind == "Scale") SetVector(child, new FVector(0, 0, 0));
                                else SetScalar(child, 0);
                                break;
                            case "LeaveTangent":
                                if (kind == "Position") SetVector(child, TangentOpen(pts, i, false));
                                else if (kind == "Rotation") SetQuat(child, new FQuat(0, 0, 0, 1));
                                else if (kind == "Scale") SetVector(child, new FVector(0, 0, 0));
                                else SetScalar(child, 0);
                                break;
                        }
                    }
                    built.Add(cl);
                }
                arr.Value = built.ToArray();
            }

            var posArr = curves.Value.OfType<StructPropertyData>().FirstOrDefault(p => (p.Name?.Value?.Value ?? "") == "Position");
            Rebuild(posArr?.Value.OfType<ArrayPropertyData>().FirstOrDefault(p => (p.Name?.Value?.Value ?? "") == "Points"), "Position");
            Rebuild(CurveArray(curves, "Rotation"), "Rotation");
            Rebuild(CurveArray(curves, "Scale"), "Scale");
            Rebuild(CurveArray(curves, "ReparamTable"), "ReparamTable");

            // --- actor clone -------------------------------------------------
            var actor = new NormalExport(actorTmpl);
            actor.ObjectName = FName.FromString(asset, actorName);
            actor.OuterIndex = new FPackageIndex(levelIdx1);
            actor.ClassIndex = actorTmpl.ClassIndex;
            actor.Data = actorTmpl.Data.Where(x => (x.Name?.Value?.Value ?? "") != "CourseKey").Select(CloneProp).ToList();
            // Traffic roads are not part of the time-attack course: only the single CourseKey
            // road may claim CourseKey=C1Shuto, so drop the inherited key and mark these as Road.
            foreach (var ep in actor.Data.OfType<EnumPropertyData>().Where(x => (x.Name?.Value?.Value ?? "") == "RoadType"))
                ep.Value = FName.FromString(asset, "Road");

            void SetNum(string key, double val, bool asFloat)
            {
                var p = actor.Data.FirstOrDefault(x => (x.Name?.Value?.Value ?? "") == key);
                if (p is IntPropertyData ip) { ip.Value = (int)Math.Round(val); return; }
                if (p is FloatPropertyData fp) { fp.Value = (float)val; return; }
                if (asFloat)
                {
                    var np = new FloatPropertyData(FName.FromString(asset, key)) { Value = (float)val };
                    np.PropertyTypeName = MakeTypeName(asset, new FString("FloatProperty"));
                    actor.Data.Add(np);
                }
                else
                {
                    var np = new IntPropertyData(FName.FromString(asset, key)) { Value = (int)Math.Round(val) };
                    np.PropertyTypeName = MakeTypeName(asset, new FString("IntProperty"));
                    actor.Data.Add(np);
                }
            }

            SetNum("NumForwardLanes", lanes, false);
            SetNum("NumBackwardLanes", 0, false);
            SetNum("LaneWidth", laneWidth * 100.0, true);   // metres -> centimetres
            SetNum("RoadFlags", 0, false);                  // AI traffic enabled
            foreach (var p in actor.Data.OfType<ObjectPropertyData>())
            {
                var pn = p.Name?.Value?.Value ?? "";
                if (pn == "Spline" || pn == "RootComponent") p.Value = new FPackageIndex(newCompIdx1);
            }

            var bounds = actor.Data.OfType<StructPropertyData>().FirstOrDefault(p => (p.Name?.Value?.Value ?? "") == "SplineBounds");
            if (bounds != null)
            {
                double mnx = pts.Min(v => v.X), mny = pts.Min(v => v.Y), mnz = pts.Min(v => v.Z);
                double mxx = pts.Max(v => v.X), mxy = pts.Max(v => v.Y), mxz = pts.Max(v => v.Z);
                foreach (var child in bounds.Value)
                {
                    switch (child.Name?.Value?.Value)
                    {
                        case "Min": SetVector(child, new FVector(mnx, mny, mnz)); break;
                        case "Max": SetVector(child, new FVector(mxx, mxy, mxz)); break;
                        case "IsValid": if (child is BoolPropertyData bv) bv.Value = true; break;
                    }
                }
            }

            asset.Exports.Add(comp);
            asset.Exports.Add(actor);
            levelExport?.Actors?.Add(new FPackageIndex(actorIdx1));
            made++;
        }

        asset.Write(outPath);
        Console.WriteLine($"LANEROADS_DONE roads={made} -> {outPath}");
    }

    // Non-wrapping Catmull-Rom tangent: these road splines are open, so the ends must not
    // borrow curvature from the opposite end of the road.
    static FVector TangentOpen(List<FVector> pts, int i, bool arrive)
    {
        int prev = Math.Max(0, i - 1), next = Math.Min(pts.Count - 1, i + 1);
        return arrive
            ? new FVector((pts[i].X - pts[prev].X) * 0.5f, (pts[i].Y - pts[prev].Y) * 0.5f, (pts[i].Z - pts[prev].Z) * 0.5f)
            : new FVector((pts[next].X - pts[i].X) * 0.5f, (pts[next].Y - pts[i].Y) * 0.5f, (pts[next].Z - pts[i].Z) * 0.5f);
    }

    // Catmull-Rom tangent so the curve passes smoothly through every point.
    static FVector TangentAt(List<FVector> pts, int i, int n, bool arrive)
    {
        var prev = pts[(i - 1 + n) % n];
        var next = pts[(i + 1) % n];
        return arrive
            ? new FVector((pts[i].X - prev.X) * 0.5f, (pts[i].Y - prev.Y) * 0.5f, (pts[i].Z - prev.Z) * 0.5f)
            : new FVector((next.X - pts[i].X) * 0.5f, (next.Y - pts[i].Y) * 0.5f, (next.Z - pts[i].Z) * 0.5f);
    }

    // Point a struct's vector child (OutVal/ArriveTangent/...) at a value, reaching through the
    // wrapper struct to the VectorPropertyData that actually holds the FVector.
    // Scalar curve child (ReparamTable uses plain floats).
    static void SetScalar(PropertyData container, float v)
    {
        if (container is FloatPropertyData f) { f.Value = v; return; }
        if (container is StructPropertyData sd && sd.Value.Count == 1) { SetScalar(sd.Value[0], v); return; }
        var prop = container.GetType().GetProperty("Value");
        if (prop != null && prop.PropertyType == typeof(float)) { prop.SetValue(container, v); return; }
        Console.WriteLine($"WARN cannot set scalar on {container.GetType().Name}");
    }

    // Quat curve child (Rotation).
    static void SetQuat(PropertyData container, FQuat q)
    {
        if (container is StructPropertyData sd && sd.Value.Count == 1) { SetQuat(sd.Value[0], q); return; }
        var prop = container.GetType().GetProperty("Value");
        if (prop != null && prop.PropertyType == typeof(FQuat)) { prop.SetValue(container, q); return; }
        Console.WriteLine($"WARN cannot set quat on {container.GetType().Name}");
    }

    static void SetVector(PropertyData container, FVector v)
    {
        if (container is StructPropertyData sd && sd.Value.Count == 1) { SetVector(sd.Value[0], v); return; }
        var prop = container.GetType().GetProperty("Value");
        if (prop != null && prop.PropertyType == typeof(FVector)) { prop.SetValue(container, v); return; }
        Console.WriteLine($"WARN cannot set vector on {container.GetType().Name}");
    }

    static void SetVecDeep(PropertyData p, double x, double y, double z)
    {
        if (p is VectorPropertyData v) { v.Value = new FVector(x, y, z); return; }
        if (p is StructPropertyData s) foreach (var c in s.Value) SetVecDeep(c, x, y, z);
    }
    static void SetRotDeep(PropertyData p, double yaw)
    {
        if (p is RotatorPropertyData r) { r.Value = new FRotator(0, yaw, 0); return; }
        if (p is StructPropertyData s) foreach (var c in s.Value) SetRotDeep(c, yaw);
    }

    // ---- place a GarageActorBP instance in a level ------------------------------
    // A Blueprint actor instance in a cooked level needs only: an actor export whose
    // class is the BP and whose RootComponent points at a component export holding the
    // transform. The BP's SCS builds InteractionCube / MotorTownInteractable / Camera by
    // itself, so nothing else has to be authored here.
    // ---- clone an actor's whole component subtree -------------------------------
    // A Motor Town garage is not a bare actor: it is a BP_C1_Prop_C instance carrying
    // DefaultSceneRoot + a "Child" ChildActorComponent whose ChildActorClass is
    // GarageActorBP_C. Anything else fails at runtime, so copy the structure verbatim
    // (same component classes, same names, same attach wiring) and move only the root.
    // Cooked exports carry the async loader's scheduling metadata. UAssetAPI's Export copy
    // constructor does NOT carry it, so a clone lands as tpl=0, RF_NoFlags, and empty
    // CBS/SBC/CBC lists -- the engine then cannot create it and fatals with
    // "Missing Dependency ... still waiting for creation/serialization".
    static FPackageIndex RemapDepIdx(FPackageIndex p, Dictionary<int, int> m)
        => (p != null && p.Index > 0 && m.TryGetValue(p.Index, out var ni)) ? new FPackageIndex(ni) : p;

    static void CopyExportMeta(Export src, Export dst, Dictionary<int, int> m)
    {
        dst.TemplateIndex = src.TemplateIndex;
        dst.ObjectFlags = src.ObjectFlags;
        dst.SerializationBeforeSerializationDependencies = src.SerializationBeforeSerializationDependencies.Select(p => RemapDepIdx(p, m)).ToList();
        dst.CreateBeforeSerializationDependencies = src.CreateBeforeSerializationDependencies.Select(p => RemapDepIdx(p, m)).ToList();
        dst.SerializationBeforeCreateDependencies = src.SerializationBeforeCreateDependencies.Select(p => RemapDepIdx(p, m)).ToList();
        dst.CreateBeforeCreateDependencies = src.CreateBeforeCreateDependencies.Select(p => RemapDepIdx(p, m)).ToList();
    }

    static void CloneActorSubtree(string inPath, string outPath, string templateName, string newName,
                                  double x, double y, double z, double yaw)
    {
        UAsset.CaptureOriginalExportData = true;   // needed to patch the level actor table
        var asset = new UAsset(inPath, EngineVersion.VER_UE5_5, Mappings);
        var exports = asset.Exports;

        int tmplIdx1 = -1;
        for (int i = 0; i < exports.Count; i++)
        {
            // FName.ToString() is authoritative: .Value.Value is null for table-indexed names
            var nm = exports[i].ObjectName?.ToString();
            if (nm == templateName) { tmplIdx1 = i + 1; break; }
        }
        if (tmplIdx1 < 0) { Console.WriteLine($"CLONE_FAIL no export named {templateName}"); return; }
        if (exports[tmplIdx1 - 1] is not NormalExport tmpl) { Console.WriteLine("CLONE_FAIL template is not a NormalExport"); return; }

        // component set = every export referenced by the template's object-typed properties
        var comps = new List<int>();
        void Collect(PropertyData p)
        {
            if (p is ObjectPropertyData o && o.Value != null)
            {
                int i = o.Value.Index;
                if (i > 0 && !comps.Contains(i)) comps.Add(i);
            }
            else if (p is ArrayPropertyData a)
            {
                foreach (var c in a.Value) Collect(c);
            }
        }
        foreach (var p in tmpl.Data) Collect(p);
        if (comps.Count == 0) { Console.WriteLine("CLONE_FAIL template references no components"); return; }

        // Layout matters: in a cooked map the actor sits BEFORE its own components
        // (BP_C1_Prop_C_0 = 1, Child = 4, DefaultSceneRoot = 13), so every component's Outer
        // points backwards at an already-created object. Appending the components first makes
        // their Outer point forward and the loader fails with "request for <actor> but it was
        // still waiting for creation".
        int actorIdx1 = exports.Count + 1;
        var map = new Dictionary<int, int>();
        for (int k = 0; k < comps.Count; k++) map[comps[k]] = actorIdx1 + 1 + k;
        map[tmplIdx1] = actorIdx1;      // component CBC points at the actor: repoint it

        static void RemapRefs(PropertyData p, Dictionary<int, int> m)
        {
            if (p is ObjectPropertyData o)
            {
                if (o.Value != null && o.Value.Index > 0 && m.TryGetValue(o.Value.Index, out var ni))
                    o.Value = new FPackageIndex(ni);
            }
            else if (p is ArrayPropertyData a)
            {
                foreach (var c in a.Value) RemapRefs(c, m);
            }
            else if (p is StructPropertyData s)
            {
                foreach (var c in s.Value) RemapRefs(c, m);
            }
        }

        int tmplRoot = -1;
        foreach (var p in tmpl.Data)
            if (p.Name?.Value?.Value == "RootComponent" && p is ObjectPropertyData ro && ro.Value != null)
                tmplRoot = ro.Value.Index;

        var newComps = new List<NormalExport>();
        foreach (var idx in comps)
        {
            if (exports[idx - 1] is not NormalExport src) { Console.WriteLine($"CLONE_FAIL component {idx} unparsed"); return; }
            var cl = new NormalExport(src);
            cl.Data = src.Data.Select(CloneProp).ToList();
            cl.ObjectName = FName.FromString(asset, src.ObjectName?.ToString() ?? "Comp");  // keep the name
            cl.OuterIndex = new FPackageIndex(actorIdx1);
            cl.ClassIndex = src.ClassIndex;
            CopyExportMeta(src, cl, map);
            foreach (var p in cl.Data) RemapRefs(p, map);
            if (idx == tmplRoot)
            {
                foreach (var p in cl.Data)
                {
                    var n = p.Name?.Value?.Value;
                    if (n == "RelativeLocation") SetVecDeep(p, x, y, z);
                    else if (n == "RelativeRotation") SetRotDeep(p, yaw);
                }
            }
            newComps.Add(cl);
        }

        var actor = new NormalExport(tmpl);
        actor.Data = tmpl.Data.Select(CloneProp).ToList();
        actor.ObjectName = FName.FromString(asset, newName);
        actor.OuterIndex = tmpl.OuterIndex;   // same level as the template
        actor.ClassIndex = tmpl.ClassIndex;   // same BP class: structure is the contract
        CopyExportMeta(tmpl, actor, map);
        foreach (var p in actor.Data) RemapRefs(p, map);

        exports.Add(actor);              // actor first: lower index than its components
        foreach (var c in newComps) exports.Add(c);

        // Exports alone are not enough: the level carries an actor table (the same one
        // --drop-actors rewrites). Appending the export without registering it there leaves
        // the actor unspawned, which reads in game as "nothing was added".
        var lvl = asset.Exports.OfType<LevelExport>().FirstOrDefault();
        if (lvl?.Actors == null || lvl.OriginalData == null)
        {
            Console.WriteLine("CLONE_FAIL level actor table unavailable (load with CaptureOriginalExportData)");
            return;
        }
        {
            int expected = lvl.Actors.Count;
            int off = FindActorCountOffset(lvl.OriginalData, expected,
                maxIdx: Math.Max(expected, asset.Exports.Count) + 4096, minIdx: -65536);
            if (off < 0) { Console.WriteLine($"CLONE_FAIL no actor table (count={expected})"); return; }
            var raw = lvl.OriginalData;
            int arrayStart = off + 4;
            int arrayBytes = expected * 4;
            var outB = new List<byte>(raw.Length + 4);
            outB.AddRange(raw.Take(arrayStart + arrayBytes));
            outB.AddRange(BitConverter.GetBytes(actorIdx1));
            outB.AddRange(raw.Skip(arrayStart + arrayBytes));
            var arr = outB.ToArray();
            Array.Copy(BitConverter.GetBytes(expected + 1), 0, arr, off, 4);
            lvl.OriginalData = arr;
            lvl.DataDirty = false;          // write patched original bytes, never a re-serialisation
            lvl.SerialSize = arr.Length;
            lvl.Actors.Add(new FPackageIndex(actorIdx1));
            Console.WriteLine($"CLONE_ACTORS {expected} -> {expected + 1} (+{actorIdx1})");
        }

        asset.Write(outPath);
        Console.WriteLine($"CLONE_OK {newName} actor={actorIdx1} comps={string.Join(",", comps.Select(c => map[c]))} " +
                          $"from={templateName} at ({x},{y},{z}) yaw={yaw} -> {outPath}");
    }

    static void RunAddGarage(string inPath, string outPath, double x, double y, double z, double yaw)
    {
        var asset = new UAsset(inPath, EngineVersion.VER_UE5_5, Mappings);

        string ClassOf(Export ex)
        {
            var ci = ex.ClassIndex;
            if (ci == null) return "?";
            int idx = ci.Index;
            if (idx < 0)
            {
                int ii = -idx - 1;
                return (ii >= 0 && ii < asset.Imports.Count) ? (asset.Imports[ii].ObjectName?.Value?.Value ?? "?") : "?";
            }
            if (idx > 0 && idx - 1 < asset.Exports.Count) return asset.Exports[idx - 1].ObjectName?.Value?.Value ?? "?";
            return "?";
        }

        // A BP actor export needs a schema entry to be written at all. The instance stores only
        // AActor-level properties (RootComponent), so reuse the StaticMeshActor schema rather
        // than inventing one - the engine resolves cooked properties by name, not by our schema.
        if (Mappings != null && !Mappings.Schemas.ContainsKey("GarageActorBP_C"))
        {
            var smaKey = Mappings.Schemas.Keys.FirstOrDefault(k => k.EndsWith("StaticMeshActor"));
            if (smaKey != null) Mappings.Schemas["GarageActorBP_C"] = Mappings.Schemas[smaKey];
        }

        int levelIdx1 = -1, garageImport = -1;
        NormalExport compTmpl = null, actorTmpl = null;
        for (int i = 0; i < asset.Exports.Count; i++)
        {
            var c = ClassOf(asset.Exports[i]);
            if (c == "Level" && levelIdx1 < 0) levelIdx1 = i + 1;
            else if (c == "SceneComponent" && compTmpl == null) compTmpl = asset.Exports[i] as NormalExport;
            else if (c == "StaticMeshActor" && actorTmpl == null) actorTmpl = asset.Exports[i] as NormalExport;
        }
        for (int i = 0; i < asset.Imports.Count; i++)
            if (asset.Imports[i].ObjectName?.Value?.Value == "GarageActorBP_C") { garageImport = i; break; }

        if (levelIdx1 < 0) { Console.WriteLine("GARAGE_FAIL no Level export"); return; }
        if (compTmpl == null) { Console.WriteLine("GARAGE_FAIL no parsed SceneComponent template"); return; }
        if (actorTmpl == null) { Console.WriteLine("GARAGE_FAIL no parsed actor template"); return; }
        if (garageImport < 0) { Console.WriteLine("GARAGE_FAIL GarageActorBP_C import missing"); return; }

        int compIdx1 = asset.Exports.Count + 1;
        int actorIdx1 = asset.Exports.Count + 2;

        var comp = new NormalExport(compTmpl);
        comp.Data = compTmpl.Data.Select(x => CloneProp(x)).ToList();   // ctor copy does not carry Data
        comp.ObjectName = FName.FromString(asset, "GarageRoot");
        comp.OuterIndex = new FPackageIndex(actorIdx1);
        comp.ClassIndex = compTmpl.ClassIndex;
        foreach (var p in comp.Data)
        {
            var n = p.Name?.Value?.Value;
            if (n == "RelativeLocation") SetVecDeep(p, x, y, z);
            else if (n == "RelativeRotation") SetRotDeep(p, yaw);
        }

        var actor = new NormalExport(actorTmpl);
        actor.ObjectName = FName.FromString(asset, "GarageActor_0");
        actor.OuterIndex = new FPackageIndex(levelIdx1);
        actor.ClassIndex = new FPackageIndex(-(garageImport + 1));   // negative = import
        actor.Data = new List<PropertyData>();
        var rc = new ObjectPropertyData(FName.FromString(asset, "RootComponent")) { Value = new FPackageIndex(compIdx1) };
        rc.PropertyTypeName = MakeTypeName(asset, new FString("ObjectProperty"));
        actor.Data.Add(rc);

        asset.Exports.Add(comp);
        asset.Exports.Add(actor);
        asset.Write(outPath);
        Console.WriteLine($"GARAGE_OK actor={actorIdx1} comp={compIdx1} class=GarageActorBP_C at ({x},{y},{z}) yaw={yaw} -> {outPath}");
    }

    // ---- place any Blueprint-class actor in a level ----------------------------
    // Builds the import chain the engine needs (Package / BlueprintGeneratedClass / CDO)
    // and appends an actor export whose RootComponent is a fresh SceneComponent carrying
    // the transform. The BP's own component tree is constructed by its class at spawn.
    static void AddBpActor(string inPath, string outPath, string pkgPath, string bpClass,
                           string actorName, double x, double y, double z, double yaw)
    {
        var asset = new UAsset(inPath, EngineVersion.VER_UE5_5, Mappings);

        // Cooked-property schema is looked up by class name; reuse a known actor schema so
        // the exports serialize at all. Engine resolves properties by name, not by this.
        if (Mappings != null && !Mappings.Schemas.ContainsKey(bpClass))
        {
            var key = Mappings.Schemas.Keys.FirstOrDefault(k => k.EndsWith("StaticMeshActor"));
            if (key != null) Mappings.Schemas[bpClass] = Mappings.Schemas[key];
        }

        int levelIdx1 = -1;
        NormalExport compTmpl = null;
        for (int i = 0; i < asset.Exports.Count; i++)
        {
            var ex = asset.Exports[i];
            string cls = ClassNameOf(asset, ex);
            if (cls == "Level" && levelIdx1 < 0) levelIdx1 = i + 1;
            else if ((cls == "SceneComponent" || cls == "CapsuleComponent") && compTmpl == null && ex is NormalExport ne) compTmpl = ne;
        }
        if (levelIdx1 < 0) { Console.WriteLine("BPACTOR_FAIL no Level export"); return; }
        if (compTmpl == null) { Console.WriteLine("BPACTOR_FAIL no component template"); return; }

        // import chain for the actor class: blueprint classes need Package/BPGC/CDO;
        // native classes only need their module package plus the class object.
        int clsIdx;
        if (bpClass.EndsWith("_C"))
        {
            var chain = AddImportChain(asset, "/Script/Engine", "BlueprintGeneratedClass", pkgPath, bpClass, addCdoImport: true);
            clsIdx = chain.assetIdx;
        }
        else
        {
            int pkg0 = -1;
            for (int i = 0; i < asset.Imports.Count; i++)
            {
                var im = asset.Imports[i];
                if (im.ObjectName?.Value?.Value == pkgPath && im.ClassName?.Value?.Value == "Package") { pkg0 = i; break; }
            }
            if (pkg0 < 0)
            {
                asset.Imports.Add(new Import("/Script/CoreUObject", "Package",
                    FPackageIndex.FromRawIndex(0), pkgPath, false, asset));
                pkg0 = asset.Imports.Count - 1;
                Console.WriteLine($"  Added imports: Package [{pkg0 + 1}] = {pkgPath}");
            }
            asset.Imports.Add(new Import("/Script/CoreUObject", "Class",
                FPackageIndex.FromImport(pkg0), bpClass, false, asset));
            clsIdx = asset.Imports.Count;
            Console.WriteLine($"  Added imports: Class [{clsIdx}] = {bpClass}");
        }

        // SceneComponent class import, outer = /Script/Engine package import
        int enginePkg0 = -1;
        for (int i = 0; i < asset.Imports.Count; i++)
        {
            var im = asset.Imports[i];
            if (im.ObjectName?.Value?.Value == "/Script/Engine" && im.OuterIndex != null && im.OuterIndex.Index == 0 && im.ClassName?.Value?.Value == "Package") { enginePkg0 = i; break; }
        }
        if (enginePkg0 < 0) { Console.WriteLine("BPACTOR_FAIL no /Script/Engine package import"); return; }
        int sceneCls0 = -1;
        for (int i = 0; i < asset.Imports.Count; i++)
        {
            var im = asset.Imports[i];
            if (im.ObjectName?.Value?.Value == "SceneComponent" && im.OuterIndex != null && im.OuterIndex.Index == -(enginePkg0 + 1)) { sceneCls0 = i; break; }
        }
        if (sceneCls0 < 0)
        {
            asset.Imports.Add(new Import("/Script/CoreUObject", "Class",
                FPackageIndex.FromImport(enginePkg0), "SceneComponent", false, asset));
            sceneCls0 = asset.Imports.Count - 1;
        }

        int compIdx1 = asset.Exports.Count + 1;
        int actorIdx1 = asset.Exports.Count + 2;

        var comp = new NormalExport(compTmpl);
        comp.Data = compTmpl.Data.Where(p => p.Name?.Value?.Value == "RelativeLocation" ||
                                             p.Name?.Value?.Value == "RelativeRotation")
                                .Select(CloneProp).ToList();
        comp.ObjectName = FName.FromString(asset, actorName + "_Root");
        comp.OuterIndex = new FPackageIndex(actorIdx1);
        comp.ClassIndex = new FPackageIndex(-(sceneCls0 + 1));
        foreach (var p in comp.Data)
        {
            var n = p.Name?.Value?.Value;
            if (n == "RelativeLocation") SetVecDeep(p, x, y, z);
            else if (n == "RelativeRotation") SetRotDeep(p, yaw);
        }
        if (comp.Data.Count == 0) { Console.WriteLine("BPACTOR_FAIL template has no transform properties"); return; }

        var actor = new NormalExport(compTmpl);
        actor.ObjectName = FName.FromString(asset, actorName);
        actor.OuterIndex = new FPackageIndex(levelIdx1);
        actor.ClassIndex = new FPackageIndex(-clsIdx);
        actor.Data = new List<PropertyData>();
        // Unversioned serialisation resolves every property through its ancestry, so the
        // RootComponent entry must be cloned from a real actor export, not constructed.
        PropertyData rc = null;
        foreach (var ex2 in asset.Exports)
        {
            if (ex2 is not NormalExport ne2) continue;
            foreach (var p in ne2.Data)
            {
                if (p.Name?.Value?.Value == "RootComponent" && p is ObjectPropertyData) { rc = CloneProp(p); break; }
            }
            if (rc != null) break;
        }
        if (rc == null) { Console.WriteLine("BPACTOR_FAIL no RootComponent template property"); return; }
        ((ObjectPropertyData)rc).Value = new FPackageIndex(compIdx1);
        actor.Data.Add(rc);

        asset.Exports.Add(comp);
        asset.Exports.Add(actor);
        asset.Write(outPath);
        Console.WriteLine($"BPACTOR_OK {actorName} class={bpClass} pkg={pkgPath} at ({x},{y},{z}) yaw={yaw} comp={compIdx1} actor={actorIdx1} scenecls_import={sceneCls0 + 1} -> {outPath}");
    }

    // ---- move an existing actor by patching its root component transform --------
    static void MoveActor(string inPath, string outPath, string actorName, double x, double y, double z, double yaw)
    {
        var asset = new UAsset(inPath, EngineVersion.VER_UE5_5, Mappings);
        NormalExport actor = null;
        int actorIdx1 = -1;
        for (int i = 0; i < asset.Exports.Count; i++)
        {
            var nm = asset.Exports[i].ObjectName;
            var s = nm?.ToString();
            if (s == actorName || nm?.Value?.Value == actorName)
            { actor = asset.Exports[i] as NormalExport; actorIdx1 = i + 1; break; }
        }
        if (actor == null) { Console.WriteLine($"MOVEACTOR_FAIL no export named {actorName}"); return; }

        int rootIdx1 = -1;
        foreach (var p in actor.Data)
            if (p.Name?.Value?.Value == "RootComponent" && p is ObjectPropertyData op && op.Value != null)
                rootIdx1 = op.Value.Index;

        NormalExport comp = null;
        if (rootIdx1 > 0 && rootIdx1 - 1 < asset.Exports.Count) comp = asset.Exports[rootIdx1 - 1] as NormalExport;
        if (comp == null) { Console.WriteLine($"MOVEACTOR_FAIL {actorName} has no resolvable RootComponent"); return; }

        int hit = 0;
        foreach (var p in comp.Data)
        {
            var n = p.Name?.Value?.Value;
            if (n == "RelativeLocation") { SetVecDeep(p, x, y, z); hit++; }
            else if (n == "RelativeRotation") { SetRotDeep(p, yaw); hit++; }
        }
        asset.Write(outPath);
        Console.WriteLine($"MOVEACTOR_OK {actorName} root={rootIdx1} at ({x},{y},{z}) yaw={yaw} patched={hit} -> {outPath}");
    }

    // ---- bake navigation graph into the nav actor ------------------------------
    // Takes the JSON produced by the C1NavDump UE4SS probe (real BuildNavigation output
    // captured in the running game) and serialises it into AMotorTownNavigation as a real
    // FMTRoadGraphData property. The actor as shipped by NS has NO GraphData property at
    // all, so this creates it.
    static void RunBakeNav(string inPath, string outPath, string jsonPath)
    {
        var asset = new UAsset(inPath, EngineVersion.VER_UE5_5, Mappings);

        string ClassOf(UAssetAPI.ExportTypes.Export ex)
        {
            var ci = ex.ClassIndex;
            if (ci == null) return "?";
            int idx = ci.Index;
            if (idx < 0)
            {
                int ii = -idx - 1;
                return (ii >= 0 && ii < asset.Imports.Count) ? (asset.Imports[ii].ObjectName?.Value?.Value ?? "?") : "?";
            }
            if (idx > 0 && idx - 1 < asset.Exports.Count) return asset.Exports[idx - 1].ObjectName?.Value?.Value ?? "?";
            return "?";
        }

        NormalExport nav = null, road = null;
        int roadIdx1 = -1;
        for (int i = 0; i < asset.Exports.Count; i++)
        {
            var c = ClassOf(asset.Exports[i]);
            if (c == "MotorTownNavigation" && nav == null) nav = asset.Exports[i] as NormalExport;
            else if (c == "MotorTownRoad" && road == null) { road = asset.Exports[i] as NormalExport; roadIdx1 = i + 1; }
        }
        if (nav == null) { Console.WriteLine("BAKENAV_FAIL no MotorTownNavigation export"); return; }
        if (road == null) { Console.WriteLine("BAKENAV_FAIL no MotorTownRoad export"); return; }

        // an existing FVector instance to clone (keeps whatever precision/type the game uses)
        // FVector / FBox have native UAssetAPI types in this fork (BoxPropertyData showed up
        // for SplineBounds), so build them directly instead of cloning a template.
        void Type(PropertyData p, string t) { p.PropertyTypeName = MakeTypeName(asset, new FString(t)); }

        PropertyData Vec(string name, double x, double y, double z)
        {
            var v = new VectorPropertyData(FName.FromString(asset, name)) { Value = new FVector(x, y, z) };
            Type(v, "VectorProperty");
            return v;
        }
        PropertyData F(string n, double v) { var p = new FloatPropertyData(FName.FromString(asset, n)) { Value = (float)v }; Type(p, "FloatProperty"); return p; }
        PropertyData I(string n, int v) { var p = new IntPropertyData(FName.FromString(asset, n)) { Value = v }; Type(p, "IntProperty"); return p; }
        PropertyData U(string n, uint v) { var p = new UInt32PropertyData(FName.FromString(asset, n)) { Value = v }; Type(p, "UInt32Property"); return p; }

        using var doc = JsonDocument.Parse(File.ReadAllText(jsonPath));
        var rootEl = doc.RootElement;
        var nodesEl = rootEl.GetProperty("nodes");

        double Num(JsonElement e, string key)
            => e.TryGetProperty(key, out var v) && v.ValueKind == JsonValueKind.Number ? v.GetDouble() : 0.0;
        int Int(JsonElement e, string key, int dflt = 0)
            => e.TryGetProperty(key, out var v) && v.ValueKind == JsonValueKind.Number ? v.GetInt32() : dflt;

        var nodeList = new List<PropertyData>();
        foreach (var n in nodesEl.EnumerateArray())
        {
            var node = new StructPropertyData(FName.FromString(asset, "Nodes"), FName.FromString(asset, "MTRoadGraphNode"));
            Type(node, "StructProperty");
            node.StructType = FName.FromString(asset, "MTRoadGraphNode");

            // Each node belongs to its own road actor; a single hard-wired road reference is only
            // correct for one-road maps.
            int nodeRoadIdx1 = roadIdx1;
            if (n.TryGetProperty("road", out var roadEl) && roadEl.ValueKind == JsonValueKind.String)
            {
                string want = roadEl.GetString() ?? "";
                bool found = false;
                for (int ri = 0; ri < asset.Exports.Count; ri++)
                {
                    if ((asset.Exports[ri].ObjectName?.Value?.Value ?? "") == want) { nodeRoadIdx1 = ri + 1; found = true; break; }
                }
                if (!found)
                {
                    Console.WriteLine($"BAKENAV_WARN road not found: '{want}' (len={want.Length})");
                    string head = want.Substring(0, Math.Min(14, want.Length));
                    for (int ri = 0; ri < asset.Exports.Count; ri++)
                    {
                        string nm = asset.Exports[ri].ObjectName?.Value?.Value ?? "";
                        if (nm.StartsWith(head) || ClassOf(asset.Exports[ri]) == "MotorTownRoad")
                            Console.WriteLine($"   candidate export[{ri}] '{nm}' (len={nm.Length}) raw='{asset.Exports[ri].ObjectName}' cls={ClassOf(asset.Exports[ri])}");
                    }
                }
            }

            var r = new ObjectPropertyData(FName.FromString(asset, "Road")) { Value = new FPackageIndex(nodeRoadIdx1) };
            Type(r, "ObjectProperty");
            node.Value.Add(r);

            node.Value.Add(F("SplineDistance", Num(n, "sd")));
            node.Value.Add(Vec("AbsoluteLocation", Num(n, "x"), Num(n, "y"), Num(n, "z")));
            node.Value.Add(Vec("Direction", Num(n, "dx"), Num(n, "dy"), Num(n, "dz")));
            node.Value.Add(Vec("RightVector", Num(n, "rx"), Num(n, "ry"), Num(n, "rz")));
            node.Value.Add(I("NodeIndex", Int(n, "i")));
            node.Value.Add(F("LateralDistance", Num(n, "lat")));
            node.Value.Add(F("LateralOffset", Num(n, "off")));
            node.Value.Add(I("Lane", Int(n, "lane")));
            node.Value.Add(I("SplinePointIndex", Int(n, "spi")));
            node.Value.Add(U("Flags", (uint)Int(n, "flag")));
            node.Value.Add(F("AutoConnectDistance", Num(n, "auto")));

            var edgesArr = new ArrayPropertyData(FName.FromString(asset, "Edges"));
            Type(edgesArr, "ArrayProperty");
            edgesArr.ArrayType = FName.FromString(asset, "StructProperty");
            var edgeList = new List<PropertyData>();
            if (n.TryGetProperty("edges", out var edgesEl) && edgesEl.ValueKind == JsonValueKind.Array)
            {
                foreach (var e in edgesEl.EnumerateArray())
                {
                    var ed = new StructPropertyData(FName.FromString(asset, "Edges"), FName.FromString(asset, "MTRoadGraphNodeEdge"));
                    Type(ed, "StructProperty");
                    ed.StructType = FName.FromString(asset, "MTRoadGraphNodeEdge");
                    ed.Value.Add(I("NodeIndex", Int(e, "to", -1)));
                    ed.Value.Add(F("Cost", Num(e, "cost")));
                    ed.Value.Add(F("Distance", Num(e, "dist")));
                    ed.Value.Add(U("Flags", (uint)Int(e, "f")));
                    edgeList.Add(ed);
                }
            }
            edgesArr.Value = edgeList.ToArray();
            node.Value.Add(edgesArr);

            node.Value.Add(F("SpeedLimit", Num(n, "spd")));
            node.Value.Add(I("IslandId", Int(n, "isl")));
            node.Value.Add(I("CrossroadId", Int(n, "xrd")));
            node.Value.Add(F("RightSideClearance", Num(n, "clr")));
            nodeList.Add(node);
        }

        var nodesArr = new ArrayPropertyData(FName.FromString(asset, "Nodes"));
        Type(nodesArr, "ArrayProperty");
        nodesArr.ArrayType = FName.FromString(asset, "StructProperty");
        nodesArr.Value = nodeList.ToArray();

        var boxEl = rootEl.GetProperty("bounds");
        var gdBounds = new BoxPropertyData(FName.FromString(asset, "Bounds"))
        {
            Value = new TBox<FVector>(
                new FVector(Num(boxEl, "min_x"), Num(boxEl, "min_y"), Num(boxEl, "min_z")),
                new FVector(Num(boxEl, "max_x"), Num(boxEl, "max_y"), Num(boxEl, "max_z")), 1)
        };
        Type(gdBounds, "BoxProperty");

        var gd = new StructPropertyData(FName.FromString(asset, "GraphData"), FName.FromString(asset, "MTRoadGraphData"));
        Type(gd, "StructProperty");
        gd.StructType = FName.FromString(asset, "MTRoadGraphData");
        gd.Value.Add(nodesArr);
        gd.Value.Add(gdBounds);

        nav.Data.RemoveAll(p => p.Name?.Value?.Value == "GraphData");
        nav.Data.Add(gd);

        asset.Write(outPath);
        Console.WriteLine($"BAKENAV_OK nodes={nodeList.Count} -> {outPath}");
    }

    // Class name of an export, resolved through the import table (negative index) or exports.
    static string ClassNameOf(UAsset asset, UAssetAPI.ExportTypes.Export ex)
    {
        var ci = ex.ClassIndex;
        if (ci == null) return "?";
        int idx = ci.Index;
        if (idx < 0)
        {
            int ii = -idx - 1;
            return (ii >= 0 && ii < asset.Imports.Count) ? (asset.Imports[ii].ObjectName?.Value?.Value ?? "?") : "?";
        }
        if (idx > 0 && idx - 1 < asset.Exports.Count) return asset.Exports[idx - 1].ObjectName?.Value?.Value ?? "?";
        return "?";
    }

    static PropertyData CloneProp(PropertyData p)
    {
        var mi = typeof(object).GetMethod("MemberwiseClone", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance);
        var copy = (PropertyData)mi.Invoke(p, null);
        if (copy is StructPropertyData s)
        {
            var vals = new List<PropertyData>();
            foreach (var c in s.Value) vals.Add(CloneProp(c));
            s.Value = vals;
        }
        else if (copy is ArrayPropertyData a)
        {
            var vals = new List<PropertyData>();
            foreach (var c in a.Value) vals.Add(CloneProp(c));
            a.Value = vals.ToArray();
        }
        return copy;
    }

    // Does a parameter array on this export carry an entry with the given parameter name?
    static bool ContainsParam(System.Collections.Generic.IList<PropertyData> props, string arrName, string paramName)
    {
        var arr = props.OfType<ArrayPropertyData>().FirstOrDefault(p => p.Name?.Value?.Value == arrName);
        if (arr == null) return false;
        foreach (var el in arr.Value)
        {
            var sp = el as StructPropertyData;
            if (sp == null) continue;
            var info = sp.Value.OfType<StructPropertyData>().FirstOrDefault(s => s.Name?.Value?.Value == "ParameterInfo");
            var nm = info?.Value.OfType<NamePropertyData>().FirstOrDefault(n => n.Name?.Value?.Value == "Name");
            if ((nm?.Value?.ToString() ?? "") == paramName) return true;
        }
        return false;
    }

    static void SetEnumArray(ArrayPropertyData arr, JsonElement values,
        UAsset asset, string defaultEnumTypeName)
    {
        EnumPropertyData? templateEnum;
        if (arr.Value.Length > 0)
            templateEnum = (EnumPropertyData)arr.Value[0];
        else
        {
            // Template array is empty (e.g. TruckClasses on car tires): synthesize
            // an element so the enum type can be taken from the config instead.
            templateEnum = new EnumPropertyData(FName.FromString(asset, defaultEnumTypeName))
            {
                Name = FName.FromString(asset, defaultEnumTypeName)
            };
        }
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
            RichCurveKeyPropertyData curveKeyProp => new
            {
                interp_mode = curveKeyProp.Value.InterpMode.ToString(),
                tangent_mode = curveKeyProp.Value.TangentMode.ToString(),
                tangent_weight_mode = curveKeyProp.Value.TangentWeightMode.ToString(),
                time = curveKeyProp.Value.Time,
                value = curveKeyProp.Value.Value,
                arrive_tangent = curveKeyProp.Value.ArriveTangent,
                arrive_tangent_weight = curveKeyProp.Value.ArriveTangentWeight,
                leave_tangent = curveKeyProp.Value.LeaveTangent,
                leave_tangent_weight = curveKeyProp.Value.LeaveTangentWeight,
            },
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
