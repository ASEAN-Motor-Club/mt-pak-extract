using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using UAssetAPI;
using UAssetAPI.ExportTypes;
using UAssetAPI.PropertyTypes.Objects;
using UAssetAPI.PropertyTypes.Structs;
using UAssetAPI.UnrealTypes;
using UAssetAPI.Unversioned;

namespace UMapPatch
{
    /// <summary>
    /// In-place rewrite of a cooked Motor Town mod level cloned from the Nordschleife map:
    ///  - MotorTownRoad spline positions and MotorTownRaceSection gate transforms
    ///  - static mesh actor set repointed at our own cell meshes (--geom)
    /// Every edit mutates property values only, so the package layout never changes
    /// (the input round-trips byte-identically through UAssetAPI first).
    /// </summary>
    static class Program
    {
        static Usmap Mappings;

        static int Main(string[] args)
        {
            if (args.Length < 1)
            {
                Usage();
                return 2;
            }
            string inPath = args[0];
            string jsonPath = args.Length > 1 && !args[1].StartsWith("--") ? args[1] : null;
            string outPath = args.Length > 2 && !args[2].StartsWith("--") ? args[2] : null;
            bool geom = args.Contains("--geom");
            bool inspect = args.Contains("--inspect");
            bool verify = args.Contains("--verify");
            bool tree = args.Contains("--tree");
            int ui = Array.IndexOf(args, "--usmap");
            string usmap = ui >= 0 && args.Length > ui + 1 ? args[ui + 1] : "Mappings.usmap";
            Mappings = new Usmap(usmap);

            var asset = new UAsset(inPath, EngineVersion.VER_UE5_5, Mappings);
            var roads = ExportsOfClass(asset, "MotorTownRoad").ToList();
            var gates = ExportsOfClass(asset, "MotorTownRaceSection").ToList();
            var areas = ExportsOfClass(asset, "MTAAreaVolume").ToList();
            Console.WriteLine($"exports={asset.Exports.Count} imports={asset.Imports.Count} roads={roads.Count} gates={gates.Count} areas={areas.Count}");

            if (tree)
            {
                var tr = roads.OrderByDescending(r => GetSplinePointStructs(asset, r)?.Count ?? 0).FirstOrDefault();
                DumpProp(GetSplinePointStructs(asset, tr)[0], 0, 5);
                return 0;
            }
            if (verify) { VerifyRoads(asset, roads, gates); return 0; }
            if (inspect) { InspectAll(asset, roads, gates, areas); return 0; }
            if (args.Contains("--rename")) return RenameNames(asset, outPath);
            if (args.Contains("--spawn"))
            {
                var si = Array.IndexOf(args, "--spawn");
                var sp = si + 1 < args.Length ? args[si + 1].Split(",") : Array.Empty<string>();
                if (sp.Length != 3) { Console.WriteLine("--spawn needs x,y,z"); return 2; }
                return SetSpawn(asset, double.Parse(sp[0]), double.Parse(sp[1]), double.Parse(sp[2]), outPath);
            }
            if (args.Contains("--repoint")) return Repoint(asset, outPath, args.Contains("--sky-only"));
            if (args.Contains("--comps")) return DumpComps(asset);
            if (args.Contains("--nocull")) return ClearCull(asset, outPath);
            if (args.Contains("--owners")) return DumpOwners(asset);
            if (args.Contains("--unhide")) return UnhideCells(asset, outPath);
            if (args.Contains("--place"))
            {
                var pi = Array.IndexOf(args, "--place");
                var parts = pi + 1 < args.Length ? args[pi + 1].Split(',') : Array.Empty<string>();
                if (parts.Length != 3) { Console.WriteLine("--place needs x,y,z"); return 2; }
                int rc = PlaceComps(asset, double.Parse(parts[0]), double.Parse(parts[1]), double.Parse(parts[2]));
                if (rc == 0 && outPath != null) { asset.Write(outPath); Console.WriteLine($"written {outPath}"); }
                return rc;
            }
            if (args.Contains("--imports")) return DumpImports(asset);
            if (args.Contains("--drop-mod-actors")) return DropModActors(asset, outPath);
            if (args.Contains("--fix-level")) return PatchLevel(asset, jsonPath, outPath);

            if (geom) return PatchGeometry(asset, jsonPath, outPath);
            return PatchRoads(asset, jsonPath, outPath, roads, gates);
        }

        static void Usage()
        {
            Console.WriteLine("usage: UMapPatch <in.umap> <patch.json> <out.umap> [--geom] [--inspect] [--verify] [--tree] [--usmap Mappings.usmap]");
        }

        // ---------- package helpers ----------

        static string Name(UAsset a, Export e)
        {
            try { return e.ObjectName.Value.Value; } catch { return e.ObjectName.ToString(); }
        }

        static string ClassName(UAsset a, Export e)
        {
            try
            {
                var ci = e.ClassIndex;
                if (ci.IsImport()) return a.Imports[-ci.Index - 1].ObjectName.Value.Value;
                if (ci.IsExport()) return (a.Exports[ci.Index] as Export)?.ObjectName.Value.Value;
            }
            catch { }
            return null;
        }

        static IEnumerable<NormalExport> ExportsOfClass(UAsset a, string cls)
        {
            foreach (var e in a.Exports)
            {
                var ne = e as NormalExport;
                if (ne == null) continue;
                if (ClassName(a, ne) == cls) yield return ne;
            }
        }

        static NormalExport ExportAt(UAsset a, FPackageIndex idx)
        {
            if (idx == null || !idx.IsExport()) return null;
            return a.Exports[idx.Index] as NormalExport;
        }

        static PropertyData Prop(NormalExport e, string name)
        {
            if (e?.Data == null) return null;
            foreach (var p in e.Data)
            {
                string pn = null;
                try { pn = p.Name.Value.Value; } catch { }
                if (pn == name) return p;
            }
            return null;
        }

        static PropertyData Child(PropertyData parent, string name)
        {
            var list = (parent as StructPropertyData)?.Value;
            if (list == null) return null;
            foreach (var p in list)
            {
                string pn = null;
                try { pn = p.Name.Value.Value; } catch { }
                if (pn == name) return p;
            }
            return null;
        }

        // ---------- geometry: static mesh actors -> our cells ----------

        // ---------- repoint Nordschleife class imports to vanilla MT ----------

        static int Repoint(UAsset a, string outPath, bool skyOnly = false)
        {
            var map = skyOnly
                ? new (string from, string to)[] { ("/Game/Mods/Nordschleife/Sky/BP_NS_Sky", "/Game/Blueprints/MTSunSky") }
                : new (string from, string to)[]
            {
                ("/Game/Mods/Nordschleife/Sky/BP_NS_Sky",   "/Game/Blueprints/MTSunSky"),
                ("/Game/Mods/Nordschleife/Props/BP_NS_Prop", "/Game/Blueprints/ActorPreviewBP"),
            };
            var names = skyOnly
                ? new (string from, string to)[] { ("Default__BP_NS_Sky_C", "Default__MTSunSky_C"), ("BP_NS_Sky_C", "MTSunSky_C") }
                : new (string from, string to)[]
            {
                ("Default__BP_NS_Sky_C",  "Default__MTSunSky_C"),
                ("Default__BP_NS_Prop_C", "Default__ActorPreviewBP_C"),
                ("BP_NS_Sky_C",  "MTSunSky_C"),
                ("BP_NS_Prop_C", "ActorPreviewBP_C"),
            };
            int pk = 0, nm = 0;
            for (int i = 0; i < a.Imports.Count; i++)
            {
                var imp = a.Imports[i];
                string cur = imp.ObjectName.ToString();
                foreach (var (from, to) in map)
                {
                    if (cur == from) { imp.ObjectName = FName.FromString(a, to); pk++; }
                }
                foreach (var (from, to) in names)
                {
                    if (cur == from) { imp.ObjectName = FName.FromString(a, to); nm++; }
                }
            }
            Console.WriteLine($"repointed packages={pk} classnames={nm}");
            a.Write(outPath);
            Console.WriteLine($"written {outPath}");
            return 0;
        }

        static readonly (string from, string to)[] Renames = new[]
        {
            ("/Game/Mods/Nordschleife/Maps/NS_Nordschleife_Roads", "/Game/Mods/C1/Maps/C1_Roads"),
            ("/Game/Mods/Nordschleife/Maps/NS_Nordschleife",       "/Game/Mods/C1/Maps/C1"),
            ("NS_Nordschleife_Roads",                              "C1_Roads"),
            ("NS_Nordschleife",                                    "C1"),
        };

        static int RenameNames(UAsset a, string outPath)
        {
            int changed = 0;
            var nm = a.GetNameMapIndexList();
            for (int i = 0; i < nm.Count; i++)
            {
                string cur = nm[i].Value;
                foreach (var (from, to) in Renames)
                {
                    if (cur == from)
                    {
                        a.SetNameReference(i, new FString(to));
                        Console.WriteLine($"  name[{i}] '{from}' -> '{to}'");
                        changed++;
                        break;
                    }
                }
            }
            Console.WriteLine($"renamed entries={changed}");
            a.Write(outPath);
            Console.WriteLine($"written {outPath}");
            return changed > 0 ? 0 : 1;
        }

        static int SetSpawn(UAsset a, double x, double y, double z, string outPath)
        {
            var starts = ExportsOfClass(a, "PlayerStart").ToList();
            if (starts.Count == 0) { Console.WriteLine("no PlayerStart"); return 1; }
            var ps = starts[0];
            // template struct to clone: any StaticMeshComponent carrying RelativeLocation
            StructPropertyData tpl = null;
            foreach (var e in a.Exports.OfType<NormalExport>())
                if (Prop(e, "RelativeLocation") is StructPropertyData rl) { tpl = rl; break; }
            if (tpl == null) { Console.WriteLine("no RelativeLocation template found"); return 1; }

            int done = 0;
            var rc0 = Prop(ps, "RootComponent") as ObjectPropertyData;
            var cur = (rc0 != null ? ExportAt(a, rc0.Value) : null) as NormalExport;
            for (int hop = 0; hop < 4 && cur != null; hop++)
            {
                // only scene components carry RelativeLocation; writing it onto an
                // actor export throws "No valid property in class ..." at save time
                if (!ClassName(a, cur).EndsWith("Component"))
                {
                    cur = null; break;
                }
                if (Prop(cur, "RelativeLocation") is StructPropertyData loc)
                {
                    SetVec(loc, x, y, z); done++;
                }
                else
                {
                    var clone = Clone(tpl);
                    SetVec(clone, x, y, z);
                    cur.Data ??= new List<PropertyData>();
                    cur.Data.Add(clone);
                    done++;
                }
                var ap = Prop(cur, "AttachParent") as ObjectPropertyData;
                cur = (ap != null ? ExportAt(a, ap.Value) : null) as NormalExport;
            }
            Console.WriteLine($"spawn components positioned={done} at ({x},{y},{z})");
            a.Write(outPath);
            Console.WriteLine($"written {outPath}");
            return 0;
        }

        static StructPropertyData Clone(StructPropertyData src)
        {
            var copy = new StructPropertyData(src.Name, src.StructType);
            foreach (var c in src.Value) copy.Value.Add(DeepCopy(c));
            return copy;
        }

        static PropertyData DeepCopy(PropertyData p)
        {
            if (p is DoublePropertyData d) return new DoublePropertyData { Name = d.Name, Value = d.Value };
            if (p is FloatPropertyData f) return new FloatPropertyData { Name = f.Name, Value = f.Value };
            if (p is IntPropertyData i) return new IntPropertyData { Name = i.Name, Value = i.Value };
            if (p is StructPropertyData s)
            {
                var c = new StructPropertyData(s.Name, s.StructType);
                foreach (var k in s.Value) c.Value.Add(DeepCopy(k));
                return c;
            }
            return p;
        }

        static int PlaceComps(UAsset a, double x, double y, double z)
        {
            int n = 0;
            foreach (var e in a.Exports)
            {
                if (e is not NormalExport ne || ClassName(a, ne) != "StaticMeshComponent") continue;
                if (Prop(ne, "StaticMesh") is not ObjectPropertyData sm || sm.Value.Index >= 0) continue;
                if (Prop(ne, "RelativeLocation") is StructPropertyData loc)
                {
                    if (SetVec(loc, x, y, z)) n++;
                }
            }
            Console.WriteLine($"placed {n} components at ({x},{y},{z})");
            return 0;
        }

        static int DumpComps(UAsset a)
        {
            int n = 0;
            foreach (var e in a.Exports)
            {
                if (e is not NormalExport ne || ClassName(a, ne) != "StaticMeshComponent") continue;
                if (Prop(ne, "StaticMesh") is not ObjectPropertyData sm || sm.Value.Index >= 0) continue;
                string mesh = sm.Value.Index < 0 && -sm.Value.Index - 1 < a.Imports.Count
                    ? a.Imports[-sm.Value.Index - 1].ObjectName.ToString() : "?";
                string loc = "?";
                if (Prop(ne, "RelativeLocation") is StructPropertyData rl) loc = VecStr(rl);
                Console.WriteLine($"comp[{a.Exports.IndexOf(ne)}] mesh={mesh} loc={loc}");
                n++;
            }
            Console.WriteLine($"components with mesh={n}");
            return 0;
        }

        static int DumpImports(UAsset a)
        {
            for (int i = 0; i < a.Imports.Count; i++)
            {
                var imp = a.Imports[i];
                string cls = imp.ClassName != null ? imp.ClassName.Value.Value : "-";
                string outer = "pkg";
                if (imp.OuterIndex != null && imp.OuterIndex.Index < 0) outer = a.Imports[-imp.OuterIndex.Index - 1].ObjectName.Value.Value;
                Console.WriteLine($"Import[{i}]: {imp.ObjectName.Value.Value} | class={cls} | outer={outer}");
            }
            return 0;
        }

        static int PatchGeometry(UAsset asset, string jsonPath, string outPath)
        {
            if (jsonPath == null || outPath == null) { Usage(); return 2; }
            var doc = JsonDocument.Parse(File.ReadAllText(jsonPath));
            var meshes = doc.RootElement.GetProperty("meshes").EnumerateArray().Select(e => e.GetString()).ToList();
            Console.WriteLine($"target meshes={meshes.Count}");

            var comps = new List<NormalExport>();
            foreach (var e in asset.Exports)
            {
                var ne = e as NormalExport;
                if (ne != null && ClassName(asset, ne) == "StaticMeshComponent") comps.Add(ne);
            }
            Console.WriteLine($"staticMeshComponents={comps.Count}");

            // component index -> static mesh import index, plus the reverse usage map
            var compImport = new Dictionary<int, int>();
            var users = new Dictionary<int, List<int>>();
            for (int i = 0; i < comps.Count; i++)
            {
                if (!(Prop(comps[i], "StaticMesh") is ObjectPropertyData sm)) continue;
                var idx = sm.Value;
                if (idx == null || idx.Index >= 0) continue;
                int imp = -idx.Index - 1;
                compImport[i] = imp;
                if (!users.TryGetValue(imp, out var list)) users[imp] = list = new List<int>();
                list.Add(i);
            }
            Console.WriteLine($"components with mesh={compImport.Count} distinctImports={users.Count}");

            // one import per target mesh, taking the least-shared ones first
            var picks = users.OrderBy(kv => kv.Value.Count).ThenBy(kv => kv.Key).Take(meshes.Count).ToList();
            if (picks.Count < meshes.Count)
            {
                Console.WriteLine($"ERROR: only {picks.Count} distinct mesh imports for {meshes.Count} meshes");
                return 1;
            }

            var repointedImports = new HashSet<int>();
            int repointed = 0;
            for (int m = 0; m < meshes.Count; m++)
            {
                int impIdx = picks[m].Key;
                string mesh = meshes[m];
                var meshImport = asset.Imports[impIdx];
                var outer = meshImport.OuterIndex;
                if (outer == null || outer.Index >= 0) { Console.WriteLine($"  skip import {impIdx}: outer not an import"); continue; }
                var pkgImport = asset.Imports[-outer.Index - 1];

                meshImport.ObjectName = FName.FromString(asset, mesh);
                pkgImport.ObjectName = FName.FromString(asset, "/Game/Mods/C1/Meshes/" + mesh);
                repointedImports.Add(impIdx);

                int owner = picks[m].Value[0];
                SetVisible(asset, comps[owner], true);
                SetTransform(comps[owner], 0, 0, 0, 0, 0, 0, 1, 1, 1);
                foreach (int other in picks[m].Value.Skip(1)) NullMesh(asset, comps[other]);
                repointed++;
            }

            int cleared = 0;
            foreach (var kv in users)
            {
                if (repointedImports.Contains(kv.Key)) continue;
                foreach (int ci in kv.Value) { NullMesh(asset, comps[ci]); cleared++; }
            }

            asset.Write(outPath);
            Console.WriteLine($"repointed={repointed} cleared={cleared} written={outPath}");
            return 0;
        }

        static void NullMesh(UAsset asset, NormalExport comp)
        {
            if (Prop(comp, "StaticMesh") is ObjectPropertyData sm) sm.Value = FPackageIndex.FromRawIndex(0);
            SetVisible(asset, comp, false);
        }

        static void SetVisible(UAsset asset, NormalExport comp, bool visible)
        {
            foreach (var p in comp.Data)
            {
                string pn = null; try { pn = p.Name.Value.Value; } catch { }
                if (pn == "bVisible" && p is BoolPropertyData b) b.Value = visible;
            }
            if (asset != null && comp.OuterIndex != null && comp.OuterIndex.IsExport())
            {
                var actor = asset.Exports[comp.OuterIndex.Index] as NormalExport;
                if (actor?.Data != null)
                {
                    foreach (var p in actor.Data)
                    {
                        string pn = null; try { pn = p.Name.Value.Value; } catch { }
                        if (pn == "bHidden" && p is BoolPropertyData b) b.Value = !visible;
                    }
                }
            }
        }

        static void SetTransform(NormalExport comp, double x, double y, double z,
                                 double pitch, double yaw, double roll, double sx, double sy, double sz)
        {
            if (Prop(comp, "RelativeLocation") is StructPropertyData loc) SetVec(loc, x, y, z);
            if (Prop(comp, "RelativeRotation") is StructPropertyData rot)
            {
                var rp = FindDeep<RotatorPropertyData>(rot);
                if (rp != null) rp.Value = new FRotator(pitch, yaw, roll);
            }
            if (Prop(comp, "RelativeScale3D") is StructPropertyData sc)
            {
                var vp = FindDeep<VectorPropertyData>(sc);
                if (vp != null) vp.Value = new FVector(sx, sy, sz);
            }
        }

        // ---------- drop actors whose classes live in the source mod ----------

        static int DropModActors(UAsset asset, string outPath)
        {
            if (outPath == null) { Usage(); return 2; }
            var sourceClasses = new HashSet<string> { "BP_NS_Prop_C", "BP_NS_Sky_C", "GarageActorBP_C", "FuelPump_01A_C" };

            int compsCleared = 0;
            foreach (var e in asset.Exports)
            {
                var ne = e as NormalExport;
                if (ne == null || ClassName(asset, ne) != "ChildActorComponent") continue;
                if (!(Prop(ne, "ChildActorClass") is ObjectPropertyData cls)) continue;
                var v = cls.Value;
                if (v == null || v.Index >= 0) continue;
                string imp = asset.Imports[-v.Index - 1].ObjectName.Value.Value;
                if (!sourceClasses.Contains(imp)) continue;
                cls.Value = FPackageIndex.FromRawIndex(0);
                compsCleared++;
            }

            int hidden = 0;
            foreach (var e in asset.Exports)
            {
                var ne = e as NormalExport;
                if (ne == null) continue;
                if (!sourceClasses.Contains(ClassName(asset, ne) ?? "")) continue;
                bool set = false;
                foreach (var p in ne.Data)
                {
                    string pn = null; try { pn = p.Name.Value.Value; } catch { }
                    if (pn == "bHidden" && p is BoolPropertyData b) { b.Value = true; set = true; }
                }
                if (!set && ne.Data != null)
                {
                    var bp = new BoolPropertyData(FName.FromString(asset, "bHidden"));
                    bp.Value = true;
                    ne.Data.Add(bp);
                }
                hidden++;
            }

            asset.Write(outPath);
            Console.WriteLine($"dropped childComponents={compsCleared} hiddenActors={hidden}; written {outPath}");
            return 0;
        }

        // ---------- level plumbing: streamed sublevel + spawns ----------

        static int PatchLevel(UAsset a, string jsonPath, string outPath)
        {
            if (jsonPath == null || outPath == null) { Usage(); return 2; }
            var doc = JsonDocument.Parse(File.ReadAllText(jsonPath));
            int streamed = 0, spawns = 0;

            if (doc.RootElement.TryGetProperty("stream", out var st))
            {
                string pkg = st.GetProperty("package").GetString();
                string asn = st.GetProperty("asset").GetString();
                foreach (var e in a.Exports.OfType<NormalExport>())
                {
                    if (!ClassName(a, e).Contains("LevelStreaming")) continue;
                    if (Prop(e, "WorldAsset") is SoftObjectPropertyData so)
                    {
                        var path = so.Value;   // FSoftObjectPath is a struct: mutate a copy, then assign back
                        path.AssetPath = new FTopLevelAssetPath(FName.FromString(a, pkg), FName.FromString(a, asn));
                        path.SubPathString = new FString(string.Empty);
                        so.Value = path;
                        streamed++;
                    }
                }
            }

            if (doc.RootElement.TryGetProperty("playerstarts", out var ps))
            {
                var starts = ExportsOfClass(a, "PlayerStart").ToList();
                Console.WriteLine($"playerstart exports found={starts.Count}");
                int i = 0;
                foreach (var s in starts)
                {
                    var sIdx = a.Exports.IndexOf(s);
                    Console.WriteLine($"  [{sIdx}] class={ClassName(a, s)} props={(s.Data == null ? "<null>" : string.Join(",", s.Data.Select(p => p.Name.ToString())))}");
                    var rcProbe = Prop(s, "RootComponent") as ObjectPropertyData;
                    var hostProbe = (rcProbe != null ? ExportAt(a, rcProbe.Value) : null) ?? s;
                    var rl = Prop(hostProbe, "RelativeLocation") as StructPropertyData;
                    Console.WriteLine($"      host[{a.Exports.IndexOf(hostProbe)}] class={ClassName(a, hostProbe)} props={(hostProbe.Data == null ? "<null>" : string.Join(",", hostProbe.Data.Select(p => p.Name.ToString())))}");
                    Console.WriteLine($"      root={(rcProbe != null)} rl={(rl != null ? VecStr(rl) : "<missing>")}");
                    {
                        var cur = hostProbe;
                        for (int hop = 0; hop < 6 && cur != null; hop++)
                        {
                            var ap = Prop(cur, "AttachParent") as ObjectPropertyData;
                            var outer = (cur.OuterIndex is FPackageIndex oi && oi.Index > 0 && oi.Index <= a.Exports.Count) ? a.Exports[oi.Index - 1] as NormalExport : null;
                            string outerDesc = outer == null ? "-" : $"{ClassName(a, outer)}";
                            string vec = "";
                            if (outer != null && Prop(outer, "RelativeLocation") is StructPropertyData orl) vec = VecStr(orl);
                            Console.WriteLine($"        hop{hop} cur[{a.Exports.IndexOf(cur)}]={ClassName(a, cur)} attachParent={(ap != null ? ap.Value.Index : 0)} outer={outerDesc} outerLoc={vec}");
                            cur = (ap != null ? ExportAt(a, ap.Value) : null) as NormalExport;
                        }
                    }
                    if (i >= ps.GetArrayLength()) break;
                    var d = ps[i];
                    var loc = d.GetProperty("loc");
                    double yaw = d.TryGetProperty("yaw", out var y) ? y.GetDouble() : 0.0;
                    bool ok = PatchGate(a, s, loc[0].GetDouble(), loc[1].GetDouble(), loc[2].GetDouble(), yaw);
                    var rl2 = Prop(hostProbe, "RelativeLocation") as StructPropertyData;
                    Console.WriteLine($"      after={(rl2 != null ? VecStr(rl2) : "<missing>")} target=({loc[0]},{loc[1]},{loc[2]}) yaw={yaw}");
                    if (!ok) Console.WriteLine("      WARN playerstart has no writable RelativeLocation - NOT positioned (inherits parent transform)");
                    spawns++; i++;
                }
            }

            a.Write(outPath);
            Console.WriteLine($"streamed re-pointed={streamed} playerstarts moved={spawns}; written {outPath}");
            return 0;
        }

        // ---------- roads + gates ----------

        static int PatchRoads(UAsset asset, string jsonPath, string outPath, List<NormalExport> roads, List<NormalExport> gates)
        {
            if (jsonPath == null || outPath == null) { Usage(); return 2; }
            var doc = JsonDocument.Parse(File.ReadAllText(jsonPath));
            var spline = doc.RootElement.GetProperty("spline");
            var gateJson = doc.RootElement.GetProperty("gates");

            int sPts = 0, gDone = 0;
            var ordered = roads.OrderByDescending(r => GetSplinePointStructs(asset, r)?.Count ?? 0).ToList();
            foreach (var road in ordered)
            {
                var points = GetSplinePointStructs(asset, road);
                if (points == null) { Console.WriteLine($"no spline on {Name(asset, road)}"); continue; }
                int n = Math.Min(points.Count, spline.GetArrayLength());
                for (int i = 0; i < n; i++)
                {
                    var arr = spline[i];
                    var outVal = Child(points[i], "OutVal") as StructPropertyData;
                    if (outVal == null) continue;
                    SetVec(outVal, arr[0].GetDouble(), arr[1].GetDouble(), arr[2].GetDouble());
                    sPts++;
                }
                if (Prop(road, "CourseKey") is NamePropertyData ck) ck.Value = FName.FromString(asset, "C1_Shuto");
                Console.WriteLine($"spline {Name(asset, road)}: patched {n}/{points.Count}");
                break;
            }

            foreach (var gate in gates)
            {
                if (gDone >= gateJson.GetArrayLength()) break;
                var gd = gateJson[gDone];
                var loc = gd.GetProperty("loc");
                PatchGate(asset, gate, loc[0].GetDouble(), loc[1].GetDouble(), loc[2].GetDouble(),
                          gd.GetProperty("yaw").GetDouble());
                gDone++;
            }

            asset.Write(outPath);
            Console.WriteLine($"patched splinePoints={sPts} gates={gDone}; written {outPath}");
            return 0;
        }

        static List<StructPropertyData> GetSplinePointStructs(UAsset a, NormalExport road)
        {
            var comps = new List<NormalExport>();
            int roadIdx = a.Exports.IndexOf(road);
            foreach (var cand in a.Exports)
            {
                var ce = cand as NormalExport;
                if (ce == null) continue;
                if (ce.OuterIndex == null || ce.OuterIndex.Index != roadIdx) continue;
                if (ClassName(a, ce) == "SplineComponent") comps.Add(ce);
            }
            foreach (var comp in comps)
            {
                var curves = Prop(comp, "SplineCurves") as StructPropertyData;
                var position = Child(curves, "Position") as StructPropertyData;
                var points = Child(position, "Points") as ArrayPropertyData;
                if (points != null) return points.Value.OfType<StructPropertyData>().ToList();
            }
            return null;
        }

        static bool PatchGate(UAsset a, NormalExport gate, double x, double y, double z, double yaw)
        {
            var rc = Prop(gate, "RootComponent") as ObjectPropertyData;
            var host = (rc != null ? ExportAt(a, rc.Value) : null) ?? gate;
            bool moved = false;
            if (Prop(host, "RelativeLocation") is StructPropertyData loc) moved = SetVec(loc, x, y, z);
            if (Prop(host, "RelativeRotation") is StructPropertyData rot)
            {
                var rp = FindDeep<RotatorPropertyData>(rot);
                if (rp != null) rp.Value = new FRotator(0f, (float)yaw, 0f);
            }
            if (Prop(gate, "CourseName") is NamePropertyData course) course.Value = FName.FromString(a, "C1_Shuto");
            return moved;
        }

        // ---------- math helpers ----------

        static T FindDeep<T>(PropertyData p, int depth = 0) where T : PropertyData
        {
            if (p is T hit) return hit;
            var sp = p as StructPropertyData;
            if (sp?.Value == null || depth > 3) return null;
            foreach (var c in sp.Value)
            {
                var f = FindDeep<T>(c, depth + 1);
                if (f != null) return f;
            }
            return null;
        }

        static bool SetVec(StructPropertyData v, double x, double y, double z)
        {
            var vp = FindDeep<VectorPropertyData>(v);
            if (vp == null) return false;
            vp.Value = new FVector(x, y, z);
            return true;
        }

        static string VecStr(StructPropertyData v)
        {
            var vp = FindDeep<VectorPropertyData>(v);
            if (vp != null) return string.Format("({0:F1}, {1:F1}, {2:F1})", vp.Value.X, vp.Value.Y, vp.Value.Z);
            var rp = FindDeep<RotatorPropertyData>(v);
            if (rp != null) return string.Format("(P{0:F1}, Y{1:F1}, R{2:F1})", rp.Value.Pitch, rp.Value.Yaw, rp.Value.Roll);
            return "null";
        }

        // ---------- diagnostics ----------

        static void VerifyRoads(UAsset asset, List<NormalExport> roads, List<NormalExport> gates)
        {
            if (roads.Count == 0) { VerifyGeometry(asset); return; }
            var rr = roads.OrderByDescending(r => GetSplinePointStructs(asset, r)?.Count ?? 0).First();
            var pts = GetSplinePointStructs(asset, rr);
            foreach (int i in new[] { 0, 1, 500, 1009, 1010 }.Where(i => i < pts.Count))
                Console.WriteLine($"pt[{i}] = {VecStr(Child(pts[i], "OutVal") as StructPropertyData)}");
            var g0 = gates.FirstOrDefault();
            if (g0 != null)
            {
                var box = Prop(g0, "RootComponent") is ObjectPropertyData rc2 ? ExportAt(asset, rc2.Value) : null;
                Console.WriteLine($"gate0 loc={VecStr(Prop(box ?? g0, "RelativeLocation") as StructPropertyData)} rot={VecStr(Prop(box ?? g0, "RelativeRotation") as StructPropertyData)} course={(Prop(g0, "CourseName") as NamePropertyData)?.Value}");
            }
        }

        static int ClearCull(UAsset asset, string outPath)
        {
            if (outPath == null) { Console.WriteLine("--nocull needs an output path"); return 2; }
            int changed = 0, cleared = 0, scanned = 0;
            foreach (var c in ExportsOfClass(asset, "StaticMeshComponent"))
            {
                scanned++;
                var sm = Prop(c, "StaticMesh") as ObjectPropertyData;
                if (sm?.Value == null || sm.Value.Index >= 0) continue;
                var imp = asset.Imports[-sm.Value.Index - 1];
                var outer = imp.OuterIndex;
                string pkg = outer != null && outer.Index < 0 ? asset.Imports[-outer.Index - 1].ObjectName.Value.Value : "?";
                if (!pkg.StartsWith("/Game/Mods/C1/")) continue;

                bool hit = false;
                foreach (var p in c.Data)
                {
                    string pn = null; try { pn = p.Name.Value.Value; } catch { }
                    if (pn != "MaxDrawDistance" && pn != "LDMaxDrawDistance") continue;
                    if (p is FloatPropertyData f) { f.Value = 0f; hit = true; }
                }
                if (!hit)
                {
                    foreach (var nm in new[] { "MaxDrawDistance", "LDMaxDrawDistance" })
                    {
                        var fp = new FloatPropertyData { Name = FName.FromString(asset, nm) };
                        fp.Value = 0f;
                        c.Data.Add(fp);
                    }
                }
                if (Prop(c, "bVisible") is BoolPropertyData bv) bv.Value = true;
                cleared++;
                if (hit) changed++;
            }
            asset.Write(outPath);
            Console.WriteLine($"nocull scanned={scanned} ours={cleared} had_distance={changed}; written {outPath}");
            return 0;
        }

        static int DumpOwners(UAsset asset)
        {
            var comps = ExportsOfClass(asset, "StaticMeshComponent").ToList();
            Console.WriteLine($"mesh_components={comps.Count}");
            var ownerCount = new Dictionary<string, int>();
            foreach (var c in comps)
            {
                var sm = Prop(c, "StaticMesh") as ObjectPropertyData;
                if (sm?.Value == null || sm.Value.Index >= 0) continue;
                var imp = asset.Imports[-sm.Value.Index - 1];
                string mesh = imp.ObjectName.Value.Value;
                string ownerName = "?", ownerClass = "?";
                bool hidden = false;
                if (c.OuterIndex.Index > 0)
                {
                    var owner = asset.Exports[c.OuterIndex.Index - 1] as NormalExport;
                    if (owner != null)
                    {
                        ownerName = Name(asset, owner);
                        ownerClass = ClassName(asset, owner) ?? "?";
                        if (Prop(owner, "bHidden") is BoolPropertyData bh) hidden = bh.Value;
                    }
                }
                var key = ownerClass + "::" + ownerName;
                ownerCount[key] = ownerCount.TryGetValue(key, out var n) ? n + 1 : 1;
                Console.WriteLine($"comp[{asset.Exports.IndexOf(c) + 1}] mesh={mesh} owner={ownerName} class={ownerClass} hidden={hidden} outer={c.OuterIndex.Index}");
            }
            Console.WriteLine("distinct_owners=" + ownerCount.Count);
            foreach (var kv in ownerCount.OrderByDescending(k => k.Value).Take(10))
                Console.WriteLine($"  owner {kv.Key} x{kv.Value}");
            return 0;
        }

        static int UnhideCells(UAsset asset, string outPath)
        {
            if (outPath == null) { Console.WriteLine("--unhide needs an output path"); return 2; }
            int actors = 0, comps = 0;
            foreach (var c in ExportsOfClass(asset, "StaticMeshComponent"))
            {
                var sm = Prop(c, "StaticMesh") as ObjectPropertyData;
                if (sm?.Value == null || sm.Value.Index >= 0) continue;
                var imp = asset.Imports[-sm.Value.Index - 1];
                var outer = imp.OuterIndex;
                string pkg = outer != null && outer.Index < 0 ? asset.Imports[-outer.Index - 1].ObjectName.Value.Value : "?";
                if (!pkg.StartsWith("/Game/Mods/C1/")) continue;

                if (Prop(c, "bVisible") is BoolPropertyData cb) cb.Value = true;
                comps++;
                if (c.OuterIndex.Index > 0)
                {
                    var owner = asset.Exports[c.OuterIndex.Index - 1] as NormalExport;
                    if (owner == null) continue;
                    bool had = false;
                    if (Prop(owner, "bHidden") is BoolPropertyData bh) { bh.Value = false; had = true; }
                    if (Prop(owner, "bActorHiddenInGame") is BoolPropertyData bg) { bg.Value = false; had = true; }
                    if (!had)
                    {
                        var np = new BoolPropertyData(FName.FromString(asset, "bHidden"));
                        np.Value = false;
                        owner.Data.Add(np);
                    }
                    actors++;
                }
            }
            asset.Write(outPath);
            Console.WriteLine($"unhide components={comps} actors={actors}; written {outPath}");
            return 0;
        }

        static void VerifyGeometry(UAsset asset)
        {
            var comps = ExportsOfClass(asset, "StaticMeshComponent").ToList();
            int ours = 0, nulled = 0, other = 0, visible = 0;
            foreach (var c in comps)
            {
                if (Prop(c, "bVisible") is BoolPropertyData bv && bv.Value) visible++;
                var sm = Prop(c, "StaticMesh") as ObjectPropertyData;
                if (sm?.Value == null || sm.Value.Index == 0) { nulled++; continue; }
                if (sm.Value.Index < 0)
                {
                    var imp = asset.Imports[-sm.Value.Index - 1];
                    var outer = imp.OuterIndex;
                    string pkg = outer != null && outer.Index < 0 ? asset.Imports[-outer.Index - 1].ObjectName.Value.Value : "?";
                    if (pkg.StartsWith("/Game/Mods/C1/")) ours++; else other++;
                }
            }
            Console.WriteLine($"geometry: components={comps.Count} ours={ours} nulled={nulled} other={other} visible={visible}");
            foreach (var c in comps.Where(x => Prop(x, "bVisible") is BoolPropertyData b && b.Value).Take(3))
            {
                var sm = Prop(c, "StaticMesh") as ObjectPropertyData;
                if (sm?.Value != null && sm.Value.Index < 0)
                {
                    var imp = asset.Imports[-sm.Value.Index - 1];
                    var outer = imp.OuterIndex;
                    string pkg = outer != null && outer.Index < 0 ? asset.Imports[-outer.Index - 1].ObjectName.Value.Value : "?";
                    Console.WriteLine($"  sample {pkg} :: {imp.ObjectName.Value.Value}");
                }
            }
        }

        static void InspectAll(UAsset asset, List<NormalExport> roads, List<NormalExport> gates, List<NormalExport> areas)
        {
            foreach (var r in roads) Console.WriteLine($"road {Name(asset, r)} splinePoints={GetSplinePointStructs(asset, r)?.Count ?? -1}");
            var comps = ExportsOfClass(asset, "StaticMeshComponent").ToList();
            Console.WriteLine($"meshComponents={comps.Count}");
            if (comps.Count > 0)
                foreach (var p in comps[0].Data)
                {
                    string pn = null; try { pn = p.Name.Value.Value; } catch { }
                    Console.WriteLine($"  comp.{pn} : {p.GetType().Name}");
                }
            if (gates.Count > 0) Inspect(asset, gates[0], "gate");
            if (areas.Count > 0) Inspect(asset, areas[0], "area");
        }

        static void DumpProp(PropertyData p, int depth, int max)
        {
            if (p == null || depth > max) return;
            string pn = null; try { pn = p.Name.Value.Value; } catch { }
            string extra = "";
            if (p is FloatPropertyData fp) extra = " = " + fp.Value;
            Console.WriteLine(new string(' ', depth * 2) + $"{pn} [{p.GetType().Name}]{extra}");
            if (p is StructPropertyData sp && sp.Value != null)
                foreach (var c in sp.Value) DumpProp(c, depth + 1, max);
            if (p is ArrayPropertyData ap && ap.Value != null)
                foreach (var c in ap.Value.Take(2)) DumpProp(c, depth + 1, max);
        }

        static void Inspect(UAsset a, NormalExport e, string label)
        {
            Console.WriteLine($"--- {label} {Name(a, e)}");
            if (e.Data == null) return;
            foreach (var p in e.Data)
            {
                string pn = null; try { pn = p.Name.Value.Value; } catch { }
                Console.WriteLine($"    {pn} : {p.GetType().Name}");
            }
        }
    }
}
