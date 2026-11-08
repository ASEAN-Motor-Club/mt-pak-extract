import unreal, json, traceback

# Task 2, pass 6 (values chosen in game 2026-11-07): the lamp must be LIT and AIMED by default.
#
# Two defects found in-game:
#   1. template had visible=False and intensity=2 (unitless). UE unitless 2 is a match flame;
#      the runtime Lua could not fix it because the component handle it reached was not a real
#      component object (SetIntensity/SetVisibility failed silently inside pcall).
#   2. a SpotLightComponent with no rotation points along +X, so a lamp placed at road height
#      was shining sideways, not down at the road.
PATH = "/Game/Mods/C1Full/Blueprints/BP_C1_Lamp"
out = {"steps": [], "params": {}, "handles": []}
WANT = [
    ("visible", True),
    ("intensity", 200000.0),
    ("attenuation_radius", 4000.0),
    ("inner_cone_angle", 20.0),
    ("outer_cone_angle", 60.0),
    ("cast_shadows", False),
    ("mobility", getattr(unreal.ComponentMobility, "MOVABLE", None)),
    ("intensity_units", getattr(unreal.LightUnits, "UNITLESS", None)),
    ("light_color", unreal.Color(r=255, g=214, b=170, a=255)),
    ("relative_rotation", unreal.Rotator(roll=0.0, pitch=-90.0, yaw=0.0)),
]


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

bp = step("load asset", lambda: eal.load_asset(PATH))


def apply():
    n = 0
    seen = set()
    for h in sds.k2_gather_subobject_data_for_blueprint(bp):
        d = SDL.get_data(h)
        name = str(SDL.get_display_name(d))
        if "Light" not in name or name in seen:
            continue
        seen.add(name)
        obj = SDL.get_object_for_blueprint(d, bp)
        out["handles"].append(name)
        for prop, value in WANT:
            if value is None:
                continue
            try:
                obj.set_editor_property(prop, value)
                out["params"][prop] = "%r" % (obj.get_editor_property(prop),)
                n += 1
            except Exception as e:
                out["params"][prop] = "FAIL %r" % (e,)
    return "applied=%d" % n


step("apply lit+aimed defaults", apply)
step("compile", lambda: bel.compile_blueprint(bp))
step("save", lambda: eal.save_loaded_asset(bp))

bad = [s for s in out["steps"] if not s["ok"]]
out["summary"] = "LAMPBP6 ok=%d failed=%d" % (len(out["steps"]) - len(bad), len(bad))
with open("D:/C1FullMirror/Scripts/make_lamp_bp.json", "w") as f:
    json.dump(out, f, indent=1)
print(out["summary"])
