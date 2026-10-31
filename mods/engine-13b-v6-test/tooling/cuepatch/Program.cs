using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UAssetAPI;
using UAssetAPI.ExportTypes;
using UAssetAPI.Unversioned;
using UAssetAPI.PropertyTypes.Objects;
using UAssetAPI.UnrealTypes;
using UAssetAPI.PropertyTypes.Structs;

class Program
{
    static Usmap mappings;
    static UAsset asset;

    static NormalExport Export(int idx)
    {
        return (NormalExport)asset.Exports[idx];
    }

    static PropertyData Find(IList<PropertyData> props, string name)
    {
        foreach (var p in props)
            if (p.Name != null && p.Name.Value != null && p.Name.Value.Value == name) return p;
        return null;
    }

    static StructPropertyData Struct(IList<PropertyData> props, string name)
    {
        var p = Find(props, name);
        if (p == null) throw new Exception($"missing struct '{name}'");
        return (StructPropertyData)p;
    }

    static void SetFloat(IList<PropertyData> props, string name, float value, string where)
    {
        var p = Find(props, name);
        if (p == null) throw new Exception($"{where}: missing float '{name}'");
        if (!(p is FloatPropertyData f)) throw new Exception($"{where}: '{name}' is {p.GetType().Name}, not Float");
        Console.WriteLine($"  {where}.{name}: {f.Value} -> {value}");
        f.Value = value;
    }

    static void AddFloat(IList<PropertyData> props, string name, float value, string where)
    {
        var p = Find(props, name);
        if (p is FloatPropertyData existing) { Console.WriteLine($"  {where}.{name}: {existing.Value} -> {value}"); existing.Value = value; return; }
        props.Add(new FloatPropertyData(FName.FromString(asset, name)) { Value = value });
        Console.WriteLine($"  {where}.{name}: <absent> -> {value} (added)");
    }

    static void SetSoft(int exportIdx, string propName, string packagePath, string assetName)
    {
        var exp = Export(exportIdx);
        var prop = Find(exp.Data, propName);
        if (prop == null) throw new Exception($"export {exportIdx}: missing '{propName}'");
        if (!(prop is SoftObjectPropertyData soft)) throw new Exception($"export {exportIdx}: '{propName}' is {prop.GetType().Name}");
        string old = soft.Value.AssetPath.ToString();
        soft.Value = new FSoftObjectPath(
            FName.FromString(asset, packagePath),
            FName.FromString(asset, assetName),
            new FString(""));
        Console.WriteLine($"  Export[{exportIdx}].{propName}: {old} -> {packagePath}");
    }

    static void Main(string[] args)
    {
        string profile = args[0], input = args[1], outDir = args[2], mapPath = args[3];
        mappings = new Usmap(mapPath);
        asset = new UAsset(input, EngineVersion.VER_UE5_5, mappings);

        switch (profile)
        {
            case "idlebed":
                // idle crossfade (Export 10): keep the rotary bed alive through the rev range
                var fadeArr = (ArrayPropertyData)Find(Export(10).Data, "CrossFadeInput");
                var elem = (StructPropertyData)fadeArr.Value[0];
                SetFloat(elem.Value, "FadeOutDistanceStart", 6000f, "CF_idle");
                SetFloat(elem.Value, "FadeOutDistanceEnd", 9500f, "CF_idle");
                // idle modulator (Export 6): pitch tracks RPM, volume eases off with throttle
                var pitch = Struct(Export(6).Data, "PitchModulationParams");
                SetFloat(pitch.Value, "MinInput", 900f, "pitch");
                SetFloat(pitch.Value, "MaxInput", 6500f, "pitch");
                SetFloat(pitch.Value, "MinOutput", 0.55f, "pitch");
                SetFloat(pitch.Value, "MaxOutput", 2.2f, "pitch");
                var vol = Struct(Export(6).Data, "VolumeModulationParams");
                SetFloat(vol.Value, "MinOutput", 1.0f, "volume");
                SetFloat(vol.Value, "MaxOutput", 0.35f, "volume");
                break;

            case "v6":
                // low/high layers -> V6Sport sample set. Base rates match this cue's curves
                // (low curve ~= rpm/3000, high curve ~= rpm/5000), so 3000 + 5320 rpm samples
                // play at roughly correct speed without retuning pitch.
                SetSoft(15, "SoundWaveAssetPtr",
                    "/Game/Cars/Parts/Engine/Sound/V6Sport/V6Sport_02/3000rpm_Engine", "3000rpm_Engine");
                SetSoft(14, "SoundWaveAssetPtr",
                    "/Game/Cars/Parts/Engine/Sound/V6Sport/V6Sport_02/5320rpm_Engine", "5320rpm_Engine");
                // quieter V6 layers
                var hiVol = Struct(Export(7).Data, "VolumeModulationParams");
                SetFloat(hiVol.Value, "MinOutput", 0.15f, "high_vol");
                SetFloat(hiVol.Value, "MaxOutput", 2.0f, "high_vol");
                SetFloat(Struct(Export(8).Data, "VolumeModulationParams").Value, "MinOutput", 0.2f, "high_thr");
                SetFloat(Struct(Export(4).Data, "VolumeModulationParams").Value, "MinOutput", 0.15f, "low_vol");
                SetFloat(Struct(Export(5).Data, "VolumeModulationParams").Value, "MinOutput", 0.35f, "low_thr");
                // rotary bed louder at high revs (throttle-open end of its curve)
                SetFloat(Struct(Export(6).Data, "VolumeModulationParams").Value, "MaxOutput", 0.6f, "bed");
                break;

            case "v6b":
                // carry v0.1.2 forward, then: V6 a bit louder, rotary bed quieter off throttle
                SetSoft(15, "SoundWaveAssetPtr",
                    "/Game/Cars/Parts/Engine/Sound/V6Sport/V6Sport_02/3000rpm_Engine", "3000rpm_Engine");
                SetSoft(14, "SoundWaveAssetPtr",
                    "/Game/Cars/Parts/Engine/Sound/V6Sport/V6Sport_02/5320rpm_Engine", "5320rpm_Engine");
                var hv = Struct(Export(7).Data, "VolumeModulationParams");
                SetFloat(hv.Value, "MinOutput", 0.2f, "high_vol");
                SetFloat(hv.Value, "MaxOutput", 3.2f, "high_vol");
                SetFloat(Struct(Export(8).Data, "VolumeModulationParams").Value, "MinOutput", 0.28f, "high_thr");
                SetFloat(Struct(Export(4).Data, "VolumeModulationParams").Value, "MinOutput", 0.2f, "low_vol");
                SetFloat(Struct(Export(5).Data, "VolumeModulationParams").Value, "MinOutput", 0.45f, "low_thr");
                // rotary bed: closed throttle quiet, open throttle present
                var bedVol = Struct(Export(6).Data, "VolumeModulationParams");
                SetFloat(bedVol.Value, "MinOutput", 0.4f, "bed");
                SetFloat(bedVol.Value, "MaxOutput", 0.9f, "bed");
                // scale the whole idle chain so idle itself stays loud
                var cfArr = (ArrayPropertyData)Find(Export(10).Data, "CrossFadeInput");
                SetFloat(((StructPropertyData)cfArr.Value[0]).Value, "Volume", 1.5f, "CF_idle");
                break;

            case "dumptext":
            {
                var dt = (DataTableExport)asset.Exports[0];
                Console.WriteLine($"rows: {dt.Table.Data.Count}");
                foreach (var rowName in new[] { args.Length > 4 ? args[4] : "KartEngine_10HP" })
                {
                    var row = dt.Table.Data.FirstOrDefault(r => r.Name.Value.Value == rowName);
                    if (row == null) { Console.WriteLine("no row " + rowName); continue; }
                    foreach (var p in row.Value)
                    {
                        if (p is TextPropertyData t)
                        {
                            Console.WriteLine($"  {p.Name.Value.Value}: valueClass={t.Value?.GetType().FullName}");
                            Console.WriteLine($"    str={t.Value?.Value}");
                        }
                    }
                }
                return;
            }

            case "v6swap":
            {
                // the V6 chain: two V6Sport rpm samples replace the V8 high/low loops,
                // and the idle crossfade runs hot (1.5) so the rotary bed sits on top.
                SetSoft(14, "SoundWaveAssetPtr",
                    "/Game/Cars/Parts/Engine/Sound/V6Sport/V6Sport_02/5320rpm_Engine", "5320rpm_Engine");
                SetSoft(15, "SoundWaveAssetPtr",
                    "/Game/Cars/Parts/Engine/Sound/V6Sport/V6Sport_02/3000rpm_Engine", "3000rpm_Engine");
                var cf = (ArrayPropertyData)Find(Export(10).Data, "CrossFadeInput");
                var el = (StructPropertyData)cf.Value[0];
                ((FloatPropertyData)Find(el.Value, "Volume")).Value = 1.5f;
                break;
            }

            case "layer26b":
            {
                // Adds a 4th mixer input: the 26B idle loop, gated by an RPM crossfade that is
                // only open below ~1100 rpm. The 13b idle stays as the base idle layer.
                int wpIdx = asset.Exports.Count;
                var wp = (NormalExport)Export(13).Clone();
                wp.Data = Export(13).Data.Select(p => (PropertyData)p.Clone()).ToList();
                wp.ObjectName = FName.FromString(asset, "SoundNodeWavePlayer_5");
                wp.OuterIndex = new FPackageIndex(1);
                var soft = (SoftObjectPropertyData)Find(wp.Data, "SoundWaveAssetPtr");
                soft.Value = new FSoftObjectPath(
                    FName.FromString(asset, "/Game/Cars/Parts/Engine/Sound/26b/idle"),
                    FName.FromString(asset, "idle"), new FString(""));
                asset.Exports.Add(wp);

                int xfIdx = asset.Exports.Count;
                var xf = (NormalExport)Export(10).Clone();
                xf.Data = Export(10).Data.Select(p => (PropertyData)p.Clone()).ToList();
                xf.ObjectName = FName.FromString(asset, "SoundNodeParamCrossFade_5");
                xf.OuterIndex = new FPackageIndex(1);
                var xfArr = (ArrayPropertyData)Find(xf.Data, "CrossFadeInput");
                var xfElem = (StructPropertyData)xfArr.Value[0];
                ((FloatPropertyData)Find(xfElem.Value, "FadeInDistanceStart")).Value = 10f;
                ((FloatPropertyData)Find(xfElem.Value, "FadeInDistanceEnd")).Value = 10f;
                ((FloatPropertyData)Find(xfElem.Value, "FadeOutDistanceStart")).Value = 500f;
                ((FloatPropertyData)Find(xfElem.Value, "FadeOutDistanceEnd")).Value = 1100f;
                ((FloatPropertyData)Find(xfElem.Value, "Volume")).Value = 1.0f;
                var kids = (ArrayPropertyData)Find(xf.Data, "ChildNodes");
                kids.Value[0] = new ObjectPropertyData(FName.FromString(asset, "0")) { Value = new FPackageIndex(wpIdx + 1) };
                asset.Exports.Add(xf);

                var mixer = (ArrayPropertyData)Find(Export(3).Data, "ChildNodes");
                var vols = (ArrayPropertyData)Find(Export(3).Data, "InputVolume");
                var newKids = mixer.Value.ToList();
                newKids.Add(new ObjectPropertyData(FName.FromString(asset, "3")) { Value = new FPackageIndex(xfIdx + 1) });
                mixer.Value = newKids.ToArray();
                var newVols = vols.Value.ToList();
                newVols.Add(new FloatPropertyData(FName.FromString(asset, "3")) { Value = 0.9f });
                vols.Value = newVols.ToArray();
                Console.WriteLine($"  added waveplayer #{wpIdx} and crossfade #{xfIdx}; mixer inputs now {mixer.Value.Length}");
                break;
            }

            case "layer26b2":
            {
                // Adds a 4th mixer input: the 26B idle loop, gated by an RPM crossfade that is
                // only open below ~1100 rpm. The 13b idle stays as the base idle layer.
                int wpIdx = asset.Exports.Count;
                var wp = (NormalExport)Export(13).Clone();
                wp.Data = Export(13).Data.Select(p => (PropertyData)p.Clone()).ToList();
                wp.ObjectName = FName.FromString(asset, "SoundNodeWavePlayer_5");
                wp.OuterIndex = new FPackageIndex(1);
                var soft = (SoftObjectPropertyData)Find(wp.Data, "SoundWaveAssetPtr");
                soft.Value = new FSoftObjectPath(
                    FName.FromString(asset, "/Game/Cars/Parts/Engine/Sound/26b/idle"),
                    FName.FromString(asset, "idle"), new FString(""));
                asset.Exports.Add(wp);

                int xfIdx = asset.Exports.Count;
                var xf = (NormalExport)Export(10).Clone();
                xf.Data = Export(10).Data.Select(p => (PropertyData)p.Clone()).ToList();
                xf.ObjectName = FName.FromString(asset, "SoundNodeParamCrossFade_5");
                xf.OuterIndex = new FPackageIndex(1);
                var xfArr = (ArrayPropertyData)Find(xf.Data, "CrossFadeInput");
                var xfElem = (StructPropertyData)xfArr.Value[0];
                ((FloatPropertyData)Find(xfElem.Value, "FadeInDistanceStart")).Value = 10f;
                ((FloatPropertyData)Find(xfElem.Value, "FadeInDistanceEnd")).Value = 10f;
                ((FloatPropertyData)Find(xfElem.Value, "FadeOutDistanceStart")).Value = 1600f;
                ((FloatPropertyData)Find(xfElem.Value, "FadeOutDistanceEnd")).Value = 2200f;
                ((FloatPropertyData)Find(xfElem.Value, "Volume")).Value = 1.0f;
                var kids = (ArrayPropertyData)Find(xf.Data, "ChildNodes");
                kids.Value[0] = new ObjectPropertyData(FName.FromString(asset, "0")) { Value = new FPackageIndex(wpIdx + 1) };
                asset.Exports.Add(xf);

                var mixer = (ArrayPropertyData)Find(Export(3).Data, "ChildNodes");
                var vols = (ArrayPropertyData)Find(Export(3).Data, "InputVolume");
                var newKids = mixer.Value.ToList();
                newKids.Add(new ObjectPropertyData(FName.FromString(asset, "3")) { Value = new FPackageIndex(xfIdx + 1) });
                mixer.Value = newKids.ToArray();
                var newVols = vols.Value.ToList();
                newVols.Add(new FloatPropertyData(FName.FromString(asset, "3")) { Value = 0.9f });
                vols.Value = newVols.ToArray();
                Console.WriteLine($"  added waveplayer #{wpIdx} and crossfade #{xfIdx}; mixer inputs now {mixer.Value.Length}");
                break;
            }

            case "idle26b":
            {
                // swap only the idle layer to the 26B rotary's idle loop (the brap source).
                SetSoft(13, "SoundWaveAssetPtr",
                    "/Game/Cars/Parts/Engine/Sound/26b/idle", "idle");
                break;
            }

            case "engsounddata":
            {
                // The 13b asset has NO BackfireSound - it carries EngineSoundData at the same
                // import slot instead. Mirror that exactly, keeping our cue on EnginesSound.
                var props = Export(0).Data;
                var bf = props.FirstOrDefault(x => x.Name?.Value?.Value == "BackfireSound");
                if (bf == null) { Console.WriteLine("  no BackfireSound property"); break; }
                bf.Name = FName.FromString(asset, "EngineSoundData");
                Console.WriteLine($"  BackfireSound -> EngineSoundData (index {(bf is ObjectPropertyData o ? o.Value.Index.ToString() : "?")})");
                break;
            }

            case "soundonly":
            {
                // only the engine values that can change what you hear:
                // MaxRPM re-scales every RPM-driven crossfade/pitch node,
                // IdleThrottle sets the idle speed, the blip pair drives the idle catch,
                // AfterFire drives the pops. Inertia/friction/torque curve/row cost+mass untouched.
                var ep = Struct(Export(0).Data, "EngineProperty");
                AddFloat(ep.Value, "MaxRPM", 9000f, "engine");
                AddFloat(ep.Value, "IdleThrottle", 0.0017f, "engine");
                AddFloat(ep.Value, "BlipThrottle", 10f, "engine");
                AddFloat(ep.Value, "BlipDurationSeconds", 1f, "engine");
                AddFloat(ep.Value, "AfterFireProbability", 1f, "engine");
                break;
            }

            case "match13b":
            {
                var ep = Struct(Export(0).Data, "EngineProperty");
                AddFloat(ep.Value, "Inertia", 3000f, "engine");
                AddFloat(ep.Value, "StarterTorque", 200000f, "engine");
                AddFloat(ep.Value, "MaxTorque", 2833914f, "engine");
                AddFloat(ep.Value, "MaxRPM", 9000f, "engine");
                AddFloat(ep.Value, "FrictionCoulombCoeff", 283391f, "engine");
                AddFloat(ep.Value, "FrictionViscosityCoeff", 1200f, "engine");
                AddFloat(ep.Value, "IdleThrottle", 0.0017f, "engine");
                AddFloat(ep.Value, "FuelConsumption", 69.2f, "engine");
                AddFloat(ep.Value, "HeatingPower", 1.05f, "engine");
                AddFloat(ep.Value, "BlipThrottle", 10f, "engine");
                AddFloat(ep.Value, "BlipDurationSeconds", 1f, "engine");
                AddFloat(ep.Value, "AfterFireProbability", 1f, "engine");
                // torque curve -> the one the 13b uses
                asset.Imports[1].ObjectName = FName.FromString(asset, "TorqueCurve_V12");
                asset.Imports[5].ObjectName = FName.FromString(asset, "/Game/Cars/Parts/Engine/TorqueCurve/TorqueCurve_V12");
                Console.WriteLine($"  curve import1 -> {asset.Imports[1].ObjectName.Value.Value}");
                Console.WriteLine($"  curve pkg import5 -> {asset.Imports[5].ObjectName.Value.Value}");
                break;
            }

            case "full13b":
            {
                // the donor serialises these; the V8 donor does not, so they default to 0.
                // BlipDurationSeconds = 0 means BlipThrottle never fires -> no idle blip at all.
                var ep = Struct(Export(0).Data, "EngineProperty");
                AddFloat(ep.Value, "BlipDurationSeconds", 1f, "engine");
                AddFloat(ep.Value, "HeatingPower", 1.05f, "engine");
                AddFloat(ep.Value, "FuelConsumption", 69.2f, "engine");
                break;
            }

            case "refcue":
            {
                // diagnostic: point this engine at MoreTuning's own 13b cue, unchanged.
                // Reuses the existing import slots (pkg import 4, object import 9) by rename,
                // so no import-table surgery is needed.
                asset.Imports[4].ObjectName = FName.FromString(asset, "/Game/Cars/Parts/Engine/Sound/13b/SC_V12Engine");
                asset.Imports[9].ObjectName = FName.FromString(asset, "SC_V12Engine");
                Console.WriteLine($"  pkg import4 -> {asset.Imports[4].ObjectName.Value.Value}");
                Console.WriteLine($"  obj import9 -> {asset.Imports[9].ObjectName.Value.Value}");
                break;
            }

            case "engine13b":
            {
                var ep = Struct(Export(0).Data, "EngineProperty");
                SetFloat(ep.Value, "Inertia", 3000f, "engine");
                SetFloat(ep.Value, "MaxTorque", 2833914f, "engine");
                SetFloat(ep.Value, "MaxRPM", 9000f, "engine");
                SetFloat(ep.Value, "FrictionCoulombCoeff", 283391f, "engine");
                SetFloat(ep.Value, "FrictionViscosityCoeff", 1200f, "engine");
                SetFloat(ep.Value, "IdleThrottle", 0.0017f, "engine");
                SetFloat(ep.Value, "BlipThrottle", 10f, "engine");
                if (Find(ep.Value, "BlipDurationSeconds") != null) SetFloat(ep.Value, "BlipDurationSeconds", 1f, "engine");
                SetFloat(ep.Value, "AfterFireProbability", 1f, "engine");
                break;
            }

            case "wide9000":
            {
                var p9000 = Struct(Export(6).Data, "PitchModulationParams");
                SetFloat(p9000.Value, "MaxInput", 9000f, "pitch");
                SetFloat(p9000.Value, "MaxOutput", 2.6f, "pitch");
                var cf9000 = (ArrayPropertyData)Find(Export(10).Data, "CrossFadeInput");
                var e9000 = (StructPropertyData)cf9000.Value[0];
                SetFloat(e9000.Value, "FadeOutDistanceStart", 8000f, "CF_idle");
                SetFloat(e9000.Value, "FadeOutDistanceEnd", 11000f, "CF_idle");
                var hi = Struct(Export(7).Data, "PitchModulationParams");
                SetFloat(hi.Value, "MaxInput", 9000f, "high_pitch");
                break;
            }

            case "enginebrap":
            {
                var ep = Struct(Export(0).Data, "EngineProperty");
                SetFloat(ep.Value, "BlipThrottle", 10f, "engine");
                SetFloat(ep.Value, "AfterFireProbability", 1f, "engine");
                break;
            }

            default:
                throw new Exception($"unknown profile '{profile}'");
        }

        asset.ResolveAncestries();
        Directory.CreateDirectory(outDir);
        string dest = Path.Combine(outDir, Path.GetFileName(input));
        asset.Write(dest);
        Console.WriteLine($"written {dest}");
    }
}
