import unreal, json, traceback

# Task 2, pass 2: the Blueprint now EXISTS (created via BlueprintFactory); this pass
#   - applies the SpotLight defaults on the component template
#   - adds the two member variables with whatever API 5.5 actually exposes
#   - records which API names exist so the next pass is not guesswork
#
# 5.5 facts learned the hard way:
#   bel.create_blueprint_asset_with_parent(Actor, PATH)  -> TypeError (nativize)
#   unreal.EditorBlueprintLibraryType                   -> does not exist
#   SubobjectDataBlueprintFunctionLibrary.get_object_for_blueprint(handle) -> needs (handle, blueprint)

PATH = "/Game/Mods/C1Full/Blueprints/BP_C1_Lamp"
out = {"steps": [], "params": {}, "api": {}}


def step(name, fn):
    try:
        r = fn()
        out["steps"].append({"step": name, "ok": True, "result": str(r)})
        return r
    except Exception:
        out["steps"].append({"step": name, "ok": False, "error": traceback.format_exc()})
        return None


bel = unreal.BlueprintEditorLibrary
eal = unreal.EditorAssetLibrary
sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)

# --- what the API actually offers -------------------------------------------
out["api"]["unreal_attrs_variable"] = [n for n in dir(unreal) if "Variable" in n][:40]
out["api"]["unreal_attrs_type_enum"] = [n for n in dir(unreal)
                                        if n.endswith("Type") or "BlueprintLibraryType" in n][:40]
out["api"]["bel_methods"] = [n for n in dir(bel) if "variable" in n.lower() or "graph" in n.lower()]

bp = step("load asset", lambda: eal.load_asset(PATH))
if bp is None:
    with open("D:/C1FullMirror/Scripts/make_lamp_bp.json", "w") as f:
        json.dump(out, f, indent=1)
    raise SystemExit("BP_C1_Lamp missing")

WANT = [
    ("attenuation_radius", 2000.0),
    ("inner_cone_angle", 25.0),
    ("outer_cone_angle", 170.0),
    ("intensity", 2.0),
    ("cast_shadows", False),
    ("mobility", getattr(unreal.ComponentMobility, "MOVABLE", None)),
    ("intensity_units", getattr(unreal.LightUnits, "UNITLESS", None)),
    ("light_color", unreal.Color(255, 100, 0, 255)),
    ("visible", False),
]


def apply_defaults():
    handles = sds.k2_gather_subobject_data_for_blueprint(bp)
    targets = []
    for h in handles:
        d = unreal.SubobjectDataBlueprintFunctionLibrary.get_data(h)
        name = str(unreal.SubobjectDataBlueprintFunctionLibrary.get_display_name(d))
        if "Light" not in name:
            continue
        try:
            obj = unreal.SubobjectDataBlueprintFunctionLibrary.get_object_for_blueprint(h, bp)
        except Exception as e:
            out["params"]["_lookup"] = "FAIL %r" % (e,)
            continue
        targets.append((name, obj))
    out["params"]["_targets"] = [n for n, _ in targets]
    for name, obj in targets:
        for prop, value in WANT:
            if value is None:
                out["params"][prop] = "SKIP (enum missing)"
                continue
            try:
                obj.set_editor_property(prop, value)
                out["params"][prop] = "ok -> %r" % (obj.get_editor_property(prop),)
            except Exception as e:
                out["params"][prop] = "FAIL %r" % (e,)
    return "targets=%d" % len(targets)


step("apply component defaults", apply_defaults)


def add_var(name, type_names):
    last = None
    for tname in type_names:
        t = getattr(unreal, tname, None)
        if t is None:
            continue
        member = getattr(t, "BOOLEAN", None) or getattr(t, "FLOAT", None)
        if member is None:
            continue
        try:
            bel.add_member_variable(bp, name, member)
            return "via %s" % tname
        except Exception as e:
            last = "%s: %r" % (tname, e)
    raise RuntimeError("no working type api; last=%s" % last)


step("add variable bLit", lambda: add_var("bLit", ["BlueprintEditorLibraryVariableType",
                                                  "EditorBlueprintLibraryType",
                                                  "BlueprintVariableType",
                                                  "EdGraphPinType"]))
step("add variable RegisterRadius", lambda: add_var("RegisterRadius", ["BlueprintEditorLibraryVariableType",
                                                                      "EditorBlueprintLibraryType",
                                                                      "BlueprintVariableType",
                                                                      "EdGraphPinType"]))
step("compile", lambda: bel.compile_blueprint(bp))
step("save", lambda: eal.save_loaded_asset(bp))


def describe():
    handles = sds.k2_gather_subobject_data_for_blueprint(bp)
    comps = []
    for h in handles:
        d = unreal.SubobjectDataBlueprintFunctionLibrary.get_data(h)
        comps.append(str(unreal.SubobjectDataBlueprintFunctionLibrary.get_display_name(d)))
    out["components"] = comps
    out["class"] = str(bel.generated_class(bp))
    return "comps=%s" % comps


step("describe", describe)
step("save final", lambda: eal.save_loaded_asset(bp))

bad = [s for s in out["steps"] if not s["ok"]]
out["summary"] = "LAMPBP2 ok=%d failed=%d" % (len(out["steps"]) - len(bad), len(bad))
with open("D:/C1FullMirror/Scripts/make_lamp_bp.json", "w") as f:
    json.dump(out, f, indent=1)
print(out["summary"])
