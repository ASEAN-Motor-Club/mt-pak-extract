import unreal, json, traceback

# Task 2 (P0): author /Game/Mods/C1Full/Blueprints/BP_C1_Lamp inside D:\C1FullMirror.
#
# Why our own BP: placing instances of game BP classes from this project ships a
# dummy-backed export and the game dies on load with RF_NeedLoad. A plain-Actor
# parent of ours is safe.
#
# Pattern copied from the proven D:\UEProjects\C1\Scripts\bp_create.py harness
# (BlueprintEditorLibrary.create_blueprint_asset_with_parent + SubobjectDataSubsystem).

out = {"steps": [], "params": {}}
PATH = "/Game/Mods/C1Full/Blueprints/BP_C1_Lamp"


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

if eal.does_asset_exist(PATH):
    step("delete existing", lambda: eal.delete_asset(PATH))

bp = step("create_blueprint_asset_with_parent",
          lambda: bel.create_blueprint_asset_with_parent(unreal.Actor, PATH))
if bp is None:
    def via_factory():
        at = unreal.AssetToolsHelpers.get_asset_tools()
        f = unreal.BlueprintFactory()
        f.set_editor_property("parent_class", unreal.Actor)
        return at.create_asset(PATH.rsplit("/", 1)[-1], PATH.rsplit("/", 1)[0],
                               unreal.Blueprint, f)
    bp = step("create via BlueprintFactory", via_factory)

if bp is None:
    with open("D:/C1FullMirror/Scripts/make_lamp_bp.json", "w") as f:
        json.dump(out, f, indent=1)
    raise SystemExit("could not create the blueprint")


def add_light_component():
    handles = sds.k2_gather_subobject_data_for_blueprint(bp)
    root = handles[0]
    params = unreal.AddNewSubobjectParams(parent_handle=root,
                                          new_class=unreal.SpotLightComponent,
                                          blueprint_context=bp)
    res = sds.add_new_subobject(params)
    handle = res[0] if isinstance(res, (tuple, list)) else res
    sds.rename_subobject(handle, unreal.Text("Light"))
    return handle


handle = step("add SpotLightComponent", add_light_component)

# Defaults on the component template. Each property is probed separately and recorded,
# because a wrong property name must not abort the whole authoring run.
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
    if handle is None:
        raise RuntimeError("no component handle")
    obj = unreal.SubobjectDataBlueprintFunctionLibrary.get_object_for_blueprint(handle)
    if obj is None:
        raise RuntimeError("get_object_for_blueprint returned None")
    for name, value in WANT:
        if value is None:
            out["params"][name] = "SKIP (enum missing)"
            continue
        try:
            obj.set_editor_property(name, value)
            got = obj.get_editor_property(name)
            out["params"][name] = "ok -> %s" % (got,)
        except Exception as e:
            out["params"][name] = "FAIL %r" % (e,)
    return "applied"


step("apply component defaults", apply_defaults)
step("add_member_variable bLit",
     lambda: bel.add_member_variable(bp, "bLit", unreal.EditorBlueprintLibraryType.BOOLEAN))
step("add_member_variable RegisterRadius",
     lambda: bel.add_member_variable(bp, "RegisterRadius", unreal.EditorBlueprintLibraryType.FLOAT))
step("compile_blueprint", lambda: bel.compile_blueprint(bp))
step("save", lambda: eal.save_loaded_asset(bp))


def describe():
    gen = bel.generated_class(bp)
    comps = []
    for c in sds.k2_gather_subobject_data_for_blueprint(bp):
        d = unreal.SubobjectDataBlueprintFunctionLibrary.get_data(c)
        comps.append(str(unreal.SubobjectDataBlueprintFunctionLibrary.get_display_name(d)))
    out["class"] = str(gen)
    out["components"] = comps
    return "comps=%s" % comps


step("describe", describe)
step("save final", lambda: eal.save_loaded_asset(bp))

ok = [s for s in out["steps"] if s["ok"]]
bad = [s for s in out["steps"] if not s["ok"]]
out["summary"] = "LAMPBP ok=%d failed=%d class=%s" % (
    len(ok), len(bad), out.get("class", "?"))
with open("D:/C1FullMirror/Scripts/make_lamp_bp.json", "w") as f:
    json.dump(out, f, indent=1)
print(out["summary"])
for s in bad:
    print("FAILED", s["step"], s.get("error", "")[:400])
