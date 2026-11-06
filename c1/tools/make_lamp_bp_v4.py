import unreal, json, traceback

# Task 2, pass 4: fix the light colour (unreal.Color positional args are B,G,R,A in 5.5 —
# positional (255,100,0) produced b=255,g=100,r=0 = blue), verify the real component count
# on the CDO, add the two member variables via EdGraphPinType, recompile and save.
PATH = "/Game/Mods/C1Full/Blueprints/BP_C1_Lamp"
out = {"steps": [], "params": {}, "handles": [], "api": {}, "components_cdo": None}


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
gen = step("generated_class", lambda: bel.generated_class(bp))


def count_components():
    cdo = unreal.get_default_object(gen)
    try:
        lights = cdo.get_components_by_class(unreal.SpotLightComponent)
        out["components_cdo"] = "SpotLight=%d" % len(lights)
        return out["components_cdo"]
    except Exception as e:
        out["components_cdo"] = "probe failed: %r" % (e,)
        raise


step("count components on CDO", count_components)


def fix_targets():
    handles = sds.k2_gather_subobject_data_for_blueprint(bp)
    out["handles"] = []
    n = 0
    for h in handles:
        d = SDL.get_data(h)
        name = str(SDL.get_display_name(d))
        entry = {"name": name}
        try:
            obj = SDL.get_object_for_blueprint(d, bp)
            entry["class"] = obj.get_class().get_name()
            entry["addr"] = hex(obj.get_path_name().__hash__())
            entry["path"] = obj.get_path_name()
        except Exception as e:
            entry["class"] = "lookup FAIL %r" % (e,)
            out["handles"].append(entry)
            continue
        out["handles"].append(entry)
        if "Light" not in name:
            continue
        n += 1
        # keyword args: the struct's positional order is B,G,R,A — do not use it
        for prop, kwargs in (
            ("light_color", dict(r=255, g=100, b=0, a=255)),
            ("attenuation_radius", None),
        ):
            try:
                if kwargs is not None:
                    obj.set_editor_property(prop, unreal.Color(**kwargs))
                got = obj.get_editor_property(prop)
                out["params"][prop] = "ok -> %r" % (got,)
            except Exception as e:
                out["params"][prop] = "FAIL %r" % (e,)
    return "light targets=%d" % n


step("fix light colour", fix_targets)


def add_var(name, category):
    pt = unreal.EdGraphPinType()
    pt.set_editor_property("pin_category", category)
    ok = bel.add_member_variable(bp, name, pt)
    return "%s -> %s" % (name, ok)


step("add variable bLit", lambda: add_var("bLit", "bool"))
step("add variable RegisterRadius", lambda: add_var("RegisterRadius", "real"))
step("compile", lambda: bel.compile_blueprint(bp))
step("save", lambda: eal.save_loaded_asset(bp))

bad = [s for s in out["steps"] if not s["ok"]]
out["summary"] = "LAMPBP4 ok=%d failed=%d cdo=%s" % (
    len(out["steps"]) - len(bad), len(bad), out.get("components_cdo"))
with open("D:/C1FullMirror/Scripts/make_lamp_bp.json", "w") as f:
    json.dump(out, f, indent=1)
print(out["summary"])
