import unreal, json, traceback

# Task 2, pass 3: apply the real SpotLight defaults and diagnose the component list.
#   5.5 signatures that matter:
#     SubobjectDataBlueprintFunctionLibrary.get_object_for_blueprint(DATA, blueprint)  <- data, not handle
#     BlueprintEditorLibrary.add_member_variable(...)  <- docstring printed below for the next pass
PATH = "/Game/Mods/C1Full/Blueprints/BP_C1_Lamp"
out = {"steps": [], "params": {}, "handles": [], "api": {}}


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
SDL = unreal.SubobjectDataBlueprintFunctionLibrary

out["api"]["add_member_variable_doc"] = (bel.add_member_variable.__doc__ or "")[:800]

bp = step("load asset", lambda: eal.load_asset(PATH))

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


def inspect_and_apply():
    handles = sds.k2_gather_subobject_data_for_blueprint(bp)
    out["handles"] = []
    applied = 0
    for h in handles:
        d = SDL.get_data(h)
        name = str(SDL.get_display_name(d))
        info = {"name": name}
        for probe in ("is_component", "get_object_for_blueprint"):
            pass
        try:
            info["class"] = str(SDL.get_object_for_blueprint(d, bp).get_class().get_name())
        except Exception as e:
            info["class"] = "lookup FAIL %r" % (e,)
        out["handles"].append(info)
        if "Light" not in name:
            continue
        try:
            obj = SDL.get_object_for_blueprint(d, bp)
        except Exception as e:
            out["params"]["_lookup"] = "FAIL %r" % (e,)
            continue
        for prop, value in WANT:
            if value is None:
                out["params"][prop] = "SKIP (enum missing)"
                continue
            try:
                obj.set_editor_property(prop, value)
                out["params"][prop] = "ok -> %r" % (obj.get_editor_property(prop),)
                applied += 1
            except Exception as e:
                out["params"][prop] = "FAIL %r" % (e,)
    return "applied=%d handles=%d" % (applied, len(handles))


step("inspect + apply defaults", inspect_and_apply)
step("compile", lambda: bel.compile_blueprint(bp))
step("save", lambda: eal.save_loaded_asset(bp))

bad = [s for s in out["steps"] if not s["ok"]]
out["summary"] = "LAMPBP3 ok=%d failed=%d" % (len(out["steps"]) - len(bad), len(bad))
with open("D:/C1FullMirror/Scripts/make_lamp_bp.json", "w") as f:
    json.dump(out, f, indent=1)
print(out["summary"])
