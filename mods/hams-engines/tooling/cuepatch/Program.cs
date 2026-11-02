using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UAssetAPI;
using UAssetAPI.ExportTypes;
using UAssetAPI.Unversioned;
using UAssetAPI.PropertyTypes.Objects;
using UAssetAPI.UnrealTypes;
using UAssetAPI.UnrealTypes.EngineEnums;
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

    static RichCurveKeyPropertyData RichKey(PropertyData p)
    {
        if (p is RichCurveKeyPropertyData rk) return rk;
        if (p is StructPropertyData sp)
        {
            foreach (var child in sp.Value)
            {
                var found = RichKey(child);
                if (found != null) return found;
            }
        }
        return null;
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

            case "kd330cue":
            {
                // MediumDuty_330HP x KartEngine_10HP, blend-the-whole-way:
                //   diesel base  = the 330's own MidDuty_02 sample set (560 idle + 2000 mid engine/exhaust)
                //   2-stroke saw = the kart's chainsaw idle loop layered over it at ~45% level,
                //                  pitch-tracked across the diesel's 560..2900 rpm band.
                // Host is a clone of SC_Truck_02 (same 3-layer diesel scaffolding + Starter),
                // because MediumDuty_330HP itself has no SoundCue at all - it drives EngineSoundData.
                SetSoft(14, "SoundWaveAssetPtr",
                    "/Game/Cars/Parts/Engine/Sound/Truck/MidDuty_02/560rpm_Engine", "560rpm_Engine");
                SetSoft(15, "SoundWaveAssetPtr",
                    "/Game/Cars/Parts/Engine/Sound/Truck/MidDuty_02/2000rpm_Engine", "2000rpm_Engine");
                SetSoft(13, "SoundWaveAssetPtr",
                    "/Game/Cars/Parts/Engine/Sound/Truck/MidDuty_02/2000rpm_Exhaust", "2000rpm_Exhaust");

                // pitch curves retuned to those sample base rates, redline 3500
                var idlePitch = Struct(Export(8).Data, "PitchModulationParams");
                AddFloat(idlePitch.Value, "MinInput", 500f, "idle_pitch");
                AddFloat(idlePitch.Value, "MaxInput", 1500f, "idle_pitch");
                AddFloat(idlePitch.Value, "MinOutput", 1.0f, "idle_pitch");
                AddFloat(idlePitch.Value, "MaxOutput", 2.7f, "idle_pitch");
                foreach (int chain in new[] { 4, 5 })
                {
                    var p = Struct(Export(chain).Data, "PitchModulationParams");
                    AddFloat(p.Value, "MinInput", 560f, $"chain{chain}_pitch");
                    AddFloat(p.Value, "MaxInput", 3200f, $"chain{chain}_pitch");
                    AddFloat(p.Value, "MinOutput", 0.28f, $"chain{chain}_pitch");
                    AddFloat(p.Value, "MaxOutput", 1.6f, $"chain{chain}_pitch");
                }
                // idle layer hands over to the loap band by 1500 rpm
                var idleFade = (ArrayPropertyData)Find(Export(11).Data, "CrossFadeInput");
                var idleEl = (StructPropertyData)idleFade.Value[0];
                SetFloat(idleEl.Value, "FadeOutDistanceStart", 900f, "CF_idle");
                SetFloat(idleEl.Value, "FadeOutDistanceEnd", 1500f, "CF_idle");

                // ---- chainsaw layer: waveplayer -> modulator -> always-on crossfade ----
                int wpIdx = asset.Exports.Count;
                var wp = (NormalExport)Export(14).Clone();
                wp.Data = Export(14).Data.Select(p => (PropertyData)p.Clone()).ToList();
                wp.ObjectName = FName.FromString(asset, "SoundNodeWavePlayer_5");
                wp.OuterIndex = new FPackageIndex(1);
                var soft = (SoftObjectPropertyData)Find(wp.Data, "SoundWaveAssetPtr");
                soft.Value = new FSoftObjectPath(
                    FName.FromString(asset, "/Game/Cars/Parts/Engine/Sound/2Stroke/Chainsaw/538141-Chainsaw-Close-Idling-02-18-LOOP"),
                    FName.FromString(asset, "538141-Chainsaw-Close-Idling-02-18-LOOP"), new FString(""));
                asset.Exports.Add(wp);

                int modIdx = asset.Exports.Count;
                var md = (NormalExport)Export(8).Clone();
                md.Data = Export(8).Data.Select(p => (PropertyData)p.Clone()).ToList();
                md.ObjectName = FName.FromString(asset, "SoundNodeModulatorContinuous_9");
                md.OuterIndex = new FPackageIndex(1);
                var mdPitch = Struct(md.Data, "PitchModulationParams");
                AddFloat(mdPitch.Value, "Default", 560f, "saw_pitch");
                AddFloat(mdPitch.Value, "MinInput", 550f, "saw_pitch");
                AddFloat(mdPitch.Value, "MaxInput", 3500f, "saw_pitch");
                AddFloat(mdPitch.Value, "MinOutput", 0.9f, "saw_pitch");
                AddFloat(mdPitch.Value, "MaxOutput", 1.9f, "saw_pitch");
                var mdVol = Struct(md.Data, "VolumeModulationParams");
                AddFloat(mdVol.Value, "MinOutput", 1.0f, "saw_vol");
                AddFloat(mdVol.Value, "MaxOutput", 1.0f, "saw_vol");
                var mdKids = (ArrayPropertyData)Find(md.Data, "ChildNodes");
                mdKids.Value[0] = new ObjectPropertyData(FName.FromString(asset, "0")) { Value = new FPackageIndex(wpIdx + 1) };
                asset.Exports.Add(md);

                int xfIdx = asset.Exports.Count;
                var xf = (NormalExport)Export(11).Clone();
                xf.Data = Export(11).Data.Select(p => (PropertyData)p.Clone()).ToList();
                xf.ObjectName = FName.FromString(asset, "SoundNodeParamCrossFade_4");
                xf.OuterIndex = new FPackageIndex(1);
                var xfArr = (ArrayPropertyData)Find(xf.Data, "CrossFadeInput");
                var xfEl = (StructPropertyData)xfArr.Value[0];
                SetFloat(xfEl.Value, "FadeInDistanceStart", 10f, "CF_saw");
                SetFloat(xfEl.Value, "FadeInDistanceEnd", 10f, "CF_saw");
                SetFloat(xfEl.Value, "FadeOutDistanceStart", 1e12f, "CF_saw");
                SetFloat(xfEl.Value, "FadeOutDistanceEnd", 1e12f, "CF_saw");
                SetFloat(xfEl.Value, "Volume", 1.0f, "CF_saw");
                var xfKids = (ArrayPropertyData)Find(xf.Data, "ChildNodes");
                xfKids.Value[0] = new ObjectPropertyData(FName.FromString(asset, "0")) { Value = new FPackageIndex(modIdx + 1) };
                asset.Exports.Add(xf);

                var mixer = (ArrayPropertyData)Find(Export(3).Data, "ChildNodes");
                var vols = (ArrayPropertyData)Find(Export(3).Data, "InputVolume");
                var newKids = mixer.Value.ToList();
                newKids.Add(new ObjectPropertyData(FName.FromString(asset, "3")) { Value = new FPackageIndex(xfIdx + 1) });
                mixer.Value = newKids.ToArray();
                var newVols = vols.Value.ToList();
                newVols.Add(new FloatPropertyData(FName.FromString(asset, "3")) { Value = 0.45f });
                vols.Value = newVols.ToArray();
                Console.WriteLine($"  added saw waveplayer #{wpIdx}, modulator #{modIdx}, crossfade #{xfIdx}; mixer inputs now {mixer.Value.Length}/{vols.Value.Length}");
                break;
            }

            case "kd330engine":
            {
                // The 330's own numbers (donor is MediumDuty_250HP, same field set, so this is a
                // straight value copy - inertia/torque/friction do change here on purpose: the
                // hybrid must still DRIVE like the 330).
                var ep = Struct(Export(0).Data, "EngineProperty");
                AddFloat(ep.Value, "Inertia", 40000f, "engine");
                AddFloat(ep.Value, "StarterTorque", 3000000f, "engine");
                AddFloat(ep.Value, "StarterRPM", 1500f, "engine");
                // 12,526,316 = 14,000,000 * 340/380: the stock 14M read 380 HP once the
                // 3500 rpm ceiling let the curve's overspeed tail into the power peak, so
                // scale torque linearly to land on 340 HP (still under 350).
                AddFloat(ep.Value, "MaxTorque", 12526316f, "engine");

                AddFloat(ep.Value, "MaxRPM", 3500f, "engine");
                AddFloat(ep.Value, "FrictionCoulombCoeff", 2940000f, "engine");
                AddFloat(ep.Value, "FrictionViscosityCoeff", 6000f, "engine");
                AddFloat(ep.Value, "IdleThrottle", 0.017f, "engine");
                AddFloat(ep.Value, "FuelConsumption", 330f, "engine");
                AddFloat(ep.Value, "BlipThrottle", 5f, "engine");
                AddFloat(ep.Value, "IntakeSpeedEfficency", 2f, "engine");
                AddFloat(ep.Value, "BlipDurationSeconds", 0.5f, "engine");
                break;
            }

            case "enginebrap":
            {
                var ep = Struct(Export(0).Data, "EngineProperty");
                SetFloat(ep.Value, "BlipThrottle", 10f, "engine");
                SetFloat(ep.Value, "AfterFireProbability", 1f, "engine");
                break;
            }

            case "rotarycurve":
            {
                // TorqueCurve_Rotary: rewrite the cloned SmallBlock key set into a rotary
                // shape - torque builds to a peak just past half redline, then eases so the
                // POWER curve peaks near 8.5k instead of dying at 8.4k. X = rpm/MaxRPM.
                float[,] pts =
                {
                    {0.00f, 0.620f}, {0.10f, 0.720f}, {0.25f, 0.860f}, {0.40f, 0.950f},
                    {0.58f, 1.000f}, {0.72f, 0.985f}, {0.85f, 0.945f}, {0.94f, 0.900f},
                    {1.00f, 0.830f},
                };
                var fc = Struct(Export(0).Data, "FloatCurve");
                var keysArr = (ArrayPropertyData)Find(fc.Value, "Keys");
                if (keysArr == null) throw new Exception("FloatCurve.Keys not found");
                var proto = keysArr.Value[0];
                Console.WriteLine($"  key prototype: {proto.GetType().Name}");
                var keys = new List<PropertyData>();
                for (int i = 0; i < pts.GetLength(0); i++)
                {
                    var clone = (PropertyData)proto.Clone();
                    clone.Name = FName.FromString(asset, i.ToString());
                    var rk = RichKey(clone);
                    if (rk == null) throw new Exception("RichCurveKey not found inside key struct");
                    rk.Value = new FRichCurveKey(
                        ERichCurveInterpMode.RCIM_Linear,
                        ERichCurveTangentMode.RCTM_Auto,
                        ERichCurveTangentWeightMode.RCTWM_WeightedNone,
                        pts[i, 0], pts[i, 1], 0f, 0f, 0f, 0f);
                    keys.Add(clone);
                }
                keysArr.Value = keys.ToArray();
                Console.WriteLine($"  keys written: {keys.Count}");
                break;
            }

            case "rotaryspec":
            {
                // Point the rotary engine at TorqueCurve_Rotary and rescale MaxTorque so the
                // new shape still lands 250 hp (model-solved: 2,338,101 g*cm).
                var ep = Struct(Export(0).Data, "EngineProperty");
                SetFloat(ep.Value, "MaxTorque", 2338101f, "engine");
                bool obj = false, pkg = false;
                for (int i = 0; i < asset.Imports.Count; i++)
                {
                    var imp = asset.Imports[i];
                    var nm = imp.ObjectName.Value.Value;
                    if (!nm.Contains("TorqueCurve_SmallBlock")) continue;
                    if (nm.Contains("/")) { imp.ObjectName = FName.FromString(asset,
                        "/Game/Cars/Parts/Engine/TorqueCurve/TorqueCurve_Rotary"); pkg = true; }
                    else { imp.ObjectName = FName.FromString(asset, "TorqueCurve_Rotary"); obj = true; }
                    Console.WriteLine($"  curve import[{i}] -> {imp.ObjectName.Value.Value}");
                }
                Console.WriteLine($"  curve import rewrite: object={obj} package={pkg}");
                break;
            }

            case "hybridvtdi":
            {
                // Audi 5.5 TDI (MoreTuning "R10") takes over the MID and HIGH layers only -
                // the Harley V-twin keeps the idle window so the low end lops like the twin,
                // and a 540 heavy-duty diesel bed is mixed in underneath it.
                var swaps = new[] {
                    ("4_1000_Mid",   "/Game/Cars/Parts/Engine/Sound/R10/mid",  "mid"),
                    ("4_1000_High2", "/Game/Cars/Parts/Engine/Sound/R10/high", "high"),
                };
                // 5th CLI arg = redline this cue is being built for, so the same profile can
                // serve the 2,900 rpm heavy duty and the 1,800 rpm Thumper.
                int redline = 2900;
                if (args.Length > 4 && int.TryParse(args[4], out var rr) && rr > 0) redline = rr;
                Console.WriteLine($"  target redline: {redline} rpm");
                int hits = 0;
                for (int i = 0; i < asset.Exports.Count; i++)
                {
                    if (asset.Exports[i] is not NormalExport ne || ne.Data == null) continue;
                    var prop = Find(ne.Data, "SoundWaveAssetPtr") as SoftObjectPropertyData;
                    if (prop == null) continue;
                    var pkg = prop.Value.AssetPath.PackageName?.Value?.Value ?? "";
                    foreach (var (suffix, newPkg, newName) in swaps)
                    {
                        if (!pkg.EndsWith(suffix)) continue;
                        SetSoft(i, "SoundWaveAssetPtr", newPkg, newName);
                        hits++;
                    }
                }
                Console.WriteLine($"  wave layers repointed to the TDI set: {hits}");

                // the clone tool rewrites "harley" inside import package paths, which strands
                // the two exhaust layers at a non-existent Bike/SC_HybridTDIVTwin/ folder.
                for (int i = 0; i < asset.Exports.Count; i++)
                {
                    if (asset.Exports[i] is not NormalExport ne || ne.Data == null) continue;
                    var prop = Find(ne.Data, "SoundWaveAssetPtr") as SoftObjectPropertyData;
                    if (prop == null) continue;
                    var pkg = prop.Value.AssetPath.PackageName?.Value?.Value ?? "";
                    if (!pkg.Contains("/Bike/SC_HybridTDIVTwin/")) continue;
                    var fixedPkg = pkg.Replace("/Bike/SC_HybridTDIVTwin/", "/Bike/harley/");
                    var assetName = prop.Value.AssetPath.AssetName?.Value?.Value ?? "";
                    SetSoft(i, "SoundWaveAssetPtr", fixedPkg, assetName);
                }

                // pitch/volume curves were written for a 10k-rpm bike; re-scale them to
                // this engine's redline so the samples play near natural rate.
                // keep the hybrid's original 0.45x -> 1.35x spread: flattening it stripped the
                // low end out of the idle sample and is what made the short-band cue sound tinny
                float pitchLo = 0.45f;
                float pitchHi = 1.35f;
                foreach (var exp in asset.Exports)
                {
                    if (exp is not NormalExport ne || ne.Data == null) continue;
                    foreach (var name in new[] { "PitchModulationParams", "VolumeModulationParams" })
                    {
                        var ps = Find(ne.Data, name) as StructPropertyData;
                        if (ps == null) continue;
                        var param = Find(ps.Value, "ParameterName") as NamePropertyData;
                        if (param?.Value?.Value?.Value != "RPM") continue;
                        if (name == "PitchModulationParams")
                        {
                            if (Find(ps.Value, "MinInput") != null) SetFloat(ps.Value, "MinInput", redline * 0.14f, "pitch");
                            if (Find(ps.Value, "MaxInput") != null) SetFloat(ps.Value, "MaxInput", redline, "pitch");
                            if (Find(ps.Value, "MinOutput") != null) SetFloat(ps.Value, "MinOutput", pitchLo, "pitch");
                            if (Find(ps.Value, "MaxOutput") != null) SetFloat(ps.Value, "MaxOutput", pitchHi, "pitch");
                        }
                        else if (Find(ps.Value, "MaxInput") != null)
                        {
                            SetFloat(ps.Value, "MaxInput", redline, "volume");
                        }
                    }
                }
                // ---- 540 heavy-duty diesel bed: waveplayer -> modulator -> always-on crossfade,
                // rolled in behind the V-twin at low volume so the twin stays the voice.
                int wpIdx = asset.Exports.Count;
                var bedWp = (NormalExport)Export(20).Clone();
                bedWp.Data = Export(20).Data.Select(p => (PropertyData)p.Clone()).ToList();
                bedWp.ObjectName = FName.FromString(asset, "SoundNodeWavePlayer_7");
                bedWp.OuterIndex = new FPackageIndex(1);
                var bedSoft = (SoftObjectPropertyData)Find(bedWp.Data, "SoundWaveAssetPtr");
                bedSoft.Value = new FSoftObjectPath(
                    FName.FromString(asset, "/Game/Cars/Parts/Engine/Sound/Truck/Truck_05_Idle"),
                    FName.FromString(asset, "Truck_05_Idle"), new FString(""));
                asset.Exports.Add(bedWp);

                int bedModIdx = asset.Exports.Count;
                var bedMod = (NormalExport)Export(8).Clone();
                bedMod.Data = Export(8).Data.Select(p => (PropertyData)p.Clone()).ToList();
                bedMod.ObjectName = FName.FromString(asset, "SoundNodeModulatorContinuous_12");
                bedMod.OuterIndex = new FPackageIndex(1);
                var bedPitch = Struct(bedMod.Data, "PitchModulationParams");
                // scale to this engine's redline - hardcoding 2,900 left the bed at a fixed
                // pitch on the 1,800 rpm Thumper, because the rescale pass runs before this
                AddFloat(bedPitch.Value, "MinInput", redline * 0.17f, "bed_pitch");
                AddFloat(bedPitch.Value, "MaxInput", redline, "bed_pitch");
                AddFloat(bedPitch.Value, "MinOutput", 0.85f, "bed_pitch");
                AddFloat(bedPitch.Value, "MaxOutput", 1.15f, "bed_pitch");
                var bedVolP = Struct(bedMod.Data, "VolumeModulationParams");
                AddFloat(bedVolP.Value, "MinOutput", 1.0f, "bed_vol");
                AddFloat(bedVolP.Value, "MaxOutput", 1.0f, "bed_vol");
                var bedKids = (ArrayPropertyData)Find(bedMod.Data, "ChildNodes");
                bedKids.Value[0] = new ObjectPropertyData(FName.FromString(asset, "0")) { Value = new FPackageIndex(wpIdx + 1) };
                asset.Exports.Add(bedMod);

                int bedXfIdx = asset.Exports.Count;
                var bedXf = (NormalExport)Export(13).Clone();
                bedXf.Data = Export(13).Data.Select(p => (PropertyData)p.Clone()).ToList();
                bedXf.ObjectName = FName.FromString(asset, "SoundNodeParamCrossFade_7");
                bedXf.OuterIndex = new FPackageIndex(1);
                var bedXfKids = (ArrayPropertyData)Find(bedXf.Data, "ChildNodes");
                bedXfKids.Value[0] = new ObjectPropertyData(FName.FromString(asset, "0")) { Value = new FPackageIndex(bedModIdx + 1) };
                asset.Exports.Add(bedXf);

                var mixKids = (ArrayPropertyData)Find(Export(3).Data, "ChildNodes");
                var mixVols = (ArrayPropertyData)Find(Export(3).Data, "InputVolume");
                var kidList = mixKids.Value.ToList();
                kidList.Add(new ObjectPropertyData(FName.FromString(asset, "5")) { Value = new FPackageIndex(bedXfIdx + 1) });
                mixKids.Value = kidList.ToArray();
                var volList = mixVols.Value.ToList();
                volList.Add(new FloatPropertyData(FName.FromString(asset, "5")) { Value = 0.30f });
                // input 0 is the V-twin idle window - push it up so it leads down low
                ((FloatPropertyData)volList[0]).Value = 0.85f;
                if (redline <= 2000)
                {
                    // On the short band the two TDI (diesel) layers sat under the twin and never
                    // read as diesel. Lift both, and lift the bed which is the only low-end body
                    // once the twin idle fades.
                    ((FloatPropertyData)volList[1]).Value = 0.75f;   // TDI mid
                    ((FloatPropertyData)volList[3]).Value = 0.75f;   // TDI high
                    ((FloatPropertyData)volList[5]).Value = 0.40f;   // 540 bed
                }
                mixVols.Value = volList.ToArray();
                Console.WriteLine($"  added 540 diesel bed #{wpIdx}/{bedModIdx}/{bedXfIdx}; mixer inputs {mixKids.Value.Length}, idle vol 0.85, bed vol 0.30");

                // Short rev band: the crossfade windows were cut for a 2,900+ rpm engine, so at
                // 1,800 the high layer would never fade in and the mid barely engage. Redraw them.
                if (redline <= 2000)
                {
                    int cfSeen = 0;
                    void Win(int ordinal, float inA, float inB, float outA, float outB)
                    {
                        int idx = -1; int seen = 0;
                        for (int i = 0; i < asset.Exports.Count; i++)
                        {
                            var nm = asset.Exports[i].ObjectName?.Value?.Value ?? "";
                            if (!nm.Contains("ParamCrossFade")) continue;
                            seen++;
                            if (seen == ordinal) { idx = i; break; }
                        }
                        if (idx < 0) { Console.WriteLine($"  ! crossfade #{ordinal} not found"); return; }
                        var arr = (ArrayPropertyData)Find(Export(idx).Data, "CrossFadeInput");
                        var el = (StructPropertyData)arr.Value[0];
                        Console.WriteLine($"  window #{ordinal} ({asset.Exports[idx].ObjectName.Value.Value}): {inA}-{inB} in, {outA} out");
                        SetFloat(el.Value, "FadeInDistanceStart", inA, $"cf{ordinal}");
                        SetFloat(el.Value, "FadeInDistanceEnd", inB, $"cf{ordinal}");
                        SetFloat(el.Value, "FadeOutDistanceStart", outA, $"cf{ordinal}");
                        SetFloat(el.Value, "FadeOutDistanceEnd", outB, $"cf{ordinal}");
                    }
                    // Windows fitted to an 1,800 rpm band, but spread the way the 2,900 cue
                    // spreads them (twin leads low, TDI takes the middle, both highs arrive
                    // late) instead of stacking everything in the first 900 rpm.
                    Win(1, 10f, 10f, 1e12f, 1e12f);       // bus, always on
                    Win(2, 10f, 10f, 1500f, 1800f);       // twin idle - holds to redline, it IS the low end
                    Win(3, 500f, 1100f, 1e12f, 1e12f);    // TDI mid
                    Win(4, 1000f, 1600f, 1e12f, 1e12f);   // TDI high
                    Win(5, 1000f, 1600f, 1e12f, 1e12f);   // twin high exhaust
                    Win(6, 500f, 1100f, 1e12f, 1e12f);    // twin mid exhaust
                    Win(7, 10f, 10f, 1e12f, 1e12f);       // diesel bed
                }

                if (Find(Export(0).Data, "VolumeMultiplier") != null)
                    SetFloat(Export(0).Data, "VolumeMultiplier", 0.55f, "cue");
                break;
            }

            case "thumpercurve":
            {
                // TorqueCurve_Thumper: peak torque at half redline (~900 of 1,800) and a hard
                // decay after it, so a 3,000 Nm engine still tops out around 350-390 hp.
                // X = rpm/MaxRPM.
                float[,] pts =
                {
                    {0.00f, 0.800f}, {0.20f, 0.950f}, {0.42f, 1.000f},
                    {0.72f, 0.550f}, {1.00f, 0.330f},
                };
                var fcT = Struct(Export(0).Data, "FloatCurve");
                var keysT = (ArrayPropertyData)Find(fcT.Value, "Keys");
                if (keysT == null) throw new Exception("FloatCurve.Keys not found");
                var protoT = keysT.Value[0];
                var newKeys = new List<PropertyData>();
                for (int i = 0; i < pts.GetLength(0); i++)
                {
                    var clone = (PropertyData)protoT.Clone();
                    clone.Name = FName.FromString(asset, i.ToString());
                    var rk = RichKey(clone);
                    if (rk == null) throw new Exception("RichCurveKey not found inside key struct");
                    rk.Value = new FRichCurveKey(
                        ERichCurveInterpMode.RCIM_Linear,
                        ERichCurveTangentMode.RCTM_Auto,
                        ERichCurveTangentWeightMode.RCTWM_WeightedNone,
                        pts[i, 0], pts[i, 1], 0f, 0f, 0f, 0f);
                    newKeys.Add(clone);
                }
                keysT.Value = newKeys.ToArray();
                Console.WriteLine($"  keys written: {newKeys.Count}");
                break;
            }

            case "thumperengine":
            {
                // Thumper: 1,800 rpm lugger. Model-solved against the curve above:
                // MaxTorque 30,000,000 -> 3,000 Nm @ 756 rpm, 335.8 hp @ 977, 990 Nm at the limiter.
                var ep = Struct(Export(0).Data, "EngineProperty");
                SetFloat(ep.Value, "MaxTorque", 30000000f, "engine");
                SetFloat(ep.Value, "MaxRPM", 1800f, "engine");
                // starter has to crank a heavy flywheel to a much lower limiter
                SetFloat(ep.Value, "StarterRPM", 400f, "engine");
                SetFloat(ep.Value, "StarterTorque", 4500000f, "engine");
                SetFloat(ep.Value, "Inertia", 32000f, "engine");
                // rev blips run out of revs fast on a 1,800 ceiling
                AddFloat(ep.Value, "BlipThrottle", 3f, "engine");
                AddFloat(ep.Value, "BlipDurationSeconds", 0.35f, "engine");
                AddFloat(ep.Value, "FuelConsumption", 300f, "engine");
                break;
            }

            case "amci4loops":
            {
                // point the three I4Sport loop players at our own wave packages so the
                // game streams them from a path it owns, never over a vanilla streamed asset.
                // Vanilla export order is NOT low/mid/high: 13 = the 1.0k idle player,
                // 14 = the 1.6k player (the HIGH layer), 15 = the 1.3k player (the MID layer).
                // Assigning low/mid/high in order silently swaps the top two layers.
                SetSoft(13, "SoundWaveAssetPtr", "/Game/Cars/Parts/Engine/Sound/AMC/amc_i4_low", "amc_i4_low");
                SetSoft(14, "SoundWaveAssetPtr", "/Game/Cars/Parts/Engine/Sound/AMC/amc_i4_high", "amc_i4_high");
                SetSoft(15, "SoundWaveAssetPtr", "/Game/Cars/Parts/Engine/Sound/AMC/amc_i4_mid", "amc_i4_mid");
                // A soft pointer alone leaves the wave packages out of the import table, so the
                // cue only has a lazy path to them. MoreTuning's working cues carry the wave
                // packages as HARD package imports (Import[7..9]). Rename the three existing
                // wave-package imports in place - same count, so no import-table surgery - and
                // the SoundWave object imports (Outer points at them) follow automatically.
                bool renameImports = args.Length > 4 && args[4] == "hardrefs";
                if (renameImports)
                {
                    string[] pkgs = {
                        "/Game/Cars/Parts/Engine/Sound/AMC/amc_i4_low",
                        "/Game/Cars/Parts/Engine/Sound/AMC/amc_i4_high",
                        "/Game/Cars/Parts/Engine/Sound/AMC/amc_i4_mid" };
                    string[] objs = { "amc_i4_low", "amc_i4_high", "amc_i4_mid" };
                    for (int k = 0; k < 3; k++)
                    {
                        asset.Imports[6 + k].ObjectName = FName.FromString(asset, pkgs[k]);
                        asset.Imports[21 + k].ObjectName = FName.FromString(asset, objs[k]);
                        Console.WriteLine($"  Import[{6 + k}] -> {pkgs[k]}");
                        Console.WriteLine($"  Import[{21 + k}] -> {objs[k]}");
                    }
                }
                break;
            }

            case "engcue":
            {
                // point an engine DataAsset at our own cue package (rename, no import growth)
                asset.Imports[4].ObjectName = FName.FromString(asset, "/Game/Cars/Parts/Engine/Sound/AMC/SC_AMC_I4Engine");
                asset.Imports[9].ObjectName = FName.FromString(asset, "SC_AMC_I4Engine");
                Console.WriteLine($"  Import[4] -> {asset.Imports[4].ObjectName.Value.Value}");
                Console.WriteLine($"  Import[9] -> {asset.Imports[9].ObjectName.Value.Value}");
                break;
            }

            case "amci4tune":
            {
                // Our loops are recordings, not samples cut for a fixed rpm, so the vanilla
                // pitch maps (idle 0.5-3.0, mid 0.167-3.33, high 0.1-2.0 over the whole rev
                // range) bend them into something else entirely. Flatten each layer to a
                // narrow band around 1.0 so the recording is audible as itself, and cap the
                // high layer's volume map, which boosted to 5x at the top of the range.
                // All three layers get the SAME pitch law. Vanilla gives each layer its own map
                // because each vanilla sample was recorded at a different rpm, and the maps
                // compensate so the layers still agree on absolute pitch. Ours are three separate
                // recordings, so source-specific compensation is wrong: at 3000 rpm vanilla would
                // play idle at 3.0x, mid at 1.0x and high at 0.42x AT THE SAME TIME. One shared
                // law keeps them in tune with each other while still tracking rpm.
                int[] layerExports = { 6, 4, 7 };   // idle, mid, high
                string[] layerNames = { "idle", "mid", "high" };
                for (int i = 0; i < layerExports.Length; i++)
                {
                    var pp = Struct(Export(layerExports[i]).Data, "PitchModulationParams");
                    SetFloat(pp.Value, "MinInput", 1000f, layerNames[i] + ".pitch");
                    SetFloat(pp.Value, "MaxInput", 9000f, layerNames[i] + ".pitch");
                    SetFloat(pp.Value, "MinOutput", 0.80f, layerNames[i] + ".pitch");
                    SetFloat(pp.Value, "MaxOutput", 1.80f, layerNames[i] + ".pitch");
                }

                var hiVolParams = Struct(Export(7).Data, "VolumeModulationParams");
                SetFloat(hiVolParams.Value, "MinOutput", 0.60f, "high.volume");
                SetFloat(hiVolParams.Value, "MaxOutput", 2.00f, "high.volume");

                // mid layer's own volume map bottomed at 0.2 - unusable under other layers
                var midVolParams = Struct(Export(4).Data, "VolumeModulationParams");
                SetFloat(midVolParams.Value, "MinOutput", 0.45f, "mid.volume");

                // balance pass: mid and the low-as-high layer up, the high-clip bed down a touch
                var mixVols = (ArrayPropertyData)Find(Export(3).Data, "InputVolume");
                ((FloatPropertyData)mixVols.Value[1]).Value = 1.40f;   // mid
                ((FloatPropertyData)mixVols.Value[2]).Value = 0.75f;   // high clip bed ("background")
                Console.WriteLine("  mixer: low 1.00, mid 0.55 (undertone), high 0.70");
                break;
            }

            case "amci4stack":
            {
                // Layering per the user's spec:
                //   idle node      -> low clip, untouched (vanilla 1500-2000 fade out)
                //   mid node       -> mid clip, the 2k-4k section, then decaying as an undertone
                //   high node      -> HIGH clip, unchanged, the bed everywhere above ~5k
                //   NEW 4th input  -> the LOW clip again, rpm-pitched, covering the high section
                // so the top of the range is the low loop pitched up, over the high bed, with mid
                // still underneath it.

                // mid section window: 2,000 -> 4,000, then a long tail as the undertone
                var midCf = (ArrayPropertyData)Find(Export(11).Data, "CrossFadeInput");
                var midEl = (StructPropertyData)midCf.Value[0];
                ((FloatPropertyData)Find(midEl.Value, "FadeInDistanceStart")).Value = 1800f;
                ((FloatPropertyData)Find(midEl.Value, "FadeInDistanceEnd")).Value = 2000f;
                ((FloatPropertyData)Find(midEl.Value, "FadeOutDistanceStart")).Value = 4000f;
                ((FloatPropertyData)Find(midEl.Value, "FadeOutDistanceEnd")).Value = 7000f;
                Console.WriteLine("  mid window: in 1800-2000, out 4000-7000");

                // new wave player on the LOW clip
                int wpIdx = asset.Exports.Count;
                var wp = (NormalExport)Export(15).Clone();
                wp.Data = Export(15).Data.Select(p => (PropertyData)p.Clone()).ToList();
                wp.ObjectName = FName.FromString(asset, "SoundNodeWavePlayer_5");
                wp.OuterIndex = new FPackageIndex(1);
                var soft = (SoftObjectPropertyData)Find(wp.Data, "SoundWaveAssetPtr");
                soft.Value = new FSoftObjectPath(
                    FName.FromString(asset, "/Game/Cars/Parts/Engine/Sound/AMC/amc_i4_low"),
                    FName.FromString(asset, "amc_i4_low"), new FString(""));
                asset.Exports.Add(wp);

                // pitch/volume node for it: same shared law as the other layers
                int pnIdx = asset.Exports.Count;
                var pn = (NormalExport)Export(4).Clone();
                pn.Data = Export(4).Data.Select(p => (PropertyData)p.Clone()).ToList();
                pn.ObjectName = FName.FromString(asset, "SoundNodeModulatorContinuous_10");
                pn.OuterIndex = new FPackageIndex(1);
                var pp = Struct(pn.Data, "PitchModulationParams");
                SetFloat(pp.Value, "MinInput", 1000f, "low-as-high.pitch");
                SetFloat(pp.Value, "MaxInput", 9000f, "low-as-high.pitch");
                SetFloat(pp.Value, "MinOutput", 0.80f, "low-as-high.pitch");
                SetFloat(pp.Value, "MaxOutput", 1.80f, "low-as-high.pitch");
                var pv = Struct(pn.Data, "VolumeModulationParams");
                SetFloat(pv.Value, "MinOutput", 0.60f, "low-as-high.volume");
                AddFloat(pv.Value, "MaxOutput", 1.00f, "low-as-high.volume");
                var pnKids = (ArrayPropertyData)Find(pn.Data, "ChildNodes");
                pnKids.Value[0] = new ObjectPropertyData(FName.FromString(asset, "0")) { Value = new FPackageIndex(wpIdx + 1) };
                asset.Exports.Add(pn);

                // crossfade opening into the high section
                int xfIdx = asset.Exports.Count;
                var xf = (NormalExport)Export(12).Clone();
                xf.Data = Export(12).Data.Select(p => (PropertyData)p.Clone()).ToList();
                xf.ObjectName = FName.FromString(asset, "SoundNodeParamCrossFade_5");
                xf.OuterIndex = new FPackageIndex(1);
                var xfArr = (ArrayPropertyData)Find(xf.Data, "CrossFadeInput");
                var xfEl = (StructPropertyData)xfArr.Value[0];
                ((FloatPropertyData)Find(xfEl.Value, "FadeInDistanceStart")).Value = 3500f;
                ((FloatPropertyData)Find(xfEl.Value, "FadeInDistanceEnd")).Value = 4500f;
                ((FloatPropertyData)Find(xfEl.Value, "FadeOutDistanceStart")).Value = 1e12f;
                ((FloatPropertyData)Find(xfEl.Value, "FadeOutDistanceEnd")).Value = 1e12f;
                var xfKids = (ArrayPropertyData)Find(xf.Data, "ChildNodes");
                xfKids.Value[0] = new ObjectPropertyData(FName.FromString(asset, "0")) { Value = new FPackageIndex(pnIdx + 1) };
                asset.Exports.Add(xf);

                var mixer = (ArrayPropertyData)Find(Export(3).Data, "ChildNodes");
                var vols = (ArrayPropertyData)Find(Export(3).Data, "InputVolume");
                var newKids = mixer.Value.ToList();
                newKids.Add(new ObjectPropertyData(FName.FromString(asset, "3")) { Value = new FPackageIndex(xfIdx + 1) });
                mixer.Value = newKids.ToArray();
                var newVols = vols.Value.ToList();
                newVols.Add(new FloatPropertyData(FName.FromString(asset, "3")) { Value = 1.25f });
                vols.Value = newVols.ToArray();
                Console.WriteLine($"  added waveplayer #{wpIdx}, pitch node #{pnIdx}, crossfade #{xfIdx}; mixer inputs now {mixer.Value.Length}");
                break;
            }

            case "amci4rpm":
            {
                // MaxRPM 6500 -> 8500 (ratio 1.307692). Every rpm breakpoint in the cue is
                // scaled by that ratio so the layer transitions keep the same shape/ratios
                // relative to the rev range.
                const float K = 1.307692f;
                void Xf(int ex, float fin0, float fin1, float fout0, float fout1)
                {
                    var a = (ArrayPropertyData)Find(Export(ex).Data, "CrossFadeInput");
                    var e = (StructPropertyData)a.Value[0];
                    ((FloatPropertyData)Find(e.Value, "FadeInDistanceStart")).Value = fin0 * K;
                    ((FloatPropertyData)Find(e.Value, "FadeInDistanceEnd")).Value = fin1 * K;
                    ((FloatPropertyData)Find(e.Value, "FadeOutDistanceStart")).Value = fout0 * K;
                    ((FloatPropertyData)Find(e.Value, "FadeOutDistanceEnd")).Value = fout1 * K;
                    Console.WriteLine($"  xfade #{ex}: in {fin0 * K:F0}-{fin1 * K:F0} out {fout0 * K:F0}-{fout1 * K:F0}");
                }
                Xf(10, 10f, 10f, 1500f, 2000f);          // idle
                Xf(11, 1800f, 2000f, 4000f, 7000f);      // mid section + undertone tail
                Xf(12, 1200f, 5000f, 1e9f, 1e9f);        // high bed
                Xf(19, 3500f, 4500f, 1e9f, 1e9f);        // low-as-high section

                // pitch law 1000-9000 -> 1308-11769 keeps the same rate at the same relative rpm
                foreach (var ex in new[] { 6, 4, 7 })
                {
                    var pp = Struct(Export(ex).Data, "PitchModulationParams");
                    ((FloatPropertyData)Find(pp.Value, "MinInput")).Value = 1000f * K;
                    ((FloatPropertyData)Find(pp.Value, "MaxInput")).Value = 9000f * K;
                }
                var pn = Struct(Export(18).Data, "PitchModulationParams");
                ((FloatPropertyData)Find(pn.Value, "MinInput")).Value = 1000f * K;
                ((FloatPropertyData)Find(pn.Value, "MaxInput")).Value = 9000f * K;
                // the rpm-driven VOLUME ramps were authored over 500-10000 too - scale them
                foreach (var ex in new[] { 4, 7, 8, 18 })
                {
                    try
                    {
                        var vp = Struct(Export(ex).Data, "VolumeModulationParams");
                        var mi = Find(vp.Value, "MinInput") as FloatPropertyData;
                        var ma = Find(vp.Value, "MaxInput") as FloatPropertyData;
                        if (mi != null) mi.Value = 500f * K;
                        if (ma != null) ma.Value = 10000f * K;
                    }
                    catch (Exception ex2) { Console.WriteLine($"  volume ramp #{ex}: skipped ({ex2.GetType().Name})"); }
                }
                Console.WriteLine("  pitch law -> 1308-11769 rpm; volume ramps -> 654-13077 rpm");
                break;
            }

            case "enginerpm":
            {
                var ep = Struct(Export(0).Data, "EngineProperty");
                SetFloat(ep.Value, "MaxRPM", 8500f, "engine.MaxRPM");
                SetFloat(ep.Value, "MaxTorque", 593000f, "engine.MaxTorque");
                Console.WriteLine("  engine: MaxRPM 8500, MaxTorque 593000 (peak ~50.0 hp @ ~7900)");
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
